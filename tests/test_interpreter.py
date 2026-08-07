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

- **The judge is consulted exactly when it can still change the outcome**
  (FR-003, 002's flow invariant 2). The criteria a world hands back are scored
  (`scenarios=True`) or not, and both shapes are real dispatches: a node owing
  only `FR-###` bullets is verified on its gates and its output check alone,
  while a node owing a user story is scored against its scenarios — on a diff
  read by an activity, by a judge inside its own component-1 key lifecycle, with
  its feedback quoted into the next attempt. The default is unscored, because
  most of what this file asserts is about scheduling and the ladder; the judge
  path has its own section at the end.

Three properties of the setup are deliberate:

- **The default scripted criteria carry FR bullets and no acceptance
  scenarios**, so `judge_required` is false and the judge is never consulted for
  every test above the judge section. That is a designed-for shape —
  `has_scenarios` exists precisely to say a node owing only `FR-###` bullets is
  verified on its gates and its output check alone — and it keeps those tests on
  the interpreter rather than on 002, whose own composition is proven under time
  skipping in `tests/test_verification_flow.py`.

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

import ast
import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
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
    ReadWorktreeDiffInput,
    RemoveWorktreeInput,
    ResolvePersonaInput,
    SalvageWorktreeInput,
)
from factory.activities.merge_activities import (
    DisableAutoMergeInput,
    EnqueueLandingInput,
    OpenLandingPrInput,
    PollLandingInput,
    PrepareLandingPrInput,
    SyncLandingBranchInput,
    SyncLandingBranchResult,
    ValidateTargetRepoInput,
)
from factory.activities.notify_activities import (
    ExpiredEscalation,
    ExpireEscalationInput,
    SendEscalationInput,
    SentEscalation,
)
from factory.activities.usage_activities import (
    KEY_ISSUANCE_FAILED,
    IssueKeyInput,
    TeardownInput,
    key_alias_for,
)
from factory.activities.verify_activities import (
    JUDGE_UNAVAILABLE,
    CheckOutputInput,
    RecordedVerification,
    RecordVerificationInput,
    RunGatesInput,
    RunJudgeInput,
    SnapshotCriteriaInput,
)
from factory.config import Persona, WriteScope
from factory.mergequeue.models import (
    Finding,
    Landing,
    LandingConfig,
    LandingState,
    ObservedOutcome,
    PrSnapshot,
    QueueOutcome,
    TargetRepoProfile,
)
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
    Scenario,
    VerificationConfig,
    VerificationResult,
)
from factory.verify.store import EXPIRED
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    EpicState,
    NodeRecord,
    NodeState,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph import workflow as workflow_module
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

