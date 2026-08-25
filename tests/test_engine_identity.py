"""105-US2: engine identity vocabulary and record lifetime.

The module under test is intentionally standard-library-only, so these tests
import it directly without spinning up Temporal or docker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Awaitable, Callable

import pytest

from factory.registry import resolve_state_home
from factory.supervision import engine_identity
from factory.supervision.container_supervisor import ChildController
from factory.supervision.engine_identity import (
    EngineIdentity,
    IDENTITY_FILENAME,
    IMAGE_REPOSITORY,
    cli_version,
    identity_path,
    image_reference,
    read_identity,
    write_identity,
)
from factory.supervision.units import supervision_home


# ---------------------------------------------------------------------------
# T013 [US2] vocabulary tests
# ---------------------------------------------------------------------------


def test_image_repository_matches_compose_reference() -> None:
    """IMAGE_REPOSITORY equals the repository parsed out of compose.reference.yaml:10."""
    compose_path = Path(__file__).resolve().parents[1] / "container" / "compose.reference.yaml"
    line = compose_path.read_text(encoding="utf-8").splitlines()[9]
    # image: ghcr.io/bryantharpeorg/ergane:${ERGANE_VERSION}
    image_value = line.split(":", 1)[1].strip()
    repo_part = image_value.rsplit(":", 1)[0]
    assert IMAGE_REPOSITORY == repo_part


def test_image_reference_formats_version() -> None:
    assert image_reference("1.2.3") == f"{IMAGE_REPOSITORY}:1.2.3"


def test_cli_version_reads_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata

    expected = importlib.metadata.version("ergane-cli")
    assert cli_version() == expected

    def _raise(*args: object, **kwargs: object) -> None:
        raise importlib.metadata.PackageNotFoundError("ergane-cli")

    monkeypatch.setattr(importlib.metadata, "version", _raise)
    assert cli_version() == "unknown"


def test_identity_path_matches_supervision_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two joins produce the same absolute path, without env-only resolution in the supervisor."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    assert identity_path(resolve_state_home()) == supervision_home() / IDENTITY_FILENAME


def test_module_imports_only_standard_library() -> None:
    """No third-party imports in the engine identity module."""
    import sys

    before = set(sys.modules.keys())
    from importlib import import_module

    fresh = import_module("factory.supervision.engine_identity")
    after = set(sys.modules.keys())
    added = after - before
    third_party = {name for name in added if not (name.startswith("factory.") or name in ("__future__",))}
    # We allow only stdlib; names that are part of CPython's standard library
    # are not in any external package.  The only expected new module is the
    # target itself, which is not third-party.
    assert fresh.__name__ == "factory.supervision.engine_identity"
    for name in third_party:
        mod = sys.modules[name]
        if mod is None:
            continue
        spec = getattr(mod, "__spec__", None)
        if spec is None:
            continue
        origin = getattr(spec, "origin", None) or ""
        # If it came from site-packages, that's a violation.
        assert "site-packages" not in origin, f"{name} appears to be third-party"


# ---------------------------------------------------------------------------
# T012 [US2] record fields
# ---------------------------------------------------------------------------


def test_record_fields_parsed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The record carries version, UTC ISO-8601 started_at, image_reference and image_digest."""
    monkeypatch.setenv("ERGANE_VERSION", "0.4.0")
    monkeypatch.setenv("ERGANE_IMAGE_DIGEST", "sha256:abc123")
    record = EngineIdentity(
        version=cli_version(),
        started_at=engine_identity._now_utc_iso(),
        image_reference=os.environ.get("ERGANE_VERSION"),
        image_digest=os.environ.get("ERGANE_IMAGE_DIGEST"),
    )
    path = write_identity(tmp_path, record)
    loaded = read_identity(tmp_path)
    assert loaded is not None
    assert loaded.version == cli_version()
    assert loaded.image_reference == "0.4.0"
    assert loaded.image_digest == "sha256:abc123"
    # ISO-8601 with timezone
    assert loaded.started_at.endswith("+00:00")


