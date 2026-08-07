"""The bridge from a button press back to the workflow that is waiting on it.

`python -m factory.notify.service` runs one long-polling process per deployment.
It owns no state of its own (R11): every fact it needs is in the escalation row,
so a bridge restarted mid-hour answers a press exactly as the process that sent
the message would have, and running two by accident cannot resolve one
escalation twice — the store's guarded UPDATE decides that, not this code.

The order of operations in `handle` is the whole design:

1. **Parse, then look up, then validate the choice.** Shape is all
   `parse_callback_data` knows; whether `PAUSE_EPIC` was ever *offered* is a fact
   about the row. Anything that fails here is answered with a notice and dropped
   — never raised, because one bad payload must not stop the poll loop that every
   other escalation depends on.
2. **Signal before resolving.** A row marked resolved before the signal is sent
   is a workflow that waits out the full hour on a decision the store already
   considers made. Signal first and the worst case is a press that has to be
   repeated.
3. **A signal that never landed leaves the row pending.** If Temporal is
   unreachable, recording the press anyway would strand the workflow for the hour
   and then kill it — the same outcome as never pressing, except the operator was
   told it worked. Pending means they can press again, and if nobody does, the
   workflow's own timer applies the fail-safe kill (R12).
4. **The guarded UPDATE is the authority on who won.** The state read in step 1
   can go stale while the signal is in flight; `resolve_escalation` returning
   False is how this process learns that the hour expired, or that a double tap
   got there first. The answer is then re-derived from the row rather than from
   what was read before.

The bridge deliberately does not own the clock. A row past `expires_at` but still
pending is honored, because the workflow's timer is the authority on expiry — a
bridge with a skewed clock second-guessing that would silently drop presses the
workflow is still waiting for.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from factory.notify.messages import parse_callback_data, resolution_notice
from factory.verify.models import EscalationChoice, EscalationRecord, QuestionRecord
from factory.verify.store import (
    ANSWERED,
    EXPIRED,
    connect,
    get_escalation,
    get_question_by_message_id,
    resolve_escalation,
    resolve_question,
)

logger = logging.getLogger(__name__)

#: The signal the reference flow waits on (contracts/verification-flow.md), sent
#: as `escalation_resolved(escalation_id, choice)` — the id travels with it so a
#: workflow that escalated twice can tell which answer arrived.
SIGNAL_NAME = "escalation_resolved"

#: The sibling signal a free-text reply sends (008-US2), sent as
#: `question_answered(question_id, answer_text)`. The escalation signal cannot
#: carry free text (the escalations CHECK constraints pin the choice enum), which
#: is the whole reason a sibling signal exists (plan § US2): the answer threads
#: back to the question by the Telegram message id the send returned (FR-008), and
#: the workflow un-parks the node and carries the text into the next attempt's
#: prompt verbatim (FR-003).
QUESTION_SIGNAL_NAME = "question_answered"

#: Read inside this process only, never placed in a payload or a log line — the
#: master-key discipline of 001 FR-009, extended to the bot token.
BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"

TEMPORAL_ADDRESS_ENV = "TEMPORAL_ADDRESS"
TEMPORAL_NAMESPACE_ENV = "TEMPORAL_NAMESPACE"

DEFAULT_TEMPORAL_ADDRESS = "localhost:7233"

#: The namespace the factory's workflows run in (plan.md, Target Platform).
DEFAULT_TEMPORAL_NAMESPACE = "factory"

#: Callback answers are toasts, capped by the Bot API at 200 characters — these
#: exist so an ignored press always says *why* it was ignored.
_ANSWER_NOT_OURS = "That button is not one of this factory's escalations."
_ANSWER_UNKNOWN = "This escalation is no longer on record; nothing was changed."
_ANSWER_NOT_OFFERED = "That choice was not offered for this escalation."
_ANSWER_EXPIRED = "The hour ran out — the node was killed by default."
_ANSWER_ALREADY = "Already resolved as {resolution}; nothing was changed."
_ANSWER_SIGNAL_FAILED = "Could not reach the orchestrator — nothing recorded, press again."
_ANSWER_RESOLVED = "{choice} recorded."

#: Reply answers are toasts sent as replies to the operator's message, capped by
#: the Bot API at 200 characters — these exist so an ignored reply always says
#: *why* it was ignored, the way a callback's `query.answer` does.
_REPLY_NOT_A_REPLY = "That message is not a reply; nothing to answer."
_REPLY_UNKNOWN = "That reply is not to one of this factory's questions; nothing changed."
_REPLY_ALREADY = "That question is already answered; nothing changed."
_REPLY_EXPIRED = "The question's window ran out — the node was un-parked as a FAIL."
_REPLY_EMPTY = "An empty reply carries no answer; nothing recorded."
_REPLY_SIGNAL_FAILED = "Could not reach the orchestrator — nothing recorded, reply again."
_REPLY_RESOLVED = "Answer recorded; the next attempt will carry it."


class BridgeOutcome(str, Enum):
    """What one press did — the return value of `handle`, and what tests assert.

    Every value except RESOLVED means no signal was sent. They are distinct
    because they are distinct *operator* situations: a press that lost a race
    needs a different answer from a press on a choice nobody offered.
    """

    RESOLVED = "RESOLVED"
    MALFORMED = "MALFORMED"
    UNKNOWN = "UNKNOWN"
    INVALID_CHOICE = "INVALID_CHOICE"
    EXPIRED = "EXPIRED"
    ALREADY_RESOLVED = "ALREADY_RESOLVED"
    SIGNAL_FAILED = "SIGNAL_FAILED"


class CallbackBridge:
    """Turns one Telegram callback query into at most one Temporal signal.

    `client` is anything with `get_workflow_handle(workflow_id)` — the real
    `temporalio.client.Client` in the service, a recorder in tests. `now` is
    injectable for the same reason the store takes `resolved_at` as an argument:
    the timestamp is evidence, and evidence has to be assertable.
    """

    def __init__(
        self,
        *,
        db_path: str | Path,
        client: Any,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._client = client
        self._now = now or _now_iso

    async def handle(self, update: Any) -> BridgeOutcome:
        """Resolve one button press. Never raises on operator-visible input."""
        query = getattr(update, "callback_query", None)
        if query is None:
            # Not a callback at all — nothing to answer, nothing to do.
            return BridgeOutcome.MALFORMED

        press = parse_callback_data(getattr(query, "data", None))
        if press is None:
            await query.answer(_ANSWER_NOT_OURS)
            return BridgeOutcome.MALFORMED

        conn = connect(self.db_path)
        try:
            record = get_escalation(conn, press.escalation_id)
            if record is None:
                await query.answer(_ANSWER_UNKNOWN)
                return BridgeOutcome.UNKNOWN

            offered = {EscalationChoice(choice).value for choice in record.choices}
            if press.choice not in offered:
                # Forged, or a button from before the offer narrowed. Signalling
                # it would hand the workflow a decision it never asked for.
                await query.answer(_ANSWER_NOT_OFFERED)
                return BridgeOutcome.INVALID_CHOICE

            if record.resolution is not None:
                return await self._answer_settled(query, record.resolution)

            if not await self._signal(record, press.choice):
                await query.answer(_ANSWER_SIGNAL_FAILED)
                return BridgeOutcome.SIGNAL_FAILED

            choice = EscalationChoice(press.choice)
            if not resolve_escalation(
                conn, press.escalation_id, choice, resolved_at=self._now()
            ):
                # The read above went stale while the signal was in flight: the
                # hour expired, or another press won. The row's decision stands.
                settled = get_escalation(conn, press.escalation_id)
                return await self._answer_settled(
                    query, settled.resolution if settled else None
                )

            await query.answer(_ANSWER_RESOLVED.format(choice=choice.value))
            await query.edit_message_text(
                resolution_notice(record, choice), reply_markup=None
            )
            return BridgeOutcome.RESOLVED
        finally:
            conn.close()

    async def handle_reply(self, update: Any) -> BridgeOutcome:
        """Resolve one free-text reply into at most one Temporal signal (008-US2).

        The mirror of `handle` for the one thing a button cannot carry: the
        operator's answer to a question. The order of operations is the same
        design — parse, look up, signal before resolving, guarded UPDATE
        decides — with two deltas that make a reply a reply:

        1. **Route by the quoted message id, never by recency (FR-008).** A reply
           threads to the question whose `message_id` matches the reply's
           `reply_to_message.message_id` — the id the send returned and the store
           captured. A reply that quotes no message, or quotes one the factory
           never sent, is answered with a notice and dropped, never raised.
        2. **The answer text travels verbatim in the signal (FR-003).** The
           escalation signal carries a choice from a closed enum; this one
           carries free text, which is the whole reason a sibling signal and a
           sibling `questions` table exist (plan § Technical Context).

        Never raises on operator-visible input: one bad reply must not stop the
        poll loop that every open question depends on.
        """
        message = getattr(update, "message", None)
        if message is None:
            # Not a message update at all — nothing to answer, nothing to do.
            return BridgeOutcome.MALFORMED

        reply_to = getattr(message, "reply_to_message", None)
        if reply_to is None:
            # A plain chat message quotes nothing — there is no thread to route
            # by, so it is not an answer to anything (FR-008).
            await message.reply_text(_REPLY_NOT_A_REPLY)
            return BridgeOutcome.MALFORMED

        answer = getattr(message, "text", None)
        if not answer:
            # A sticker or a media attachment carries no text the next attempt
            # could carry verbatim (FR-003). Ignored rather than recorded as an
            # empty answer, which would park the node on nothing.
            await message.reply_text(_REPLY_EMPTY)
            return BridgeOutcome.MALFORMED

        quoted_id = getattr(reply_to, "message_id", None)
        conn = connect(self.db_path)
        try:
            record = (
                None
                if quoted_id is None
                else get_question_by_message_id(conn, quoted_id)
            )
            if record is None:
                # A reply to a human, or to a message from another deployment —
                # not ours. Answered with a notice, never a crashed poll loop.
                await message.reply_text(_REPLY_UNKNOWN)
                return BridgeOutcome.UNKNOWN

            if record.resolution is not None:
                # A double reply, a redelivery, or a late answer. The first
                # resolution stands and the workflow hears about it exactly
                # once. Answered-as-settled, the way a second press is.
                return await self._reply_settled(message, record.resolution)

            if not await self._answer_signal(record, answer):
                await message.reply_text(_REPLY_SIGNAL_FAILED)
                return BridgeOutcome.SIGNAL_FAILED

            if not resolve_question(
                conn, record.question_id, answer_text=answer, resolved_at=self._now()
            ):
                # The read above went stale while the signal was in flight: the
                # question expired, or another reply won. The row's decision
                # stands.
                settled = get_question_by_message_id(conn, quoted_id)
                return await self._reply_settled(
                    message, settled.resolution if settled else None
                )

            await message.reply_text(_REPLY_RESOLVED)
            return BridgeOutcome.RESOLVED
        finally:
            conn.close()

    async def _answer_signal(self, record: QuestionRecord, answer: str) -> bool:
        """Tell the workflow. False means it was not told, and nothing is recorded."""
        try:
            handle = self._client.get_workflow_handle(record.workflow_id)
            await handle.signal(
                QUESTION_SIGNAL_NAME, args=[record.question_id, answer]
            )
        except Exception:
            # Broad on purpose: whatever went wrong between here and Temporal,
            # the safe move is identical — leave the row pending and say so.
            logger.exception(
                "question %s: signalling %s failed; row left pending",
                record.question_id,
                record.workflow_id,
            )
            return False
        return True

    async def _reply_settled(
        self, message: Any, resolution: str | None
    ) -> BridgeOutcome:
        """Answer a reply to a question that is already terminal.

        The question is resolved or expired, so a reply that arrives now is a
        double reply, a redelivery, or a late answer — all ordinary, none of
        them errors. The row's decision stands and the workflow hears nothing.
        """
        if resolution is None:
            await message.reply_text(_REPLY_UNKNOWN)
            return BridgeOutcome.UNKNOWN

        if resolution == EXPIRED:
            await message.reply_text(_REPLY_EXPIRED)
            return BridgeOutcome.EXPIRED

        await message.reply_text(_REPLY_ALREADY)
        return BridgeOutcome.ALREADY_RESOLVED

    async def _signal(self, record: EscalationRecord, choice: str) -> bool:
        """Tell the workflow. False means it was not told, and nothing is recorded."""
        try:
            handle = self._client.get_workflow_handle(record.workflow_id)
            await handle.signal(SIGNAL_NAME, args=[record.escalation_id, choice])
        except Exception:
            # Broad on purpose: whatever went wrong between here and Temporal,
            # the safe move is identical — leave the row pending and say so.
            logger.exception(
                "escalation %s: signalling %s failed; row left pending",
                record.escalation_id,
                record.workflow_id,
            )
            return False
        return True

    async def _answer_settled(
        self, query: Any, resolution: EscalationChoice | str | None
    ) -> BridgeOutcome:
        """Answer a press on an escalation that is already terminal.

        The buttons were removed when it was resolved, so arriving here means a
        redelivered callback, a double tap, or a stale message — all ordinary,
        none of them errors.
        """
        if resolution is None:
            await query.answer(_ANSWER_UNKNOWN)
            return BridgeOutcome.UNKNOWN

        value = resolution.value if isinstance(resolution, Enum) else str(resolution)
        if value == EXPIRED:
            await query.answer(_ANSWER_EXPIRED)
            return BridgeOutcome.EXPIRED

        await query.answer(_ANSWER_ALREADY.format(resolution=value))
        return BridgeOutcome.ALREADY_RESOLVED


def _now_iso() -> str:
    """ISO 8601 UTC, to the second — the evidence timestamp format (001 FR-012)."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


