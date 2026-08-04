"""The loop that drives all of it — proven against a skipped hour.

002 ships activities and pure decision functions; the WorkGraph interpreter owns
the loop that calls them. `contracts/verification-flow.md` is that loop written
down, and `tests/reference_flow.py` is it written out — test support, explicitly
not production code, exercised here under Temporal's time-skipping environment so
the one-hour escalation deadline costs a millisecond instead of an hour.

Everything the flow touches is scripted. Gates, the output check, the judge, the
store write, the send and the expiry are all fakes registered under the real
activity names, which is what makes the loop itself the thing under test: no
subprocess runs, no proxy is called, no database is opened, and every verdict the
ladder reads is one this file chose. What is *not* faked is the ladder — the
decisions come from `factory/verify/ladder.py`, so a flow that reimplemented the
policy inline would pass its own rules and fail these.

What these tests pin down, in the order the contract states them:

- **Downstream unlocks on PASS and only on PASS (FR-005).** Every test asserts
  `downstream_unlocked` either way, because the one thing this loop can get wrong
  that nothing downstream can detect is releasing an edge over a node that failed.
- **The retry prompt carries the prior evidence verbatim (FR-006, SC-004).** Not
  paraphrased, not summarized: the failing gate's `output_tail` and the judge's
  feedback appear as exact substrings of the next attempt's prompt. An agent
  handed a summary is an agent debugging the summarizer.
- **The ladder walks retry → debugger → escalate.** Three attempts, one debugger
  cycle, then a human — and the judge is never consulted on an attempt whose gates
  failed (flow invariant 2), which the scripted world proves by recording that
  `run_judge` was never called at all.
- **Every attempt is recorded before anything acts on it (invariant 3).** The
  evidence store is written even when the node is about to be killed, because
  SC-005's failure history is assembled from those rows. Asserted structurally,
  from the activity call log, rather than by counting rows afterwards — "both
  happened" is not the claim.
- **Each escalation choice is honored.** RETRY grants exactly one more attempt,
  KILL ends the node with downstream still locked, PAUSE_EPIC parks it and says so
  to the interpreter that owns epic-level suspension.
- **Silence has a deadline, and an undelivered escalation has none.** An hour of
  no answer expires the escalation in the store and applies the default kill
  (FR-008, R12); a `delivered=false` send skips the wait entirely, because waiting
  out an hour for a message nobody received is an hour of pretending.

Two properties of the design are load-bearing enough that the fakes are built to
break a flow that gets them wrong:

- **A resolution can arrive before the workflow starts waiting.** The fake
  `send_escalation` signals from *inside* the activity, exactly as the bridge does
  the moment an operator presses a button — so the signal is in history before the
  activity's completion is. A flow that only accepts a signal while parked in
  `wait_condition`, or that validates the id against state it has not yet stored,
  drops the press and kills a node the operator asked to retry. Resolutions have to
  be buffered by escalation id and read afterwards.
- **Expiry reports a transition rather than asserting one.** `expire_escalation`
  returns `EXPIRED` when the hour genuinely won, and the operator's choice when a
  press got there first (R12, and the activity's own contract). A flow that
  discarded that return value would kill a node whose store row says RETRY.

Written before `tests/reference_flow.py` exists (T029 precedes T030): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, AsyncIterator, Sequence

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

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
)
from factory.notify.service import SIGNAL_NAME
from factory.usage.models import KeyLease, Termination, UsageRecord
from factory.verify.ladder import DEBUGGER_PERSONA
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    NextAction,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationConfig,
    VerificationResult,
)
from factory.verify.store import EXPIRED
from tests.reference_flow import NodeDispatch, VerificationFlow

EPIC = "epic-002-verification-gating"
NODE = "node-implement-gates"
SPEC_REF = "specs/002-verification-gating/spec.md#US2"
WORKTREE = "/srv/factory/worktrees/node-implement-gates"

#: The judge's persona registry alias, never a model name (constitution VII).
MODEL_ALIAS = "judge-alias"
PROXY_URL = "http://litellm.test"

#: What component 1's `issue_attempt_key` hands back for the judge's own call.
#: Distinctive so the assertion that the judge ran on the *leased* key cannot pass
#: by accident.
JUDGE_KEY = "sk-attempt-judge-lease"

#: The diff the adapter read out of the worktree. Its content is irrelevant to
#: every assertion here — the judge is scripted — so it carries a marker instead
#: of code, which is exactly what it is in this test: an opaque payload the flow
#: must hand to the judge and nothing else.
DIFF = "--- a/factory/verify/gates.py\n+++ b/factory/verify/gates.py\n+# scripted diff\n"

#: Failing gate output, one distinctive block per attempt. Every one of these is
#: asserted to survive verbatim into a retry prompt (SC-004) and into the
#: escalation's failure history (SC-005), so no two may be substrings of another.
GATE_TAIL = {
    1: "E   AssertionError: attempt-one expected a GateResult, found none",
    2: "E   TypeError: attempt-two GateExecutor.run() missing 1 argument",
    3: "E   AssertionError: attempt-three timeout never sent SIGKILL",
    4: "E   AssertionError: attempt-four debugger left the deadline unhandled",
    5: "E   AssertionError: attempt-five still no SIGKILL",
}

#: Judge feedback, likewise quoted verbatim into the next prompt and citing the
#: scenario by name as FR-003 requires.
JUDGE_FEEDBACK = (
    "US1-S1 fails: the timeout path sends SIGTERM and returns, so nothing in the "
    "diff ever escalates to SIGKILL as the scenario's Then step requires."
)


# --- the criteria the node was dispatched against ---------------------------


CRITERIA = CriteriaSet(
    feature="002-verification-gating",
    spec_ref=SPEC_REF,
    requirements=[
        Requirement(
            key="US1",
            kind=RequirementKind.STORY,
            title="Two-tier verification of a node's diff",
            priority="P1",
            body="As the interpreter, a verifier evaluates the node's work.",
            scenarios=[
                Scenario(
                    scenario_id="US1-S1",
                    steps=[
                        "Given a gate command that hangs",
                        "When the deadline passes",
                        "Then the runner sends SIGTERM and then SIGKILL",
                    ],
                    raw_text=(
                        "1. **Given** a gate command that hangs, **When** the "
                        "deadline passes, **Then** the runner sends SIGTERM and "
                        "then SIGKILL."
                    ),
                )
            ],
        )
    ],
    source_path="specs/002-verification-gating/spec.md",
    source_sha256="0" * 64,
    snapshotted_at="2026-08-04T09:00:00Z",
)


# --- scripted evidence ------------------------------------------------------


def gate_pass(name: str = "test") -> GateResult:
    return GateResult(
        name=name,
        command="uv run pytest -q",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=12.5,
        output_tail="41 passed in 12.44s",
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
        write_scope="worktree",
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


def judge_pass() -> JudgeVerdict:
    return JudgeVerdict(
        outcome=JudgeOutcome.PASS,
        findings=[
            JudgeScenarioFinding(
                scenario="US1-S1",
                passed=True,
                reasoning="The runner escalates to SIGKILL after the grace period.",
            )
        ],
        feedback="",
        judge_attempt=1,
        truncated_input=False,
        model_alias=MODEL_ALIAS,
    )


def judge_retry(feedback: str = JUDGE_FEEDBACK) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=JudgeOutcome.RETRY,
        findings=[
            JudgeScenarioFinding(
                scenario="US1-S1", passed=False, reasoning=feedback
            )
        ],
        feedback=feedback,
        judge_attempt=1,
        truncated_input=False,
        model_alias=MODEL_ALIAS,
    )


@dataclass(frozen=True)
class Attempt:
    """What the world does to one attempt of the node.

    `judge` is what `run_judge` returns *if the flow asks*. Scripting a verdict
    the flow never collects is how the gate-failure tests prove invariant 2: the
    judge is loaded and then never called.
    """

    gates: list[GateResult]
    output: OutputCheck = field(default_factory=wrote_something)
    judge: JudgeVerdict | None = None


def failing_attempt(attempt: int) -> Attempt:
    """A gate failure — the cheapest verdict, and the one that skips the judge."""
    return Attempt(gates=[gate_fail(attempt)])


def passing_attempt() -> Attempt:
    return Attempt(gates=[gate_pass()], judge=judge_pass())


# --- the scripted world -----------------------------------------------------


#: Activity names that act on a verdict. Nothing in this set may precede the
#: `record_verification` of the attempt it belongs to (flow invariant 3).
_ACTIONS = frozenset({"send_escalation", "expire_escalation"})


class ScriptedWorld:
    """Every activity the reference flow calls, answered from a script.

    Registered under the real activity names, so the flow addresses
    `run_gates`/`run_judge`/`record_verification`/`send_escalation` exactly as it
    would in production and a rename in the activity surface breaks these tests
    rather than silently bypassing them.

    The escalation half is where the fakes have opinions. `press` is signalled
    from inside `send_escalation` — the bridge's timing, not a convenient one —
    and `expiry_state` is what `expire_escalation` reports the store settled on.
    """

    def __init__(
        self,
        attempts: Sequence[Attempt],
        *,
        client: Any,
        delivered: bool = True,
        press: str | None = None,
        stale_press: bool = False,
        expiry_state: str | None = EXPIRED,
    ) -> None:
        self._attempts = list(attempts)
        self._client = client
        self._delivered = delivered
        self._press = press
        self._stale_press = stale_press
        self._expiry_state = expiry_state

        #: Activity names in call order — the evidence for invariant 3.
        self.calls: list[str] = []
        self.gate_requests: list[RunGatesInput] = []
        self.output_requests: list[CheckOutputInput] = []
        self.judge_requests: list[RunJudgeInput] = []
        self.key_requests: list[IssueKeyInput] = []
        self.teardowns: list[TeardownInput] = []
        self.records: list[VerificationResult] = []
        self.escalation_requests: list[SendEscalationInput] = []
        self.expirations: list[str] = []
        self.escalation_ids: list[str] = []
        self._index = -1

    # The current attempt's script. Running past the end is a test failure, not
    # an exception: an activity that raised would be retried forever by Temporal
    # and hang the test rather than fail it.
    @property
    def _current(self) -> Attempt:
        if self._index >= len(self._attempts):
            self.calls.append("overrun")
            return self._attempts[-1]
        return self._attempts[self._index]

    def activities(self) -> list[Any]:
        script = self

        @activity.defn(name="run_gates")
        async def run_gates(request: RunGatesInput) -> list[GateResult]:
            script._index += 1
            script.calls.append("run_gates")
            script.gate_requests.append(request)
            return script._current.gates

        @activity.defn(name="check_output")
        async def check_output(request: CheckOutputInput) -> OutputCheck:
            script.calls.append("check_output")
            script.output_requests.append(request)
            return script._current.output

        @activity.defn(name="issue_attempt_key")
        async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
            script.calls.append("issue_attempt_key")
            script.key_requests.append(request)
            return KeyLease(
                key=JUDGE_KEY,
                key_alias=f"{request.epic_id}-{request.node_id}-{request.attempt}-judge",
                node_id=request.node_id,
                epic_id=request.epic_id,
                attempt=request.attempt,
                persona=request.persona,
                spec_ref=request.spec_ref,
                issued_at="2026-08-04T09:30:00Z",
            )

        @activity.defn(name="run_judge")
        async def run_judge(request: RunJudgeInput) -> JudgeVerdict:
            script.calls.append("run_judge")
            script.judge_requests.append(request)
            verdict = script._current.judge
            assert verdict is not None, "the flow judged an attempt with no scripted verdict"
            return verdict

        @activity.defn(name="teardown_attempt")
        async def teardown_attempt(request: TeardownInput) -> UsageRecord:
            script.calls.append("teardown_attempt")
            script.teardowns.append(request)
            lease = request.lease
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
                termination=Termination.COMPLETED,
                issued_at=lease.issued_at,
                torn_down_at="2026-08-04T09:31:00Z",
            )

        @activity.defn(name="record_verification")
        async def record_verification(
            request: RecordVerificationInput,
        ) -> RecordedVerification:
            script.calls.append("record_verification")
            script.records.append(request.result)
            return RecordedVerification(
                row_id=len(script.records),
                criteria_drift=request.result.criteria_drift,
            )

        @activity.defn(name="send_escalation")
        async def send_escalation(request: SendEscalationInput) -> SentEscalation:
            script.calls.append("send_escalation")
            script.escalation_requests.append(request)

            escalation_id = f"{len(script.escalation_requests):012x}"
            script.escalation_ids.append(escalation_id)

            if script._delivered and script._stale_press:
                # A button from some other escalation entirely. The flow is
                # holding exactly one, and answering to an id it never sent is
                # how a duplicated message resolves the wrong node.
                await script._signal(request.workflow_id, "ffffffffffff", "KILL")
            if script._delivered and script._press is not None:
                # The bridge's timing: the press lands while the send activity is
                # still open, so the signal precedes the activity's completion in
                # history and the flow is not yet parked on the resolution.
                await script._signal(request.workflow_id, escalation_id, script._press)

            return SentEscalation(
                escalation_id=escalation_id,
                delivered=script._delivered,
                expires_at="2026-08-04T10:30:00Z",
            )

        @activity.defn(name="expire_escalation")
        async def expire_escalation(
            request: ExpireEscalationInput,
        ) -> ExpiredEscalation:
            script.calls.append("expire_escalation")
            script.expirations.append(request.escalation_id)
            return ExpiredEscalation(final_state=script._expiry_state)

        return [
            run_gates,
            check_output,
            issue_attempt_key,
            run_judge,
            teardown_attempt,
            record_verification,
            send_escalation,
            expire_escalation,
        ]

    async def _signal(self, workflow_id: str, escalation_id: str, choice: str) -> None:
        """Exactly what `CallbackBridge` sends, by the same name and shape."""
        handle = self._client.get_workflow_handle(workflow_id)
        await handle.signal(SIGNAL_NAME, args=[escalation_id, choice])


# --- harness ----------------------------------------------------------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — an hour of silence costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


def dispatch(**overrides: Any) -> NodeDispatch:
    """The node as the interpreter would hand it to the flow.

    Every field named here is required of `NodeDispatch`; anything else it
    carries (`expected_artifacts`, `form`, `criteria_source_path`) must default.
    """
    request = {
        "epic_id": EPIC,
        "node_id": NODE,
        "spec_ref": SPEC_REF,
        "criteria": CRITERIA,
        "worktree_path": WORKTREE,
        "diff_text": DIFF,
        "persona": "implementer",
        "write_scope": "worktree",
        "proxy_url": PROXY_URL,
        "model_alias": MODEL_ALIAS,
        "config": VerificationConfig(),
    }
    request.update(overrides)
    return NodeDispatch(**request)


async def run_flow(
    env: WorkflowEnvironment,
    script: ScriptedWorld,
    node: NodeDispatch | None = None,
) -> Any:
    """Run one node's verification lifecycle to its terminal decision."""
    task_queue = f"verification-flow-{uuid.uuid4()}"
    async with Worker(
        env.client,
        task_queue=task_queue,
        workflows=[VerificationFlow],
        activities=script.activities(),
    ):
        handle = await env.client.start_workflow(
            VerificationFlow.run,
            node if node is not None else dispatch(),
            id=f"{NODE}-{uuid.uuid4()}",
            task_queue=task_queue,
        )
        return await handle.result()


