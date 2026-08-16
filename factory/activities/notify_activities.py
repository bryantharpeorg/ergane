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
far. Since 041-US1 it is re-exported from `factory/notify/service.py`, where the
Telegram transport now lives, and handed to whichever adapter this worker is
configured with — patching it here still reaches every send, because the name is
looked up in this module at call time.

What changed in 041-US1 and what did not: these activities no longer know they
are talking to Telegram. They render a message (`factory/notify/messages.py`),
hand it to the configured `MessengerAdapter` with the escalation's or question's
own id as the correlation id, and read a `DeliveryReceipt`. The row-first
ordering, the fail-safe reading of a failed send, and the raise on a store that
will not take the row are all unchanged — they were never transport concerns.
"""

from __future__ import annotations

import logging
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
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.notify.adapter import RenderedMessage, resolve_adapter
from factory.notify.messages import (
    escalation_actions,
    escalation_message,
    question_message,
    roadmap_failure_notice,
    roadmap_recovery_notice,
)
from factory.notify.service import open_bot
from factory.mergequeue.models import CheckFailure
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord, QuestionRecord

logger = logging.getLogger(__name__)

#: Read out of the worker environment by the Telegram transport
#: (`factory.notify.service.BOT_TOKEN_ENV`, the same variable under the module
#: that now owns the send) and never placed in an input, a result, a row or a
#: log line. Named here because these activities are where a caller configuring
#: a worker looks for it, and because the credential sweep asserts that this
#: pair is spelled in exactly the two modules entitled to the value.
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


def _deliver(message: RenderedMessage, correlation_id: str) -> Any:
    """Hand one rendered message to whichever transport this worker pages over.

    Resolved per call, not per process: `open_bot` is looked up in this module's
    namespace at the moment of the send, which is what keeps the seam the 008
    suite patches — `monkeypatch.setattr(notify_activities, "open_bot", …)` —
    reaching the adapter that actually opens the socket.
    """
    return resolve_adapter(open_bot=open_bot).deliver(message, correlation_id)


@dataclass(frozen=True)
class SendEscalationInput:
    """One escalation, in the terms an operator will read it in.

    There is deliberately no field for a token or a chat id: a credential in an
    activity input is a credential in the workflow's history forever (FR-009).
    `history_summary` is the full failure history the ladder assembled (SC-005) —
    the store keeps it whole and only the message is ever clipped.

    `escalation_id` is optional: when a caller has already recorded the row
    (US4's roadmap failure path writes it before attempting delivery so a down
    notifier loses the message but not the fact), the same id is reused and the
    insert is skipped. When omitted, `send_escalation` mints a fresh id and
    inserts the row as usual (R11).
    """

    workflow_id: str
    epic_id: str
    node_id: str
    history_summary: str
    choices: list[EscalationChoice] = field(default_factory=lambda: list(DEFAULT_CHOICES))
    timeout_s: int = ESCALATION_TIMEOUT_S
    escalation_id: str | None = None
    #: US2: the failing check evidence to render into the operator-facing message.
    check_evidence: tuple[CheckFailure, ...] = ()


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
class SettleEscalationInput:
    """One operator decision, on its way to the row (041-US2, FR-013).

    `choice` is a value from the closed enum the escalations table's CHECK
    constraints admit. Validating that it was *offered* is the workflow's, in
    workflow scope where it is pure; by the time it reaches here it has been
    checked, which is what keeps this activity from being the thing that fails a
    workflow over a forged button.
    """

    escalation_id: str
    choice: str


@dataclass(frozen=True)
class SettledEscalation:
    """What the escalation settled on, and whether this call is what settled it.

    `final_state` is the row's terminal resolution — the operator's choice when
    this call won, whatever got there first when it lost, and `None` for an id
    the store has never heard of. `settled_here` is False when the guarded
    UPDATE matched nothing, which is how the caller learns it lost rather than
    by comparing timestamps.
    """

    final_state: str | None
    settled_here: bool


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
class FindFerriedQuestionInput:
    """The attempt a ferried question would be attributed to (008-US3).

    The workflow asks the store — not the adapter result — whether a question
    for this attempt already exists before it re-sends on the US1 degrade path.
    D-018's hole stays at one signal (the marker): the ferry's question id is
    evidence in the store, never a second field on the adapter result.
    """

    epic_id: str
    node_id: str
    attempt: int


@dataclass(frozen=True)
class FindFerriedQuestion:
    """What the store said about a prior ferry for this attempt (008-US3).

    `question_id` is the id of the unanswered row the ferry wrote, or ``None``
    when no ferry shipped for this attempt (the US1 path sends fresh, as it did
    before). Only the id is carried back: the message id, timestamps, and text
    are the row's, not the workflow's, and the workflow reuses the row rather
    than re-paging the operator about it.
    """

    question_id: str | None


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

    When `request.escalation_id` is set, the caller has already recorded the row
    (US4 writes it before attempting delivery), so `send_escalation` skips the
    insert and only sends + marks delivered. A missing row is treated as a
    caller-side race and inserted defensively.
    """
    record = _pending_record(request)

    with closing(_connect()) as conn:
        if request.escalation_id is None:
            _insert(conn, record)
        else:
            # US4: the row was written before this send was attempted. If a retry
            # or a store rebuild lost it, fall back to inserting defensively.
            existing = store.get_escalation(conn, record.escalation_id)
            if existing is None:
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


