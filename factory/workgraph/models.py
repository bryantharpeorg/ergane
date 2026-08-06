"""The WorkGraph's types, and the validation that runs before anything dispatches.

One dataclass per entity in data-model.md, frozen so a value that crossed an
activity boundary can never be edited in place, and plain enough that Temporal's
default JSON converter round-trips them without help. Enums are `StrEnum`
specifically, not the older `class X(str, Enum)` spelling: both serialize as
their value, but only `StrEnum` is recognised by the converter's *deserializer*,
which rebuilds a field annotated with any other str-subclass enum as a list of
one-character strings — a `PASSED` that arrives as `['P', 'A', ...]` and compares
equal to nothing. `epic_status` returns these to the CLI, so the failure mode is
a status view full of garbage. The values are UPPERCASE and identical to the
member names because that is what an operator reads in the CLI and in Temporal's
Web UI.

`validate_workgraph` is the FR-002 gate. `workgraph.json` is a compiled artifact,
but it is also *a file on disk between two commands* — `factory-epic derive`
writes it, `factory-epic start` reads it, and an operator's text editor is
available in between — so the graph is re-validated against the registry it will
actually resolve personas from, and a graph that fails is rejected before a
single key is issued or worktree created.

Three properties of that validation carry weight:

- **Rejection names the offender.** "invalid workgraph" tells an operator
  nothing; every message here names the node id (or the field) that caused it,
  and the cycle case names *the cycle's* members rather than every node in the
  graph — the difference between a one-line fix and a bisect.
- **Declaration order is scheduling order** (R10), so validation is a check and
  never a transform: it does not sort, does not topologically reorder, and does
  not reject a graph merely for declaring a dependency after its dependent. The
  scheduler picks the first *ready* node, so out-of-order declaration runs
  identically and only a genuine cycle is a defect.
- **Timeout resolution is persona-first, with an override** (R8). A producing
  node whose persona resolves no timeout fails here, at start, rather than at the
  moment the adapter needs a deadline it does not have and falls back to a number
  nobody chose (FR-010).

The registry arrives as an argument rather than being read from `personas.yaml`:
validation stays pure (constitution IV), the `resolve_graph` activity owns the
one read per epic, and the workflow validates against the same snapshot it will
dispatch from — not against whatever the file says at some other moment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

from factory.config import Persona
from factory.usage.models import Termination, UsageSnapshot
from factory.verify.models import AttemptRecord


class WorkGraphError(ValueError):
    """A graph that must not dispatch (FR-002)."""


# State machines (data-model.md § NodeState, § EpicState) ---------------------


class NodeState(StrEnum):
    """Where one node stands.

    ```
    PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED
                                              ↘ FAILED
    any non-terminal ────────────────────────→ KILLED
    ```

    Terminal: `PASSED`, `FAILED` (parked by a PAUSE_EPIC resolution), `KILLED`.
    The ladder's `RETRY`/`DEBUGGER`/`ESCALATE` are deliberately absent — they are
    `NextAction` values that route a node back into `KEY_ISSUED` or forward to a
    terminal state. Giving them membership here would create a second place the
    ladder's outcome is represented, one of which a node could be parked in.
    """

    PENDING = "PENDING"
    KEY_ISSUED = "KEY_ISSUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    KILLED = "KILLED"


class EpicState(StrEnum):
    """Where the epic stands: `RUNNING → PAUSED ⇄ RUNNING`, `→ KILLED`,
    `→ COMPLETED` (every node terminal).

    `COMPLETED` does not imply all-PASSED — the workflow result carries the
    per-node outcome map, and SC-005's reading of success is "every node PASSED".
    """

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    KILLED = "KILLED"
    COMPLETED = "COMPLETED"


# Derivation intermediate (pure) ----------------------------------------------


@dataclass(frozen=True)
class WorkGraphDeclaration:
    """One parsed `## Work Graph` entry, before cross-validation.

    Never serialized beyond the deriver; it exists so a rejection can name the
    declaration (SC-006) at a point where no `WorkNode` has been built yet — the
    grammar's errors are about what the spec author wrote, not about a node.
    """

    story_id: str
    depends_on: list[str]
    implements: list[str]
    timeout: int | None = None
    depends_on_merged: list[str] = field(default_factory=list)


# The compiled graph ----------------------------------------------------------


@dataclass(frozen=True)
class WorkNode:
    """One user story, compiled (FR-011: one node per story, never hand-authored).

    `id` is the story key lowercased and names three things at once — the branch
    `factory/<epic_id>/<id>`, the worktree, and the transcript directory — which
    is why uniqueness is validated rather than assumed. `requirement_keys` is
    `[story_key, *implements]`: the exact filter later handed to
    `snapshot_criteria`, so what the node is verified against is fixed at
    derivation, not re-derived at verify time.
    """

    id: str
    story_key: str
    persona: str
    spec_ref: str
    requirement_keys: list[str]
    depends_on: list[str]
    #: Merge-gated edges (FR-009). Unlike `depends_on` — whose edge unlocks once
    #: the dependency is *verified* — an edge here unlocks only when the dependency
    #: has *merged*. Additive (D-025): a graph without the key stays valid, so the
    #: default is empty and every existing graph is unchanged.
    depends_on_merged: list[str] = field(default_factory=list)
    timeout_override_s: int | None = None


@dataclass(frozen=True)
class WorkGraph:
    """The `workgraph.json` artifact and the workflow's input.

    `nodes` is in declaration order, and that order *is* scheduling order (R10) —
    the deriver emits stories in spec order, so the spec author's sequencing is
    the visible tiebreak whenever more than one node is ready. `target_repo` is a
    worker-host path to the target clone (bootstrap topology); `specs_root` +
    `feature` resolve the spec that criteria are snapshotted from (D-023).
    """

    epic_id: str
    feature: str
    specs_root: str
    target_repo: str
    nodes: list[WorkNode]


@dataclass(frozen=True)
class ResolvedNode:
    """One node with the persona registry read against it, once, at epic start.

    The same snapshot discipline as 002's criteria: an operator editing
    `personas.yaml` mid-epic changes the *next* epic, never the one in flight.
    `model_alias` is the only place a model name enters an epic (constitution
    VII), and `timeout_s` is already resolved per R8 — the adapter is handed a
    deadline, never a rule for computing one.
    """

    node: WorkNode
    model_alias: str
    models: list[str]
    write_scope: str
    timeout_s: int


@dataclass(frozen=True)
class ResolvedPersona:
    """A registry entry resolved for a role no node is routed to.

    The judge is the whole reason this is separate from `ResolvedNode`: it scores
    the work another persona produced, so it has an alias and a key of its own
    (constitution V) but no node, no worktree and no deadline of its own — 002's
    judge is bounded by its own retry caps rather than by an attempt timeout
    (R8). Resolved once at epic start alongside the graph, under the same
    snapshot discipline: an operator editing `personas.yaml` mid-epic changes the
    *next* epic.
    """

    persona: str
    model_alias: str
    models: list[str]


@dataclass
class NodeRecord:
    """One node's live state in workflow memory, surfaced by `epic_status`.

    Mutable, alone among the types here: this is the workflow's own bookkeeping,
    advanced in place as an attempt moves through the ladder, and it never
    travels *into* an activity as an argument. `history` is 002's `AttemptRecord`
    verbatim because it is the ladder's input — a second representation would be
    a second thing to keep honest. `last_snapshot` is the latest usage poll (R3),
    retained so teardown has a fallback figure when the final read is unavailable
    rather than fabricating one (constitution V).
    """

    node_id: str
    branch: str
    state: NodeState = NodeState.PENDING
    attempt: int = 0
    history: list[AttemptRecord] = field(default_factory=list)
    escalations: list[str] = field(default_factory=list)
    base_ref: str | None = None
    last_snapshot: UsageSnapshot | None = None


# The adapter seam's payloads (FR-005) ----------------------------------------


@dataclass(frozen=True)
class AttemptContext:
    """Everything one attempt needs, assembled purely in the workflow.

    This is the entire interface between pure workflow logic and the one activity
    that touches an agent, so the field set is closed on purpose: a field added
    here is a new thing the workflow is trusted to assemble. `virtual_key` comes
    from the attempt's `KeyLease` and is the only credential any payload in this
    component may carry — the proxy master key never enters orchestration state
    (constitution V). `session_id` is generated with `workflow.uuid4()` so a
    replay reuses the id it already issued.
    """

    epic_id: str
    node_id: str
    attempt: int
    prompt: str
    worktree_path: str
    proxy_url: str
    virtual_key: str
    model_alias: str
    session_id: str
    timeout_s: int


@dataclass(frozen=True)
class AdapterResult:
    """D-018's narrow output — nothing else crosses back.

    No diff, no usage numbers, no parsed verdict: the diff is read from the
    worktree and usage from the ledger, and FR-012 forbids any agent-reported
    signal from reaching node state. `termination` is a process-outcome
    classification, not a reading of what the agent said it accomplished.
    `transcript_path` is the archived attempt directory under `.factory/`, which
    is evidence, never an input to a decision.
    """

    termination: Termination
    transcript_path: str


# Validation (FR-002) ---------------------------------------------------------


def resolve_timeout_s(node: WorkNode, persona: Persona) -> int | None:
    """The attempt's wall-clock bound, persona-first with a per-story override (R8).

    None means unresolvable, which is a hard stop at epic start rather than a
    default invented at dispatch: FR-010 puts every timeout in operator-editable
    config, so there is no number this could fall back to.
    """
    if node.timeout_override_s is not None:
        return node.timeout_override_s
    return persona.timeout_s


def validate_workgraph(graph: WorkGraph, personas: Mapping[str, Persona]) -> None:
    """Reject a graph that must not dispatch, naming what is wrong with it.

    The rules are contracts/workgraph-schema.md § Start-time validation: the
    three identity fields non-blank, node ids unique, every `depends_on` pointing
    at a declared node, the dependency relation acyclic, and every node's persona
    resolvable in the given registry *with* a resolvable timeout.

    Raises on the first offender rather than collecting: this runs as the
    workflow's first step, where the outcome is binary — the epic starts or it
    does not — and the deriver already reports the full error list at the point
    an author can act on all of them at once. Returns None; the graph is left
    exactly as it was declared (R10).
    """

    def fail(message: str) -> WorkGraphError:
        return WorkGraphError(f"workgraph '{graph.epic_id}': {message}")

    for field_name in ("epic_id", "feature", "target_repo"):
        value = getattr(graph, field_name)
        if not isinstance(value, str) or not value.strip():
            raise fail(f"field '{field_name}' must be a non-blank string, got {value!r}")

    declared: set[str] = set()
    for node in graph.nodes:
        if node.id in declared:
            raise fail(
                f"duplicate node id '{node.id}' — an id names the branch, the "
                "worktree, and the transcript directory (FR-013)"
            )
        declared.add(node.id)

    for node in graph.nodes:
        for dependency in node.depends_on:
            if dependency not in declared:
                raise fail(
                    f"node '{node.id}' depends on '{dependency}', which is not a "
                    "declared node"
                )
        for dependency in node.depends_on_merged:
            if dependency not in declared:
                raise fail(
                    f"node '{node.id}' depends on the merge of '{dependency}', "
                    "which is not a declared node"
                )

    for node in graph.nodes:
        overlap = set(node.depends_on) & set(node.depends_on_merged)
        if overlap:
            raise fail(
                f"node '{node.id}' lists {sorted(overlap)} in both `depends_on` "
                "and `depends_on_merged` — an edge gates on either verification "
                "or merge, never both (FR-009)"
            )

    cycle = _find_cycle(graph.nodes)
    if cycle is not None:
        raise fail(f"dependency cycle: {' -> '.join(cycle)}")

    for node in graph.nodes:
        persona = personas.get(node.persona)
        if persona is None:
            known = ", ".join(sorted(personas)) or "<empty registry>"
            raise fail(
                f"node '{node.id}': persona '{node.persona}' is not in the "
                f"persona registry (known: {known})"
            )

        override = node.timeout_override_s
        if override is not None and (
            isinstance(override, bool) or not isinstance(override, int) or override <= 0
        ):
            raise fail(
                f"node '{node.id}': timeout override must be a positive integer "
                f"of seconds, got {override!r}"
            )

        if resolve_timeout_s(node, persona) is None:
            raise fail(
                f"node '{node.id}': persona '{node.persona}' resolves no timeout "
                "and the node declares no timeout override — an attempt cannot be "
                "bounded (FR-010)"
            )


def _find_cycle(nodes: list[WorkNode]) -> list[str] | None:
    """One cycle in the dependency relation as the path that closes it, or None.

    A cycle is reported as `a -> b -> a` rather than as a set of implicated nodes
    because the operator's next move is to delete one of those edges, and the
    path says which edges exist. Only the nodes on the cycle appear: a message
    listing the whole graph would leave the reader to re-derive the cycle by hand,
    which is the work this just did.
    """
    # The union of both edge sets: a merge-gated edge is as real a dependency as
    # a verified one, and a cycle that spans the two is still a deadlock.
    adjacency = {
        node.id: [*node.depends_on, *node.depends_on_merged] for node in nodes
    }
    finished: set[str] = set()
    path: list[str] = []
    on_path: set[str] = set()

    def visit(node_id: str) -> list[str] | None:
        path.append(node_id)
        on_path.add(node_id)
        for dependency in adjacency[node_id]:
            if dependency in on_path:
                return path[path.index(dependency) :] + [dependency]
            if dependency not in finished:
                cycle = visit(dependency)
                if cycle is not None:
                    return cycle
        path.pop()
        on_path.discard(node_id)
        finished.add(node_id)
        return None

    for node in nodes:
        if node.id not in finished:
            cycle = visit(node.id)
            if cycle is not None:
                return cycle
    return None
