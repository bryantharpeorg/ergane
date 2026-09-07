"""US2 of epic 130: the detector watches only the attempt's own worktree.

The detector's runtime-root walk used to snapshot every sibling node's worktree,
contents included.  Sibling worktrees are not this attempt's escape — they are
where the *other* nodes legitimately work, and the factory itself removes them
as ordinary housekeeping (`factory/workgraph/workflow.py` `_remove_worktree`,
called from four sites).  A detector that fires on neighbours is the reason
`max_concurrent_epics` has been pinned at 1 for a build.

After this story the runtime-root half of the comparison looks at exactly two
kinds of place: the three named evidence stores at the root, and nothing else
under `worktrees/`.  The target-repo half is untouched, so a genuine escape — a
tracked path changed in the target repository, or an evidence store truncated —
still files its `critical` finding with the same evidence it filed yesterday.

These tests drive the detector directly through `capture_start` and
`compare_and_report` against a `tmp_path` runtime root, the pattern
`tests/test_detector_reports_removals_only.py` established.

The overrides this story makes deliberately, and where each is recorded:

- 073-US4 scenario 2 (sibling worktree removed → finding) is reversed.  The
  reversal is named in the frontmatter fence of
  `specs/073-the-ledger-triages-what-it-can-prove/spec.md` and in the
  docstring of `test_removed_sibling_worktree_files_no_finding` below.  That
  spec's scenario text, story titles, work-graph block and FR bodies are
  fingerprint input and are byte-identical in this diff.
- 011-US1 scenario 5's sibling-worktree half and 011's FR-012 are reversed the
  same way, recorded in the frontmatter fence of
  `specs/011-agent-sandbox/spec.md` and in the docstring of the edited
  `test_agent_truncating_runtime_root_store_files_finding` in
  `tests/test_us1_detector.py`.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path
from typing import Callable

import pytest

from factory.doctor.models import Severity
from factory.workgraph.detector import capture_start, compare_and_report
from factory.workgraph.models import AttemptContext

EPIC = "130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote"
NODE = "us2"
ATTEMPT = 1
#: The sibling node that runs concurrently under the same runtime root.
SIBLING_NODE = "us4"

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
    """A sibling node's worktree, carrying real content."""
    worktree = runtime_root / "worktrees" / EPIC / SIBLING_NODE
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "sibling.py").write_text("VALUE = 1\n", encoding="utf-8")
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
        prompt="Implement US2.\n",
        worktree_path=str(own_worktree),
        home_path=str(own_worktree / "home"),
        proxy_url="http://litellm.test:4000",
        virtual_key="sk-virtual-130-us2-1",
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


# --- T008 / US2-S1: a sibling's writes are not this attempt's escape (control) ---


