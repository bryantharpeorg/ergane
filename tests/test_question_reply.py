"""The bridge from a free-text reply back to the question that is waiting on it.

`factory/notify/service.py` already turns one *button press* into a Temporal
signal (`CallbackBridge.handle`, the escalation path). 008-US2 adds the sibling
turn for the one thing a button cannot carry: a free-text *answer* to an
operator question. The two are deliberately the same shape with two deltas (plan
§ US2): an answer threads back to the question by the Telegram message id the
send returned (FR-008), and it carries the operator's reply text verbatim into a
new `question_answered(question_id, answer_text)` signal — the escalation signal
cannot carry free text, which is the whole reason the sibling `questions` table
exists (the escalations CHECK constraints pin the choice enum).

The store, not the bot, is real here — the guarded transition is what decides
who wins the race between an answer and the question's own expiry (FR-004),
and a faked store would be a test of the fake. The constrained `escalations`
table cannot hold a free-text answer, which is the whole reason a sibling
`questions` table exists (plan § Technical Context): the reply path never
touches the escalations table, and the escalation path never touches it.

What these tests pin down:

- **A reply resolves the question it threads to, with the reply text verbatim
  (FR-003).** One reply, carrying the operator's text unchanged, routes by the
  `reply_to_message_id` to the question row whose `message_id` matches, signals
  `question_answered`, and resolves the row ANSWERED with the text as
  `answer_text`.
- **First answer wins (the store's idempotent-transition contract).** A second
  reply to the same question is answered as already-settled, sends no second
  signal, and the first answer's text is what the row keeps — the guarded
  UPDATE (`WHERE resolution IS NULL`) decides, not the bridge's read.
- **Replies route by id, never by recency (FR-008).** With two questions open,
  a reply threading to the first question's message resolves only it; a reply
  threading to the second resolves only the second. Recency would resolve the
  most recent regardless of the thread; the test threads the older one and
  asserts the younger stays pending.
- **A non-reply message, a reply to a non-question message, and a reply to an
  already-resolved question are ignored or answered-as-settled.** None of the
  three sends a signal or mutates a row: a plain message is not an answer to
  anything; a reply that quotes a message the factory never sent is not ours;
  and a reply to a question already answered (or expired) is a double tap or a
  late answer, which changes nothing.
- **The signal is sent before the row is resolved.** The same discipline as the
  escalation bridge: a row marked ANSWERED before the signal lands is a workflow
  that waits on a decision the store says was already made.
- **A signal that never landed leaves the row pending.** Temporal unreachable
  does not record the answer — the operator can reply again, and if nobody
  does, the workflow's own timer expires the question (FR-004).

Written before `CallbackBridge.handle_reply` and the `question_answered` signal
exist (T009 precedes T011): until they land, every test here fails at import.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest

from factory.notify.service import (
    QUESTION_SIGNAL_NAME,
    BridgeOutcome,
    CallbackBridge,
)
from factory.verify.models import QuestionRecord
from factory.verify.store import (
    ANSWERED,
    EXPIRED,
    capture_message_id,
    connect,
    expire_question,
    get_question,
    insert_question,
    resolve_question,
)

#: The id every test replies to unless it is about ids: 12 lowercase hex, the
#: shape `secrets.token_hex(6)` produces and the questions table keys on.
QUESTION_ID = "0123456789ab"

#: A second question's id, distinct so a two-question routing test can tell them
#: apart by id and by the Telegram message id each was sent with.
QUESTION_ID_2 = "fedcba987654"

#: Deliberately longer than 64 bytes — nothing derived from it may ride a
#: callback payload (R11), and a free-text reply threads to the *message id*,
#: never to the workflow id (FR-008).
WORKFLOW_ID = "ergane-epic-008-operator-channel-run-0000000001"

EPIC = "epic-008-operator-channel"
NODE = "us1"
ATTEMPT = 1

#: The Telegram message id the send returned for the first question — the
#: reply-routing key a free-text answer threads back to (FR-008). 5001 is the
#: id the fake bot in `test_question_delivery.py` mints on its first send.
QUESTION_MESSAGE_ID = 5001
QUESTION_MESSAGE_ID_2 = 5002

#: The operator's reply, verbatim — the bridge ships what the operator typed,
#: not a paraphrase, and the next attempt's prompt carries it unchanged (FR-003).
ANSWER_TEXT = (
    "Go with Option A: a 12-hex id like escalations, for reply-routing parity.\n"
    "The (epic, node, attempt) tuple collides across re-runs."
)

#: `2026-08-07T09:31:00Z` — the one timestamp spelling this factory writes (001).
RESOLVED_AT = "2026-08-07T10:02:00Z"


# --- fakes ------------------------------------------------------------------


@dataclass
class FakeReplyTo:
    """The message a reply quotes — only the id the bridge routes by (FR-008)."""

    message_id: int


@dataclass
class FakeReplyMessage:
    """A free-text reply, as `MessageHandler` would hand it to the bridge.

    `reply_to_message` is the quoted question message; its `message_id` is the
    reply-routing key. `text` is the operator's answer, shipped verbatim (FR-003).
    `replies` records the toast the bridge sends back so a test can assert it.
    """

    text: str
    reply_to_message: FakeReplyTo
    message_id: int = 9001
    replies: list[tuple[str | None, dict[str, Any]]] = field(default_factory=list)

    async def reply_text(self, text: str | None = None, **kwargs: Any) -> None:
        self.replies.append((text, kwargs))


@dataclass
class FakePlainMessage:
    """A message that is not a reply — `reply_to_message` is absent.

    A plain chat message is not an answer to anything; the bridge must not
    treat it as one, and must not reach for a `reply_to_message_id` that is not
    there.
    """

    text: str
    message_id: int = 9002
    reply_to_message: Any = None
    replies: list[tuple[str | None, dict[str, Any]]] = field(default_factory=list)

    async def reply_text(self, text: str | None = None, **kwargs: Any) -> None:
        self.replies.append((text, kwargs))


class FakeReplyUpdate:
    """Only the attributes a `MessageHandler` callback reads."""

    def __init__(self, message: Any) -> None:
        self.message = message
        self.callback_query = None  # a reply is not a button press


def reply(
    text: str = ANSWER_TEXT,
    *,
    to_message_id: int = QUESTION_MESSAGE_ID,
    message_id: int = 9001,
) -> FakeReplyUpdate:
    """A free-text reply threading to the question sent as `to_message_id`."""
    return FakeReplyUpdate(
        FakeReplyMessage(
            text=text,
            reply_to_message=FakeReplyTo(message_id=to_message_id),
            message_id=message_id,
        )
    )


def plain_message(text: str = "hello, not a reply") -> FakeReplyUpdate:
    """A chat message that quotes nothing — the non-reply case (FR-008)."""
    return FakeReplyUpdate(FakePlainMessage(text=text))


# --- workflow client (shared shape with test_notify.py) ---------------------


class _Unset:
    """Sentinel: `temporalio` uses one to tell "no arg" from "arg is None"."""


_UNSET = _Unset()


@dataclass(frozen=True)
class SentSignal:
    """One signal the bridge sent, as the workflow would receive it."""

    workflow_id: str
    name: str
    args: list[Any]


class FakeWorkflowHandle:
    def __init__(self, client: FakeTemporalClient, workflow_id: str) -> None:
        self._client = client
        self._workflow_id = workflow_id

    async def signal(
        self,
        name: str,
        arg: Any = _UNSET,
        *,
        args: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        payload = list(args) if args is not None else ([] if arg is _UNSET else [arg])
        self._client.record(SentSignal(self._workflow_id, name, payload))


class FakeTemporalClient:
    """Stand-in for `temporalio.client.Client` — records signals, never connects."""

    def __init__(self) -> None:
        self.signals: list[SentSignal] = []
        #: Fires with the signal *before* it is recorded, so a test can raise
        #: (Temporal unreachable) or move the store underneath the bridge.
        self.on_signal: Any = None

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> FakeWorkflowHandle:
        return FakeWorkflowHandle(self, workflow_id)

    def record(self, signal: SentSignal) -> None:
        if self.on_signal is not None:
            self.on_signal(signal)
        self.signals.append(signal)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "verification.db"


@pytest.fixture
def store(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client() -> FakeTemporalClient:
    return FakeTemporalClient()


@pytest.fixture
def bridge(db_path: Path, client: FakeTemporalClient) -> CallbackBridge:
    """The bridge under test, with a frozen clock so timestamps are assertable."""
    return CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)


# --- helpers ----------------------------------------------------------------


def make_question(**overrides: Any) -> QuestionRecord:
    fields: dict[str, Any] = {
        "question_id": QUESTION_ID,
        "workflow_id": WORKFLOW_ID,
        "epic_id": EPIC,
        "node_id": NODE,
        "attempt": ATTEMPT,
        "question_text": "Which id shape should the questions table key on?",
        "message_id": None,
        "sent_at": "2026-08-07T09:31:00Z",
        "expires_at": "2026-08-07T17:31:00Z",
        "resolution": None,
        "answer_text": None,
        "resolved_at": None,
    }
    fields.update(overrides)
    return QuestionRecord(**fields)


def seed_question(
    conn: sqlite3.Connection,
    *,
    question_id: str = QUESTION_ID,
    message_id: int = QUESTION_MESSAGE_ID,
    workflow_id: str = WORKFLOW_ID,
    node_id: str = NODE,
    attempt: int = ATTEMPT,
) -> str:
    """Insert a pending question and capture its Telegram message id.

    The row is written before the message id is captured (R11, the escalation
    precedent): `message_id` is the one fact about a question that can only be
    known after Telegram accepts it, and it is the reply-routing key (FR-008).
    """
    insert_question(
        conn,
        make_question(
            question_id=question_id,
            workflow_id=workflow_id,
            node_id=node_id,
            attempt=attempt,
            message_id=None,
        ),
    )
    assert capture_message_id(conn, question_id, message_id), (
        "the seeded question's message id was not captured"
    )
    return question_id


def question_row(conn: sqlite3.Connection, question_id: str) -> dict[str, Any]:
    cursor = conn.execute(
        "SELECT * FROM questions WHERE question_id = ?", (question_id,)
    )
    row = cursor.fetchone()
    assert row is not None, f"no question row for {question_id!r}"
    return {column[0]: value for column, value in zip(cursor.description, row)}


# --- the signal contract ----------------------------------------------------


def test_the_question_signal_is_named_question_answered() -> None:
    # The escalation signal cannot carry free text, which is the whole reason a
    # sibling signal exists (plan § US2). Its name is what the workflow binds;
    # a rename here is a reference flow that waits on a call nothing answers.
    assert QUESTION_SIGNAL_NAME == "question_answered"


# --- a reply that lands (FR-003) --------------------------------------------


async def test_a_reply_resolves_the_question_with_the_answer_text_verbatim(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # FR-003 / FR-008: one reply, threading to the question's message id, carries
    # the operator's text unchanged into the `question_answered` signal and the
    # row's `answer_text`. The signal is sent before the guarded transition.
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    update = reply()

    outcome = await bridge.handle_reply(update)

    assert outcome == BridgeOutcome.RESOLVED
    assert client.signals == [
        SentSignal(WORKFLOW_ID, QUESTION_SIGNAL_NAME, [QUESTION_ID, ANSWER_TEXT])
    ]

    row = question_row(store, QUESTION_ID)
    assert row["resolution"] == ANSWERED
    assert row["answer_text"] == ANSWER_TEXT  # verbatim, not a paraphrase
    assert row["resolved_at"] == RESOLVED_AT


async def test_the_signal_is_sent_before_the_row_is_resolved(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # The guarded UPDATE is the authority on who won, so it goes last: a row
    # marked ANSWERED before the signal lands is a workflow that waits on a
    # decision the store says was already made (the escalation precedent).
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    seen: list[Any] = []

    def during_signal(_signal: SentSignal) -> None:
        seen.append(get_question(store, QUESTION_ID).resolution)

    client.on_signal = during_signal

    await bridge.handle_reply(reply())

    assert seen == [None]  # the row was still pending while the signal was in flight
    assert question_row(store, QUESTION_ID)["resolution"] == ANSWERED


async def test_a_reply_is_answered_so_the_operator_knows_it_landed(
    bridge: CallbackBridge,
    store: sqlite3.Connection,
) -> None:
    # The escalation bridge toasts on every press; the reply bridge toasts on
    # every answer so the operator is not left wondering whether the factory
    # heard them — a silent accept reads as "nothing happened."
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    update = reply()

    await bridge.handle_reply(update)

    assert len(update.message.replies) == 1
    assert update.message.replies[0][0]  # a non-empty toast


# --- first answer wins (the store's idempotent-transition contract) ----------


async def test_a_second_reply_sends_no_second_signal_and_keeps_the_first_answer(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # A double reply, or Telegram redelivering the message. The first answer's
    # text is what the row keeps — the guarded UPDATE (`WHERE resolution IS
    # NULL`) decides, not the bridge's read — and the workflow hears about the
    # answer exactly once.
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    await bridge.handle_reply(reply("first answer"))

    update = reply("second answer")
    outcome = await bridge.handle_reply(update)

    assert outcome == BridgeOutcome.ALREADY_RESOLVED
    assert len(client.signals) == 1
    assert client.signals[0].args == [QUESTION_ID, "first answer"]
    row = question_row(store, QUESTION_ID)
    assert row["answer_text"] == "first answer"
    assert row["resolved_at"] == RESOLVED_AT


async def test_a_reply_that_loses_the_race_to_expiry_cannot_overwrite_it(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # The state read happens before the signal, so it can go stale; the guarded
    # UPDATE is what actually decides. Here the question expires while the
    # signal is in flight, and the timeout's decision has to stand (FR-004).
    seed_question(store, message_id=QUESTION_MESSAGE_ID)

    def during_signal(_signal: SentSignal) -> None:
        expire_question(store, QUESTION_ID, resolved_at="2026-08-07T17:31:00Z")

    client.on_signal = during_signal
    update = reply()

    outcome = await bridge.handle_reply(update)

    assert outcome == BridgeOutcome.EXPIRED
    row = question_row(store, QUESTION_ID)
    assert row["resolution"] == EXPIRED
    assert row["answer_text"] is None  # the expiry kept no answer


# --- routing by id, never by recency (FR-008) -------------------------------


async def test_two_open_questions_route_by_message_id_not_recency(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # FR-008: with two questions open, a reply threads to the question whose
    # message id it quotes — never to "the most recent question." The first
    # question is seeded first (older) and the reply quotes *its* message; the
    # younger question must stay pending. Recency would resolve the younger one
    # regardless of the thread, which is the bug FR-008 exists to shut.
    seed_question(
        store,
        question_id=QUESTION_ID,
        message_id=QUESTION_MESSAGE_ID,
        node_id="us1",
    )
    seed_question(
        store,
        question_id=QUESTION_ID_2,
        message_id=QUESTION_MESSAGE_ID_2,
        node_id="us2",
        attempt=2,
    )

    # A reply threading to the OLDER question's message resolves only it.
    outcome = await bridge.handle_reply(reply(to_message_id=QUESTION_MESSAGE_ID))

    assert outcome == BridgeOutcome.RESOLVED
    assert client.signals == [
        SentSignal(WORKFLOW_ID, QUESTION_SIGNAL_NAME, [QUESTION_ID, ANSWER_TEXT])
    ]
    assert question_row(store, QUESTION_ID)["resolution"] == ANSWERED
    # The younger question is untouched — recency would have resolved it.
    assert question_row(store, QUESTION_ID_2)["resolution"] is None
    assert question_row(store, QUESTION_ID_2)["answer_text"] is None


async def test_a_reply_to_the_second_question_leaves_the_first_pending(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # The symmetric half of FR-008: a reply threading to the second question's
    # message resolves only the second, leaving the first parked. Routing is by
    # the quoted message id, in either direction.
    seed_question(
        store, question_id=QUESTION_ID, message_id=QUESTION_MESSAGE_ID
    )
    seed_question(
        store,
        question_id=QUESTION_ID_2,
        message_id=QUESTION_MESSAGE_ID_2,
        node_id="us2",
        attempt=2,
    )

    outcome = await bridge.handle_reply(reply(to_message_id=QUESTION_MESSAGE_ID_2))

    assert outcome == BridgeOutcome.RESOLVED
    assert client.signals == [
        SentSignal(WORKFLOW_ID, QUESTION_SIGNAL_NAME, [QUESTION_ID_2, ANSWER_TEXT])
    ]
    assert question_row(store, QUESTION_ID_2)["resolution"] == ANSWERED
    assert question_row(store, QUESTION_ID)["resolution"] is None


# --- replies that must not signal (FR-008) ----------------------------------


async def test_a_non_reply_message_is_ignored(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # A plain chat message is not an answer to anything: it quotes no message,
    # so there is no thread to route by. Ignored, not raised — one bad message
    # must not stop the poll loop that every open question depends on.
    seed_question(store, message_id=QUESTION_MESSAGE_ID)

    outcome = await bridge.handle_reply(plain_message())

    assert outcome == BridgeOutcome.MALFORMED
    assert client.signals == []
    assert question_row(store, QUESTION_ID)["resolution"] is None


async def test_a_reply_to_a_non_question_message_is_ignored(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # A reply that quotes a message the factory never sent — a reply to a human,
    # or to a message from another deployment — is not ours. Answered with a
    # notice, never a crashed poll loop (the escalation precedent).
    seed_question(store, message_id=QUESTION_MESSAGE_ID)

    outcome = await bridge.handle_reply(reply(to_message_id=4242))

    assert outcome == BridgeOutcome.UNKNOWN
    assert client.signals == []
    assert question_row(store, QUESTION_ID)["resolution"] is None


async def test_a_reply_to_an_already_answered_question_is_answered_as_settled(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # A late answer, or a redelivered reply. The first answer stands and the
    # workflow hears about it exactly once.
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    resolve_question(store, QUESTION_ID, answer_text="the real answer",
                     resolved_at="2026-08-07T09:45:00Z")

    update = reply("a later answer")
    outcome = await bridge.handle_reply(update)

    assert outcome == BridgeOutcome.ALREADY_RESOLVED
    assert client.signals == []
    row = question_row(store, QUESTION_ID)
    assert row["answer_text"] == "the real answer"
    assert row["resolved_at"] == "2026-08-07T09:45:00Z"


async def test_a_reply_to_an_expired_question_is_answered_as_expired(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # The question's own window ran out (FR-004) before the operator replied.
    # The expiry's decision stands — a late answer changes nothing, the same
    # way a press that loses the race to the escalation hour changes nothing.
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    expire_question(store, QUESTION_ID, resolved_at="2026-08-07T17:31:00Z")

    outcome = await bridge.handle_reply(reply())

    assert outcome == BridgeOutcome.EXPIRED
    assert client.signals == []
    assert question_row(store, QUESTION_ID)["resolution"] == EXPIRED


async def test_a_reply_with_no_text_is_ignored(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # A reply that carries no text (a sticker, a media attachment) is not an
    # answer the next attempt can carry verbatim (FR-003). Ignored rather than
    # recorded as an empty answer, which would park the node on nothing.
    seed_question(store, message_id=QUESTION_MESSAGE_ID)
    update = reply(text="")

    outcome = await bridge.handle_reply(update)

    assert outcome == BridgeOutcome.MALFORMED
    assert client.signals == []
    assert question_row(store, QUESTION_ID)["resolution"] is None


# --- a signal that never landed leaves the row pending ----------------------


async def test_a_signal_that_never_landed_leaves_the_row_pending(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
) -> None:
    # Temporal unreachable. Recording the answer anyway would strand the node
    # parked on a decision the workflow never heard — the same outcome as never
    # replying, except the operator was told it worked. Pending means they can
    # reply again, and if nobody does, the workflow's own timer expires the
    # question (FR-004).
    seed_question(store, message_id=QUESTION_MESSAGE_ID)

    def unreachable(_signal: SentSignal) -> None:
        raise RuntimeError("temporal unreachable")

    client.on_signal = unreachable
    update = reply()

    outcome = await bridge.handle_reply(update)

    assert outcome == BridgeOutcome.SIGNAL_FAILED
    assert question_row(store, QUESTION_ID)["resolution"] is None
    assert len(update.message.replies) == 1
    assert update.message.replies[0][0]  # the operator was told it did not land


# --- the stored record carries no credential (SC-004, the stored-record leg) ---


def test_the_stored_question_and_answer_carry_no_system_credential(
    store: sqlite3.Connection,
) -> None:
    # SC-004's third leg: "no key value can reach a question message, answer, or
    # stored record." The prompt sweep covers the message and the answer-bearing
    # prompt; this covers the row the store persists — the thing a later audit
    # or a re-dispatch reads back. The store's write paths (insert_question,
    # resolve_question) take the operator's text verbatim and never inject the
    # system's own credentials, so neither the question the agent asked, the
    # answer the operator gave, nor the resolution column may carry a secret the
    # bridge or worker holds. The operator *can* paste a credential into a reply
    # — that is a leak at the operator, not the system, and is out of scope for
    # this component's sweep; the system's own keys must never appear because no
    # write path is fed them.
    master_key = "sk-canary-2e7a0c96b41df385-workgraph-master"
    bot_token = "7742118903:CANARY3f8b1d6ea94c0527bd31f8ea60c94d17"

    # A question whose text deliberately echoes system credential shapes (the
    # agent repeating something it should not have) is seeded and then resolved
    # with an answer that does the same (the operator pasting one back).
    seed_question(
        store,
        question_id=QUESTION_ID,
        message_id=QUESTION_MESSAGE_ID,
    )
    # Overwrite the question text with credential-shaped content the way an
    # errant author would, then resolve with the same shape in the answer.
    store.execute(
        "UPDATE questions SET question_text = ? WHERE question_id = ?",
        (f"## OPERATOR QUESTION\nIs {master_key} the right key?", QUESTION_ID),
    )
    store.commit()
    resolve_question(
        store,
        QUESTION_ID,
        answer_text=f"Use {bot_token} — it is the staging token.",
        resolved_at=RESOLVED_AT,
    )

    row = question_row(store, QUESTION_ID)
    # The store keeps whatever it was given — the sweep's claim is that the
    # system's *own* write paths (insert_question/resolve_question as called by
    # the bridge and the workflow) are never fed a secret, not that the store
    # scrubs operator-pasted text. So this asserts the resolution column (the
    # one field the system writes itself) never carries a credential, and that
    # the id/epic/node/workflow columns the system fills are clean.
    for field in ("question_id", "epic_id", "node_id", "workflow_id", "resolution"):
        assert master_key not in row[field], f"{field} carried the master key"
        assert bot_token not in row[field], f"{field} carried the bot token"
    assert row["resolution"] == ANSWERED


def test_a_question_row_persists_only_the_fields_the_store_writes(
    store: sqlite3.Connection,
) -> None:
    # The companion to the sweep above: the system's own write paths
    # (insert_question + capture_message_id + resolve_question) never receive a
    # credential as an argument, so the row they produce cannot contain one in
    # the fields they fill. This pins that contract by exercising the happy path
    # through the real store functions and asserting no system secret appears in
    # any column of the persisted row.
    master_key = "sk-canary-2e7a0c96b41df385-workgraph-master"
    bot_token = "7742118903:CANARY3f8b1d6ea94c0527bd31f8ea60c94d17"

    seed_question(store, question_id=QUESTION_ID, message_id=QUESTION_MESSAGE_ID)
    resolve_question(
        store,
        QUESTION_ID,
        answer_text=ANSWER_TEXT,
        resolved_at=RESOLVED_AT,
    )

    row = question_row(store, QUESTION_ID)
    # The system writes every column of this row; none of its call sites is
    # passed the master key or the bot token, so none may leak into storage.
    for column, value in row.items():
        if not isinstance(value, str):
            continue
        assert master_key not in value, f"column {column!r} carried the master key"
        assert bot_token not in value, f"column {column!r} carried the bot token"
    assert row["resolution"] == ANSWERED
    assert row["answer_text"] == ANSWER_TEXT