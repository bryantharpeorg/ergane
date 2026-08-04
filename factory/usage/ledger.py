"""The factory's own record of what was spent, and the only writer to it.

The ledger is a published surface: FR-012 promises operators that the file they
open with `sqlite3` has the shape documented in `contracts/ledger-schema.sql`.
That promise is why the DDL below is a verbatim copy of the contract rather than
a paraphrase of it — `tests/test_ledger_schema.py` applies the contract file to a
scratch database and compares it, structure for structure, against what `connect`
creates. The two drift apart only over a failing test.

Three decisions carry the weight here:

- **WAL with a busy timeout (R6).** Teardowns run concurrently on the one host
  that owns the file; in rollback-journal mode they would serialize into
  `database is locked` on the single code path that must never drop a row
  (FR-002). Each activity invocation opens its own connection — no pool, no
  cross-task sharing — and `upsert_record` commits before returning, so a row is
  durable the moment the writer is told it was written.
- **`key_alias` is the idempotency key.** Temporal runs teardown at least once,
  so the second run must land on the first run's row. The uniqueness is
  structural (a UNIQUE column) and the write is an upsert on it, which makes
  "exactly one row per attempt" (SC-001) a property of the schema rather than of
  the caller's care.
- **Unknown stays unknown.** The token and spend columns are nullable so a
  fallback teardown can say "the proxy never told us" without inventing a 0
  (FR-005). This module writes `None` through untouched; the only conversions it
  performs are the two the storage layer forces — `bool` to the DDL's 0/1 flag,
  and `Termination` to its lowercase value.

Rollup queries (FR-006) arrive with T021; this module is bootstrap plus write.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from factory.usage.models import Termination, UsageRecord

#: Bumping this means the DDL below changed shape and existing ledgers need a
#: migration path. Recorded in the database so a reader can tell.
SCHEMA_VERSION = 1

#: R6: how long a writer waits out another writer's lock before giving up. Long
#: enough to absorb a concurrent teardown, short enough that a genuinely wedged
#: ledger fails the activity instead of hanging it.
BUSY_TIMEOUT_MS = 5000

#: Verbatim from `contracts/ledger-schema.sql` (FR-012). Every statement is
#: `IF NOT EXISTS`, so bootstrap is safe to run on every connect.
_SCHEMA_DDL = """
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
"""

#: The columns `upsert_record` writes, in DDL order. `id` is SQLite's to assign,
#: and re-teardown must not renumber the row it lands on.
_WRITABLE_COLUMNS = (
    "epic_id",
    "node_id",
    "attempt",
    "persona",
    "spec_ref",
    "key_alias",
    "prompt_tokens",
    "completion_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "request_count",
    "spend_usd",
    "final_usage_confirmed",
    "termination",
    "issued_at",
    "torn_down_at",
)

#: A rerun overwrites every column except the alias it matched on: the second
#: teardown's reading of the attempt is the current one, even when it is the
#: poorer, unconfirmed one (R3).
_UPSERT_SQL = (
    f"INSERT INTO usage_records ({', '.join(_WRITABLE_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _WRITABLE_COLUMNS)}) "
    "ON CONFLICT (key_alias) DO UPDATE SET "
    + ", ".join(
        f"{column} = excluded.{column}"
        for column in _WRITABLE_COLUMNS
        if column != "key_alias"
    )
)


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the ledger at `path`, creating file, directories and schema as needed.

    Callers get a connection they own for the duration of one activity
    invocation (R6) and are responsible for closing.
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
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def upsert_record(conn: sqlite3.Connection, record: UsageRecord) -> UsageRecord:
    """Write one attempt's usage, returning the record with its ledger `id`.

    Keyed on `record.key_alias`: a teardown that runs a second time updates the
    row the first one wrote instead of adding another (FR-002, SC-001), so the
    returned `id` is stable across reruns.
    """
    values = {column: getattr(record, column) for column in _WRITABLE_COLUMNS}
    values["final_usage_confirmed"] = int(record.final_usage_confirmed)
    values["termination"] = Termination(record.termination).value

    conn.execute(_UPSERT_SQL, values)
    row = conn.execute(
        "SELECT id FROM usage_records WHERE key_alias = ?", (record.key_alias,)
    ).fetchone()
    conn.commit()

    return replace(record, id=row[0])
