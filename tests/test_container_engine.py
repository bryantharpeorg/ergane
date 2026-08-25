"""104-US5: bring-up, bounded readiness, the port preflight and verify-through.

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

Every test here is a **seam capture** (traps 11 and 14). The compose runner, the
port probe and the clock are all injected: **no Docker daemon is contacted, no
container is started and no `apparmor_parser` is run**. What a stubbed engine
"says" to verify is this file's fixture text, not a real engine's — which is
exactly why the verdict under test is the child's *exit code* and never its
words (R8).

The three properties this module exists to hold:

* **Bounded.** The readiness wait is `deploy._await_registration`'s contract with
  a port in place of a registration: an injected clock, a deadline, and a
  timeout that names the address and the bound rather than hanging.
* **Nothing is torn down on failure.** A readiness timeout and a failing verify
  both leave the engine running, so the assertion is on the recorded argv: no
  `down`, no `stop`, no `rm`, ever.
* **The verdict is not parsed.** `render_findings` emits free text with no
  machine-readable form, so a host that read `[PASS] name: detail` back into a
  verdict would turn a version skew into a silent pass.
"""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest

from factory.cli.errors import OperatorError
from factory.supervision import container_engine as ce
from factory.supervision import container_supervisor as cs
from factory.registry import load_registry
from factory.supervision import container_project as cp
from factory.supervision.container_manifest import write_project
from factory.supervision.container_project import (
    ENGINE_TEMPORAL_ADDRESS,
    SERVICE_NAME,
    render_env,
)
from factory.supervision.units import CommandResult

# The 104-US2 host fixture, imported rather than rebuilt: a relocated state
# home, two registered repos and a scratch build context.
from tests.test_container_project import (  # noqa: F401
    _config,
    host,
)


def _resolved(host: Any, address: str = "127.0.0.1:7233") -> cp.ContainerProject:
    """The operational project for the fixture host, from confirmed answers.

    `address` is the *host-side* `temporal.address` the operator confirmed, and
    the only thing the tests below vary: it decides the published port and must
    decide nothing inside the engine (US5-S4).
    """
    return cp.resolve_project(
        _config(address),
        registry=load_registry(host.registry_path),
        config_path=host.config_path,
        personas_path=host.personas_path,
        home=host.home,
        install_root=host.install_root,
    )

#: What a real engine's verify prints. Held here as a fixture string and
#: labelled as one: no engine produced it.
FIXTURE_VERIFY_OUTPUT = (
    "[PASS] llm: gateway at http://127.0.0.1:4000 answered\n"
    "[FAIL] temporal: Temporal at 127.0.0.1:7233 did not answer\n"
)


# ---------------------------------------------------------------------------
# The seams
# ---------------------------------------------------------------------------


class FakeCompose:
    """A compose runner that records every argv and answers from a table.

    Keyed by the compose verb — `up`, `ps`, `exec` — because that is the only
    thing a caller here varies, and a table keyed by the whole argv would pass
    while the argv drifted underneath it.
    """

    def __init__(self, **replies: CommandResult) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.replies = replies

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(argv))
        return self.replies.get(self.verb(argv), CommandResult(0, ""))

    @staticmethod
    def verb(argv: Sequence[str]) -> str:
        """The compose verb: `docker compose -f <path> <verb> …`."""
        return argv[4] if len(argv) > 4 else ""

    @property
    def verbs(self) -> list[str]:
        return [self.verb(argv) for argv in self.calls]


@dataclasses.dataclass
class FakeClock:
    """An injected clock. `sleep` advances it, so a bounded wait terminates and
    an unbounded one runs the deadline check into the ground instead of hanging
    the suite."""

    t: float = 0.0
    slept: list[float] = dataclasses.field(default_factory=list)

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def answers_after(count: int) -> Callable[[str, float], bool]:
    """A port probe that says no `count` times and yes after."""
    seen: list[str] = []

    def probe(address: str, timeout_s: float) -> bool:
        seen.append(address)
        return len(seen) > count

    probe.seen = seen  # type: ignore[attr-defined]
    return probe


def never(address: str, timeout_s: float) -> bool:
    return False


def always(address: str, timeout_s: float) -> bool:
    return True


def _ps(*services: str) -> CommandResult:
    """What `docker compose ps --services --status running` prints."""
    return CommandResult(0, "\n".join(services))


