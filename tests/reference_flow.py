"""The verification loop, written out — test support, never production code.

`contracts/verification-flow.md` states the loop the WorkGraph interpreter must
run around this component's activities; this module is that contract compiled,
so `tests/test_verification_flow.py` can execute it under Temporal's
time-skipping environment and prove the pattern rather than the prose. It lives
under `tests/` deliberately (plan.md, Structure Decision): 002 ships activities
and pure decision functions, and the component that owns the production loop is
005. Nothing in `factory/` imports this file, and nothing should.

The loop it writes out is small, because almost every decision in it was moved
somewhere testable long before this file existed:

- **What happens next is `next_action`'s call, not this file's.** Every branch
  below dispatches on the pure ladder's answer (constitution IV). A flow that
  reimplemented "three attempts then a debugger" inline would satisfy its own
  policy and quietly diverge from `factory/verify/ladder.py`, which is the one an
  operator tunes.
- **What counts as a PASS is `compose_result`'s call.** The verdict truth table
  is stated once, in the composer; this flow only reads the single
  `OverallVerdict` that comes out and unlocks a downstream edge on nothing else
  (FR-005).
- **Whether the judge is worth asking is `judge_required`'s call.** A node whose
  lint gate failed in two seconds costs no completion (invariant 2), and the flow
  asks that question before minting a key rather than after.

Four orderings are the flow's own contribution, and each is load-bearing:

1. **Record, then act.** `record_verification` runs before anything branches on
   the result — before a retry prompt exists, before an operator is paged, before
   a kill. The escalation an operator answers is assembled from those rows
   (SC-005), so an ordering that acted first would page them about attempts the
   store has no record of.
2. **The judge runs inside component 1's key lifecycle.** Mint for persona
   `judge`, complete, tear down — every time, including the retries a malformed
   response buys, so no completion in this component is anonymous (constitution
   V). The key is constrained to the judge persona's own alias, which is the only
   model it has any business calling.
3. **Evidence travels verbatim.** Gate `output_tail`s and judge feedback are
   quoted into the next attempt's prompt unedited and unclipped (FR-006, SC-004).
   The prompt is a *return value* here rather than a dispatch: dispatching the
   agent belongs to the interpreter, and this flow's job is to prove the evidence
   it would hand over survives intact.
4. **A resolution is buffered by escalation id, then read.** The signal can land
   while `send_escalation` is still open — that is exactly what happens when an
   operator presses a button the instant the message arrives — so the handler
   records every answer it is given and the flow looks up its own id afterwards.
   A flow that only accepted a press while parked in `wait_condition` would drop
   it and kill a node the operator asked to retry.

Two smaller decisions worth naming. An undelivered escalation applies the kill
immediately: waiting out an hour for a message nobody received delays the same
outcome and calls it patience (R11). And an expiry that lost the race is honored
— `expire_escalation` reports the transition the store actually made, so a press
that beat the timer by a millisecond still decides the node (R12).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Sequence

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
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
        teardown_attempt,
    )
    from factory.activities.verify_activities import (
        CheckOutputInput,
        RecordVerificationInput,
        RunGatesInput,
        RunJudgeInput,
        check_output,
        record_verification,
        run_gates,
        run_judge,
    )
    from factory.notify.messages import render_history
    from factory.notify.service import SIGNAL_NAME
    from factory.usage.models import Termination
    from factory.verify.ladder import DEBUGGER_PERSONA, next_action
    from factory.verify.models import (
        AttemptRecord,
        CriteriaSet,
        EscalationChoice,
        GateStatus,
        JudgeOutcome,
        JudgeVerdict,
        NextAction,
        OutputCheck,
        OverallVerdict,
        VerificationConfig,
        VerificationForm,
        VerificationResult,
        compose_result,
        judge_required,
    )

#: The registry entry the judge's own key is minted against — a persona, never a
#: model (constitution VII). It is not the node's persona: the judge scores the
#: work, so its spend is attributed to itself.
JUDGE_PERSONA = "judge"

#: Activities here are idempotent reads, one guarded upsert, and one send that
#: mints a fresh id per attempt — all safe to retry, none worth retrying for long
#: when the ladder is holding a decision.
_RETRIES = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3)

#: One try, and the whole call including its retries: the ladder is holding a
#: decision while any of this runs, so the total is the number that matters.
#:
#: Both are test-scale, deliberately. The activities underneath are scripted
#: fakes that answer in microseconds, and — because `WorkflowEnvironment`'s
#: skipping clock advances to whatever timer is still pending when a workflow
#: closes — an ambitious ceiling here lands on the clock of a test asserting that
#: the flow did *not* wait (`test_an_undelivered_escalation_kills_immediately`
#: measures exactly that). Keeping both bounds under the minute that test allows
#: is what makes it measure the flow instead of a stale activity timeout.
#:
#: The production interpreter must scale them, and they are the least interesting
#: thing to copy out of this file: `run_gates` has to outlast a repo's entire
#: gate suite — each gate bounded separately by `VerificationConfig.gate_timeout_s`
#: (600s by default), with the per-gate `heartbeat_timeout` below as the real
#: liveness bound and room for the runner's own SIGTERM → SIGKILL escalation to
#: land — and `run_judge` has to outlast one bounded chat completion and the HTTP
#: retries inside it. The rest are a git read, a SQLite upsert and two API calls.
_ATTEMPT_TIMEOUT = timedelta(seconds=45)
_TOTAL_TIMEOUT = timedelta(seconds=50)

#: Shorter than one try, or it would bound nothing. `run_gates` reports one
#: heartbeat per gate (`_HeartbeatingExecutor`), which is what lets a legitimately
#: slow suite outlive any fixed ceiling in production.
_HEARTBEAT_TIMEOUT = timedelta(seconds=20)

#: What every activity call below shares, stated once so the bounds cannot drift
#: apart between the eight of them.
_BOUNDS = {
    "start_to_close_timeout": _ATTEMPT_TIMEOUT,
    "schedule_to_close_timeout": _TOTAL_TIMEOUT,
    "retry_policy": _RETRIES,
}


@dataclass(frozen=True)
class NodeDispatch:
    """One node, as the interpreter hands it to verification.

    `criteria` is the dispatch-time snapshot every attempt is judged against
    (FR-010) — it is passed in rather than read here, because re-snapshotting
    mid-node is precisely what that requirement forbids. `diff_text` is what the
    adapter read out of the worktree for the attempt just finished.

    `config` carries the caps the ladder reads; `form` distinguishes verification
    as a node's own phase from an explicit verifier node (FR-002), and
    `criteria_source_path` is what `record_verification` re-hashes to detect
    drift when the interpreter knows where the spec lives.
    """

    epic_id: str
    node_id: str
    spec_ref: str
    criteria: CriteriaSet
    worktree_path: str
    diff_text: str
    persona: str
    write_scope: str
    proxy_url: str
    model_alias: str
    config: VerificationConfig
    expected_artifacts: list[str] = field(default_factory=list)
    form: VerificationForm = VerificationForm.PHASE
    criteria_source_path: str | None = None


@dataclass(frozen=True)
class EscalationOutcome:
    """One page to a human, and what came back.

    `resolution` is a plain string because it has four sources with one meaning:
    a button (`RETRY`/`KILL`/`PAUSE_EPIC`), the store's `EXPIRED`, the fail-safe
    default applied when nobody was paged, and whatever the store reports when an
    expiry lost the race. The ladder reads all of them the same way.
    """

    escalation_id: str
    delivered: bool
    resolution: str


@dataclass(frozen=True)
class FlowOutcome:
    """Everything the interpreter needs once a node stops.

    `downstream_unlocked` is derived from `action` alone and is the only field an
    edge may read (FR-005); `verdict` is the last attempt's and is evidence, not
    a gate. `epic_paused` is separate from `action` because suspending an epic is
    the interpreter's move — the most a per-node loop can do is park and say so.

    `retry_prompts` are the prompts the interpreter would have dispatched, in
    order, kept so their contents can be asserted (SC-004): this flow builds them
    and runs no agent.
    """

    action: NextAction
    verdict: OverallVerdict
    downstream_unlocked: bool
    epic_paused: bool
    history: list[AttemptRecord]
    retry_prompts: list[str]
    escalations: list[EscalationOutcome]


@workflow.defn
class VerificationFlow:
    """One node's verification lifecycle, from first attempt to terminal action."""

    def __init__(self) -> None:
        #: Operator answers keyed by escalation id, buffered rather than awaited.
        #: A press can arrive before the send activity has even returned the id
        #: it belongs to, so nothing here may assume the flow is already waiting.
        self._resolutions: dict[str, str] = {}

    @workflow.signal(name=SIGNAL_NAME)
    def escalation_resolved(self, escalation_id: str, choice: str) -> None:
        """Record one operator decision (`factory/notify/service.py` sends it).

        Deliberately incurious: an id this node never escalated is stored and
        never read, because the alternative — validating against state the flow
        may not have stored yet — drops the presses that arrive fastest.
        """
        self._resolutions[escalation_id] = choice

    @workflow.run
    async def run(self, node: NodeDispatch) -> FlowOutcome:
        """Verify, decide, and repeat until the ladder says the node is done."""
        history: list[AttemptRecord] = []
        results: list[VerificationResult] = []
        prompts: list[str] = []
        escalations: list[EscalationOutcome] = []
        resolutions: list[str] = []

        persona = node.persona
        prior_feedback: str | None = None
        epic_paused = False
        attempt = 0

        while True:
            attempt += 1
            # The agent runs here in production, on the prompt this loop built
            # for it and inside its own component-1 key lifecycle. Verification
            # picks up the moment it stops.
            result, verdict = await self._verify(node, attempt, prior_feedback)
            if verdict is not None and verdict.feedback:
                # Carried across attempts, not just to the next one: an attempt
                # that failed its gates never reached the judge, and the judge's
                # last objection is still the objection being answered (R4).
                prior_feedback = verdict.feedback

            results.append(result)
            history.append(
                AttemptRecord(
                    attempt=attempt,
                    persona=persona,
                    verdict=result.verdict,
                    judge_outcome=verdict.outcome if verdict is not None else None,
                )
            )

            action = next_action(history, node.config, escalations=resolutions)

            if action == NextAction.ESCALATE:
                outcome = await self._escalate(node, results)
                escalations.append(outcome)
                resolutions.append(outcome.resolution)
                epic_paused = epic_paused or (
                    outcome.resolution == EscalationChoice.PAUSE_EPIC
                )

                action = next_action(history, node.config, escalations=resolutions)
                if action == NextAction.ESCALATE:
                    # The grant bought an attempt the caps cannot spend — the
                    # judge is out of rewrites and the debugger has had its turn.
                    # Paging again would ask the same question forever, so the
                    # node ends where the operator was already told it might.
                    action = NextAction.KILLED

            if action in (NextAction.PASSED, NextAction.KILLED):
                break

            persona = (
                DEBUGGER_PERSONA if action == NextAction.DEBUGGER else node.persona
            )
            prompts.append(
                agent_prompt(node, results, action=action, attempt=attempt + 1)
            )

        return FlowOutcome(
            action=action,
            verdict=history[-1].verdict,
            # FR-005 in one expression: PASSED is the only action that opens an
            # edge, and it is the ladder's word, not this flow's reading of a
            # verdict.
            downstream_unlocked=action == NextAction.PASSED,
            epic_paused=epic_paused,
            history=history,
            retry_prompts=prompts,
            escalations=escalations,
        )

    # --- one attempt ---------------------------------------------------------

    async def _verify(
        self, node: NodeDispatch, attempt: int, prior_feedback: str | None
    ) -> tuple[VerificationResult, JudgeVerdict | None]:
        """Gates, then output, then — only if it can still matter — the judge.

        Cheapest-first is not an optimization here but the invariant that keeps a
        failed gate from costing a completion (FR-003, invariant 2), and it is
        why `judge` stays None on every failing-gate row.
        """
        started_at = _now()

        gate_results = await workflow.execute_activity(
            run_gates,
            RunGatesInput(worktree_path=node.worktree_path),
            heartbeat_timeout=_HEARTBEAT_TIMEOUT,
            **_BOUNDS,
        )
        output = await workflow.execute_activity(
            check_output,
            CheckOutputInput(
                worktree_path=node.worktree_path,
                write_scope=node.write_scope,
                expected_artifacts=node.expected_artifacts,
            ),
            **_BOUNDS,
        )

        verdict: JudgeVerdict | None = None
        if judge_required(gate_results, output, node.criteria):
            verdict = await self._judge(node, attempt, prior_feedback)

        result = compose_result(
            epic_id=node.epic_id,
            node_id=node.node_id,
            attempt=attempt,
            form=node.form,
            gate_results=gate_results,
            output_check=output,
            judge=verdict,
            criteria_sha256=node.criteria.source_sha256,
            spec_ref=node.spec_ref,
            started_at=started_at,
            finished_at=_now(),
        )

        recorded = await workflow.execute_activity(
            record_verification,
            RecordVerificationInput(
                result=result, criteria_source_path=node.criteria_source_path
            ),
            **_BOUNDS,
        )
        # The activity re-hashes the spec file and may have found drift the
        # workflow could not see; the prompt and the escalation summary are built
        # from this bundle, so they read what the row reads (R8).
        return replace(result, criteria_drift=recorded.criteria_drift), verdict

    async def _judge(
        self, node: NodeDispatch, attempt: int, prior_feedback: str | None
    ) -> JudgeVerdict:
        """Score the diff, on a key minted and revoked for this call alone.

        The loop is for responses the strict parser could not read, and for
        nothing else: `run_judge` returns those as a RETRY with no findings, and
        asking again is the only way to tell a broken model turn from a real
        objection. A RETRY that names scenarios is an answer — re-asking it about
        an unchanged diff would buy the same verdict at twice the price, so it
        ends the attempt and the ladder takes over.
        """
        verdict: JudgeVerdict | None = None

        for judge_attempt in range(1, node.config.max_judge_retries + 2):
            lease = await workflow.execute_activity(
                issue_attempt_key,
                IssueKeyInput(
                    node_id=node.node_id,
                    epic_id=node.epic_id,
                    attempt=attempt,
                    persona=JUDGE_PERSONA,
                    spec_ref=node.spec_ref,
                    # The judge's key may call the judge's alias and nothing
                    # else: a key that could call anything is attribution
                    # without constraint (constitution V).
                    models=[node.model_alias],
                ),
                **_BOUNDS,
            )

            try:
                verdict = await workflow.execute_activity(
                    run_judge,
                    RunJudgeInput(
                        criteria=node.criteria,
                        diff_text=node.diff_text,
                        virtual_key=lease.key,
                        proxy_url=node.proxy_url,
                        model_alias=node.model_alias,
                        judge_attempt=judge_attempt,
                        prior_feedback=prior_feedback,
                        max_judge_retries=node.config.max_judge_retries,
                    ),
                    **_BOUNDS,
                )
            finally:
                # Even when the judge failed outright: a key that outlives its
                # call is spend nobody is reading, and teardown is what writes
                # the ledger row (component 1, R3).
                await workflow.execute_activity(
                    teardown_attempt,
                    TeardownInput(lease=lease, termination=Termination.COMPLETED),
                    **_BOUNDS,
                )

            if verdict.outcome != JudgeOutcome.RETRY or verdict.findings:
                break
            prior_feedback = verdict.feedback

        assert verdict is not None  # the range above is never empty
        return verdict

    # --- paging a human ------------------------------------------------------

    async def _escalate(
        self, node: NodeDispatch, results: Sequence[VerificationResult]
    ) -> EscalationOutcome:
        """Send the escalation, then wait out the hour it is worth waiting."""
        sent = await workflow.execute_activity(
            send_escalation,
            SendEscalationInput(
                workflow_id=workflow.info().workflow_id,
                epic_id=node.epic_id,
                node_id=node.node_id,
                # Every attempt, evidence and all (SC-005). The operator is being
                # asked to decide, and one summarized failure hides the shape the
                # decision turns on.
                history_summary=render_history(results),
                choices=list(DEFAULT_CHOICES),
                timeout_s=node.config.escalation_timeout_s,
            ),
            **_BOUNDS,
        )

        if not sent.delivered:
            # Nobody was paged, so there is no silence to interpret (R11).
            return EscalationOutcome(
                escalation_id=sent.escalation_id,
                delivered=False,
                resolution=EscalationChoice.KILL.value,
            )

        try:
            await workflow.wait_condition(
                lambda: sent.escalation_id in self._resolutions,
                timeout=timedelta(seconds=node.config.escalation_timeout_s),
            )
        except asyncio.TimeoutError:
            expired = await workflow.execute_activity(
                expire_escalation,
                ExpireEscalationInput(escalation_id=sent.escalation_id),
                **_BOUNDS,
            )
            # The store is the authority on who won the race, and it may report
            # a press that beat the timer (R12). `None` means it has no record at
            # all, which is not consent — the fail-safe default applies.
            resolution = expired.final_state or EscalationChoice.KILL.value
        else:
            resolution = self._resolutions[sent.escalation_id]

        return EscalationOutcome(
            escalation_id=sent.escalation_id, delivered=True, resolution=resolution
        )


