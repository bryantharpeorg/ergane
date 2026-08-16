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

041-US1 splits this module along the seam it always had implicitly.
`TelegramAdapter` is the transport: it delivers an already-rendered message and
translates an inbound update into `(correlation id, reply text, sender
identity)`, and it can do nothing else. `CallbackBridge` is the factory side:
it looks the row up, decides, signals and settles. The four numbered decisions
above are the bridge's and stay exactly where they were — which is why the
existing operator-channel suite passes unmodified.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

from factory.notify.adapter import (
    UNKNOWN_SENDER,
    DeliveryReceipt,
    InboundRelay,
    MessengerAdapter,
    RenderedMessage,
    register_adapter,
    resolve_adapter,
)
from factory.notify.messages import (
    actions_keyboard,
    parse_callback_data,
    resolution_notice,
)
from factory.verify.models import EscalationChoice, EscalationRecord, QuestionRecord
from factory.verify.store import (
    ANSWERED,
    EXPIRED,
    connect,
    get_escalation,
    get_question,
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

#: Where messages are sent. Not a credential, but worker configuration all the
#: same: an escalation addressed by the dispatch could be redirected by anything
#: that could write one.
CHAT_ID_ENV = "TELEGRAM_CHAT_ID"

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

#: What an identity the configured list does not carry is told (041-US4). Named
#: back to them: the ordinary cause is a spelling, `bryan` for `@bryan`.
_UNAUTHORIZED = "{identity} is not an authorized responder; nothing was changed."


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
    #: 041-US4: the sender is not on `escalation.authorized_responders`. Its own
    #: value rather than a reused one — a reply that vanished into an existing
    #: outcome would be indistinguishable from one never delivered.
    UNAUTHORIZED = "UNAUTHORIZED"


# --- the transport (041-US1) -------------------------------------------------


def open_bot(token: str) -> Any:
    """The Telegram client a message goes out over — a seam, not a factory.

    Returned rather than constructed inline so a test can substitute a bot that
    never opens a socket while the caller still has to find a real token in its
    own environment to reach this call. `factory.activities.notify_activities`
    re-exports this name and hands it to the adapter, which is why patching it
    there still reaches every send.
    """
    from telegram import Bot

    return Bot(token)


class TelegramAdapter:
    """Telegram behind the seam: it delivers, and it translates. Nothing else.

    008's reference transport, moved behind `MessengerAdapter` with no change to
    a single byte an operator receives — the message text and the inline
    keyboard are still built by `factory/notify/messages.py`, and this only
    hands them to the Bot API.

    A plain library (041 FR-002): no Temporal import, no client, no workflow
    context, and no store. 042's supervision probe constructs one of these in a
    process with none of those and pages a human to say the orchestrator is
    down.

    What it deliberately cannot do is acknowledge, answer or expire (FR-001).
    There is nothing here to do it with: no connection, no workflow handle, and
    a `relay` that returns a value rather than acting on one. The toast that
    tells an operator their press was ignored is `CallbackBridge`'s, because
    *why* it was ignored is a fact about a row.
    """

    def __init__(self, *, open_bot: Callable[[str], Any] = open_bot) -> None:
        self._open_bot = open_bot

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        """Page the operator. `delivered=False` means they were not, for any reason.

        The reasons are deliberately not distinguished: an absent credential, an
        unreachable API and a refused message all leave the factory with the
        same move — apply the default now rather than wait out a deadline of
        silence that means nothing (R11).
        """
        token = os.environ.get(BOT_TOKEN_ENV)
        chat_id = os.environ.get(CHAT_ID_ENV)
        if not token or not chat_id:
            # Named, never valued: which variable is unset is the whole
            # diagnosis, and the token's value is exactly what may not be
            # written down.
            logger.warning(
                "%s: not sent — %s is not set on this worker",
                correlation_id,
                BOT_TOKEN_ENV if not token else CHAT_ID_ENV,
            )
            return DeliveryReceipt(delivered=False)

        try:
            async with self._open_bot(token) as bot:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=message.text,
                    reply_markup=actions_keyboard(message.actions),
                )
        except Exception as exc:
            # Broad on purpose: whatever went wrong between here and Telegram,
            # the safe move is identical. The exception's class is logged and
            # its message is not — an unauthorized Bot API error quotes the
            # token back at us, since the token is in the URL it failed on.
            logger.warning(
                "%s: not delivered (%s)", correlation_id, type(exc).__name__
            )
            return DeliveryReceipt(delivered=False)

        return DeliveryReceipt(
            delivered=True, message_id=getattr(sent, "message_id", None)
        )

    def relay(self, event: Any) -> InboundRelay | None:
        """Translate one Telegram update into the factory's three inbound terms.

        Pure translation. It reads no row, sends no notice, and returns a value
        instead of acting on one — `None` for anything that is not one of ours,
        which the factory then decides what to say about.

        The correlation id is the handle Telegram can actually carry back. A
        press carries the escalation id the factory minted into its
        `callback_data` (R11). A free-text reply cannot carry anything the
        factory minted, so it carries what Telegram minted — the message id of
        the question it quotes, which is the key the store captured at send
        time and routes by (008 FR-008).
        """
        query = getattr(event, "callback_query", None)
        if query is not None:
            press = parse_callback_data(getattr(query, "data", None))
            if press is None:
                return None
            return InboundRelay(
                correlation_id=press.escalation_id,
                reply_text=press.choice,
                sender_identity=_identity(getattr(query, "from_user", None)),
            )

        message = getattr(event, "message", None)
        if message is None:
            return None

        quoted = getattr(
            getattr(message, "reply_to_message", None), "message_id", None
        )
        text = getattr(message, "text", None)
        if quoted is None or not text:
            # A message quoting nothing is not an answer to anything, and a
            # sticker carries no text the next attempt could repeat verbatim.
            return None

        return InboundRelay(
            correlation_id=str(quoted),
            reply_text=text,
            sender_identity=_identity(getattr(message, "from_user", None)),
        )


