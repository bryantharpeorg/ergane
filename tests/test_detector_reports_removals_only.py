"""US4 of epic 073: the boundary detector reports what it says it reports.

The detector's docstring has always promised a finding for a store, ledger or
sibling worktree that was "removed or truncated". The comparison underneath it
tested `before != after`, so it also reported every path that *appeared* — and
because sibling nodes run concurrently under one runtime root, what appeared was
usually a sibling's test output. One measured finding carried 3,860 changes, of
which 3,859 were creations under a worktree belonging to a different node, and
the one remaining entry was `doctor.db` growing because the detector had written
its own finding there.

These tests pin the sentence to the code. Each one supplies its own runtime root
under `tmp_path` and drives the detector directly through `capture_start` and
`compare_and_report`, so nothing here reads the running factory's evidence.

The controls are the point (plan trap 15): scenario 1 is the silence that
scenario 2 must not take with it, and scenario 4 is the silence that scenario 3
must not take with it. Scenario 5 is the tracked-path half, which caught four
real escapes and is out of scope for every change this story makes (FR-023).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import pytest

from factory.doctor.models import Severity
from factory.workgraph.detector import capture_start, compare_and_report
from factory.workgraph.models import AttemptContext

EPIC = "073-the-ledger-triages-what-it-can-prove"
NODE = "us4"
ATTEMPT = 1
#: The sibling node that runs concurrently under the same runtime root.
SIBLING_NODE = "us9"

#: A tracked file in the fixture target repo.
TRACKED_FILE = "src/calc.py"

STORE_NAMES = ("doctor.db", "ledger.db", "verification.db")


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    """A supplied runtime root with all three evidence stores populated."""
    root = tmp_path / ".ergane"
    root.mkdir()
    for name in STORE_NAMES:
        (root / name).write_text(f"initial {name} content\n", encoding="utf-8")
    return root


@pytest.fixture
def sibling(runtime_root: Path) -> Path:
    """A sibling node's worktree, already carrying generated test output.

    The `__pycache__` and `.pytest_cache` trees are present *before* the attempt
    starts, so a test can assert they never entered the snapshot (FR-022) rather
    than only that they were tolerated on the way out.
    """
    worktree = runtime_root / "worktrees" / EPIC / SIBLING_NODE
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "sibling.py").write_text("VALUE = 1\n", encoding="utf-8")
    (worktree / "src" / "__pycache__").mkdir()
    (worktree / "src" / "__pycache__" / "sibling.cpython-312.pyc").write_bytes(b"\x00" * 64)
    (worktree / ".pytest_cache" / "v" / "cache").mkdir(parents=True)
    (worktree / ".pytest_cache" / "v" / "cache" / "lastfailed").write_text("{}\n", encoding="utf-8")
    return worktree


@pytest.fixture
def own_worktree(tmp_path: Path) -> Path:
    """Where this attempt's agent runs; it is allowed to write here."""
    path = tmp_path / "own-worktree"
    path.mkdir()
    return path


@pytest.fixture
def repo(target_repo: Callable[..., Path]) -> Path:
    """A real target repository, clean at attempt start."""
    return target_repo("passing")


@pytest.fixture
def context(repo: Path, own_worktree: Path) -> AttemptContext:
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="Implement US4.\n",
        worktree_path=str(own_worktree),
        home_path=str(own_worktree / "home"),
        proxy_url="http://litellm.test:4000",
        virtual_key="sk-virtual-073-us4-1",
        model_alias="anthropic/CHANGEME",
        session_id="0f2c9a71-5d48-4c3b-8a6e-2b7c1d0e9f43",
        timeout_s=60,
        target_repo=str(repo),
    )


@pytest.fixture
def attempt(
    runtime_root: Path, repo: Path, context: AttemptContext
) -> Callable[[Callable[[], None]], object]:
    """Run one attempt: capture, let `during` happen, compare.

    Returns whatever `compare_and_report` returns — the finding, or `None` for
    silence.
    """

    def run(during: Callable[[], None]):
        capture_start(runtime_root, repo, context)
        during()
        return compare_and_report(runtime_root, repo, context)

    return run


def snapshot_entries(runtime_root: Path) -> dict[str, dict]:
    """The runtime-root entries the start snapshot recorded."""
    directory = runtime_root.parent / f"{runtime_root.name}-detector"
    path = directory / f"{EPIC}-{NODE}-{ATTEMPT}.json"
    return json.loads(path.read_text(encoding="utf-8"))["runtime"]


