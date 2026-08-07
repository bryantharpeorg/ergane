"""The factory's record of what was verified, and the only writer to it.

`.factory/verification.db` is a published surface the same way the 001 ledger is:
an operator opens it with `sqlite3`, escalation summaries read it, and a future
operations UI will query it. That promise is why `_SCHEMA_DDL` below is a
verbatim copy of `contracts/verification-store.sql` rather than a paraphrase —
`tests/test_verify_store.py` applies the contract file to a scratch database and
compares it, structure for structure, against what `connect` creates. The two
drift apart only over a failing test. (A copy, not a read: the contract lives
under `specs/`, which is documentation, not something a worker unpacks at
runtime.)

Four decisions carry the weight here:

- **WAL with a busy timeout (R10, inherited from 001's R6).** Sibling nodes
  finish verifying concurrently on the one host that owns `.factory/`; in
  rollback-journal mode they would serialize into `database is locked` on the
  one path that records evidence. Each activity invocation opens its own
  connection, and every writer here commits before returning, so evidence is
  durable the moment the caller is told it was written.
- **`(epic_id, node_id, attempt, form)` is the upsert key.** Temporal runs
  `record_verification` at least once, so a re-run must land on the first run's
  row. The uniqueness is structural, which makes "one row per attempt per form"
  a property of the schema rather than of the caller's care. `form` is in the
  key because one attempt can be verified both as a node's built-in phase and by
  an explicit verifier node (FR-002).
- **An escalation makes exactly one terminal transition.** Both
  `resolve_escalation` and `expire_escalation` are a single UPDATE guarded by
  `WHERE resolution IS NULL`, and report what SQLite did rather than checking
  first and writing second — the bridge's button press and the workflow's
  timeout race by design (R12), and a read-then-write would let both win. A
  losing caller gets `False`, not an exception: a double-tapped button and a
  redelivered activity are ordinary, not errors.
- **Evidence round-trips.** Gate results, the output check and the judge verdict
  live in JSON text columns; `node_history` hands them back as the same frozen
  dataclasses, because the retry prompt quotes `output_tail` and judge feedback
  verbatim (FR-006, SC-004) and escalation messages carry the full history
  (SC-005). The codecs below are written out longhand for that reason — a lossy
  conversion would not surface here, it would surface much later, inside a
  prompt.

`judge_verdict` is the one nullable evidence column, and the distinction is
deliberate: NULL means the judge never ran (gates failed under cheapest-first, or
the node has no scenarios), which is a different fact from a judge that ran and
returned FAIL.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from factory.verify.models import (
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
    VerificationForm,
    VerificationResult,
)

#: Bumping this means the DDL below changed shape and existing stores need a
#: migration path. Recorded in the database so a reader can tell.
SCHEMA_VERSION = 2

#: R10: how long a writer waits out another writer's lock before giving up. Long
#: enough to absorb a concurrent recorder, short enough that a genuinely wedged
#: store fails the activity instead of hanging it.
BUSY_TIMEOUT_MS = 5000

#: The terminal `resolution` that no button can produce — written only by the
#: workflow's timeout path, which is why `EscalationRecord.resolution` is typed
#: `EscalationChoice | str | None` rather than just the enum.
EXPIRED = "EXPIRED"

#: Verbatim from `contracts/verification-store.sql`. Every statement is
#: `IF NOT EXISTS`, so bootstrap is safe to run on every connect.
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_results (
    id                INTEGER PRIMARY KEY,
    epic_id           TEXT    NOT NULL CHECK (epic_id <> ''),
    node_id           TEXT    NOT NULL CHECK (node_id <> ''),
    attempt           INTEGER NOT NULL CHECK (attempt >= 1),
    form              TEXT    NOT NULL CHECK (form IN ('PHASE', 'NODE')),
    verdict           TEXT    NOT NULL CHECK (verdict IN ('PASS', 'FAIL')),
    -- evidence bundles (JSON text, schemas in data-model.md)
    gate_results      TEXT    NOT NULL,   -- JSON: list[GateResult]
    output_check      TEXT    NOT NULL,   -- JSON: OutputCheck
    judge_verdict     TEXT,               -- JSON: JudgeVerdict | NULL (gates failed / no scenarios)
    -- flags
    judge_unavailable INTEGER NOT NULL DEFAULT 0 CHECK (judge_unavailable IN (0, 1)),
    criteria_drift    INTEGER NOT NULL DEFAULT 0 CHECK (criteria_drift IN (0, 1)),
    criteria_sha256   TEXT    NOT NULL,   -- dispatch-snapshot hash (FR-010)
    spec_ref          TEXT    NOT NULL CHECK (spec_ref <> ''),
    started_at        TEXT    NOT NULL,   -- ISO-8601 UTC
    finished_at       TEXT    NOT NULL,
    UNIQUE (epic_id, node_id, attempt, form)   -- upsert key (record_verification)
);

CREATE INDEX IF NOT EXISTS idx_vr_epic    ON verification_results (epic_id);
CREATE INDEX IF NOT EXISTS idx_vr_node    ON verification_results (epic_id, node_id);
CREATE INDEX IF NOT EXISTS idx_vr_specref ON verification_results (spec_ref);
CREATE INDEX IF NOT EXISTS idx_vr_verdict ON verification_results (verdict);

CREATE TABLE IF NOT EXISTS escalations (
    escalation_id  TEXT PRIMARY KEY,       -- 12-hex token (callback_data key)
    workflow_id    TEXT NOT NULL,
    epic_id        TEXT NOT NULL,
    node_id        TEXT NOT NULL,
    choices        TEXT NOT NULL,          -- JSON: list[EscalationChoice]
    history_summary TEXT NOT NULL,         -- full failure history (SC-005)
    delivered      INTEGER NOT NULL DEFAULT 0 CHECK (delivered IN (0, 1)),
    sent_at        TEXT NOT NULL,
    expires_at     TEXT NOT NULL,          -- sent_at + 1h
    resolution     TEXT CHECK (resolution IN ('RETRY', 'KILL', 'PAUSE_EPIC', 'EXPIRED')),
    resolved_at    TEXT,
    resolved_via   TEXT CHECK (resolved_via IN ('BUTTON', 'TIMEOUT')),
    CHECK ((resolution IS NULL) = (resolved_at IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_esc_pending ON escalations (resolution) WHERE resolution IS NULL;
CREATE INDEX IF NOT EXISTS idx_esc_node    ON escalations (epic_id, node_id);

-- 008-US1: a sibling to escalations for operator questions. The escalations
-- table's CHECK constraints (resolution IN RETRY/KILL/PAUSE_EPIC/EXPIRED) cannot
-- hold a free-text answer, which is the whole reason this table exists (plan §
-- Technical Context): an escalation path never touches it, and it is never
-- touched by one. `message_id` is the Telegram message id the send returned —
-- the reply-routing key a free-text answer threads back to (FR-008, US2); it is
-- NULL until the message is delivered. `resolution` is ANSWERED (an operator
-- replied, US2) or EXPIRED (the question's own window ran out, FR-004); NULL
-- while the node is parked WAITING_OPERATOR.
CREATE TABLE IF NOT EXISTS questions (
    question_id    TEXT PRIMARY KEY,         -- 12-hex token (reply-routing key)
    workflow_id    TEXT NOT NULL,
    epic_id        TEXT NOT NULL,
    node_id        TEXT NOT NULL,
    attempt        INTEGER NOT NULL CHECK (attempt >= 1),
    question_text  TEXT NOT NULL,            -- the marker body, verbatim (FR-002)
    message_id     INTEGER,                  -- Telegram message id; NULL until delivered
    sent_at        TEXT NOT NULL,
    expires_at     TEXT NOT NULL,            -- sent_at + 8h (FR-004, the question's own window)
    resolution     TEXT CHECK (resolution IN ('ANSWERED', 'EXPIRED')),
    answer_text    TEXT,                     -- the operator's reply (US2 fills this)
    resolved_at    TEXT,
    CHECK ((resolution IS NULL) = (resolved_at IS NULL)),
    CHECK ((answer_text IS NULL OR resolution = 'ANSWERED'))
);

CREATE INDEX IF NOT EXISTS idx_q_pending ON questions (resolution) WHERE resolution IS NULL;
CREATE INDEX IF NOT EXISTS idx_q_node    ON questions (epic_id, node_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the evidence store at `path`, creating file, directories and schema.

    Callers get a connection they own for the duration of one activity
    invocation (R10) and are responsible for closing.
    """
    location = Path(path)
    location.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(location)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    _bootstrap_schema(conn)
    return conn