@activity.defn
async def settle_escalation(request: SettleEscalationInput) -> SettledEscalation:
    """Record the operator's decision on the row — the workflow's own transition.

    The mirror of `expire_escalation` for the other terminal direction, and it
    exists for one reason: until 041-US2 the *channel* decided whether a row
    settled. A Telegram press went through `CallbackBridge`, which writes the
    row; `ergane build resolve` signalled the workflow and walked away, writing
    nothing. So a resolution meant a settled row or an abandoned one depending
    on where the operator happened to be sitting
    (`interpreter/resolved-escalation-never-clears-in-the-store`, recurred).
    With the lifecycle in a workflow, settlement is the workflow's transition
    and every channel becomes equal because no channel writes.

    No arbitration is added beside the store's guarded UPDATE (plan trap 2): this
    *is* that UPDATE. When it matches nothing — an operator's press already got
    there, or the hour already expired — the row is read back and its decision
    is what comes home, so a second writer can never overwrite a first.

    Never raises on an unknown id or an unreadable store, for the reason
    `expire_escalation` does not: the caller's terminal transition must not be
    blocked by the same failure that lost the row.
    """
    try:
        with closing(store.connect(_store_path())) as conn:
            if store.resolve_escalation(
                conn, request.escalation_id, request.choice, resolved_at=_now_iso()
            ):
                return SettledEscalation(
                    final_state=request.choice, settled_here=True
                )

            # The guard matched nothing: something already settled this. Only
            # the row itself can say what.
            record = store.get_escalation(conn, request.escalation_id)
    except (sqlite3.Error, OSError):
        logger.warning(
            "escalation %s: store unreadable; the decision was not recorded",
            request.escalation_id,
        )
        return SettledEscalation(final_state=None, settled_here=False)

    if record is None or record.resolution is None:
        return SettledEscalation(final_state=None, settled_here=False)
    return SettledEscalation(
        final_state=_value(record.resolution), settled_here=False
    )


# --- the row ----------------------------------------------------------------


