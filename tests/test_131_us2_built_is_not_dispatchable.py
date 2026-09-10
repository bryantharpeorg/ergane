from __future__ import annotations

from pathlib import Path

from factory.cli.status import (
    FloorStatus,
    QueueEntry,
    ReadinessBasis,
    _readiness_basis,
    _queue_lines,
    _read_corpus,
)
from factory.roadmap.models import (
    LandedKind,
    LandedStatus,
    SpecState,
    compute_readiness,
)
from tests.target_repo import git
from tests.test_roadmap_scheduler import build_corpus


def _observed_landed(spec_dir: str) -> LandedStatus | None:
    return LandedStatus(landed=True, kind=LandedKind.OBSERVED)


def _floor(entry: QueueEntry) -> FloorStatus:
    return FloorStatus(
        specs_root=str(Path("specs")),
        roadmap=None,
        epics=[],
        queue=[entry],
        drafts=[],
        pace=[],
        readiness_basis=ReadinessBasis(observed=True, detail="test"),
        notes=[],
        degraded=False,
    )


def test_a_built_ready_spec_is_not_dispatchable(tmp_path: Path) -> None:
    """US2-S1: a supplied observed-landed answer keeps `ready` from dispatching."""
    specs_root = build_corpus(tmp_path, {"131-built": {"state": SpecState.READY}})
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(
        roadmap, landed_for=_observed_landed, drifted_for=lambda spec_dir: False
    )

    assert readiness.spec("131-built").dispatchable is False


def test_a_built_ready_spec_renders_as_built_not_ready_or_landed(
    tmp_path: Path,
) -> None:
    """US2-S2: attestation is the outstanding act, so the state is a third word."""
    specs_root = build_corpus(tmp_path, {"131-built": {"state": SpecState.READY}})
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(
        roadmap, landed_for=_observed_landed, drifted_for=lambda spec_dir: False
    )

    rendered = readiness.spec("131-built").rendered_state
    assert rendered not in {SpecState.READY.value, SpecState.LANDED.value}


def test_a_built_and_drifted_ready_spec_still_dispatches(tmp_path: Path) -> None:
    """Trap 17: drift supplies the exit from the not-dispatchable built state."""
    specs_root = build_corpus(tmp_path, {"131-amended": {"state": SpecState.READY}})
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(
        roadmap, landed_for=_observed_landed, drifted_for=lambda spec_dir: True
    )

    assert readiness.spec("131-amended").dispatchable is True


def test_landed_without_a_drift_resolver_leaves_today_s_behavior(tmp_path: Path) -> None:
    """Trap 18: an unsupplied drift answer is not evidence that a spec is clean."""
    specs_root = build_corpus(tmp_path, {"131-built": {"state": SpecState.READY}})
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(roadmap, landed_for=_observed_landed)

    assert readiness.spec("131-built").dispatchable is True


def test_the_built_queue_line_reports_the_outstanding_attestation(tmp_path: Path) -> None:
    """US2-S3: the line follows the computed flag and replaces `dispatchable`."""
    entry = QueueEntry(
        spec_dir="131-built",
        state="built",
        dispatchable=False,
        blockers=[],
    )

    line = _queue_lines(_floor(entry))[0]

    assert line == "131-built  built  awaiting attestation"


def test_a_ready_spec_with_an_unlanded_story_still_dispatches(tmp_path: Path) -> None:
    """US2-S4: landing on only some stories leaves the spec `ready`."""
    specs_root = build_corpus(tmp_path, {"131-begun": {"state": SpecState.READY}})
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(
        roadmap,
        landed_for=lambda spec_dir: None,
        drifted_for=lambda spec_dir: False,
    )

    spec = readiness.spec("131-begun")
    assert spec.dispatchable is True
    assert spec.rendered_state == "ready"


def _committed_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Build and commit one clean ready fixture on its own landing branch."""
    repo = tmp_path / "repo"
    specs_root = build_corpus(repo, {"131-built": {"state": SpecState.READY}})
    git(repo, "init", "-b", "main", "--quiet")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "131-built/us1: US1 (#1)")
    return repo, specs_root


def test_status_supplies_a_drift_answer_for_a_landed_ready_spec(tmp_path: Path) -> None:
    """The CLI closes the built window only when the fingerprints are clean."""
    repo, specs_root = _committed_fixture(tmp_path)
    roadmap = _read_corpus(specs_root)
    _, landed_for, drifted_for = _readiness_basis(roadmap, specs_root)

    readiness = compute_readiness(
        roadmap, landed_for=landed_for, drifted_for=drifted_for
    )

    spec = readiness.spec("131-built")
    assert spec.dispatchable is False
    assert spec.rendered_state == "built"
    assert drifted_for is not None and drifted_for("131-built") is False


def test_status_supplies_drift_that_reopens_a_landed_ready_spec(
    tmp_path: Path,
) -> None:
    """The amended rebuild path stays dispatchable on `ergane status specs`."""
    repo, specs_root = _committed_fixture(tmp_path)
    spec_path = specs_root / "131-built" / "spec.md"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace("it works", "it works differently"),
        encoding="utf-8",
    )
    roadmap = _read_corpus(specs_root)
    _, landed_for, drifted_for = _readiness_basis(roadmap, specs_root)

    readiness = compute_readiness(
        roadmap, landed_for=landed_for, drifted_for=drifted_for
    )

    spec = readiness.spec("131-built")
    assert spec.dispatchable is True
    assert spec.rendered_state == "ready"
    assert drifted_for is not None and drifted_for("131-built") is True
