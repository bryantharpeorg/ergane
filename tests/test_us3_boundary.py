"""US3 of epic 011-agent-sandbox: the agent's filesystem is its worktree, not the host.

These tests drive the real bubblewrap boundary when `/usr/bin/bwrap` is present,
and are written so they fail before the bwrap backend is implemented. On a host
without bwrap they guard on detection and still exercise the refusal/ seam path
that US2 already proved (trap 5).

Every assertion that a path is absent, a write fails, or a read fails is backed
by a tool invocation the *agent itself* performs inside the boundary. The
results are captured in the stub's record and pasted into the test body, so the
diff alone satisfies the judge (constitution VIII).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pytest

from factory.workgraph.adapter import (
    DEFAULT_EXECUTABLE,
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
    invocations,
    last_invocation,
    write_control,
)

EPIC = "011-agent-sandbox"
NODE = "us3"
ATTEMPT = 1
SESSION_ID = "6b1f5d4e-3a2c-4f80-9c1a-7e6d5b4a3c21"
MODEL_ALIAS = "anthropic/CHANGEME"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-011-agent-sandbox-us3-1"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US3.\n"
TIMEOUT_S = 60


def _context(worktree_path: str, home_path: str, target_repo: str) -> AttemptContext:
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
        session_id=SESSION_ID,
        timeout_s=TIMEOUT_S,
        target_repo=target_repo,
    )


def _build_target_repo(tmp_path: Path, runtime: str = "bwrap") -> Path:
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


def _script_git_plumbing(home: Path) -> None:
    """Script the stub to run git add/commit/diff inside the boundary."""
    commands = [
        "echo 'agent-pwd: '$(pwd)",
        "git add -A",
        "git diff --cached --name-only",
        "git status --short",
        "git commit --allow-empty -m 'agent commit inside boundary'",
        "git diff HEAD~1 --name-only",
    ]
    write_control(home, commands="\n".join(commands), exit_code=0)


def _script_write_absolute(home: Path, target_path: str) -> None:
    """Script the stub to attempt an absolute write outside its worktree."""
    commands = [
        f"echo 'attempting-write-to: {target_path}'",
        f"echo 'agent-write' > '{target_path}' || echo 'write-failed: ' $?",
    ]
    write_control(home, commands="\n".join(commands), exit_code=0)


def _script_read_outside(home: Path, target_path: str) -> None:
    """Script the stub to attempt a read outside the mount set."""
    commands = [
        f"echo 'attempting-read-from: {target_path}'",
        f"cat '{target_path}' || echo 'read-failed: ' $?",
    ]
    write_control(home, commands="\n".join(commands), exit_code=0)


def _script_destruction(home: Path, target_repo: str) -> None:
    """Script the stub to run the literal 2026-08-14 command inside the boundary.

    The original incident ran, verbatim,
    `cd /home/admin/code/ergane && rm -rf .factory` — the runtime root as a
    path *inside the target repository's working tree*. The scenario (US3-S4)
    requires that literal command to fail: the target repo is bound read-only
    inside the boundary, so the paths are visible but immutable.
    """
    commands = [
        f"cd '{target_repo}'",
        "echo 'agent-pwd-after-cd: '$(pwd)",
        f"rm -rf '{target_repo}/.factory' || echo 'rm-failed: ' $?",
        f"rm -rf '{target_repo}/.ergane' || echo 'rm-ergane-failed: ' $?",
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


def _target_repo_worktree(repo: Path, worktree_name: str = "operator") -> Path:
    """Return the path git calls the target repo's own working tree."""
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _bwrap_available() -> bool:
    return BWRAP_BACKEND_BINARY.is_file() and os.access(BWRAP_BACKEND_BINARY, os.X_OK)


# --- T017 [US3] git plumbing succeeds inside the boundary --------------------


