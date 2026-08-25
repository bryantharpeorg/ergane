"""104-US5: `ergane install` end to end onto the engine container.

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

`tests/test_container_engine.py` proves each step; this module proves the
**order**, through the real `install_command` and the real interview — because
every step is correct in isolation and wrong in the wrong place: personas before
the engine that reads them comes up (R3), the project resolved before the sudo
prompt (R10), the profile decided before a byte is written (104-US4), and the
port preflighted before `compose up` (trap 6).

Gateway mode (trap 2): `_interview_personas` reads
`document["llm"]["master_key_env"]` and `_DIRECT_SEED` has no such key, so
direct mode raises `KeyError` inside it — 103's defect, inherited.

**Seam capture** (traps 11 and 14): the daemon predicate, the compose runner,
the port probe and the privileged runner are all injected, so no daemon is
contacted, no container started and no kernel policy touched. The verify output
the stubbed engine "prints" is this file's fixture text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

import pytest

import factory.cli.install as install_module
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.cli.install import ENGINE_CONTAINER
from factory.supervision import container_engine, container_profile
from factory.supervision.container_manifest import installed_project
from factory.supervision.container_project import (
    APPARMOR_ARTIFACT,
    SECCOMP_ARTIFACT,
    SERVICE_NAME,
    project_dir,
)
from factory.supervision.units import CommandResult

from tests.test_container_engine import FIXTURE_VERIFY_OUTPUT

# 033's walkthrough harness, imported rather than rebuilt.
from tests.test_ergane_install_walkthrough import (  # noqa: F401
    Run,
    ScriptedPrompter,
    _answers,
    config_path,
    walkthrough,
)

#: The one answer this story adds to a gateway interview after US1's: consent to
#: the AppArmor load, which defaults to yes (104-US4, trap 7).
CONSENT = "y"


@pytest.fixture
def engine_host(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A scratch host shaped like a real one, and relocated off `~`.

    Both details are the mount guard (trap 4), not hygiene: config and personas
    share one `~/.config/ergane`, because the project mounts the config
    *directory*; and the state home is off `~` (trap 5), so a path copied from
    the reference rather than resolved cannot pass.
    """
    home = tmp_path / "home"
    config_dir = home / ".config" / "ergane"
    state_home = tmp_path / "state"
    for directory in (config_dir, state_home / "ergane"):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    for name in ("ERGANE_CONFIG_PATH", "FACTORY_CONFIG_PATH"):
        monkeypatch.setenv(name, str(config_dir / "config.toml"))
    for name in ("ERGANE_PERSONAS_PATH", "FACTORY_PERSONAS_PATH"):
        monkeypatch.setenv(name, str(config_dir / "personas.yaml"))
    return state_home


class Recorder:
    """One ordered log of everything the install did through a seam — a single
    list, because the claim under test is *order* across seams."""

    def __init__(
        self, verify: CommandResult, ps_running: bool, answers_before_up: bool
    ) -> None:
        self.events: list[str] = []
        self.compose: list[tuple[str, ...]] = []
        self.verify = verify
        self.ps_running = ps_running
        self.answers_before_up = answers_before_up

    def probe(self, address: str, timeout_s: float) -> bool:
        """The port seam, answering the way a real one would: silent until the
        engine is up, unless something already held the port — which is the
        difference between a collision and a re-entry."""
        return self.answers_before_up or "compose up" in self.events

    def run_compose(self, argv: Sequence[str]) -> CommandResult:
        verb = argv[4] if len(argv) > 4 else ""
        self.compose.append(tuple(argv))
        self.events.append(f"compose {verb}")
        if verb == "exec":
            return self.verify
        if verb == "ps":
            return CommandResult(0, SERVICE_NAME if self.ps_running else "")
        return CommandResult(0, "")

    def run_privileged(self, argv: Sequence[str]) -> Any:
        self.events.append("apparmor_parser")
        return container_profile.PrivilegedResult(0, "", "")

    def personas(self, prompter: Any, document: Any, personas_path: Path) -> None:
        self.events.append("personas")


@pytest.fixture
def engine(
    monkeypatch: pytest.MonkeyPatch, engine_host: Path
) -> Callable[..., Recorder]:
    """Close every seam this path would reach through, and record — a factory,
    so a test chooses the verify result and whether the port already answers."""

    def install(
        *,
        verify: CommandResult,
        port_answers: bool = False,
        ps_running: bool = False,
    ) -> Recorder:
        recorder = Recorder(verify, ps_running, port_answers)
        monkeypatch.setattr(
            install_module, "_docker_daemon_available", lambda *_a, **_k: True
        )
        monkeypatch.setattr(container_engine, "_run_compose", recorder.run_compose)
        monkeypatch.setattr(container_engine, "_probe_address", recorder.probe)
        monkeypatch.setattr(
            container_profile, "_run_privileged", recorder.run_privileged
        )
        # 103's persona step reaches the gateway for real; stubbed with a
        # *recorder* rather than a no-op, so R3's ordering claim stays provable.
        monkeypatch.setattr(install_module, "_interview_personas", recorder.personas)
        return recorder

    return install


def _verbs(recorder: Recorder) -> list[str]:
    return [argv[4] for argv in recorder.compose if len(argv) > 4]


# --- T041 (US5-S1): the whole path, in order ---


