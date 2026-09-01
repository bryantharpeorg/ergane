"""044 US1: `ergane spec validate` assembles every node's prompt, offline.

The incident this story exists for, in full. On the morning of 2026-08-15 the
roadmap dispatched a four-node epic and one tick later every node was dead,
killed before any agent ran:

    node 'us1': tasks.md declares no phase naming user story US1, so this node
    has no task slice to work (FR-006)

The grammar that refusal enforces ran in exactly one place — `build_attempt_prompt`,
called from the epic workflow at dispatch — so dispatch was the first moment a
spec author could learn their `tasks.md` did not parse, and the price of the
lesson was an epic. These tests pin the same refusal to `ergane spec validate`,
where it costs one command.

Two properties are asserted throughout and are worth naming up front:

- **The finding names the node, the story and the document.** An operator who is
  told "assembly failed" has to go find which of four nodes and which of three
  documents; the whole value of moving the check earlier is lost if the message
  is vaguer than the one dispatch already gave.

- **There is exactly one copy of the heading grammar** (FR-004). The layer calls
  the assembler the dispatch path calls. A second regex here would be a check
  that agrees with dispatch until the day it does not, which is worse than no
  check at all — `test_the_layer_carries_no_second_copy_of_the_story_grammar`
  is what holds that.

Red first. `uv run pytest tests/test_prompt_assembly.py -q --no-header`, run
against the tree with these fixtures committed and no layer written, verbatim::

    FAILED tests/test_prompt_assembly.py::test_validate_names_every_node_the_story_and_tasks_md_for_the_heading_defect
    FAILED tests/test_prompt_assembly.py::test_the_heading_defect_is_named_on_stderr_without_json
    FAILED tests/test_prompt_assembly.py::test_a_node_whose_story_the_spec_does_not_declare_is_named_with_spec_md
    FAILED tests/test_prompt_assembly.py::test_a_well_formed_trio_reports_prompt_assembly_checked_and_no_finding
    FAILED tests/test_prompt_assembly.py::test_prompt_assembly_is_reported_skipped_when_there_is_no_graph_to_check
    FAILED tests/test_prompt_assembly.py::test_a_missing_document_is_reported_as_a_finding_naming_its_path[plan.md]
    FAILED tests/test_prompt_assembly.py::test_a_missing_document_is_reported_as_a_finding_naming_its_path[tasks.md]
    FAILED tests/test_prompt_assembly.py::test_the_layer_carries_no_second_copy_of_the_story_grammar
    FAILED tests/test_prompt_assembly.py::test_the_assembly_check_opens_no_socket
    9 failed, 2 passed in 0.17s

The two that passed red are the control (SC-004), and they had to: they run
*only* the four pre-existing layers, and the claim this story rests on is that
those four see nothing wrong with either fixture. A control that failed red
would mean the fixtures were already being caught by a check that existed.

Green after, same command::

    11 passed in 0.14s

And the whole suite, `uv run pytest -q`::

    2389 passed, 44 skipped, 4 warnings in 262.16s (0:04:22)

Run the thing, not the tests about it. `uv run python -m factory.cli.main spec
validate tests/fixtures/prompt_assembly/901-heading-defect`, verbatim::

    ergane spec validate: [prompt_assembly] tasks.md: node 'us1': tasks.md declares no phase naming user story US1, so this node has no task slice to work (FR-006)
    ergane spec validate: [prompt_assembly] tasks.md: node 'us2': tasks.md declares no phase naming user story US2, so this node has no task slice to work (FR-006)
    ergane spec validate: [prompt_assembly] tasks.md: node 'us3': tasks.md declares no phase naming user story US3, so this node has no task slice to work (FR-006)
    ergane spec validate: [prompt_assembly] tasks.md: node 'us4': tasks.md declares no phase naming user story US4, so this node has no task slice to work (FR-006)
    exit=1

...and on the control trio::

    tests/fixtures/prompt_assembly/903-well-formed/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage and prompt assembly all pass
    exit=0

The layer was then run across every trio under `specs/` in this tree. It is not
theatre: two live specs are already carrying the defect, neither of them
dispatched yet, and neither reported by any other layer::

    === specs/017-peer-channel/ (exit 1)
    ergane spec validate: [prompt_assembly] tasks.md: node 'us5': tasks.md declares no phase naming user story US5, so this node has no task slice to work (FR-006)
    === specs/022-validate-calibration/ (exit 1)
    ergane spec validate: [prompt_assembly] tasks.md: node 'us1': tasks.md declares no phase naming user story US1, so this node has no task slice to work (FR-006)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main
from factory.cli.nouns import build as build_noun, spec as spec_noun
from factory.doctor.scaffold import ERGANE_TODO, scan_sentinels
from factory.workgraph import preflight
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.models import WorkGraph, WorkNode

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prompt_assembly"

#: This repository, whose committed manifest declares the gates 102-US1's
#: `evidence` layer reads. Tests that assert on the *whole* `checked` or
#: `skipped` list name it, so that list is decided by a declaration rather than
#: by whether the host happens to carry validate's default target repo.
REPO_ROOT = Path(__file__).resolve().parent.parent

HEADING_DEFECT = FIXTURES / "901-heading-defect"
STALE_GRAPH = FIXTURES / "902-stale-graph"
WELL_FORMED = FIXTURES / "903-well-formed"

TARGET_REPO = "/srv/factory/targets/short-links"

#: The four pre-existing validate layers, in the order `_validate_command` runs
#: them. Named here so the control (SC-004) can run *only* those layers.
EXISTING_LAYERS = (
    "frontmatter",
    "workgraph_derivation",
    "persona_registry",
    "scenario_coverage",
)


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    @property
    def messages(self) -> str:
        return " ".join(finding["message"] for finding in self.json["findings"])

    @property
    def layers(self) -> list[str]:
        return [finding["layer"] for finding in self.json["findings"]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """`ergane` through its real entry point — no crash is swallowed here.

    Only `SystemExit` is caught, so a layer that raises instead of reporting
    (US1 scenario 4's whole point) fails the test with its traceback rather
    than being read as a finding.
    """

    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _copy_trio(source: Path, destination: Path) -> Path:
    """A fixture trio in a scratch directory, so a document can be removed."""
    shutil.copytree(source, destination)
    return destination


# --- T001 / US1-S1: the 2026-08-15 kill, caught offline -----------------------


def test_validate_names_every_node_the_story_and_tasks_md_for_the_heading_defect(
    run: Callable[..., Run],
) -> None:
    """The reconstructed incident: four nodes, four refusals, one document.

    `901-heading-defect/tasks.md` names each story's title and never its key,
    which is exactly what the dispatched spec did. The layer must reproduce the
    refusal dispatch produced — verbatim, including the FR-006 citation — for
    every node, and it must exit non-zero so a scripted refinement pass stops.
    """
    result = run("spec", "validate", "--json", str(HEADING_DEFECT))

    assert result.code == 1
    assert result.layers == ["prompt_assembly"] * 4

    # The refusal the dispatch tick produced, byte for byte.
    assert (
        "node 'us1': tasks.md declares no phase naming user story US1, so this "
        "node has no task slice to work (FR-006)"
    ) in result.messages

    for node_id, story_key in (
        ("us1", "US1"),
        ("us2", "US2"),
        ("us3", "US3"),
        ("us4", "US4"),
    ):
        assert f"node '{node_id}'" in result.messages
        assert f"user story {story_key}" in result.messages
    assert result.messages.count("tasks.md") >= 4


def test_the_heading_defect_is_named_on_stderr_without_json(
    run: Callable[..., Run],
) -> None:
    """The human path says the same thing: layer, node, story, document."""
    result = run("spec", "validate", str(HEADING_DEFECT))

    assert result.code == 1
    assert "[prompt_assembly]" in result.stderr
    assert "node 'us1'" in result.stderr
    assert "tasks.md" in result.stderr


# --- T002 / US1-S2: the spec.md half of assembly ------------------------------


def test_a_node_whose_story_the_spec_does_not_declare_is_named_with_spec_md() -> None:
    """A compiled graph that outlived its spec: the finding names node and spec.md.

    `902-stale-graph/workgraph.json` is the artifact `ergane build start` loads
    and dispatches; it still carries a `us2` node, and `spec.md` no longer
    declares that story. This is the only way the spec.md half of assembly is
    reachable, and it is worth stating why: the criteria parser's story-heading
    grammar is strictly *narrower* than the assembler's (it anchors the heading
    text, the assembler searches it), so every story a freshly derived graph
    contains necessarily has a findable section. A graph that drifted from the
    spec beside it does not.
    """
    document = json.loads((STALE_GRAPH / "workgraph.json").read_text(encoding="utf-8"))
    document["specs_root"] = str((STALE_GRAPH / document["specs_root"]).resolve())
    # Build the WorkGraph directly so the test still reaches prompt assembly on a
    # relative-path fixture without going through load_workgraph's new absolute-path
    # refusal.  The scenario is about assembly, not about path validation.
    graph = WorkGraph(
        epic_id=document["epic_id"],
        feature=document["feature"],
        specs_root=document["specs_root"],
        target_repo=document["target_repo"],
        nodes=[WorkNode(**node) for node in document["nodes"]],
    )

    findings = preflight.check_prompt_assembly(graph, STALE_GRAPH)
    assert [finding.node_id for finding in findings] == ["us2"]
    assert findings[0].document == "spec.md"
    assert "node 'us2'" in findings[0].detail
    assert "user story US2" in findings[0].detail
    assert "spec.md" in str(findings[0])


# --- T003 / US1-S3: the clean case, and an honest `checked` list ---------------


def test_a_well_formed_trio_reports_prompt_assembly_checked_and_no_finding(
    run: Callable[..., Run],
) -> None:
    result = run("spec", "validate", "--json", "--target-repo", str(REPO_ROOT), str(WELL_FORMED))

    assert result.code == 0
    document = result.json
    assert document["findings"] == []
    # US3 added a sixth layer over the same graph and the same `tasks.md`, and
    # 069-US2 a seventh. The list stays exhaustive — a layer that runs must
    # appear here — so it grows by exactly the layers that now run.
    # 106-US3 adds an eighth layer, `sentinels`, that scans the authored
    # documents for ERGANE-TODO markers and reports them on the `information`
    # channel without changing the exit code.
    # 102-US1 adds a ninth, `evidence`, and with it the `--target-repo` above:
    # that layer reads the gates the target repository declares, so a run
    # against validate's default — a path this host need not carry — would skip
    # it, and whether `skipped` is empty would depend on the machine.
    # 072-US1 adds a tenth, `anchor_resolution`, which opens every cited
    # `path:NN` in the target repository, and 072-US2 an eleventh,
    # `symbol_anchors`, which resolves Python symbol spans against that
    # repository's AST. Both run before `evidence` and in that order.
    assert document["checked"] == [
        *EXISTING_LAYERS,
        "prompt_assembly",
        "slice_coverage",
        "slice_contention",
        "sentinels",
        "anchor_resolution",
        "symbol_anchors",
        "evidence",
    ]
    assert document["skipped"] == []


def test_prompt_assembly_is_reported_skipped_when_there_is_no_graph_to_check(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Trap 5: a layer that could not run says so rather than claiming a pass.

    Derivation failing leaves no graph, and a graph is what assembly is per-node
    over. The report must then omit `prompt_assembly` from `checked` and name it
    as skipped with the reason — a `checked` list that quietly grew a layer
    nobody ran is how a preflight comes to be trusted for something it never did.
    """
    spec_dir = _copy_trio(WELL_FORMED, tmp_path / "904-broken-graph")
    spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    (spec_dir / "spec.md").write_text(
        spec_text.replace("US2:\n  depends_on: [US1]", "US2:\n  depends_on: [US9]"),
        encoding="utf-8",
    )

    result = run("spec", "validate", "--json", "--target-repo", str(REPO_ROOT), str(spec_dir))

    assert result.code == 1
    document = result.json
    assert "prompt_assembly" not in document["checked"]
    # US3's slice-coverage layer is per node over the same graph, so a failed
    # derivation skips it for the same reason and names it the same way — as
    # does 069-US2's contention layer, which has no nodes to compare either.
    assert [entry["layer"] for entry in document["skipped"]] == [
        "prompt_assembly",
        "slice_coverage",
        "slice_contention",
    ]
    assert "US9" in result.messages


