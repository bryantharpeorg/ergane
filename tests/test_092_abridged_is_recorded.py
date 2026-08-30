"""A verdict reached on part of a diff says so, and one reached on all of it says that.

US1 and US2 opened a gap between the judge's attention budget and the size at
which work is refused, and every diff that lands in that gap is judged on an
abridgement. That is the outcome those stories exist to make reachable, and it
is also what Principle VIII spends its argument on: the judge sees the diff and
the criteria and nothing else, so a PASS formed over elided evidence is only
safe if the record admits it was.

Three states, never two, which is the whole of plan trap 6:

- **abridged**, with the numbers — the diff cost more than the budget, and the
  record says by how much;
- **whole** — the diff fit, said out loud. An `OutputCheck` whose abridgement
  field reads "not abridged" is a statement; one whose field is absent is not;
- **not recorded** — every row written before this story, and every check that
  never measured a diff at all (a read-scoped node, an empty worktree). `None`
  is reserved for exactly that, so "the judge saw it whole" can never be read
  off a row that predates anyone asking.

The amount is measured through the functions under test rather than recomputed
here. `measured()` makes the refusal state its own count of the same assembly,
and `prepare_diff` is asked whether it actually abridged; a test that assembled
the listing and the sections itself would agree with itself rather than with the
code, and the pair agreeing at the margin is what plan trap 3 is about. Sizes
come from the two constants and never from 65536, for the reason the two
sibling files give: both are tuned values and one has moved already.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli import main as main_module
from factory.config import WriteScope
from factory.env import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.verify.diffbounds import DIFF_INPUT_LIMIT
from factory.verify.diffcheck import check_output
from factory.verify.judge import prepare_diff
from factory.verify.models import (
    DiffAbridgement,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
    compose_result,
)
from factory.verify.store import connect, node_history, upsert_result
from factory.workgraph.worktree import diff as worktree_diff
from tests.test_092_two_limits import (
    RAISED_THRESHOLD,
    between_the_limits,
    measured,
)
from tests.test_diff_size import (
    TRACKED_FILE,
    WORK,
    base_of,
    commit,
    green_gates,
    write,
)

EPIC_ID = "092-the-diff-ceiling-and-the-evidence-doctrine-agree"


def stored_result(
    check: OutputCheck, *, node_id: str = "us3", attempt: int = 1
) -> VerificationResult:
    """The smallest complete evidence bundle carrying one output check."""
    return compose_result(
        epic_id=EPIC_ID,
        node_id=node_id,
        attempt=attempt,
        form=VerificationForm.PHASE,
        gate_results=green_gates(),
        output_check=check,
        judge=None,
        criteria_sha256="a" * 64,
        spec_ref=f"specs/{EPIC_ID}/spec.md",
        started_at="2026-08-30T10:00:00Z",
        finished_at="2026-08-30T10:03:00Z",
    )


def ordinary_work(node_worktree: Callable[..., Path]) -> tuple[Path, str]:
    """A committed worktree well under either limit — the whole-diff case."""
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, WORK)
    commit(worktree, "us3: ordinary work, well under the judge's budget")
    return worktree, base


# --- T016 / US3-S1: an abridged input is recorded, with its amount -----------


def test_an_abridged_judge_input_is_recorded_with_how_much_it_cost(
    node_worktree: Callable[..., Path], tmp_path: Path
) -> None:
    """US3-S1. The diff in the gap the last two stories opened, on the record.

    The worktree is US1's: larger than the attention budget, smaller than a
    raised refusal threshold, so it passes the check and reaches the judge
    abridged. Before US1 it had one possible outcome and it was FAIL; after US1
    it had a verdict and no way to tell that verdict from one taken on a diff
    read whole. This is that difference, written down.

    The amount is cross-examined rather than asserted alone: the refusal states
    its own count of the same assembly (`measured`), and `prepare_diff` is asked
    whether it truly abridged. If the record's numbers came from a different
    measurement than the abridger's, these three would part company here rather
    than in a stored row someone reads next week (plan trap 3).
    """
    worktree, base = between_the_limits(node_worktree)
    patch = worktree_diff(worktree, base_ref=base)

    check = check_output(
        worktree,
        WriteScope.WORKTREE,
        base_ref=base,
        diff_size_limit=RAISED_THRESHOLD,
    )
    record = check.abridgement

    assert check.passed is True, "between the two limits is judged, not refused"
    assert record is not None
    assert record.abridged is True
    assert record.limit_bytes == DIFF_INPUT_LIMIT, "the name, never a copy"
    assert record.total_bytes == measured(patch)
    assert record.over_limit_bytes == measured(patch) - DIFF_INPUT_LIMIT > 0
    assert prepare_diff(patch).truncated is record.abridged

    conn = connect(tmp_path / "verification.db")
    upsert_result(conn, stored_result(check))
    [loaded] = node_history(conn, EPIC_ID, "us3")

    assert loaded.verdict == OverallVerdict.PASS
    assert loaded.output_check.abridgement == record


# --- T017 / US3-S2: a whole diff says so, and silence is a third thing -------


def test_a_diff_the_judge_saw_whole_records_that_it_did(
    node_worktree: Callable[..., Path], tmp_path: Path
) -> None:
    """US3-S2 and plan trap 6. The absence of a flag must be a statement.

    An ordinary attempt's row now carries a positive claim — this diff cost N
    bytes against a budget of M, and nothing was elided — rather than the
    nothing that a row written before this story also carries. The two are
    distinguished in the companion test below; here the point is that the
    ordinary case is not silent.
    """
    worktree, base = ordinary_work(node_worktree)
    patch = worktree_diff(worktree, base_ref=base)

    check = check_output(worktree, WriteScope.WORKTREE, base_ref=base)
    record = check.abridgement

    assert check.passed is True
    assert record is not None, "a whole diff is a fact, not an omission"
    assert record.abridged is False
    assert record.limit_bytes == DIFF_INPUT_LIMIT
    assert record.total_bytes == measured(patch) < DIFF_INPUT_LIMIT
    assert record.over_limit_bytes == 0
    assert prepare_diff(patch).truncated is record.abridged

    conn = connect(tmp_path / "verification.db")
    upsert_result(conn, stored_result(check))
    [loaded] = node_history(conn, EPIC_ID, "us3")

    assert loaded.output_check.abridgement == record


def test_a_row_written_before_this_story_is_not_read_as_a_whole_diff(
    tmp_path: Path,
) -> None:
    """Plan trap 6, from the other side: nobody recorded is its own answer.

    Every row in `verification.db` today carries no abridgement key at all. Read
    back as "not abridged" they would become a claim the run never made — a
    verdict certified as taken on a whole diff by a version of the code that
    could not tell. `None` is that third state, and it is the one thing the
    ordinary case above may never be confused with.
    """
    conn = connect(tmp_path / "verification.db")
    passing = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
        abridgement=DiffAbridgement(total_bytes=4_096, limit_bytes=DIFF_INPUT_LIMIT),
    )
    row_id = upsert_result(conn, stored_result(passing))
    conn.execute(
        "UPDATE verification_results SET output_check = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "write_scope": "worktree",
                    "has_diff": True,
                    "expected_artifacts": [],
                    "artifacts_present": None,
                    "passed": True,
                    "hygiene_violations": [],
                    "size_refusal": None,
                }
            ),
            row_id,
        ),
    )
    conn.commit()

    [loaded] = node_history(conn, EPIC_ID, "us3")

    assert loaded.output_check.abridgement is None
    assert loaded.output_check != passing, "nobody recorded is not 'saw it whole'"


# --- T019 / FR-007: the field outlives the run ------------------------------


def test_the_abridgement_round_trips_through_the_evidence_store(
    tmp_path: Path,
) -> None:
    """FR-007, in the shape the size refusal already round-trips.

    The CLI reading below renders this from the stored row, so a field that did
    not survive the store would make an abridged PASS indistinguishable from a
    whole one the moment the process ended — which is the state this story
    exists to leave.

    The serialised shape is asserted beside `size_refusal`'s, not instead of it:
    the two are the same kind of evidence about the same measurement, and a
    second idiom for the second one is how a reader ends up believing they mean
    different things (T021).
    """
    conn = connect(tmp_path / "verification.db")
    abridged = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
        abridgement=DiffAbridgement(
            total_bytes=DIFF_INPUT_LIMIT * 2, limit_bytes=DIFF_INPUT_LIMIT
        ),
    )

    row_id = upsert_result(conn, stored_result(abridged))
    [loaded] = node_history(conn, EPIC_ID, "us3")

    assert loaded.output_check == abridged
    assert loaded.output_check.abridgement is not None
    assert loaded.output_check.abridgement.abridged is True

    [(stored,)] = conn.execute(
        "SELECT output_check FROM verification_results WHERE id = ?", (row_id,)
    ).fetchall()
    document = json.loads(stored)

    assert document["abridgement"] == {
        "total_bytes": DIFF_INPUT_LIMIT * 2,
        "limit_bytes": DIFF_INPUT_LIMIT,
    }
    assert document["size_refusal"] is None, "the pair it is written beside"


# --- T018 / US3-S3: the operator reads it without opening the store ---------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def invoke(*argv: str) -> Run:
    """Drive the real CLI entry point, capturing what an operator would see."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


