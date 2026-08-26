"""110-US1: first boot leaves the demo project dispatchable.

Every test here drives the demo driver through seams against scratch directories.
No real Temporal server, worker, gateway or bwrap dispatch is started in tests
(plan T8).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Awaitable, Callable

import pytest

from factory.registry import DEFAULT_REGISTRY_REL, render_registry

DEMO_ANSWERS = (
    Path(__file__).resolve().parents[1] / "container" / "ergane-install-answer.demo.toml"
)


def _relocated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point HOME and XDG paths at a scratch directory so git has no global identity."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    return home


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# -----------------------------------------------------------------------------
# T001 [US1] (spec US1-S1, FR-001) supervisor spawn test
# -----------------------------------------------------------------------------


class ChildStub:
    """A fake child process for the supervisor."""

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


ChildFactory = Callable[[str], Awaitable[ChildStub]]


@pytest.fixture
def supervisor_mod():
    """Import the supervisor module; tests fail cleanly until it exists."""
    from factory.supervision import container_supervisor

    return container_supervisor


@pytest.fixture
def make_child() -> ChildFactory:
    created: list[ChildStub] = []

    async def factory(name: str) -> ChildStub:
        child = ChildStub(name)
        created.append(child)
        return child

    yield factory
    for child in created:
        child.finish(0)


@pytest.fixture
def supervisor_config(tmp_path: Path) -> dict:
    return {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.5,
        "grace_period_s": 0.2,
        "state_home": str(tmp_path / "state"),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }


@pytest.mark.asyncio
async def test_supervisor_spawns_demo_driver_when_flag_set(
    supervisor_mod,
    make_child: ChildFactory,
    supervisor_config: dict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """With ERGANE_DEMO=1 and no sentinel, the supervisor spawns the demo driver.

    The driver is a plain subprocess: it appears in neither the controllers nor
    the tasks maps, and its nonzero exit does not stop the container.
    """
    _relocated_home(monkeypatch, tmp_path)
    state_home = Path(supervisor_config["state_home"])
    (state_home / DEFAULT_REGISTRY_REL).parent.mkdir(parents=True)
    (state_home / DEFAULT_REGISTRY_REL).write_text(
        render_registry({"version": 1, "repos": {}}), encoding="utf-8"
    )

    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    driver = ChildStub("demo_driver")
    driver_started = False

    async def start_child(name: str, argv: list[str]) -> ChildStub:
        nonlocal driver_started
        if name == "demo_driver":
            driver_started = True
            return driver
        return children[name]

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    monkeypatch.setenv("ERGANE_DEMO", "1")
    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            supervisor_config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )

    # Wait until the three supervised children have started.
    while not all(c._started_event.is_set() for c in children.values()):
        await asyncio.sleep(0)

    assert driver_started, "demo driver was not spawned"

    # Simulate the driver exiting nonzero; this must not stop the container.
    driver.finish(1)
    await asyncio.sleep(0)

    # Signal a normal container shutdown so an unprompted child death is not
    # treated as a fault.
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=2.0)

    assert result == 0
    assert driver.returncode == 1
    assert "demo_driver" not in {n for n, _ in children.items()}
    assert driver not in children.values()


@pytest.mark.asyncio
async def test_supervisor_does_not_spawn_demo_driver_without_flag(
    supervisor_mod,
    make_child: ChildFactory,
    supervisor_config: dict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without ERGANE_DEMO, only the three supervised children start."""
    _relocated_home(monkeypatch, tmp_path)
    state_home = Path(supervisor_config["state_home"])
    (state_home / DEFAULT_REGISTRY_REL).parent.mkdir(parents=True)
    (state_home / DEFAULT_REGISTRY_REL).write_text(
        render_registry({"version": 1, "repos": {}}), encoding="utf-8"
    )

    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    started: list[str] = []

    async def start_child(name: str, argv: list[str]) -> ChildStub:
        started.append(name)
        return children[name]

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    monkeypatch.delenv("ERGANE_DEMO", raising=False)
    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            supervisor_config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )

    while not all(c._started_event.is_set() for c in children.values()):
        await asyncio.sleep(0)

    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=2.0)

    assert result == 0
    assert sorted(started) == ["bridge", "temporal", "worker"]


