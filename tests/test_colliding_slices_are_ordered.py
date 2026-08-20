"""US2: siblings whose task slices name a common file are not raced.

The defect this suite pins is a *scheduling* one, not a code one. Two stories
declared independent, dispatched together, both writing `factory/x.py`: the one
that lands second is rejected by the merge queue for a conflict it did not
cause, and pays a ladder rung for it. 069's own report lost a defect-free node
that way, exhausted purely because its siblings kept landing first.

So derivation reads `tasks.md` as well as `spec.md` and infers an ordering edge
between stories whose slices name the same file. Four properties decide whether
that inference is worth having, each with a test below: it fires (US2-S1); it
does not fire otherwise (US2-S2, the control — an inference that serialises every
fan-out has removed the concurrency the factory exists to provide, and will be
switched off); an operator can tell which edges they wrote (US2-S3); and the
operator has the last word (US2-S5).

Every case derives `valid_epic`'s spec with only its `## Work Graph` block
swapped, so a failing case has one explanation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest

from factory.cli.main import main
from factory.workgraph.contention import named_files, slice_files
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph

CORPUS = Path(__file__).resolve().parent / "fixtures" / "workgraph"
VALID = "valid_epic"

IDENTITY = {
    "epic_id": "042-short-links",
    "feature": "042-short-links",
    "specs_root": "specs",
    "target_repo": "/home/admin/code/ergane-target",
}

#: The three story titles `valid_epic` declares, in spec order. A phase heading
#: is matched on the story *number* it names, so these are prose; they are the
#: fixture's words only so the corpus reads as one document.
TITLES = {"US1": "Save a link", "US2": "Follow a short link", "US3": "List my links"}


# --- fixtures: one spec, one tasks.md, both parameterised by one line ---------


def respecified(work_graph: str) -> str:
    """`valid_epic`'s spec with its `## Work Graph` block swapped for another."""
    head, _, tail = (CORPUS / VALID / "spec.md").read_text(
        encoding="utf-8"
    ).partition("## Work Graph\n")
    assert tail, "valid_epic must declare a `## Work Graph` section"
    _, _, after = tail.partition("## Assumptions")
    block = work_graph.strip("\n")
    return f"{head}## Work Graph\n\n```yaml\n{block}\n```\n\n## Assumptions{after}"


#: `valid_epic`'s three stories and the requirements each implements.
STORIES = {"US1": "[FR-001, FR-002]", "US2": "[FR-003]", "US3": "[FR-004]"}


def work_graph(**declared: str) -> str:
    """`valid_epic`'s three stories, with only the keys a case varies.

    `work_graph(US3="depends_on: [US1]")` — everything unstated is an independent
    story, so the one line that differs between cases is the one the call names.
    """
    return "".join(
        f"{story}:\n  {declared.get(story, 'depends_on: []')}\n"
        f"  implements: {requirements}\n"
        for story, requirements in STORIES.items()
    )


INDEPENDENT = work_graph()


def tasks(work: Mapping[str, Iterable[str]]) -> str:
    """A `tasks.md` whose phases name each story and whose tasks name files.

    One phase per story in `work`, in US order, one task line per path. The
    heading spelling is the corpus's, because the slice this is read into is cut
    by the assembler's own scan, not by anything this file knows.
    """
    blocks = ["# Tasks: Short Links\n"]
    for index, (story, paths) in enumerate(sorted(work.items()), start=1):
        number = story.removeprefix("US")
        blocks.append(
            f"## Phase {index}: User Story {number} - {TITLES.get(story, story)}\n"
        )
        for offset, path in enumerate(paths):
            task_id = f"T{index}{offset:02d}"
            blocks.append(f"- [ ] {task_id} [{story}] write the store in `{path}`\n")
        blocks.append("")
    return "\n".join(blocks)


def derive(work_graph: str = INDEPENDENT, *, tasks_text: str | None) -> WorkGraph:
    return derive_workgraph(
        respecified(work_graph), tasks_text=tasks_text, **IDENTITY
    )


