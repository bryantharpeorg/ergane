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
- **`(epic_id, node_id, attempt, form, dispatch)` is the upsert key.** Temporal
  runs `record_verification` at least once, so a re-run must land on the first
  run's row. The uniqueness is structural, which makes "one row per attempt per
  form per dispatch" a property of the schema rather than of the caller's care.
  `form` is in the key because one attempt can be verified both as a node's
  built-in phase and by an explicit verifier node (FR-002). `dispatch` is in it
  since 117-US1, because without it the two things the key could not tell apart
  were a *retry* and a *re-dispatch*: a node dispatched again started over at
  attempt 1 and overwrote the first dispatch's evidence, which is exactly the
  record a post-mortem of a killed build begins from. A retried activity carries
  the run id of the workflow that scheduled it, so adding the dispatch preserves
  at-least-once idempotence exactly rather than trading it away.
- **An escalation makes exactly one terminal transition.** Both
  `resolve_escalation` and `expire_escalation` are a single UPDATE guarded by
  `WHERE resolution IS NULL`, and report what SQLite did rather than checking
  first and writing second — the bridge's button press and the workflow's
  timeout race by design (R12), and a read-then-write would let both win. A
  losing caller gets `False`, not an exception: a double-tapped button and a
  redelivered activity are ordinary, not errors.
- **The readers group by dispatch.** Since 117-US3 every read here returns a
  node's builds oldest first and each build's attempts together, because the
  rows US1 stopped destroying were still being handed back interleaved at every
  attempt number two dispatches shared. The order is the dispatch's earliest
  `finished_at` and never the row id: ids are minted at insert, and the rows a
  pre-US1 re-dispatch overwrote kept the ids of the build it replaced. Inside
  one dispatch nothing moved — `(attempt, form)`, as since 002 — because a node
  dispatched once must read exactly as it always has (FR-009).
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
import os
import sqlite3
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExternalCompletionCount:
    """The measured external-completion count for a whole corpus.

    `total` is the number of distinct accepted completions recorded.
    `by_spec` maps each epic_id to how many of those completions belong to it.
    `measured` is always True when this value is returned by the store: it
    distinguishes "0 because the counter checked" from "0 because the counter
    was never asked" (035-US3, FR-008).
    `target` is zero: the number this feature exists to drive to zero, stated
    alongside the count so a first-time reader knows what the number means.
    """

    total: int
    by_spec: dict[str, int]
    measured: bool = True
    target: int = 0

from factory.env import (
    ERGANE_EVIDENCE_STORE_ALLOW_REAL_ENV,
    FACTORY_EVIDENCE_STORE_ALLOW_REAL_ENV,
    resolve_env_flag,
)
from factory.mergequeue.models import CheckFailure
from factory.verify.models import (
    DiffAbridgement,
    DiffFileSize,
    DiffSizeRefusal,
    EscalationChoice,
    EscalationRecord,
    GateContradiction,
    GateResult,
    GateStatus,
    HygieneViolation,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    QuestionRecord,
    UNKNOWN_BASE_REF,
    UNKNOWN_BUILDER,
    UNKNOWN_DISPATCH,
    VerificationForm,
    VerificationResult,
)

#: Bumping this means the DDL below changed shape and existing stores need a
#: migration path. Recorded in the database so a reader can tell.
#:
#: 3 (041-US2): `escalations.check_evidence`. Every store in existence was
#: written at 2, so `_migrate` below adds the column in place rather than
#: assuming a fresh database — the first thing the factory does with a store is
#: `SELECT` the escalation columns by name, and a deployment answering `no such
#: column` would have lost the escalation channel outright.
#:
#: 5 (035-US3): `external_completion_counts` table. Counts every accepted
#: external completion idempotently per (epic_id, node_id, branch, provenance).
#:
#: 6 (023-US4): `verification_results.loop_digest` and `.loop_summary`. Additive
#: text columns; pre-023 rows read as NULL, never backfilled.
#:
#: 7 (068-US2): `escalations.resolution` admits `KILL_EPIC`. The only migration
#: here that is not additive — SQLite cannot alter a CHECK — so `_migrate`
#: rebuilds the table. It has to run: a store whose constraint predates the
#: button rejects the settling write and leaves the escalation pending.
#:
#: 8 (118-US2): `verification_results.base_ref` — the base the verdict was
#: measured against. Additive; every row written before it reads
#: `UNKNOWN_BASE_REF`, never a backfilled guess.
#:
#: 9 (095-US2): `escalations.default_choice` — the fail-safe default applied on
#: silence, which varies with the escalation's cause. Additive; NULL for every
#: row written before it, which reads as the ordinary default (KILL).
#:
#: 10 (116-US3): `verification_results.gate_contradictions` — the judge findings
#: this attempt did not charge the node for, and the measurements they
#: contradicted. Additive; NULL for every row written before it, which reads as
#: the empty tuple. The sibling fact, whether the judge was shown the gate
#: results at all, needs no column: it rides inside the `judge_verdict` JSON,
#: where it belongs to the verdict rather than to the row.
#:
#: 11 (117-US1): `verification_results.dispatch`, and the UNIQUE constraint it
#: joins. The second migration here that is not additive — SQLite cannot drop a
#: UNIQUE constraint any more than it can widen a CHECK — so `_migrate` rebuilds
#: the table. It has to run: without it a re-dispatched node keeps overwriting
#: its own history. Rows copied across carry `UNKNOWN_DISPATCH`, never NULL.
#:
#: 12 (117-US2): `verification_results.persona`, `.model_alias` and `.route` —
#: who built the attempt. Additive, and applied *after* the rebuild above, which
#: is the only order that leaves a migrated store column-for-column identical to
#: a fresh one. Every row written before them reads `UNKNOWN_BUILDER`, never a
#: backfilled guess: the registry has moved on, so a persona looked up today
#: would answer for the wrong model.
SCHEMA_VERSION = 12

#: R10: how long a writer waits out another writer's lock before giving up. Long
#: enough to absorb a concurrent recorder, short enough that a genuinely wedged
#: store fails the activity instead of hanging it.
BUSY_TIMEOUT_MS = 5000

#: The terminal `resolution` that no button can produce — written only by the
#: workflow's timeout path, which is why `EscalationRecord.resolution` is typed
#: `EscalationChoice | str | None` rather than just the enum.
EXPIRED = "EXPIRED"

#: Modern operator acknowledgment variable. When set, the store guard in
#: `connect()` permits opening a real evidence-store path while a test is running.
EVIDENCE_STORE_ALLOW_REAL_ENV = "ERGANE_EVIDENCE_STORE_ALLOW_REAL"