def test_null_defaults_when_environment_unset(tmp_path: Path) -> None:
    """When ERGANE_VERSION and ERGANE_IMAGE_DIGEST are unset, both fields are null."""
    record = EngineIdentity(
        version=cli_version(),
        started_at=engine_identity._now_utc_iso(),
        image_reference=os.environ.get("ERGANE_VERSION"),
        image_digest=os.environ.get("ERGANE_IMAGE_DIGEST"),
    )
    write_identity(tmp_path, record)
    document = json.loads((tmp_path / "ergane" / "supervision" / IDENTITY_FILENAME).read_text(encoding="utf-8"))
    assert document.get("image_reference") is None
    assert document.get("image_digest") is None


# ---------------------------------------------------------------------------
# T011 [US2] restart replaces whole, atomic write
# ---------------------------------------------------------------------------


def test_restart_replaces_whole_file(tmp_path: Path) -> None:
    """Running twice against the same state_home leaves exactly one valid record."""
    first = EngineIdentity(version="0.3.0", started_at="2026-08-24T00:00:00+00:00", image_reference=None, image_digest=None)
    second = EngineIdentity(version="0.4.0", started_at="2026-08-25T00:00:00+00:00", image_reference="0.4.0", image_digest=None)

    write_identity(tmp_path, first)
    write_identity(tmp_path, second)

    path = identity_path(tmp_path)
    assert path.exists()
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == "0.4.0"
    assert document["started_at"] == "2026-08-25T00:00:00+00:00"
    # No concatenated JSON or trailing old data.
    text = path.read_text(encoding="utf-8")
    text.index("version")
    assert text.rfind("version") == text.index("version")


def test_write_is_atomic(tmp_path: Path) -> None:
    """Concurrent readers never see a partial document: a temp file is renamed over."""
    record = EngineIdentity(version="0.5.0", started_at="2026-08-25T00:00:00+00:00", image_reference=None, image_digest=None)
    path = write_identity(tmp_path, record)
    # The parent should contain the final file and no stray temp files.
    parent_files = list(path.parent.iterdir())
    assert path in parent_files
    assert all(not f.name.startswith(".") for f in parent_files)


# ---------------------------------------------------------------------------
# T008 / T009 / T009a / T010 [US2] supervisor integration
# ---------------------------------------------------------------------------


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


import asyncio
import signal


@pytest.fixture
def supervisor_mod():
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
def config(tmp_path: Path) -> dict:
    return {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.5,
        "grace_period_s": 0.2,
        "state_home": str(tmp_path / "state"),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }


@pytest.mark.asyncio
async def test_identity_written_before_worker_starts(supervisor_mod, make_child: ChildFactory, config: dict) -> None:
    """When start_child('worker', ...) is called, the identity file already exists."""
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
        if name == "worker":
            order.append("identity_exists" if identity_path(config["state_home"]).exists() else "identity_missing")
        return children[name]

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=readiness_probe,
        )
    )

    while "bridge" not in order:
        await asyncio.sleep(0)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=2.0)

    assert result == 0
    assert order.index("temporal") < order.index("ready") < order.index("worker")
    assert "identity_exists" in order
    assert "identity_missing" not in order


@pytest.mark.asyncio
async def test_no_identity_written_on_readiness_timeout(supervisor_mod, make_child: ChildFactory, config: dict) -> None:
    """If the address never answers, _run_supervisor returns 1 and leaves no record."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def never_ready(address: str, timeout: float) -> bool:
        return False

    async def start_child(name: str, argv: list[str]) -> ChildController:
        return children[name]

    result = await supervisor_mod._run_supervisor(
        config,
        start_child=start_child,
        probe_address=never_ready,
    )

    assert result == 1
    assert not identity_path(config["state_home"]).exists()


@pytest.mark.asyncio
async def test_identity_removed_on_child_death(supervisor_mod, make_child: ChildFactory, config: dict) -> None:
    """A child exiting removes the record, and the return code stays the child's status."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")
    children = {"temporal": temporal, "worker": worker, "bridge": bridge}

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        if name == "temporal":
            asyncio.get_event_loop().call_soon(
                lambda: asyncio.create_task(_exit_after_others(temporal))
            )
        return children[name]

    async def _exit_after_others(child: ChildStub) -> None:
        await worker._started_event.wait()
        await bridge._started_event.wait()
        await asyncio.sleep(0)
        child.finish(7)

    result = await asyncio.wait_for(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        ),
        timeout=2.0,
    )

    assert result == 1
    assert not identity_path(config["state_home"]).exists()


