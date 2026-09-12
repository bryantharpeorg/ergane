"""US4: the exported read-only artifact reader is attempt-scoped."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def _artifact(
    gate: str,
    path: str,
    *,
    dispatch: str = "workflow-run-1",
    capture_id: str = "0" * 32,
    digest: str | None = None,
) -> GateArtifact:
    return GateArtifact(
        gate=gate,
        path=path,
        type=ArtifactType.COVERAGE,
        present=True,
        size=5,
        stored_path="/tmp/coverage.xml",
        status="permitted",
        provenance="new",
        dispatch=dispatch,
        capture_id=capture_id,
        digest=digest,
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


def test_attempt_artifacts_stay_scoped_to_one_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "verification.db"
    with connect(database) as connection:
        upsert_result(
            connection,
            _result(
                "us4",
                1,
                artifacts=(_artifact("test", "first.xml"),),
            ),
        )
        upsert_result(
            connection,
            _result(
                "us4",
                2,
                artifacts=(_artifact("test", "second.xml"),),
            ),
        )

    with connect_readonly(database) as connection:
        first = attempt_artifacts(connection, "134-epic", "us4", 1)
        second = attempt_artifacts(connection, "134-epic", "us4", 2)

    assert [artifact.path for artifact in first] == ["first.xml"]
    assert [artifact.path for artifact in second] == ["second.xml"]


def test_an_attempt_without_artifacts_reads_as_empty(
    tmp_path: Path,
) -> None:
    database = tmp_path / "verification.db"
    with connect(database) as connection:
        upsert_result(connection, _result("us4", 1, artifacts=()))

    with connect_readonly(database) as connection:
        artifacts = attempt_artifacts(connection, "134-epic", "us4", 1)

    assert artifacts == ()


def test_explicit_dispatch_and_capture_select_one_capture(
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
                    _artifact(
                        "test",
                        "first.xml",
                        dispatch="workflow-run-1",
                        capture_id="1" * 32,
                        digest="first-digest",
                    ),
                ),
            ),
        )
        upsert_result(
            connection,
            _result(
                "us4",
                1,
                artifacts=(
                    _artifact(
                        "test",
                        "second.xml",
                        dispatch="workflow-run-2",
                        capture_id="2" * 32,
                        digest="second-digest",
                    ),
                ),
            ),
        )

    with connect_readonly(database) as connection:
        selected = attempt_artifacts(
            connection,
            "134-epic",
            "us4",
            1,
            dispatch="workflow-run-2",
            capture_id="2" * 32,
        )

    assert [(artifact.path, artifact.digest) for artifact in selected] == [
        ("second.xml", "second-digest")
    ]
    assert [artifact.status for artifact in selected] == ["permitted"]
    assert [artifact.provenance for artifact in selected] == ["new"]


def test_an_ambiguous_old_style_request_refuses(
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
                    _artifact(
                        "test",
                        "first.xml",
                        dispatch="workflow-run-1",
                        capture_id="1" * 32,
                    ),
                ),
            ),
        )
        upsert_result(
            connection,
            _result(
                "us4",
                1,
                artifacts=(
                    _artifact(
                        "test",
                        "second.xml",
                        dispatch="workflow-run-2",
                        capture_id="2" * 32,
                    ),
                ),
            ),
        )

    with connect_readonly(database) as connection:
        with pytest.raises(ValueError, match="dispatch and capture_id"):
            attempt_artifacts(connection, "134-epic", "us4", 1)