def _identity(user: Any) -> str:
    """Who replied, in the spelling an authorized-responders list would carry.

    `@username` when Telegram has one, the numeric id otherwise, and
    `UNKNOWN_SENDER` when the update names no sender at all. Nothing here
    decides whether that identity may answer: US4's check is factory-side,
    because answer-or-not is a decision and the seam keeps decisions out of the
    transport (FR-001).
    """
    if user is None:
        return UNKNOWN_SENDER

    username = getattr(user, "username", None)
    if username:
        return f"@{username}"

    user_id = getattr(user, "id", None)
    return UNKNOWN_SENDER if user_id is None else str(user_id)


def _build_telegram(**seams: Any) -> TelegramAdapter:
    """Build the reference transport from whatever seams the caller owns.

    The only seam it recognises is `open_bot`: the send activity keeps its own
    patchable copy of that name so a test can stop a socket from opening while
    the credential still has to come out of the worker environment.
    """
    return TelegramAdapter(open_bot=seams.get("open_bot") or open_bot)


register_adapter("telegram", _build_telegram)


# --- the factory side --------------------------------------------------------


def configured_responders() -> tuple[str, ...]:
    """Who may answer, per the control-plane file. Empty means anyone (FR-011).

    The placement is the requirement, not a convenience. An adapter reading it
    would be deciding answer-or-not, the one decision the seam keeps out of the
    transport (FR-001). A workflow reading it would be reading a file from
    workflow scope, which constitution IV forbids and 039's guard fails — the
    same read wedged the roadmap schedule for eleven hours on 2026-08-13.

    Unrestricted with no control-plane file and with one this process cannot
    parse, the way `configured_adapter_name` falls back to the reference
    transport: refusing every reply over a malformed config would make the
    parser the thing that silences the channel.
    """
    try:
        from factory.controlplane.config import (
            ControlPlaneConfigError,
            load_controlplane_config,
        )
    except ImportError:  # pragma: no cover - the control plane is always shipped
        return ()

    try:
        return tuple(load_controlplane_config().escalation.authorized_responders)
    except (ControlPlaneConfigError, OSError) as exc:
        logger.debug("no configured responders (%s)", type(exc).__name__)
        return ()