def attempt_segments(calls: Sequence[str]) -> list[list[str]]:
    """Split the activity call log at each attempt's first call.

    One segment per attempt, so "what happened during attempt 3" is a list rather
    than an offset someone has to count out by hand.
    """
    segments: list[list[str]] = []
    for call in calls:
        if call == "run_gates" or not segments:
            segments.append([])
        segments[-1].append(call)
    return segments


# --- PASS unlocks, and only PASS unlocks (FR-005) ---------------------------


async def test_a_passing_attempt_unlocks_downstream(env: WorkflowEnvironment) -> None:
    """Green gates, real output and an agreeing judge: the edge opens, once."""
    script = ScriptedWorld([passing_attempt()], client=env.client)

    outcome = await run_flow(env, script)

    assert outcome.action == NextAction.PASSED
    assert outcome.verdict == OverallVerdict.PASS
    assert outcome.downstream_unlocked is True
    assert outcome.retry_prompts == []
    assert outcome.escalations == []
    assert outcome.epic_paused is False

    assert [record.attempt for record in outcome.history] == [1]
    assert outcome.history[0].persona == "implementer"
    assert len(script.records) == 1
    assert script.records[0].verdict == OverallVerdict.PASS


async def test_the_judge_runs_inside_component_ones_key_lifecycle(
    env: WorkflowEnvironment,
) -> None:
    """No unattributed LLM call exists in this component (constitution V).

    The judge's completion is bracketed by `issue_attempt_key` and
    `teardown_attempt`, it authenticates with the key that lease returned, and the
    key is minted for the `judge` persona — not for the node's own.
    """
    script = ScriptedWorld([passing_attempt()], client=env.client)

    await run_flow(env, script)

    assert script.calls == [
        "run_gates",
        "check_output",
        "issue_attempt_key",
        "run_judge",
        "teardown_attempt",
        "record_verification",
    ]

    [key_request] = script.key_requests
    assert key_request.persona == "judge"
    assert (key_request.epic_id, key_request.node_id, key_request.attempt) == (
        EPIC,
        NODE,
        1,
    )

    [judge_request] = script.judge_requests
    assert judge_request.virtual_key == JUDGE_KEY
    assert judge_request.model_alias == MODEL_ALIAS
    assert judge_request.diff_text == DIFF
    assert judge_request.criteria.requirements[0].scenarios[0].scenario_id == "US1-S1"

    [teardown] = script.teardowns
    assert teardown.lease.key == JUDGE_KEY


