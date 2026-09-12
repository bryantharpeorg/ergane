"""US5: the activity resolves the durable artifact destination and stores it."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import fields
from pathlib import Path

import pytest

from factory.activities import verify_activities
from factory.activities.verify_activities import RunGatesInput, run_gates
from factory.verify.gates import SubprocessGateExecutor
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
    _gate_from_dict,
    _gate_to_dict,
    connect,
    connect_readonly,
    node_history,
    upsert_result,
)


def _stored_result(
    artifact: GateArtifact,
    *,
    dispatch: str,
) -> VerificationResult:
    gate = GateResult(
        name="test",
        command="true",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=0.0,
        output_tail="",
        artifacts=(artifact,),
    )
    return VerificationResult(
        epic_id="134-epic",
        node_id="us5",
        attempt=1,
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
        spec_ref="134/US5",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        dispatch=dispatch,
    )


def _result() -> GateResult:
    return GateResult(
        name="test",
        command="true",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=0.0,
        output_tail="",
    )


def _old_fields(result: GateResult) -> dict[str, object]:
    return {
        field.name: getattr(result, field.name)
        for field in fields(GateResult)
        if field.name != "artifacts"
    }


def _artifact(
    dispatch: str,
    *,
    digest: str,
    stored_path: str | None,
) -> GateArtifact:
    return GateArtifact(
        gate="test",
        path="coverage.xml",
        type=ArtifactType.COVERAGE,
        present=True,
        size=5,
        stored_path=stored_path,
        status="permitted",
        provenance="new",
        dispatch=dispatch,
        capture_id="0" * 32,
        digest=digest,
    )


async def _capture_destination(
    request: RunGatesInput, roots: list[Path]
) -> Path:
    seen: list[Path] = []

    def fake_gates(*args: object, **kwargs: object) -> list[GateResult]:
        seen.append(Path(kwargs["artifact_destination"]))
        return [_result()]

    def fake_resolver() -> tuple[Path, object, object]:
        return roots.pop(0), object(), "test"

    monkeypatch_request = pytest.MonkeyPatch()
    try:
        monkeypatch_request.setattr(
            verify_activities.gates, "run_gates", fake_gates
        )
        monkeypatch_request.setattr(
            verify_activities.gates,
            "resolve_gate_executor",
            lambda *args, **kwargs: object(),
        )
        monkeypatch_request.setattr(
            verify_activities, "resolve_factory_root", fake_resolver
        )
        await run_gates(request)
    finally:
        monkeypatch_request.undo()
    [destination] = seen
    return destination


async def test_destination_comes_only_from_the_engine_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    request = RunGatesInput(
        worktree_path=str(worktree),
        epic_id="134-epic",
        node_id="us5",
        attempt=3,
        dispatch="workflow-run-1",
    )

    destination = await _capture_destination(
        request, [tmp_path / "first-root"]
    )

    root = tmp_path / "first-root"
    assert destination.is_absolute()
    assert destination.parts == root.parts + (
        "artifacts",
        "134-epic",
        "us5",
        "3",
    )
    assert not destination.is_relative_to(worktree)

    other = await _capture_destination(
        request, [tmp_path / "second-root"]
    )
    assert other == tmp_path / "second-root" / "artifacts" / "134-epic" / "us5" / "3"


async def test_a_relative_runtime_root_becomes_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    request = RunGatesInput(
        worktree_path=str(tmp_path / "worktree"),
        epic_id="134-epic",
        node_id="us5",
        attempt=1,
        dispatch="workflow-run-1",
    )
    destination = await _capture_destination(request, [Path("relative-root")])

    assert destination == tmp_path / "relative-root" / "artifacts" / "134-epic" / "us5" / "1"


def test_gate_input_supplies_identity_and_no_composed_path() -> None:
    from factory.workgraph.workflow import _gate_input

    request = _gate_input(
        epic_id="134-epic",
        node_id="us5",
        attempt=4,
        dispatch="workflow-run-2",
        worktree_path="/tmp/node-worktree",
    )
    assert request.epic_id == "134-epic"
    assert request.node_id == "us5"
    assert request.attempt == 4
    assert request.dispatch == "workflow-run-2"
    assert request.worktree_path == "/tmp/node-worktree"
    assert request.factory_yaml_path is None


def test_artifacts_round_trip_with_capture_identity() -> None:
    digest = hashlib.sha256(b"bytes").hexdigest()
    artifact = _artifact("workflow-run-1", digest=digest, stored_path="/tmp/store")
    result = GateResult(
        name="test",
        command="true",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=0.0,
        output_tail="",
        artifacts=(artifact,),
    )

    [decoded] = _gate_from_dict(_gate_to_dict(result)).artifacts
    assert decoded == artifact


def test_an_old_artifact_free_gate_payload_is_readable(tmp_path: Path) -> None:
    result = _result()
    document = _gate_to_dict(result)
    document.pop("artifacts", None)

    decoded = _gate_from_dict(document)

    assert decoded.artifacts == ()
    assert _old_fields(decoded) == _old_fields(result)

    store = tmp_path / "verification.db"
    with sqlite3.connect(store) as connection:
        connection.execute(
            """
            CREATE TABLE verification_results (
                id INTEGER PRIMARY KEY,
                gate_results TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO verification_results (gate_results) VALUES (?)",
            (json.dumps([document]),),
        )
    row = sqlite3.connect(store).execute(
        "SELECT sql FROM sqlite_master WHERE name = 'verification_results'"
    ).fetchone()
    assert "gate_results TEXT NOT NULL" in row[0]


