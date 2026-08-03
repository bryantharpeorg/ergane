-- Verification evidence store: .factory/verification.db
-- Owned by spec 002. Same operational pattern as the 001 usage ledger:
-- WAL mode, busy_timeout=5000, one connection per activity invocation,
-- single-INSERT/UPSERT transactions, single designated worker host.
-- This DDL is the documented direct-SQL surface (queryable by operators,
-- BI tools, and any future operations UI).

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
-- seeded with 1 on bootstrap

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

-- Canonical queries -----------------------------------------------------------

-- Failure history for one node (retry prompts, escalation summaries, SC-005):
--   SELECT attempt, form, verdict, gate_results, judge_verdict, criteria_drift
--   FROM verification_results
--   WHERE epic_id = :epic AND node_id = :node
--   ORDER BY attempt, form;

-- Verification health by epic:
--   SELECT epic_id,
--          COUNT(*)                                        AS verifications,
--          SUM(verdict = 'PASS')                           AS passed,
--          SUM(judge_unavailable)                          AS judge_unavailable,
--          SUM(criteria_drift)                             AS drifted
--   FROM verification_results GROUP BY epic_id;

-- Retry pressure by spec ref (pairs with 001's per-spec-ref cost rollup):
--   SELECT spec_ref, MAX(attempt) AS attempts, MIN(verdict = 'PASS') AS ever_failed
--   FROM verification_results GROUP BY spec_ref;

-- Pending escalations (bridge service + operator visibility):
--   SELECT escalation_id, epic_id, node_id, expires_at
--   FROM escalations WHERE resolution IS NULL;
