"""The WorkGraph's shape, and the validation that runs before anything dispatches.

`workgraph.json` is a compiled artifact, but it is also a *file on disk between
two commands* — `factory-epic derive` writes it and `factory-epic start` reads it,
with an operator's text editor available in between. That is why FR-002 puts
validation at epic start rather than trusting derive-time checks: the graph the
workflow runs is re-validated against the registry it will actually resolve
personas from, and a graph that fails is rejected before a single key is issued or
worktree created (contracts/workgraph-schema.md § Start-time validation).

Three properties carry the weight here:

- **Rejection names the offender.** An operator reading "invalid workgraph" learns
  nothing; every message in this module is asserted to contain the node id (or the
  field name) that caused it, and the cycle case is asserted to name *the cycle's*
  members rather than every node in the graph. The graph is small enough that a
  precise message is the difference between a one-line fix and a bisect.
- **Declaration order is scheduling order** (R10). Validation is a check, not a
  transform: it never sorts, never topologically reorders, and never rejects a
  graph merely for declaring a dependency after its dependent — the scheduler
  picks the first *ready* node, so out-of-order declaration is legal and only a
  genuine cycle is not.
- **Timeout resolution is persona-first, with an override** (R8). A producing node
  whose persona resolves no timeout fails here, at start, rather than at the
  moment the adapter needs a deadline it does not have. A per-story
  `timeout_override_s` rescues it, which is the whole point of the override.

`validate_workgraph` takes the persona registry as an argument rather than reading
`personas.yaml` itself: it stays pure (constitution IV), the `resolve_graph`
activity owns the one read per epic (the registry snapshot in data-model.md), and
these tests inject the exact registry each case needs instead of editing shipped
config to describe a hypothetical.

The round-trip tests exist because every type here crosses a Temporal activity or
workflow boundary through the default JSON converter. `StrEnum` specifically, not
`class X(str, Enum)`: only `StrEnum` survives the converter's *deserializer*, which
rebuilds a field annotated with any other str-subclass enum as a list of
one-character strings (the same trap `factory/verify/models.py` documents).

Written before `factory/workgraph/models.py` exists (T007 precedes T008): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import dataclasses
import json
from enum import StrEnum

import pytest

from factory.config import Persona, WriteScope
from factory.usage.models import Termination
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    EpicState,
    NodeState,
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)

EPIC = "003-merge-queue"
FEATURE = "003-merge-queue"
TARGET_REPO = "/home/admin/code/ergane-target"

#: The bootstrap persona every derived node names (contracts/workgraph-schema.md).
IMPLEMENTER = "implementer"


def _persona(
    name: str = IMPLEMENTER,
    *,
    timeout_s: int | None = 3600,
    agent: str = "claude-code",
) -> Persona:
    """A registry entry for an agent-backed persona.

    The model alias is a placeholder because nothing in this module resolves one —
    constitution VII keeps model names in `personas.yaml`, and a test that pinned
    a real alias would be asserting the operator's config, not the validator's.
    """
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


#: The registry most cases validate against: one persona, timeout resolvable.
REGISTRY = {IMPLEMENTER: _persona()}


def _node(node_id: str = "us1", **overrides: object) -> WorkNode:
    """One compiled story node, valid unless a test breaks exactly one field."""
    story_key = node_id.upper()
    fields: dict[str, object] = {
        "id": node_id,
        "story_key": story_key,
        "persona": IMPLEMENTER,
        "spec_ref": f"{FEATURE}:{story_key}",
        "requirement_keys": [story_key],
        "depends_on": [],
        "depends_on_merged": [],
        "timeout_override_s": None,
    }
    fields.update(overrides)
    return WorkNode(**fields)  # type: ignore[arg-type]


def _graph(nodes: list[WorkNode] | None = None, **overrides: object) -> WorkGraph:
    """A graph that validates, overridable one field at a time."""
    fields: dict[str, object] = {
        "epic_id": EPIC,
        "feature": FEATURE,
        "specs_root": "specs",
        "target_repo": TARGET_REPO,
        "nodes": nodes if nodes is not None else [_node()],
    }
    fields.update(overrides)
    return WorkGraph(**fields)  # type: ignore[arg-type]


def _json_round_trip(value: object) -> dict[str, object]:
    """What Temporal's default converter puts on the wire and reads back."""
    return json.loads(json.dumps(dataclasses.asdict(value)))  # type: ignore[call-overload]


