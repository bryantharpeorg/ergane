"""Which stories will collide in a file, and the ordering that stops the race.

Two sibling nodes whose diffs touch one file are not a bug in either of them.
They are a bug in the schedule: they run concurrently, both open a landing, and
the merge queue rejects whichever arrives second for a conflict it did not
cause. That rejection is priced as a code defect and costs the node a ladder
rung, which is how 069's report lost a defect-free node. US1 makes that
survivable; this makes it rarer, by ordering the pair before either dispatches.

**The fact this reads is the task slice**, the only statement of intent that
exists before an agent runs. There is no diff to compare at derive time and
never will be — the whole point is to decide before dispatch (FR-007).

**Silence is the design constraint, not a side effect.** An inference that fires
too readily removes the concurrency the factory exists to provide and will be
switched off, which leaves every real collision unhandled. Four things are
therefore never contention: a directory, the trio every node is handed, a token
that is not a filename, and a pair the author already spoke about or the graph
already lands in merge order.

**Direction is declaration order**, never a guess at who creates the file, since
declaration order is already scheduling order (R10). A rule that read "creates"
out of prose would break on a rewording — the same mistake as classifying a
rejection by its message text (069 plan trap 2).

One case has no safe answer: the slices overlap, nothing guarantees a merge
order, *and* the declared graph runs the other way, so the edge the overlap
needs would close a cycle. That is refused by name (spec § Edge Cases) rather
than emitted as a graph no epic can compile.
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

#: A candidate path token: the run of characters a path may be spelled with. It
#: stops at every delimiter prose puts around one — a backtick, a bracket, a
#: comma, and (crucially) the `:` of a `file.py:558` anchor, so the anchor never
#: has to be stripped.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")

#: A final segment that is a filename: a name, a dot, a short extension.
#: `factory/mergequeue/` fails it (no final segment), `factory/<epic>` fails it
#: (the token stopped at `<`), and `2325` fails it.
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]*[A-Za-z0-9_]\.([A-Za-z][A-Za-z0-9]{0,7})$")

#: Extensions a *directory-less* name must carry to count as a file. A path with
#: a `/` needs no allow-list — the slash is already evidence — but a bare token
#: is one prose word away from `e.g.`, so this half is deliberately closed. A
#: file type missing from it is a reason to widen it deliberately, not to loosen
#: the rule.
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

    Carries both stories, because neither is the offender: the defect is the
    disagreement between the edges the author wrote and the files their tasks
    name, and the fix is one line in either. `Rejection` has a single `story`
    slot, so the pair is stated in `problem` too — a refusal an operator has to
    bisect costs what it saved.
    """

    stories: tuple[str, str]
    problem: str


