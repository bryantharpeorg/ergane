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
   stops dispatch and nothing else: the node already in flight keeps its whole
   ladder, because its key lease and its worktree are one bracket and suspending
   a node halfway through would leave a key issued against work nobody is doing.
   `kill` is the single exception and the only path that interrupts an attempt —
   it cancels the adapter (whose KILLED path archives the transcript first, R2),
   closes the bracket the attempt opened, salvages and sweeps, and then marks
   every node the epic never reached KILLED, so a killed epic still accounts for
   its whole graph. A `PAUSE_EPIC` press is where the two meet: the ladder can
   only end the node, so the node parks FAILED — terminal, salvaged, swept, and
   distinguishable from the node an operator abandoned — and the epic-level half
   of that answer, stopping the scheduler, is supplied here.

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
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Sequence

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from factory.activities.agent_activities import (
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
        DisableAutoMergeInput,
        EnqueueLandingInput,
        OpenLandingPrInput,
        PollLandingInput,
        PrepareLandingPrInput,
        SyncLandingBranchInput,
        disable_auto_merge,
        enqueue_landing,
        open_landing_pr,
        poll_landing,
        prepare_landing_pr,
        sync_landing_branch,
    )
    from factory.activities.notify_activities import (
        DEFAULT_CHOICES,
        ExpireEscalationInput,
        SendEscalationInput,
        expire_escalation,
        send_escalation,
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
        RecordVerificationInput,
        RunGatesInput,
        RunJudgeInput,
        SnapshotCriteriaInput,
        check_output,
        record_verification,
        run_gates,
        run_judge,
        snapshot_criteria,
    )
    from factory.mergequeue.classify import classify
    from factory.mergequeue.models import (
        Landing,
        LandingConfig,
        LandingState,
        ObservedOutcome,
        QueueOutcome,
    )
    from factory.notify.messages import render_history, render_landing_history
    from factory.notify.service import SIGNAL_NAME
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
    )
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
    from factory.workgraph.prompt import AttemptEvidence, LandingEvidence, build_attempt_prompt
    from factory.workgraph.worktree import PreparedWorktree, branch_name

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

#: Reads and small writes: a registry parse, a spec parse, a git diff, a SQLite
#: upsert, two API calls.
_FAST = {
    "start_to_close_timeout": timedelta(minutes=2),
    "retry_policy": _RETRIES,
}

#: Proxy round trips that page spend logs on the way (001 R3).
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
#: and holding the worktree the workflow is about to salvage (US3-S3). Five
#: beats, at the adapter's `HEARTBEAT_INTERVAL_S`, is the slack a healthy attempt
#: on a busy worker needs — derived from that constant so the two can never
#: drift into a bound shorter than the beat it is bounding.
_AGENT_HEARTBEAT_TIMEOUT = timedelta(seconds=5 * HEARTBEAT_INTERVAL_S)


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


@dataclass(frozen=True)
class EpicStatus:
    """The epic's whole observable state — the query's answer and the run's result.

    `nodes` is keyed by node id in declaration order, which is also scheduling
    order (R10), so reading the status top to bottom reads the epic in the order
    it was authored to run.
    """

    epic_state: EpicState
    nodes: dict[str, NodeStatus]


@dataclass(frozen=True)
class _Escalation:
    """One page to a human, and what came back.

    `resolution` is a plain string because it has four sources with one meaning:
    a button (`RETRY`/`KILL`/`PAUSE_EPIC`), the store's `EXPIRED`, the fail-safe
    default applied when nobody was paged, and whatever the store reports when an
    expiry lost the race to a press. The ladder reads all four the same way.
    """

    escalation_id: str
    delivered: bool
    resolution: str


