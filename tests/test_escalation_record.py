"""The record a workflow writes at every transition, and the two ways it leaked.

041-US2, US2-S7 / FR-014. Both defects landed together in
`025-ci-red-recovery/us2` (59842eb) and both live in the exact files this story
writes rows from:

1. **`check_evidence` was silently dropped on read.** It reached the outgoing
   Telegram message but never the store: `_ESCALATION_COLUMNS` had no such
   column and `_escalation_from_row` never passed one, so every read-back got
   the default `()` and an operator reading the row back saw an escalation with
   no evidence at all. Filed as
   `verify/escalation-check-evidence-is-dropped-on-store-read`.
2. **The annotation named a module the file never imports.**
   `factory/verify/models.py` annotated the field
   `tuple["factory.mergequeue.models.CheckFailure", ...]` while importing no
   `factory` name at all; `from __future__ import annotations` hid it at
   definition time, so `typing.get_type_hints(EscalationRecord)` raised
   `NameError` the day anything introspected it. Filed as
   `verify/escalation-record-annotation-cannot-resolve`.

A workflow that writes a row at every terminal transition (FR-013) should not be
writing rows that lose fields, which is why FR-014 closes both here rather than
later.

What would make these pass if the production code did nothing: nothing. The
round-trip test compares what came out of SQLite against what went in, and the
annotation test calls `get_type_hints` — the exact call that raised. The
migration test builds a store in the *pre-041* shape by hand and opens it with
the shipped `connect()`, so a schema change that only works on a fresh database
— which is every live store the factory has — fails here.

Runtime evidence is pasted verbatim at the bottom of this file (constitution
VIII / D-037).
"""

from __future__ import annotations

import sqlite3
import typing
from contextlib import closing
from pathlib import Path

import pytest

from factory.mergequeue.models import CheckFailure
from factory.notify.messages import escalation_message
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord

EVIDENCE = (
    CheckFailure(
        name="build (merge_group)",
        url="https://github.com/tharpe/ergane/actions/runs/12345",
        log_tail="E   assert 2 == 3\nFAILED tests/test_ladder.py::test_budget",
        note="",
    ),
    CheckFailure(
        name="lint",
        url="https://github.com/tharpe/ergane/actions/runs/12346",
        log_tail="",
        note="log not fetched: the run had already been deleted",
    ),
)


def an_escalation(**overrides: object) -> EscalationRecord:
    fields: dict[str, object] = {
        "escalation_id": "0123456789ab",
        "workflow_id": "0123456789ab",
        "epic_id": "041-escalation-workflow",
        "node_id": "us2",
        "choices": [EscalationChoice.RETRY, EscalationChoice.KILL],
        "history_summary": "attempt 3 FAIL (merge-queue checks)",
        "sent_at": "2026-08-16T09:00:00Z",
        "expires_at": "2026-08-16T10:00:00Z",
        "delivered": True,
        "check_evidence": EVIDENCE,
    }
    fields.update(overrides)
    return EscalationRecord(**fields)  # type: ignore[arg-type]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "verification.db"


# ============================================================================
# T012a — US2-S7: the annotation resolves
# ============================================================================


def test_every_annotation_on_the_record_resolves() -> None:
    """FR-014: `typing.get_type_hints(EscalationRecord)` does not raise.

    It did until this story: the annotation named
    `factory.mergequeue.models.CheckFailure` in a module that imported no
    `factory` name, and `from __future__ import annotations` deferred the
    lookup until something introspected it. Anything that does — a schema
    generator, a serializer, `dataclasses.fields` with types resolved, a
    docs build — got `NameError` instead of a type.
    """
    hints = typing.get_type_hints(EscalationRecord)

    assert hints["check_evidence"] == tuple[CheckFailure, ...]
    assert hints["escalation_id"] is str


# ============================================================================
# T012a — US2-S7: the evidence survives the round trip
# ============================================================================


def test_check_evidence_survives_the_store_round_trip(db_path: Path) -> None:
    """FR-014: what went in comes back out, evidence included."""
    record = an_escalation()

    with closing(store.connect(db_path)) as conn:
        store.insert_escalation(conn, record)
        read_back = store.get_escalation(conn, record.escalation_id)
        pending = store.pending_escalations(conn)

    assert read_back is not None
    assert read_back.check_evidence == EVIDENCE
    assert read_back == record

    # The read-back is not merely equal, it is *usable*: the operator-facing
    # message a re-render produces is byte-identical, which is the thing the
    # dropped column actually cost.
    assert escalation_message(read_back) == escalation_message(record)

    # And the pending listing carries it too, since that is what a recovery
    # sweep or a list surface would read.
    assert [item.check_evidence for item in pending] == [EVIDENCE]


