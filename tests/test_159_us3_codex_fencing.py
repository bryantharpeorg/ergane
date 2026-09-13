"""US3 of 159: no child can write a candidate after its owner inspects it."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator

import pytest

from factory.workgraph.adapter import (
    HostAgentBackend,
    CODEX_GATEWAY_PROVIDER,
    SharedAttemptPolicy,
    _group_alive,
    _read_pgid,
    pid_file,
)
from factory.workgraph.codex_credential import (
    CredentialFinalization,
    CredentialCandidate,
    CredentialFenceFailure,
    fence_prior_child_before_candidate,
    finalize_current_candidate,
    quarantine_candidate,
)
from factory.workgraph.models import AttemptContext
from factory.workgraph.adapter import CredentialStage
from tests.stub_codex import (
    codex_home,
    install_as,
    write_control,
)


EPIC = "159-a-subscription-credential-has-one-durable-owner"
NODE = "us3"
ATTEMPT = 1


@pytest.fixture
def attempt(worktree: Path, node_home: Path) -> Callable[..., AttemptContext]:
    def build(**overrides: object) -> AttemptContext:
        fields = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": "scope",
            "worktree_path": str(worktree),
            "home_path": str(node_home),
            "proxy_url": "http://litellm.test:4000",
            "virtual_key": "virtual-key",
            "model_alias": "synthetic-model",
            "session_id": "synthetic-session",
            "timeout_s": 1,
            "agent": "codex",
            "route": "subscription",
        }
        return AttemptContext(**(fields | overrides))

    return build


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    path = tmp_path / "worktree"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def node_home(tmp_path: Path) -> Path:
    return tmp_path / "node-home"


@pytest.fixture
def spawn_orphan() -> Iterator[Callable[[], subprocess.Popen[bytes]]]:
    spawned: list[subprocess.Popen[bytes]] = []

    def spawn() -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        spawned.append(process)
        return process

    yield spawn
    for process in spawned:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


async def test_prior_reap_precedes_candidate_inspection(tmp_path: Path) -> None:
    """FR-010: the old owner's handle is fenced before its bytes are opened."""
    calls: list[str] = []
    candidate = tmp_path / "candidate" / "auth.json"
    candidate.parent.mkdir()
    candidate.write_text("{}", encoding="utf-8")

    async def reap(pid_file: object) -> None:
        calls.append("reap")

    async def inspect_candidate(candidate: CredentialCandidate) -> object:
        calls.append("candidate")
        return candidate.path.read_text(encoding="utf-8")

    result = await fence_prior_child_before_candidate(
        reap, inspect_candidate, object(), candidate, generation=1
    )

    assert calls == ["reap", "candidate"]
    assert result == "{}"


