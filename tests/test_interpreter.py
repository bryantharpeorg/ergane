"""The interpreter itself — one graph, driven to the end, against a fake world.

`factory/workgraph/workflow.py` is the component: one generic workflow that reads
a WorkGraph and drives every node through dispatch → agent attempt → 002's
verification ladder to a terminal state, unlocking downstream edges on nothing but
a PASS. `contracts/workflow.md` states that loop; this file executes it under
Temporal's time-skipping environment with every activity it calls replaced by a
script.

Everything the workflow touches is faked, and every fake is registered under the
*real* activity name — `resolve_graph`, `prepare_worktree`, `run_agent_attempt`,
`issue_attempt_key`, `poll_usage`, `teardown_attempt`, `snapshot_criteria`,
`run_gates`, `check_output`, `record_verification`, `salvage_worktree`,
`remove_worktree`, `send_escalation`, `expire_escalation` — so a rename in any of
the three components' activity surfaces breaks these tests instead of silently
bypassing them. No subprocess runs, no proxy is called, no repository is touched.

What is *not* faked is the decision-making. The ladder is
`factory/verify/ladder.py`, the verdict is `compose_result`'s, the graph rejection
is `validate_workgraph`'s, and the prompt is `build_attempt_prompt`'s. A workflow
that reimplemented any of those inline would satisfy its own policy and fail
these tests.

What this suite pins down, in the order the contract states it:

- **A node dispatches only when every dependency has PASSED** (FR-003, SC-002).
  Asserted from inside the running attempt: the scripted agent queries
  `epic_status` while it is the in-flight node, so "B had not started while A was
  running" is observed at the moment it matters rather than inferred from a
  terminal snapshot. The same query proves the converse on the failure path — a
  node whose dependency was killed never dispatches at all, and the independent
  leaf still runs.

- **Every attempt is bracketed and recorded** (FR-004, SC-003). One
  `issue_attempt_key` opens it, one `teardown_attempt` closes it carrying the
  adapter's termination, and `record_verification` lands before anything acts on
  the verdict — before a retry prompt exists, before an operator is paged, before
  a worktree is swept. Asserted structurally from the call log, per node: "both
  happened" is true of an ordering that loses the row to a crash mid-escalation,
  which is the ordering this forbids.

- **Retry evidence survives the trip through workflow state** (FR-006, SC-004).
  The failing gate's `output_tail` appears as an exact substring of the *next*
  attempt's prompt — the prompt the scripted agent actually received, not one
  rebuilt by the test.

- **Nothing terminal loses work** (constitution VI, SC-004). Salvage precedes
  removal on every path out of a node, kill included, and the salvage carries the
  attempt number and the termination the adapter classified.

- **The verdict is never the agent's** (FR-012). A TIMEOUT attempt runs the gates
  like any other: the worktree may hold salvageable work, and no agent signal —
  in either direction — shortcuts verification.

- **Replay dispatches nothing twice** (US1-S4, SC-001). The recorded history is
  replayed against the workflow code with no worker attached; a nondeterministic
  loop fails there, and the scripted world proves no activity ran again.

- **The steering wheel is honored** (FR-008, US3-S2/US3-S3). `pause_epic` stops
  the *scheduler*, not the attempt: the in-flight node finishes its whole ladder,
  no next node starts until `resume_epic`, and a `PAUSE_EPIC` press on an
  escalation parks its node FAILED and pauses the epic by the same route.
  `kill_epic` is the one signal that interrupts an attempt — the adapter is
  cancelled, the worktree salvaged, the key torn down, and every node that never
  ran is recorded KILLED. Both signals are sent by *name*, because the name is
  the wire contract an operator types and the notify bridge routes.

Three properties of the setup are deliberate:

- **The scripted criteria carry FR bullets and no acceptance scenarios**, so
  `judge_required` is false throughout and the judge is never consulted (002's
  flow invariant 2, asserted). That is a designed-for shape — `has_scenarios`
  exists precisely to say a node owing only `FR-###` bullets is verified on its
  gates and its output check alone — and it keeps this suite on the interpreter.
  The judge's own composition (its key lifecycle, its rewrites, its feedback) is
  002's contract, proven under time skipping in `tests/test_verification_flow.py`.
  Wiring the judge into the interpreter still needs two things no shipped
  activity provides — where the worktree diff is read, and how the `judge`
  persona's model alias is resolved (`resolve_graph` answers only for graph
  nodes) — and inventing either shape inside a test is how a test starts
  designing the system it is supposed to check.

- **Time skipping is locked while an activity runs**, which is why the usage-poll
  interval is an input rather than a constant: the poll timer competes with the
  agent activity in real seconds, so the one test that asserts the poll loop
  shortens it and the scripted agent waits for a beat before returning. Every
  other test leaves the interval long, and no poll fires.

- **The graph is a chain plus an independent leaf** (`us1 → us2`, `us3` alone),
  declared in that order. It is the smallest shape that can tell "scheduled in
  declaration order" from "scheduled by readiness" and can show a failure
  stopping one branch without touching the other.

Written before `factory/workgraph/workflow.py` exists (T018 precedes T019): until
the module lands, every test here fails at import. The signal tests were written
the same way one task later (T025 precedes T026): until the handlers exist, an
unhandled signal is *buffered* rather than rejected, so they fail on a status
query that never reports the state they are waiting for.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, AsyncIterator, Callable, Sequence

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from factory.activities.agent_activities import (
    GRAPH_INVALID,
    LoadPromptSourcesInput,
    PrepareWorktreeInput,
    PromptSources,
    RemoveWorktreeInput,
    SalvageWorktreeInput,
)
from factory.activities.notify_activities import (
    ExpiredEscalation,
    ExpireEscalationInput,
    SendEscalationInput,
    SentEscalation,
)
from factory.activities.usage_activities import IssueKeyInput, TeardownInput
from factory.activities.verify_activities import (
    CheckOutputInput,
    RecordedVerification,
    RecordVerificationInput,
    RunGatesInput,
    RunJudgeInput,
    SnapshotCriteriaInput,
)
from factory.config import Persona, WriteScope
from factory.notify.service import SIGNAL_NAME
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.verify.ladder import DEBUGGER_PERSONA
from factory.verify.models import (
    CriteriaSet,
    EscalationChoice,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    VerificationConfig,
    VerificationResult,
)
from factory.verify.store import EXPIRED
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    EpicState,
    NodeState,
    ResolvedNode,
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.worktree import PreparedWorktree, branch_name
from factory.workgraph.workflow import EpicInput, EpicWorkflow

EPIC_ID = "demo-loans"
FEATURE = "007-library-loans"
SPECS_ROOT = "specs"
TARGET_REPO = "/srv/factory/targets/library"
PROXY_URL = "http://litellm.test"

#: The contract's workflow-id convention (R12). The CLI mints it; this suite
#: reproduces it because the scripted agent queries the epic by id from inside a
#: running attempt.
WORKFLOW_ID = f"epic-{EPIC_ID}"

#: The real task queue name (D-002) — the worker registers on it in production,
#: and using it here means a typo in either place shows up as a hung test.
TASK_QUEUE = "workgraph"

#: The operator's steering wheel (contracts/workflow.md § Signals), spelled as
#: the names go over the wire. Sent as strings rather than through the workflow
#: class on purpose: `temporal workflow signal --name pause_epic` is the
#: documented operator surface (R12), so the string *is* the contract, and a
#: handler renamed under a still-compiling method reference would pass a test
#: that used one.
PAUSE_SIGNAL = "pause_epic"
RESUME_SIGNAL = "resume_epic"
KILL_SIGNAL = "kill_epic"

#: How long a real-time wait for a workflow state gives up after. Generous
#: because it is only ever paid in full by a failing test, and short enough that
#: a missing handler is a failure inside a minute rather than a hung suite.
WAIT_TIMEOUT_S = 10.0

#: The quiet moment a paused epic is watched through: long enough that a workflow
#: treating pause as advisory would have dispatched the next node inside it.
SETTLE_S = 0.5

#: Where the scripted `prepare_worktree` claims the node's worktree is. Nothing
#: is created on disk; the path is an identity the gates, the output check and
#: the attempt context must all agree on.
WORKTREE_ROOT = "/srv/factory/.factory/worktrees"

#: The persona registry the scripted `resolve_graph` resolves against — the same
#: shape `load_personas` returns, so the real `validate_workgraph` runs against
#: it unchanged.
MODEL_ALIAS = "implementer-alias"
FALLBACK_ALIAS = "implementer-fallback"
TIMEOUT_S = 5400
DEBUGGER_TIMEOUT_S = 7200

#: What the standards key of the target repo's `factory.yaml` declares (R11).
#: `load_prompt_sources` reads it, `prepare_worktree` demands it, and the prompt
#: points the agent at it — one value, three hops.
STANDARDS_PATH = ".specify/memory/constitution.md"

#: Failing gate output, one distinctive block per attempt. Every one is asserted
#: to survive verbatim into the next attempt's prompt (FR-006, SC-004) and into
#: the escalation's failure history, so no two may be substrings of another.
GATE_TAIL = {
    1: "E   AssertionError: attempt-one recorded no loan against the member",
    2: "E   TypeError: attempt-two Catalogue.borrow() missing 1 argument",
    3: "E   AssertionError: attempt-three refused an available book",
    4: "E   AssertionError: attempt-four debugger left the ledger unwritten",
}


# --- the epic's authored text (what `load_prompt_sources` reads) --------------


STORY_ONE = """### User Story 1 - Borrow a book (Priority: P1)

