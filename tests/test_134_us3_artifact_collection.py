"""US3: the gate boundary carries what each gate declared it wrote."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from factory.verify import artifact_capture as artifact_capture_module
from factory.verify.artifact_capture import os as artifact_capture_os
from factory.verify import gates as gates_module
from factory.verify.gates import (
    ExecutionOutcome,
    GateInvocation,
    SubprocessGateExecutor,
    run_gates,
)
from factory.verify.judge import _gate_blocks
from factory.verify.models import ArtifactType, GateArtifact, GateResult, GateStatus

from tests.test_134_bounded_artifact_capture import _regular_file
from tests.test_134_us2_artifact_exemption import _manifest, _node_worktree


def _run(
    worktree: Path,
    manifest: Path,
    destination: Path | None = None,
    *,
    candidate: bool = False,
) -> list[GateResult]:
    if candidate:
        (worktree / "factory" / "verify").mkdir(parents=True)
        (worktree / "factory" / "verify" / "factory_yaml.py").write_text(
            "# the worktree's own parser marker\n", encoding="utf-8"
        )
    return run_gates(
        worktree,
        manifest_path=manifest,
        executor=SubprocessGateExecutor(),
        artifact_destination=destination,
    )


@pytest.mark.parametrize("candidate", [True, False])
def test_a_declared_written_artifact_is_copied_and_recorded(
    tmp_path: Path,
    candidate: bool,
) -> None:
    """US3-S1: collection reads the declared disk path, even when ignored."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    manifest = _manifest(
        worktree,
        gate="test",
        command="printf artifact\\ bytes > ignored-report.txt",
        artifacts=[
            {"gate": "test", "path": "ignored-report.txt", "type": "coverage"}
        ],
    )

    [result] = _run(worktree, manifest, destination, candidate=candidate)

    [artifact] = result.artifacts
    assert artifact.gate == "test"
    assert artifact.path == "ignored-report.txt"
    assert artifact.type is ArtifactType.COVERAGE
    assert artifact.present is True
    assert artifact.size == 14
    assert artifact.stored_path is not None
    stored = Path(artifact.stored_path)
    assert stored.is_absolute()
    assert stored.read_bytes() == b"artifact bytes"
    assert artifact.capture_status == "permitted"
    assert artifact.provenance == "new"
    assert result.worktree_writes == ()


def test_a_declared_absent_artifact_is_recorded(tmp_path: Path) -> None:
    """US3-S2: a declaration that produced nothing is still evidence."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo clean",
        artifacts=[{"gate": "test", "path": "absent.xml", "type": "coverage"}],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert artifact.present is False
    assert artifact.size is None
    assert artifact.stored_path is None
    assert artifact.capture_status == "absent"
    assert destination.exists() is False


def test_opaque_artifacts_are_carried_like_coverage(tmp_path: Path) -> None:
    """US3-S3: `opaque` is a recognised type, not a drop or a refusal."""
    opaque_worktree = _node_worktree(tmp_path / "opaque")
    coverage_worktree = _node_worktree(tmp_path / "coverage")
    destination = tmp_path / "captures"
    opaque = _manifest(
        opaque_worktree,
        gate="test",
        command="echo -n opaque bytes > opaque.report",
        artifacts=[{"gate": "test", "path": "opaque.report", "type": "opaque"}],
    )
    coverage = _manifest(
        coverage_worktree,
        gate="test",
        command="echo -n opaque bytes > coverage.xml",
        artifacts=[{"gate": "test", "path": "coverage.xml", "type": "coverage"}],
    )

    [opaque_result] = _run(opaque_worktree, opaque, destination / "opaque")
    [coverage_result] = _run(coverage_worktree, coverage, destination / "coverage")

    assert dataclasses.fields(opaque_result.artifacts[0]) == dataclasses.fields(
        coverage_result.artifacts[0]
    )
    assert opaque_result.artifacts[0].type is ArtifactType.OPAQUE
    assert opaque_result.artifacts[0].present is True
    assert Path(opaque_result.artifacts[0].stored_path) == (
        destination / "opaque" / "test" / "opaque.report"
    )
    assert Path(coverage_result.artifacts[0].stored_path) == (
        destination / "coverage" / "test" / "coverage.xml"
    )


def test_an_oversized_artifact_is_present_but_not_stored(tmp_path: Path) -> None:
    """US3-S4: oversized evidence is never truncated into a corrupt artifact."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    manifest = _manifest(
        worktree,
        gate="test",
        command="head -c 1048577 /dev/zero > oversized.sbom",
        artifacts=[{"gate": "test", "path": "oversized.sbom", "type": "sbom"}],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert artifact.present is True
    assert artifact.size == 1048577
    assert artifact.capture_status == "oversized"
    assert artifact.stored_path is None
    assert destination.exists() is False


