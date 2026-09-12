"""US2-S5: exact Git and gate evidence is captured before cleanup."""

import subprocess
from pathlib import Path

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.verify_activities import CaptureAttemptEvidenceInput, capture_attempt_evidence
from factory.attestation import read_attempt_evidence
from factory.verify.gates import tail_output
from factory.verify.models import GateResult, GateStatus


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


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
    base = run_git(repo, "rev-parse", "HEAD")
    (repo / "removed.txt").unlink()
    write(repo / "modified.txt", b"new\n")
    write(repo / "new.txt", b"added\n")
    write(repo / "binary.bin", bytes(range(256)))
    (repo / "new line \n and é.txt").write_bytes(b"unicode\n")
    run_git(repo, "add", "-A")
    run_git(repo, "mv", "renamed.txt", "renamed-later.txt")
    run_git(repo, "commit", "-m", "attempt")
    attempted = run_git(repo, "rev-parse", "HEAD")
    return repo, base, attempted, attempted


def gate_results() -> tuple[GateResult, GateResult]:
    return (
        GateResult("test", "pytest", GateStatus.PASS, 0, 1.0, tail_output("x" * 40_000), output_truncated=True),
        GateResult("lint", "lint", GateStatus.PASS, 0, 0.5, "ok"),
    )


def request(repo: Path, base: str, attempted: str, verified: str, evidence_id: str, journal: Path):
    return CaptureAttemptEvidenceInput(
        evidence_id=evidence_id, epic_id="epic", node_id="node", attempt=1,
        dispatch="dispatch", worktree_path=str(repo), base_ref=base,
        attempted_ref=attempted, verified_ref=verified, gate_results=list(gate_results()),
        journal_path=str(journal),
    )


async def test_capture_exact_refs_and_safe_file_manifest(git_repo: tuple[Path, str, str, str]) -> None:
    repo, base, attempted, verified = git_repo
    evidence = await ActivityEnvironment().run(
        capture_attempt_evidence,
        request(repo, base, attempted, verified, "evidence-1", repo.parent / "attestation.db"),
    )
    assert (evidence.base_commit, evidence.attempted_commit, evidence.verified_commit) == (base, attempted, verified)
    statuses = {(item.path, item.status, item.binary) for item in evidence.files}
    assert {("new.txt", "A", False), ("modified.txt", "M", False),
            ("removed.txt", "D", False), ("renamed-later.txt", "R100", False),
            ("binary.bin", "A", True), ("new line \n and é.txt", "A", False)} <= statuses
    assert all("\0" not in item.path for item in evidence.files)
    assert evidence.tests_executed == ("pytest",)
    assert evidence.coverage_status == "absent"
    assert evidence.log_truncated is True


async def test_attempt_evidence_is_persisted_for_the_report(git_repo: tuple[Path, str, str, str]) -> None:
    repo, base, attempted, verified = git_repo
    journal = repo.parent / "attestation.db"
    await ActivityEnvironment().run(
        capture_attempt_evidence,
        request(repo, base, attempted, verified, "evidence-2", journal),
    )
    records = read_attempt_evidence(journal)
    assert len(records) == 1
    evidence = records[0]
    assert (evidence.evidence_id, evidence.base_commit, evidence.attempted_commit,
            evidence.verified_commit, evidence.log_truncated, evidence.coverage_status) == (
        "evidence-2", base, attempted, verified, True, "absent",
    )
