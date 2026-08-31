"""A reader can tell two dispatches apart (117 US3).

US1 stopped the second dispatch from overwriting the first, so the rows are all
there now — and nothing that reads them says so. `node_history` ordered by
`(attempt, form)`, which lands a re-dispatched node's two attempt-one rows
adjacent and indistinguishable, and `ergane build attempts` printed five lines
that read as one build of five attempts rather than a build of three and a
build of two. "This story was built twice" was in the store and in nobody's
hands.

Four claims, and two of them are about what must *not* move:

- **Grouped, oldest first within each (US3-S1).** The reading is by dispatch
  first, so a build's attempts stay together.
- **The CLI states how many (US3-S2).** The count is the fact an operator
  arrives with; it is printed for a node that has more than one, beside the
  attempts of each.
- **A single dispatch reads exactly as it did (US3-S3, plan trap 8).** The
  control, and the reason the within-a-dispatch order stays `(attempt, form)`
  rather than becoming the row's stamps: `node_history` and `attempt_timings`
  are exported, quoted by retry prompts and read by at least one consumer
  outside this repository. The node verified in both forms is the shape that
  would have moved — a PHASE row finishes before the NODE row that verifies the
  same attempt, so ordering the rows of one dispatch by their stamps would have
  swapped a pair that has read the other way since 002 — so that node is what
  the control is built from.
- **By write time, not by row id (US3-S4, plan trap 7).** Ids are minted when a
  row is *inserted*; the stamps say when the attempt actually ran. The two part
  company whenever a recording lands late, and the whole reason this epic
  exists is a store where they had.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.env import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.verify.models import OverallVerdict, VerificationForm
from factory.verify.store import (
    attempt_timings,
    connect,
    dispatch_groups,
    epic_history,
    node_history,
    upsert_result,
)

# The CLI driver, borrowed rather than copied: it is the real entry point with
# stdout captured, and a second copy of it here would drift from the one the
# other reading tests hold `build attempts` to.
from tests.test_092_abridged_is_recorded import invoke
from tests.test_117_dispatch_scoped_rows import (
    EPIC,
    FIRST_DISPATCH,
    NODE,
    SECOND_DISPATCH,
    make_result,
)

#: What `node_history` ordered by before this story, kept here as executable
#: text rather than as a remembered fact: the control compares the reader's
#: sequence against this query's, run against the same rows.
PRE_US3_ORDER_SQL = (
    "SELECT attempt, form FROM verification_results "
    "WHERE epic_id = ? AND node_id = ? ORDER BY attempt, form"
)


def stamp(clock: str) -> str:
    """One ISO-8601 UTC minute of the day the measured case was recorded."""
    return f"2026-08-28T{clock}:00Z"


def recorded(
    store: sqlite3.Connection,
    *,
    attempt: int,
    dispatch: str,
    at: str,
    form: VerificationForm = VerificationForm.PHASE,
    **overrides: Any,
) -> int:
    """Record one attempt as if its verification finished at `at`.

    Returns the row id, which is what the id-order claim (US3-S4) is made
    against — nothing else in the store exposes the order rows were inserted in.
    """
    return upsert_result(
        store,
        make_result(
            attempt=attempt,
            dispatch=dispatch,
            form=form,
            started_at=stamp(at),
            finished_at=stamp(at),
            **overrides,
        ),
    )


@pytest.fixture
def store(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(connect(tmp_path / "verification.db")) as conn:
        yield conn


@pytest.fixture
def cli_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty store the CLI will read, pointed at by both env names."""
    path = tmp_path / "cli" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))
    return path


def two_dispatches(store: sqlite3.Connection) -> None:
    """A killed build of three attempts, then a re-dispatch of two.

    The measured case in miniature, and the shape every claim here is about.
    """
    for attempt, at in ((1, "10:03"), (2, "10:20"), (3, "10:41")):
        recorded(store, attempt=attempt, dispatch=FIRST_DISPATCH, at=at)
    for attempt, at in ((1, "11:02"), (2, "11:19")):
        recorded(store, attempt=attempt, dispatch=SECOND_DISPATCH, at=at)