async def test_surviving_prior_child_refuses_candidate_inspection(
    tmp_path: Path,
    spawn_orphan: Callable[[], subprocess.Popen[bytes]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-010: an unproved old group is refused before its candidate is opened."""
    orphan = spawn_orphan()
    pid_file = tmp_path / "previous.pid"
    pid_file.write_text(f"{orphan.pid}\n", encoding="utf-8")
    candidate = tmp_path / "candidate" / "auth.json"
    candidate.parent.mkdir()
    candidate.write_text("{}", encoding="utf-8")
    calls: list[str] = []
    policy = SharedAttemptPolicy.__new__(SharedAttemptPolicy)
    policy._cli = type("StubCLI", (), {"grace_s": -1})()
    monkeypatch.setattr(
        "factory.workgraph.adapter._group_alive", lambda pgid: pgid == orphan.pid
    )

    async def reap(path: object) -> None:
        await policy._reap(path)
        calls.append("reap")

    async def inspect_candidate(candidate: CredentialCandidate) -> object:
        calls.append("candidate")
        return candidate.path

    with pytest.raises(CredentialFenceFailure) as excinfo:
        await fence_prior_child_before_candidate(
            reap, inspect_candidate, pid_file, candidate, generation=1
        )

    assert "could not prove" in str(excinfo.value)
    assert calls == []
    assert candidate.read_text(encoding="utf-8") == "{}"
    orphan.kill()
    orphan.wait(timeout=2)


async def test_gateway_subscription_gateway_reuses_one_clean_home(
    node_home: Path, attempt: Callable[..., AttemptContext]
) -> None:
    """FR-011: one node home holds only the current route's exact inputs."""
    from factory.workgraph.adapter import CodexAdapter

    adapter = CodexAdapter()
    codex_home = node_home / ".codex"
    node_home.mkdir(parents=True, exist_ok=True)
    gateway = attempt(route="gateway", virtual_key="gateway-key")
    subscription = attempt(route="subscription", virtual_key="")

    adapter._seed_home(node_home, None, gateway)
    assert (codex_home / "config.toml").read_text(encoding="utf-8").count(
        f'model_provider = "{CODEX_GATEWAY_PROVIDER}"'
    ) == 1
    assert not (codex_home / "auth.json").exists()

    operator = node_home / "operator-auth.json"
    operator.parent.mkdir(parents=True, exist_ok=True)
    operator.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
    adapter._seed_home(node_home, operator, subscription)
    assert not (codex_home / "config.toml").exists()
    assert (codex_home / "auth.json").is_file()

    adapter._seed_home(node_home, None, gateway)
    assert not (codex_home / "auth.json").exists()
    assert (codex_home / "config.toml").read_text(encoding="utf-8").count(
        f'model_provider = "{CODEX_GATEWAY_PROVIDER}"'
    ) == 1


@pytest.mark.parametrize("outcome", ["normal", "nonzero", "timeout"])
async def test_current_finalization_is_ordered_before_candidate_read(
    outcome: str, tmp_path: Path
) -> None:
    """FR-012: terminate, prove, then read for every termination class."""
    calls: list[str] = []
    candidate = tmp_path / "candidate" / "auth.json"
    candidate.parent.mkdir()
    candidate.write_text("{}", encoding="utf-8")

    async def terminate() -> None:
        calls.append("terminate")

    async def prove() -> None:
        calls.append("prove")

    async def inspect_candidate(candidate: CredentialCandidate) -> object:
        calls.append("candidate")
        return candidate.path.read_text(encoding="utf-8")

    result = await finalize_current_candidate(
        terminate, prove, inspect_candidate, candidate, generation=1
    )

    assert calls == ["terminate", "prove", "candidate"]
    assert result.result == "{}"
    assert result.retained_ownership is False


async def test_unprovable_death_quarantines_and_retains_the_lease(
    tmp_path: Path,
) -> None:
    """FR-012: an unproved candidate is never read and ownership survives."""
    calls: list[str] = []
    candidate = tmp_path / "candidate" / "auth.json"
    candidate.parent.mkdir()
    candidate.write_text("{}", encoding="utf-8")

    async def terminate() -> None:
        calls.append("terminate")

    async def prove() -> None:
        calls.append("prove")
        raise CredentialFenceFailure("could not prove process group death")

    def quarantine(path: object) -> None:
        calls.append("quarantine")
        candidate = getattr(path, "path")
        quarantine_candidate(tmp_path, candidate, generation=1)

    result = await finalize_current_candidate(
        terminate,
        prove,
        lambda candidate: calls.append("candidate") or candidate.path,
        candidate,
        generation=1,
        quarantine=quarantine,
    )

    assert calls == ["terminate", "prove", "quarantine"]
    assert not candidate.exists()
    quarantined = tmp_path / "quarantine" / "1" / "auth.json"
    assert quarantined.read_text(encoding="utf-8") == "{}"
    assert result.retained_ownership is True
    assert result.result is None


async def test_real_current_process_group_and_descendant_are_dead_before_read(
    tmp_path: Path,
) -> None:
    """FR-012: the descendant is gone too, not merely the agent leader."""
    child_script = (
        "import os, subprocess, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'],"
        " start_new_session=False)\n"
        "time.sleep(300)\n"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        child_script,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid_file = tmp_path / "current.pid"
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    candidate = tmp_path / "candidate" / "auth.json"
    candidate.parent.mkdir()
    candidate.write_text("{}", encoding="utf-8")
    policy = SharedAttemptPolicy.__new__(SharedAttemptPolicy)
    policy._cli = type("StubCLI", (), {"grace_s": 0.05})()

    async def terminate() -> None:
        await policy._reclaim(process)

    async def prove() -> None:
        pgid = _read_pgid(pid_file)
        assert pgid is not None and not _group_alive(pgid)

    async def inspect_candidate(candidate: CredentialCandidate) -> object:
        return candidate.path.read_text(encoding="utf-8")

    result = await finalize_current_candidate(
        terminate,
        prove,
        inspect_candidate,
        candidate,
        generation=1,
    )

    assert result.result == "{}"
    assert result.retained_ownership is False
    await process.wait()


@pytest.mark.parametrize("outcome", ["normal", "nonzero", "timeout", "cancelled"])
async def test_adapter_finalizes_before_candidate_reads(
    outcome: str,
    tmp_path: Path,
    worktree: Path,
    node_home: Path,
    attempt: Callable[..., AttemptContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-012: the shared adapter runs the same fence before its final read."""
    calls: list[str] = []
    candidate = codex_home(node_home) / "auth.json"

    async def terminate() -> None:
        calls.append("terminate")

    async def prove() -> None:
        calls.append("prove")

    async def inspect_candidate(observed: CredentialCandidate) -> object:
        calls.append("candidate")
        assert observed.path == candidate
        return candidate.read_text(encoding="utf-8")

    def wrapped(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return finalize_current_candidate(
            terminate, prove, inspect_candidate, candidate, generation=1
        )

    monkeypatch.setattr(
        "factory.workgraph.adapter.finalize_current_candidate",
        wrapped,
    )

    node_home.mkdir(parents=True, exist_ok=True)
    operator = node_home / "operator-auth.json"
    operator.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
    codex_home(node_home).mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    install_as(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    from factory.workgraph.adapter import CodexAdapter

    adapter = CodexAdapter(
        executable="codex",
        grace_s=0.02,
        backend=HostAgentBackend(executable="codex"),
    )
    adapter._credential = lambda context: CredentialStage(
        gateway=False,
        path=operator,
        source="synthetic-codex-file",
    )
    context = attempt(timeout_s=1)
    if outcome in {"timeout", "cancelled"}:
        write_control(node_home, sleep_s=2.0)
    else:
        write_control(
            node_home,
            sleep_s=0.0,
            exit_code=0 if outcome == "normal" else 1,
            json_events=False,
            write_rollout=False,
        )
    if outcome == "cancelled":
        run = asyncio.create_task(
            adapter.run_attempt(context, factory_root=tmp_path / "factory")
        )
        await wait_until_file(
            pid_file(tmp_path / "factory", EPIC, NODE), "the child process"
        )
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert calls == ["terminate", "prove", "candidate"]
    else:
        await adapter.run_attempt(context, factory_root=tmp_path / "factory")
        assert calls == ["terminate", "prove", "candidate"]


async def test_adapter_retains_owner_when_current_death_is_unprovable(
    tmp_path: Path,
    worktree: Path,
    node_home: Path,
    attempt: Callable[..., AttemptContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-012: failed fencing keeps the pid and candidate for recovery."""
    candidate = codex_home(node_home) / "auth.json"
    node_home.mkdir(parents=True, exist_ok=True)
    operator = node_home / "operator-auth.json"
    operator.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
    codex_home(node_home).mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    install_as(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr("factory.workgraph.adapter._group_alive", lambda pgid: True)
    from factory.workgraph.adapter import CodexAdapter

    adapter = CodexAdapter(
        executable="codex",
        grace_s=0.02,
        backend=HostAgentBackend(executable="codex"),
    )
    adapter._credential = lambda context: CredentialStage(
        gateway=False,
        path=operator,
        source="synthetic-codex-file",
    )
    context = attempt(timeout_s=1)
    write_control(
        node_home,
        sleep_s=0.0,
        exit_code=0,
        json_events=False,
        write_rollout=False,
    )
    factory_root = tmp_path / "factory"

    result = await adapter.run_attempt(context, factory_root=factory_root)
    pids = pid_file(factory_root, EPIC, NODE)

    assert result.owner_retained is True
    assert "could not prove" in result.detail
    quarantined = candidate.parent / "quarantine" / "1" / "auth.json"
    assert quarantined.read_text(encoding="utf-8") == operator.read_text(
        encoding="utf-8"
    )
    assert not candidate.exists()
    assert pids.exists()


async def test_cancelled_adapter_retains_owner_without_finalizing_evidence(
    tmp_path: Path,
    worktree: Path,
    node_home: Path,
    attempt: Callable[..., AttemptContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-012: cancellation plus failed fencing leaves recovery state alone."""
    candidate = codex_home(node_home) / "auth.json"
    node_home.mkdir(parents=True, exist_ok=True)
    operator = node_home / "operator-auth.json"
    operator.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
    codex_home(node_home).mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    install_as(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    async def retained_finalization(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return CredentialFinalization(
            candidate=CredentialCandidate(candidate, 1),
            retained_ownership=True,
            fence_error="could not prove current process group died",
        )

    monkeypatch.setattr(
        "factory.workgraph.adapter.finalize_current_candidate",
        retained_finalization,
    )
    from factory.workgraph.adapter import CodexAdapter

    adapter = CodexAdapter(
        executable="codex",
        grace_s=0.02,
        backend=HostAgentBackend(executable="codex"),
    )
    adapter._credential = lambda context: CredentialStage(
        gateway=False,
        path=operator,
        source="synthetic-codex-file",
    )
    context = attempt(timeout_s=1)
    write_control(node_home, sleep_s=2.0)
    factory_root = tmp_path / "factory"
    run = asyncio.create_task(adapter.run_attempt(context, factory_root=factory_root))
    await wait_until_file(pid_file(factory_root, EPIC, NODE), "the child process")
    candidate_before_cancel = candidate.read_text(encoding="utf-8")
    run.cancel()
    result = await run

    assert result.owner_retained is True
    assert candidate.read_text(encoding="utf-8") == candidate_before_cancel
    assert pid_file(factory_root, EPIC, NODE).exists()


async def wait_until_file(path: Path, what: str) -> None:
    for _ in range(100):
        if path.exists():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}: {path}")
