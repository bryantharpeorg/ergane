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

Five orderings and one omission are this module's own contribution, and each is
load-bearing:

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

The omission is the judge. 002's flow consults it when the gates are green, the
output check passed, and the criteria carry acceptance scenarios; this
interpreter asks the same question (`judge_required`) and cannot yet answer it,
because two shapes no shipped activity provides are missing — where the
worktree's diff is read, and how the `judge` persona's model alias resolves
(`resolve_graph` answers only for graph nodes). Rather than pass unjudged work
off as judged, an attempt that *would* have been scored is recorded with
`judge_unavailable` set: the row then says, in the column built for exactly this,
that this PASS was reached without judge agreement. Wiring the judge is a
follow-up that owes a test first, and the flag is what will make its absence
impossible to forget.

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
        RemoveWorktreeInput,
        SalvageWorktreeInput,
        load_prompt_sources,
        prepare_worktree,
        remove_worktree,
        resolve_graph,
        run_agent_attempt,
        salvage_worktree,
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
        CheckOutputInput,
        RecordVerificationInput,
        RunGatesInput,
        SnapshotCriteriaInput,
        check_output,
        record_verification,
        run_gates,
        snapshot_criteria,
    )
    from factory.notify.messages import render_history
    from factory.notify.service import SIGNAL_NAME
    from factory.usage.models import KeyLease, Termination
    from factory.verify.ladder import DEBUGGER_PERSONA, next_action
    from factory.verify.models import (
        AttemptRecord,
        CriteriaSet,
        EscalationChoice,
        NextAction,
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
        WorkGraph,
        WorkNode,
    )
    from factory.workgraph.prompt import AttemptEvidence, build_attempt_prompt
    from factory.workgraph.worktree import PreparedWorktree, branch_name

#: The one task queue every epic and every activity of this component runs on
#: (D-002). Named here rather than in the worker so the worker, the CLI and the
#: workflow cannot drift apart on a string.
TASK_QUEUE = "workgraph"

#: How often the workflow reads what a live attempt has spent (R3). A poll is a
#: read with no consequence — enforcement is deferred (D-021) — and its only
#: product is the fallback figure teardown records when the final read fails.
#: Settable per epic because a test cannot afford production's interval and
#: production cannot afford a test's.
DEFAULT_POLL_INTERVAL_S = 30

#: Node states from which no dependent can ever be dispatched. A node whose
#: dependency reached one of these is KILLED where it stands, never dispatched
#: (SC-002) — the epic's remaining ready set is then a fact about the graph
#: rather than a race between the scheduler and a dead branch.
_UNREACHABLE = frozenset({NodeState.FAILED, NodeState.KILLED})

#: Ladder actions that end a node.
_TERMINAL_ACTIONS = frozenset({NextAction.PASSED, NextAction.KILLED})

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

#: Grace on top of one gate's own deadline before the *activity* is declared
#: dead: the runner's SIGTERM → SIGKILL escalation has to have time to land and
#: be reported as a TIMEOUT gate result rather than as a lost activity.
_GATE_HEARTBEAT_GRACE_S = 60

#: Grace on top of the node's own deadline before the *activity* is declared
#: dead. The adapter enforces the deadline itself and then has work to do —
#: TERM, KILL, archive the transcript (FR-007) — and an activity timeout that
#: fired first would discard exactly the evidence that path exists to produce.
_ADAPTER_GRACE_S = 120

#: Missed beats before a live attempt is presumed dead. The adapter beats every
#: `HEARTBEAT_INTERVAL_S`; a bound of one beat would fail a healthy attempt on a
#: busy worker, and this is also what makes a cancellation land within a beat.
_AGENT_HEARTBEAT_TIMEOUT = timedelta(seconds=4 * HEARTBEAT_INTERVAL_S)


@dataclass(frozen=True)
class EpicInput:
    """One epic's whole dispatch — the workflow's only argument.

    `graph` is the compiled artifact (never hand-authored, FR-011) and carries
    the epic's identity, its target repo and its specs root. `proxy_url` is where
    the agent's virtual key is honored. `config` is the ladder's caps, passed in
    rather than read so an operator's retry policy is a property of the epic they
    started (002's `VerificationConfig`). `poll_interval_s` is the usage-poll beat
    (R3).
    """

    graph: WorkGraph
    proxy_url: str
    config: VerificationConfig = VerificationConfig()
    poll_interval_s: int = DEFAULT_POLL_INTERVAL_S