# --- T017 [US3] (spec US3-S1) ------------------------------------------------


def test_two_dispatches_read_grouped_oldest_first_within_each(
    store: sqlite3.Connection,
) -> None:
    """US3-S1. A build's attempts stay together, and the builds stay in order.

    Ordering by attempt — what this reader did until now — interleaves the two
    dispatches at every attempt number they share, which is the reading that
    made a re-dispatched node look like one long build.
    """
    two_dispatches(store)

    history = node_history(store, EPIC, NODE)

    assert [(row.dispatch, row.attempt) for row in history] == [
        (FIRST_DISPATCH, 1),
        (FIRST_DISPATCH, 2),
        (FIRST_DISPATCH, 3),
        (SECOND_DISPATCH, 1),
        (SECOND_DISPATCH, 2),
    ]
    # Not a vacuous claim: the old order is a different sequence over the same
    # rows, and it is the one an interleaving reader would print.
    assert [row.attempt for row in history] != sorted(
        row.attempt for row in history
    )


def test_the_groups_are_the_dispatches_in_the_order_they_ran(
    store: sqlite3.Connection,
) -> None:
    """US3-S1. The grouping is offered, not left for each caller to redo.

    `dispatch_groups` splits the sequence a reader already returned rather than
    asking the store a second question — this story adds no query surface — so a
    caller that wants the builds rather than the attempts (the CLI, below) reads
    them without holding the ordering rule itself.
    """
    two_dispatches(store)

    groups = dispatch_groups(node_history(store, EPIC, NODE))

    assert [group.dispatch for group in groups] == [FIRST_DISPATCH, SECOND_DISPATCH]
    assert [len(group.results) for group in groups] == [3, 2]
    assert [row.attempt for row in groups[0].results] == [1, 2, 3]
    assert [row.attempt for row in groups[1].results] == [1, 2]


def test_the_epic_wide_readers_group_by_dispatch_too(
    store: sqlite3.Connection,
) -> None:
    """US3-S1 through the two readers that span an epic rather than a node.

    `epic_history` is `node_history` widened by one column of the same key and
    `attempt_timings` is its narrow sibling; a node that read grouped through
    one and interleaved through the others would make the answer depend on
    which verb the operator happened to type.
    """
    two_dispatches(store)
    recorded(store, attempt=1, dispatch=FIRST_DISPATCH, at="09:30", node_id="us0")

    assert [(row.node_id, row.dispatch, row.attempt) for row in
            epic_history(store, EPIC)] == [
        ("us0", FIRST_DISPATCH, 1),
        (NODE, FIRST_DISPATCH, 1),
        (NODE, FIRST_DISPATCH, 2),
        (NODE, FIRST_DISPATCH, 3),
        (NODE, SECOND_DISPATCH, 1),
        (NODE, SECOND_DISPATCH, 2),
    ]
    assert [(timing.node_id, timing.attempt) for timing in
            attempt_timings(store, EPIC)] == [
        ("us0", 1),
        (NODE, 1),
        (NODE, 2),
        (NODE, 3),
        (NODE, 1),
        (NODE, 2),
    ]


# --- T018 [US3] (spec US3-S2) ------------------------------------------------


