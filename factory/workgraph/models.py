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
but it is also *a file on disk between two commands* — `ergane spec derive`
writes it, `ergane build start` reads it, and an operator's text editor is
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
from typing import TYPE_CHECKING, Mapping, Sequence

from factory.config import Persona
from factory.mergequeue.models import Landing
from factory.usage.models import Termination, UsageSnapshot
from factory.verify.models import (
    UNRESOLVED_MODEL_ALIAS,
    AttemptRecord,
    VerificationResult,
)

if TYPE_CHECKING:
    # 008-US2: `OperatorAnswer` lives in the prompt assembler, which itself
    # imports `WorkNode` from this module — a runtime import here would cycle.
    # The field is a forward reference under `from __future__ import annotations`,
    # so the symbol is only needed for type checkers, never at runtime.
    from factory.workgraph.prompt import OperatorAnswer


class WorkGraphError(ValueError):
    """A graph that must not dispatch (FR-002)."""


#: `StandardsResolution.source` when the landing branch answered — the updated
#: text, which is the whole point of resolving per attempt (118 US3-S1).
STANDARDS_SOURCE_LANDING = "landing-branch"

#: `StandardsResolution.source` when the landing branch could not be read and
#: the pinned tree's copy answered instead (118 FR-008's fallback, trap 7).
STANDARDS_SOURCE_PINNED = "pinned-tree"


@dataclass(frozen=True)
class StandardsResolution:
    """One attempt's standards text, and where it was read from (118 FR-008).

    Resolved per attempt by the activity that reads the target repository, and
    carried into prompt assembly as already-read data so the builder stays pure
    (trap 6). `source` is one of the two constants above; `detail` is the reason
    a fallback fired — empty when the landing branch answered, the failure's own
    wording when the pinned copy was used, and quoted into the prompt so the
    archived record says not only *what* an attempt was told but *why it was
    told that version* (trap 8).
    """

    text: str
    source: str
    detail: str = ""


# State machines (data-model.md § NodeState, § EpicState) ---------------------