# Acceptance ------------------------------------------------------------------


def test_a_well_formed_graph_validates() -> None:
    """The chain-plus-leaf shape the interpreter suite runs (SC-001)."""
    graph = _graph(
        nodes=[
            _node("us1"),
            _node("us2", depends_on=["us1"]),
            _node("us3"),
        ]
    )

    validate_workgraph(graph, REGISTRY)


def test_validation_leaves_declaration_order_untouched() -> None:
    """Declaration order *is* scheduling order (R10), so validation must not sort.

    The workflow picks "the first node in declaration order with all dependencies
    PASSED"; a validator that returned a topologically sorted graph, or sorted in
    place, would silently rewrite the operator's intended sequencing for every
    epic that has more than one ready node at a time.
    """
    declared = ["us3", "us1", "us2"]
    graph = _graph(nodes=[_node(node_id) for node_id in declared])

    validate_workgraph(graph, REGISTRY)

    assert [node.id for node in graph.nodes] == declared


def test_a_dependency_declared_after_its_dependent_is_still_valid() -> None:
    """Only cycles are rejected — declaration order need not be topological.

    Derivation emits spec order, which is usually topological, but nothing
    requires it: scheduling is by readiness, not by position, so a graph whose
    root is declared last runs exactly the same. Rejecting it would be a rule the
    contract's table does not contain.
    """
    graph = _graph(nodes=[_node("us2", depends_on=["us1"]), _node("us1")])

    validate_workgraph(graph, REGISTRY)


# Structural rejection (data-model.md § WorkGraph) ----------------------------


def test_duplicate_node_ids_are_rejected_by_id() -> None:
    """Ids name the branch, the worktree, and the transcript directory (FR-013).

    Two nodes sharing one id share all three, so the second node's attempt would
    run in the first's worktree and salvage onto its branch. There is no
    disambiguating them later — the collision has to be caught before dispatch.
    """
    graph = _graph(nodes=[_node("us1"), _node("us2"), _node("us1")])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    assert "us1" in str(excinfo.value)


def test_a_dangling_dependency_is_rejected_naming_both_ends() -> None:
    """An edge to a node that does not exist can never unlock.

    Left in, it is not an error the epic reports — it is a node that sits PENDING
    forever while the epic waits for a dependency no attempt will ever satisfy.
    """
    graph = _graph(nodes=[_node("us1"), _node("us2", depends_on=["us9"])])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert "us2" in message
    assert "us9" in message


def test_a_cycle_is_rejected_naming_its_members() -> None:
    """Deadlock detected as data, before it is observed as a hung epic."""
    graph = _graph(
        nodes=[
            _node("us1", depends_on=["us3"]),
            _node("us2", depends_on=["us1"]),
            _node("us3", depends_on=["us2"]),
        ]
    )

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert all(node_id in message for node_id in ("us1", "us2", "us3"))


def test_a_cycle_message_names_the_cycle_not_the_whole_graph() -> None:
    """"Names the cycle's members" is the contract, and it is the useful part.

    A message listing every node in the graph is a message the operator has to
    re-derive the cycle from by hand — which is the work the validator just did.
    """
    graph = _graph(
        nodes=[
            _node("us1"),
            _node("us2", depends_on=["us3"]),
            _node("us3", depends_on=["us2"]),
        ]
    )

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert "us2" in message
    assert "us3" in message
    assert "us1" not in message


def test_a_self_dependency_is_rejected() -> None:
    """A cycle of one — the shape a hand-edit produces most easily."""
    graph = _graph(nodes=[_node("us1", depends_on=["us1"])])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    assert "us1" in str(excinfo.value)


# FR-009: verified vs merged gating — `depends_on_merged` -----------------------
#
# A merge-gated edge (`depends_on_merged`) unlocks only when the dependency has
# *merged*, not merely verified. The validator treats it as a second edge set with
# the same discipline as `depends_on`: entries must be declared nodes, never the
# story itself, never also in `depends_on` (an edge gates on one thing — the plan
# D-025 discipline), and the union of both edge sets must be acyclic.