@dataclass(frozen=True)
class NodeStatus:
    """One node as an operator reads it (contracts/workflow.md § Query).

    Deliberately narrower than `NodeRecord`: the branch is what survives every
    sweep, the state and attempt are what a human is watching, and the attempt
    history is evidence that belongs in the store rather than in a status line.
    """

    state: NodeState
    attempt: int
    branch: str


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

        #: Operator answers keyed by escalation id, buffered rather than awaited.
        #: A press can arrive before the send activity has returned the id it
        #: belongs to — that is what happens when someone taps the button the
        #: instant the message lands — so nothing here may assume the workflow is
        #: already waiting.
        self._resolutions: dict[str, str] = {}

    # --- signals and queries -------------------------------------------------

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
                    state=record.state, attempt=record.attempt, branch=record.branch
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
            ready = self._next_ready(resolved)
            if ready is None:
                # Every node is terminal: a non-terminal node either had a ready
                # dependency chain (and would have been picked) or a dead one
                # (and was killed the moment that dependency died).
                break
            await self._run_node(ready, request, sources)
            if self._nodes[ready.node.id].state != NodeState.PASSED:
                self._lock_out_dependents(resolved)

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

    def _next_ready(self, resolved: Sequence[ResolvedNode]) -> ResolvedNode | None:
        """The first PENDING node whose every dependency has PASSED (FR-003).

        First, not any: declaration order is the visible tiebreak whenever more
        than one node is ready, and the deriver emits stories in spec order, so
        the spec author's sequencing is what an operator sees run (R10). Being a
        pure function of graph data and node state is also what makes scheduling
        replay-identical (SC-001).
        """
        for item in resolved:
            if self._nodes[item.node.id].state != NodeState.PENDING:
                continue
            if all(
                self._nodes[dependency].state == NodeState.PASSED
                for dependency in item.node.depends_on
            ):
                return item
        return None

    def _lock_out_dependents(self, resolved: Sequence[ResolvedNode]) -> None:
        """Kill what can no longer be dispatched, transitively (SC-002).

        Run the moment a node ends anything but PASSED. A dependent is marked
        KILLED without a worktree, a key or an attempt — the edge stayed locked,
        so there is nothing to salvage and nothing to sweep — and the pass
        repeats until it settles, because a chain three deep dies all at once.
        """
        settled = False
        while not settled:
            settled = True
            for item in resolved:
                record = self._nodes[item.node.id]
                if record.state != NodeState.PENDING:
                    continue
                if any(
                    self._nodes[dependency].state in _UNREACHABLE
                    for dependency in item.node.depends_on
                ):
                    record.state = NodeState.KILLED
                    settled = False

    # --- one node's life ----------------------------------------------------

    async def _run_node(
        self,
        resolved: ResolvedNode,
        request: EpicInput,
        sources: PromptSources,
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

        results: list[VerificationResult] = []
        evidence: list[AttemptEvidence] = []
        persona = node.persona

        while True:
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
            termination = adapter_result.termination

            record.state = NodeState.VERIFYING
            result = await self._verify(
                graph.epic_id,
                resolved,
                criteria,
                prepared,
                record.attempt,
                request.config,
            )
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

            # The bracket closes on the adapter's word about the process, and on
            # the last thing the proxy was willing to tell us (FR-004, R3).
            await workflow.execute_activity(
                teardown_attempt,
                TeardownInput(
                    lease=lease,
                    termination=termination,
                    last_snapshot=record.last_snapshot,
                ),
                **_PROXY,
            )

            action = next_action(
                record.history, request.config, escalations=record.escalations
            )
            if action == NextAction.ESCALATE:
                escalation = await self._escalate(graph, node, results, request.config)
                record.escalations.append(escalation.resolution)
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

        await self._close_out(
            graph, node, record, termination, passed=action == NextAction.PASSED
        )

    async def _attempt(
        self,
        record: NodeRecord,
        lease: KeyLease,
        context: AttemptContext,
        *,
        poll_interval_s: int,
    ) -> AdapterResult:
        """Run one agent attempt, reading its spend while it works (R3).

        The adapter's output cannot carry usage numbers (D-018), so the workflow
        polls beside it and keeps the newest reading: an unreadable proxy at
        teardown then records the figure that was true a beat ago rather than
        none at all (constitution V). The poll is a read with no consequence —
        nothing here branches on a dollar figure, at any magnitude (D-021).
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
                    agent.done, timeout=timedelta(seconds=poll_interval_s)
                )
            except asyncio.TimeoutError:
                record.last_snapshot = await workflow.execute_activity(
                    poll_usage, lease, **_FAST
                )
                continue
            return await agent

    async def _verify(
        self,
        epic_id: str,
        resolved: ResolvedNode,
        criteria: CriteriaSet,
        prepared: PreparedWorktree,
        attempt: int,
        config: VerificationConfig,
    ) -> VerificationResult:
        """Gates, then output, then the verdict — and the row before anything else.

        Cheapest-first is 002's flow invariant 2 rather than an optimization: a
        node whose lint gate failed in two seconds must not cost a completion to
        find that out. `judge_required` is the question that guard asks, and this
        component cannot yet answer it (see the module docstring) — so an attempt
        that would have been scored is flagged `judge_unavailable`, which is the
        one column that says "this PASS was reached without judge agreement".
        """
        node = resolved.node
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
                expected_artifacts=[],
            ),
            **_FAST,
        )

        result = compose_result(
            epic_id=epic_id,
            node_id=node.id,
            attempt=attempt,
            form=VerificationForm.PHASE,
            gate_results=gate_results,
            output_check=output,
            judge=None,
            criteria_sha256=criteria.source_sha256,
            spec_ref=node.spec_ref,
            started_at=started_at,
            finished_at=_now(),
        )
        if judge_required(gate_results, output, criteria):
            result = replace(result, judge_unavailable=True)

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
        return replace(result, criteria_drift=recorded.criteria_drift)

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
        passed: bool,
    ) -> None:
        """Salvage, sweep, then say what the node became (constitution VI).

        In that order on every path out, pass included: the salvage commit
        carries the attempt number and the termination the adapter classified, so
        the branch alone accounts for how the node ended once `.factory/` is
        swept (SC-004). Removal takes the directory and never the record — the
        branch and its commits outlive it.
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
        await workflow.execute_activity(
            remove_worktree,
            RemoveWorktreeInput(
                epic_id=graph.epic_id,
                node_id=node.id,
                target_repo=graph.target_repo,
            ),
            **_GIT,
        )
        record.state = NodeState.PASSED if passed else NodeState.KILLED


def _now() -> str:
    """The workflow's own clock, in the factory's one timestamp spelling.

    `workflow.now()` rather than `datetime.now()`: a replayed workflow has to
    stamp a row with the same instant the first run did.
    """
    return _iso(workflow.now())


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")