class NodeState(StrEnum):
    """Where one node stands.

    ```
    PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED → PR_OPEN → ENQUEUED → MERGED
                                              ↘ FAILED
                                              ↘ WAITING_OPERATOR
    any non-terminal ───────────────────────────────────────────────→ KILLED
    ```

    `PASSED` now means *verified, landing not terminal*: a node that passed the
    ladder has opened a landing (FR-009's whole distinction), so the happy-path
    terminal is `MERGED`, not `PASSED`. `PR_OPEN`/`ENQUEUED` are the landing
    phase's states, and `MERGED` is the new terminal a verified node reaches when
    the queue confirms it. `FAILED` and `KILLED` remain terminals reachable from
    any non-terminal state, a landing interrupted included. `WAITING_OPERATOR` is
    the non-terminal park a QUESTION attempt ends in (008-US1): the marker
    stopped the node, the operator's answer (US2) is what un-parks it, and the
    epic pauses the way a `PAUSE_EPIC` press pauses it. It is deliberately not in
    `_UNREACHABLE` — a parked question is not a dead edge, so its dependents stay
    PENDING rather than being KILLED.

    **079-US4 makes that sentence do a second job.** A `PAUSE_EPIC` press used to
    park its node in `FAILED`, which *is* in `_UNREACHABLE`, so one press ended
    the node and every node waiting on it (2026-08-19, three nodes). A press
    leaves `WAITING_OPERATOR` now, at both escalation sites: the reason the
    question park is not a dead edge is exactly the reason a pressed park is not
    one, and stating it twice in two states is how the two would drift. `FAILED`
    is consequently written by nothing in the interpreter today; it stays in the
    vocabulary because histories carry it and `_UNREACHABLE` must keep reading it
    as unreachable when they replay. The
    ladder's `RETRY`/`DEBUGGER`/`ESCALATE` are deliberately absent — they are
    `NextAction` values that route a node back into `KEY_ISSUED` or forward to a
    terminal state. Giving them membership here would create a second place the
    ladder's outcome is represented, one of which a node could be parked in.
    """

    PENDING = "PENDING"
    KEY_ISSUED = "KEY_ISSUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    PASSED = "PASSED"
    PR_OPEN = "PR_OPEN"
    ENQUEUED = "ENQUEUED"
    MERGED = "MERGED"
    FAILED = "FAILED"
    KILLED = "KILLED"
    #: The node is parked on the operator. Two doors reach it: an agent asked a
    #: question and is waiting for the answer (008-US1, FR-001), or an operator
    #: pressed `PAUSE_EPIC` and stopped the epic on this node (079-US4, FR-013).
    #: Non-terminal either way, and in neither case a dead edge — the dependents
    #: are not locked out, which is the whole of FR-013. The epic pauses while it
    #: waits. What differs is what un-parks it: an answer for the first, an
    #: operator's `resume`, `reset` or `kill` for the second.
    WAITING_OPERATOR = "WAITING_OPERATOR"


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
    persona: str | None = None
    #: Stories this one may safely race despite a shared file (069-US2 FR-008).
    #: The author's override of the slice-contention inference. It compiles to no
    #: node field: it is an instruction about an edge *not* to add, and once the
    #: graph is compiled there is nothing left of it to carry.
    concurrent_with: list[str] = field(default_factory=list)


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
class InferredEdge:
    """One ordering edge the deriver added that no author wrote (069-US2 FR-008).

    The edge itself lives where every other edge lives — the waiting node's
    `depends_on_merged` — because the scheduler must treat an inferred edge and a
    declared one alike. This is the *provenance* beside it, and it exists because
    an operator who cannot tell which edges they wrote cannot debug their own
    spec (US2-S3).

    `shared_files` is the evidence, sorted, and `reason` the sentence an operator
    reads. Both are carried rather than recomputed, so the artifact answers the
    question without re-reading a `tasks.md` that may since have been edited.
    Evidence, never an input: nothing schedules or dispatches from this list.
    """

    #: The node that waits — the later-declared story of the colliding pair.
    node_id: str
    #: The node whose *merge* it waits for, named for the field the edge landed
    #: in so the two can be matched by eye in the artifact.
    depends_on_merged: str
    shared_files: list[str] = field(default_factory=list)
    reason: str = ""


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
    #: Provenance for the edges the deriver inferred from task-slice contention
    #: (069-US2). Additive and empty by default: a graph derived without a
    #: `tasks.md` — and every artifact compiled before this landed — has none.
    inferred_edges: list[InferredEdge] = field(default_factory=list)


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
    #: Optional context-window tokens the persona declares for its model.
    #: None means undeclared; the adapter then emits nothing (FR-010).
    context_window: int | None = None


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

    Since 075-US1 it is also the epic's per-persona snapshot entry, and what a
    *rung* is routed by: the debugger cycle and the promotion rung select roles
    no node names either, and the attempt built for one of them takes its `agent`
    and its `model_alias` from a single entry of this type (FR-002). The two
    travel together on purpose — an attempt whose key was minted for one
    persona's agent while the process ran another's model is the disagreement
    that hid that defect twice. `agent` defaults to empty because a recorded
    payload written before the field existed must still deserialize, and because
    empty has always been what an unresolvable entry's agent reads as.
    """

    persona: str
    model_alias: str
    models: list[str]
    agent: str = ""


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
    #: True once the ladder PASSed this node — the moment `depends_on` (verified)
    #: edges unlock (FR-009). Distinct from `landing.state == MERGED`, which is what
    #: `depends_on_merged` edges wait on. `state == PASSED` is derived from this the
    #: moment a landing opens; it is kept as a boolean so the verified fact survives
    #: the landing's own state changes (PR_OPEN → ENQUEUED → MERGED).
    verified: bool = False
    #: The landing the workflow is driving for this node, `None` until its ladder
    #: PASSes. `None` is also the signal a node never reached the landing phase.
    landing: Landing | None = None
    #: The worktree and snapshotted criteria the node's attempts run in, captured
    #: once at first dispatch (FR-013) and reused by a recovery re-entry (US2):
    #: recovery re-verifies the *same* tree on the synced branch, so it must see
    #: the same pin and the same goalposts. `None` until a node dispatches.
    prepared: "PreparedWorktree | None" = None
    criteria: "CriteriaSet | None" = None
    #: 008-US2: the operator answer that un-parked this node, set the moment an
    #: answer arrives and cleared the moment the next attempt consumes it. `None`
    #: whenever the node was never parked, or was parked and expired (the
    #: operator never engaged, so there is no answer to carry — the question
    #: re-enters the ladder as a FAIL, FR-004, and the next prompt gets no answer
    #: section). Transient across one attempt: read once into the prompt, then
    #: reset to `None` so a *second* question on the same node starts clean.
    operator_answer: "OperatorAnswer | None" = None
    #: 008-US2: the question id this node is parked on while WAITING_OPERATOR,
    #: stashed at park time so the scheduler can route the buffered answer (or
    #: the expiry) back to *this* node on un-park. `None` unless the node is
    #: parked, and cleared on re-dispatch.
    pending_question_id: str | None = None
    #: 068-US2: the escalation child this node is paged on, set when the child
    #: starts and cleared when it settles or is cancelled; `None` when nobody is
    #: waited on. It is what tells an operator surface that a node in a
    #: live-looking state (`VERIFYING`, usually) is waiting rather than working
    #: — the distinction `ergane build reset` turns on (FR-007).
    pending_escalation_id: str | None = None
    #: US2: how many pre-first-token launch faults this node has hit.  Kept
    #: outside `history` because launch failures are not attempts and must not be
    #: counted by `_attempts_spent` (FR-005).  Bounded by `max_launch_retries`
    #: (FR-007).
    launch_failures: int = 0
    #: Set only when a node ended for a reason the ladder did not produce (US1):
    #: a crashed node coroutine, or — since 079-US1 — an escalation that could
    #: only be answered with choices nobody offered it. The text is surfaced in
    #: `ergane build status` for the KILLED node.
    terminal_reason: str | None = None
    #: US2: provenance for externally-completed work, surfaced in status and PR.
    provenance: str | None = None
    #: 095-US1: what the node's *latest* attempt was, when what it was is not
    #: readable from its verdict — today only the pre-agent failure, whose gate
    #: results are real, damning, and about nothing the story did (FR-004).
    #: Distinct from `terminal_reason`, which answers why a node *ended*: a
    #: pre-agent failure is ordinarily not an ending at all, and the operator
    #: watching a node still on rung two is exactly the one who needs to know
    #: that no agent has run yet. Rewritten every attempt, and `None` for an
    #: attempt that reached the agent, so it cannot outlive what it describes.
    attempt_note: str | None = None
    #: 079-US1: what the escalation this node was last paged on offered, in
    #: offer order. Kept after the page settles, because it is what a resolution
    #: coming back is checked against (FR-004).
    offered_choices: list[str] = field(default_factory=list)
    #: 079-US1: every resolution refused because this node's escalation never
    #: offered it, in arrival order (FR-004) — the record the refusal leaves
    #: behind, where before it fell through to the kill branch leaving nothing.
    refused_resolutions: list[str] = field(default_factory=list)
    #: 079-US1: the answer that ended this node — `KILL`, `PAUSE_EPIC`,
    #: `KILL_EPIC`, the store's `EXPIRED`, or a refusal that ran out of re-asks;
    #: `None` while no escalation has ended it. It is what stops a second page
    #: for a node whose operator already answered (FR-005).
    ending_answer: str | None = None
    #: 075-US3: the persona the node's *current* attempt was routed to, and the
    #: alias it runs under — the pair `ergane build status` reports for a node in
    #: flight (FR-012), where the history's own records do not exist yet. Written
    #: at the moment the rung's routing is read, *before* the resolution can
    #: fail, so a rung naming a persona the snapshot never resolved reports that
    #: persona with no alias rather than the node's own (US3-S3). Empty and
    #: unresolved until the node dispatches: a node that has run nothing names no
    #: model, because naming one would be indistinguishable from a reading.
    persona: str = ""
    model_alias: str = UNRESOLVED_MODEL_ALIAS
    #: 069-US1: the verdict this node's landing was opened on, kept so a rebase
    #: that spends no attempt can still re-render the PR body it already earned.
    #: A free rebase produces no new verification — that is the whole point — so
    #: without this the only way back onto the queue would be to run an agent,
    #: which is the charge the story removes. `None` until the ladder PASSes.
    last_result: VerificationResult | None = None


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
    home_path: str
    proxy_url: str
    virtual_key: str
    model_alias: str
    session_id: str
    timeout_s: int
    #: Optional context-window tokens the persona declares for its model.
    #: None means the adapter emits no context-window variable (FR-010).
    context_window: int | None = None
    #: Path to the target repository this attempt is dispatched against.
    #: The US1 detector compares the target repo's tracked-file state at start
    #: and teardown; it is part of the context because it is fixed at dispatch.
    target_repo: str = ""
    #: The persona's `agent` value resolved at dispatch, used by the adapter to
    #: decide gateway routing (US2 FR-005). Empty means "use the default path"
    #: for legacy payloads that predate this field.
    agent: str = ""


@dataclass(frozen=True)
class AdapterResult:
    """D-018's narrow output — nothing else crosses back.

    No diff, no parsed verdict: the diff is read from the worktree and FR-012
    forbids any agent-reported signal from reaching node state. `termination` is
    a process-outcome classification, not a reading of what the agent said it
    accomplished. `transcript_path` is the archived attempt directory under
    `.factory/`, which is evidence, never an input to a decision.

    `last_snapshot` is the exception, and a deliberate one (plan US1): usage is
    read *inside* the attempt (the heartbeat), and the newest reading rides home
    in the return value on the normal path — zero extra history events (FR-001).
    It is a number the proxy reported, never one the workflow or adapter
    invented, and `None` means the proxy was never read (constitution V).
    """

    termination: Termination
    #: Empty only on the one path where there is nothing to point at: the attempt
    #: that died on a heartbeat timeout never archived a transcript (the worker
    #: was already gone), so the workflow records that ending without inventing a
    #: path. Every adapter-produced result carries one.
    transcript_path: str = ""
    last_snapshot: UsageSnapshot | None = None
    #: 095-US1: the dying process's own last line, quoted for the operator and
    #: for nothing else. It is filled by the activity that owns interpreting the
    #: adapter's output, never by the adapter (D-018/FR-012 keeps what the agent
    #: *says* out of the classification), and it is read by no decision anywhere:
    #: the termination beside it was already settled, structurally, before this
    #: string was looked at. Empty on every path but the pre-agent one.
    detail: str = ""
    #: US1: which credential source a subscription-routed attempt used, so the
    #: precedence (long-lived token vs. copied credential) is legible in the
    #: record rather than inferred from behaviour (FR-005, trap 10). `None` for
    #: gateway-routed attempts, which have no such choice.
    credential_source: str | None = None


# The pre-agent failure, as an operator reads it (095-US1) --------------------


#: Words that, appearing in a dead process's own last line, mean the remedy is a
#: credential rather than a configuration. Enrichment only, and deliberately not
#: a classifier (plan trap 1): the attempt is a `PRE_AGENT_FAILURE` before this
#: tuple is consulted, so the day an agent invents a new way to say "logged out"
#: the class, the quote and the context all survive and only the remedy line
#: falls back to the general one.
CREDENTIAL_WORDS = (
    "authenticat",
    "oauth",
    "credential",
    "unauthorized",
    "log in",
    "login",
    "401",
)

#: What every pre-agent note says first, whatever killed the process. Two facts,
#: because the operator needs both: nothing was attempted of the story, and the
#: gate results sitting beside this note were measured on a worktree no agent
#: prepared — a typecheck failing with a missing binary there is correct, and
#: reading it as the story's failure is what cost an evening (FR-004, trap 3).
PRE_AGENT_CONTEXT = (
    "no agent turn ran: the process exited before producing a single token, so "
    "nothing was attempted of the story and the gates for this attempt ran "
    "against a worktree no agent prepared — their results describe the "
    "environment, not the work."
)

#: The remedy when the dying line names a credential, and when it names nothing
#: this code recognises. Both are actions on the worker host, because that is
#: where a pre-agent failure lives; neither asks anyone to open a transcript
#: (FR-002).
PRE_AGENT_AUTH_REMEDY = (
    "authentication: the worker host's agent session was refused. remedy: "
    "re-authenticate on the worker host (`claude login` for a subscription-routed "
    "persona, or reissue the node's proxy key), then re-dispatch."
)
PRE_AGENT_GENERAL_REMEDY = (
    "remedy: check the worker host's agent credentials and toolchain before "
    "re-dispatching — nothing recorded for this attempt is a fact about the story."
)


def pre_agent_note(detail: str = "") -> str:
    """What an operator is told about an attempt in which no agent turn ran.

    Pure, so the workflow can build it without an activity, and total: an empty
    `detail` is the ordinary case for a result that crossed a boundary written
    before this field existed, and it still yields the context and a remedy. The
    process's own words are quoted rather than paraphrased — the line that named
    the real cause on 2026-08-28 was 73 bytes long and no summary of it would
    have carried the word "OAuth".
    """
    parts = [PRE_AGENT_CONTEXT]
    quoted = " ".join(detail.split())
    if quoted:
        parts.append(f'the process\'s last words: "{quoted}"')
    parts.append(
        PRE_AGENT_AUTH_REMEDY
        if any(word in quoted.lower() for word in CREDENTIAL_WORDS)
        else PRE_AGENT_GENERAL_REMEDY
    )
    return " ".join(parts)


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

    cycle = find_cycle(
        {node.id: [*node.depends_on, *node.depends_on_merged] for node in graph.nodes}
    )
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


def find_cycle(adjacency: Mapping[str, Sequence[str]]) -> list[str] | None:
    """One cycle in a dependency relation as the path that closes it, or None.

    A cycle is reported as `a -> b -> a` rather than as a set of implicated nodes
    because the operator's next move is to delete one of those edges, and the
    path says which edges exist. Only the nodes on the cycle appear: a message
    listing the whole graph would leave the reader to re-derive the cycle by hand,
    which is the work this just did.

    Generalized from the two byte-identical `_find_cycle` copies this repo used
    to carry (one over `WorkNode`s, one over `WorkGraphDeclaration`s): both built
    an adjacency mapping and then ran the same DFS, so the mapping is the whole
    interface. The roadmap graph is the third caller — three duplicates was the
    defect the second copy's docstring warned about, so the shared spelling lives
    here and both existing callers reach it through their own adjacency dicts.
    """
    finished: set[str] = set()
    path: list[str] = []
    on_path: set[str] = set()

    def visit(node_id: str) -> list[str] | None:
        path.append(node_id)
        on_path.add(node_id)
        for dependency in adjacency.get(node_id, ()):
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

    for node_id in adjacency:
        if node_id not in finished:
            cycle = visit(node_id)
            if cycle is not None:
                return cycle
    return None