A member borrows an available book and the catalogue records the loan.
"""

STORY_TWO = """### User Story 2 - Return a book (Priority: P2)

A member returns a book and the catalogue clears the loan.
"""

STORY_THREE = """### User Story 3 - List the shelves (Priority: P3)

Anyone lists which books are on the shelf right now.
"""

FR_ONE = "- **FR-001**: The catalogue MUST record every loan against the borrowing member."
FR_TWO = "- **FR-002**: The catalogue MUST clear a loan when the book is returned."
FR_THREE = "- **FR-003**: The catalogue MUST list every book not currently on loan."

SPEC_TEXT = f"""# Feature Specification: Library Loans

## User Scenarios & Testing

{STORY_ONE}
{STORY_TWO}
{STORY_THREE}
## Requirements

### Functional Requirements

{FR_ONE}
{FR_TWO}
{FR_THREE}
"""

PLAN_TEXT = """# Implementation Plan: Library Loans

## Summary

One `loans` table is the system of record; the catalogue reads it and never
caches it.
"""

TASKS_TEXT = """# Tasks: Library Loans

## Phase 1: Setup

- [ ] T001 Create the package skeleton

## Phase 2: User Story 1 - Borrow a book (Priority: P1)

- [ ] T002 [US1] Write tests/test_loans.py FIRST — records a loan
- [ ] T003 [US1] Implement library/loans.py until T002 passes

## Phase 3: User Story 2 - Return a book (Priority: P2)

- [ ] T004 [US2] Write tests/test_returns.py FIRST
- [ ] T005 [US2] Implement the return path until T004 passes

## Phase 4: User Story 3 - List the shelves (Priority: P3)

