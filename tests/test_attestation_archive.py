"""Story packet export and offline verification behavior."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest

from factory.attestation.archive import (
    ArchiveLimits,
    PacketError,
    export_packet,
    read_manifest,
    verify_packet,
)
from factory.attestation.journal import record_attempt_evidence, record_launch, record_scoring_evaluation
from factory.attestation.models import AttemptGitEvidence, GitFileChange, JudgeEvaluationRecord
from factory.usage.ledger import connect as connect_usage
from factory.usage.ledger import upsert_record
from factory.usage.models import Termination, UsageRecord
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
from factory.verify.store import connect as connect_verification
from factory.verify.store import upsert_result


SUBJECT = "org/repo:167/US3"


def _launch(invocation: str, ordinal: int, outcome: str) -> None:
    from factory.attestation.models import RungSelection

    record_launch(
        EVIDENCE_JOURNAL,
        _launch_record(
            invocation=invocation,
            ordinal=ordinal,
            outcome=outcome,
            persona="builder",
        ),
    )


def _launch_record(
    *, invocation: str, ordinal: int, outcome: str, persona: str
):
    from factory.attestation.models import LaunchRecord, RungSelection

    rung = RungSelection(persona=persona, runner="claude", route="gateway", model_aliases=("small",), reason="first")
    return LaunchRecord(
        target="org/repo",
        spec_revision="167-spec",
        spec_fingerprint="f" * 64,
        epic_id="167",
        epic_workflow_id="wf",
        epic_run_id="run",
        node_id="US3",
        invocation_id=invocation,
        ladder_ordinal=ordinal,
        launch_ordinal=ordinal,
        phase="build",
        form="node",
        scoring_job_id=None,
        scoring_call_ordinal=None,
        delivery_id=None,
        key_alias=f"167:US3:{ordinal}:{persona}",
        usage_id=None,
        actual_rung=rung,
        ladder=(rung,),
        transition_reason="dispatch",
        outcome=outcome,
        outcome_reason=None,
    )


def _evaluation(invocation: str, ordinal: int, verdict: str) -> JudgeEvaluationRecord:
    return JudgeEvaluationRecord(
        evaluation_id=f"eval-{ordinal}",
        scoring_job_id="job-1",
        scoring_call_ordinal=ordinal,
        invocation_id=invocation,
        key_alias=f"167:US3:{ordinal}:judge",
        criteria_fingerprint="c" * 64,
        tested_revision="attempt-" + str(ordinal),
        status=verdict,
        model_alias="judge",
        scenario_results=((US3_S1, verdict == "valid", "covered"),),
        feedback="failed " if verdict == "parse_error" else "passed",
        prompt_tokens=12,
        completion_tokens=3,
        usage_status="complete",
    )


def _artifact(invocation: str, capture: str, path: Path, *, status: str = "permitted", present: bool = True, stored_path: str | None = None) -> GateArtifact:
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return GateArtifact(
        gate="test",
        path="coverage.txt",
        type=ArtifactType.COVERAGE,
        present=present,
        size=path.stat().st_size if path.is_file() else None,
        stored_path=stored_path if stored_path is not None else (str(path) if present else None),
        status=status,
        provenance="captured",
        dispatch=invocation,
        capture_id=capture,
        digest=digest,
    )


def _verification(path: Path, attempt: int, artifact: GateArtifact, verdict: OverallVerdict = OverallVerdict.PASS) -> None:
    result = VerificationResult(
        epic_id="167",
        node_id="US3",
        attempt=attempt,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="true",
                status=GateStatus.PASS if verdict == OverallVerdict.PASS else GateStatus.FAIL,
                exit_code=0 if verdict == OverallVerdict.PASS else 1,
                duration_s=0.1,
                output_tail="",
                artifacts=(artifact,),
            )
        ],
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=["coverage.txt"],
            artifacts_present=artifact.present,
            passed=True,
        ),
        judge=None,
        judge_unavailable=False,
        criteria_drift=False,
        verdict=verdict,
        criteria_sha256="c" * 64,
        spec_ref="167/US3",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        dispatch=f"dispatch-{attempt}",
    )
    upsert_result(path, result)


def _write(root: Path) -> None:
    global EVIDENCE_JOURNAL
    EVIDENCE_JOURNAL = root / "attestation.db"
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source-worktree"
    artifacts = root / "artifacts" / "167" / "US3"
    artifacts.mkdir(parents=True, exist_ok=True)
    source.mkdir(exist_ok=True)
    artifact_paths = []
    for ordinal in (1, 2):
        path = artifacts / f"coverage-{ordinal}.txt"
        path.write_text(f"coverage {ordinal}\n")
        artifact_paths.append(path)
        artifact = _artifact(f"dispatch-{ordinal}", f"capture-{ordinal}", path)
        _verification(connect_verification(root / "verification.db"), ordinal, artifact)
    _launch("builder-1", 1, "failed")
    _launch("builder-2", 2, "succeeded")
    record_scoring_evaluation(EVIDENCE_JOURNAL, _evaluation("judge-1", 1, "parse_error"))
    record_scoring_evaluation(EVIDENCE_JOURNAL, _evaluation("judge-2", 2, "valid"))
    record_attempt_evidence(
        EVIDENCE_JOURNAL,
        AttemptGitEvidence(
            evidence_id="git-1",
            epic_id="167",
            node_id="US3",
            attempt=2,
            dispatch="dispatch-2",
            base_commit="b" * 40,
            attempted_commit="a" * 40,
            verified_commit="v" * 40,
            attempted_files=(GitFileChange(path="src/new.py", status="added"),),
            verified_files=(GitFileChange(path="src/new.py", status="added"),),
            log_tail="test output\n",
            log_truncated=False,
            tests_executed=("tests/test_one.py",),
            coverage_status="missing",
        ),
    )
    usage = connect_usage(root / "usage.db")
    for ordinal, status in ((1, "partial"), (2, "complete")):
        upsert_record(
            usage,
            UsageRecord(
                epic_id="167",
                node_id="US3",
                attempt=ordinal,
                persona="builder",
                spec_ref="167/US3",
                key_alias=f"167:US3:{ordinal}:builder",
                prompt_tokens=10 if status == "complete" else None,
                completion_tokens=2 if status == "complete" else None,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=None,
                spend_usd=0.01 if status == "complete" else None,
                final_usage_confirmed=status == "complete",
                termination=Termination.COMPLETED,
                issued_at="2026-01-01T00:00:00Z",
                torn_down_at="2026-01-01T00:01:00Z",
                usage_source="gateway",
                usage_status=status,
                cost_basis="gateway_usd",
            ),
        )
    usage.close()


US3_S1 = "US3-S1"
EVIDENCE_JOURNAL: Path | None = None


def _selector(ordinal: int) -> tuple[str, str, str, str]:
    return ("test", "coverage.txt", f"dispatch-{ordinal}", f"capture-{ordinal}")


def _read_zip(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        return names, {name: archive.read(name) for name in names}


def test_export_contains_manifest_report_exact_bytes_and_offline_verifies(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    output = root / "packet.zip"
    export_packet(root, SUBJECT, output=output, selectors=(_selector(2),))
    names, contents = _read_zip(output)
    assert names == ["manifest.json", "manifest.sha256", "report.md", "attachments/coverage.txt"]
    manifest = json.loads(contents["manifest.json"])
    assert manifest["schema_version"] == 1
    assert manifest["subject"] == SUBJECT
    assert len(manifest["content_revision"]) == 64
    assert manifest["spec_revision"] == "167-spec"
    assert manifest["entries"]["attachments/coverage.txt"]["sha256"] == hashlib.sha256(contents["attachments/coverage.txt"]).hexdigest()
    assert manifest["entries"]["attachments/coverage.txt"]["identity"]["dispatch"] == "dispatch-2"
    assert contents["attachments/coverage.txt"] == b"coverage 2\n"
    assert "US3-S1" in contents["report.md"].decode() and "passed" in contents["report.md"].decode()
    assert all("/tmp/" not in text.decode(errors="ignore") for text in contents.values())

    relocated = tmp_path / "elsewhere" / "packet.zip"
    relocated.parent.mkdir()
    shutil.move(output, relocated)
    source = root / "source-worktree"
    shutil.rmtree(source)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("socket.socket", pytest.fail("packet verification must not use a socket"))
        verify_packet(relocated)
    assert read_manifest(relocated)["schema_version"] == 1


def test_identical_evidence_is_reproducible_and_new_evidence_is_successor(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    first = root / "first.zip"
    second = root / "second.zip"
    result = export_packet(root, SUBJECT, output=first, selectors=(_selector(2),))
    export_packet(root, SUBJECT, output=second, selectors=(_selector(2),))
    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_size == second.stat().st_size
    assert (first.stat().st_mode & 0o077) == 0

    original = first.read_bytes()
    changed = root / "artifacts" / "167" / "US3" / "coverage-2.txt"
    changed.write_text("coverage changed\n")
    successor = export_packet(root, SUBJECT, output=root / "third.zip", selectors=(_selector(2),))
    assert successor.revision != result.revision
    assert successor.predecessor == result.revision
    assert first.read_bytes() == original


def test_missing_expired_refused_oversized_items_remain_visible(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    verification = connect_verification(root / "verification.db")
    artifacts_dir = root / "artifacts" / "167" / "US3"
    _verification(
        verification,
        3,
        _artifact("dispatch-3", "capture-3", artifacts_dir / "absent.txt", present=False),
        verdict=OverallVerdict.FAIL,
    )
    expired_path = artifacts_dir / "expired.txt"
    expired_path.write_text("expired\n")
    _verification(
        verification,
        4,
        _artifact("dispatch-4", "capture-4", expired_path, status="expired"),
        verdict=OverallVerdict.FAIL,
    )
    refused_path = artifacts_dir / "refused.txt"
    refused_path.write_text("refused\n")
    _verification(
        verification,
        5,
        _artifact("dispatch-5", "capture-5", refused_path, status="refused"),
        verdict=OverallVerdict.FAIL,
    )
    oversized_path = artifacts_dir / "oversized.txt"
    oversized_path.write_text("too large\n")
    _verification(
        verification,
        6,
        _artifact("dispatch-6", "capture-6", oversized_path),
        verdict=OverallVerdict.FAIL,
    )
    verification.close()

    result = export_packet(
        root,
        SUBJECT,
        output=root / "incomplete.zip",
        selectors=(
            _selector(1),
            _selector(2),
            _selector(3),
            _selector(4),
            _selector(5),
            _selector(6),
        ),
        limits=ArchiveLimits(max_artifact_bytes=4),
    )
    reasons = {item.identity: (item.status, item.reason) for item in result.items}
    assert reasons[_selector(1)][0] == "included"
    assert reasons[_selector(3)] == ("missing", "artifact was not stored")
    assert reasons[_selector(4)][0] == "expired"
    assert reasons[_selector(5)][0] == "refused"
    assert reasons[_selector(6)][0] == "oversized"
    assert result.complete is False
    manifest = read_manifest(root / "incomplete.zip")
    assert set(reasons).issubset(manifest["completeness"])

    with pytest.raises(PacketError) as error:
        export_packet(root, SUBJECT, output=root / "strict.zip", selectors=(_selector(3),), strict=True)
    assert "incomplete" in str(error.value)
    assert not (root / "strict.zip").exists()
