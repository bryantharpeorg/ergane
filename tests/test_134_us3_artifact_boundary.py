"""US3: the gate boundary carries declared artifacts without changing verdicts."""

from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from factory.verify import artifact_capture

from factory.verify.gates import SubprocessGateExecutor, run_gates
from factory.verify.judge import _gate_blocks
from factory.verify.models import GateArtifact, GateResult, GateStatus

from tests.test_134_bounded_artifact_capture import (
    _escaping_symlink,
    _fifo,
    _hardlink_alias,
    _regular_file,
    _socket,
    _substituted_symlink,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _node_worktree(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.email", "factory@example.invalid")
    _git(repo, "config", "user.name", "Ergane Tests")
    (repo / ".gitignore").write_text(
        "\n".join(
            [
                "alias",
                "escaped",
                "ignored-report.txt",
                "pipe",
                "socket",
                "substituted",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
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
    second: str | None = None,
    artifacts: list[dict[str, str]] | None = None,
) -> Path:
    lines = ["version: 2", "runtime: bwrap", "gates:"]
    lines.append(f'  {gate}: "{command}"')
    if second is not None:
        lines.append(f'  second: "{second}"')
    if artifacts:
        lines.append("artifacts:")
        for artifact in artifacts:
            lines.extend(
                [
                    f"  - gate: {artifact['gate']}",
                    f"    path: {artifact['path']}",
                    f"    type: {artifact['type']}",
                ]
            )
    path = worktree / "factory.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(
    worktree: Path,
    manifest: Path,
    destination: Path | None,
) -> list[GateResult]:
    return run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
        artifact_destination=destination,
    )


def _old_fields(result: GateResult) -> dict[str, object]:
    return {
        field.name: getattr(result, field.name)
        for field in dataclasses.fields(GateResult)
        if field.name != "artifacts"
    }


def test_a_declared_written_artifact_is_stored_and_recorded(
    tmp_path: Path,
) -> None:
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command="printf 'coverage bytes\\n' > ignored-report.txt",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )

    [result] = _run(worktree, manifest, destination)
    [artifact] = result.artifacts

    assert isinstance(artifact, GateArtifact)
    assert artifact.gate == "test"
    assert artifact.path == "ignored-report.txt"
    assert artifact.type == "coverage"
    assert artifact.present is True
    assert artifact.size == len(b"coverage bytes\n")
    assert artifact.provenance == "new"
    stored = Path(artifact.stored_path)
    assert stored.is_absolute()
    assert stored.read_bytes() == b"coverage bytes\n"
    assert result.status is GateStatus.PASS


def test_an_absent_declared_artifact_is_still_recorded(tmp_path: Path) -> None:
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command="true",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert artifact.path == "ignored-report.txt"
    assert artifact.type == "coverage"
    assert artifact.present is False
    assert artifact.size is None
    assert artifact.stored_path is None
    assert result.status is GateStatus.PASS


def test_opaque_is_recorded_like_a_recognised_type(tmp_path: Path) -> None:
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command="printf 'opaque bytes\\n' > ignored-report.txt",
        artifacts=[
            {"gate": "test", "path": "ignored-report.txt", "type": "opaque"}
        ],
    )

    [result] = _run(worktree, manifest, destination)
    [opaque] = result.artifacts

    assert opaque.type == "opaque"
    assert opaque.present is True
    assert opaque.size == len(b"opaque bytes\n")
    assert opaque.provenance == "new"
    assert opaque.status == "permitted"
    stored = Path(opaque.stored_path)
    assert stored.is_absolute()
    assert stored.read_bytes() == b"opaque bytes\n"


def test_an_oversized_artifact_is_recorded_but_not_truncated(
    tmp_path: Path,
) -> None:
    from factory.verify.gates import MAX_ARTIFACT_STORED_BYTES

    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    oversized_size = MAX_ARTIFACT_STORED_BYTES + 17
    manifest = _manifest(
        worktree,
        gate="test",
        command=f"head -c {oversized_size} /dev/zero > ignored-report.txt",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "sbom",
            }
        ],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert artifact.present is True
    assert artifact.size == oversized_size
    assert artifact.stored_path is None
    assert artifact.status == "oversized"
    assert not destination.exists() or not any(destination.rglob("*"))