#: The judge's own registry entry, resolved for the epic rather than for a node —
#: no node names the `judge` persona, and its spend is attributed to itself
#: (constitution V). Distinct aliases so a judge dispatched under the node's
#: model cannot pass an assertion here.
JUDGE_PERSONA = "judge"
JUDGE_ALIAS = "judge-alias"
JUDGE_FALLBACK_ALIAS = "judge-fallback"
JUDGE_TIMEOUT_S = 3600

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
    JUDGE_PERSONA: Persona(
        name=JUDGE_PERSONA,
        agent="claude-code",
        model=JUDGE_ALIAS,
        fallback=JUDGE_FALLBACK_ALIAS,
        skills=(),
        # The judge reads a diff it is handed; it writes nothing and needs no
        # worktree of its own (the shipped registry's shape).
        write_scope=WriteScope.READ,
        needs_worktree=False,
        timeout_s=JUDGE_TIMEOUT_S,
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


def criteria_for(node: WorkNode, *, scenarios: bool = False) -> CriteriaSet:
    """What `snapshot_criteria` answers with, in either of its two real shapes.

    Unscored (the default) is the node's FR bullet alone: a node owing only
    `FR-###` bullets has nothing the judge could score (`has_scenarios`), so it
    is verified on its gates and its output check, and `judge_required` is false
    for the whole of its life. Scored adds the story the node implements, with
    the one acceptance scenario the judge must echo back by id — which is the
    shape that opens the judge branch (002's flow invariant 2).
    """
    key = FR_FOR[node.story_key]
    requirements = [
        Requirement(
            key=key,
            kind=RequirementKind.FUNCTIONAL,
            title=None,
            priority=None,
            body=f"The catalogue MUST satisfy {key}.",
            scenarios=[],
        )
    ]
    if scenarios:
        requirements.insert(0, story_requirement(node.story_key))

    return CriteriaSet(
        feature=FEATURE,
        spec_ref=node.spec_ref,
        requirements=requirements,
        source_path=f"{SPECS_ROOT}/{FEATURE}/spec.md",
        source_sha256="0" * 64,
        snapshotted_at="2026-08-05T09:00:00Z",
    )


def scenario_id(story_key: str) -> str:
    """The id the judge must echo character-for-character (002's judge contract)."""
    return f"{story_key}-S1"


def story_requirement(story_key: str) -> Requirement:
    return Requirement(
        key=story_key,
        kind=RequirementKind.STORY,
        title="Borrow a book",
        priority="P1",
        body=f"The member-facing behavior {story_key} describes.",
        scenarios=[
            Scenario(
                scenario_id=scenario_id(story_key),
                steps=[
                    "**Given** an available book",
                    "**When** a member borrows it",
                    "**Then** the catalogue records the loan against that member",
                ],
                raw_text=f"1. **Given** ... ({scenario_id(story_key)})",
            )
        ],
    )


#: What `read_worktree_diff` answers with — the attempt's work, as the only
#: activity allowed to read a worktree's patch reports it. Distinctive because
#: the judge is asserted to have been handed *this* text: a workflow that read
#: the diff itself, or passed the wrong worktree's, cannot produce it.
DIFF_TEXT = (
    "--- a/library/loans.py\n"
    "+++ b/library/loans.py\n"
    "@@\n"
    "+def borrow(member, book):\n"
    "+    return Loan(member=member, book=book)\n"
)

#: The judge's objection, quoted verbatim into the next attempt's prompt
#: (FR-006, 002 SC-004) — an agent handed a paraphrase debugs the paraphraser.
JUDGE_FEEDBACK = (
    "Scenario US1-S1 is unmet: borrow() builds a Loan but nothing records it "
    "against the member, so the catalogue has no loan to show."
)

#: What the judge says when its response could not be read at all: a RETRY with
#: no findings, which is the one verdict worth re-asking within an attempt (R4).
UNREADABLE_FEEDBACK = "the judge's response was not valid JSON"


def judge_pass(model_alias: str = JUDGE_ALIAS, story_key: str = "US1") -> JudgeVerdict:
    return JudgeVerdict(
        outcome=JudgeOutcome.PASS,
        findings=[
            JudgeScenarioFinding(
                scenario=scenario_id(story_key),
                passed=True,
                reasoning="the loan is recorded against the borrowing member",
            )
        ],
        feedback="",
        judge_attempt=1,
        truncated_input=False,
        model_alias=model_alias,
    )


def judge_retry(
    feedback: str = JUDGE_FEEDBACK,
    *,
    findings: bool = True,
    story_key: str = "US1",
) -> JudgeVerdict:
    """A rewrite request — with findings it is an answer, without one it is noise.

    `findings=False` is what `run_judge` returns for a response the strict parser
    refused: the same outcome, but nothing was actually scored, so it is worth
    asking again inside the same attempt rather than spending one.
    """
    return JudgeVerdict(
        outcome=JudgeOutcome.RETRY,
        findings=(
            [
                JudgeScenarioFinding(
                    scenario=scenario_id(story_key),
                    passed=False,
                    reasoning="no write to the loans table appears in the diff",
                )
            ]
            if findings
            else []
        ),
        feedback=feedback,
        judge_attempt=1,
        truncated_input=False,
        model_alias=JUDGE_ALIAS,
    )


def judge_unavailable() -> JudgeVerdict:
    """Scripted as a verdict, delivered as an outage.

    `run_judge` never *returns* UNAVAILABLE — it raises `JUDGE_UNAVAILABLE` once
    its own HTTP retries are spent, and composing a gates-only PASS out of that
    is the caller's decision (002's activity contract). Scripting it as a verdict
    keeps `Attempt` one vocabulary; the fake turns it back into the raise.
    """
    return JudgeVerdict(
        outcome=JudgeOutcome.UNAVAILABLE,
        findings=[],
        feedback="",
        judge_attempt=1,
        truncated_input=False,
        model_alias=JUDGE_ALIAS,
    )


@dataclass(frozen=True)
class Attempt:
    """What the world does to one attempt of one node.

    `termination` is the adapter's classification and travels to teardown and to
    the salvage commit; the gates decide the verdict independently of it, which
    is FR-012 in the shape of a fixture.

    `judge` is what `run_judge` answers, one entry per call *within* this attempt
    — more than one only when the first response was unreadable and the flow
    asks again (R4). It is empty for the unscored criteria the default world
    hands back, where the judge is never reached at all.
    """

    gates: list[GateResult] = field(default_factory=lambda: [gate_pass()])
    output: OutputCheck = field(default_factory=wrote_something)
    termination: Termination = Termination.COMPLETED
    judge: tuple[JudgeVerdict, ...] = ()


def passing() -> Attempt:
    return Attempt()


def failing(attempt: int) -> Attempt:
    """A gate failure — the whole verdict, with no judge in the picture."""
    return Attempt(gates=[gate_fail(attempt)])


def scored(*judge: JudgeVerdict, gates: list[GateResult] | None = None) -> Attempt:
    """An attempt whose criteria carry scenarios, and what the judge says about it."""
    return Attempt(gates=gates if gates is not None else [gate_pass()], judge=judge)


def all_passing() -> dict[str, list[Attempt]]:
    return {"us1": [passing()], "us2": [passing()], "us3": [passing()]}


# --- the landing phase's scripted payloads ------------------------------------


@dataclass(frozen=True)
class OpenLandingPrBody:
    """What `prepare_landing_pr` hands back — the body file and title."""

    body_file: str
    title: str


@dataclass(frozen=True)
class OpenLandingPr:
    """What `open_landing_pr` hands back — the PR's identity."""

    number: int
    url: str


@dataclass(frozen=True)
class EnqueueOutcome:
    """What `enqueue_landing` hands back — accepted, or refused as data."""

    rejected: bool
    reason: str


@dataclass(frozen=True)
class DisableOutcome:
    """What `disable_auto_merge` hands back — best-effort."""

    failed: bool
    reason: str


def _node_of_pr(pr_number: int) -> str:
    """Invert the scripted PR-number scheme: which node a PR belongs to.

    The reverse of `ScriptedWorld._pr_number_for` — the fake's call log names the
    node behind a `pr merge`/`pr view` the way the workflow's own record does.
    """
    for node_id in ("us1", "us2", "us3"):
        if ScriptedWorld._pr_number_for(node_id) == pr_number:
            return node_id
    return f"pr-{pr_number}"


def _snapshot(
    *,
    state: str = "OPEN",
    auto_merge: bool = True,
    merged_at: str | None = None,
    failing_checks: tuple[str, ...] = (),
    merge_state_status: str = "CLEAN",
    observed_at: str = "2026-08-06T10:10:00Z",
) -> PrSnapshot:
    """One `PrSnapshot` the scripted poll answers with."""
    return PrSnapshot(
        state=state,
        is_draft=False,
        auto_merge_requested=auto_merge,
        merge_state_status=merge_state_status,
        merged_at=merged_at,
        closed_at=None,
        failing_required_checks=failing_checks,
        observed_at=observed_at,
    )


def pending_snapshot() -> PrSnapshot:
    """The queue is still holding the PR — a poll that answers "keep polling"."""
    return _snapshot()


def merged_snapshot() -> PrSnapshot:
    """The queue landed the PR — the reconciled success (FR-004)."""
    return _snapshot(state="MERGED", auto_merge=False, merged_at="2026-08-06T10:09:00Z")


def dequeued_snapshot() -> PrSnapshot:
    """A human took the PR out of the queue without merging it."""
    return _snapshot(state="CLOSED", auto_merge=False)


def checks_failed_snapshot() -> PrSnapshot:
    """The queue rejected the PR because required checks failed (recovery-eligible)."""
    return _snapshot(auto_merge=False, failing_checks=("lint",))


def conflict_snapshot() -> PrSnapshot:
    """The queue cannot merge the PR — its branch is dirty (recovery-eligible)."""
    return _snapshot(auto_merge=False, merge_state_status="DIRTY")


def stalled_snapshot() -> PrSnapshot:
    """The queue has held the PR past the stall window."""
    return _snapshot(auto_merge=True, observed_at="2026-08-06T12:00:00Z")


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
        signal_during: dict[str, str] | None = None,
        await_cancel: bool = False,
        scenarios: bool = False,
        adapter_snapshot: UsageSnapshot | None = None,
        heartbeat_then_block: bool = False,
        agent_sleep_s: float = 0.0,
    ) -> None:
        self._script = script
        self._client = client
        self._delivered = delivered
        self._press = press
        self._expiry_state = expiry_state
        #: Whether `snapshot_criteria` hands back criteria the judge can score.
        #: False is not "the judge is disabled" — it is a node owing only
        #: `FR-###` bullets, for which `judge_required` is false by 002's own
        #: rule and the interpreter must consult nobody.
        self._scenarios = scenarios
        #: `{node_id: signal name}` — sent from inside that node's attempt, so
        #: the operator's hand lands on the wheel while the node is genuinely in
        #: flight. Any other timing tests a different thing.
        self._signal_during = signal_during or {}
        self._await_cancel = await_cancel
        #: The snapshot the fake adapter carries on its heartbeat and returns on
        #: the `AdapterResult` (US1: observation rides the agent activity, D-018).
        #: `None` models "never measured", which teardown records as NULL.
        self.adapter_snapshot = adapter_snapshot
        #: Whether the fake agent heartbeats its snapshot once and then blocks —
        #: the worker-death shape that makes Temporal fire a heartbeat timeout
        #: whose `last_heartbeat_details` the workflow reads (US1 delivery 2).
        self.heartbeat_then_block = heartbeat_then_block
        #: How long the fake agent sleeps before returning, in real seconds.
        #: Under time-skipping the activity runs real-time, so the history-cost
        #: test keeps this tiny: it measures the workflow's event count, not wall
        #: time, and a long real sleep would only slow the suite without changing
        #: the count.
        self._agent_sleep_s = agent_sleep_s

        #: Activity names in call order, and the same log with the node each call
        #: belonged to — "what happened to us1" is a list rather than an offset
        #: someone has to count out by hand.
        self.calls: list[str] = []
        self.node_calls: list[tuple[str, str]] = []

        self.graphs: list[WorkGraph] = []
        self.persona_requests: list[ResolvePersonaInput] = []
        self.prompt_source_requests: list[LoadPromptSourcesInput] = []
        self.criteria_requests: list[SnapshotCriteriaInput] = []
        self.prepare_requests: list[PrepareWorktreeInput] = []
        self.key_requests: list[IssueKeyInput] = []
        self.attempts: list[AttemptContext] = []
        self.polls: list[tuple[str, int, UsageSnapshot]] = []
        self.teardowns: list[TeardownInput] = []
        self.gate_requests: list[RunGatesInput] = []
        self.output_requests: list[CheckOutputInput] = []
        self.diff_requests: list[ReadWorktreeDiffInput] = []
        self.judge_requests: list[RunJudgeInput] = []
        self.records: list[VerificationResult] = []
        self.salvages: list[SalvageWorktreeInput] = []
        self.removals: list[RemoveWorktreeInput] = []
        self.escalation_requests: list[SendEscalationInput] = []
        self.escalation_ids: list[str] = []
        self.expirations: list[str] = []

        #: The landing phase's scripted surface. `landing_snapshots` is the per-PR
        #: answer queue, in poll order: each `poll_landing` call consumes one
        #: `PrSnapshot` and records the observed outcome (the workflow's
        #: reconciliation, FR-004). A node with no scripted snapshot gets a canned
        #: pending one so a poll that overruns reads as `overrun` rather than as
        #: an unscripted hang.
        self.landing_snapshots: dict[int, list[PrSnapshot]] = {}
        self.body_prepare_requests: list[PrepareLandingPrInput] = []
        self.landing_requests: list[OpenLandingPrInput] = []
        self.enqueue_requests: list[EnqueueLandingInput] = []
        self.poll_requests: list[PollLandingInput] = []
        self.disable_requests: list[DisableAutoMergeInput] = []

        #: US2 recovery: per-node scripted `sync_landing_branch` answers, and the
        #: calls logged. A node with no scripted sync answers a clean sync with a
        #: canned head, so a recovery test that only cares about the ladder
        #: reaches re-enqueue without scripting git.
        self.landing_syncs: dict[str, SyncLandingBranchResult] = {}
        self.sync_requests: list[SyncLandingBranchInput] = []

        #: US3 onboarding: the profile the scripted `validate_target_repo` returns,
        #: and the calls logged. Defaults to a fully conforming repo so the rest of
        #: the suite runs unchanged; onboarding tests override it with a failing
        #: profile to prove dispatch is blocked (FR-010, SC-005).
        self.onboard_profile = TargetRepoProfile(
            repo=TARGET_REPO,
            default_branch="main",
            visibility="PUBLIC",
            queue_enabled=True,
            required_checks=("test",),
            declared_gates=("test",),
            findings=(
                Finding("visibility", True, "repo is public"),
                Finding("merge_queue", True, "merge queue enabled on main"),
                Finding("factory_yaml", True, "factory.yaml is valid"),
                Finding("gate_check:test", True, "required check 'test' exists"),
            ),
            passed=True,
        )
        self.onboard_requests: list[ValidateTargetRepoInput] = []

        #: PR number assigned per node by `open_landing_pr`, so `enqueue_landing`
        #: and `poll_landing` know which node a PR belongs to (the workflow's PR
        #: number, reconstructed for the call log's sake).
        self._pr_numbers: dict[str, int] = {}
        #: Whether the next `enqueue_landing` is refused (spec edge case). One-shot.
        self._enqueue_refused = False
        #: Every snapshot a poll consumed, in order — the reconciliation record.
        self._observed_outcomes: list[PrSnapshot] = []

        #: What `epic_status` said while each node's attempt was in flight — the
        #: only place a mid-epic view of the graph can be taken.
        self.observed: dict[str, Any] = {}

        #: The set of nodes whose state was RUNNING at the moment each agent
        #: attempt started, in dispatch order. The concurrency claim — "N nodes
        #: in flight at once" — is asserted from these snapshots, taken while the
        #: workflow is genuinely parked on the attempt activities (US1, SC-001).
        self.running_sets: list[set[str]] = []

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

        #: Aliases with a live key behind them, issue-to-teardown. The fake
        #: enforces what the real proxy enforces — a duplicate alias will not
        #: mint while the first key lives — because the judge's key is minted
        #: inside the implementer's still-open bracket: an alias that did not
        #: carry the persona would collide right here, exactly as it would in
        #: production (001 R1).
        self._live_aliases: set[str] = set()

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

    @staticmethod
    def _pr_number_for(node_id: str) -> int:
        """A stable PR number per node, so scripted polls can key on it."""
        return int(
            hashlib.sha1(node_id.encode()).hexdigest()[:8], 16
        ) % 1000 + 1

    def _snapshot_for(self, pr_number: int) -> PrSnapshot:
        """The next scripted poll answer for a PR, or the happy-path default.

        A `poll_landing` whose PR was not scripted answers MERGED — the default a
        green node's landing takes, so scheduling tests that only care about the
        ladder reach a terminal without per-node landing scripting. Landing tests
        that need a specific queue shape script it with `script_landing`; an
        overrun past the scripted answers reads as `overrun_poll` (recorded) and
        returns the default.
        """
        queue = self.landing_snapshots.get(pr_number)
        if not queue:
            return merged_snapshot()
        return queue.pop(0)

    def script_landing(
        self,
        node_id: str,
        *snapshots: PrSnapshot,
        pr_number: int | None = None,
    ) -> int:
        """Script one node's landing poll answers; return the PR number.

        Call before starting the epic. Each snapshot is consumed in poll order,
        so a `(pending, merged)` pair scripts FR-004's event gap — the queue says
        nothing, then lands.
        """
        number = pr_number if pr_number is not None else self._pr_number_for(node_id)
        self.landing_snapshots[number] = list(snapshots)
        return number

    def script_sync(
        self,
        node_id: str,
        *,
        clean: bool = True,
        base_ref: str = "c0ffee",
        conflicted_files: tuple[str, ...] = (),
        refused: bool = False,
        reason: str = "",
    ) -> None:
        """Script one node's recovery sync answer (US2, FR-005).

        The default clean answer carries a canned head so a recovery test that
        only cares about the ladder re-enters without scripting git; a conflict
        or refusal scripts the shape that routes to the debugger or to
        escalation.
        """
        self.landing_syncs[node_id] = SyncLandingBranchResult(
            clean=clean,
            base_ref=base_ref,
            conflicted_files=conflicted_files,
            refused=refused,
            reason=reason,
        )

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

        @activity.defn(name="resolve_persona")
        async def resolve_persona(request: ResolvePersonaInput) -> ResolvedPersona:
            script._log("resolve_persona")
            script.persona_requests.append(request)
            persona = PERSONAS.get(request.persona)
            if persona is None or persona.model is None:
                raise ApplicationError(
                    f"persona '{request.persona}' is not in the registry",
                    type=GRAPH_INVALID,
                    non_retryable=True,
                )
            return ResolvedPersona(
                persona=request.persona,
                model_alias=persona.model,
                models=[a for a in (persona.model, persona.fallback) if a],
            )

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
            return criteria_for(node, scenarios=script._scenarios)

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
            alias = key_alias_for(
                request.epic_id, request.node_id, request.attempt, request.persona
            )
            if alias in script._live_aliases:
                # LiteLLM's answer to a duplicate alias, surfaced the way the
                # real activity surfaces it — and non-retryable here, because a
                # workflow that minted a colliding alias has a wiring bug no
                # retry budget can spend its way out of.
                raise ApplicationError(
                    f"key_alias '{alias}' already names a live key",
                    type=KEY_ISSUANCE_FAILED,
                    non_retryable=True,
                )
            script._live_aliases.add(alias)
            return KeyLease(
                key=f"sk-{request.node_id}-{request.attempt}-{request.persona}",
                key_alias=alias,
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
            status = await handle.query(EpicWorkflow.epic_status)
            script.observed[context.node_id] = status
            script.running_sets.append(
                {
                    node_id
                    for node_id, node in status.nodes.items()
                    if node.state == NodeState.RUNNING
                }
            )

            steer = script._signal_during.get(context.node_id)
            if steer is not None:
                # The signal lands in history *before* this activity completes,
                # which is the only timing under which "the in-flight attempt"
                # names anything at all (US3-S2, US3-S3).
                await handle.signal(steer)

            if script.heartbeat_then_block:
                # The worker-death shape (US1 delivery 2): the adapter beats its
                # newest snapshot once and then stops — nothing beats again, so
                # Temporal fires a heartbeat timeout whose `last_heartbeat_details`
                # the workflow reads. The block is real, so the test pays one
                # heartbeat timeout (5s) and no more.
                activity.heartbeat(script.adapter_snapshot)
                await asyncio.Event().wait()

            if script._await_cancel and steer is not None:
                # The adapter's kill path (R2): it waits, heartbeating, and on
                # cancellation archives the transcript and re-raises. Bounded, so
                # a workflow that never cancels fails an assertion rather than
                # hanging the suite — and the overrun is recorded, because
                # "the attempt ran to completion" is exactly the bug.
                for _ in range(int(WAIT_TIMEOUT_S / 0.05)):
                    activity.heartbeat(script.adapter_snapshot)
                    try:
                        await asyncio.sleep(0.05)
                    except asyncio.CancelledError:
                        script.cancellations.append(context.node_id)
                        raise
                script.calls.append("never_cancelled")

            if script._agent_sleep_s:
                # A real-time wait standing in for a longer attempt. History cost
                # is what the test measures, so the sleep itself is tiny even when
                # it represents hours: the workflow's event count is what must not
                # grow, and a long real sleep would only slow the suite.
                await asyncio.sleep(script._agent_sleep_s)

            result_kwargs: dict[str, Any] = {
                "termination": script._current.termination,
                "transcript_path": (
                    f"/srv/factory/.factory/transcripts/{context.epic_id}/"
                    f"{context.node_id}/attempt-{context.attempt}"
                ),
            }
            if "last_snapshot" in AdapterResult.__dataclass_fields__:
                result_kwargs["last_snapshot"] = script.adapter_snapshot
            return AdapterResult(**result_kwargs)

        @activity.defn(name="poll_usage")
        async def poll_usage(lease: KeyLease) -> UsageSnapshot:
            script._log("poll_usage", lease.node_id)
            script._spend = round(script._spend + 0.011, 6)
            snapshot = UsageSnapshot(
                spend_usd=script._spend, captured_at="2026-08-05T09:31:00Z"
            )
            script.polls.append((lease.node_id, lease.attempt, snapshot))
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

        @activity.defn(name="read_worktree_diff")
        async def read_worktree_diff(request: ReadWorktreeDiffInput) -> str:
            script._log("read_worktree_diff", _node_of_worktree(request.worktree_path))
            script.diff_requests.append(request)
            return DIFF_TEXT

        @activity.defn(name="run_judge")
        async def run_judge(request: RunJudgeInput) -> JudgeVerdict:
            script._log("run_judge")
            script.judge_requests.append(request)

            verdicts = script._current.judge
            if not verdicts:
                # A judge consulted for an attempt that scripted no verdict is an
                # assertion failure in the tests, not a hang in the harness — so
                # it is recorded and answered rather than raised.
                script.calls.append("unscripted_judge")
                return judge_pass(request.model_alias)

            verdict = verdicts[min(request.judge_attempt, len(verdicts)) - 1]
            if verdict.outcome == JudgeOutcome.UNAVAILABLE:
                # The activity's real shape: an outage raises once its own HTTP
                # retries are spent, and it stays retryable, so the workflow's
                # budget is spent before any fallback is composed.
                raise ApplicationError(
                    "judge backend unavailable after 3 attempts",
                    type=JUDGE_UNAVAILABLE,
                )
            return verdict

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
            # Revoking the key frees its alias; `discard` because a teardown
            # Temporal re-runs finds it already gone, which is a normal outcome.
            script._live_aliases.discard(lease.key_alias)
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

        @activity.defn(name="prepare_landing_pr")
        async def prepare_landing_pr(request: PrepareLandingPrInput) -> Any:
            script._log("prepare_landing_pr", request.node_id)
            script.body_prepare_requests.append(request)
            return OpenLandingPrBody(
                body_file=f"/srv/factory/.factory/landing/{request.epic_id}/{request.node_id}/attempt-{request.attempt}.md",
                title=f"{request.epic_id}/{request.node_id}: {request.story_title}",
            )

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr(request: OpenLandingPrInput) -> Any:
            script._log("open_landing_pr", request.node_id)
            script.landing_requests.append(request)
            pr_number = script._pr_number_for(request.node_id)
            script._pr_numbers[request.node_id] = pr_number
            return OpenLandingPr(number=pr_number, url=f"https://x/pull/{pr_number}")

        @activity.defn(name="enqueue_landing")
        async def enqueue_landing(request: EnqueueLandingInput) -> Any:
            script._log("enqueue_landing", _node_of_pr(request.pr_number))
            script.enqueue_requests.append(request)
            if script._enqueue_refused:
                script._enqueue_refused = False
                return EnqueueOutcome(rejected=True, reason="queue disabled")
            return EnqueueOutcome(rejected=False, reason="")

        @activity.defn(name="poll_landing")
        async def poll_landing(request: PollLandingInput) -> PrSnapshot:
            script._log("poll_landing", _node_of_pr(request.pr_number))
            script.poll_requests.append(request)
            pending = script._snapshot_for(request.pr_number)
            script._observed_outcomes.append(pending)
            return pending

        @activity.defn(name="disable_auto_merge")
        async def disable_auto_merge(request: DisableAutoMergeInput) -> Any:
            script._log("disable_auto_merge", _node_of_pr(request.pr_number))
            script.disable_requests.append(request)
            return DisableOutcome(failed=False, reason="")

        @activity.defn(name="sync_landing_branch")
        async def sync_landing_branch(
            request: SyncLandingBranchInput,
        ) -> SyncLandingBranchResult:
            script._log("sync_landing_branch", request.node_id)
            script.sync_requests.append(request)
            return script.landing_syncs.get(
                request.node_id,
                SyncLandingBranchResult(
                    clean=True,
                    base_ref="c0ffee",
                    conflicted_files=(),
                    refused=False,
                    reason="",
                ),
            )

        @activity.defn(name="validate_target_repo")
        async def validate_target_repo(request: ValidateTargetRepoInput) -> TargetRepoProfile:
            script._log("validate_target_repo")
            script.onboard_requests.append(request)
            return script.onboard_profile

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
            resolve_persona,
            load_prompt_sources,
            snapshot_criteria,
            prepare_worktree,
            issue_attempt_key,
            run_agent_attempt,
            poll_usage,
            run_gates,
            check_output,
            read_worktree_diff,
            run_judge,
            record_verification,
            teardown_attempt,
            salvage_worktree,
            remove_worktree,
            prepare_landing_pr,
            open_landing_pr,
            enqueue_landing,
            poll_landing,
            disable_auto_merge,
            sync_landing_branch,
            validate_target_repo,
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
    workflow_id: str = WORKFLOW_ID,
    **input_overrides: Any,
) -> AsyncIterator[Any]:
    """Start one epic and hold the worker open while the test steers it.

    The worker outlives the block on purpose: a signal test has to observe the
    epic *between* two of its decisions, and every assertion about what an
    activity saw has to be made before shutdown cancels whatever is still
    running.

    `workflow_id` lets a test run two epics in one environment (the history-cost
    comparison) without colliding on the shared default; the fake agent still
    queries the fixed `WORKFLOW_ID` to observe the one in flight, so only a test
    that runs a *second* workflow in the same env passes a distinct id.
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
            id=workflow_id,
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
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
        "us3": NodeState.MERGED,
    }
    assert attempt_counts(status) == {"us1": 1, "us2": 1, "us3": 1}
    assert list(status.nodes) == ["us1", "us2", "us3"]
    assert status.nodes["us2"].branch == branch_name(EPIC_ID, "us2")

    assert script.dispatched == ["us1", "us2", "us3"]
    assert "overrun" not in script.calls
    assert "unscripted" not in script.calls

    # The registry and the epic's authored text are each read once, at the start
    # — the same snapshot discipline 002 applies to criteria. The judge's own
    # entry is resolved there too: no node names it, and discovering four
    # attempts in that the epic cannot score anything is the failure resolving
    # the whole graph first exists to prevent. Onboarding (US3) runs ahead of all
    # of it — the repo is validated before anything dispatches (FR-010, SC-005).
    assert script.calls[:4] == [
        "validate_target_repo",
        "resolve_graph",
        "resolve_persona",
        "load_prompt_sources",
    ]
    assert [request.persona for request in script.persona_requests] == [JUDGE_PERSONA]
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
    # `us1` verified — its landing opened — yet its own queue ride is still
    # pending: a verified-gated dependent dispatches while the dependency's
    # landing is ENQUEUED, not after it merges (FR-009, US1-S4).
    assert during_us2["us1"] == NodeState.ENQUEUED
    assert during_us2["us2"] == NodeState.RUNNING
    assert during_us2["us3"] == NodeState.PENDING

    during_us3 = states(script.observed["us3"])
    assert during_us3 == {
        "us1": NodeState.ENQUEUED,
        "us2": NodeState.ENQUEUED,
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
        "prepare_landing_pr",
        "open_landing_pr",
        "enqueue_landing",
        "poll_landing",
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
    assert states(status)["us1"] == NodeState.MERGED
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

    # Exactly one salvage, and the sweep deferred past the landing — a retry does
    # not sweep the worktree the next attempt is about to open, and the sweep
    # comes only after the landing is terminal.
    assert len([s for s in script.salvages if s.node_id == "us1"]) == 1
    assert script.sequence("us1").count("remove_worktree") == 1
    assert script.sequence("us1").index("salvage_worktree") < script.sequence("us1").index(
        "remove_worktree"
    )


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
        "us3": NodeState.MERGED,
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
        # Salvage comes first; the landing phase rides the queue; removal is
        # deferred to the landing's terminal, so the sweep is the last thing. A
        # node that never PASSes (us1 here) has no landing to interleave.
        assert sequence[-1] == "remove_worktree"
        if "open_landing_pr" in sequence:
            assert sequence.index("salvage_worktree") < sequence.index("open_landing_pr")
            assert sequence.index("open_landing_pr") < sequence.index("remove_worktree")

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

    assert states(status)["us1"] == NodeState.MERGED
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

    # Onboarding passes first (US3), then the graph is rejected at resolve_graph.
    assert script.calls == ["validate_target_repo", "resolve_graph"]
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
    # Onboarding passes first; the unknown persona is then rejected at resolve_graph.
    assert script.calls == ["validate_target_repo", "resolve_graph"]


async def test_a_failing_onboarding_profile_blocks_dispatch_before_resolve_graph(
    env: WorkflowEnvironment,
) -> None:
    """SC-005: a repo that fails onboarding never dispatches — before resolve_graph.

    `validate_target_repo` runs ahead of `resolve_graph` in `EpicWorkflow.run`.
    A failing profile fails the epic at its first step, with zero keys issued and
    zero worktrees prepared, and the failure message carries the findings so an
    operator sees exactly which check failed and how to fix it.
    """
    script = ScriptedWorld({}, client=env.client)
    script.onboard_profile = TargetRepoProfile(
        repo=TARGET_REPO,
        default_branch="main",
        visibility="private",
        queue_enabled=False,
        required_checks=(),
        declared_gates=(),
        findings=(
            Finding(
                "visibility", False,
                "repo is 'private'; the merge queue is available on any plan "
                "only for public repos",
            ),
            Finding(
                "merge_queue", False,
                "merge queue is not enabled on the default branch 'main'",
            ),
        ),
        passed=False,
    )

    with pytest.raises(WorkflowFailureError) as failure:
        await run_epic(env, script)

    message = str(failure.value.__cause__)
    # The failure carries the findings, so the operator is told what to change.
    assert "visibility" in message
    assert "merge_queue" in message
    # The onboarding gate ran; resolve_graph never did, and nothing dispatched.
    assert script.calls == ["validate_target_repo"]
    assert script.prepare_requests == []
    assert script.key_requests == []
    assert script.attempts == []


async def test_a_passing_onboarding_profile_proceeds_to_normal_dispatch(
    env: WorkflowEnvironment,
) -> None:
    """A passing profile is not a gate that stops dispatch — the epic runs."""
    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
        scenarios=True,
    )

    status = await run_epic(env, script)

    # Onboarding ran first, then normal dispatch reached completion.
    assert script.onboard_requests, "validate_target_repo never ran"
    assert script.calls[0] == "validate_target_repo"
    assert script.dispatched == ["us1", "us2", "us3"]
    assert status.epic_state == EpicState.COMPLETED


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
        # The signal lands while `us1` is mid-attempt; the epic parks only after
        # us1's ladder is complete, so the node reaches ENQUEUED (the landing
        # opens and enqueues before the scheduler parks). Polling keeps running
        # (passive) but its timer only advances when the workflow's clock does,
        # so the landing stays ENQUEUED while parked — the scheduler, and only
        # the scheduler, is what pause suspends.
        paused = await wait_for_status(
            handle,
            paused_with("us1", NodeState.ENQUEUED),
            what="the epic to park after us1's ladder opened and enqueued its landing",
        )

        # The whole ladder, not a suspended half of one: the node the signal
        # interrupted is verified, recorded, torn down, salvaged, then landed.
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
            "prepare_landing_pr",
            "open_landing_pr",
            "enqueue_landing",
        ]
        assert states(paused) == {
            "us1": NodeState.ENQUEUED,
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
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
        "us3": NodeState.MERGED,
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
            paused_with("us1", NodeState.ENQUEUED),
            what="the epic to park after us1's landing opened and enqueued",
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
        "us3": NodeState.MERGED,
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


# --- US1: the snapshot reaches teardown on all three delivery paths -----------
#
# US1 moves observation onto the agent activity's heartbeat (plan US1). Teardown
# keeps the same `last_snapshot` field and the same meaning — the fallback figure
# when the proxy is unreadable — but the figure now arrives three ways: on the
# returned `AdapterResult` (normal), read off a heartbeat-timeout's
# `last_heartbeat_details` (worker death), and read once at kill (the SDK gives
# the workflow no details on a cancellation it requested). A path that silently
# stops populating the field records NULL and loses a dollar figure no existing
# test would catch, so each is asserted independently (plan's "trap").

SNAPSHOT = UsageSnapshot(spend_usd=6.25, captured_at="2026-08-05T09:31:00Z")


async def test_a_normal_attempt_delivers_its_snapshot_to_teardown(
    env: WorkflowEnvironment,
) -> None:
    """Delivery 1: the attempt's last observation rides home on the returned
    `AdapterResult`, and the workflow hands it to teardown — zero extra events.

    The node verifies and the bracket closes with the measured figure, not NULL.
    """
    script = ScriptedWorld(
        all_passing(),
        client=env.client,
        adapter_snapshot=SNAPSHOT,
    )

    await run_epic(env, script)

    assert script.teardown_for("us1", 1).last_snapshot == SNAPSHOT


async def test_a_heartbeat_timeout_delivers_its_snapshot_to_teardown(
    env: WorkflowEnvironment,
) -> None:
    """Delivery 2: a worker death beats the snapshot once and stops; Temporal
    fires the heartbeat timeout carrying `last_heartbeat_details`, which the
    workflow reads and hands to teardown.

    The attempt's bracket still closes (FR-004) with the figure that was true a
    beat ago — not NULL — and the node still verifies (FR-012).
    """
    script = ScriptedWorld(
        all_passing(),
        client=env.client,
        adapter_snapshot=SNAPSHOT,
        heartbeat_then_block=True,
    )

    status = await run_epic(env, script)

    assert script.teardown_for("us1", 1).last_snapshot == SNAPSHOT
    assert script.teardown_for("us1", 1).termination == Termination.TIMEOUT
    assert "run_gates" in script.sequence("us1")
    # MERGED, not PASSED: on the landed tree a verified node rides the scripted
    # landing to its terminal state (003's semantics — PASSED now means
    # "verified, landing not terminal").
    assert states(status)["us1"] == NodeState.MERGED


async def test_a_kill_delivers_a_snapshot_to_teardown(
    env: WorkflowEnvironment,
) -> None:
    """Delivery 3: a kill cancels the attempt and tears down with a non-NULL
    figure — the SDK does not surface heartbeat details on a cancellation the
    workflow itself requested, so the bracket reads the proxy once before it
    closes rather than recording NULL.
    """
    script = ScriptedWorld(
        all_passing(),
        client=env.client,
        signal_during={"us1": KILL_SIGNAL},
        await_cancel=True,
        adapter_snapshot=SNAPSHOT,
    )

    async with start_epic(env, script) as handle:
        status = await handle.result()
        await wait_for(
            lambda: bool(script.cancellations),
            what="the adapter's attempt to be cancelled",
        )

    assert script.cancellations == ["us1"]
    assert status.epic_state == EpicState.KILLED
    assert script.teardown_for("us1", 1).termination == Termination.KILLED
    assert script.teardown_for("us1", 1).last_snapshot is not None


# --- US1: an attempt's history cost is O(1), not O(duration) ------------------
#
# The whole story's defect (spec.md, plan.md): the poll loop fired a
# `wait_condition` timer and a `poll_usage` activity every `poll_interval_s`,
# so a four-hour attempt grew its history without bound — ~5,300 events, one
# heartbeat timeout from Temporal's ceiling. US1 replaces that with a plain
# `await agent`: observation rides the agent heartbeat, and the workflow's
# history for an attempt is a fixed constant no matter how long the attempt
# runs. This test runs two otherwise-identical epics whose attempts differ only
# in their configured duration and asserts their history counts are within a
# small constant, and that neither the four-hour attempt's history carries a
# timer nor a `poll_usage` activity (FR-001, FR-002).


#: The numeric `HistoryEventType` members the history-cost test keys off.
_EVENT_TIMER_STARTED = 17
_EVENT_TIMER_FIRED = 18
_EVENT_ACTIVITY_SCHEDULED = 10

#: Poll interval the history-cost test runs both epics at. Small enough that the
#: poll loop fires several times over the longer sleep (so its per-interval
#: growth is observable) yet coarse enough that the loop completes under time
#: skipping; the exact value is a test constant, not a production default.
_HISTORY_POLL_INTERVAL_S = 1.0


def _history_event_count(history: Any) -> dict[int, int]:
    """`event_type -> count` for one run's whole history."""
    counts: dict[int, int] = {}
    for event in history.events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return counts


