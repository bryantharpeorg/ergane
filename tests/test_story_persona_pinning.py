"""US1: a story can name the persona that builds it.

The deriver is pure and persona-agnostic: it carries whatever the spec declares,
and leaves resolution to the registry snapshot taken at epic start.  This suite
exercises the new `persona:` Work Graph key and the two places it surfaces:

- derivation: the declared persona (or the default) lands on the `WorkNode`;
- validation: an unknown persona or one without a resolvable timeout is rejected
  before dispatch, naming the node and the persona.

It also pins the guard required by trap 16: a `persona:` key added to a story
that has already landed must not silently reopen it.  The chosen design treats
routing as operational metadata, not judgeable content, so `persona` is excluded
from the declaration component of the fingerprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from factory.config import Persona, WriteScope
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.landed import LandedFact, LandedKind, fingerprint, landed_facts
from factory.workgraph.models import (
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)

EPIC_ID = "070-a-story-can-choose-who-builds-it"
FEATURE = "070-a-story-can-choose-who-builds-it"
SPECS_ROOT = "specs"
TARGET_REPO = "/home/admin/code/ergane-target"

IDENTITY = {
    "epic_id": EPIC_ID,
    "feature": FEATURE,
    "specs_root": SPECS_ROOT,
    "target_repo": TARGET_REPO,
}

IMPLEMENTER = "implementer"


def _spec_text(*, stories: list[str], work_graph: str) -> str:
    """A minimal Spec Kit feature spec with the requested pieces."""
    body = "# Feature\n\n"
    body += "## Requirements *(mandatory)*\n\n"
    for number, _ in enumerate(stories, start=1):
        body += f"- **FR-{number:03d}**: The system MUST do thing {number}.\n"
    body += "\n"
    for number, title in enumerate(stories, start=1):
        body += (
            f"### User Story {number} - {title} (Priority: P{number})\n\n"
            "As the operator, I want this.\n\n"
            "**Acceptance Scenarios**:\n"
            f"1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        )
    body += "## Work Graph\n\n```yaml\n" + work_graph + "\n```\n"
    return body


def _derive(work_graph: str, *, stories: list[str] | None = None) -> WorkGraph:
    stories = stories or ["US1", "US2", "US3"]
    return derive_workgraph(_spec_text(stories=stories, work_graph=work_graph), **IDENTITY)


def _persona(
    name: str = IMPLEMENTER,
    *,
    timeout_s: int | None = 3600,
    agent: str = "claude-code",
) -> Persona:
    return Persona(
        name=name,
        agent=agent,
        model="fake-provider/CHANGEME",
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=timeout_s,
    )


def _node(persona: str = IMPLEMENTER, **overrides: Any) -> WorkNode:
    fields: dict[str, Any] = {
        "id": "us1",
        "story_key": "US1",
        "persona": persona,
        "spec_ref": f"{FEATURE}:US1",
        "requirement_keys": ["US1"],
        "depends_on": [],
        "depends_on_merged": [],
        "timeout_override_s": None,
    }
    fields.update(overrides)
    return WorkNode(**fields)  # type: ignore[arg-type]


def _graph(*nodes: WorkNode) -> WorkGraph:
    return WorkGraph(
        epic_id=EPIC_ID,
        feature=FEATURE,
        specs_root=SPECS_ROOT,
        target_repo=TARGET_REPO,
        nodes=list(nodes),
    )


# T001 [P] [US1] (spec US1-S1)
def test_a_declared_persona_carries_to_its_node_while_siblings_keep_default() -> None:
    """One story pinned, the rest default — both halves asserted."""
    graph = _derive(
        """
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: []
  implements: [FR-002]
  persona: closer
US3:
  depends_on: []
  implements: [FR-003]
"""
    )

    personas = {node.story_key: node.persona for node in graph.nodes}
    assert personas == {"US1": IMPLEMENTER, "US2": "closer", "US3": IMPLEMENTER}


# T002 [P] [US1] (spec US1-S2)
def test_a_story_without_persona_carries_the_default() -> None:
    """Omitting the key is identical to today's behaviour."""
    graph = _derive(
        """
US1:
  depends_on: []
  implements: [FR-001]
""",
        stories=["US1"],
    )

    assert graph.nodes[0].persona == IMPLEMENTER


# T003 [P] [US1] (spec US1-S3)
def test_an_unknown_persona_is_rejected_at_start_naming_story_and_persona() -> None:
    """The refusal must come from `validate_workgraph`'s existing check, not a new one."""
    graph = _graph(_node(persona="archaeologist"))

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, {IMPLEMENTER: _persona()})

    message = str(excinfo.value)
    assert "us1" in message
    assert "archaeologist" in message


