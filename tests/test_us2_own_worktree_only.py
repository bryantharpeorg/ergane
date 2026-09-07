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

from pathlib import Path
from typing import Callable

import pytest

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