def _scheduled_activity_names(history: Any) -> list[str]:
    """The activity types scheduled across the run, in order."""
    names: list[str] = []
    for event in history.events:
        if event.event_type == _EVENT_ACTIVITY_SCHEDULED:
            names.append(event.activity_task_scheduled_event_attributes.activity_type.name)
    return names


async def _attempt_history(
    label: str, *, agent_sleep_s: float
) -> tuple[int, dict[int, int], list[str]]:
    """Run one one-node epic in its own environment and return
    (total events, event counts, activities).

    Duration is modelled by `agent_sleep_s`, the real seconds the fake adapter
    stands in for the attempt (spec.md: the agent runs in real time under time
    skipping, so the poll loop's growth is driven by how many poll intervals
    elapse while it runs). The poll interval is fixed small enough that the
    poll loop fires more than once over the longer sleep (so its growth is
    observable) yet coarse enough that the loop completes — a duration axis
    that must not change the event count.

    The workflow id is a module constant and the fake agent queries that fixed
    id, so a test may not run two epics in one environment. Each call therefore
    starts its own Temporal environment, making the id unique per run.
    """
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        script = ScriptedWorld(
            {"us1": [passing()]}, client=env.client, agent_sleep_s=agent_sleep_s
        )
        await run_epic(
            env,
            script,
            graph=make_graph([make_node("us1", "US1")]),
            poll_interval_s=_HISTORY_POLL_INTERVAL_S,
        )
        history = await script.handle.fetch_history()
        return (
            sum(_history_event_count(history).values()),
            _history_event_count(history),
            _scheduled_activity_names(history),
        )
    finally:
        await env.shutdown()


