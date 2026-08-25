"""104-US5: bring-up, bounded readiness, the port preflight and verify-through.

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

Every test here is a **seam capture** (traps 11 and 14): the compose runner,
the port probe and the clock are injected, so **no Docker daemon is contacted,
no container is started and no `apparmor_parser` is run**. What the stubbed
engine "says" to verify is this file's fixture text — which is exactly why the
verdict under test is its *exit code* (R8).
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

# 104-US2's host fixture: relocated state home, two repos, a build context.
from tests.test_container_project import (  # noqa: F401
    _config,
    host,
)


def _resolved(host: Any, address: str = "127.0.0.1:7233") -> cp.ContainerProject:
    """The operational project for the fixture host. `address` is the host-side
    `temporal.address`: it decides the published port and nothing inside."""
    return cp.resolve_project(
        _config(address),
        registry=load_registry(host.registry_path),
        config_path=host.config_path,
        personas_path=host.personas_path,
        home=host.home,
        install_root=host.install_root,
    )

#: A fixture string, labelled as one: no engine produced it.
FIXTURE_VERIFY_OUTPUT = (
    "[PASS] llm: gateway at http://127.0.0.1:4000 answered\n"
    "[FAIL] temporal: Temporal at 127.0.0.1:7233 did not answer\n"
)


# --- The seams ---


class FakeCompose:
    """A compose runner recording every argv, answering from a verb-keyed
    table — a table keyed by the whole argv would pass while the argv drifted.
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
    """An injected clock; `sleep` advances it, so an unbounded wait would run
    the deadline check into the ground rather than hang the suite."""

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


def _bring_up(
    project: Any,
    runner: FakeCompose,
    probe: Callable[[str, float], bool],
    *,
    clock: FakeClock | None = None,
    emit: Callable[[str], None] | None = None,
    **bounds: float,
) -> None:
    """`bring_up_and_verify` with all four seams closed, spelled once."""
    clock = FakeClock() if clock is None else clock
    ce.bring_up_and_verify(
        project,
        run=runner,
        probe=probe,
        now=clock.now,
        sleep=clock.sleep,
        emit=(lambda _line: None) if emit is None else emit,
        **bounds,
    )


# --- T035 (US5-S1): compose up, then a bounded wait on the published address ---


def test_bring_up_ups_the_project_then_waits_bounded_on_the_published_address(
    host: Any,
) -> None:
    """US5-S1: `docker compose up -d`, then the wait — on an address derived
    from the project's own published port, so the two cannot drift apart."""
    project = _resolved(host)
    runner = FakeCompose(exec=CommandResult(0, FIXTURE_VERIFY_OUTPUT))
    clock = FakeClock()
    probe = answers_after(2)

    _bring_up(project, runner, probe, clock=clock)

    compose = project.directory / "compose.yaml"
    # The port was silent at the preflight, so there was nothing to ask `ps`
    # about and nothing to collide with; up, then wait, then verify.
    assert runner.verbs == ["up", "exec"]
    assert runner.calls[0] == ("docker", "compose", "-f", str(compose), "up", "-d")
    # `127.0.0.1:<host port>:7233`; the host dials its first two fields.
    assert project.ports == ("127.0.0.1:7233:7233",)
    assert ce.published_address(project) == "127.0.0.1:7233"
    # The preflight, then two polls, the second of which answered.
    assert probe.seen == ["127.0.0.1:7233"] * 3  # type: ignore[attr-defined]
    assert clock.slept == [ce.DEFAULT_POLL_S]


def test_a_readiness_timeout_names_the_address_and_the_timeout(host: Any) -> None:
    """US5-S1: the bound is named when reached, and nothing is torn down — a
    floor that will not answer is when an operator most needs its logs."""
    project = _resolved(host)
    runner = FakeCompose()
    clock = FakeClock()

    with pytest.raises(OperatorError) as raised:
        _bring_up(project, runner, never, clock=clock, wait_s=12.0, poll_s=5.0)

    message = str(raised.value)
    assert "127.0.0.1:7233" in message
    assert "12" in message
    assert "logs" in message  # the remedy: go and look
    assert clock.slept  # clipped to the deadline, never past it == [5.0, 5.0, 2.0]
    assert clock.now() == 12.0
    assert runner.verbs == ["up"]
    assert _teardown_verbs(runner) == []


def test_the_wait_returns_the_last_observation_rather_than_raising() -> None:
    """The wait itself is a predicate; the refusal is the caller's to word."""
    clock = FakeClock()
    bounds = dict(wait_s=3.0, poll_s=1.0, now=clock.now, sleep=clock.sleep)
    assert ce.await_address("127.0.0.1:7233", probe=answers_after(1), **bounds) is True
    assert ce.await_address("127.0.0.1:7233", probe=never, **bounds) is False


# --- T036 (US5-S1): verify-through streams, and never parses (R8) ---


def test_verify_runs_inside_the_engine_and_streams_the_child_verbatim(
    host: Any,
) -> None:
    """R8: `ergane install --verify` inside the engine, output passed through
    under a header naming which side of the mount it came from."""
    project = _resolved(host)
    runner = FakeCompose(exec=CommandResult(0, FIXTURE_VERIFY_OUTPUT))
    printed: list[str] = []

    code = ce.verify_through_engine(
        project.directory / "compose.yaml", run=runner, emit=printed.append
    )

    assert code == 0
    compose = project.directory / "compose.yaml"
    assert runner.calls[-1] == (
        "docker", "compose", "-f", str(compose),
        "exec", "-T", SERVICE_NAME, "ergane", "install", "--verify",
    )
    assert "engine container" in "\n".join(printed)
    assert FIXTURE_VERIFY_OUTPUT in printed  # verbatim, unreflowed


