from __future__ import annotations

from pathlib import Path

import factory.cli.status as status_module
from factory.cli.status import _read_corpus
from factory.cli.status import _readiness_basis
from factory.roadmap.models import (
    LandedKind,
    LandedStatus,
    SpecState,
    compute_readiness,
)
from tests.test_roadmap_scheduler import build_corpus
from tests.target_repo import git


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


def _committed_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Create a clean one-story spec with one pinned landing commit."""
    repo = tmp_path / "repo"
    specs_root = build_corpus(repo, {"131-built": {"state": SpecState.READY}})
    git(repo, "init", "-b", "main", "--quiet")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "131-built/us1: US1 (#1)")
    return repo, specs_root


def test_status_drift_is_consulted_only_for_a_landed_ready_spec(
    tmp_path: Path, monkeypatch
) -> None:
    """US4-S4: the landed read gates each fingerprint comparison."""
    repo = tmp_path / "repo"
    specs_root = build_corpus(
        repo,
        {
            "131-built": {"state": SpecState.READY},
            "131-begun": {"state": SpecState.READY},
            "131-attested": {"state": SpecState.LANDED},
        },
    )
    git(repo, "init", "-b", "main", "--quiet")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "131-built/us1: US1 (#1)")
    fingerprint = status_module.fingerprint
    fingerprint_reads: list[str] = []

    def spy(repo_path, rev, spec_dir, story_key):
        fingerprint_reads.append(spec_dir)
        return fingerprint(repo_path, rev, spec_dir, story_key)

    monkeypatch.setattr(status_module, "fingerprint", spy)
    roadmap = _read_corpus(specs_root)
    _, landed_for, drifted_for = _readiness_basis(roadmap, specs_root)

    readiness = compute_readiness(
        roadmap, landed_for=landed_for, drifted_for=drifted_for
    )

    assert landed_for is not None
    assert landed_for("131-built") is not None
    assert landed_for("131-begun") is None
    assert fingerprint_reads == ["131-built"]
    assert readiness.spec("131-built").dispatchable is False
    assert readiness.spec("131-begun").dispatchable is True


def test_status_drift_compares_pinned_to_current_without_fetching(
    tmp_path: Path, monkeypatch
) -> None:
    """US4-S4: reporting compares the landing pins, never touching the remote."""
    repo, specs_root = _committed_fixture(tmp_path)
    landed_facts = status_module.landed_facts
    calls: list[bool] = []

    def spy(*args, **kwargs):
        calls.append(kwargs.get("fetch", True))
        return landed_facts(*args, **kwargs)

    monkeypatch.setattr(status_module, "landed_facts", spy)
    roadmap = _read_corpus(specs_root)
    _, landed_for, drifted_for = _readiness_basis(roadmap, specs_root)

    assert landed_for is not None and landed_for("131-built") is not None
    assert drifted_for is not None and drifted_for("131-built") is False
    assert calls and all(fetch is False for fetch in calls)

    spec_path = specs_root / "131-built" / "spec.md"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace(
            "it works", "it works differently"
        ),
        encoding="utf-8",
    )
    assert drifted_for("131-built") is True