async def test_an_attempts_history_cost_does_not_grow_with_its_duration() -> None:
    """FR-001/FR-002: a four-hour attempt and a one-minute attempt contribute
    history event counts within a small constant.

    Under time-skipping the agent runs in real seconds, so "duration" is modelled
    by `agent_sleep_s`: the four-hour attempt is the longer real-time stand-in
    (many poll intervals elapse while it runs), the one-minute attempt the short
    one. That is the axis the poll loop grew history along — this is the story's
    whole defect (spec.md). Under the plain await neither attempt's history moves
    with its duration.

    Two epics, two runs — the workflow id is a module constant and the fake agent
    queries that fixed id, so a test may not run two epics in one environment.
    Each case runs in its own fresh environment (built inside `_attempt_history`),
    and the two compare their counts against the same constant.
    """
    hours_count, _, _ = await _attempt_history("hours", agent_sleep_s=4.0)
    minutes_count, _, _ = await _attempt_history("minutes", agent_sleep_s=1.0)

    assert abs(hours_count - minutes_count) <= 6, (
        f"history cost grew with duration: hours={hours_count}, "
        f"minutes={minutes_count}"
    )


async def test_an_attempts_history_has_no_timer_and_no_poll_activity() -> None:
    """FR-002: the attempt contributes no duration-driven timer and no
    `poll_usage` activity — the two things that made the old loop's cost grow.

    On the landed tree the landing phase legitimately fires a bounded number of
    poll timers *after* the attempt completes, so absolute timer absence is no
    longer the honest claim. What US1 forbids is timers that grow with the
    attempt's duration — so the four-hour and one-minute attempts must carry
    identical timer counts — and the poll activity itself, which must be gone
    outright.
    """
    _, hours_events, hours_activity = await _attempt_history(
        "hours", agent_sleep_s=4.0
    )
    _, minute_events, _ = await _attempt_history("minute", agent_sleep_s=1.0)

    assert hours_events.get(_EVENT_TIMER_STARTED, 0) == minute_events.get(
        _EVENT_TIMER_STARTED, 0
    ), "timer count grew with attempt duration"
    assert hours_events.get(_EVENT_TIMER_FIRED, 0) == minute_events.get(
        _EVENT_TIMER_FIRED, 0
    ), "timer count grew with attempt duration"
    assert "poll_usage" not in hours_activity, (
        "the four-hour attempt scheduled a poll_usage activity"
    )