# --- retry prompts carry the evidence verbatim (FR-006, SC-004) -------------


async def test_retry_prompts_quote_gate_output_and_judge_feedback_verbatim(
    env: WorkflowEnvironment,
) -> None:
    """Both kinds of failure evidence reach the next attempt unedited.

    Attempt 1 fails on the judge, attempt 2 on a gate, attempt 3 passes — so one
    prompt has to carry feedback and the other has to carry gate output, and
    neither may arrive summarized. The assertion is substring-exact on purpose:
    an agent handed a paraphrase is debugging the paraphraser.
    """
    script = ScriptedWorld(
        [
            Attempt(gates=[gate_pass()], judge=judge_retry()),
            failing_attempt(2),
            passing_attempt(),
        ],
        client=env.client,
    )

    outcome = await run_flow(env, script)

    assert outcome.action == NextAction.PASSED
    assert outcome.downstream_unlocked is True
    assert len(outcome.retry_prompts) == 2

    assert JUDGE_FEEDBACK in outcome.retry_prompts[0]
    assert GATE_TAIL[2] in outcome.retry_prompts[1]

    # The judge asked for the first rewrite; the gate failed the second attempt
    # on its own, and no judge was consulted for it (invariant 2).
    assert [record.judge_outcome for record in outcome.history] == [
        JudgeOutcome.RETRY,
        None,
        JudgeOutcome.PASS,
    ]
    assert len(script.judge_requests) == 2

    # The rewrite request travels into the judge's next call as prior feedback,
    # so the judge is scoring an answer to its own objection (R4).
    assert script.judge_requests[1].prior_feedback == JUDGE_FEEDBACK


