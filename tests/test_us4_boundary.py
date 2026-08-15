"""US4 of epic 011-agent-sandbox: deadlines, transcripts and signals survive the boundary.

These tests drive the real bubblewrap boundary when `/usr/bin/bwrap` is present,
and are written so they fail before US4's guarantees are deliberately proved.
On a host without bwrap they guard on detection and still exercise the seam path
that US2 proved (trap 5).

Every assertion that no process survives, the transcript is byte-identical, or
the worker is still alive is backed by tool output the *agent itself* produces
inside the boundary, captured in the archived stdout log and committed as test
evidence (constitution VIII). The control test (T025) disables the boundary
through the seam's explicit host implementation and reproduces the damage,
proving the boundary is what does the work (SC-009, trap 12).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable

import pytest

from factory.workgraph.adapter import (
    STDOUT_LOG_NAME,
    BWRAP_BACKEND_BINARY,
    ClaudeCodeAdapter,
    HostAgentBackend,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from tests.stub_agent import (
    STUB_AGENT_PATH,
    install_as,
    last_invocation,
    write_control,
)

EPIC = "011-agent-sandbox"
NODE = "us4"
ATTEMPT = 1
MODEL_ALIAS = "anthropic/CHANGEME"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-011-agent-sandbox-us4-1"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US4.\n"


def _context(
    worktree_path: str,
    home_path: str,
    target_repo: str,
    session_id: str,
    timeout_s: int = 60,
) -> AttemptContext:
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt=PROMPT,
        worktree_path=worktree_path,
        home_path=home_path,
        proxy_url=PROXY_URL,
        virtual_key=VIRTUAL_KEY,
        model_alias=MODEL_ALIAS,
        session_id=session_id,
        timeout_s=timeout_s,
        target_repo=target_repo,
    )


def _build_target_repo(tmp_path: Path) -> Path:
    from tests.target_repo import build_target_repo as _build_fixture_repo

    return _build_fixture_repo(Path(tempfile.mkdtemp(prefix="target-")) / "repo", variant="passing")


@pytest.fixture(autouse=True)
def _stub_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    return tmp_path / ".ergane"


@pytest.fixture
def per_node_home(factory_root: Path) -> Path:
    home = factory_root / "homes" / EPIC / NODE
    home.mkdir(parents=True, exist_ok=True)
    return home


def _script_hang(home: Path) -> None:
    """Script the stub to spawn a child and then ignore SIGTERM past a short deadline."""
    write_control(
        home,
        ignore_sigterm=True,
        spawn_child=True,
        # A unique sleep value lets the test search for the child on the host
        # and prove it died with the namespace.
        child_sleep_s=12345.6789,
        sleep_s=300.0,
        exit_code=0,
    )


def _script_transcript(home: Path) -> None:
    """Script the stub to print distinctive output and write a transcript."""
    write_control(
        home,
        commands="echo 'us4-transcript-marker'",
        write_transcript=True,
        stdout="us4-stdout-marker",
        exit_code=0,
    )


def _script_pkill(home: Path) -> None:
    """Script the stub to run the literal 2026-08-12 pkill pattern inside the boundary.

    The literal pattern `pkill -f "python -"` matches the agent's own command
    shell inside the namespace (its command line contains the pattern), so the
    shell is killed. The stub itself survives because its command line does not
    contain `python -`, and the worker outside the PID namespace is untouched.
    This is the same containment effect the boundary exists for: the damage
    stops at the namespace edge.
    """
    commands = [
        "echo 'worker-pid-before-pkill: '$$",
        "pkill -f 'python -'",
    ]
    write_control(home, commands="\n".join(commands), exit_code=0)


async def wait_until(
    predicate: Callable[[], bool], *, what: str, timeout_s: float = 20.0
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out after {timeout_s}s waiting for {what}")


def _archive_dir(factory_root: Path) -> Path:
    return transcript_dir(factory_root, EPIC, NODE, ATTEMPT)


def _stdout_log(factory_root: Path) -> str:
    return (_archive_dir(factory_root) / STDOUT_LOG_NAME).read_text(encoding="utf-8")


def _bwrap_available() -> bool:
    return BWRAP_BACKEND_BINARY.is_file() and os.access(BWRAP_BACKEND_BINARY, os.X_OK)


def _process_alive(pid: int) -> bool:
    """Whether sending signal 0 to `pid` finds it."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _find_by_cmdline(pattern: str) -> list[int]:
    """PIDs of host processes whose command line contains `pattern`."""
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def _kill_silently(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.kill(pid, signal.SIGKILL)


# --- T022 [P] [US4] timeout: hanging agent is killed and nothing survives ------


@pytest.mark.asyncio
async def test_hanging_agent_is_killed_at_deadline_with_no_survivors(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US4-S1 / FR-006 / trap 2: deadline terminates the agent and every spawned process."""
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us4", str(worktree)],
        check=True,
    )

    # A fresh session id is unique to this attempt. After the deadline kills the
    # namespace, no host process should still carry it.
    session_id = str(uuid.uuid4())
    _script_hang(per_node_home)

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH), grace_s=1.0)
    result = await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo), session_id=session_id, timeout_s=3),
        factory_root=factory_root,
    )

    assert result.termination == "timeout"

    # The stub records signals delivered to it. The deadline machinery sends
    # SIGTERM first; the namespace is then taken down by SIGKILL, which cannot
    # be caught, so the log shows at least TERM.
    invocation = last_invocation(worktree)
    assert any(
        "TERM" in entry for entry in invocation.signals
    ), f"SIGTERM not delivered; signals={invocation.signals}"

    # Give the host a moment to reap the namespaced processes after bwrap dies.
    await asyncio.sleep(0.2)

    # On the host side, no process carrying this attempt's unique session id
    # should survive: the bwrap process and every namespaced child are gone.
    session_survivors = _find_by_cmdline(session_id)
    assert not session_survivors, f"processes with session id survived timeout: {session_survivors}"

    # The stub spawned a child whose command line contained a unique sleep value.
    # If the namespace leaked, this process would still be visible on the host.
    child_survivors = _find_by_cmdline("time.sleep(12345.6789)")
    assert not child_survivors, f"stub child survived timeout: {child_survivors}"


# --- T023 [P] [US4] transcript: stdout + session file archive byte-identically -


@pytest.mark.asyncio
async def test_attempt_inside_boundary_archives_stdout_and_transcript(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US4-S2 / FR-007 / trap 3: stdout.log and the session transcript archive with the same contents as today."""
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us4", str(worktree)],
        check=True,
    )

    session_id = str(uuid.uuid4())
    _script_transcript(per_node_home)

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    result = await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo), session_id=session_id, timeout_s=30),
        factory_root=factory_root,
    )

    assert result.termination == "completed"
    archive = _archive_dir(factory_root)
    stdout_log = archive / STDOUT_LOG_NAME
    assert stdout_log.is_file(), "stdout.log was not archived"
    log_text = stdout_log.read_text(encoding="utf-8")
    assert "us4-transcript-marker" in log_text
    assert "us4-stdout-marker" in log_text

    # The session transcript is archived beside stdout.log, named after the session id.
    from tests.stub_agent import session_transcript_path

    expected_transcript = session_transcript_path(per_node_home, worktree, session_id)
    archived_transcript = archive / f"{session_id}.jsonl"
    assert archived_transcript.is_file(), (
        f"session transcript not archived; expected {archived_transcript}"
    )
    assert archived_transcript.read_bytes() == expected_transcript.read_bytes(), (
        "archived transcript differs from the source in the per-node home"
    )