def _bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Apply the DDL and stamp the version — idempotent across reconnects."""
    conn.executescript(_SCHEMA_DDL)
    recorded = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    if recorded == 0:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
    conn.commit()


# --- verification results ---------------------------------------------------

#: The columns identifying one verification — the ON CONFLICT target, and what a
#: re-run matches on rather than overwrites.
_RESULT_KEY = ("epic_id", "node_id", "attempt", "form")

#: Everything `upsert_result` writes, in DDL order. `id` is SQLite's to assign,
#: and a re-recorded attempt must not renumber the row it lands on.
_RESULT_COLUMNS = (
    "epic_id",
    "node_id",
    "attempt",
    "form",
    "verdict",
    "gate_results",
    "output_check",
    "judge_verdict",
    "judge_unavailable",
    "criteria_drift",
    "criteria_sha256",
    "spec_ref",
    "started_at",
    "finished_at",
)

#: A re-run overwrites every column except the four it matched on: the second
#: recording of an attempt is the current one.
_UPSERT_RESULT_SQL = (
    f"INSERT INTO verification_results ({', '.join(_RESULT_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _RESULT_COLUMNS)}) "
    f"ON CONFLICT ({', '.join(_RESULT_KEY)}) DO UPDATE SET "
    + ", ".join(
        f"{column} = excluded.{column}"
        for column in _RESULT_COLUMNS
        if column not in _RESULT_KEY
    )
)

_SELECT_RESULT_SQL = f"SELECT {', '.join(_RESULT_COLUMNS)} FROM verification_results"


def upsert_result(conn: sqlite3.Connection, result: VerificationResult) -> int:
    """Record one attempt's evidence, returning its stable row id.

    Keyed on `(epic_id, node_id, attempt, form)`: a `record_verification` that
    runs a second time updates the row the first one wrote instead of adding
    another, so the returned id is stable across reruns.
    """
    values = _result_values(result)

    conn.execute(_UPSERT_RESULT_SQL, values)
    row = conn.execute(
        "SELECT id FROM verification_results WHERE "
        + " AND ".join(f"{column} = :{column}" for column in _RESULT_KEY),
        {column: values[column] for column in _RESULT_KEY},
    ).fetchone()
    conn.commit()

    return int(row[0])


def node_history(
    conn: sqlite3.Connection, epic_id: str, node_id: str
) -> list[VerificationResult]:
    """Every verification of one node, oldest attempt first.

    The canonical per-node query from the DDL — what retry prompts quote and
    what an escalation's failure history is built from (SC-004, SC-005). Ordered
    by `(attempt, form)` so the sequence reads the way it happened.
    """
    rows = conn.execute(
        f"{_SELECT_RESULT_SQL} WHERE epic_id = ? AND node_id = ? "
        "ORDER BY attempt, form",
        (epic_id, node_id),
    ).fetchall()

    return [_result_from_row(row) for row in rows]


def _result_values(result: VerificationResult) -> dict[str, Any]:
    """One result as bound parameters — the storage layer's only conversions."""
    return {
        "epic_id": result.epic_id,
        "node_id": result.node_id,
        "attempt": result.attempt,
        "form": VerificationForm(result.form).value,
        "verdict": OverallVerdict(result.verdict).value,
        "gate_results": json.dumps([_gate_to_dict(g) for g in result.gate_results]),
        "output_check": json.dumps(_output_check_to_dict(result.output_check)),
        "judge_verdict": (
            None if result.judge is None else json.dumps(_judge_to_dict(result.judge))
        ),
        "judge_unavailable": int(result.judge_unavailable),
        "criteria_drift": int(result.criteria_drift),
        "criteria_sha256": result.criteria_sha256,
        "spec_ref": result.spec_ref,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }


def _result_from_row(row: tuple[Any, ...]) -> VerificationResult:
    """Rebuild a result from a `_RESULT_COLUMNS`-ordered row."""
    values = dict(zip(_RESULT_COLUMNS, row))
    judge_verdict = values["judge_verdict"]

    return VerificationResult(
        epic_id=values["epic_id"],
        node_id=values["node_id"],
        attempt=values["attempt"],
        form=VerificationForm(values["form"]),
        gate_results=[_gate_from_dict(g) for g in json.loads(values["gate_results"])],
        output_check=_output_check_from_dict(json.loads(values["output_check"])),
        # NULL is "the judge never ran", not "ran and said nothing" — the latter
        # is a stored verdict whose outcome is FAIL.
        judge=None if judge_verdict is None else _judge_from_dict(json.loads(judge_verdict)),
        verdict=OverallVerdict(values["verdict"]),
        judge_unavailable=bool(values["judge_unavailable"]),
        criteria_drift=bool(values["criteria_drift"]),
        criteria_sha256=values["criteria_sha256"],
        spec_ref=values["spec_ref"],
        started_at=values["started_at"],
        finished_at=values["finished_at"],
    )


# --- evidence codecs --------------------------------------------------------


def _gate_to_dict(gate: GateResult) -> dict[str, Any]:
    return {
        "name": gate.name,
        "command": gate.command,
        "status": GateStatus(gate.status).value,
        "exit_code": gate.exit_code,
        "duration_s": gate.duration_s,
        "output_tail": gate.output_tail,
        "concurrent_gates": gate.concurrent_gates,
    }