# --- the ladder walk (FR-006, FR-007, FR-008) -------------------------------


def kill_pressed(client: Any) -> ScriptedWorld:
    """Three attempts, a debugger cycle, an escalation the operator kills."""
    return ScriptedWorld(
        [failing_attempt(n) for n in (1, 2, 3, 4)],
        client=client,
        press="KILL",
    )


async def test_the_ladder_walks_retry_then_debugger_then_escalation(
    env: WorkflowEnvironment,
) -> None:
    """Three attempts, one debugger cycle, then — and only then — a human.

    The debugger is a rung rather than a fourth attempt: it runs on the same
    worktree under its own persona, and its failure is what fires the escalation
    (FR-007). The judge is never consulted anywhere in this run, because every
    attempt died on a gate (invariant 2, and SC-003's bound from the cheap side).
    """
    script = kill_pressed(env.client)

    outcome = await run_flow(env, script)

    assert [record.attempt for record in outcome.history] == [1, 2, 3, 4]
    assert [record.persona for record in outcome.history] == [
        "implementer",
        "implementer",
        "implementer",
        DEBUGGER_PERSONA,
    ]
    assert all(record.verdict == OverallVerdict.FAIL for record in outcome.history)

    assert script.judge_requests == []
    assert script.key_requests == []

    # Attempts 2, 3 and the debugger's each got a prompt built from the failure
    # before it, the debugger included — a debugger dispatched without the
    # evidence is a debugger starting from scratch.
    assert len(outcome.retry_prompts) == 3
    for prompt, attempt in zip(outcome.retry_prompts, (1, 2, 3)):
        assert GATE_TAIL[attempt] in prompt

    assert len(script.escalation_requests) == 1
    assert outcome.action == NextAction.KILLED
    assert outcome.downstream_unlocked is False