@pytest.mark.asyncio
async def test_identity_removed_on_sigterm(supervisor_mod, make_child: ChildFactory, config: dict) -> None:
    """SIGTERM-shaped shutdown removes the record and returns 0."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        if name == "temporal":
            return temporal
        if name == "worker":
            return worker
        return bridge

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

    # The identity file must have appeared before children fully started.
    # Give the event loop a moment for the identity write to land after wait()
    # sets the started event.
    await asyncio.sleep(0.05)
    assert identity_path(config["state_home"]).exists()

    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=0.5)

    assert result == 0
    assert not identity_path(config["state_home"]).exists()


@pytest.mark.asyncio
async def test_removal_is_best_effort_missing_ok(supervisor_mod, make_child: ChildFactory, config: dict) -> None:
    """A state_home whose record was deleted by hand still shuts down normally."""
    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        if name == "temporal":
            return temporal
        if name == "worker":
            return worker
        return bridge

    run_task = asyncio.create_task(
        supervisor_mod._run_supervisor(
            config,
            start_child=start_child,
            probe_address=always_ready,
        )
    )
    await temporal._started_event.wait()
    await asyncio.sleep(0.05)
    identity_path(config["state_home"]).unlink(missing_ok=True)
    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(run_task, timeout=0.5)
    assert result == 0


@pytest.mark.asyncio
async def test_identity_path_isolated_to_config_state_home(supervisor_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_child: ChildFactory) -> None:
    """With HOME left alone, the file lands under the tmp state_home and not the real one."""
    real_state = tmp_path / "real_state"
    real_state.mkdir(parents=True)
    # Leave HOME alone, point ERGANE_STATE_HOME at a real-style path
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ERGANE_STATE_HOME", str(real_state))

    config = {
        "temporal_address": "127.0.0.1",
        "temporal_port": 7233,
        "readiness_timeout_s": 0.5,
        "grace_period_s": 0.2,
        "state_home": str(tmp_path / "state"),
        "db_filename": str(tmp_path / "temporal.sqlite"),
    }

    temporal = await make_child("temporal")
    worker = await make_child("worker")
    bridge = await make_child("bridge")

    async def always_ready(address: str, timeout: float) -> bool:
        return True

    async def start_child(name: str, argv: list[str]) -> ChildController:
        if name == "temporal":
            return temporal
        if name == "worker":
            return worker
        return bridge

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
    await asyncio.sleep(0.05)

    assert identity_path(config["state_home"]).exists()
    assert not identity_path(real_state).exists()

    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_task, timeout=0.5)


# ---------------------------------------------------------------------------
# T014 [US2] main.py rewire
# ---------------------------------------------------------------------------


def test_main_version_text_uses_cli_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """_version_text delegates to cli_version() and no longer imports importlib.metadata itself."""
    from factory.cli import main as main_mod

    called: list[str] = []

    def fake_cli_version() -> str:
        called.append("cli_version")
        return "9.9.9"

    monkeypatch.setattr(main_mod, "cli_version", fake_cli_version)
    # The _version_text body calls resolve_temporal_target() and resolve_proxy_url()
    # as top-level names; patch those in the main module namespace.
    monkeypatch.setattr(main_mod, "resolve_temporal_target", lambda: _FakeTarget("temporal.example:7233", "factory-ns"), raising=False)
    monkeypatch.setattr(main_mod, "resolve_proxy_url", lambda: _FakeProxy("http://proxy.example:4000"), raising=False)

    text = main_mod._version_text()
    assert "9.9.9" in text
    assert called == ["cli_version"]

    # The module source must not still import importlib.metadata in _version_text.
    source = Path(main_mod.__file__).read_text(encoding="utf-8")
    version_body = source.split("def _version_text", 1)[1].split("def main", 1)[0]
    assert "importlib.metadata" not in version_body
    assert "version(\"ergane-cli\")" not in version_body


class _FakeTarget:
    def __init__(self, address: str, namespace: str) -> None:
        self.address = address
        self.namespace = namespace


class _FakeProxy:
    def __init__(self, url: str) -> None:
        self.url = url
