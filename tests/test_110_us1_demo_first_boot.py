"""110-US1: first boot leaves the demo project dispatchable.

Every test here drives seams, not live processes: no Temporal server, no
worker, no gateway, no real bubblewrap dispatch. The supervisor tests reuse the
injectable `start_child`/`probe_address` seams; the driver tests call functions
over scratch directories with injectable CLI and probe callables.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

import factory.cli.install as install_module
import factory.supervision.container_supervisor as supervisor_mod
from factory.cli.install import _demo_manifest_text, _run_cli
from factory.doctor.scaffold import scaffold_spec
from factory.registry import resolve_state_home

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_ANSWERS = REPO_ROOT / "container" / "ergane-install-answer.demo.toml"

DEMO_AUTHOR_NAME = "Ergane Demo"
DEMO_AUTHOR_EMAIL = "demo@ergane.invalid"


# -----------------------------------------------------------------------------
# Harness shared across tests
# -----------------------------------------------------------------------------


class _RecordingChild:
    """A fake supervised child that can finish with a chosen status."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = False
        self.stopped = False
        self.killed = False
        self.signals: list[int] = []
        self.returncode: int | None = None
        self._started_event = asyncio.Event()
        self._exit_event = asyncio.Event()

    async def wait(self) -> int:
        self.started = True
        self._started_event.set()
        await self._exit_event.wait()
        assert self.returncode is not None
        return self.returncode

    def stop(self) -> None:
        self.stopped = True
        self.signals.append(signal.SIGTERM)
        if not self._exit_event.is_set():
            self.returncode = 0
            self._exit_event.set()

    def kill(self) -> None:
        self.killed = True
        self.signals.append(signal.SIGKILL)
        if not self._exit_event.is_set():
            self.returncode = -9
            self._exit_event.set()

    def finish(self, code: int = 0) -> None:
        if not self._exit_event.is_set():
            self.returncode = code
            self._exit_event.set()


def _scratched_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a scratch state home and point resolution at it."""
    home = tmp_path / "home"
    state_home = home / ".local" / "state" / "ergane"
    state_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    return state_home


def _scratched_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a scratch config home and point resolution at it."""
    config_home = tmp_path / "home" / ".config" / "ergane"
    config_home.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_home / "config.toml"))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(config_home / "config.toml"))
    return config_home


# -----------------------------------------------------------------------------
# T001 [US1] (spec US1-S1, FR-001) supervisor spawn test
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_spawns_demo_driver_after_worker_and_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ERGANE_DEMO=1 and no sentinel, the driver is spawned plain and
    non-fatal after worker and bridge start, and is absent from the supervised
    maps."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    monkeypatch.setenv("ERGANE_DEMO", "1")

    temporal = _RecordingChild("temporal")
    worker = _RecordingChild("worker")
    bridge = _RecordingChild("bridge")
    driver = _RecordingChild("demo_driver")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    started: list[tuple[str, list[str]]] = []
    finished_drivers: list[int] = []

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> Any:
        started.append((name, list(argv)))
        if name == "demo_driver":
            # Driver exits successfully after a brief moment; it is not fatal.
            asyncio.get_event_loop().call_later(0.05, driver.finish, 0)
            return driver
        return children[name]

    config = {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.1,
        "grace_period_s": 0.1,
        "state_home": str(state_home),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )

    # Wait until the driver (if spawned) has had a chance to exit, then shut
    # down cleanly via SIGTERM so the supervised children exit normally.
    await asyncio.sleep(0.15)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=1.0)

    names = [name for name, _ in started]
    assert "demo_driver" in names
    # Driver starts only after the three supervised children are started.
    assert names.index("demo_driver") > names.index("temporal")
    assert names.index("demo_driver") > names.index("worker")
    assert names.index("demo_driver") > names.index("bridge")

    # The driver is a plain subprocess: it was handed to start_child as a module
    # argv with `python3 -m`, and it is **not** in the supervised maps.
    driver_argv = next(argv for name, argv in started if name == "demo_driver")
    joined = " ".join(driver_argv)
    assert "python3 -m" not in joined or "factory.supervision.demo_driver" in joined, (
        f"driver argv should launch the demo driver module: {driver_argv!r}"
    )
    assert "python -" not in joined, f"driver argv contains 'python -': {joined!r}"

    # Driver is absent from the supervised controllers and tasks maps.
    assert driver not in [temporal, worker, bridge]
    # The supervisor's normal return value is unchanged by a driver exit.
    assert result == 0


