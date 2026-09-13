"""Story packet export and offline verification behavior."""

from __future__ import annotations

import dataclasses
import hashlib
import gc
import json
import math
import os
import shutil
import socket
import stat
import sqlite3
import zipfile
import zlib
from contextlib import closing
from pathlib import Path

import pytest

from factory.attestation.archive import (
    ArchiveLimits,
    PacketError,
    export_packet,
    read_manifest,
    verify_packet,
)
from factory.attestation.journal import record_launch, record_scoring_evaluation
from factory.attestation.models import JudgeEvaluationRecord, LaunchRecord, RungSelection
from factory.usage.ledger import connect as connect_usage, upsert_record
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
from factory.verify.store import connect as connect_verification, upsert_result

SUBJECT = "org/repo:167/US3"
US3_S1 = "US3-S1"


def _launch_record(*, invocation: str, ordinal: int, outcome: str, node_id: str = "US3") -> LaunchRecord:
    rung = RungSelection("builder", "claude", "gateway", ("small",), "first")
    return LaunchRecord(
        target="org/repo", spec_revision="167-spec", spec_fingerprint="f" * 64,
        epic_id="167", epic_workflow_id="wf", epic_run_id="run", node_id=node_id,
        invocation_id=invocation, ladder_ordinal=ordinal, launch_ordinal=ordinal,
        phase="build", form="node", scoring_job_id=None, scoring_call_ordinal=None,
        delivery_id=None, key_alias=f"167:{node_id}:{ordinal}:builder", usage_id=None,
        actual_rung=rung, ladder=(rung,), transition_reason="dispatch", outcome=outcome,
    )


def _evaluation(invocation: str, ordinal: int, verdict: str) -> JudgeEvaluationRecord:
    return JudgeEvaluationRecord(
        evaluation_id=f"eval-{ordinal}", scoring_job_id="job-1",
        scoring_call_ordinal=ordinal, invocation_id=invocation,
        key_alias=f"167:US3:{ordinal}:judge", criteria_fingerprint="c" * 64,
        tested_revision=f"attempt-{ordinal}", status=verdict, model_alias="judge",
        scenario_results=((US3_S1, verdict == "valid", "covered"),),
        feedback="failed" if verdict == "parse_error" else "passed",
        prompt_tokens=12, completion_tokens=3, usage_status="complete",
    )


def _artifact(
    invocation: str, capture: str, path: Path, *, status: str = "permitted",
    present: bool = True, stored_path: str | None = None,
) -> GateArtifact:
    exists = path.is_file()
    return GateArtifact(
        gate="test", path="coverage.txt", type=ArtifactType.COVERAGE, present=present,
        size=path.stat().st_size if exists else None,
        stored_path=stored_path if stored_path is not None else (str(path) if present else None),
        status=status, provenance="captured", dispatch=invocation, capture_id=capture,
        digest=hashlib.sha256(path.read_bytes()).hexdigest() if exists else None,
    )


def _verification(
    store: Path, attempt: int, artifact: GateArtifact, verdict: OverallVerdict = OverallVerdict.PASS,
) -> None:
    passed = verdict == OverallVerdict.PASS
    with closing(connect_verification(store)) as connection:
        upsert_result(connection, VerificationResult(
        epic_id="167", node_id="US3", attempt=attempt, form=VerificationForm.PHASE,
        gate_results=(GateResult(
            name="test", command="true", status=GateStatus.PASS if passed else GateStatus.FAIL,
            exit_code=0 if passed else 1, duration_s=0.1, output_tail="", artifacts=(artifact,),
        ),),
        output_check=OutputCheck(
            write_scope="worktree", has_diff=True, expected_artifacts=["coverage.txt"],
            artifacts_present=artifact.present, passed=True,
        ),
        judge=None, judge_unavailable=False, criteria_drift=False, verdict=verdict,
        criteria_sha256="c" * 64, spec_ref="167/US3",
        started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:01:00Z",
            dispatch=f"dispatch-{attempt}",
        ))


