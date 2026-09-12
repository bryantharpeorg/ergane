"""US4: the exported read-only artifact reader is attempt-scoped."""

from __future__ import annotations

from pathlib import Path

from factory.verify.models import (
    ArtifactType,
    GateArtifact,
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.verify.store import (
    attempt_artifacts,
    connect,
    connect_readonly,
    upsert_result,
)


def _artifact(gate: str, path: str) -> GateArtifact:
    return GateArtifact(
        gate=gate,
        path=path,
        type=ArtifactType.COVERAGE,
        present=True,
        size=5,
        stored_path="/tmp/coverage.xml",
        status="permitted",
        provenance="new",
    )


def _result(
    node_id: str,
    attempt: int,
    *,
    artifacts: tuple[GateArtifact, ...],
) -> VerificationResult:
    gate = GateResult(
        name="test",
        command="true",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=0.0,
        output_tail="",
        artifacts=artifacts,
    )
    return VerificationResult(
        epic_id="134-epic",
        node_id=node_id,
        attempt=attempt,
        form=VerificationForm.PHASE,
        gate_results=[gate],
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=None,
        judge_unavailable=False,
        criteria_drift=False,
        verdict=OverallVerdict.PASS,
        criteria_sha256="a" * 64,
        spec_ref="134/US4",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        dispatch="workflow-run-1",
    )


def test_attempt_artifacts_returns_their_declared_fields(
    tmp_path: Path,
) -> None:
    database = tmp_path / "verification.db"
    with connect(database) as connection:
        upsert_result(
            connection,
            _result(
                "us4",
                1,
                artifacts=(
                    _artifact("test", "coverage.xml"),
                    _artifact("audit", "sbom.json"),
                ),
            ),
        )

    with connect_readonly(database) as connection:
        artifacts = attempt_artifacts(connection, "134-epic", "us4", 1)

    assert [(artifact.gate, artifact.path) for artifact in artifacts] == [
        ("test", "coverage.xml"),
        ("audit", "sbom.json"),
    ]
    assert [artifact.type for artifact in artifacts] == [
        ArtifactType.COVERAGE,
        ArtifactType.COVERAGE,
    ]
    assert all(artifact.present for artifact in artifacts)
    assert all(
        artifact.stored_path == "/tmp/coverage.xml" for artifact in artifacts
    )