def test_an_escalation_with_no_evidence_round_trips_as_empty(db_path: Path) -> None:
    """The common case stays the common case: no evidence is `()`, not `None`."""
    record = an_escalation(check_evidence=())

    with closing(store.connect(db_path)) as conn:
        store.insert_escalation(conn, record)
        read_back = store.get_escalation(conn, record.escalation_id)

    assert read_back is not None
    assert read_back.check_evidence == ()


# ============================================================================
# T014a — the live store is a store that already exists
# ============================================================================

#: The escalations table exactly as every store written before 041-US2 has it:
#: no `check_evidence` column. Written out here rather than read from git so the
#: migration is tested against a shape, not against whatever the file says today.
_PRE_041_ESCALATIONS_DDL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version) VALUES (2);

CREATE TABLE escalations (
    escalation_id  TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL,
    epic_id        TEXT NOT NULL,
    node_id        TEXT NOT NULL,
    choices        TEXT NOT NULL,
    history_summary TEXT NOT NULL,
    delivered      INTEGER NOT NULL DEFAULT 0 CHECK (delivered IN (0, 1)),
    sent_at        TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    resolution     TEXT CHECK (resolution IN ('RETRY', 'KILL', 'PAUSE_EPIC', 'EXPIRED')),
    resolved_at    TEXT,
    resolved_via   TEXT CHECK (resolved_via IN ('BUTTON', 'TIMEOUT')),
    CHECK ((resolution IS NULL) = (resolved_at IS NULL))
);

INSERT INTO escalations (
    escalation_id, workflow_id, epic_id, node_id, choices, history_summary,
    delivered, sent_at, expires_at
) VALUES (
    'deadbeef0001', 'epic-027-gate-suite-fake-time', '027-gate-suite-fake-time',
    'us2', '["RETRY", "KILL"]', 'a row written before this story existed',
    1, '2026-08-06T14:55:00Z', '2026-08-06T15:55:00Z'
);
"""


def test_a_store_written_before_this_story_migrates_in_place(db_path: Path) -> None:
    """FR-014: the column arrives on the stores that already exist.

    Every `.factory/verification.db` in the world predates this column, and the
    first thing the factory does with one is `SELECT` the escalation columns by
    name. A migration that only ran on a fresh database would leave the running
    deployment answering `no such column: check_evidence` on every escalation it
    tried to read — including the fourteen pending ones.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_PRE_041_ESCALATIONS_DDL)
        conn.commit()
    finally:
        conn.close()

    with closing(store.connect(db_path)) as migrated:
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(escalations)")
        }
        assert "check_evidence" in columns

        # The row that was already there reads back, with no evidence and
        # nothing else lost.
        old = store.get_escalation(migrated, "deadbeef0001")
        assert old is not None
        assert old.check_evidence == ()
        assert old.history_summary == "a row written before this story existed"
        assert old.resolution is None

        # 068-US2: the rebuilt table admits the fourth button and is still
        # closed against what is not an answer. A store whose CHECK predates
        # `KILL_EPIC` rejects the settling write, so this is what makes the
        # button do anything at all.
        migrated.execute(
            "UPDATE escalations SET resolution = 'KILL_EPIC', "
            "resolved_at = '2026-08-20T11:05:00Z' WHERE escalation_id = ?",
            ("deadbeef0001",),
        )
        assert store.get_escalation(migrated, "deadbeef0001").resolution == "KILL_EPIC"
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute("UPDATE escalations SET resolution = 'KILL_FACTORY'")

        # And a new row round-trips its evidence in the migrated store.
        store.insert_escalation(migrated, an_escalation())
        fresh = store.get_escalation(migrated, "0123456789ab")
        assert fresh is not None
        assert fresh.check_evidence == EVIDENCE

        version = migrated.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == store.SCHEMA_VERSION


def test_the_schema_version_records_the_new_shape(db_path: Path) -> None:
    """A shape change the store can tell a reader about (store.py's own rule)."""
    with closing(store.connect(db_path)) as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_version")]

    # 10 since 116-US3 added `verification_results.gate_contradictions`; 9 was
    # 095-US2 adding `escalations.default_choice`; 8 was 118-US2 adding
    # `verification_results.base_ref`; 7 was 068-US2 widening
    # `escalations.resolution` to admit `KILL_EPIC`.
    assert store.SCHEMA_VERSION == 10
    assert versions == [store.SCHEMA_VERSION]