- [ ] T006 [US3] Write tests/test_shelves.py FIRST
- [ ] T007 [US3] Implement the shelf listing until T006 passes
"""

#: One FR per story, exactly as the fixture spec declares them — the deriver's
#: `requirement_keys = [story_key, *implements]`.
FR_FOR = {"US1": "FR-001", "US2": "FR-002", "US3": "FR-003"}


# --- the graph ----------------------------------------------------------------


def make_node(node_id: str, story_key: str, **overrides: Any) -> WorkNode:
    """One node as the deriver would compile it (FR-011)."""
    fields: dict[str, Any] = {
        "id": node_id,
        "story_key": story_key,
        "persona": "implementer",
        "spec_ref": f"{FEATURE}:{story_key}",
        "requirement_keys": [story_key, FR_FOR[story_key]],
        "depends_on": [],
    }
    fields.update(overrides)
    return WorkNode(**fields)


def chain_and_leaf() -> list[WorkNode]:
    """`us1 → us2`, plus the independent `us3` — declared in that order (R10)."""
    return [
        make_node("us1", "US1"),
        make_node("us2", "US2", depends_on=["us1"]),
        make_node("us3", "US3"),
    ]


def make_graph(nodes: list[WorkNode] | None = None, **overrides: Any) -> WorkGraph:
    fields: dict[str, Any] = {
        "epic_id": EPIC_ID,
        "feature": FEATURE,
        "specs_root": SPECS_ROOT,
        "target_repo": TARGET_REPO,
        "nodes": nodes if nodes is not None else chain_and_leaf(),
    }
    fields.update(overrides)
    return WorkGraph(**fields)


PERSONAS = {
    "implementer": Persona(
        name="implementer",
        agent="claude-code",
        model=MODEL_ALIAS,
        fallback=FALLBACK_ALIAS,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=TIMEOUT_S,
    ),
    DEBUGGER_PERSONA: Persona(
        name=DEBUGGER_PERSONA,
        agent="claude-code",
        model="debugger-alias",
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=DEBUGGER_TIMEOUT_S,
    ),
}


# --- scripted evidence --------------------------------------------------------


def gate_pass(name: str = "test") -> GateResult:
    return GateResult(
        name=name,
        command="uv run pytest -q",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=11.5,
        output_tail="41 passed in 11.44s",
    )


def gate_fail(attempt: int, name: str = "test") -> GateResult:
    return GateResult(
        name=name,
        command="uv run pytest -q",
        status=GateStatus.FAIL,
        exit_code=1,
        duration_s=9.0,
        output_tail=GATE_TAIL[attempt],
    )


def wrote_something() -> OutputCheck:
    return OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


def criteria_for(node: WorkNode) -> CriteriaSet:
    """What `snapshot_criteria` answers with: the node's FR bullet, no scenarios.

    A node owing only `FR-###` bullets is verified on its gates and its output
    check alone (`has_scenarios`), which is what keeps the judge — and the two
    unresolved questions its wiring raises — out of this suite.
    """
    key = FR_FOR[node.story_key]
    return CriteriaSet(
        feature=FEATURE,
        spec_ref=node.spec_ref,
        requirements=[
            Requirement(
                key=key,
                kind=RequirementKind.FUNCTIONAL,
                title=None,
                priority=None,
                body=f"The catalogue MUST satisfy {key}.",
                scenarios=[],
            )
        ],
        source_path=f"{SPECS_ROOT}/{FEATURE}/spec.md",
        source_sha256="0" * 64,
        snapshotted_at="2026-08-05T09:00:00Z",
    )


@dataclass(frozen=True)
class Attempt:
    """What the world does to one attempt of one node.

    `termination` is the adapter's classification and travels to teardown and to
    the salvage commit; the gates decide the verdict independently of it, which
    is FR-012 in the shape of a fixture.
    """

    gates: list[GateResult] = field(default_factory=lambda: [gate_pass()])
    output: OutputCheck = field(default_factory=wrote_something)
    termination: Termination = Termination.COMPLETED


def passing() -> Attempt:
    return Attempt()


def failing(attempt: int) -> Attempt:
    """A gate failure — the whole verdict, with no judge in the picture."""
    return Attempt(gates=[gate_fail(attempt)])


def all_passing() -> dict[str, list[Attempt]]:
    return {"us1": [passing()], "us2": [passing()], "us3": [passing()]}


# --- the scripted world -------------------------------------------------------


#: Activity names that act on a verdict. Nothing in this set may precede the
#: `record_verification` of the attempt it belongs to (002 flow invariant 3).
_ACTIONS = frozenset(
    {"send_escalation", "expire_escalation", "salvage_worktree", "remove_worktree"}
)


class ScriptedWorld:
    """Every activity the interpreter calls, answered from a per-node script.

    The script is `{node_id: [Attempt, ...]}`, indexed by attempt number, so a
    node's third attempt is `script["us1"][2]`. Which node and attempt is current
    is tracked from the activity requests themselves rather than from a counter
    the test maintains: the workflow says whose attempt this is, and a workflow
    that dispatched the wrong node reads its own answer back.

    Running past a node's script is recorded as `overrun` rather than raised — an
    activity that raised would be retried by Temporal and hang the test instead
    of failing it.
    """

    def __init__(
        self,
        script: dict[str, list[Attempt]],
        *,
        client: Any,
        delivered: bool = True,
        press: str | None = None,
        expiry_state: str | None = EXPIRED,
        wait_for_poll: bool = False,
        signal_during: dict[str, str] | None = None,
        await_cancel: bool = False,
    ) -> None:
        self._script = script
        self._client = client
        self._delivered = delivered
        self._press = press
        self._expiry_state = expiry_state
        self._wait_for_poll = wait_for_poll
        #: `{node_id: signal name}` — sent from inside that node's attempt, so
        #: the operator's hand lands on the wheel while the node is genuinely in
        #: flight. Any other timing tests a different thing.
        self._signal_during = signal_during or {}
        self._await_cancel = await_cancel

        #: Activity names in call order, and the same log with the node each call
        #: belonged to — "what happened to us1" is a list rather than an offset
        #: someone has to count out by hand.
        self.calls: list[str] = []
        self.node_calls: list[tuple[str, str]] = []

        self.graphs: list[WorkGraph] = []
        self.prompt_source_requests: list[LoadPromptSourcesInput] = []
        self.criteria_requests: list[SnapshotCriteriaInput] = []
        self.prepare_requests: list[PrepareWorktreeInput] = []
        self.key_requests: list[IssueKeyInput] = []
        self.attempts: list[AttemptContext] = []
        self.polls: list[tuple[str, int, UsageSnapshot]] = []
        self.teardowns: list[TeardownInput] = []
        self.gate_requests: list[RunGatesInput] = []
        self.output_requests: list[CheckOutputInput] = []
        self.judge_requests: list[RunJudgeInput] = []
        self.records: list[VerificationResult] = []
        self.salvages: list[SalvageWorktreeInput] = []
        self.removals: list[RemoveWorktreeInput] = []
        self.escalation_requests: list[SendEscalationInput] = []
        self.escalation_ids: list[str] = []
        self.expirations: list[str] = []

        #: What `epic_status` said while each node's attempt was in flight — the
        #: only place a mid-epic view of the graph can be taken.
        self.observed: dict[str, Any] = {}

        #: Nodes whose attempt was cancelled by the workflow (the adapter's kill
        #: path, R2). Kept out of the call log because it is recorded by the
        #: activity worker while the workflow is already salvaging: an ordering
        #: the call log has no way to be honest about.
        self.cancellations: list[str] = []

        #: The handle of the run in progress, for the replay test.
        self.handle: Any = None

        self._node = ""
        self._attempt = 0
        self._spend = 0.0
        self._polled = asyncio.Event()

    # --- bookkeeping --------------------------------------------------------

    def _log(self, name: str, node_id: str | None = None) -> None:
        if node_id:
            self._node = node_id
        self.calls.append(name)
        self.node_calls.append((self._node, name))

    @property
    def _current(self) -> Attempt:
        attempts = self._script.get(self._node)
        if not attempts:
            self.calls.append("unscripted")
            return passing()
        if self._attempt > len(attempts):
            self.calls.append("overrun")
            return attempts[-1]
        return attempts[self._attempt - 1]

    def sequence(self, node_id: str, *, without: Sequence[str] = ("poll_usage",)) -> list[str]:
        """One node's activity calls in order, minus the noisy ones."""
        return [
            name
            for node, name in self.node_calls
            if node == node_id and name not in without
        ]

    @property
    def dispatched(self) -> list[str]:
        """The nodes an agent actually ran for, in dispatch order."""
        return [context.node_id for context in self.attempts]

    def prompts_for(self, node_id: str) -> list[str]:
        return [c.prompt for c in self.attempts if c.node_id == node_id]

    def teardown_for(self, node_id: str, attempt: int) -> TeardownInput:
        [found] = [
            request
            for request in self.teardowns
            if request.lease.node_id == node_id and request.lease.attempt == attempt
        ]
        return found

    # --- the fakes ----------------------------------------------------------

    def activities(self) -> list[Any]:
        script = self

        @activity.defn(name="resolve_graph")
        async def resolve_graph(graph: WorkGraph) -> list[ResolvedNode]:
            script._log("resolve_graph")
            script.graphs.append(graph)
            try:
                # The real validator, against a real registry: a graph this
                # rejects must never reach a dispatch (FR-002).
                validate_workgraph(graph, PERSONAS)
            except WorkGraphError as exc:
                raise ApplicationError(
                    str(exc), type=GRAPH_INVALID, non_retryable=True
                ) from exc

            resolved = []
            for node in graph.nodes:
                persona = PERSONAS[node.persona]
                resolved.append(
                    ResolvedNode(
                        node=node,
                        model_alias=persona.model or "",
                        models=[a for a in (persona.model, persona.fallback) if a],
                        write_scope=persona.write_scope.value,
                        timeout_s=node.timeout_override_s or (persona.timeout_s or 0),
                    )
                )
            return resolved

        @activity.defn(name="load_prompt_sources")
        async def load_prompt_sources(
            request: LoadPromptSourcesInput,
        ) -> PromptSources:
            script._log("load_prompt_sources")
            script.prompt_source_requests.append(request)
            return PromptSources(
                spec_text=SPEC_TEXT,
                plan_text=PLAN_TEXT,
                tasks_text=TASKS_TEXT,
                standards=STANDARDS_PATH,
            )

        @activity.defn(name="snapshot_criteria")
        async def snapshot_criteria(request: SnapshotCriteriaInput) -> CriteriaSet:
            node = _node_of_spec_ref(request.spec_ref)
            script._log("snapshot_criteria", node.id)
            script.criteria_requests.append(request)
            return criteria_for(node)

        @activity.defn(name="prepare_worktree")
        async def prepare_worktree(request: PrepareWorktreeInput) -> PreparedWorktree:
            script._log("prepare_worktree", request.node_id)
            script.prepare_requests.append(request)
            return PreparedWorktree(
                path=f"{WORKTREE_ROOT}/{request.epic_id}/{request.node_id}",
                branch=branch_name(request.epic_id, request.node_id),
                base_ref="9" * 40,
            )

        @activity.defn(name="issue_attempt_key")
        async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
            script._log(f"issue_attempt_key:{request.persona}", request.node_id)
            script.key_requests.append(request)
            # The judge's key rides on the node's attempt number; only a node
            # attempt advances the script.
            script._attempt = request.attempt
            return KeyLease(
                key=f"sk-{request.node_id}-{request.attempt}-{request.persona}",
                key_alias=f"{request.epic_id}:{request.node_id}:{request.attempt}",
                node_id=request.node_id,
                epic_id=request.epic_id,
                attempt=request.attempt,
                persona=request.persona,
                spec_ref=request.spec_ref,
                issued_at="2026-08-05T09:30:00Z",
            )

        @activity.defn(name="run_agent_attempt")
        async def run_agent_attempt(context: AttemptContext) -> AdapterResult:
            script._log("run_agent_attempt", context.node_id)
            script.attempts.append(context)
            script._attempt = context.attempt

            # The one view of the epic taken while a node is genuinely in
            # flight: the workflow is parked on this activity and answers the
            # query from the same state it is scheduling from.
            handle = script._client.get_workflow_handle(WORKFLOW_ID)
            script.observed[context.node_id] = await handle.query(
                EpicWorkflow.epic_status
            )

            steer = script._signal_during.get(context.node_id)
            if steer is not None:
                # The signal lands in history *before* this activity completes,
                # which is the only timing under which "the in-flight attempt"
                # names anything at all (US3-S2, US3-S3).
                await handle.signal(steer)

            if script._await_cancel and steer is not None:
                # The adapter's kill path (R2): it waits, heartbeating, and on
                # cancellation archives the transcript and re-raises. Bounded, so
                # a workflow that never cancels fails an assertion rather than
                # hanging the suite — and the overrun is recorded, because
                # "the attempt ran to completion" is exactly the bug.
                for _ in range(int(WAIT_TIMEOUT_S / 0.05)):
                    activity.heartbeat()
                    try:
                        await asyncio.sleep(0.05)
                    except asyncio.CancelledError:
                        script.cancellations.append(context.node_id)
                        raise
                script.calls.append("never_cancelled")

            if script._wait_for_poll:
                # Bounded, so a workflow with no poll loop fails the assertion
                # instead of hanging the suite.
                try:
                    await asyncio.wait_for(script._polled.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass

            return AdapterResult(
                termination=script._current.termination,
                transcript_path=(
                    f"/srv/factory/.factory/transcripts/{context.epic_id}/"
                    f"{context.node_id}/attempt-{context.attempt}"
                ),
            )

        @activity.defn(name="poll_usage")
        async def poll_usage(lease: KeyLease) -> UsageSnapshot:
            script._log("poll_usage", lease.node_id)
            script._spend = round(script._spend + 0.011, 6)
            snapshot = UsageSnapshot(
                spend_usd=script._spend, captured_at="2026-08-05T09:31:00Z"
            )
            script.polls.append((lease.node_id, lease.attempt, snapshot))
            script._polled.set()
            return snapshot

        @activity.defn(name="run_gates")
        async def run_gates(request: RunGatesInput) -> list[GateResult]:
            script._log("run_gates", _node_of_worktree(request.worktree_path))
            script.gate_requests.append(request)
            return script._current.gates

        @activity.defn(name="check_output")
        async def check_output(request: CheckOutputInput) -> OutputCheck:
            script._log("check_output", _node_of_worktree(request.worktree_path))
            script.output_requests.append(request)
            return script._current.output

        @activity.defn(name="run_judge")
        async def run_judge(request: RunJudgeInput) -> JudgeVerdict:
            # Registered so the name alignment is real, and recorded rather than
            # raised: a judge consulted for criteria with no scenarios is an
            # assertion failure in the tests, not a hang in the harness.
            script._log("run_judge")
            script.judge_requests.append(request)
            return JudgeVerdict(
                outcome=JudgeOutcome.PASS,
                findings=[
                    JudgeScenarioFinding(
                        scenario="none", passed=True, reasoning="nothing to score"
                    )
                ],
                feedback="",
                judge_attempt=1,
                truncated_input=False,
                model_alias=request.model_alias,
            )

        @activity.defn(name="record_verification")
        async def record_verification(
            request: RecordVerificationInput,
        ) -> RecordedVerification:
            script._log("record_verification", request.result.node_id)
            script.records.append(request.result)
            return RecordedVerification(
                row_id=len(script.records), criteria_drift=request.result.criteria_drift
            )

        @activity.defn(name="teardown_attempt")
        async def teardown_attempt(request: TeardownInput) -> UsageRecord:
            lease = request.lease
            script._log(f"teardown_attempt:{lease.persona}", lease.node_id)
            script.teardowns.append(request)
            return UsageRecord(
                epic_id=lease.epic_id,
                node_id=lease.node_id,
                attempt=lease.attempt,
                persona=lease.persona,
                spec_ref=lease.spec_ref,
                key_alias=lease.key_alias,
                prompt_tokens=1200,
                completion_tokens=180,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=1,
                spend_usd=0.004,
                final_usage_confirmed=True,
                termination=request.termination,
                issued_at=lease.issued_at,
                torn_down_at="2026-08-05T09:32:00Z",
            )

        @activity.defn(name="salvage_worktree")
        async def salvage_worktree(request: SalvageWorktreeInput) -> str:
            script._log("salvage_worktree", request.node_id)
            script.salvages.append(request)
            return f"{len(script.salvages):040x}"

        @activity.defn(name="remove_worktree")
        async def remove_worktree(request: RemoveWorktreeInput) -> None:
            script._log("remove_worktree", request.node_id)
            script.removals.append(request)

        @activity.defn(name="send_escalation")
        async def send_escalation(request: SendEscalationInput) -> SentEscalation:
            script._log("send_escalation", request.node_id)
            script.escalation_requests.append(request)

            escalation_id = f"{len(script.escalation_requests):012x}"
            script.escalation_ids.append(escalation_id)

            if script._delivered and script._press is not None:
                # The bridge's timing: the press lands while the send activity
                # is still open, so the signal precedes the activity's
                # completion in history.
                handle = script._client.get_workflow_handle(request.workflow_id)
                await handle.signal(SIGNAL_NAME, args=[escalation_id, script._press])

            return SentEscalation(
                escalation_id=escalation_id,
                delivered=script._delivered,
                expires_at="2026-08-05T10:30:00Z",
            )

        @activity.defn(name="expire_escalation")
        async def expire_escalation(
            request: ExpireEscalationInput,
        ) -> ExpiredEscalation:
            script._log("expire_escalation")
            script.expirations.append(request.escalation_id)
            return ExpiredEscalation(final_state=script._expiry_state)

        return [
            resolve_graph,
            load_prompt_sources,
            snapshot_criteria,
            prepare_worktree,
            issue_attempt_key,
            run_agent_attempt,
            poll_usage,
            run_gates,
            check_output,
            run_judge,
            record_verification,
            teardown_attempt,
            salvage_worktree,
            remove_worktree,
            send_escalation,
            expire_escalation,
        ]


def _node_of_spec_ref(spec_ref: str) -> WorkNode:
    """The node a `<feature>:<story key>` reference names."""
    story_key = spec_ref.rsplit(":", 1)[-1]
    return make_node(story_key.lower(), story_key)


def _node_of_worktree(path: str) -> str:
    """`.../<epic>/<node>` → `<node>` — the worktree names whose work this is."""
    return PurePosixPath(path).name


# --- harness ------------------------------------------------------------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — an hour of silence costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@asynccontextmanager
async def start_epic(
    env: WorkflowEnvironment,
    script: ScriptedWorld,
    *,
    graph: WorkGraph | None = None,
    **input_overrides: Any,
) -> AsyncIterator[Any]:
    """Start one epic and hold the worker open while the test steers it.

    The worker outlives the block on purpose: a signal test has to observe the
    epic *between* two of its decisions, and every assertion about what an
    activity saw has to be made before shutdown cancels whatever is still
    running.
    """
    request: dict[str, Any] = {
        "graph": graph if graph is not None else make_graph(),
        "proxy_url": PROXY_URL,
    }
    request.update(input_overrides)

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow],
        activities=script.activities(),
    ):
        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(**request),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        script.handle = handle
        yield handle