def test_the_cli_states_how_many_dispatches_a_node_has_had(
    cli_store: Path,
) -> None:
    """US3-S2. The number is stated, not left to be counted off the lines.

    Five attempt lines under one node id is what the operator saw before, and
    it is indistinguishable from a node that took five attempts once. The count
    is printed beside the attempts of each dispatch, so which rows belong to
    which build is legible in the same reading.
    """
    with closing(connect(cli_store)) as store:
        two_dispatches(store)

    run = invoke("build", "attempts", EPIC)

    assert run.code == 0, run.stderr
    # How many there were, on each heading, where the operator is already
    # looking — and which dispatch ran the attempts beneath it.
    assert "dispatch 1 of 2" in run.stdout, run.stdout
    assert "dispatch 2 of 2" in run.stdout, run.stdout
    assert FIRST_DISPATCH in run.stdout and SECOND_DISPATCH in run.stdout
    # Both attempt-one rows are printed, each under its own dispatch's heading.
    lines = run.stdout.splitlines()
    headings = [index for index, line in enumerate(lines) if "dispatch" in line]
    assert len(headings) == 2
    assert sum(1 for line in lines if "attempt 1" in line) == 2
    assert headings[0] < headings[1] < max(
        index for index, line in enumerate(lines) if "attempt 1" in line
    )


# --- T019 [US3] (spec US3-S3, trap 8) ----------------------------------------


def one_dispatch(store: sqlite3.Connection) -> None:
    """One build, verified in both forms — the shape trap 8 is about.

    The NODE-form verification of attempt two finishes *after* the PHASE one:
    an explicit verifier node runs after the phase it re-checks. So a reader
    that ordered a dispatch's rows by their stamps would return this pair the
    other way round from every reader since 002, and every consumer of
    `node_history` would silently change its mind about which verdict came
    first.
    """
    recorded(store, attempt=1, dispatch=FIRST_DISPATCH, at="10:03")
    recorded(store, attempt=2, dispatch=FIRST_DISPATCH, at="10:20")
    recorded(
        store,
        attempt=2,
        dispatch=FIRST_DISPATCH,
        at="10:44",
        form=VerificationForm.NODE,
        verdict=OverallVerdict.FAIL,
    )


def test_a_single_dispatch_node_reads_exactly_as_it_did(
    store: sqlite3.Connection,
) -> None:
    """US3-S3, FR-009. Compared against the old ordering, not against a memory.

    `PRE_US3_ORDER_SQL` is the `ORDER BY` this reader carried before the story,
    run against the same rows: the control passes only while the two sequences
    are the same sequence.
    """
    one_dispatch(store)

    history = node_history(store, EPIC, NODE)
    before = [
        (int(row[0]), VerificationForm(row[1]))
        for row in store.execute(PRE_US3_ORDER_SQL, (EPIC, NODE))
    ]

    assert [(row.attempt, row.form) for row in history] == before
    assert before == [
        (1, VerificationForm.PHASE),
        (2, VerificationForm.NODE),
        (2, VerificationForm.PHASE),
    ], "the NODE form has sorted before the PHASE form of the same attempt since 002"
    assert [group.dispatch for group in dispatch_groups(history)] == [FIRST_DISPATCH]


def test_a_single_dispatch_reads_unchanged_through_the_epic_wide_readers(
    store: sqlite3.Connection,
) -> None:
    """US3-S3, trap 8. The exported readers, all three, over one dispatch."""
    one_dispatch(store)
    recorded(store, attempt=1, dispatch=FIRST_DISPATCH, at="09:30", node_id="us0")

    assert [(row.node_id, row.attempt, row.form) for row in epic_history(store, EPIC)] == [
        ("us0", 1, VerificationForm.PHASE),
        (NODE, 1, VerificationForm.PHASE),
        (NODE, 2, VerificationForm.NODE),
        (NODE, 2, VerificationForm.PHASE),
    ]
    assert [(timing.node_id, timing.attempt, timing.form) for timing in
            attempt_timings(store, EPIC)] == [
        ("us0", 1, VerificationForm.PHASE.value),
        (NODE, 1, VerificationForm.PHASE.value),
        (NODE, 2, VerificationForm.NODE.value),
        (NODE, 2, VerificationForm.PHASE.value),
    ]


