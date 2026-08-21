"""US5 of epic 073: one class, one key, bounded evidence.

The boundary detector filed its findings under
`hardening/agent-worktree-boundary/<epic>/<node>`, so four real escapes arrived
in the ledger as forty rows — one per node that ever tripped it — each with an
occurrence count of one. A ledger whose whole purpose is counting recurrence
cannot count a class it has already split by the thing that recurs. FR-024 makes
the key the class alone; FR-025 keeps the attribution the suffix used to carry,
in the refs where it belongs; FR-026 bounds the evidence so one pathological
attempt cannot write a finding of unbounded size.

Every test here supplies its own runtime root and its own target repository under
`tmp_path` and drives the detector through `capture_start` / `compare_and_report`
(plan trap 13). Nothing reads the running factory's store.

Scenario 4 is the control (plan trap 15): a bound that truncates everything
passes scenario 3 and is useless, so the paired silence — an attempt under the
bound naming every path, with no truncation notice — is what makes scenario 3
mean anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from factory.doctor.store import connect, list_findings
from factory.workgraph.detector import (
    FINDING_KEY,
    MAX_EVIDENCE_PATHS,
    capture_start,
    compare_and_report,
)
from factory.workgraph.models import AttemptContext

EPIC = "073-the-ledger-triages-what-it-can-prove"
NODE = "us5"
#: A second node of the same epic, tripping the same boundary on its own attempt.
OTHER_NODE = "us9"

#: A tracked file in the fixture target repo; changing it is a boundary escape.
TRACKED_FILE = "src/calc.py"


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    """A supplied runtime root; the detector creates `doctor.db` under it."""
    root = tmp_path / ".ergane"
    root.mkdir()
    return root


@pytest.fixture
def attempt(
    runtime_root: Path, target_repo: Callable[..., Path], tmp_path: Path
) -> Callable[..., object]:
    """Run one attempt on its own node and its own target repo.

    `during` is the escape: it runs between the start snapshot and the teardown
    comparison, exactly where an agent's writes would land. Returns whatever
    `compare_and_report` returns — the finding, or `None` for silence.
    """

    def run(node_id: str, during: Callable[[Path], None]):
        repo = target_repo("passing", name=f"repo-{node_id}")
        worktree = tmp_path / f"worktree-{node_id}"
        worktree.mkdir()
        context = AttemptContext(
            epic_id=EPIC,
            node_id=node_id,
            attempt=1,
            prompt="Implement US5.\n",
            worktree_path=str(worktree),
            home_path=str(worktree / "home"),
            proxy_url="http://litellm.test:4000",
            virtual_key=f"sk-virtual-073-{node_id}-1",
            model_alias="anthropic/CHANGEME",
            session_id="6d1b3f80-7a24-4e91-9c05-3f8a2b6d4e17",
            timeout_s=60,
            target_repo=str(repo),
        )
        capture_start(runtime_root, repo, context)
        during(repo)
        return compare_and_report(runtime_root, repo, context)

    return run


def escape_on(repo: Path) -> None:
    """One boundary violation: a tracked file in the target repo is modified."""
    target = repo / TRACKED_FILE
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# written outside the worktree\n",
        encoding="utf-8",
    )


def stored_findings(runtime_root: Path):
    """Every finding the detector persisted into the runtime root's store."""
    conn = connect(runtime_root / "doctor.db")
    try:
        return list_findings(conn)
    finally:
        conn.close()


def write_extra_paths(repo: Path, count: int) -> list[str]:
    """Create `count` new files in the target repo; return their sorted paths.

    Zero-padded so lexicographic order is numeric order: the detector sorts, and
    a test that asserts *which* paths survived the bound needs to know which ones
    those are.
    """
    (repo / "extra").mkdir()
    paths = []
    for index in range(count):
        relative = f"extra/escape-{index:03d}.py"
        (repo / relative).write_text(f"VALUE = {index}\n", encoding="utf-8")
        paths.append(relative)
    return sorted(paths)


