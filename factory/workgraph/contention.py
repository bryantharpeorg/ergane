"""Which stories will collide in a file, and the ordering that stops the race.

Two sibling nodes whose diffs touch one file are not a bug in either of them.
They are a bug in the schedule: they run concurrently, both open a landing, and
the merge queue rejects whichever arrives second for a conflict it did not
cause. Today that rejection is priced as a code defect and costs the node a
ladder rung, which is how 069's report lost an entire node — defect-free, and
exhausted purely because its siblings kept landing first. US1 makes that
survivable. This makes it rarer, by ordering the pair before either dispatches.

**The fact this reads is the task slice**, because the task slice is the only
statement of intent that exists before an agent runs. There is no diff to
compare at derive time and there never will be — the whole point is to decide
before dispatch — so what a story's tasks *name* is the evidence available, and
FR-007 says so in those words.

The work splits in two, and the halves have very different answers:

- **Which lines are one story's?** Already solved, once, by
  `task_slice_bounds` — the assembler's own scan. This calls it rather than
  scanning headings again, so the lines called a story's slice here are exactly
  the lines dispatch cuts. A second slicer would agree with `spec validate`
  until the day one copy was edited, and would disagree first at exactly the
  boundary cases that matter (044 FR-004).

- **Which files do those lines name?** New. Nothing in this tree extracted a
  file path from prose before: the slice-coverage lint maps task id → story and
  never looks at a path, and `diffbounds` parses paths out of a unified diff,
  which does not exist before dispatch. So `named_files` is small, pure, and
  tested on its own against the corpus's real spelling variety rather than
  against the one shape it was written for.

**Silence is the design constraint, not a side effect.** An inference that fires
too readily removes the concurrency the factory exists to provide, and it will be
switched off — which leaves every real collision unhandled. So the extraction
refuses three things that are trivially shared across a whole spec and are never
what two stories fight over:

- a **directory** (`factory/mergequeue/`, `factory/<epic>/<node>`): two stories
  adding different files under one package merge cleanly, and the merge queue
  rejects nothing over a directory;
- the **three documents every node is handed** (`spec.md`, `plan.md`,
  `tasks.md`) when named bare: dispatch gives all three to every node by
  construction, so citing one is evidence that the author wrote a sentence;
- anything whose last segment is not a filename with an extension, which is what
  keeps `:2325`, `US1-S3` and `e.g.` out.

**Direction is declaration order**, never a guess at who creates the file.
Declaration order is already scheduling order (R10), so the inference follows the
sequencing the author wrote instead of inventing a second one — and a rule that
tried to read "creates" out of prose would be a heuristic that breaks on a
rewording, which is the same mistake as classifying a rejection by its message
text (069 plan trap 2).

**The author outranks the inference** (FR-008). A pair with any declared
relationship — an edge in either direction, or an explicit `concurrent_with`
waiver — is left exactly as written.

**A pair the graph already lands in order gains nothing either**, and "in
order" means *merge* order, not reachability: a story that waits on a sibling's
verification is still cut from a base that sibling has not landed in. The
predicate is `_merge_ordered`, and the corpus is what settled its shape —
017-peer-channel chains five stories with `depends_on_merged` and two of them
name `docs/architecture.md`, which a coarser rule refused as contention. That
would have failed a spec whose stories provably cannot collide, and a check that
cries wolf on correct specs is a check that gets switched off.

What is left is the one case with no safe answer: the slices overlap, nothing
guarantees a merge order, *and* the declared graph runs the other way, so the
edge the overlap needs would close a cycle. That is refused by name (spec
§ Edge Cases) rather than emitted as a graph no epic can compile — with the fix
that is usually right named first, which is to make the declared edge
merge-gated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from factory.workgraph.models import InferredEdge, WorkGraph, WorkNode
from factory.workgraph.prompt import (
    PLAN_DOCUMENT,
    SPEC_DOCUMENT,
    TASKS_DOCUMENT,
    PromptAssemblyError,
    task_slice_bounds,
)

#: A candidate path token: the run of characters a path may be spelled with,
#: which stops at every delimiter prose puts around one — a backtick, a bracket,
#: a comma, and (crucially) the `:` of a `file.py:558` line anchor, so the anchor
#: never has to be stripped.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")

#: A final segment that is a filename: a name, a dot, and a short extension.
#: `factory/mergequeue/` fails it (no final segment), `factory/<epic>` fails it
#: (the token stopped at `<`), and `2325` fails it.
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]*[A-Za-z0-9_]\.([A-Za-z][A-Za-z0-9]{0,7})$")

#: Extensions a *directory-less* name must carry to count as a file. A path with
#: a `/` needs no allow-list — the slash is already evidence — but a bare token
#: is one prose word away from `e.g.`, so this half is deliberately closed. A
#: file type missing from this list is a reason to widen it deliberately, the way
#: 044 widened its story-reference forms, not to loosen the rule.
_BARE_EXTENSIONS = frozenset(
    {
        "py", "md", "yaml", "yml", "json", "toml", "cfg", "ini", "txt",
        "sh", "bash", "sql", "lock", "html", "css", "js", "ts", "rs", "go",
    }
)

#: The trio dispatch hands to every node. Naming one is not contention.
_UNIVERSAL_DOCUMENTS = frozenset({SPEC_DOCUMENT, PLAN_DOCUMENT, TASKS_DOCUMENT})


@dataclass(frozen=True)
class ContentionRefusal:
    """An overlap whose only available ordering contradicts a declared one.

    Carries both stories rather than one, because neither is the offender: the
    defect is the disagreement between the edges the author wrote and the files
    the author's tasks name, and the fix is one line in either story. The
    deriver's `Rejection` has a single `story` slot, so the pair is stated in
    `problem` too — a refusal an operator has to bisect is a refusal that costs
    what it was meant to save.
    """

    stories: tuple[str, str]
    problem: str


def named_files(text: str) -> frozenset[str]:
    """Every file path a block of task prose names (069-US2 FR-007).

    Pure and tree-blind: the file a story is dispatched to *create* does not
    exist at derive time, so a check that stat'd the path would be blind to
    exactly the collisions worth catching. What is named is what counts.

    Conservative by construction — a token is a file only if its last segment is
    a filename with an extension, and a directory-less name only if that
    extension is one this repository writes. Everything else is prose.
    """
    found: set[str] = set()
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0).rstrip("./-").removeprefix("./")
        if not token:
            continue
        head, slash, tail = token.rpartition("/")
        if _FILENAME_RE.match(tail) is None:
            continue
        if not slash:
            extension = tail.rsplit(".", 1)[1].lower()
            if extension not in _BARE_EXTENSIONS or tail in _UNIVERSAL_DOCUMENTS:
                continue
        found.add(token)
    return frozenset(found)


def slice_files(graph: WorkGraph, *, tasks_text: str) -> dict[str, frozenset[str]]:
    """node id → the files that node's task slice names.

    Sliced through `task_slice_bounds`, never through a second scan of the same
    headings: the lines this calls a story's are the lines dispatch cuts.

    A node whose slice does not assemble is **absent**, not empty.
    `check_prompt_assembly` already refuses that node by name, and inferring
    "this story names no file" from "this story has no findable slice" would
    quietly answer a question that was never asked.
    """
    lines = tasks_text.splitlines()
    files: dict[str, frozenset[str]] = {}
    for node in graph.nodes:
        try:
            start, end = task_slice_bounds(node, tasks_text)
        except PromptAssemblyError:
            continue
        files[node.id] = named_files("\n".join(lines[start:end]))
    return files


def infer_contention_edges(
    graph: WorkGraph,
    *,
    tasks_text: str,
    waived: Mapping[str, Sequence[str]] = {},
) -> tuple[list[InferredEdge], list[ContentionRefusal]]:
    """The ordering edges the slices imply, and the overlaps with no safe answer.

    Pure: a compiled graph and one text in, provenance out. Nothing is added to
    the graph here — `apply_contention_edges` does that — so a caller that only
    wants to *report* the contention (validation, FR-009) reads the same answer
    the deriver acts on rather than a second opinion about it.

    `waived` maps a node id to the node ids it may safely race, in *ids* because
    that is what edges are spelled in; the deriver translates the author's story
    keys once, at the point it validates them.
    """
    files = slice_files(graph, tasks_text=tasks_text)
    by_id = {node.id: node for node in graph.nodes}
    order = [node.id for node in graph.nodes]
    # A working copy: inferred edges join it as they are decided, so the second
    # inference sees the first (an overlap already ordered by an inferred edge
    # needs no second one, and the cycle check must include them).
    adjacency = {
        node.id: [*node.depends_on, *node.depends_on_merged] for node in graph.nodes
    }

    merged_edges = {node.id: set(node.depends_on_merged) for node in graph.nodes}

    edges: list[InferredEdge] = []
    refusals: list[ContentionRefusal] = []
    for position, earlier in enumerate(order):
        for later in order[position + 1 :]:
            shared = files.get(earlier, frozenset()) & files.get(later, frozenset())
            if not shared:
                continue
            if _declared_between(by_id[earlier], by_id[later], waived):
                continue
            if _merge_ordered(adjacency, merged_edges, later, earlier) or _merge_ordered(
                adjacency, merged_edges, earlier, later
            ):
                # One of them already lands before the other *merges*, in one
                # direction or the other. Either way they cannot both be in
                # flight against the same base, so there is nothing to add and
                # nothing to say.
                continue
            names = ", ".join(f"`{name}`" for name in sorted(shared))
            keys = (by_id[earlier].story_key, by_id[later].story_key)
            if _reaches(adjacency, earlier, later):
                path = " → ".join(
                    by_id[step].story_key
                    for step in _path(adjacency, earlier, later) or ()
                )
                refusals.append(
                    ContentionRefusal(
                        stories=keys,
                        problem=(
                            f"{keys[0]} and {keys[1]} both name {names} in their task "
                            f"slices, so whichever lands second is rejected for the "
                            f"other's change. {keys[0]} already waits on {keys[1]} "
                            f"({path}), but on its *verification*, which is not its "
                            f"merge — so the collision stands, and the edge that "
                            f"would fix it ({keys[1]} after {keys[0]}) would close a "
                            f"cycle the graph could never compile. Three fixes, and "
                            f"the first is usually the one: make that edge "
                            f"`depends_on_merged` so {keys[0]} waits for {keys[1]} to "
                            f"land; move the shared file into one story; or declare "
                            f"`concurrent_with: [{keys[0]}]` on {keys[1]} if they "
                            "touch it safely"
                        ),
                    )
                )
                continue
            adjacency[later].append(earlier)
            merged_edges[later].add(earlier)
            edges.append(
                InferredEdge(
                    node_id=later,
                    depends_on_merged=earlier,
                    shared_files=sorted(shared),
                    reason=(
                        f"inferred, not declared: {keys[1]}'s task slice and "
                        f"{keys[0]}'s both name {names}, and the spec declares no "
                        f"ordering between them. Raced, whichever lands second is "
                        f"rejected for the other's change, so {keys[1]} — the "
                        f"later-declared of the two — waits for {keys[0]} to merge. "
                        f"Declare `concurrent_with: [{keys[0]}]` on {keys[1]} to run "
                        "them together anyway (069-US2 FR-007)"
                    ),
                )
            )
    return edges, refusals


def apply_contention_edges(
    graph: WorkGraph,
    *,
    tasks_text: str,
    waived: Mapping[str, Sequence[str]] = {},
) -> tuple[WorkGraph, list[ContentionRefusal]]:
    """The same graph with the inferred edges hooked up, and any refusals.

    The edge lands in `depends_on_merged` — the existing contention edge type
    (D-025), not a third kind — because the collision this prevents is a *merge*
    collision: a sibling that is merely verified has landed nothing the other's
    base would carry. The scheduler needs no change to honour it.

    Returns the graph untouched when there is nothing to infer, and refusals
    never mutate anything: the caller decides whether a refusal is fatal (the
    deriver: yes, nothing is emitted) or a report (validation).
    """
    edges, refusals = infer_contention_edges(
        graph, tasks_text=tasks_text, waived=waived
    )
    if not edges:
        return graph, refusals

    added: dict[str, list[str]] = {}
    for edge in edges:
        added.setdefault(edge.node_id, []).append(edge.depends_on_merged)

    nodes: list[WorkNode] = [
        node
        if node.id not in added
        else replace(
            node, depends_on_merged=[*node.depends_on_merged, *added[node.id]]
        )
        for node in graph.nodes
    ]
    return replace(graph, nodes=nodes, inferred_edges=edges), refusals


def _declared_between(
    earlier: WorkNode, later: WorkNode, waived: Mapping[str, Sequence[str]]
) -> bool:
    """Has the author already said something about this pair? (FR-008)

    An edge in either direction or a waiver in either direction. Direction does
    not matter because the question is not "are they ordered the way the overlap
    wants" but "did a person consider this pair" — and if one did, the inference
    has nothing to add.
    """
    for one, other in ((earlier, later), (later, earlier)):
        if other.id in one.depends_on or other.id in one.depends_on_merged:
            return True
        if other.id in waived.get(one.id, ()):
            return True
    return False


def _merge_ordered(
    adjacency: Mapping[str, Sequence[str]],
    merged_edges: Mapping[str, set[str]],
    waiter: str,
    target: str,
) -> bool:
    """Does `waiter` dispatch only after `target` has *merged*?

    This, not plain reachability, is what makes a pair safe — and getting it
    wrong in either direction is expensive, so the reasoning is written out.

    A `depends_on` edge unlocks on *verification*. A story that waits only on a
    sibling's verification is cut from a base that sibling's change has not
    landed in, so both are in flight against the same base and the second to
    land is still rejected. Reachability alone would therefore call a colliding
    pair safe.

    But a *merge* edge anywhere upstream is enough, whatever the edges above it
    are: if any node `waiter` transitively waits for lists `target` in its
    `depends_on_merged`, then that node dispatched after `target` landed, and
    everything waiting on that node dispatched later still. So the question is
    "can `waiter` reach a node that waits for `target`'s merge", and the kinds
    of the edges along the way do not matter.

    The corpus is what settled this: 017-peer-channel chains five stories with
    `depends_on_merged` and two of them name `docs/architecture.md`. Treating
    that as contention refused a spec whose stories provably cannot collide —
    a false alarm on the one shape the check is least entitled to be wrong
    about, since a check that cries wolf on correct specs gets switched off.
    """
    for node_id in _reachable(adjacency, waiter):
        if target in merged_edges.get(node_id, ()):
            return True
    return False


def _reachable(adjacency: Mapping[str, Sequence[str]], start: str) -> set[str]:
    """`start` and every node it transitively waits on, by any edge kind."""
    seen: set[str] = set()
    stack = [start]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(adjacency.get(node_id, ()))
    return seen


def _reaches(adjacency: Mapping[str, Sequence[str]], start: str, goal: str) -> bool:
    return _path(adjacency, start, goal) is not None


def _path(
    adjacency: Mapping[str, Sequence[str]], start: str, goal: str
) -> list[str] | None:
    """The dependency path from `start` to `goal`, or None — depth-first.

    Used for two answers at once: whether an ordering already holds, and, when
    the ordering runs the wrong way, which edges an operator has to look at. The
    graph is a handful of nodes and already known acyclic at this point (the
    deriver's own check runs first), so the walk is unguarded against depth.
    """
    seen: set[str] = set()

    def walk(node_id: str) -> list[str] | None:
        if node_id == goal:
            return [node_id]
        if node_id in seen:
            return None
        seen.add(node_id)
        for dependency in adjacency.get(node_id, ()):
            found = walk(dependency)
            if found is not None:
                return [node_id, *found]
        return None

    return walk(start)