def named(finding, needle: str) -> bool:
    """Whether a finding names `needle` anywhere an operator would read it."""
    return (
        needle in finding.summary
        or any(needle in ref for ref in finding.refs)
        or (finding.notes is not None and needle in finding.notes)
    )


# --- T040 / US4-S1: a concurrent sibling's output is not this attempt's escape ---


def test_sibling_worktree_gaining_files_files_no_finding(
    runtime_root: Path,
    repo: Path,
    sibling: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """FR-020/FR-022: creation is not removal, and generated output is not captured."""
    capture_start(runtime_root, repo, context)

    # FR-022: the snapshot excludes generated paths at capture, so it never grows
    # to hold a sibling's test output in the first place.
    entries = snapshot_entries(runtime_root)
    assert entries, "the snapshot should still record the sibling's real content"
    assert any("sibling.py" in path for path in entries)
    assert not [path for path in entries if "__pycache__" in path]
    assert not [path for path in entries if ".pytest_cache" in path]
    assert not [path for path in entries if path.endswith(".pyc")]

    # The sibling node runs its own suite while this attempt is in flight.
    (sibling / "src" / "added_by_sibling.py").write_text("VALUE = 2\n", encoding="utf-8")
    (sibling / "src" / "__pycache__" / "added.cpython-312.pyc").write_bytes(b"\x01" * 128)
    (sibling / "tests").mkdir()
    (sibling / "tests" / "test_sibling.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (sibling / ".pytest_cache" / "v" / "cache" / "nodeids").write_text("[]\n", encoding="utf-8")

    assert compare_and_report(runtime_root, repo, context) is None


# --- T041 / US4-S2: the control — removal must survive ---


def test_sibling_worktree_removed_files_a_finding_naming_it(
    runtime_root: Path,
    sibling: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """FR-020: this is the behaviour scenario 1's silence must not take with it."""
    relative = str(sibling.relative_to(runtime_root))

    finding = attempt(lambda: shutil.rmtree(sibling))

    assert finding is not None, "removing a sibling worktree must still be a finding"
    assert finding.severity is Severity.CRITICAL
    assert named(finding, relative)
    assert named(finding, "sibling.py")


# --- T042 / US4-S3: truncating an evidence store must survive ---


def test_truncated_evidence_store_files_a_finding_naming_it(
    runtime_root: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """FR-021: truncation of a store is loud, including `doctor.db` itself."""

    def truncate() -> None:
        for name in STORE_NAMES:
            (runtime_root / name).write_text("", encoding="utf-8")

    finding = attempt(truncate)

    assert finding is not None, "truncating an evidence store must still be a finding"
    assert finding.severity is Severity.CRITICAL
    for name in STORE_NAMES:
        assert named(finding, name)


# --- T043 / US4-S4: the control — the detector writes `doctor.db` itself ---


def test_growing_evidence_store_files_no_finding(
    runtime_root: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """FR-021: growth is not truncation, or every attempt files a finding forever."""

    def grow() -> None:
        for name in STORE_NAMES:
            path = runtime_root / name
            path.write_text(
                path.read_text(encoding="utf-8") + "a page of rows\n" * 64,
                encoding="utf-8",
            )

    assert attempt(grow) is None


# --- T044 / US4-S5: the tracked half is untouched ---


def test_modified_tracked_path_still_files_a_finding(
    runtime_root: Path,
    repo: Path,
    sibling: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """FR-023: the half that caught the real escapes reports exactly as it did."""
    target = repo / TRACKED_FILE
    original = target.read_text(encoding="utf-8")

    def escape() -> None:
        target.write_text(original + "\n# modified outside the worktree\n", encoding="utf-8")

    finding = attempt(escape)

    assert finding is not None, "a tracked path changed in the target repo is a finding"
    assert finding.severity is Severity.CRITICAL
    assert f"target:{TRACKED_FILE}" in finding.refs
    assert finding.notes is not None
    assert "Tracked paths changed in target repository:" in finding.notes
    # Nothing under the runtime root was lost, so the finding is the tracked
    # half alone — the two halves are reported independently.
    assert not [ref for ref in finding.refs if ref.startswith("runtime:")]
    # The detector is read-only: it reports the escape, it does not undo it.
    assert target.read_text(encoding="utf-8") != original