#: Legacy name still honored during the rename.
FACTORY_EVIDENCE_STORE_ALLOW_REAL_ENV = FACTORY_EVIDENCE_STORE_ALLOW_REAL_ENV

#: Finding key the guard names when it refuses an out-of-tmp store during a test.
#: Matches the finding the spec records.
TEST_SUITE_STORE_ISOLATION_FINDING = (
    "hardening/test-suite-writes-to-the-live-evidence-store"
)


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
    provenance        TEXT,              -- 035-US1: non-NULL for externally-completed work
    -- 023-US4: resolved loop configuration, carried with every verdict (FR-010).
    -- NULL for rows written before this feature; additive, never backfilled.
    loop_digest       TEXT,
    loop_summary      TEXT,
    -- 118-US2: the base the node's worktree was pinned to, so a verdict names
    -- what it was measured against (FR-006). NULL for rows written before this
    -- feature, read back as `UNKNOWN_BASE_REF`; additive, never backfilled.
    base_ref          TEXT,
    -- 116-US3: the judge findings this attempt did not charge the node for, and
    -- the recorded gate each one contradicted (JSON: list[GateContradiction]).
    -- NULL for rows written before this feature, read back as the empty tuple;
    -- additive, never backfilled. Without it a PASS composed over a judge that
    -- returned FAIL reads, on the row alone, as a composer that ignored its
    -- judge.
    gate_contradictions TEXT,
    -- 117-US1: the interpreter run that produced this attempt, and part of the
    -- upsert key. Last in the table because a store written before it gets the
    -- column appended, and a migrated store must have the same column order as
    -- a fresh one. NOT NULL with a reserved default rather than nullable: a
    -- NULL here is distinct from every other NULL in a UNIQUE index, which
    -- would key every unnamed row on itself and disable the idempotence below.
    dispatch          TEXT    NOT NULL DEFAULT '<unknown>' CHECK (dispatch <> ''),
    -- 117-US2: who built this attempt — the persona the rung selected, the alias
    -- it was dispatched under and the credential path it ran through (FR-005).
    -- Filled from the routing that dispatched the attempt, never re-derived from
    -- the persona at write time: the debugger rung relabels the persona without
    -- re-resolving the alias (FR-006). NULL for rows written before these
    -- columns, read back as `UNKNOWN_BUILDER`; additive, never backfilled.
    -- After `dispatch` because ALTER TABLE ADD COLUMN appends and a migrated
    -- store must have the same column order as a fresh one.
    persona           TEXT,
    model_alias       TEXT,
    route             TEXT,
    UNIQUE (epic_id, node_id, attempt, form, dispatch)   -- upsert key (record_verification)
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
    resolution     TEXT CHECK (resolution IN ('RETRY', 'KILL', 'PAUSE_EPIC', 'KILL_EPIC', 'EXPIRED')),
    resolved_at    TEXT,
    resolved_via   TEXT CHECK (resolved_via IN ('BUTTON', 'TIMEOUT')),
    -- 041-US2: the failing merge-queue checks the escalation was raised over
    -- (JSON: list[CheckFailure]). Written since 025 and read since never: the
    -- column did not exist, so every read-back handed the caller an empty
    -- tuple. Last in the table because ALTER TABLE ADD COLUMN appends, and a
    -- migrated store must have the same column order as a fresh one.
    check_evidence TEXT NOT NULL DEFAULT '[]',
    -- 095-US2: the fail-safe default applied on silence, which varies with the
    -- escalation's cause. NULL means the ordinary default (KILL); an
    -- authentication escalation records PAUSE_EPIC here.
    default_choice TEXT,
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