def test_sibling_worktree_written_to_files_no_finding(
    runtime_root: Path,
    sibling: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US2-S1 / FR-004 (control): a sibling that writes during the attempt is silence.

    Green before this story through the loss-only rule — creations are not
    losses — and it must stay green through the walk change: after US2 the
    sibling worktree is not in either snapshot at all, so its files can never be
    compared, let alone charged to this attempt.
    """
    # The sibling writes while this attempt is in flight: new files, edits to
    # existing ones, and generated output it would produce running its suite.
    def sibling_writes() -> None:
        (sibling / "src" / "added_by_sibling.py").write_text(
            "VALUE = 2\n", encoding="utf-8"
        )
        (sibling / "src" / "sibling.py").write_text("VALUE = 99\n", encoding="utf-8")
        (sibling / "src" / "__pycache__").mkdir()
        (sibling / "src" / "__pycache__" / "sibling.cpython-312.pyc").write_bytes(
            b"\x00" * 64
        )

    assert attempt(sibling_writes) is None


# --- T010 / US2-S3: a genuine escape still files, with its evidence unchanged (control) ---


def test_genuine_escape_files_critical_and_names_no_sibling(
    runtime_root: Path,
    repo: Path,
    sibling: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US2-S3 / FR-009 (control): the tracked half files exactly as it did.

    A tracked path is modified in the target repository *and* the sibling
    worktree is removed — ordinary housekeeping — during the same attempt.  The
    finding must be the tracked half alone: critical, naming the tracked path,
    with no ``runtime:`` ref, because a sibling worktree is not evidence.
    """
    target = repo / "src" / "calc.py"
    original = target.read_text(encoding="utf-8")

    def escape_and_housekeeping() -> None:
        target.write_text(
            original + "\n# modified outside the worktree\n", encoding="utf-8"
        )
        shutil.rmtree(sibling)

    finding = attempt(escape_and_housekeeping)

    assert finding is not None, "a tracked path changed in the target repo is a finding"
    assert finding.severity is Severity.CRITICAL
    assert "target:src/calc.py" in finding.refs
    assert finding.notes is not None
    assert "Tracked paths changed in target repository:" in finding.notes
    # The sibling's removal is in neither half of the finding.
    assert not [ref for ref in finding.refs if ref.startswith("runtime:")]
    assert SIBLING_NODE not in finding.summary
    # The detector is read-only: it reports the escape, it does not undo it.
    assert target.read_text(encoding="utf-8") != original


def test_genuine_escape_store_truncation_files_critical(
    runtime_root: Path,
    sibling: Path,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US2-S3 / FR-009 (control): the store half files exactly as it did."""
    sibling_present = sibling.exists()

    def truncate_stores() -> None:
        for name in STORE_NAMES:
            (runtime_root / name).write_text("", encoding="utf-8")

    finding = attempt(truncate_stores)

    assert finding is not None, "truncating an evidence store must still be a finding"
    assert finding.severity is Severity.CRITICAL
    for name in STORE_NAMES:
        assert name in finding.summary or any(name in ref for ref in finding.refs)
    assert sibling_present


# --- T011 / US2-S4: the report stays advisory (control) ---


def test_compare_and_report_return_gates_nothing_at_both_call_sites() -> None:
    """US2-S4 / FR-010 (control): no call site consumes the detector's return.

    Both call sites in ``run_attempt`` discard ``compare_and_report``'s return
    today — the finding is an advisory channel, and FR-010 forbids this story
    from making it enforcing.  Asserted structurally over the module's AST: each
    call must be a bare expression statement, not an assignment and not a
    condition, so no branch on it can hide.  Green before this story; its job is
    to stay green through the walk change.
    """
    adapter_path = Path(__file__).resolve().parents[1] / "factory" / "workgraph" / "adapter.py"
    tree = ast.parse(adapter_path.read_text(encoding="utf-8"))

    call_sites: list[ast.stmt] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        if not isinstance(call.func, ast.Name) or call.func.id != "compare_and_report":
            continue
        call_sites.append(node)

    assert len(call_sites) == 2, (
        "expected exactly two compare_and_report call sites in run_attempt, "
        f"found {len(call_sites)} — a third would be a new consumer of the "
        "return value and needs FR-010's answer before it lands"
    )


# --- T012 / US2-S5: the worst case still files (control) ---


def test_deleted_runtime_root_still_files_naming_the_stores(
    runtime_root: Path,
    repo: Path,
    sibling: Path,
    own_worktree: Path,
    context: AttemptContext,
) -> None:
    """US2-S5 / FR-009 (control): deleting the root outright is still loud.

    The 2026-08-14 destruction.  The start snapshot lives outside the runtime
    root, so the comparison survives the deletion; after US2 the snapshot holds
    the three stores and no sibling paths, so the finding names exactly what was
    lost — the stores — and charges no sibling.  Mirrors
    ``tests/test_us1_detector.py::test_detector_reports_even_when_runtime_root_is_deleted``
    at the detector surface, which passes unedited.
    """
    capture_start(runtime_root, repo, context)
    shutil.rmtree(runtime_root)

    finding = compare_and_report(runtime_root, repo, context)

    assert finding is not None, "a deleted runtime root must still file"
    assert finding.severity is Severity.CRITICAL
    for name in STORE_NAMES:
        assert name in finding.summary or any(name in ref for ref in finding.refs)
    # The sibling worktree went with the root, but no sibling path is charged.
    assert not [ref for ref in finding.refs if SIBLING_NODE in ref]