# --- the runnable service ---------------------------------------------------


async def run_bridge(bridge: CallbackBridge, token: str) -> None:
    """Long-poll until cancelled, handing every press and reply to `bridge`.

    Two handlers share one poll loop: `CallbackQueryHandler` turns a button press
    into an escalation resolution, and `MessageHandler` turns a free-text reply
    into a question answer (008-US2, FR-008). The reply handler is registered with
    `filters.REPLY` so it fires only on messages that quote another — a plain chat
    message is not an answer to anything and never reaches `handle_reply`.

    Built with the async context-manager form rather than `run_polling()` so the
    Temporal client and the Telegram updater share one event loop — a client
    created on a loop the bot then replaces is a client whose calls never return.
    """
    from telegram.ext import Application, CallbackQueryHandler, MessageHandler
    from telegram.ext import filters

    async def on_callback(update: Any, _context: Any) -> None:
        await bridge.handle(update)

    async def on_reply(update: Any, _context: Any) -> None:
        await bridge.handle_reply(update)

    application = Application.builder().token(token).build()
    application.add_handler(CallbackQueryHandler(on_callback))
    # Only replies — a message that quotes another is the one shape that can
    # thread back to a question's message id (FR-008). A non-reply chat message
    # never reaches `handle_reply`, so the bridge does not see the chat's noise.
    application.add_handler(MessageHandler(filters.REPLY, on_reply))

    async with application:
        await application.start()
        await application.updater.start_polling()
        logger.info("escalation bridge polling; store at %s", bridge.db_path)
        try:
            await asyncio.Event().wait()
        finally:
            await application.updater.stop()
            await application.stop()


async def main() -> None:
    """Wire the store, a Temporal client and the bot together, then poll."""
    from temporalio.client import Client

    from factory.activities.verify_activities import (
        DEFAULT_VERIFICATION_DB_PATH,
        VERIFICATION_DB_PATH_ENV,
    )

    token = os.environ.get(BOT_TOKEN_ENV)
    if not token:
        raise SystemExit(f"{BOT_TOKEN_ENV} is not set; the bridge cannot poll Telegram")

    client = await Client.connect(
        os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS,
        namespace=os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE,
    )
    db_path = os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH

    await run_bridge(CallbackBridge(db_path=db_path, client=client), token)


if __name__ == "__main__":  # pragma: no cover - process entry point
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
