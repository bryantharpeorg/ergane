"""US2-S5: exact Git and gate evidence is captured before cleanup."""

import subprocess
from dataclasses import replace
from pathlib import Path
import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.verify_activities import CaptureAttemptEvidenceInput, capture_attempt_evidence
from factory.attestation import read_attempt_evidence
from factory.verify.gates import tail_output
from factory.verify.models import GateResult, GateStatus


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    for name, content in [("removed.txt", b"delete me\n"), ("modified.txt", b"old\n"), ("renamed.txt", b"rename me\n")]:
        write(repo / name, content)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "removed.txt").unlink()
    write(repo / "modified.txt", b"new\n")
    write(repo / "new.txt", b"added\n")
    write(repo / "binary.bin", bytes(range(256)))
    write(repo / "new line \n and é.txt", b"unicode\n")
    git(repo, "add", "-A")
    git(repo, "mv", "renamed.txt", "renamed-later.txt")
    git(repo, "commit", "-m", "attempt")
    return repo, base, git(repo, "rev-parse", "HEAD")


def gate_results() -> tuple[GateResult, GateResult]:
    return (
        GateResult("test", "pytest", GateStatus.PASS, 0, 1.0, tail_output("x" * 40_000), output_truncated=True),
        GateResult("lint", "lint", GateStatus.PASS, 0, 0.5, "ok"),
    )


def request(repo: Path, base: str, attempted: str, evidence_id: str):
    return CaptureAttemptEvidenceInput(
        evidence_id=evidence_id, epic_id="epic", node_id="node", attempt=1, dispatch="dispatch",
        worktree_path=str(repo), base_ref=base, attempted_ref=attempted, verified_ref=attempted,
        gate_results=list(gate_results()),
    )


async def capture(git_repo, evidence_id: str):
    repo, base, attempted = git_repo
    return await ActivityEnvironment().run(capture_attempt_evidence, request(repo, base, attempted, evidence_id))


async def test_capture_exact_refs_and_safe_file_manifest(git_repo, monkeypatch) -> None:
    journal = git_repo[0].parent / "attestation.db"
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    evidence = await capture(git_repo, "evidence-1")
    assert evidence.base_commit == git_repo[1]
    assert evidence.attempted_commit == evidence.verified_commit == git_repo[2]
    statuses = {(item.path, item.status, item.binary) for item in evidence.files}
    assert {
        ("new.txt", "A", False), ("modified.txt", "M", False), ("removed.txt", "D", False),
        ("renamed-later.txt", "R100", False), ("binary.bin", "A", True), ("new line \n and é.txt", "A", False),
    } <= statuses
    assert all("\0" not in item.path for item in evidence.files)
    assert (evidence.tests_executed, evidence.coverage_status, evidence.log_truncated) == (("pytest",), "absent", True)


async def test_attempt_evidence_is_persisted_for_the_report(git_repo, monkeypatch) -> None:
    journal = git_repo[0].parent / "attestation.db"
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    await capture(git_repo, "evidence-2")
    evidence = read_attempt_evidence(journal)[0]
    assert (evidence.evidence_id, evidence.base_commit) == ("evidence-2", git_repo[1])
    assert evidence.attempted_commit == evidence.verified_commit == git_repo[2]
    assert (evidence.log_truncated, evidence.coverage_status) == (True, "absent")