async def run_epic(
    env: WorkflowEnvironment,
    script: ScriptedWorld,
    **overrides: Any,
) -> Any:
    """Run one epic to its terminal state and hand back the final `EpicStatus`."""
    async with start_epic(env, script, **overrides) as handle:
        return await handle.result()


async def wait_for_status(
    handle: Any,
    predicate: Callable[[Any], bool],
    *,
    what: str,
    timeout: float = WAIT_TIMEOUT_S,
) -> Any:
    """Poll `epic_status` until it says what the test is waiting for.

    Real seconds, not the workflow's: time skipping only advances while a client
    awaits the workflow's *result*, so a query loop watches an epic that is
    running at its own pace — which is what makes an assertion about a paused
    scheduler mean something.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        status = await handle.query(EpicWorkflow.epic_status)
        if predicate(status):
            return status
        if loop.time() >= deadline:
            raise AssertionError(
                f"timed out after {timeout}s waiting for {what}; last status: {status}"
            )
        await asyncio.sleep(0.05)


async def wait_for(
    predicate: Callable[[], bool], *, what: str, timeout: float = WAIT_TIMEOUT_S
) -> None:
    """The same wait, over the scripted world instead of over the query."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError(f"timed out after {timeout}s waiting for {what}")
        await asyncio.sleep(0.05)