def node(graph: WorkGraph, node_id: str) -> Any:
    (found,) = [candidate for candidate in graph.nodes if candidate.id == node_id]
    return found


# --- T012 (US2-S1): the edge is inferred -------------------------------------


SHARED = "factory/links/store.py"

#: One file each and no two the same — the control shape, used wherever a case
#: asserts nothing is inferred from slices that genuinely disagree.
DISJOINT = {
    "US1": ["factory/links/store.py"],
    "US2": ["factory/links/redirect.py"],
    "US3": ["factory/links/listing.py"],
}


def test_two_undeclared_independent_stories_naming_one_file_are_ordered() -> None:
    """US2-S1: overlapping slices, no declared edge, an inferred one.

    `depends_on_merged`, not `depends_on`: the collision is a *merge* collision,
    and a sibling that is merely verified has landed nothing the other's base
    would carry. It runs from the later-declared story to the earlier because
    declaration order is scheduling order (R10).
    """
    graph = derive(tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]}))

    assert node(graph, "us3").depends_on_merged == ["us1"]
    # And only that edge: the story that shares nothing is untouched.
    assert node(graph, "us1").depends_on_merged == []
    assert node(graph, "us2").depends_on_merged == []
    assert [(edge.node_id, edge.depends_on_merged) for edge in graph.inferred_edges] == [
        ("us3", "us1")
    ]


def test_the_shared_file_does_not_have_to_exist_yet() -> None:
    """A story that *creates* a file collides with one that edits it.

    The extraction reads what the prose names, never the tree: a check that
    stat'd the path would miss exactly the collisions worth catching.
    """
    unwritten = "factory/links/not_written_yet.py"
    graph = derive(tasks_text=tasks({"US1": [unwritten], "US2": [unwritten]}))

    assert node(graph, "us2").depends_on_merged == ["us1"]


# --- T013 (US2-S2): the control ----------------------------------------------


def test_stories_whose_slices_share_no_file_are_not_ordered() -> None:
    """US2-S2: disjoint slices, no edge, no provenance, nothing serialised.

    The same spec and task shape as the firing case above, so the *only*
    difference between a graph with an edge and one without is whether the two
    paths are the same string. A deriver that ordered siblings on any other
    signal fails here.
    """
    graph = derive(tasks_text=tasks(DISJOINT))

    assert [node_.depends_on_merged for node_ in graph.nodes] == [[], [], []]
    assert graph.inferred_edges == []


def test_the_documents_every_node_is_handed_are_not_contention() -> None:
    """Naming `spec.md`, `plan.md` or `tasks.md` orders nobody.

    Dispatch hands all three to every node, so counting them would order every
    pair of stories in the corpus.
    """
    graph = derive(
        tasks_text=tasks({story: [doc, *paths] for (story, paths), doc in zip(
            DISJOINT.items(), ("spec.md", "plan.md", "tasks.md")
        )})
    )

    assert graph.inferred_edges == []


def test_a_directory_is_not_a_file() -> None:
    """Two stories working under one directory do not collide in it.

    The merge queue rejects nothing over a directory, and treating one as a
    shared file would serialise every fan-out that shares a package.
    """
    graph = derive(
        tasks_text=tasks(
            {"US1": ["factory/links/store.py"], "US2": ["factory/links/redirect.py"]}
        )
    )

    assert graph.inferred_edges == []


def test_three_stories_over_one_file_are_chained_not_fully_connected() -> None:
    """The minimum ordering that removes the race, and not one edge more.

    A chain already lands all three in some order; a third edge (US3 on US1 as
    well as on US2) says it twice, and every redundant edge is a line an
    operator has to account for.
    """
    graph = derive(
        tasks_text=tasks({"US1": [SHARED], "US2": [SHARED], "US3": [SHARED]})
    )

    assert [(edge.node_id, edge.depends_on_merged) for edge in graph.inferred_edges] == [
        ("us2", "us1"),
        ("us3", "us2"),
    ]


