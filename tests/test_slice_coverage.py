"""044 US3: tasks that reach no agent are named.

US1 moved the assembler's refusal to `ergane spec validate`. This story is about
the half a refusal cannot reach: a `tasks.md` where every slice assembles and
the slices are *wrong*.

Two shapes, both reconstructed as committed trios:

- `904-split-slice` — the 011 near-miss. Tests and Implementation are both
  written at phase level, so each story's slice runs from its Tests heading to
  the next heading of the same depth, which is its own Implementation heading.
  Every node assembles a prompt. Every prompt is missing that story's
  implementation. All five earlier validate layers pass this trio, which is what
  `test_the_split_slice_defect_is_invisible_to_every_earlier_layer` pins.

- `905-wrong-slice` — the worse half. A story was inserted at position two after
  `tasks.md` was numbered, so each phase below the first carries the number of
  the story that used to sit there. Measured against the fixture with the
  assembler itself, before any of this was written::

      us1 (US1) slice heading: ## Phase 2: User Story 1 — A question reaches a peer agent in the same epic
          - [ ] T002 [P] [US1] Write the routing cases FIRST with scripted child
          - [ ] T003 [US1] Implement the addressee grammar and the workflow buff
      us2 (US2) slice heading: ## Phase 3: User Story 2 — A message reaches a named external agent
          - [ ] T004 [P] [US3] Write the registry cases FIRST: `peers.yaml` pars
          - [ ] T005 [US3] Implement the peer registry and the mailbox transport
      us3 (US3) slice heading: ## Phase 4: User Story 3 — A message crosses epics
          - [ ] T006 [P] [US4] Write the cross-epic cases FIRST: an epic-address
          - [ ] T007 [US4] Implement cross-epic routing and complete the namespa
      us4: REFUSED — node 'us4': tasks.md declares no phase naming user story US4, so this node has no task slice to work (FR-006)

  Three of the four nodes assemble, and two of those three are handed the next
  story's task list. Only the last reports anything. A silent wrong answer costs
  a full attempt and says nothing; a refusal costs a command.

The third fixture is the calibration in the other direction. `906-orphan-tasks`
carries the two shapes a miscalibrated lint would refuse and must not: a
`## Verification` phase whose ids carry no story key (information, exit code
unchanged — FR-006, plan trap 6) and a task line quoted inside a fenced block,
deliberately written as the worst case this lint reports so that a scan without
the assembler's `mask_fences` produces a finding naming a task nobody wrote
(plan trap 2).

Red first. `uv run pytest tests/test_slice_coverage.py -q --no-header`, run
against the tree with these fixtures committed and no lint written, verbatim::

    FAILED tests/test_slice_coverage.py::test_the_split_slice_defect_names_every_task_its_story_drops
    FAILED tests/test_slice_coverage.py::test_a_task_inside_another_storys_slice_names_the_task_the_story_and_the_slice
    FAILED tests/test_slice_coverage.py::test_three_of_the_four_nodes_assemble_and_only_one_refuses
    FAILED tests/test_slice_coverage.py::test_task_ids_in_no_slice_with_no_story_reference_are_information
    FAILED tests/test_slice_coverage.py::test_the_information_is_printed_without_the_refusal_prefix
    FAILED tests/test_slice_coverage.py::test_a_trailing_section_with_no_task_ids_reports_nothing
    FAILED tests/test_slice_coverage.py::test_a_well_formed_trio_reports_slice_coverage_checked_and_silent
    FAILED tests/test_slice_coverage.py::test_slice_coverage_is_reported_skipped_when_tasks_md_cannot_be_read
    FAILED tests/test_slice_coverage.py::test_the_lint_carries_no_second_copy_of_the_story_grammar
    9 failed, 2 passed in 0.22s

The two that passed red had to, and they are the two that carry the calibration:

- `test_the_split_slice_defect_is_invisible_to_every_earlier_layer` runs the
  five layers that existed before this story over `904-split-slice` and asserts
  they report nothing. Had it failed red, the fixture would already have been
  caught by a check that existed and this lint would be a second spelling of it.

- `test_a_task_quoted_inside_a_fence_is_text_about_a_task` asserts an absence,
  so nothing can make it red before the lint exists. Its force is entirely in
  the pairing: the fenced line is written as the exact shape
  `test_a_task_inside_another_storys_slice_names_the_task_the_story_and_the_slice`
  proves the lint *does* report, so once the lint runs, only fence masking keeps
  it quiet.

Green after, same command::

    11 passed in 0.17s

And the whole suite, `uv run pytest -q`::

    2457 passed, 44 skipped, 4 warnings in 277.42s (0:04:37)

The fence masking was then mutated out — `in_code = [False] * len(lines)` in
`_task_entries` — to check that the trap-2 test can fail. It can, and the lint
without it reports a line nobody wrote::

    FAILED tests/test_slice_coverage.py::test_task_ids_in_no_slice_with_no_story_reference_are_information
    FAILED tests/test_slice_coverage.py::test_the_information_is_printed_without_the_refusal_prefix
    FAILED tests/test_slice_coverage.py::test_a_task_quoted_inside_a_fence_is_text_about_a_task
    3 failed, 8 passed in 0.17s

    ergane spec validate: [slice_coverage] task T999 names story US2, but it sits inside the task slice cut for US1 — the node building US2 is never shown it, and the node building US1 is shown it instead

Run the thing, not the tests about it. `uv run python -m factory.cli.main spec
validate tests/fixtures/prompt_assembly/904-split-slice`, verbatim::

    ergane spec validate: [slice_coverage] task T002 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it
    ergane spec validate: [slice_coverage] task T003 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it
    ergane spec validate: [slice_coverage] task T005 names story US2, but it falls outside the task slice cut for US2 and inside no other — no node is shown it
    ergane spec validate — noted, not a refusal: [slice_coverage] task ids inside no story's slice and naming no story, so they reach no node: T006 — expected in a setup or verification phase the operator works by hand, a defect anywhere else
    exit=1

...and on `905-wrong-slice`, where the one refusal and the four silent wrong
slices appear side by side — the top line is everything a refusal-only check
sees, the four below it are the two nodes that would have been dispatched with
the next story's work::

    ergane spec validate: [prompt_assembly] tasks.md: node 'us4': tasks.md declares no phase naming user story US4, so this node has no task slice to work (FR-006)
    ergane spec validate: [slice_coverage] task T004 names story US3, but it sits inside the task slice cut for US2 — the node building US3 is never shown it, and the node building US2 is shown it instead
    ergane spec validate: [slice_coverage] task T005 names story US3, but it sits inside the task slice cut for US2 — the node building US3 is never shown it, and the node building US2 is shown it instead
    ergane spec validate: [slice_coverage] task T006 names story US4, but it sits inside the task slice cut for US3 — the node building US4 is never shown it, and the node building US3 is shown it instead
    ergane spec validate: [slice_coverage] task T007 names story US4, but it sits inside the task slice cut for US3 — the node building US4 is never shown it, and the node building US3 is shown it instead
    ergane spec validate — noted, not a refusal: [slice_coverage] task ids inside no story's slice and naming no story, so they reach no node: T001 — expected in a setup or verification phase the operator works by hand, a defect anywhere else
    exit=1

...and on `906-orphan-tasks`, which passes with the orphans stated::

    ergane spec validate — noted, not a refusal: [slice_coverage] task ids inside no story's slice and naming no story, so they reach no node: T005, T006 — expected in a setup or verification phase the operator works by hand, a defect anywhere else
    tests/fixtures/prompt_assembly/906-orphan-tasks/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
    exit=0

Last, the layer was run over every trio under `specs/` in this tree, which is
where trap 6 is either honoured or disproved. Twenty-odd specs report a `T001`
setup id as information and pass; **two carry real defects, and nothing else in
the tree reports them.** `specs/024-ledger-token-honesty` is the 011 shape
exactly — `## Tests for User Story 1` followed by `## Implementation`, so the
single node it compiles to would have been dispatched with its tests and none
of its implementation::

    ergane spec validate: [slice_coverage] task T005 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it
    ergane spec validate: [slice_coverage] task T006 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it
    ergane spec validate: [slice_coverage] task T007 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it
    ergane spec validate: [slice_coverage] task T008 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it
    ergane spec validate: [slice_coverage] task T009 names story US1, but it falls outside the task slice cut for US1 and inside no other — no node is shown it

...and `specs/017-peer-channel` is the wrong-slice shape, still half-repaired:
its phase headings were renumbered when the inserted story was found, its task
tags were not, so every task below Phase 2 still names the story that used to
own the phase it sits in::

    ergane spec validate: [slice_coverage] task T008 names story US2, but it sits inside the task slice cut for US3 — the node building US2 is never shown it, and the node building US3 is shown it instead
    ergane spec validate: [slice_coverage] task T009 names story US2, but it sits inside the task slice cut for US3 — the node building US2 is never shown it, and the node building US3 is shown it instead
    ergane spec validate: [slice_coverage] task T010 names story US2, but it sits inside the task slice cut for US3 — the node building US2 is never shown it, and the node building US3 is shown it instead
    ergane spec validate: [slice_coverage] task T011 names story US3, but it sits inside the task slice cut for US4 — the node building US3 is never shown it, and the node building US4 is shown it instead
    ergane spec validate: [slice_coverage] task T012 names story US3, but it sits inside the task slice cut for US4 — the node building US3 is never shown it, and the node building US4 is shown it instead
    ergane spec validate: [slice_coverage] task T013 names story US3, but it sits inside the task slice cut for US4 — the node building US3 is never shown it, and the node building US4 is shown it instead
    ergane spec validate: [slice_coverage] task T014 names story US4, but it sits inside the task slice cut for US5 — the node building US4 is never shown it, and the node building US5 is shown it instead
    ergane spec validate: [slice_coverage] task T015 names story US4, but it sits inside the task slice cut for US5 — the node building US4 is never shown it, and the node building US5 is shown it instead
    ergane spec validate: [slice_coverage] task T016 names story US4, but it sits inside the task slice cut for US5 — the node building US4 is never shown it, and the node building US5 is shown it instead
    ergane spec validate: [slice_coverage] task T017 names story US4, but it sits inside the task slice cut for US5 — the node building US4 is never shown it, and the node building US5 is shown it instead

Both are at `state: draft`, so this landed before either could be dispatched,
which is the whole point. Neither is edited here: repairing a spec is spec work
and belongs to whoever refines it, and the tags are only half of what 017 is
held at draft for.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main
from factory.cli.nouns import spec as spec_noun
from factory.workgraph import preflight
from factory.workgraph.derive import derive_workgraph

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prompt_assembly"

WELL_FORMED = FIXTURES / "903-well-formed"
SPLIT_SLICE = FIXTURES / "904-split-slice"
WRONG_SLICE = FIXTURES / "905-wrong-slice"
ORPHAN_TASKS = FIXTURES / "906-orphan-tasks"

TARGET_REPO = "/srv/factory/targets/short-links"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    @property
    def findings(self) -> list[dict[str, str]]:
        return self.json["findings"]

    @property
    def information(self) -> list[dict[str, str]]:
        return self.json["information"]

    def messages(self, layer: str) -> str:
        return " ".join(
            entry["message"] for entry in self.findings if entry["layer"] == layer
        )

    @property
    def layers(self) -> list[str]:
        return [entry["layer"] for entry in self.findings]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """`ergane` through its real entry point; only `SystemExit` is caught.

    A lint that raises on a shape it did not expect fails the test with its
    traceback rather than being read as a finding.
    """

    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _graph(spec_dir: Path) -> Any:
    spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    return derive_workgraph(
        spec_text,
        epic_id=spec_dir.name,
        feature=spec_dir.name,
        specs_root=str(FIXTURES),
        target_repo=TARGET_REPO,
    )


# --- T015 / US3-S1: the 011 near-miss, caught offline -------------------------


def test_the_split_slice_defect_names_every_task_its_story_drops(
    run: Callable[..., Run],
) -> None:
    """US3-S1: each task id that names a story whose slice excludes it.

    `904-split-slice` assembles perfectly: `us1` is handed the tests it wrote
    for US1 and `us2` the tests it wrote for US2. What neither is handed is its
    own implementation — `T002` and `T003` say `[US1]` and sit below the next
    phase heading, `T005` says `[US2]` and does the same. Those three lines
    reach no agent, and the finding must name each id together with the story
    it belongs to, because the fix is a heading depth per group and the author
    needs to see which groups moved.
    """
    result = run("spec", "validate", "--json", str(SPLIT_SLICE))

    assert result.code == 1
    assert result.layers == ["slice_coverage"] * 3

    named = result.messages("slice_coverage")
    for task_id, story_key in (("T002", "US1"), ("T003", "US1"), ("T005", "US2")):
        assert task_id in named
        # The id and its story travel together: one finding names both.
        finding = next(
            entry["message"]
            for entry in result.findings
            if task_id in entry["message"]
        )
        assert story_key in finding

    # The two correctly-placed tasks are not accused of anything.
    assert "T001" not in named
    assert "T004" not in named


def test_the_split_slice_defect_is_invisible_to_every_earlier_layer() -> None:
    """The calibration: five layers pass this trio, and the sixth does not.

    Frontmatter, derivation, structure, personas, scenario coverage and — the
    one that matters — `prompt_assembly` all report nothing against
    `904-split-slice`. Every node assembles a complete, well-formed prompt. So
    the findings the test above asserts are a check that did not exist, rather
    than a second spelling of a refusal the command already made; and a lint
    that did nothing at all could not produce them.
    """
    spec_dir = SPLIT_SLICE
    spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    findings: list[spec_noun._ValidateFinding] = []

    spec_noun._check_frontmatter(spec_dir, spec_dir.name, findings)
    graph = _graph(spec_dir)
    spec_noun._check_workgraph(graph, findings)
    spec_noun._check_personas(graph, findings)
    spec_noun._check_scenario_coverage(spec_dir, spec_text, findings)

    assert [f"[{finding.layer}] {finding.message}" for finding in findings] == []
    assert (
        preflight.check_prompt_assembly(graph, spec_dir, spec_text=spec_text) == []
    )


# --- T016 / US3-S2: a task tagged for one story inside another's slice --------


def test_a_task_inside_another_storys_slice_names_the_task_the_story_and_the_slice(
    run: Callable[..., Run],
) -> None:
    """US3-S2: three facts per finding — the id, its story, the slice it sits in.

    In `905-wrong-slice` the phases below the first are numbered one story
    short, so `us2`'s slice is the phase whose tasks say `[US3]` and `us3`'s is
    the phase whose tasks say `[US4]`. Naming only the id would leave the author
    guessing which of two adjacent phases moved; naming the slice as well is
    what turns the finding into an edit.
    """
    result = run("spec", "validate", "--json", str(WRONG_SLICE))

    assert result.code == 1
    named = result.messages("slice_coverage")

    for task_id, referenced, sits_in in (
        ("T004", "US3", "US2"),
        ("T005", "US3", "US2"),
        ("T006", "US4", "US3"),
        ("T007", "US4", "US3"),
    ):
        finding = next(
            entry["message"]
            for entry in result.findings
            if entry["layer"] == "slice_coverage" and task_id in entry["message"]
        )
        assert referenced in finding, finding
        assert sits_in in finding, finding

    # US1's two tasks sit in US1's slice and are not named.
    assert "T002" not in named
    assert "T003" not in named


def test_three_of_the_four_nodes_assemble_and_only_one_refuses(
    run: Callable[..., Run],
) -> None:
    """The reason this lint exists: assembly reports one node out of three defects.

    `prompt_assembly` sees exactly one thing wrong with `905-wrong-slice` — the
    story no heading names at all. The two nodes that would have been handed
    another story's task list assemble cleanly and say nothing, which is why a
    refusal-only check leaves the expensive half of this defect in the tree.
    """
    spec_dir = WRONG_SLICE
    spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    graph = _graph(spec_dir)

    assembly = preflight.check_prompt_assembly(graph, spec_dir, spec_text=spec_text)

    assert [finding.node_id for finding in assembly] == ["us4"]

    result = run("spec", "validate", "--json", str(WRONG_SLICE))
    assert result.messages("prompt_assembly").count("node '") == 1
    assert "us4" in result.messages("prompt_assembly")
    # And the layer that does see the silent half names the two hidden slices.
    assert result.layers.count("slice_coverage") == 4


# --- T017 / US3-S3: orphans are information, and a fenced task is not a task --


def test_task_ids_in_no_slice_with_no_story_reference_are_information(
    run: Callable[..., Run],
) -> None:
    """FR-006 and plan trap 6: a `## Verification` phase is a convention.

    `906-orphan-tasks` closes with two ids that carry no story key. They reach
    no agent — that is worth saying, because an author who meant them to reach
    one has a defect — but it is the operator's own closing pass, so it is
    stated and the exit code is unchanged. A lint that failed this trio would
    fail the in-tree corpus too.
    """
    result = run("spec", "validate", "--json", str(ORPHAN_TASKS))

    assert result.code == 0
    assert result.findings == []

    notes = " ".join(entry["message"] for entry in result.information)
    assert [entry["layer"] for entry in result.information] == ["slice_coverage"]
    assert "T005" in notes
    assert "T006" in notes
    # The tasks that do sit in a slice are not reported as reaching nobody.
    assert "T001" not in notes
    assert "T004" not in notes


def test_the_information_is_printed_without_the_refusal_prefix(
    run: Callable[..., Run],
) -> None:
    """A note is not a finding, and a reader counting refusals must not count it.

    The human path prints the orphan ids on a line that deliberately does not
    carry the `ergane spec validate:` prefix every refusal carries — the same
    discipline US1 applied to a skipped layer.
    """
    result = run("spec", "validate", str(ORPHAN_TASKS))

    assert result.code == 0
    output = result.stdout + result.stderr
    assert "T005" in output
    assert "ergane spec validate:" not in output


def test_a_trailing_section_with_no_task_ids_reports_nothing(
    run: Callable[..., Run],
) -> None:
    """US3-S3's second half: silence when there is nothing to say.

    `903-well-formed` ends with the same `## Verification` heading, carrying one
    unnumbered line. No ids, no note — a lint that announced the section itself
    would be noise on every well-formed spec in the tree.
    """
    result = run("spec", "validate", "--json", str(WELL_FORMED))

    assert result.code == 0
    assert result.information == []


def test_a_task_quoted_inside_a_fence_is_text_about_a_task(
    run: Callable[..., Run],
) -> None:
    """Plan trap 2: the lint masks fences with the same function the assembler does.

    `906-orphan-tasks` quotes `T999`, tagged `[US2]`, inside a fenced block that
    sits in US1's slice — the exact shape
    `test_a_task_inside_another_storys_slice_names_the_task_the_story_and_the_slice`
    refuses. A line scan without `mask_fences` reports it, and the report names
    a task nobody wrote; the assembler would never have carried it into a
    prompt, so a lint that sees it disagrees with dispatch.
    """
    result = run("spec", "validate", "--json", str(ORPHAN_TASKS))

    assert "T999" not in json.dumps(result.json)


# --- T018 / US3-S4: the well-formed trio, and the honesty rule ----------------


def test_a_well_formed_trio_reports_slice_coverage_checked_and_silent(
    run: Callable[..., Run],
) -> None:
    """US3-S4: every id sits in the slice its reference names, so nothing is said."""
    result = run("spec", "validate", "--json", str(WELL_FORMED))

    assert result.code == 0
    document = result.json
    assert document["findings"] == []
    assert document["information"] == []
    # Membership rather than position: 069-US2 added a layer that runs after
    # this one, and what US3-S4 asserts is that slice coverage *ran* and said
    # nothing — not where in the list it landed.
    assert "slice_coverage" in document["checked"]
    assert document["skipped"] == []


def test_slice_coverage_is_reported_skipped_when_tasks_md_cannot_be_read(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Trap 5 again: no tasks.md, no slices, and no claim that there were.

    `prompt_assembly` already refuses the missing document. What this pins is
    that `slice_coverage` does not quietly appear in `checked` having located
    nothing in a file that is not there.
    """
    spec_dir = tmp_path / "907-no-tasks"
    shutil.copytree(WELL_FORMED, spec_dir)
    (spec_dir / "tasks.md").unlink()

    result = run("spec", "validate", "--json", str(spec_dir))

    assert result.code == 1
    document = result.json
    assert "slice_coverage" not in document["checked"]
    assert "slice_coverage" in [entry["layer"] for entry in document["skipped"]]


def test_the_lint_carries_no_second_copy_of_the_story_grammar() -> None:
    """FR-004 holds for this layer too: the slices come from the assembler.

    The lint needs the *bounds* of each slice, not just its text, and the only
    honest way to have them is to ask the module that cuts the slice at dispatch.
    A local scan for phase headings here would be a second grammar, agreeing
    with dispatch until the day either copy was edited.
    """
    source = Path(preflight.__file__ or "").read_text(encoding="utf-8")

    assert "task_slice_bounds" in source
    assert "mask_fences" in source
