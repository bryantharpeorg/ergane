"""Delta derivation: full derive, then subtract what already landed.

A pure function over (spec_text, baseline) emitting a compiled `WorkGraph` and
provenance.  It wraps `derive_workgraph` unchanged, then:

- keeps every unlanded story;
- subtracts every landed story whose pinned fingerprint equals the current
  fingerprint, recording satisfied edges;
- re-opens every landed story whose fingerprint changed, carrying the diff as
  provenance;
- refuses by name when identity is broken (missing story, or a story number
  whose content no longer matches its pinned fingerprint).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from factory.workgraph.derive import (
    DerivationError,
    Rejection,
    derive_workgraph,
)
from factory.workgraph.landed import Fingerprint, _declaration_text, _story_parts
from factory.workgraph.models import WorkGraph, WorkNode


@dataclass(frozen=True)
class DeltaResult:
    """The compiled delta graph plus provenance for every touched node."""

    graph: WorkGraph
    #: node id -> provenance record.  For subtracted nodes:
    #  {"satisfied_by": commit}.  For nodes whose edge was satisfied:
    #  {"satisfied_edge_to": id, "by": commit}.  For reopened nodes:
    #  {"reopened": True, "what_changed": str}.
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class StoryFingerprint(Fingerprint):
    """A fingerprint with per-component digests, so delta can explain what changed."""

    components: dict[str, str] = field(default_factory=dict)


def fingerprint_for(spec_text: str, story_key: str) -> StoryFingerprint:
    """Structural fingerprint of one story in the current spec text.

    Used by tests and by callers that already have the spec text in hand and do
    not want to shell git.  Returns per-component digests so `derive_delta` can
    quote which part changed.
    """
    scenarios, fr_bodies, declaration = _story_parts(spec_text, story_key)
    components = {
        "scenarios": _component_digest(scenarios),
        "fr_bodies": _component_digest(fr_bodies),
        "declaration": _component_digest(declaration),
    }
    digest = _structural_digest(
        {
            "story_key": story_key,
            "scenarios": scenarios,
            "fr_bodies": fr_bodies,
            "declaration": declaration,
        }
    )
    return StoryFingerprint(
        story_key=story_key, revision="current", digest=digest, components=components
    )


def derive_delta(
    spec_text: str,
    *,
    baseline: Mapping[str, Mapping[str, Any]],
    epic_id: str,
    feature: str,
    specs_root: str,
    target_repo: str,
) -> DeltaResult:
    """Derive a workgraph containing only work that remains.

    `baseline` maps story key -> {"commit": str, "fingerprint": Fingerprint-like}.
    """
    full = derive_workgraph(
        spec_text,
        epic_id=epic_id,
        feature=feature,
        specs_root=specs_root,
        target_repo=target_repo,
    )

    derived_by_key: dict[str, WorkNode] = {node.story_key: node for node in full.nodes}

    # Compute current fingerprints once per baseline story.
    current_fps: dict[str, StoryFingerprint] = {
        story_key: fingerprint_for(spec_text, story_key) for story_key in baseline
    }

    # Identity guard first: every baseline key must be present in the derived graph
    # with content that matches its pinned fingerprint.
    rejections: list[Rejection] = []
    for story_key, fact in baseline.items():
        node = derived_by_key.get(story_key)
        if node is None:
            rejections.append(
                Rejection(
                    rule="identity_missing",
                    story=story_key,
                    problem=(
                        f"baseline claims story {story_key} landed at {fact['commit']}, "
                        "but the current spec does not declare it"
                    ),
                )
            )
            continue

        pinned = fact.get("fingerprint")
        if pinned is None:
            rejections.append(
                Rejection(
                    rule="identity_unclassifiable",
                    story=story_key,
                    problem=(
                        f"baseline for {story_key} carries no fingerprint; "
                        "cannot verify identity"
                    ),
                )
            )
            continue

        current_fp = current_fps[story_key]
        if pinned.digest == current_fp.digest:
            # Satisfied: will be subtracted in the second pass.
            continue

        # The fingerprint differs.  Re-opening is allowed only when the current
        # story still has a work-graph declaration (so the number is still a
        # declared story in this spec) and none of the *other* current story
        # fingerprints match the pinned one (which would mean this story number
        # has taken over another story's content).
        if _declaration_text(spec_text, story_key) is None:
            rejections.append(
                Rejection(
                    rule="identity_renumbered",
                    story=story_key,
                    problem=(
                        "baseline fingerprint does not match current content and "
                        "the story has no work-graph declaration"
                    ),
                )
            )
            continue

        other_story = next(
            (
                other_key
                for other_key, other_fp in current_fps.items()
                if other_key != story_key and other_fp.digest == pinned.digest
            ),
            None,
        )
        if other_story is not None:
            rejections.append(
                Rejection(
                    rule="identity_renumbered",
                    story=story_key,
                    problem=(
                        f"baseline fingerprint for {story_key} matches the current "
                        f"fingerprint of {other_story}; landed story numbers are immutable"
                    ),
                )
            )
            continue

    if rejections:
        raise DerivationError(rejections)

    # Second pass: classify each baseline story and build provenance.
    provenance: dict[str, dict[str, Any]] = {}
    subtracted: set[str] = set()
    commit_by_id: dict[str, str] = {}
    for story_key, fact in baseline.items():
        node = derived_by_key[story_key]
        if current_fps[story_key].digest == fact["fingerprint"].digest:
            subtracted.add(node.id)
            provenance[node.id] = {"satisfied_by": fact["commit"]}
            commit_by_id[node.id] = fact["commit"]

    # Build the remaining graph: drop subtracted nodes and remove edges to them.
    kept_nodes: list[WorkNode] = []
    for node in full.nodes:
        if node.id in subtracted:
            continue

        new_depends_on: list[str] = []
        for dep in node.depends_on:
            if dep in subtracted:
                provenance.setdefault(node.id, {}).update(
                    {"satisfied_edge_to": dep, "by": commit_by_id[dep]}
                )
            else:
                new_depends_on.append(dep)

        new_depends_on_merged: list[str] = []
        for dep in node.depends_on_merged:
            if dep in subtracted:
                provenance.setdefault(node.id, {}).update(
                    {"satisfied_edge_to": dep, "by": commit_by_id[dep]}
                )
            else:
                new_depends_on_merged.append(dep)

        kept_nodes.append(
            WorkNode(
                id=node.id,
                story_key=node.story_key,
                persona=node.persona,
                spec_ref=node.spec_ref,
                requirement_keys=node.requirement_keys,
                depends_on=new_depends_on,
                depends_on_merged=new_depends_on_merged,
                timeout_override_s=node.timeout_override_s,
            )
        )

    # Reopened nodes: add provenance for stories whose fingerprint changed.
    for node in kept_nodes:
        if node.story_key in baseline:
            pinned = baseline[node.story_key]["fingerprint"]
            current_fp = current_fps[node.story_key]
            if current_fp.digest != pinned.digest:
                provenance[node.id] = {
                    "reopened": True,
                    "what_changed": _what_changed(current_fp, pinned),
                }

    return DeltaResult(
        graph=WorkGraph(
            epic_id=full.epic_id,
            feature=full.feature,
            specs_root=full.specs_root,
            target_repo=full.target_repo,
            nodes=kept_nodes,
        ),
        provenance=provenance,
    )


def _what_changed(current: StoryFingerprint, pinned: Fingerprint) -> str:
    """Human-readable summary of which fingerprint components differ."""
    if not isinstance(pinned, StoryFingerprint) or not pinned.components:
        return f"fingerprint changed from {pinned.digest} to {current.digest}"

    changed: list[str] = []
    for key in ("scenarios", "fr_bodies", "declaration"):
        if pinned.components.get(key) != current.components.get(key):
            changed.append(key)
    if not changed:
        return f"fingerprint changed from {pinned.digest} to {current.digest}"
    return f"changed: {', '.join(changed)}"


def _component_digest(value: object) -> str:
    """Hash a single component in the same canonical form as the full fingerprint."""
    return _structural_digest({"value": value})


def _structural_digest(payload: dict) -> str:
    """Canonicalize a dict for hashing; mirrors landed._structural_digest."""
    from factory.workgraph.landed import _normalize, _serialize

    text = _normalize(_serialize(payload))
    from hashlib import sha256

    return sha256(text.encode("utf-8")).hexdigest()
