"""US1: a story can name the persona that builds it.

A story's `## Work Graph` declaration may carry an optional `persona:` key that
names a persona in the operator's registry. A node that declares none keeps the
default implementer. Every validation path that already existed for timeout and
persona resolution remains the one refusal a bad declaration reaches.

The key is also excluded from the landed-story fingerprint: pinning an already
landed story to a different persona must not silently reopen it.
"""

from __future__ import annotations

import pytest

from factory.config import Persona, WriteScope
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.landed import Fingerprint, fingerprint
from factory.workgraph.models import WorkGraph, WorkGraphError, WorkNode, validate_workgraph

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

IMPLEMENTER = "implementer"


def _spec_text(work_graph: str, stories: int = 3) -> str:
    """A minimal spec with the requested number of US<n> story headers."""
    body = "# Feature\n\n## Requirements *(mandatory)*\n\n"
    body += "- **FR-001**: The system MUST do one thing.\n\n"
    for number in range(1, stories + 1):
        body += (
            f"### User Story {number} - Story {number} (Priority: P{number})\n\n"
            "As the operator, I want this.\n\n"
            "**Acceptance Scenarios**:\n"
            "1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        )
    body += "## Work Graph\n\n```yaml\n" + work_graph + "\n```\n"
    return body


def _derive(work_graph: str) -> WorkGraph:
    """Derive a graph whose spec contains exactly the stories the block declares."""
    stories = sum(1 for line in work_graph.splitlines() if line.strip().endswith(":"))
    return derive_workgraph(_spec_text(work_graph, stories), **IDENTITY)


def _persona(name: str = IMPLEMENTER, *, timeout_s: int | None = 3600) -> Persona:
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


def _node(**overrides: object) -> WorkNode:
    """One compiled node with the US1 defaults."""
    fields: dict[str, object] = {
        "id": "us1",
        "story_key": "US1",
        "persona": IMPLEMENTER,
        "spec_ref": f"{FEATURE}:US1",
        "requirement_keys": ["US1"],
        "depends_on": [],
        "depends_on_merged": [],
        "timeout_override_s": None,
    }
    fields.update(overrides)
    return WorkNode(**fields)  # type: ignore[arg-type]


# T001 [P] [US1] (spec US1-S1) -----------------------------------------------


def test_pinned_story_carries_persona_siblings_carry_default() -> None:
    """One pinned story carries the declared persona; its siblings keep the default.

    Asserting both halves prevents a change that sets every node's persona from
    passing an assertion about only the declared one.
    """
    graph = _derive(
        "US1:\n  depends_on: []\n  implements: []\n  persona: debugger\n"
        "US2:\n  depends_on: []\n  implements: []\n"
        "US3:\n  depends_on: []\n  implements: []\n"
    )

    personas = {node.id: node.persona for node in graph.nodes}
    assert personas == {"us1": "debugger", "us2": IMPLEMENTER, "us3": IMPLEMENTER}


# T002 [P] [US1] (spec US1-S2) -----------------------------------------------


def test_story_without_persona_carries_default_implementer() -> None:
    """A declaration with no `persona:` key behaves exactly as today."""
    graph = _derive("US1:\n  depends_on: []\n  implements: []\n")

    assert graph.nodes[0].persona == IMPLEMENTER


# T003 [P] [US1] (spec US1-S3) -----------------------------------------------


def test_unknown_persona_reaches_existing_validate_workgraph_refusal() -> None:
    """A declared persona absent from the registry is rejected at epic start.

    The refusal must be `validate_workgraph`'s existing message, naming both the
    node and the unknown persona — not a second refusal invented by the deriver.
    """
    graph = _derive("US1:\n  depends_on: []\n  implements: []\n  persona: archaeologist\n")

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, {IMPLEMENTER: _persona()})

    message = str(excinfo.value)
    assert "us1" in message
    assert "archaeologist" in message


# T004 [P] [US1] (spec US1-S4) -----------------------------------------------


