"""One escalation, one workflow: the lifecycle 008 welded into the epic's park.

041-US2. 008 was already Temporal-hosted where it mattered — the durable timer
is the sole authority on expiry and answers travel as signals — but it never
built a workflow *type*. The lifecycle lived inside `EpicWorkflow._escalate`,
so any consumer without an epic (042's supervision alert, a `--verify` test
escalation, 017's peer channel) had to fake one. The 017 peer-park deadlock is
standing evidence of what that cost the second consumer.

So the lifecycle moves here, whole, and the epic becomes just another caller
(US3, not this story).

Four decisions carry the weight:

- **The workflow ID *is* the correlation id (FR-004).** Not a field on the
  request: reading it back from `workflow.info()` makes a second id
  structurally impossible, and a second id is how a press ends up naming
  something nobody is waiting on. The starter mints it — a workflow id has to
  exist before `start_workflow`, and `secrets.token_hex` cannot be called from
  workflow scope — with `mint_correlation_id()` in a plain process and
  `child_correlation_id()` in a workflow one. Both are 12 hex digits, which is
  the whole reason Telegram's `callback_data` fits in 64 bytes without carrying
  a workflow id (002 R11).

- **The store settles because the workflow says so, never because a channel
  did (FR-013).** Every terminal transition — answered, expired, or never
  delivered — runs an activity that writes the row. Until this story the
  *channel* decided: a Telegram press went through `CallbackBridge`, which
  writes; `ergane build resolve` signalled and walked away, which does not. That
  asymmetry is `interpreter/resolved-escalation-never-clears-in-the-store`
  (recurred), and it is why fourteen escalations and every question ever asked
  sat unsettled in the live store on 2026-08-14.

- **The store's guarded UPDATE is the only arbiter (FR-007, plan trap 2).** The
  race between a press and the hour is settled by exactly one `WHERE resolution
  IS NULL`, in the store, where it already was. This workflow *asks* rather than
  decides: on timeout it takes whatever `expire_escalation` read back, and on an
  answer it takes whatever `settle_escalation` read back. Two arbiters is how a
  press that beat the timer starts losing sometimes.

- **Nothing here reads the process environment or a wall clock (FR-012,
  constitution IV).** 039's guard discovers workflow modules by scanning for the
  `@workflow.defn` decorator, so this module was covered the moment it existed;
  the defect it guards against — a workflow-scope `os.environ` read — silently
  disabled the entire roadmap schedule for eleven hours on 2026-08-13. Store
  paths are resolved in *activity* scope, where they are legitimate. The clock
  is `workflow.now()`, so the deadline this workflow holds and the deadline the
  row advertises are the same instant even after a replay.

What an undelivered escalation does is inherited on purpose: it applies the
fail-safe *now* rather than waiting out an hour for a message nobody received
(002 R11). The only thing this story adds to that path is the row it always
should have written.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from factory.activities.notify_activities import (
        DEFAULT_CHOICES,
        ESCALATION_TIMEOUT_S,
        ExpireEscalationInput,
        SendEscalationInput,
        SettleEscalationInput,
        expire_escalation,
        send_escalation,
        settle_escalation,
    )
    from factory.mergequeue.models import CheckFailure
    from factory.notify.adapter import UNKNOWN_SENDER
    from factory.notify.service import SIGNAL_NAME
    from factory.verify.models import EscalationChoice

#: The query an operator surface reads to learn what is waiting on them
#: (FR-008). Named rather than spelled at the call site, because the name is the
#: wire contract `ergane escalations list` types.
ESCALATION_STATUS_QUERY = "escalation_status"

#: The two terminal shapes an escalation can take. Spelled exactly as the store
#: spells them (`factory.verify.store.ANSWERED` / `.EXPIRED`) so a reader of a
#: result and a reader of a row never have to translate between them —
#: `tests/test_escalation_workflow.py` holds the two vocabularies together.
OUTCOME_ANSWERED = "ANSWERED"
OUTCOME_EXPIRED = "EXPIRED"

#: How wide a correlation id is, in hex digits. 12, because Telegram caps
#: `callback_data` at 64 bytes and `esc:<id>:<choice>` has to fit inside it
#: without ever carrying a workflow id (002 R11).
CORRELATION_ID_HEX = 12

#: Reads and small writes: a SQLite insert, a message out, a guarded UPDATE.
#: The same budget the epic gives the same three activities.
_RETRIES = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

_FAST = {
    "start_to_close_timeout": timedelta(minutes=2),
    "retry_policy": _RETRIES,
}

#: The shortest wait this workflow will set a timer for. A deadline already in
#: the past is still a wait of *some* length rather than none, because a zero
#: timeout is not a thing `wait_condition` has a defined answer for — and an
#: answer already buffered when the workflow gets here still wins, since the
#: condition is evaluated before the timer starts.
_MINIMUM_PATIENCE = timedelta(milliseconds=1)


@dataclasses.dataclass(frozen=True)
class EscalationRequest:
    """One human decision, in the terms the operator will read it in.

    There is deliberately no `escalation_id` field: the correlation id is the
    workflow's own id (FR-004), read back from `workflow.info()`. A request that
    carried one would be a second id to keep in step with the first.

    `question` is the one line a list surface shows — what is being asked, not
    the whole history. `history_summary` is the full failure record the message
    carries (SC-005); the store keeps it whole and only the message is clipped.
    """

    epic_id: str
    node_id: str
    history_summary: str
    question: str = ""
    choices: list[EscalationChoice] = dataclasses.field(
        default_factory=lambda: list(DEFAULT_CHOICES)
    )
    timeout_s: int = ESCALATION_TIMEOUT_S
    check_evidence: tuple[CheckFailure, ...] = ()


@dataclasses.dataclass(frozen=True)
class EscalationOutcome:
    """What the escalation settled on, and how the caller should read it.

    `outcome` is `ANSWERED` or `EXPIRED`; `resolution` is the row's terminal
    value, which is a choice from the closed enum or `EXPIRED`. They are
    separate because a caller usually wants the choice and sometimes wants to
    know whether a human produced it.

    `delivered=False` means nobody was ever paged, and the caller applies its own
    fail-safe default without treating the expiry as silence from an operator
    who saw the question (002 R11) — the epic reads it as KILL.

    `late` is the transition that *lost* the race to the store's guarded UPDATE,
    or `None` when nothing lost: an answer that arrived after the hour, or an
    expiry that arrived after a press. It is carried rather than dropped so a
    loss is visible; the row keeps the winner and is never overwritten.

    `identity` is who answered, when the transport reported one — `""` when
    nobody answered, and `UNKNOWN_SENDER` when the answer was read back from the
    store rather than delivered as a signal, because the row does not record who
    pressed.
    """

    escalation_id: str
    outcome: str
    resolution: str
    identity: str
    delivered: bool
    late: str | None = None


@dataclasses.dataclass(frozen=True)
class OpenEscalation:
    """One escalation as an operator surface sees it (FR-008).

    `resolution` is `None` while it is still waiting and terminal once it is
    not, which is what lets a list drain: a query answers for a completed
    workflow too, so the reader filters on this rather than trusting a
    visibility index that is eventually consistent.
    """

    escalation_id: str
    epic_id: str
    node_id: str
    question: str
    expires_at: str
    resolution: str | None = None


def child_correlation_id() -> str:
    """Mint a correlation id from *workflow* scope, deterministically.

    `workflow.uuid4()` is the replay-safe generator: the value is recorded in
    history, so the second pass through mints the same id rather than a new one.
    `secrets.token_hex` — what a plain process uses — would produce a different
    id on every replay and point the operator's button at a workflow that does
    not exist.
    """
    return workflow.uuid4().hex[:CORRELATION_ID_HEX]


@workflow.defn
class EscalationWorkflow:
    """One escalation, from the page to the row that closes it."""

    def __init__(self) -> None:
        #: Every reply this escalation has been told about, in arrival order.
        #: Buffered rather than judged in the handler for 008's reason: a press
        #: can arrive before the workflow is waiting for it, and a handler that
        #: validated against state the workflow has not written yet drops the
        #: answers that arrive fastest. Which of them counts is decided by
        #: `_answer`, which is pure and reads the same way on every replay.
        self._replies: list[tuple[str, str]] = []

        #: The choices this escalation actually offered. A reply carrying
        #: anything else is not an answer — the same check `CallbackBridge`
        #: makes before it signals, kept here too because a signal can arrive
        #: from anywhere and the settling activity may only be handed a value
        #: the escalations table's CHECK constraints admit.
        self._offered: frozenset[str] = frozenset()

        #: What the request said, kept for the status query.
        self._request: EscalationRequest | None = None

        #: The row's own deadline, so the query reports the instant the message
        #: advertised rather than one this workflow recomputed.
        self._expires_at = ""

        #: `None` while waiting, terminal once settled. The status query reads
        #: it, which is how `ergane escalations list` drains.
        self._resolution: str | None = None

    # --- signals and queries -------------------------------------------------

    @workflow.signal(name=SIGNAL_NAME)
    def escalation_resolved(
        self, escalation_id: str, choice: str, identity: str = UNKNOWN_SENDER
    ) -> None:
        """Record one operator decision (`factory/notify/service.py` sends it).

        The wire shape is 008's, unchanged: `escalation_resolved(escalation_id,
        choice)`. `identity` rides as an optional third argument so a transport
        that knows who replied can say so (US1's `InboundRelay.sender_identity`,
        which US4's authorized-responders check reads) without breaking the
        two-argument senders that exist today — the bridge, `ergane build
        resolve`, and every button already sitting in the operator's chat.

        Deliberately incurious about the id, exactly as the epic's handler is:
        an id this workflow does not own is buffered and never read, because
        validating against state the workflow may not have written yet is what
        drops the presses that arrive fastest.
        """
        self._replies.append((choice, identity))

    @workflow.query(name=ESCALATION_STATUS_QUERY)
    def escalation_status(self) -> OpenEscalation:
        """What is waiting on the operator, and until when (FR-008).

        Read-only and answerable after the workflow completes, which is what
        makes `resolution` the thing a list surface filters on.
        """
        request = self._request
        return OpenEscalation(
            escalation_id=workflow.info().workflow_id,
            epic_id="" if request is None else request.epic_id,
            node_id="" if request is None else request.node_id,
            question=_question(request),
            expires_at=self._expires_at,
            resolution=self._resolution,
        )

    # --- the lifecycle -------------------------------------------------------

    @workflow.run
    async def run(self, request: EscalationRequest) -> EscalationOutcome:
        """Page a human, then wait exactly as long as waiting is worth.

        The correlation id is this workflow's own id (FR-004) and is handed to
        the send activity through the optional `escalation_id` the input already
        carries, so the row and the workflow agree on the id without either one
        minting a second (plan trap 3).
        """
        self._request = request
        self._offered = frozenset(
            EscalationChoice(choice).value for choice in request.choices
        )
        escalation_id = workflow.info().workflow_id

        sent = await workflow.execute_activity(
            send_escalation,
            SendEscalationInput(
                # The row points at *this* workflow, so a press reaches the
                # thing that is waiting without knowing whether an epic exists.
                workflow_id=escalation_id,
                epic_id=request.epic_id,
                node_id=request.node_id,
                history_summary=request.history_summary,
                choices=list(request.choices),
                timeout_s=request.timeout_s,
                escalation_id=escalation_id,
                check_evidence=request.check_evidence,
            ),
            **_FAST,
        )
        self._expires_at = sent.expires_at

        if not sent.delivered:
            # Nobody was paged. Waiting out an hour for a message nobody
            # received delays the same default and calls it patience (002 R11).
            return await self._settle_unanswered(escalation_id, delivered=False)

        try:
            await workflow.wait_condition(
                lambda: self._answer() is not None,
                timeout=self._patience(sent.expires_at, request.timeout_s),
            )
        except asyncio.TimeoutError:
            return await self._settle_unanswered(escalation_id, delivered=True)

        return await self._settle_answer(escalation_id)

    async def _settle_answer(self, escalation_id: str) -> EscalationOutcome:
        """Write the operator's decision to the row, and take what the row says.

        `settle_escalation` is the store's guarded UPDATE. When it matches
        nothing the escalation was already terminal — the hour expired a beat
        earlier, or another press won — and the recorded decision stands. This
        workflow reports that one and carries its own answer back as `late`
        rather than overwriting anything (FR-007).
        """
        answer = self._answer()
        assert answer is not None  # `wait_condition` only returns once it is not
        choice, identity = answer

        settled = await workflow.execute_activity(
            settle_escalation,
            SettleEscalationInput(escalation_id=escalation_id, choice=choice),
            **_FAST,
        )
        recorded = settled.final_state or choice
        self._resolution = recorded

        if recorded == choice:
            return EscalationOutcome(
                escalation_id=escalation_id,
                outcome=_outcome_for(recorded),
                resolution=recorded,
                identity=identity,
                delivered=True,
            )

        return EscalationOutcome(
            escalation_id=escalation_id,
            outcome=_outcome_for(recorded),
            resolution=recorded,
            # The recorded decision is not the one this workflow was handed, so
            # the identity it holds belongs to the answer that lost.
            identity="" if recorded == OUTCOME_EXPIRED else UNKNOWN_SENDER,
            delivered=True,
            late=choice,
        )

    async def _settle_unanswered(
        self, escalation_id: str, *, delivered: bool
    ) -> EscalationOutcome:
        """Close the escalation out with nobody having answered it.

        `expire_escalation` marks the row `EXPIRED` iff it is still pending and
        hands back the operator's choice when a press got there first (002 R12,
        the case its docstring is written about). So a press that beat the timer
        by a millisecond still decides, and the timer is recorded as the late
        arrival.

        `final_state=None` means the store has no record at all — a database
        rebuilt under a running escalation, a row lost with the disk — which is
        not consent. The fail-safe default applies.
        """
        expired = await workflow.execute_activity(
            expire_escalation,
            ExpireEscalationInput(escalation_id=escalation_id),
            **_FAST,
        )

        if expired.final_state is None:
            self._resolution = EscalationChoice.KILL.value
            return EscalationOutcome(
                escalation_id=escalation_id,
                outcome=OUTCOME_EXPIRED,
                resolution=EscalationChoice.KILL.value,
                identity="",
                delivered=delivered,
            )

        recorded = expired.final_state
        self._resolution = recorded
        if recorded == OUTCOME_EXPIRED:
            return EscalationOutcome(
                escalation_id=escalation_id,
                outcome=OUTCOME_EXPIRED,
                resolution=recorded,
                identity="",
                delivered=delivered,
            )

        # A press won the race at the store. Prefer the identity the signal
        # carried, when this workflow also received it, over the row — which
        # records what was decided but never who decided it.
        answer = self._answer()
        identity = (
            answer[1] if answer is not None and answer[0] == recorded
            else UNKNOWN_SENDER
        )
        return EscalationOutcome(
            escalation_id=escalation_id,
            outcome=OUTCOME_ANSWERED,
            resolution=recorded,
            identity=identity,
            delivered=delivered,
            late=OUTCOME_EXPIRED,
        )

    # --- pure -----------------------------------------------------------------

    def _answer(self) -> tuple[str, str] | None:
        """The first reply that was actually an answer, or `None`.

        Pure and order-independent, so the same buffer reads the same way on
        every replay. A reply carrying a choice nobody offered is not an answer:
        it is forged, or it is a button from before the offer narrowed, and
        signalling it on would hand the caller a decision it never asked for —
        and hand the settling activity a value the store's CHECK constraints
        would reject.
        """
        for choice, identity in self._replies:
            if choice in self._offered:
                return choice, identity
        return None

    def _patience(self, expires_at: str, timeout_s: int) -> timedelta:
        """How long is left, measured against the row's own deadline.

        The row advertises `expires_at` and the operator's message quotes it, so
        the timer runs to that instant rather than to `timeout_s` from whenever
        the send activity happened to return. A workflow that restarted the
        clock would let the bridge and the workflow disagree about whether a
        press was still in time (plan trap 3).

        `workflow.now()` and not `datetime.now()`: the clock is Temporal's, or
        the second pass through disagrees with the first.
        """
        deadline = _parse_iso(expires_at)
        if deadline is None:
            return timedelta(seconds=timeout_s)
        remaining = deadline - workflow.now()
        return remaining if remaining > _MINIMUM_PATIENCE else _MINIMUM_PATIENCE


def _outcome_for(resolution: str) -> str:
    """`EXPIRED` is the one resolution no human can produce (store.py's rule)."""
    return OUTCOME_EXPIRED if resolution == OUTCOME_EXPIRED else OUTCOME_ANSWERED


def _question(request: EscalationRequest | None) -> str:
    """The one line a list surface shows, composed if the caller supplied none.

    A fallback rather than an empty cell: an operator reading "what is waiting
    on me" needs to know which node it is about, and the request's own fields
    are enough to say that much.
    """
    if request is None:
        return ""
    if request.question:
        return request.question
    offered = " / ".join(EscalationChoice(choice).value for choice in request.choices)
    return f"{request.epic_id}/{request.node_id}: {offered}?"


def _parse_iso(moment: str) -> datetime | None:
    """One ISO-8601 UTC timestamp, or `None` when it cannot be read.

    Pure: parsing a string is not reading a clock. `None` rather than a raise
    because a deadline this workflow cannot parse is a reason to fall back to
    the configured window, not a reason to fail an escalation a human is
    waiting on.
    """
    try:
        parsed = datetime.fromisoformat(moment)
    except ValueError:
        return None
    # A deadline with no zone cannot be compared with `workflow.now()`, which is
    # always aware. The factory writes `...Z` everywhere (001 FR-012); anything
    # else is a store from another tool, and the configured window is the safer
    # reading of it than a `TypeError` inside a workflow task.
    return parsed if parsed.tzinfo is not None else None
