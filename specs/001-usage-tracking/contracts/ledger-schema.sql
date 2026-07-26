-- Ledger schema: the documented direct-SQL surface (FR-012).
-- SQLite, WAL mode. One row per node attempt teardown. Version 1.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    epic_id                TEXT    NOT NULL,
    node_id                TEXT    NOT NULL,
    attempt                INTEGER NOT NULL CHECK (attempt >= 1),
    persona                TEXT    NOT NULL,
    spec_ref               TEXT    NOT NULL,
    key_alias              TEXT    NOT NULL UNIQUE,          -- "{epic}:{node}:{attempt}"; idempotency guard
    prompt_tokens          INTEGER,                          -- NULL = unknown (never fabricated 0)
    completion_tokens      INTEGER,
    cache_read_tokens      INTEGER,                          -- NULL = metric absent from backend
    cache_write_tokens     INTEGER,
    request_count          INTEGER,
    spend_usd              REAL,                             -- NULL only if no snapshot ever taken
    final_usage_confirmed  INTEGER NOT NULL CHECK (final_usage_confirmed IN (0, 1)),
    termination            TEXT    NOT NULL CHECK (termination IN
                               ('completed', 'agent_error', 'timeout', 'killed')),
    issued_at              TEXT    NOT NULL,                 -- ISO 8601 UTC
    torn_down_at           TEXT    NOT NULL                  -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_usage_epic     ON usage_records (epic_id);
CREATE INDEX IF NOT EXISTS idx_usage_persona  ON usage_records (persona);
CREATE INDEX IF NOT EXISTS idx_usage_spec_ref ON usage_records (spec_ref);
CREATE INDEX IF NOT EXISTS idx_usage_attempt  ON usage_records (epic_id, node_id, attempt);

-- Canonical rollup shapes (FR-006). The CLI executes these; direct SQL users may too.

-- By persona within an epic:
--   SELECT persona,
--          SUM(prompt_tokens) AS prompt_tokens,
--          SUM(completion_tokens) AS completion_tokens,
--          SUM(cache_read_tokens) AS cache_read_tokens,
--          SUM(cache_write_tokens) AS cache_write_tokens,
--          SUM(request_count) AS requests,
--          SUM(spend_usd) AS spend_usd,
--          SUM(1 - final_usage_confirmed) AS unconfirmed_rows
--   FROM usage_records WHERE epic_id = :epic GROUP BY persona;

-- By spec_ref across epics (what did this piece of work cost?):
--   ... GROUP BY spec_ref;

-- Cost of retries (attempt ordinal >= 2):
--   ... WHERE attempt >= 2 GROUP BY persona;

-- Node totals (attempts aggregated):
--   ... GROUP BY epic_id, node_id;
