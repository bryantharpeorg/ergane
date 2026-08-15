"""US1 of epic 011-agent-sandbox: an attempt that writes outside its worktree is caught and named.

The detector is the cheapest thing the spec builds and it survives the boundary
stories as the standing regression guard. These tests exercise it through the
activity surface, because the activity is what production calls.

Every test uses a real target repo built from the fixture skeleton, and a real
factory runtime root under `tmp_path`, so the detector compares real git state and
real filesystem state. The stub agent is shimmed onto `PATH` as `claude`, the same
pattern `test_agent_activities.py` uses.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
import asyncio
from temporalio.exceptions import CancelledError
from temporalio.testing import ActivityEnvironment

from factory.activities import agent_activities
from factory.activities.agent_activities import run_agent_attempt
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.store import connect, get_finding
from factory.usage.models import Termination
from factory.workgraph.adapter import STDOUT_LOG_NAME, home_path, transcript_dir
from factory.workgraph.models import AdapterResult, AttemptContext
from factory.workgraph.worktree import branch_name
from tests.stub_agent import install_as, last_invocation, write_control
from tests.target_repo import git, git_env

EPIC = "011-agent-sandbox"
NODE = "us1"
ATTEMPT = 1
SESSION_ID = "0f2c9a71-5d48-4c3b-8a6e-2b7c1d0e9f43"
# Make valid UUIDs for derived session ids in T004
_SESSION_ID_PREFIX = SESSION_ID[:-1]
MODEL_ALIAS = "anthropic/CHANGEME"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-011-agent-sandbox-us1-1"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"
TIMEOUT_S = 60

# A distinctive tracked file in the fixture repo.
TRACKED_FILE = "src/calc.py"
# A distinctive file the agent creates inside its own worktree.
NEW_FILE = "src/added_by_agent.py"

MASTER_KEY = "sk-master-must-never-reach-an-agent"
BOT_TOKEN = "1234567:telegram-bot-token-must-never-reach-an-agent"


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory: worktrees, transcripts, pid files."""
    return tmp_path / ".ergane"


@pytest.fixture(autouse=True)
def worker_host(
    tmp_path: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A worker host: a scratch factory root, a fake home, and credentials."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv(agent_activities.ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(agent_activities.FACTORY_ROOT_ENV, raising=False)
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("EDITOR", "vim")
    return home


@pytest.fixture(autouse=True)
def agent_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`tests/stub_agent.py` where `claude` would be found."""
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def repo(target_repo: Callable[..., Path]) -> Path:
    """A real target repo with one commit on `main`."""
    return target_repo("passing")


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Where the agent runs: a directory, not a repository."""
    path = tmp_path / "agent-worktree"
    path.mkdir()
    return path


@pytest.fixture
def context(
    repo: Path, worktree: Path, factory_root: Path
) -> Callable[..., AttemptContext]:
    """Build the attempt's context; `context(attempt=3)` overrides one field."""

    def build(**overrides: Any) -> AttemptContext:
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "home_path": str(home_path(factory_root, EPIC, NODE)),
            "proxy_url": PROXY_URL,
            "virtual_key": VIRTUAL_KEY,
            "model_alias": MODEL_ALIAS,
            "session_id": SESSION_ID,
            "timeout_s": TIMEOUT_S,
            "target_repo": str(repo),
        }
        return AttemptContext(**(fields | overrides))

    return build


@pytest.fixture
def runtime_root(factory_root: Path) -> Path:
    """The factory runtime root with stores and a sibling worktree."""
    root = factory_root
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def sibling_worktree(runtime_root: Path, tmp_path: Path) -> Path:
    """A sibling node worktree under the runtime root, with some content."""
    sibling = runtime_root / "worktrees" / EPIC / "us2"
    sibling.mkdir(parents=True, exist_ok=True)
    (sibling / "sibling.txt").write_text("sibling content\n", encoding="utf-8")
    return sibling


