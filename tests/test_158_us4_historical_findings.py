"""US4: historical findings preserve observation identity, time and purity."""

from __future__ import annotations

import argparse
import os
import sqlite3
import re
import json
import tempfile
from pathlib import Path
from typing import Iterator
from dataclasses import replace

import pytest

from factory.cli.doctor import add_findings_parser, findings_ingest_command
from factory.doctor.cli import _sanitize_historical_observation
from factory.doctor.models import (
    HistoricalObservation,
    Status,
    parse_historical_findings_batch,
)
from factory.doctor.store import (
    SCHEMA_VERSION,
    connect,
    connect_readonly,
    get_finding,
    list_events,
    apply_historical_observation,
    report,
    resolve,
)


INGESTED_AT = "2026-09-11T12:00:00Z"
OBSERVED_AT = "2026-09-01T00:00:00Z"
OBSERVATION_ID = "audit-2026-09-01:ops/historical"


def _historical_batch() -> str:
    return (
        r"""
        {
          "source": "audit-2026-09-01",
          "findings": [
            {
              "key": "ops/historical",
              "category": "ops",
              "severity": "warning",
              "summary": "the old observation",
              "refs": ["factory/old.py:1"],
              "notes": "observed on 2026-09-01; prose says it was fixed",
              "observation_id": "audit-2026-09-01:ops/historical",
              "observed_at": "2026-09-01T00:00:00Z"
            }
          ]
        }
        """
    )


def _observation() -> HistoricalObservation:
    return parse_historical_findings_batch(
        _historical_batch(), ingested_at=INGESTED_AT
    )[0]


@pytest.fixture
def store(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "doctor.db")
    try:
        yield conn
    finally:
        conn.close()


def test_historical_batch_preserves_identity_and_observed_time() -> None:
    parsed = parse_historical_findings_batch(
        _historical_batch(), ingested_at=INGESTED_AT
    )

    assert len(parsed) == 1
    observation = parsed[0]
    assert isinstance(observation, HistoricalObservation)
    assert observation.observation_id == OBSERVATION_ID
    assert observation.observed_at == OBSERVED_AT
    assert observation.ingested_at == INGESTED_AT
    assert observation.observation.source == "audit-2026-09-01"


def test_historical_batch_refuses_one_observation_id_for_two_entries() -> None:
    batch = json.loads(_historical_batch())
    duplicate = dict(batch["findings"][0])
    duplicate["key"] = "ops/other"
    batch["findings"].append(duplicate)

    with pytest.raises(ValueError, match="observation_id"):
        parse_historical_findings_batch(
            json.dumps(batch), ingested_at=INGESTED_AT
        )


def test_historical_event_round_trip_keeps_all_times_distinct(
    store: sqlite3.Connection,
) -> None:
    observation = _observation()

    assert apply_historical_observation(
        store, observation, ingested_at=INGESTED_AT
    )

    stored = get_finding(store, observation.observation.key)
    assert stored is not None
    assert stored.status == Status.OPEN
    assert stored.occurrences == 1
    assert stored.first_seen == OBSERVED_AT
    assert stored.last_seen == OBSERVED_AT

    events = list_events(store, observation.observation.key)
    assert len(events) == 1
    event = events[0]
    assert event.observation_id == OBSERVATION_ID
    assert event.observed_at == OBSERVED_AT
    assert event.ingested_at == INGESTED_AT
    assert event.ingested_at != event.observed_at


def test_duplicate_historical_observation_is_idempotent(
    store: sqlite3.Connection,
) -> None:
    first = apply_historical_observation(
        store, _observation(), ingested_at=INGESTED_AT
    )
    before = get_finding(store, "ops/historical")

    second = apply_historical_observation(
        store, _observation(), ingested_at="2026-09-11T13:00:00Z"
    )

    assert (first, second) == (True, False)
    stored = get_finding(store, "ops/historical")
    assert stored == before
    assert len(list_events(store, "ops/historical")) == 1


def test_historical_observation_does_not_change_a_current_row(
    store: sqlite3.Connection,
) -> None:
    observation = _observation()
    report(store, observation.observation, seen_at="2026-09-01T00:00:00Z")
    before = get_finding(store, "ops/historical")
    assert before is not None

    assert apply_historical_observation(
        store,
        replace(
            observation,
            observation_id="audit-2026-09-02:ops/historical",
            ingested_at=INGESTED_AT,
        ),
        ingested_at=INGESTED_AT,
    )

    stored = get_finding(store, "ops/historical")
    assert stored == before
    assert len(list_events(store, "ops/historical")) == 2