def _gate_from_dict(data: dict[str, Any]) -> GateResult:
    return GateResult(
        name=data["name"],
        command=data["command"],
        status=GateStatus(data["status"]),
        exit_code=data["exit_code"],
        duration_s=data["duration_s"],
        output_tail=data["output_tail"],
        # Rows written before 007 FR-005 have no contention marker; absent
        # means uncontended, which is the only honest reading of a row that
        # predates fan-out.
        concurrent_gates=data.get("concurrent_gates", 0),
    )


def _output_check_to_dict(check: OutputCheck) -> dict[str, Any]:
    return {
        "write_scope": check.write_scope,
        "has_diff": check.has_diff,
        "expected_artifacts": list(check.expected_artifacts),
        "artifacts_present": check.artifacts_present,
        "passed": check.passed,
    }


def _output_check_from_dict(data: dict[str, Any]) -> OutputCheck:
    return OutputCheck(
        write_scope=data["write_scope"],
        has_diff=data["has_diff"],
        expected_artifacts=data["expected_artifacts"],
        artifacts_present=data["artifacts_present"],
        passed=data["passed"],
    )


def _judge_to_dict(judge: JudgeVerdict) -> dict[str, Any]:
    return {
        "outcome": JudgeOutcome(judge.outcome).value,
        "findings": [
            {
                "scenario": finding.scenario,
                "passed": finding.passed,
                "reasoning": finding.reasoning,
            }
            for finding in judge.findings
        ],
        "feedback": judge.feedback,
        "judge_attempt": judge.judge_attempt,
        "truncated_input": judge.truncated_input,
        "model_alias": judge.model_alias,
    }


def _judge_from_dict(data: dict[str, Any]) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=JudgeOutcome(data["outcome"]),
        findings=[
            JudgeScenarioFinding(
                scenario=finding["scenario"],
                passed=finding["passed"],
                reasoning=finding["reasoning"],
            )
            for finding in data["findings"]
        ],
        feedback=data["feedback"],
        judge_attempt=data["judge_attempt"],
        truncated_input=data["truncated_input"],
        model_alias=data["model_alias"],
    )


# --- escalations ------------------------------------------------------------

_ESCALATION_COLUMNS = (
    "escalation_id",
    "workflow_id",
    "epic_id",
    "node_id",
    "choices",
    "history_summary",
    "delivered",
    "sent_at",
    "expires_at",
    "resolution",
    "resolved_at",
    "resolved_via",
)

_INSERT_ESCALATION_SQL = (
    f"INSERT INTO escalations ({', '.join(_ESCALATION_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _ESCALATION_COLUMNS)})"
)

_SELECT_ESCALATION_SQL = f"SELECT {', '.join(_ESCALATION_COLUMNS)} FROM escalations"

#: Both terminal transitions are this one guarded UPDATE. The guard is the state
#: machine: whichever of the bridge and the timeout path arrives second matches
#: no rows and is told so, instead of overwriting a decision already made.
_TRANSITION_SQL = (
    "UPDATE escalations SET resolution = ?, resolved_at = ?, resolved_via = ? "
    "WHERE escalation_id = ? AND resolution IS NULL"
)