# ============================================================================
# EVIDENCE — pasted verbatim (constitution VIII / D-037)
# ============================================================================

RED_BEFORE_THE_IMPLEMENTATION = """
Both defects reproduced against the tree as it stood before this story, exactly
where the plan said they were (trap 12).

$ uv run pytest tests/test_escalation_record.py -q --tb=line
FF.FF                                                                    [100%]
=================================== FAILURES ===================================
E   NameError: name 'factory' is not defined
<string>:1: NameError: name 'factory' is not defined
E   AssertionError: assert () == (CheckFailure...een deleted'))

      Right contains 2 more items, first extra item: CheckFailure(name='build (merge_group)', url='https://github.com/tharpe/ergane/actions/runs/12345', log_tail='E   assert 2 == 3\\nFAILED tests/test_ladder.py::test_budget', note='')
      Use -v to get more diff
tests/test_escalation_record.py:124: AssertionError: assert () == (CheckFailure...een deleted'))
E   AssertionError: assert 'check_evidence' in {'choices', 'delivered', 'epic_id', 'escalation_id', 'expires_at', 'history_summary', ...}
tests/test_escalation_record.py:207: AssertionError: assert 'check_evidence' in {'choices', 'delivered', 'epic_id', 'escalation_id', 'expires_at', 'history_summary', ...}
E   assert 2 == 3
     +  where 2 = store.SCHEMA_VERSION
tests/test_escalation_record.py:232: assert 2 == 3
=========================== short test summary info ============================
FAILED tests/test_escalation_record.py::test_every_annotation_on_the_record_resolves
FAILED tests/test_escalation_record.py::test_check_evidence_survives_the_store_round_trip
FAILED tests/test_escalation_record.py::test_a_store_written_before_this_story_migrates_in_place
FAILED tests/test_escalation_record.py::test_the_schema_version_records_the_new_shape
4 failed, 1 passed in 0.37s

The `NameError` above is the second defect in full: `get_type_hints` evaluating
`tuple["factory.mergequeue.models.CheckFailure", ...]` in a module whose globals
hold no name `factory`.
"""

MUTATIONS = """
The red run above is already the strongest evidence these tests can fail: it is
the production code doing nothing, because before this story it did nothing.
Two further mutations pin the halves separately.

--- 1. the read drops the column again ---------------------------------------
    `_escalation_from_row`: `check_evidence=()` instead of decoding the column.
    The write still happens, so the data is in SQLite and the reader throws it
    away — which is exactly the shape of the original defect.

$ uv run pytest tests/test_escalation_record.py -q --tb=line
.F.F.                                                                    [100%]
E   AssertionError: assert () == (CheckFailure...een deleted'))
      Right contains 2 more items, first extra item: CheckFailure(name='build (merge_group)', ...)
.../tests/test_escalation_record.py:124: AssertionError
E   AssertionError: assert () == (CheckFailure...een deleted'))
.../tests/test_escalation_record.py:221: AssertionError
FAILED tests/test_escalation_record.py::test_check_evidence_survives_the_store_round_trip
FAILED tests/test_escalation_record.py::test_a_store_written_before_this_story_migrates_in_place
2 failed, 3 passed in 0.35s

--- 2. the migration is removed ----------------------------------------------
    `_migrate`: `pass` instead of the `ALTER TABLE`. A fresh store still works
    — the DDL creates the column — so only the store that already exists
    breaks, which is every store the factory has.

$ uv run pytest tests/test_escalation_record.py -q --tb=line
...F.                                                                    [100%]
E   AssertionError: assert 'check_evidence' in {'choices', 'delivered', 'epic_id', 'escalation_id', 'expires_at', 'history_summary', ...}
.../tests/test_escalation_record.py:207: AssertionError
FAILED tests/test_escalation_record.py::test_a_store_written_before_this_story_migrates_in_place
1 failed, 4 passed in 0.28s

Note which tests survive mutation 2 and which does not: everything that builds
its store from scratch passes. A suite without the pre-041 fixture would have
been green on a change that breaks the running deployment.
"""


FINAL_SUITE = """
$ uv run pytest -q
2673 passed, 44 skipped, 4 warnings in 290.23s (0:04:50)
"""