# --- the prompt the next attempt is dispatched with -------------------------


def agent_prompt(
    node: NodeDispatch,
    results: Sequence[VerificationResult],
    *,
    action: NextAction,
    attempt: int,
) -> str:
    """What the next attempt is told, with the failure evidence quoted verbatim.

    Pure, and unclipped where the Telegram message is not: FR-006 asks for the
    evidence itself, and an agent handed a summary spends its attempt debugging
    the summarizer (SC-004).

    A debugger cycle sees the whole history rather than the last failure. It is
    called in *because* the ordinary retries did not converge, and the pattern
    across the attempts — the same gate failing four different ways, or four
    unrelated failures — is the thing a single failure cannot show.
    """
    if action == NextAction.DEBUGGER:
        header = (
            f"Attempt {attempt} on node {node.node_id} (epic {node.epic_id}) is a "
            f"{DEBUGGER_PERSONA} cycle on the same worktree: {len(results)} "
            "attempts have now failed verification. Read every failure below "
            "before changing anything."
        )
        evidence = list(results)
    else:
        header = (
            f"Attempt {attempt} on node {node.node_id} (epic {node.epic_id}). "
            f"Attempt {results[-1].attempt} did not pass verification."
        )
        evidence = list(results[-1:])

    return "\n\n".join(
        [
            header,
            *(_evidence(result) for result in evidence),
            f"The acceptance criteria have not changed ({node.spec_ref}): the same "
            "gates run again and the same scenarios are scored again.",
        ]
    )


