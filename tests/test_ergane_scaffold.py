"""US1: the scaffold generator emits a trio that validates.

Every assertion parses the returned text rather than diffing a golden file.
The generator is pure text in, text out; the directory and the validator are
the test's responsibility, not the generator's.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main
from factory.doctor.scaffold import ERGANE_TODO, scan_sentinels, scaffold_spec
from factory.verify.criteria import parse_spec
from factory.verify.models import RequirementKind
from factory.workgraph.contention import named_files
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.prompt import task_slice_bounds

SLUG = "demo-feature"
TITLE = "A demonstrative feature"
ANCHOR = "factory/cli/main.py:171"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        import json

        return json.loads(self.stdout)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def trio() -> tuple[str, str, str]:
    return scaffold_spec(slug=SLUG, title=TITLE, anchor=ANCHOR)


def _write_trio(tmp_path: Path, spec_md: str, plan_md: str, tasks_md: str) -> Path:
    spec_dir = tmp_path / "106-demo-feature"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(spec_md, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan_md, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks_md, encoding="utf-8")
    return spec_dir


# --- T001: validator passes over the generated trio --------------------------


def test_generated_trio_validates_cleanly(run: Callable[..., Run], trio: tuple[str, str, str], tmp_path: Path) -> None:
    """Write the returned texts into a tmp_path directory and drive the real
    `ergane spec validate --json` over it; assert exit 0 and empty findings."""
    spec_dir = _write_trio(tmp_path, *trio)

    result = run("spec", "validate", "--json", str(spec_dir))

    assert result.code == 0
    assert result.json["findings"] == []


# --- T002: structure of spec.md ----------------------------------------------


def test_spec_has_three_story_slots(trio: tuple[str, str, str]) -> None:
    spec_md = trio[0]
    headings = re.findall(r"^### User Story \d+ - .+ \(Priority: P\d+\)$", spec_md, re.MULTILINE)
    assert len(headings) == 3
    assert all(re.match(r"^### User Story \d+ - .+ \(Priority: P\d+\)$", h) for h in headings)


def test_spec_has_literal_acceptance_scenarios(trio: tuple[str, str, str]) -> None:
    spec_md = trio[0]
    assert "**Acceptance Scenarios**:" in spec_md
    requirements = parse_spec(spec_md)
    stories = [r for r in requirements if r.kind is RequirementKind.STORY]
    assert len(stories) == 3
    for story in stories:
        assert story.scenarios, f"{story.key} has no scenarios"
        for scenario in story.scenarios:
            assert any("Given" in step for step in scenario.steps)
            assert any("When" in step for step in scenario.steps)
            assert any("Then" in step for step in scenario.steps)


def test_spec_frontmatter_is_draft_and_nothing_else(trio: tuple[str, str, str]) -> None:
    spec_md = trio[0]
    assert spec_md.startswith("---\n")
    parts = spec_md.split("---\n", 2)
    frontmatter = parts[1]
    assert frontmatter.strip() == "state: draft"


def test_work_graph_has_implements_on_every_node(trio: tuple[str, str, str]) -> None:
    spec_md = trio[0]
    fence_match = re.search(r"```yaml\n(.*?)\n```", spec_md, re.DOTALL)
    assert fence_match is not None
    fence = fence_match.group(1)
    for line in fence.splitlines():
        if re.match(r"^US\d+:$", line.strip()):
            # Each node block must contain an `implements:` line.
            block = fence[fence.index(line) :]
            block = block.split("\nUS", 1)[0]
            assert "implements:" in block


# --- T003: sentinel placement -------------------------------------------------


def test_sentinels_only_in_mandatory_blanks(trio: tuple[str, str, str]) -> None:
    spec_md, plan_md, tasks_md = trio
    all_sentinel_lines: list[tuple[str, int, str]] = []
    for doc_name, text in (("spec.md", spec_md), ("plan.md", plan_md), ("tasks.md", tasks_md)):
        all_sentinel_lines.extend((doc_name, line_no, line) for line_no, line in scan_sentinels(text))

    # There must be at least one sentinel in the trio.
    assert all_sentinel_lines

    for doc_name, _line_no, line in all_sentinel_lines:
        # No sentinel inside a story heading.
        assert not re.match(r"^### User Story \d+ - ", line), f"sentinel in story heading: {line}"
        # No sentinel inside the Work Graph fence (it is delimited by ```yaml ... ```).
        assert "```" not in line, f"sentinel on fence line: {line}"
        # No sentinel in a task-id prefix (task lines start with '- [ ] T...').
        assert not re.match(r"^\s*-\s+\[\s*\]\s+T\d+", line), f"sentinel in task-id line: {line}"


# --- T004: slice self-proof and scenario coverage -----------------------------


def test_every_node_has_task_slice_bounds_and_scenarios_referenced(trio: tuple[str, str, str]) -> None:
    spec_md, _plan_md, tasks_md = trio
    graph = derive_workgraph(
        spec_md,
        epic_id=SLUG,
        feature=SLUG,
        specs_root="specs",
        target_repo=".",
        tasks_text=tasks_md,
    )

    requirements = parse_spec(spec_md)
    scenario_ids = {
        scenario.scenario_id
        for requirement in requirements
        for scenario in getattr(requirement, "scenarios", ())
        if scenario.scenario_id is not None
    }
    referenced = set(re.findall(r"US\d+-S\d+", tasks_md))
    assert scenario_ids <= referenced, f"uncovered scenarios: {scenario_ids - referenced}"

    for node in graph.nodes:
        start, end = task_slice_bounds(node, tasks_md)
        assert 0 <= start < end <= len(tasks_md.splitlines())


# --- T005: no self-contention -------------------------------------------------


def test_only_worked_story_slice_names_files(trio: tuple[str, str, str]) -> None:
    _spec_md, _plan_md, tasks_md = trio
    graph = derive_workgraph(
        trio[0],
        epic_id=SLUG,
        feature=SLUG,
        specs_root="specs",
        target_repo=".",
        tasks_text=tasks_md,
    )

    by_node: dict[str, frozenset[str]] = {}
    for node in graph.nodes:
        start, end = task_slice_bounds(node, tasks_md)
        slice_text = "\n".join(tasks_md.splitlines()[start:end])
        by_node[node.id] = named_files(slice_text)

    # Exactly one node names files, and the others name none.
    non_empty = {node_id for node_id, files in by_node.items() if files}
    assert len(non_empty) == 1, f"expected one non-empty slice, got {non_empty}"


# --- T006: demonstration mode --------------------------------------------------


def test_demonstration_mode_returns_worked_story_alone_with_no_sentinel() -> None:
    spec_md, plan_md, tasks_md = scaffold_spec(slug=SLUG, title=TITLE, anchor=ANCHOR, demonstration=True)

    headings = re.findall(r"^### User Story \d+ - .+ \(Priority: P\d+\)$", spec_md, re.MULTILINE)
    assert len(headings) == 1

    for text in (spec_md, plan_md, tasks_md):
        assert scan_sentinels(text) == []

    graph = derive_workgraph(
        spec_md,
        epic_id=SLUG,
        feature=SLUG,
        specs_root="specs",
        target_repo=".",
        tasks_text=tasks_md,
    )
    assert len(graph.nodes) == 1