def test_serialised_results_do_not_carry_artifact_bytes(tmp_path: Path) -> None:
    """US3-S5: the activity payload holds references, not report contents."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    sizes = [512, 4096, 512 * 1024]
    serialized_sizes = []
    for index, size in enumerate(sizes):
        manifest = _manifest(
            worktree,
            gate="test",
            command=(
                "python3 -c \"import sys; sys.stdout.buffer.write("
                f"bytes({size}))\" > growing.coverage"
            ),
            artifacts=[
                {"gate": "test", "path": "growing.coverage", "type": "coverage"}
            ],
        )
        [result] = _run(worktree, manifest, destination / str(index))
        serialized_sizes.append(len(json.dumps(dataclasses.asdict(result))))

    assert all(size < 2048 for size in serialized_sizes)


def test_malformed_coverage_is_collected_like_well_formed_coverage(
    tmp_path: Path,
) -> None:
    """US3-S6: the platform carries bytes; it does not grade their XML."""
    malformed_worktree = _node_worktree(tmp_path / "malformed")
    well_formed_worktree = _node_worktree(tmp_path / "well-formed")
    destination = tmp_path / "captures"
    malformed = _manifest(
        malformed_worktree,
        gate="test",
        command="printf PGNvdmVyYWdl | base64 -d > coverage.xml",
        artifacts=[{"gate": "test", "path": "coverage.xml", "type": "coverage"}],
    )
    well_formed = _manifest(
        well_formed_worktree,
        gate="test",
        command="printf PGNvdmVyYWdlLz4= | base64 -d > coverage.xml",
        artifacts=[{"gate": "test", "path": "coverage.xml", "type": "coverage"}],
    )

    [malformed_result] = _run(malformed_worktree, malformed, destination / "malformed")
    [well_formed_result] = _run(
        well_formed_worktree, well_formed, destination / "well-formed"
    )

    malformed_artifact = malformed_result.artifacts[0]
    well_formed_artifact = well_formed_result.artifacts[0]
    assert malformed_artifact.capture_status == "permitted"
    assert malformed_artifact.provenance == "new"
    assert malformed_artifact.size == 9
    assert well_formed_artifact.capture_status == "permitted"
    assert well_formed_artifact.provenance == "new"
    assert well_formed_artifact.size == 11


def test_no_declaration_preserves_the_previous_gate_result(tmp_path: Path) -> None:
    """US3-S7: no declarations means no carriage and no destination writes."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    manifest = _manifest(worktree, gate="test", command="echo unchanged")

    [result] = _run(worktree, manifest, destination)

    assert result.artifacts == ()
    assert result.status is GateStatus.PASS
    assert result.worktree_writes == ()
    assert destination.exists() is False