def archive_dir(factory_root: Path, attempt: int = ATTEMPT) -> Path:
    return transcript_dir(factory_root, EPIC, NODE, attempt)


def stdout_log(factory_root: Path, attempt: int = ATTEMPT) -> str:
    return (archive_dir(factory_root, attempt) / STDOUT_LOG_NAME).read_text(
        encoding="utf-8"
    )


async def wait_until(
    predicate: Callable[[], bool], *, what: str, timeout_s: float = 20.0
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out after {timeout_s}s waiting for {what}")




def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stub_is_up(worktree: Path, attempt: int) -> bool:
    """True once the stub for this specific attempt has written its stdin record."""
    return (worktree / ".stub-agent" / str(attempt) / "stdin.txt").is_file()



def finding_key(epic_id: str, node_id: str) -> str:
    return f"hardening/agent-worktree-boundary/{epic_id}/{node_id}"


def _detector_snapshot_dir(factory_root: Path) -> Path | None:
    """Return the detector's outside-runtime-root snapshot directory, if any."""
    candidate = factory_root.parent / f"{factory_root.name}-detector"
    if candidate.is_dir():
        return candidate
    return None


def _read_surviving_finding(snapshot_dir: Path, epic_id: str, node_id: str) -> Finding | None:
    """Read the finding the detector persisted outside the runtime root."""
    path = snapshot_dir / "findings.json"
    if not path.exists():
        return None
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data.get("findings", []):
        if entry.get("key") == finding_key(epic_id, node_id):
            return Finding(
                key=entry["key"],
                category=entry["category"],
                severity=Severity(entry["severity"]),
                status=Status(entry.get("status", "open")),
                summary=entry["summary"],
                refs=list(entry["refs"]),
                notes=entry.get("notes"),
                source=entry.get("source", "detector"),
                occurrences=entry.get("occurrences", 1),
                first_seen=entry.get("first_seen", ""),
                last_seen=entry.get("last_seen", ""),
                promoted_spec=None,
                resolved_at=None,
                resolution=None,
            )
    return None

# --- T001: an attempt whose agent modifies a tracked file outside its worktree files a finding ---


async def test_agent_modifying_tracked_file_in_target_repo_files_finding(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    repo: Path,
    worker_host: Path,
) -> None:
    """US1-S1 / FR-001: a tracked path changed in the target repo becomes a finding."""
    target_file = repo / TRACKED_FILE
    original = target_file.read_text(encoding="utf-8")
    # Script the stub to overwrite a tracked file in the *target repo*.
    # Keep the agent alive long enough for us to mutate the target repo from
    # this test process (standing in for an agent tool call).  The finding names
    # what changed, not who changed it.
    write_control(
        home_path(factory_root, EPIC, NODE),
        stdout="done",
        sleep_s=5.0,
    )

    running = asyncio.create_task(env.run(run_agent_attempt, context()))
    await wait_until(lambda: stub_is_up(worktree, ATTEMPT), what="the agent to launch")
    # Simulate the agent writing outside its worktree while the attempt runs.
    target_file.write_text(original + "\n# modified outside worktree\n", encoding="utf-8")
    result = await running

    assert result.termination == Termination.COMPLETED

    conn = connect(factory_root / "doctor.db")
    try:
        finding = get_finding(conn, finding_key(EPIC, NODE))
        assert finding is not None, "expected a finding for the changed tracked path"
        assert finding.severity is Severity.CRITICAL
        assert str(target_file.relative_to(repo)) in finding.summary or any(
            str(target_file.relative_to(repo)) in ref for ref in finding.refs
        )
        assert EPIC in finding.summary
        assert NODE in finding.summary
        assert str(ATTEMPT) in finding.summary
        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") != original
    finally:
        conn.close()


# --- T002: an attempt that writes only inside its worktree files nothing ---


async def test_agent_writing_only_inside_worktree_files_nothing(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    worker_host: Path,
) -> None:
    """US1-S2: a well-behaved attempt produces no boundary finding."""
    (worktree / "src").mkdir(exist_ok=True)
    (worktree / NEW_FILE).write_text("VALUE = 1\n", encoding="utf-8")

    write_control(home_path(factory_root, EPIC, NODE), stdout="done")
    await env.run(run_agent_attempt, context())

    conn = connect(factory_root / "doctor.db")
    try:
        assert get_finding(conn, finding_key(EPIC, NODE)) is None
    finally:
        conn.close()


# --- T003: operator work is reported but left untouched ---


async def test_operator_work_is_reported_and_untouched(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    repo: Path,
    worker_host: Path,
) -> None:
    """US1-S3/S4 / FR-002: intent is not attributed, and the detector is read-only."""
    target_file = repo / TRACKED_FILE
    original = target_file.read_text(encoding="utf-8")
    operator_file = repo / "operator_work.txt"
    operator_file.write_text("operator uncommitted work\n", encoding="utf-8")

    write_control(home_path(factory_root, EPIC, NODE), stdout="done")
    await env.run(run_agent_attempt, context())

    conn = connect(factory_root / "doctor.db")
    try:
        finding = get_finding(conn, finding_key(EPIC, NODE))
        assert finding is not None
        assert finding.severity is Severity.CRITICAL
        assert "operator_work.txt" in finding.summary or any(
            "operator_work.txt" in ref for ref in finding.refs
        )
        # The detector must not have tidied the operator's work.
        assert operator_file.read_text(encoding="utf-8") == "operator uncommitted work\n"
        assert target_file.read_text(encoding="utf-8") == original
    finally:
        conn.close()


# --- T004: the detector runs on all four termination paths ---


async def test_detector_runs_on_completed_agent_error_timeout_and_killed(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    repo: Path,
    worker_host: Path,
) -> None:
    """US1-S1: the breach is likeliest on the bad paths, so detection must cover them."""
    target_file = repo / TRACKED_FILE
    original = target_file.read_text(encoding="utf-8")

    terminations: dict[Termination, int] = {}
    for termination, exit_code, sleep_s in (
        (Termination.COMPLETED, 0, 0.0),
        (Termination.AGENT_ERROR, 1, 0.0),
        (Termination.TIMEOUT, 0, 300.0),
        (Termination.KILLED, 0, 300.0),
    ):
        attempt = len(terminations) + 1
        terminations[termination] = attempt
        ctx = context(attempt=attempt, session_id=f"{_SESSION_ID_PREFIX}{attempt}")
        write_control(
            home_path(factory_root, EPIC, NODE),
            exit_code=exit_code,
            sleep_s=sleep_s,
            stdout="working",
        )
        # Make a fresh change each iteration.
        target_file.write_text(
            original + f"\n# changed for {termination.value}\n", encoding="utf-8"
        )

        if termination is Termination.TIMEOUT:
            monkeypatch = pytest.MonkeyPatch()
            monkeypatch.setattr(agent_activities, "HEARTBEAT_INTERVAL_S", 0.05)
            try:
                result = await env.run(run_agent_attempt, ctx)
            finally:
                monkeypatch.undo()
            assert result.termination == Termination.TIMEOUT
        elif termination is Termination.KILLED:
            monkeypatch = pytest.MonkeyPatch()
            monkeypatch.setattr(agent_activities, "HEARTBEAT_INTERVAL_S", 0.05)
            running = asyncio.create_task(env.run(run_agent_attempt, ctx))
            try:
                await wait_until(lambda: stub_is_up(worktree, attempt), what="the agent to launch")
                env.cancel()
                with pytest.raises((CancelledError, asyncio.CancelledError)):
                    await running
            finally:
                monkeypatch.undo()
        else:
            await env.run(run_agent_attempt, ctx)

    conn = connect(factory_root / "doctor.db")
    try:
        # At least one finding should exist and mention the tracked file.
        finding = get_finding(conn, finding_key(EPIC, NODE))
        assert finding is not None
        assert finding.severity is Severity.CRITICAL
        assert TRACKED_FILE in finding.summary or any(
            TRACKED_FILE in ref for ref in finding.refs
        )
        assert finding.occurrences >= len(terminations)
    finally:
        conn.close()


# --- T005: runtime-root changes are detected even though they are gitignored ---


async def test_agent_truncating_runtime_root_store_files_finding(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    runtime_root: Path,
    sibling_worktree: Path,
    worker_host: Path,
) -> None:
    """US1-S5 / FR-012: evidence store / ledger / sibling worktree truncation is caught."""
    # Pre-populate the evidence stores.
    for name in ("doctor.db", "ledger.db", "verification.db"):
        (runtime_root / name).write_text("initial store content\n", encoding="utf-8")

    write_control(home_path(factory_root, EPIC, NODE), stdout="done", sleep_s=3.0)
    # Truncate while the attempt runs.
    running = asyncio.create_task(env.run(run_agent_attempt, context()))
    await wait_until(lambda: stub_is_up(worktree, ATTEMPT), what="the agent to launch")
    (runtime_root / "doctor.db").write_text("", encoding="utf-8")
    (runtime_root / "ledger.db").write_text("", encoding="utf-8")
    (sibling_worktree / "sibling.txt").write_text("", encoding="utf-8")
    await running

    conn = connect(factory_root / "doctor.db")
    try:
        finding = get_finding(conn, finding_key(EPIC, NODE))
        assert finding is not None
        assert finding.severity is Severity.CRITICAL
        summary = finding.summary
        assert "doctor.db" in summary
        assert "ledger.db" in summary
        assert str(sibling_worktree.relative_to(runtime_root)) in summary or any(
            str(sibling_worktree.relative_to(runtime_root)) in ref for ref in finding.refs
        )
        # The detector is read-only: it must not undo the truncation of files
        # it merely reports on.  `doctor.db` is where the finding itself is stored,
        # so it legitimately changes at teardown; `ledger.db` and the sibling
        # worktree must stay truncated.
        assert (runtime_root / "ledger.db").stat().st_size == 0
        assert (sibling_worktree / "sibling.txt").stat().st_size == 0
    finally:
        conn.close()


# --- T006: detector survives deletion of the runtime root ---


async def test_detector_reports_even_when_runtime_root_is_deleted(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    runtime_root: Path,
    sibling_worktree: Path,
    worker_host: Path,
) -> None:
    """US1-S6 / FR-013: the snapshot lives outside the blast radius."""
    for name in ("doctor.db", "ledger.db", "verification.db"):
        (runtime_root / name).write_text("initial store content\n", encoding="utf-8")

    write_control(home_path(factory_root, EPIC, NODE), stdout="done", sleep_s=3.0)
    running = asyncio.create_task(env.run(run_agent_attempt, context()))
    await wait_until(lambda: stub_is_up(worktree, ATTEMPT), what="the agent to launch")

    # The agent deletes the runtime root outright.
    subprocess.run(["rm", "-rf", str(runtime_root)], check=True)

    await running

    # The finding store was deleted too, so we cannot read it from the runtime root.
    # The detector must have kept its start snapshot somewhere else.
    snapshot_dir = _detector_snapshot_dir(factory_root)
    assert snapshot_dir is not None, "detector did not keep a snapshot outside the runtime root"
    assert snapshot_dir.exists(), "detector snapshot directory was also deleted"

    # Reconstitute the finding by replaying the detector with the saved snapshot.
    # (The implementation writes a findings batch file or the finding row itself
    # outside the runtime root; this test reads that artifact.)
    finding = _read_surviving_finding(snapshot_dir, EPIC, NODE)
    assert finding is not None, "expected a surviving finding after runtime root deletion"
    assert finding.severity is Severity.CRITICAL
    assert "runtime root" in finding.summary or "doctor.db" in finding.summary