def _usage(path: Path, node_id: str, ordinal: int, status: str) -> None:
    complete = status == "complete"
    with closing(connect_usage(path)) as usage:
        upsert_record(usage, UsageRecord(
            epic_id="167", node_id=node_id, attempt=ordinal, persona="builder",
            spec_ref=f"167/{node_id}", key_alias=f"167:{node_id}:{ordinal}:builder",
            prompt_tokens=10 if complete else None,
            completion_tokens=2 if complete else None, cache_read_tokens=None,
            cache_write_tokens=None, request_count=None,
            spend_usd=0.01 if complete else None, final_usage_confirmed=complete,
            termination=Termination.COMPLETED, issued_at="2026-01-01T00:00:00Z",
            torn_down_at="2026-01-01T00:01:00Z", usage_source="gateway",
            usage_status=status, cost_basis="gateway_usd",
        ))


def _write(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    journal = root / "attestation.db"
    (root / "source-worktree").mkdir()
    artifacts = root / "artifacts" / "167" / "US3"
    artifacts.mkdir(parents=True)
    verification = root / "verification.db"
    for ordinal in (1, 2):
        path = artifacts / f"coverage-{ordinal}.txt"
        path.write_text(f"coverage {ordinal}\n")
        _verification(verification, ordinal, _artifact(
            f"dispatch-{ordinal}", f"capture-{ordinal}", path
        ))
    record_launch(journal, _launch_record(invocation="builder-1", ordinal=1, outcome="failed"))
    record_launch(journal, _launch_record(invocation="builder-2", ordinal=2, outcome="succeeded"))
    record_scoring_evaluation(journal, _evaluation("judge-1", 1, "parse_error"))
    record_scoring_evaluation(journal, _evaluation("judge-2", 2, "valid"))
    _usage(root / "usage.db", "US3", 1, "partial")
    _usage(root / "usage.db", "US3", 2, "complete")


def _selector(ordinal: int) -> tuple[str, str, str, str]:
    return "test", "coverage.txt", f"dispatch-{ordinal}", f"capture-{ordinal}"


def _capture_artifact(
    root: Path, ordinal: int, source: Path, *, kind: ArtifactType = ArtifactType.COVERAGE,
    status: str = "permitted", present: bool = True, declared_path: str = "coverage.txt",
    stored_path: str | None = None, capture: str | None = None,
) -> tuple[str, str, str, str]:
    capture = capture or f"capture-{ordinal}"
    artifact = _artifact(
        f"dispatch-{ordinal}", capture, source, status=status, present=present,
        stored_path=stored_path,
    )
    artifact = dataclasses.replace(artifact, type=kind, path=declared_path)
    _verification(root / "verification.db", ordinal, artifact)
    return "test", declared_path, f"dispatch-{ordinal}", capture


def _read_zip(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        return names, {name: archive.read(name) for name in names}


def _write_zip(path: Path, contents: dict[str, bytes], **extra: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        for name, data in extra.items():
            archive.writestr(name, data)


def _blocked_socket(*args: object, **kwargs: object) -> None:
    pytest.fail("packet verification must not use a socket")


def test_export_contains_manifest_report_exact_bytes_and_offline_verifies(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    output = root / "packet.zip"
    export_packet(root, SUBJECT, output=output, selectors=(_selector(2),))
    names, contents = _read_zip(output)
    assert names == ["manifest.json", "manifest.sha256", "report.md", "attachments/coverage.txt"]
    manifest = json.loads(contents["manifest.json"])
    entry = manifest["entries"]["attachments/coverage.txt"]
    assert manifest["schema_version"] == 1 and manifest["subject"] == SUBJECT
    assert len(manifest["content_revision"]) == 64 and manifest["spec_revision"] == "167-spec"
    assert entry["sha256"] == hashlib.sha256(contents["attachments/coverage.txt"]).hexdigest()
    assert entry["identity"]["dispatch"] == "dispatch-2"
    assert contents["attachments/coverage.txt"] == b"coverage 2\n"
    report = contents["report.md"].decode()
    assert "US3-S1" in report and "passed" in report
    assert all("/tmp/" not in value.decode(errors="ignore") for value in contents.values())

    relocated = tmp_path / "elsewhere" / "packet.zip"
    relocated.parent.mkdir()
    shutil.move(output, relocated)
    shutil.rmtree(root / "source-worktree")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "socket", _blocked_socket)
        assert verify_packet(relocated, strict=True)["schema_version"] == 1
    assert read_manifest(relocated)["schema_version"] == 1


def test_export_scopes_evidence_to_the_selected_subject(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    journal = root / "attestation.db"
    record_launch(journal, _launch_record(
        invocation="builder-other", ordinal=99, outcome="succeeded", node_id="US4"
    ))
    record_scoring_evaluation(journal, JudgeEvaluationRecord(
        evaluation_id="eval-other", scoring_job_id="job-other", scoring_call_ordinal=99,
        invocation_id="judge-other", key_alias="167:US4:1:judge",
        criteria_fingerprint="c" * 64, tested_revision="attempt-other", status="valid",
        model_alias="judge", scenario_results=((US3_S1, True, "another node"),),
        feedback="unrelated judge",
    ))
    _usage(root / "usage.db", "US4", 99, "complete")
    export_packet(root, SUBJECT, output=root / "scoped.zip", selectors=(_selector(2),))
    report = _read_zip(root / "scoped.zip")[1]["report.md"].decode()
    assert "other" not in report and "9.99" not in report


def test_packet_reads_do_not_migrate_the_journal(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    journal = root / "attestation.db"
    gc.collect()
    with closing(sqlite3.connect(journal)) as connection:
        connection.execute("PRAGMA journal_mode = DELETE")
    before = journal.read_bytes()

    export_packet(root, SUBJECT, output=root / "readonly-source.zip", selectors=(_selector(2),))

    assert journal.read_bytes() == before
    assert not (root / "attestation.db-wal").exists()
    assert not (root / "attestation.db-shm").exists()


def test_identical_evidence_is_reproducible_and_new_evidence_is_successor(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    first, second = root / "first.zip", root / "second.zip"
    result = export_packet(root, SUBJECT, output=first, selectors=(_selector(2),))
    export_packet(root, SUBJECT, output=second, selectors=(_selector(2),))
    assert first.read_bytes() == second.read_bytes()
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
    artifacts = root / "artifacts" / "167" / "US3"
    cases = (
        (3, "missing", False, "permitted", "absent.txt", 0),
        (4, "expired", True, "expired", "expired.txt", 6),
        (5, "refused", True, "refused", "refused.txt", 6),
        (6, "oversized", True, "permitted", "oversized.txt", 64),
    )
    for ordinal, _, present, status, name, size in cases:
        path = artifacts / name
        if present:
            path.write_text("x" * size)
        _verification(root / "verification.db", ordinal, _artifact(
            f"dispatch-{ordinal}", f"capture-{ordinal}", path,
            status=status, present=present,
        ), OverallVerdict.FAIL)
    selectors = tuple(_selector(ordinal) for ordinal in range(1, 7))
    result = export_packet(root, SUBJECT, output=root / "incomplete.zip", selectors=selectors,
                           limits=ArchiveLimits(max_artifact_bytes=32))
    reasons = {item.identity: (item.status, item.reason) for item in result.items}
    assert [reasons[selector][0] for selector in selectors] == [
        "included", "included", "missing", "expired", "refused", "oversized"
    ]
    assert result.complete is False
    manifest = read_manifest(root / "incomplete.zip")
    assert manifest["completeness"] == {
        identity.key(): {"status": values[0], "reason": values[1]}
        for identity, values in reasons.items()
    }
    with pytest.raises(PacketError, match="incomplete"):
        export_packet(root, SUBJECT, output=root / "strict.zip",
                      selectors=(_selector(3),), strict=True)
    assert not (root / "strict.zip").exists()


def test_source_containment_types_aliases_and_names_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    artifacts = root / "artifacts" / "167" / "US3"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    symlink = artifacts / "linked.txt"
    symlink.symlink_to(outside)
    hardlink = artifacts / "hardlink.txt"
    os.link(artifacts / "coverage-2.txt", hardlink)
    same = artifacts / "same.txt"
    same.write_text("same\n")
    fifo = artifacts / "pipe"
    os.mkfifo(fifo)
    selectors = (
        _capture_artifact(root, 7, symlink),
        _capture_artifact(root, 8, hardlink),
        _capture_artifact(root, 9, fifo),
        _capture_artifact(root, 10, outside, stored_path=str(outside)),
    )
    result = export_packet(root, SUBJECT, output=root / "unsafe.zip", selectors=selectors)
    assert [item.status for item in result.items] == ["refused"] * 4
    assert "symlink" in result.items[0].reason and "hardlink" in result.items[1].reason
    assert "FIFO" in result.items[2].reason and "containment" in result.items[3].reason
    assert fifo.exists() and stat.S_ISFIFO(fifo.stat().st_mode)

    duplicate = (
        _capture_artifact(root, 11, same, declared_path="same.txt"),
        _capture_artifact(root, 12, same, declared_path="same.txt",
                           capture="../escape"),
    )
    with pytest.raises(PacketError, match="unsafe artifact name"):
        export_packet(root, SUBJECT, output=root / "names.zip", selectors=duplicate)
    assert not (root / "names.zip").exists()


def test_raw_transcripts_are_excluded_and_text_and_opaque_are_handled(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    transcript = root / "artifacts" / "167" / "US3" / ".codex" / "sessions" / "run.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"raw cli transcript": "/home/private/alice/secret"}\n')
    raw_selector = _capture_artifact(
        root, 11, transcript, kind=ArtifactType.OPAQUE,
        declared_path=".codex/sessions/run.jsonl",
    )
    raw = export_packet(root, SUBJECT, output=root / "raw.zip", selectors=(raw_selector,))
    assert raw.items[0].status == "refused"
    assert "raw CLI transcript" in raw.items[0].reason

    record_scoring_evaluation(root / "attestation.db", JudgeEvaluationRecord(
        evaluation_id="eval-html", scoring_job_id="job-1", scoring_call_ordinal=3,
        invocation_id="judge-1", key_alias="167:US3:1:judge",
        criteria_fingerprint="c" * 64, tested_revision="attempt-html",
        status="parse_error", model_alias="judge",
        scenario_results=((US3_S1, False, '<script>alert("x")</script> & /home/private/alice/notes'),),
        feedback="token=sk-live-abcdef ABC_TOKEN=abc123 <img src=x onerror=alert(1)>",
    ))
    export_packet(root, SUBJECT, output=root / "text.zip", selectors=(_selector(2),))
    report = _read_zip(root / "text.zip")[1]["report.md"].decode()
    assert "<script>" not in report and "&lt;script&gt;" in report
    assert "/home/private/alice" not in report and "[PRIVATE_PATH]" in report
    assert "sk-live-abcdef" not in report and "ABC_TOKEN" not in report and "<img" not in report

    blob = root / "artifacts" / "167" / "US3" / "blob.bin"
    blob.write_bytes(b"\x00\x01opaque\n")
    opaque_selector = _capture_artifact(root, 12, blob, kind=ArtifactType.OPAQUE,
                                        declared_path="blob.bin")
    opaque = export_packet(root, SUBJECT, output=root / "opaque.zip",
                           selectors=(opaque_selector,))
    assert opaque.items[0].sensitivity == "opaque"
    manifest = read_manifest(root / "opaque.zip")
    assert manifest["entries"]["attachments/blob.bin"]["sensitivity"] == "opaque"
    report = _read_zip(root / "opaque.zip")[1]["report.md"]
    assert b"not redacted" in report and b"safe" not in report


def test_offline_verification_refuses_bad_names_bounds_and_manifests(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    archive = root / "good.zip"
    export_packet(root, SUBJECT, output=archive, selectors=(_selector(2),))
    _, contents = _read_zip(archive)
    manifest = json.loads(contents["manifest.json"])
    manifest["entries"]["attachments/coverage.txt"]["sha256"] = "0" * 64
    contents["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    contents["manifest.sha256"] = hashlib.sha256(contents["manifest.json"]).hexdigest().encode()
    _write_zip(root / "digest.zip", contents)
    with pytest.raises(PacketError, match="entry digest mismatch"):
        verify_packet(root / "digest.zip")
    _write_zip(root / "unlisted.zip", contents, **{"attachments/extra.txt": b"unlisted"})
    with pytest.raises(PacketError, match="unlisted"):
        verify_packet(root / "unlisted.zip")
    _write_zip(root / "duplicate.zip", contents, **{"report.md": b"duplicate"})
    with pytest.raises(PacketError, match="duplicate"):
        verify_packet(root / "duplicate.zip")

    manifest = json.loads(contents["manifest.json"])
    manifest["entries"].pop("report.md")
    bad_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    bad_contents = dict(contents)
    bad_contents["manifest.json"] = bad_manifest
    bad_contents["manifest.sha256"] = hashlib.sha256(bad_manifest).hexdigest().encode()
    _write_zip(root / "bad-manifest.zip", bad_contents)
    with pytest.raises(PacketError, match="invalid manifest entries"):
        verify_packet(root / "bad-manifest.zip")
    export_packet(root, SUBJECT, output=root / "clean.zip", selectors=(_selector(2),))
    clean_contents = _read_zip(root / "clean.zip")[1]
    malformed = json.loads(clean_contents["manifest.json"])
    malformed["completeness"] = {"selector": "included"}
    malformed_bytes = json.dumps(malformed, sort_keys=True, separators=(",", ":")).encode()
    malformed_contents = dict(clean_contents)
    malformed_contents["manifest.json"] = malformed_bytes
    malformed_contents["manifest.sha256"] = hashlib.sha256(malformed_bytes).hexdigest().encode()
    _write_zip(root / "bad-completeness.zip", malformed_contents)
    with pytest.raises(PacketError, match="invalid manifest completeness"):
        verify_packet(root / "bad-completeness.zip")
    _write_zip(root / "bomb.zip", contents)
    with pytest.raises(PacketError, match="expanded"):
        verify_packet(root / "bomb.zip", limits=ArchiveLimits(max_expanded_bytes=8))


def test_archive_limits_and_atomic_output_writes_are_bounded(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="finite"):
        ArchiveLimits(max_artifact_bytes=math.nan)
    root = tmp_path / "evidence"
    _write(root)
    collision = root / "collision.zip"
    collision.write_bytes(b"unchanged\n")
    with pytest.raises(PacketError, match="collision"):
        export_packet(root, SUBJECT, output=collision, selectors=(_selector(2),))
    assert collision.read_bytes() == b"unchanged\n" and not list(root.glob("*.tmp"))

    output = root / "crash.zip"
    original_replace = os.replace

    def failing_replace(source: Path, destination: Path) -> None:
        if Path(destination) == output:
            raise OSError("simulated crash before publication")
        return original_replace(source, destination)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "replace", failing_replace)
        with pytest.raises(OSError, match="simulated crash"):
            export_packet(root, SUBJECT, output=output, selectors=(_selector(2),))
    assert not output.exists() and not list(root.glob("*.tmp"))


def test_verification_refuses_zlib_failures_as_packet_errors(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root)
    archive = root / "good.zip"
    export_packet(root, SUBJECT, output=archive, selectors=(_selector(2),))
    with zipfile.ZipFile(archive, "r") as source:
        original_read = type(source).read

        def invalid_deflate(self: zipfile.ZipFile, name: str, pwd: object = None) -> bytes:
            if name == "report.md":
                raise zlib.error("invalid distance code")
            return original_read(self, name, pwd=pwd)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(type(source), "read", invalid_deflate)
            with pytest.raises(PacketError, match="corrupted archive"):
                verify_packet(archive)