def test_serialized_results_do_not_carry_artifact_bytes(tmp_path: Path) -> None:
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command="head -c 131072 /dev/zero > ignored-report.txt",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "sbom",
            }
        ],
    )

    [result] = _run(worktree, manifest, destination)
    serialised = json.dumps(dataclasses.asdict(result))

    assert len(serialised) < 4096


def test_malformed_coverage_is_carried_like_wellformed_coverage(
    tmp_path: Path,
) -> None:
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    malformed = _manifest(
        worktree,
        gate="test",
        command="printf '<coverage>' > ignored-report.txt",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )

    [result] = _run(worktree, malformed, destination)
    [artifact] = result.artifacts

    assert artifact.status == "permitted"
    assert artifact.present is True
    assert artifact.size == len(b"<coverage>")
    assert artifact.provenance == "new"
    assert Path(artifact.stored_path).read_bytes() == b"<coverage>"
    assert result.status is GateStatus.PASS


def test_no_artifact_declarations_leave_results_and_destination_unchanged(
    tmp_path: Path,
) -> None:
    clean_worktree = _node_worktree(tmp_path / "first")
    destination_worktree = _node_worktree(tmp_path / "second")
    destination = tmp_path / "second-store"
    destination.mkdir()
    before_entries = set(destination.iterdir())
    clean_manifest = _manifest(clean_worktree, gate="test", command="true")
    destination_manifest = _manifest(
        destination_worktree, gate="test", command="true"
    )

    [clean] = _run(clean_worktree, clean_manifest, None)
    [carried] = _run(destination_worktree, destination_manifest, destination)

    assert carried.artifacts == ()
    assert dataclasses.replace(
        carried, artifacts=(), duration_s=clean.duration_s
    ) == dataclasses.replace(clean, artifacts=())
    assert set(destination.iterdir()) == before_entries


def test_collection_does_not_charge_the_next_gate(tmp_path: Path) -> None:
    declared_worktree = _node_worktree(tmp_path / "declared")
    undeclared_worktree = _node_worktree(tmp_path / "undeclared")
    destination = tmp_path / "artifact-store"
    declared_manifest = _manifest(
        declared_worktree,
        gate="first",
        command="printf 'coverage bytes\\n' > ignored-report.txt",
        second="true",
        artifacts=[
            {
                "gate": "first",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )
    undeclared_manifest = _manifest(
        undeclared_worktree,
        gate="first",
        command="printf 'coverage bytes\\n' > ignored-report.txt",
        second="true",
    )

    declared_results = _run(declared_worktree, declared_manifest, destination)
    undeclared_results = _run(
        undeclared_worktree, undeclared_manifest, destination
    )

    assert declared_results[0].status is GateStatus.PASS
    assert undeclared_results[1].status == GateStatus.PASS
    assert undeclared_results[1].worktree_writes == ()


def test_gate_blocks_are_unchanged_by_artifacts(tmp_path: Path) -> None:
    result = GateResult(
        name="test",
        command="true",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=0.1,
        output_tail="",
        artifacts=(
            GateArtifact(
                gate="test",
                path="ignored-report.txt",
                type="coverage",
                present=True,
                size=13,
                stored_path="/tmp/irrelevant",
                status="permitted",
                provenance="new",
                reason=None,
            ),
        ),
    )

    assert _gate_blocks([result]) == _gate_blocks(
        [dataclasses.replace(result, artifacts=())]
    )


@pytest.mark.parametrize(
    ("make_source", "expected_status"),
    [
        (lambda root: _escaping_symlink(root, root.parent / "outside"), "unsafe"),
        (_substituted_symlink, "unsafe"),
        (_hardlink_alias, "unsafe"),
        (_fifo, "unsafe"),
        (_socket, "unsafe"),
    ],
)
def test_the_real_collector_refuses_unsafe_sources_without_changing_verdict(
    tmp_path: Path,
    make_source,
    expected_status: str,
) -> None:
    worktree = _node_worktree(tmp_path)
    relative_path = make_source(worktree)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command="true",
        artifacts=[
            {"gate": "test", "path": relative_path, "type": "opaque"}
        ],
    )

    [result] = _run(worktree, manifest, destination)

    assert result.status is GateStatus.PASS
    assert result.artifacts[0].status == expected_status
    assert result.artifacts[0].present is False
    assert result.artifacts[0].stored_path is None
    assert result.artifacts[0].reason


def test_the_real_collector_refuses_an_oversized_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from factory.verify import gates

    worktree = _node_worktree(tmp_path)
    path = worktree / "ignored-report.txt"
    path.write_bytes(b"y" * 17)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command="true",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "opaque",
            }
        ],
    )
    monkeypatch.setattr(gates, "MAX_ARTIFACT_STORED_BYTES", 16)

    [result] = _run(worktree, manifest, destination)

    assert result.status is GateStatus.PASS
    assert result.artifacts[0].status == "oversized"
    assert result.artifacts[0].present is True
    assert result.artifacts[0].size == 17
    assert result.artifacts[0].stored_path is None