def test_no_tasks_text_infers_nothing() -> None:
    """No `tasks.md`, no slices, no opinion — never a guess.

    A caller that has not read `tasks.md` gets exactly the graph the spec
    declares, which keeps every existing caller and artifact unchanged."""
    graph = derive(tasks_text=None)

    assert graph.inferred_edges == []
    assert [node_.depends_on_merged for node_ in graph.nodes] == [[], [], []]


# --- T014 (US2-S3): an inferred edge is not a declared one --------------------


DECLARES_US2_ON_US1 = work_graph(
    US2="depends_on: []\n  depends_on_merged: [US1]"
)


def test_an_inferred_edge_is_distinguishable_and_says_why() -> None:
    """US2-S3: provenance for the edge nobody wrote, and only for that one.

    Both land in the same field, because the scheduler must treat them alike.
    What separates them is `inferred_edges`: the author's own edge appears
    nowhere in it, the deriver's appears with the file that caused it.
    """
    graph = derive(
        DECLARES_US2_ON_US1,
        tasks_text=tasks(
            {"US1": [SHARED], "US2": ["factory/links/redirect.py"], "US3": [SHARED]}
        ),
    )

    # Both nodes carry an edge to us1; only one of them is the deriver's.
    assert node(graph, "us2").depends_on_merged == ["us1"]
    assert node(graph, "us3").depends_on_merged == ["us1"]

    (inferred,) = graph.inferred_edges
    assert (inferred.node_id, inferred.depends_on_merged) == ("us3", "us1")
    assert inferred.shared_files == [SHARED]
    # The reason states the cause, names both stories, and names the file.
    assert SHARED in inferred.reason
    assert "US3" in inferred.reason and "US1" in inferred.reason


def test_the_reason_survives_into_the_compiled_artifact(tmp_path: Path) -> None:
    """US2-S3, at the surface an operator reads: the compiled artifact.

    Provenance that lived only in memory would satisfy the dataclass alone.
    """
    epic = _epic_dir(tmp_path, tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]}))

    code = main(_argv("derive", epic))
    assert code == 0

    artifact = json.loads((epic / "workgraph.json").read_text(encoding="utf-8"))
    (edge,) = artifact["inferred_edges"]
    assert edge["node_id"] == "us3"
    assert edge["depends_on_merged"] == "us1"
    assert SHARED in edge["reason"]


# --- T015 (US2-S4): validation reports the disagreement -----------------------


def test_validate_reports_stories_declared_disjoint_whose_slices_overlap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """US2-S4: the check 060 needed.

    060 declared its stories file-disjoint, its diffs contradicted that, and only
    landing order saved it. The disagreement is knowable from two documents the
    author already has, so validate names both stories and the file, and lists
    the layer so a reader can see it ran.
    """
    epic = _epic_dir(tmp_path, tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]}))

    report = _validate(epic, capsys)

    assert "slice_contention" in report["checked"]
    (finding,) = [
        entry
        for entry in report["findings"]
        if entry["layer"] == "slice_contention"
    ]
    assert "US1" in finding["message"] and "US3" in finding["message"]
    assert SHARED in finding["message"]


