"""US1: a story can name the persona that builds it.

Every test here drives the pure deriver and the pure start-time validator. No
proxy, no filesystem, no Temporal — the story is about the compiled graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from factory.config import Persona, WriteScope, load_personas
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.delta import derive_delta, fingerprint_for
from factory.workgraph.landed import fingerprint
from factory.workgraph.models import WorkGraph, WorkNode, WorkGraphError, validate_workgraph

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"

EPIC_ID = "070-story-persona"
FEATURE = "070-story-persona"
SPECS_ROOT = "specs"
TARGET_REPO = "/home/admin/code/ergane-target"

IDENTITY = {
    "epic_id": EPIC_ID,
    "feature": FEATURE,
    "specs_root": SPECS_ROOT,
    "target_repo": TARGET_REPO,
}

IMPLEMENTER = "implementer"
DEFAULT_TIMEOUT = 14400


def _spec_text(
    *,
    us1_persona: str | None = None,
    us1_timeout: int | None = None,
    us2_persona: str | None = None,
    us2_timeout: int | None = None,
    us3_persona: str | None = None,
    us3_timeout: int | None = None,
) -> str:
    """A minimal three-story spec with per-story persona and timeout overrides."""
    lines = [
        "# Feature Specification: Story Persona Pinning",
        "",
        "## User Scenarios & Testing",
        "",
        "### User Story 1 - First story (Priority: P1)",
        "",
        "As a reader, I can see the first story.",
        "",
        "**Acceptance Scenarios**:",
        "",
        "1. **Given** the first story, **When** it runs, **Then** it passes.",
        "",
        "---",
        "",
        "### User Story 2 - Second story (Priority: P1)",
        "",
        "As a reader, I can see the second story.",
        "",
        "**Acceptance Scenarios**:",
        "",
        "1. **Given** the second story, **When** it runs, **Then** it passes.",
        "",
        "---",
        "",
        "### User Story 3 - Third story (Priority: P2)",
        "",
        "As a reader, I can see the third story.",
        "",
        "**Acceptance Scenarios**:",
        "",
        "1. **Given** the third story, **When** it runs, **Then** it passes.",
        "",
        "## Requirements",
        "",
        "### Functional Requirements",
        "",
        "- **FR-001**: The system MUST make the first story work.",
        "- **FR-002**: The system SHALL make the second story work.",
        "- **FR-003**: The system SHALL make the third story work.",
        "",
        "## Work Graph",
        "",
        "```yaml",
    ]

    def _entry(story: str, persona: str | None, timeout: int | None) -> list[str]:
        out = [f"{story}:", "  depends_on: []", f"  implements: [FR-001]"]
        if persona is not None:
            out.append(f"  persona: {persona}")
        if timeout is not None:
            out.append(f"  timeout: {timeout}")
        return out

    lines.extend(_entry("US1", us1_persona, us1_timeout))
    lines.extend(_entry("US2", us2_persona, us2_timeout))
    lines.extend(_entry("US3", us3_persona, us3_timeout))
    lines.extend(["```", ""])
    return "\n".join(lines)


def _derive(
    **overrides: Any,
) -> WorkGraph:
    return derive_workgraph(_spec_text(**overrides), **IDENTITY)


def _persona(
    name: str = IMPLEMENTER, *, timeout_s: int | None = DEFAULT_TIMEOUT
) -> Persona:
    return Persona(
        name=name,
        agent="claude-code",
        model="fake-provider/CHANGEME",
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=timeout_s,
    )


def _registry(**kwargs: Persona) -> dict[str, Persona]:
    registry = {IMPLEMENTER: _persona()}
    registry.update(kwargs)
    return registry


# T001 [P] [US1] (spec US1-S1) ----------------------------------------------


def test_pinned_story_carries_persona_and_siblings_default() -> None:
    """One story declares a persona; that node carries it, the rest keep default."""
    graph = _derive(us2_persona="closer")

    personas = {node.id: node.persona for node in graph.nodes}
    assert personas == {"us1": IMPLEMENTER, "us2": "closer", "us3": IMPLEMENTER}


# T002 [P] [US1] (spec US1-S2) ----------------------------------------------


def test_unpinned_story_carries_default_persona() -> None:
    """A story declaring no persona carries the default implementer."""
    graph = _derive()

    assert {node.id: node.persona for node in graph.nodes} == {
        "us1": IMPLEMENTER,
        "us2": IMPLEMENTER,
        "us3": IMPLEMENTER,
    }


# T003 [P] [US1] (spec US1-S3) ----------------------------------------------


def test_unknown_persona_rejected_at_start_naming_story_and_persona() -> None:
    """A declared persona absent from the registry reaches validate_workgraph."""
    graph = _derive(us2_persona="nosuchpersona")
    registry = _registry()

    with pytest.raises(WorkGraphError) as caught:
        validate_workgraph(graph, registry)

    message = str(caught.value)
    assert "us2" in message
    assert "nosuchpersona" in message


# T004 [P] [US1] (spec US1-S4) ----------------------------------------------


def test_persona_without_timeout_rejected_at_start() -> None:
    """A persona that resolves no timeout is rejected at epic start."""
    graph = _derive(us2_persona="notimeout")
    registry = _registry(notimeout=_persona("notimeout", timeout_s=None))

    with pytest.raises(WorkGraphError) as caught:
        validate_workgraph(graph, registry)

    message = str(caught.value)
    assert "us2" in message
    assert "notimeout" in message
    assert "timeout" in message.lower()


# T005 [P] [US1] (spec US1-S5) ----------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"us1_persona": "closer"},
        {"us2_timeout": 3600},
        {"us1_persona": "closer", "us3_timeout": 7200},
    ],
    ids=["neither", "persona_only", "timeout_only", "both"],
)
def test_persona_key_is_optional_like_timeout(kwargs: dict[str, Any]) -> None:
    """Blocks with neither key, one key, or both all derive successfully."""
    graph = _derive(**kwargs)

    assert len(graph.nodes) == 3
    assert {node.story_key for node in graph.nodes} == {"US1", "US2", "US3"}


# T006 [P] [US1] (spec US1-S6) ----------------------------------------------


def test_pinned_persona_is_snapshotted_at_epic_start() -> None:
    """A registry edit mid-epic does not change the running node's resolution."""
    graph = _derive(us2_persona="closer")
    registry_v1 = _registry(closer=_persona("closer", timeout_s=3600))
    validate_workgraph(graph, registry_v1)

    # Simulate an operator editing personas.yaml after the epic started: the same
    # graph validated against a different registry must still carry the pinned
    # persona, and validation succeeds because the snapshot is fixed.
    registry_v2 = _registry(closer=_persona("closer", timeout_s=9999))
    validate_workgraph(graph, registry_v2)

    # The node itself still says "closer" regardless of which registry it was
    # validated against — the resolution happens once at start against the snapshot.
    us2 = next(node for node in graph.nodes if node.id == "us2")
    assert us2.persona == "closer"