def test_the_cli_says_nothing_about_dispatches_for_a_single_dispatch_node(
    cli_store: Path,
) -> None:
    """US3-S3, FR-009. One build prints the lines it printed before, and no more.

    The count answers a question a single-dispatch node does not raise, and a
    heading printed over every node would push the reading it exists to make
    legible — an abridged PASS, a contradicted gate — one line further down for
    every row in the store.
    """
    with closing(connect(cli_store)) as store:
        one_dispatch(store)

    run = invoke("build", "attempts", EPIC)

    assert run.code == 0, run.stderr
    assert "dispatch" not in run.stdout, run.stdout
    assert len(run.stdout.splitlines()) == 4, "the epic's line and one per attempt"


# --- T020 [US3] (spec US3-S4, trap 7) ----------------------------------------


def test_rows_are_ordered_by_when_they_were_written_not_by_row_id(
    store: sqlite3.Connection,
) -> None:
    """US3-S4, trap 7. Ids are insertion order; the stamps are what happened.

    The second dispatch's rows are inserted before the first dispatch's second
    attempt is — a recording that lands late, which is ordinary: the write is a
    Temporal activity and a delivery that failed once arrives whenever it
    succeeds. Read by id, the two builds interleave and the second appears to
    have run inside the first. Read by write time they come apart, which is the
    only ordering the epic's premise survives: surviving rows keep the ids they
    were minted with, so id order is not chronological order.
    """
    ids = {
        (FIRST_DISPATCH, 1): recorded(
            store, attempt=1, dispatch=FIRST_DISPATCH, at="10:03"
        ),
        (SECOND_DISPATCH, 1): recorded(
            store, attempt=1, dispatch=SECOND_DISPATCH, at="11:02"
        ),
        (SECOND_DISPATCH, 2): recorded(
            store, attempt=2, dispatch=SECOND_DISPATCH, at="11:19"
        ),
        (FIRST_DISPATCH, 2): recorded(
            store, attempt=2, dispatch=FIRST_DISPATCH, at="10:20"
        ),
    }
    assert sorted(ids.values()) == list(ids.values()), "ids ascend with insertion"

    history = node_history(store, EPIC, NODE)
    read = [(row.dispatch, row.attempt) for row in history]
    by_id = sorted(read, key=lambda key: ids[key])

    assert read == [
        (FIRST_DISPATCH, 1),
        (FIRST_DISPATCH, 2),
        (SECOND_DISPATCH, 1),
        (SECOND_DISPATCH, 2),
    ]
    assert by_id == [
        (FIRST_DISPATCH, 1),
        (SECOND_DISPATCH, 1),
        (SECOND_DISPATCH, 2),
        (FIRST_DISPATCH, 2),
    ], "id order interleaves the two builds — which is the reading being refused"
    assert read != by_id
    assert [group.dispatch for group in dispatch_groups(history)] == [
        FIRST_DISPATCH,
        SECOND_DISPATCH,
    ]


def test_two_dispatches_the_clock_cannot_separate_still_read_in_order(
    store: sqlite3.Connection,
) -> None:
    """US3-S4, the tie. `finished_at` is stamped to the second.

    Found by running the story's own demonstration: under a time-skipping
    workflow environment both dispatches record inside one second, every group
    ties on the clock, and whatever the ordering falls back to decides which
    build the operator is shown first. Falling back to the dispatch itself
    would decide it by comparing two uuids — the second dispatch read first
    here, for no reason but its leading digit. The insertion order of a group's
    first row is the only evidence left when the clock has none, and it is
    consulted last rather than first, which is the whole of trap 7.
    """
    tied = stamp("10:03")
    recorded(store, attempt=1, dispatch=SECOND_DISPATCH, at="10:03")
    recorded(store, attempt=1, dispatch=FIRST_DISPATCH, at="10:03")
    recorded(store, attempt=2, dispatch=SECOND_DISPATCH, at="10:03")

    history = node_history(store, EPIC, NODE)

    assert {row.finished_at for row in history} == {tied}, "the clock cannot tell"
    assert [(row.dispatch, row.attempt) for row in history] == [
        (SECOND_DISPATCH, 1),
        (SECOND_DISPATCH, 2),
        (FIRST_DISPATCH, 1),
    ], "the build whose first row was written first, even though its uuid sorts second"
