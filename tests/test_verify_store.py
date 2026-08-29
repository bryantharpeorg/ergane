"""The evidence store's shape on disk, and the state machine it enforces.

`.factory/verification.db` is a published surface the same way the 001 ledger is:
`contracts/verification-store.sql` is what an operator opens `sqlite3` against,
what escalation summaries read, and what a future operations UI will query. So
the schema tests here compare what `factory.verify.store.connect` creates against
*that file applied to a scratch database* — not against a copy of the DDL pasted
into this module, which would only prove the implementation agrees with itself.

Four properties carry the weight:

- **WAL, with a busy timeout.** Verifications for sibling nodes finish
  concurrently on the one host that owns `.factory/`; rollback-journal mode would
  serialize them into `database is locked` on the path that records evidence.
  Same R6 pattern as the ledger, deliberately.
- **The upsert key is `(epic_id, node_id, attempt, form)`.** Temporal runs
  `record_verification` at least once, so a re-run must land on the first run's
  row — "one row per attempt per form" is a property of the schema, not of the
  caller's care. `form` is in the key because one attempt can be verified both as
  a node's built-in phase and by an explicit verifier node (FR-002).
- **An escalation makes exactly one terminal transition.** `resolved` xor
  `expired`: a button press that arrives after the hour is up finds a row it
  cannot move, and the timeout path cannot overwrite an operator's decision.
  Later attempts are no-ops, not errors and not overwrites — the bridge and the
  workflow race by design (R11/R12).
- **Evidence round-trips.** Gate results, the output check and the judge verdict
  are stored as JSON text; `node_history` must hand them back as the same
  dataclasses, because the retry prompt quotes `output_tail` and judge feedback
  verbatim (FR-006, SC-004) and the escalation message needs the full history
  (SC-005). A lossy write would only surface much later, in a prompt.

`judge_verdict` is the one nullable evidence column: NULL means the judge never
ran — gates failed under cheapest-first, or the node has no scenarios — and that
is a different fact from "ran and said nothing", which is a stored verdict with
outcome FAIL.

Written before `factory/verify/store.py` exists (T005 precedes T006): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.verify.models import (
    DEFAULT_LOOP_DIGEST,
    DEFAULT_LOOP_SUMMARY,
    EscalationChoice,
    EscalationRecord,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    QuestionRecord,
    VerificationConfig,
    VerificationForm,
    VerificationResult,
    compose_result,
)
from factory.verify.store import (
    ANSWERED,
    BUSY_TIMEOUT_MS,
    SCHEMA_VERSION,
    connect,
    expire_escalation,
    find_pending_question_by_attempt,
    get_escalation,
    insert_escalation,
    insert_question,
    node_history,
    pending_escalations,
    resolve_escalation,
    resolve_question,
    upsert_result,
)

#: The published DDL. The store's schema is compared against this file rather
#: than against a duplicate of it kept in the test.
CONTRACT_DDL = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "002-verification-gating"
    / "contracts"
    / "verification-store.sql"
)

#: (name, declared type, NOT NULL, primary key) per contracts/verification-store.sql.
EXPECTED_RESULT_COLUMNS: list[tuple[str, str, int, int]] = [
    ("id", "INTEGER", 0, 1),
    ("epic_id", "TEXT", 1, 0),
    ("node_id", "TEXT", 1, 0),
    ("attempt", "INTEGER", 1, 0),
    ("form", "TEXT", 1, 0),
    ("verdict", "TEXT", 1, 0),
    ("gate_results", "TEXT", 1, 0),
    ("output_check", "TEXT", 1, 0),
    ("judge_verdict", "TEXT", 0, 0),
    ("judge_unavailable", "INTEGER", 1, 0),
    ("criteria_drift", "INTEGER", 1, 0),
    ("criteria_sha256", "TEXT", 1, 0),
    ("spec_ref", "TEXT", 1, 0),
    ("started_at", "TEXT", 1, 0),
    ("finished_at", "TEXT", 1, 0),
    # 035-US1: non-NULL for externally-completed work, otherwise NULL.
    ("provenance", "TEXT", 0, 0),
    # 023-US4: loop configuration carried with every verdict; NULL for pre-023 rows.
    ("loop_digest", "TEXT", 0, 0),
    ("loop_summary", "TEXT", 0, 0),
]

EXPECTED_ESCALATION_COLUMNS: list[tuple[str, str, int, int]] = [
    ("escalation_id", "TEXT", 0, 1),
    ("workflow_id", "TEXT", 1, 0),
    ("epic_id", "TEXT", 1, 0),
    ("node_id", "TEXT", 1, 0),
    ("choices", "TEXT", 1, 0),
    ("history_summary", "TEXT", 1, 0),
    ("delivered", "INTEGER", 1, 0),
    ("sent_at", "TEXT", 1, 0),
    ("expires_at", "TEXT", 1, 0),
    ("resolution", "TEXT", 0, 0),
    ("resolved_at", "TEXT", 0, 0),
    ("resolved_via", "TEXT", 0, 0),
    # 041-US2 (schema 3): the failing checks the escalation was raised over.
    # Last, because a store written before this version gets the column by
    # ALTER TABLE ADD COLUMN and that appends — a migrated store and a fresh
    # one have to agree column for column, order included.
    ("check_evidence", "TEXT", 1, 0),
]

EXPECTED_INDEXES = {
    "idx_vr_epic",
    "idx_vr_node",
    "idx_vr_specref",
    "idx_vr_verdict",
    "idx_esc_pending",
    "idx_esc_node",
}


def make_gate(**overrides: Any) -> GateResult:
    fields: dict[str, Any] = {
        "name": "test",
        "command": "uv run pytest -q",
        "status": GateStatus.PASS,
        "exit_code": 0,
        "duration_s": 12.5,
        "output_tail": "42 passed in 12.5s",
    }
    fields.update(overrides)
    return GateResult(**fields)


def make_judge(**overrides: Any) -> JudgeVerdict:
    fields: dict[str, Any] = {
        "outcome": JudgeOutcome.PASS,
        "findings": [
            JudgeScenarioFinding(
                scenario="US1-S1", passed=True, reasoning="ledger row asserted"
            ),
            JudgeScenarioFinding(
                scenario="US1-S2", passed=True, reasoning="rollup covered"
            ),
        ],
        "feedback": "all scenarios covered",
        "judge_attempt": 1,
        "truncated_input": False,
        "model_alias": "judge",
    }
    fields.update(overrides)
    return JudgeVerdict(**fields)


def make_result(**overrides: Any) -> VerificationResult:
    """A passing node verification; override only what a test is about."""
    fields: dict[str, Any] = {
        "epic_id": "epic-7",
        "node_id": "node-3",
        "attempt": 2,
        "form": VerificationForm.PHASE,
        "gate_results": [make_gate(), make_gate(name="lint", command="ruff check .")],
        "output_check": OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        "judge": make_judge(),
        "verdict": OverallVerdict.PASS,
        "judge_unavailable": False,
        "criteria_drift": False,
        "criteria_sha256": "a" * 64,
        "spec_ref": "002-verification-gating/US1",
        "started_at": "2026-08-04T10:00:00Z",
        "finished_at": "2026-08-04T10:03:00Z",
    }
    fields.update(overrides)
    return VerificationResult(**fields)


def make_escalation(**overrides: Any) -> EscalationRecord:
    fields: dict[str, Any] = {
        "escalation_id": "0123456789ab",
        "workflow_id": "epic-7-interpreter",
        "epic_id": "epic-7",
        "node_id": "node-3",
        "choices": [
            EscalationChoice.RETRY,
            EscalationChoice.KILL,
            EscalationChoice.PAUSE_EPIC,
        ],
        "history_summary": "attempt 1: gates FAIL (pytest, exit 1)\nattempt 2: judge RETRY",
        "sent_at": "2026-08-04T11:00:00Z",
        "expires_at": "2026-08-04T12:00:00Z",
        "delivered": True,
    }
    fields.update(overrides)
    return EscalationRecord(**fields)


def raw_insert_result(conn: sqlite3.Connection, **overrides: Any) -> None:
    """Write a row with plain SQL, so the DDL's constraints are what answers."""
    values: dict[str, Any] = {
        "epic_id": "epic-7",
        "node_id": "node-3",
        "attempt": 1,
        "form": "PHASE",
        "verdict": "PASS",
        "gate_results": "[]",
        "output_check": "{}",
        "judge_verdict": None,
        "judge_unavailable": 0,
        "criteria_drift": 0,
        "criteria_sha256": "a" * 64,
        "spec_ref": "002-verification-gating/US1",
        "started_at": "2026-08-04T10:00:00Z",
        "finished_at": "2026-08-04T10:03:00Z",
    }
    values.update(overrides)
    _raw_insert(conn, "verification_results", values)