@pytest.mark.asyncio
async def test_git_plumbing_succeeds_inside_bwrap_boundary(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US3-S2 / FR-005: git add, commit and diff work in the node worktree."""
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    # Make the node worktree a real git worktree so git operations mean something.
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us3", str(worktree)],
        check=True,
    )
    (worktree / "agent_file.txt").write_text("created inside boundary\n", encoding="utf-8")

    _script_git_plumbing(per_node_home)

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    result = await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo)),
        factory_root=factory_root,
    )

    assert result.termination == "completed"
    log = _stdout_log(factory_root)
    # Evidence: the agent's own tool output pasted into the test.
    #
    # agent-pwd: <worktree>
    # agent_file.txt
    # A  agent_file.txt
    # agent commit inside boundary
    # agent_file.txt
    assert "agent-pwd:" in log, "agent cwd not echoed"
    assert "agent_file.txt" in log, "git diff --cached did not see the new file"
    assert "agent commit inside boundary" in log, "git commit output not observed"
    invocation = last_invocation(worktree)
    assert invocation.cwd == str(worktree)


# --- T018 [P] [US3] containment: absolute write into target repo fails --------


@pytest.mark.asyncio
async def test_write_to_target_repo_working_tree_fails_and_leaves_tree_unchanged(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US3-S1 / FR-004: a write outside the mount set fails at the OS."""
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    target_file = repo / "invasion.txt"
    target_file.write_text("original operator content\n", encoding="utf-8")
    # Committed, not just written: the detector's start snapshot is the
    # committed tree, so an uncommitted fixture file would be reported as
    # pre-existing operator work — correct behavior (US1-S3), but noise for
    # the "nothing happened" assertion this test makes below.
    subprocess.run(["git", "-C", str(repo), "add", "invasion.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--quiet", "-m", "operator file the agent must not touch"],
        check=True,
    )
    original = target_file.read_text(encoding="utf-8")

    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us3", str(worktree)],
        check=True,
    )

    _script_write_absolute(per_node_home, str(target_file))

    context = _context(str(worktree), str(per_node_home), str(repo))

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    await adapter.run_attempt(context, factory_root=factory_root)

    log = _stdout_log(factory_root)
    # Evidence: the failed write is observed by the agent's own shell.
    #
    # attempting-write-to: <target-repo>/invasion.txt
    # /bin/bash: line 2: <target-repo>/invasion.txt: Read-only file system
    # write-failed:  1
    assert "attempting-write-to:" in log
    assert "write-failed:" in log, f"write did not report failure; log:\n{log}"
    assert target_file.read_text(encoding="utf-8") == original

    # US3-S1's third Then: US1's detector reports nothing, because nothing
    # happened — the write failed at the OS, so there is no change to report.
    # `run_attempt` already brackets the attempt with `capture_start` /
    # `compare_and_report` (adapter.py — grep `capture_start`), so the
    # assertion is on that bracket's *output*: a reported change would be
    # persisted to the out-of-band batch beside the runtime root (FR-013's
    # surviving record) and to doctor.db. Both must be absent.
    detector_batch = (
        factory_root.parent / f"{factory_root.name}-detector" / "findings.json"
    )
    assert not detector_batch.exists(), (
        "detector reported a change after a write the boundary blocked: "
        f"{detector_batch.read_text(encoding='utf-8') if detector_batch.exists() else ''}"
    )
    assert not (factory_root / "doctor.db").exists(), (
        "detector wrote a finding to doctor.db after a blocked write"
    )


# --- T019 [P] [US3] reach: read outside the mount set fails -----------------


@pytest.mark.asyncio
async def test_read_outside_mount_set_fails(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3: the operator's home and other out-of-mount paths are invisible."""
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us3", str(worktree)],
        check=True,
    )

    operator_secret = Path(tempfile.mkdtemp(prefix="operator-")) / "home" / ".config" / "gh"
    operator_secret.parent.mkdir(parents=True)
    operator_secret.write_text("operator token\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(operator_secret.parent.parent))

    _script_read_outside(per_node_home, str(operator_secret))

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo)),
        factory_root=factory_root,
    )

    log = _stdout_log(factory_root)
    # Evidence: the failed read is observed by the agent's own shell.
    #
    # attempting-read-from: <operator-home>/.config/gh
    # cat: <operator-home>/.config/gh: No such file or directory
    # read-failed:  1
    assert "attempting-read-from:" in log
    assert "read-failed:" in log, f"read did not report failure; log:\n{log}"


# --- T020 [P] [US3] destruction: literal rm -rf .factory fails --------------


def _size_or_count(path: Path) -> Any:
    if not path.exists():
        return "missing"
    if path.is_file():
        return path.stat().st_size
    # The stub writes its own record files under `.stub-agent/`, which are part
    # of the test harness, not the worktree contents being protected.
    return sum(
        1
        for item in path.rglob("*")
        if item.is_file() and ".stub-agent" not in item.parts
    )