def test_a_repository_declaring_no_artifacts_round_trips(tmp_path: Path) -> None:
    result = _result()
    stored_result = VerificationResult(
        epic_id="134-epic",
        node_id="us5",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[result],
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
        spec_ref="134/US5",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
    )
    with connect(tmp_path / "verification.db") as connection:
        row = upsert_result(connection, stored_result)
    with connect(tmp_path / "verification.db") as connection:
        [stored] = [
            result
            for stored_result in node_history(connection, "134-epic", "us5")
            for result in stored_result.gate_results
        ]

    assert row == 1
    assert stored.artifacts == ()
    assert _old_fields(stored) == _old_fields(result)


def test_reused_ordinals_and_identical_redelivery_stay_distinct(
    tmp_path: Path,
) -> None:
    first_digest = hashlib.sha256(b"first").hexdigest()
    second_digest = hashlib.sha256(b"second").hexdigest()
    first = _artifact(
        "dispatch-1",
        digest=first_digest,
        stored_path=f"{tmp_path / 'dispatch-1'}",
    )
    second = _artifact(
        "dispatch-2",
        digest=second_digest,
        stored_path=f"{tmp_path / 'dispatch-2'}",
    )
    store = tmp_path / "verification.db"
    with connect(store) as connection:
        first_row = upsert_result(connection, _stored_result(first, dispatch="dispatch-1"))
        second_row = upsert_result(
            connection, _stored_result(second, dispatch="dispatch-2")
        )
        redelivery_row = upsert_result(
            connection, _stored_result(first, dispatch="dispatch-1")
        )

    with connect_readonly(store) as connection:
        history = node_history(connection, "134-epic", "us5")

    assert (first_row, second_row, redelivery_row) == (1, 2, 1)
    assert len(history) == 2
    assert history[0].dispatch == "dispatch-1"
    assert history[0].gate_results[0].artifacts[0].digest == first_digest
    assert history[1].dispatch == "dispatch-2"
    assert history[1].gate_results[0].artifacts[0].digest == second_digest


def test_identical_redelivery_is_idempotent_and_conflict_does_not_overwrite(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "captures"
    first = verify_activities.publish_artifact_capture(
        destination,
        dispatch="dispatch-1",
        capture_id="0" * 32,
        gate="test",
        path="coverage.xml",
        artifact_type=ArtifactType.COVERAGE,
        payload=b"first",
    )

    redelivered = verify_activities.publish_artifact_capture(
        destination,
        dispatch="dispatch-1",
        capture_id="0" * 32,
        gate="test",
        path="coverage.xml",
        artifact_type=ArtifactType.COVERAGE,
        payload=b"first",
    )

    assert redelivered == first
    assert Path(first.stored_path).read_bytes() == b"first"

    with pytest.raises(ValueError, match="conflicting bytes"):
        verify_activities.publish_artifact_capture(
            destination,
            dispatch="dispatch-1",
            capture_id="0" * 32,
            gate="test",
            path="coverage.xml",
            artifact_type=ArtifactType.COVERAGE,
            payload=b"conflicting",
        )

    assert Path(first.stored_path).read_bytes() == b"first"
