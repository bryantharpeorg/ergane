"""One operator question, one workflow — the sibling of `EscalationWorkflow`.

041-US3. 008 built two parks into the epic, not one: an escalation offers a
closed set of buttons, a question asks for free text. They are siblings all the
way down — two signals, two tables, two windows — because a choice pinned by the
`escalations` table's CHECK constraints cannot carry a sentence (plan trap 5).

Four differences from `EscalationWorkflow`, all inherited from 008's park: the
window is the question's own 8h (a question asked into an operator's sleep is
cheaper parked till morning than burned at 3 AM, FR-004); the ferry dedup lives
here, and the row it finds is *adopted* — its routing column re-pointed here —
rather than paged twice; there is no undelivered fail-safe, because an
escalation's default is a kill and a question's is patience; and a timeout is
EXPIRED even when `expire_question` reports a reply that won by a millisecond.

Nothing here reads the environment or a wall clock (FR-012); 039's guard finds
this module by its decorator. The window is a duration anchored at the send, not
a comparison against the row's `expires_at`: those are two clocks, for the
reason `factory/escalation/workflow.py` records.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from factory.activities.notify_activities import (
        QUESTION_TIMEOUT_S,
        ExpireQuestionInput,
        FindFerriedQuestionInput,
        SendQuestionInput,
        SettleQuestionInput,
        expire_question,
        find_ferried_question,
        send_question,
        settle_question,
    )
    from factory.notify.service import QUESTION_SIGNAL_NAME
    from factory.verify.store import ANSWERED, EXPIRED

_RETRIES = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

_FAST = {
    "start_to_close_timeout": timedelta(minutes=2),
    "retry_policy": _RETRIES,
}


@dataclasses.dataclass(frozen=True)
class QuestionRequest:
    """One question, in the operator's terms. `attempt` travels because a
    question is attributed to the attempt that asked it — what the ferry dedup
    matches on."""

    epic_id: str
    node_id: str
    attempt: int
    question_text: str
    timeout_s: int = QUESTION_TIMEOUT_S


@dataclasses.dataclass(frozen=True)
class QuestionOutcome:
    """What the question settled on. `answer_text` is exactly what the signal
    delivered, because the exchange is reproduced verbatim in the next attempt's
    prompt (008 FR-003)."""

    question_id: str
    outcome: str
    answer_text: str = ""

    @property
    def answered(self) -> bool:
        return self.outcome == ANSWERED


@workflow.defn
class QuestionWorkflow:
    """One question, from the page to the row that closes it."""

    def __init__(self) -> None:
        #: Every reply this question has been told about, in arrival order.
        #: Buffered rather than judged in the handler, for 008's reason: a reply
        #: can arrive before the workflow is waiting for it, and validating
        #: against unwritten state drops the answers that arrive fastest.
        self._replies: list[str] = []

    @workflow.signal(name=QUESTION_SIGNAL_NAME)
    def question_answered(self, question_id: str, answer_text: str) -> None:
        """Record one operator answer (`factory/notify/service.py` sends it).

        008's wire shape unchanged — `question_answered(question_id,
        answer_text)` — so the bridge and `ergane build answer` reach this
        handler without knowing the lifecycle moved, and as incurious about the
        id as the epic's was.
        """
        self._replies.append(answer_text)

    @workflow.run
    async def run(self, request: QuestionRequest) -> QuestionOutcome:
        """Page a human, then wait out the question's own window."""
        waiting_on = workflow.info().workflow_id

        ferried = await workflow.execute_activity(
            find_ferried_question,
            FindFerriedQuestionInput(
                epic_id=request.epic_id,
                node_id=request.node_id,
                attempt=request.attempt,
            ),
            **_FAST,
        )
        sent = await workflow.execute_activity(
            send_question,
            SendQuestionInput(
                # The row points at *this* workflow, so a reply reaches what is
                # waiting without knowing whether an epic exists.
                workflow_id=waiting_on,
                epic_id=request.epic_id,
                node_id=request.node_id,
                attempt=request.attempt,
                question_text=request.question_text,
                timeout_s=request.timeout_s,
                # A ferried row is adopted; otherwise the question and the
                # workflow waiting on it share one id.
                question_id=ferried.question_id or waiting_on,
            ),
            **_FAST,
        )

        try:
            await workflow.wait_condition(
                lambda: bool(self._replies),
                timeout=timedelta(seconds=request.timeout_s),
            )
        except asyncio.TimeoutError:
            await workflow.execute_activity(
                expire_question,
                ExpireQuestionInput(question_id=sent.question_id),
                **_FAST,
            )
            return QuestionOutcome(question_id=sent.question_id, outcome=EXPIRED)

        answer = self._replies[0]
        await workflow.execute_activity(
            settle_question,
            SettleQuestionInput(question_id=sent.question_id, answer_text=answer),
            **_FAST,
        )
        return QuestionOutcome(
            question_id=sent.question_id, outcome=ANSWERED, answer_text=answer
        )