-- 035-US1: every external-completion signal the workflow receives, accepted or
-- refused. The signal is buffered by the workflow and validated at the ladder
-- decision point, so this log records what happened rather than what was sent.
CREATE TABLE IF NOT EXISTS external_completion_signals (
    id          INTEGER PRIMARY KEY,
    epic_id     TEXT    NOT NULL CHECK (epic_id <> ''),
    node_id     TEXT    NOT NULL CHECK (node_id <> ''),
    branch      TEXT    NOT NULL CHECK (branch <> ''),
    provenance  TEXT    NOT NULL CHECK (provenance <> ''),
    accepted    INTEGER NOT NULL DEFAULT 0 CHECK (accepted IN (0, 1)),
    reason      TEXT,
    recorded_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_extcomp_epic_node ON external_completion_signals (epic_id, node_id);

-- 035-US3: a durable counter of accepted external completions. Keyed by the
-- completion identity (epic, node, branch, provenance) so a repeat signal is
-- recorded once, not twice — the count is evidence of a trend, and a
-- double-count would invent one.
CREATE TABLE IF NOT EXISTS external_completion_counts (
    epic_id     TEXT    NOT NULL CHECK (epic_id <> ''),
    node_id     TEXT    NOT NULL CHECK (node_id <> ''),
    branch      TEXT    NOT NULL CHECK (branch <> ''),
    provenance  TEXT    NOT NULL CHECK (provenance <> ''),
    recorded_at TEXT    NOT NULL,
    PRIMARY KEY (epic_id, node_id, branch, provenance)
);

CREATE INDEX IF NOT EXISTS idx_extcomp_counts_epic ON external_completion_counts (epic_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the evidence store at `path`, creating file, directories and schema.

    Callers get a connection they own for the duration of one activity
    invocation (R10) and are responsible for closing.
    """
    location = Path(path)

    # Defense in depth: while a pytest sentinel is present, refuse to construct
    # the store outside the process's tmp tree unless the operator has explicitly
    # acknowledged the risk. This is the enforcement behind the session fixture's
    # convention (US1), and it fires before any filesystem side effect.
    #
    # Production paths (worker, notify service, CLI) do not set PYTEST_CURRENT_TEST,
    # so they are byte-identical to the pre-guard behavior.
    if os.environ.get("PYTEST_CURRENT_TEST") and not resolve_env_flag(
        ERGANE_EVIDENCE_STORE_ALLOW_REAL_ENV,
        FACTORY_EVIDENCE_STORE_ALLOW_REAL_ENV,
    ):
        tmp_root = Path(tempfile.gettempdir()).resolve()
        try:
            Path(location).resolve().relative_to(tmp_root)
        except ValueError:
            raise RuntimeError(
                f"refusing to open evidence store at {location}: "
                f"test-time writes must stay under the tmp tree "
                f"({TEST_SUITE_STORE_ISOLATION_FINDING})"
            ) from None

    location.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(location)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    _bootstrap_schema(conn)
    return conn


def connect_readonly(path: str | Path) -> sqlite3.Connection:
    """Open an existing evidence store for reading, and only for reading.

    `connect` above is the writer's door: it creates the parent directory, the
    file, and the schema. A reporting caller must not do any of that (046
    FR-002), so this one opens the same file through SQLite's `mode=ro` URI,
    where a write is refused by the driver rather than by the caller's care.
    Nothing here bootstraps the schema: a store that has never been written has
    no rows to report and the caller is expected to check the file exists first.
    """
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def _bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Apply the DDL, migrate what already exists, and stamp the version.

    Idempotent across reconnects, and — since a store that predates a column is
    the normal case rather than the exotic one — idempotent across versions too.
    """
    conn.executescript(_SCHEMA_DDL)
    _migrate(conn)
    recorded = conn.execute("SELECT version FROM schema_version").fetchone()
    if recorded is None:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
    elif int(recorded[0]) < SCHEMA_VERSION:
        # The migrations above brought it up to date; say so, so a reader can
        # tell. A store already at or beyond this version is left alone: an
        # older ergane opening a newer store must not stamp it backwards.
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    conn.commit()


#: The `resolution` constraint every store in existence carries, and 068-US2's
#: widening of it. `_SCHEMA_DDL` has spelled these since 008 and SQLite records
#: the creating text verbatim, so the migration rewrites the recorded DDL rather
#: than restating the table: no second column list, nothing to drift.
_OLD_RESOLUTIONS = "'RETRY', 'KILL', 'PAUSE_EPIC', 'EXPIRED'"
_NEW_RESOLUTIONS = "'RETRY', 'KILL', 'PAUSE_EPIC', 'KILL_EPIC', 'EXPIRED'"


def _escalations_ddl(conn: sqlite3.Connection) -> str | None:
    """The text SQLite recorded when this store's `escalations` table was made."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='escalations'"
    ).fetchone()
    return None if row is None else (row[0] or "")


def _widen_escalation_resolutions(conn: sqlite3.Connection) -> None:
    """Rebuild `escalations` so `resolution` admits `KILL_EPIC` (068-US2).

    `ALTER TABLE` cannot widen a CHECK, so: new table, rows copied, old dropped,
    new renamed, indexes recreated. The new table is the old one's own recorded
    DDL with the constraint rewritten, so nothing restates a column list — a
    rebuild that guessed the shape would be the one migration that could
    silently drop a column. A store whose DDL does not carry the old constraint
    verbatim is left alone rather than guessed at.
    """
    recorded = _escalations_ddl(conn)
    if not recorded or _OLD_RESOLUTIONS not in recorded:
        return
    rebuilt = recorded.replace(_OLD_RESOLUTIONS, _NEW_RESOLUTIONS)
    # One replacement, and the table name is the first occurrence: no column is
    # named `escalations`, so nothing else in the DDL can match.
    rebuilt = rebuilt.replace("escalations", "escalations_v7", 1)
    columns = ", ".join(
        row[1] for row in conn.execute("PRAGMA table_info(escalations)")
    )
    conn.executescript(
        f"{rebuilt};\n"
        f"INSERT INTO escalations_v7 ({columns}) SELECT {columns} FROM escalations;\n"
        "DROP TABLE escalations;\n"
        "ALTER TABLE escalations_v7 RENAME TO escalations;\n"
        "CREATE INDEX IF NOT EXISTS idx_esc_pending ON escalations (resolution)"
        " WHERE resolution IS NULL;\n"
        "CREATE INDEX IF NOT EXISTS idx_esc_node ON escalations (epic_id, node_id);"
    )


#: The `verification_results` upsert key every store written before 117-US1
#: carries, and what it becomes. `_SCHEMA_DDL` has spelled the old one since 002
#: and SQLite records the creating text verbatim, so — exactly as with the
#: escalations rebuild above — the migration rewrites the recorded DDL rather
#: than restating the table. The replacement carries the new column *and* the
#: new constraint in one substitution, which puts `dispatch` last in the column
#: list (where `ALTER TABLE ADD COLUMN` would have put it, and where the fresh
#: DDL declares it) without any second column list to drift.
_OLD_RESULT_UNIQUE = "UNIQUE (epic_id, node_id, attempt, form)"
_NEW_RESULT_UNIQUE = (
    f"dispatch TEXT NOT NULL DEFAULT '{UNKNOWN_DISPATCH}' CHECK (dispatch <> ''),\n"
    "    UNIQUE (epic_id, node_id, attempt, form, dispatch)"
)


def _results_ddl(conn: sqlite3.Connection) -> str | None:
    """The text SQLite recorded when this store's results table was made."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='verification_results'"
    ).fetchone()
    return None if row is None else (row[0] or "")


def _add_dispatch_to_the_upsert_key(conn: sqlite3.Connection) -> None:
    """Rebuild `verification_results` so the dispatch joins its key (117-US1).

    `ALTER TABLE` can add the column but cannot touch the UNIQUE constraint, and
    a constraint left alone is the failure mode that passes every test written
    against a fresh store while the defect survives untouched in the field. So:
    new table, rows copied, old dropped, new renamed, indexes recreated — the
    shape `_widen_escalation_resolutions` already established here.

    Copied rows are given `UNKNOWN_DISPATCH` explicitly rather than left to the
    column default, because what they carry is the point (FR-004): they were
    written before dispatches were distinguished, they belong to one unnamed
    dispatch, and the next dispatch of the same node must land beside them
    rather than merge into them. NULL would not do it — SQLite reads NULLs as
    distinct in a UNIQUE index, so every historical row would key on itself.

    Run after the additive result-column migrations above, so the copy has every
    column. A store whose DDL does not carry the old constraint verbatim is left
    alone rather than guessed at: the read that follows names the missing column
    out loud, which is cheaper than a rebuild that invented a shape.
    """
    recorded = _results_ddl(conn)
    if not recorded or _OLD_RESULT_UNIQUE not in recorded:
        return
    rebuilt = recorded.replace(_OLD_RESULT_UNIQUE, _NEW_RESULT_UNIQUE)
    # One replacement, and the table name is the first occurrence: no column is
    # named `verification_results`, so nothing else in the DDL can match.
    rebuilt = rebuilt.replace(
        "verification_results", "verification_results_v11", 1
    )
    columns = ", ".join(
        row[1] for row in conn.execute("PRAGMA table_info(verification_results)")
    )
    conn.executescript(
        f"{rebuilt};\n"
        f"INSERT INTO verification_results_v11 ({columns}, dispatch) "
        f"SELECT {columns}, '{UNKNOWN_DISPATCH}' FROM verification_results;\n"
        "DROP TABLE verification_results;\n"
        "ALTER TABLE verification_results_v11 RENAME TO verification_results;\n"
        "CREATE INDEX IF NOT EXISTS idx_vr_epic"
        " ON verification_results (epic_id);\n"
        "CREATE INDEX IF NOT EXISTS idx_vr_node"
        " ON verification_results (epic_id, node_id);\n"
        "CREATE INDEX IF NOT EXISTS idx_vr_specref"
        " ON verification_results (spec_ref);\n"
        "CREATE INDEX IF NOT EXISTS idx_vr_verdict"
        " ON verification_results (verdict);"
    )


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a store written by an older ergane up to `SCHEMA_VERSION`.

    `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists, so
    the DDL above never adds a column to a store that has one — which is every
    store the factory has ever written. Each migration is therefore expressed as
    "add it if it is missing", keyed off `PRAGMA table_info` rather than off the
    recorded version, because a version number is a claim and the columns are
    the fact.
    """
    escalation_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(escalations)")
    }
    if escalation_columns and "check_evidence" not in escalation_columns:
        # 041-US2. NOT NULL with a default is what SQLite's ADD COLUMN accepts,
        # and `[]` is the right reading of a row written before the column
        # existed: nobody recorded evidence, not "evidence was empty".
        conn.execute(
            "ALTER TABLE escalations ADD COLUMN "
            "check_evidence TEXT NOT NULL DEFAULT '[]'"
        )
    if escalation_columns and "default_choice" not in escalation_columns:
        # 095-US2. NULL for every row written before the field existed, which
        # reads as the ordinary default (KILL) — the only honest reading of a
        # row from a run where the cause was not recorded.
        conn.execute(
            "ALTER TABLE escalations ADD COLUMN default_choice TEXT"
        )

    recorded = _escalations_ddl(conn)
    if recorded is not None and "KILL_EPIC" not in recorded:
        # 068-US2, keyed off the recorded constraint rather than off the version
        # number — a version is a claim and the schema is the fact. Run after
        # the `check_evidence` migration above, so the copy has every column.
        _widen_escalation_resolutions(conn)

    result_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(verification_results)")
    }
    if result_columns and "provenance" not in result_columns:
        # 035-US1: provenance is NULL for every row written before this feature.
        conn.execute(
            "ALTER TABLE verification_results ADD COLUMN provenance TEXT"
        )
    if result_columns and "loop_digest" not in result_columns:
        # 023-US4: loop_digest and loop_summary are NULL for pre-023 rows.
        conn.execute(
            "ALTER TABLE verification_results ADD COLUMN loop_digest TEXT"
        )
        conn.execute(
            "ALTER TABLE verification_results ADD COLUMN loop_summary TEXT"
        )
    if result_columns and "base_ref" not in result_columns:
        # 118-US2: NULL for every row written before the base was carried, and
        # left NULL — a backfill would have to invent the one value this column
        # exists to stop inventing. `_result_from_row` reads it as unknown.
        conn.execute(
            "ALTER TABLE verification_results ADD COLUMN base_ref TEXT"
        )
    if result_columns and "gate_contradictions" not in result_columns:
        # 116-US3: NULL for every row written before the check existed, and left
        # NULL. A backfill would have to re-run a matcher over stored reasoning
        # and write down what a composer *would* have decided, which is a
        # different fact from what it did decide. `_result_from_row` reads NULL
        # as the empty tuple.
        conn.execute(
            "ALTER TABLE verification_results ADD COLUMN gate_contradictions TEXT"
        )
    if result_columns and "dispatch" not in result_columns:
        # 117-US1, keyed off the column rather than off the version number, and
        # run last of the result migrations so the rebuild's copy carries every
        # column the ones above just added.
        _add_dispatch_to_the_upsert_key(conn)
    if result_columns and "persona" not in result_columns:
        # 117-US2, and the order is the whole trick (plan trap 2). These run
        # *after* the rebuild above, never before: `ALTER TABLE ADD COLUMN`
        # appends, the rebuild puts `dispatch` last, and a store that gained
        # these three first would come out of the rebuild with `dispatch` behind
        # them while a fresh store has it in front. `_RESULT_COLUMNS` is read
        # positionally, so a divergent order does not raise — it hands every
        # field of every row to the wrong attribute.
        #
        # NULL for every row written before them, and left NULL. A backfill
        # would have to read a persona registry that has since been re-pointed
        # at other models and write down what the attempt *would* run under
        # today, which is a different fact from what it ran under.
        # `_result_from_row` reads NULL as `UNKNOWN_BUILDER`.
        for column in ("persona", "model_alias", "route"):
            conn.execute(
                f"ALTER TABLE verification_results ADD COLUMN {column} TEXT"
            )

    extcomp_tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if extcomp_tables and "external_completion_signals" not in extcomp_tables:
        # 035-US1: the refusal/acceptance log is a new table, not a column.
        conn.execute(
            """
            CREATE TABLE external_completion_signals (
                id          INTEGER PRIMARY KEY,
                epic_id     TEXT    NOT NULL CHECK (epic_id <> ''),
                node_id     TEXT    NOT NULL CHECK (node_id <> ''),
                branch      TEXT    NOT NULL CHECK (branch <> ''),
                provenance  TEXT    NOT NULL CHECK (provenance <> ''),
                accepted    INTEGER NOT NULL DEFAULT 0 CHECK (accepted IN (0, 1)),
                reason      TEXT,
                recorded_at TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX idx_extcomp_epic_node "
            "ON external_completion_signals (epic_id, node_id)"
        )

    if extcomp_tables and "external_completion_counts" not in extcomp_tables:
        # 035-US3: the counter table arrives on stores that already exist.
        conn.execute(
            """
            CREATE TABLE external_completion_counts (
                epic_id     TEXT    NOT NULL CHECK (epic_id <> ''),
                node_id     TEXT    NOT NULL CHECK (node_id <> ''),
                branch      TEXT    NOT NULL CHECK (branch <> ''),
                provenance  TEXT    NOT NULL CHECK (provenance <> ''),
                recorded_at TEXT    NOT NULL,
                PRIMARY KEY (epic_id, node_id, branch, provenance)
            )
            """
        )
        conn.execute(
            "CREATE INDEX idx_extcomp_counts_epic "
            "ON external_completion_counts (epic_id)"
        )


# --- verification results ---------------------------------------------------

#: The columns identifying one verification — the ON CONFLICT target, and what a
#: re-run matches on rather than overwrites. `dispatch` is the last of them
#: (117-US1): appended rather than prefixed, so the index still serves the
#: `(epic_id, node_id, ...)` prefix scans the canonical queries read through.
_RESULT_KEY = ("epic_id", "node_id", "attempt", "form", "dispatch")

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
    "provenance",
    "loop_digest",
    "loop_summary",
    "base_ref",
    "gate_contradictions",
    "dispatch",
    "persona",
    "model_alias",
    "route",
)

#: A re-run overwrites every column except the five it matched on: the second
#: recording of an attempt *of the same dispatch* is the current one, while a
#: second dispatch of the same attempt is a different row entirely.
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

_SELECT_RESULT_SQL = (
    f"SELECT {', '.join('r.' + column for column in _RESULT_COLUMNS)} "
    "FROM verification_results AS r"
)

#: When the dispatch a row belongs to first finished recording anything — the
#: clock a build is placed on, and the first ordering term of every reader below
#: (117-US3, FR-008).
#:
#: A row's id is minted when it is *inserted*, which is not when the attempt it
#: records ran: a delivery that failed once arrives whenever it succeeds, and in
#: every store written before 117-US1 the rows a second dispatch overwrote kept
#: the ids the first had minted. So id order is not chronological order, and
#: ordering a re-dispatched node by it interleaves the two builds at every
#: attempt number they share (plan trap 7).
#:
#: Correlated rather than a window function or a join, because it is read from
#: the same three columns `idx_vr_node` already covers and the alternative
#: shapes buy nothing at this table's size.
_DISPATCH_CLOCK_SQL = (
    "(SELECT MIN(d.finished_at) FROM verification_results AS d "
    "WHERE d.epic_id = r.epic_id AND d.node_id = r.node_id "
    "AND d.dispatch = r.dispatch)"
)

#: Which of two dispatches has the older row, for the one case the clock above
#: cannot decide: `finished_at` is stamped to the second, so two builds that
#: recorded their first attempt inside the same second tie on it.
#:
#: This is the only place an id is consulted and it is consulted *last* — when
#: the store's clock has no answer, the order rows were inserted in is the only
#: evidence left, and a uuid comparison (what any remaining tie-break would come
#: down to) is not evidence at all. Unique per group, so nothing follows it: two
#: dispatches of one node hold disjoint rows and cannot share a lowest id.
_DISPATCH_FIRST_ROW_SQL = (
    "(SELECT MIN(d.id) FROM verification_results AS d "
    "WHERE d.epic_id = r.epic_id AND d.node_id = r.node_id "
    "AND d.dispatch = r.dispatch)"
)

#: The order every reader returns: the builds oldest first, then the attempts of
#: each in the order they have read in since 002.
#:
#: `(attempt, form)` *within* a dispatch rather than the row's own stamps, and
#: that is FR-009 rather than an economy. One attempt can be verified twice —
#: as the node's built-in phase and by an explicit verifier node — and the NODE
#: form finishes after the PHASE form it re-checks, so a stamps-first ordering
#: would hand that pair back reversed from every reading since 002. Inside one
#: dispatch the attempts are sequential anyway, so this *is* write order; what
#: it refuses is to reorder a single-dispatch node, which is what `node_history`
#: and `attempt_timings` are read by name for.
_DISPATCH_ORDER_SQL = (
    f"{_DISPATCH_CLOCK_SQL}, {_DISPATCH_FIRST_ROW_SQL}, r.attempt, r.form"
)


@dataclass(frozen=True)
class DispatchGroup:
    """One dispatch's attempts, in the order the reader returned them.

    `dispatch` is the interpreter run that produced them, or `UNKNOWN_DISPATCH`
    for the one unnamed dispatch every row written before 117-US1 belongs to.
    """

    dispatch: str
    results: tuple[VerificationResult, ...]


def dispatch_groups(results: Sequence[VerificationResult]) -> list[DispatchGroup]:
    """Rows a reader already returned, split into the builds that wrote them.

    A grouping over rows in hand, not a second question for the store: US3 makes
    the existing readers able to tell two dispatches apart and adds no query
    surface. It splits at each change of `(node_id, dispatch)` rather than
    collecting by value, which is what keeps it faithful to the order it was
    handed — the readers return each build's rows contiguously, and a caller
    that sorted them again would be deciding the order a second time, by its own
    rule.
    """
    groups: list[DispatchGroup] = []
    current: list[VerificationResult] = []
    for result in results:
        if current and (result.node_id, result.dispatch) != (
            current[0].node_id,
            current[0].dispatch,
        ):
            groups.append(
                DispatchGroup(dispatch=current[0].dispatch, results=tuple(current))
            )
            current = []
        current.append(result)
    if current:
        groups.append(
            DispatchGroup(dispatch=current[0].dispatch, results=tuple(current))
        )
    return groups


def upsert_result(conn: sqlite3.Connection, result: VerificationResult) -> int:
    """Record one attempt's evidence, returning its stable row id.

    Keyed on `(epic_id, node_id, attempt, form, dispatch)`: a
    `record_verification` that runs a second time *within one dispatch* updates
    the row the first one wrote instead of adding another, so the returned id is
    stable across Temporal's redeliveries. A second dispatch of the same node is
    a different key and gets its own rows, which is what keeps a killed build's
    evidence readable after the next one has run (117-US1).
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
    """Every verification of one node, dispatch by dispatch and oldest first.

    The canonical per-node query from the DDL — what retry prompts quote and
    what an escalation's failure history is built from (SC-004, SC-005). Grouped
    by dispatch since 117-US3 (FR-008): the builds in the order they ran, then
    each build's attempts in the order they happened. A node dispatched once —
    which is nearly all of them — reads exactly as it read before, because its
    rows are one group and `_DISPATCH_ORDER_SQL` orders inside a group the way
    this query always did (FR-009).

    Ordering by attempt alone was what made a re-dispatched node illegible: the
    two builds interleaved at every attempt number they shared, so five rows
    read as one build of five attempts rather than three and then two.
    """
    rows = conn.execute(
        f"{_SELECT_RESULT_SQL} WHERE r.epic_id = ? AND r.node_id = ? "
        f"ORDER BY {_DISPATCH_ORDER_SQL}",
        (epic_id, node_id),
    ).fetchall()

    return [_result_from_row(row) for row in rows]


def epic_history(conn: sqlite3.Connection, epic_id: str) -> list[VerificationResult]:
    """Every verification of one epic, node by node and oldest attempt first.

    `node_history` widened by one column of the same key, because the operator
    reading an epic's verdicts does not hold its node ids — they are in the
    compiled graph and in Temporal, and this read exists for the moment both are
    gone. Node by node, then dispatch by dispatch within each (117-US3), so a
    re-run of the same query prints the same report and a node built twice
    prints as two builds.
    """
    rows = conn.execute(
        f"{_SELECT_RESULT_SQL} WHERE r.epic_id = ? "
        f"ORDER BY r.node_id, {_DISPATCH_ORDER_SQL}",
        (epic_id,),
    ).fetchall()

    return [_result_from_row(row) for row in rows]


@dataclass(frozen=True)
class AttemptTiming:
    """One recorded verification, reduced to what a pace report needs.

    `started_at`/`finished_at` bracket *one verification*, not one story: the
    dispatch-to-verification-start interval and merge-queue time are not in this
    table at all. A caller reporting these as anything other than the wall-time
    of an attempt's verification is reporting something the store cannot support
    (046 plan trap 5).
    """

    node_id: str
    attempt: int
    form: str
    verdict: str
    started_at: str
    finished_at: str


_SELECT_TIMING_SQL = (
    "SELECT r.node_id, r.attempt, r.form, r.verdict, r.started_at, r.finished_at "
    "FROM verification_results AS r WHERE r.epic_id = ? "
    f"ORDER BY r.node_id, {_DISPATCH_ORDER_SQL}"
)


def attempt_timings(conn: sqlite3.Connection, epic_id: str) -> list[AttemptTiming]:
    """Every recorded verification of one epic, in a stable reporting order.

    The narrow sibling of `node_history`: that one rebuilds the whole evidence
    bundle for a single node because a retry prompt quotes it; this one spans an
    epic and reads six columns, because a status report has no use for a gate's
    output tail and should not pay to decode one.

    It keeps its sibling's order, dispatch grouping included (117-US3): the six
    columns do not carry the dispatch, so a pace report reading these rows
    interleaved would put a re-dispatched node's attempts in an order no reading
    of the same rows through `node_history` agrees with.
    """
    rows = conn.execute(_SELECT_TIMING_SQL, (epic_id,)).fetchall()
    return [
        AttemptTiming(
            node_id=row[0],
            attempt=int(row[1]),
            form=str(row[2]),
            verdict=str(row[3]),
            started_at=str(row[4]),
            finished_at=str(row[5]),
        )
        for row in rows
    ]


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
        "provenance": result.provenance,
        "loop_digest": result.loop_digest,
        "loop_summary": result.loop_summary,
        # 118-US2: the sentinel is a reading, not a measurement, so it is stored
        # as the NULL it means. Writing `<unknown>` into the column would make a
        # row that never had a base indistinguishable in SQL from one that did.
        "base_ref": (
            None if result.base_ref == UNKNOWN_BASE_REF else result.base_ref
        ),
        # 116-US3: written whichever way it came out. `[]` is "the check ran and
        # found nothing", which is not the same fact as the NULL a row written
        # before the check existed carries — the dataclass has one spelling for
        # both, but SQL does not have to lose the distinction on the way in.
        "gate_contradictions": json.dumps(
            [
                _contradiction_to_dict(contradiction)
                for contradiction in result.gate_contradictions
            ]
        ),
        # 117-US1: written literally, sentinel included. Unlike `base_ref` above
        # this one is part of the key, and a NULL in a UNIQUE index is distinct
        # from every other NULL — an unnamed dispatch stored as NULL would key
        # each of its rows on itself and lose the idempotence the upsert is for.
        "dispatch": result.dispatch or UNKNOWN_DISPATCH,
        # 117-US2: the sentinel is a reading rather than a measurement, so it is
        # stored as the NULL it means — the `base_ref` treatment, and for the
        # same reason: writing `<unknown>` into the column would make a row
        # nobody recorded a builder for indistinguishable, in SQL, from one that
        # recorded a persona literally named that. None of the three is part of
        # the key, so unlike `dispatch` a NULL here costs no idempotence.
        **{
            column: (None if value == UNKNOWN_BUILDER else value)
            for column, value in (
                ("persona", result.persona),
                ("model_alias", result.model_alias),
                ("route", result.route),
            )
        },
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
        provenance=values["provenance"],
        loop_digest=values["loop_digest"],
        loop_summary=values["loop_summary"],
        # 118-US2: NULL is "nobody recorded a base for this attempt", which is
        # every row written before the column existed. It reads as the sentinel
        # rather than as a value, because a wrong base is worse than an
        # admitted gap — the audit this column exists for turns on the number.
        base_ref=(
            UNKNOWN_BASE_REF if values["base_ref"] is None else values["base_ref"]
        ),
        # 116-US3: NULL is a row the column predates, and it reads as the empty
        # tuple because that is the only spelling the record has for "no finding
        # was neutralised". Reading it as anything else would invent a
        # contradiction on rows composed before one could be detected.
        gate_contradictions=_contradictions_from_json(values["gate_contradictions"]),
        # 117-US1: NOT NULL in the schema, so what comes back is what was
        # written — the migration stamped every pre-117 row with the sentinel
        # rather than leaving a NULL for this read to interpret.
        dispatch=values["dispatch"],
        # 117-US2 (FR-007): NULL is "nobody recorded who built this", which is
        # every row written before these columns existed. It reads as one
        # sentinel value rather than as None or `""` — a renderer prints the
        # first as nothing and the second like a persona whose name is empty,
        # and a human reads either as a fact about the build.
        persona=_builder_or_unknown(values["persona"]),
        model_alias=_builder_or_unknown(values["model_alias"]),
        route=_builder_or_unknown(values["route"]),
    )


def _builder_or_unknown(value: Any) -> str:
    """One of US2's three builder columns, with NULL read as the admitted gap."""
    return UNKNOWN_BUILDER if value is None else str(value)


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
        "worktree_writes": list(gate.worktree_writes),
        "writes_declared": gate.writes_declared,
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
        # Rows written before 084 have no writes record, and absent means
        # "nothing recorded" rather than "unknown": the retry prompt is built
        # from stored evidence, so a field that skipped this codec would be lost
        # the moment the row was re-read.
        worktree_writes=tuple(data.get("worktree_writes", ())),
        # Absent means nobody declared this gate a writer, which is the honest
        # reading of any row written before the `writes:` key existed — and of
        # every row a manifest that declares nothing will ever produce.
        writes_declared=bool(data.get("writes_declared", False)),
    )


def _output_check_to_dict(check: OutputCheck) -> dict[str, Any]:
    return {
        "write_scope": check.write_scope,
        "has_diff": check.has_diff,
        "expected_artifacts": list(check.expected_artifacts),
        "artifacts_present": check.artifacts_present,
        "passed": check.passed,
        "hygiene_violations": [
            {"path": violation.path, "rule": violation.rule}
            for violation in check.hygiene_violations
        ],
        "size_refusal": _size_refusal_to_dict(check.size_refusal),
        "abridgement": _abridgement_to_dict(check.abridgement),
    }


def _size_refusal_to_dict(refusal: DiffSizeRefusal | None) -> dict[str, Any] | None:
    """The oversize record, or None — the shape a check that passed writes."""
    if refusal is None:
        return None
    return {
        "total_bytes": refusal.total_bytes,
        "limit_bytes": refusal.limit_bytes,
        "largest_files": [
            {"path": named.path, "size_bytes": named.size_bytes}
            for named in refusal.largest_files
        ],
    }


def _size_refusal_from_dict(data: dict[str, Any] | None) -> DiffSizeRefusal | None:
    """Read back what refused an oversized diff, if anything did.

    Rows written before 045 FR-003 have no key at all, and rows written since
    have `null` whenever the diff fit. Both mean the same thing — nothing was
    refused for size — which is why the caller reads the key with `.get()`.
    """
    if data is None:
        return None
    return DiffSizeRefusal(
        total_bytes=data["total_bytes"],
        limit_bytes=data["limit_bytes"],
        largest_files=[
            DiffFileSize(path=item["path"], size_bytes=item["size_bytes"])
            for item in data.get("largest_files", ())
        ],
    )


def _abridgement_to_dict(
    record: DiffAbridgement | None,
) -> dict[str, Any] | None:
    """How much of the diff the judge was shown, or None if nobody measured.

    The two measured numbers and nothing else. `abridged` and
    `over_limit_bytes` are properties derived from them, and a stored copy of a
    derived value is a second answer waiting to disagree with the first — the
    same reason `_size_refusal_to_dict` stores the total and the limit rather
    than "how far over".
    """
    if record is None:
        return None
    return {
        "total_bytes": record.total_bytes,
        "limit_bytes": record.limit_bytes,
    }


def _abridgement_from_dict(data: dict[str, Any] | None) -> DiffAbridgement | None:
    """Read back what the judge was shown, if anyone recorded it (092 FR-007).

    Rows written before this story have no key at all, and `None` is what they
    read back as: *nobody measured*, which is a different fact from "the judge
    saw the diff whole" and must never be collapsed into it. Since this story
    every check that weighed a diff writes one of the two real answers, so the
    absent key stops appearing rather than being reinterpreted.
    """
    if data is None:
        return None
    return DiffAbridgement(
        total_bytes=data["total_bytes"],
        limit_bytes=data["limit_bytes"],
    )


def _output_check_from_dict(data: dict[str, Any]) -> OutputCheck:
    return OutputCheck(
        write_scope=data["write_scope"],
        has_diff=data["has_diff"],
        expected_artifacts=data["expected_artifacts"],
        artifacts_present=data["artifacts_present"],
        passed=data["passed"],
        # Rows written before 045 FR-001 have no hygiene record; absent means
        # nothing was refused, which is the only honest reading of a row from a
        # run where nothing could be.
        hygiene_violations=[
            HygieneViolation(path=item["path"], rule=item["rule"])
            for item in data.get("hygiene_violations", ())
        ],
        # Likewise for 045 FR-003: an absent key is a row from a run where no
        # diff could be refused for its size, not one where a huge diff passed.
        size_refusal=_size_refusal_from_dict(data.get("size_refusal")),
        # And for 092 FR-007: absent is "nobody measured what the judge was
        # shown", which every row written before that story means and no row
        # written since can mean.
        abridgement=_abridgement_from_dict(data.get("abridgement")),
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
        # 116-US3 (FR-008), and written in both directions on purpose (plan
        # trap 8): a key present only when the answer is yes would, when the
        # answer is no, make the row byte-identical to one written before this
        # spec — which is exactly the silence the field exists to break.
        "gates_shown": judge.gates_shown,
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
        # Absent is every row in the store today, and it reads as False. Unlike
        # the other absences in this file that is a fact rather than a reading:
        # no prompt assembled before 116-US1 had a parameter to carry gate
        # results through, so no verdict written before this key existed can
        # have been formed with them in front of it.
        gates_shown=bool(data.get("gates_shown", False)),
    )


def _contradiction_to_dict(contradiction: GateContradiction) -> dict[str, Any]:
    """One neutralised finding as stored text — longhand, like the other codecs.

    Written out rather than derived, for the reason `_check_evidence_json` gives:
    a field added to `GateContradiction` has to be added here too, and the
    alternative is a record that round-trips *almost* everything, quietly.
    """
    return {
        "scenario": contradiction.scenario,
        "gate": contradiction.gate,
        "recorded_status": GateStatus(contradiction.recorded_status).value,
        "claim": contradiction.claim,
    }


def _contradictions_from_json(stored: str | None) -> tuple[GateContradiction, ...]:
    """Read the neutralised findings back. `None` is a row the column predates.

    Rows written before 116-US3 have NULL in the column, and rows written since
    have `'[]'` whenever the judge contradicted nothing. Both arrive here as the
    empty tuple, because the record has one spelling for "no finding was
    neutralised" — the distinction the column keeps is for SQL, where a reader
    asking which attempts the check had even run on can still tell.
    """
    if not stored:
        return ()
    return tuple(
        GateContradiction(
            scenario=item["scenario"],
            gate=item["gate"],
            recorded_status=GateStatus(item["recorded_status"]),
            claim=item["claim"],
        )
        for item in json.loads(stored)
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
    "check_evidence",
    "default_choice",
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
            "check_evidence": _check_evidence_json(record.check_evidence),
            "default_choice": _default_choice_value(record.default_choice),
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


def _default_choice_value(choice: EscalationChoice | None) -> str | None:
    """The stored spelling of a fail-safe default, or `None` for the ordinary one."""
    return None if choice is None else EscalationChoice(choice).value


def _default_choice_from_value(value: str | None) -> EscalationChoice | None:
    """Read a fail-safe default back; `None` is the ordinary default (KILL)."""
    return None if value is None else EscalationChoice(value)


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
        check_evidence=_check_evidence_from_json(values["check_evidence"]),
        default_choice=_default_choice_from_value(values["default_choice"]),
    )


def _check_evidence_json(evidence: tuple[CheckFailure, ...]) -> str:
    """The failing checks as stored text — longhand, like the other codecs.

    Written out rather than derived so a field added to `CheckFailure` has to be
    added here too. The alternative is the defect this closes: a record that
    round-trips *almost* everything, quietly.
    """
    return json.dumps(
        [
            {
                "name": failure.name,
                "url": failure.url,
                "log_tail": failure.log_tail,
                "note": failure.note,
            }
            for failure in evidence
        ]
    )


def _check_evidence_from_json(stored: str | None) -> tuple[CheckFailure, ...]:
    """Read the failing checks back. `None` is a row the column predates.

    Rows written before 041-US2 have `'[]'` after the migration; a row read
    through a connection that somehow has no such column reads `None`. Both mean
    the same thing — nobody recorded evidence — which is the only honest reading
    of a row from a run where none could be recorded.
    """
    if not stored:
        return ()
    return tuple(
        CheckFailure(
            name=item["name"],
            url=item["url"],
            log_tail=item["log_tail"],
            note=item["note"],
        )
        for item in json.loads(stored)
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


def find_pending_question_by_attempt(
    conn: sqlite3.Connection,
    *,
    epic_id: str,
    node_id: str,
    attempt: int,
) -> QuestionRecord | None:
    """The unanswered question row for one (epic, node, attempt), or None.

    008-US3: the in-attempt ferry may ship a question mid-flight and then degrade
    to the marker path before an answer arrives. When the workflow then reaches
    the US1 send path, it asks the store — not the adapter result — whether a
    question for this attempt already exists, so it can reuse that row instead
    of paging the operator a second time. The store is the source of truth for
    "did the ferry already ask," which keeps D-018's hole at one signal: the
    marker. The ferry's question id is evidence in the store, never a second
    field on the adapter result.

    A pending question (resolution IS NULL) is the one a degrade would reuse; a
    question already ANSWERED belongs to an answered ferry window, where the
    agent resumed rather than degrading, so the US1 send path is never reached.
    """
    row = conn.execute(
        f"{_SELECT_QUESTION_SQL} "
        "WHERE epic_id = ? AND node_id = ? AND attempt = ? "
        "AND resolution IS NULL "
        "ORDER BY sent_at DESC, question_id DESC "
        "LIMIT 1",
        (epic_id, node_id, attempt),
    ).fetchone()
    return _question_from_row(row) if row is not None else None


def adopt_question(
    conn: sqlite3.Connection, question_id: str, *, workflow_id: str
) -> bool:
    """Point a pending question row at the workflow now waiting on it (041-US3).

    `workflow_id` is the reply-routing column both `CallbackBridge` and
    `ergane build answer` signal. A question the ferry shipped mid-flight names
    the *epic*; once the agent degrades to the marker path the waiter is a
    `QuestionWorkflow`, and a reply routed to the epic reaches no handler. Only
    the routing column moves, only while the row is pending, never the
    resolution — so this is no second writer of the transition (plan trap 10).
    """
    cursor = conn.execute(
        "UPDATE questions SET workflow_id = ? "
        "WHERE question_id = ? AND resolution IS NULL",
        (workflow_id, question_id),
    )
    conn.commit()
    return cursor.rowcount == 1


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


# --- external completion signals (035-US1) ----------------------------------

_EXTERNAL_COMPLETION_COLUMNS = (
    "epic_id",
    "node_id",
    "branch",
    "provenance",
    "accepted",
    "reason",
    "recorded_at",
)

_INSERT_EXTERNAL_COMPLETION_SQL = (
    f"INSERT INTO external_completion_signals ({', '.join(_EXTERNAL_COMPLETION_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _EXTERNAL_COMPLETION_COLUMNS)})"
)


def record_external_completion_signal(
    conn: sqlite3.Connection,
    *,
    epic_id: str,
    node_id: str,
    branch: str,
    provenance: str,
    accepted: bool,
    reason: str | None,
    recorded_at: str,
) -> int:
    """Log one external-completion signal decision, returning its row id.

    Both acceptances and refusals are recorded so the operator can audit what
    happened. A refusal carries a reason; an acceptance may leave it NULL.

    An accepted signal also records the completion in the durable counter.
    The counter is idempotent per (epic_id, node_id, branch, provenance): a
    repeat signal for the same completion lands on the same row rather than
    inventing a second occurrence (035-US3, plan.md trap 5).
    """
    conn.execute(
        _INSERT_EXTERNAL_COMPLETION_SQL,
        {
            "epic_id": epic_id,
            "node_id": node_id,
            "branch": branch,
            "provenance": provenance,
            "accepted": int(accepted),
            "reason": reason,
            "recorded_at": recorded_at,
        },
    )
    row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    if accepted:
        _record_external_completion_count(
            conn,
            epic_id=epic_id,
            node_id=node_id,
            branch=branch,
            provenance=provenance,
            recorded_at=recorded_at,
        )
    conn.commit()
    return row_id


#: 035-US3: the durable counter of accepted external completions.
#: Keyed by (epic_id, node_id, branch, provenance) so a repeat signal is a
#: no-op, not a second occurrence.
_EXTERNAL_COMPLETION_COUNT_COLUMNS = (
    "epic_id",
    "node_id",
    "branch",
    "provenance",
    "recorded_at",
)

_INSERT_EXTERNAL_COMPLETION_COUNT_SQL = (
    f"INSERT INTO external_completion_counts ({', '.join(_EXTERNAL_COMPLETION_COUNT_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _EXTERNAL_COMPLETION_COUNT_COLUMNS)}) "
    "ON CONFLICT (epic_id, node_id, branch, provenance) DO NOTHING"
)


def _record_external_completion_count(
    conn: sqlite3.Connection,
    *,
    epic_id: str,
    node_id: str,
    branch: str,
    provenance: str,
    recorded_at: str,
) -> None:
    """Record one accepted external completion in the durable counter.

    The unique constraint on (epic_id, node_id, branch, provenance) makes a
    repeat of the same completion a no-op, so a re-delivered signal or a
    re-run activity cannot inflate the count.
    """
    conn.execute(
        _INSERT_EXTERNAL_COMPLETION_COUNT_SQL,
        {
            "epic_id": epic_id,
            "node_id": node_id,
            "branch": branch,
            "provenance": provenance,
            "recorded_at": recorded_at,
        },
    )


def external_completion_count(conn: sqlite3.Connection) -> ExternalCompletionCount:
    """Read the durable external-completion count, total and per spec.

    A store that has never recorded an accepted completion returns an explicit
    zero with `measured=True`, so the absence of use is distinguishable from a
    broken or absent counter (035-US3, FR-008). The target is stated as zero.
    """
    rows = conn.execute(
        """
        SELECT epic_id, COUNT(*) AS n
        FROM external_completion_counts
        GROUP BY epic_id
        ORDER BY epic_id
        """
    ).fetchall()
    by_spec = {row[0]: row[1] for row in rows}
    total = sum(by_spec.values())
    return ExternalCompletionCount(total=total, by_spec=by_spec)
