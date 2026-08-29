"""US1-S6 — the `messages` table: the row an exchange is recorded in.

017-US1 / FR-008. Every message and reply is persisted in the verification
store, attributed to sender and recipient, alongside 008's questions. The
table is a sibling of `questions` in the same WAL/contract-DDL discipline
(plan: "Messages are a sibling table … in the same WAL/contract-DDL
discipline"), and the resolution grammar is the one the questions table
already established: a guarded UPDATE settles the race between a reply and
the message's own expiry, first wins, and whichever arrives second matches no
rows and is told so (`resolve_question`'s pattern, plan trap 2).

What these tests pin down:

- **The row carries the exchange whole.** Sender (epic, node, attempt,
  persona), addressee, body, reply, resolution, expiry — every field the
  routing, the expiry loop and an operator reading the store need, and none
  besides. `message_id` is the 12-hex threading key: the reply routes by it,
  so two open exchanges cannot cross.
- **Guarded resolution is first-wins.** A reply and an expiry racing for the
  same row settle exactly one way — the same `WHERE resolution IS NULL` the
  questions table uses. A late reply arriving after the expiry is *stored* on
  the row the expiry already closed, and never read: the workflow that asked
  is gone, and nothing may reopen a closed window (the `_answers` discipline
  the plan names).
- **The expiry is a resolution, not a delete.** An unanswered message's row
  stays, EXPIRED — an operator reading the store sees the question that was
  asked and never answered, not a hole where it was.
- **Pending rows are enumerable**, the input the degradation sweep reads: the
  expiry loop asks for every message whose window has lapsed, oldest first.

Written before the table exists (T006 precedes T007): until it lands, every
test here fails at import — `store.MessageRecord` is not a name yet.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from factory.verify import store

#: The exchange these fixtures carry. `us1` asks `us2` about the interface the
#: plan's reuse inventory cites; `us2` replies.
EPIC = "epic-017-peer-channel"
SENDER = "us1"
ADDRESSEE = "us2"
ATTEMPT = 1
PERSONA = "implementer"

BODY = (
    "The reuse inventory cites the question seam at\n"
    "`factory/escalation/question.py`. Does the addressee line belong in the\n"
    "marker body, and which half owns the peel?\n"
)

REPLY = (
    "In the body's first line; the parse owns the peel. The marker is the\n"
    "agent's contract and the addressee is routing data.\n"
)

#: What `secrets.token_hex(6)` produces — the threading shape the questions
#: table already established, so a reply routes by a key the same size as an
#: operator answer's.
MESSAGE_ID = "1a2b3c4d5e6f"

#: The one timestamp spelling this factory writes (001).
SENT_AT = "2026-08-29T09:31:00Z"
EXPIRES_AT = "2026-08-29T17:31:00Z"
RESOLVED_AT = "2026-08-29T10:02:00Z"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """A real store, in a scratch database — the transitions are the point.

    The guarded UPDATE is what decides who wins the race between a reply and
    an expiry, and a faked store would be a test of the fake.
    """
    connection = store.connect(tmp_path / "verification.db")
    try:
        yield connection
    finally:
        connection.close()


def a_message(**overrides: object) -> store.MessageRecord:
    """One pending message row, defaulting to `us1` asking `us2`."""
    fields: dict[str, object] = {
        "message_id": MESSAGE_ID,
        "epic_id": EPIC,
        "sender_node": SENDER,
        "sender_attempt": ATTEMPT,
        "sender_persona": PERSONA,
        "addressee": ADDRESSEE,
        "body": BODY,
        "sent_at": SENT_AT,
        "expires_at": EXPIRES_AT,
    }
    fields.update(overrides)
    return store.MessageRecord(**fields)  # type: ignore[arg-type]


# --- the row ------------------------------------------------------------------


def test_the_table_exists_beside_the_questions_table(conn: sqlite3.Connection) -> None:
    """FR-008: `messages` is a sibling of `questions`, in the same database.

    Questions are evidence about a node; so are peer exchanges. One store,
    opened once by an operator reading one epic (quickstart §5).
    """
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "messages" in names
    assert "questions" in names


def test_a_message_row_carries_the_whole_exchange(conn: sqlite3.Connection) -> None:
    """FR-008: attributed to sender and recipient, with body, reply,
    resolution and expiry — the fields the routing, the expiry loop and an
    operator each read."""
    store.insert_message(conn, a_message())

    record = store.get_message(conn, MESSAGE_ID)

    assert record is not None
    assert record.message_id == MESSAGE_ID
    assert record.epic_id == EPIC
    assert record.sender_node == SENDER
    assert record.sender_attempt == ATTEMPT
    assert record.sender_persona == PERSONA
    assert record.addressee == ADDRESSEE
    assert record.body == BODY
    assert record.sent_at == SENT_AT
    assert record.expires_at == EXPIRES_AT
    # Pending: no reply, no resolution — the addressee has not answered.
    assert record.reply is None
    assert record.resolution is None
    assert record.resolved_at is None


def test_the_reply_is_stored_on_the_row_it_threads_to(conn: sqlite3.Connection) -> None:
    """FR-003 / FR-008: the reply threads by message id, verbatim.

    The threading key is the id the message was minted with — not recency, not
    "the addressee's latest" — so two open exchanges to one addressee cannot
    cross, the same reason an operator reply threads by Telegram message id.
    """
    store.insert_message(conn, a_message())

    assert store.resolve_message(
        conn, MESSAGE_ID, reply_text=REPLY, resolved_at=RESOLVED_AT
    )

    record = store.get_message(conn, MESSAGE_ID)
    assert record is not None
    assert record.reply == REPLY
    assert record.resolution == store.ANSWERED
    assert record.resolved_at == RESOLVED_AT


def test_a_reply_to_an_unknown_id_is_refused_not_invented(conn: sqlite3.Connection) -> None:
    """FR-004's store half: a reply naming an id the store has never heard of
    resolves nothing — refused, not fabricated into a row nobody asked for.

    A store rebuilt under a running epic loses rows; the reply must not
    crash the sweeper that read it, and must not invent the exchange it
    threaded to.
    """
    assert not store.resolve_message(
        conn, "000000000000", reply_text=REPLY, resolved_at=RESOLVED_AT
    )
    assert store.get_message(conn, "000000000000") is None


# --- the guarded transition ---------------------------------------------------


def test_the_first_resolution_wins_and_the_second_is_told_so(
    conn: sqlite3.Connection,
) -> None:
    """FR-004 / the `resolve_question` pattern: one guarded UPDATE, first wins.

    A reply and an expiry race for the same row; whichever lands first sets
    the resolution, and the other matches no rows. Two arbiters is how a
    reply that beat the timer starts losing sometimes — the reason the store
    is the only arbiter.
    """
    store.insert_message(conn, a_message())

    # The reply lands first.
    assert store.resolve_message(
        conn, MESSAGE_ID, reply_text=REPLY, resolved_at=RESOLVED_AT
    )
    # The expiry arrives second and wins nothing — the row is already closed.
    assert not store.expire_message(conn, MESSAGE_ID, resolved_at="2026-08-29T17:31:01Z")

    record = store.get_message(conn, MESSAGE_ID)
    assert record is not None
    assert record.resolution == store.ANSWERED
    assert record.reply == REPLY


def test_an_expiry_wins_when_the_reply_never_came(
    conn: sqlite3.Connection,
) -> None:
    """FR-004: the message's own window elapsing is the one resolution no
    reply can overwrite — and the expiry, landing first, is what a late reply
    finds.

    The losing transition writes *nothing* — the guarded UPDATE is pure
    first-wins (plan trap 2), so a reply that arrives late changes no field it
    lost the race for. Recording the late reply is the caller's explicit act,
    the test below it.
    """
    store.insert_message(conn, a_message())

    assert store.expire_message(conn, MESSAGE_ID, resolved_at="2026-08-29T17:31:00Z")
    # The late reply resolves nothing, and stores nothing by itself: a guarded
    # UPDATE with a side effect would be a second writer of the transition.
    assert not store.resolve_message(
        conn, MESSAGE_ID, reply_text=REPLY, resolved_at="2026-08-29T18:00:00Z"
    )

    record = store.get_message(conn, MESSAGE_ID)
    assert record is not None
    assert record.resolution == store.EXPIRED
    assert record.reply is None


def test_an_expired_row_is_not_deleted_but_closed(conn: sqlite3.Connection) -> None:
    """The degradation's record: an unanswered message stays, EXPIRED, with
    its body — an operator reading the store sees the question that was asked
    and never answered, not a hole where it was."""
    store.insert_message(conn, a_message())

    assert store.expire_message(conn, MESSAGE_ID, resolved_at="2026-08-29T17:31:00Z")

    record = store.get_message(conn, MESSAGE_ID)
    assert record is not None
    assert record.resolution == store.EXPIRED
    assert record.body == BODY


def test_a_late_reply_on_an_expired_row_is_stored_and_never_read(
    conn: sqlite3.Connection,
) -> None:
    """The `_answers` discipline, extended to messages: a reply arriving
    after the asker went terminal (the expiry closed the window) is stored on
    the row and delivered to nobody.

    The reply is evidence, not a delivery — reopening the window would park a
    node that has already moved on, and an asker that expired cannot un-expire
    by receiving mail.
    """
    store.insert_message(conn, a_message())
    store.expire_message(conn, MESSAGE_ID, resolved_at="2026-08-29T17:31:00Z")

    stored = store.record_late_reply(conn, MESSAGE_ID, reply_text=REPLY)

    assert stored
    record = store.get_message(conn, MESSAGE_ID)
    assert record is not None
    # Stored — the text is on the row — and never read: the resolution is
    # still EXPIRED, so no workflow will deliver it.
    assert record.reply == REPLY
    assert record.resolution == store.EXPIRED
    assert record.resolved_at == "2026-08-29T17:31:00Z"


# --- the sweep's inputs --------------------------------------------------------


def test_pending_messages_are_enumerable_oldest_first(
    conn: sqlite3.Connection,
) -> None:
    """The expiry loop's input: every message still awaiting a reply, in the
    order they were asked — the same enumeration `pending_questions` gives the
    question expiry path."""
    store.insert_message(conn, a_message(message_id="000000000001", sent_at="2026-08-29T09:00:00Z"))
    store.insert_message(conn, a_message(message_id="000000000002", sent_at="2026-08-29T08:00:00Z"))
    store.insert_message(
        conn,
        a_message(message_id="000000000003", sent_at="2026-08-29T10:00:00Z"),
    )
    # A resolved message is not pending — the sweep must not re-expire it.
    store.resolve_message(
        conn, "000000000003", reply_text=REPLY, resolved_at=RESOLVED_AT
    )

    pending = store.pending_messages(conn)

    assert [record.message_id for record in pending] == [
        "000000000002",
        "000000000001",
    ]


def test_pending_messages_scoped_to_one_epic(
    conn: sqlite3.Connection,
) -> None:
    """The sweep reads one epic's messages, not every epic's — the same
    scoping the question path has, so a sibling epic's open exchange is never
    another epic's expiry to close."""
    store.insert_message(conn, a_message())
    store.insert_message(
        conn,
        a_message(
            message_id="999999999999",
            epic_id="epic-018-somewhere-else",
            sent_at="2026-08-29T07:00:00Z",
        ),
    )

    pending = store.pending_messages(conn, epic_id=EPIC)

    assert [record.message_id for record in pending] == [MESSAGE_ID]


def test_a_reinserted_id_is_refused(conn: sqlite3.Connection) -> None:
    """A reused threading key would let a reply to last week's message land on
    this one's — the same reason `insert_question` raises on a taken id."""
    store.insert_message(conn, a_message())

    with pytest.raises(sqlite3.IntegrityError):
        store.insert_message(conn, a_message())