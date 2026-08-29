"""One peer message, one workflow — the sibling of `QuestionWorkflow` (017-US1).

041-US3 took the question lifecycle out of the epic and made it a child
workflow; the peer message is the same move, made deliberately this time. The
plan's instruction is explicit: do not build peer messages as sibling buffers
inside the epic workflow — that was 041's recorded mistake. So `MessageWorkflow`
mirrors `QuestionWorkflow` (`factory/escalation/question.py`) and owns its
signal, its window and its row.

What makes it *not* a copy: the epic's park semantics. 008's operator park
raises the scheduler's pause flag — an epic waiting on a sleeping human should
idle rather than spend. Reusing that path here deadlocks the feature by
construction: the node that must answer a peer question is a node of this same
epic, and the pause is exactly what stops it from being dispatched (the
deadlock 008 itself documented, and the reason FR-016 exists). The epic parks
its node in `WAITING_PEER` and writes **no** pause flag; the workflow here owns
the message row, the window, and the `message_reply` signal.

Nothing here reads the environment or a wall clock; the window is a duration
anchored at the send, not a comparison against the row's `expires_at` (two
clocks, one bug — the reason `factory/escalation/workflow.py` records).
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, VersioningBehavior

with workflow.unsafe.imports_passed_through():
    from factory.activities.notify_activities import (
        QUESTION_TIMEOUT_S,
        ResolveMessageInput,
        resolve_message_row,
    )
    from factory.notify.service import MESSAGE_REPLY_SIGNAL_NAME
    from factory.versioning import workflow_versioning_behavior
    from factory.verify.store import (
        MESSAGE_ANSWERED,
        MESSAGE_EXPIRED,
    )

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
class MessageRequest:
    """One peer message, in the sender's terms. Everything attribution needs
    (FR-008) plus the routing key a reply threads to (FR-003)."""

    epic_id: str
    node_id: str
    attempt: int
    message_id: str
    body: str
    addressee: str
    workflow_id: str
    timeout_s: int = QUESTION_TIMEOUT_S


@dataclasses.dataclass(frozen=True)
class MessageOutcome:
    """What the message settled on. `reply_text` is exactly what the signal
    delivered, because the exchange is reproduced verbatim in the next attempt's
    prompt (FR-003)."""

    message_id: str
    outcome: str
    reply_text: str = ""

    @property
    def answered(self) -> bool:
        return self.outcome == MESSAGE_ANSWERED


@workflow.defn(versioning_behavior=workflow_versioning_behavior(VersioningBehavior.PINNED))
class MessageWorkflow:
    """One peer message, from the page to the row that closes it."""

    def __init__(self) -> None:
        #: Every reply this message has been told about, in arrival order.
        #: Buffered rather than judged in the handler — the 008 hard rule: a
        #: reply can arrive before the workflow is waiting for it, and
        #: validating against unwritten state drops the replies that arrive
        #: fastest.
        self._replies: list[str] = []

    @workflow.signal(name=MESSAGE_REPLY_SIGNAL_NAME)
    def message_replied(self, message_id: str, reply_text: str) -> None:
        """Record one peer reply (`factory/notify/service.py` sends it).

        As incurious about the id as `question_answered` is: the signal only
        buffers; the wait condition reads (plan trap 2).
        """
        self._replies.append(reply_text)

    @workflow.run
    async def run(self, request: MessageRequest) -> MessageOutcome:
        """Wait out the message's own window, then settle the row."""
        _ = request  # attribution lives in the row the send wrote; see below

        try:
            await workflow.wait_condition(
                lambda: bool(self._replies),
                timeout=timedelta(seconds=request.timeout_s),
            )
        except asyncio.TimeoutError:
            await workflow.execute_activity(
                resolve_message_row,
                ResolveMessageInput(
                    message_id=request.message_id,
                    outcome=MESSAGE_EXPIRED,
                    reply_text=None,
                ),
                **_FAST,
            )
            return MessageOutcome(message_id=request.message_id, outcome=MESSAGE_EXPIRED)

        reply = self._replies[0]
        await workflow.execute_activity(
            resolve_message_row,
            ResolveMessageInput(
                message_id=request.message_id,
                outcome=MESSAGE_ANSWERED,
                reply_text=reply,
            ),
            **_FAST,
        )
        return MessageOutcome(
            message_id=request.message_id, outcome=MESSAGE_ANSWERED, reply_text=reply
        )