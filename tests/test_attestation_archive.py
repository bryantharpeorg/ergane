"""Story packet export and offline verification behavior."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
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


def _blocked_socket(*args: object, **kwargs: object) -> None:
    pytest.fail("packet verification must not use a socket")


def _selector(ordinal: int) -> tuple[str, str, str, str]:
    return ("test", "coverage.txt", f"dispatch-{ordinal}", f"capture-{ordinal}")


def _capture_artifact(
    root: Path,
    *,
    ordinal: int,
    source: Path,
    kind: ArtifactType = ArtifactType.COVERAGE,
    status: str = "permitted",
    present: bool = True,
    declared_path: str = "coverage.txt",
) -> tuple[tuple[str, str, str, str], GateArtifact]:
    artifact = _artifact(
        f"dispatch-{ordinal}",
        f"capture-{ordinal}",
        source,
        status=status,
        present=present,
    )
    artifact = GateArtifact(**{**artifact.__dict__, "type": kind, "path": declared_path})
    _verification(connect_verification(root / "verification.db"), ordinal, artifact)
    return ("test", declared_path, f"dispatch-{ordinal}", f"capture-{ordinal}"), artifact


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
        patch.setattr(socket, "socket", _blocked_socket)
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


def test_source_containment_types_and_aliases_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    artifacts = root / "artifacts" / "167" / "US3"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    symlink = artifacts / "linked.txt"
    symlink.symlink_to(outside)
    hardlink = artifacts / "hardlink.txt"
    os.link(artifacts / "coverage-2.txt", hardlink)
    fifo = artifacts / "pipe"
    os.mkfifo(fifo)

    selectors = (
        _capture_artifact(root, ordinal=7, source=symlink)[0],
        _capture_artifact(root, ordinal=8, source=hardlink)[0],
        _capture_artifact(root, ordinal=9, source=fifo)[0],
        _capture_artifact(root, ordinal=10, source=outside, stored_path=str(outside))[0],
    )
    result = export_packet(root, SUBJECT, output=root / "unsafe.zip", selectors=selectors)
    reasons = {item.identity: (item.status, item.reason) for item in result.items}
    assert reasons[selectors[0]][0] == "refused" and "symlink" in reasons[selectors[0]][1]
    assert reasons[selectors[1]][0] == "refused" and "hardlink" in reasons[selectors[1]][1]
    assert reasons[selectors[2]][0] == "refused" and "FIFO" in reasons[selectors[2]][1]
    assert reasons[selectors[3]][0] == "refused" and "containment" in reasons[selectors[3]][1]
    assert not symlink.exists() or symlink.is_symlink()
    assert fifo.exists() and stat.S_ISFIFO(fifo.stat().st_mode)


def test_raw_cli_transcripts_are_excluded_and_html_and_paths_are_escaped(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    transcript = root / "artifacts" / "167" / "US3" / ".codex" / "sessions" / "run.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text('{"raw cli transcript": "/home/private/alice/secret"}\n')
    selector, _ = _capture_artifact(
        root,
        ordinal=11,
        source=transcript,
        kind=ArtifactType.OPAQUE,
        declared_path=".codex/sessions/run.jsonl",
    )
    result = export_packet(root, SUBJECT, output=root / "raw.zip", selectors=(selector,))
    item = result.items[0]
    assert item.status == "refused" and "raw CLI transcript" in item.reason

    record_scoring_evaluation(
        EVIDENCE_JOURNAL,
        JudgeEvaluationRecord(
            evaluation_id="eval-html",
            scoring_job_id="job-1",
            scoring_call_ordinal=3,
            invocation_id="judge-1",
            key_alias="167:US3:1:judge",
            criteria_fingerprint="c" * 64,
            tested_revision="attempt-html",
            status="parse_error",
            model_alias="judge",
            scenario_results=((US3_S1, False, '<script>alert("x")</script> & /home/private/alice/notes'),),
            feedback="token=sk-live-abcdef ABC_TOKEN=abc123 <img src=x onerror=alert(1)>",
        ),
    )
    export_packet(root, SUBJECT, output=root / "text.zip", selectors=(_selector(2),))
    names, contents = _read_zip(root / "text.zip")
    report = contents["report.md"].decode()
    assert "<script>" not in report and "&lt;script&gt;" in report
    assert "/home/private/alice" not in report and "[PRIVATE_PATH]" in report
    assert "sk-live-abcdef" not in report and "ABC_TOKEN" not in report
    assert "<img" not in report


def test_opaque_bytes_are_selected_with_sensitivity_metadata(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    blob = root / "artifacts" / "167" / "US3" / "blob.bin"
    blob.write_bytes(b"\x00\x01opaque\n")
    selector, artifact = _capture_artifact(root, ordinal=12, source=blob, kind=ArtifactType.OPAQUE)
    result = export_packet(root, SUBJECT, output=root / "opaque.zip", selectors=(selector,))
    assert result.items[0].sensitivity == "opaque"
    manifest = read_manifest(root / "opaque.zip")
    assert manifest["entries"]["attachments/blob.bin"]["sensitivity"] == "opaque"
    report = (root / "opaque.zip").read_bytes()
    assert b"not redacted" in report and b"safe" not in report


def test_offline_verification_refuses_bad_names_bounds_and_bytes(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    archive = root / "good.zip"
    export_packet(root, SUBJECT, output=archive, selectors=(_selector(2),))
    names, contents = _read_zip(archive)
    manifest = json.loads(contents["manifest.json"])
    manifest["entries"]["attachments/coverage.txt"]["sha256"] = "0" * 64
    contents["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    contents["manifest.sha256"] = hashlib.sha256(contents["manifest.json"]).hexdigest().encode()

    corrupt = root / "corrupt.zip"
    with zipfile.ZipFile(corrupt, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in contents.items():
            output.writestr(name, data)
    with pytest.raises(PacketError, match="digest"):
        verify_packet(corrupt)

    unlisted = root / "unlisted.zip"
    with zipfile.ZipFile(unlisted, "w") as output:
        for name, data in contents.items():
            output.writestr(name, data)
        output.writestr("attachments/extra.txt", b"unlisted")
    with pytest.raises(PacketError, match="unlisted"):
        verify_packet(unlisted)

    duplicate = root / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as output:
        for name, data in contents.items():
            output.writestr(name, data)
        output.writestr("report.md", b"duplicate")
    with pytest.raises(PacketError, match="duplicate"):
        verify_packet(duplicate)

    bomb = root / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("manifest.json", contents["manifest.json"])
        output.writestr("manifest.sha256", contents["manifest.sha256"])
        output.writestr("report.md", contents["report.md"])
        output.writestr("attachments/coverage.txt", b"x" * 32)
    with pytest.raises(PacketError, match="expanded"):
        verify_packet(bomb, limits=ArchiveLimits(max_expanded_bytes=8))


def test_output_writes_are_atomic_and_collisions_are_preserved(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    collision = root / "collision.zip"
    collision.write_bytes(b"unchanged\n")
    with pytest.raises(PacketError, match="collision"):
        export_packet(root, SUBJECT, output=collision, selectors=(_selector(2),))
    assert collision.read_bytes() == b"unchanged\n"
    assert not list(root.glob("*.tmp"))

    output = root / "atomic.zip"
    export_packet(root, SUBJECT, output=output, selectors=(_selector(2),))
    before = output.read_bytes()
    temporary = root / "atomic.zip.tmp"
    temporary.write_bytes(b"partial")
    original_replace = os.replace

    def failing_replace(source: Path, destination: Path) -> None:
        if Path(destination) == output:
            raise OSError("simulated crash before publication")
        return original_replace(source, destination)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "replace", failing_replace)
        with pytest.raises(OSError, match="simulated crash"):
            export_packet(root, SUBJECT, output=output, selectors=(_selector(2),), force_output=True)
    assert output.read_bytes() == before
    assert temporary.exists()
    temporary.unlink()