def _teardown_verbs(runner: FakeCompose) -> list[str]:
    """Every verb that would have taken the engine down. Must always be empty:
    a failure the operator cannot look at is a failure they cannot fix."""
    return [verb for verb in runner.verbs if verb in ("down", "stop", "rm", "kill")]


# ---------------------------------------------------------------------------
# T035 (US5-S1): compose up, then a bounded wait on the published address
# ---------------------------------------------------------------------------


def test_bring_up_ups_the_project_then_waits_bounded_on_the_published_address(
    host: Any,
) -> None:
    """US5-S1: `docker compose up -d` for the generated project, then the wait.

    The address waited on is derived from the project's own published port, so
    the port compose binds and the port install dials cannot drift apart.
    """
    project = _resolved(host)
    runner = FakeCompose(exec=CommandResult(0, FIXTURE_VERIFY_OUTPUT))
    clock = FakeClock()
    probe = answers_after(2)

    ce.bring_up_and_verify(
        project,
        run=runner,
        probe=probe,
        now=clock.now,
        sleep=clock.sleep,
        emit=lambda _line: None,
    )

    compose = project.directory / "compose.yaml"
    # The port was silent at the preflight, so there was nothing to ask `ps`
    # about and nothing to collide with; up, then wait, then verify.
    assert runner.verbs == ["up", "exec"]
    assert runner.calls[0] == ("docker", "compose", "-f", str(compose), "up", "-d")
    # The published port is `127.0.0.1:<host port>:7233`; the host dials the
    # first two fields of that same string.
    assert project.ports == ("127.0.0.1:7233:7233",)
    assert ce.published_address(project) == "127.0.0.1:7233"
    # Three probes: the preflight, then two polls — the second of which answered.
    assert probe.seen == ["127.0.0.1:7233"] * 3  # type: ignore[attr-defined]
    # Bounded: it polled rather than blocking, and the sleep was one poll.
    assert clock.slept == [ce.DEFAULT_POLL_S]


def test_a_readiness_timeout_names_the_address_and_the_timeout(host: Any) -> None:
    """US5-S1: the bound is named when it is reached, and nothing is torn down.

    `deploy._await_registration`'s contract: a deadline, the last observation
    reported either way, and — here — an engine left running, because a floor
    that will not answer is when an operator most needs to read its logs.
    """
    project = _resolved(host)
    runner = FakeCompose()
    clock = FakeClock()

    with pytest.raises(OperatorError) as raised:
        ce.bring_up_and_verify(
            project,
            run=runner,
            probe=never,
            now=clock.now,
            sleep=clock.sleep,
            emit=lambda _line: None,
            wait_s=12.0,
            poll_s=5.0,
        )

    message = str(raised.value)
    assert "127.0.0.1:7233" in message
    assert "12" in message
    assert "logs" in message  # the remedy: go and look
    # Bounded: the last sleep is clipped to the deadline, never past it.
    assert clock.slept == [5.0, 5.0, 2.0]
    assert clock.now() == 12.0
    assert runner.verbs == ["up"]
    assert _teardown_verbs(runner) == []


def test_the_wait_returns_the_last_observation_rather_than_raising() -> None:
    """The wait itself is a predicate; the refusal is the caller's to word."""
    clock = FakeClock()
    assert (
        ce.await_address(
            "127.0.0.1:7233",
            wait_s=3.0,
            poll_s=1.0,
            now=clock.now,
            sleep=clock.sleep,
            probe=answers_after(1),
        )
        is True
    )
    assert (
        ce.await_address(
            "127.0.0.1:7233",
            wait_s=3.0,
            poll_s=1.0,
            now=clock.now,
            sleep=clock.sleep,
            probe=never,
        )
        is False
    )


# ---------------------------------------------------------------------------
# T036 (US5-S1): verify-through streams, and never parses (R8)
# ---------------------------------------------------------------------------


def test_verify_runs_inside_the_engine_and_streams_the_child_verbatim(
    host: Any,
) -> None:
    """R8: `ergane install --verify` inside the engine, output passed through.

    The header names the engine so an operator reading a terminal knows which
    side of the mount these findings came from.
    """
    project = _resolved(host)
    runner = FakeCompose(exec=CommandResult(0, FIXTURE_VERIFY_OUTPUT))
    printed: list[str] = []

    code = ce.verify_through_engine(
        project.directory / "compose.yaml", run=runner, emit=printed.append
    )

    assert code == 0
    compose = project.directory / "compose.yaml"
    assert runner.calls[-1] == (
        "docker",
        "compose",
        "-f",
        str(compose),
        "exec",
        "-T",
        SERVICE_NAME,
        "ergane",
        "install",
        "--verify",
    )
    header = "\n".join(printed)
    assert "engine container" in header
    # Verbatim: the child's whole text, unreflowed and unsummarised.
    assert FIXTURE_VERIFY_OUTPUT in printed