def test_depends_on_merged_defaults_to_empty() -> None:
    """An existing graph without the key stays valid — the additive default."""
    node = _node("us1")

    assert node.depends_on_merged == []


def test_depends_on_merged_round_trips_as_json() -> None:
    """`workgraph.json` carries the merge-gated edges across the wire."""
    graph = _graph(nodes=[_node("us2", depends_on_merged=["us1"])])

    raw = _json_round_trip(graph)
    rebuilt = WorkGraph(
        **{**raw, "nodes": [WorkNode(**node) for node in raw["nodes"]]}  # type: ignore[arg-type]
    )

    assert rebuilt == graph
    assert raw["nodes"][0]["depends_on_merged"] == ["us1"]


def test_a_merge_gated_dependency_must_be_a_declared_node() -> None:
    """A dangling merge-gated edge can never unlock — reject by both ends."""
    graph = _graph(nodes=[_node("us1"), _node("us2", depends_on_merged=["us9"])])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert "us2" in message
    assert "us9" in message


def test_a_self_merge_gated_dependency_is_rejected() -> None:
    """A node waiting on its own merge could never dispatch (cycle of one)."""
    graph = _graph(nodes=[_node("us1", depends_on_merged=["us1"])])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    assert "us1" in str(excinfo.value)


def test_a_key_in_both_edge_sets_is_rejected() -> None:
    """One dependency cannot gate on both verified and merged (D-025).

    A key in `depends_on` *and* `depends_on_merged` means the author wrote the
    same edge twice with two meanings; the scheduler would not know whether to
    dispatch on verification or on merge. The validator refuses it rather than
    silently preferring one.
    """
    graph = _graph(
        nodes=[_node("us1"), _node("us2", depends_on=["us1"], depends_on_merged=["us1"])]
    )

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert "us2" in message
    assert "us1" in message


def test_a_cycle_through_the_union_of_both_edge_sets_is_rejected() -> None:
    """Cycles may span both edge kinds — each edge is a real dependency.

    `us1` waits on `us3`'s *merge*; `us3` waits on `us2`'s merge; `us2` waits on
    `us1`'s verification. None of the three can ever run, but no single edge set
    contains a cycle — the union is what deadlocks, and the validator must see the
    union.
    """
    graph = _graph(
        nodes=[
            _node("us1", depends_on_merged=["us3"]),
            _node("us2", depends_on=["us1"]),
            _node("us3", depends_on_merged=["us2"]),
        ]
    )

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert all(node_id in message for node_id in ("us1", "us2", "us3"))


@pytest.mark.parametrize(
    "field_name, value",
    [
        ("epic_id", ""),
        ("epic_id", "   "),
        ("feature", ""),
        ("feature", "\t"),
        ("target_repo", ""),
        ("target_repo", "  "),
    ],
    ids=[
        "blank-epic",
        "whitespace-epic",
        "blank-feature",
        "whitespace-feature",
        "blank-target-repo",
        "whitespace-target-repo",
    ],
)
def test_a_blank_identity_field_is_rejected_by_name(field_name: str, value: str) -> None:
    """The three fields nothing downstream can proceed without.

    `epic_id` names branches, key aliases, and transcript directories; `feature`
    resolves the spec to snapshot criteria from; `target_repo` is the repository
    the worktree attaches to. Whitespace counts as blank because a stray space in
    a hand-edited JSON string is exactly how a "present" field arrives empty.
    """
    graph = _graph(**{field_name: value})

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    assert field_name in str(excinfo.value)


# Registry resolution (R8) ----------------------------------------------------


def test_an_unresolvable_persona_is_rejected_naming_node_and_persona() -> None:
    """A persona the registry does not carry resolves no model, scope, or timeout.

    Validation takes the registry as an argument, so this is the same check the
    `resolve_graph` activity makes against the snapshot it actually resolved from
    — not against whatever `personas.yaml` says at some other moment.
    """
    graph = _graph(nodes=[_node("us1", persona="archaeologist")])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, REGISTRY)

    message = str(excinfo.value)
    assert "us1" in message
    assert "archaeologist" in message