def _evidence(result: VerificationResult) -> str:
    """One attempt's failures, quoted — nothing that passed, nothing paraphrased."""
    blocks = [f"── attempt {result.attempt}: {result.verdict} ──"]

    for gate in result.gate_results:
        if gate.status == GateStatus.PASS:
            continue
        blocks.append(
            f"gate {gate.name} ({gate.status}, `{gate.command}`):\n{gate.output_tail}"
        )

    check = result.output_check
    if not check.passed:
        blocks.append(f"output check: {_output_check_detail(check)}")

    if result.judge is not None and result.judge.feedback:
        blocks.append(f"judge ({result.judge.outcome}):\n{result.judge.feedback}")

    return "\n\n".join(blocks)


def _output_check_detail(check: OutputCheck) -> str:
    """Name an empty diff for what it is (FR-004).

    Left out of the message, this failure reads as "everything passed": the node
    produced nothing and the gates were green about it.
    """
    if not check.has_diff:
        return (
            f"no diff in the {check.write_scope} write scope — this attempt "
            "produced nothing"
        )
    if check.artifacts_present is False:
        expected = ", ".join(check.expected_artifacts) or "(none declared)"
        return f"expected artifacts missing or empty: {expected}"
    return "failed"


def _now() -> str:
    """The workflow's own clock, in the factory's one timestamp spelling.

    `workflow.now()` rather than `datetime.now()`: a replayed workflow has to
    stamp a row with the same instant the first run did.
    """
    return _iso(workflow.now())


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")