async def test_the_escalation_carries_the_full_failure_history(
    env: WorkflowEnvironment,
) -> None:
    """SC-005: every attempt's evidence, in the one message that pages a human.

    The operator is being asked to decide, and the history is the whole basis for
    deciding. A summary of the last failure would hide the shape that matters —
    the same gate failing four different ways is a different decision from four
    unrelated failures.
    """
    script = kill_pressed(env.client)

    await run_flow(env, script)

    [escalation] = script.escalation_requests
    assert escalation.workflow_id  # the bridge signals this; it cannot be blank
    assert (escalation.epic_id, escalation.node_id) == (EPIC, NODE)
    for attempt in (1, 2, 3, 4):
        assert GATE_TAIL[attempt] in escalation.history_summary

    offered = {str(choice) for choice in escalation.choices}
    assert offered == {"RETRY", "KILL", "PAUSE_EPIC"}


async def test_every_attempt_is_recorded_before_anything_acts_on_it(
    env: WorkflowEnvironment,
) -> None:
    """Flow invariant 3 — the evidence store is written even on the way to a kill.

    Asserted from the call log rather than from row counts afterwards: "the row
    exists and the escalation was sent" is true of an ordering that loses every
    row to a crash mid-escalation, which is precisely the ordering this forbids.
    """
    script = kill_pressed(env.client)

    await run_flow(env, script)

    segments = attempt_segments(script.calls)
    assert len(segments) == 4
    for segment in segments:
        assert "record_verification" in segment
        recorded = segment.index("record_verification")
        assert not _ACTIONS.intersection(segment[:recorded])

    assert [record.attempt for record in script.records] == [1, 2, 3, 4]
    assert script.calls.count("record_verification") == 4
    assert script.calls[-1] == "send_escalation"
    assert "overrun" not in script.calls


