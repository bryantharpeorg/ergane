"""The two calls that page a human, and what they promise when nobody answers.

`factory/notify/` renders an escalation and turns a button press back into a
signal; this module is the other half — what the workflow calls when the ladder
has run out of ideas (`send_escalation`) and when the hour has run out
(`expire_escalation`). Between them they are the only place the bot token is
read, and it is read from the worker environment inside the activity, never from
an input (FR-009, the discipline 001 established for the master key).

Three decisions carry the weight:

- **The row is written before the message goes out (R11).** Every other ordering
  can lose an escalation: a message that exists before its row is a button
  pointing at nothing — answered by a bridge that has never heard of it, waited
  on by a workflow nothing will ever signal, and invisible to the timeout path
  that would otherwise expire it. Insert first and the worst case is a recorded
  escalation nobody was told about, which is exactly what `delivered=False`
  reports.
- **A notifier that is down is data, not an error.** No token, no chat id, a
  refused connection, an API that says no: all of them return
  `delivered=False` with the row retained, because the workflow's response is to
  apply the fail-safe default (KILL) immediately rather than wait out an hour for
  a message nobody received. Raising would instead hand the escalation to
  Temporal's retry policy and stall the node on the notifier's availability — the
  one dependency the send path was designed not to have. A store it cannot write
  is the one real error: `delivered=False` is survivable because the row is still
  expirable, and a missing row is not recoverable by anything downstream.
- **Expiry reports a transition rather than asserting one.** The operator's
  button press and the workflow's hour race by design (R12), and the timeout path
  cannot know it lost until it asks. `expire_escalation` returns whatever the
  store's guarded UPDATE settled on — `EXPIRED` when it was still pending, the
  operator's choice when a press got there first, `None` for an id the store has
  never heard of — and never raises on the ordinary cases, because a workflow
  blocked on this call is a workflow that cannot apply its own default.

`open_bot` is a seam in the same sense as component 1's `open_client` and the
judge's `judge_transport`: tests replace it to keep a socket from opening, and
the token still has to come out of the environment for the activity to get that
far.
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.activities.verify_activities import (
    DEFAULT_VERIFICATION_DB_PATH,
    VERIFICATION_DB_PATH_ENV,
)
from factory.notify.messages import escalation_keyboard, escalation_message, question_message
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord, QuestionRecord

logger = logging.getLogger(__name__)

#: Read inside these activities only, and never placed in an input, a result, a
#: row or a log line. The bridge service names the same variable
#: (`factory.notify.service.BOT_TOKEN_ENV`) for the same process-local reason.
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"

#: Where escalations are sent. Not a credential, but worker configuration all the
#: same: an escalation addressed by the dispatch could be redirected by anything
#: that could write one.
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"

#: The activity error type for an escalation that could not be recorded. Unlike a
#: failed send, this one raises: an unwritten row cannot be expired, resolved or
#: found again, so nothing downstream could recover from it.
ESCALATION_NOT_RECORDED = "ESCALATION_NOT_RECORDED"

#: How long an operator has before silence becomes a kill (data-model.md,
#: `VerificationConfig.escalation_timeout_s`). The row advertises the deadline the
#: workflow's own timer is holding, so both answer the same question the same way.
ESCALATION_TIMEOUT_S = 3600

#: What the ladder offers when the dispatch does not narrow it (FR-008).
DEFAULT_CHOICES = (
    EscalationChoice.RETRY,
    EscalationChoice.KILL,
    EscalationChoice.PAUSE_EPIC,
)

#: The activity error type for a question that could not be recorded (008-US1).
#: The mirror of `ESCALATION_NOT_RECORDED`: an unwritten row cannot be expired,
#: resolved or found again, so it raises before a message exists in a chat.
QUESTION_NOT_RECORDED = "QUESTION_NOT_RECORDED"

#: How long an operator has to answer a question before silence reclassifies it
#: as a burn (FR-004). The question's own window, not the escalation hour: a
#: question asked into an operator's sleep is cheaper parked till morning than
#: burned at 3 AM (decided 2026-08-07). The row advertises the deadline the
#: workflow's timer (US2) holds.
QUESTION_TIMEOUT_S = 28800


def open_bot(token: str) -> Any:
    """The Telegram client the escalation goes out over — a seam, not a factory.

    Returned rather than constructed inline so a test can substitute a bot that
    never opens a socket while the activity still has to find a real token in the
    worker environment to reach this call.
    """
    from telegram import Bot

    return Bot(token)


@dataclass(frozen=True)
class SendEscalationInput:
    """One escalation, in the terms an operator will read it in.

    There is deliberately no field for a token or a chat id: a credential in an
    activity input is a credential in the workflow's history forever (FR-009).
    `history_summary` is the full failure history the ladder assembled (SC-005) —
    the store keeps it whole and only the message is ever clipped.
    """

    workflow_id: str
    epic_id: str
    node_id: str
    history_summary: str
    choices: list[EscalationChoice] = field(default_factory=lambda: list(DEFAULT_CHOICES))
    timeout_s: int = ESCALATION_TIMEOUT_S


@dataclass(frozen=True)
class SentEscalation:
    """What the workflow needs to decide how to wait.

    `delivered=False` means nobody was paged, and the caller applies the fail-safe
    default without waiting (R11). `expires_at` is the row's deadline, so the
    workflow's timer and the evidence agree on when the hour is up.
    """

    escalation_id: str
    delivered: bool
    expires_at: str


@dataclass(frozen=True)
class ExpireEscalationInput:
    escalation_id: str


@dataclass(frozen=True)
class ExpiredEscalation:
    """What the escalation settled on — or `None` when there is nothing to report.

    `None` covers an id the store has never heard of (a store rebuilt under a
    running epic, a row lost with the disk). The workflow applies its default
    either way; there is simply no recorded state to hand back.
    """

    final_state: str | None


# --- operator questions (008-US1) -------------------------------------------


@dataclass(frozen=True)
class SendQuestionInput:
    """One question, in the terms an operator will read it in (FR-002).

    The mirror of `SendEscalationInput` with the deltas that make a question a
    question: there is no `choices` field (the operator types a reply rather than
    pressing a button), and `attempt` travels because a question is attributed to
    one attempt the way a teardown's ledger row is. There is deliberately no
    field for a token or a chat id: a credential in an activity input is a
    credential in the workflow's history forever (FR-007, the discipline 001
    established for the master key). `question_text` is the marker body the
    detector extracted, shipped verbatim.
    """

    workflow_id: str
    epic_id: str
    node_id: str
    attempt: int
    question_text: str
    timeout_s: int = QUESTION_TIMEOUT_S


@dataclass(frozen=True)
class SentQuestion:
    """What the workflow needs to know the question is on its way (FR-002).

    `message_id` is the Telegram message id the bot returned — the reply-routing
    key a free-text answer threads back to (FR-008, US2) — and is ``None`` when no
    message was sent (the notifier is down, unconfigured, or refused the send),
    the way `delivered=False` works for an escalation. `question_id` keys the row
    either way: the row is written before the send (R11), so a crash in between
    leaves something the expiry path (US2) can still close.
    """

    question_id: str
    message_id: int | None
    sent_at: str
    expires_at: str


@dataclass(frozen=True)
class ExpireQuestionInput:
    question_id: str


@dataclass(frozen=True)
class ExpiredQuestion:
    """What the question settled on — `ANSWERED`/`EXPIRED`, or `None` for an
    unknown id (the escalation precedent: the workflow applies its default either
    way, and there is no recorded state to hand back). US2 owns the call.
    """

    final_state: str | None


@activity.defn
async def send_escalation(request: SendEscalationInput) -> SentEscalation:
    """Record an escalation, then page the operator about it (R11).

    The row is inserted first and committed before the message is built, so a
    crash — or a notifier that is simply down — leaves something the timeout path
    can still expire. Delivery failures are reported, not raised: `delivered=False`
    is the signal that the workflow should stop waiting and apply the default.

    Raises `ESCALATION_NOT_RECORDED` when the store refuses the row, before any
    message exists. Retryable: nothing was written, so a retry mints a fresh id
    rather than duplicating an escalation.
    """
    record = _pending_record(request)

    with closing(_connect()) as conn:
        _insert(conn, record)

        delivered = await _send(record)
        if delivered:
            # Best effort, and after the fact by construction: the message is
            # already out, and a row that understates delivery costs a reader one
            # misleading column, where raising here would re-send the message on
            # the next attempt.
            _mark_delivered(conn, record.escalation_id)

    return SentEscalation(
        escalation_id=record.escalation_id,
        delivered=delivered,
        expires_at=record.expires_at,
    )


@activity.defn
async def expire_escalation(request: ExpireEscalationInput) -> ExpiredEscalation:
    """Close out the hour, and report what the escalation actually settled on.

    Marks the row `EXPIRED` iff it is still pending; a press that won the race
    (R12) keeps its resolution and is handed back instead, so the workflow learns
    the operator's answer rather than killing a node they asked to retry. Safe to
    run twice — the store's guarded UPDATE allows exactly one terminal
    transition, so a redelivered activity re-reads rather than re-stamps.

    Never raises on an unknown id, or on a store it cannot read: the caller's
    fail-safe kill must not be blocked by the same failure that lost the row.
    """
    try:
        with closing(store.connect(_store_path())) as conn:
            if store.expire_escalation(
                conn, request.escalation_id, resolved_at=_now_iso()
            ):
                return ExpiredEscalation(final_state=store.EXPIRED)

            # The guard matched nothing: either an operator already answered, or
            # there is no such row. Only the row itself can say which.
            record = store.get_escalation(conn, request.escalation_id)
    except (sqlite3.Error, OSError):
        logger.warning(
            "escalation %s: store unreadable; reporting no recorded resolution",
            request.escalation_id,
        )
        return ExpiredEscalation(final_state=None)

    if record is None or record.resolution is None:
        return ExpiredEscalation(final_state=None)
    return ExpiredEscalation(final_state=_value(record.resolution))


# --- the row ----------------------------------------------------------------


def _pending_record(request: SendEscalationInput) -> EscalationRecord:
    """The escalation as it is written down: a fresh id and one hour of patience.

    Both timestamps come off one instant so the deadline the row advertises is
    exactly `timeout_s` after the moment it was sent — the workflow's timer runs
    against the same span, and a row that disagreed would have the bridge and the
    workflow answering differently about whether a press was still in time.
    """
    sent = datetime.now(timezone.utc).replace(microsecond=0)

    return EscalationRecord(
        # 12 hex digits: the whole reason `callback_data` fits in 64 bytes
        # without ever carrying a workflow id (R11).
        escalation_id=secrets.token_hex(6),
        workflow_id=request.workflow_id,
        epic_id=request.epic_id,
        node_id=request.node_id,
        choices=[EscalationChoice(choice) for choice in request.choices],
        history_summary=request.history_summary,
        sent_at=_iso(sent),
        expires_at=_iso(sent + timedelta(seconds=request.timeout_s)),
        delivered=False,
    )


def _connect() -> sqlite3.Connection:
    """Open the evidence store, or fail before an untracked message exists."""
    try:
        return store.connect(_store_path())
    except (sqlite3.Error, OSError) as exc:
        raise ApplicationError(
            f"cannot open the verification store at {_store_path()}: {exc}",
            type=ESCALATION_NOT_RECORDED,
        ) from exc


def _insert(conn: sqlite3.Connection, record: EscalationRecord) -> None:
    """Write the pending row — the first half of the ordering R11 turns on."""
    try:
        store.insert_escalation(conn, record)
    except sqlite3.Error as exc:
        raise ApplicationError(
            f"could not record the escalation for node {record.node_id!r} "
            f"in epic {record.epic_id!r}: {exc}",
            type=ESCALATION_NOT_RECORDED,
        ) from exc


def _mark_delivered(conn: sqlite3.Connection, escalation_id: str) -> None:
    try:
        store.mark_delivered(conn, escalation_id)
    except sqlite3.Error:
        logger.warning(
            "escalation %s: sent, but the store could not be updated to say so",
            escalation_id,
        )


# --- the message ------------------------------------------------------------


async def _send(record: EscalationRecord) -> bool:
    """Page the operator. False means they were not paged, for any reason at all.

    The reasons are deliberately not distinguished in the return value: an absent
    token, an unreachable API and a refused message all leave the workflow with
    the same move — apply the default now rather than wait out an hour of silence
    that means nothing.
    """
    token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)
    chat_id = os.environ.get(TELEGRAM_CHAT_ID_ENV)
    if not token or not chat_id:
        # Named, never valued: which variable is unset is the whole diagnosis,
        # and the token's value is exactly what may not be written down.
        logger.warning(
            "escalation %s: not sent — %s is not set on this worker",
            record.escalation_id,
            TELEGRAM_BOT_TOKEN_ENV if not token else TELEGRAM_CHAT_ID_ENV,
        )
        return False

    try:
        async with open_bot(token) as bot:
            await bot.send_message(
                chat_id=chat_id,
                text=escalation_message(record),
                reply_markup=escalation_keyboard(record),
            )
    except Exception as exc:
        # Broad on purpose: whatever went wrong between here and Telegram, the
        # safe move is identical. The exception's class is logged and its message
        # is not — an unauthorized Bot API error quotes the token back at us,
        # since the token is in the URL it failed on.
        logger.warning(
            "escalation %s: not delivered (%s)",
            record.escalation_id,
            type(exc).__name__,
        )
        return False

    return True


# --- small conversions ------------------------------------------------------


def _store_path() -> Path:
    """The same `.factory/verification.db` the verification activities record to.

    Escalations are evidence about a node, and an operator reading one epic opens
    one database (quickstart §5).
    """
    return Path(
        os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH
    )


def _iso(moment: datetime) -> str:
    """ISO 8601 UTC to the second — the factory's one timestamp spelling (001)."""
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _now_iso() -> str:
    return _iso(datetime.now(timezone.utc))


