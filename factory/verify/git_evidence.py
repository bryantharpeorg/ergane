import subprocess
from pathlib import Path

from factory.attestation.journal import record_attempt_evidence
from factory.attestation.models import AttemptGitEvidence, GitFileChange
from factory.verify.gates import scrubbed_env
from factory.verify.models import GateResult
from factory.verify.worktree_snapshot import snapshot_tree

LOG_TAIL_LIMIT = 8192
DIFF_TREE = ("diff-tree", "--no-commit-id", "-r", "-M", "-z")


def capture_attempt_evidence(
    worktree_path: str | Path, *, base_ref: str, attempted_ref: str, verified_ref: str,
    gate_results: list[GateResult], evidence_id: str = "", epic_id: str = "", node_id: str = "",
    attempt: int = 1, dispatch: str = "", journal_path: str,
) -> AttemptGitEvidence:
    cwd = Path(worktree_path)
    base_commit = _rev_parse(cwd, base_ref)
    attempted_commit = _tree_or_commit(cwd, attempted_ref)
    verified_commit = attempted_commit if verified_ref == "worktree" else _tree_or_commit(cwd, verified_ref)
    gate_tail = "\n".join(f"{gate.name}: {gate.output_tail}" for gate in gate_results)
    log_truncated = any(gate.output_truncated for gate in gate_results)
    encoded = gate_tail.encode("utf-8")
    if len(encoded) > LOG_TAIL_LIMIT:
        gate_tail = (
            f"[... {len(encoded) - LOG_TAIL_LIMIT} earlier characters truncated ...]\n"
            + encoded[-LOG_TAIL_LIMIT:].decode("utf-8", errors="replace")
        )
        log_truncated = True
    evidence = AttemptGitEvidence(
        evidence_id=evidence_id, epic_id=epic_id, node_id=node_id, attempt=attempt,
        dispatch=dispatch, base_commit=base_commit, attempted_commit=attempted_commit,
        verified_commit=verified_commit,
        attempted_files=_file_manifest(cwd, base_commit, attempted_commit),
        verified_files=_file_manifest(cwd, base_commit, verified_commit), log_tail=gate_tail,
        log_truncated=log_truncated,
        tests_executed=tuple(gate.command for gate in gate_results if gate.name == "test"),
        coverage_status="absent",
    )
    return record_attempt_evidence(journal_path, evidence)


def _tree_or_commit(cwd: Path, ref: str) -> str:
    if ref == "worktree":
        snapshot = snapshot_tree(cwd, env=scrubbed_env())
        if snapshot.error or not snapshot.tree_id:
            raise RuntimeError(f"attempt worktree could not be snapshotted: {snapshot.error}")
        return snapshot.tree_id
    return _rev_parse(cwd, ref)


def _rev_parse(cwd: Path, ref: str) -> str:
    return _git(cwd, "rev-parse", "--verify", f"{ref}^{{commit}}").decode("ascii").strip()


def _git(cwd: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def _file_manifest(cwd: Path, base: str, attempted: str) -> tuple[GitFileChange, ...]:
    statuses = _git(cwd, *DIFF_TREE, "--name-status", base, attempted).decode("utf-8", errors="surrogateescape")
    binaries = _binary_paths(cwd, base, attempted)
    files: list[GitFileChange] = []
    entries = iter(statuses.split("\0"))
    for status in entries:
        if not status:
            continue
        if status.startswith(("R", "C")):
            old_path, path = next(entries), next(entries)
            files.append(GitFileChange(path=path, status=status, old_path=old_path, binary=path in binaries))
        else:
            path = next(entries)
            files.append(GitFileChange(path=path, status=status, binary=path in binaries))
    return tuple(sorted(files, key=lambda item: (item.path, item.old_path or "")))


def _binary_paths(cwd: Path, base: str, attempted: str) -> set[str]:
    output = _git(cwd, *DIFF_TREE, "--numstat", base, attempted).decode("utf-8", errors="surrogateescape")
    return {
        fields[2] for entry in output.split("\0") if len(fields := entry.split("\t", 2)) == 3
        and fields[0] == fields[1] == "-"
    }