def test_the_exit_code_is_the_verdict_and_the_text_is_never_parsed(
    host: Any,
) -> None:
    """R8: a skew must surface as unreadable output, never a silent pass.

    Three runs, and the verdict is the code in all of them — a host that read
    the words would disagree with the engine on every one.
    """
    compose = _resolved(host).directory / "compose.yaml"
    said = [
        CommandResult(0, "?? ergane 9.9.9: findings: {llm: ok}\n"),  # unreadable
        CommandResult(0, "[FAIL] llm: nothing answered\n"),  # readable, and wrong
        CommandResult(3, "[PASS] llm: fine\n"),  # readable, and wrong the other way
    ]
    for result in said:
        assert (
            ce.verify_through_engine(
                compose,
                run=FakeCompose(exec=result),
                emit=lambda _line: None,
            )
            == result.code
        )


def test_the_module_never_reaches_for_the_findings_vocabulary() -> None:
    """R8, structurally: no import of the probe registry or its renderer.

    On the source, not on behaviour: the failure mode is a *later* edit reaching
    for the findings vocabulary "just to pretty-print it".
    """
    source = Path(ce.__file__).read_text(encoding="utf-8")
    for forbidden in ("factory.controlplane.verify", "[PASS]", "[FAIL]"):
        assert forbidden not in source, forbidden


# --- T037 (US5-S2): a failing verify leaves the engine up and names a remedy ---


def test_a_failing_verify_leaves_the_engine_up_and_names_a_remedy(host: Any) -> None:
    """US5-S2: nonzero, engine still running — it is the only place the
    failures reproduce, so taking it down destroys the evidence."""
    project = _resolved(host)
    # A half-up stack again: the port answers and it is our own service, so the
    # preflight lets this through and the failure under test is verify's.
    runner = FakeCompose(
        ps=_ps(SERVICE_NAME), exec=CommandResult(1, FIXTURE_VERIFY_OUTPUT)
    )
    printed: list[str] = []

    with pytest.raises(OperatorError) as raised:
        _bring_up(project, runner, always, emit=printed.append)

    assert raised.value.code != 0
    message = str(raised.value)
    assert "still" in message and "running" in message
    assert "logs" in message  # …and how to look at it
    assert "ergane uninstall" in message  # …and how to stop it when done
    assert FIXTURE_VERIFY_OUTPUT in printed  # the findings came first
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
        _bring_up(project, runner, always)

    assert "no such image" in str(raised.value)
    assert runner.verbs == ["ps", "up"]
    assert _teardown_verbs(runner) == []


# --- T038 (US5-S3): idempotent re-entry against a half-up stack ---


def test_a_half_up_stack_converges_rather_than_erroring(host: Any) -> None:
    """US5-S3: project on disk, service up, port answering — and it re-runs.

    Each would have made a less careful path raise; a port answering is a
    collision only when it is somebody else's (trap 6).
    """
    project = _resolved(host)

    first = write_project(project)
    assert first.written  # the first run really wrote the project

    # Re-render from the same answers: identical bytes, so the writer touches
    # nothing. Idempotence is decided in the renderer; this inherits it.
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
    _bring_up(again, runner, always)  # the port answers: it is our own engine

    # It converged: preflight consulted `ps`, saw our own service, and re-upped.
    assert runner.verbs == ["ps", "up", "exec"]
    assert _teardown_verbs(runner) == []


# --- T039 (US5-S1): the published-port preflight (trap 6) ---


def test_a_port_held_by_someone_else_is_refused_before_compose_up(host: Any) -> None:
    """Trap 6: refuse before `up`, naming the collision and both remedies.

    On the reference floor that port is the *native* managed Temporal's; taking
    it leaves the CLI on one Temporal and the engine on another, both healthy.
    """
    project = _resolved(host)
    runner = FakeCompose(ps=_ps())  # nothing of ours is running

    with pytest.raises(OperatorError) as raised:
        _bring_up(project, runner, always)  # …but something answers on the port

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
        "docker", "compose", "-f", str(compose), "ps", "--services", "--status", "running",
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


# --- T040 (US5-S4): one address convention, `host:port`, on both sides (R12) ---


def test_the_generated_env_names_the_engines_own_loopback_never_the_host_port(
    host: Any,
) -> None:
    """US5-S4 (a): `TEMPORAL_ADDRESS=127.0.0.1:7233` in the tree-wide spelling.

    The children live *inside* the container, so what they read is the engine's
    own loopback. Driven from a config whose published port is deliberately not
    7233, so a generator leaking it into the `.env` cannot pass.
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

    As landed, `_run_supervisor` appended a port unconditionally, so the
    tree-wide value became `127.0.0.1:7233:7233`, the probe dialled host
    `127.0.0.1:7233` and the engine never came up. The host-only spelling is
    covered too: a fix, not a swap of one broken meaning for another.
    """
    assert cs._resolve_temporal_address(spelled, cs.DEFAULT_TEMPORAL_PORT) == expected
    assert expected.count(":") == 1


def test_the_supervisors_probe_splits_one_address_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US5-S4 (b): `_probe_temporal_address` dials host `127.0.0.1` port `7233`."""
    dialled: list[tuple[Any, Any]] = []

    async def _open(host: Any, port: Any) -> Any:
        dialled.append((host, port))
        raise ConnectionRefusedError

    monkeypatch.setattr(asyncio, "open_connection", _open)

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
    """US5-S4: end to end through the supervisor's own resolution, on the value
    the generated `.env` writes — taken from the generator's constant rather
    than restated, or the two sides are not being compared at all."""
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

    class _Stub:  # the ChildController shape, and nothing else
        async def wait(self) -> int:
            return 0

        stop = kill = lambda self: None  # noqa: E731

    async def start_child(name: str, argv: list[str]) -> Any:
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