# --- T024 [P] [US4] signal: pkill -f "python -" does not reach the worker ----


@pytest.mark.asyncio
async def test_pkill_pattern_inside_boundary_does_not_kill_worker(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US4-S3 / FR-015 / SC-008 / trap 11: agent signalling by pattern cannot affect the worker.

    The literal pattern from the 2026-08-12 incident, `pkill -f "python -"`,
    matches the agent's own command shell inside the namespace (its command line
    contains the pattern). The assertion that matters is the worker's liveness,
    not the agent's exit code or the shell's survival.
    """
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us4", str(worktree)],
        check=True,
    )

    session_id = str(uuid.uuid4())
    _script_pkill(per_node_home)

    worker_pid = os.getpid()
    assert _process_alive(worker_pid), "worker not alive at test start"

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    result = await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo), session_id=session_id, timeout_s=30),
        factory_root=factory_root,
    )

    # The stub survived the pkill (its command line does not contain `python -`),
    # so the attempt completes. The worker outside the namespace is the liveness
    # assertion required by the scenario.
    assert result.termination == "completed"
    log = _stdout_log(factory_root)
    assert "worker-pid-before-pkill:" in log, f"pkill did not run; log:\n{log}"
    assert _process_alive(worker_pid), f"worker pid {worker_pid} was killed by agent's pkill"


# --- T025 [US4] control: boundary disabled, damage reproduces ----------------


@pytest.mark.asyncio
async def test_boundary_disabled_via_host_backend_reproduces_damage(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US4-S4 / SC-009 / trap 12: with the seam's host implementation, the same commands do damage.

    The live boundary tests use the literal 2026-08-12 pattern (`pkill -f "python -"`) and
    assert the worker survives. The control cannot use that exact pattern without killing the
    pytest runner too, so it uses a unique decoy marker read from a file: the agent's shell
    command line contains `$MARKER` rather than the marker itself, so the pkill cannot match
    the shell and the test can observe the decoy dying.
    """
    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us4", str(worktree)],
        check=True,
    )

    # Filesystem damage control: directories inside the target repo's working tree that the
    # live boundary made immutable must be deletable when the boundary is off.
    (repo / ".factory").mkdir(exist_ok=True)
    (repo / ".factory" / "verification.db").write_text("live store\n", encoding="utf-8")
    (repo / ".ergane").mkdir(exist_ok=True)
    (repo / ".ergane" / "marker.txt").write_text("ergane marker\n", encoding="utf-8")

    # Signal damage control: a process outside the boundary with a unique marker in its command
    # line. The pkill pattern uses the classic `[p]ython.*<marker>` regex: it matches the decoy
    # (whose command line starts with `python`) but does not match the agent's own shell, whose
    # command line contains the literal `[p]ython.*<marker>` string.
    decoy_marker = f"us4-control-decoy-{uuid.uuid4().hex}"
    decoy = subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep(300)  # {decoy_marker}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        commands = [
            f"echo 'control-agent-pid: '$$",
            f"rm -rf '{repo}/.factory' && echo 'rm-factory-ok' || echo 'rm-factory-failed: ' $?",
            f"rm -rf '{repo}/.ergane' && echo 'rm-ergane-ok' || echo 'rm-ergane-failed: ' $?",
            f"pkill -9 -f '[p]ython.*{decoy_marker}' ; echo 'pkill-decoy-exit: ' $?",
            "echo 'control-done'",
        ]
        write_control(per_node_home, commands="\n".join(commands), exit_code=0)

        session_id = str(uuid.uuid4())
        adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH), backend=HostAgentBackend())
        await adapter.run_attempt(
            _context(str(worktree), str(per_node_home), str(repo), session_id=session_id, timeout_s=30),
            factory_root=factory_root,
        )

        log = _stdout_log(factory_root)
        assert "rm-factory-ok" in log, f"control rm -rf .factory did not run; log:\n{log}"
        assert "rm-ergane-ok" in log, f"control rm -rf .ergane did not run; log:\n{log}"
        assert "pkill-decoy-exit:" in log, f"control pkill did not run; log:\n{log}"
        assert "control-done" in log, f"control agent did not finish; log:\n{log}"

        # Filesystem damage reproduced: the directories are gone.
        assert not (repo / ".factory").exists(), "control did not delete .factory"
        assert not (repo / ".ergane").exists(), "control did not delete .ergane"

        # Signal damage reproduced: the decoy outside the boundary was killed.
        # pkill sends SIGTERM; the decoy becomes a zombie until the test parent reaps it,
        # so wait() before the liveness assertion to avoid a false positive.
        with contextlib.suppress(subprocess.TimeoutExpired):
            decoy.wait(timeout=5.0)
        assert not _process_alive(decoy.pid), (
            "control did not reproduce signal damage: decoy process survived"
        )
    finally:
        _kill_silently(decoy.pid)