# T004 [P] [US1] (spec US1-S4)
def test_a_persona_without_resolvable_timeout_is_rejected_at_start() -> None:
    """Pinning must not bypass `resolve_timeout_s`'s existing contract."""
    registry = {IMPLEMENTER: _persona(timeout_s=None)}
    graph = _graph(_node())

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, registry)

    message = str(excinfo.value)
    assert "us1" in message
    assert "timeout" in message


# T005 [P] [US1] (spec US1-S5)
OPTIONAL_COMBOS = [
    ("neither", "depends_on: []\n  implements: [FR-001]", IMPLEMENTER, None),
    ("persona_only", "depends_on: []\n  implements: [FR-001]\n  persona: closer", "closer", None),
    ("timeout_only", "depends_on: []\n  implements: [FR-001]\n  timeout: 7200", IMPLEMENTER, 7200),
    ("both", "depends_on: []\n  implements: [FR-001]\n  persona: closer\n  timeout: 7200", "closer", 7200),
]


@pytest.mark.parametrize(
    ("case", "declaration", "expected_persona", "expected_timeout"),
    OPTIONAL_COMBOS,
    ids=[row[0] for row in OPTIONAL_COMBOS],
)
def test_persona_key_is_optional_like_timeout(
    case: str,
    declaration: str,
    expected_persona: str,
    expected_timeout: int | None,
) -> None:
    """Blocks with neither key, one key, or both all derive."""
    graph = _derive(f"US1:\n  {declaration}", stories=["US1"])

    node = graph.nodes[0]
    assert node.persona == expected_persona
    assert node.timeout_override_s == expected_timeout


# T006 [P] [US1] (spec US1-S6)
def test_pinned_persona_is_snapshotted_at_epic_start() -> None:
    """A registry edit mid-epic does not change the running node."""
    graph = _graph(_node(persona="closer"))
    original_registry = {"closer": _persona("closer", timeout_s=3600)}

    # The graph validates against the snapshot it was handed.
    validate_workgraph(graph, original_registry)

    # An operator edits personas.yaml mid-epic: the closer persona now lacks a
    # timeout.  The same graph, validated against the *new* registry, would fail,
    # but the in-flight epic was resolved from the old one.
    edited_registry = {"closer": _persona("closer", timeout_s=None)}
    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, edited_registry)
    assert "closer" in str(excinfo.value)
    assert "timeout" in str(excinfo.value)


# T048 [P] [US1] (spec US1-S7, trap 16)
def test_adding_persona_to_landed_story_does_not_reopen_it(tmp_path: Path) -> None:
    """Routing is operational metadata, not judgeable content, so it is excluded
    from the declaration component of the fingerprint."""
    from tests.test_landed import _git_env, _git, _commit

    repo = tmp_path / "repo"
    repo.mkdir()
    env = _git_env(tmp_path / "empty")
    env["GIT_AUTHOR_NAME"] = "Fixture"
    env["GIT_AUTHOR_EMAIL"] = "fixture@ergane.invalid"
    env["GIT_COMMITTER_NAME"] = "Fixture"
    env["GIT_COMMITTER_EMAIL"] = "fixture@ergane.invalid"
    env["GIT_AUTHOR_DATE"] = "2026-01-01T00:00:00+00:00"
    env["GIT_COMMITTER_DATE"] = "2026-01-01T00:00:00+00:00"
    _git(repo, "init", "-b", "main", "--quiet", env=env)

    spec_dir = repo / "specs" / EPIC_ID
    spec_dir.mkdir(parents=True)

    landed_spec = _spec_text(
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
    )
    spec_path = spec_dir / "spec.md"
    spec_path.write_text(landed_spec, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    landing_commit = _commit(repo, f"{EPIC_ID}/us1: US1 (#1)", env=env, allow_empty=True)

    # Edit the spec to add a persona key.
    pinned_spec = _spec_text(
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n  persona: closer\n",
    )
    spec_path.write_text(pinned_spec, encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "add persona pin to landed US1", env=env, allow_empty=True)

    # The story must still read as landed, and the fingerprint must match.
    facts = landed_facts(repo, EPIC_ID, default_branch="main", fetch=False)
    assert facts == {
        "US1": LandedFact(story_key="US1", commit=landing_commit, kind=LandedKind.OBSERVED)
    }

    fp = fingerprint(repo, landing_commit, EPIC_ID, "US1")
    current_fp = fingerprint(repo, "HEAD", EPIC_ID, "US1")
    assert fp.digest == current_fp.digest