def test_choosing_the_container_generates_consents_writes_ups_waits_and_verifies(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    engine: Callable[..., Recorder],
    engine_host: Path,
    config_path: Path,
) -> None:
    """US5-S1: one interview, and the six acts in the one order that works."""
    recorder = engine(verify=CommandResult(0, FIXTURE_VERIFY_OUTPUT))

    run, prompter = walkthrough(_answers() + [ENGINE_CONTAINER, CONSENT])

    assert run.code == EXIT_OK, run.stdout + run.stderr

    # R3 and trap 6 as one ordered claim: personas, then the privileged act,
    # then the project up — and nothing up before the port was preflighted.
    assert recorder.events == ["personas", "apparmor_parser", "compose up", "compose exec"]

    # On disk under the relocated state home: four generated files, remembered.
    directory = project_dir()
    assert directory == engine_host / "ergane" / "supervision" / "container"
    installed = installed_project()
    assert installed is not None
    assert set(installed.files) == {
        "compose.yaml",
        ".env",
        SECCOMP_ARTIFACT,
        APPARMOR_ARTIFACT,
    }

    # Up from the project just written, and verified *inside* it.
    assert recorder.compose[0] == (
        "docker", "compose", "-f", str(installed.compose_path), "up", "-d",
    )
    assert recorder.compose[1][-4:] == (SERVICE_NAME, "ergane", "install", "--verify")

    # The engine's own words, verbatim, under a header naming their side.
    assert FIXTURE_VERIFY_OUTPUT in run.stdout
    assert "engine container" in run.stdout
    # The consent prompt was asked once, and defaulted to yes (trap 7).
    consent = [a for a in prompter.asked if "AppArmor" in a.prompt]
    assert len(consent) == 1 and consent[0].default == "y"


def test_the_host_side_verify_never_runs_on_the_container_path(
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    engine: Callable[..., Recorder],
) -> None:
    """R8: the battery runs in the engine, and its exit code is the verdict.

    The host's own `verify_controlplane` is a detonator here, so a path still
    reaching for it fails rather than verifying the wrong side of the mount; and
    this engine emits text no findings parser could read, exits 0, and passes.
    """

    def _detonate(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the container path must not verify on the host")

    monkeypatch.setattr(install_module, "verify_controlplane", _detonate)
    unreadable = "ergane 9.9.9 :: subsystems nominal (schema v4)\n"
    recorder = engine(verify=CommandResult(0, unreadable))

    run, _prompter = walkthrough(_answers() + [ENGINE_CONTAINER, CONSENT])

    assert run.code == EXIT_OK, run.stdout + run.stderr
    assert unreadable in run.stdout
    assert _verbs(recorder) == ["up", "exec"]


# --- T041 (US5-S2): the failing verify, through the CLI ---


def test_a_failing_verify_ends_the_install_nonzero_with_the_engine_still_up(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    engine: Callable[..., Recorder],
) -> None:
    """US5-S2: nonzero, a named remedy, and nothing taken down."""
    recorder = engine(verify=CommandResult(1, FIXTURE_VERIFY_OUTPUT))

    run, _prompter = walkthrough(_answers() + [ENGINE_CONTAINER, CONSENT])

    assert run.code == EXIT_USER
    assert FIXTURE_VERIFY_OUTPUT in run.stdout  # the findings reached them first
    assert "still running" in run.stderr
    assert "ergane uninstall" in run.stderr
    assert _verbs(recorder) == ["up", "exec"]
    assert not [v for v in _verbs(recorder) if v in ("down", "stop", "rm", "kill")]
    # And the project is still on disk, which is what makes the re-run converge.
    assert installed_project() is not None


# --- T041 (US5-S3): re-entry against the stack the previous test left ---


def test_a_second_install_against_a_half_up_stack_converges(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    engine: Callable[..., Recorder],
) -> None:
    """US5-S3: same answers, same host, engine already up — and it converges.

    Every generated file already on disk, a port already answering, a service
    `ps` reports running — and none of them is an error.
    """
    first = engine(verify=CommandResult(0, FIXTURE_VERIFY_OUTPUT))
    run_one, _ = walkthrough(_answers() + [ENGINE_CONTAINER, CONSENT])
    assert run_one.code == EXIT_OK, run_one.stdout + run_one.stderr
    before = installed_project()
    assert before is not None
    written = {
        name: (before.directory / name).read_bytes() for name in before.files
    }

    # Now the stack is half up: the port answers, and `ps` reports the answer
    # is our own service — which is the branch that decides converge or refuse.
    second = engine(
        verify=CommandResult(0, FIXTURE_VERIFY_OUTPUT),
        port_answers=True,
        ps_running=True,
    )

    run_two, _ = walkthrough(_answers() + [ENGINE_CONTAINER, CONSENT])

    assert run_two.code == EXIT_OK, run_two.stdout + run_two.stderr
    # The preflight asked `ps`, recognised our own service and let `up` through.
    assert _verbs(second) == ["ps", "up", "exec"]
    # Byte-identical: a converged install stops touching the directory.
    after = installed_project()
    assert after is not None
    assert after.files == before.files
    assert {name: (after.directory / name).read_bytes() for name in after.files} == written
    assert "already current" in run_two.stdout
    assert first.events[0] == second.events[0] == "personas"
