"""088-US2: the container supervisor (T005–T008b).

Every test here drives the supervisor with stub children only.  No real
Temporal server, worker or bridge is started in tests (trap 6).
"""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Awaitable, Callable

import pytest

from factory.registry import DEFAULT_REGISTRY_REL, render_registry
from factory.supervision.container_supervisor import ChildController


def _relocated_state_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point registry resolution at a temporary state home."""
    home = tmp_path / "home"
    state = home / ".local" / "state"
    state.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    return state


def _write_registry(state_home: Path, repos: dict[str, str]) -> Path:
    """Write a registry document under `state_home` naming the given slug→path map."""
    path = state_home / DEFAULT_REGISTRY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"version": 1, "repos": {slug: {"path": str(repo_path)} for slug, repo_path in repos.items()}}
    path.write_text(render_registry(document), encoding="utf-8")
    return path


@pytest.fixture
def supervisor_mod():
    """Import the supervisor module; tests fail cleanly until it exists."""
    from factory.supervision import container_supervisor

    return container_supervisor


#: Stub child factory signature used throughout.
ChildFactory = Callable[[str], Awaitable["ChildStub"]]


class ChildStub(ChildController):
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
def config(tmp_path: Path) -> dict:
    """Default supervisor configuration for stub runs."""
    return {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.5,
        "grace_period_s": 0.2,
        "state_home": str(tmp_path / "state"),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }


# -----------------------------------------------------------------------------
# T005 [US2-S1, US2-S2, FR-005, FR-006] startup order and readiness timeout
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_temporal_starts_first_worker_waits_for_address(
    supervisor_mod, make_child: ChildFactory, config: dict
) -> None:
    """Temporal starts first; worker is not started until the address answers."""
    order: list[str] = []
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def readiness_probe(address: str, timeout: float) -> bool:
        await temporal._started_event.wait()
        order.append("ready")
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        order.append(name)
        return children[name]

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=readiness_probe,
        )
    )

    # Wait until all three children have been started in the correct order,
    # then signal a normal container shutdown.
    while "bridge" not in order:
        await asyncio.sleep(0)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=2.0)

    assert result == 0
    assert order.index("temporal") < order.index("ready") < order.index("worker")
    assert order.index("bridge") > order.index("ready")


@pytest.mark.asyncio
async def test_readiness_timeout_exits_nonzero_naming_address_and_timeout(
    supervisor_mod, make_child: ChildFactory, config: dict, caplog
) -> None:
    """An address that never answers exits nonzero naming the address and timeout."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def never_ready(address: str, timeout: float) -> bool:
        return False

    async def start_child(name: str, argv: list[str]) -> ChildController:
        return children[name]

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=never_ready,
        )
    )
    result = await asyncio.wait_for(run_task, timeout=1.0)

    assert result != 0
    assert any("127.0.0.1:7233" in rec.message for rec in caplog.records)
    assert any("0.5" in rec.message for rec in caplog.records)


# -----------------------------------------------------------------------------
# T006 [US2-S3, FR-007] first child death stops the others and names the victim
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_child_death_stops_others_and_names_victim(
    supervisor_mod, make_child: ChildFactory, config: dict, caplog
) -> None:
    """When one child exits, the supervisor stops the others and names it."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        if name == "temporal":
            # Make the first-started child the first to exit once the
            # worker and bridge have also been started.
            asyncio.get_event_loop().call_soon(
                lambda: asyncio.create_task(_exit_after_others(temporal))
            )
        return children[name]

    async def _exit_after_others(child: ChildStub) -> None:
        await worker._started_event.wait()
        await bridge._started_event.wait()
        # Yield once so the worker/bridge wait tasks have observed the events
        # and are truly pending; only then is temporal the first-completed task.
        await asyncio.sleep(0)
        child.finish(7)

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )
    result = await asyncio.wait_for(run_task, timeout=2.0)

    assert result != 0
    assert any("temporal" in rec.message for rec in caplog.records)
    assert any("7" in rec.message for rec in caplog.records)
    assert worker.stopped
    assert bridge.stopped


# -----------------------------------------------------------------------------
# T007 [US2-S4, FR-008] SIGTERM fan-out with grace period before SIGKILL
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sigterm_fans_out_with_grace_before_kill(
    supervisor_mod, make_child: ChildFactory, config: dict, caplog
) -> None:
    """SIGTERM reaches every child; SIGKILL is used only after the grace period."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        return children[name]

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )
    await temporal._started_event.wait()
    await worker._started_event.wait()
    await bridge._started_event.wait()

    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=0.5)

    # SIGTERM-driven shutdown of all children is a clean container stop.
    assert result == 0
    assert signal.SIGTERM in temporal.signals
    assert signal.SIGTERM in worker.signals
    assert signal.SIGTERM in bridge.signals
    # Grace period is short enough that a cooperating stub exits without SIGKILL.
    assert not temporal.killed
    assert not worker.killed
    assert not bridge.killed