# --- each escalation choice is honored (FR-008) -----------------------------


async def test_escalation_retry_grants_exactly_one_more_attempt(
    env: WorkflowEnvironment,
) -> None:
    """One press, one attempt — and a press for an id we never sent changes nothing.

    The grant is an attempt, not a fresh budget: a fifth attempt runs and the
    ladder's caps are otherwise untouched, so a node that failed again would need
    a second escalation to try a sixth time.
    """
    script = ScriptedWorld(
        [failing_attempt(n) for n in (1, 2, 3, 4)] + [passing_attempt()],
        client=env.client,
        press="RETRY",
        stale_press=True,
    )

    outcome = await run_flow(env, script)

    assert [record.attempt for record in outcome.history] == [1, 2, 3, 4, 5]
    assert outcome.history[-1].persona == "implementer"
    assert outcome.action == NextAction.PASSED
    assert outcome.downstream_unlocked is True

    [escalation] = outcome.escalations
    assert escalation.delivered is True
    assert escalation.resolution == "RETRY"
    assert script.expirations == []
    assert "overrun" not in script.calls


async def test_escalation_kill_ends_the_node_with_downstream_locked(
    env: WorkflowEnvironment,
) -> None:
    """The operator's kill is terminal, and it is evidence — not a lost run."""
    script = kill_pressed(env.client)

    outcome = await run_flow(env, script)

    assert outcome.action == NextAction.KILLED
    assert outcome.verdict == OverallVerdict.FAIL
    assert outcome.downstream_unlocked is False
    assert outcome.epic_paused is False

    [escalation] = outcome.escalations
    assert escalation.resolution == "KILL"
    assert escalation.escalation_id == script.escalation_ids[0]

    # Nothing ran after the answer: a kill that let one more attempt through is a
    # kill the operator has to press twice.
    assert len(outcome.history) == 4
    assert script.expirations == []