# --- T004 / US1-S4: a missing document is a finding, never a traceback --------


@pytest.mark.parametrize("missing", ["plan.md", "tasks.md"])
def test_a_missing_document_is_reported_as_a_finding_naming_its_path(
    run: Callable[..., Run], tmp_path: Path, missing: str
) -> None:
    """Trap 4: validate is a refinement tool, and a stack trace is not a finding.

    `_validate_command` reads only `spec.md` today; assembly needs all three, and
    an uncaught `OSError` on the two it newly opens would turn a clean refusal
    into a crash the operator has to read as one.
    """
    spec_dir = _copy_trio(WELL_FORMED, tmp_path / "905-missing-document")
    (spec_dir / missing).unlink()

    result = run("spec", "validate", "--json", str(spec_dir))

    assert result.code == 1
    assert "prompt_assembly" in result.layers
    assembly = [
        finding
        for finding in result.json["findings"]
        if finding["layer"] == "prompt_assembly"
    ]
    assert len(assembly) == 1
    assert str(spec_dir / missing) in assembly[0]["message"]


# --- T005 / US1-S5: one grammar, in one place (FR-004) ------------------------


def test_the_layer_carries_no_second_copy_of_the_story_grammar() -> None:
    """The layer calls the assembler; it does not re-implement it.

    A second story-heading regex would pass this suite and disagree with
    dispatch the first time either copy is touched — the failure mode FR-004
    exists to make impossible. So: neither module implementing the layer may
    contain the story-heading literal or reach into the assembler's private
    section-scanning helpers, and the shared module must name the public
    assembler the dispatch path calls.
    """
    layer_sources = {
        module.__name__: Path(module.__file__ or "").read_text(encoding="utf-8")
        for module in (preflight, spec_noun)
    }

    for name, source in layer_sources.items():
        assert "User Story" not in source, f"{name} re-states the heading grammar"
        for private in ("_names_story", "_first_section", "_task_slice", "_requirement_sections"):
            assert private not in source, f"{name} reaches into {private}"

    assert "build_attempt_prompt" in layer_sources["factory.workgraph.preflight"]