def states(status: Any) -> dict[str, NodeState]:
    return {node_id: node.state for node_id, node in status.nodes.items()}


def attempt_counts(status: Any) -> dict[str, int]:
    return {node_id: node.attempt for node_id, node in status.nodes.items()}


# --- US1-S1: a graph runs to completion (SC-001) ------------------------------


async def test_a_three_node_graph_runs_to_epic_completion(
    env: WorkflowEnvironment,
) -> None:
    """Every node passes, in declaration order, one attempt each.

    Declaration order is scheduling order (R10): `us2` is not ready until `us1`
    passes, and `us3` — ready from the start — still waits its turn, because the
    scheduler picks the *first* ready node rather than any ready node.
    """
    script = ScriptedWorld(all_passing(), client=env.client)

    status = await run_epic(env, script)

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.PASSED,
        "us2": NodeState.PASSED,
        "us3": NodeState.PASSED,
    }
    assert attempt_counts(status) == {"us1": 1, "us2": 1, "us3": 1}
    assert list(status.nodes) == ["us1", "us2", "us3"]
    assert status.nodes["us2"].branch == branch_name(EPIC_ID, "us2")

    assert script.dispatched == ["us1", "us2", "us3"]
    assert "overrun" not in script.calls
    assert "unscripted" not in script.calls

    # The registry and the epic's authored text are each read once, at the start
    # — the same snapshot discipline 002 applies to criteria.
    assert script.calls[:2] == ["resolve_graph", "load_prompt_sources"]
    assert len(script.prompt_source_requests) == 1
    assert script.prompt_source_requests[0].specs_root == SPECS_ROOT
    assert script.prompt_source_requests[0].feature == FEATURE
    assert script.prompt_source_requests[0].target_repo == TARGET_REPO


async def test_a_dependent_node_waits_for_its_dependencys_pass(
    env: WorkflowEnvironment,
) -> None:
    """FR-003 asserted from inside the running attempt, not after the fact.

    While `us1`'s agent is running, `us2` and `us3` must still be PENDING; while
    `us2`'s is, `us1` must already be PASSED. A terminal snapshot cannot tell an
    edge that unlocked on a PASS from one that unlocked on a hope.
    """
    script = ScriptedWorld(all_passing(), client=env.client)

    await run_epic(env, script)

    during_us1 = states(script.observed["us1"])
    assert during_us1["us1"] == NodeState.RUNNING
    assert during_us1["us2"] == NodeState.PENDING
    assert during_us1["us3"] == NodeState.PENDING

    during_us2 = states(script.observed["us2"])
    assert during_us2["us1"] == NodeState.PASSED
    assert during_us2["us2"] == NodeState.RUNNING
    assert during_us2["us3"] == NodeState.PENDING

    during_us3 = states(script.observed["us3"])
    assert during_us3 == {
        "us1": NodeState.PASSED,
        "us2": NodeState.PASSED,
        "us3": NodeState.RUNNING,
    }
    assert script.observed["us3"].epic_state == EpicState.RUNNING


async def test_one_nodes_lifecycle_composes_the_verification_contract(
    env: WorkflowEnvironment,
) -> None:
    """The node lifecycle of contracts/workflow.md, in order, once per node.

    Criteria and the worktree are snapshotted once per node (002 FR-010,
    FR-013); the attempt is opened by a key and closed by a teardown carrying the
    adapter's termination (FR-004); the verdict is recorded before the worktree
    is salvaged and swept (constitution VI).
    """
    script = ScriptedWorld(all_passing(), client=env.client)

    await run_epic(env, script)

    assert script.sequence("us1") == [
        "snapshot_criteria",
        "prepare_worktree",
        "issue_attempt_key:implementer",
        "run_agent_attempt",
        "run_gates",
        "check_output",
        "record_verification",
        "teardown_attempt:implementer",
        "salvage_worktree",
        "remove_worktree",
    ]

    # The judge is never consulted: these criteria carry no scenarios, and a
    # verdict nobody can score is not worth a completion (002 invariant 2).
    assert script.judge_requests == []

    [criteria_request] = [
        request
        for request in script.criteria_requests
        if request.spec_ref.endswith("US1")
    ]
    assert criteria_request.specs_root == SPECS_ROOT
    assert criteria_request.feature == FEATURE
    assert criteria_request.requirement_keys == ["US1", "FR-001"]

    [prepare] = [r for r in script.prepare_requests if r.node_id == "us1"]
    assert prepare.target_repo == TARGET_REPO
    assert prepare.standards == STANDARDS_PATH

    # The gates and the output check read the worktree the attempt ran in — not
    # the target clone, and not a sibling's tree.
    worktree = f"{WORKTREE_ROOT}/{EPIC_ID}/us1"
    assert [r.worktree_path for r in script.gate_requests].count(worktree) == 1
    [output] = [r for r in script.output_requests if r.worktree_path == worktree]
    assert output.write_scope == WriteScope.WORKTREE.value
    assert output.expected_artifacts == []

    [record] = [r for r in script.records if r.node_id == "us1"]
    assert record.verdict == OverallVerdict.PASS
    assert record.attempt == 1
    assert record.spec_ref == f"{FEATURE}:US1"
    assert [g.output_tail for g in record.gate_results] == [gate_pass().output_tail]


async def test_the_attempt_context_is_assembled_from_the_snapshot(
    env: WorkflowEnvironment,
) -> None:
    """What the one agent-touching activity is handed, field by field (FR-005).

    The virtual key is the attempt's own lease and the only credential in the
    payload (constitution V); the model alias and the deadline come from the
    registry snapshot, never from code (constitution VII, FR-010); the session id
    is fresh per attempt, because it is what makes the transcript discoverable.
    """
    script = ScriptedWorld(all_passing(), client=env.client)

    await run_epic(env, script)

    [context] = [c for c in script.attempts if c.node_id == "us1"]
    assert context.epic_id == EPIC_ID
    assert context.attempt == 1
    assert context.proxy_url == PROXY_URL
    assert context.virtual_key == "sk-us1-1-implementer"
    assert context.model_alias == MODEL_ALIAS
    assert context.timeout_s == TIMEOUT_S
    assert context.worktree_path == f"{WORKTREE_ROOT}/{EPIC_ID}/us1"
    assert uuid.UUID(context.session_id).version == 4

    assert len({c.session_id for c in script.attempts}) == len(script.attempts)

    # The key is minted for the node's persona and constrained to the aliases
    # that persona names — an attempt that could call anything is attribution
    # without constraint.
    [key_request] = [r for r in script.key_requests if r.node_id == "us1"]
    assert key_request.persona == "implementer"
    assert key_request.models == [MODEL_ALIAS, FALLBACK_ALIAS]
    assert key_request.spec_ref == f"{FEATURE}:US1"

    # The prompt is the assembler's, over the sources the activity read: the
    # node's own story and slice, the whole plan, and the standards directive.
    assert "### User Story 1 - Borrow a book (Priority: P1)" in context.prompt
    assert "T003 [US1] Implement library/loans.py until T002 passes" in context.prompt
    assert STANDARDS_PATH in context.prompt
    assert "T005 [US2]" not in context.prompt