def raw_insert_escalation(conn: sqlite3.Connection, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "escalation_id": "0123456789ab",
        "workflow_id": "epic-7-interpreter",
        "epic_id": "epic-7",
        "node_id": "node-3",
        "choices": '["RETRY", "KILL"]',
        "history_summary": "two failed attempts",
        "delivered": 1,
        "sent_at": "2026-08-04T11:00:00Z",
        "expires_at": "2026-08-04T12:00:00Z",
        "resolution": None,
        "resolved_at": None,
        "resolved_via": None,
    }
    values.update(overrides)
    _raw_insert(conn, "escalations", values)


def _raw_insert(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join(f":{column}" for column in values)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
    conn.commit()


def _canonical(sql: str) -> str:
    """DDL text reduced to its structure: comments, layout and case dropped."""
    text = re.sub(r"--[^\n]*", " ", sql)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([(),])\s*", r"\1", text)
    return text.strip().casefold()


def schema_of(conn: sqlite3.Connection) -> dict[str, str]:
    """Every table/index the database defines, keyed by name."""
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0]: _canonical(row[1]) for row in rows}


def result_row(conn: sqlite3.Connection, **key: Any) -> dict[str, Any]:
    where = " AND ".join(f"{column} = :{column}" for column in key)
    cursor = conn.execute(f"SELECT * FROM verification_results WHERE {where}", key)
    row = cursor.fetchone()
    assert row is not None, f"no verification row for {key!r}"
    return {column[0]: value for column, value in zip(cursor.description, row)}


def escalation_row(conn: sqlite3.Connection, escalation_id: str) -> dict[str, Any]:
    cursor = conn.execute(
        "SELECT * FROM escalations WHERE escalation_id = ?", (escalation_id,)
    )
    row = cursor.fetchone()
    assert row is not None, f"no escalation row for {escalation_id!r}"
    return {column[0]: value for column, value in zip(cursor.description, row)}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "verification.db"


