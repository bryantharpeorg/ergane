"""A re-dispatch adds to a node's history rather than replacing it (117 US1).

`verification_results` was keyed `(epic_id, node_id, attempt, form)`, so a node
dispatched a second time started again at attempt 1 and overwrote the first
dispatch's row for every attempt number it reached. The measured case spent nine
attempts and then six, and only the second dispatch's last three rows survived.

The fix is one column in the key, and the whole difficulty is that the upsert it
joins exists for a *good* reason: Temporal delivers `record_verification` at
least once, so a redelivered recording must still land on the row the first
delivery wrote. These tests hold both ends of that at once:

- **A re-dispatch adds (US1-S1).** Two dispatches' attempt-one rows both exist
  and can be told apart.
- **A retry still updates (US1-S2).** The control. The same attempt recorded
  twice within one dispatch is one row, and the same row.
- **An existing store migrates (US1-S3).** A UNIQUE constraint cannot be altered
  in place, so the migration rebuilds the table — and a rebuild is the one shape
  that can silently reorder columns. `_RESULT_COLUMNS` is documented as being in
  DDL order and read positionally, so a divergent order would return the wrong
  field for every row. The order is therefore compared against a freshly created
  store, column for column.
- **Old rows do not merge with the next dispatch (US1-S4).** Rows written before
  dispatches were distinguished belong to one unnamed dispatch. They carry a
  reserved value rather than NULL: SQLite treats NULLs as distinct in a UNIQUE
  index, which would give every historical row a key of its own and quietly
  disable the very idempotence US1-S2 is about.

The discriminator is the dispatch's workflow run, not a timestamp and not a
uuid minted per activity invocation. That is what makes US1-S2 hold at all: a
retried activity carries the run id of the workflow that scheduled it, so the
value is identical across redeliveries, and `criteria_sha256` — the other
candidate — was identical across all nine rows of the measured case and so can
discriminate nothing.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from temporalio.testing import WorkflowEnvironment

from factory.activities.verify_activities import (
    RecordVerificationInput,
    record_verification,
)
from factory.env import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.verify.models import (
    UNKNOWN_DISPATCH,
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.verify.store import connect, node_history, upsert_result

EPIC = "117-the-record-outlives-the-build"
NODE = "us1"

#: Two workflow runs of the same node — what `build reset` and a second
#: `build start` produce. Shaped like the run ids Temporal mints, because that
#: is the identity the column carries.
FIRST_DISPATCH = "0f5b1c9e-1111-4a0a-9c3d-000000000001"
SECOND_DISPATCH = "0f5b1c9e-2222-4a0a-9c3d-000000000002"


def make_result(
    *,
    attempt: int = 1,
    dispatch: str = FIRST_DISPATCH,
    verdict: OverallVerdict = OverallVerdict.PASS,
    **overrides: Any,
) -> VerificationResult:
    """One attempt's evidence; override only what a test is about."""
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "node_id": NODE,
        "attempt": attempt,
        "form": VerificationForm.PHASE,
        "gate_results": [
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.0,
                output_tail="1 passed",
            )
        ],
        "output_check": OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        "judge": None,
        "verdict": verdict,
        "judge_unavailable": False,
        "criteria_drift": False,
        # The other candidate discriminator, held constant on purpose: it was
        # identical across all nine rows of the measured case.
        "criteria_sha256": "a" * 64,
        "spec_ref": f"{EPIC}/US1",
        "started_at": "2026-08-28T10:00:00Z",
        "finished_at": "2026-08-28T10:03:00Z",
        "dispatch": dispatch,
    }
    fields.update(overrides)
    return VerificationResult(**fields)


def row_count(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM verification_results").fetchone()[0]
    )