def _value(item: EscalationChoice | str) -> str:
    """The wire spelling of a resolution: a choice's value, or `EXPIRED` itself."""
    return item.value if isinstance(item, Enum) else str(item)


# --- operator questions (008-US1) -------------------------------------------


@activity.defn
async def send_question(request: SendQuestionInput) -> SentQuestion:
    """Record a question, then page the operator about it (008-US1, R11).

    The mirror of `send_escalation` with the two deltas that make a question a
    question: the message carries no keyboard (the operator types a reply), and
    the Telegram message id the bot returns is captured into the sibling
    `questions` table so a free-text answer can thread back to it (FR-008). The
    row is inserted first and committed before the message is built — the same
    ordering R11 turns on — so a crash in between leaves something the expiry
    path (US2) can still close.

    Raises `QUESTION_NOT_RECORDED` when the store refuses the row, before any
    message exists. A send that fails (no token, no chat id, a refused connection)
    is data, not an error: `message_id=None` is the signal that the workflow
    should proceed with no reply-routing key, the way `delivered=False` is the
    signal an escalation applies the fail-safe default immediately.
    """
    record = _pending_question(request)

    with closing(_connect_question()) as conn:
        _insert_question(conn, record)

        message_id = await _send_question(record)
        if message_id is not None:
            # Best effort, and after the fact by construction: the message is
            # already out, and a row missing its message id costs a reply its
            # routing key, where raising here would re-send on the next attempt.
            _capture_message_id(conn, record.question_id, message_id)

    return SentQuestion(
        question_id=record.question_id,
        message_id=message_id,
        sent_at=record.sent_at,
        expires_at=record.expires_at,
    )