@pytest.fixture
def store(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def contract_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A scratch database with `contracts/verification-store.sql` applied verbatim."""
    conn = sqlite3.connect(tmp_path / "contract.db")
    try:
        conn.executescript(CONTRACT_DDL.read_text())
        yield conn
    finally:
        conn.close()


# --- schema bootstrap ------------------------------------------------------


def test_a_new_store_matches_the_published_contract_ddl(
    store: sqlite3.Connection, contract_db: sqlite3.Connection
) -> None:
    # The DDL file is the documented direct-SQL surface: what an operator reads
    # there is what the factory actually creates, structure for structure.
    assert schema_of(store) == schema_of(contract_db)


def test_the_verification_results_columns_match_the_contract(
    store: sqlite3.Connection,
) -> None:
    columns = [
        (row[1], row[2], row[3], row[5])
        for row in store.execute("PRAGMA table_info(verification_results)").fetchall()
    ]

    assert columns == EXPECTED_RESULT_COLUMNS


def test_the_escalations_columns_match_the_contract(store: sqlite3.Connection) -> None:
    columns = [
        (row[1], row[2], row[3], row[5])
        for row in store.execute("PRAGMA table_info(escalations)").fetchall()
    ]

    assert columns == EXPECTED_ESCALATION_COLUMNS


def test_the_query_indexes_exist(store: sqlite3.Connection) -> None:
    names = set()
    for table in ("verification_results", "escalations"):
        names |= {
            row[1] for row in store.execute(f"PRAGMA index_list({table})").fetchall()
        }

    # The canonical queries at the bottom of the DDL — per-node history, epic
    # health, spec-ref retry pressure, pending escalations — all read through
    # these; without them they degrade to full scans as epics accumulate.
    assert EXPECTED_INDEXES <= names


def test_the_upsert_key_carries_a_unique_index(store: sqlite3.Connection) -> None:
    unique_on = set()
    for row in store.execute("PRAGMA index_list(verification_results)").fetchall():
        name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        columns = tuple(
            info[2] for info in store.execute(f"PRAGMA index_info({name!r})").fetchall()
        )
        unique_on.add(columns)

    # Idempotency is structural: record_verification running twice cannot make a
    # second row for one attempt.
    assert ("epic_id", "node_id", "attempt", "form") in unique_on


def test_the_schema_version_is_recorded_once(store: sqlite3.Connection) -> None:
    versions = [row[0] for row in store.execute("SELECT version FROM schema_version")]

    # 8 since 017-US1 added the `messages` table (a `CREATE TABLE IF NOT EXISTS`
    # in `_SCHEMA_DDL` needs no data migration — every existing store gains the
    # table on its next open, and there is nothing to backfill). The literal is
    # deliberate: a bump claims every existing store has a migration path, and
    # `tests/test_escalation_record.py` checks that against one.
    assert SCHEMA_VERSION == 8
    assert versions == [SCHEMA_VERSION]


def test_the_store_is_opened_in_wal_mode_with_a_busy_timeout(
    store: sqlite3.Connection,
) -> None:
    journal_mode = store.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = store.execute("PRAGMA busy_timeout").fetchone()[0]

    # R10 inherits 001's R6: concurrent recorders on one host must not
    # serialize into lock errors.
    assert journal_mode.lower() == "wal"
    assert BUSY_TIMEOUT_MS == 5000
    assert busy_timeout == BUSY_TIMEOUT_MS


def test_connecting_creates_the_factory_directory(tmp_path: Path) -> None:
    nested = tmp_path / "workdir" / ".factory" / "verification.db"

    conn = connect(str(nested))
    try:
        assert nested.exists()
        assert schema_of(conn)
    finally:
        conn.close()


def test_reconnecting_to_an_existing_store_preserves_it(db_path: Path) -> None:
    first = connect(db_path)
    try:
        upsert_result(first, make_result())
        insert_escalation(first, make_escalation())
    finally:
        first.close()

    second = connect(db_path)
    try:
        # Bootstrap is idempotent: no duplicated version row, no lost evidence.
        versions = [
            row[0] for row in second.execute("SELECT version FROM schema_version")
        ]
        assert versions == [SCHEMA_VERSION]
        assert (
            second.execute("SELECT COUNT(*) FROM verification_results").fetchone()[0]
            == 1
        )
        assert second.execute("SELECT COUNT(*) FROM escalations").fetchone()[0] == 1
    finally:
        second.close()


# --- verification_results constraints --------------------------------------


def test_attempt_ordinals_start_at_one(store: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store, attempt=0)


@pytest.mark.parametrize("form", list(VerificationForm))
def test_every_verification_form_is_storable(
    store: sqlite3.Connection, form: VerificationForm
) -> None:
    raw_insert_result(store, form=form.value)

    stored = result_row(store, epic_id="epic-7", node_id="node-3", attempt=1,
                        form=form.value)
    assert stored["form"] == form.value


@pytest.mark.parametrize("form", ["phase", "", "BOTH"])
def test_forms_outside_the_enum_are_rejected(
    store: sqlite3.Connection, form: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store, form=form)


@pytest.mark.parametrize("verdict", ["UNKNOWN", "RETRY", "pass", ""])
def test_there_is_no_third_verdict(store: sqlite3.Connection, verdict: str) -> None:
    # FR-005: edge unlocking reads PASS or FAIL and nothing else. A judge that
    # was unreachable is a PASS carrying `judge_unavailable`, never a third
    # value downstream code could mistake for passing.
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store, verdict=verdict)


@pytest.mark.parametrize("column", ["judge_unavailable", "criteria_drift"])
@pytest.mark.parametrize("flag", [2, -1])
def test_the_evidence_flags_are_strictly_flags(
    store: sqlite3.Connection, column: str, flag: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store, **{column: flag})


@pytest.mark.parametrize("column", ["epic_id", "node_id", "spec_ref"])
def test_attribution_columns_reject_the_empty_string(
    store: sqlite3.Connection, column: str
) -> None:
    # A row that cannot say whose verification it was is worse than no row —
    # the same discipline the 001 ledger holds for spend.
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store, **{column: ""})


@pytest.mark.parametrize(
    "column",
    ["epic_id", "node_id", "attempt", "form", "verdict", "gate_results",
     "output_check", "criteria_sha256", "spec_ref", "started_at", "finished_at"],
)
def test_the_required_columns_are_not_nullable(
    store: sqlite3.Connection, column: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store, **{column: None})


def test_a_judge_that_never_ran_is_storable_as_null(store: sqlite3.Connection) -> None:
    # Cheapest-first: gates failed, so no judge call was made. NULL is the only
    # honest value — distinct from a judge that ran and returned FAIL.
    raw_insert_result(store, verdict="FAIL", judge_verdict=None)

    stored = result_row(store, epic_id="epic-7", node_id="node-3", attempt=1,
                        form="PHASE")
    assert stored["judge_verdict"] is None


def test_a_duplicate_attempt_cannot_be_inserted_directly(
    store: sqlite3.Connection,
) -> None:
    raw_insert_result(store)

    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_result(store)


# --- upsert_result ---------------------------------------------------------


def test_upsert_result_persists_the_whole_evidence_bundle(
    store: sqlite3.Connection,
) -> None:
    result = make_result()

    row_id = upsert_result(store, result)

    assert row_id is not None
    stored = result_row(store, id=row_id)
    assert stored["epic_id"] == result.epic_id
    assert stored["node_id"] == result.node_id
    assert stored["attempt"] == result.attempt
    assert stored["form"] == "PHASE"
    assert stored["verdict"] == "PASS"
    assert stored["criteria_sha256"] == result.criteria_sha256
    assert stored["spec_ref"] == result.spec_ref
    assert stored["started_at"] == result.started_at
    assert stored["finished_at"] == result.finished_at
    # bool -> 0/1 and nested dataclass -> JSON text are this layer's mappings.
    assert stored["judge_unavailable"] == 0
    assert stored["criteria_drift"] == 0
    gate_names = [gate["name"] for gate in json.loads(stored["gate_results"])]
    assert gate_names == ["test", "lint"]
    assert json.loads(stored["output_check"])["has_diff"] is True
    findings = json.loads(stored["judge_verdict"])["findings"]
    assert [finding["scenario"] for finding in findings] == ["US1-S1", "US1-S2"]


def test_upsert_result_commits_for_other_connections(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        upsert_result(conn, make_result())
    finally:
        conn.close()

    # One connection per activity invocation (R10): evidence left in an open
    # transaction is evidence lost when the activity's process exits.
    reader = sqlite3.connect(db_path)
    try:
        assert (
            reader.execute("SELECT COUNT(*) FROM verification_results").fetchone()[0]
            == 1
        )
    finally:
        reader.close()


def test_re_recording_an_attempt_updates_the_same_row(
    store: sqlite3.Connection,
) -> None:
    first = upsert_result(store, make_result())

    # Temporal re-runs record_verification after a worker crash; the second run
    # must land on the first run's row rather than duplicating the attempt.
    second = upsert_result(
        store,
        make_result(
            gate_results=[make_gate(status=GateStatus.FAIL, exit_code=1,
                                    output_tail="1 failed")],
            judge=None,
            verdict=OverallVerdict.FAIL,
            criteria_drift=True,
            finished_at="2026-08-04T10:05:00Z",
        ),
    )

    assert (
        store.execute("SELECT COUNT(*) FROM verification_results").fetchone()[0] == 1
    )
    assert second == first

    stored = result_row(store, id=first)
    assert stored["verdict"] == "FAIL"
    assert stored["judge_verdict"] is None
    assert stored["criteria_drift"] == 1
    assert stored["finished_at"] == "2026-08-04T10:05:00Z"


def test_the_two_verification_forms_of_one_attempt_do_not_collide(
    store: sqlite3.Connection,
) -> None:
    phase = upsert_result(store, make_result(form=VerificationForm.PHASE))
    node = upsert_result(
        store, make_result(form=VerificationForm.NODE, verdict=OverallVerdict.FAIL)
    )

    # FR-002: an attempt can be verified as a node's built-in phase *and* by an
    # explicit verifier node — two findings, two rows.
    assert phase != node
    assert store.execute("SELECT COUNT(*) FROM verification_results").fetchone()[0] == 2


def test_each_attempt_of_a_node_gets_its_own_row(store: sqlite3.Connection) -> None:
    upsert_result(store, make_result(attempt=1, verdict=OverallVerdict.FAIL))
    upsert_result(store, make_result(attempt=2))

    attempts = [
        row[0]
        for row in store.execute(
            "SELECT attempt FROM verification_results "
            "WHERE epic_id = 'epic-7' AND node_id = 'node-3' ORDER BY attempt"
        )
    ]
    assert attempts == [1, 2]


# --- node_history ----------------------------------------------------------


def test_node_history_round_trips_the_evidence_verbatim(
    store: sqlite3.Connection,
) -> None:
    result = make_result()
    upsert_result(store, result)

    (restored,) = node_history(store, "epic-7", "node-3")

    # The retry prompt quotes `output_tail` and judge feedback verbatim (FR-006,
    # SC-004) and the escalation message carries the full history (SC-005): a
    # lossy round-trip would only surface later, inside a prompt.
    assert restored == result
    assert restored.gate_results[0].output_tail == "42 passed in 12.5s"
    assert restored.judge is not None
    assert restored.judge.findings[1].scenario == "US1-S2"


def test_node_history_is_ordered_and_scoped_to_one_node(
    store: sqlite3.Connection,
) -> None:
    upsert_result(store, make_result(attempt=2, form=VerificationForm.NODE))
    upsert_result(store, make_result(attempt=1, verdict=OverallVerdict.FAIL))
    upsert_result(store, make_result(attempt=2, form=VerificationForm.PHASE))
    upsert_result(store, make_result(node_id="node-9"))
    upsert_result(store, make_result(epic_id="epic-8"))

    history = node_history(store, "epic-7", "node-3")

    assert [(entry.attempt, entry.form) for entry in history] == [
        (1, VerificationForm.PHASE),
        (2, VerificationForm.NODE),
        (2, VerificationForm.PHASE),
    ]


def test_node_history_of_an_unverified_node_is_empty(
    store: sqlite3.Connection,
) -> None:
    assert node_history(store, "epic-7", "node-3") == []


def test_a_judge_that_never_ran_round_trips_as_none(
    store: sqlite3.Connection,
) -> None:
    upsert_result(store, make_result(judge=None, verdict=OverallVerdict.FAIL))

    (restored,) = node_history(store, "epic-7", "node-3")

    assert restored.judge is None


# --- escalations: insert and read ------------------------------------------


def test_insert_escalation_writes_a_pending_row(store: sqlite3.Connection) -> None:
    record = make_escalation()

    insert_escalation(store, record)

    stored = escalation_row(store, record.escalation_id)
    assert stored["workflow_id"] == record.workflow_id
    assert stored["epic_id"] == record.epic_id
    assert stored["node_id"] == record.node_id
    assert json.loads(stored["choices"]) == ["RETRY", "KILL", "PAUSE_EPIC"]
    assert stored["history_summary"] == record.history_summary
    assert stored["delivered"] == 1
    assert stored["sent_at"] == record.sent_at
    assert stored["expires_at"] == record.expires_at
    # Pending is the absence of a terminal state, in all three columns.
    assert stored["resolution"] is None
    assert stored["resolved_at"] is None
    assert stored["resolved_via"] is None


def test_an_undelivered_escalation_is_still_recorded(
    store: sqlite3.Connection,
) -> None:
    # The row is written before the send, so a crash — or a notifier that is
    # simply down — leaves something expirable rather than an untracked message.
    insert_escalation(store, make_escalation(delivered=False))

    assert escalation_row(store, "0123456789ab")["delivered"] == 0


def test_insert_escalation_commits_for_other_connections(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        insert_escalation(conn, make_escalation())
    finally:
        conn.close()

    # The bridge service is a separate process holding no state of its own: it
    # can only find the row if the sender committed it.
    reader = sqlite3.connect(db_path)
    try:
        assert reader.execute("SELECT COUNT(*) FROM escalations").fetchone()[0] == 1
    finally:
        reader.close()


def test_get_escalation_returns_the_record(store: sqlite3.Connection) -> None:
    record = make_escalation()
    insert_escalation(store, record)

    assert get_escalation(store, record.escalation_id) == record


def test_get_escalation_of_an_unknown_id_is_none(store: sqlite3.Connection) -> None:
    # An id the bridge cannot find is answered with a notice, not an exception:
    # a stale button from a previous deployment must not crash the service.
    assert get_escalation(store, "ffffffffffff") is None


def test_a_duplicate_escalation_id_cannot_be_inserted(
    store: sqlite3.Connection,
) -> None:
    insert_escalation(store, make_escalation())

    with pytest.raises(sqlite3.IntegrityError):
        insert_escalation(store, make_escalation())


@pytest.mark.parametrize("resolution", ["retry", "TIMEOUT", "PAUSE", ""])
def test_resolutions_outside_the_enum_are_rejected(
    store: sqlite3.Connection, resolution: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_escalation(
            store, resolution=resolution, resolved_at="2026-08-04T11:30:00Z"
        )


@pytest.mark.parametrize(
    "resolution,resolved_at",
    [("RETRY", None), (None, "2026-08-04T11:30:00Z")],
)
def test_a_resolution_and_its_timestamp_travel_together(
    store: sqlite3.Connection, resolution: str | None, resolved_at: str | None
) -> None:
    # Half a terminal state is not a state: the DDL's paired CHECK is what stops
    # a resolved row that cannot say when, or a timestamp with no decision.
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_escalation(store, resolution=resolution, resolved_at=resolved_at)


# --- escalation state machine ----------------------------------------------


@pytest.mark.parametrize("choice", list(EscalationChoice))
def test_resolving_a_pending_escalation_records_the_operators_choice(
    store: sqlite3.Connection, choice: EscalationChoice
) -> None:
    insert_escalation(store, make_escalation())

    transitioned = resolve_escalation(
        store, "0123456789ab", choice, resolved_at="2026-08-04T11:30:00Z"
    )

    assert transitioned is True
    stored = escalation_row(store, "0123456789ab")
    assert stored["resolution"] == choice.value
    assert stored["resolved_at"] == "2026-08-04T11:30:00Z"
    assert stored["resolved_via"] == "BUTTON"


def test_expiring_a_pending_escalation_records_the_timeout(
    store: sqlite3.Connection,
) -> None:
    insert_escalation(store, make_escalation())

    transitioned = expire_escalation(
        store, "0123456789ab", resolved_at="2026-08-04T12:00:00Z"
    )

    assert transitioned is True
    stored = escalation_row(store, "0123456789ab")
    assert stored["resolution"] == "EXPIRED"
    assert stored["resolved_at"] == "2026-08-04T12:00:00Z"
    assert stored["resolved_via"] == "TIMEOUT"


def test_a_second_button_press_is_a_no_op(store: sqlite3.Connection) -> None:
    insert_escalation(store, make_escalation())
    resolve_escalation(
        store, "0123456789ab", EscalationChoice.RETRY, resolved_at="2026-08-04T11:30:00Z"
    )

    # Telegram redelivers, and operators double-tap. The second press is
    # answered "already resolved" — it must not signal a second decision.
    transitioned = resolve_escalation(
        store, "0123456789ab", EscalationChoice.KILL, resolved_at="2026-08-04T11:31:00Z"
    )

    assert transitioned is False
    stored = escalation_row(store, "0123456789ab")
    assert stored["resolution"] == "RETRY"
    assert stored["resolved_at"] == "2026-08-04T11:30:00Z"


def test_expiry_cannot_overwrite_an_operators_decision(
    store: sqlite3.Connection,
) -> None:
    insert_escalation(store, make_escalation())
    resolve_escalation(
        store, "0123456789ab", EscalationChoice.RETRY, resolved_at="2026-08-04T11:30:00Z"
    )

    # The workflow's timeout and the bridge's press race by design (R12); the
    # press landed first, so the hour elapsing changes nothing.
    transitioned = expire_escalation(
        store, "0123456789ab", resolved_at="2026-08-04T12:00:00Z"
    )

    assert transitioned is False
    stored = escalation_row(store, "0123456789ab")
    assert stored["resolution"] == "RETRY"
    assert stored["resolved_via"] == "BUTTON"


def test_a_press_after_expiry_is_a_no_op(store: sqlite3.Connection) -> None:
    insert_escalation(store, make_escalation())
    expire_escalation(store, "0123456789ab", resolved_at="2026-08-04T12:00:00Z")

    # The other side of the same race: the default kill has already been
    # applied, so a late press must not resurrect the node.
    transitioned = resolve_escalation(
        store, "0123456789ab", EscalationChoice.RETRY, resolved_at="2026-08-04T12:05:00Z"
    )

    assert transitioned is False
    stored = escalation_row(store, "0123456789ab")
    assert stored["resolution"] == "EXPIRED"
    assert stored["resolved_via"] == "TIMEOUT"


def test_expiring_twice_is_a_no_op(store: sqlite3.Connection) -> None:
    insert_escalation(store, make_escalation())
    expire_escalation(store, "0123456789ab", resolved_at="2026-08-04T12:00:00Z")

    # expire_escalation is an activity: Temporal runs it at least once.
    transitioned = expire_escalation(
        store, "0123456789ab", resolved_at="2026-08-04T13:00:00Z"
    )

    assert transitioned is False
    assert escalation_row(store, "0123456789ab")["resolved_at"] == "2026-08-04T12:00:00Z"


@pytest.mark.parametrize("transition", [resolve_escalation, expire_escalation])
def test_transitioning_an_unknown_escalation_is_a_no_op(
    store: sqlite3.Connection, transition: Any
) -> None:
    kwargs = (
        {"choice": EscalationChoice.RETRY}
        if transition is resolve_escalation
        else {}
    )

    transitioned = transition(
        store, "ffffffffffff", resolved_at="2026-08-04T12:00:00Z", **kwargs
    )

    assert transitioned is False
    assert store.execute("SELECT COUNT(*) FROM escalations").fetchone()[0] == 0


def test_a_terminal_transition_commits_for_other_connections(
    db_path: Path,
) -> None:
    writer = connect(db_path)
    try:
        insert_escalation(writer, make_escalation())
        resolve_escalation(
            writer,
            "0123456789ab",
            EscalationChoice.KILL,
            resolved_at="2026-08-04T11:30:00Z",
        )
    finally:
        writer.close()

    # The bridge resolves in its own process; the workflow's expiry path reads
    # from another. An uncommitted resolution is a decision applied twice.
    reader = connect(db_path)
    try:
        assert pending_escalations(reader) == []
    finally:
        reader.close()


# --- pending_escalations ---------------------------------------------------


def test_pending_escalations_returns_only_unresolved_rows(
    store: sqlite3.Connection,
) -> None:
    insert_escalation(store, make_escalation(escalation_id="aaaaaaaaaaaa"))
    insert_escalation(store, make_escalation(escalation_id="bbbbbbbbbbbb"))
    insert_escalation(store, make_escalation(escalation_id="cccccccccccc"))
    resolve_escalation(
        store, "bbbbbbbbbbbb", EscalationChoice.KILL, resolved_at="2026-08-04T11:30:00Z"
    )
    expire_escalation(store, "cccccccccccc", resolved_at="2026-08-04T12:00:00Z")

    pending = pending_escalations(store)

    # What an operator (and a restarted bridge) sees as still awaiting a
    # decision — resolved and expired rows are history, not work.
    assert [record.escalation_id for record in pending] == ["aaaaaaaaaaaa"]
    assert pending[0].resolution is None
    assert pending[0].resolved_at is None


def test_pending_escalations_is_empty_when_nothing_awaits_a_decision(
    store: sqlite3.Connection,
) -> None:
    assert pending_escalations(store) == []


# --- 008-US3: find a pending question by attempt (the ferry's dedup) ----------
#
# The workflow's US1 degrade path asks the store — not the adapter result —
# whether the in-attempt ferry already shipped a question for this attempt, so
# it can reuse that row instead of paging the operator a second time. Only a
# *pending* row is the one to reuse: an answered row was a ferry window that
# closed the other way (the agent resumed), so the US1 send path is never
# reached. The store is the source of truth, keeping D-018's hole at one signal.


def _make_question(
    *,
    question_id: str = "q1234567890ab",
    epic_id: str = "epic-008",
    node_id: str = "us1",
    attempt: int = 1,
) -> QuestionRecord:
    """A pending question row, the way `insert_question` wants one."""
    return QuestionRecord(
        question_id=question_id,
        workflow_id="wf-008-run-1",
        epic_id=epic_id,
        node_id=node_id,
        attempt=attempt,
        question_text="which option?",
        message_id=None,
        sent_at="2026-08-07T09:31:00Z",
        expires_at="2026-08-07T17:31:00Z",
    )


def test_find_pending_question_by_attempt_returns_the_row_when_one_is_pending(
    store: sqlite3.Connection,
) -> None:
    insert_question(store, _make_question(question_id="ferryaaaaaa", attempt=1))

    found = find_pending_question_by_attempt(
        store, epic_id="epic-008", node_id="us1", attempt=1
    )
    assert found is not None
    assert found.question_id == "ferryaaaaaa"
    assert found.resolution is None


def test_find_pending_question_by_attempt_returns_none_when_no_row_exists(
    store: sqlite3.Connection,
) -> None:
    assert (
        find_pending_question_by_attempt(
            store, epic_id="epic-008", node_id="us1", attempt=1
        )
        is None
    )


def test_find_pending_question_by_attempt_distinguishes_attempts(
    store: sqlite3.Connection,
) -> None:
    """A question for attempt 2 is not this attempt's ferry (FR-002 attribution)."""
    insert_question(store, _make_question(question_id="ferrybbbbbb", attempt=2))

    assert (
        find_pending_question_by_attempt(
            store, epic_id="epic-008", node_id="us1", attempt=1
        )
        is None
    )
    found = find_pending_question_by_attempt(
        store, epic_id="epic-008", node_id="us1", attempt=2
    )
    assert found is not None and found.question_id == "ferrybbbbbb"


def test_find_pending_question_by_attempt_distinguishes_nodes(
    store: sqlite3.Connection,
) -> None:
    insert_question(
        store, _make_question(question_id="ferrycccccc", node_id="us2", attempt=1)
    )

    assert (
        find_pending_question_by_attempt(
            store, epic_id="epic-008", node_id="us1", attempt=1
        )
        is None
    )


def test_find_pending_question_by_attempt_ignores_an_answered_row(
    store: sqlite3.Connection,
) -> None:
    """An ANSWERED row was a ferry that got its reply — the agent resumed, not
    degraded, so it is not the row the US1 degrade path reuses.
    """
    insert_question(store, _make_question(question_id="ferrydddddd", attempt=1))
    assert resolve_question(
        store, "ferrydddddd", answer_text="option A", resolved_at="2026-08-07T10:00:00Z"
    )

    assert (
        find_pending_question_by_attempt(
            store, epic_id="epic-008", node_id="us1", attempt=1
        )
        is None
    )


def test_find_pending_question_by_attempt_picks_the_newest_pending_row(
    store: sqlite3.Connection,
) -> None:
    """When more than one pending row exists for an attempt, the newest ships.

    A rare race (two ferry beats shipped before the first recorded), the store
    resolves it deterministically: the latest send is the one the operator saw
    last, so its id is the one to reuse.
    """
    insert_question(
        store,
        replace(
            _make_question(question_id="ferryeeeeee", attempt=1),
            sent_at="2026-08-07T09:00:00Z",
        ),
    )
    insert_question(
        store,
        replace(
            _make_question(question_id="ferryffffff", attempt=1),
            sent_at="2026-08-07T10:00:00Z",
        ),
    )

    found = find_pending_question_by_attempt(
        store, epic_id="epic-008", node_id="us1", attempt=1
    )
    assert found is not None and found.question_id == "ferryffffff"


# --- 023-US4: loop digest and summary on the evidence row --------------------


def _us4_loop_digest(
    config: VerificationConfig,
    verify_order: tuple[str, ...],
    gate_names: tuple[str, ...],
    *,
    schema_version: int = 1,
) -> str:
    """SHA-256 of the canonical loop configuration (FR-010)."""
    data = {
        "schema_version": schema_version,
        "gate_names": list(gate_names),
        "verify_order": list(verify_order),
        "ladder": {
            k: v
            for k, v in asdict(config).items()
            if k in ("max_attempts", "max_judge_retries", "debugger_cycles", "escalation_timeout_s")
        },
        "judge_present": "judge" in verify_order,
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _us4_loop_summary(
    config: VerificationConfig,
    verify_order: tuple[str, ...],
    gate_names: tuple[str, ...],
    *,
    schema_version: int = 1,
) -> str:
    """Human-readable one-line summary of the resolved loop."""
    steps = ", ".join(verify_order)
    ladder = (
        f"attempts={config.max_attempts}, judge_retries={config.max_judge_retries}, "
        f"debugger={config.debugger_cycles}, deadline={config.escalation_timeout_s}s"
    )
    judge = "judge present" if "judge" in verify_order else "no judge"
    gates = ", ".join(gate_names) if gate_names else "no gates"
    return f"schema v{schema_version}; gates [{gates}]; order [{steps}]; {ladder}; {judge}"


#: v1 repo with default gate names, default verify order, default VerificationConfig.
_US4_DEFAULT_LOOP_DIGEST = _us4_loop_digest(
    VerificationConfig(), ("gates", "diff_check", "judge"), ("test", "lint", "typecheck")
)


def _us4_result(
    config: VerificationConfig,
    verify_order: tuple[str, ...],
    gate_names: tuple[str, ...],
    *,
    schema_version: int = 1,
    attempt: int = 1,
    **overrides: Any,
) -> VerificationResult:
    """A passing result carrying the loop digest/summary for the given config."""
    fields: dict[str, Any] = {
        "epic_id": "023-us4",
        "node_id": "node-a",
        "attempt": attempt,
        "form": VerificationForm.PHASE,
        "gate_results": [
            GateResult(
                name=name,
                command="echo pass",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.0,
                output_tail=f"{name} passed",
            )
            for name in gate_names
        ],
        "output_check": OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        "judge": JudgeVerdict(
            outcome=JudgeOutcome.PASS,
            findings=[],
            feedback="ok",
            judge_attempt=1,
            truncated_input=False,
            model_alias="judge",
        ),
        "criteria_sha256": "a" * 64,
        "spec_ref": "023-composable-verification/US4",
        "started_at": "2026-08-17T10:00:00Z",
        "finished_at": "2026-08-17T10:03:00Z",
        "verdict": OverallVerdict.PASS,
        "judge_unavailable": False,
        "criteria_drift": False,
        "loop_digest": _us4_loop_digest(
            config, verify_order, gate_names, schema_version=schema_version
        ),
        "loop_summary": _us4_loop_summary(
            config, verify_order, gate_names, schema_version=schema_version
        ),
    }
    fields.update(overrides)
    return VerificationResult(**fields)


def test_digest_is_stable_across_attempts_under_same_loop(
    store: sqlite3.Connection,
) -> None:
    """The digest identifies the loop, not the attempt (US4-S4)."""
    config = VerificationConfig()
    order = ("gates", "diff_check", "judge")
    gates = ("test", "lint", "typecheck")

    first = _us4_result(config, order, gates, attempt=1)
    second = _us4_result(config, order, gates, attempt=2)

    upsert_result(store, first)
    upsert_result(store, second)

    rows = store.execute(
        "SELECT loop_digest FROM verification_results WHERE epic_id = '023-us4' "
        "ORDER BY attempt"
    ).fetchall()
    digests = [row[0] for row in rows]

    assert digests[0] == digests[1]
    assert digests[0] == _US4_DEFAULT_LOOP_DIGEST


def test_digest_differs_across_different_loops(store: sqlite3.Connection) -> None:
    """A different declared loop produces a different digest (US4-S1)."""
    default = _us4_result(
        VerificationConfig(),
        ("gates", "diff_check", "judge"),
        ("test", "lint", "typecheck"),
        epic_id="epic-default",
    )
    reordered = _us4_result(
        VerificationConfig(),
        ("diff_check", "gates", "judge"),
        ("unit", "contract"),
        epic_id="epic-reordered",
    )
    judgeless = _us4_result(
        VerificationConfig(),
        ("gates", "diff_check"),
        ("test",),
        epic_id="epic-judgeless",
    )

    upsert_result(store, default)
    upsert_result(store, reordered)
    upsert_result(store, judgeless)

    rows = store.execute(
        "SELECT epic_id, loop_digest FROM verification_results ORDER BY id"
    ).fetchall()
    digests = {row[0]: row[1] for row in rows}

    assert len(set(digests.values())) == 3


def test_unconfigured_default_loop_digest_is_named_constant(
    store: sqlite3.Connection,
) -> None:
    """A v1 repo records the explicit default digest, not an absent field (US4-S3)."""
    result = _us4_result(
        VerificationConfig(),
        ("gates", "diff_check", "judge"),
        ("test", "lint", "typecheck"),
    )

    upsert_result(store, result)

    raw = result_row(store, epic_id="023-us4", node_id="node-a", attempt=1, form="PHASE")
    assert raw["loop_digest"] == _US4_DEFAULT_LOOP_DIGEST
    assert "schema v1" in raw["loop_summary"]
    assert "judge present" in raw["loop_summary"]


def test_v1_unconfigured_repo_records_default_loop_from_compose_result(
    store: sqlite3.Connection,
) -> None:
    """A caller that does not pass loop fields still records the explicit default.

    US4-S3: the unconfigured default is a described state, never an absent field.
    This test exercises the production compose path rather than constructing a
    result manually, so it proves the default is applied automatically.
    """
    result = compose_result(
        epic_id="v1-default",
        node_id="node-a",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="echo pass",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.0,
                output_tail="ok",
            )
        ],
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=None,
        criteria_sha256="a" * 64,
        spec_ref="v1/US1",
        started_at="2026-08-17T10:00:00Z",
        finished_at="2026-08-17T10:03:00Z",
    )

    upsert_result(store, result)

    raw = result_row(store, epic_id="v1-default", node_id="node-a", attempt=1, form="PHASE")
    assert raw["loop_digest"] == DEFAULT_LOOP_DIGEST
    assert raw["loop_summary"] == DEFAULT_LOOP_SUMMARY
    assert "schema v1" in raw["loop_summary"]
    assert "judge present" in raw["loop_summary"]


def test_pre_023_rows_read_loop_digest_as_absent(store: sqlite3.Connection) -> None:
    """Stores written before US4 return absent loop fields, never backfilled."""
    raw_insert_result(
        store,
        epic_id="pre-023",
        node_id="node-a",
        attempt=1,
        form="PHASE",
        verdict="PASS",
        gate_results="[]",
        output_check=(
            '{"write_scope":"worktree","has_diff":false,'
            '"expected_artifacts":[],"artifacts_present":null,"passed":false}'
        ),
        judge_verdict=None,
        judge_unavailable=0,
        criteria_drift=0,
        criteria_sha256="a" * 64,
        spec_ref="old/US1",
        started_at="2026-08-01T10:00:00Z",
        finished_at="2026-08-01T10:03:00Z",
    )

    (restored,) = node_history(store, "pre-023", "node-a")
    assert restored.loop_digest is None
    assert restored.loop_summary is None