@workflow.defn
class EpicWorkflow:
    """One epic, from graph validation to every node terminal."""

    def __init__(self) -> None:
        #: Per-node bookkeeping in declaration order — the whole of the epic's
        #: state, and the reason replay needs no store to rebuild it.
        self._nodes: dict[str, NodeRecord] = {}
        self._epic_state = EpicState.RUNNING

        #: One background poll task per open landing, keyed by node id. Started
        #: when a PASS node's landing enqueues (US1) and reaped when the landing
        #: goes terminal. Deterministic under Temporal (`asyncio.ensure_future`
        #: inside the workflow): the poll loop is a timer-driven read, never a
        #: wall-clock one, so replay rebuilds it exactly.
        self._landing_tasks: dict[str, asyncio.Task[None]] = {}

        #: Operator answers keyed by escalation id, buffered rather than awaited.
        #: A press can arrive before the send activity has returned the id it
        #: belongs to — that is what happens when someone taps the button the
        #: instant the message lands — so nothing here may assume the workflow is
        #: already waiting.
        self._resolutions: dict[str, str] = {}

        #: The steering wheel's whole state (FR-008). Two plain flags and no
        #: persistence: a signal is a history event, so replay rebuilds both
        #: exactly where the recorded run had them (R1).
        self._paused = False
        self._kill_requested = False

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

    @workflow.signal(name=SIGNAL_NAME)
    def escalation_resolved(self, escalation_id: str, choice: str) -> None:
        """Record one operator decision (`factory/notify/service.py` sends it).

        Deliberately incurious: an id this epic never escalated is stored and
        never read, because the alternative — validating against state the
        workflow may not have written yet — drops the presses that arrive
        fastest (002's contract, and its reference flow's hardest-won ordering).
        """
        self._resolutions[escalation_id] = choice

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
                )
                for node_id, record in self._nodes.items()
            },
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
        resolved = await self._resolve(graph)
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

        while True:
            if self._kill_requested:
                break
            if self._paused:
                # Parked between two nodes, which is the only place a pause can
                # take effect: the signal may have arrived mid-attempt, and that
                # attempt has since finished its ladder (R10). Polling keeps
                # running (passive) so an in-flight landing is not left parked on
                # a live queue, but recovery dispatch waits for resume (US1).
                self._epic_state = EpicState.PAUSED
                await workflow.wait_condition(
                    lambda: not self._paused or self._kill_requested
                )
                if not self._kill_requested:
                    self._epic_state = EpicState.RUNNING
                continue
            recovery = self._next_recovery(resolved)
            if recovery is not None:
                await self._run_recovery(recovery, request, sources, judge)
                continue
            ready = self._next_ready(resolved)
            if ready is None:
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
            await self._run_node(ready, request, sources, judge)
            if self._nodes[ready.node.id].state != NodeState.PASSED:
                self._lock_out_dependents(resolved)

        if self._kill_requested:
            await self._kill_landings(graph.target_repo)
            self._kill_remaining()
            self._epic_state = EpicState.KILLED
        else:
            self._epic_state = EpicState.COMPLETED
        return self.epic_status()

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
            return await workflow.execute_activity(resolve_graph, graph, **_FAST)
        except ActivityError as exc:
            invalid = exc.cause
            if isinstance(invalid, ApplicationError) and invalid.type == GRAPH_INVALID:
                raise ApplicationError(
                    invalid.message, type=GRAPH_INVALID, non_retryable=True
                ) from exc
            raise

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

    def _next_ready(self, resolved: Sequence[ResolvedNode]) -> ResolvedNode | None:
        """The next node to dispatch: a pending recovery, then the first PENDING
        node whose every dependency has satisfied its edge.

        Recovery outranks fresh dispatch (plan.md § US2): a REJECTED landing is
        verified work that must not sit idle while independent fresh nodes run.
        The recovery ordering is a pure function of landing state, so it is
        replay-identical like the rest of the scheduler (SC-001).

        Two kinds of edge, distinguished by what unlocks them (FR-009): a
        `depends_on` edge unlocks when the dependency is *verified* — its ladder
        PASSed, `record.verified` — while a `depends_on_merged` edge unlocks only
        when the dependency has *merged*, `state == MERGED`. A verified but
        still-enqueued dependency therefore releases its verified-gated
        dependents while its own landing is still riding the queue (US1-S4).

        First, not any: declaration order is the visible tiebreak whenever more
        than one node is ready, and the deriver emits stories in spec order, so
        the spec author's sequencing is what an operator sees run (R10). Being a
        pure function of graph data and node state is also what makes scheduling
        replay-identical (SC-001).
        """
        recovery = self._next_recovery(resolved)
        if recovery is not None:
            return recovery
        for item in resolved:
            if self._nodes[item.node.id].state != NodeState.PENDING:
                continue
            if self._edges_satisfied(item.node):
                return item
        return None

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
            )

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
                ),
                **_PROXY,
            )
            record.state = NodeState.KEY_ISSUED
            # A snapshot of some earlier attempt's key is not this attempt's
            # fallback figure: teardown would attribute another attempt's spend.
            record.last_snapshot = None

            adapter_result = await self._attempt(
                record,
                lease,
                AttemptContext(
                    epic_id=graph.epic_id,
                    node_id=node.id,
                    attempt=record.attempt,
                    prompt=prompt,
                    worktree_path=prepared.path,
                    proxy_url=request.proxy_url,
                    virtual_key=lease.key,
                    model_alias=resolved.model_alias,
                    session_id=str(workflow.uuid4()),
                    timeout_s=resolved.timeout_s,
                ),
                poll_interval_s=request.poll_interval_s,
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
                await self._teardown(lease, termination, record.last_snapshot)
                action = NextAction.KILLED
                break

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

            await self._teardown(lease, termination, record.last_snapshot)

            action = next_action(
                record.history, request.config, escalations=record.escalations
            )
            if action == NextAction.ESCALATE:
                escalation = await self._escalate(graph, node, results, request.config)
                record.escalations.append(escalation.resolution)
                if escalation.resolution == EscalationChoice.PAUSE_EPIC:
                    # The press the ladder can only half answer: it ends the
                    # node (as every non-grant does), and the epic-level half —
                    # park rather than abandon, and stop dispatching — is this
                    # component's to supply (contracts/workflow.md).
                    parked = True
                    self._paused = True
                action = next_action(
                    record.history, request.config, escalations=record.escalations
                )
                if action == NextAction.ESCALATE:
                    # The grant bought an attempt the caps cannot spend — the
                    # debugger has had its turn and the budget is gone. Paging
                    # again would ask the same question forever, so the node ends
                    # where the operator was already told it might.
                    action = NextAction.KILLED

            if action in _TERMINAL_ACTIONS:
                break

            persona = (
                DEBUGGER_PERSONA if action == NextAction.DEBUGGER else node.persona
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
        *,
        poll_interval_s: int,
    ) -> AdapterResult | None:
        """Run one agent attempt, reading its spend while it works (R3).

        The adapter's output cannot carry usage numbers (D-018), so the workflow
        polls beside it and keeps the newest reading: an unreadable proxy at
        teardown then records the figure that was true a beat ago rather than
        none at all (constitution V). The poll is a read with no consequence —
        nothing here branches on a dollar figure, at any magnitude (D-021).

        The same loop is where a kill lands: the flag is checked on every beat,
        so an operator's stop takes effect within one poll interval rather than
        at the end of an attempt that may be hours long. `None` is returned for
        the attempt that was cancelled — there is no result, and the caller
        supplies the classification.
        """
        record.state = NodeState.RUNNING
        agent = workflow.start_activity(
            run_agent_attempt,
            context,
            start_to_close_timeout=timedelta(
                seconds=context.timeout_s + _ADAPTER_GRACE_S
            ),
            heartbeat_timeout=_AGENT_HEARTBEAT_TIMEOUT,
            retry_policy=_AGENT_RETRIES,
        )

        while True:
            try:
                await workflow.wait_condition(
                    lambda: agent.done() or self._kill_requested,
                    timeout=timedelta(seconds=poll_interval_s),
                )
            except asyncio.TimeoutError:
                record.last_snapshot = await workflow.execute_activity(
                    poll_usage, lease, **_FAST
                )
                continue
            if self._kill_requested and not agent.done():
                await self._cancel(agent)
                return None
            return await agent

    async def _cancel(self, agent: workflow.ActivityHandle[AdapterResult]) -> None:
        """Stop the running attempt and wait for the cancellation to be recorded.

        The adapter's KILLED path terminates the process group, archives the
        transcript (FR-007) and re-raises rather than returning, so a cancelled
        attempt reaches the workflow as a failure — which is the correct shape
        and not an error to propagate: this workflow asked for it. However the
        attempt ended once it was told to stop is not a fact the epic turns on,
        so every ending is swallowed here and the node is closed out on the
        operator's decision instead.
        """
        agent.cancel()
        try:
            await agent
        except (ActivityError, asyncio.CancelledError):
            pass

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
        """
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
        )

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
            ),
            **_PROXY,
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
    ) -> _Escalation:
        """Page a human, then wait exactly as long as waiting is worth (FR-008).

        An undelivered escalation applies the fail-safe default at once: waiting
        out an hour for a message nobody received delays the same kill and calls
        it patience (002 R11). A silence that runs out expires the row and takes
        the store's word for what happened — a press that beat the timer by a
        millisecond still decides the node (002 R12).
        """
        sent = await workflow.execute_activity(
            send_escalation,
            SendEscalationInput(
                workflow_id=workflow.info().workflow_id,
                epic_id=graph.epic_id,
                node_id=node.id,
                # Every attempt, evidence and all (SC-005): the operator is being
                # asked to decide, and one summarized failure hides the shape the
                # decision turns on.
                history_summary=render_history(results),
                choices=list(DEFAULT_CHOICES),
                timeout_s=config.escalation_timeout_s,
            ),
            **_FAST,
        )

        if not sent.delivered:
            return _Escalation(
                escalation_id=sent.escalation_id,
                delivered=False,
                resolution=EscalationChoice.KILL.value,
            )

        try:
            await workflow.wait_condition(
                lambda: sent.escalation_id in self._resolutions,
                timeout=timedelta(seconds=config.escalation_timeout_s),
            )
        except asyncio.TimeoutError:
            expired = await workflow.execute_activity(
                expire_escalation,
                ExpireEscalationInput(escalation_id=sent.escalation_id),
                **_FAST,
            )
            # `None` means the store has no record at all, which is not consent.
            resolution = expired.final_state or EscalationChoice.KILL.value
        else:
            resolution = self._resolutions[sent.escalation_id]

        return _Escalation(
            escalation_id=sent.escalation_id, delivered=True, resolution=resolution
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

        record.landing = replace(landing, enqueued_at=_now(), state=LandingState.ENQUEUED)
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

            record.landing = replace(
                record.landing,
                outcomes=record.landing.outcomes
                + (ObservedOutcome(at=_now(), outcome=outcome),),
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
                record.landing = replace(record.landing, state=LandingState.REJECTED)
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
          queue history rendered and choices `[RETRY | KILL | PAUSE_EPIC]`
          (FR-007). `RETRY` grants exactly one more cycle; 1h silence or `KILL`
          ends the node KILLED, branch preserved (FR-008); `PAUSE_EPIC` parks
          the node and pauses the epic.

        A recovery cycle that PASSes re-pushes + re-enqueues the same PR and
        starts a fresh poll — the landing is back on the queue (FR-005).
        """
        graph = request.graph
        record = self._nodes[resolved.node.id]
        landing = record.landing
        if landing is None:
            return
        config = request.landing_config

        # Exhaustion gates the automatic cycle. An operator's RETRY is not an
        # automatic cycle — it is one more cycle, granted by hand.
        if not granted and landing.recovery_cycles >= config.max_recovery_cycles:
            resolution = await self._escalate_landing(graph, request, record)
            await self._apply_landing_resolution(
                graph, request, resolved, resolution, sources, judge
            )
            return

        record.landing = replace(
            landing, recovery_cycles=landing.recovery_cycles + 1
        )
        last = record.landing.outcomes[-1].outcome

        # The sync runs first for both recovery-eligible rejections: a
        # CHECKS_FAILED needs the new target head merged in, and a CONFLICT sync
        # is what surfaces the conflicted file list the debugger resolves.
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
            resolution = await self._escalate_landing(graph, request, record)
            await self._apply_landing_resolution(
                graph, request, resolved, resolution, sources, judge
            )
            return

        # Carry the new branch point into re-verification (D-027 extended): the
        # diff and the judge see only the node's own work above the merged-in
        # target head.
        prepared = replace(record.prepared, base_ref=sync.base_ref)
        record.base_ref = sync.base_ref
        record.prepared = prepared

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
        )
        if result is not None:
            await self._reenqueue(
                graph, request, resolved, sources, judge, record, prepared, result
            )
            return

        # The recovery cycle failed again — exhaustion.
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
            ),
        )

        lease = await workflow.execute_activity(
            issue_attempt_key,
            IssueKeyInput(
                node_id=node.id,
                epic_id=graph.epic_id,
                attempt=record.attempt,
                persona=persona,
                spec_ref=node.spec_ref,
                models=list(resolved.models),
            ),
            **_PROXY,
        )
        record.last_snapshot = None

        adapter_result = await self._attempt(
            record,
            lease,
            AttemptContext(
                epic_id=graph.epic_id,
                node_id=node.id,
                attempt=record.attempt,
                prompt=prompt,
                worktree_path=prepared.path,
                proxy_url=request.proxy_url,
                virtual_key=lease.key,
                model_alias=resolved.model_alias,
                session_id=str(workflow.uuid4()),
                timeout_s=resolved.timeout_s,
            ),
            poll_interval_s=request.poll_interval_s,
        )
        if adapter_result is None or self._kill_requested:
            termination = (
                adapter_result.termination
                if adapter_result is not None
                else Termination.KILLED
            )
            await self._teardown(lease, termination, record.last_snapshot)
            return None

        termination = adapter_result.termination
        result, _verdict = await self._verify(
            request, resolved, record.criteria, prepared, record.attempt, judge, None
        )
        await self._teardown(lease, termination, record.last_snapshot)
        record.history.append(
            AttemptRecord(
                attempt=record.attempt,
                persona=persona,
                verdict=result.verdict,
                judge_outcome=None if result.judge is None else result.judge.outcome,
            )
        )
        return result if result.verdict == OverallVerdict.PASS else None

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
            state=LandingState.ENQUEUED,
        )
        record.state = NodeState.ENQUEUED
        self._landing_tasks[record.node_id] = asyncio.ensure_future(
            self._poll_landing(graph, record, config)
        )

    async def _escalate_landing(
        self, graph: WorkGraph, request: EpicInput, record: NodeRecord
    ) -> str:
        """Page a human with the rendered queue history and wait out the hour.

        The landing escalation carries the recovery evidence — every queue
        outcome in order and the recovery cycles spent — through the same
        `send_escalation` / `expire_escalation` activities the verification
        ladder uses, with choices `[RETRY | KILL | PAUSE_EPIC]` (FR-007). An
        undelivered message applies the fail-safe KILL at once; an hour of
        silence expires to KILL; the store's word on a press that beat the timer
        by a millisecond still decides (002 R12).
        """
        sent = await workflow.execute_activity(
            send_escalation,
            SendEscalationInput(
                workflow_id=workflow.info().workflow_id,
                epic_id=graph.epic_id,
                node_id=record.node_id,
                history_summary=render_landing_history(record.landing),
                choices=list(DEFAULT_CHOICES),
                timeout_s=request.config.escalation_timeout_s,
            ),
            **_FAST,
        )
        if not sent.delivered:
            return EscalationChoice.KILL.value
        try:
            await workflow.wait_condition(
                lambda: sent.escalation_id in self._resolutions,
                timeout=timedelta(seconds=request.config.escalation_timeout_s),
            )
        except asyncio.TimeoutError:
            expired = await workflow.execute_activity(
                expire_escalation,
                ExpireEscalationInput(escalation_id=sent.escalation_id),
                **_FAST,
            )
            return expired.final_state or EscalationChoice.KILL.value
        return self._resolutions[sent.escalation_id]

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
        exactly as the verification ladder's escalation does. `RETRY` is not
        routed here — the caller grants one more recovery cycle.
        """
        record = self._nodes[resolved.node.id]
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