def test_the_exit_code_is_the_verdict_and_the_text_is_never_parsed(
    host: Any,
) -> None:
    """R8: a version skew must surface as unreadable output, never a silent pass.

    Two runs prove the verdict is the code and nothing else: text that no
    `[PASS] name: detail` parser could read passes on exit 0, and text that
    parses perfectly *as failures* also passes on exit 0. A host that read the
    words would disagree with the engine on both.
    """
    project = _resolved(host)
    compose = project.directory / "compose.yaml"

    unreadable = "?? ergane 9.9.9: findings: {llm: ok}\n"
    assert (
        ce.verify_through_engine(
            compose,
            run=FakeCompose(exec=CommandResult(0, unreadable)),
            emit=lambda _line: None,
        )
        == 0
    )
    assert (
        ce.verify_through_engine(
            compose,
            run=FakeCompose(exec=CommandResult(0, "[FAIL] llm: nothing answered\n")),
            emit=lambda _line: None,
        )
        == 0
    )
    assert (
        ce.verify_through_engine(
            compose,
            run=FakeCompose(exec=CommandResult(3, "[PASS] llm: fine\n")),
            emit=lambda _line: None,
        )
        == 3
    )


def test_the_module_never_reaches_for_the_findings_vocabulary() -> None:
    """R8, structurally: no import of the probe registry or its renderer.

    Asserted on the source rather than on behaviour, because the failure mode
    is a *later* edit reaching for `render_findings` "just to pretty-print it"
    and re-opening the string-parsing contract this ruling closed.
    """
    source = Path(ce.__file__).read_text(encoding="utf-8")
    for forbidden in ("factory.controlplane.verify", "[PASS]", "[FAIL]"):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------------------
# T037 (US5-S2): a failing verify leaves the engine up and names a remedy
# ---------------------------------------------------------------------------


def test_a_failing_verify_leaves_the_engine_up_and_names_a_remedy(host: Any) -> None:
    """US5-S2: the install ends nonzero, the engine keeps running.

    The engine is the only place the failures can be reproduced, so taking it
    down on failure would destroy the evidence the operator was just handed.
    """
    project = _resolved(host)
    # A half-up stack again: the port answers and it is our own service, so the
    # preflight lets this through and the failure under test is verify's.
    runner = FakeCompose(
        ps=_ps(SERVICE_NAME), exec=CommandResult(1, FIXTURE_VERIFY_OUTPUT)
    )
    printed: list[str] = []

    with pytest.raises(OperatorError) as raised:
        ce.bring_up_and_verify(
            project,
            run=runner,
            probe=always,
            now=FakeClock().now,
            sleep=lambda _s: None,
            emit=printed.append,
        )

    assert raised.value.code != 0
    message = str(raised.value)
    assert "still" in message and "running" in message
    assert "logs" in message  # …and how to look at it
    assert "ergane uninstall" in message  # …and how to stop it when done
    # The findings the engine printed reached the operator before the refusal.
    assert FIXTURE_VERIFY_OUTPUT in printed
    # The whole of US5-S2, asserted on what was run: nothing came down.
    assert runner.verbs == ["ps", "up", "exec"]
    assert _teardown_verbs(runner) == []


def test_a_failed_bring_up_is_named_and_still_tears_nothing_down(host: Any) -> None:
    """A compose that refuses to start says so in compose's own words."""
    project = _resolved(host)
    runner = FakeCompose(
        ps=_ps(SERVICE_NAME), up=CommandResult(1, "no such image: ergane-local:0.3.0")
    )

    with pytest.raises(OperatorError) as raised:
        ce.bring_up_and_verify(
            project,
            run=runner,
            probe=always,
            now=FakeClock().now,
            sleep=lambda _s: None,
            emit=lambda _line: None,
        )

    assert "no such image" in str(raised.value)
    assert runner.verbs == ["ps", "up"]
    assert _teardown_verbs(runner) == []


# ---------------------------------------------------------------------------
# T038 (US5-S3): idempotent re-entry against a half-up stack
# ---------------------------------------------------------------------------