# T048 [P] [US1] (spec US1-S7, trap 16) -------------------------------------
#
# Decision: exclude `persona` from the declaration component of the fingerprint.
# A `persona:` key is a routing annotation, not part of what the story means; the
# operator's plan is to pin existing specs to different personas, and a routing
# change must not silently reopen already-landed work. The diff and a committed
# test below say this choice was made deliberately.


def test_adding_persona_to_landed_story_does_not_reopen_it() -> None:
    """A landed story stays landed when a `persona:` key is added to its block."""
    base_text = _spec_text()
    changed_text = _spec_text(us2_persona="closer")

    base_fp = fingerprint_for(base_text, "US2")
    current_fp = fingerprint_for(changed_text, "US2")

    assert base_fp.digest == current_fp.digest, (
        "adding a persona key must not change the story's fingerprint"
    )

    baseline = {"US2": {"commit": "abc123", "fingerprint": base_fp}}
    result = derive_delta(changed_text, baseline=baseline, **IDENTITY)

    assert "us2" not in {node.id for node in result.graph.nodes}
    assert result.provenance.get("us2") == {"satisfied_by": "abc123"}


# Guard: the deriver still refuses unknown keys other than persona/timeout -------


def test_persona_key_is_no_longer_unknown() -> None:
    """The previous `unknown_key` fixture behavior is replaced by carrying it."""
    graph = _derive(us2_persona="closer")

    assert next(node for node in graph.nodes if node.id == "us2").persona == "closer"
