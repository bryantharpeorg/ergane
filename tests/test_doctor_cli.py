"""The `factory-doctor` command surface.

Written before `factory/doctor/cli.py` exists (T006 precedes T009): until the
module lands, tests here fail at import. Tests drive `main(argv)` directly,
the same way the existing CLI suites do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.doctor.cli import main


def _db_arg(path: Path) -> list[str]:
    return ["--db", str(path)]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "doctor.db"


def test_report_via_flags_then_list_shows_open_finding(db_path: Path, tmp_path: Path) -> None:
    rc = main(
        _db_arg(db_path)
        + [
            "report",
            "--key",
            "ops/manual",
            "--category",
            "ops",
            "--severity",
            "critical",
            "--summary",
            "manual finding",
            "--refs",
            "a:1",
            "--notes",
            "n1",
            "--source",
            "operator",
        ]
    )
    assert rc == 0

    rc = main(_db_arg(db_path) + ["list"])
    assert rc == 0


def test_report_re_report_recurs_and_list_orders(db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-07T10:00:00Z")
    base = [
        "report",
        "--key",
        "ops/recur",
        "--category",
        "ops",
        "--severity",
        "warning",
        "--summary",
        "first",
        "--refs",
        "a:1",
        "--source",
        "probe",
    ]
    assert main(_db_arg(db_path) + base) == 0

    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T11:00:00Z")
    assert main(_db_arg(db_path) + base[:-2] + ["--summary", "second", "--refs", "b:2"]) == 0

    assert main(_db_arg(db_path) + ["list"]) == 0


def test_resolve_records_resolution_and_re_report_regresses(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-07T10:00:00Z")
    assert main(_db_arg(db_path) + [
        "report",
        "--key",
        "ops/lifecycle",
        "--category",
        "ops",
        "--severity",
        "info",
        "--summary",
        "s",
        "--refs",
        "a:1",
        "--source",
        "probe",
    ]) == 0

    assert main(_db_arg(db_path) + [
        "resolve",
        "--key",
        "ops/lifecycle",
        "--reason",
        "landed",
    ]) == 0

    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    assert main(_db_arg(db_path) + [
        "report",
        "--key",
        "ops/lifecycle",
        "--category",
        "ops",
        "--severity",
        "info",
        "--summary",
        "it came back",
        "--refs",
        "a:2",
        "--source",
        "probe",
    ]) == 0

    assert main(_db_arg(db_path) + ["list"]) == 0


def test_batch_ingest_and_list(db_path: Path, tmp_path: Path) -> None:
    fixture = (
        Path(__file__).resolve().parents[1]
        / "specs"
        / "015-factory-doctor"
        / "seed-findings.json"
    )
    rc = main(_db_arg(db_path) + ["report", "--batch", str(fixture)])
    assert rc == 0

    rc = main(_db_arg(db_path) + ["list"])
    assert rc == 0


def test_batch_with_malformed_entry_refuses_whole_batch(db_path: Path, tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "doctor" / "batch-duplicate-key" / "findings.json"
    rc = main(_db_arg(db_path) + ["report", "--batch", str(fixture)])
    assert rc == 1

    rc = main(_db_arg(db_path) + ["list"])
    assert rc == 0


def test_resolve_unknown_key_exits_user(db_path: Path, tmp_path: Path) -> None:
    rc = main(_db_arg(db_path) + ["resolve", "--key", "ops/never", "--reason", "x"])
    assert rc == 1


def test_report_missing_required_field_exits_user(db_path: Path, tmp_path: Path) -> None:
    rc = main(_db_arg(db_path) + [
        "report",
        "--key",
        "ops/bad",
        "--category",
        "ops",
        "--severity",
        "critical",
        "--refs",
        "a:1",
    ])
    assert rc == 1


def test_report_unknown_severity_exits_user(db_path: Path, tmp_path: Path) -> None:
    rc = main(_db_arg(db_path) + [
        "report",
        "--key",
        "ops/bad",
        "--category",
        "ops",
        "--severity",
        "fatal",
        "--summary",
        "s",
        "--refs",
        "a:1",
    ])
    assert rc == 1


def test_list_is_deterministic_and_includes_age(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T12:00:00Z")

    for key, severity, occurrences in [
        ("ops/c-low", "warning", 5),
        ("ops/a-high", "critical", 1),
        ("ops/b-high-many", "critical", 3),
        ("ops/d-info", "info", 10),
    ]:
        for _ in range(occurrences):
            assert main(_db_arg(db_path) + [
                "report",
                "--key",
                key,
                "--category",
                "ops",
                "--severity",
                severity,
                "--summary",
                key,
                "--refs",
                "a:1",
                "--source",
                "probe",
            ]) == 0

    rc = main(_db_arg(db_path) + ["list"])
    assert rc == 0

    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    # header + 4 findings
    assert len(lines) == 5

    keys = [line.split()[0] for line in lines[1:]]
    assert keys == [
        "ops/b-high-many",
        "ops/a-high",
        "ops/c-low",
        "ops/d-info",
    ]

    for line in lines[1:]:
        parts = line.split()
        assert parts[1] in {"critical", "warning", "info"}
        assert parts[2] in {"open", "resolved", "regressed", "promoted"}
        assert parts[3].isdigit()
        assert parts[4].endswith(("m", "h", "d")) or parts[4].isdigit()


def test_regressed_finding_renders_distinctly(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-07T10:00:00Z")
    assert main(_db_arg(db_path) + [
        "report",
        "--key",
        "ops/reg",
        "--category",
        "ops",
        "--severity",
        "warning",
        "--summary",
        "s",
        "--refs",
        "a:1",
        "--source",
        "probe",
    ]) == 0

    assert main(_db_arg(db_path) + ["resolve", "--key", "ops/reg", "--reason", "fixed"]) == 0

    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    assert main(_db_arg(db_path) + [
        "report",
        "--key",
        "ops/reg",
        "--category",
        "ops",
        "--severity",
        "warning",
        "--summary",
        "back",
        "--refs",
        "a:2",
        "--source",
        "probe",
    ]) == 0

    assert main(_db_arg(db_path) + ["list"]) == 0
    out = capsys.readouterr().out
    assert "regressed" in out