@activity.defn
async def expire_question(request: ExpireQuestionInput) -> ExpiredQuestion:
    """Close out the question's window, and report what it settled on (US2's call).

    The mirror of `expire_escalation`: marks the row `EXPIRED` iff it is still
    pending, hands back `ANSWERED` if an operator already replied (the race the
    guarded UPDATE settles), and `None` for an id the store has no record of.
    Never raises on an unknown id or an unreadable store: the caller's default
    must not be blocked by the same failure that lost the row.
    """
    try:
        with closing(store.connect(_store_path())) as conn:
            if store.expire_question(
                conn, request.question_id, resolved_at=_now_iso()
            ):
                return ExpiredQuestion(final_state=store.EXPIRED)
            record = store.get_question(conn, request.question_id)
    except (sqlite3.Error, OSError):
        logger.warning(
            "question %s: store unreadable; reporting no recorded resolution",
            request.question_id,
        )
        return ExpiredQuestion(final_state=None)

    if record is None or record.resolution is None:
        return ExpiredQuestion(final_state=None)
    return ExpiredQuestion(final_state=record.resolution)


# --- the row ----------------------------------------------------------------


def _pending_question(request: SendQuestionInput) -> QuestionRecord:
    """The question as it is written down: a fresh id and its own window."""
    sent = datetime.now(timezone.utc).replace(microsecond=0)

    return QuestionRecord(
        question_id=secrets.token_hex(6),
        workflow_id=request.workflow_id,
        epic_id=request.epic_id,
        node_id=request.node_id,
        attempt=request.attempt,
        question_text=request.question_text,
        sent_at=_iso(sent),
        expires_at=_iso(sent + timedelta(seconds=request.timeout_s)),
        message_id=None,
    )


