"""Evidence-store discipline and recurrence semantics for factory/doctor/store.py.

Written before `factory/doctor/store.py` exists (T003/T004 precede T008): until
that module lands, tests here fail at import. The store mirrors the
verification store's contract-copy pattern: `_SCHEMA_DDL` in the module is a
verbatim copy of `specs/015-factory-doctor/contracts/doctor-store.sql`, and this
suite holds it structure-for-structure against the contract file.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.doctor.models import Finding, FindingEvent, Severity, Status
from factory.doctor.store import (
    BUSY_TIMEOUT_MS,
    SCHEMA_VERSION,
    connect,
    list_findings,
    report,
    resolve,
)

#: The published DDL. The store's schema is compared against this file rather
#: than against a duplicate of it kept in the test.
CONTRACT_DDL = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "015-factory-doctor"
    / "contracts"
    / "doctor-store.sql"
)

EXPECTED_FINDINGS_COLUMNS: list[tuple[str, str, int, int]] = [
    ("key", "TEXT", 0, 1),
    ("category", "TEXT", 1, 0),
    ("severity", "TEXT", 1, 0),
    ("status", "TEXT", 1, 0),
    ("summary", "TEXT", 1, 0),
    ("refs", "TEXT", 1, 0),
    ("notes", "TEXT", 0, 0),
    ("source", "TEXT", 1, 0),
    ("occurrences", "INTEGER", 1, 0),
    ("first_seen", "TEXT", 1, 0),
    ("last_seen", "TEXT", 1, 0),
    ("promoted_spec", "TEXT", 0, 0),
    ("resolved_at", "TEXT", 0, 0),
    ("resolution", "TEXT", 0, 0),
]

EXPECTED_EVENTS_COLUMNS: list[tuple[str, str, int, int]] = [
    ("id", "INTEGER", 0, 1),
    ("finding_key", "TEXT", 1, 0),
    ("seen_at", "TEXT", 1, 0),
    ("source", "TEXT", 1, 0),
    ("severity", "TEXT", 1, 0),
    ("kind", "TEXT", 1, 0),
]

EXPECTED_INDEXES = {
    "idx_finding_events_key",
}


def _canonical(sql: str) -> str:
    text = re.sub(r"--[^\n]*", " ", sql)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([(),])\s*", r"\1", text)
    return text.strip().casefold()


def schema_of(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0]: _canonical(row[1]) for row in rows}


def raw_insert_finding(conn: sqlite3.Connection, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "key": "ops/default",
        "category": "ops",
        "severity": "warning",
        "status": "open",
        "summary": "s",
        "refs": json.dumps(["a:1"]),
        "notes": None,
        "source": "operator",
        "occurrences": 1,
        "first_seen": "2026-08-07T10:00:00Z",
        "last_seen": "2026-08-07T10:00:00Z",
        "promoted_spec": None,
        "resolved_at": None,
        "resolution": None,
    }
    values.update(overrides)
    _raw_insert(conn, "findings", values)


def _raw_insert(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join(f":{column}" for column in values)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
    conn.commit()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "doctor.db"


@pytest.fixture
def store(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def contract_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
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
    assert schema_of(store) == schema_of(contract_db)


def test_the_findings_columns_match_the_contract(store: sqlite3.Connection) -> None:
    columns = [
        (row[1], row[2], row[3], row[5])
        for row in store.execute("PRAGMA table_info(findings)").fetchall()
    ]
    assert columns == EXPECTED_FINDINGS_COLUMNS


def test_the_finding_events_columns_match_the_contract(
    store: sqlite3.Connection,
) -> None:
    columns = [
        (row[1], row[2], row[3], row[5])
        for row in store.execute("PRAGMA table_info(finding_events)").fetchall()
    ]
    assert columns == EXPECTED_EVENTS_COLUMNS


def test_the_query_indexes_exist(store: sqlite3.Connection) -> None:
    names = set()
    for table in ("findings", "finding_events"):
        names |= {
            row[1] for row in store.execute(f"PRAGMA index_list({table})").fetchall()
        }
    assert EXPECTED_INDEXES <= names


def test_the_schema_version_is_recorded_once(store: sqlite3.Connection) -> None:
    versions = [row[0] for row in store.execute("SELECT version FROM schema_version")]
    assert versions == [SCHEMA_VERSION]


def test_the_store_is_opened_in_wal_mode_with_a_busy_timeout(
    store: sqlite3.Connection,
) -> None:
    journal_mode = store.execute("PRAGMA journal_mode").fetchone()[0]
    busy_timeout = store.execute("PRAGMA busy_timeout").fetchone()[0]
    assert journal_mode.lower() == "wal"
    assert BUSY_TIMEOUT_MS == 5000
    assert busy_timeout == BUSY_TIMEOUT_MS


def test_connecting_creates_the_factory_directory(tmp_path: Path) -> None:
    nested = tmp_path / "workdir" / ".factory" / "doctor.db"
    conn = connect(str(nested))
    try:
        assert nested.exists()
        assert schema_of(conn)
    finally:
        conn.close()


def test_reconnecting_to_an_existing_store_preserves_it(db_path: Path) -> None:
    first = connect(db_path)
    try:
        raw_insert_finding(first, key="ops/persisted")
    finally:
        first.close()

    second = connect(db_path)
    try:
        versions = [row[0] for row in second.execute("SELECT version FROM schema_version")]
        assert versions == [SCHEMA_VERSION]
        assert second.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 1
    finally:
        second.close()


# --- DDL constraints --------------------------------------------------------


@pytest.mark.parametrize("severity", ["fatal", "unknown", ""])
def test_severity_outside_the_enum_is_rejected(
    store: sqlite3.Connection, severity: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_finding(store, severity=severity)


@pytest.mark.parametrize("status", ["closed", "draft", ""])
def test_status_outside_the_enum_is_rejected(
    store: sqlite3.Connection, status: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_finding(store, status=status)


def test_a_required_column_cannot_be_null(store: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert_finding(store, summary=None)


# --- report / recurrence ----------------------------------------------------


def _finding(store: sqlite3.Connection, key: str) -> Finding:
    rows = list_findings(store)
    for f in rows:
        if f.key == key:
            return f
    raise AssertionError(f"finding {key!r} not found")


def _events(store: sqlite3.Connection, key: str) -> list[FindingEvent]:
    cursor = store.execute(
        "SELECT id, finding_key, seen_at, source, severity, kind "
        "FROM finding_events WHERE finding_key = ? ORDER BY id",
        (key,),
    )
    return [
        FindingEvent(
            id=row[0],
            finding_key=row[1],
            seen_at=row[2],
            source=row[3],
            severity=Severity(row[4]),
            kind=row[5],
        )
        for row in cursor.fetchall()
    ]


def test_first_report_inserts_open_with_one_occurrence_and_event(store: sqlite3.Connection) -> None:
    f = Finding(
        key="ops/first",
        category="ops",
        severity=Severity.CRITICAL,
        status=Status.OPEN,
        summary="the first finding",
        refs=["a:1"],
        notes="n1",
        source="operator",
        occurrences=1,
        first_seen="2026-08-07T10:00:00Z",
        last_seen="2026-08-07T10:00:00Z",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(store, f, seen_at="2026-08-07T10:00:00Z")

    stored = _finding(store, "ops/first")
    assert stored.status == Status.OPEN
    assert stored.occurrences == 1
    assert stored.first_seen == stored.last_seen == "2026-08-07T10:00:00Z"
    assert stored.summary == "the first finding"

    events = _events(store, "ops/first")
    assert [e.kind for e in events] == ["reported"]
    assert events[0].severity == Severity.CRITICAL


def test_same_key_recurs_no_duplicate_row(store: sqlite3.Connection) -> None:
    base = Finding(
        key="ops/recur",
        category="ops",
        severity=Severity.WARNING,
        status=Status.OPEN,
        summary="first summary",
        refs=["a:1"],
        notes="n1",
        source="probe-a",
        occurrences=1,
        first_seen="2026-08-07T10:00:00Z",
        last_seen="2026-08-07T10:00:00Z",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(store, base, seen_at="2026-08-07T10:00:00Z")
    updated = Finding(
        key="ops/recur",
        category="ops",
        severity=Severity.WARNING,
        status=Status.OPEN,
        summary="second summary",
        refs=["b:2", "c:3"],
        notes="n2",
        source="probe-a",
        occurrences=1,
        first_seen="2026-08-07T10:00:00Z",
        last_seen="2026-08-08T11:00:00Z",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(store, updated, seen_at="2026-08-08T11:00:00Z")

    rows = list_findings(store)
    assert [r.key for r in rows] == ["ops/recur"]
    stored = rows[0]
    assert stored.occurrences == 2
    assert stored.last_seen == "2026-08-08T11:00:00Z"
    assert stored.summary == "second summary"
    assert stored.refs == ["b:2", "c:3"]
    assert stored.notes == "n2"

    events = _events(store, "ops/recur")
    assert [e.kind for e in events] == ["reported", "reported"]


def test_report_on_resolved_key_transitions_to_regressed(store: sqlite3.Connection) -> None:
    base = Finding(
        key="ops/regressed",
        category="ops",
        severity=Severity.INFO,
        status=Status.OPEN,
        summary="original",
        refs=["a:1"],
        notes="n1",
        source="probe-a",
        occurrences=1,
        first_seen="2026-08-07T10:00:00Z",
        last_seen="2026-08-07T10:00:00Z",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(store, base, seen_at="2026-08-07T10:00:00Z")
    resolve(store, "ops/regressed", reason="fixed", resolved_at="2026-08-07T12:00:00Z")

    reopened = Finding(
        key="ops/regressed",
        category="ops",
        severity=Severity.INFO,
        status=Status.OPEN,
        summary="it came back",
        refs=["a:2"],
        notes="n2",
        source="probe-a",
        occurrences=1,
        first_seen="2026-08-08T10:00:00Z",
        last_seen="2026-08-08T10:00:00Z",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(store, reopened, seen_at="2026-08-08T10:00:00Z")

    stored = _finding(store, "ops/regressed")
    assert stored.status == Status.REGRESSED
    assert stored.occurrences == 2
    assert stored.resolved_at == "2026-08-07T12:00:00Z"
    assert stored.resolution == "fixed"
    assert stored.summary == "it came back"

    events = _events(store, "ops/regressed")
    assert [e.kind for e in events] == ["reported", "resolved", "regressed"]


def test_report_transition_is_atomic_under_concurrent_connections(db_path: Path) -> None:
    """Two at-least-once reporters landing on the same identity end up with one
    row and two events.

    The race happens through independent connections opened inside each thread,
    because that is how separate activity invocations actually contend on the
    store. SQLite's WAL + busy_timeout absorb the collision.
    """
    exceptions: list[Exception] = []

    def worker(seen_at: str, summary: str, refs: list[str]) -> None:
        try:
            conn = connect(db_path)
            try:
                f = Finding(
                    key="ops/concurrent",
                    category="ops",
                    severity=Severity.WARNING,
                    status=Status.OPEN,
                    summary=summary,
                    refs=refs,
                    notes="n",
                    source="probe",
                    occurrences=1,
                    first_seen=seen_at,
                    last_seen=seen_at,
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                )
                report(conn, f, seen_at=seen_at)
            finally:
                conn.close()
        except Exception as exc:  # pragma: no cover
            exceptions.append(exc)

    # Prime the store so both threads open an already-initialised WAL file,
    # avoiding the first-open race that can mis-report a busy timeout.
    primer = connect(db_path)
    primer.close()

    t1 = threading.Thread(target=worker, args=("2026-08-07T10:00:00Z", "s1", ["a:1"]))
    t2 = threading.Thread(target=worker, args=("2026-08-07T10:00:01Z", "s2", ["b:2"]))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not exceptions, exceptions

    conn = connect(db_path)
    try:
        stored = list_findings(conn)[0]
        events = _events(conn, "ops/concurrent")
        assert stored.occurrences == 2, stored.occurrences
        assert len(events) == 2
    finally:
        conn.close()


# --- resolve ----------------------------------------------------------------


def test_resolve_records_resolution_and_a_resolved_event(store: sqlite3.Connection) -> None:
    base = Finding(
        key="ops/fixed",
        category="ops",
        severity=Severity.WARNING,
        status=Status.OPEN,
        summary="s",
        refs=["a:1"],
        notes="n",
        source="probe",
        occurrences=1,
        first_seen="2026-08-07T10:00:00Z",
        last_seen="2026-08-07T10:00:00Z",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(store, base, seen_at="2026-08-07T10:00:00Z")
    resolve(store, "ops/fixed", reason="landed in 009", resolved_at="2026-08-08T12:00:00Z")

    stored = _finding(store, "ops/fixed")
    assert stored.status == Status.RESOLVED
    assert stored.resolved_at == "2026-08-08T12:00:00Z"
    assert stored.resolution == "landed in 009"

    events = _events(store, "ops/fixed")
    assert [e.kind for e in events] == ["reported", "resolved"]


def test_resolve_unknown_key_is_a_no_op(store: sqlite3.Connection) -> None:
    assert resolve(store, "ops/never-reported", reason="x", resolved_at="2026-08-08T12:00:00Z") is False


# --- list -------------------------------------------------------------------


def test_list_orders_by_severity_then_occurrences_desc_then_key(store: sqlite3.Connection) -> None:
    for key, severity, occurrences in [
        ("ops/c-low", Severity.WARNING, 5),
        ("ops/a-high", Severity.CRITICAL, 1),
        ("ops/b-high-many", Severity.CRITICAL, 3),
        ("ops/d-info", Severity.INFO, 10),
    ]:
        f = Finding(
            key=key,
            category="ops",
            severity=severity,
            status=Status.OPEN,
            summary=key,
            refs=["a:1"],
            notes=None,
            source="probe",
            occurrences=occurrences,
            first_seen="2026-08-07T10:00:00Z",
            last_seen="2026-08-07T10:00:00Z",
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        )
        report(store, f, seen_at="2026-08-07T10:00:00Z")

    rows = list_findings(store)
    assert [r.key for r in rows] == [
        "ops/b-high-many",
        "ops/a-high",
        "ops/c-low",
        "ops/d-info",
    ]