def columns_of(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    """Every column of `verification_results`, in the order the table declares.

    Name, declared type, NOT NULL, default and primary-key flag — the whole
    `PRAGMA table_info` row minus its ordinal, so two stores agree on shape as
    well as on sequence.
    """
    return [
        tuple(row[1:])
        for row in conn.execute("PRAGMA table_info(verification_results)")
    ]


# --- T001 [US1] (spec US1-S1) ------------------------------------------------


def test_a_second_dispatch_adds_rows_rather_than_replacing_the_first(
    tmp_path: Path,
) -> None:
    """FR-001: the evidence of a killed dispatch survives the next one.

    Three attempts, then a re-dispatch that records its own attempt one. Before
    the dispatch joined the key this left three rows, the first dispatch's
    attempt one silently replaced — which is exactly the row a post-mortem of a
    killed build starts from.
    """
    with closing(connect(tmp_path / "verification.db")) as store:
        for attempt in (1, 2, 3):
            upsert_result(store, make_result(attempt=attempt))
        upsert_result(
            store,
            make_result(
                attempt=1,
                dispatch=SECOND_DISPATCH,
                verdict=OverallVerdict.FAIL,
            ),
        )

        assert row_count(store) == 4
        history = node_history(store, EPIC, NODE)

        first_attempts = [row for row in history if row.attempt == 1]
        # Both exist...
        assert len(first_attempts) == 2
        # ...and are distinguishable, by the dispatch and by what they record.
        assert {row.dispatch for row in first_attempts} == {
            FIRST_DISPATCH,
            SECOND_DISPATCH,
        }
        assert {(row.dispatch, row.verdict) for row in first_attempts} == {
            (FIRST_DISPATCH, OverallVerdict.PASS),
            (SECOND_DISPATCH, OverallVerdict.FAIL),
        }
        # The first dispatch's later attempts are untouched by the second.
        assert sorted(
            row.attempt for row in history if row.dispatch == FIRST_DISPATCH
        ) == [1, 2, 3]


# --- T002 [US1] (spec US1-S2) ------------------------------------------------


def test_a_repeated_recording_within_one_dispatch_updates_the_row(
    tmp_path: Path,
) -> None:
    """FR-002, the idempotence control. At-least-once delivery must not fan out.

    This is the property the upsert exists for, and the one a naive fix — a new
    row per recording, or a NULL dispatch SQLite reads as always-distinct —
    would regress without failing anything else here.
    """
    with closing(connect(tmp_path / "verification.db")) as store:
        first = upsert_result(store, make_result(verdict=OverallVerdict.PASS))
        second = upsert_result(store, make_result(verdict=OverallVerdict.FAIL))

        assert row_count(store) == 1
        # The same row, and the second recording is the current one.
        assert first == second
        (row,) = node_history(store, EPIC, NODE)
        assert row.verdict == OverallVerdict.FAIL
        assert row.dispatch == FIRST_DISPATCH


#: `verification_results` as every store written before this story has it: no
#: `dispatch` column, and — since a store two features older is the ordinary
#: case rather than the exotic one — no `base_ref` or `gate_contradictions`
#: either, so the additive migrations run ahead of the rebuild here the way
#: they will in the field. Written out rather than read from git: the migration
#: is tested against a shape, not against whatever the DDL says today.
_PRE_117_RESULTS_DDL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version) VALUES (7);

CREATE TABLE verification_results (
    id                INTEGER PRIMARY KEY,
    epic_id           TEXT    NOT NULL CHECK (epic_id <> ''),
    node_id           TEXT    NOT NULL CHECK (node_id <> ''),
    attempt           INTEGER NOT NULL CHECK (attempt >= 1),
    form              TEXT    NOT NULL CHECK (form IN ('PHASE', 'NODE')),
    verdict           TEXT    NOT NULL CHECK (verdict IN ('PASS', 'FAIL')),
    gate_results      TEXT    NOT NULL,
    output_check      TEXT    NOT NULL,
    judge_verdict     TEXT,
    judge_unavailable INTEGER NOT NULL DEFAULT 0 CHECK (judge_unavailable IN (0, 1)),
    criteria_drift    INTEGER NOT NULL DEFAULT 0 CHECK (criteria_drift IN (0, 1)),
    criteria_sha256   TEXT    NOT NULL,
    spec_ref          TEXT    NOT NULL CHECK (spec_ref <> ''),
    started_at        TEXT    NOT NULL,
    finished_at       TEXT    NOT NULL,
    provenance        TEXT,
    loop_digest       TEXT,
    loop_summary      TEXT,
    UNIQUE (epic_id, node_id, attempt, form)
);

CREATE INDEX idx_vr_epic    ON verification_results (epic_id);
CREATE INDEX idx_vr_node    ON verification_results (epic_id, node_id);
CREATE INDEX idx_vr_specref ON verification_results (spec_ref);
CREATE INDEX idx_vr_verdict ON verification_results (verdict);

