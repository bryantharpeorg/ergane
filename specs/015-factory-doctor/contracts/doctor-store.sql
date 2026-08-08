-- The doctor's findings ledger: .factory/doctor.db
--
-- Read by `factory-doctor list` and any operator with sqlite3; written only by
-- factory/doctor/store.py, whose _SCHEMA_DDL is a verbatim copy of this file —
-- the same contract-copy discipline as contracts/verification-store.sql, held
-- by a structure-for-structure test.
--
-- Identity is the finding key. `findings` holds current state (one row per
-- identity, upsert target for at-least-once reporting); `finding_events` holds
-- the recurrence trail (append-only, one row per observation). Severity and
-- status are closed sets held by the schema, so the arithmetic that computes
-- over them (list ordering, check exit codes, regression transitions) rests on
-- the schema rather than on caller care. (Wording matters: this header is
-- copied verbatim into a module-level DDL constant, and a non-docstring string
-- literal containing the D-021 sweep's vocabulary would fail
-- test_final_sweep.py.) Category is deliberately unconstrained:
-- taxonomy is open, grammar is closed (spec § Decision, call 5).

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    key           TEXT PRIMARY KEY,           -- category/slug, stable identity
    category      TEXT NOT NULL,              -- open taxonomy (prefix of key)
    severity      TEXT NOT NULL
        CHECK (severity IN ('critical', 'warning', 'info')),
    status        TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'promoted', 'resolved', 'regressed')),
    summary       TEXT NOT NULL,              -- latest report's summary
    refs          TEXT NOT NULL,              -- JSON array of file:line strings
    notes         TEXT,                       -- latest report's notes, nullable
    source        TEXT NOT NULL,              -- latest reporter: probe name,
                                              --   'operator', or audit id
    occurrences   INTEGER NOT NULL DEFAULT 1,
    first_seen    TEXT NOT NULL,              -- ISO-8601 UTC
    last_seen     TEXT NOT NULL,              -- ISO-8601 UTC
    promoted_spec TEXT,                       -- spec dir once promoted
    resolved_at   TEXT,                       -- ISO-8601 UTC, set on resolve
    resolution    TEXT                        -- reason, or the spec that landed
);

CREATE TABLE IF NOT EXISTS finding_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_key TEXT NOT NULL REFERENCES findings(key),
    seen_at     TEXT NOT NULL,                -- ISO-8601 UTC
    source      TEXT NOT NULL,
    severity    TEXT NOT NULL
        CHECK (severity IN ('critical', 'warning', 'info')),
    kind        TEXT NOT NULL
        CHECK (kind IN ('reported', 'promoted', 'resolved', 'regressed'))
);

CREATE INDEX IF NOT EXISTS idx_finding_events_key
    ON finding_events(finding_key, seen_at);