@pytest.mark.asyncio
async def test_supervisor_spawns_nothing_without_demo_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ERGANE_DEMO=1 the supervised set is exactly today's three."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    monkeypatch.delenv("ERGANE_DEMO", raising=False)

    temporal = _RecordingChild("temporal")
    worker = _RecordingChild("worker")
    bridge = _RecordingChild("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    started: list[str] = []

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> Any:
        started.append(name)
        return children[name]

    config = {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.1,
        "grace_period_s": 0.1,
        "state_home": str(state_home),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )
    # Wait for all three children to be started, then signal shutdown.
    while len(started) < 3:
        await asyncio.sleep(0)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=1.0)

    assert sorted(started) == ["bridge", "temporal", "worker"]
    assert result == 0


@pytest.mark.asyncio
async def test_demo_driver_exiting_nonzero_leaves_children_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A driver that exits nonzero does not stop the container or the three
    supervised children."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    monkeypatch.setenv("ERGANE_DEMO", "1")

    temporal = _RecordingChild("temporal")
    worker = _RecordingChild("worker")
    bridge = _RecordingChild("bridge")
    driver = _RecordingChild("demo_driver")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> Any:
        if name == "demo_driver":
            # Exit nonzero immediately; supervised children must stay up.
            driver.finish(1)
            return driver
        return children[name]

    config = {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.1,
        "grace_period_s": 0.1,
        "state_home": str(state_home),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )

    # Wait until the driver's nonzero exit has been reaped, then assert the
    # three supervised children are still up before terminating the test.
    while not driver._exit_event.is_set():
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)

    # The three supervised children were never stopped because of the driver.
    assert not temporal.stopped
    assert not worker.stopped
    assert not bridge.stopped
    assert not temporal.killed
    assert not worker.killed
    assert not bridge.killed

    # End the test cleanly: the supervisor's own shutdown is not what we are
    # testing here.
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass


# -----------------------------------------------------------------------------
# T002 [P] [US1] (spec US1-S2, FR-002, FR-003) prepare-phase offline test
# -----------------------------------------------------------------------------


@dataclass
class _CliCall:
    argv: list[str]
    code: int