def named_files(text: str) -> frozenset[str]:
    """Every file path a block of task prose names (069-US2 FR-007).

    New code with no precedent in this tree — the slice-coverage lint maps task
    id → story and never looks at a path, and `diffbounds` parses paths out of a
    unified diff that does not exist before dispatch — so it is small, pure, and
    tested against the corpus's real spelling variety.

    Tree-blind: the file a story is dispatched to *create* does not exist at
    derive time, so a check that stat'd the path would be blind to exactly the
    collisions worth catching. What is named is what counts.

    Conservative by construction — a token is a file only if its last segment is
    a filename with an extension, and a bare name only if that extension is one
    this repository writes.
    """
    found: set[str] = set()
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0).rstrip("./-").removeprefix("./")
        if not token:
            continue
        _directory, slash, tail = token.rpartition("/")
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

    Sliced through `task_slice_bounds`, never a second scan of the same headings:
    the lines this calls a story's are exactly the lines dispatch cuts. A second
    slicer would agree with `spec validate` until the day one copy was edited,
    then disagree at the cases that matter.

    A node whose slice does not assemble is **absent**, not empty:
    `check_prompt_assembly` already refuses it by name, and reading "names no
    file" out of "has no findable slice" would answer an unasked question.
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
    waived: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[InferredEdge], list[ContentionRefusal]]:
    """The ordering edges the slices imply, and the overlaps with no safe answer.

    Pure: a compiled graph and one text in, provenance out. Nothing is added to
    the graph here — `apply_contention_edges` does that — so a caller that only
    wants to *report* the contention (validation, FR-009) reads the same answer
    the deriver acts on rather than a second opinion. `waived` maps a node id to
    the ids it may safely race, in *ids* because that is what edges are spelled
    in.
    """
    waived = waived if waived is not None else {}
    files = slice_files(graph, tasks_text=tasks_text)
    by_id = {node.id: node for node in graph.nodes}
    order = [node.id for node in graph.nodes]
    # Working copies: an inferred edge joins them the moment it is decided, so
    # every later pair is judged against the ordering the edges before it
    # established — which is what drops the redundant third edge of a
    # three-way collision instead of emitting it.
    adjacency = {
        node.id: [*node.depends_on, *node.depends_on_merged] for node in graph.nodes
    }
    merged_edges = {node.id: set(node.depends_on_merged) for node in graph.nodes}

    edges: list[InferredEdge] = []
    refusals: list[ContentionRefusal] = []
    # Nearest sibling first: each story is ordered against the *closest*
    # preceding story it collides with, and the ones behind it are then covered
    # by the chain. Three stories over one file get two edges, not three.
    for position, later in enumerate(order):
        for earlier in reversed(order[:position]):
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
            # The path is both the test and the explanation: if one exists the
            # declared graph already runs the other way, and it is the very
            # thing the refusal has to show the author.
            existing = _path(adjacency, earlier, later)
            if existing is not None:
                path = " → ".join(by_id[step].story_key for step in existing)
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
                            f"cycle. Three fixes, the first usually right: make that "
                            f"edge `depends_on_merged` so {keys[0]} waits for "
                            f"{keys[1]} to land; move the shared file into one story; "
                            f"or declare `concurrent_with: [{keys[0]}]` on {keys[1]} "
                            "if they touch it safely"
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
    waived: Mapping[str, Sequence[str]] | None = None,
) -> tuple[WorkGraph, list[ContentionRefusal]]:
    """The same graph with the inferred edges hooked up, and any refusals.

    The edge lands in `depends_on_merged` — the existing contention edge type
    (D-025), not a third kind — because the collision it prevents is a *merge*
    collision, so the scheduler needs no change to honour it. Refusals never
    mutate anything: the caller decides whether one is fatal (the deriver: yes,
    nothing is emitted) or a report (validation).
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

    An edge or a waiver, either direction. Direction does not matter: the
    question is not "are they ordered the way the overlap wants" but "did a
    person consider this pair" — and if one did, the inference adds nothing.
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

    This, not plain reachability, is what makes a pair safe. A `depends_on` edge
    unlocks on *verification*: a story waiting only on that is cut from a base
    the sibling's change has not landed in, so both are in flight against one
    base and the second is still rejected — reachability alone would call a
    colliding pair safe. But a merge edge anywhere upstream is enough: if any
    node `waiter` transitively waits for lists `target` in `depends_on_merged`,
    that node dispatched after `target` landed and everything behind it later
    still, so the edge kinds along the way do not matter.

    The corpus settled this: 017-peer-channel chains five stories with
    `depends_on_merged` and two name `docs/architecture.md`. Calling that
    contention failed a spec whose stories provably cannot collide.
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


def _path(
    adjacency: Mapping[str, Sequence[str]], start: str, goal: str
) -> list[str] | None:
    """The dependency path from `start` to `goal`, or None — depth-first.

    Two answers at once: whether an ordering already holds, and, when it runs the
    wrong way, which edges an operator must look at. The graph is a handful of
    nodes and already known acyclic here, so the walk is unguarded.
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
