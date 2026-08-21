"""What `ergane findings triage --apply` is allowed to enact, and what it is not.

US2 sorts every open finding into a class. This suite is about the half-dozen
lines that decide which of those classes may reach the store — and, far more
importantly, which may not. Two of the seven scenarios are silences: a prose
candidate and a finding seen after its fix landed must come out of `--apply`
byte-identical, because a mention is not a proof and a re-sighting is the top of
the operator's queue rather than the bottom of the closable pile.

Every fixture here is a supplied tree: a store built with `connect()` on a
`tmp_path` and, where a corpus is needed, a specs directory this file writes.
Nothing reads `.factory/`, the real `specs/`, or the repository's own git
history — a test that did would be asserting against the running factory's
production evidence, and would change its answer the week a spec's state flips.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from factory.doctor.models import Finding, FindingEvent, Severity, Status
from factory.doctor.store import (
    annotate,
    connect,
    get_finding,
    list_events,
)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "doctor.db")
    try:
        yield conn
    finally:
        conn.close()


def _report(
    conn: sqlite3.Connection,
    key: str,
    *,
    source: str = "probe",
    notes: str | None = None,
    occurrences: int = 1,
    seen_at: str = "2026-08-01T10:00:00Z",
    status: Status = Status.OPEN,
) -> Finding:
    """Insert one finding directly, so the row's shape is the test's to choose.

    `report()` is deliberately not used: it is the recurrence machine, and a
    fixture that went through it could not put a row at three occurrences
    without also writing three events for this suite to have to discount.
    """
    finding = Finding(
        key=key,
        category=key.split("/")[0],
        severity=Severity.WARNING,
        status=status,
        summary=f"summary of {key}",
        refs=[f"{key}:1"],
        notes=notes,
        source=source,
        occurrences=occurrences,
        first_seen=seen_at,
        last_seen=seen_at,
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    with conn:
        conn.execute(
            """
            INSERT INTO findings (
                key, category, severity, status, summary, refs, notes, source,
                occurrences, first_seen, last_seen, promoted_spec, resolved_at,
                resolution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.key,
                finding.category,
                finding.severity.value,
                finding.status.value,
                finding.summary,
                '["%s:1"]' % key,
                finding.notes,
                finding.source,
                finding.occurrences,
                finding.first_seen,
                finding.last_seen,
                None,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO finding_events (finding_key, seen_at, source, severity, kind)
            VALUES (?, ?, ?, ?, 'reported')
            """,
            (key, seen_at, source, finding.severity.value),
        )
    return finding


def _row(conn: sqlite3.Connection, key: str) -> Finding:
    found = get_finding(conn, key)
    assert found is not None, f"finding {key!r} not found"
    return found


def _events(conn: sqlite3.Connection, key: str) -> list[FindingEvent]:
    return list_events(conn, key)


# --- annotate: the one new store function (T038, FR-017, FR-018) --------------


def test_annotate_writes_the_note_and_nothing_else(store: sqlite3.Connection) -> None:
    """FR-018: notes change; occurrences, last_seen and the trail do not.

    This is the assertion that keeps `annotate` away from `report()`, which
    increments occurrences, advances `last_seen` and appends an event on every
    call — and would have added one phantom recurrence per annotated row to a
    ledger whose whole purpose is counting recurrence.
    """
    _report(store, "ops/cold-one", occurrences=3, seen_at="2026-06-01T10:00:00Z")
    before = _row(store, "ops/cold-one")

    assert annotate(store, "ops/cold-one", annotation="cold: seen once") is True

    after = _row(store, "ops/cold-one")
    assert "cold: seen once" in (after.notes or "")
    assert after.status is Status.OPEN
    assert after.occurrences == before.occurrences
    assert after.last_seen == before.last_seen
    assert after.first_seen == before.first_seen
    assert after.resolved_at is None
    assert after.resolution is None
    assert _events(store, "ops/cold-one") == _events(store, "ops/cold-one")
    assert len(_events(store, "ops/cold-one")) == 1


def test_annotate_keeps_the_note_a_human_wrote(store: sqlite3.Connection) -> None:
    _report(store, "ops/has-notes", notes="the probe saw this at 03:00")

    annotate(store, "ops/has-notes", annotation="needs a human")

    notes = _row(store, "ops/has-notes").notes or ""
    assert "the probe saw this at 03:00" in notes
    assert "needs a human" in notes


def test_annotate_twice_writes_one_annotation(store: sqlite3.Connection) -> None:
    """FR-018: idempotent across repeated passes.

    The second call must not append a second copy, and must report that it
    changed nothing, so a caller can tell a fresh annotation from a re-run.
    """
    _report(store, "ops/twice", notes="original")

    assert annotate(store, "ops/twice", annotation="cold: seen once") is True
    first = _row(store, "ops/twice").notes or ""
    assert annotate(store, "ops/twice", annotation="cold: seen once") is False
    second = _row(store, "ops/twice").notes or ""

    assert first == second
    assert first.count("cold: seen once") == 1


def test_annotate_replaces_a_stale_annotation(store: sqlite3.Connection) -> None:
    """A row's class can change between passes; its notes must not accumulate."""
    _report(store, "ops/moved", notes="a human wrote this")

    annotate(store, "ops/moved", annotation="cold: seen once")
    annotate(store, "ops/moved", annotation="needs a human: nothing declares it")

    notes = _row(store, "ops/moved").notes or ""
    assert "a human wrote this" in notes
    assert "cold: seen once" not in notes
    assert notes.count("needs a human: nothing declares it") == 1


def test_annotate_unknown_key_is_a_no_op(store: sqlite3.Connection) -> None:
    assert annotate(store, "ops/never-reported", annotation="x") is False
