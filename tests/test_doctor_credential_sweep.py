"""FR-010 credential sweep for the doctor component.

The pattern mirrors `tests/test_final_sweep.py`: a canary master key is placed
in the environment and driven through every surface that could carry it, then
grep-backed assertions prove it never reaches findings, events, snapshots,
scaffold text, or CLI output. Written before the full promote/loop
implementation exists (T017 precedes T019): it must fail until the sweep is
wired.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from factory.doctor.cli import main
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.probes import FindingReport

SECRET = "sk-canary-4f21bd8e6c0a47d9b3-master"
CREDENTIAL_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_MODULES = sorted((REPO_ROOT / "factory" / "doctor").rglob("*.py"))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "doctor.db"


def _db_arg(path: Path) -> list[str]:
    return ["--db", str(path)]


def test_no_doctor_module_carries_a_credential_literal() -> None:
    for path in DOCTOR_MODULES:
        found = CREDENTIAL_RE.findall(path.read_text(encoding="utf-8"))
        assert not found, f"{path.relative_to(REPO_ROOT)} contains what looks like a key: {found}"


def test_report_does_not_echo_secret_in_finding_or_event(
    db_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LITELLM_MASTER_KEY", SECRET)
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")

    rc = main(
        _db_arg(db_path)
        + [
            "report",
            "--key",
            "ops/secret-in-notes",
            "--category",
            "ops",
            "--severity",
            "warning",
            "--summary",
            f"notes may contain {SECRET}",
            "--refs",
            "a:1",
            "--notes",
            f"again {SECRET}",
        ]
    )
    # The CLI is allowed to refuse, but if it accepts it must not leak.
    assert rc in (0, 1)

    out, err = capsys.readouterr()
    assert SECRET not in out
    assert SECRET not in err

    conn = sqlite3.connect(db_path)
    try:
        for table in ("findings", "finding_events"):
            for row in conn.execute(f"SELECT * FROM {table}"):
                joined = " ".join(str(c) for c in row)
                assert SECRET not in joined, f"{table} leaked secret: {joined}"
    finally:
        conn.close()


def test_check_does_not_leak_secret_through_probe_output(
    db_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")

    @dataclass(frozen=True)
    class SnapshotWithSecret:
        secret: str

    class SecretProbe:
        name = "secret-carrier"

        def gather(self) -> SnapshotWithSecret:
            return SnapshotWithSecret(secret=SECRET)

        def evaluate(self, snapshot: Any) -> list[FindingReport]:
            return [
                FindingReport(
                    key="ops/secret-in-probe",
                    category="ops",
                    severity=Severity.WARNING,
                    summary=f"probe saw {snapshot.secret}",
                    refs=["a:1"],
                    notes=f"notes {snapshot.secret}",
                )
            ]

    monkeypatch.setattr("factory.doctor.probes.REGISTRY", [SecretProbe()])
    monkeypatch.setattr("factory.doctor.cli.REGISTRY", [SecretProbe()])

    rc = main(_db_arg(db_path) + ["check"])
    assert rc == 0

    out, err = capsys.readouterr()
    assert SECRET not in out
    assert SECRET not in err

    conn = sqlite3.connect(db_path)
    try:
        for table in ("findings", "finding_events"):
            for row in conn.execute(f"SELECT * FROM {table}"):
                joined = " ".join(str(c) for c in row)
                assert SECRET not in joined, f"{table} leaked secret: {joined}"
    finally:
        conn.close()


def test_promote_scaffold_does_not_leak_secret(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    specs_root = tmp_path / "specs"

    finding = Finding(
        key="ops/secret-finding",
        category="ops",
        severity=Severity.WARNING,
        status=Status.OPEN,
        summary=f"summary {SECRET}",
        refs=[f"file.py:1 # {SECRET}"],
        notes=f"notes {SECRET}",
        source="operator",
        occurrences=1,
        first_seen="",
        last_seen="",
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    from factory.doctor.scaffold import scaffold_spec

    spec_text, plan_text, tasks_text = scaffold_spec(
        slug="secret-fix", findings=[finding], specs_root="specs", target_repo="."
    )
    assert SECRET not in spec_text
    assert SECRET not in plan_text
    assert SECRET not in tasks_text


def test_credential_pattern_matches_secret() -> None:
    assert CREDENTIAL_RE.search(SECRET)
