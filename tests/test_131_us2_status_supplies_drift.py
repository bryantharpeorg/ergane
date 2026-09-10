from __future__ import annotations

from pathlib import Path

from factory.cli.status import _read_corpus
from factory.roadmap.models import (
    LandedKind,
    LandedStatus,
    SpecState,
    compute_readiness,
)
from tests.test_roadmap_scheduler import build_corpus


def _observed_landed(spec_dir: str) -> LandedStatus | None:
    return LandedStatus(landed=True, kind=LandedKind.OBSERVED)


def test_readiness_reaches_both_facts_through_the_injected_resolvers(
    tmp_path: Path,
) -> None:
    """US4-S1: the pure predicate receives its facts and owns no repository."""
    specs_root = build_corpus(
        tmp_path / "corpus-only", {"131-built": {"state": SpecState.READY}}
    )
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(
        roadmap,
        landed_for=_observed_landed,
        drifted_for=lambda spec_dir: False,
    )

    spec = readiness.spec("131-built")
    assert spec.dispatchable is False
    assert spec.rendered_state == "built"


def test_a_drifted_landed_ready_spec_still_dispatches(tmp_path: Path) -> None:
    """US4-S2: a supplied drift answer keeps the amended rebuild path open."""
    specs_root = build_corpus(
        tmp_path / "corpus-only", {"131-amended": {"state": SpecState.READY}}
    )
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(
        roadmap,
        landed_for=_observed_landed,
        drifted_for=lambda spec_dir: True,
    )

    spec = readiness.spec("131-amended")
    assert spec.dispatchable is True
    assert spec.rendered_state == "ready"


def test_an_absent_drift_answer_is_not_a_negative_answer(tmp_path: Path) -> None:
    """US4-S3: only a supplied `False` can close a built `ready` spec."""
    specs_root = build_corpus(
        tmp_path / "corpus-only", {"131-built": {"state": SpecState.READY}}
    )
    roadmap = _read_corpus(specs_root)

    readiness = compute_readiness(roadmap, landed_for=_observed_landed)

    spec = readiness.spec("131-built")
    assert spec.dispatchable is True
    assert spec.rendered_state == "ready"