def node_line(stdout: str, node_id: str) -> str:
    """The one printed line for a node, or an assertion naming what was there."""
    for line in stdout.splitlines():
        if line.startswith(f"{node_id} "):
            return line
    raise AssertionError(f"no line for {node_id!r} in:\n{stdout}")


@pytest.fixture
def seeded_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One epic, three PASSes, one of them taken on an abridged diff.

    The whole-diff PASS is the control: a reading that printed the abridgement
    and nothing else would look right here and tell an operator nothing, because
    the question they arrive with is which of two green rows to trust.
    """
    path = tmp_path / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))

    conn = connect(path)
    whole = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
        abridgement=DiffAbridgement(total_bytes=4_096, limit_bytes=DIFF_INPUT_LIMIT),
    )
    abridged = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
        abridgement=DiffAbridgement(
            total_bytes=DIFF_INPUT_LIMIT * 2, limit_bytes=DIFF_INPUT_LIMIT
        ),
    )
    legacy = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )
    upsert_result(conn, stored_result(whole, node_id="us1"))
    upsert_result(conn, stored_result(abridged, node_id="us2"))
    upsert_result(conn, stored_result(legacy, node_id="us3"))
    conn.close()
    return path


def test_the_cli_tells_an_abridged_pass_from_a_whole_one(seeded_store: Path) -> None:
    """US3-S3. Visible without reading the store, which is the whole ask.

    Two PASSes that differ only in what the judge was shown read identically
    everywhere an operator looks today — `ergane build status` reports the
    workflow's own state and never the evidence row. So this is the reading, and
    it says all three things: abridged with its numbers, whole, and the row that
    predates anyone recording either.
    """
    run = invoke("build", "attempts", EPIC_ID)

    assert run.code == 0, run.stderr
    assert "abridged" in node_line(run.stdout, "us2")
    assert str(DIFF_INPUT_LIMIT * 2) in node_line(run.stdout, "us2")
    assert str(DIFF_INPUT_LIMIT) in node_line(run.stdout, "us2")
    assert "whole" in node_line(run.stdout, "us1")
    assert "abridged" not in node_line(run.stdout, "us1")
    assert "not recorded" in node_line(run.stdout, "us3")
    # The verdict is on the line too: an abridged PASS is only legible as one
    # if the PASS is beside the abridgement.
    assert OverallVerdict.PASS.value in node_line(run.stdout, "us2")


def test_an_epic_with_nothing_recorded_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that has never seen the epic is an answer, not a failure.

    The same line an absent store gets: this verb is a read, and every honest
    answer to "what was recorded" — including none — is exit 0.
    """
    path = tmp_path / "absent.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))

    run = invoke("build", "attempts", EPIC_ID)

    assert run.code == 0, run.stderr
    assert EPIC_ID in run.stdout
    assert "no verification" in run.stdout
    assert not path.exists(), "a read may not create the store it reads"


def test_the_reading_takes_no_temporal_client(
    seeded_store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row outlives the workflow, and so must the way to read it.

    An epic whose execution has aged out of Temporal is exactly when an operator
    asks what its verdicts rested on. A reading that dialled the server would be
    unavailable at that moment, which is the argument `salvage` already makes
    for itself.
    """

    async def refuse() -> Any:
        raise AssertionError("`build attempts` must not open a Temporal client")

    monkeypatch.setattr("factory.cli.nouns._open_client", refuse)

    run = invoke("build", "attempts", EPIC_ID)

    assert run.code == 0, run.stderr