class CallbackBridge:
    """Turns one inbound reply into at most one Temporal signal.

    `client` is anything with `get_workflow_handle(workflow_id)` — the real
    `temporalio.client.Client` in the service, a recorder in tests. `now` is
    injectable for the same reason the store takes `resolved_at` as an argument:
    the timestamp is evidence, and evidence has to be assertable. `adapter` is
    the transport whose updates this bridge translates; it defaults to the
    configured one, so a deployment that switched messengers switched this too.

    `authorized_responders` is the identity list an inbound reply must match to
    become an answer (041 FR-011), defaulting to the configured one for the same
    reason `adapter` does. Empty is unrestricted, which every 008 deployment is.
    """

    def __init__(
        self,
        *,
        db_path: str | Path,
        client: Any,
        now: Callable[[], str] | None = None,
        adapter: MessengerAdapter | None = None,
        authorized_responders: Sequence[str] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._client = client
        self._now = now or _now_iso
        self._adapter = adapter if adapter is not None else resolve_adapter()
        self._responders = (
            configured_responders()
            if authorized_responders is None
            else tuple(authorized_responders)
        )

    async def handle(self, update: Any) -> BridgeOutcome:
        """Resolve one button press. Never raises on operator-visible input.

        The press is read through the adapter (041-US1): which escalation it
        names and which choice it carries are the transport's to translate, and
        everything after that — the lookup, the offered-choice check, the
        signal, the guarded UPDATE and the toast — is this bridge's, unchanged.
        """
        query = getattr(update, "callback_query", None)
        if query is None:
            # Not a callback at all — nothing to answer, nothing to do.
            return BridgeOutcome.MALFORMED

        press = self._adapter.relay(update)
        if press is None:
            await query.answer(_ANSWER_NOT_OURS)
            return BridgeOutcome.MALFORMED

        # Before the lookup, and long before the signal: an unauthorized press
        # touches neither the row nor the clock (FR-011).
        refused = await self._refuse_unauthorized(press, query.answer)
        if refused is not None:
            return refused

        escalation_id = press.correlation_id
        pressed = press.reply_text
        conn = connect(self.db_path)
        try:
            record = get_escalation(conn, escalation_id)
            if record is None:
                await query.answer(_ANSWER_UNKNOWN)
                return BridgeOutcome.UNKNOWN

            offered = {EscalationChoice(choice).value for choice in record.choices}
            if pressed not in offered:
                # Forged, or a button from before the offer narrowed. Signalling
                # it would hand the workflow a decision it never asked for.
                await query.answer(_ANSWER_NOT_OFFERED)
                return BridgeOutcome.INVALID_CHOICE

            if record.resolution is not None:
                return await self._answer_settled(query, record.resolution)

            if not await self._signal(record, pressed):
                await query.answer(_ANSWER_SIGNAL_FAILED)
                return BridgeOutcome.SIGNAL_FAILED

            choice = EscalationChoice(pressed)
            if not resolve_escalation(
                conn, escalation_id, choice, resolved_at=self._now()
            ):
                # The read above went stale while the signal was in flight: the
                # hour expired, or another press won. The row's decision stands.
                settled = get_escalation(conn, escalation_id)
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

        # The two checks above pick which notice a rejected reply gets, which is
        # a fact about Telegram's update shapes; the routing key and the text
        # come from the adapter (041-US1).
        relay = self._adapter.relay(update)
        if relay is None:
            await message.reply_text(_REPLY_UNKNOWN)
            return BridgeOutcome.UNKNOWN

        return await self._settle_question(relay, message.reply_text)

    async def handle_relay(self, relay: InboundRelay) -> BridgeOutcome:
        """Settle one inbound relay, whatever transport produced it (041-US1).

        The transport-neutral half of `handle_reply`: the same lookup, the same
        signal-before-resolve ordering, and the same guarded UPDATE, with no
        notice sent back — a relay is three terms, not a chat message, and a
        transport with somewhere to reply says so itself.

        The relay's correlation id is resolved as the message handle the
        transport carried back, which is what Telegram can do and therefore
        what US1 builds. US4 adds the case where the transport carries the
        factory's own id, because a webhook can.
        """
        return await self._settle_question(relay, _no_notice)

    async def _settle_question(
        self,
        relay: InboundRelay,
        notify: Callable[[str], Awaitable[None]],
    ) -> BridgeOutcome:
        """One answer, from parse to settled row — the part no transport owns."""
        refused = await self._refuse_unauthorized(relay, notify)
        if refused is not None:
            return refused

        conn = connect(self.db_path)
        try:
            record = self._question_for(conn, relay.correlation_id)
            if record is None:
                # A reply to a human, or to a message from another deployment —
                # not ours. Answered with a notice, never a crashed poll loop.
                await notify(_REPLY_UNKNOWN)
                return BridgeOutcome.UNKNOWN

            if record.resolution is not None:
                # A double reply, a redelivery, or a late answer. The first
                # resolution stands and the workflow hears about it exactly
                # once. Answered-as-settled, the way a second press is.
                return await self._reply_settled(notify, record.resolution)

            if not await self._answer_signal(record, relay.reply_text):
                await notify(_REPLY_SIGNAL_FAILED)
                return BridgeOutcome.SIGNAL_FAILED

            if not resolve_question(
                conn,
                record.question_id,
                answer_text=relay.reply_text,
                resolved_at=self._now(),
            ):
                # The read above went stale while the signal was in flight: the
                # question expired, or another reply won. The row's decision
                # stands.
                settled = self._question_for(conn, relay.correlation_id)
                return await self._reply_settled(
                    notify, settled.resolution if settled else None
                )

            await notify(_REPLY_RESOLVED)
            return BridgeOutcome.RESOLVED
        finally:
            conn.close()

    async def _refuse_unauthorized(
        self,
        relay: InboundRelay,
        notify: Callable[..., Awaitable[Any]],
    ) -> BridgeOutcome | None:
        """`None` when this sender may answer; the refusal when they may not.

        Applied to every adapter's relay rather than per adapter (FR-011): the
        seam reports *who* replied and never judges it, so the one place that
        judges is here. Called at both inbound entries — a press and a reply —
        because they do not share a settling core, and a guard proven at one is
        proven at one.

        The refusal is **recorded**, at WARNING, with the identity and the
        correlation id (US4-S2): a reply dropped silently is indistinguishable
        from one never delivered. Nothing is written to the store — the scenario
        says state and the expiry clock are untouched, and a row is state. This
        consults the configured list and nothing else, so an earlier refusal
        never counts against a later reply (US4-S3).
        """
        if not self._responders or relay.sender_identity in self._responders:
            return None

        logger.warning(
            "%s: reply from %s ignored — not in escalation.authorized_responders",
            relay.correlation_id,
            relay.sender_identity,
        )
        await notify(_UNAUTHORIZED.format(identity=relay.sender_identity))
        return BridgeOutcome.UNAUTHORIZED

    @staticmethod
    def _question_for(conn: Any, correlation_id: str) -> QuestionRecord | None:
        """The question a relay threads to, by the handle the transport carried.

        Two handles, because two transports carry different things back and the
        seam's promise is that the factory resolves whatever they managed.
        Telegram's is the quoted message id, the key the store captured at send
        time (008 FR-008). A webhook mints none, so its relay carries the
        factory's own question id — what went out in the delivery body and what
        an operator types at `ergane answer` (041-US4).

        The message id is tried first, so Telegram's landed routing is unchanged
        by a fallback it never reaches. A correlation id that is neither names
        no question, and saying so is the caller's job.
        """
        try:
            message_id = int(correlation_id)
        except (TypeError, ValueError):
            message_id = None

        if message_id is not None:
            threaded = get_question_by_message_id(conn, message_id)
            if threaded is not None:
                return threaded

        return get_question(conn, correlation_id)

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
        self,
        notify: Callable[[str], Awaitable[None]],
        resolution: str | None,
    ) -> BridgeOutcome:
        """Answer a reply to a question that is already terminal.

        The question is resolved or expired, so a reply that arrives now is a
        double reply, a redelivery, or a late answer — all ordinary, none of
        them errors. The row's decision stands and the workflow hears nothing.
        """
        if resolution is None:
            await notify(_REPLY_UNKNOWN)
            return BridgeOutcome.UNKNOWN

        if resolution == EXPIRED:
            await notify(_REPLY_EXPIRED)
            return BridgeOutcome.EXPIRED

        await notify(_REPLY_ALREADY)
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


async def _no_notice(text: str) -> None:
    """Say nothing back. A relay is three terms and has nobody to toast at.

    The transport-neutral inbound path (`handle_relay`) reports its outcome to
    its caller instead — `ergane answer` prints it, and a webhook bridge has
    already returned to whoever POSTed.
    """
    return None


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
