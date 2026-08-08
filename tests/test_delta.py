"""Delta derivation: subtract what already landed, reopen what changed, refuse bad identity.

The delta function is pure: (spec_text, baseline) -> DeltaResult.  It wraps the
full deriver and then applies the rules from US2.  These tests drive it through
the existing fixture corpus plus the banked 007/009 remainder graphs.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from factory.workgraph.derive import DerivationError, Rejection, derive_workgraph
from factory.workgraph.models import WorkGraph, WorkNode

CORPUS = Path(__file__).resolve().parent / "fixtures"
WORKGRAPH_CORPUS = CORPUS / "workgraph"
REMAINDERS = CORPUS / "remainders"

EPIC_ID = "042-short-links"
FEATURE = "042-short-links"
SPECS_ROOT = "specs"
TARGET_REPO = "/home/admin/code/ergane-target"

IDENTITY = {
    "epic_id": EPIC_ID,
    "feature": FEATURE,
    "specs_root": SPECS_ROOT,
    "target_repo": TARGET_REPO,
}


def _spec_text(fixture: str = "valid_epic") -> str:
    return (WORKGRAPH_CORPUS / fixture / "spec.md").read_text(encoding="utf-8")


def _full_graph(fixture: str = "valid_epic") -> WorkGraph:
    return derive_workgraph(_spec_text(fixture), **IDENTITY)


def _baseline(*facts: tuple[str, str]) -> dict[str, Any]:
    """Build a minimal baseline dict: story_key -> {commit, fingerprint}."""
    text = _spec_text("valid_epic")
    from factory.workgraph.landed import Fingerprint
    from factory.workgraph.delta import fingerprint_for

    full = _full_graph()
    baseline: dict[str, Any] = {}
    for story_key, commit in facts:
        fp = fingerprint_for(text, story_key)
        baseline[story_key] = {"commit": commit, "fingerprint": fp}
    return baseline


# --- T007: delta rules -------------------------------------------------------


def test_empty_baseline_yields_full_derivation_node_for_node() -> None:
    """SC-001 / FR-006: an empty baseline is the existing derive path."""
    from factory.workgraph.delta import derive_delta

    spec_text = _spec_text("valid_epic")
    full = _full_graph()
    result = derive_delta(spec_text, baseline={}, **IDENTITY)
    assert result.graph == full
    assert result.provenance == {}


def test_unchanged_landed_story_is_subtracted() -> None:
    """SC-002: a landed story whose fingerprint matches is removed entirely."""
    from factory.workgraph.delta import derive_delta

    spec_text = _spec_text("valid_epic")
    baseline = _baseline(("US1", "abc123"))
    result = derive_delta(spec_text, baseline=baseline, **IDENTITY)

    assert {n.story_key for n in result.graph.nodes} == {"US2", "US3"}
    assert result.provenance["us1"] == {"satisfied_by": "abc123"}
    assert result.provenance["us2"] == {"satisfied_edge_to": "us1", "by": "abc123"}


def test_edges_into_subtracted_stories_are_satisfied() -> None:
    """SC-002 / FR-005: edges through a subtracted story are dropped with provenance."""
    from factory.workgraph.delta import derive_delta

    spec_text = _spec_text("valid_epic")
    baseline = _baseline(("US1", "abc123"))
    result = derive_delta(spec_text, baseline=baseline, **IDENTITY)

    us2 = next(n for n in result.graph.nodes if n.id == "us2")
    assert us2.depends_on == []
    assert result.provenance == {
        "us1": {"satisfied_by": "abc123"},
        "us2": {"satisfied_edge_to": "us1", "by": "abc123"},
    }


def test_edges_are_satisfied_by_removal_only_not_retargeted() -> None:
    """plan.md US2 trap: a kept node loses an edge, it never points elsewhere."""
    from factory.workgraph.delta import derive_delta

    spec_text = _spec_text("valid_epic")
    baseline = _baseline(("US1", "abc123"))
    result = derive_delta(spec_text, baseline=baseline, **IDENTITY)

    # US2's depends_on is removed, not rewritten.
    us2 = next(n for n in result.graph.nodes if n.id == "us2")
    assert us2.depends_on == []
    assert "us1" not in us2.depends_on


def test_changed_scenario_reopens_story_with_diff() -> None:
    """SC-003: a changed acceptance scenario reopens the story."""
    from factory.workgraph.delta import derive_delta, fingerprint_for

    base_text = _spec_text("valid_epic")
    # Change US1's acceptance scenario wording.
    changed_text = base_text.replace(
        "a link is stored with a short code no other link holds",
        "a link is stored with a short code no other reader holds",
    )
    old_fp = fingerprint_for(base_text, "US1")
    baseline = {"US1": {"commit": "abc123", "fingerprint": old_fp}}

    result = derive_delta(changed_text, baseline=baseline, **IDENTITY)

    assert {n.story_key for n in result.graph.nodes} == {"US1", "US2", "US3"}
    assert "us1" in result.provenance
    prov = result.provenance["us1"]
    assert prov["reopened"]
    assert "scenarios" in prov["what_changed"].lower() or "given" in prov["what_changed"].lower()


def test_changed_fr_body_reopens_story_with_diff() -> None:
    """SC-003: a changed implemented FR body reopens the story."""
    from factory.workgraph.delta import derive_delta, fingerprint_for

    base_text = _spec_text("valid_epic")
    changed_text = base_text.replace(
        "assign every stored link a short code unique across all links",
        "assign every stored link a short code unique across the reader's own links",
    )
    old_fp = fingerprint_for(base_text, "US1")
    baseline = {"US1": {"commit": "abc123", "fingerprint": old_fp}}

    result = derive_delta(changed_text, baseline=baseline, **IDENTITY)

    assert {n.story_key for n in result.graph.nodes} == {"US1", "US2", "US3"}
    prov = result.provenance["us1"]
    assert prov["reopened"]
    assert "fr" in prov["what_changed"].lower()


def test_changed_declaration_reopens_story_with_diff() -> None:
    """SC-003: a changed work-graph declaration reopens the story."""
    from factory.workgraph.delta import derive_delta, fingerprint_for

    base_text = _spec_text("valid_epic")
    changed_text = base_text.replace(
        "US1:\n  depends_on: []\n  implements: [FR-001, FR-002]",
        "US1:\n  depends_on: []\n  implements: [FR-001, FR-002, FR-003]",
    )
    old_fp = fingerprint_for(base_text, "US1")
    baseline = {"US1": {"commit": "abc123", "fingerprint": old_fp}}

    result = derive_delta(changed_text, baseline=baseline, **IDENTITY)

    us1 = next(n for n in result.graph.nodes if n.id == "us1")
    assert "FR-003" in us1.requirement_keys
    prov = result.provenance["us1"]
    assert prov["reopened"]
    assert "declaration" in prov["what_changed"].lower()


def test_prose_only_edit_yields_empty_delta() -> None:
    """Prose outside the fingerprint components must not reopen a landed story.

    A full-graph delta with every story satisfied must drop every node, leaving
    an empty graph and only satisfied provenance.
    """
    from factory.workgraph.delta import derive_delta, fingerprint_for

    base_text = _spec_text("valid_epic")
    changed_text = base_text.replace(
        "Prose in this section is welcome and read past",
        "Prose in this section is welcome and absolutely ignored",
    )
    old_fp = {
        story_key: fingerprint_for(base_text, story_key)
        for story_key in ("US1", "US2", "US3")
    }
    baseline = {
        story_key: {"commit": f"abc{index}", "fingerprint": old_fp[story_key]}
        for index, story_key in enumerate(["US1", "US2", "US3"], start=1)
    }

    result = derive_delta(changed_text, baseline=baseline, **IDENTITY)

    assert result.graph.nodes == []
    assert result.provenance == {
        "us1": {"satisfied_by": "abc1"},
        "us2": {"satisfied_by": "abc2"},
        "us3": {"satisfied_by": "abc3"},
    }


# --- T008: identity guard ------------------------------------------------------


def test_landed_story_absent_from_spec_refuses() -> None:
    """FR-007: a baseline key that the current spec no longer declares is refused."""
    from factory.workgraph.delta import derive_delta

    spec_text = _spec_text("valid_epic")
    baseline = {
        "US9": {"commit": "abc123", "fingerprint": "anything"},
    }
    with pytest.raises(DerivationError) as caught:
        derive_delta(spec_text, baseline=baseline, **IDENTITY)
    assert any(r.story == "US9" for r in caught.value.rejections)




def test_identity_refusals_are_collected_all_at_once() -> None:
    """FR-007 / SC-006: all identity problems are reported together."""
    from factory.workgraph.delta import derive_delta

    spec_text = _spec_text("valid_epic")
    baseline = {
        "US9": {"commit": "abc123", "fingerprint": "anything"},
        "US8": {"commit": "def456", "fingerprint": "anything"},
    }
    with pytest.raises(DerivationError) as caught:
        derive_delta(spec_text, baseline=baseline, **IDENTITY)
    stories = {r.story for r in caught.value.rejections}
    assert {"US8", "US9"} <= stories


# --- T009: 007/009 remainder replay ------------------------------------------


def _remainder_graph(path: Path) -> WorkGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    return WorkGraph(
        epic_id=data["epic_id"],
        feature=data["feature"],
        specs_root=data["specs_root"],
        target_repo=data["target_repo"],
        nodes=[WorkNode(**n) for n in data["nodes"]],
    )


def _build_baseline(feature_dir: str, landed_stories: dict[str, str]) -> dict[str, Any]:
    """Build a baseline from the real spec text and landing commits.

    `landed_stories` maps story key -> commit sha.
    """
    from factory.workgraph.delta import fingerprint_for

    spec_path = Path("specs") / feature_dir / "spec.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    baseline: dict[str, Any] = {}
    for story_key, commit in landed_stories.items():
        baseline[story_key] = {
            "commit": commit,
            "fingerprint": fingerprint_for(spec_text, story_key),
        }
    return baseline


def test_007_split_replays_to_banked_remainder() -> None:
    """SC-002: 007 split, us1/us2 landed -> only us3/us4/us5 remain."""
    from factory.workgraph.delta import derive_delta

    feature_dir = "007-parallel-dispatch"
    spec_text = (Path("specs") / feature_dir / "spec.md").read_text(encoding="utf-8")
    baseline = _build_baseline(
        feature_dir,
        {
            "US1": "9f0f37de6a8429988e0424e86ce35f73a4dfd2b4",
            "US2": "18b3d674d218dcf2e0e842733a8ed1b5d5336305",
        },
    )

    result = derive_delta(
        spec_text,
        baseline=baseline,
        epic_id=feature_dir,
        feature=feature_dir,
        specs_root="specs",
        target_repo="/home/admin/code/ergane-007-target",
    )

    expected = _remainder_graph(REMAINDERS / "007-parallel-dispatch-remainder.json")
    assert result.graph == expected


def test_009_split_replays_to_banked_remainder() -> None:
    """SC-002: 009 split, us1 landed -> us2/us3 remain; us3 keeps depends_on_merged us2."""
    from factory.workgraph.delta import derive_delta

    feature_dir = "009-roadmap-scheduler"
    spec_text = (Path("specs") / feature_dir / "spec.md").read_text(encoding="utf-8")
    baseline = _build_baseline(
        feature_dir,
        {
            "US1": "5f6aef16b37184942052fa0d82756a6deeab6380",
        },
    )

    result = derive_delta(
        spec_text,
        baseline=baseline,
        epic_id=feature_dir,
        feature=feature_dir,
        specs_root="specs",
        target_repo="/home/admin/code/ergane-009-target",
    )

    expected = _remainder_graph(REMAINDERS / "009-roadmap-scheduler-remainder.json")
    assert result.graph == expected