def _connect_question() -> sqlite3.Connection:
    """Open the evidence store, or fail before an untracked message exists."""
    try:
        return store.connect(_store_path())
    except (sqlite3.Error, OSError) as exc:
        raise ApplicationError(
            f"cannot open the verification store at {_store_path()}: {exc}",
            type=QUESTION_NOT_RECORDED,
        ) from exc


def _insert_question(conn: sqlite3.Connection, record: QuestionRecord) -> None:
    """Write the pending row — the first half of the ordering R11 turns on."""
    try:
        store.insert_question(conn, record)
    except sqlite3.Error as exc:
        raise ApplicationError(
            f"could not record the question for node {record.node_id!r} "
            f"in epic {record.epic_id!r}: {exc}",
            type=QUESTION_NOT_RECORDED,
        ) from exc


def _capture_message_id(
    conn: sqlite3.Connection, question_id: str, message_id: int
) -> None:
    try:
        store.capture_message_id(conn, question_id, message_id)
    except sqlite3.Error:
        logger.warning(
            "question %s: sent, but the store could not record its message id",
            question_id,
        )


# --- the message ------------------------------------------------------------


async def _send_question(record: QuestionRecord) -> int | None:
    """Page the operator. None means they were not paged, for any reason.

    No keyboard: a question is not a choice the operator picks from a list, so
    the message sends with no `reply_markup` (FR-008). The message id the bot
    returns is the reply-routing key, captured into the row by the caller.
    """
    token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)
    chat_id = os.environ.get(TELEGRAM_CHAT_ID_ENV)
    if not token or not chat_id:
        logger.warning(
            "question %s: not sent — %s is not set on this worker",
            record.question_id,
            TELEGRAM_BOT_TOKEN_ENV if not token else TELEGRAM_CHAT_ID_ENV,
        )
        return None

    try:
        async with open_bot(token) as bot:
            message = await bot.send_message(
                chat_id=chat_id,
                text=question_message(record),
            )
    except Exception as exc:
        # Broad on purpose, and the message is not logged: an unauthorized Bot
        # API error quotes the token back at us (it is in the URL it failed on),
        # and nothing the factory keeps may repeat it (FR-007).
        logger.warning(
            "question %s: not delivered (%s)", record.question_id, type(exc).__name__
        )
        return None

    return message.message_id
