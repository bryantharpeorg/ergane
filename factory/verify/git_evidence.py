"""Exact, bounded Git evidence captured while the worktree is still present."""

from __future__ import annotations

import subprocess
from pathlib import Path

from factory.attestation.models import GitFileChange
from factory.verify.models import GateResult

LOG_TAIL_LIMIT = 8192


def capture_attempt_evidence(
    worktree_path: str | Path,
    *,
    base_ref: str,
    attempted_ref: str,
    verified_ref: str,
    gate_results: list[GateResult],
    evidence_id: str = "",
    epic_id: str = "",
    node_id: str = "",
    attempt: int = 1,
    dispatch: str = "",
) -> dict[str, object]:
    """Read exact refs and the attempted diff into report-safe data."""
    cwd = Path(worktree_path)
    base_commit = _rev_parse(cwd, base_ref)
    attempted_commit = _rev_parse(cwd, attempted_ref)
    verified_commit = _rev_parse(cwd, verified_ref)
    files = _file_manifest(cwd, base_commit, attempted_commit)
    gate_tail = "\n".join(f"{gate.name}: {gate.output_tail}" for gate in gate_results)
    log_truncated = any(gate.output_truncated for gate in gate_results)
    encoded = gate_tail.encode("utf-8")
    if len(encoded) > LOG_TAIL_LIMIT:
        gate_tail = (
            f"[... {len(encoded) - LOG_TAIL_LIMIT} earlier characters truncated ...]\n"
            + encoded[-LOG_TAIL_LIMIT:].decode("utf-8", errors="replace")
        )
        log_truncated = True
    return {
        "evidence_id": evidence_id,
        "epic_id": epic_id,
        "node_id": node_id,
        "attempt": attempt,
        "dispatch": dispatch,
        "base_commit": base_commit,
        "attempted_commit": attempted_commit,
        "verified_commit": verified_commit,
        "files": files,
        "log_tail": gate_tail,
        "log_truncated": log_truncated,
        "tests_executed": tuple(
            gate.command for gate in gate_results if gate.name == "test"
        ),
        "coverage_status": "absent",
    }


def _rev_parse(cwd: Path, ref: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _git_bytes(cwd: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _file_manifest(
    cwd: Path, base_commit: str, attempted_commit: str
) -> tuple[GitFileChange, ...]:
    """Parse NUL-separated Git output; never split path bytes by text."""
    statuses = _git_bytes(
        cwd,
        "diff-tree",
        "--no-commit-id",
        "-r",
        "-M",
        "-z",
        "--name-status",
        base_commit,
        attempted_commit,
    ).decode("utf-8", errors="surrogateescape")
    binaries = _binary_paths(
        cwd,
        base_commit,
        attempted_commit,
    )

    files: list[GitFileChange] = []
    tokens = statuses.split("\0")
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if not status:
            continue
        if status.startswith(("R", "C")):
            old_path = tokens[index]
            path = tokens[index + 1]
            index += 2
            files.append(
                GitFileChange(
                    path=path, status=status, old_path=old_path, binary=path in binaries
                )
            )
        else:
            path = tokens[index]
            index += 1
            files.append(
                GitFileChange(path=path, status=status, binary=path in binaries)
            )
    return tuple(sorted(files, key=lambda item: (item.path, item.old_path or "")))


def _binary_paths(cwd: Path, base_commit: str, attempted_commit: str) -> set[str]:
    output = _git_bytes(
        cwd,
        "diff-tree",
        "--no-commit-id",
        "-r",
        "-M",
        "-z",
        "--numstat",
        base_commit,
        attempted_commit,
    ).decode("utf-8", errors="surrogateescape")
    binary: set[str] = set()
    for entry in output.split("\0"):
        if not entry:
            continue
        fields = entry.split("\t", 2)
        if len(fields) == 3 and fields[0] == "-" and fields[1] == "-":
            binary.add(fields[2])
    return binary