# --- US1-S2: a failure retries with the evidence (FR-006, SC-004) -------------


async def test_a_failed_attempt_retries_with_its_evidence_verbatim(
    env: WorkflowEnvironment,
) -> None:
    """The ladder's RETRY re-dispatches the same node, same worktree, fresh key.

    The failing gate's output reaches the next attempt as an exact substring —
    an agent handed a paraphrase is an agent debugging the paraphraser.
    """
    script = ScriptedWorld(
        {"us1": [failing(1), passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )

    status = await run_epic(env, script)

    assert status.epic_state == EpicState.COMPLETED
    assert states(status)["us1"] == NodeState.PASSED
    assert attempt_counts(status) == {"us1": 2, "us2": 1, "us3": 1}

    first, second = script.prompts_for("us1")
    assert GATE_TAIL[1] not in first
    assert GATE_TAIL[1] in second

    contexts = [c for c in script.attempts if c.node_id == "us1"]
    assert [c.attempt for c in contexts] == [1, 2]
    assert contexts[0].worktree_path == contexts[1].worktree_path
    assert contexts[0].virtual_key != contexts[1].virtual_key

    # One worktree and one criteria snapshot for the node, two of everything the
    # attempt owns (FR-013, 002 FR-010).
    assert script.sequence("us1").count("prepare_worktree") == 1
    assert script.sequence("us1").count("snapshot_criteria") == 1
    assert script.sequence("us1").count("issue_attempt_key:implementer") == 2
    assert [r.attempt for r in script.records if r.node_id == "us1"] == [1, 2]
    assert [r.verdict for r in script.records if r.node_id == "us1"] == [
        OverallVerdict.FAIL,
        OverallVerdict.PASS,
    ]

    # And exactly one salvage/remove pair, at the end — a retry does not sweep
    # the worktree the next attempt is about to open.
    assert script.sequence("us1")[-2:] == ["salvage_worktree", "remove_worktree"]
    assert len([s for s in script.salvages if s.node_id == "us1"]) == 1


# --- US1-S3: exhaustion, escalation, and a kill (SC-002, SC-004) --------------


def exhausted(press: str, client: Any) -> ScriptedWorld:
    """`us1` fails three attempts and a debugger cycle, then a human presses."""
    return ScriptedWorld(
        {
            "us1": [failing(n) for n in (1, 2, 3, 4)],
            "us2": [passing()],
            "us3": [passing()],
        },
        client=client,
        press=press,
    )


async def test_the_ladder_exhausts_into_an_escalation_the_operator_kills(
    env: WorkflowEnvironment,
) -> None:
    """Three attempts, one debugger cycle, then a human — and then the node dies.

    The debugger is a rung rather than a fourth attempt: it runs on the same
    worktree under its own persona, and its key is minted for that persona so the
    cycle's spend is attributed to the debugger and not to the node's implementer
    (constitution V).
    """
    script = exhausted("KILL", env.client)

    status = await run_epic(env, script)

    assert states(status)["us1"] == NodeState.KILLED
    assert attempt_counts(status)["us1"] == 4

    personas = [r.persona for r in script.key_requests if r.node_id == "us1"]
    assert personas == ["implementer", "implementer", "implementer", DEBUGGER_PERSONA]
    assert [c.attempt for c in script.attempts if c.node_id == "us1"] == [1, 2, 3, 4]

    # Each attempt after the first carries the failure before it, the debugger's
    # included — a debugger dispatched without the evidence starts from scratch.
    prompts = script.prompts_for("us1")
    for prompt, attempt in zip(prompts[1:], (1, 2, 3)):
        assert GATE_TAIL[attempt] in prompt

    [escalation] = script.escalation_requests
    assert escalation.epic_id == EPIC_ID
    assert escalation.node_id == "us1"
    assert escalation.workflow_id == WORKFLOW_ID
    for attempt in (1, 2, 3, 4):
        assert GATE_TAIL[attempt] in escalation.history_summary
    assert {str(choice) for choice in escalation.choices} == {
        "RETRY",
        "KILL",
        "PAUSE_EPIC",
    }
    assert script.expirations == []
    assert "overrun" not in script.calls


async def test_a_killed_nodes_dependents_never_dispatch(
    env: WorkflowEnvironment,
) -> None:
    """SC-002 on the failure path: the edge stays locked, the leaf still runs.

    `us2` depends on a node that died, so it is marked KILLED without ever being
    dispatched — no worktree, no key, no attempt. `us3` depends on nothing and is
    unaffected, which is the difference between a locked edge and a stopped epic.
    """
    script = exhausted("KILL", env.client)

    status = await run_epic(env, script)

    assert states(status) == {
        "us1": NodeState.KILLED,
        "us2": NodeState.KILLED,
        "us3": NodeState.PASSED,
    }
    assert attempt_counts(status)["us2"] == 0
    assert status.epic_state == EpicState.COMPLETED

    assert script.dispatched == ["us1", "us1", "us1", "us1", "us3"]
    assert script.sequence("us2") == []
    assert [r.node_id for r in script.prepare_requests] == ["us1", "us3"]
    assert [r.node_id for r in script.key_requests] == ["us1"] * 4 + ["us3"]
    assert not [r for r in script.records if r.node_id == "us2"]

    # The leaf saw the kill and dispatched anyway; nothing about it waited.
    during_us3 = states(script.observed["us3"])
    assert during_us3["us1"] == NodeState.KILLED
    assert during_us3["us2"] == NodeState.KILLED


async def test_salvage_precedes_removal_on_every_terminal_path(
    env: WorkflowEnvironment,
) -> None:
    """Constitution VI: no work is lost, and the ref proves the attempt happened.

    Every node that ran ends with a salvage commit and then a sweep, carrying the
    attempt number and the termination the adapter classified — the branch is all
    that survives `.factory/` being cleaned, so it has to be enough (SC-004). A
    node that never dispatched has nothing to salvage and no worktree to remove.
    """
    script = exhausted("KILL", env.client)

    await run_epic(env, script)

    for node_id in ("us1", "us3"):
        sequence = script.sequence(node_id)
        assert sequence.index("salvage_worktree") < sequence.index("remove_worktree")
        assert sequence[-2:] == ["salvage_worktree", "remove_worktree"]

    assert [s.node_id for s in script.salvages] == ["us1", "us3"]
    assert [s.attempt for s in script.salvages] == [4, 1]
    assert [s.termination for s in script.salvages] == [Termination.COMPLETED] * 2
    assert [(r.node_id, r.target_repo) for r in script.removals] == [
        ("us1", TARGET_REPO),
        ("us3", TARGET_REPO),
    ]


async def test_the_adapters_termination_never_shortcuts_verification(
    env: WorkflowEnvironment,
) -> None:
    """FR-012 from the other side: a TIMEOUT attempt is still verified.

    The worktree may hold work worth keeping, and no agent-side signal — an exit
    code included — is allowed to decide a node. The termination travels to
    teardown and to the salvage subject, and nowhere else.
    """
    timed_out = Attempt(gates=[gate_pass()], termination=Termination.TIMEOUT)
    script = ScriptedWorld(
        {"us1": [timed_out], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )

    status = await run_epic(env, script)

    assert states(status)["us1"] == NodeState.PASSED
    assert "run_gates" in script.sequence("us1")
    assert script.teardown_for("us1", 1).termination == Termination.TIMEOUT
    assert [s.termination for s in script.salvages if s.node_id == "us1"] == [
        Termination.TIMEOUT
    ]


# --- FR-002: an invalid graph never dispatches --------------------------------


async def test_an_invalid_graph_is_rejected_before_anything_dispatches(
    env: WorkflowEnvironment,
) -> None:
    """A cycle fails the epic at its first step, naming the cycle's members.

    Nothing follows: no worktree, no key, no attempt. The failure is the
    workflow's, not a node's — an epic that cannot be scheduled has no node to
    charge it to.
    """
    cyclic = make_graph(
        nodes=[
            make_node("us1", "US1", depends_on=["us2"]),
            make_node("us2", "US2", depends_on=["us1"]),
        ]
    )
    script = ScriptedWorld({}, client=env.client)

    with pytest.raises(WorkflowFailureError) as failure:
        await run_epic(env, script, graph=cyclic)

    message = str(failure.value.__cause__)
    assert "us1" in message and "us2" in message

    assert script.calls == ["resolve_graph"]
    assert script.prepare_requests == []
    assert script.key_requests == []
    assert script.attempts == []


async def test_an_unknown_persona_is_rejected_before_anything_dispatches(
    env: WorkflowEnvironment,
) -> None:
    """The registry snapshot is the authority, and it is read before dispatch.

    A node routed to a persona the worker's registry has never heard of is
    undispatchable, and the epic says which node rather than which file.
    """
    script = ScriptedWorld({}, client=env.client)
    graph = make_graph(nodes=[make_node("us1", "US1", persona="archaeologist")])

    with pytest.raises(WorkflowFailureError) as failure:
        await run_epic(env, script, graph=graph)

    message = str(failure.value.__cause__)
    assert "us1" in message and "archaeologist" in message
    assert script.calls == ["resolve_graph"]


# --- FR-004 / SC-003: the bracket, and recording before acting ----------------


async def test_every_attempt_is_bracketed_by_a_key_and_recorded_before_acting(
    env: WorkflowEnvironment,
) -> None:
    """One key and one teardown per attempt, and the row before any consequence.

    Asserted from the call log rather than from counts afterwards: "the row
    exists and the escalation was sent" is true of an ordering that loses every
    row to a crash mid-escalation, which is precisely the ordering this forbids
    (002 flow invariant 3, SC-003).
    """
    script = exhausted("KILL", env.client)

    await run_epic(env, script)

    for node_id in ("us1", "us3"):
        segments: list[list[str]] = []
        for node, name in script.node_calls:
            if node != node_id or name == "poll_usage":
                continue
            if name.startswith("issue_attempt_key") or not segments:
                segments.append([])
            segments[-1].append(name)

        # Everything before the first key is per-node setup, never an attempt.
        assert segments[0] == ["snapshot_criteria", "prepare_worktree"]
        for segment in segments[1:]:
            assert segment[0].startswith("issue_attempt_key")
            assert "record_verification" in segment
            assert any(name.startswith("teardown_attempt") for name in segment)
            recorded = segment.index("record_verification")
            assert not _ACTIONS.intersection(segment[:recorded])
            assert segment.index("record_verification") < next(
                i for i, n in enumerate(segment) if n.startswith("teardown_attempt")
            )

    # Every attempt, and only the attempts: one key, one teardown, one row each.
    assert len(script.key_requests) == len(script.teardowns) == len(script.records) == 5
    assert [(r.node_id, r.attempt) for r in script.records] == [
        ("us1", 1),
        ("us1", 2),
        ("us1", 3),
        ("us1", 4),
        ("us3", 1),
    ]
    assert [(t.lease.node_id, t.lease.attempt) for t in script.teardowns] == [
        ("us1", 1),
        ("us1", 2),
        ("us1", 3),
        ("us1", 4),
        ("us3", 1),
    ]
    # No key is issued twice for the same attempt: the alias is the ledger's
    # uniqueness key, and a duplicate would upsert one attempt's spend onto
    # another's row (001 R5).
    assert len({t.lease.key_alias for t in script.teardowns}) == len(script.teardowns)

    # The row is written against the criteria the node was dispatched with, so
    # drift is measured against the snapshot rather than against today's spec.
    assert all(r.criteria_sha256 == "0" * 64 for r in script.records)


async def test_the_teardown_carries_the_terminations_the_adapter_reported(
    env: WorkflowEnvironment,
) -> None:
    """The bracket closes on the adapter's word about the *process* (FR-004)."""
    script = ScriptedWorld(
        {
            "us1": [
                Attempt(gates=[gate_fail(1)], termination=Termination.AGENT_ERROR),
                passing(),
            ],
            "us2": [passing()],
            "us3": [passing()],
        },
        client=env.client,
    )

    await run_epic(env, script)

    assert script.teardown_for("us1", 1).termination == Termination.AGENT_ERROR
    assert script.teardown_for("us1", 2).termination == Termination.COMPLETED


# --- R3: the poll loop's snapshot reaches teardown ----------------------------


async def test_the_poll_loop_retains_the_last_snapshot_for_teardown(
    env: WorkflowEnvironment,
) -> None:
    """Usage is polled while the agent runs, and the latest read survives (R3).

    D-018 caps the adapter's output at a termination and a transcript path, so
    the snapshot cannot ride back through it. Teardown's fallback figure is
    whatever the last poll saw — an unreadable proxy at teardown must record the
    number that was true 30 seconds ago rather than none at all (constitution V).
    """
    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
        wait_for_poll=True,
    )

    await run_epic(env, script, poll_interval_s=1)

    assert script.polls, "the workflow never polled usage while the agent ran"

    for node_id, attempt, _ in script.polls:
        assert (node_id, attempt) in {
            (context.node_id, context.attempt) for context in script.attempts
        }

    node_polls = [poll for poll in script.polls if poll[0] == "us1"]
    assert node_polls
    assert script.teardown_for("us1", 1).last_snapshot == node_polls[-1][2]


# --- US1-S4: replay ------------------------------------------------------------


async def test_replay_dispatches_nothing_twice(env: WorkflowEnvironment) -> None:
    """SC-001's determinism claim, against the history the epic actually wrote.

    Replaying the recorded history against the workflow code re-runs every
    decision and no side effect: a scheduler that consulted a clock, a set's
    iteration order, or `uuid4()` outside `workflow.uuid4()` fails here, and the
    scripted world proves no activity ran a second time — no node re-dispatched,
    no key re-issued.
    """
    script = ScriptedWorld(
        {"us1": [failing(1), passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )

    await run_epic(env, script)
    history = await script.handle.fetch_history()

    before = list(script.calls)
    keys_before = [(r.node_id, r.attempt) for r in script.key_requests]

    await Replayer(workflows=[EpicWorkflow]).replay_workflow(history)

    assert script.calls == before
    assert [(r.node_id, r.attempt) for r in script.key_requests] == keys_before
    assert len(script.attempts) == 4


# --- US3-S2: pause stops the scheduler, not the attempt (FR-008) --------------


def paused_with(node_id: str, state: NodeState) -> Callable[[Any], bool]:
    """The epic parked, and the node that parked it in the state it parked in.

    Both halves, because they are not simultaneous: a workflow may raise the
    paused flag the instant the signal arrives, while the node it interrupted is
    still working through its ladder. Waiting on the conjunction is what makes
    "the in-flight node finished first" an assertion rather than a race.
    """

    def predicate(status: Any) -> bool:
        return (
            status.epic_state == EpicState.PAUSED
            and status.nodes[node_id].state == state
        )

    return predicate


async def test_pause_blocks_new_dispatch_while_the_in_flight_node_finishes(
    env: WorkflowEnvironment,
) -> None:
    """`pause_epic` suspends the scheduler; the running node keeps its whole ladder.

    The signal lands while `us1`'s agent is still running, and the clarified
    reading of "in-flight attempts run to completion" (R10) is the strong one:
    the node runs its gates, records its verdict, tears down its key and salvages
    its worktree — the key/worktree lifecycle stays atomic — and only *then* does
    the epic stop, with `us2` and `us3` untouched.
    """
    script = ScriptedWorld(
        all_passing(), client=env.client, signal_during={"us1": PAUSE_SIGNAL}
    )

    async with start_epic(env, script) as handle:
        paused = await wait_for_status(
            handle,
            paused_with("us1", NodeState.PASSED),
            what="the epic to park after us1's ladder finished",
        )

        # The whole ladder, not a suspended half of one: the node the signal
        # interrupted is verified, recorded, torn down and swept.
        assert script.sequence("us1") == [
            "snapshot_criteria",
            "prepare_worktree",
            "issue_attempt_key:implementer",
            "run_agent_attempt",
            "run_gates",
            "check_output",
            "record_verification",
            "teardown_attempt:implementer",
            "salvage_worktree",
            "remove_worktree",
        ]
        assert states(paused) == {
            "us1": NodeState.PASSED,
            "us2": NodeState.PENDING,
            "us3": NodeState.PENDING,
        }

        # A quiet window: an epic that treated pause as advisory would have
        # dispatched `us2` — ready the moment `us1` passed — inside it.
        await asyncio.sleep(SETTLE_S)
        still = await handle.query(EpicWorkflow.epic_status)
        assert still.epic_state == EpicState.PAUSED
        assert states(still)["us2"] == NodeState.PENDING
        assert script.dispatched == ["us1"]

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.PASSED,
        "us2": NodeState.PASSED,
        "us3": NodeState.PASSED,
    }
    assert script.dispatched == ["us1", "us2", "us3"]
    assert "overrun" not in script.calls


async def test_a_paused_epic_survives_replay(env: WorkflowEnvironment) -> None:
    """R1: pause is durable because a signal is history, and history replays.

    No persistence code exists to test, which is the decision — so what is tested
    is the mechanism it rests on. Replaying the recorded history rebuilds the
    paused flag from the same signal event, and a workflow that rebuilt it
    differently would try to dispatch `us2` during the window the recorded run
    spent parked, which is a nondeterminism error here rather than a silent
    divergence in production.
    """
    script = ScriptedWorld(
        all_passing(), client=env.client, signal_during={"us1": PAUSE_SIGNAL}
    )

    async with start_epic(env, script) as handle:
        await wait_for_status(
            handle,
            paused_with("us1", NodeState.PASSED),
            what="the epic to park after us1's ladder finished",
        )
        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()
        history = await handle.fetch_history()

    before = list(script.calls)

    await Replayer(workflows=[EpicWorkflow]).replay_workflow(history)

    assert status.epic_state == EpicState.COMPLETED
    assert script.calls == before
    assert script.dispatched == ["us1", "us2", "us3"]


async def test_a_pause_epic_resolution_parks_the_node_and_pauses_the_epic(
    env: WorkflowEnvironment,
) -> None:
    """The third button (contracts/workflow.md § Node lifecycle).

    `PAUSE_EPIC` is neither a grant nor a kill: the ladder ends the node, because
    parking is the most a per-node decision can say about an epic-level
    suspension, and the interpreter supplies the rest of the meaning — the node
    is FAILED rather than KILLED (parked, its branch salvaged and its worktree
    swept like any terminal path) and the scheduler stops, so the operator can
    look at what happened before `us3` spends anything.
    """
    script = exhausted(EscalationChoice.PAUSE_EPIC.value, env.client)

    async with start_epic(env, script) as handle:
        paused = await wait_for_status(
            handle,
            paused_with("us1", NodeState.FAILED),
            what="us1 to park FAILED and the epic to pause",
        )

        assert states(paused) == {
            # Parked, not killed: the operator stopped the epic rather than
            # abandoning the node.
            "us1": NodeState.FAILED,
            # A dependent of a node that will never pass — killed where it
            # stands, without a worktree, a key or an attempt (SC-002).
            "us2": NodeState.KILLED,
            # Independent, and not dispatched: the pause outranks its readiness.
            "us3": NodeState.PENDING,
        }
        assert attempt_counts(paused) == {"us1": 4, "us2": 0, "us3": 0}

        [escalation] = script.escalation_requests
        assert escalation.node_id == "us1"
        assert script.expirations == []

        # Constitution VI holds on the park path too: the work is on the branch
        # before the tree is swept, and it says which attempt left it there.
        assert script.sequence("us1")[-2:] == ["salvage_worktree", "remove_worktree"]
        assert [(s.node_id, s.attempt) for s in script.salvages] == [("us1", 4)]

        await asyncio.sleep(SETTLE_S)
        assert script.dispatched == ["us1"] * 4

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.FAILED,
        "us2": NodeState.KILLED,
        "us3": NodeState.PASSED,
    }
    assert script.dispatched == ["us1"] * 4 + ["us3"]


# --- US3-S3: kill interrupts the attempt and ends the epic --------------------


async def test_kill_cancels_the_attempt_salvages_and_kills_every_node(
    env: WorkflowEnvironment,
) -> None:
    """The one signal that interrupts an attempt (contracts/workflow.md § Signals).

    `kill_epic` arrives while `us1`'s agent is running and cancels it: the
    adapter's KILLED path (R2), which archives the transcript and re-raises
    rather than reporting a termination the workflow could mistake for an
    ending. What follows is the ordering constitution VI insists on — teardown
    closes the bracket carrying KILLED, the worktree is salvaged and only then
    swept — and every node that never ran is recorded KILLED, so the final status
    accounts for the whole graph (US3-S3).

    No gates run and no verdict is recorded for the interrupted attempt: the
    operator asked for the epic to stop, and a two-hour gate suite against a
    worktree nobody will read is the opposite of stopping. The bracket still
    closes, which is what FR-004 requires of every attempt that was opened.
    """
    script = ScriptedWorld(
        all_passing(),
        client=env.client,
        signal_during={"us1": KILL_SIGNAL},
        await_cancel=True,
    )

    async with start_epic(env, script) as handle:
        status = await handle.result()
        await wait_for(
            lambda: bool(script.cancellations),
            what="the adapter's attempt to be cancelled",
        )

        assert script.cancellations == ["us1"]
        assert "never_cancelled" not in script.calls

    assert status.epic_state == EpicState.KILLED
    assert states(status) == {
        "us1": NodeState.KILLED,
        "us2": NodeState.KILLED,
        "us3": NodeState.KILLED,
    }
    # Every node recorded, in declaration order — a kill leaves no node
    # unaccounted for, dispatched or not.
    assert list(status.nodes) == ["us1", "us2", "us3"]
    assert attempt_counts(status) == {"us1": 1, "us2": 0, "us3": 0}

    assert script.dispatched == ["us1"]
    assert script.sequence("us2") == []
    assert script.sequence("us3") == []

    sequence = script.sequence("us1")
    assert sequence[:4] == [
        "snapshot_criteria",
        "prepare_worktree",
        "issue_attempt_key:implementer",
        "run_agent_attempt",
    ]
    assert sequence[-2:] == ["salvage_worktree", "remove_worktree"]
    assert "teardown_attempt:implementer" in sequence
    assert "run_gates" not in sequence
    assert "check_output" not in sequence
    assert "record_verification" not in sequence
    assert script.records == []

    # The key the attempt opened is torn down on the adapter's classification of
    # a kill, and the salvage commit carries the same word (SC-004).
    assert script.teardown_for("us1", 1).termination == Termination.KILLED
    assert [(s.node_id, s.attempt, s.termination) for s in script.salvages] == [
        ("us1", 1, Termination.KILLED)
    ]
    assert [(r.node_id, r.target_repo) for r in script.removals] == [
        ("us1", TARGET_REPO)
    ]