def test_persona_without_timeout_reaches_existing_resolution_refusal() -> None:
    """A persona that resolves no timeout is rejected at start.

    The path is `resolve_timeout_s`'s existing contract (`models.py:355-363`):
    the pinned persona has no timeout and the story declares none, so the node
    cannot be bounded.
    """
    graph = _derive("US1:\n  depends_on: []\n  implements: []\n  persona: researcher\n")
    registry = {
        IMPLEMENTER: _persona(),
        "researcher": _persona("researcher", timeout_s=None),
    }

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, registry)

    message = str(excinfo.value)
    assert "us1" in message
    assert "timeout" in message


# T005 [P] [US1] (spec US1-S5) -----------------------------------------------


@pytest.mark.parametrize(
    "declaration",
    [
        "US1:\n  depends_on: []\n  implements: []\n",
        "US1:\n  depends_on: []\n  implements: []\n  timeout: 3600\n",
        "US1:\n  depends_on: []\n  implements: []\n  persona: debugger\n",
        (
            "US1:\n  depends_on: []\n  implements: []\n"
            "  timeout: 3600\n  persona: debugger\n"
        ),
    ],
    ids=["neither", "timeout-only", "persona-only", "both"],
)
def test_persona_is_optional_the_same_way_timeout_is(declaration: str) -> None:
    """Blocks with neither key, one key, or both all derive cleanly."""
    graph = _derive(declaration)

    assert len(graph.nodes) == 1
    assert graph.nodes[0].id == "us1"


# T006 [P] [US1] (spec US1-S6) -----------------------------------------------


def test_pinned_persona_is_snapshotted_at_epic_start() -> None:
    """The persona registry is snapshotted at start; a mid-epic edit does not
    change the running node.

    `validate_workgraph` takes the registry as an argument and `resolve_graph`
    resolves each node against that snapshot (`models.py:199`). Validation with a
    registry that lacks the pinned persona succeeds against the snapshot that
    contained it and fails against a different one.
    """
    graph = _derive("US1:\n  depends_on: []\n  implements: []\n  persona: closer\n")
    registry_with_closer = {
        IMPLEMENTER: _persona(),
        "closer": _persona("closer"),
    }

    # The snapshot taken at epic start resolves the pinned persona.
    validate_workgraph(graph, registry_with_closer)

    # A mid-epic edit that removes `closer` would break the *next* epic, not this one.
    registry_without_closer = {IMPLEMENTER: _persona()}
    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, registry_without_closer)

    assert "us1" in str(excinfo.value)
    assert "closer" in str(excinfo.value)


# T048 [P] [US1] (spec US1-S7, trap 16) --------------------------------------


def test_adding_persona_to_landed_story_does_not_reopen_it() -> None:
    """`persona:` is excluded from the declaration fingerprint component.

    Adding a `persona:` key to a story that has already landed changes the raw
    declaration YAML text, which is a fingerprint component today. The default
    behaviour would reopen the story, branching from a base that already contains
    its work and burning the ladder on an unjudgeable diff.

    We choose to treat persona as routing/metaconfig: it is not part of what the
    story means, so it must not reopen a landed node.
    """
    base_graph = (
        "US1:\n  depends_on: []\n  implements: []\n"
        "US2:\n  depends_on: []\n  implements: []\n"
    )
    base_text = _spec_text(base_graph, stories=2)
    pinned_graph = (
        "US1:\n  depends_on: []\n  implements: []\n  persona: closer\n"
        "US2:\n  depends_on: []\n  implements: []\n"
    )
    pinned_text = _spec_text(pinned_graph, stories=2)

    fp_base = fingerprint_for_text(base_text, "US1")
    fp_pinned = fingerprint_for_text(pinned_text, "US1")

    assert fp_base.digest == fp_pinned.digest


# Helpers -------------------------------------------------------------------


def fingerprint_for_text(spec_text: str, story_key: str) -> Fingerprint:
    """Compute the structural fingerprint for a story directly from text.

    Mirrors `factory.workgraph.landed.fingerprint` without shelling to git.
    """
    from factory.workgraph.landed import _story_parts, _structural_digest

    scenarios, fr_bodies, declaration = _story_parts(spec_text, story_key)
    digest = _structural_digest(
        {
            "story_key": story_key,
            "scenarios": scenarios,
            "fr_bodies": fr_bodies,
            "declaration": declaration,
        }
    )
    return Fingerprint(story_key=story_key, revision="current", digest=digest)
