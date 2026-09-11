"""US2 exempts only the artifact paths a gate declares it writes."""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from typing import Mapping

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    PARSE_CLI_OK,
    load_factory_config,
)
from factory.verify.gates import (
    CandidateOutcome,
    SubprocessGateExecutor,
    run_gates,
)
from factory.verify.gates import GateResult
from factory.verify.models import GateStatus


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _node_worktree(tmp_path: Path) -> Path:
    """A linked worktree, as the production gate runner observes it."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.email", "factory@example.invalid")
    _git(repo, "config", "user.name", "Ergane Tests")
    (repo / ".gitignore").write_text("ignored-report.txt\n", encoding="utf-8")
    (repo / "source.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "base")

    worktree = tmp_path / "worktree"
    _git(repo, "worktree", "add", "--quiet", "-b", "node/work", str(worktree))
    return worktree


def _manifest(
    worktree: Path,
    *,
    gate: str,
    command: str,
    artifacts: list[Mapping[str, str]] | None = None,
) -> Path:
    lines = ["version: 2", "runtime: bwrap", "gates:"]
    lines.append(f"  {gate}: '{command}'")
    if artifacts:
        lines.append("artifacts:")
        for artifact in artifacts:
            lines.append(f"  - gate: {artifact['gate']}")
            lines.append(f"    path: {artifact['path']}")
            lines.append(f"    type: {artifact['type']}")
    path = worktree / MANIFEST_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_artifacts(
    manifest: Path,
) -> tuple[dict[str, object], ...]:
    document = load_factory_config(manifest)
    return tuple(dataclasses.asdict(artifact) for artifact in document.artifacts)


def _run(
    worktree: Path,
    manifest: Path,
    *,
    candidate: bool,
) -> list[GateResult]:
    if candidate:
        (worktree / "factory" / "verify").mkdir(parents=True)
        (worktree / "factory" / "verify" / "factory_yaml.py").write_text(
            "# the worktree's own parser marker\n", encoding="utf-8"
        )
        candidate_runner = lambda worktree_path, manifest_path: CandidateOutcome(
            exit_code=PARSE_CLI_OK,
            stdout=json.dumps(
                {
                    "kind": "accepted",
                    "gates": {"test": "echo declared > report.txt"},
                    "timeouts": {},
                    "writes": {},
                    "artifacts": _candidate_artifacts(manifest),
                }
            ),
            stderr="",
        )
        return run_gates(
            worktree,
            manifest_path=manifest,
            executor=SubprocessGateExecutor(),
            candidate_runner=candidate_runner,
        )
    return run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
    )


@pytest.mark.parametrize("candidate", [True, False])
def test_a_declared_written_artifact_passes_and_is_still_recorded(
    tmp_path: Path, candidate: bool
) -> None:
    """US2-S1/S4: the declaration moves the verdict, never the recording."""
    worktree = _node_worktree(tmp_path)
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo declared > report.txt",
        artifacts=[
            {"gate": "test", "path": "report.txt", "type": "coverage"}
        ],
    )
    check_ignore = subprocess.run(
        ["git", "-C", str(worktree), "check-ignore", "report.txt"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert check_ignore.returncode != 0

    [result] = _run(worktree, manifest, candidate=candidate)

    assert result.status is GateStatus.PASS
    assert result.worktree_writes == ("report.txt",)
    assert result.writes_declared is False


def test_an_undeclared_write_is_still_demoted(tmp_path: Path) -> None:
    """US2-S2: the existing worktree watch is unchanged without a declaration."""
    worktree = _node_worktree(tmp_path)
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo undeclared > undeclared.txt",
    )

    [result] = run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
    )

    assert result.status is GateStatus.DIRTIED_WORKTREE
    assert result.worktree_writes == ("undeclared.txt",)


def test_a_declared_but_absent_artifact_keeps_the_verdict(tmp_path: Path) -> None:
    """US2-S3: a missing artifact is a collection fact, not a gate verdict."""
    worktree = _node_worktree(tmp_path)
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo clean",
        artifacts=[
            {"gate": "test", "path": "report.txt", "type": "coverage"}
        ],
    )

    [result] = run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
    )

    assert result.status is GateStatus.PASS
    assert result.worktree_writes == ()


def test_an_unreadable_snapshot_demotes_declared_artifacts(
    tmp_path: Path,
) -> None:
    """US2-S5: fail closed even when the gate writes only declared paths."""
    worktree = tmp_path / "broken-repo"
    worktree.mkdir()
    (worktree / ".git").write_text(
        "gitdir: /nonexistent-ergane-134\n", encoding="utf-8"
    )
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo declared > report.txt",
        artifacts=[
            {"gate": "test", "path": "report.txt", "type": "coverage"}
        ],
    )

    [result] = run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
    )

    assert result.status is GateStatus.DIRTIED_WORKTREE


def test_an_undeclared_write_beside_a_declared_artifact_demotes(
    tmp_path: Path,
) -> None:
    """US2-S6: the exemption is per path, never a blanket excuse."""
    worktree = _node_worktree(tmp_path)
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo declared > report.txt; echo undeclared > undeclared.txt",
        artifacts=[
            {"gate": "test", "path": "report.txt", "type": "coverage"}
        ],
    )

    [result] = run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
    )

    assert result.status is GateStatus.DIRTIED_WORKTREE
    assert result.worktree_writes == ("report.txt", "undeclared.txt")