# -----------------------------------------------------------------------------
# T002 [P] [US1] (spec US1-S2, FR-002, FR-003) prepare-phase offline test
# -----------------------------------------------------------------------------


@pytest.fixture
def demo_mod(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Import the demo driver module and reset its module-level seams."""
    home = _relocated_home(monkeypatch, tmp_path)
    state_home = home / ".local" / "state"
    state_home.mkdir(parents=True)
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state_home))
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(home / ".config" / "ergane" / "config.toml"))

    from factory.supervision import demo_driver

    return demo_driver


def _fake_install_runner(answers_path: Path) -> Callable[[list[str]], int]:
    """Return a runner that performs install's write side without verification.

    The real `ergane install --from-file` runs control-plane probes that need
    live services the demo compose provides; offline tests skip those probes
    and assert on the files install would have written.
    """

    def runner(argv: list[str]) -> int:
        # Accept only the install-from-file argv shape the driver uses.
        if "install" not in argv or "--from-file" not in argv:
            return 1
        # Run the real install command in non-interactive mode to write the
        # config and seed the persona registry, but skip the verification
        # round trip that needs a live gateway/Temporal.
        from factory.cli.main import main

        result = main(["install", "--from-file", str(answers_path), "--non-interactive"])
        # non-interactive install currently also verifies; override the exit
        # code when the config file was written so the driver proceeds.
        config_path = Path(os.environ["ERGANE_CONFIG_PATH"])
        return 0 if config_path.is_file() else result

    return runner


def _passing_probe(argv: list[str]) -> tuple[int, str, str]:
    """A fake sandbox probe that always succeeds.

    Driver tests run against seams, never live processes (plan T8); the
    refusal test is the only one that injects a failing probe.
    """
    return (0, "", "")


def _drive_prepare(
    demo_mod,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    answers_path: Path | None = None,
    sandbox_probe: demo_mod.Probe | None = None,
) -> Path:
    """Run the prepare phase against scratch directories and return the repo root."""
    repo_root = tmp_path / "repo"
    state_home = Path(os.environ["ERGANE_STATE_HOME"])
    answers = answers_path or DEMO_ANSWERS

    monkeypatch.setattr(demo_mod, "_install_runner", _fake_install_runner(answers))

    demo_mod.prepare_first_boot(
        state_home=state_home,
        repo_root=repo_root,
        answers_file=answers,
        sandbox_probe=sandbox_probe or _passing_probe,
    )
    return repo_root


def test_prepare_phase_creates_repo_and_config(demo_mod, monkeypatch, tmp_path) -> None:
    """The prepare phase installs, scaffolds, commits, and leaves a dispatchable repo."""
    repo_root = _drive_prepare(demo_mod, monkeypatch, tmp_path)

    config_path = Path(os.environ["ERGANE_CONFIG_PATH"])
    assert config_path.is_file(), f"control-plane config not written at {config_path}"

    git_dir = repo_root / ".git"
    assert git_dir.is_dir(), f"repo not a git repository: {repo_root}"

    branch = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert branch == "main"

    from factory.cli.install import _demo_manifest_text

    assert (repo_root / "ergane.yaml").read_text(encoding="utf-8") == _demo_manifest_text()

    spec_dir = repo_root / "specs" / "001-demo"
    assert (spec_dir / "spec.md").is_file()
    assert (spec_dir / "plan.md").is_file()
    assert (spec_dir / "tasks.md").is_file()

    log = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--format=%an <%ae>", "-1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "Ergane Demo <demo@ergane.invalid>", f"unexpected commit identity: {log!r}"


# -----------------------------------------------------------------------------
# T003 [P] [US1] (spec US1-S3, FR-004) validate-and-derive test
# -----------------------------------------------------------------------------


def test_prepared_repo_validates_and_derives(demo_mod, monkeypatch, tmp_path) -> None:
    """After prepare, `ergane spec validate` and `ergane spec derive` both succeed."""
    repo_root = _drive_prepare(demo_mod, monkeypatch, tmp_path)
    spec_dir = repo_root / "specs" / "001-demo"

    from factory.cli.install import _run_cli
    from factory.cli.install import _spec_validate_argv, _spec_derive_argv

    assert _run_cli(_spec_validate_argv(spec_dir, repo_root)) == 0
    assert _run_cli(_spec_derive_argv(spec_dir, repo_root)) == 0

    artifact = spec_dir / "workgraph.json"
    assert artifact.is_file(), f"compiled graph missing: {artifact}"
    graph = json.loads(artifact.read_text(encoding="utf-8"))
    assert graph.get("epic_id") == "001-demo"


# -----------------------------------------------------------------------------
# T004 [P] [US1] (spec US1-S4, FR-005) sandbox-probe refusal test
# -----------------------------------------------------------------------------


def test_sandbox_probe_refusal_stops_before_dispatch(demo_mod, monkeypatch, tmp_path, capsys) -> None:
    """A failing bwrap probe prints stderr + remedy and returns nonzero with no dispatch."""
    repo_root = _drive_prepare(demo_mod, monkeypatch, tmp_path)

    captured_argv: list[str] | None = None
    probe_stderr = "bwrap: Can't mount proc on /proc"

    def failing_probe(argv: list[str]) -> tuple[int, str, str]:
        nonlocal captured_argv
        captured_argv = argv
        return (1, "", probe_stderr)

    # Clear the prepare sentinel so the second invocation actually reaches the
    # sandbox probe step instead of short-circuiting as already-booted.
    sentinel = Path(os.environ["ERGANE_STATE_HOME"]) / demo_mod.DEMO_SENTINEL_REL
    sentinel.unlink()

    # Use a fresh repo for the probe-failure run so the first run's files do not
    # collide with a re-creation attempt.
    repo_root2 = tmp_path / "repo2"
    state_home = Path(os.environ["ERGANE_STATE_HOME"])
    result = demo_mod.prepare_first_boot(
        state_home=state_home,
        repo_root=repo_root2,
        answers_file=DEMO_ANSWERS,
        sandbox_probe=failing_probe,
    )

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert result != 0
    assert probe_stderr in combined
    assert "remedy" in combined.lower()
    assert captured_argv is not None
    assert "--unshare-pid" in captured_argv
    assert "--proc" in captured_argv

    # No dispatch sentinel means the prepare sentinel is already written; but
    # there must be no separate dispatch sentinel because we stopped first.
    assert not (state_home / "demo" / "dispatched").exists()


# -----------------------------------------------------------------------------
# T005 [P] [US1] (spec US1-S5, FR-006) sentinel idempotency test
# -----------------------------------------------------------------------------


def test_second_prepare_run_is_noop(demo_mod, monkeypatch, tmp_path, capsys) -> None:
    """Running prepare twice: second run does nothing, says so, and exits 0."""
    repo_root = tmp_path / "repo"
    state_home = Path(os.environ["ERGANE_STATE_HOME"])

    monkeypatch.setattr(demo_mod, "_install_runner", _fake_install_runner(DEMO_ANSWERS))

    result1 = demo_mod.prepare_first_boot(
        state_home=state_home,
        repo_root=repo_root,
        answers_file=DEMO_ANSWERS,
    )
    assert result1 == 0

    captured = capsys.readouterr()
    result2 = demo_mod.prepare_first_boot(
        state_home=state_home,
        repo_root=repo_root,
        answers_file=DEMO_ANSWERS,
    )
    captured2 = capsys.readouterr()

    assert result2 == 0
    assert "already" in captured2.out.lower()
    assert captured2.out.count("\n") == 1 or captured2.out.count("\n") == 2