def test_historical_fix_prose_does_not_resolve_a_current_row(
    store: sqlite3.Connection,
) -> None:
    observation = _observation()
    assert "fixed" in (observation.observation.notes or "")
    report(store, observation.observation, seen_at="2026-09-01T00:00:00Z")
    before = get_finding(store, "ops/historical")
    assert before is not None

    assert apply_historical_observation(
        store,
        replace(
            observation,
            observation_id="audit-2026-09-02:ops/historical",
            ingested_at=INGESTED_AT,
        ),
        ingested_at=INGESTED_AT,
    )

    stored = get_finding(store, "ops/historical")
    assert stored == before


def test_current_live_report_keeps_the_old_recurrence_semantics(
    store: sqlite3.Connection,
) -> None:
    observation = _observation()
    live = observation.observation
    report(store, live, seen_at="2026-09-11T12:00:00Z")
    report(store, live, seen_at="2026-09-11T13:00:00Z")

    stored = get_finding(store, "ops/historical")
    assert stored is not None
    assert stored.occurrences == 2
    assert stored.last_seen == "2026-09-11T13:00:00Z"
    events = list_events(store, "ops/historical")
    assert [event.ingested_at for event in events] == [
        "2026-09-11T12:00:00Z",
        "2026-09-11T13:00:00Z",
    ]


