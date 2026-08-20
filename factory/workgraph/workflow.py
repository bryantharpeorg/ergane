"""The interpreter: one workflow, any graph, driven to a terminal state.

This is the component the other two were built for. `EpicWorkflow` has no
knowledge of any particular epic: it reads a `WorkGraph`, and everything it then
does — which node runs, when an edge opens, how many attempts a failure buys, who
gets paged — comes out of that data and out of the two pure decision functions
002 already ships (D-002). There is one workflow type in the factory, and adding
a node type or a dependency edge is a change to a JSON file, never to this file.

Its shape is `contracts/workflow.md`, which in turn *composes*
`specs/002-verification-gating/contracts/verification-flow.md` — the reference
loop 002 wrote out and proved under time skipping, here made production and
wrapped in the two things a per-node loop could not own: scheduling, and the
worktree lifecycle.

Seven orderings are this module's own contribution, and each is load-bearing:

1. **Resolve the whole graph before dispatching any of it** (FR-002). A cycle, a
   dangling edge, an unknown persona, a persona with no timeout: all of them fail
   the epic at its first step, with the offending node named, before a key exists
   to be spent or a worktree to be swept. The registry read that validates is the
   same snapshot every node is later dispatched from, so an operator editing
   `personas.yaml` mid-epic changes the *next* epic (002's criteria discipline,
   applied to routing).

2. **An edge opens on a PASS and on nothing else** (FR-003, SC-002). The ladder's
   `NextAction.PASSED` is the only thing that marks a node PASSED, and a node is
   only dispatched once every dependency holds that state. The converse is
   enforced eagerly rather than lazily: the moment a node ends FAILED or KILLED,
   every node that transitively depended on it is marked KILLED *without being
   dispatched*, so "the epic ran out of ready nodes" and "the epic finished" are
   the same condition and there is no path where an unmet dependency is merely
   not-yet-satisfied.

3. **Record before acting** (FR-004, SC-003). One `issue_attempt_key` opens every
   attempt and one `teardown_attempt` closes it carrying the adapter's
   termination; `record_verification` lands before anything reads the verdict —
   before a retry prompt is built, before an operator is paged, before a worktree
   is swept. The escalation a human answers is assembled from those rows, so an
   ordering that acted first would page them about attempts the store has no
   record of.

4. **Salvage, then sweep, on every path out of a node** (constitution VI,
   SC-004). Pass, gate failure, timeout, kill, escalation-expiry: each ends with
   a salvage commit carrying the attempt number and the termination the adapter
   classified, and only then is the worktree removed. Once `.factory/` is swept
   the branch is the only account of the attempt, so it has to be enough.

5. **The adapter's termination never shortcuts verification** (FR-012). A
   TIMEOUT or AGENT_ERROR attempt runs the gates exactly like a clean one: the
   worktree may hold salvageable work, and no agent-side signal — an exit code
   included — is allowed to decide a node in either direction. The termination
   travels to teardown and to the salvage subject, and nowhere else.

6. **The steering wheel turns the scheduler, not the node** (FR-008). `pause`
   stops dispatch and nothing else: every node already in flight keeps its whole
   ladder, because each key lease and worktree is one bracket and suspending a
   node halfway through would leave a key issued against work nobody is doing.
   With N in flight the scheduler drains every in-flight task to its terminal
   state — reaping each, applying the lock-out its ending demands — *before* it
   parks, so the sentence stays true of N rather than being quietly reinterpreted
   to one (FR-007). `kill` is the single exception and the only path that
   interrupts an attempt — it cancels the adapter (whose KILLED path archives the
   transcript first, R2), closes the bracket the attempt opened, salvages and
   sweeps, and then marks every node the epic never reached KILLED, so a killed
   epic still accounts for its whole graph. With N in flight the same drain runs
   for kill: each in-flight node closes its own bracket on the way out (the
   `_kill_requested` flag each `_attempt` polls), so salvage runs per node and a
   kill that salvages some-but-not-all is a lost-work bug the drain prevents
   (FR-008). `_lock_out_dependents` is scoped to the finishing node's edge: it
   only ever marks a `PENDING` node whose *own* dependency is unreachable, so an
   unrelated in-flight node (RUNNING, never PENDING) is never touched (FR-009).
   A `PAUSE_EPIC` press is where the two meet: the ladder can only end the node,
   so the node parks FAILED — terminal, salvaged, swept, and distinguishable from
   the node an operator abandoned — and the epic-level half of that answer,
   stopping the scheduler, is supplied here.

7. **The judge is asked last, and only while it can still change the answer**
   (FR-003, 002's flow invariant 2). `judge_required` is the guard: gates green,
   output check passed, criteria carrying acceptance scenarios. Only then is the
   worktree's patch read — by an activity, because workflow code touches nothing
   — and only then is a key minted. That key is the judge's own, for persona
   `judge` and constrained to that persona's aliases, so scoring is spend
   attributed to the scorer (constitution V); it is torn down whatever the call
   did, an outage included. A judge that stayed down through the workflow's own
   retry budget does not block a PASS the deterministic evidence already earned,
   but the row carries `judge_unavailable` — the one column that says this PASS
   was reached without judge agreement, so nobody reads it later as judged work.

The debugger cycle runs on the node's own resolved alias and deadline for the
same reason — the registry snapshot covers graph nodes — but its key is minted
for persona `debugger`, so the cycle's spend is attributed to the debugger rather
than to the node's implementer (constitution V).

Everything here is pure decision-making over recorded results: no filesystem, no
clock but `workflow.now()`, no randomness but `workflow.uuid4()`, and no
scheduling input but graph declaration order and node state (constitution IV,
R10). That is what makes replay re-derive the epic without re-dispatching any of
it (SC-001), and what makes `pause` durable without a line of persistence code
(R1) — a signal is a history event, and replay rebuilds the flag.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Sequence

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    TimeoutError as ActivityTimeoutError,
)

with workflow.unsafe.imports_passed_through():
    from factory.activities.agent_activities import (
        AGENT_LAUNCH_FAILED,
        GRAPH_INVALID,
        HEARTBEAT_INTERVAL_S,
        LoadPromptSourcesInput,
        PrepareWorktreeInput,
        PromptSources,
        ReadWorktreeDiffInput,
        RemoveWorktreeInput,
        ResolvePersonaInput,
        SalvageWorktreeInput,
        load_prompt_sources,
        prepare_worktree,
        read_worktree_diff,
        remove_worktree,
        resolve_graph,
        resolve_persona,
        run_agent_attempt,
        salvage_worktree,
    )
    from factory.activities.merge_activities import (
        CompareTreesInput,
        DisableAutoMergeInput,
        EnqueueLandingInput,
        FetchCheckFailureInput,
        OpenLandingPrInput,
        PollLandingInput,
        PrepareLandingPrInput,
        SyncLandingBranchInput,
        ValidateTargetRepoInput,
        compare_trees,
        disable_auto_merge,
        enqueue_landing,
        fetch_check_failure,
        open_landing_pr,
        poll_landing,
        prepare_landing_pr,
        sync_landing_branch,
        validate_target_repo,
    )
    from factory.activities.notify_activities import (
        DEFAULT_CHOICES,
        QUESTION_TIMEOUT_S,
    )
    from factory.notify.service import EXTERNAL_COMPLETION_SIGNAL
    from factory.escalation.question import (
        QuestionRequest,
        QuestionWorkflow,
    )
    from factory.escalation.workflow import (
        EscalationRequest,
        EscalationWorkflow,
        child_correlation_id,
    )
    from factory.activities.usage_activities import (
        IssueKeyInput,
        TeardownInput,
        issue_attempt_key,
        poll_usage,
        teardown_attempt,
    )
    from factory.activities.verify_activities import (
        JUDGE_UNAVAILABLE,
        CheckOutputInput,
        DetectQuestionInput,
        RecordExternalCompletionInput,
        RecordVerificationInput,
        RunGatesInput,
        RunJudgeInput,
        SnapshotCriteriaInput,
        check_output,
        detect_operator_question_activity,
        record_external_completion,
        record_verification,
        run_gates,
        run_judge,
        snapshot_criteria,
    )
    from factory.mergequeue.classify import classify
    from factory.mergequeue.models import (
        CheckFailure,
        Landing,
        LandingConfig,
        LandingState,
        ObservedOutcome,
        QueueOutcome,
        RejectionCause,
        TargetRepoProfile,
    )
    from factory.mergequeue.rejection import rejection_cause
    from factory.notify.messages import render_history, render_landing_history
    from factory.usage.models import KeyLease, Termination, UsageSnapshot
    from factory.verify.ladder import DEBUGGER_PERSONA, next_action
    from factory.verify.models import (
        AttemptRecord,
        CriteriaSet,
        EscalationChoice,
        JudgeOutcome,
        JudgeVerdict,
        NextAction,
        OverallVerdict,
        VerificationConfig,
        VerificationForm,
        VerificationResult,
        compose_result,
        judge_required,
        loop_digest,
        loop_summary,
    )
    from factory.workgraph.adapter import home_path
    from factory.config import Persona, SUBSCRIPTION_AGENT
    from factory.workgraph.models import (
        AdapterResult,
        AttemptContext,
        EpicState,
        NodeRecord,
        NodeState,
        ResolvedNode,
        ResolvedPersona,
        WorkGraph,
        WorkNode,
    )
    from factory.workgraph.prompt import (
        AttemptEvidence,
        LandingEvidence,
        OperatorAnswer,
        build_attempt_prompt,
    )
    from factory.workgraph.worktree import DEFAULT_FACTORY_ROOT, PreparedWorktree, branch_name

#: The one task queue every epic and every activity of this component runs on
#: (D-002). Named here rather than in the worker so the worker, the CLI and the
#: workflow cannot drift apart on a string.
TASK_QUEUE = "workgraph"

#: The registry entry the judge's own key is minted against — a persona, never a
#: model (constitution VII). Deliberately not the node's: the judge scores the
#: work, so the completion is attributed to the judge and constrained to the
#: aliases that persona names. No node is routed to it, which is why it is
#: resolved by name at epic start rather than found on a `ResolvedNode`.
JUDGE_PERSONA = "judge"

#: How often the workflow reads what a live attempt has spent (R3). A poll is a
#: read with no consequence — enforcement is deferred (D-021) — and its only
#: product is the fallback figure teardown records when the final read fails.
#: Settable per epic because a test cannot afford production's interval and
#: production cannot afford a test's.
DEFAULT_POLL_INTERVAL_S = 30

#: Node states from which no *verified-gated* dependent can ever be dispatched. A
#: node whose dependency reached one of these is KILLED where it stands, never
#: dispatched (SC-002). A landing-terminal that is not MERGED (KILLED / a final
#: rejection) is unreachable only for merge-gated dependents (`depends_on_merged`),
#: which wait for the dependency to MERGE, not merely to pass — FR-009.
_UNREACHABLE = frozenset({NodeState.FAILED, NodeState.KILLED})

#: Ladder actions that end a node.
_TERMINAL_ACTIONS = frozenset({NextAction.PASSED, NextAction.KILLED})

#: Node states nothing may move a node out of. The kill sequence writes over
#: every node that is not already in one of these, which is what makes a killed
#: epic's status an account of the whole graph rather than of the part that ran.
#: `PASSED` (verified, landing not terminal) is deliberately not here — a verified
#: node still owes its landing a terminal, and `MERGED` is what a passed node
#: reaches when the queue confirms it (FR-009).
_TERMINAL_STATES = frozenset({NodeState.MERGED, NodeState.FAILED, NodeState.KILLED})

#: Landing states that end a landing and admit no recovery: MERGED (the queue
#: landed it) and KILLED (operator/epic kill, or a rejection routed to a terminal).
#: `REJECTED` is deliberately absent — FR-006's bounded recovery cycle (US2) can
#: return a rejected landing to ENQUEUED.
_LANDING_TERMINAL = frozenset({LandingState.MERGED, LandingState.KILLED})

#: Queue outcomes that are a rejection a recovery cycle can fix (US2, FR-006),
#: rather than a terminal the landing ends on. Everything else the classifier
#: yields — MERGED, DEQUEUED_BY_HUMAN, STALLED — ends the landing here.
_RECOVERY_OUTCOMES = frozenset(
    {QueueOutcome.CHECKS_FAILED, QueueOutcome.CONFLICT}
)

#: Activities here are idempotent reads, guarded upserts, and sends that mint a
#: fresh id per call — all safe to retry, none worth retrying for long while the
#: ladder holds a decision.
_RETRIES = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

#: One relaunch and no more. A worker that died mid-attempt leaves an orphaned
#: agent the adapter reaps before starting again (R4), which is worth exactly one
#: retry; a second would spend hours of model time on the assumption that the
#: third launch differs from the second. Everything past that is the ladder's
#: budget to spend, and the ladder can read the evidence.
_AGENT_RETRIES = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_attempts=2,
)

#: Key issuance retries. A proxy restart is minutes, not seconds, and the only
#: thing this policy backs is `issue_attempt_key` (FR-009). `_RETRIES` stays
#: untouched because it is shared by `_FAST`, `_GIT`, `_GATES`, and `_JUDGE`, and
#: `teardown_attempt` keeps the old budget — the new tolerance is issuance-only.
_ISSUE_KEY_RETRIES = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=8,
    backoff_coefficient=2.0,
)

#: Reads and small writes: a registry parse, a spec parse, a git diff, a SQLite
#: upsert, two API calls.
_FAST = {
    "start_to_close_timeout": timedelta(minutes=2),
    "retry_policy": _RETRIES,
}

#: Proxy round trips that page spend logs on the way (001 R3).
#: Issuance now has its own retry budget (FR-009); `_PROXY` is kept on `_RETRIES`
#: for `teardown_attempt`, whose budget is unchanged.
_PROXY = {
    "start_to_close_timeout": timedelta(minutes=5),
    "retry_policy": _RETRIES,
}

#: git, which may be checking out a large repository for the first time
#: (`worktree.GIT_TIMEOUT_S` bounds each command underneath).
_GIT = {
    "start_to_close_timeout": timedelta(minutes=10),
    "retry_policy": _RETRIES,
}

#: A whole gate suite, whose real liveness bound is the per-gate heartbeat below:
#: the number of gates a repo declares is the repo's business, and a ceiling that
#: guessed at it would fail the honest slow suite rather than the wedged one.
_GATES = {
    "start_to_close_timeout": timedelta(hours=2),
    "retry_policy": _RETRIES,
}

#: One bounded chat completion, plus the HTTP retries the judge makes inside it
#: (002 R4). Longer than a proxy round trip and far shorter than a gate suite: a
#: judge still thinking after a quarter of an hour is a judge nobody is waiting
#: for, and the ladder is holding the node open the whole time.
_JUDGE = {
    "start_to_close_timeout": timedelta(minutes=15),
    "retry_policy": _RETRIES,
}

#: Grace on top of one gate's own deadline before the *activity* is declared
#: dead: the runner's SIGTERM → SIGKILL escalation has to have time to land and
#: be reported as a TIMEOUT gate result rather than as a lost activity.
_GATE_HEARTBEAT_GRACE_S = 60

#: Grace on top of the node's own deadline before the *activity* is declared
#: dead. The adapter enforces the deadline itself and then has work to do —
#: TERM, KILL, archive the transcript (FR-007) — and an activity timeout that
#: fired first would discard exactly the evidence that path exists to produce.
_ADAPTER_GRACE_S = 120

#: Missed beats before a live attempt is presumed dead — and, more sharply, how
#: long a killed agent goes on spending. Temporal delivers activity cancellation
#: in a heartbeat's *response*, and batches heartbeats to one round trip per 80%
#: of this value, so a kill reaches the agent about `0.8 ×` this timeout after
#: the operator sends it. That is the binding purpose: detecting a dead worker a
#: minute later costs nothing (the epic is stalled either way), while an agent
#: that runs on for a minute after "stop" is spending model time nobody wants
#: and holding the worktree the workflow is about to salvage (US3-S3).
#:
#: The bound is derived from the attempt's own timeout so a multi-hour attempt
#: survives a multi-second Temporal blip (FR-008), but it is floored at five
#: beats so a short attempt never collapses below the beat it is bounding.
#: The worker's `max_heartbeat_throttle_interval` is set independently to keep
#: the actual cancellation latency small; without that cap, a 45-minute timeout
#: would let a killed agent bill for minutes.
_AGENT_HEARTBEAT_TIMEOUT_FLOOR = timedelta(seconds=5 * HEARTBEAT_INTERVAL_S)


def _agent_heartbeat_timeout(timeout_s: float) -> timedelta:
    """Heartbeat timeout for one attempt: half its deadline, floored at five beats."""
    return max(
        timedelta(seconds=timeout_s / 2),
        _AGENT_HEARTBEAT_TIMEOUT_FLOOR,
    )


@dataclass(frozen=True)
class EpicInput:
    """One epic's whole dispatch — the workflow's only argument.

    `graph` is the compiled artifact (never hand-authored, FR-011) and carries
    the epic's identity, its target repo and its specs root. `proxy_url` is where
    the agent's virtual key is honored. `config` is the ladder's caps, passed in
    rather than read so an operator's retry policy is a property of the epic they
    started (002's `VerificationConfig`). `poll_interval_s` is the usage-poll beat
    (R3). `landing_config` is the merge-queue's knobs — how a PASS node lands,
    how often a landing is polled, when a wait counts as stalled (US1).
    """

    graph: WorkGraph
    proxy_url: str
    config: VerificationConfig = VerificationConfig()
    poll_interval_s: int = DEFAULT_POLL_INTERVAL_S
    landing_config: LandingConfig = LandingConfig()
    #: 023 FR-003. The verification-step order the child epic must execute. It
    #: is part of dispatch so the operator clone's manifest pins it; a node
    #: worktree cannot move it. Defaults to today's order so every pre-023
    #: payload and every v1 repo replays identically.
    verify_order: tuple[str, ...] = ("gates", "diff_check", "judge")
    #: How many ready nodes the scheduler may have in flight at once (US1,
    #: FR-001/002). A property of the epic's dispatch — the machine's capacity,
    #: not the repo's — supplied at `ergane build start`. Defaulting to 1 is what
    #: makes SC-002 true by construction: an epic that does not ask for fan-out
    #: gets today's sequential behaviour exactly. Validated here as well as in
    #: the CLI, because `EpicInput` can be constructed without the CLI.
    max_concurrent_nodes: int = 1
    #: US4 FR-010: how many subscription-routed ready nodes may run at once.
    #: A subscription persona shares one operator credential, so virtual keys do
    #: not isolate concurrent attempts.  `None` (the default) means no additional
    #: subscription-specific cap: subscription-routed nodes are constrained only
    #: by `max_concurrent_nodes`.  A declared positive integer lower than that
    #: general cap caps subscription nodes specifically; a higher value is harmless
    #: because the general cap is still enforced first.
    max_concurrent_subscription_nodes: int | None = None
    #: 053 US3: the revision of the worker code that imported this workflow,
    #: captured once at worker boot and carried in the query answer. `None` when
    #: the worker predates this story or runs from a non-git tree. It is part of
    #: dispatch so the worker that will serve the epic advertises its own revision
    #: up front, and the query answer can return it without re-reading the tree.
    worker_revision: str | None = None


@dataclass(frozen=True)
class NodeStatus:
    """One node as an operator reads it (contracts/workflow.md § Query).

    Deliberately narrower than `NodeRecord`: the branch is what survives every
    sweep, the state and attempt are what a human is watching, and the attempt
    history is evidence that belongs in the store rather than in a status line.
    `landing_state` and `pr_number` are the landing's observable identity and
    where it stands — `None` until the node's ladder PASSes and a landing opens
    (US1, FR-009).
    """

    state: NodeState
    attempt: int
    branch: str
    #: Whether the node's ladder PASSed — the fact a `depends_on` edge opens on
    #: (FR-009). Distinct from `state`: a verified node advances off PASSED the
    #: moment its landing opens, so "can its verified-gated dependents run?" is
    #: answered by this flag, not by `state == PASSED`.
    verified: bool = False
    landing_state: LandingState | None = None
    pr_number: int | None = None
    #: US2: the queue history an operator reads when a landing is rejected, in
    #: order. Empty until the node has a landing with recorded outcomes.
    landing_history: tuple[ObservedOutcome, ...] = ()
    #: US2: how many recovery cycles have been spent on this landing.
    recovery_cycles: int = 0
    #: 069-US1: the ladder's own history for this node — the records
    #: `factory.verify.ladder` counts attempts and debugger cycles from. The
    #: docstring above says evidence belongs in the store, and it still does;
    #: this is not evidence but the *other half of a budget reading*. A rejection
    #: spends from two independent budgets, `recovery_cycles` is already here,
    #: and a reader who can see only one of the pair cannot tell a node that
    #: stopped being charged from one still dying of the other.
    history: tuple[AttemptRecord, ...] = ()
    #: 069-US1: how many free rebases this landing has taken — the bound on the
    #: path that spends neither budget (FR-004).
    free_rebases: int = 0
    #: 069-US1: what the latest rejection was classified as, `None` when the
    #: landing has not been rejected or predates the classification.
    rejection_cause: RejectionCause | None = None
    #: US1: the reason a node ended KILLED when the ladder did not produce it.
    #: Set only when a node coroutine crashed; otherwise None.
    terminal_reason: str | None = None
    #: US2: external-completion provenance, or None for agent-built work.
    provenance: str | None = None
    #: 068-US2: whether this node is parked on a human rather than working — an
    #: open escalation child, or the question park. The node's `state` cannot
    #: answer that on its own: a node awaiting an escalation reads `VERIFYING`,
    #: which is indistinguishable from gates actually running, and `ergane build
    #: reset` has to tell those two apart to refuse the second while succeeding
    #: against the first (FR-007). Defaults to False, so a query answered by a
    #: worker that predates the field reads as "working" and reset refuses —
    #: the safe direction, because the other one archives a live worktree.
    awaiting_operator: bool = False


@dataclass(frozen=True)
class EpicStatus:
    """The epic's whole observable state — the query's answer and the run's result.

    `nodes` is keyed by node id in declaration order, which is also scheduling
    order (R10), so reading the status top to bottom reads the epic in the order
    it was authored to run.
    """

    epic_state: EpicState
    nodes: dict[str, NodeStatus]
    #: 053 US3: the worker revision that produced this answer, captured at worker
    #: boot and carried unchanged through the epic's life. `None` when the worker
    #: recorded none.
    worker_revision: str | None = None


@dataclass(frozen=True)
class _Escalation:
    """One page to a human, and what came back.

    `resolution` is a plain string because it has four sources with one meaning:
    a button (`RETRY`/`KILL`/`PAUSE_EPIC`/`KILL_EPIC`), the store's `EXPIRED`, the fail-safe
    default applied when nobody was paged, and whatever the store reports when an
    expiry lost the race to a press. The ladder reads all four the same way.
    """

    escalation_id: str
    delivered: bool
    resolution: str


class _LaunchFailed(Exception):
    """A pre-first-token launch fault: the agent never started.

    Raised from `_attempt` when the adapter reports `AGENT_LAUNCH_FAILED`.  This
    is a workflow-internal signal, not an activity error to propagate: it tells
    `_run_node` to treat the node as launch-failed, outside the ordinary ladder.
    """


@workflow.defn
class EpicWorkflow:
    """One epic, from graph validation to every node terminal."""

    def __init__(self) -> None:
        #: Per-node bookkeeping in declaration order — the whole of the epic's
        #: state, and the reason replay needs no store to rebuild it.
        self._nodes: dict[str, NodeRecord] = {}
        self._epic_state = EpicState.RUNNING
        #: 053 US3: the revision of the worker that imported this workflow class,
        #: captured once at worker boot and supplied in `EpicInput`. `None` when
        #: the worker predates this story or runs outside a git checkout.
        self._worker_revision: str | None = None

        #: US4 FR-010: the registry snapshot, kept so the scheduler can tell
        #: subscription-routed nodes from gateway-routed ones when applying the
        #: per-subscription concurrency limit.  Filled during `_resolve`.
        self._personas: dict[str, Persona] = {}

        #: One background poll task per open landing, keyed by node id. Started
        #: when a PASS node's landing enqueues (US1) and reaped when the landing
        #: goes terminal. Deterministic under Temporal (`asyncio.ensure_future`
        #: inside the workflow): the poll loop is a timer-driven read, never a
        #: wall-clock one, so replay rebuilds it exactly.
        self._landing_tasks: dict[str, asyncio.Task[None]] = {}

        #: 041-US3: the epic buffers no operator answers of its own. Both
        #: lifecycles are children now, each owning its handler, buffer and
        #: timer — the 017 obstacle this removes.

        #: The steering wheel's whole state (FR-008). Two plain flags and no
        #: persistence: a signal is a history event, so replay rebuilds both
        #: exactly where the recorded run had them (R1).
        self._paused = False
        self._kill_requested = False

        #: 035-US1: buffered operator hand-backs `(node_id, branch, provenance)`.
        self._external_completions: list[tuple[str, str, str]] = []

    # --- signals and queries -------------------------------------------------

    @workflow.signal
    def pause_epic(self) -> None:
        """Stop dispatching; let the node in flight finish (contracts/workflow.md).

        Only the scheduler is suspended. The in-flight node keeps its ladder to
        the end — verdict recorded, key torn down, worktree salvaged and swept —
        because the key lease and the worktree are one bracket, and a node parked
        halfway through would hold an issued key against work nobody is doing
        (constitution V). Idempotent: pausing a paused epic is what an operator
        does when they are not sure the first one landed.
        """
        self._paused = True

    @workflow.signal
    def resume_epic(self) -> None:
        """Release the scheduler. A resume that arrives first simply never pauses."""
        self._paused = False

    @workflow.signal
    def kill_epic(self) -> None:
        """Stop the epic, in-flight attempt included (US3-S3).

        The one signal that interrupts an attempt: the flag is read both by the
        scheduler and by the running attempt's poll loop, which cancels the
        adapter within a heartbeat. Nothing here awaits or acts — a signal
        handler that ran the kill sequence would run it inside whatever workflow
        task delivered the signal, racing the node lifecycle it is trying to end.
        A kill is never taken back: no un-kill signal exists, because the keys
        are torn down and the worktrees swept by the time an operator could
        change their mind.
        """
        self._kill_requested = True

    @workflow.signal(name=EXTERNAL_COMPLETION_SIGNAL)
    def complete_node_externally(
        self, node_id: str, branch: str, provenance: str
    ) -> None:
        """Buffer an operator hand-back. Validation happens at the ladder decision."""
        self._external_completions.append((node_id, branch, provenance))

    @workflow.query
    def epic_status(self) -> EpicStatus:
        """What the CLI reads (FR-009). Read-only: no activity, no mutation."""
        return EpicStatus(
            epic_state=self._epic_state,
            nodes={
                node_id: NodeStatus(
                    state=record.state,
                    attempt=record.attempt,
                    branch=record.branch,
                    verified=record.verified,
                    landing_state=record.landing.state
                    if record.landing is not None
                    else None,
                    pr_number=record.landing.pr_number
                    if record.landing is not None
                    else None,
                    landing_history=record.landing.outcomes
                    if record.landing is not None
                    else (),
                    recovery_cycles=record.landing.recovery_cycles
                    if record.landing is not None
                    else 0,
                    terminal_reason=record.terminal_reason,
                    provenance=record.provenance,
                    history=tuple(record.history),
                    free_rebases=record.landing.free_rebases
                    if record.landing is not None
                    else 0,
                    rejection_cause=record.landing.rejection_cause
                    if record.landing is not None
                    else None,
                    # 068-US2: parked on a human, by either of the two ways a
                    # node can be. Derived rather than stored, so it cannot
                    # disagree with the park that set it.
                    awaiting_operator=(
                        record.pending_escalation_id is not None
                        or record.state == NodeState.WAITING_OPERATOR
                    ),
                )
                for node_id, record in self._nodes.items()
            },
            worker_revision=self._worker_revision,
        )

    # --- the main loop (R10) -------------------------------------------------

    @workflow.run
    async def run(self, request: EpicInput) -> EpicStatus:
        """Drive every node of the graph to a terminal state, in declaration order.

        Sequential by design: one node at a time, the first ready one in
        declaration order, re-evaluated after each terminal state. Parallel
        execution is deferred (spec § deferred), and this loop is where it would
        widen — the ready set is already computed, only the picker is narrow.
        """
        graph = request.graph
        # 053 US3: the worker revision is part of dispatch input, captured once at
        # worker boot, so the query answer can report the worker's revision without
        # re-reading the tree (which would always report the CLI's revision).
        self._worker_revision = request.worker_revision
        # The concurrency cap is validated here as well as in the CLI (FR-002):
        # `EpicInput` can be constructed without the CLI, so CLI-only validation
        # is not validation. A non-positive cap is a wiring error, not a dispatch
        # decision — fail the epic rather than silently serialise.
        if not isinstance(request.max_concurrent_nodes, int) or isinstance(
            request.max_concurrent_nodes, bool
        ) or request.max_concurrent_nodes < 1:
            raise ApplicationError(
                f"max_concurrent_nodes must be a positive integer, got "
                f"{request.max_concurrent_nodes!r}",
                type=GRAPH_INVALID,
                non_retryable=True,
            )
        # US4 FR-010: a declared subscription-specific limit must be a positive
        # integer, or absent.  An absent limit means "no additional cap beyond
        # max_concurrent_nodes"; a present one caps subscription-routed nodes
        # specifically.
        if request.max_concurrent_subscription_nodes is not None and (
            not isinstance(request.max_concurrent_subscription_nodes, int)
            or isinstance(request.max_concurrent_subscription_nodes, bool)
            or request.max_concurrent_subscription_nodes < 1
        ):
            raise ApplicationError(
                f"max_concurrent_subscription_nodes must be a positive integer or "
                f"None, got {request.max_concurrent_subscription_nodes!r}",
                type=GRAPH_INVALID,
                non_retryable=True,
            )
        # US3 onboarding gate (FR-010, SC-005): the target repo must conform to
        # the factory's assumptions — public, merge queue enabled on the default
        # branch, required checks matching factory.yaml's gates — before a single
        # key is issued or worktree created. A failing profile fails the epic
        # here, with its findings carried in the failure message so the operator
        # is told exactly what to change. Checked at every epic start, never
        # cached (spec § US3 IT).
        await self._onboard_target(graph)
        resolved = await self._resolve(graph)
        # US4 FR-010: a stable lookup from node id to persona name so the
        # scheduler can count in-flight subscription-routed nodes without recomputing
        # it on every dispatch decision.
        self._persona_by_node_id = {item.node.id: item.node.persona for item in resolved}
        # The one persona no node names, read in the same breath as the graph and
        # under the same snapshot rule: an epic with nobody to score its stories
        # fails here, not four attempts and one spent key later.
        judge = await workflow.execute_activity(
            resolve_persona, ResolvePersonaInput(persona=JUDGE_PERSONA), **_FAST
        )

        self._nodes = {
            item.node.id: NodeRecord(
                node_id=item.node.id,
                branch=branch_name(graph.epic_id, item.node.id),
            )
            for item in resolved
        }

        # The epic's authored text, read once: every node's prompt is cut from
        # these bytes, so a spec edited mid-epic reaches the next epic and not
        # this one (002 FR-010's discipline, applied to prompts).
        sources = await workflow.execute_activity(
            load_prompt_sources,
            LoadPromptSourcesInput(
                specs_root=graph.specs_root,
                feature=graph.feature,
                target_repo=graph.target_repo,
            ),
            **_FAST,
        )

        #: The nodes currently in flight, keyed by node id. The scheduler starts
        #: a `_run_node` task for each ready node while a slot is free, then
        #: parks on a task finishing (or a kill/pause arriving) and recomputes
        #: the ready set against the state that completion left behind (FR-001,
        #: FR-003). `asyncio.create_task` is the SDK's deterministic concurrency
        #: primitive — the same one the landing polls already use — so the fan-out
        #: replays identically (SC-001).
        in_flight: dict[str, asyncio.Task[None]] = {}

        while True:
            if self._kill_requested:
                break
            if self._paused:
                # Pause stops dispatch and lets every in-flight node finish its
                # ladder — the key lease and the worktree are one bracket, and a
                # node parked halfway would hold an issued key against work
                # nobody is doing (constitution V). The node that *raised* the
                # pause (a PAUSE_EPIC escalation) sets the flag from inside its
                # own `_run_node` before that task is done, so the scheduler must
                # drain the in-flight set — reaping each task as it reaches its
                # terminal state and applying the lock-out its ending demands
                # — *before* it parks, or a dependent whose dependency just
                # failed is left PENDING through the pause instead of KILLED
                # (FR-009). Polling keeps running (passive) so an in-flight
                # landing is not left parked on a live queue, but recovery
                # dispatch waits for resume (US1).
                await self._drain_in_flight(in_flight, resolved)
                self._epic_state = EpicState.PAUSED
                # 008-US2: a question park is paused the same way a PAUSE_EPIC
                # press pauses, but its resume is time-based (the question's 8h
                # expiry) rather than signal-based, and a `wait_condition` with
                # no timeout creates no timer — so the time-skipping test
                # environment cannot advance the clock past the parked wait, and
                # the expiry never fires. The parked node's own `wait_condition`
                # carries the 8h timeout that expires it; the scheduler's wait
                # needs *a* timer too, so the environment can skip the window. A
                # bounded re-wait loop lets the clock advance without changing
                # the resume semantics: the condition is still `not _paused`,
                # and a timeout just re-evaluates it. (PAUSE_EPIC's resume is a
                # signal, which lands as an activation and re-evaluates the
                # condition before any timeout matters.)
                while self._paused and not self._kill_requested:
                    try:
                        await workflow.wait_condition(
                            lambda: not self._paused or self._kill_requested,
                            timeout=timedelta(seconds=QUESTION_TIMEOUT_S),
                        )
                    except asyncio.TimeoutError:
                        continue
                if not self._kill_requested:
                    self._epic_state = EpicState.RUNNING
                continue

            # Fill every free slot with a ready node. The ready set is read
            # fresh each pass — never cached across a completion — so a node
            # whose dependency just failed is not dispatched (FR-003, SC-003).
            # A REJECTED landing is a recovery, not a fresh dispatch: it routes
            # through `_run_recovery` (sync → debugger → re-verify → re-enqueue,
            # or escalate), which is the path the queue rejection came in on
            # (US2). Routing it through `_run_node` would re-issue a key and run
            # a fresh agent against a tree that already verified — the wrong
            # kind of work, charged to the wrong rung — so the scheduler picks
            # the handler the same way the base loop did, only now N of either
            # may be in flight at once.
            for item in self._ready_set(resolved):
                if self._kill_requested:
                    break
                if len(in_flight) >= request.max_concurrent_nodes:
                    break
                if item.node.id in in_flight:
                    continue
                # US4 FR-010: a declared subscription-specific cap bounds how many
                # subscription-routed nodes may be in flight at once.  When no limit
                # is declared, subscription nodes are constrained only by the
                # general cap above.  A non-subscription node that appears later in
                # the ready set still gets its slot, so this check is a `continue`
                # rather than a `break`.
                if self._is_subscription_node(item.node.persona):
                    limit = request.max_concurrent_subscription_nodes
                    if limit is not None:
                        subscription_in_flight = self._subscription_nodes_in_flight(
                            in_flight
                        )
                        if subscription_in_flight >= limit:
                            continue
                landing = self._nodes[item.node.id].landing
                if landing is not None and landing.state == LandingState.REJECTED:
                    in_flight[item.node.id] = asyncio.create_task(
                        self._run_recovery(item, request, sources, judge)
                    )
                else:
                    in_flight[item.node.id] = asyncio.create_task(
                        self._run_node(item, request, sources, judge)
                    )

            if not in_flight:
                # No recovery pending and no fresh node ready. That is only the
                # epic's end when every landing is terminal (MERGED or KILLED);
                # a landing still riding the queue — or about to be rejected into
                # a recovery — parks the scheduler until the queue is done with
                # it (US1-S4), and a REJECTED landing wakes it into a recovery.
                if self._all_landings_terminal():
                    break
                await workflow.wait_condition(
                    lambda: self._all_landings_terminal()
                    or self._next_recovery(resolved) is not None
                    or self._kill_requested
                )
                continue

            # Park on the first in-flight node to reach a terminal state (or a
            # kill/pause arriving). `wait_condition` re-evaluates on every
            # activation, so a completion is picked up the moment it lands and a
            # slot frees immediately (FR-001). The predicate is a pure function
            # of task state and the kill/pause flags, so it replays identically.
            await workflow.wait_condition(
                lambda: any(task.done() for task in in_flight.values())
                or self._kill_requested
                or self._paused
            )

            # Reap every finished task, release its slot, and apply the lock-out
            # its terminal state demands — scoped to that node's dependents, so
            # unrelated in-flight nodes are never touched (FR-009). The ready set
            # is recomputed on the next pass against the state this left behind.
            for node_id, task in list(in_flight.items()):
                if not task.done():
                    continue
                await self._reap_finished(node_id, task, in_flight, resolved)

        if self._kill_requested:
            # Kill outranks the ladder: every in-flight node closes its own
            # bracket on the way out — its `_attempt` sees `_kill_requested` in
            # the `wait_condition`, cancels its adapter, and runs teardown +
            # salvage before returning (constitution VI). `task.cancel()` would
            # interrupt that bracket at whatever `await` it was parked on and
            # skip teardown, so the scheduler does NOT cancel: it waits for each
            # in-flight task to finish itself, reaping each so the lock-out a
            # killed node's dependents need is applied (FR-009). A kill that
            # salvages three of four nodes is a lost-work bug; this is the guard.
            await self._drain_in_flight(in_flight, resolved)
            await self._kill_landings(graph.target_repo)
            self._kill_remaining()
            self._epic_state = EpicState.KILLED
        else:
            self._epic_state = EpicState.COMPLETED
        return self.epic_status()

    async def _onboard_target(self, graph: WorkGraph) -> None:
        """Validate the target repo before anything dispatches (FR-010, SC-005).

        The onboarding gate is structural and live at every epic start: it reads
        the repo's visibility, merge-queue rule and required checks via the
        `validate_target_repo` activity, and its `factory.yaml` through the 002
        loader. A failing profile fails the epic here — before `resolve_graph`,
        before any key is issued, before any worktree is prepared — with its
        findings rendered into the failure message so the operator is told which
        check failed and how to fix it. There is no caching: onboarding is a
        property of a repo that can change between epics, so it is re-read every
        time (spec § US3 IT).
        """
        profile: TargetRepoProfile = await workflow.execute_activity(
            validate_target_repo,
            ValidateTargetRepoInput(target_repo=graph.target_repo),
            **_FAST,
        )
        if not profile.passed:
            findings = "\n".join(
                f"  [{('PASS' if f.passed else 'FAIL')}] {f.check}: {f.detail}"
                for f in profile.findings
            )
            raise ApplicationError(
                f"target repo {graph.target_repo} failed onboarding; nothing "
                f"dispatches against an unvalidated repo:\n{findings}",
                type=GRAPH_INVALID,
                non_retryable=True,
            )

    async def _resolve(self, graph: WorkGraph) -> list[ResolvedNode]:
        """Validate the graph against the persona registry, or fail the epic.

        The rejection is re-raised as the workflow's own failure carrying the
        validator's message verbatim, because that message names the offending
        node and an `ActivityError`'s does not: an operator holding a ten-node
        epic needs "node 'us2' depends on 'us7', which is not a declared node",
        not "Activity task failed". Failing the workflow — rather than any node —
        is the honest shape: an epic that cannot be scheduled has no node to
        charge it to.
        """
        try:
            resolved = await workflow.execute_activity(resolve_graph, graph, **_FAST)
        except ActivityError as exc:
            invalid = exc.cause
            if isinstance(invalid, ApplicationError) and invalid.type == GRAPH_INVALID:
                raise ApplicationError(
                    invalid.message, type=GRAPH_INVALID, non_retryable=True
                ) from exc
            raise

        # US4 FR-010: keep the registry snapshot for the scheduler's subscription
        # concurrency bound.  `_run_node` also uses it to pass the resolved agent
        # value to key issuance and the adapter.
        self._personas = {item.node.persona: self._resolve_persona(item.node.persona) for item in resolved}
        return resolved

    def _resolve_persona(self, persona_name: str) -> Persona | None:
        """Read one registry entry by name, returning None if it cannot be loaded.

        This is a workflow-side helper only: the authoritative read happens in
        `resolve_graph`.  We use it to recover the `agent` value for nodes
        because `ResolvedNode` intentionally does not carry it (constitution VII:
        only the model alias crosses the boundary).  A missing registry is handled
        gracefully because `_is_subscription_node` tolerates None.
        """
        from factory.config import load_personas

        try:
            registry = load_personas()
        except Exception:
            return None
        return registry.get(persona_name)

    def _is_subscription_node(self, persona_name: str) -> bool:
        """Whether a node routed to this persona runs against the operator's subscription.

        The registry snapshot is filled during `_resolve`; an unknown persona is
        treated as non-subscription so a routing misconfiguration fails the node
        on its own terms rather than being silently counted here.
        """
        persona = self._personas.get(persona_name)
        return persona is not None and persona.agent == SUBSCRIPTION_AGENT

    def _subscription_nodes_in_flight(
        self, in_flight: dict[str, asyncio.Task[None]]
    ) -> int:
        """How many in-flight nodes are routed through the operator's subscription."""
        return sum(
            1
            for node_id in in_flight
            if self._is_subscription_node(self._persona_by_node_id.get(node_id, ""))
        )

    def _next_recovery(self, resolved: Sequence[ResolvedNode]) -> ResolvedNode | None:
        """The first node whose landing is REJECTED and pending a recovery cycle.

        A rejection parks the node (`landing.state == REJECTED`) but never makes
        it terminal — the recovery routing (US2) owns what happens next. Recovery
        outranks a fresh PENDING node in the scheduler: stranded verified work is
        the more expensive kind of idle (plan.md § US2). Declaration order is the
        tiebreak, so recovery order is the authored order (R10).
        """
        for item in resolved:
            landing = self._nodes[item.node.id].landing
            if landing is not None and landing.state == LandingState.REJECTED:
                return item
        return None

    def _ready_set(self, resolved: Sequence[ResolvedNode]) -> list[ResolvedNode]:
        """Every node the scheduler may dispatch right now, in dispatch order.

        Recovery outranks fresh dispatch (plan.md § US2): a REJECTED landing is
        verified work that must not sit idle while independent fresh nodes run.
        Within each class, declaration order is the visible tiebreak whenever
        more than one node is ready, and the deriver emits stories in spec order,
        so the spec author's sequencing is what an operator sees run (R10).

        Two kinds of edge, distinguished by what unlocks them (FR-009): a
        `depends_on` edge unlocks when the dependency is *verified* — its ladder
        PASSed, `record.verified` — while a `depends_on_merged` edge unlocks only
        when the dependency has *merged*, `state == MERGED`. A verified but
        still-enqueued dependency therefore releases its verified-gated
        dependents while its own landing is still riding the queue (US1-S4).

        The set is a pure function of graph data and node state, so it is
        replay-identical (SC-001) — and it is recomputed against current state
        every time a slot frees, never cached across a completion, so a node
        whose dependency just failed cannot slip through the gap (FR-003,
        SC-003).
        """
        ready: list[ResolvedNode] = []
        for item in resolved:
            landing = self._nodes[item.node.id].landing
            if landing is not None and landing.state == LandingState.REJECTED:
                ready.append(item)
        for item in resolved:
            if self._nodes[item.node.id].state != NodeState.PENDING:
                continue
            if self._edges_satisfied(item.node):
                ready.append(item)
        return ready

    def _edges_satisfied(self, node: WorkNode) -> bool:
        """Whether every one of `node`'s two edge kinds is unlocked (FR-009)."""
        if not all(
            self._nodes[dependency].verified
            for dependency in node.depends_on
        ):
            return False
        if not all(
            self._nodes[dependency].state == NodeState.MERGED
            for dependency in node.depends_on_merged
        ):
            return False
        return True

    def _lock_out_dependents(self, resolved: Sequence[ResolvedNode]) -> None:
        """Kill what can no longer be dispatched, transitively (SC-002, FR-009).

        Run the moment a node ends anything but PASSED — and, for merge-gated
        dependents, the moment a dependency's landing ends terminal-but-unmerged
        (`REJECTED`-final, `KILLED`). A dependent is marked KILLED without a
        worktree, a key or an attempt — the edge stayed locked, so there is
        nothing to salvage and nothing to sweep — and the pass repeats until it
        settles, because a chain three deep dies all at once.

        A verified-gated dependent (already dispatched once the dependency
        verified) is never touched here: its dispatch happened on `verified`, not
        on the landing. Only a merge-gated dependent still waiting for MERGED can
        be locked out by a landing that will never merge.
        """
        settled = False
        while not settled:
            settled = True
            for item in resolved:
                record = self._nodes[item.node.id]
                if record.state != NodeState.PENDING:
                    continue
                if self._dead_edge(item.node):
                    record.state = NodeState.KILLED
                    settled = False

    def _dead_edge(self, node: WorkNode) -> bool:
        """Whether any of `node`'s dependencies can never satisfy its edge."""
        if any(
            self._nodes[dependency].state in _UNREACHABLE
            for dependency in node.depends_on
        ):
            return True
        # A merge-gated dependency's edge is dead when it can no longer merge:
        # it ended FAILED/KILLED outright, or its landing ended terminal without
        # merging. A verified dependency still riding the queue might still merge.
        for dependency in node.depends_on_merged:
            record = self._nodes[dependency]
            if record.state in _UNREACHABLE or self._landing_unmerged_terminal(
                dependency
            ):
                return True
        return False

    def _landing_unmerged_terminal(self, node_id: str) -> bool:
        """Whether a node's landing ended terminal without merging (FR-009)."""
        landing = self._nodes[node_id].landing
        return (
            landing is not None
            and landing.state in _LANDING_TERMINAL
            and landing.state != LandingState.MERGED
        )

    def _all_landings_terminal(self) -> bool:
        """Whether every open landing has reached a terminal state.

        The main loop's second exit condition (US1-S4): an epic whose nodes are
        all terminal is not done until the queue has finished with every landing
        it was given. A node with no landing (never verified, killed, failed) owes
        nothing here.
        """
        return all(
            record.landing is None or record.landing.state in _LANDING_TERMINAL
            for record in self._nodes.values()
        )

    async def _drain_in_flight(
        self,
        in_flight: dict[str, "asyncio.Task[None]"],
        resolved: Sequence[ResolvedNode],
    ) -> None:
        """Wait for every in-flight node to finish, reaping each as it does.

        Used by the pause and the kill paths, which both need the in-flight set
        empty and every finished node's lock-out applied *before* they take their
        next step: a pause parks the scheduler (so the drain must run first, or
        a node that raised the pause mid-`_close_out` is left un-reaped and its
        dependents stay PENDING through the pause), and a kill waits for the
        epic's last bracket to close before it accounts for the rest.

        Each `_run_node` closes its own bracket — teardown, salvage — on its way
        out, so the drain only reaps: it waits on a task finishing, releases the
        slot, and applies the lock-out a non-PASSED terminal demands (FR-009).
        It does NOT cancel the tasks: cancelling would interrupt `_run_node` at
        whatever `await` it was parked on and skip teardown (constitution VI).
        The predicate is a pure function of task state, so it replays
        identically (SC-005).

        008-US2: a node parked on an operator question (WAITING_OPERATOR) is
        in-flight but not done — its `_run_node` is parked in a `wait_condition`
        for the answer, holding its slot for up to the question's 8h window. The
        drain must not wait on it: doing so would deadlock the pause (the task is
        alive by design). Such a node stays in `in_flight` across the pause and
        is reaped when its answer (or expiry) ends its `_run_node`. The pause's
        `wait_condition(not self._paused)` is what parks the scheduler while the
        parked node waits.
        """
        drainable = {
            node_id: task
            for node_id, task in in_flight.items()
            if self._nodes[node_id].state != NodeState.WAITING_OPERATOR
        }
        while drainable:
            await workflow.wait_condition(
                lambda: any(task.done() for task in drainable.values())
            )
            for node_id, task in list(drainable.items()):
                if not task.done():
                    continue
                await self._reap_finished(node_id, task, in_flight, resolved)
                del drainable[node_id]

    async def _reap_finished(
        self,
        node_id: str,
        task: "asyncio.Task[None]",
        in_flight: dict[str, "asyncio.Task[None]"],
        resolved: Sequence[ResolvedNode],
    ) -> None:
        """Release a finished node's slot and apply its lock-out.

        The task's outcome is retrieved rather than discarded: a node coroutine that
        raises ends here. `except Exception` is deliberate — `asyncio.CancelledError`
        derives from `BaseException`, so a bare `Exception` handler lets cancellation
        through (FR-006). The kill path deliberately never cancels node tasks so each
        closes its own bracket; treating cancellation as a recorded crash would defeat
        that design.
        """
        del in_flight[node_id]
        try:
            task.result()
        except Exception as exc:
            record = self._nodes[node_id]
            record.state = NodeState.KILLED
            record.terminal_reason = str(exc)
            workflow.logger.exception(
                "node %s coroutine raised; ended KILLED", node_id
            )
        if self._nodes[node_id].state != NodeState.PASSED:
            self._lock_out_dependents(resolved)

    async def _kill_landings(self, target_repo: str) -> None:
        """Take every open landing out of the queue and stop polling it (US1).

        Kill's landing half: cancel each background poll task, ask the queue to
        disable auto-merge best-effort (FR-008 — a killed epic must not keep
        landing, and a failure to de-queue is surfaced, not fatal), and mark each
        open landing KILLED. Branches are never removed — the branch is the
        queue's to land and outlives the kill (FR-008).
        """
        for node_id, task in list(self._landing_tasks.items()):
            task.cancel()
        self._landing_tasks.clear()
        for record in self._nodes.values():
            landing = record.landing
            if landing is None or landing.pr_number is None:
                continue
            if landing.state in _LANDING_TERMINAL:
                continue
            try:
                await workflow.execute_activity(
                    disable_auto_merge,
                    DisableAutoMergeInput(
                        pr_number=landing.pr_number,
                        target_repo=target_repo,
                    ),
                    **_GIT,
                )
            except ActivityError:
                # Best-effort: a queue that is down while the epic dies is not a
                # reason the kill sequence itself fails (FR-008). The landing is
                # marked KILLED regardless; a human seeing the status knows.
                pass
            record.landing = replace(landing, state=LandingState.KILLED)

    def _kill_remaining(self) -> None:
        """Account for every node the kill caught short (US3-S3).

        A node that never dispatched has no worktree to salvage and no key to
        tear down — the node the kill *interrupted* did both on its way out, in
        its own lifecycle — so this is bookkeeping alone: the status an operator
        reads after a kill names every node in the graph, and none of them is
        left claiming to be pending an epic that has stopped.
        """
        for record in self._nodes.values():
            if record.state not in _TERMINAL_STATES:
                record.state = NodeState.KILLED

    # --- one node's life ----------------------------------------------------

    async def _run_node(
        self,
        resolved: ResolvedNode,
        request: EpicInput,
        sources: PromptSources,
        judge: ResolvedPersona,
    ) -> None:
        """One node from dispatch to terminal state (contracts/workflow.md).

        Criteria and the worktree are taken once, before the first attempt: the
        goalposts are fixed for the node's whole life (002 FR-010) and every
        attempt — the debugger's included — opens the tree the previous attempt
        left behind (FR-013). Everything inside the attempt loop is per-attempt
        by construction: a fresh key, a fresh prompt, a fresh session id.
        """
        graph = request.graph
        node = resolved.node
        record = self._nodes[node.id]

        criteria = await workflow.execute_activity(
            snapshot_criteria,
            SnapshotCriteriaInput(
                specs_root=graph.specs_root,
                feature=graph.feature,
                spec_ref=node.spec_ref,
                requirement_keys=list(node.requirement_keys),
            ),
            **_FAST,
        )
        prepared = await workflow.execute_activity(
            prepare_worktree,
            PrepareWorktreeInput(
                epic_id=graph.epic_id,
                node_id=node.id,
                target_repo=graph.target_repo,
                standards=sources.standards,
            ),
            **_GIT,
        )
        record.base_ref = prepared.base_ref
        # The recovery re-entry (US2) re-verifies this same tree against this same
        # pin and these same goalposts, so they live on the record rather than
        # only in this method's locals.
        record.prepared = prepared
        record.criteria = criteria

        # 035-US1: a PENDING node has no ladder outcome; any buffered signal is refused.
        await self._refuse_buffered_external_completions(
            graph.epic_id, node.id, reason="node ladder has not run"
        )

        results: list[VerificationResult] = []
        evidence: list[AttemptEvidence] = []
        persona = node.persona
        #: Set by a `PAUSE_EPIC` press: the node ends parked rather than
        #: abandoned, and the epic stops. Nothing else in the ladder's
        #: vocabulary distinguishes the two, because nothing else has to — a
        #: per-node decision cannot say "and stop the epic".
        parked = False
        #: The classification the node ends with if a kill lands before any
        #: attempt reports one of its own.
        termination = Termination.KILLED
        #: The judge's last objection, carried across attempts rather than to
        #: the next one only: an attempt that failed its gates never reached the
        #: judge, and what the judge last asked for is still the thing being
        #: answered (002 R4).
        prior_feedback: str | None = None

        while True:
            if self._kill_requested:
                # Between two attempts, with the previous one's bracket already
                # closed: the kill outranks whatever the ladder was about to
                # grant, and no key is issued for an attempt nobody will read.
                action = NextAction.KILLED
                break

            record.attempt += 1
            # Pure, and built from workflow state alone: the same inputs on a
            # replay produce the same bytes, so a replayed attempt is handed the
            # prompt the first one was (FR-006, R9).
            prompt = build_attempt_prompt(
                node=node,
                epic_id=graph.epic_id,
                spec_text=sources.spec_text,
                plan_text=sources.plan_text,
                tasks_text=sources.tasks_text,
                standards=sources.standards,
                prior_attempts=evidence,
                operator_answer=record.operator_answer,
            )
            # 008-US2: the operator answer is consumed by this one attempt's
            # prompt, then cleared so a *second* question on the same node
            # starts from a clean prompt — the answer is the operator's reply
            # to the *previous* question, not a standing instruction. The
            # expiry path never sets it, so an expired question's retry gets no
            # answer section (the operator never engaged, FR-004).
            record.operator_answer = None

            # Resolve the persona registry entry for this node so key issuance
            # and the adapter both know whether this attempt routes through the
            # gateway or the operator's subscription (US2 FR-005).
            persona_entry = self._personas.get(node.persona)
            agent = persona_entry.agent if persona_entry is not None else ""

            lease = await workflow.execute_activity(
                issue_attempt_key,
                IssueKeyInput(
                    node_id=node.id,
                    epic_id=graph.epic_id,
                    attempt=record.attempt,
                    # The debugger's spend is the debugger's (constitution V);
                    # the aliases it may call are still the node's, because the
                    # registry snapshot covers graph nodes and inventing a
                    # second resolution here would be a second source of truth.
                    persona=persona,
                    spec_ref=node.spec_ref,
                    models=list(resolved.models),
                    agent=agent,
                ),
                start_to_close_timeout=_PROXY["start_to_close_timeout"],
                retry_policy=_ISSUE_KEY_RETRIES,
            )
            record.state = NodeState.KEY_ISSUED
            # A snapshot of some earlier attempt's key is not this attempt's
            # fallback figure: teardown would attribute another attempt's spend.
            record.last_snapshot = None
            teardown_done = False
            try:
                adapter_result = await self._attempt(
                    record,
                    lease,
                    AttemptContext(
                        epic_id=graph.epic_id,
                        node_id=node.id,
                        attempt=record.attempt,
                        prompt=prompt,
                        worktree_path=prepared.path,
                        home_path=str(home_path(DEFAULT_FACTORY_ROOT, graph.epic_id, node.id)),
                        proxy_url=request.proxy_url,
                        virtual_key=lease.key,
                        model_alias=resolved.model_alias,
                        session_id=str(workflow.uuid4()),
                        timeout_s=resolved.timeout_s,
                        context_window=resolved.context_window,
                        target_repo=graph.target_repo,
                        agent=agent,
                    ),
                )
                # `None` is the attempt the kill cancelled: the adapter re-raises on
                # its KILLED path rather than reporting a termination the workflow
                # could mistake for an ending (R2), so the classification is the
                # workflow's own — it is the one that asked.
                if adapter_result is not None:
                    termination = adapter_result.termination

                if self._kill_requested:
                    # The bracket still closes — FR-004 is about every attempt that
                    # was *opened* — but nothing is verified: a two-hour gate suite
                    # against a worktree nobody will read is the opposite of
                    # stopping, and the node ends KILLED whatever the gates say.
                    action = NextAction.KILLED
                    break

                # 008-US1: the narrowest hole in D-018/FR-012. The marker is the one
                # agent-authored signal that reaches node state, and its only effect
                # is to park — never to grade. Detection is a read-only scan over the
                # archived stdout.log the adapter streams on every termination path
                # (the transcript_path the adapter just returned), so it runs before
                # the gates and the judge are consulted: a QUESTION attempt has
                # nothing to grade, and consulting them would let the marker
                # influence the verdict path (FR-010).
                if adapter_result is not None:
                    marker = await workflow.execute_activity(
                        detect_operator_question_activity,
                        DetectQuestionInput(
                            transcript_path=adapter_result.transcript_path
                        ),
                        **_FAST,
                    )
                    if marker.is_question:
                        termination = Termination.QUESTION
                        # Salvage runs under _close_out on every terminal path
                        # (constitution VI, FR-005/006) — a question attempt is a
                        # terminal like any other, so the committed work survives on
                        # the branch and the ledger row carries the real usage.
                        # The attempt key is torn down before the park, not left
                        # open across a wait that may last hours or never resume: a
                        # parked question closes the bracket for this attempt; the
                        # next attempt after an answer or expiry mints a fresh key
                        # (FR-007/FR-008, 008-US2). Salvage runs here so committed
                        # work survives, but the worktree must *not* be removed yet
                        # — a parked question is non-terminal, and `_drain_in_flight`
                        # leaves it in-flight across the pause so an answer can
                        # resume on the same tree.
                        await workflow.execute_activity(
                            salvage_worktree,
                            SalvageWorktreeInput(
                                epic_id=graph.epic_id,
                                node_id=node.id,
                                termination=termination,
                                attempt=record.attempt,
                            ),
                            **_GIT,
                        )
                        # The question ships once, attributed to its epic/node/attempt
                        # (FR-002). The send happens after salvage, so the branch the
                        # operator might be asked about is the one the question names.
                        #
                        # 041-US3: the lifecycle is a `QuestionWorkflow` now — send,
                        # ferry dedup, the 8h window and the signal are all its, and
                        # its row names *it*, so a reply reaches what is waiting.
                        question = await workflow.start_child_workflow(
                            QuestionWorkflow.run,
                            QuestionRequest(
                                epic_id=graph.epic_id,
                                node_id=node.id,
                                attempt=record.attempt,
                                question_text=marker.text,
                                timeout_s=QUESTION_TIMEOUT_S,
                            ),
                            id=child_correlation_id(),
                        )
                        # Park the node and pause the epic — the operator's answer
                        # (US2) is what un-parks it. WAITING_OPERATOR is non-terminal
                        # and not a dead edge, so dependents stay PENDING; the pause
                        # stops the scheduler from dispatching anything else while it
                        # waits, the way a PAUSE_EPIC press does. Unlike PAUSE_EPIC,
                        # the node's `_run_node` task stays alive — parked in the
                        # `wait_condition` below for the answer or the question's own
                        # 8h window — so `_drain_in_flight` leaves it in-flight across
                        # the pause (a parked question is not a bracket to close), and
                        # the scheduler's `wait_condition(not self._paused)` is what
                        # idles while it waits. The node clears the pause itself on
                        # un-park, the way it set it on park.
                        record.state = NodeState.WAITING_OPERATOR
                        record.pending_question_id = question.id
                        self._paused = True
                        # Close the attempt key before the long wait: the park is
                        # non-terminal and may outlive this workflow activation, so
                        # teardown must run while the event loop is still present.
                        # The next attempt mints a fresh key on answer or expiry.
                        await self._teardown(lease, termination, record.last_snapshot)
                        teardown_done = True
                        # 008-US2: wait for the child to settle or for an operator's
                        # kill. The child owns the window (the question's own 8h, not
                        # the escalation hour, FR-004) and the signal; the kill is
                        # watched here because it is the *epic's* stop. `Task.done()`
                        # is a pure read, so this replays identically.
                        await workflow.wait_condition(
                            lambda: question.done() or self._kill_requested
                        )
                        if not question.done():
                            # A kill landed while parked. Cancel the child so its 8h
                            # timer dies with the park — the row stays pending, as it
                            # did when the epic's own wait was abandoned — and leave
                            # the node parked for the post-loop. Do not expire or
                            # answer: a stopped epic is neither a reply nor a burn.
                            question.cancel()
                            action = NextAction.KILLED
                            break
                        answered = await question
                        if not answered.answered:
                            # The operator never engaged; the child expired the row.
                            # Re-enter the ladder as a FAIL — the one case where a
                            # question burns a slot (FR-001/FR-004), because the node
                            # cannot park forever and the attempt that asked consumed
                            # a key. The FAIL `AttemptRecord` is what `_attempts_spent`
                            # counts, so appending it here is what consumes the slot.
                            record.history.append(
                                AttemptRecord(
                                    attempt=record.attempt,
                                    persona=persona,
                                    verdict=OverallVerdict.FAIL,
                                )
                            )
                        else:
                            # The operator answered. Carry the exchange verbatim into
                            # the next attempt's prompt under a dedicated section
                            # (FR-003) — the question the agent asked and the answer the
                            # operator gave, read as the operator's decision. No
                            # `AttemptRecord` is appended: the QUESTION attempt broke
                            # the loop before the history append, so `_attempts_spent`
                            # excludes it by construction and the answer costs no slot
                            # (FR-001). The retry re-enters the ladder with the same
                            # budget it had before the question.
                            record.operator_answer = OperatorAnswer(
                                question_text=marker.text,
                                answer_text=answered.answer_text,
                            )
                        # An answer or an expiry un-parks the node: an answer
                        # re-dispatches with the exchange in the prompt, an expiry
                        # re-enters the ladder as a FAIL. Clear the pause the park set
                        # (the scheduler is parked on `not self._paused`) and `continue`
                        # the `while True` loop, which increments `record.attempt` and
                        # builds a fresh prompt — so the answer attempt gets the next
                        # number naturally and the expiry's FAIL is already in history
                        # for the ladder to count. (The kill path above `break`s, leaving
                        # the pause set so the scheduler stays parked too.)
                        record.pending_question_id = None
                        self._paused = False
                        continue

                    record.state = NodeState.VERIFYING
                result, verdict = await self._verify(
                    request,
                    resolved,
                    criteria,
                    prepared,
                    record.attempt,
                    judge,
                    prior_feedback,
                )
                if verdict is not None and verdict.feedback:
                    prior_feedback = verdict.feedback
                results.append(result)
                evidence.append(
                    AttemptEvidence(termination=termination, result=result)
                )
                record.history.append(
                    AttemptRecord(
                        attempt=record.attempt,
                        persona=persona,
                        verdict=result.verdict,
                        judge_outcome=None if result.judge is None else result.judge.outcome,
                    )
                )

                action = next_action(
                    record.history, request.config, escalations=record.escalations
                )
                if action == NextAction.ESCALATE:
                    # 035-US1: the ladder is exhausted. Offer the operator hand-back
                    # precedence over paging: if a completion is buffered, verify it.
                    external_action = await self._apply_external_completion_if_present(
                        record, request, resolved, criteria, prepared, judge, results, evidence, termination
                    )
                    if external_action is not None:
                        action = external_action
                    else:
                        escalation = await self._escalate(graph, node, results, request.config)
                        if escalation is None:
                            # 068-US2: the epic was stopped with the page open.
                            # No resolution exists, so none is recorded — the
                            # node ends KILLED the way every in-flight node a
                            # kill catches does, through its own bracket.
                            action = NextAction.KILLED
                            break
                        record.escalations.append(escalation.resolution)
                        if escalation.resolution == EscalationChoice.PAUSE_EPIC:
                            # The press the ladder can only half answer: it ends the
                            # node (as every non-grant does), and the epic-level half —
                            # park rather than abandon, and stop dispatching — is this
                            # component's to supply (contracts/workflow.md).
                            parked = True
                            self._paused = True
                        elif escalation.resolution == EscalationChoice.KILL_EPIC:
                            # 068 FR-008's other half. The ladder ends this node
                            # (every non-grant does); ending the *epic* is the
                            # same epic-level supply PAUSE_EPIC gets, one step
                            # further — the scheduler's own stop, so every
                            # sibling's open page is cancelled and every
                            # undispatched node is accounted for by the kill
                            # sequence rather than dispatched into a dead epic.
                            self._kill_requested = True
                        action = next_action(
                            record.history, request.config, escalations=record.escalations
                        )
                        if action == NextAction.ESCALATE:
                            # 035-US1: one more hand-back chance before KILLED.
                            external_action = await self._apply_external_completion_if_present(
                                record, request, resolved, criteria, prepared, judge, results, evidence, termination
                            )
                            action = external_action if external_action is not None else NextAction.KILLED

                # 035-US1: non-exhausted nodes refuse any buffered signal.
                if action not in _TERMINAL_ACTIONS:
                    await self._refuse_buffered_external_completions(
                        graph.epic_id, node.id, reason="node ladder not exhausted"
                    )

                if action in _TERMINAL_ACTIONS:
                    break

                persona = (
                    DEBUGGER_PERSONA if action == NextAction.DEBUGGER else node.persona
                )
            except _LaunchFailed as exc:
                # FR-005: a pre-first-token launch fault is not an attempt.  Record
                # it as launch evidence so the next prompt can name it, but do not
                # append an AttemptRecord — that is what `_attempts_spent` counts.
                # FR-006 is handled by the post-loop terminal_reason.
                record.launch_failures += 1
                evidence.append(
                    AttemptEvidence(termination=Termination.AGENT_ERROR, result=None)
                )
                # FR-007: bound launch retries independently of the attempt budget.
                # Exceeding the bound ends the node rather than looping forever.
                if record.launch_failures >= request.config.max_launch_retries:
                    action = NextAction.KILLED
                    record.terminal_reason = (
                        f"launch failed {record.launch_failures} time(s) "
                        f"(AGENT_LAUNCH_FAILED): {exc}"
                    )
                    # FR-006: surface the launch failure as an operator-facing
                    # condition at the time it happens, not after the ladder exhausts.
                    # The escalation history names the launch fault and carries no
                    # verification results, because no attempt ever ran.
                    launch_summary = (
                        f"Agent launch failure (AGENT_LAUNCH_FAILED): {exc}\n\n"
                        f"The agent could not be started after "
                        f"{record.launch_failures} attempt(s). No node attempt "
                        f"was recorded and no ordinary attempt was consumed."
                    )
                    escalation = await self._escalate(
                        graph, node, [], request.config, history_summary=launch_summary
                    )
                    # 068-US2: `None` is a stop with the page still open — no
                    # resolution to record. The node is already KILLED here
                    # either way, so only the epic-level half is left to apply.
                    if escalation is not None:
                        record.escalations.append(escalation.resolution)
                        if escalation.resolution == EscalationChoice.KILL_EPIC:
                            self._kill_requested = True
                    break
                action = NextAction.RETRY
                # Continue the loop, which increments attempt and re-dispatches.
                # The retry is bounded above, so this cannot loop forever.
                continue
            except asyncio.CancelledError:
                # SDK eviction/cancellation: the worker is reclaiming this workflow
                # coroutine. Do not emit any further commands — `teardown_attempt`
                # must not run because the eviction path is not a normal node
                # ending and the SDK will not record new history anyway
                # (FR-002). Re-raise immediately so Python does not report a
                # swallowed cancellation that later awaits in `finally`.
                raise
            finally:
                # Every key that is opened for an attempt is closed on every exit
                # (FR-007), including raises and the kills/questions that break the
                # loop. The bracket is per-iteration: one mint, one teardown. A
                # parked question closes its key before entering the long wait so
                # the workflow can be cancelled while parked without leaking it.
                #
                # The exception-interpreter excludes `asyncio.CancelledError` and
                # `GeneratorExit` from this finally: when the SDK evicts the workflow
                # coroutine, or when a suspended coroutine is garbage-collected, the
                # finally block still executes during finalization, and any `await`
                # here (including `workflow.execute_activity`) can produce an unraisable
                # `GeneratorExit` warning and emit commands the eviction path must not
                # emit (FR-002).
                if not teardown_done:
                    if sys.exc_info()[1] is not None and isinstance(
                        sys.exc_info()[1], (asyncio.CancelledError, GeneratorExit)
                    ):
                        teardown_done = True
                    else:
                        await self._teardown(lease, termination, record.last_snapshot)

        # 035-US1: any unconsumed buffered signal is refused once the node is terminal.
        await self._refuse_buffered_external_completions(
            graph.epic_id, node.id, reason="node already terminal"
        )

        if action == NextAction.PASSED:
            # Verified — the fact FR-009's `depends_on` edges wait on, and the
            # moment the landing phase begins. The worktree is salvaged (its work
            # is the branch the PR will land), then the node lands; removal is
            # deferred to the landing's terminal, because recovery and the PR
            # both read the tree the work was done in (plan.md § US1). This is
            # the single PASSED grant an edge may open on (FR-003, SC-002).
            record.verified = True
            record.state = NodeState.PASSED
            await self._close_out(graph, node, record, termination, state=None)
            await self._land(graph, request, resolved, record, prepared, results[-1])
        elif record.state == NodeState.WAITING_OPERATOR:
            # 008-US1 parked here; US2 moved the un-park *inside* the loop (the
            # question path `continue`s on answer or expiry, and `break`s on a
            # kill that lands while parked). So reaching this branch means a kill
            # stopped the epic mid-question: the node stays parked, the epic
            # stays paused, and nothing else dispatches. The state is the truth.
            pass
        elif parked:
            state = NodeState.FAILED
            await self._close_out(graph, node, record, termination, state=state)
        else:
            state = NodeState.KILLED
            await self._close_out(graph, node, record, termination, state=state)

    async def _attempt(
        self,
        record: NodeRecord,
        lease: KeyLease,
        context: AttemptContext,
    ) -> AdapterResult | None:
        """Run one agent attempt, and hand its measured spend to teardown.

        Observation lives inside the activity (plan US1): the adapter reads the
        proxy on its own cadence and carries the newest snapshot as heartbeat
        details, and the normal path returns it on the `AdapterResult`. The
        workflow no longer polls beside the attempt, so an attempt's history
        cost is a constant — no per-interval timer, no `poll_usage` activity
        (FR-001, FR-002).

        The wait is `wait_condition(timeout=None)`, which creates **no Temporal
        timer** (FR-002) while still re-evaluating the condition on every
        workflow activation: an operator's kill lands within a beat's response
        and the attempt's completion is picked up in the same breath. A kill
        still stops the adapter, and because the SDK does not surface heartbeat
        details on a cancellation the workflow itself requested, the bracket
        reads the proxy once before it closes rather than records NULL (FR-003,
        constitution V) — a constant cost per kill, not per interval.

        A worker death surfaces as an `ActivityError` whose cause is a heartbeat
        `TimeoutError` carrying the last heartbeat payload; the workflow reads
        that figure off it and reports the attempt TIMEOUT so it is verified like
        any other (FR-012). `None` is returned for the attempt a kill cancelled —
        there is no result, and the caller supplies the classification.

        A pre-first-token launch fault is the other `ActivityError` this method
        distinguishes: the adapter raised `AGENT_LAUNCH_FAILED`, which means no
        agent ever started.  It must not be recorded as an attempt (FR-005), so it
        is signalled to the caller as a launch failure rather than as an
        `AdapterResult`.
        """
        record.state = NodeState.RUNNING
        agent = workflow.start_activity(
            run_agent_attempt,
            context,
            # The activity's id *is* the node id (US5): `ergane build status`
            # reads each pending `run_agent_attempt`'s heartbeat off `describe()`
            # and attributes the spend to the node named by `activity_id`, so a
            # wide epic with several attempts in flight charges each node alone
            # (FR-011). A node runs one attempt at a time, so the id is unique
            # among concurrently-pending agent activities by construction; it is
            # replay-safe because it is a fixed string, not a derived value.
            activity_id=context.node_id,
            start_to_close_timeout=timedelta(
                seconds=context.timeout_s + _ADAPTER_GRACE_S
            ),
            heartbeat_timeout=_agent_heartbeat_timeout(context.timeout_s),
            retry_policy=_AGENT_RETRIES,
        )

        await workflow.wait_condition(
            lambda: agent.done() or self._kill_requested,
            timeout=None,
        )

        if self._kill_requested and not agent.done():
            await self._cancel(agent)
            # The SDK does not surface heartbeat details on a cancellation the
            # workflow itself requested, so the bracket is closed with a single
            # proxy read rather than with a fabricated NULL (FR-003).
            record.last_snapshot = await workflow.execute_activity(
                poll_usage, lease, **_FAST
            )
            return None

        try:
            result = await agent
        except ActivityError as exc:
            cause = exc.cause
            if (
                isinstance(cause, ApplicationError)
                and cause.type == AGENT_LAUNCH_FAILED
            ):
                raise _LaunchFailed(cause.message) from exc
            return self._attempt_timeout(record, exc)
        record.last_snapshot = result.last_snapshot
        return result

    def _attempt_timeout(
        self, record: NodeRecord, exc: ActivityError
    ) -> AdapterResult:
        """Turn a dead attempt into a TIMEOUT result, keeping its last measurement.

        The one ending that is not the adapter's word: the worker died and the
        activity heartbeated no more, so Temporal reports a heartbeat timeout.
        The figure that was true a beat ago rode the final heartbeat, and the SDK
        exposes it here (`TimeoutError.last_heartbeat_details`) — a teardown that
        can no longer reach the proxy still records what was measured, never a
        fabricated zero (constitution V). A heartbeat-timeout attempt is verified
        like any other (FR-012), so this returns an ordinary `AdapterResult`
        rather than letting the error escape.
        """
        timeout = exc.cause
        snapshot: UsageSnapshot | None = None
        if isinstance(timeout, ActivityTimeoutError):
            details = list(timeout.last_heartbeat_details)
            if details and isinstance(details[0], dict):
                # The heartbeat payload round-trips as a dict on the workflow
                # side, not as the dataclass (the activity encoded it, the
                # workflow decodes to the JSON shape).
                payload = details[0]
                snapshot = UsageSnapshot(
                    spend_usd=payload["spend_usd"],
                    captured_at=payload["captured_at"],
                )
        record.last_snapshot = snapshot
        # No transcript: the worker died before the adapter could archive one,
        # so `transcript_path` stays its empty default rather than this module
        # inventing a path for an ending that produced no archive (FR-012).
        return AdapterResult(termination=Termination.TIMEOUT, last_snapshot=snapshot)

    async def _cancel(self, agent: workflow.ActivityHandle[AdapterResult]) -> None:
        """Stop the running attempt and wait for the cancellation to be recorded.

        The adapter's KILLED path terminates the process group, archives the
        transcript (FR-007) and re-raises rather than returning, so a cancelled
        attempt reaches the workflow as a failure — which is the correct shape
        and not an error to propagate: this workflow asked for it. However the
        attempt ended once it was told to stop is not a fact the epic turns on,
        so every ending is swallowed here and the node is closed out on the
        operator's decision instead.

        If the SDK itself is evicting this workflow, the cancellation propagates
        as `asyncio.CancelledError`. Swallowing it would leave a coroutine alive
        long enough to `await` in a `finally` block, which Python reports as an
        unraisable `GeneratorExit` and which can emit a teardown command after the
        SDK has already reclaimed the worker slot. Re-raising lets the SDK close
        the workflow coroutine cleanly without reaching any further awaits
        (FR-001).
        """
        agent.cancel()
        try:
            await agent
        except ActivityError:
            pass
        except asyncio.CancelledError:
            raise

    async def _teardown(
        self,
        lease: KeyLease,
        termination: Termination,
        last_snapshot: UsageSnapshot | None,
    ) -> None:
        """Close a key's bracket (FR-004).

        On the adapter's word about the process, and on the last thing the proxy
        was willing to tell us (R3). Every path that issued a key comes through
        here — the verified attempt, the one a kill cut short, and the judge's
        own call, which nothing polls and which therefore has no fallback figure
        to fall back to.
        """
        await workflow.execute_activity(
            teardown_attempt,
            TeardownInput(
                lease=lease,
                termination=termination,
                last_snapshot=last_snapshot,
            ),
            **_PROXY,
        )

    async def _verify(
        self,
        request: EpicInput,
        resolved: ResolvedNode,
        criteria: CriteriaSet,
        prepared: PreparedWorktree,
        attempt: int,
        judge: ResolvedPersona,
        prior_feedback: str | None,
        *,
        provenance: str | None = None,
    ) -> tuple[VerificationResult, JudgeVerdict | None]:
        """Gates, then output, then — only if it can still matter — the judge.

        Cheapest-first is 002's flow invariant 2 rather than an optimization: a
        node whose lint gate failed in two seconds must not cost a completion to
        find that out. `judge_required` is the question that guard asks, and it
        gates the worktree read as well as the scoring — reading a patch nobody
        will score is work for an answer already known.

        The verdict itself is `compose_result`'s, which is also where an
        unreachable judge becomes a PASS carrying `judge_unavailable` rather than
        a third kind of answer. The row lands before anything acts on it
        (invariant 3).

        `provenance` is recorded for externally-completed work (035-US1)."""
        node = resolved.node
        config = request.config
        started_at = _now()

        gate_results = await workflow.execute_activity(
            run_gates,
            RunGatesInput(worktree_path=prepared.path),
            heartbeat_timeout=timedelta(
                seconds=config.gate_timeout_s + _GATE_HEARTBEAT_GRACE_S
            ),
            **_GATES,
        )
        output = await workflow.execute_activity(
            check_output,
            CheckOutputInput(
                worktree_path=prepared.path,
                write_scope=resolved.write_scope,
                # Work is measured from where the node began (D-027): the agent
                # commits as it goes, so HEAD has moved with the work.
                base_ref=prepared.base_ref,
                expected_artifacts=[],
            ),
            **_FAST,
        )

        verdict: JudgeVerdict | None = None
        if judge_required(gate_results, output, criteria):
            diff_text = await workflow.execute_activity(
                read_worktree_diff,
                ReadWorktreeDiffInput(
                    worktree_path=prepared.path, base_ref=prepared.base_ref
                ),
                **_GIT,
            )
            verdict = await self._judge(
                request, node, criteria, diff_text, attempt, judge, prior_feedback
            )

        gate_names = tuple(r.name for r in gate_results)
        resolved_digest = loop_digest(config, request.verify_order, gate_names)
        resolved_summary = loop_summary(config, request.verify_order, gate_names)

        result = compose_result(
            epic_id=request.graph.epic_id,
            node_id=node.id,
            attempt=attempt,
            form=VerificationForm.PHASE,
            gate_results=gate_results,
            output_check=output,
            judge=verdict,
            criteria_sha256=criteria.source_sha256,
            spec_ref=node.spec_ref,
            started_at=started_at,
            finished_at=_now(),
            loop_digest=resolved_digest,
            loop_summary=resolved_summary,
        )
        if provenance is not None:
            result = replace(result, provenance=provenance)

        recorded = await workflow.execute_activity(
            record_verification,
            RecordVerificationInput(
                result=result, criteria_source_path=criteria.source_path
            ),
            **_FAST,
        )
        # The activity re-hashed the spec file and may have found drift the
        # workflow could not see; the retry prompt and the escalation summary are
        # built from this bundle, so they read what the row reads (002 R8).
        return replace(result, criteria_drift=recorded.criteria_drift), verdict

    async def _judge(
        self,
        request: EpicInput,
        node: WorkNode,
        criteria: CriteriaSet,
        diff_text: str,
        attempt: int,
        judge: ResolvedPersona,
        prior_feedback: str | None,
    ) -> JudgeVerdict:
        """Score the diff, on one key minted and revoked for this scoring alone.

        One key, not one per re-ask: the loop below retries a single scoring
        job, and each re-ask is the same attribution unit — a fresh mint per
        re-ask would split one job's spend across ledger rows for no reader's
        benefit. The mint happens inside the implementer's still-open bracket,
        which is why the alias carries the persona (001 R1): the proxy refuses
        a duplicate alias while its key lives.

        The loop is for responses the strict parser could not read, and for
        nothing else: `run_judge` reports those as a RETRY with no findings, and
        asking again is the only way to tell a broken model turn from a real
        objection. A RETRY that names scenarios is an answer — re-asking it about
        an unchanged diff would buy the same verdict at twice the price, so it
        ends the attempt and the ladder takes over.

        An outage is not a verdict and not a failure of the node: once the
        workflow's own retry budget is spent, `JUDGE_UNAVAILABLE` becomes the
        UNAVAILABLE verdict `compose_result` reads as "did not block this PASS,
        and say so in the row". Every other error propagates — a judge that
        cannot be called for any other reason is a wiring fault, and passing work
        off as judged because of one is the failure the flag exists to prevent.
        """
        verdict: JudgeVerdict | None = None

        lease = await workflow.execute_activity(
            issue_attempt_key,
            IssueKeyInput(
                node_id=node.id,
                epic_id=request.graph.epic_id,
                # The node's attempt number: this is the scoring of *that*
                # attempt, and the ledger should read it that way.
                attempt=attempt,
                persona=JUDGE_PERSONA,
                spec_ref=node.spec_ref,
                # The judge's key may call the judge's aliases and nothing
                # else: a key that could call anything is attribution
                # without constraint (constitution V).
                models=list(judge.models),
                # The judge is a gateway persona by registry contract; it is
                # resolved by name, not routed, so agent is not required here.
                agent="",
            ),
            start_to_close_timeout=_PROXY["start_to_close_timeout"],
            retry_policy=_ISSUE_KEY_RETRIES,
        )
        try:
            for judge_attempt in range(1, request.config.max_judge_retries + 2):
                verdict = await self._score(
                    request, criteria, diff_text, lease, judge, judge_attempt, prior_feedback
                )
                if verdict.outcome != JudgeOutcome.RETRY or verdict.findings:
                    break
                prior_feedback = verdict.feedback
        finally:
            # Even when the judge failed outright: a key that outlives its
            # call is spend nobody is reading, and teardown is what writes
            # the ledger row (001 R3).
            await self._teardown(lease, Termination.COMPLETED, None)

        assert verdict is not None  # the range above is never empty
        return verdict

    def _pop_external_completion(self, node_id: str) -> tuple[str, str] | None:
        """Remove and return the first buffered completion for `node_id`, if any."""
        for i, (nid, branch, provenance) in enumerate(self._external_completions):
            if nid == node_id:
                del self._external_completions[i]
                return (branch, provenance)
        return None

    async def _record_external_completion(
        self,
        epic_id: str,
        node_id: str,
        branch: str,
        provenance: str,
        accepted: bool,
        reason: str | None,
    ) -> None:
        await workflow.execute_activity(
            record_external_completion,
            RecordExternalCompletionInput(
                epic_id=epic_id, node_id=node_id, branch=branch,
                provenance=provenance, accepted=accepted, reason=reason,
            ),
            **_FAST,
        )

    async def _refuse_buffered_external_completions(
        self, epic_id: str, node_id: str, reason: str
    ) -> None:
        """Refuse every buffered completion for `node_id`, logging each one."""
        while True:
            completion = self._pop_external_completion(node_id)
            if completion is None:
                return
            branch, provenance = completion
            await self._record_external_completion(
                epic_id,
                node_id,
                branch,
                provenance,
                accepted=False,
                reason=reason,
            )

    async def _apply_external_completion_if_present(
        self,
        record: NodeRecord,
        request: EpicInput,
        resolved: ResolvedNode,
        criteria: CriteriaSet,
        prepared: PreparedWorktree,
        judge: ResolvedPersona,
        results: list[VerificationResult],
        evidence: list[Any],
        termination: Termination,
    ) -> NextAction | None:
        """If a completion signal is buffered for this node, verify it and return the terminal action.

        The ladder has just returned ESCALATE, so the node is exhausted. The
        operator's branch becomes the node's result; a new attempt number is issued
        for the external verification row. The path rejoins the normal VERIFYING
        flow: gates, judge, PR and queue all run unchanged.
        """
        completion = self._pop_external_completion(record.node_id)
        if completion is None:
            return None

        branch, provenance = completion
        record.branch = branch
        record.attempt += 1
        record.provenance = provenance

        result, verdict = await self._verify(
            request,
            resolved,
            criteria,
            prepared,
            record.attempt,
            judge,
            None,
            provenance=provenance,
        )

        # Keep evidence lists and ladder history consistent with the normal loop.
        results.append(result)
        evidence.append(AttemptEvidence(termination=termination, result=result))
        record.history.append(
            AttemptRecord(
                attempt=record.attempt,
                persona=resolved.node.persona,
                verdict=result.verdict,
                judge_outcome=None if result.judge is None else result.judge.outcome,
            )
        )
        await self._record_external_completion(
            request.graph.epic_id, record.node_id, branch, provenance, accepted=True, reason=None
        )
        return NextAction.PASSED if result.verdict == OverallVerdict.PASS else NextAction.KILLED

    async def _score(
        self,
        request: EpicInput,
        criteria: CriteriaSet,
        diff_text: str,
        lease: KeyLease,
        judge: ResolvedPersona,
        judge_attempt: int,
        prior_feedback: str | None,
    ) -> JudgeVerdict:
        """One judge completion, with an outage answered rather than raised."""
        try:
            return await workflow.execute_activity(
                run_judge,
                RunJudgeInput(
                    criteria=criteria,
                    diff_text=diff_text,
                    virtual_key=lease.key,
                    proxy_url=request.proxy_url,
                    model_alias=judge.model_alias,
                    judge_attempt=judge_attempt,
                    prior_feedback=prior_feedback,
                    max_judge_retries=request.config.max_judge_retries,
                ),
                **_JUDGE,
            )
        except ActivityError as exc:
            outage = exc.cause
            if not (
                isinstance(outage, ApplicationError) and outage.type == JUDGE_UNAVAILABLE
            ):
                raise
            return JudgeVerdict(
                outcome=JudgeOutcome.UNAVAILABLE,
                findings=[],
                # The library scrubbed this message before it was ever an error
                # (002 FR-009), and the row is the only place it is read: an
                # UNAVAILABLE behind green gates has no next attempt to tell.
                feedback=outage.message,
                judge_attempt=judge_attempt,
                truncated_input=False,
                model_alias=judge.model_alias,
            )

    async def _escalate(
        self,
        graph: WorkGraph,
        node: WorkNode,
        results: Sequence[VerificationResult],
        config: VerificationConfig,
        *,
        history_summary: str | None = None,
    ) -> _Escalation | None:
        """Page a human, then wait exactly as long as waiting is worth (FR-008).

        An undelivered escalation applies the fail-safe default at once: waiting
        out an hour for a message nobody received delays the same kill and calls
        it patience (002 R11). A silence that runs out expires the row and takes
        the store's word for what happened — a press that beat the timer by a
        millisecond still decides the node (002 R12).

        041-US3: all of that is an `EscalationWorkflow` child's now, and this
        await parks no scheduler — `_run_node` is one task per node (FR-010).

        US2: a launch failure may pass a custom `history_summary` naming the fault,
        because there are no `VerificationResult`s to render.

        068-US2 (FR-006): the wait watches `_kill_requested` as well as the
        child, and returns `None` when the epic was stopped with the page still
        open. Until then this was `execute_child_workflow`, which waits for the
        child and nothing else — so `ergane build kill` set a flag that neither
        this method nor the scheduler behind it could reach, and an epic holding
        an unanswered escalation ignored the operator's stop for the whole of
        `escalation_timeout_s`. An hour of that is what sent four sessions to
        `temporal workflow terminate`. The shape is the question park's, at
        `_run_node`'s `wait_condition(question.done() or self._kill_requested)`:
        cancel the child so its timer dies with the epic, and leave the store row
        PENDING. A stopped epic is neither a press nor a burn — writing a
        resolution here would be pressing a button on the operator's behalf,
        which the spec's Assumptions forbid in as many words.
        """
        record = self._nodes[node.id]
        if self._kill_requested:
            # Already stopping. Paging a human about a node nobody will act on
            # is a message that can only be answered into the void.
            return None

        child = await workflow.start_child_workflow(
            EscalationWorkflow.run,
            EscalationRequest(
                epic_id=graph.epic_id,
                node_id=node.id,
                # Every attempt, evidence and all (SC-005): the operator is being
                # asked to decide, and one summarized failure hides the shape the
                # decision turns on.
                history_summary=history_summary or render_history(results),
                choices=list(DEFAULT_CHOICES),
                timeout_s=config.escalation_timeout_s,
            ),
            # Workflow scope, so a replay mints the same correlation id.
            id=child_correlation_id(),
        )
        # What `epic_status` reports as `awaiting_operator`, and therefore what
        # `ergane build reset` reads to tell a waiting node from a working one.
        record.pending_escalation_id = child.id
        try:
            # `Task.done()` is a pure read and the flag is a signal-set boolean,
            # so this predicate replays identically (constitution IV).
            await workflow.wait_condition(
                lambda: child.done() or self._kill_requested
            )
            if not child.done():
                child.cancel()
                return None
            outcome = await child
        finally:
            record.pending_escalation_id = None

        return _Escalation(
            escalation_id=outcome.escalation_id,
            delivered=outcome.delivered,
            resolution=outcome.resolution,
        )

    async def _close_out(
        self,
        graph: WorkGraph,
        node: WorkNode,
        record: NodeRecord,
        termination: Termination,
        *,
        state: NodeState | None,
    ) -> None:
        """Salvage, sweep, then say what the node became (constitution VI).

        In that order on every path out — pass, gate failure, kill, and the
        `PAUSE_EPIC` park alike: the salvage commit carries the attempt number
        and the termination the adapter classified, so the branch alone accounts
        for how the node ended once `.factory/` is swept (SC-004). Removal takes
        the directory and never the record — the branch and its commits outlive
        it. The terminal state is decided by the caller, because only the caller
        knows whether a node that did not pass was abandoned or parked.

        A `state` of `None` is the PASS path: salvage still happens (the work's
        durable form precedes the push, constitution VI), but the worktree is
        *not* removed — the landing phase reads it and recovery needs it, so
        removal is deferred to the landing's terminal (plan.md § US1).
        """
        await workflow.execute_activity(
            salvage_worktree,
            SalvageWorktreeInput(
                epic_id=graph.epic_id,
                node_id=node.id,
                termination=termination,
                attempt=record.attempt,
            ),
            **_GIT,
        )
        if state is None:
            # PASS path: salvage, defer removal. The caller sets the terminal
            # PASSED (the landing phase follows), so the single PASSED grant —
            # the one edge may open on (FR-003) — stays in `_run_node` under
            # `action == NextAction.PASSED`.
            return
        await workflow.execute_activity(
            remove_worktree,
            RemoveWorktreeInput(
                epic_id=graph.epic_id,
                node_id=node.id,
                target_repo=graph.target_repo,
            ),
            **_GIT,
        )
        record.state = state

    # --- the landing phase (US1) -------------------------------------------

    async def _land(
        self,
        graph: WorkGraph,
        request: EpicInput,
        resolved: ResolvedNode,
        record: NodeRecord,
        prepared: PreparedWorktree,
        result: VerificationResult,
    ) -> None:
        """Open a landing for a PASS node and start polling it (US1).

        Salvage already happened in `_close_out`. Here: render the PR body, push
        + open the PR, enqueue it, then start the background poll task that rides
        it to a terminal. The node advances PASSED → PR_OPEN → ENQUEUED as the
        landing does; `MERGED` is the verified node's terminal (FR-009). The main
        scheduler is not blocked: the poll runs on the queue's own beat while the
        epic goes on to other nodes (US1-S4).
        """
        node = resolved.node
        config = request.landing_config

        rendered = await workflow.execute_activity(
            prepare_landing_pr,
            PrepareLandingPrInput(
                epic_id=graph.epic_id,
                node_id=node.id,
                branch=record.branch,
                attempt=record.attempt,
                feature=graph.feature,
                requirement_keys=tuple(node.requirement_keys),
                result=result,
                story_title=node.story_key,
            ),
            **_FAST,
        )
        opened = await workflow.execute_activity(
            open_landing_pr,
            OpenLandingPrInput(
                epic_id=graph.epic_id,
                node_id=node.id,
                target_repo=graph.target_repo,
                base=prepared.default_branch,
                branch=record.branch,
                title=rendered.title,
                body_file=rendered.body_file,
            ),
            **_GIT,
        )
        landing = Landing(
            node_id=node.id,
            branch=record.branch,
            pr_number=opened.number,
            pr_url=opened.url,
        )
        record.landing = landing
        record.state = NodeState.PR_OPEN
        # 069-US1: the verdict this landing was opened on, kept so a rebase that
        # spends no attempt can still re-render the body the node already earned.
        record.last_result = result

        enqueued = await workflow.execute_activity(
            enqueue_landing,
            EnqueueLandingInput(
                pr_number=opened.number,
                merge_method=config.merge_method,
                target_repo=graph.target_repo,
            ),
            **_FAST,
        )
        if enqueued.rejected:
            # The queue refused the enqueue outright (disabled mid-flight — the
            # spec edge case). US1 surfaces it as a killed landing; US2's
            # recovery routing is where a refusal an operator can fix goes.
            record.landing = replace(
                landing,
                outcomes=(
                    ObservedOutcome(at=_now(), outcome=QueueOutcome.DEQUEUED_BY_HUMAN),
                ),
                state=LandingState.KILLED,
            )
            record.state = NodeState.KILLED
            return

        record.landing = replace(
            landing,
            enqueued_at=_now(),
            enqueued_tip=opened.pushed_sha,
            # 069-US1: the base half of what the queue is about to test. The tip
            # says which tree; this says which world it was built for.
            enqueued_base=prepared.base_ref,
            state=LandingState.ENQUEUED,
        )
        record.state = NodeState.ENQUEUED
        self._landing_tasks[node.id] = asyncio.ensure_future(
            self._poll_landing(graph, record, config)
        )

    async def _poll_landing(
        self,
        graph: WorkGraph,
        record: NodeRecord,
        config: LandingConfig,
    ) -> None:
        """Ride one landing to a terminal, on the queue's own beat (US1, FR-004).

        A background task started when the landing enqueues. It polls the PR,
        classifies what the queue says, and advances the landing — a pending
        answer is a read with no consequence (D-021), and a terminal answer ends
        it. `MERGED` is the reconciled success (a late or manual merge included);
        recovery-eligible rejections park the landing for US2; an operator
        dequeue or stall ends it as a killed landing. The worktree, deferred at
        PASS, is removed only once the landing is terminal.
        """
        node_id = record.node_id
        while True:
            if self._kill_requested:
                return
            try:
                await workflow.wait_condition(
                    lambda: self._kill_requested,
                    timeout=timedelta(seconds=config.poll_interval_s),
                )
                if self._kill_requested:
                    return
            except asyncio.TimeoutError:
                pass

            snapshot = await workflow.execute_activity(
                poll_landing,
                PollLandingInput(
                    pr_number=record.landing.pr_number,
                    target_repo=graph.target_repo,
                ),
                **_FAST,
            )
            outcome = classify(
                snapshot, record.landing, config, now=snapshot.observed_at
            )
            if outcome is None:
                # Keep polling: the queue is still on it.
                continue

            failing_checks = (
                snapshot.failing_required_checks
                if outcome == QueueOutcome.CHECKS_FAILED
                else ()
            )
            record.landing = replace(
                record.landing,
                outcomes=record.landing.outcomes
                + (ObservedOutcome(at=_now(), outcome=outcome, failing_checks=failing_checks),),
            )
            if outcome == QueueOutcome.MERGED:
                # Removal precedes the terminal state, so the main loop — which
                # wakes on landing-terminal — only sees MERGED once the deferred
                # sweep has actually happened. The epic must not complete with a
                # worktree still on disk (US1-S4, plan.md § US1).
                await self._remove_worktree(graph, node_id)
                record.landing = replace(record.landing, state=LandingState.MERGED)
                record.state = NodeState.MERGED
                return
            if outcome in _RECOVERY_OUTCOMES:
                # Recovery-eligible (CHECKS_FAILED, CONFLICT): the landing is
                # rejected but not finished — US2's bounded recovery cycle owns
                # what happens next. Not terminal, so the epic parks on it.
                #
                # 069-US1: and *why* it was rejected is decided here, at the one
                # moment the snapshot exists. The recovery runs later, against a
                # world that may have moved again; re-deriving the cause then
                # would answer a question about a different moment.
                record.landing = replace(
                    record.landing,
                    state=LandingState.REJECTED,
                    rejection_cause=rejection_cause(
                        outcome,
                        enqueued_base=record.landing.enqueued_base,
                        observed_base=snapshot.base_sha,
                    ),
                )
                return
            # DEQUEUED_BY_HUMAN and STALLED: operator/queue rejections that are
            # terminal. Node ends killed, branch preserved.
            await self._remove_worktree(graph, node_id)
            record.landing = replace(record.landing, state=LandingState.KILLED)
            record.state = NodeState.KILLED
            return

    async def _remove_worktree(self, graph: WorkGraph, node_id: str) -> None:
        """The worktree removal deferred to landing-terminal time (plan.md § US1)."""
        await workflow.execute_activity(
            remove_worktree,
            RemoveWorktreeInput(
                epic_id=graph.epic_id,
                node_id=node_id,
                target_repo=graph.target_repo,
            ),
            **_GIT,
        )

    # --- the landing-recovery routing (US2, FR-005/006/007/008) ---------------

    async def _run_recovery(
        self,
        resolved: ResolvedNode,
        request: EpicInput,
        sources: PromptSources,
        judge: ResolvedPersona,
        *,
        granted: bool = False,
    ) -> None:
        """One recovery cycle for a REJECTED landing, or escalate (US2).

        The main loop schedules this for a node whose landing is REJECTED
        (`_next_recovery`), outranking fresh nodes. A recovery cycle routes on
        the last classified outcome:

        - **CHECKS_FAILED** → sync the branch onto the new target head; a clean
          sync re-enters the inner loop as the node's own persona.
        - **CONFLICT** (or a sync that conflicts) → the `debugger` persona gets
          the cycle, with the conflicted files in the prompt (FR-006).
        - **Exhaustion** (`recovery_cycles >= max_recovery_cycles`, or a cycle
          that fails again, or a refused sync) → Telegram escalation with the
          queue history rendered and choices
          `[RETRY | KILL | PAUSE_EPIC | KILL_EPIC]` (FR-007). `RETRY` grants
          exactly one more cycle; 1h silence or `KILL` ends the node KILLED,
          branch preserved (FR-008); `PAUSE_EPIC` parks the node and pauses
          the epic; `KILL_EPIC` ends the epic (068 FR-008).

        A recovery cycle that PASSes re-pushes + re-enqueues the same PR and
        starts a fresh poll — the landing is back on the queue (FR-005).

        069-US1 puts one route ahead of all of that. A rejection classified
        `BASE_MOVED` is the world moving under a tree that was never wrong, and
        the answer to it is a rebase, not an attempt: the branch syncs onto the
        new head and goes straight back into the queue, spending neither of the
        two budgets a recovery spends — no `recovery_cycles` increment here, and
        no `AttemptRecord` from `_recovery_attempt` for the ladder to count.
        Freeing one of those and not the other leaves the node dying at
        whichever was left, which is why both are named in one sentence.

        That path is bounded by `max_free_rebases` (FR-004) and it is narrow: a
        sync that conflicts is *not* only a moved base — the node's work and the
        sibling's overlap textually, and reconciling them is work, so it drops
        back onto the charged cycle below and the debugger gets it exactly as it
        always did.
        """
        graph = request.graph
        record = self._nodes[resolved.node.id]
        landing = record.landing
        if landing is None:
            return
        config = request.landing_config

        # 069-US1. `granted` is an operator who already answered an escalation:
        # they asked for a cycle, and giving them a silent rebase instead would
        # answer a different question than the one they pressed.
        # A rebase re-offers the verdict the landing was opened on. Without one
        # there is nothing to re-offer, and the charged cycle — which produces a
        # fresh verdict — is the honest route.
        earned = record.last_result
        free = (
            not granted
            and landing.rejection_cause == RejectionCause.BASE_MOVED
            and landing.free_rebases < config.max_free_rebases
            and earned is not None
        )

        if not free:
            # Exhaustion gates the automatic cycle. An operator's RETRY is not an
            # automatic cycle — it is one more cycle, granted by hand.
            if not granted and landing.recovery_cycles >= config.max_recovery_cycles:
                await self._escalate_and_apply(graph, request, resolved, sources, judge)
                return

            record.landing = replace(
                landing, recovery_cycles=landing.recovery_cycles + 1
            )
        last = record.landing.outcomes[-1].outcome

        # The base the branch sat on before this sync — read before the sync
        # answers, because the sync is what moves it.
        base_before_sync = record.base_ref

        # The sync runs first for both recovery-eligible rejections: a
        # CHECKS_FAILED needs the new target head merged in, and a CONFLICT sync
        # is what surfaces the conflicted file list the debugger resolves. It is
        # also the rebase 069-US1's free path consists of.
        sync = await workflow.execute_activity(
            sync_landing_branch,
            SyncLandingBranchInput(
                epic_id=graph.epic_id,
                node_id=record.node_id,
                target_repo=graph.target_repo,
            ),
            **_GIT,
        )
        if sync.refused:
            # A recovery that could not run is not a silent pass — it escalates.
            await self._escalate_and_apply(graph, request, resolved, sources, judge)
            return

        if free and not sync.clean:
            # 069-US1: the base moved *and* the node's own work collides with
            # what landed. That is not "only a moved base" (FR-001's word), and
            # resolving it is work — so it is charged, and the gate the free
            # route skipped applies now.
            free = False
            spent = record.landing.recovery_cycles
            if not granted and spent >= config.max_recovery_cycles:
                await self._escalate_and_apply(graph, request, resolved, sources, judge)
                return
            record.landing = replace(
                record.landing,
                recovery_cycles=record.landing.recovery_cycles + 1,
            )

        # Carry the new branch point into re-verification (D-027 extended): the
        # diff and the judge see only the node's own work above the merged-in
        # target head.
        prepared = replace(record.prepared, base_ref=sync.base_ref)
        record.base_ref = sync.base_ref
        record.prepared = prepared

        # US3: remember whether the sync merged in nothing. This refutes the
        # stale-base hypothesis for the recovery attempt's prompt (FR-013).
        #
        # 069-US1 corrected the comparison: it read `record.base_ref` *after* the
        # line above had already assigned `sync.base_ref` to it, so it answered
        # "is the new head the new head" and was True whenever a head existed at
        # all. The fact it is supposed to state — did this sync merge anything in
        # — is the same fact the rejection classifier turns on, and a prompt that
        # tells the agent the base did not move while the workflow classified the
        # base as moved is two halves of one system disagreeing out loud.
        base_unmoved = (
            base_before_sync is not None and base_before_sync == sync.base_ref
        )

        if free and earned is not None:
            # The rebase *is* the recovery. No key is issued, no agent runs, and
            # no record joins `record.history`, so the ladder counts exactly what
            # it counted before the queue said anything (FR-001). `_reenqueue`
            # still runs the identical-tree refusal (FR-006): a rebase that
            # changed nothing must not re-offer the tree the queue just refused,
            # free or not.
            record.landing = replace(
                record.landing, free_rebases=landing.free_rebases + 1
            )
            await self._reenqueue(
                graph, request, resolved, sources, judge, record, prepared, earned
            )
            return

        failing_checks: tuple[CheckFailure, ...] = ()
        if sync.clean and last == QueueOutcome.CHECKS_FAILED:
            failing_checks = await workflow.execute_activity(
                fetch_check_failure,
                FetchCheckFailureInput(
                    epic_id=graph.epic_id,
                    node_id=record.node_id,
                    pr_number=landing.pr_number,
                    check_names=record.landing.outcomes[-1].failing_checks,
                    target_repo=graph.target_repo,
                ),
                **_FAST,
            )

        if sync.clean:
            persona = resolved.node.persona
            conflicted_files = ()
        else:
            persona = DEBUGGER_PERSONA
            conflicted_files = sync.conflicted_files

        result = await self._recovery_attempt(
            graph,
            request,
            resolved,
            sources,
            judge,
            prepared,
            persona,
            conflicted_files,
            failing_checks,
            base_unmoved=base_unmoved,
        )
        if result is not None:
            await self._reenqueue(
                graph, request, resolved, sources, judge, record, prepared, result
            )
            return

        # The recovery cycle failed again — exhaustion.
        record.landing = replace(record.landing, check_evidence=failing_checks)
        resolution = await self._escalate_landing(graph, request, record)
        if resolution == EscalationChoice.RETRY.value:
            # Exactly one more cycle, granted by the operator.
            await self._run_recovery(
                resolved, request, sources, judge, granted=True
            )
            return
        await self._apply_landing_resolution(
            graph, request, resolved, resolution, sources, judge
        )

    async def _escalate_and_apply(
        self,
        graph: WorkGraph,
        request: EpicInput,
        resolved: ResolvedNode,
        sources: PromptSources,
        judge: ResolvedPersona,
    ) -> None:
        """Page a human about a landing, then act on whatever comes back.

        The pair every route out of `_run_recovery` that is not "try again" ends
        in: exhaustion, a sync that could not run, a moved base whose rebase
        collided. Extracted so the routing above reads as the decisions it makes
        rather than as three copies of the same two calls.
        """
        record = self._nodes[resolved.node.id]
        resolution = await self._escalate_landing(graph, request, record)
        await self._apply_landing_resolution(
            graph, request, resolved, resolution, sources, judge
        )

    async def _recovery_attempt(
        self,
        graph: WorkGraph,
        request: EpicInput,
        resolved: ResolvedNode,
        sources: PromptSources,
        judge: ResolvedPersona,
        prepared: PreparedWorktree,
        persona: str,
        conflicted_files: tuple[str, ...],
        failing_checks: tuple[CheckFailure, ...] = (),
        base_unmoved: bool = False,
    ) -> VerificationResult | None:
        """One bounded recovery attempt: fresh key, landing evidence, then verify.

        The recovery attempt is an ordinary bracketed attempt (constitution V):
        a fresh key with the persona in the alias (D-026), the queue rejection
        quoted into the prompt, and the full 002 ladder authority (gates →
        output → judge). Returns the `VerificationResult` on PASS, `None` on a
        failed or killed attempt — the caller routes a failure to escalation.
        """
        node = resolved.node
        record = self._nodes[node.id]
        landing = record.landing

        record.attempt += 1
        prompt = build_attempt_prompt(
            node=node,
            epic_id=graph.epic_id,
            spec_text=sources.spec_text,
            plan_text=sources.plan_text,
            tasks_text=sources.tasks_text,
            standards=sources.standards,
            prior_attempts=(),
            landing_evidence=LandingEvidence(
                outcome=landing.outcomes[-1].outcome,
                queue_history=landing.outcomes,
                conflicted_files=conflicted_files,
                failing_checks=failing_checks,
                base_unmoved=base_unmoved,
            ),
        )

        # Recovery re-uses the same persona as the original node; resolve its
        # agent value the same way `_run_node` does.
        recovery_persona_entry = self._personas.get(persona)
        recovery_agent = recovery_persona_entry.agent if recovery_persona_entry is not None else ""

        lease = await workflow.execute_activity(
            issue_attempt_key,
            IssueKeyInput(
                node_id=node.id,
                epic_id=graph.epic_id,
                attempt=record.attempt,
                persona=persona,
                spec_ref=node.spec_ref,
                models=list(resolved.models),
                agent=recovery_agent,
            ),
            start_to_close_timeout=_PROXY["start_to_close_timeout"],
            retry_policy=_ISSUE_KEY_RETRIES,
        )
        record.last_snapshot = None

        try:
            adapter_result = await self._attempt(
                record,
                lease,
                AttemptContext(
                    epic_id=graph.epic_id,
                    node_id=node.id,
                    attempt=record.attempt,
                    prompt=prompt,
                    worktree_path=prepared.path,
                    home_path=str(home_path(DEFAULT_FACTORY_ROOT, graph.epic_id, node.id)),
                    proxy_url=request.proxy_url,
                    virtual_key=lease.key,
                    model_alias=resolved.model_alias,
                    session_id=str(workflow.uuid4()),
                    timeout_s=resolved.timeout_s,
                    context_window=resolved.context_window,
                    target_repo=graph.target_repo,
                    agent=recovery_agent,
                ),
            )
            if adapter_result is None or self._kill_requested:
                termination = (
                    adapter_result.termination
                    if adapter_result is not None
                    else Termination.KILLED
                )
                return None

            termination = adapter_result.termination
            result, _verdict = await self._verify(
                request, resolved, record.criteria, prepared, record.attempt, judge, None
            )
            record.history.append(
                AttemptRecord(
                    attempt=record.attempt,
                    persona=persona,
                    verdict=result.verdict,
                    judge_outcome=None if result.judge is None else result.judge.outcome,
                )
            )
            return result if result.verdict == OverallVerdict.PASS else None
        finally:
            # The recovery key is closed on every exit, raise included, exactly
            # once per lease (FR-007/FR-008).
            await self._teardown(lease, termination, record.last_snapshot)

    async def _reenqueue(
        self,
        graph: WorkGraph,
        request: EpicInput,
        resolved: ResolvedNode,
        sources: PromptSources,
        judge: ResolvedPersona,
        record: NodeRecord,
        prepared: PreparedWorktree,
        result: VerificationResult,
    ) -> None:
        """Salvage, re-push and re-enqueue the same PR after a recovery PASS (FR-005).

        The recovery PASS re-enters the landing phase exactly as the first
        landing did: salvage the recovery work (the branch's durable form,
        constitution VI), re-render the PR body, push the synced branch, and
        re-enqueue the *same* PR (`open_landing_pr` reuses it idempotently), then
        start a fresh poll task. `recovery_cycles` was already incremented.
        """
        config = request.landing_config
        node = resolved.node
        landing = record.landing
        # US3: before preparing the PR, decide whether re-enqueueing would be
        # futile: the tree the queue already rejected vs. the tree we are about
        # to push. Identical trees require a human's flake judgment.
        if landing is not None and landing.enqueued_tip is not None:
            identical = await workflow.execute_activity(
                compare_trees,
                CompareTreesInput(
                    epic_id=graph.epic_id,
                    node_id=record.node_id,
                    target_repo=graph.target_repo,
                    rejected_tip=landing.enqueued_tip,
                    current_head=prepared.base_ref,
                ),
                **_GIT,
            )
            if identical:
                record.landing = replace(
                    landing,
                    check_evidence=(),
                    state=LandingState.REJECTED,
                )
                resolution = await self._escalate_landing(
                    graph,
                    request,
                    record,
                    note=(
                        "Re-enqueueing would be futile: the recovery's tree is "
                        "identical to the tree the queue already rejected. "
                        "RETRY means 'I judge the red a flake' and will enqueue "
                        "the identical tree."
                    ),
                )
                if resolution == EscalationChoice.RETRY.value:
                    # The operator judged it a flake; complete the interrupted
                    # enqueue of the same recovery cycle.
                    record.landing = replace(
                        record.landing,
                        state=LandingState.REJECTED,
                    )
                else:
                    await self._apply_landing_resolution(
                        graph, request, resolved, resolution, sources, judge
                    )
                    return

        await workflow.execute_activity(
            salvage_worktree,
            SalvageWorktreeInput(
                epic_id=graph.epic_id,
                node_id=record.node_id,
                termination=Termination.COMPLETED,
                attempt=record.attempt,
            ),
            **_GIT,
        )
        rendered = await workflow.execute_activity(
            prepare_landing_pr,
            PrepareLandingPrInput(
                epic_id=graph.epic_id,
                node_id=record.node_id,
                branch=record.branch,
                attempt=record.attempt,
                feature=graph.feature,
                requirement_keys=tuple(node.requirement_keys),
                result=result,
                story_title=node.story_key,
            ),
            **_FAST,
        )
        opened = await workflow.execute_activity(
            open_landing_pr,
            OpenLandingPrInput(
                epic_id=graph.epic_id,
                node_id=record.node_id,
                target_repo=graph.target_repo,
                base=prepared.default_branch,
                branch=record.branch,
                title=rendered.title,
                body_file=rendered.body_file,
            ),
            **_GIT,
        )
        enqueued = await workflow.execute_activity(
            enqueue_landing,
            EnqueueLandingInput(
                pr_number=opened.number,
                merge_method=config.merge_method,
                target_repo=graph.target_repo,
            ),
            **_FAST,
        )
        if enqueued.rejected:
            # A refusal is a queue rejection an operator can fix — escalate.
            resolution = await self._escalate_landing(graph, request, record)
            await self._apply_landing_resolution(
                graph, request, resolved, resolution, sources, judge
            )
            return

        record.landing = replace(
            record.landing,
            enqueued_at=_now(),
            enqueued_tip=opened.pushed_sha,
            # 069-US1: the world this re-offer was built for. Without moving it
            # forward, the next rejection would be compared against the base of
            # a landing two cycles old and read as moved forever.
            enqueued_base=prepared.base_ref,
            state=LandingState.ENQUEUED,
        )
        record.state = NodeState.ENQUEUED
        record.last_result = result
        self._landing_tasks[record.node_id] = asyncio.ensure_future(
            self._poll_landing(graph, record, config)
        )

    async def _escalate_landing(
        self,
        graph: WorkGraph,
        request: EpicInput,
        record: NodeRecord,
        *,
        note: str | None = None,
    ) -> str:
        """Page a human with the rendered queue history and wait out the hour.

        The landing escalation carries the recovery evidence — every queue
        outcome in order and the recovery cycles spent — through the same
        `EscalationWorkflow` the verification ladder now uses, with choices
        `[RETRY | KILL | PAUSE_EPIC | KILL_EPIC]` (FR-007). An undelivered message applies
        the fail-safe KILL at once; an hour of silence expires to KILL; the
        store's word on a press that beat the timer by a millisecond still
        decides (002 R12). 041-US3 moved all three into the child.

        US3: an optional `note` explains why this escalation fired when it is not
        the ordinary exhaustion case — e.g. a futile re-enqueue. The note is
        appended to the rendered history summary so the operator sees the reason.

        068-US2 (FR-006): the wait watches `_kill_requested` too, for the reason
        `_escalate` records at length — a landing escalation held the epic open
        against `ergane build kill` exactly as a verification one did. A stop
        applies the same fail-safe an undelivered page does: nobody answered, so
        the node ends KILLED with its branch preserved. The child is cancelled
        and its row left PENDING, so nothing here is recorded as a press.
        """
        if self._kill_requested:
            return EscalationChoice.KILL.value

        history_summary = render_landing_history(record.landing)
        if note:
            history_summary = f"{history_summary}\n\n{note}"
        child = await workflow.start_child_workflow(
            EscalationWorkflow.run,
            EscalationRequest(
                epic_id=graph.epic_id,
                node_id=record.node_id,
                history_summary=history_summary,
                choices=list(DEFAULT_CHOICES),
                timeout_s=request.config.escalation_timeout_s,
                check_evidence=record.landing.check_evidence,
            ),
            id=child_correlation_id(),
        )
        record.pending_escalation_id = child.id
        try:
            await workflow.wait_condition(
                lambda: child.done() or self._kill_requested
            )
            if not child.done():
                child.cancel()
                return EscalationChoice.KILL.value
            outcome = await child
        finally:
            record.pending_escalation_id = None

        if not outcome.delivered:
            return EscalationChoice.KILL.value
        return outcome.resolution

    async def _apply_landing_resolution(
        self,
        graph: WorkGraph,
        request: EpicInput,
        resolved: ResolvedNode,
        resolution: str,
        sources: PromptSources,
        judge: ResolvedPersona,
    ) -> None:
        """Act on an operator's landing decision (FR-007/008).

        `KILL` (and the hour of silence that defaults to it) ends the node KILLED
        with the branch preserved — removal takes the directory, never the branch
        (constitution VI). `PAUSE_EPIC` parks the node and pauses the epic,
        exactly as the verification ladder's escalation does. `KILL_EPIC` ends
        the epic and this node with it (068 FR-008), which is `KILL`'s effect on
        the node plus the scheduler's own stop. `RETRY` is not routed here — the
        caller grants one more recovery cycle.
        """
        record = self._nodes[resolved.node.id]
        if resolution == EscalationChoice.KILL_EPIC.value:
            # The epic-level half, set before the node closes out so the
            # scheduler sees the stop as soon as this task is reaped. The
            # node-level half is the fall-through below: ending the node is
            # exactly what KILL does, and the two answers differ only in what
            # they do to the epic.
            self._kill_requested = True
        if resolution == EscalationChoice.PAUSE_EPIC.value:
            self._paused = True
            self._epic_state = EpicState.PAUSED
            await self._close_out(
                graph, resolved.node, record, Termination.KILLED, state=NodeState.FAILED
            )
            record.landing = replace(record.landing, state=LandingState.KILLED)
            record.state = NodeState.FAILED
            return
        # KILL, EXPIRED, or anything unoffered — all end the node killed.
        await self._remove_worktree(graph, record.node_id)
        record.landing = replace(record.landing, state=LandingState.KILLED)
        record.state = NodeState.KILLED



def _now() -> str:
    """The workflow's own clock, in the factory's one timestamp spelling.

    `workflow.now()` rather than `datetime.now()`: a replayed workflow has to
    stamp a row with the same instant the first run did.
    """
    return _iso(workflow.now())


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")