def insert_escalation(conn: sqlite3.Connection, record: EscalationRecord) -> None:
    """Write a pending escalation row.

    Called *before* the message is sent (R11), so a crash — or a notifier that
    is simply down — leaves something expirable rather than an untracked
    message. Raises `sqlite3.IntegrityError` if the id is already taken, since a
    reused token would let one button press resolve someone else's escalation.
    """
    resolution = _resolution_value(record.resolution)
    conn.execute(
        _INSERT_ESCALATION_SQL,
        {
            "escalation_id": record.escalation_id,
            "workflow_id": record.workflow_id,
            "epic_id": record.epic_id,
            "node_id": record.node_id,
            "choices": json.dumps(
                [EscalationChoice(choice).value for choice in record.choices]
            ),
            "history_summary": record.history_summary,
            "delivered": int(record.delivered),
            "sent_at": record.sent_at,
            "expires_at": record.expires_at,
            "resolution": resolution,
            "resolved_at": record.resolved_at,
            "resolved_via": _resolved_via(resolution),
        },
    )
    conn.commit()


def mark_delivered(conn: sqlite3.Connection, escalation_id: str) -> bool:
    """Note that the message actually reached Telegram. True if a row was updated.

    Separate from the insert because the insert happens first, on purpose (R11):
    the row exists before the send, so `delivered` is the one fact about an
    escalation that can only be known afterwards. It is evidence for a reader —
    nothing gates on it, since a button press resolves an escalation whether or
    not the factory ever learned the message landed.
    """
    cursor = conn.execute(
        "UPDATE escalations SET delivered = 1 WHERE escalation_id = ?",
        (escalation_id,),
    )
    conn.commit()

    return cursor.rowcount == 1


def get_escalation(
    conn: sqlite3.Connection, escalation_id: str
) -> EscalationRecord | None:
    """One escalation by its `callback_data` token, or None if there is no such row.

    None rather than an exception: a stale button from a previous deployment is
    answered with a notice, not a crashed bridge service.
    """
    row = conn.execute(
        f"{_SELECT_ESCALATION_SQL} WHERE escalation_id = ?", (escalation_id,)
    ).fetchone()

    return None if row is None else _escalation_from_row(row)


def pending_escalations(conn: sqlite3.Connection) -> list[EscalationRecord]:
    """Every escalation still awaiting a decision, oldest first.

    What an operator — and a restarted bridge, which holds no state of its own —
    sees as outstanding work; resolved and expired rows are history.
    """
    rows = conn.execute(
        f"{_SELECT_ESCALATION_SQL} WHERE resolution IS NULL "
        "ORDER BY sent_at, escalation_id"
    ).fetchall()

    return [_escalation_from_row(row) for row in rows]


def resolve_escalation(
    conn: sqlite3.Connection,
    escalation_id: str,
    choice: EscalationChoice | str,
    *,
    resolved_at: str,
) -> bool:
    """Record an operator's button press. True if this call is what resolved it.

    False means the escalation was unknown or already terminal — a double-tap, a
    Telegram redelivery, or a press that lost the race to the hour expiring. The
    caller answers "already resolved" and sends no signal.
    """
    return _transition(
        conn,
        escalation_id,
        resolution=EscalationChoice(choice).value,
        resolved_at=resolved_at,
    )


def expire_escalation(
    conn: sqlite3.Connection, escalation_id: str, *, resolved_at: str
) -> bool:
    """Record the hour elapsing. True if this call is what expired it.

    False means an operator already decided, or a previous run of this activity
    already expired it — Temporal runs it at least once, and the default kill
    must not be applied on top of an answered escalation.
    """
    return _transition(
        conn, escalation_id, resolution=EXPIRED, resolved_at=resolved_at
    )


def _transition(
    conn: sqlite3.Connection, escalation_id: str, *, resolution: str, resolved_at: str
) -> bool:
    cursor = conn.execute(
        _TRANSITION_SQL,
        (resolution, resolved_at, _resolved_via(resolution), escalation_id),
    )
    conn.commit()

    return cursor.rowcount == 1


def _resolution_value(resolution: EscalationChoice | str | None) -> str | None:
    if resolution is None:
        return None
    return EXPIRED if resolution == EXPIRED else EscalationChoice(resolution).value