# --- T049 / US5-S1: two nodes, one class, one row -----------------------------


def test_two_nodes_violating_the_boundary_file_one_row_with_two_occurrences(
    runtime_root: Path,
    attempt: Callable[..., object],
) -> None:
    """FR-024: the key is the class, so recurrence across nodes is countable."""
    first = attempt(NODE, escape_on)
    second = attempt(OTHER_NODE, escape_on)

    assert first is not None and second is not None, "both attempts escaped"
    # The key carries no epic or node suffix — it is the class and nothing else.
    assert first.key == FINDING_KEY == "hardening/agent-worktree-boundary"
    assert second.key == FINDING_KEY

    rows = [row for row in stored_findings(runtime_root) if row.source == first.source]
    assert [row.key for row in rows] == [FINDING_KEY], "one class is one row"
    assert rows[0].occurrences == 2, "two nodes tripping one boundary is two occurrences"


# --- T050 / US5-S2: the attribution the suffix used to carry ------------------


def test_the_row_names_the_epic_and_node_of_the_attempt_that_filed_it(
    runtime_root: Path,
    attempt: Callable[..., object],
) -> None:
    """FR-025: dropping the suffix must not drop the attribution."""
    finding = attempt(NODE, escape_on)

    assert finding is not None
    assert f"epic:{EPIC}" in finding.refs
    assert f"node:{NODE}" in finding.refs

    # And it survives the round trip through the store, which is where the
    # operator reads it.
    row = next(row for row in stored_findings(runtime_root) if row.key == FINDING_KEY)
    assert f"epic:{EPIC}" in row.refs
    assert f"node:{NODE}" in row.refs

    # A second attempt on a different node folds into the same row and the refs
    # name that attempt, not the first one's.
    attempt(OTHER_NODE, escape_on)
    row = next(row for row in stored_findings(runtime_root) if row.key == FINDING_KEY)
    assert f"epic:{EPIC}" in row.refs
    assert f"node:{OTHER_NODE}" in row.refs


# --- T051 / US5-S3: evidence that does not grow without limit -----------------


def test_an_attempt_over_the_bound_is_truncated_with_a_remainder_count(
    attempt: Callable[..., object],
) -> None:
    """FR-026: at most the bound of paths, plus a count of what was left out."""
    surplus = 6
    total = MAX_EVIDENCE_PATHS + surplus
    paths: list[str] = []

    def escape(repo: Path) -> None:
        paths.extend(write_extra_paths(repo, total))

    finding = attempt(NODE, escape)

    assert finding is not None
    assert finding.notes is not None
    kept, dropped = paths[:MAX_EVIDENCE_PATHS], paths[MAX_EVIDENCE_PATHS:]

    for path in kept:
        assert path in finding.notes, f"{path} is within the bound and must be named"
    for path in dropped:
        assert path not in finding.notes, f"{path} is past the bound and must not be"
    assert f"{surplus} more" in finding.notes, "the remainder is counted, not silent"

    # The refs and the summary are evidence too, and are bounded with the notes.
    assert f"target:{kept[0]}" in finding.refs
    assert f"target:{dropped[0]}" not in finding.refs
    assert dropped[0] not in finding.summary
    assert f"{surplus} more" in finding.summary


# --- T052 / US5-S4: the control — under the bound, nothing is hidden ----------


def test_an_attempt_under_the_bound_names_every_path_and_says_nothing_more(
    attempt: Callable[..., object],
) -> None:
    """FR-026's control: the bound truncates the pathological case and only it."""
    total = MAX_EVIDENCE_PATHS - 1
    paths: list[str] = []

    def escape(repo: Path) -> None:
        paths.extend(write_extra_paths(repo, total))

    finding = attempt(NODE, escape)

    assert finding is not None
    assert finding.notes is not None
    for path in paths:
        assert path in finding.notes, f"{path} is under the bound and must be named"
        assert f"target:{path}" in finding.refs
    assert "more" not in finding.notes, "nothing was left out, so nothing is claimed to be"
    assert "more" not in finding.summary