def test_connect_migrates_a_v1_store(
    tmp_path: Path,
) -> None:
    path = tmp_path / "doctor.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS findings (
            key TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('critical','warning','info')),
            status TEXT NOT NULL DEFAULT 'open',
            summary TEXT NOT NULL,
            refs TEXT NOT NULL,
            notes TEXT,
            source TEXT NOT NULL,
            occurrences INTEGER NOT NULL DEFAULT 1,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            promoted_spec TEXT,
            resolved_at TEXT,
            resolution TEXT
        );
        CREATE TABLE IF NOT EXISTS finding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_key TEXT NOT NULL REFERENCES findings(key),
            seen_at TEXT NOT NULL,
            source TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('critical','warning','info')),
            kind TEXT NOT NULL CHECK (kind IN ('reported','promoted','resolved','regressed'))
        );
        INSERT INTO schema_version (version) VALUES (1);
        INSERT INTO findings (
            key, category, severity, summary, refs, source, first_seen, last_seen
        )
        VALUES ('ops/migrated', 'ops', 'warning', 'old', '[]', 'probe',
                '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z');
        INSERT INTO finding_events (finding_key, seen_at, source, severity, kind)
        VALUES ('ops/migrated', '2026-09-01T00:00:00Z', 'probe', 'warning', 'reported');
        """
    )
    conn.commit()
    conn.close()

    conn = connect(path)
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(finding_events)")
        }
    finally:
        conn.close()

    assert version == SCHEMA_VERSION == 2
    assert {"observation_id", "observed_at", "ingested_at"} <= columns


def test_analysis_only_ingest_rehearses_and_never_opens_the_operational_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    operational = tmp_path / "operational.db"
    operational.write_bytes(b"")
    rehearsal = tmp_path / "rehearsal.db"
    args = argparse.Namespace(
        batch=str(tmp_path / "batch.json"),
        apply=False,
        rehearsal_db=str(rehearsal),
    )

    real_connect = connect

    def forbidden(path: Path) -> sqlite3.Connection:
        if path == operational:
            raise AssertionError("analysis-only ingestion opened the operational store")
        return real_connect(path)

    monkeypatch.setattr("factory.doctor.cli.connect", forbidden)
    (tmp_path / "batch.json").write_text(_historical_batch())

    exit_code = findings_ingest_command(args)

    assert exit_code == 0
    assert rehearsal.is_file()
    rehearsal_conn = connect(rehearsal)
    try:
        stored = get_finding(rehearsal_conn, "ops/historical")
        assert stored is not None
        assert stored.last_seen == OBSERVED_AT
    finally:
        rehearsal_conn.close()
    assert operational.read_bytes() == b""
    assert str(rehearsal) in capsys.readouterr().out


def test_authorized_ingest_can_apply_to_an_explicit_store(
    tmp_path: Path,
) -> None:
    operational = tmp_path / "operational.db"
    rehearsal = tmp_path / "rehearsal.db"
    batch = tmp_path / "batch.json"
    batch.write_text(_historical_batch())

    args = argparse.Namespace(
        batch=str(batch),
        apply=True,
        db=str(operational),
    )
    findings_ingest_command(args)

    with connect(operational) as conn:
        assert get_finding(conn, "ops/historical") is not None
    assert not rehearsal.exists()


def test_findings_ingest_defaults_to_analysis_only(
    capsys: pytest.CaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = argparse.ArgumentParser()
    verbs = parser.add_subparsers(dest="verb", required=True)
    add_findings_parser(verbs)
    args = parser.parse_args(
        ["findings", "ingest", "--batch", str(tmp_path / "batch.json")]
    )

    assert args.apply is False


def test_analysis_only_ingest_defaults_to_a_readable_rehearsal_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    operational = tmp_path / "operational.db"
    operational.write_bytes(b"placeholder-ledger")
    operational_bytes = operational.read_bytes()
    batch = tmp_path / "batch.json"
    batch.write_text(_historical_batch())

    parser = argparse.ArgumentParser()
    verbs = parser.add_subparsers(dest="verb", required=True)
    add_findings_parser(verbs)
    args = parser.parse_args(["findings", "ingest", "--batch", str(batch)])

    created_fds: list[int] = []
    closed_fds: list[int] = []
    real_mkstemp = tempfile.mkstemp
    real_close = os.close

    def tracked_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        handle, path = real_mkstemp(*args, **kwargs)  # type: ignore[arg-type]
        created_fds.append(handle)
        return handle, path

    def tracked_close(handle: int) -> None:
        if handle in created_fds:
            closed_fds.append(handle)
        real_close(handle)

    monkeypatch.setattr("factory.doctor.cli.tempfile.mkstemp", tracked_mkstemp)
    monkeypatch.setattr("factory.doctor.cli.os.close", tracked_close)

    real_connect = connect

    def forbidden(path: Path) -> sqlite3.Connection:
        if path == operational:
            raise AssertionError("analysis-only ingestion opened the operational store")
        return real_connect(path)

    monkeypatch.setattr("factory.doctor.cli.connect", forbidden)
    exit_code = args.run(args)

    assert exit_code == 0
    output = capsys.readouterr()
    assert output.err == ""
    printed_paths = output.out.splitlines()
    assert len(printed_paths) == 1
    rehearsal_path = Path(printed_paths[0])
    assert rehearsal_path.is_file()
    assert rehearsal_path != operational
    with connect(rehearsal_path) as rehearsal_conn:
        stored = get_finding(rehearsal_conn, "ops/historical")
        events = list_events(rehearsal_conn, "ops/historical")
    assert stored is not None
    assert stored.last_seen == OBSERVED_AT
    assert len(events) == 1
    assert events[0].observed_at == OBSERVED_AT
    assert events[0].ingested_at != OBSERVED_AT
    assert operational.read_bytes() == operational_bytes
    assert len(created_fds) == 1
    assert closed_fds == created_fds


def test_analysis_only_ingest_closes_the_descriptor_when_writing_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = tmp_path / "batch.json"
    batch.write_text(_historical_batch())
    parser = argparse.ArgumentParser()
    verbs = parser.add_subparsers(dest="verb", required=True)
    add_findings_parser(verbs)
    args = parser.parse_args(["findings", "ingest", "--batch", str(batch)])

    created_fds: list[int] = []
    closed_fds: list[int] = []
    real_mkstemp = tempfile.mkstemp
    real_close = os.close

    def tracked_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        handle, path = real_mkstemp(*args, **kwargs)  # type: ignore[arg-type]
        created_fds.append(handle)
        return handle, path

    def tracked_close(handle: int) -> None:
        if handle in created_fds:
            closed_fds.append(handle)
        real_close(handle)

    def failing_write(*args: object, **kwargs: object) -> None:
        raise RuntimeError("historical write failed")

    monkeypatch.setattr("factory.doctor.cli.tempfile.mkstemp", tracked_mkstemp)
    monkeypatch.setattr("factory.doctor.cli.os.close", tracked_close)
    monkeypatch.setattr(
        "factory.doctor.cli.apply_historical_observation", failing_write
    )

    with pytest.raises(RuntimeError, match="historical write failed"):
        args.run(args)

    assert len(created_fds) == 1
    assert closed_fds == created_fds


def test_analysis_only_rehearsal_sanitizes_observation_identity_too(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    markers = (
        "sk-test-observation-alpha",
        "sk-test-source-alpha",
        "sk-test-summary-alpha",
        "sk-test-reference-alpha",
        "sk-test-note-alpha",
        "sk-test-observation-beta",
        "sk-test-source-beta",
        "sk-test-summary-beta",
        "sk-test-reference-beta",
        "sk-test-note-beta",
    )
    batch = tmp_path / "batch.json"
    batch.write_text(
        f"""
        {{
          "source": "{markers[1]}",
          "findings": [
            {{
              "key": "ops/historical",
              "category": "ops",
              "severity": "warning",
              "summary": "{markers[2]}",
              "refs": ["{markers[3]}"],
              "notes": "{markers[4]}",
              "observation_id": "{markers[0]}",
              "observed_at": "{OBSERVED_AT}"
            }},
            {{
              "key": "ops/historical-beta",
              "category": "ops",
              "severity": "warning",
              "summary": "{markers[7]}",
              "refs": ["{markers[8]}"],
              "notes": "{markers[9]}",
              "observation_id": "{markers[5]}",
              "observed_at": "{OBSERVED_AT}"
            }}
          ]
        }}
        """
    )
    parser = argparse.ArgumentParser()
    verbs = parser.add_subparsers(dest="verb", required=True)
    add_findings_parser(verbs)
    rehearsal = tmp_path / "rehearsal.db"
    args = parser.parse_args(
        [
            "findings",
            "ingest",
            "--batch",
            str(batch),
            "--rehearsal-db",
            str(rehearsal),
        ]
    )

    def leak_on_write(
        _conn: sqlite3.Connection, observation: object, ingested_at: str
    ) -> bool:
        if leak_on_write.writes == 0:
            leak_on_write.writes = 1
            return apply_historical_observation(
                _conn, observation, ingested_at=ingested_at
            )
        raise RuntimeError(str(observation))

    leak_on_write.writes = 0

    monkeypatch.setattr(
        "factory.doctor.cli.apply_historical_observation", leak_on_write
    )
    try:
        args.run(args)
        raise AssertionError("historical write unexpectedly succeeded")
    except RuntimeError as exc:
        exception_text = str(exc)

    capsys.readouterr()
    assert not any(marker in exception_text for marker in markers)

    assert rehearsal.is_file()
    database_bytes = rehearsal.read_bytes()
    with connect(rehearsal) as rehearsal_conn:
        stored = get_finding(rehearsal_conn, "ops/historical")
        events = list_events(rehearsal_conn, "ops/historical")
    assert stored is not None
    assert markers[2] not in stored.summary
    assert all(markers[3] not in ref for ref in stored.refs)
    assert markers[4] not in (stored.notes or "")
    assert markers[1] not in stored.source
    assert len(events) == 1
    assert all(marker.encode() not in database_bytes for marker in markers)
    assert all(
        marker not in (event.observation_id or "")
        for event in events
        for marker in markers
    )


def test_sanitized_historical_ids_stay_idempotent_and_distinct(
    store: sqlite3.Connection,
) -> None:
    observation = _observation()
    credential_observation = replace(
        observation, observation_id="sk-test-observation-credential"
    )
    sanitized = _sanitize_historical_observation(credential_observation)
    repeat = _sanitize_historical_observation(credential_observation)
    distinct_source = _sanitize_historical_observation(
        replace(credential_observation, observation_id="sk-test-observation-other")
    )

    assert sanitized.observation_id == repeat.observation_id
    assert sanitized.observation_id != distinct_source.observation_id

    assert apply_historical_observation(
        store, sanitized, ingested_at=INGESTED_AT
    )
    before = get_finding(store, observation.observation.key)
    assert before is not None

    assert apply_historical_observation(
        store, distinct_source, ingested_at=INGESTED_AT
    )
    after_distinct = get_finding(store, observation.observation.key)
    events = list_events(store, observation.observation.key)
    assert after_distinct == before
    assert len(events) == 2
    assert {event.observation_id for event in events} == {
        sanitized.observation_id,
        distinct_source.observation_id,
    }

    assert not apply_historical_observation(
        store, repeat, ingested_at="2026-09-11T13:00:00Z"
    )
    assert len(list_events(store, observation.observation.key)) == 2
    assert get_finding(store, observation.observation.key) == after_distinct


def test_findings_ingest_skill_keeps_analysis_and_apply_distinct() -> None:
    skill = Path(".agents/skills/findings-ingest/SKILL.md").read_text()

    assert "## 6. Analysis-only rehearsal" in skill
    assert "## 6.1 Separate authorized application" in skill
    assert "findings ingest --batch batch.json --rehearsal-db" in skill
    assert "--batch batch.json" in skill
    assert "--apply \\\n  --db" in skill
    assert "uv run ergane findings report --batch" not in skill