def test_a_second_gate_is_not_charged_for_collection(tmp_path: Path) -> None:
    """US3-S8: destination writes are outside the watched worktree."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    artifacts = [{"gate": "first", "path": "coverage.xml", "type": "coverage"}]
    collected = _manifest(
        worktree,
        gate="first",
        command="printf bytes > coverage.xml",
        artifacts=artifacts,
    )
    manifest = worktree / "factory.yaml"
    manifest.write_text(
        collected.read_text(encoding="utf-8").replace(
            "artifacts:", "\n  second: 'echo next'\nartifacts:"
        ),
        encoding="utf-8",
    )

    [first, second] = _run(worktree, manifest, destination)

    assert first.artifacts[0].present is True
    assert second.status is GateStatus.PASS
    assert second.worktree_writes == ()
    assert second.artifacts == ()


def test_gate_blocks_are_unchanged_by_artifacts() -> None:
    """US3-S9: `_gate_blocks` remains artifact-blind by declaration."""
    with_artifacts = GateResult(
        name="test",
        command="uv run pytest -q",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=1.0,
        output_tail="passed",
        artifacts=(
            _record(
                path="coverage.xml",
                type=ArtifactType.COVERAGE,
                present=True,
                size=12,
                stored_path="/tmp/ergane-134/coverage.xml",
            ),
        ),
    )
    without_artifacts = dataclasses.replace(with_artifacts, artifacts=())

    assert _gate_blocks([with_artifacts]) == _gate_blocks([without_artifacts])


def test_unchanged_preexisting_bytes_are_not_claimed_new(
    tmp_path: Path,
) -> None:
    """US3-S11: presence alone never proves that the gate produced bytes."""
    worktree = _node_worktree(tmp_path)
    (worktree / "ignored-report.txt").write_bytes(b"stable bytes\n")
    destination = tmp_path / "captures"
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo unchanged",
        artifacts=[
            {"gate": "test", "path": "ignored-report.txt", "type": "coverage"}
        ],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert artifact.present is True
    assert artifact.capture_status == "permitted"
    assert artifact.provenance == "unchanged"


class _MutatingAfterGateExecutor:
    """Runs the real gate, then lets the post-gate read race the fixture."""

    def __init__(self, path: Path) -> None:
        self._backend = SubprocessGateExecutor()
        self._path = path
        self.post_gate_started = False

    def run(self, invocation: GateInvocation) -> ExecutionOutcome:
        outcome = self._backend.run(invocation)
        self.post_gate_started = True
        return outcome


def test_changed_bytes_are_not_published_as_a_snapshot(tmp_path: Path) -> None:
    """US3-S11: an inconsistent post-gate observation is refused, not copied."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    path = worktree / "ignored-report.txt"
    path.write_bytes(b"stable bytes")
    manifest = _manifest(
        worktree,
        gate="test",
        command="echo unchanged",
        artifacts=[
            {"gate": "test", "path": "ignored-report.txt", "type": "coverage"}
        ],
    )
    executor = _MutatingAfterGateExecutor(path)
    real_capture_source = artifact_capture_module.capture_source
    post_capture_started = False

    def capture_then_mutate(*args, **kwargs):
        nonlocal post_capture_started
        post_capture_started = True
        return real_capture_source(*args, **kwargs)

    real_read = os.read
    mutated = False

    def read_during_capture(fd: int, amount: int) -> bytes:
        nonlocal mutated
        chunk = real_read(fd, amount)
        if (
            executor.post_gate_started
            and post_capture_started
            and not mutated
            and chunk
        ):
            with path.open("r+b") as changing:
                changing.write(b"XXXXXXXXXXXX")
            mutated = True
        return chunk

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(gates_module, "capture_source", capture_then_mutate)
        patch.setattr(artifact_capture_os, "read", read_during_capture)
        [result] = run_gates(
            worktree,
            manifest_path=manifest,
            executor=executor,
            artifact_destination=destination,
        )

    [artifact] = result.artifacts
    assert result.status is GateStatus.PASS
    assert artifact.capture_status == "unstable"
    assert artifact.provenance == "changed"
    assert artifact.stored_path is None
    assert destination.exists() is False


@pytest.mark.parametrize(
    ("relative_path", "command"),
    [
        ("escaped", "ln -s outside-source escaped"),
        ("substituted", "ln -s ordinary.txt substituted"),
        ("alias", "ln alias-original alias"),
        ("pipe", "mkfifo pipe"),
    ],
)
def test_unsafe_sources_are_refused_without_changing_the_verdict(
    tmp_path: Path,
    relative_path: str,
    command: str,
) -> None:
    """US3-S10: manifest acceptance is not runtime containment."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    if relative_path == "escaped":
        outside = tmp_path / "outside-root" / "outside-source"
        outside.parent.mkdir()
        outside.write_bytes(b"UNRELATED OUTSIDE BYTES\n")
        command = f"ln -s {outside} escaped"
    elif relative_path == "substituted":
        _regular_file(worktree, "ordinary.txt")
    elif relative_path == "alias":
        _regular_file(worktree, "alias-original")

    manifest = _manifest(
        worktree,
        gate="test",
        command=command,
        artifacts=[{"gate": "test", "path": relative_path, "type": "opaque"}],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert result.status is GateStatus.PASS
    assert artifact.capture_status == "unsafe"
    assert artifact.present is True
    assert artifact.reason is not None
    assert artifact.stored_path is None
    assert destination.exists() is False


def test_a_bounded_read_refusal_records_oversize_without_truncation(
    tmp_path: Path,
) -> None:
    """US3-S10: the actual collector respects the read bound on every source."""
    worktree = _node_worktree(tmp_path)
    destination = tmp_path / "captures"
    manifest = _manifest(
        worktree,
        gate="test",
    command="head -c 1048577 /dev/zero > oversized.sbom",
        artifacts=[{"gate": "test", "path": "oversized.sbom", "type": "sbom"}],
    )

    [result] = _run(worktree, manifest, destination)

    [artifact] = result.artifacts
    assert result.status is GateStatus.PASS
    assert artifact.capture_status == "oversized"
    assert artifact.size == 1048577
    assert artifact.stored_path is None


def _record(
    *,
    path: str,
    type: ArtifactType,
    present: bool,
    size: int,
    stored_path: str,
) -> GateArtifact:
    return GateArtifact(
        gate="test",
        path=path,
        type=type,
        present=present,
        size=size,
        stored_path=stored_path,
        capture_status="permitted",
        provenance="new",
    )
