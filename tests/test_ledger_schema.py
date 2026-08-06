"""The ledger's shape on disk, and the uniqueness that makes teardown safe.

The schema is a published surface: FR-012 invites operators to query the file
with `sqlite3` directly, and `contracts/ledger-schema.sql` is what they are
promised. So the tests here compare the database `factory.usage.ledger` creates
against that contract file *applied to a scratch database* — not against a copy
of the DDL pasted into this module, which would only prove the implementation
agrees with itself.

Three properties matter beyond column names:

- **WAL, with a busy timeout.** Teardowns are concurrent within one host (R6);
  a ledger opened in rollback-journal mode would serialize them into `database
  is locked` failures on the one code path that must never lose a row (FR-002).
- **The CHECK constraints are real.** `attempt >= 1`, the 0/1 confirmation flag
  and the termination enum are the last line of defence for a file the factory
  will be read from long after this component ships — and the enum's rejection
  of `budget_breach` is where D-021's deferral is enforced in storage.
- **`key_alias` is UNIQUE and writes upsert on it.** Temporal runs teardown at
  least once, so the second run must land on the same row: exactly one
  `UsageRecord` per attempt, on every terminal path (SC-001).

NULLs get the same care as elsewhere in this component: the token and spend
columns are nullable on purpose, because a fallback teardown records "unknown"
and must never be able to write a fabricated 0 (FR-005).

Written before `factory/usage/ledger.py` exists (T012 precedes T013): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.usage.ledger import BUSY_TIMEOUT_MS, SCHEMA_VERSION, connect, upsert_record
from factory.usage.models import Termination, UsageRecord

#: The published DDL (FR-012). The ledger's schema is compared against this file
#: rather than against a duplicate of it kept in the test.
CONTRACT_DDL = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "001-usage-tracking"
    / "contracts"
    / "ledger-schema.sql"
)

#: (name, declared type, NOT NULL, primary key) per data-model.md § UsageRecord.
EXPECTED_COLUMNS: list[tuple[str, str, int, int]] = [
    ("id", "INTEGER", 0, 1),
    ("epic_id", "TEXT", 1, 0),
    ("node_id", "TEXT", 1, 0),
    ("attempt", "INTEGER", 1, 0),
    ("persona", "TEXT", 1, 0),
    ("spec_ref", "TEXT", 1, 0),
    ("key_alias", "TEXT", 1, 0),
    ("prompt_tokens", "INTEGER", 0, 0),
    ("completion_tokens", "INTEGER", 0, 0),
    ("cache_read_tokens", "INTEGER", 0, 0),
    ("cache_write_tokens", "INTEGER", 0, 0),
    ("request_count", "INTEGER", 0, 0),
    ("spend_usd", "REAL", 0, 0),
    ("final_usage_confirmed", "INTEGER", 1, 0),
    ("termination", "TEXT", 1, 0),
    ("issued_at", "TEXT", 1, 0),
    ("torn_down_at", "TEXT", 1, 0),
]

EXPECTED_INDEXES = {
    "idx_usage_epic",
    "idx_usage_persona",
    "idx_usage_spec_ref",
    "idx_usage_attempt",
}


def make_record(**overrides: Any) -> UsageRecord:
    """A confirmed teardown record; override only what a test is about."""
    fields: dict[str, Any] = {
        "epic_id": "epic-7",
        "node_id": "node-3",
        "attempt": 2,
        "persona": "implementer",
        "spec_ref": "add-usage-tracking/ledger-row",
        "key_alias": "epic-7:node-3:2",
        "prompt_tokens": 1200,
        "completion_tokens": 340,
        "cache_read_tokens": 900,
        "cache_write_tokens": 64,
        "request_count": 7,
        "spend_usd": 0.4212,
        "final_usage_confirmed": True,
        "termination": Termination.COMPLETED,
        "issued_at": "2026-07-24T10:00:00Z",
        "torn_down_at": "2026-07-24T10:31:00Z",
    }
    fields.update(overrides)
    return UsageRecord(**fields)


def raw_insert(conn: sqlite3.Connection, **overrides: Any) -> None:
    """Write a row with plain SQL, so the DDL's constraints are what answers."""
    values: dict[str, Any] = {
        "epic_id": "epic-7",
        "node_id": "node-3",
        "attempt": 1,
        "persona": "implementer",
        "spec_ref": "add-usage-tracking/ledger-row",
        "key_alias": "epic-7:node-3:1",
        "prompt_tokens": None,
        "completion_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "request_count": None,
        "spend_usd": None,
        "final_usage_confirmed": 1,
        "termination": "completed",
        "issued_at": "2026-07-24T10:00:00Z",
        "torn_down_at": "2026-07-24T10:31:00Z",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f":{column}" for column in values)
    conn.execute(
        f"INSERT INTO usage_records ({columns}) VALUES ({placeholders})", values
    )
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