def _resolved_via(resolution: str | None) -> str | None:
    """How a terminal state was reached, derived from the state itself.

    `EXPIRED` is the one resolution no button can produce, so the two columns
    can never disagree about whether an operator answered.
    """
    if resolution is None:
        return None
    return "TIMEOUT" if resolution == EXPIRED else "BUTTON"


def _escalation_from_row(row: tuple[Any, ...]) -> EscalationRecord:
    """Rebuild a record from an `_ESCALATION_COLUMNS`-ordered row."""
    values = dict(zip(_ESCALATION_COLUMNS, row))
    resolution = values["resolution"]

    return EscalationRecord(
        escalation_id=values["escalation_id"],
        workflow_id=values["workflow_id"],
        epic_id=values["epic_id"],
        node_id=values["node_id"],
        choices=[EscalationChoice(choice) for choice in json.loads(values["choices"])],
        history_summary=values["history_summary"],
        sent_at=values["sent_at"],
        expires_at=values["expires_at"],
        delivered=bool(values["delivered"]),
        # EXPIRED stays a bare string: it is a terminal state, not a choice
        # anyone was ever offered.
        resolution=(
            None
            if resolution is None
            else EXPIRED
            if resolution == EXPIRED
            else EscalationChoice(resolution)
        ),
        resolved_at=values["resolved_at"],
    )


# --- operator questions (008-US1) -------------------------------------------
#
# A sibling table to escalations, for the one thing the escalations CHECK
# constraints cannot hold: a free-text answer. The shape mirrors escalations —
# the row is written before the send (R11), the message id is captured at send
# (FR-008's prerequisite), and a terminal transition is one guarded UPDATE —
# but the resolution vocabulary is ANSWERED/EXPIRED, not RETRY/KILL/PAUSE_EPIC,
# because a question is not a choice the operator picks from a list. The no-burn
# accounting and the answer round-trip are US2; this component owns only the row
# the send writes and the transition the expiry (US2) will close.

#: `ANSWERED` — the operator replied (US2). `EXPIRED` — the question's own
#: window ran out (FR-004), reusing the escalation vocabulary's terminal word so
#: a reader of either table reads the other the same way.
ANSWERED = "ANSWERED"

#: The columns identifying one question, in the order `_SELECT_QUESTION_SQL`
#: returns them — the same order `_question_from_row` reads.
_QUESTION_COLUMNS = (
    "question_id",
    "workflow_id",
    "epic_id",
    "node_id",
    "attempt",
    "question_text",
    "message_id",
    "sent_at",
    "expires_at",
    "resolution",
    "answer_text",
    "resolved_at",
)

_SELECT_QUESTION_SQL = (
    f"SELECT {', '.join(_QUESTION_COLUMNS)} FROM questions"
)

_INSERT_QUESTION_SQL = (
    "INSERT INTO questions (question_id, workflow_id, epic_id, node_id, attempt, "
    "question_text, message_id, sent_at, expires_at, resolution, answer_text, "
    "resolved_at) VALUES (:question_id, :workflow_id, :epic_id, :node_id, :attempt, "
    ":question_text, :message_id, :sent_at, :expires_at, :resolution, :answer_text, "
    ":resolved_at)"
)

#: The guarded transition an answer (US2) or the question's own expiry closes.
#: Whichever arrives second matches no rows and is told so, the same way the
#: escalations table settles the race between a press and the hour.
_QUESTION_TRANSITION_SQL = (
    "UPDATE questions SET resolution = ?, answer_text = ?, resolved_at = ? "
    "WHERE question_id = ? AND resolution IS NULL"
)


def insert_question(conn: sqlite3.Connection, record: QuestionRecord) -> None:
    """Write a pending question row (R11, the escalation precedent).

    Called *before* the message is sent, so a crash in between leaves something
    the expiry path (US2) can still close rather than an untracked message in a
    chat. Raises `sqlite3.IntegrityError` if the id is already taken, since a
    reused token would let a reply to last week's question land on this one's.
    """
    conn.execute(
        _INSERT_QUESTION_SQL,
        {
            "question_id": record.question_id,
            "workflow_id": record.workflow_id,
            "epic_id": record.epic_id,
            "node_id": record.node_id,
            "attempt": record.attempt,
            "question_text": record.question_text,
            "message_id": record.message_id,
            "sent_at": record.sent_at,
            "expires_at": record.expires_at,
            "resolution": record.resolution,
            "answer_text": record.answer_text,
            "resolved_at": record.resolved_at,
        },
    )
    conn.commit()