def test_validate_says_nothing_when_the_slices_are_disjoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the layer: a correct spec is not nagged.

    A validate that reported contention here would report it for every spec in
    the corpus, and an operator told everything is told nothing."""
    epic = _epic_dir(tmp_path, tasks_text=tasks(DISJOINT))

    report = _validate(epic, capsys)

    assert "slice_contention" in report["checked"]
    assert [
        entry for entry in report["findings"] if entry["layer"] == "slice_contention"
    ] == []


# --- T016 (US2-S5): the operator has the last word ---------------------------


DECLARES_US3_ON_US1 = work_graph(US3="depends_on: [US1]")

#: The reverse of what the inference would have chosen: US1 waits for US3.
DECLARES_US1_ON_US3 = work_graph(US1="depends_on: [US3]")

WAIVES_US3_AGAINST_US1 = work_graph(
    US3="depends_on: []\n  concurrent_with: [US1]"
)


@pytest.mark.parametrize(
    "work_graph",
    [
        pytest.param(DECLARES_US3_ON_US1, id="declared-in-the-same-direction"),
        pytest.param(DECLARES_US1_ON_US3, id="declared-in-the-other-direction"),
        pytest.param(WAIVES_US3_AGAINST_US1, id="declared-safe-to-race"),
    ],
)
def test_an_explicit_declaration_overrides_the_inference(work_graph: str) -> None:
    """US2-S5: what the author wrote about this pair stands, unamended.

    Three ways to say it, all three win. The edges say "I have ordered these";
    `concurrent_with` says "I know they share a file and it is safe" — the case
    an operator must be able to state, because prose can name a file two stories
    genuinely do not fight over.
    """
    graph = derive(
        work_graph, tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]})
    )

    assert graph.inferred_edges == []
    # The declared edge is left exactly as authored — the override adds nothing
    # and removes nothing.
    assert node(graph, "us3").depends_on_merged == []
    assert node(graph, "us1").depends_on_merged == []


def test_a_waiver_naming_an_undeclared_story_is_refused() -> None:
    """A typo'd waiver must not silently waive nothing.

    `concurrent_with: [US9]` reads to its author as a collision they accepted.
    Ignoring it would leave the collision in place *and* the author believing it
    was handled — worse than never offering the key."""
    block = work_graph(US3="depends_on: []\n  concurrent_with: [US9]")

    with pytest.raises(DerivationError) as caught:
        derive(block, tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]}))

    assert [
        (fault.rule, fault.story) for fault in caught.value.rejections
    ] == [("concurrent_with", "US3")]


# --- T017 (Edge Cases): an inference that would cycle refuses -----------------


CHAINED = work_graph(US1="depends_on: [US2]", US2="depends_on: [US3]")


def test_an_inference_that_would_cycle_refuses_naming_both_stories() -> None:
    """Edge case: refuse by name rather than emit an uncompilable graph.

    US1 waits on US2 waits on US3 — on their *verification*, not their merge —
    and US1's slice and US3's name one file, so the collision is real. But the
    edge that would fix it, US3 after US1, closes the cycle the author already
    wrote. No safe direction and no graph to emit, so the refusal names both
    stories and the file: the fix is one line and the author must know which.
    """
    with pytest.raises(DerivationError) as caught:
        derive(
            CHAINED,
            tasks_text=tasks(
                {"US1": [SHARED], "US2": ["factory/links/redirect.py"], "US3": [SHARED]}
            ),
        )

    (fault,) = caught.value.rejections
    assert fault.rule == "slice_contention"
    assert "US1" in str(fault) and "US3" in str(fault)
    assert SHARED in str(fault)


def test_a_pair_already_ordered_through_a_third_story_gains_no_edge() -> None:
    """The other side of the same check: no cycle, no edge, no noise.

    US2 waits for US1 to *merge* and US3 waits on US2, so US3 dispatches after
    US1 landed: the ordering the overlap wants is in force, and the edge kinds
    above the merge edge do not matter. A second edge saying so would send an
    operator looking for a collision the graph already handles.
    """
    chained_forward = work_graph(
        US2="depends_on: []\n  depends_on_merged: [US1]", US3="depends_on: [US2]"
    )

    graph = derive(
        chained_forward, tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]})
    )

    assert graph.inferred_edges == []
    assert node(graph, "us3").depends_on_merged == []


def test_a_merge_gated_chain_running_the_other_way_is_left_alone() -> None:
    """017-peer-channel's shape, which the corpus caught this check failing.

    A serial `depends_on_merged` chain whose *earlier-declared* story lands last,
    the shared file at the two ends: US1 waits for US3's merge, so the pair
    provably cannot be in flight against one base. The ordering runs opposite to
    the inference's and the edge it would add would close a cycle — but there is
    no collision to prevent, so refusing would fail a correct spec.
    """
    merge_chained_backwards = work_graph(
        US1="depends_on: []\n  depends_on_merged: [US2]",
        US2="depends_on: []\n  depends_on_merged: [US3]",
    )

    graph = derive(
        merge_chained_backwards,
        tasks_text=tasks({"US1": [SHARED], "US3": [SHARED]}),
    )

    assert graph.inferred_edges == []
    assert node(graph, "us3").depends_on_merged == []


# --- the extraction itself (trap 7): new code, tested on its own -------------
#
# Nothing in this tree extracted a file path from prose before this story, so
# the half that is new is tested against the corpus's real spelling variety
# rather than against the one shape it was written for.


#: How this corpus really spells a path, and what each must yield. The empty
#: cases keep the inference quiet: a namespace, a directory, a line anchor and
#: ordinary prose are not files.
SPELLINGS: dict[str, tuple[str, set[str]]] = {
    "backticked": (
        "write `factory/links/store.py` first", {"factory/links/store.py"}
    ),
    "bare": ("write factory/links/store.py first", {"factory/links/store.py"}),
    "line-anchored-and-parenthesised": (
        "the assembler's own scan (`factory/workgraph/prompt.py:558`).",
        {"factory/workgraph/prompt.py"},
    ),
    "line-range": (
        "`factory/verify/ladder.py:119-133` — `_attempts_spent`",
        {"factory/verify/ladder.py"},
    ),
    "dotted-directory": (
        "read `.specify/memory/constitution.md`",
        {".specify/memory/constitution.md"},
    ),
    "bare-filename-no-directory": (
        "declare it in `factory.yaml`", {"factory.yaml"}
    ),
    "two-paths-one-line": (
        "in `tests/test_x.py`, and in `tests/test_y.py`.",
        {"tests/test_x.py", "tests/test_y.py"},
    ),
    "a-namespace-is-not-a-file": (
        "scope every call to `factory/<epic>/<node>`", set()
    ),
    "a-directory-is-not-a-file": (
        "everything under `factory/mergequeue/` is US3's", set()
    ),
    "a-bare-line-anchor-is-not-a-file": (
        "the counter at `:2325`, incremented once", set()
    ),
    "prose-abbreviations-are-not-files": (
        "assert it is charged, e.g. on both budgets", set()
    ),
    "requirement-keys-are-not-files": ("US1-S3 and SC-002 are the control", set()),
}


@pytest.mark.parametrize(
    "text,expected", SPELLINGS.values(), ids=list(SPELLINGS)
)
def test_the_extraction_reads_the_corpus_spellings(
    text: str, expected: set[str]
) -> None:
    assert named_files(text) == expected


def test_slice_files_reads_through_the_assemblers_own_scan() -> None:
    """Which lines are a story's is answered once, by dispatch's own scan.

    So this asserts the boundary a second slicer would drift at: US1's file is
    attributed to US1 and nobody else, though the phases are adjacent."""
    graph = derive(tasks_text=None)

    assert slice_files(graph, tasks_text=tasks(DISJOINT)) == {
        "us1": frozenset({"factory/links/store.py"}),
        "us2": frozenset({"factory/links/redirect.py"}),
        "us3": frozenset({"factory/links/listing.py"}),
    }


# --- helpers -----------------------------------------------------------------


def _epic_dir(
    tmp_path: Path, *, tasks_text: str, work_graph: str = INDEPENDENT
) -> Path:
    """A spec directory holding the trio, ready for a CLI verb."""
    epic = tmp_path / "specs" / "042-short-links"
    epic.mkdir(parents=True)
    (epic / "spec.md").write_text(respecified(work_graph), encoding="utf-8")
    (epic / "plan.md").write_text(
        "# Plan\n\nCarried into every node's prompt whole.\n", encoding="utf-8"
    )
    (epic / "tasks.md").write_text(tasks_text, encoding="utf-8")
    return epic


def _argv(verb: str, epic: Path) -> list[str]:
    """`ergane spec <verb> --json <epic>`, rooted at the tmp tree it lives in."""
    return [
        "spec", verb, "--json", str(epic),
        "--specs-root", str(epic.parent),
        "--target-repo", str(epic.parent),
    ]


def _validate(epic: Path, capsys: pytest.CaptureFixture[str]) -> Any:
    code = main(_argv("validate", epic))
    captured = capsys.readouterr()
    assert code in (0, 1), captured.err
    return json.loads(captured.out)