async def test_escalation_pause_epic_parks_the_node_and_says_so(
    env: WorkflowEnvironment,
) -> None:
    """PAUSE_EPIC is a decision about the epic; the node parks and reports it.

    Suspending the release of new nodes belongs to the interpreter, so the most
    this loop can do is stop, keep the edge locked, and hand back the fact — which
    is why `epic_paused` exists separately from the terminal action.
    """
    script = ScriptedWorld(
        [failing_attempt(n) for n in (1, 2, 3, 4)],
        client=env.client,
        press="PAUSE_EPIC",
    )

    outcome = await run_flow(env, script)

    assert outcome.action == NextAction.KILLED
    assert outcome.downstream_unlocked is False
    assert outcome.epic_paused is True
    assert outcome.escalations[0].resolution == "PAUSE_EPIC"
    assert len(outcome.history) == 4


# --- silence, and messages nobody received (FR-008, R11, R12) ---------------


async def test_an_hour_of_silence_expires_the_escalation_then_kills(
    env: WorkflowEnvironment,
) -> None:
    """The default is kill, and the store is told before the default applies.

    An hour passes on the workflow's clock and none in the test's: the timer is
    Temporal's, which is what makes the deadline survive a worker restart and what
    makes asserting it affordable here.
    """
    script = ScriptedWorld(
        [failing_attempt(n) for n in (1, 2, 3, 4)],
        client=env.client,
        press=None,
    )

    started = await env.get_current_time()
    outcome = await run_flow(env, script)
    elapsed = await env.get_current_time() - started

    assert elapsed >= timedelta(seconds=VerificationConfig().escalation_timeout_s)
    assert script.expirations == script.escalation_ids

    assert outcome.action == NextAction.KILLED
    assert outcome.downstream_unlocked is False
    assert outcome.escalations[0].resolution == EXPIRED
    assert len(outcome.history) == 4


async def test_an_expiry_that_lost_the_race_honors_the_press(
    env: WorkflowEnvironment,
) -> None:
    """The store, not the timer, is the authority on who won (R12).

    `expire_escalation` reports the transition it actually made: `EXPIRED` when
    the hour won, the operator's choice when a press landed in the same instant.
    A flow that discarded that answer would kill a node whose own evidence row
    says the operator asked for one more attempt.
    """
    script = ScriptedWorld(
        [failing_attempt(n) for n in (1, 2, 3, 4)] + [passing_attempt()],
        client=env.client,
        press=None,
        expiry_state="RETRY",
    )

    outcome = await run_flow(env, script)

    assert script.expirations == script.escalation_ids
    assert outcome.escalations[0].resolution == "RETRY"
    assert [record.attempt for record in outcome.history] == [1, 2, 3, 4, 5]
    assert outcome.action == NextAction.PASSED
    assert outcome.downstream_unlocked is True


async def test_an_undelivered_escalation_kills_immediately(
    env: WorkflowEnvironment,
) -> None:
    """Nobody was paged, so there is nothing to wait for (R11).

    `delivered=false` means the notifier is down or unconfigured. Waiting out the
    hour would delay the same kill by an hour and call it patience; the fail-safe
    default applies at once, and the row stays in the store to be expired by
    whoever finds it.
    """
    script = ScriptedWorld(
        [failing_attempt(n) for n in (1, 2, 3, 4)],
        client=env.client,
        delivered=False,
    )

    started = await env.get_current_time()
    outcome = await run_flow(env, script)
    elapsed = await env.get_current_time() - started

    assert elapsed < timedelta(minutes=1)
    assert script.expirations == []

    assert outcome.action == NextAction.KILLED
    assert outcome.downstream_unlocked is False
    [escalation] = outcome.escalations
    assert escalation.delivered is False
    assert escalation.resolution == "KILL"
    assert len(outcome.history) == 4