def test_freshness_is_observed_before_and_after_the_gate(tmp_path: Path) -> None:
    worktree = _node_worktree(tmp_path)
    preexisting = worktree / "ignored-report.txt"
    preexisting.write_bytes(b"stable bytes\n")
    destination = tmp_path / "artifact-store"
    unchanged_manifest = _manifest(
        worktree,
        gate="test",
        command="true",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )

    [unchanged] = _run(worktree, unchanged_manifest, destination)
    assert unchanged.artifacts[0].provenance == "unchanged"
    assert unchanged.artifacts[0].status == "permitted"

    fresh_worktree = _node_worktree(tmp_path / "fresh")
    fresh_manifest = _manifest(
        fresh_worktree,
        gate="test",
        command="printf 'fresh report\\n' > ignored-report.txt",
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )
    [fresh] = _run(fresh_worktree, fresh_manifest, destination)
    assert fresh.artifacts[0].provenance == "new"


def test_an_unstable_capture_is_refused_without_changing_the_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "artifact-store"
    manifest = _manifest(
        worktree,
        gate="test",
        command=(
            "printf 'first bytes\\n' > ignored-report.txt"
        ),
        artifacts=[
            {
                "gate": "test",
                "path": "ignored-report.txt",
                "type": "coverage",
            }
        ],
    )
    path = worktree / "ignored-report.txt"
    real_read = artifact_capture.os.read
    mutated = False

    def mutate_after_first_read(descriptor: int, amount: int) -> bytes:
        nonlocal mutated
        chunk = real_read(descriptor, amount)
        if not mutated and chunk == b"first bytes\n":
            path.write_bytes(b"later bytes\n")
            mutated = True
        return chunk

    monkeypatch.setattr(
        artifact_capture.os, "read", mutate_after_first_read
    )

    [result] = _run(worktree, manifest, destination)

    assert result.status is GateStatus.PASS
    assert result.artifacts[0].status == "unstable"
    assert result.artifacts[0].provenance == "unknown"
    assert result.artifacts[0].stored_path is None


def test_the_artifact_field_is_declared_once() -> None:
    source = Path("factory/verify/models.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    [gate_result] = (
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GateResult"
    )
    assignments = [
        node
        for node in gate_result.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "artifacts"
    ]

    assert len(assignments) == 1
    fields = {field.name for field in dataclasses.fields(GateResult)}
    assert "artifacts" in fields
    assert GateResult.__dataclass_fields__["artifacts"].default == ()

    duplicate_source = "class GateResult:\n    artifacts: tuple[int, ...] = ()\n    artifacts: tuple[int, ...] = ()\n"
    duplicate_tree = ast.parse(duplicate_source)
    [duplicate_class] = (
        node for node in duplicate_tree.body if isinstance(node, ast.ClassDef)
    )
    duplicate_count = sum(
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "artifacts"
        for node in duplicate_class.body
    )
    assert duplicate_count == 2