def test_a_persona_without_a_resolvable_timeout_is_rejected() -> None:
    """FR-010: no timeout is hardcoded, so an unresolved one is a hard stop.

    The registry loader stays lenient about an absent `timeout` (a deterministic
    persona has no attempt to bound), which moves the strictness here: a node that
    will run an adapter must resolve a deadline before anything dispatches, rather
    than at the moment the adapter needs one and falls back to a number nobody
    chose.
    """
    registry = {IMPLEMENTER: _persona(timeout_s=None)}
    graph = _graph(nodes=[_node("us1")])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, registry)

    message = str(excinfo.value)
    assert "us1" in message
    assert "timeout" in message


def test_a_per_story_override_resolves_a_timeout_the_registry_lacks() -> None:
    """The override is persona-first resolution's escape hatch (R8).

    A `timeout` in the spec's `## Work Graph` block is enough on its own — which
    is what makes the override useful for the one long story in an epic whose
    persona default is tuned for the rest.
    """
    registry = {IMPLEMENTER: _persona(timeout_s=None)}
    graph = _graph(nodes=[_node("us1", timeout_override_s=7200)])

    validate_workgraph(graph, registry)


def test_the_offending_node_is_named_even_when_others_resolve() -> None:
    """One bad node in a valid graph is reported as that node, not as the graph."""
    registry = {IMPLEMENTER: _persona(), "researcher": _persona("researcher", timeout_s=None)}
    graph = _graph(nodes=[_node("us1"), _node("us2", persona="researcher")])

    with pytest.raises(WorkGraphError) as excinfo:
        validate_workgraph(graph, registry)

    assert "us2" in str(excinfo.value)


# State enums (data-model.md § NodeState, § EpicState) ------------------------


@pytest.mark.parametrize("enum_type", [NodeState, EpicState], ids=["node", "epic"])
def test_state_enums_are_str_enums(enum_type: type[StrEnum]) -> None:
    """`StrEnum`, not `class X(str, Enum)` — the converter treats them differently.

    Both serialize as their value, but only `StrEnum` is recognised by Temporal's
    *deserializer*; any other str-subclass enum comes back from a query or a
    workflow payload as a list of one-character strings, so a node state of
    `PASSED` arrives as `['P', 'A', 'S', 'S', 'E', 'D']` and compares equal to
    nothing. The `epic_status` query returns these by name, so it would surface
    as a CLI that shows garbage for every node.
    """
    assert issubclass(enum_type, StrEnum)


def test_node_states_are_exactly_the_state_machine() -> None:
    """Ladder *actions* are not states (data-model.md).

    `RETRY`, `DEBUGGER` and `ESCALATE` are `NextAction` values — they route a node
    back into `KEY_ISSUED` or forward to a terminal state, and giving them
    membership here would create a second place the ladder's outcome is
    represented, one of which the workflow could park a node in permanently.
    The landing phase (FR-004) adds the states a verified node moves through on
    its way to the queue terminal: `PR_OPEN` → `ENQUEUED` → `MERGED`, matching
    architecture §1's lifecycle, with `PASSED` now meaning *verified, landing
    not terminal*.
    """
    assert {state.name for state in NodeState} == {
        "PENDING",
        "KEY_ISSUED",
        "RUNNING",
        "VERIFYING",
        "PASSED",
        "PR_OPEN",
        "ENQUEUED",
        "MERGED",
        "FAILED",
        "KILLED",
    }


def test_epic_states_are_exactly_the_epic_machine() -> None:
    """`RUNNING → PAUSED ⇄ RUNNING`, `→ KILLED`, `→ COMPLETED`."""
    assert {state.name for state in EpicState} == {
        "RUNNING",
        "PAUSED",
        "KILLED",
        "COMPLETED",
    }


@pytest.mark.parametrize(
    "member",
    [NodeState.PASSED, NodeState.KEY_ISSUED, EpicState.RUNNING, EpicState.COMPLETED],
    ids=["node-passed", "node-key-issued", "epic-running", "epic-completed"],
)
def test_a_state_serializes_as_its_own_uppercase_name(member: StrEnum) -> None:
    """The value an operator reads in the CLI and the Temporal Web UI."""
    assert member.value == member.name
    assert json.dumps(member) == f'"{member.name}"'


# Payload shape (Temporal's default JSON converter) ---------------------------