def test_a_half_up_stack_converges_rather_than_erroring(host: Any) -> None:
    """US5-S3: project on disk, service up, port answering — and it re-runs.

    The three things a re-run meets are all present, and each is the thing that
    would have made a less careful path raise: a directory that already holds
    generated files, a compose project already up, and a port already answering
    (which is a collision only when it is somebody else's — trap 6).
    """
    project = _resolved(host)

    first = write_project(project)
    assert first.written  # the first run really wrote the project

    # Re-render from the same answers and write again: identical bytes, so the
    # writer touches nothing. Idempotence is decided in the renderer, and this
    # is where the whole path inherits it.
    again = _resolved(host)
    second = write_project(again)
    assert second.written == ()
    assert set(second.unchanged) == {
        "compose.yaml",
        ".env",
        "seccomp-ergane.json",
        "ergane-engine.profile",
    }
    assert second.kept == ()

    runner = FakeCompose(
        ps=_ps(SERVICE_NAME), exec=CommandResult(0, FIXTURE_VERIFY_OUTPUT)
    )
    ce.bring_up_and_verify(
        again,
        run=runner,
        probe=always,  # the port answers: it is our own engine
        now=FakeClock().now,
        sleep=lambda _s: None,
        emit=lambda _line: None,
    )

    # It converged: preflight consulted `ps`, saw our own service, and re-upped.
    assert runner.verbs == ["ps", "up", "exec"]
    assert _teardown_verbs(runner) == []


# ---------------------------------------------------------------------------
# T039 (US5-S1): the published-port preflight (trap 6)
# ---------------------------------------------------------------------------


def test_a_port_held_by_someone_else_is_refused_before_compose_up(host: Any) -> None:
    """Trap 6: refuse before `up`, naming the collision and both remedies.

    On the reference floor `127.0.0.1:7233` is held by the *native* managed
    Temporal. Bringing the engine up onto it leaves the host CLI talking to one
    Temporal and the engine to another, and everything looks fine.
    """
    project = _resolved(host)
    runner = FakeCompose(ps=_ps())  # nothing of ours is running

    with pytest.raises(OperatorError) as raised:
        ce.bring_up_and_verify(
            project,
            run=runner,
            probe=always,  # …but something answers on the port
            now=FakeClock().now,
            sleep=lambda _s: None,
            emit=lambda _line: None,
        )

    message = str(raised.value)
    assert "127.0.0.1:7233" in message
    assert "drain" in message  # remedy 1: take the native tier down
    assert "temporal.address" in message  # remedy 2: pick a free port
    # Refused *before* anything was brought up: `ps` is the only call made.
    assert runner.verbs == ["ps"]


def test_the_same_port_answering_from_our_own_service_proceeds(host: Any) -> None:
    """The check that makes re-entry converge is the check that refuses."""
    project = _resolved(host)
    compose = project.directory / "compose.yaml"

    ours = FakeCompose(ps=_ps("other", SERVICE_NAME))
    ce.preflight_published_port(compose, "127.0.0.1:7233", run=ours, probe=always)
    assert ours.calls[0] == (
        "docker",
        "compose",
        "-f",
        str(compose),
        "ps",
        "--services",
        "--status",
        "running",
    )

    # And a silent port needs no `ps` at all: there is nothing to collide with.
    quiet = FakeCompose()
    ce.preflight_published_port(compose, "127.0.0.1:7233", run=quiet, probe=never)
    assert quiet.calls == []


def test_a_project_that_publishes_nothing_is_refused_naming_the_answer(
    host: Any,
) -> None:
    """A `temporal.address` with no port publishes no port, and an engine the
    host CLI cannot reach is not an install that succeeded."""
    project = _resolved(host, "temporal.internal")
    assert project.ports == ()

    with pytest.raises(OperatorError) as raised:
        ce.published_address(project)

    assert "temporal.address" in str(raised.value)


# ---------------------------------------------------------------------------
# T040 (US5-S4): one address convention, `host:port`, on both sides (R12)
# ---------------------------------------------------------------------------


