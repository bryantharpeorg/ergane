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

Reading is the other half. `rollup` answers FR-006's five questions with one
grouped aggregate over this one table, and returns `contracts/cli.md`'s JSON
shape directly so the CLI renders rather than recomputes — which keeps the
never-fabricate rule in exactly one place, the SQL, where `SUM` over all-NULL
already means "nobody reported this".
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

from factory.usage.models import CodexUsageRecord, Termination, UsageRecord

#: Bumping this means the DDL below changed shape and existing ledgers need a
#: migration path. Recorded in the database so a reader can tell.
SCHEMA_VERSION = 4

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
    key_alias              TEXT    NOT NULL UNIQUE,          -- "{epic}:{node}:{attempt}:{persona}"; idempotency guard
    prompt_tokens          INTEGER,                          -- NULL = unknown (never fabricated 0)
    completion_tokens      INTEGER,
    cache_read_tokens      INTEGER,                          -- NULL = metric absent from backend
    cache_write_tokens     INTEGER,
    request_count          INTEGER,
    spend_usd              REAL,                             -- NULL only if no snapshot ever taken
    final_usage_confirmed  INTEGER NOT NULL CHECK (final_usage_confirmed IN (0, 1)),
    termination            TEXT    NOT NULL CHECK (termination IN
                               ('completed', 'agent_error', 'timeout', 'killed',
                                'question', 'auth_failure', 'pre_agent_failure')),
    issued_at              TEXT    NOT NULL,                 -- ISO 8601 UTC
    torn_down_at           TEXT    NOT NULL,                 -- ISO 8601 UTC
    usage_source           TEXT    NOT NULL DEFAULT 'legacy',
    usage_status           TEXT    NOT NULL DEFAULT 'legacy',
    cost_basis             TEXT    NOT NULL DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_usage_epic     ON usage_records (epic_id);
CREATE INDEX IF NOT EXISTS idx_usage_persona  ON usage_records (persona);
CREATE INDEX IF NOT EXISTS idx_usage_spec_ref ON usage_records (spec_ref);
CREATE INDEX IF NOT EXISTS idx_usage_attempt  ON usage_records (epic_id, node_id, attempt);

CREATE TABLE IF NOT EXISTS codex_usage_evidence (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    key_alias                TEXT    NOT NULL UNIQUE,
    input_tokens             INTEGER,
    cached_input_tokens      INTEGER,
    output_tokens            INTEGER,
    reasoning_output_tokens  INTEGER,
    source                   TEXT    NOT NULL,
    complete                 INTEGER NOT NULL CHECK (complete IN (0, 1)),
    reason                   TEXT
);
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
    "usage_source",
    "usage_status",
    "cost_basis",
)

#: upsert_record first preserves better prior measurements. Identity remains
#: stable while the latest teardown updates termination and timestamps.
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

_CODEX_WRITABLE_COLUMNS = (
    "key_alias",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "source",
    "complete",
    "reason",
)