def test_the_graph_round_trips_as_json() -> None:
    """`workgraph.json` on disk and the workflow's argument are the same bytes.

    The CLI writes this file, `start` reads it, and Temporal carries it into the
    workflow as a payload — three hops through the same converter. Anything that
    did not survive `asdict` → `json` → reconstruction would be a field the
    workflow silently runs without.
    """
    graph = _graph(
        nodes=[
            _node("us1"),
            _node("us2", depends_on=["us1"], requirement_keys=["US2", "FR-003"]),
            _node("us3", timeout_override_s=7200),
        ]
    )

    raw = _json_round_trip(graph)
    rebuilt = WorkGraph(
        **{**raw, "nodes": [WorkNode(**node) for node in raw["nodes"]]}  # type: ignore[arg-type]
    )

    assert rebuilt == graph
    assert [node["id"] for node in raw["nodes"]] == ["us1", "us2", "us3"]


def test_a_rebuilt_graph_still_validates() -> None:
    """A graph that made the trip is a graph the workflow's first step accepts."""
    graph = _graph(nodes=[_node("us1"), _node("us2", depends_on=["us1"])])

    raw = _json_round_trip(graph)
    rebuilt = WorkGraph(
        **{**raw, "nodes": [WorkNode(**node) for node in raw["nodes"]]}  # type: ignore[arg-type]
    )

    validate_workgraph(rebuilt, REGISTRY)


def test_the_attempt_context_carries_exactly_the_adapters_inputs() -> None:
    """FR-005 names the adapter's inputs, and this is that list.

    The field set is asserted rather than sampled because the context is the
    entire interface between pure workflow logic and the one activity that
    touches an agent: a field added here is a new thing the workflow is trusted to
    assemble, and `virtual_key` is the only credential any payload in this
    component is allowed to carry (constitution V).
    """
    assert {field.name for field in dataclasses.fields(AttemptContext)} == {
        "epic_id",
        "node_id",
        "attempt",
        "prompt",
        "worktree_path",
        "proxy_url",
        "virtual_key",
        "model_alias",
        "session_id",
        "timeout_s",
    }


def test_the_attempt_context_round_trips_as_json() -> None:
    """It crosses a workflow→activity boundary once per attempt."""
    context = AttemptContext(
        epic_id=EPIC,
        node_id="us1",
        attempt=2,
        prompt="## Role\n\nImplement US1.\n",
        worktree_path="/home/admin/code/ergane/.factory/worktrees/003-merge-queue/us1",
        proxy_url="http://litellm.test",
        virtual_key="sk-fake-1",
        model_alias="fake-provider/CHANGEME",
        session_id="3f2504e0-4f89-41d3-9a0c-0305e82c3301",
        timeout_s=3600,
    )

    raw = _json_round_trip(context)

    assert AttemptContext(**raw) == context  # type: ignore[arg-type]
    # The prompt is the retry evidence's carrier (FR-006); a converter that
    # mangled newlines would be discovered as a judge complaining about format.
    assert raw["prompt"] == context.prompt


def test_the_adapter_result_carries_nothing_but_outcome_and_evidence() -> None:
    """D-018's narrow output, asserted as a closed field set (FR-005).

    No diff, no parsed verdict: the diff is read from the worktree and FR-012
    forbids any agent-reported signal reaching node state. `last_snapshot` is
    the one deliberate exception (plan US1) — a number the proxy reported, never
    one the workflow or adapter invented — so observation can ride the attempt's
    heartbeat without a per-interval poll (FR-001).
    """
    assert [field.name for field in dataclasses.fields(AdapterResult)] == [
        "termination",
        "transcript_path",
        "last_snapshot",
    ]


@pytest.mark.parametrize("termination", list(Termination), ids=lambda t: t.value)
def test_the_adapter_result_round_trips_for_every_termination(
    termination: Termination,
) -> None:
    """Every classification the adapter can return survives the trip back.

    The termination feeds `teardown_attempt` and the evidence trail on all four
    paths — including the two (TIMEOUT, KILLED) that only ever occur when
    something has already gone wrong and the record matters most.
    """
    result = AdapterResult(
        termination=termination,
        transcript_path=".factory/transcripts/003-merge-queue/us1/attempt-1",
    )

    raw = _json_round_trip(result)

    assert raw["termination"] == termination.value
    assert AdapterResult(**raw) == result  # type: ignore[arg-type]