# --- the judge path (002's flow invariant 2, wired) ---------------------------


def one_node() -> WorkGraph:
    """`us1` alone — the graph the judge tests need and no more of one.

    Scheduling is asserted at length above; what these tests are about is one
    node's verification, and a chain would run the same judge three times to say
    nothing new.
    """
    return make_graph([make_node("us1", "US1")])


def scored_world(*attempts: Attempt, client: Any, **overrides: Any) -> ScriptedWorld:
    """A world whose criteria carry the story's acceptance scenario."""
    return ScriptedWorld(
        {"us1": list(attempts)}, client=client, scenarios=True, **overrides
    )


def judge_keys(script: ScriptedWorld) -> list[IssueKeyInput]:
    return [request for request in script.key_requests if request.persona == JUDGE_PERSONA]


async def test_a_scored_node_runs_the_judge_inside_its_own_key_lifecycle(
    env: WorkflowEnvironment,
) -> None:
    """Green gates, real output, scenarios to score — so the judge is asked.

    The whole of 002's flow invariant 6 in one sequence: the judge's completion
    is bracketed by its own `issue_attempt_key` / `teardown_attempt`, the key is
    minted for the `judge` persona rather than for the node's implementer
    (constitution V), it is constrained to the aliases that persona names, and
    the judge authenticates with the key that lease returned. The diff it scores
    is read first, by an activity, and only once the cheaper checks are green
    (invariant 2) — a node whose lint gate failed must not cost a completion.
    """
    script = scored_world(scored(judge_pass()), client=env.client)

    status = await run_epic(env, script, graph=one_node())

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {"us1": NodeState.MERGED}
    assert attempt_counts(status) == {"us1": 1}

    assert script.sequence("us1") == [
        "snapshot_criteria",
        "prepare_worktree",
        "issue_attempt_key:implementer",
        "run_agent_attempt",
        "run_gates",
        "check_output",
        "read_worktree_diff",
        f"issue_attempt_key:{JUDGE_PERSONA}",
        "run_judge",
        f"teardown_attempt:{JUDGE_PERSONA}",
        "record_verification",
        "teardown_attempt:implementer",
        "salvage_worktree",
        "prepare_landing_pr",
        "open_landing_pr",
        "enqueue_landing",
        "poll_landing",
        "remove_worktree",
    ]
    assert "unscripted_judge" not in script.calls

    # The judge's key: its own persona, its own aliases, and the node's attempt
    # number, so the ledger reads "what the judge spent scoring us1 attempt 1".
    [key] = judge_keys(script)
    assert key.epic_id == EPIC_ID
    assert key.node_id == "us1"
    assert key.attempt == 1
    assert key.spec_ref == f"{FEATURE}:US1"
    assert key.models == [JUDGE_ALIAS, JUDGE_FALLBACK_ALIAS]

    [teardown] = [t for t in script.teardowns if t.lease.persona == JUDGE_PERSONA]
    assert teardown.lease.key == f"sk-us1-1-{JUDGE_PERSONA}"

    [request] = script.judge_requests
    assert request.virtual_key == teardown.lease.key
    assert request.model_alias == JUDGE_ALIAS
    assert request.proxy_url == PROXY_URL
    assert request.judge_attempt == 1
    assert request.prior_feedback is None
    assert request.max_judge_retries == VerificationConfig().max_judge_retries
    # The dispatch snapshot's scenarios, not a re-read of the spec (002 FR-010).
    assert [
        scenario.scenario_id
        for requirement in request.criteria.requirements
        for scenario in requirement.scenarios
    ] == [scenario_id("US1")]

    # The judge agreed, so the row says so — and says nothing about a judge that
    # was not there.
    [record] = script.records
    assert record.verdict == OverallVerdict.PASS
    assert record.judge is not None
    assert record.judge.outcome == JudgeOutcome.PASS
    assert record.judge_unavailable is False


async def test_the_judges_alias_never_collides_with_the_live_implementer_key(
    env: WorkflowEnvironment,
) -> None:
    """Persona is part of the key's identity (001 R1), proven where it bites.

    The implementer's bracket stays open through verification — teardown wants
    the attempt's termination, which verification has not finished deciding — so
    the judge's key is minted while the implementer's is live. The fake proxy
    refuses a duplicate live alias exactly as LiteLLM does, which makes the
    guarantee structural: a run that completes at all is a run whose aliases
    never collided. And because the ledger upserts on the alias, distinct
    aliases are also what keeps the judge's row from landing on top of the
    implementer's.
    """
    script = scored_world(
        scored(judge_retry(UNREADABLE_FEEDBACK, findings=False), judge_pass()),
        client=env.client,
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}

    # Judge first (its bracket closes inside verification), implementer second —
    # one row each, four dimensions each, nothing shadowed.
    assert [t.lease.key_alias for t in script.teardowns] == [
        f"{EPIC_ID}:us1:1:{JUDGE_PERSONA}",
        f"{EPIC_ID}:us1:1:implementer",
    ]


async def test_the_diff_the_judge_scores_is_read_by_an_activity(
    env: WorkflowEnvironment,
) -> None:
    """Where the worktree is read, and where it must not be (constitution IV).

    A workflow that ran git itself would be a workflow with a side effect and a
    non-deterministic replay, so the diff crosses the activity boundary like
    every other reading of the world: `read_worktree_diff` names the node's own
    worktree, and what it returned is what the judge was handed, byte for byte.
    Asserted structurally as well, because the behavioural half would still pass
    if a second, unscheduled path appeared beside it.
    """
    script = scored_world(scored(judge_pass()), client=env.client)

    await run_epic(env, script, graph=one_node())

    [request] = script.diff_requests
    assert request.worktree_path == f"{WORKTREE_ROOT}/{EPIC_ID}/us1"
    # The diff — and the output check before it — is read against the node's
    # branch point, never HEAD (D-027): the agent commits as it goes, so HEAD
    # moves WITH the work and a HEAD-relative diff shows the judge everything
    # except it. "9" * 40 is the base the scripted prepare_worktree returned.
    assert request.base_ref == "9" * 40
    assert {r.base_ref for r in script.output_requests} == {"9" * 40}

    [judged] = script.judge_requests
    assert judged.diff_text == DIFF_TEXT

    # `read_worktree_diff` is spelled in the workflow only as the activity being
    # scheduled — never called, and never wrapped in a helper the epic's history
    # would not record.
    tree = ast.parse(Path(workflow_module.__file__).read_text(encoding="utf-8"))
    scheduled, other = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or node.id != "read_worktree_diff":
            continue
        (scheduled if _is_scheduled_activity(tree, node) else other).append(node)
    assert scheduled, "the workflow never schedules read_worktree_diff"
    assert not other, (
        "factory/workgraph/workflow.py names read_worktree_diff outside an "
        "activity invocation; the worktree is read in activities alone (FR-001)"
    )


