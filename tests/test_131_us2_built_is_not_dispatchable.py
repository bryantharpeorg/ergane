from __future__ import annotations

from pathlib import Path

from factory.cli.status import (
    FloorStatus,
    QueueEntry,
    ReadinessBasis,
    _queue_lines,
    _read_corpus,
)
from factory.roadmap.models import (
    LandedKind,
    LandedStatus,
    SpecState,
    compute_readiness,
)
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
