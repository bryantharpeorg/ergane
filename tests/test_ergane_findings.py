"""US4 `ergane findings` surface tests: list filters and JSON mode.

These cases seed a findings store with known severities and statuses, then
assert that `findings list` filters by `--severity` and `--status` and that
`--json` emits the filtered list as JSON.

Written before `factory/cli/doctor.py` exists (T025 precedes T027): until it
lands, `ergane findings` is an unknown noun.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli import main as main_module
from factory.doctor import cli as doctor_cli
from factory.doctor.store import connect, promote, report, resolve
from factory.doctor.models import Finding, Severity, Status


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: list[str]) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def invoke() -> Callable[..., Run]:
    def _caller(*argv: str) -> Run:
        return _invoke(list(argv))
    return _caller


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "doctor.db"


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """A store with one finding per severity/status combination we care about."""
    conn = connect(db_path)
    try:
        _seed = [
            ("ops/critical-open", Severity.CRITICAL, Status.OPEN),
            ("ops/warning-resolved", Severity.WARNING, Status.RESOLVED),
            ("ops/info-promoted", Severity.INFO, Status.PROMOTED),
            ("ops/critical-resolved", Severity.CRITICAL, Status.RESOLVED),
        ]
        for key, severity, status in _seed:
            report(
                conn,
                Finding(
                    key=key,
                    category="ops",
                    severity=severity,
                    status=Status.OPEN,
                    summary=key,
                    refs=["a:1"],
                    notes=None,
                    source="test",
                    occurrences=1,
                    first_seen="2026-08-10T09:00:00Z",
                    last_seen="2026-08-10T09:00:00Z",
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                ),
                seen_at="2026-08-10T09:00:00Z",
            )
            if status is Status.RESOLVED:
                resolve(conn, key, reason="fixed", resolved_at="2026-08-10T10:00:00Z")
            elif status is Status.PROMOTED:
                promote(conn, [key], spec_dir=f"/tmp/promoted/{key}", seen_at="2026-08-10T10:00:00Z")
    finally:
        conn.close()
    return db_path


# Override the private `_utcnow` so the reported ages are deterministic.
@pytest.fixture(autouse=True)
def _freeze_doctor_utcnow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor_cli, "_utcnow", lambda: "2026-08-10T12:00:00Z")


def test_findings_list_unfiltered_shows_all_rows(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke("findings", "list", "--db", str(db_path))
    assert result.code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # header + 4 findings
    assert len(lines) == 5


def test_findings_list_filter_by_severity(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke("findings", "list", "--db", str(db_path), "--severity", "critical")
    assert result.code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3  # header + 2 critical findings
    for line in lines[1:]:
        assert "critical" in line
    assert "warning" not in result.stdout
    assert "info" not in result.stdout


def test_findings_list_filter_by_status(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke("findings", "list", "--db", str(db_path), "--status", "resolved")
    assert result.code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3  # header + 2 resolved findings
    for line in lines[1:]:
        assert "resolved" in line
    assert "open" not in result.stdout or "resolved" in result.stdout


def test_findings_list_filter_by_severity_and_status(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke(
        "findings", "list", "--db", str(db_path),
        "--severity", "critical", "--status", "resolved",
    )
    assert result.code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2  # header + 1 matching finding
    body = "\n".join(lines[1:])
    assert "critical" in body
    assert "resolved" in body


def test_findings_list_json_emits_filtered_document(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke(
        "findings", "list", "--db", str(db_path),
        "--severity", "info", "--json"
    )
    assert result.code == 0
    document = result.json
    assert isinstance(document, list)
    assert len(document) == 1
    assert document[0]["key"] == "ops/info-promoted"


def test_findings_list_bad_severity_is_usage_error(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke(
        "findings", "list", "--db", str(db_path), "--severity", "fatal"
    )
    assert result.code == 2


def test_findings_list_bad_status_is_usage_error(
    invoke: Callable[..., Run], db_path: Path, seeded_db: Path
) -> None:
    result = invoke(
        "findings", "list", "--db", str(db_path), "--status", "orphaned"
    )
    assert result.code == 2