def test_the_generated_env_names_the_engines_own_loopback_never_the_host_port(
    host: Any,
) -> None:
    """US5-S4 (a): `TEMPORAL_ADDRESS=127.0.0.1:7233` in the tree-wide spelling.

    The supervisor's children live *inside* the container, so the address they
    read is the engine's own loopback — never the host's published port, which
    is a host-side fact and belongs only in `config.toml`. Driven from a config
    whose published port is deliberately *not* 7233, so a generator that leaked
    the host's port into the engine's `.env` cannot pass.
    """
    project = _resolved(host, "127.0.0.1:17233")
    lines = render_env(project).splitlines()

    assert "TEMPORAL_ADDRESS=127.0.0.1:7233" in lines
    assert ENGINE_TEMPORAL_ADDRESS == "127.0.0.1:7233"
    # …and the host side, which is the other port entirely.
    assert project.ports == ("127.0.0.1:17233:7233",)
    assert ce.published_address(project) == "127.0.0.1:17233"
    assert not any(line.startswith("TEMPORAL_ADDRESS=127.0.0.1:17233") for line in lines)


@pytest.mark.parametrize(
    "spelled, expected",
    [
        # What the generated `.env` writes, and what 088 landed. Both must mean
        # the same endpoint, and neither may gain a second port.
        ("127.0.0.1:7233", "127.0.0.1:7233"),
        ("127.0.0.1", "127.0.0.1:7233"),
        ("localhost:7233", "localhost:7233"),
    ],
)
def test_the_supervisor_resolves_both_spellings_to_one_endpoint(
    spelled: str, expected: str
) -> None:
    """US5-S4 (b): `host:port` in, `host:port` out — never `host:port:port`.

    As landed, `_run_supervisor` built `f"{TEMPORAL_ADDRESS}:{port}"`
    unconditionally, so the tree-wide value produced `127.0.0.1:7233:7233`, the
    probe dialled host `127.0.0.1:7233`, readiness timed out and the engine never
    came up. The host-only spelling is covered too: this is a fix, not a swap of
    one broken meaning for another.
    """
    assert cs._resolve_temporal_address(spelled, cs.DEFAULT_TEMPORAL_PORT) == expected
    assert expected.count(":") == 1


def test_the_supervisors_probe_splits_one_address_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US5-S4 (b): `_probe_temporal_address` dials host `127.0.0.1` port `7233`."""
    dialled: list[tuple[Any, Any]] = []

    async def _open_connection(host: Any, port: Any) -> Any:
        dialled.append((host, port))
        raise ConnectionRefusedError

    monkeypatch.setattr(asyncio, "open_connection", _open_connection)

    assert asyncio.run(cs._probe_temporal_address(ENGINE_TEMPORAL_ADDRESS, 0.0)) is False
    assert asyncio.run(cs._probe_temporal_address("127.0.0.1", 0.0)) is False
    assert dialled == []  # the deadline is zero: bounded, and it did not dial

    assert asyncio.run(cs._probe_temporal_address(ENGINE_TEMPORAL_ADDRESS, 0.05)) is False
    assert dialled[0] == ("127.0.0.1", 7233)

    dialled.clear()
    assert asyncio.run(cs._probe_temporal_address("127.0.0.1", 0.05)) is False
    assert dialled[0] == ("127.0.0.1", cs.DEFAULT_TEMPORAL_PORT)


@pytest.mark.asyncio
async def test_the_supervisor_hands_its_children_the_env_value_unchanged(
    tmp_path: Path,
) -> None:
    """US5-S4: end to end through the supervisor's own resolution.

    The value under test is the one the generated `.env` writes, taken from the
    generator's constant rather than restated here — the two sides resolve the
    same endpoint or this test is meaningless.
    """
    argv_map = cs._child_argv(
        temporal_address=cs._resolve_temporal_address(
            ENGINE_TEMPORAL_ADDRESS, cs.DEFAULT_TEMPORAL_PORT
        ),
        db_filename="/tmp/engine.db",
    )
    joined = " ".join(argv_map["temporal"])
    assert "127.0.0.1:7233:7233" not in joined

    probed: list[str] = []

    async def probe(address: str, timeout: float) -> bool:
        probed.append(address)
        return False

    async def start_child(name: str, argv: list[str]) -> Any:
        class _Stub:
            async def wait(self) -> int:
                return 0

            def stop(self) -> None:
                return None

            def kill(self) -> None:
                return None

        return _Stub()

    code = await cs._run_supervisor(
        {
            "temporal_address": ENGINE_TEMPORAL_ADDRESS,
            "readiness_timeout_s": 0.01,
            "state_home": str(tmp_path / "state"),
        },
        start_child=start_child,
        probe_address=probe,
    )

    assert code == 1  # the probe never answered, which is what we drove
    assert probed == [ENGINE_TEMPORAL_ADDRESS]