INSERT INTO verification_results (
    epic_id, node_id, attempt, form, verdict, gate_results, output_check,
    criteria_sha256, spec_ref, started_at, finished_at
) VALUES (
    '117-the-record-outlives-the-build', 'us1', 1, 'PHASE', 'FAIL', '[]',
    '{"write_scope":"worktree","has_diff":true,"expected_artifacts":[],"artifacts_present":null,"passed":true}',
    'aaaa', 'pre-117/US1', '2026-08-01T10:00:00Z', '2026-08-01T10:03:00Z'
);
"""


def legacy_store(tmp_path: Path) -> Path:
    """A store written before the dispatch was distinguished, with one row."""
    db_path = tmp_path / "verification.db"
    with closing(sqlite3.connect(db_path)) as raw:
        raw.executescript(_PRE_117_RESULTS_DDL)
        raw.commit()
    return db_path


# --- T003 [US1] (spec US1-S3, trap 2) ----------------------------------------


def test_a_pre_dispatch_store_migrates_to_a_fresh_stores_column_order(
    tmp_path: Path,
) -> None:
    """FR-003: migrated and fresh must agree column for column, order included.

    SQLite cannot drop a UNIQUE constraint, so the migration rebuilds the
    table — and a rebuild is the one migration shape that can put the columns
    back in a different order. `_RESULT_COLUMNS` is read positionally, so a
    divergent order does not raise: it hands every field of every row to the
    wrong attribute. The two orders are therefore compared directly.
    """
    db_path = legacy_store(tmp_path)

    with closing(connect(db_path)) as migrated:
        with closing(connect(tmp_path / "fresh" / "verification.db")) as fresh:
            assert columns_of(migrated) == columns_of(fresh)
        # And `dispatch` sits where an `ALTER TABLE ADD COLUMN` on the store of
        # its day would have put it: after every column that predates it, and
        # before every column added since. 117-US2 appended three more behind
        # it, which is why this is a position rather than the tail.
        order = [column[0] for column in columns_of(migrated)]
        assert order[-4:] == ["dispatch", "persona", "model_alias", "route"]
        name, _type, notnull, default, _pk = columns_of(migrated)[-4]
        assert name == "dispatch"
        # The DDL is a verbatim copy of the published contract, so its reserved
        # value is a literal; this is what stops it drifting from the constant
        # the migration and the reader use.
        assert default == f"'{UNKNOWN_DISPATCH}'"
        assert notnull == 1

        # The row that was there is still there, and still says what it said.
        (old,) = node_history(migrated, EPIC, NODE)
        assert old.verdict == OverallVerdict.FAIL
        assert old.spec_ref == "pre-117/US1"
        assert old.attempt == 1

        # The indexes the canonical queries read through survived the rebuild.
        names = {
            row[1] for row in migrated.execute("PRAGMA index_list(verification_results)")
        }
        assert {"idx_vr_epic", "idx_vr_node", "idx_vr_specref", "idx_vr_verdict"} <= names

    # Opening it again is a no-op: the migration is keyed off the column, so a
    # store that already has it is not rebuilt a second time.
    with closing(connect(db_path)) as reopened:
        assert row_count(reopened) == 1
        assert [column[0] for column in columns_of(reopened)][-4] == "dispatch"


# --- T004 [US1] (spec US1-S4, trap 3) ----------------------------------------


def test_migrated_rows_carry_a_dispatch_a_later_one_cannot_merge_into(
    tmp_path: Path,
) -> None:
    """FR-004: the rows that predate dispatches are one unnamed dispatch.

    They cannot be left NULL — SQLite treats NULLs as distinct in a UNIQUE
    index, so every historical row would key uniquely on itself and a
    redelivered recording of one would append rather than update. They get one
    reserved value instead, which no workflow run can produce, so the next
    dispatch of the same node lands beside them rather than on top of them.
    """
    db_path = legacy_store(tmp_path)

    with closing(connect(db_path)) as store:
        (old,) = node_history(store, EPIC, NODE)
        assert old.dispatch == UNKNOWN_DISPATCH
        assert old.dispatch is not None

        # A dispatch after the migration records the same attempt number.
        upsert_result(
            store,
            make_result(
                attempt=1, dispatch=SECOND_DISPATCH, verdict=OverallVerdict.PASS
            ),
        )

        assert row_count(store) == 2
        history = node_history(store, EPIC, NODE)
        assert {row.dispatch for row in history} == {UNKNOWN_DISPATCH, SECOND_DISPATCH}
        # The historical row was not merged into, overwritten or renumbered.
        (survivor,) = [row for row in history if row.dispatch == UNKNOWN_DISPATCH]
        assert survivor.verdict == OverallVerdict.FAIL
        assert survivor.spec_ref == "pre-117/US1"


# --- T005 [US1] (FR-002, trap 4) ---------------------------------------------


async def test_a_redelivered_recording_activity_writes_one_row(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The discriminator is carried in, never minted at recording time.

    Temporal delivers `record_verification` at least once, and its retries
    arrive with the same request. An activity that stamped a fresh value —
    a timestamp, a uuid — would write a new row per delivery and the upsert
    would protect nothing. Calling it twice with one request is that
    redelivery, and one row is the answer.
    """
    db_path = tmp_path / "verification.db"
    monkeypatch.delenv(FACTORY_VERIFICATION_DB_PATH_ENV, raising=False)
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(db_path))
    request = RecordVerificationInput(result=make_result(attempt=2))

    first = await record_verification(request)
    second = await record_verification(request)

    assert first.row_id == second.row_id
    with closing(connect(db_path)) as store:
        assert row_count(store) == 1
        (row,) = node_history(store, EPIC, NODE)
        assert row.dispatch == FIRST_DISPATCH


# --- T009 [US1] (FR-001, trap 4): the identity comes from the workflow run ----


async def test_the_recorded_dispatch_is_the_workflow_run(tmp_path: Path) -> None:
    """The value the row carries is the dispatch's own run, end to end.

    The store cannot check this and neither can the activity: whether the
    column discriminates dispatches at all is decided by *what the interpreter
    puts in it*, and only a run of the interpreter can say. The run id is the
    one identity a Temporal retry preserves and a re-dispatch does not.
    """
    from tests.test_interpreter import ScriptedWorld, passing, start_epic

    env = await WorkflowEnvironment.start_time_skipping()
    try:
        script = ScriptedWorld(
            {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
        async with start_epic(env, script) as handle:
            await handle.result()
            run_id = (await handle.describe()).run_id

        assert script.records
        assert {row.dispatch for row in script.records} == {run_id}
        assert UNKNOWN_DISPATCH not in {row.dispatch for row in script.records}
    finally:
        await env.shutdown()