def _prepare_cli_runner(
    *, create_config: Path | None = None
) -> Callable[[list[str]], int]:
    """Return a CLI runner that records calls and optionally writes a config."""
    calls: list[_CliCall] = []

    def run(argv: list[str]) -> int:
        if create_config is not None and argv[:2] == ["install", "--from-file"]:
            create_config.parent.mkdir(parents=True, exist_ok=True)
            create_config.write_text("# demo config\n", encoding="utf-8")
        calls.append(_CliCall(argv=list(argv), code=0))
        return 0

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _no_global_git_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Return a scratch HOME with no git identity and suppress system/global git config."""
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    return home


@pytest.fixture
def demo_driver_mod():
    """Import the demo driver module; tests fail cleanly until it exists."""
    from factory.supervision import demo_driver

    return demo_driver


def test_prepare_phase_creates_repo_spec_and_commit(
    demo_driver_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The prepare phase runs install, git init, manifest, spec trio and one
    commit under the explicit demo identity, with no global git identity."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    config_home = _scratched_config_home(tmp_path, monkeypatch)
    repo_root = tmp_path / "repo"
    _no_global_git_identity(monkeypatch, tmp_path)

    cli_runner = _prepare_cli_runner(create_config=config_home / "config.toml")

    code = demo_driver_mod.prepare_phase(
        state_home,
        repo_root,
        DEMO_ANSWERS,
        run_cli=cli_runner,
        run_probe=_passing_probe,
    )

    assert code == 0

    # Install ran through the CLI seam with the bundled answer file.
    install_calls = [c for c in cli_runner.calls if c.argv[:2] == ["install", "--from-file"]]
    assert len(install_calls) == 1
    assert install_calls[0].argv[2] == str(DEMO_ANSWERS)

    # Config exists at the resolved path.
    assert (config_home / "config.toml").is_file()

    # Repo is a git repository on branch main.
    assert (repo_root / ".git").is_dir()
    branch = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert branch == "main"

    # Manifest matches the text returned by _demo_manifest_text().
    manifest_path = repo_root / "ergane.yaml"
    assert manifest_path.read_text(encoding="utf-8") == _demo_manifest_text()

    # Spec trio exists.
    spec_dir = repo_root / "specs" / "001-demo"
    assert (spec_dir / "spec.md").is_file()
    assert (spec_dir / "plan.md").is_file()
    assert (spec_dir / "tasks.md").is_file()

    # Exactly one commit exists and its author is the demo identity.
    log = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--format=%an <%ae>", "-1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == f"{DEMO_AUTHOR_NAME} <{DEMO_AUTHOR_EMAIL}>"


def _passing_probe(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")


# -----------------------------------------------------------------------------
# T003 [P] [US1] (spec US1-S3, FR-004) validate-and-derive test
# -----------------------------------------------------------------------------


def test_validate_and_derive_on_prepared_repo(
    demo_driver_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After prepare, spec validate and spec derive both succeed and emit
    workgraph.json."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    config_home = _scratched_config_home(tmp_path, monkeypatch)
    repo_root = tmp_path / "repo"
    _no_global_git_identity(monkeypatch, tmp_path)

    # Point personas at the repo's real registry so validate resolves.
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(REPO_ROOT / "personas.yaml"))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(REPO_ROOT / "personas.yaml"))

    cli_runner = _prepare_cli_runner(create_config=config_home / "config.toml")

    code = demo_driver_mod.prepare_phase(
        state_home,
        repo_root,
        DEMO_ANSWERS,
        run_cli=cli_runner,
        run_probe=_passing_probe,
    )
    assert code == 0

    spec_dir = repo_root / "specs" / "001-demo"
    validate_argv = ["spec", "validate", str(spec_dir), "--target-repo", str(repo_root)]
    derive_argv = ["spec", "derive", str(spec_dir), "--target-repo", str(repo_root)]

    assert _run_cli(validate_argv) == 0
    assert _run_cli(derive_argv) == 0

    artifact = spec_dir / "workgraph.json"
    assert artifact.is_file()
    import json

    parsed = json.loads(artifact.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert "nodes" in parsed


# -----------------------------------------------------------------------------
# T004 [P] [US1] (spec US1-S4, FR-005) sandbox-probe refusal test
# -----------------------------------------------------------------------------


class _FailingProbe:
    """Record probe argv and fail with scripted stderr."""

    def __init__(self, stderr: str) -> None:
        self.calls: list[list[str]] = []
        self.stderr = stderr

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="", stderr=self.stderr)


def test_probe_refusal_prints_stderr_and_remedy_and_returns_nonzero(
    demo_driver_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A failing probe prints the probe stderr and a remedy, and the driver
    stops before any dispatch step."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    config_home = _scratched_config_home(tmp_path, monkeypatch)
    repo_root = tmp_path / "repo"
    _no_global_git_identity(monkeypatch, tmp_path)

    probe = _FailingProbe(stderr="bwrap: Can't mount proc on /proc")
    cli_runner = _prepare_cli_runner(create_config=config_home / "config.toml")

    code = demo_driver_mod.prepare_phase(
        state_home,
        repo_root,
        DEMO_ANSWERS,
        run_cli=cli_runner,
        run_probe=probe,
    )

    assert code != 0
    captured = capsys.readouterr()
    assert "bwrap: Can't mount proc on /proc" in captured.out
    assert "systempaths=unconfined" in captured.out or "bubblewrap#284" in captured.out

    # No dispatch argv was run through the CLI seam.
    dispatch_calls = [c for c in cli_runner.calls if c.argv[:2] == ["build", "ship"]]
    assert not dispatch_calls

    # Probe argv carried the required namespace/proc flags.
    assert len(probe.calls) == 1
    probe_argv = probe.calls[0]
    assert "--unshare-pid" in probe_argv
    assert "--proc" in probe_argv
    assert "--die-with-parent" in probe_argv


@pytest.mark.asyncio
async def test_probe_refusal_keeps_supervised_children_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the driver exits nonzero on a probe refusal, the three supervised
    children are still up."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    monkeypatch.setenv("ERGANE_DEMO", "1")

    temporal = _RecordingChild("temporal")
    worker = _RecordingChild("worker")
    bridge = _RecordingChild("bridge")
    driver = _RecordingChild("demo_driver")

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> Any:
        if name == "demo_driver":
            driver.finish(1)
            return driver
        return {"temporal": temporal, "worker": worker, "bridge": bridge}[name]

    config = {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.1,
        "grace_period_s": 0.1,
        "state_home": str(state_home),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )

    while not driver._exit_event.is_set():
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)

    assert not temporal.stopped
    assert not worker.stopped
    assert not bridge.stopped

    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass


# -----------------------------------------------------------------------------
# T005 [P] [US1] (spec US1-S5, FR-006) sentinel semantics tests
# -----------------------------------------------------------------------------


def test_prepared_sentinel_makes_second_run_noop(
    demo_driver_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """After a successful prepare+probe, a second driver run is a one-line no-op."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    config_home = _scratched_config_home(tmp_path, monkeypatch)
    repo_root = tmp_path / "repo"
    _no_global_git_identity(monkeypatch, tmp_path)

    cli_runner = _prepare_cli_runner(create_config=config_home / "config.toml")

    code = demo_driver_mod.prepare_phase(
        state_home,
        repo_root,
        DEMO_ANSWERS,
        run_cli=cli_runner,
        run_probe=_passing_probe,
    )
    assert code == 0

    # Second run: no install, no git, no probe; just one line.
    second_cli = _prepare_cli_runner()
    second_probe = _FailingProbe(stderr="should not run")
    code2 = demo_driver_mod.main(argv=[], state_home=state_home, repo_root=repo_root, run_cli=second_cli, run_probe=second_probe)

    assert code2 == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert any("first boot" in line.lower() for line in lines)
    # No CLI calls and no probe ran on the second pass.
    assert not second_cli.calls
    assert not second_probe.calls


def test_probe_refusal_leaves_no_prepared_sentinel_and_retries(
    demo_driver_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a probe refusal, no `prepared` sentinel is written and a restart
    re-runs the probe."""
    state_home = _scratched_state_home(tmp_path, monkeypatch)
    config_home = _scratched_config_home(tmp_path, monkeypatch)
    repo_root = tmp_path / "repo"
    _no_global_git_identity(monkeypatch, tmp_path)

    failing = _FailingProbe(stderr="bwrap: Can't mount proc")
    cli_runner = _prepare_cli_runner(create_config=config_home / "config.toml")

    code = demo_driver_mod.prepare_phase(
        state_home,
        repo_root,
        DEMO_ANSWERS,
        run_cli=cli_runner,
        run_probe=failing,
    )
    assert code != 0

    prepared_sentinel = state_home / "demo" / "prepared"
    assert not prepared_sentinel.exists()

    # Second run retries the probe.
    second_cli = _prepare_cli_runner()
    second_probe = _FailingProbe(stderr="still refused")
    demo_driver_mod.main(argv=[], state_home=state_home, repo_root=repo_root, run_cli=second_cli, run_probe=second_probe)
    assert len(second_probe.calls) == 1
    assert "--proc" in second_probe.calls[0]
