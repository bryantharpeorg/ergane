"""US3 of epic 062-the-registry-belongs-to-the-operator: skills are reserved.

The `skills` field on a persona is parsed and validated, but nothing ever
reads it. This story documents that reservation so an operator does not plan
around configuration that has no effect, and locks the reservation with tests
that fail the moment anyone wires `skills` into the adapter invocation without
also updating the documentation and the regression guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.cli.nouns import build as build_cli
from factory.config import Persona, WriteScope, load_personas
from factory.spec import layers
from factory.workgraph import cli as workgraph_cli
from factory.workgraph.models import WorkGraph, WorkNode

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"

# --- T021 [P] [US3] (spec US3-S1) ---------------------------------------------


def test_skills_field_is_documented_as_reserved_and_construction_sites_are_explained() -> None:
    """US3-S1 / FR-009: `skills` is parsed but not read.

    The registry header must say so, the `Persona` docstring must say so, and
    every construction site that passes `skills=()` must explain why rather than
    leaving the dead value looking accidental.
    """
    header = SHIPPED_REGISTRY.read_text(encoding="utf-8")
    assert "skills" in header, "registry header does not mention skills at all"
    assert "reserved" in header.lower(), "registry header does not state skills is reserved"
    assert "not used" in header.lower() or "unused" in header.lower(), (
        "registry header does not say skills is unused"
    )

    assert "reserved" in Persona.__doc__.lower(), "Persona docstring must say skills is reserved"
    assert (
        "not used" in Persona.__doc__.lower() or "unused" in Persona.__doc__.lower()
    ), "Persona docstring must say skills is unused"

    # The three construction sites must explain the empty tuple rather than
    # passing it silently. The spec noun's registry builder is `_vacuous_registry`,
    # which 133-US5 relocated to `factory/spec/layers.py` with the layer bodies
    # it serves — the construction site is asserted there rather than in the CLI
    # module it left.
    for module in (workgraph_cli, build_cli):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "skills=()" in source, f"{module.__name__} no longer constructs personas with skills=()"
        assert "reserved" in source.lower(), (
            f"{module.__name__} does not explain why skills=() is passed"
        )

    layers_source = Path(layers.__file__).read_text(encoding="utf-8")
    assert "skills=()" in layers_source, f"{layers.__name__} no longer constructs personas with skills=()"
    assert "reserved" in layers_source.lower(), (
        f"{layers.__name__} does not explain why skills=() is passed"
    )


# --- T022 [P] [US3] (spec US3-S2) ---------------------------------------------


def test_registry_documentation_states_visible_skill_scopes() -> None:
    """US3-S2 / FR-010: the registry header states which skill scopes a node can see.

    Home-scoped skills are invisible because the adapter constructs a factory-owned
    per-node HOME (`factory/workgraph/adapter.py:339`). Project-scoped skills
    committed at `<repo>/.claude/skills/` are visible because worktrees carry
    committed files into the node worktree.
    """
    header = SHIPPED_REGISTRY.read_text(encoding="utf-8")

    # Home-scoped skills are invisible because the node's HOME is factory-owned.
    assert "factory-owned" in header.lower() or "factory owned" in header.lower(), (
        "registry header does not describe the per-node HOME as factory-owned"
    )
    assert "HOME" in header, "registry header does not mention HOME"
    assert ".claude" in header, "registry header does not mention .claude/skills"

    # Project-scoped committed skills are visible because worktrees carry files.
    assert "worktree" in header.lower(), "registry header does not mention worktrees"
    assert "committed" in header.lower(), "registry header does not mention committed files"


# --- T023 [P] [US3] (spec US3-S3) ---------------------------------------------


def test_skills_regression_guard_is_active() -> None:
    """US3-S3: if someone wires skills into the adapter, this test fails.

    The guard must match the chosen resolution. Because this story resolves to
    "reserved and unused", the guard asserts that `Persona.skills` is never
    consumed to build an `AgentInvocation` argv or environment. A future story
    that chooses to wire skills must replace this assertion with one proving
    the wiring reaches the invocation.
    """
    adapter_source = Path(__file__).resolve().parents[1] / "factory" / "workgraph" / "adapter.py"
    source = adapter_source.read_text(encoding="utf-8")

    # The adapter must not read `.skills` to construct argv or env. If it does,
    # this story's "reserved" resolution has silently reverted. 154-US4: argv
    # construction is the per-CLI surface (`_argv`, private), so the guard
    # anchors there and in the shared policy's `run_attempt`.
    assert ".skills" not in source, (
        "adapter.py reads Persona.skills; reserved resolution has reverted"
    )
    assert "skills" not in source.split("def _argv")[1].split("def ")[0], (
        "adapter argv construction references skills"
    )
    assert "skills" not in source.split("async def run_attempt")[1].split("def ")[0], (
        "shared-policy attempt assembly references skills"
    )
    assert "skills" not in source.split("def attempt_env")[1].split("def ")[0], (
        "adapter env construction references skills"
    )


# --- helper: construction sites continue to build valid structural personas ---


def test_vacuous_personas_remain_structurally_valid() -> None:
    """The reservation does not break the structural registries: a persona with
    empty skills still validates as a WorkGraph placeholder."""
    graph = WorkGraph(
        epic_id="e",
        feature="e",
        specs_root="",
        target_repo="",
        nodes=[
            WorkNode(
                id="us1",
                story_key="US1",
                persona="placeholder",
                spec_ref="e:US1",
                requirement_keys=["US1"],
                depends_on=[],
                depends_on_merged=[],
                timeout_override_s=None,
            )
        ],
    )
    registry = workgraph_cli._persona_registry(graph)
    assert registry["placeholder"].skills == ()
    assert registry["placeholder"].write_scope is WriteScope.WORKTREE

    registry_build = build_cli._persona_registry(graph)
    assert registry_build["placeholder"].skills == ()

    registry_spec = layers._vacuous_registry(graph)
    assert registry_spec["placeholder"].skills == ()
