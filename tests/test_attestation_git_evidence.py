"""US2-S5: exact Git and gate evidence is captured before cleanup."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.verify_activities import CaptureAttemptEvidenceInput, capture_attempt_evidence
from factory.attestation import read_attempt_evidence
from factory.verify.gates import tail_output
from factory.verify.models import GateResult, GateStatus


def run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    run_git(repo, "config", "user.name", "Test")
    run_git(repo, "config", "user.email", "test@example.invalid")
    write(repo / "removed.txt", b"delete me\n")
    write(repo / "modified.txt", b"old\n")
    write(repo / "renamed.txt", b"rename me\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()

    (repo / "removed.txt").unlink()
    write(repo / "modified.txt", b"new\n")
    write(repo / "new.txt", b"added\n")
    write(repo / "binary.bin", bytes(range(256)))
    (repo / "new line \n and é.txt").write_bytes(b"unicode\n")
    run_git(repo, "add", "-A")
    run_git(repo, "mv", "renamed.txt", "renamed-later.txt")
    run_git(repo, "commit", "-m", "attempt")
    attempted = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()
    return repo, base, attempted, attempted


def gate_results() -> tuple[GateResult, GateResult]:
    large = "x" * 40_000
    return (
        GateResult(
            name="test",
            command="pytest",
            status=GateStatus.PASS,
            exit_code=0,
            duration_s=1.0,
            output_tail=tail_output(large),
            output_truncated=True,
        ),
        GateResult(
            name="lint",
            command="lint",
            status=GateStatus.PASS,
            exit_code=0,
            duration_s=0.5,
            output_tail="ok",
            output_truncated=False,
        ),
    )


async def test_capture_exact_refs_and_safe_file_manifest(
    git_repo: tuple[Path, str, str, str],
) -> None:
    repo, base, attempted, verified = git_repo
    evidence = await ActivityEnvironment().run(
        capture_attempt_evidence,
        CaptureAttemptEvidenceInput(
            evidence_id="evidence-1",
            epic_id="epic",
            node_id="node",
            attempt=1,
            dispatch="dispatch",
            worktree_path=str(repo),
            base_ref=base,
            attempted_ref=attempted,
            verified_ref=verified,
            gate_results=list(gate_results()),
            journal_path=str(repo.parent / "attestation.db"),
        ),
    )

    assert (evidence.base_commit, evidence.attempted_commit, evidence.verified_commit) == (
        base,
        attempted,
        verified,
    )
    statuses = {(item.path, item.status, item.binary) for item in evidence.files}
    assert ("new.txt", "A", False) in statuses
    assert ("modified.txt", "M", False) in statuses
    assert ("removed.txt", "D", False) in statuses
    assert ("renamed-later.txt", "R100", False) in statuses
    assert ("binary.bin", "A", True) in statuses
    assert ("new line \n and é.txt", "A", False) in statuses
    assert all("\0" not in item.path for item in evidence.files)
    assert evidence.tests_executed == ("pytest",)
    assert evidence.coverage_status == "absent"
    assert evidence.log_truncated is True


async def test_attempt_evidence_is_persisted_for_the_report(
    git_repo: tuple[Path, str, str, str],
) -> None:
    repo, base, attempted, verified = git_repo
    journal = repo.parent / "attestation.db"
    await ActivityEnvironment().run(
        capture_attempt_evidence,
        CaptureAttemptEvidenceInput(
            evidence_id="evidence-2",
            epic_id="epic",
            node_id="node",
            attempt=1,
            dispatch="dispatch",
            worktree_path=str(repo),
            base_ref=base,
            attempted_ref=attempted,
            verified_ref=verified,
            gate_results=list(gate_results()),
            journal_path=str(journal),
        ),
    )
    records = read_attempt_evidence(journal)
    assert len(records) == 1
    assert records[0].evidence_id == "evidence-2"
    assert records[0].base_commit == base
