"""The `check` driver: registry iteration, skip handling, exit codes.

Written before `factory/doctor/cli.py` has a `check` subcommand and before
`factory/doctor/probes.py` exists (T011 precedes T014): until they land, tests
here fail at import or at runtime. Tests drive `main(argv)` directly, the same
way the existing CLI suites do.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from factory.doctor.cli import main
from factory.doctor.models import Finding, Severity, Status
from factory.doctor.probes import FindingReport, Probe, ServiceNotAnswering
from factory.doctor.store import connect, get_finding, list_findings


class FakeProbe:
    """A probe whose gather/evaluate are fully scripted."""

    name = "fake"

    def __init__(
        self,
        *,
        findings: list[FindingReport] | None = None,
        skip_service: str | None = None,
        gather_side_effect: Exception | None = None,
    ) -> None:
        self.findings = findings or []
        self.skip_service = skip_service
        self.gather_side_effect = gather_side_effect
        self.gather_calls: list[Any] = []
        self.evaluate_calls: list[Any] = []

    def gather(self) -> str:
        if self.gather_side_effect is not None:
            raise self.gather_side_effect
        if self.skip_service is not None:
            raise ServiceNotAnswering(self.skip_service)
        self.gather_calls.append("called")
        return "fake-snapshot"

    def evaluate(self, snapshot: Any) -> list[FindingReport]:
        self.evaluate_calls.append(snapshot)
        return list(self.findings)


def _db_arg(path: Path) -> list[str]:
    return ["--db", str(path)]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "doctor.db"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> list[Probe]:
    """A fresh, empty registry for one test."""
    reg: list[Probe] = []
    monkeypatch.setattr("factory.doctor.probes.REGISTRY", reg)
    monkeypatch.setattr("factory.doctor.cli.REGISTRY", reg)
    return reg


def test_registry_iteration_appended_probe_runs_without_driver_changes(
    db_path: Path, registry: list[Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    probe = FakeProbe(findings=[])
    registry.append(probe)

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 0
    assert probe.gather_calls == ["called"]
    assert probe.evaluate_calls == ["fake-snapshot"]


def test_service_not_answering_marks_probe_skipped_and_others_still_run(
    db_path: Path,
    registry: list[Probe],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    skipped = FakeProbe(skip_service="temporal")
    ok = FakeProbe(findings=[])
    registry.extend([skipped, ok])

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 2
    assert skipped.gather_calls == []
    assert ok.gather_calls == ["called"]
    err = capsys.readouterr().err
    assert "temporal" in err


def test_findings_file_through_store_with_source_set_to_probe_name(
    db_path: Path,
    registry: list[Probe],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    probe = FakeProbe(
        findings=[
            FindingReport(
                key="ops/test-from-probe",
                category="ops",
                severity=Severity.WARNING,
                summary="from probe",
                refs=["a:1"],
                notes="n",
            )
        ]
    )
    probe.name = "my-probe"
    registry.append(probe)

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 0  # warning only -> no new critical
    stored = get_finding(connect(db_path), "ops/test-from-probe")
    assert stored is not None
    assert stored.source == "my-probe"
    assert stored.status == Status.OPEN
    assert stored.occurrences == 1


def test_clean_run_exits_0_and_store_gains_nothing(
    db_path: Path, registry: list[Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    registry.append(FakeProbe(findings=[]))

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 0
    assert list_findings(connect(db_path)) == []


def test_new_critical_finding_exits_1(
    db_path: Path, registry: list[Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    registry.append(
        FakeProbe(
            findings=[
                FindingReport(
                    key="ops/critical-probe-finding",
                    category="ops",
                    severity=Severity.CRITICAL,
                    summary="bad",
                    refs=["a:1"],
                    notes=None,
                )
            ]
        )
    )

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 1
    stored = get_finding(connect(db_path), "ops/critical-probe-finding")
    assert stored is not None
    assert stored.severity == Severity.CRITICAL


def test_skip_exits_2_even_without_findings(
    db_path: Path,
    registry: list[Probe],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    registry.append(FakeProbe(skip_service="proxy"))

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 2


def test_skip_outranks_new_critical_exit_is_2(
    db_path: Path,
    registry: list[Probe],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("factory.doctor.cli._utcnow", lambda: "2026-08-08T10:00:00Z")
    registry.append(FakeProbe(skip_service="proxy"))
    registry.append(
        FakeProbe(
            findings=[
                FindingReport(
                    key="ops/critical-probe-finding",
                    category="ops",
                    severity=Severity.CRITICAL,
                    summary="bad",
                    refs=["a:1"],
                    notes=None,
                )
            ]
        )
    )

    rc = main(_db_arg(db_path) + ["check"])

    assert rc == 2