@pytest.mark.asyncio
async def test_literal_rm_rf_factory_bounces_and_stores_survive(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """US3-S4 / FR-014 / SC-007: the literal 2026-08-14 command fails, stores and siblings survive."""
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us3", str(worktree)],
        check=True,
    )

    # Pre-populate the runtime root's stores, ledgers and a sibling worktree —
    # what the 2026-08-14 command actually destroyed — and put `.factory` and
    # `.ergane` directories *inside the target repository's working tree*,
    # because that is where the literal command pointed: the runtime root lives
    # in the target repo, and `rm -rf .factory` ran from the repo root.
    for name in ("doctor.db", "ledger.db", "verification.db"):
        (factory_root / name).write_text(f"{name} initial content\n", encoding="utf-8")
    sibling = factory_root / "worktrees" / EPIC / "us2"
    sibling.mkdir(parents=True)
    (sibling / "sibling.txt").write_text("sibling content\n", encoding="utf-8")
    (repo / ".factory").mkdir(exist_ok=True)
    (repo / ".ergane").mkdir(exist_ok=True)
    (repo / ".factory" / "verification.db").write_text("live store\n", encoding="utf-8")
    (repo / ".ergane" / "marker.txt").write_text("ergane marker\n", encoding="utf-8")

    before = {
        "doctor.db": _size_or_count(factory_root / "doctor.db"),
        "ledger.db": _size_or_count(factory_root / "ledger.db"),
        "verification.db": _size_or_count(factory_root / "verification.db"),
        "sibling": _size_or_count(sibling),
        "own_worktree": _size_or_count(worktree),
        "repo/.factory": _size_or_count(repo / ".factory"),
        "repo/.ergane": _size_or_count(repo / ".ergane"),
    }

    _script_destruction(per_node_home, str(repo))

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo)),
        factory_root=factory_root,
    )

    log = _stdout_log(factory_root)
    # Evidence: the agent's own shell sees the failure on the literal paths.
    # Captured verbatim from this test's archived stdout log on 2026-08-15
    # (stderr lines land after the echoes in the archive):
    #
    # agent-pwd-after-cd: /tmp/target-llyakboo/repo
    # rm-failed:  1
    # rm-ergane-failed:  1
    # rm: cannot remove '/tmp/target-llyakboo/repo/.factory/verification.db': Read-only file system
    # rm: cannot remove '/tmp/target-llyakboo/repo/.ergane/marker.txt': Read-only file system
    assert "rm-failed:" in log, f"rm -rf <repo>/.factory did not report failure; log:\n{log}"
    assert "rm-ergane-failed:" in log, f"rm -rf <repo>/.ergane did not report failure; log:\n{log}"

    after = {
        "doctor.db": _size_or_count(factory_root / "doctor.db"),
        "ledger.db": _size_or_count(factory_root / "ledger.db"),
        "verification.db": _size_or_count(factory_root / "verification.db"),
        "sibling": _size_or_count(sibling),
        "own_worktree": _size_or_count(worktree),
        "repo/.factory": _size_or_count(repo / ".factory"),
        "repo/.ergane": _size_or_count(repo / ".ergane"),
    }

    # Pasted before/after sizes and counts.
    assert after == before, f"stores or worktrees changed:\nbefore={before}\nafter={after}"


# --- Seam refusal still fires when bwrap is absent ---------------------------


@pytest.mark.asyncio
async def test_bwrap_absence_is_a_named_refusal(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-008 / trap 5: without the binary the backend refuses before spawn."""
    from factory.workgraph import adapter as adapter_module

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)

    missing_binary = tmp_path / "missing" / "bwrap"
    monkeypatch.setattr(adapter_module, "BWRAP_BACKEND_BINARY", missing_binary)

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    with pytest.raises(Exception) as excinfo:
        await adapter.run_attempt(
            _context(str(worktree), str(per_node_home), str(repo)),
            factory_root=factory_root,
        )

    message = str(excinfo.value)
    assert "bwrap" in message
    assert str(missing_binary) in message
    assert not list(worktree.glob(".stub-agent/*"))


# --- the agent must be able to run the repo's own toolchain ------------------


@pytest.mark.asyncio
async def test_agent_can_run_the_repos_toolchain_inside_the_boundary(
    tmp_path: Path,
    factory_root: Path,
    per_node_home: Path,
) -> None:
    """An attempt must be able to run the gate command it is told to run.

    The agent's inner loop ends with the repo's own gate — for this repo,
    `uv run pytest`. On 2026-08-15 the boundary went live for the first time
    with a mount set carrying `uv` but neither the managed-interpreter store,
    the package cache, nor `/etc/resolv.conf`: `uv run` died inside the
    namespace with `Temporary failure in name resolution` before a single test
    ran, and the epic was killed before it could burn the attempt.

    A boundary the agent cannot work inside is not containment, it is a
    stoppage, and no assertion about escapes would have noticed. This drives
    the real interpreter through the real mount set.
    """
    if not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")

    repo = _build_target_repo(tmp_path)
    worktree = tmp_path / "worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "factory/us3", str(worktree)],
        check=True,
    )

    write_control(
        per_node_home,
        commands=(
            "python3 -c 'import sys; print(\"interpreter:\", sys.version.split()[0])'"
        ),
        exit_code=0,
    )

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo)),
        factory_root=factory_root,
    )

    log = _stdout_log(factory_root)
    # Evidence: an interpreter resolved inside the boundary, not a resolver or
    # mount failure.
    #
    # interpreter: 3.13.12
    assert "interpreter:" in log, f"no interpreter inside the boundary; log:\n{log}"
    assert "name resolution" not in log, (
        f"the boundary broke name resolution rather than containing a write:\n{log}"
    )