def _is_scheduled_activity(tree: ast.Module, name: ast.Name) -> bool:
    """Whether `name` is the first argument of a `workflow.execute_activity` call."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("execute_activity", "start_activity")
        and node.args
        and node.args[0] is name
        for node in ast.walk(tree)
    )


async def test_a_judge_retry_spends_an_attempt_and_quotes_its_feedback(
    env: WorkflowEnvironment,
) -> None:
    """The rewrite the judge asks for, and what the next attempt is told (SC-004).

    A judge RETRY composes to FAIL — RETRY says what the ladder should do next,
    not that the attempt was acceptable — so the node is re-dispatched with the
    objection quoted verbatim, and the judge itself is handed its own last words
    as `prior_feedback` so the second scoring answers the first (R4).
    """
    script = scored_world(
        scored(judge_retry()),
        scored(judge_pass()),
        client=env.client,
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert attempt_counts(status) == {"us1": 2}

    # Two agent attempts, each with its own judge key and its own bracket: the
    # rewrite is a new attempt, not a second opinion on the old one.
    assert [c.attempt for c in script.attempts] == [1, 2]
    assert [key.attempt for key in judge_keys(script)] == [1, 2]
    assert script.sequence("us1").count("run_judge") == 2

    first, second = script.records
    assert (first.verdict, first.judge.outcome) == (
        OverallVerdict.FAIL,
        JudgeOutcome.RETRY,
    )
    assert (second.verdict, second.judge.outcome) == (
        OverallVerdict.PASS,
        JudgeOutcome.PASS,
    )

    # Verbatim into the prompt, and verbatim back to the judge.
    prompts = script.prompts_for("us1")
    assert JUDGE_FEEDBACK not in prompts[0]
    assert JUDGE_FEEDBACK in prompts[1]
    assert [request.prior_feedback for request in script.judge_requests] == [
        None,
        JUDGE_FEEDBACK,
    ]


async def test_the_judges_rewrites_are_bounded_inside_the_attempt_budget(
    env: WorkflowEnvironment,
) -> None:
    """The judge's outcome reaches the ladder, not just the row (002 SC-003).

    `max_judge_retries` bounds judge-driven retries *inside* `max_attempts`
    rather than on top of it, so with the attempt budget deliberately raised the
    only thing that can end the retries is the rewrite cap — and the node drops
    to a debugger cycle with three attempts still unspent. A workflow that
    recorded the judge's verdict but left `judge_outcome` off the ladder's
    history would keep retrying here and never call the debugger.
    """
    script = scored_world(
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_pass()),
        client=env.client,
    )

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        config=VerificationConfig(max_attempts=6, max_judge_retries=1),
    )

    assert states(status) == {"us1": NodeState.MERGED}
    assert attempt_counts(status) == {"us1": 3}
    assert [key.persona for key in script.key_requests if key.persona != JUDGE_PERSONA] == [
        "implementer",
        "implementer",
        DEBUGGER_PERSONA,
    ]
    # The cap the judge is bounded by is the one an operator set, carried into
    # every scoring rather than assumed.
    assert [request.max_judge_retries for request in script.judge_requests] == [1, 1, 1]


async def test_an_unreadable_judge_response_is_re_asked_inside_the_attempt(
    env: WorkflowEnvironment,
) -> None:
    """A response nobody could parse is not an objection (002's judge contract).

    `run_judge` reports one as a RETRY with no findings, and asking again is the
    only way to tell a broken model turn from a real disagreement — so it is
    re-asked inside the same attempt, on the same key, carrying the parse failure
    as its own prior feedback. The node's attempt budget is untouched.
    """
    script = scored_world(
        scored(judge_retry(UNREADABLE_FEEDBACK, findings=False), judge_pass()),
        client=env.client,
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert attempt_counts(status) == {"us1": 1}
    assert script.dispatched == ["us1"]

    # Two scorings on one key, one teardown: the re-ask is a retry of the same
    # scoring job, not a second attribution unit — a key per re-ask would
    # re-mint an alias whose first key is still live, and split one job's spend
    # across ledger rows. No completion is anonymous either way (constitution V).
    assert [request.judge_attempt for request in script.judge_requests] == [1, 2]
    assert [key.attempt for key in judge_keys(script)] == [1]
    assert len([t for t in script.teardowns if t.lease.persona == JUDGE_PERSONA]) == 1
    assert script.judge_requests[0].virtual_key == script.judge_requests[1].virtual_key
    assert script.judge_requests[1].prior_feedback == UNREADABLE_FEEDBACK

    # One agent attempt, one row, and the verdict of the judge that answered.
    [record] = script.records
    assert record.verdict == OverallVerdict.PASS
    assert record.judge.outcome == JudgeOutcome.PASS


async def test_an_unavailable_judge_passes_a_green_node_and_records_that_it_did(
    env: WorkflowEnvironment,
) -> None:
    """The one asymmetry in the verdict table (002 data-model.md).

    A judge that stayed down does not block a PASS — the deterministic evidence
    is green and an outage is not a finding — but the row carries
    `judge_unavailable`, which is the one column that says this PASS was reached
    without judge agreement. The fallback is composed only after the workflow's
    own retry budget is spent, and the key the judge never used is still torn
    down.
    """
    script = scored_world(scored(judge_unavailable()), client=env.client)

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert attempt_counts(status) == {"us1": 1}

    # Retried as an outage, not accepted as a verdict, before anything is
    # composed from its absence.
    assert script.sequence("us1").count("run_judge") == 3
    assert [key.attempt for key in judge_keys(script)] == [1]
    assert len([t for t in script.teardowns if t.lease.persona == JUDGE_PERSONA]) == 1

    [record] = script.records
    assert record.verdict == OverallVerdict.PASS
    assert record.judge_unavailable is True
    assert record.judge is not None
    assert record.judge.outcome == JudgeOutcome.UNAVAILABLE
    assert record.judge.model_alias == JUDGE_ALIAS


async def test_a_failed_gate_costs_no_diff_and_no_judge_completion(
    env: WorkflowEnvironment,
) -> None:
    """Cheapest-first, with the judge available and the criteria scorable.

    The guard is `judge_required`'s, and it is asserted here in the shape it
    actually matters: scenarios present, judge resolved, and still nobody asked —
    because the gates already decided a FAIL no judge verdict could lift (FR-003).
    The diff is not read either: reading a worktree nobody will score is work for
    an answer already known.
    """
    script = scored_world(
        *(scored(judge_pass(), gates=[gate_fail(n)]) for n in (1, 2, 3, 4)),
        client=env.client,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.KILLED}
    assert script.judge_requests == []
    assert script.diff_requests == []
    assert judge_keys(script) == []
    assert [record.judge for record in script.records] == [None] * 4
    assert [record.judge_unavailable for record in script.records] == [False] * 4


# --- US2: queue rejection recovery (FR-005, 006, 007, 008) --------------------


async def test_checks_failed_syncs_reenqueues_and_increments_recovery(
    env: WorkflowEnvironment,
) -> None:
    """US2-S1: CHECKS_FAILED re-enters the inner loop and re-enqueues on pass.

    A verified node whose landing the queue rejects for failing checks is not
    terminal: the branch is synced onto the new target head, the node re-enters
    the inner loop with the queue rejection quoted in the landing-evidence
    section, re-verifies through the real ladder path, and re-enqueues on pass.
    The same PR is reused, and `recovery_cycles` is incremented (FR-006).
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    pr_number = script.script_landing("us1", checks_failed_snapshot(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref="c0ffee")

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    # Two attempts: the first verified, the recovery re-verified.
    assert attempt_counts(status) == {"us1": 2}
    assert status.nodes["us1"].landing_state == LandingState.MERGED
    assert status.nodes["us1"].pr_number == pr_number

    # The recovery cycle ran a sync, then a fresh bracketed attempt.
    assert [s.node_id for s in script.sync_requests] == ["us1"]
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
        "prepare_landing_pr",
        "open_landing_pr",
        "enqueue_landing",
        "poll_landing",
        "sync_landing_branch",
        "issue_attempt_key:implementer",
        "run_agent_attempt",
        "run_gates",
        "check_output",
        "record_verification",
        "teardown_attempt:implementer",
        "salvage_worktree",
        "prepare_landing_pr",
        "open_landing_pr",
        "enqueue_landing",
        "poll_landing",
        "remove_worktree",
    ]
    # Two keys, both bracketed (FR-004 / constitution V): one per attempt.
    assert len(script.key_requests) == 2
    assert len(script.teardowns) == 2
    # The recovery attempt carried the queue rejection verbatim (002's feedback
    # discipline), and only the recovery attempt did.
    recovery_prompt = script.prompts_for("us1")[1]
    assert "## Landing rejection" in recovery_prompt
    assert "CHECKS_FAILED" in recovery_prompt
    assert "c0ffee" not in recovery_prompt  # the base_ref is carried, not quoted


async def test_conflict_routes_one_bounded_cycle_to_the_debugger_persona(
    env: WorkflowEnvironment,
) -> None:
    """US2-S2: a sync conflict gives the debugger one bounded cycle.

    The `debugger` persona runs the recovery attempt (its alias carries the
    persona, D-026), the prompt names the conflicted files, and on pass the
    branch re-enqueues. `recovery_cycles` is bounded by the config default of 1.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    pr_number = script.script_landing("us1", conflict_snapshot(), merged_snapshot())
    # The queue conflict surfaces as a sync conflict naming the dirty files.
    script.script_sync("us1", clean=False, base_ref="c0ffee",
                       conflicted_files=("src/calc.py",))

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].pr_number == pr_number
    # The recovery attempt ran under the debugger persona's alias (D-026).
    debugger_keys = [k for k in script.key_requests if k.persona == DEBUGGER_PERSONA]
    assert len(debugger_keys) == 1
    recovery_prompt = script.prompts_for("us1")[1]
    assert "## Landing rejection" in recovery_prompt
    assert "CONFLICT" in recovery_prompt
    assert "src/calc.py" in recovery_prompt


async def test_recovery_exhaustion_escalates_with_retry_and_kill_choices(
    env: WorkflowEnvironment,
) -> None:
    """US2-S3: a second failure escalates; RETRY grants one more cycle.

    With `max_recovery_cycles = 1`, a recovery that fails again exhausts the
    automatic budget and fires the Telegram escalation with the queue history
    rendered and choices [RETRY | KILL | PAUSE_EPIC] (FR-007). An operator press
    of RETRY grants exactly one more cycle; a clean re-verify then re-enqueues.
    """
    script = ScriptedWorld(
        {"us1": [passing(), failing(2), passing()]},
        client=env.client,
        press=EscalationChoice.RETRY.value,
    )
    pr_number = script.script_landing(
        "us1", checks_failed_snapshot(), merged_snapshot()
    )
    script.script_sync("us1", clean=True, base_ref="c0ffee")

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].pr_number == pr_number
    assert attempt_counts(status) == {"us1": 3}
    # One landing escalation fired, carrying the rendered queue history.
    assert len(script.escalation_requests) == 1
    history = script.escalation_requests[0].history_summary
    assert "CHECKS_FAILED" in history
    assert script.escalation_requests[0].choices == [
        EscalationChoice.RETRY,
        EscalationChoice.KILL,
        EscalationChoice.PAUSE_EPIC,
    ]


async def test_recovery_escalation_kill_preserves_the_branch(
    env: WorkflowEnvironment,
) -> None:
    """US2-S4 / FR-008: kill after exhaustion never deletes the branch.

    An operator KILL on the landing escalation ends the node KILLED; the branch
    is preserved (no removal activity deletes it — recovery's re-push still
    reads it). The queue history rendered into the escalation is the recovery
    evidence.
    """
    script = ScriptedWorld(
        {"us1": [passing(), failing(2)]},
        client=env.client,
        press=EscalationChoice.KILL.value,
    )
    script.script_landing("us1", checks_failed_snapshot(), checks_failed_snapshot())
    script.script_sync("us1", clean=True, base_ref="c0ffee")

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.KILLED}
    assert status.nodes["us1"].landing_state == LandingState.KILLED
    # The node's branch is named in the status and survives the sweep.
    assert status.nodes["us1"].branch == branch_name(EPIC_ID, "us1")
    # The escalation carried the full queue history, oldest first.
    [escalation] = script.escalation_requests
    assert "CHECKS_FAILED" in escalation.history_summary
    assert escalation.choices == [
        EscalationChoice.RETRY,
        EscalationChoice.KILL,
        EscalationChoice.PAUSE_EPIC,
    ]


async def test_recovery_outranks_a_pending_fresh_node_in_the_scheduler(
    env: WorkflowEnvironment,
) -> None:
    """A REJECTED node's recovery dispatches before a fresh PENDING node (plan § US2).

    White-box: `_ready_set` is the picker, so this asserts its ordering directly
    rather than racing the poll task's timer. A node whose landing is REJECTED
    (verified work stranded) is picked before an independent PENDING node — the
    more expensive kind of idle.
    """
    wf = EpicWorkflow()
    us1 = make_node("us1", "US1")
    us3 = make_node("us3", "US3")

    def resolved_for(node: WorkNode) -> ResolvedNode:
        return ResolvedNode(
            node=node,
            model_alias="implementer-alias",
            models=["implementer-alias"],
            write_scope="worktree",
            timeout_s=1,
        )

    # us1 verified and its landing is rejected, pending recovery.
    wf._nodes["us1"] = NodeRecord(
        node_id="us1",
        branch=branch_name(EPIC_ID, "us1"),
        state=NodeState.PR_OPEN,
        verified=True,
        landing=Landing(
            node_id="us1",
            branch=branch_name(EPIC_ID, "us1"),
            pr_number=1,
            outcomes=(
                ObservedOutcome(at="2026-08-06T10:10:00Z", outcome=QueueOutcome.CHECKS_FAILED),
            ),
            state=LandingState.REJECTED,
        ),
    )
    # us3 is fresh and ready (no dependencies).
    wf._nodes["us3"] = NodeRecord(node_id="us3", branch=branch_name(EPIC_ID, "us3"))

    ready = wf._ready_set([resolved_for(us1), resolved_for(us3)])

    assert ready
    assert ready[0].node.id == "us1"


# --- US1: the widened scheduler (FR-001/002/003/004) --------------------------


def _virtual_elapsed_s(history: Any) -> float:
    """The epic's virtual wall-clock, from the history's own timestamps.

    Under time skipping the workflow's clock advances by the real time the
    scripted agent sleeps, so a graph whose nodes run in parallel elapses about
    the slowest node's sleep, while a sequential graph elapses the sum. The
    claim "elapsed tracks the slowest node, not the sum" (SC-001) is asserted
    from these event times — the same clock the workflow itself reads.
    """
    started = completed = None
    for event in history.events:
        if event.event_type == 1:  # WorkflowExecutionStarted
            started = event.event_time.ToDatetime()
        elif event.event_type == 7:  # WorkflowExecutionCompleted
            completed = event.event_time.ToDatetime()
    assert started is not None and completed is not None
    return (completed - started).total_seconds()


def _independent_three() -> list[WorkNode]:
    """`us1`, `us2`, `us3` — all independent, declared in that order (R10)."""
    return [
        make_node("us1", "US1"),
        make_node("us2", "US2"),
        make_node("us3", "US3"),
    ]


async def test_all_ready_nodes_are_in_flight_at_once_up_to_the_cap(
    env: WorkflowEnvironment,
) -> None:
    """FR-001/SC-001: with the cap at N and N independent ready nodes, all N run
    at once.

    The scripted agent sleeps real seconds, so the three attempts genuinely
    overlap; the `running_sets` snapshots — taken while the workflow is parked on
    the attempt activities — must at some moment contain all three nodes. A
    scheduler that serialised them would never record a set of size 3.
    """
    script = ScriptedWorld(
        all_passing(), client=env.client, agent_sleep_s=0.5
    )

    await run_epic(
        env,
        script,
        graph=make_graph(_independent_three()),
        max_concurrent_nodes=3,
    )

    assert any(len(running) == 3 for running in script.running_sets), (
        f"never saw all three nodes in flight; running_sets={script.running_sets}"
    )
    # Every node dispatched an agent — order unspecified under genuine
    # concurrency: `asyncio.create_task` starts the three `_run_node` tasks in
    # declaration order, but which one's `run_agent_attempt` activity the
    # worker picks up first is timing-dependent and replays in *completion*
    # order (spec § Technical Context). SC-001's claim is simultaneity, not
    # sequence — the set is the contract, the order is not.
    assert set(script.dispatched) == {"us1", "us2", "us3"}


async def test_a_slot_is_refilled_the_moment_a_node_reaches_terminal(
    env: WorkflowEnvironment,
) -> None:
    """FR-001: with the cap below the ready count, a slot frees the instant any
    node reaches a terminal state and a new ready node takes it.

    Cap 2 over three independent nodes: `us1` and `us2` start together, and
    `us3` — which cannot start until a slot frees — must dispatch only after one
    of them has finished. No moment may ever have more than two in flight.
    """
    script = ScriptedWorld(
        all_passing(), client=env.client, agent_sleep_s=0.5
    )

    await run_epic(
        env,
        script,
        graph=make_graph(_independent_three()),
        max_concurrent_nodes=2,
    )

    assert all(len(running) <= 2 for running in script.running_sets), (
        f"more than two nodes in flight under a cap of 2: {script.running_sets}"
    )
    assert script.dispatched == ["us1", "us2", "us3"]
    # us3's attempt started only after a slot freed — i.e. after us1 or us2
    # reached a terminal state. Its running-set snapshot must show at most one
    # of us1/us2 still in flight alongside it.
    us3_snapshot = script.running_sets[2]
    assert "us3" in us3_snapshot
    assert len(us3_snapshot) <= 2


async def test_elapsed_time_tracks_the_slowest_node_not_the_sum(
    env: WorkflowEnvironment,
) -> None:
    """SC-001: a graph of N independent nodes with the cap at N elapses about
    the slowest node, not the sum of all of them.

    Three nodes each sleeping `agent_sleep_s` in parallel elapse ~one sleep; a
    sequential scheduler would elapse ~three. The virtual clock is read from the
    history's own event times, so the assertion is about the workflow's clock,
    not about wall time.

    The landing poll is taken out of the measurement (`poll_interval_s=0`) so the
    floor is the agent work alone: the landing phase is a US3 concern, and its
    60s default poll would swamp the one-second agent sleeps the test needs to
    distinguish "the slowest" from "the sum". The same graph at cap 1 — run in a
    second environment so the fixed `WORKFLOW_ID` does not collide — elapses the
    sum, which is the contrast the claim turns on.
    """
    sleep_s = 1.0
    instant_landing = LandingConfig(poll_interval_s=0)

    script = ScriptedWorld(
        all_passing(), client=env.client, agent_sleep_s=sleep_s
    )
    await run_epic(
        env,
        script,
        graph=make_graph(_independent_three()),
        max_concurrent_nodes=3,
        landing_config=instant_landing,
    )
    parallel_elapsed = _virtual_elapsed_s(await script.handle.fetch_history())

    # Three sleeps in parallel ≈ one sleep; sequential would be ≈ three.
    assert parallel_elapsed < 2.0 * sleep_s, (
        f"parallel elapsed {parallel_elapsed:.2f}s looks like the sum of three "
        f"{sleep_s}s sleeps, not the slowest one"
    )

    # The contrast: the same graph dispatched one at a time elapses the sum,
    # which is what "tracks the slowest, not the sum" is the negation of. Run in
    # its own environment because the fake agent queries the fixed WORKFLOW_ID.
    sequential_env = await WorkflowEnvironment.start_time_skipping()
    try:
        sequential_script = ScriptedWorld(
            all_passing(), client=sequential_env.client, agent_sleep_s=sleep_s
        )
        await run_epic(
            sequential_env,
            sequential_script,
            graph=make_graph(_independent_three()),
            max_concurrent_nodes=1,
            landing_config=instant_landing,
        )
        sequential_elapsed = _virtual_elapsed_s(
            await sequential_script.handle.fetch_history()
        )
    finally:
        await sequential_env.shutdown()

    assert sequential_elapsed > 2.5 * sleep_s, (
        f"sequential elapsed {sequential_elapsed:.2f}s looks parallel — a cap of "
        "1 should serialise three sleeps into ~the sum, not the slowest"
    )
    # The whole claim: parallel is markedly faster than sequential.
    assert parallel_elapsed < sequential_elapsed - sleep_s


async def test_cap_of_one_reproduces_todays_sequential_dispatch(
    env: WorkflowEnvironment,
) -> None:
    """SC-002: with the cap at 1, dispatch order and observable state are
    identical to today's sequential loop.

    The chain-plus-leaf graph (`us1 → us2`, `us3` independent) is the shape that
    distinguishes "declaration order" from "readiness": under a cap of 1, `us3` —
    ready from the start — must still wait its turn behind `us1` and `us2`,
    exactly as the sequential scheduler always did.
    """
    script = ScriptedWorld(all_passing(), client=env.client)

    status = await run_epic(env, script, max_concurrent_nodes=1)

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
        "us3": NodeState.MERGED,
    }
    assert script.dispatched == ["us1", "us2", "us3"]
    # Never more than one node in flight — the sequential loop's invariant.
    assert all(len(running) <= 1 for running in script.running_sets), (
        f"cap of 1 dispatched concurrently: {script.running_sets}"
    )
    # The in-flight observations match the sequential expectations: while us1
    # runs, us2 and us3 are still PENDING.
    during_us1 = states(script.observed["us1"])
    assert during_us1["us1"] == NodeState.RUNNING
    assert during_us1["us2"] == NodeState.PENDING
    assert during_us1["us3"] == NodeState.PENDING


async def test_no_node_is_dispatched_with_an_unmet_dependency_under_fan_out(
    env: WorkflowEnvironment,
) -> None:
    """FR-003/SC-003: with several nodes in flight, a node whose dependency
    fails is never dispatched — even while other nodes are mid-ladder.

    `us1 → us2`, `us3` independent, cap 2. `us1` fails its gate; `us2` must never
    dispatch (its dependency failed), while `us3` — independent — still runs.
    The ready set is recomputed against current state every time a slot frees,
    so a node whose dependency just failed cannot slip through the gap.
    """
    script = ScriptedWorld(
        {"us1": [failing(1)], "us2": [passing()], "us3": [passing()]},
        client=env.client,
        agent_sleep_s=0.3,
    )

    status = await run_epic(
        env,
        script,
        graph=make_graph(chain_and_leaf()),
        max_concurrent_nodes=2,
    )

    assert status.epic_state == EpicState.COMPLETED
    # `us1` exhausted its ladder and the fail-safe escalation default (no
    # operator press) ends it KILLED — the same terminal the sequential loop
    # reaches for this script at any cap, so the fan-out has not changed the
    # node's own outcome. The lock-out propagates KILLED to `us2`, whose edge
    # is now dead.
    assert states(status)["us1"] == NodeState.KILLED
    assert states(status)["us2"] == NodeState.KILLED
    assert states(status)["us3"] == NodeState.MERGED
    # us2 never dispatched an agent — its dependency failed before it could.
    assert "us2" not in script.dispatched
    assert "us3" in script.dispatched


async def test_replay_with_several_nodes_in_flight_dispatches_nothing_twice(
    env: WorkflowEnvironment,
) -> None:
    """FR-004/SC-005: a worker restart with several nodes in flight re-derives
    the epic and dispatches nothing twice.

    The recorded history is replayed against the workflow code with no worker
    attached; a scheduler that consulted a clock, a set's iteration order, or
    anything outside the SDK's deterministic event loop fails here, and the
    scripted world proves no activity ran a second time — no node re-dispatched,
    no key re-issued.
    """
    script = ScriptedWorld(
        all_passing(), client=env.client, agent_sleep_s=0.3
    )

    await run_epic(
        env,
        script,
        graph=make_graph(_independent_three()),
        max_concurrent_nodes=3,
    )
    history = await script.handle.fetch_history()

    before = list(script.calls)
    keys_before = [(r.node_id, r.attempt) for r in script.key_requests]
    attempts_before = len(script.attempts)

    await Replayer(workflows=[EpicWorkflow]).replay_workflow(history)

    assert script.calls == before
    assert [(r.node_id, r.attempt) for r in script.key_requests] == keys_before
    assert len(script.attempts) == attempts_before


# --- US4: pause, kill and lock-out stay correct with N nodes in flight --------
#
# US1 widened the scheduler to fan out up to `max_concurrent_nodes`; the three
# properties the operator's emergency controls guarantee for one in-flight node
# must hold for N. Each scenario puts several nodes genuinely in flight at once
# (independent nodes + a cap that admits them + real-time agent sleeps so the
# attempts overlap) before the control lands, and asserts the N-safe reading
# rather than the single-node one (FR-007/008/009, SC-006).


async def test_pause_with_n_in_flight_starts_nothing_new_and_lets_all_finish(
    env: WorkflowEnvironment,
) -> None:
    """FR-007/SC-1: `pause_epic` with several nodes in flight stops new dispatch
    and lets every in-flight node complete its whole ladder.

    Three independent nodes, cap 3, all in flight at once when the pause signal
    lands on `us1`'s attempt. The strong reading of "in-flight nodes finish"
    (R10) is the N-safe one: each of the three runs its gates, records its
    verdict, tears down its key, salvages, and opens + enqueues its landing —
    the key/worktree bracket stays atomic for all three — and only then does the
    epic park, with nothing further dispatched. A scheduler that treated pause
    as advisory, or that parked the moment the signal arrived and left nodes
    half-finished, would fail one of the per-node ladder assertions or the
    no-new-dispatch assertion.
    """
    script = ScriptedWorld(
        all_passing(),
        client=env.client,
        signal_during={"us1": PAUSE_SIGNAL},
        agent_sleep_s=0.5,
    )

    async with start_epic(
        env,
        script,
        graph=make_graph(_independent_three()),
        max_concurrent_nodes=3,
    ) as handle:
        # The signal lands while all three agents are still sleeping, so the
        # epic parks only after every in-flight node has drained to a terminal
        # landing state. Each node opened and enqueued its landing (the whole
        # ladder, not a suspended half), then the scheduler parked.
        paused = await wait_for_status(
            handle,
            lambda s: (
                s.epic_state == EpicState.PAUSED
                and all(
                    s.nodes[nid].state == NodeState.ENQUEUED
                    for nid in ("us1", "us2", "us3")
                )
            ),
            what="the epic to park after all three in-flight nodes finished their ladders",
        )

        # All three ran their whole ladder — verified, recorded, torn down,
        # salvaged, landed — not one of them parked halfway.
        for node_id in ("us1", "us2", "us3"):
            sequence = script.sequence(node_id)
            assert sequence[:4] == [
                "snapshot_criteria",
                "prepare_worktree",
                "issue_attempt_key:implementer",
                "run_agent_attempt",
            ], f"{node_id} did not run its full pre-landing ladder"
            assert "run_gates" in sequence, f"{node_id} did not finish its gates"
            assert "record_verification" in sequence, f"{node_id} recorded no verdict"
            assert "teardown_attempt:implementer" in sequence, (
                f"{node_id} did not close its key bracket"
            )
            assert "salvage_worktree" in sequence, f"{node_id} was not salvaged"
            assert "enqueue_landing" in sequence, f"{node_id} did not open its landing"

        assert states(paused) == {
            "us1": NodeState.ENQUEUED,
            "us2": NodeState.ENQUEUED,
            "us3": NodeState.ENQUEUED,
        }
        # All three were genuinely in flight together when the signal landed.
        assert any(len(running) == 3 for running in script.running_sets), (
            f"never saw all three in flight; running_sets={script.running_sets}"
        )
        # Pause stopped dispatch: the three independent nodes are the whole
        # graph, so nothing further could dispatch anyway — the assertion is
        # that none did, and that the epic stays parked through a quiet window.
        assert set(script.dispatched) == {"us1", "us2", "us3"}
        await asyncio.sleep(SETTLE_S)
        still = await handle.query(EpicWorkflow.epic_status)
        assert still.epic_state == EpicState.PAUSED

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
        "us3": NodeState.MERGED,
    }
    assert "overrun" not in script.calls


async def test_kill_with_n_in_flight_salvages_every_one_before_terminating(
    env: WorkflowEnvironment,
) -> None:
    """FR-008/SC-006: `kill_epic` with several nodes in flight cancels and
    salvages *every one* before the epic terminates, with every branch reachable.

    Three independent nodes, cap 3, all in flight at once when the kill signal
    lands on `us1`'s attempt. Salvage-always (constitution VI) is per node, so
    N kills must all complete their bracket — teardown, salvage, sweep — before
    the epic ends. A kill that salvages three of four is a lost-work bug; here
    the guard is that all three in-flight nodes appear in the salvage log and
    the teardown log, every branch is still named in the final status, and the
    epic does not terminate KILLED until the drain is done.
    """
    script = ScriptedWorld(
        all_passing(),
        client=env.client,
        signal_during={"us1": KILL_SIGNAL},
        await_cancel=True,
        agent_sleep_s=2.0,
    )

    async with start_epic(
        env,
        script,
        graph=make_graph(_independent_three()),
        max_concurrent_nodes=3,
    ) as handle:
        status = await handle.result()
        # The node the signal landed on ran the adapter's kill path (R2): it
        # waits, heartbeating, and on cancellation archives the transcript and
        # re-raises — recorded here, and bounded so a workflow that never
        # cancels fails rather than hangs. The other two were sleeping when the
        # kill reached them, so their cancellation surfaced as a CancelledError
        # out of the sleep rather than out of the await-cancel loop; their
        # salvage is the durable proof, and is asserted below.
        await wait_for(
            lambda: "us1" in script.cancellations,
            what="the signalled node's attempt to be cancelled",
        )

    # All three were genuinely in flight together when the kill landed.
    assert any(len(running) == 3 for running in script.running_sets), (
        f"never saw all three in flight; running_sets={script.running_sets}"
    )
    assert status.epic_state == EpicState.KILLED
    assert states(status) == {
        "us1": NodeState.KILLED,
        "us2": NodeState.KILLED,
        "us3": NodeState.KILLED,
    }
    # Every node is accounted for, and every branch is still named — a kill
    # leaves no node unaccounted for and removes no branch (FR-008).
    assert list(status.nodes) == ["us1", "us2", "us3"]
    for node_id in ("us1", "us2", "us3"):
        assert status.nodes[node_id].branch == branch_name(EPIC_ID, node_id), (
            f"{node_id}'s branch is not reachable after kill"
        )

    # The lost-work guard (SC-006): every in-flight node closed its bracket
    # (teardown) and was salvaged (constitution VI), not just the one the
    # signal landed on. A kill that salvages three of four is a lost-work bug;
    # here all three in-flight nodes must appear in both logs.
    salvaged_nodes = {s.node_id for s in script.salvages}
    assert salvaged_nodes == {"us1", "us2", "us3"}, (
        f"kill salvaged only {salvaged_nodes}, not all three in-flight nodes"
    )
    torn_down_nodes = {t.lease.node_id for t in script.teardowns}
    assert torn_down_nodes == {"us1", "us2", "us3"}, (
        f"kill tore down only {torn_down_nodes}, not all three in-flight keys"
    )
    removed_nodes = {r.node_id for r in script.removals}
    assert removed_nodes == {"us1", "us2", "us3"}, (
        f"kill swept only {removed_nodes}, not all three in-flight worktrees"
    )
    # Every bracket closed on the operator's decision — teardown carries KILLED
    # for each, whatever the agent was doing when it was told to stop.
    for teardown in script.teardowns:
        assert teardown.termination == Termination.KILLED
    # No in-flight node ran its gates or recorded a verdict: the operator asked
    # the epic to stop, and a gate suite against a worktree nobody will read is
    # the opposite of stopping (FR-008). The bracket still closed for each.
    assert "run_gates" not in script.calls
    assert "record_verification" not in script.calls
    assert script.records == []
    # The signalled node's adapter ran its kill path to the cancel; the others
    # were cancelled out of their sleep. None was left to run on.
    assert "us1" in script.cancellations
    assert "never_cancelled" not in script.calls


async def test_a_failing_node_locks_out_only_its_own_dependents_under_fan_out(
    env: WorkflowEnvironment,
) -> None:
    """FR-009/SC-3: a node ending non-PASSED while others run locks out only its
    own dependents; an unrelated in-flight node is untouched.

    `us1` fails its gates (non-PASSED) while the independent `us3` runs
    alongside it under a cap of 2. `us2` depends on `us1`, so the moment `us1`
    ends FAILED `us2` is marked KILLED without ever being dispatched — the edge
    stayed locked, so there is nothing to salvage and nothing to sweep. `us3`
    depends on nothing and is unrelated to the failed edge, so it must keep its
    ladder and reach MERGED, undisturbed by the lock-out. This is the subtlest
    change in the epic: `_lock_out_dependents` must be a statement about the
    finishing node's dependents alone, never about an unrelated in-flight node.
    """
    nodes = [
        make_node("us1", "US1"),
        make_node("us2", "US2", depends_on=["us1"]),
        make_node("us3", "US3"),
    ]
    script = ScriptedWorld(
        {
            "us1": [failing(1)],
            "us2": [passing()],
            "us3": [passing()],
        },
        client=env.client,
        agent_sleep_s=0.5,
    )

    status = await run_epic(
        env,
        script,
        graph=make_graph(nodes),
        max_concurrent_nodes=2,
    )

    # us1 ended non-PASSED (KILLED — this codebase's spelling for a node the
    # ladder did not pass, distinct from the FAILED a PAUSE_EPIC park produces),
    # us2's edge died with it, us3 was never us1's concern.
    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.KILLED,
        "us2": NodeState.KILLED,
        "us3": NodeState.MERGED,
    }
    # us2 never dispatched: no worktree, no key, no attempt — the edge stayed
    # locked, so lock-out is bookkeeping alone (FR-009).
    assert attempt_counts(status)["us2"] == 0
    assert script.sequence("us2") == []
    assert "us2" not in [r.node_id for r in script.prepare_requests]
    assert "us2" not in [r.node_id for r in script.key_requests]
    assert "us2" not in {s.node_id for s in script.salvages}

    # us3 ran its whole ladder and landed — the lock-out of us2 did not touch
    # the unrelated in-flight node.
    us3_sequence = script.sequence("us3")
    assert "run_gates" in us3_sequence
    assert "record_verification" in us3_sequence
    assert "enqueue_landing" in us3_sequence

    # us1 and us3 were genuinely in flight together — the failure happened
    # while an unrelated node was mid-ladder, which is the condition the
    # scoped lock-out must not disturb. The running-set snapshot taken when
    # us3's attempt started must show us1 still RUNNING alongside it.
    during_us3 = states(script.observed["us3"])
    assert during_us3["us1"] == NodeState.RUNNING, (
        f"us3 was not in flight alongside us1; observed={during_us3}"
    )
    # us1's failure salvaged its own work (constitution VI), then swept.
    us1_sequence = script.sequence("us1")
    assert "salvage_worktree" in us1_sequence
    assert "remove_worktree" in us1_sequence
    assert us1_sequence.index("salvage_worktree") < us1_sequence.index(
        "remove_worktree"
    )