def _pending_record(request: SendEscalationInput) -> EscalationRecord:
    """The escalation as it is written down: a fresh id and one hour of patience.

    Both timestamps come off one instant so the deadline the row advertises is
    exactly `timeout_s` after the moment it was sent — the workflow's timer runs
    against the same span, and a row that disagreed would have the bridge and the
    workflow answering differently about whether a press was still in time.

    If the caller supplied an `escalation_id`, it is reused (US4 writes the row
    before the send); otherwise a fresh token is minted.
    """
    sent = datetime.now(timezone.utc).replace(microsecond=0)

    return EscalationRecord(
        # 12 hex digits: the whole reason `callback_data` fits in 64 bytes
        # without ever carrying a workflow id (R11).
        escalation_id=request.escalation_id or secrets.token_hex(6),
        workflow_id=request.workflow_id,
        epic_id=request.epic_id,
        node_id=request.node_id,
        choices=[EscalationChoice(choice) for choice in request.choices],
        history_summary=request.history_summary,
        sent_at=_iso(sent),
        expires_at=_iso(sent + timedelta(seconds=request.timeout_s)),
        delivered=False,
        check_evidence=request.check_evidence,
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
    that means nothing. The transport says *why* against the correlation id; this
    line says which escalation it was, because both ids are 12 hex digits and a
    log that named neither kind would be unreadable a week later.
    """
    receipt = await _deliver(
        RenderedMessage(
            text=escalation_message(record),
            actions=escalation_actions(record),
        ),
        record.escalation_id,
    )
    if not receipt.delivered:
        logger.warning("escalation %s: not delivered", record.escalation_id)
    return receipt.delivered


# --- roadmap failure count (US4) --------------------------------------------

#: Table that holds the roadmap consecutive-failure count.  It lives alongside
#: the verification evidence store because the count is evidence about a
#: workflow, not workflow state (which would be lost when the workflow dies).
_ROADMAP_FAILURES_DDL = """
CREATE TABLE IF NOT EXISTS roadmap_failures (
    roadmap_id        TEXT PRIMARY KEY,
    consecutive_count INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_count >= 0),
    last_failure_text TEXT NOT NULL DEFAULT '',
    updated_at        TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class RecordRoadmapFailureInput:
    """The facts needed to record one roadmap run failure.

    `db_path` is worker-local configuration; when omitted, the activity resolves it
    from the worker environment in activity context (FR-002).  The same pattern
    `verify_activities` uses for the verification db.  No credential is in any
    field.
    """

    db_path: str | None
    roadmap_id: str
    failure_text: str


@dataclass(frozen=True)
class ResetRoadmapFailuresInput:
    """Reset the consecutive-failure count for one roadmap; returns the prior count.

    `db_path` is worker-local configuration; when omitted, the activity resolves
    it from the worker environment in activity context (FR-002).
    """

    db_path: str | None
    roadmap_id: str


@dataclass(frozen=True)
class RecordRoadmapFailureResult:
    """Result of recording a roadmap failure: the new consecutive count (FR-010).

    No escalation id is returned: roadmap failure reports are notices, not
    escalations, so there is no pending row to reuse.
    """

    count: int


@dataclass(frozen=True)
class SendRoadmapNoticeInput:
    """One roadmap notice, in the terms the operator will read it in (US2).

    There is deliberately no field for a token or a chat id: a credential in an
    activity input is a credential in the workflow's history forever (FR-009).
    The message is the rendered notice text; the durable fact lives in the
    `roadmap_failures` record written before this send is attempted.
    """

    roadmap_id: str
    message: str


@dataclass(frozen=True)
class SentRoadmapNotice:
    """What the workflow needs to know about the notice delivery (US2).

    `delivered=False` means nobody was paged, and the caller continues: a notice
    offers no choice, so there is no fail-safe default to apply.
    """

    delivered: bool


@activity.defn
async def record_roadmap_failure(request: RecordRoadmapFailureInput) -> RecordRoadmapFailureResult:
    """Record a roadmap failure and return its count (FR-010).

    The count is stored in the evidence store, not in workflow state, so it
    survives workflow restarts and continue-as-new. Repeated identical failures
    increase the count; a different failure resets it to 1.

    No escalation row is written here: roadmap failures are reported as notices,
    not choices, so there is nothing pending for a button press or expiry sweep
    to act on (US2).
    """
    db_path = request.db_path or str(_store_path())
    sent = datetime.now(timezone.utc)
    with closing(store.connect(db_path)) as conn:
        conn.executescript(_ROADMAP_FAILURES_DDL)
        row = conn.execute(
            "SELECT consecutive_count, last_failure_text FROM roadmap_failures WHERE roadmap_id = ?",
            (request.roadmap_id,),
        ).fetchone()
        if row is None:
            count = 1
            conn.execute(
                "INSERT INTO roadmap_failures (roadmap_id, consecutive_count, last_failure_text, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (request.roadmap_id, count, request.failure_text, _iso(sent)),
            )
        elif row[1] == request.failure_text:
            count = row[0] + 1
            conn.execute(
                "UPDATE roadmap_failures SET consecutive_count = ?, last_failure_text = ?, updated_at = ? "
                "WHERE roadmap_id = ?",
                (count, request.failure_text, _iso(sent), request.roadmap_id),
            )
        else:
            count = 1
            conn.execute(
                "UPDATE roadmap_failures SET consecutive_count = ?, last_failure_text = ?, updated_at = ? "
                "WHERE roadmap_id = ?",
                (count, request.failure_text, _iso(sent), request.roadmap_id),
            )
        conn.commit()
    return RecordRoadmapFailureResult(count=count)


@activity.defn
async def send_roadmap_notice(request: SendRoadmapNoticeInput) -> SentRoadmapNotice:
    """Page the operator with a roadmap notice (US2).

    A notice is a fact, not a choice: it carries no actions, so no transport
    renders a keyboard for it, and a failed delivery is data
    (`delivered=False`) rather than a raise. The durable fact lives in
    `roadmap_failures`, written before this activity is invoked.
    """
    receipt = await _deliver(
        RenderedMessage(text=request.message), request.roadmap_id
    )
    if not receipt.delivered:
        logger.warning("roadmap notice for %s: not delivered", request.roadmap_id)
    return SentRoadmapNotice(delivered=receipt.delivered)


@activity.defn
async def reset_roadmap_failures(request: ResetRoadmapFailuresInput) -> int:
    """Reset the consecutive-failure count and return the prior count (FR-009).

    Returns 0 when there was no record or no prior failures, so the caller can
    decide whether a recovery message is warranted.
    """
    db_path = request.db_path or str(_store_path())
    sent = datetime.now(timezone.utc)
    prior = 0
    with closing(store.connect(db_path)) as conn:
        conn.executescript(_ROADMAP_FAILURES_DDL)
        row = conn.execute(
            "SELECT consecutive_count FROM roadmap_failures WHERE roadmap_id = ?",
            (request.roadmap_id,),
        ).fetchone()
        if row is not None and row[0]:
            prior = row[0]
            conn.execute(
                "UPDATE roadmap_failures SET consecutive_count = 0, updated_at = ? WHERE roadmap_id = ?",
                (_iso(sent), request.roadmap_id),
            )
            conn.commit()
    return prior


# --- small conversions ------------------------------------------------------


def _store_path() -> Path:
    """The same `.factory/verification.db` the verification activities record to.

    Escalations are evidence about a node, and an operator reading one epic opens
    one database (quickstart §5).
    """
    from factory.env import resolve_env_path

    return resolve_env_path(
        ERGANE_VERIFICATION_DB_PATH_ENV,
        FACTORY_VERIFICATION_DB_PATH_ENV,
        DEFAULT_VERIFICATION_DB_PATH,
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
    return await _deliver_question(request)


async def _deliver_question(request: SendQuestionInput) -> SentQuestion:
    """Record a question and page the operator — the core both paths share (US3).

    The US1 terminal path calls this from the ``send_question`` activity; the
    US3 in-attempt ferry calls it from the ``run_agent_attempt`` activity's
    ferry callable, so a question ferried up mid-flight is recorded and paged
    exactly the way a question asked at the end is (FR-002). The row-first
    ordering and the message-id capture are the same, and so is the
    ``QUESTION_NOT_RECORDED`` raise: a ferry that cannot record a row must not
    silently ship nothing, and the adapter's isolation turns the raise into a
    skipped beat rather than a hung attempt (FR-009).
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


# --- the in-attempt ferry (008-US3) -------------------------------------------
#
# The ferry ships an in-flight question up and the answer down, so an agent
# that asks mid-flight keeps its process and context alive while the answer
# travels (US3). The send half reuses `_deliver_question` — a ferried question
# is recorded and paged exactly the way a terminal one is (FR-002). The answer
# half reads the store the bridge wrote to: a `message_id`-routed reply (US2)
# resolves the row `ANSWERED` with the operator's text, and this poll returns
# it. Both are callables the `run_agent_attempt` activity hands the adapter,
# the way `_usage_reader` is the spend callable — the adapter is a library leaf
# that owns the monitor loop, not the store or the notifier.


async def ferry_send_question(
    workflow_id: str, epic_id: str, node_id: str, attempt: int, question_text: str
) -> str:
    """Ship an in-flight question up: record the row and page the operator (US3).

    The ferry callable the adapter calls the moment it sees the agent's
    `question` file. Returns the `question_id` the adapter polls for the answer
    with, so the round trip routes by id and not by recency (FR-008). A send
    that fails to record raises `QUESTION_NOT_RECORDED`, which the adapter's
    isolation turns into a skipped beat — the question ships on the next beat,
    and the agent degrades to the US1 path if the window elapses first (FR-009).
    """
    sent = await _deliver_question(
        SendQuestionInput(
            workflow_id=workflow_id,
            epic_id=epic_id,
            node_id=node_id,
            attempt=attempt,
            question_text=question_text,
        )
    )
    return sent.question_id


async def ferry_read_answer(question_id: str) -> str | None:
    """Poll the store for the operator's reply to a ferried question (US3).

    The answer half of the ferry: returns the operator's verbatim answer once
    the bridge has routed the reply to this question (US2's
    `message_id`-threaded resolution), or ``None`` while it has not arrived. A
    store that cannot be read returns ``None`` rather than raising — the
    adapter's isolation would swallow a raise anyway, and ``None`` is the
    signal "not yet, keep polling" the same way an unreadable spend read keeps
    the previous snapshot (FR-009: a dead read never becomes a hang).
    """
    try:
        with closing(store.connect(_store_path())) as conn:
            record = store.get_question(conn, question_id)
    except (sqlite3.Error, OSError):
        logger.warning(
            "ferry: question %s unreadable; polling again", question_id
        )
        return None
    if record is None or record.resolution is None:
        return None
    return record.answer_text


@activity.defn
async def find_ferried_question(
    request: FindFerriedQuestionInput,
) -> FindFerriedQuestion:
    """Did the in-attempt ferry already ship a question for this attempt? (US3).

    The dedup the US1 degrade path asks before it re-sends: a question row the
    ferry wrote mid-flight (and that is still unanswered, because the agent
    degraded before an answer arrived) means the row and the page are already
    done, and the workflow reuses that `question_id` instead of paging the
    operator a second time. ``None`` means no ferry shipped for this attempt,
    and the US1 path sends fresh, exactly as it did before the ferry existed.

    A store that cannot be read returns ``None`` — the same posture as
    `ferry_read_answer`: a dead read degrades to the fresh send (the US1 path),
    never a hang (FR-009). The duplicate page that a read failure risks is a
    tolerable, rare failure mode; a hang is not.
    """
    try:
        with closing(store.connect(_store_path())) as conn:
            record = store.find_pending_question_by_attempt(
                conn,
                epic_id=request.epic_id,
                node_id=request.node_id,
                attempt=request.attempt,
            )
    except (sqlite3.Error, OSError):
        logger.warning(
            "ferry: pending-question lookup for %s/%s/%s unreadable; "
            "sending fresh",
            request.epic_id,
            request.node_id,
            request.attempt,
        )
        return FindFerriedQuestion(question_id=None)
    return FindFerriedQuestion(
        question_id=record.question_id if record is not None else None
    )


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

    No actions: a question is not a choice the operator picks from a list, so
    nothing renders a keyboard for it and Telegram sends with no `reply_markup`
    (FR-008). The message handle the transport returns is the reply-routing
    key, captured into the row by the caller.
    """
    receipt = await _deliver(
        RenderedMessage(text=question_message(record)), record.question_id
    )
    if not receipt.delivered:
        logger.warning("question %s: not delivered", record.question_id)
    return receipt.message_id
