"""The `promote` scaffold: pure findings-in/text-out.

Written before `factory/doctor/scaffold.py` exists (T015 precedes T018): until
the module lands, tests here fail at import.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.doctor.models import Finding, Severity, Status
from factory.verify.criteria import parse_spec
from factory.verify.models import RequirementKind
from factory.workgraph.derive import DerivationError, derive_workgraph


@pytest.fixture
def sample_findings() -> list[Finding]:
    return [
        Finding(
            key="interpreter/fire-and-forget-node-tasks",
            category="interpreter",
            severity=Severity.CRITICAL,
            status=Status.OPEN,
            summary="Node coroutines are dispatched fire-and-forget.",
            refs=["factory/workgraph/workflow.py:647-652"],
            notes="B1. Cheap partial belongs to the bugfix epic.",
            source="audit-2026-08-07",
            occurrences=1,
            first_seen="",
            last_seen="",
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        ),
        Finding(
            key="temporal/node-child-workflows",
            category="temporal",
            severity=Severity.WARNING,
            status=Status.OPEN,
            summary="Every node attempt runs inside one EpicWorkflow history.",
            refs=["factory/workgraph/workflow.py"],
            notes="T1 -> node-child-workflows epic.",
            source="audit-2026-08-07",
            occurrences=2,
            first_seen="",
            last_seen="",
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        ),
    ]


def test_scaffold_frontmatter_is_draft(sample_findings: list[Finding]) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups",
        findings=sample_findings,
        specs_root="specs",
        target_repo=".",
    )
    assert spec_text.startswith("---\n")
    assert "state: draft" in spec_text.split("---\n")[1]


def test_scaffold_has_one_story_per_finding(sample_findings: list[Finding]) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups", findings=sample_findings, specs_root="specs", target_repo="."
    )
    assert "### User Story 1 - Node coroutines are dispatched fire-and-forget. (Priority: P2)" in spec_text
    assert "### User Story 2 - Every node attempt runs inside one EpicWorkflow history. (Priority: P2)" in spec_text


def test_scaffold_folds_evidence_verbatim(sample_findings: list[Finding]) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups", findings=sample_findings, specs_root="specs", target_repo="."
    )
    assert "Node coroutines are dispatched fire-and-forget." in spec_text
    assert "factory/workgraph/workflow.py:647-652" in spec_text
    assert "B1. Cheap partial belongs to the bugfix epic." in spec_text
    assert "Every node attempt runs inside one EpicWorkflow history." in spec_text
    assert "T1 -> node-child-workflows epic." in spec_text


def test_scaffold_has_scenario_stubs_matching_criteria_parser(
    sample_findings: list[Finding],
) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups", findings=sample_findings, specs_root="specs", target_repo="."
    )
    # Every story must declare acceptance scenarios and each item must carry
    # bold Given/When/Then segments (factory.verify.criteria._STEP_RE).
    requirements = parse_spec(spec_text)
    stories = [r for r in requirements if r.kind is RequirementKind.STORY]
    assert len(stories) == 2
    for story in stories:
        assert story.scenarios, f"{story.key} has no scenarios"
        for scenario in story.scenarios:
            assert scenario.steps
            assert any(step.startswith("**Given") for step in scenario.steps)
            assert any(step.startswith("**When") for step in scenario.steps)
            assert any(step.startswith("**Then") for step in scenario.steps)


def test_scaffold_has_one_fr_bullet_per_finding_with_obligation(
    sample_findings: list[Finding],
) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups", findings=sample_findings, specs_root="specs", target_repo="."
    )
    assert "- **FR-001**: The factory MUST" in spec_text
    assert "- **FR-002**: The factory MUST" in spec_text
    requirements = parse_spec(spec_text)
    frs = [r for r in requirements if r.kind is RequirementKind.FUNCTIONAL]
    assert len(frs) == 2
    for fr in frs:
        assert "MUST" in fr.body or "SHALL" in fr.body


def test_scaffold_has_work_graph_covering_every_story(
    sample_findings: list[Finding],
) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups", findings=sample_findings, specs_root="specs", target_repo="."
    )
    assert "## Work Graph" in spec_text
    assert "US1:" in spec_text
    assert "US2:" in spec_text


def test_scaffold_compiles_with_zero_rejections(
    sample_findings: list[Finding],
) -> None:
    from factory.doctor.scaffold import scaffold_spec

    spec_text, _plan, _tasks = scaffold_spec(
        slug="audit-fixups", findings=sample_findings, specs_root="specs", target_repo="."
    )
    graph = derive_workgraph(
        spec_text,
        epic_id="audit-fixups",
        feature="audit-fixups",
        specs_root="specs",
        target_repo=".",
    )
    assert graph.epic_id == "audit-fixups"
    assert len(graph.nodes) == 2
    assert {n.story_key for n in graph.nodes} == {"US1", "US2"}


def test_scaffold_rejects_zero_findings() -> None:
    from factory.doctor.scaffold import scaffold_spec

    with pytest.raises(ValueError):
        scaffold_spec(slug="empty", findings=[], specs_root="specs", target_repo=".")