# --- T006 / SC-004: the control — the four existing layers see nothing --------


@pytest.mark.parametrize("spec_dir", [HEADING_DEFECT, STALE_GRAPH])
def test_the_fixture_defects_pass_all_four_pre_existing_layers(spec_dir: Path) -> None:
    """SC-004: the new layer changed an outcome rather than duplicating one.

    Run *only* the four layers `ergane spec validate` had before this story, in
    the order it runs them, over both fixtures. Every one of them reports
    nothing — which is what makes the `prompt_assembly` findings above evidence
    of a check that did not exist, rather than a fifth spelling of a refusal the
    command already made.
    """
    spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    epic_id = spec_dir.name
    findings: list[spec_noun._ValidateFinding] = []

    spec_noun._check_frontmatter(spec_dir, epic_id, findings)
    graph = derive_workgraph(
        spec_text,
        epic_id=epic_id,
        feature=epic_id,
        specs_root=str(FIXTURES),
        target_repo=TARGET_REPO,
    )
    spec_noun._check_workgraph(graph, findings)
    spec_noun._check_personas(graph, findings)
    spec_noun._check_scenario_coverage(spec_dir, spec_text, findings)

    assert [f"[{finding.layer}] {finding.message}" for finding in findings] == []


# --- FR-002: the layer is pure and offline ------------------------------------


def test_the_assembly_check_opens_no_socket(
    run: Callable[..., Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-002: no proxy call, no Temporal connection, no network.

    Assembly is text in, prompt out; the layer adds two file reads and nothing
    else. `socket.socket` is made to explode so any dialled connection — the
    proxy the alias preflight uses, a Temporal client — fails loudly here rather
    than making a refinement command depend on a running stack.
    """
    import socket

    def exploding_socket(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the prompt-assembly layer must open no socket")

    monkeypatch.setattr(socket, "socket", exploding_socket)

    result = run("spec", "validate", "--json", str(HEADING_DEFECT))

    assert result.code == 1
    assert result.layers == ["prompt_assembly"] * 4