def capture_message_id(conn: sqlite3.Connection, question_id: str, message_id: int) -> bool:
    """Record the Telegram message id the send returned (FR-008's prerequisite).

    Separate from the insert because the insert happens first, on purpose (R11):
    the row exists before the send, so the message id — the one fact about a
    question that can only be known after Telegram accepts it — is captured
    afterwards. True if a row was updated; False means the id is unknown to the
    store (a rebuilt database under a running epic), in which case the row's
    `message_id` stays NULL and a reply cannot thread to it.
    """
    cursor = conn.execute(
        "UPDATE questions SET message_id = ? WHERE question_id = ?",
        (message_id, question_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def get_question(conn: sqlite3.Connection, question_id: str) -> QuestionRecord | None:
    """One question by its id, or None if there is no such row.

    None rather than an exception: a reply that names a question the store has
    no record of is answered with a notice, not a crashed bridge service (US2).
    """
    row = conn.execute(
        f"{_SELECT_QUESTION_SQL} WHERE question_id = ?", (question_id,)
    ).fetchone()
    return None if row is None else _question_from_row(row)


def get_question_by_message_id(
    conn: sqlite3.Connection, message_id: int
) -> QuestionRecord | None:
    """One question by the Telegram message id the send returned (FR-008, US2).

    The reply-routing key: a free-text reply threads back to the message the
    factory sent, so the bridge looks the question up by `reply_to_message_id`
    rather than by recency. `message_id` is NULL until the message is delivered,
    so a reply to a message that never landed (or one the store has no record of)
    resolves to None and is answered with a notice, not a crashed poll loop.

    Distinct from `get_question` because the bridge never holds the question id
    — only the message id the operator replied to — and recency would route a
    reply to the wrong question when two are open (FR-008).
    """
    row = conn.execute(
        f"{_SELECT_QUESTION_SQL} WHERE message_id = ?", (message_id,)
    ).fetchone()
    return None if row is None else _question_from_row(row)


def pending_questions(conn: sqlite3.Connection) -> list[QuestionRecord]:
    """Every question still awaiting an answer, oldest first."""
    rows = conn.execute(
        f"{_SELECT_QUESTION_SQL} WHERE resolution IS NULL "
        "ORDER BY sent_at, question_id"
    ).fetchall()
    return [_question_from_row(row) for row in rows]


def resolve_question(
    conn: sqlite3.Connection,
    question_id: str,
    *,
    answer_text: str,
    resolved_at: str,
) -> bool:
    """Record the operator's reply (US2). True if this call is what resolved it.

    The guarded UPDATE settles the race between an answer and the question's own
    expiry (FR-004): whichever arrives second matches no rows and is told so,
    instead of overwriting a resolution already set. US2 owns this; it is here so
    the transition lives in the same store the send wrote to.
    """
    cursor = conn.execute(
        _QUESTION_TRANSITION_SQL,
        (ANSWERED, answer_text, resolved_at, question_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def expire_question(conn: sqlite3.Connection, question_id: str, *, resolved_at: str) -> bool:
    """Record the question's own window elapsing (FR-004). True if this call expired it.

    The one resolution no reply can produce, the same way `EXPIRED` is the one
    escalation resolution no button can produce. US2 owns the call; the
    transition is the store's.
    """
    cursor = conn.execute(
        _QUESTION_TRANSITION_SQL,
        (EXPIRED, None, resolved_at, question_id),
    )
    conn.commit()
    return cursor.rowcount == 1


def _question_from_row(row: tuple[Any, ...]) -> QuestionRecord:
    """Rebuild a record from a `_QUESTION_COLUMNS`-ordered row."""
    values = dict(zip(_QUESTION_COLUMNS, row))
    return QuestionRecord(
        question_id=values["question_id"],
        workflow_id=values["workflow_id"],
        epic_id=values["epic_id"],
        node_id=values["node_id"],
        attempt=values["attempt"],
        question_text=values["question_text"],
        message_id=values["message_id"],
        sent_at=values["sent_at"],
        expires_at=values["expires_at"],
        resolution=values["resolution"],
        answer_text=values["answer_text"],
        resolved_at=values["resolved_at"],
    )