# -----------------------------------------------------------------------------
# T008 [US2-S5, FR-009] no assembled child argv contains "python -"
# -----------------------------------------------------------------------------


def test_no_child_argv_contains_python_dash(supervisor_mod) -> None:
    """The assembled child command lines avoid the pkill-matched substring."""
    argv_map = supervisor_mod._child_argv(
        temporal_address="127.0.0.1:7233",
        db_filename="/tmp/temporal.sqlite",
    )
    for name, argv in argv_map.items():
        joined = " ".join(argv)
        assert "python -" not in joined, f"{name} argv contains 'python -': {joined!r}"


# -----------------------------------------------------------------------------
# T008b [US2-S6, US2-S7, FR-009] same-path check, both branches
# -----------------------------------------------------------------------------


async def test_missing_repo_path_refuses_before_any_child_starts(
    supervisor_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A registry pointing at a missing directory refuses before children start."""
    state_home = _relocated_state_home(monkeypatch, tmp_path)
    _write_registry(state_home, {"missing-repo": "/nonexistent/path"})

    started: list[str] = []

    async def start_child(name: str, argv: list[str]) -> ChildController:
        started.append(name)
        return ChildStub(name)

    async def never_probe(address: str, timeout: float) -> bool:
        return True

    with pytest.raises(supervisor_mod.SupervisorRefusal) as raised:
        await supervisor_mod._run_supervisor(
            {"state_home": str(state_home)},
            start_child=start_child,
            probe_address=never_probe,
        )

    message = str(raised.value)
    assert "missing-repo" in message
    assert "/nonexistent/path" in message
    assert "remedies" in message
    assert "mounted" in message
    assert "rebuild" in message
    assert started == []


async def test_empty_registry_starts_normally(
    supervisor_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty registry is a fresh container and starts normally."""
    state_home = _relocated_state_home(monkeypatch, tmp_path)
    _write_registry(state_home, {})

    created: list[ChildStub] = []

    async def start_child(name: str, argv: list[str]) -> ChildController:
        c = ChildStub(name)
        created.append(c)
        return c

    async def never_probe(address: str, timeout: float) -> bool:
        return True

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            {"state_home": str(state_home)},
            start_child=start_child,
            probe_address=never_probe,
        )
    )
    while len(created) < 3 or any(not c._started_event.is_set() for c in created):
        await asyncio.sleep(0)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=2.0)

    started = {c.name for c in created}
    assert result == 0
    assert "temporal" in started


async def test_absent_registry_file_starts_normally(
    supervisor_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No registry file at all is also a fresh container."""
    state_home = _relocated_state_home(monkeypatch, tmp_path)
    # Do not write a registry file.

    created: list[ChildStub] = []

    async def start_child(name: str, argv: list[str]) -> ChildController:
        c = ChildStub(name)
        created.append(c)
        return c

    async def never_probe(address: str, timeout: float) -> bool:
        return True

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            {"state_home": str(state_home)},
            start_child=start_child,
            probe_address=never_probe,
        )
    )
    while len(created) < 3 or any(not c._started_event.is_set() for c in created):
        await asyncio.sleep(0)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=2.0)

    started = {c.name for c in created}
    assert result == 0
    assert "temporal" in started