_CODEX_UPSERT_SQL = (
    f"INSERT INTO codex_usage_evidence ({', '.join(_CODEX_WRITABLE_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in _CODEX_WRITABLE_COLUMNS)}) "
    "ON CONFLICT (key_alias) DO UPDATE SET "
    + ", ".join(
        f"{column} = excluded.{column}"
        for column in _CODEX_WRITABLE_COLUMNS
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
    """Apply the DDL, widen what already exists, and stamp the version.

    Idempotent across reconnects, and — since a ledger that predates a
    `termination` value is the normal case rather than the exotic one — across
    versions too (079-US3).
    """
    conn.executescript(_SCHEMA_DDL)
    _migrate(conn)
    recorded = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    if recorded == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.execute("UPDATE schema_version SET version = MAX(version, ?)", (SCHEMA_VERSION,))
    conn.commit()


#: The one constraint in `usage_records` that has widened since the table was
#: first written: 008 added `'question'` on 2026-08-07, 070 added
#: `'auth_failure'`, 095 added `'pre_agent_failure'`. None of them reached a
#: ledger that already existed, because every statement in `_SCHEMA_DDL` is
#: `IF NOT EXISTS` and that is a no-op on a table which is already there. The consequence is 079-US3's wedge: a node parks on an
#: operator question, `teardown_attempt` writes the row the park owes with
#: `termination='question'`, an older ledger's CHECK refuses it, the activity
#: fails, and the node is left `WAITING_OPERATOR` with the epic paused — a
#: symptom indistinguishable from a bug in the question branch itself.
#:
#: Keyed off the recorded constraint rather than off `SCHEMA_VERSION`, for
#: `factory/verify/store.py`'s reason: a version is a claim and the schema is the
#: fact. The value list is read out of `_SCHEMA_DDL` rather than restated here,
#: so the migration cannot drift from the DDL it migrates towards.
_TERMINATION_CHECK = re.compile(r"termination\s+IN\s*\(([^)]*)\)", re.IGNORECASE)


def _termination_values(ddl: str) -> str | None:
    """The `termination IN (...)` list of a DDL, whitespace collapsed to one line."""
    match = _TERMINATION_CHECK.search(ddl)
    return None if match is None else " ".join(match.group(1).split())


def _usage_records_ddl(conn: sqlite3.Connection) -> str | None:
    """The text SQLite recorded when this ledger's `usage_records` was made."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='usage_records'"
    ).fetchone()
    return None if row is None else (row[0] or "")


def _widen_terminations(conn: sqlite3.Connection) -> None:
    """Rebuild `usage_records` so `termination` admits every value the tree writes.

    `ALTER TABLE` cannot widen a CHECK, so: new table, rows copied, old dropped,
    new renamed, indexes recreated by re-running the DDL (every statement is
    `IF NOT EXISTS`, so it restores what `DROP TABLE` took and no-ops on the
    rest). The new table is the old one's own recorded DDL with the value list
    rewritten — no second column list, nothing to drift, and a rebuild that
    guessed the shape would be the one migration that could silently drop a
    column. `id` is copied with the rest, so a row keeps the identity an operator
    may already have quoted.
    """
    recorded = _usage_records_ddl(conn)
    current = _termination_values(_SCHEMA_DDL)
    if recorded is None or current is None:
        return
    match = _TERMINATION_CHECK.search(recorded)
    existing = _termination_values(recorded)
    if match is None or existing is None:
        # A ledger whose DDL does not carry this constraint verbatim is left
        # alone rather than guessed at.
        return
    if not _values(existing) < _values(current):
        # Equal is nothing to do; anything else means the ledger admits a value
        # this ergane does not, and an older ergane must never narrow a newer
        # store's constraint under it.
        return

    rebuilt = recorded[: match.start(1)] + current + recorded[match.end(1) :]
    # One replacement, and the table name is the first occurrence: no column is
    # named `usage_records`, so nothing else in the DDL can match.
    rebuilt = rebuilt.replace("usage_records", "usage_records_v3", 1)
    columns = ", ".join(
        row[1] for row in conn.execute("PRAGMA table_info(usage_records)")
    )
    conn.executescript(
        f"{rebuilt};\n"
        f"INSERT INTO usage_records_v3 ({columns}) SELECT {columns} FROM usage_records;\n"
        "DROP TABLE usage_records;\n"
        "ALTER TABLE usage_records_v3 RENAME TO usage_records;"
    )
    conn.executescript(_SCHEMA_DDL)


def _values(value_list: str) -> set[str]:
    """A CHECK's `IN` list as the set of values it admits."""
    return {value.strip() for value in value_list.split(",") if value.strip()}


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a ledger written by an older ergane up to the DDL above (079-US3)."""
    _widen_terminations(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(usage_records)")}
    for name, default in (("usage_source", "legacy"), ("usage_status", "legacy"), ("cost_basis", "unknown")):
        if name not in columns:
            conn.execute(f"ALTER TABLE usage_records ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")


def _usage_record_from_row(columns: tuple[str, ...], row: tuple[Any, ...]) -> UsageRecord:
    """Rebuild a domain record, converting SQLite's flag to its domain type."""
    return UsageRecord(**{
        **dict(zip(columns, row)),
        "final_usage_confirmed": bool(row[columns.index("final_usage_confirmed")]),
    })


def _codex_record_from_row(columns: tuple[str, ...], row: tuple[Any, ...]) -> CodexUsageRecord:
    """Rebuild corroboration, converting SQLite's flag to its domain type."""
    return CodexUsageRecord(**{
        **dict(zip(columns, row)),
        "complete": bool(row[columns.index("complete")]),
    })


def upsert_record(conn: sqlite3.Connection, record: UsageRecord) -> UsageRecord:
    """Write one attempt's usage, returning the record with its ledger `id`.

    Keyed on `record.key_alias`: a teardown that runs a second time updates the
    row the first one wrote instead of adding another (FR-002, SC-001), so the
    returned `id` is stable across reruns.
    """
    # An at-least-once teardown may run after revocation or a proxy outage.
    # Preserve better token evidence, and preserve independently measured cost.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    columns = ("id", *_WRITABLE_COLUMNS)
    previous = conn.execute(
        f"SELECT {', '.join(columns)} FROM usage_records WHERE key_alias = ?", (record.key_alias,)
    ).fetchone()
    if previous is not None:
        old = _usage_record_from_row(columns, previous)
        old_rank = _quality(old)
        new_rank = _quality(record)
        if old_rank > new_rank:
            record = replace(record, **{field: getattr(old, field) for field in (
                "prompt_tokens", "completion_tokens", "cache_read_tokens", "cache_write_tokens",
                "request_count", "final_usage_confirmed", "usage_source", "usage_status",
            )})
        if old.spend_usd is not None and (record.spend_usd is None or old_rank > new_rank):
            record = replace(record, spend_usd=old.spend_usd, cost_basis=old.cost_basis)

    values = {column: getattr(record, column) for column in _WRITABLE_COLUMNS}
    values["final_usage_confirmed"] = int(record.final_usage_confirmed)
    values["termination"] = Termination(record.termination).value
    conn.execute(_UPSERT_SQL, values)
    row = conn.execute("SELECT id FROM usage_records WHERE key_alias = ?", (record.key_alias,)).fetchone()
    conn.commit()
    return replace(record, id=row[0])


def _quality(record: UsageRecord) -> int:
    if record.usage_status == "complete":
        return 2
    return int(record.prompt_tokens is not None or record.completion_tokens is not None)


def upsert_codex_usage(
    conn: sqlite3.Connection, record: CodexUsageRecord
) -> CodexUsageRecord:
    """Write one attempt's separate CLI corroboration row.

    This table is not in `rollup`: it is evidence about the CLI's view, never a
    second amount to add to the gateway or subscription accounting row.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    columns = ("id", *_CODEX_WRITABLE_COLUMNS)
    previous = conn.execute(
        f"SELECT {', '.join(columns)} FROM codex_usage_evidence WHERE key_alias = ?",
        (record.key_alias,),
    ).fetchone()
    if previous is not None:
        old = _codex_record_from_row(columns, previous)
        if old.complete and not record.complete:
            record = replace(record, **{
                field: getattr(old, field)
                for field in _CODEX_WRITABLE_COLUMNS[1:]
            })
    values = {column: getattr(record, column) for column in _CODEX_WRITABLE_COLUMNS}
    values["complete"] = int(record.complete)
    conn.execute(_CODEX_UPSERT_SQL, values)
    row = conn.execute(
        "SELECT id FROM codex_usage_evidence WHERE key_alias = ?", (record.key_alias,)
    ).fetchone()
    conn.commit()
    return replace(record, id=row[0])



#: The dimensions FR-006 names, and the only values `--by` accepts: the CLI's
#: argparse choices are this tuple, so a dimension cannot exist in SQL but be
#: unreachable from the command line. Order is the order they are offered in.
ROLLUP_DIMENSIONS = ("persona", "epic", "spec-ref", "attempt", "node")

#: Each dimension's grouping expression. These are interpolated into SQL, which
#: is why `rollup` looks `by` up here rather than trusting it — the lookup *is*
#: the validation.
_GROUP_EXPRESSIONS = {
    "persona": "persona",
    "epic": "epic_id",
    "spec-ref": "spec_ref",
    "attempt": "attempt",
    # A node is only identified within its epic (cli.md), so two epics' `impl`
    # nodes stay apart while one node's attempts merge.
    "node": "epic_id || ':' || node_id",
}

#: The metric block of `contracts/cli.md`, as output field -> aggregate.
#:
#: Group aggregates use bare `SUM`s: a metric reported by some rows in the group
#: is summed over those rows, and a metric absent from every row stays `NULL`.
#: This is the existing FR-004/FR-005 contract for cache counters and the same
#: rule US1 extends to prompt, completion and request count.
#:
#: The grand totals are stricter: if any row in the filtered scope is unknown
#: for a token/request metric, the total for that metric is `NULL` rather than a
#: partial sum that looks complete (US1 scenario 5, trap 4). Spend and counts are
#: still summed across every row; `unconfirmed_rows` remains the flag for rows
#: whose token detail is missing.
_METRICS = (
    ("prompt_tokens", "SUM(prompt_tokens)"),
    ("completion_tokens", "SUM(completion_tokens)"),
    ("cache_read_tokens", "SUM(cache_read_tokens)"),
    ("cache_write_tokens", "SUM(cache_write_tokens)"),
    ("requests", "SUM(request_count)"),
    ("spend_usd", "SUM(spend_usd)"),
    ("rows", "COUNT(*)"),
    ("unconfirmed_rows", "COALESCE(SUM(1 - final_usage_confirmed), 0)"),
)

_METRIC_FIELDS = tuple(field for field, _ in _METRICS)
_METRIC_SELECT = ", ".join(expression for _, expression in _METRICS)

#: The same metric block for the totals query, where a partial answer is not an
#: honest answer. If any row in scope has `NULL` for one of the token or request
#: columns, the total for that column is `NULL` rather than the sum of the rows
#: that did report it. Cache counters keep their group-level partial-sum rule.
_TOTALS_METRICS = (
    ("prompt_tokens", "CASE WHEN COUNT(prompt_tokens) < COUNT(*) THEN NULL ELSE SUM(prompt_tokens) END"),
    ("completion_tokens", "CASE WHEN COUNT(completion_tokens) < COUNT(*) THEN NULL ELSE SUM(completion_tokens) END"),
    ("cache_read_tokens", "SUM(cache_read_tokens)"),
    ("cache_write_tokens", "SUM(cache_write_tokens)"),
    ("requests", "CASE WHEN COUNT(request_count) < COUNT(*) THEN NULL ELSE SUM(request_count) END"),
    ("spend_usd", "SUM(spend_usd)"),
    ("rows", "COUNT(*)"),
    ("unconfirmed_rows", "COALESCE(SUM(1 - final_usage_confirmed), 0)"),
)

_TOTALS_SELECT = ", ".join(expression for _, expression in _TOTALS_METRICS)


def rollup(
    conn: sqlite3.Connection,
    *,
    by: str,
    epic: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Aggregate the ledger along one dimension (FR-006).

    Returns `contracts/cli.md`'s stable JSON shape — `by`, the echoed `filters`,
    `groups` ordered by key, and `totals` over the same filtered scope. Totals
    are queried, not summed from the groups, so a metric that is NULL in every
    group stays NULL instead of collapsing to 0.

    `since` compares against `torn_down_at`, both ISO 8601 UTC: a `YYYY-MM-DD`
    argument sorts at the start of that day, so the named day is included.

    Raises `ValueError` if `by` is not one of `ROLLUP_DIMENSIONS`.
    """
    if by not in _GROUP_EXPRESSIONS:
        raise ValueError(
            f"unknown rollup dimension {by!r}; expected one of {', '.join(ROLLUP_DIMENSIONS)}"
        )

    where, params = _filter_clause(epic=epic, since=since)
    group_expression = _GROUP_EXPRESSIONS[by]

    groups = conn.execute(
        f"SELECT {group_expression}, {_METRIC_SELECT} FROM usage_records{where} "
        f"GROUP BY {group_expression} ORDER BY {group_expression}",
        params,
    ).fetchall()
    total_select = _TOTALS_SELECT
    if "usage_status" in {row[1] for row in conn.execute("PRAGMA table_info(usage_records)")}:
        total_select = total_select.replace(" THEN NULL ELSE", " OR SUM(usage_status IN ('partial', 'unknown')) > 0 THEN NULL ELSE")
    totals = conn.execute(f"SELECT {total_select} FROM usage_records{where}", params).fetchone()

    return {
        "by": by,
        "filters": {"epic": epic, "since": since},
        "groups": [{"key": row[0], **_metrics(row[1:])} for row in groups],
        "totals": _metrics(totals),
        "coverage": _coverage(conn, where, params, group_expression),
    }


def _filter_clause(
    *, epic: str | None, since: str | None
) -> tuple[str, dict[str, Any]]:
    """Build the shared WHERE clause; both queries must see the same scope."""
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if epic is not None:
        conditions.append("epic_id = :epic")
        params["epic"] = epic
    if since is not None:
        conditions.append("torn_down_at >= :since")
        params["since"] = since

    return (f" WHERE {' AND '.join(conditions)}" if conditions else ""), params


def _metrics(values: tuple[Any, ...]) -> dict[str, Any]:
    """Name one aggregate row's columns, in `_METRICS` order."""
    return dict(zip(_METRIC_FIELDS, values))


def _coverage(conn: sqlite3.Connection, where: str, params: dict[str, Any], group: str) -> dict[str, Any]:
    """Additive reporting works against old ledgers without migrating on reads."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(usage_records)")}
    status = "usage_status" if "usage_status" in columns else "'legacy'"
    source = "usage_source" if "usage_source" in columns else "'legacy'"
    cost = "cost_basis" if "cost_basis" in columns else "'unknown'"
    rows = conn.execute(
        f"SELECT {group}, prompt_tokens, completion_tokens, request_count, {status}, {source}, {cost} "
        f"FROM usage_records{where}", params,
    ).fetchall()
    def metrics(selected: list[tuple[Any, ...]]) -> dict[str, Any]:
        def measured(index: int) -> int | None:
            values = [row[index] for row in selected if row[index] is not None]
            return sum(values) if values else None
        return {
            "measured_prompt_tokens": measured(1),
            "measured_completion_tokens": measured(2),
            "measured_requests": measured(3),
            "missing_usage_rows": sum(row[1] is None or row[2] is None for row in selected),
            "partial_usage_rows": sum(row[4] == "partial" for row in selected),
            "legacy_usage_rows": sum(row[4] == "legacy" for row in selected),
            "usage_sources": sorted({row[5] for row in selected}),
            "cost_bases": sorted({row[6] for row in selected}),
        }
    return {
        "groups": [{"key": key, **metrics([row for row in rows if row[0] == key])} for key in sorted({row[0] for row in rows})],
        "totals": metrics(rows),
    }