def row_as_dict(conn: sqlite3.Connection, key_alias: str) -> dict[str, Any]:
    cursor = conn.execute(
        "SELECT * FROM usage_records WHERE key_alias = ?", (key_alias,)
    )
    row = cursor.fetchone()
    assert row is not None, f"no ledger row for {key_alias!r}"
    return {column[0]: value for column, value in zip(cursor.description, row)}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.db"


@pytest.fixture
def ledger(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def contract_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A scratch database with `contracts/ledger-schema.sql` applied verbatim."""
    conn = sqlite3.connect(tmp_path / "contract.db")
    try:
        conn.executescript(CONTRACT_DDL.read_text())
        yield conn
    finally:
        conn.close()


# --- schema bootstrap ------------------------------------------------------


def test_a_new_ledger_matches_the_published_contract_ddl(
    ledger: sqlite3.Connection, contract_db: sqlite3.Connection
) -> None:
    # FR-012: what an operator reads in contracts/ledger-schema.sql is what the
    # factory actually creates — tables and indexes, structure for structure.
    assert schema_of(ledger) == schema_of(contract_db)


def test_the_usage_records_columns_match_the_data_model(
    ledger: sqlite3.Connection,
) -> None:
    columns = [
        (row[1], row[2], row[3], row[5])
        for row in ledger.execute("PRAGMA table_info(usage_records)").fetchall()
    ]

    assert columns == EXPECTED_COLUMNS


def test_the_rollup_indexes_exist(ledger: sqlite3.Connection) -> None:
    names = {
        row[1] for row in ledger.execute("PRAGMA index_list(usage_records)").fetchall()
    }

    # The four dimensions FR-006 rolls up by; without them the CLI's queries
    # degrade to full scans as the ledger grows.
    assert EXPECTED_INDEXES <= names


def test_key_alias_carries_a_unique_index(ledger: sqlite3.Connection) -> None:
    unique_on = set()
    for row in ledger.execute("PRAGMA index_list(usage_records)").fetchall():
        name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        columns = tuple(
            info[2]
            for info in ledger.execute(f"PRAGMA index_info({name!r})").fetchall()
        )
        unique_on.add(columns)

    # The idempotency guard is structural: teardown running twice cannot make a
    # second row for one attempt (FR-002, SC-001).
    assert ("key_alias",) in unique_on


def test_the_schema_version_is_recorded_once(ledger: sqlite3.Connection) -> None:
    versions = [row[0] for row in ledger.execute("SELECT version FROM schema_version")]

    assert SCHEMA_VERSION == 1
    assert versions == [SCHEMA_VERSION]


def test_the_ledger_is_opened_in_wal_mode_with_a_busy_timeout(
    ledger: sqlite3.Connection,
) -> None:
    journal_mode = ledger.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = ledger.execute("PRAGMA busy_timeout").fetchone()[0]

    # R6: concurrent teardowns on one host must not serialize into lock errors.
    assert journal_mode.lower() == "wal"
    assert BUSY_TIMEOUT_MS == 5000
    assert busy_timeout == BUSY_TIMEOUT_MS


def test_connecting_creates_the_ledger_directory(tmp_path: Path) -> None:
    nested = tmp_path / "workdir" / ".factory" / "ledger.db"

    conn = connect(str(nested))
    try:
        assert nested.exists()
        assert schema_of(conn)
    finally:
        conn.close()


def test_reconnecting_to_an_existing_ledger_preserves_it(db_path: Path) -> None:
    first = connect(db_path)
    try:
        upsert_record(first, make_record())
    finally:
        first.close()

    second = connect(db_path)
    try:
        # Bootstrap is idempotent: no duplicated version row, no lost data.
        versions = [
            row[0] for row in second.execute("SELECT version FROM schema_version")
        ]
        assert versions == [SCHEMA_VERSION]
        assert second.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0] == 1
    finally:
        second.close()


# --- constraints -----------------------------------------------------------


def test_attempt_ordinals_start_at_one(ledger: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(ledger, attempt=0)


@pytest.mark.parametrize("flag", [2, -1])
def test_final_usage_confirmed_is_strictly_a_flag(
    ledger: sqlite3.Connection, flag: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(ledger, final_usage_confirmed=flag)


@pytest.mark.parametrize("termination", list(Termination))
def test_every_termination_class_is_storable(
    ledger: sqlite3.Connection, termination: Termination
) -> None:
    raw_insert(ledger, key_alias=f"epic-7:node-3:{termination.value}",
               termination=termination.value)

    stored = row_as_dict(ledger, f"epic-7:node-3:{termination.value}")
    assert stored["termination"] == termination.value


@pytest.mark.parametrize("termination", ["budget_breach", "COMPLETED", "", "unknown"])
def test_terminations_outside_the_enum_are_rejected(
    ledger: sqlite3.Connection, termination: str
) -> None:
    # `budget_breach` is deliberately not a member: enforcement is deferred to
    # spec 004 (D-021), and the storage layer says so too.
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(ledger, termination=termination)


@pytest.mark.parametrize(
    "column", ["epic_id", "node_id", "attempt", "persona", "spec_ref", "key_alias",
               "final_usage_confirmed", "termination", "issued_at", "torn_down_at"]
)
def test_attribution_and_outcome_columns_are_not_nullable(
    ledger: sqlite3.Connection, column: str
) -> None:
    # SC-003: a row that cannot say whose spend it was is worse than no row.
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(ledger, **{column: None})


def test_unknown_usage_is_storable_as_null(ledger: sqlite3.Connection) -> None:
    # The fallback teardown's shape (FR-005): flagged unconfirmed, tokens
    # unknown — and unknown must be expressible, or the writer would have to
    # invent zeros to satisfy the schema.
    upsert_record(
        ledger,
        make_record(
            prompt_tokens=None,
            completion_tokens=None,
            cache_read_tokens=None,
            cache_write_tokens=None,
            request_count=None,
            spend_usd=None,
            final_usage_confirmed=False,
            termination=Termination.KILLED,
        ),
    )

    stored = row_as_dict(ledger, "epic-7:node-3:2")
    assert stored["prompt_tokens"] is None
    assert stored["spend_usd"] is None
    assert stored["final_usage_confirmed"] == 0
    assert stored["termination"] == "killed"


def test_a_duplicate_key_alias_cannot_be_inserted_directly(
    ledger: sqlite3.Connection,
) -> None:
    raw_insert(ledger)

    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(ledger)


# --- upsert_record ---------------------------------------------------------


def test_upsert_record_persists_every_field(ledger: sqlite3.Connection) -> None:
    record = make_record()

    written = upsert_record(ledger, record)

    assert written.id is not None
    stored = row_as_dict(ledger, record.key_alias)
    assert stored["id"] == written.id
    assert stored["epic_id"] == record.epic_id
    assert stored["node_id"] == record.node_id
    assert stored["attempt"] == record.attempt
    assert stored["persona"] == record.persona
    assert stored["spec_ref"] == record.spec_ref
    assert stored["prompt_tokens"] == record.prompt_tokens
    assert stored["completion_tokens"] == record.completion_tokens
    assert stored["cache_read_tokens"] == record.cache_read_tokens
    assert stored["cache_write_tokens"] == record.cache_write_tokens
    assert stored["request_count"] == record.request_count
    assert stored["spend_usd"] == pytest.approx(record.spend_usd)
    assert stored["issued_at"] == record.issued_at
    assert stored["torn_down_at"] == record.torn_down_at
    # bool -> 0/1 and enum -> lowercase value are this layer's two mappings.
    assert stored["final_usage_confirmed"] == 1
    assert stored["termination"] == "completed"


def test_upsert_record_commits_for_other_connections(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        upsert_record(conn, make_record())
    finally:
        conn.close()

    # Teardown owns its connection for one invocation (R6); a row left in an
    # open transaction would be a row lost when the activity's process exits.
    reader = sqlite3.connect(db_path)
    try:
        assert reader.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0] == 1
    finally:
        reader.close()


def test_re_running_teardown_updates_the_same_row(ledger: sqlite3.Connection) -> None:
    first = upsert_record(ledger, make_record())

    # A second teardown after a worker crash: the confirmed read is gone, so the
    # rerun writes the fallback shape over the same attempt (FR-002, R3).
    second = upsert_record(
        ledger,
        make_record(
            prompt_tokens=None,
            completion_tokens=None,
            cache_read_tokens=None,
            cache_write_tokens=None,
            request_count=None,
            spend_usd=0.5,
            final_usage_confirmed=False,
            termination=Termination.TIMEOUT,
            torn_down_at="2026-07-24T11:02:00Z",
        ),
    )

    assert ledger.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0] == 1
    assert second.id == first.id

    stored = row_as_dict(ledger, "epic-7:node-3:2")
    assert stored["prompt_tokens"] is None
    assert stored["spend_usd"] == pytest.approx(0.5)
    assert stored["final_usage_confirmed"] == 0
    assert stored["termination"] == "timeout"
    assert stored["torn_down_at"] == "2026-07-24T11:02:00Z"


def test_each_attempt_of_a_node_gets_its_own_row(ledger: sqlite3.Connection) -> None:
    upsert_record(ledger, make_record(attempt=1, key_alias="epic-7:node-3:1"))
    upsert_record(ledger, make_record(attempt=2, key_alias="epic-7:node-3:2"))

    # Retry cost is a first-class question (FR-006), so attempts never merge.
    attempts = [
        row[0]
        for row in ledger.execute(
            "SELECT attempt FROM usage_records "
            "WHERE epic_id = 'epic-7' AND node_id = 'node-3' ORDER BY attempt"
        )
    ]
    assert attempts == [1, 2]
