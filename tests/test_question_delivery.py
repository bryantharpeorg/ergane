"""The call that ships a question, and the row that survives the send.

`factory/activities/notify_activities.py` pages a human when the ladder runs
out of ideas (`send_escalation`); 008-US1 adds the sibling call that pages one
when an agent *asks* — `send_question`. The two are deliberately the same shape
with two deltas (plan § US1): a question carries no keyboard (it is not a
choice the operator picks from a list), and the Telegram message id is captured
into a sibling `questions` table, because a free-text reply threads back to
that id (FR-008, US2). Everything else is the precedent escalation set: the row
is written before the message (R11), a notifier that is down is data not an
error, and the bot token reaches the bot and nothing else (FR-007, extending the
discipline 001 established for the master key).

The store, not the bot, is real here — the guarded transition is what decides
who wins the race between an answer and the question's own expiry (US2), and a
faked store would be a test of the fake. The constrained `escalations` table
(CHECKs over `RETRY`/`KILL`/`PAUSE_EPIC`/`EXPIRED`) cannot hold a free-text
answer, which is the whole reason a sibling `questions` table exists (plan §
Technical Context): the new table is never touched by an escalation path, and
an escalation path never touches it.

What these tests pin down:

- **The question ships once, attributed, verbatim (FR-002).** One
  `send_message` call carries the question body the detector extracted, and the
  row is written with its epic/node/attempt and the body unchanged.
- **The message id is captured at send (FR-008's prerequisite).** The Telegram
  message id the bot returns is written into the `questions` row, so a reply can
  route back to it. A row without the id is one an answer cannot thread to.
- **The row comes first (R11, the escalation precedent).** A crash between the
  insert and the send leaves something the expiry path (US2) can still close,
  rather than an untracked message in a chat. Asserted from inside the send.
- **A notifier that is down is data, not an error.** No token, no chat id, a
  refused send: all return with the row retained and the message id unset, the
  way `delivered=False` works for an escalation. Raising would stall the node on
  the notifier — the one dependency the send path was designed not to have.
- **No credential in any surface (FR-007).** The token is not an input, not a
  result, not in the row, and a send failure that quotes the token does not
  republish it. The sweep extends to the question payload and the new table.
- **A row that could not be written is the one real error.** A question whose
  row the store refuses raises before any message exists — the mirror of
  `ESCALATION_NOT_RECORDED`.

Written before `send_question` and the `questions` table exist (T005 precedes
T008): until they land, every test here fails at import.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from telegram.error import NetworkError
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities import notify_activities
from factory.activities.notify_activities import (
    QUESTION_NOT_RECORDED,
    QUESTION_TIMEOUT_S,
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
    ExpireQuestionInput,
    FindFerriedQuestion,
    FindFerriedQuestionInput,
    SendQuestionInput,
    SentQuestion,
    expire_question,
    find_ferried_question,
    send_question,
)
from factory.activities.verify_activities import VERIFICATION_DB_PATH_ENV
from factory.verify import store
from factory.verify.models import QuestionRecord

#: Shaped like a real bot token, and deliberately distinctive: every assertion
#: that it did not leak is a substring search over something the factory wrote.
BOT_TOKEN = "1234567890:AAH-fake-bot-token-do-not-log"

CHAT_ID = "-1001234567890"

#: Long enough to be realistic; the workflow id is attribution, not a secret.
WORKFLOW_ID = "ergane-epic-008-operator-channel-run-0000000001"

EPIC = "epic-008-operator-channel"
NODE = "us1"

#: The attempt the question was raised on — a question is attributed to one
#: attempt, the way a teardown's ledger row is (FR-002).
ATTEMPT = 1

#: The question body the detector extracted from the agent's final message,
#: verbatim — the bridge ships what the agent wrote, not a paraphrase (FR-002).
QUESTION_TEXT = (
    "I hit a fork on how the questions table should key its rows.\n\n"
    "Option A: a 12-hex id like escalations. Option B: the (epic, node, "
    "attempt) tuple. I lean A for reply-routing parity.\n\n"
    "Which?"
)

#: What `secrets.token_hex(6)` produces, and what the escalations table keys on;
#: the questions table reuses the same shape for the same reason (callback-free,
#: but reply routing still needs an opaque id).
QUESTION_ID_RE = re.compile(r"^[0-9a-f]{12}$")

#: `2026-08-07T09:31:00Z` — the one timestamp spelling this factory writes (001).
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# --- fakes ------------------------------------------------------------------


class FakeMessage:
    """Only the attribute the Bot API returns that anyone here could want."""

    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class SentMessage:
    """One `send_message` call, as Telegram would have received it.

    A question sends with no `reply_markup` (no keyboard — the operator types a
    reply rather than pressing a button), so the absence is itself a contract: a
    keyboard that appeared here would be an escalation's buttons on a question.
    """

    def __init__(self, chat_id: Any, text: str, reply_markup: Any) -> None:
        self.chat_id = chat_id
        self.text = text
        self.reply_markup = reply_markup


class FakeBot:
    """Stand-in for `telegram.Bot` — records sends, never opens a socket."""

    def __init__(self) -> None:
        self.opened_with: list[str] = []
        self.sent: list[SentMessage] = []
        #: Raised instead of sending — a notifier that is down, or an API that
        #: refuses the message.
        self.fail_send: BaseException | None = None
        #: Fires before the send is recorded or refused, so a test can look at
        #: the store from the moment the message is going out.
        self.on_send: Callable[[], None] | None = None

    async def __aenter__(self) -> FakeBot:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def send_message(
        self,
        chat_id: Any = None,
        text: str = "",
        *,
        reply_markup: Any = None,
        **kwargs: Any,
    ) -> FakeMessage:
        if self.on_send is not None:
            self.on_send()
        if self.fail_send is not None:
            raise self.fail_send
        self.sent.append(SentMessage(chat_id, text, reply_markup))
        # Telegram message ids are per-chat integers; the fake mints one per
        # send, the way the Bot API does, so a reply can thread back to it.
        return FakeMessage(message_id=5000 + len(self.sent))


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the notifier at a scratch copy of the shared evidence store.

    The same file and the same environment variable the verification activities
    record into: questions are evidence about a node, and an operator reading
    one epic opens one database (quickstart §5). The sibling `questions` table
    lives in the same database the escalations table does.
    """
    path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(path))
    return path


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A second connection to the store — what a bridge, or an operator, holds."""
    connection = store.connect(db_path)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker host configured to notify (contracts/activities.md: env only)."""
    monkeypatch.setenv(TELEGRAM_BOT_TOKEN_ENV, BOT_TOKEN)
    monkeypatch.setenv(TELEGRAM_CHAT_ID_ENV, CHAT_ID)


@pytest.fixture
def bot(monkeypatch: pytest.MonkeyPatch) -> FakeBot:
    """The bot the activity will open, behind its construction seam."""
    fake = FakeBot()

    def open_bot(token: str) -> FakeBot:
        fake.opened_with.append(token)
        return fake

    monkeypatch.setattr(notify_activities, "open_bot", open_bot)
    return fake


# --- helpers ----------------------------------------------------------------


def send_input(**overrides: Any) -> SendQuestionInput:
    fields_: dict[str, Any] = {
        "workflow_id": WORKFLOW_ID,
        "epic_id": EPIC,
        "node_id": NODE,
        "attempt": ATTEMPT,
        "question_text": QUESTION_TEXT,
    }
    fields_.update(overrides)
    return SendQuestionInput(**fields_)


async def send(env: ActivityEnvironment, **overrides: Any) -> Any:
    return await env.run(send_question, send_input(**overrides))


async def expire(env: ActivityEnvironment, question_id: str) -> Any:
    return await env.run(expire_question, ExpireQuestionInput(question_id))


def question_rows(source: Path | sqlite3.Connection) -> list[dict[str, Any]]:
    """Every question row, read back with plain `sqlite3` (quickstart §5).

    Takes a path (the common case) or an open connection (the row-first test,
    which reads from the same connection the activity is writing through, so
    the assertion is made at the moment the message is going out).
    """
    if isinstance(source, sqlite3.Connection):
        cursor = source.execute("SELECT * FROM questions ORDER BY sent_at")
        return [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    if not source.exists():
        return []
    connection = sqlite3.connect(source)
    try:
        cursor = connection.execute("SELECT * FROM questions ORDER BY sent_at")
        return [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    finally:
        connection.close()


def only_row(path: Path) -> dict[str, Any]:
    rows = question_rows(path)
    assert len(rows) == 1, f"expected exactly one question row, found {len(rows)}"
    return rows[0]


def parse_iso(value: str) -> datetime:
    assert ISO_UTC_RE.match(value), f"{value!r} is not an ISO-8601 UTC timestamp"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_credential_free(value: object, *secrets: str) -> None:
    """No credential may appear in anything the factory hands on or writes down."""
    rendering = value if isinstance(value, str) else repr(value)
    for secret in secrets:
        assert secret not in rendering, f"{secret!r} leaked into {rendering!r}"


def assert_error_credential_free(error: BaseException, *secrets: str) -> None:
    """…including anywhere in a raised chain (FR-007, SC-004)."""
    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        for rendering in (str(seen), repr(seen), str(seen.args)):
            for secret in secrets:
                assert secret not in rendering, (
                    f"{secret!r} leaked into {type(seen).__name__}"
                )
        seen = seen.__cause__ or seen.__context__
        depth += 1


# --- registration -----------------------------------------------------------


@pytest.mark.parametrize("fn", [send_question, expire_question], ids=lambda fn: fn.__name__)
def test_every_activity_is_registered_under_its_contract_name(fn: Any) -> None:
    # The workflow calls these by name; a rename here is a reference flow that
    # waits on a call nothing answers.
    definition = activity._Definition.from_callable(fn)
    assert definition is not None, f"{fn.__name__} must carry @activity.defn"
    assert definition.name == fn.__name__


# --- a delivered question (FR-002) -----------------------------------------


async def test_a_sent_question_is_recorded_with_the_message_id_captured(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    result = await send(env)

    assert QUESTION_ID_RE.match(result.question_id), result.question_id
    assert result.message_id == 5001  # the id Telegram returned, captured at send

    row = only_row(db_path)
    assert row["question_id"] == result.question_id
    assert row["workflow_id"] == WORKFLOW_ID
    assert row["epic_id"] == EPIC
    assert row["node_id"] == NODE
    assert row["attempt"] == ATTEMPT
    # The body ships verbatim — the bridge ships what the agent wrote (FR-002).
    assert row["question_text"] == QUESTION_TEXT
    # The message id that travelled from send to store (FR-008's prerequisite).
    assert row["message_id"] == result.message_id
    assert row["resolution"] is None
    assert row["answer_text"] is None
    assert row["resolved_at"] is None


async def test_the_question_ships_once_attributed_and_verbatim(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # FR-002: one message, carrying the body the detector extracted unchanged,
    # attributed to its epic/node/attempt. No keyboard — a question is not a
    # choice the operator picks from a list.
    await send(env)

    assert len(bot.sent) == 1
    message = bot.sent[0]
    assert str(message.chat_id) == CHAT_ID
    assert QUESTION_TEXT in message.text
    assert EPIC in message.text or NODE in message.text  # attribution is visible
    # No keyboard on a question — the operator types a reply (FR-008, US2).
    assert message.reply_markup is None


async def test_two_questions_get_two_ids_and_two_rows(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection,
    telegram_env: None, bot: FakeBot
) -> None:
    # Ids key reply routing; a reused one would let a reply to last week's
    # question land on this one's.
    first = await send(env)
    second = await send(env, node_id="us2", attempt=2)

    assert first.question_id != second.question_id
    assert len(question_rows(db_path)) == 2


# --- the row comes first (R11, the escalation precedent) --------------------


async def test_the_row_is_written_before_the_message_goes_out(
    env: ActivityEnvironment, conn: sqlite3.Connection, telegram_env: None,
    bot: FakeBot
) -> None:
    # Asserted from inside the send: afterwards, both orderings look identical.
    # A message that exists before its row is a question an answer cannot route
    # to, and an expiry (US2) cannot close.
    pending_at_send: list[list[str]] = []
    bot.on_send = lambda: pending_at_send.append(
        [row["question_id"] for row in question_rows(conn)]
    )

    result = await send(env)

    assert pending_at_send == [[result.question_id]]


# --- a notifier that is down ------------------------------------------------


@pytest.mark.parametrize("missing", [TELEGRAM_BOT_TOKEN_ENV, TELEGRAM_CHAT_ID_ENV])
async def test_an_unconfigured_worker_records_the_question_but_captures_no_message_id(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot,
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    # R11: the row is still written (the operator goes looking for it later),
    # but no message went out, so there is no message id to capture — a reply
    # cannot thread to a message that was never sent.
    monkeypatch.delenv(missing, raising=False)

    result = await send(env)

    assert result.message_id is None
    assert bot.opened_with == []
    assert bot.sent == []
    row = only_row(db_path)
    assert row["message_id"] is None


async def test_a_failed_send_is_data_and_never_an_error(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # Raising would hand the question to Temporal's retry policy and stall the
    # node on the notifier being alive — the one dependency the send path was
    # designed not to have (the escalation precedent, R11).
    bot.fail_send = NetworkError("connection reset by peer")

    result = await send(env)

    assert result.message_id is None
    row = only_row(db_path)
    assert row["question_id"] == result.question_id
    assert row["message_id"] is None  # nothing was sent to capture from


# --- credentials (FR-007) ---------------------------------------------------


def test_the_activity_input_has_no_place_to_put_a_credential() -> None:
    # Credentials are read from the worker environment inside the activity; a
    # field for one would put it in the workflow's history forever (FR-007).
    names = {field.name for field in fields(SendQuestionInput)}

    assert not [name for name in names if "token" in name or "chat" in name]


async def test_the_token_reaches_the_bot_and_nothing_else(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    request = send_input()

    result = await env.run(send_question, request)

    assert bot.opened_with == [BOT_TOKEN]  # read from the worker env, not the input
    assert_credential_free(request, BOT_TOKEN)
    assert_credential_free(result, BOT_TOKEN)
    for value in only_row(db_path).values():
        assert_credential_free(value if isinstance(value, str) else repr(value), BOT_TOKEN)


async def test_a_send_failure_that_quotes_the_token_does_not_republish_it(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # What an unauthorized Bot API call actually looks like: the token is in the
    # URL, and therefore in the error. Nothing the factory keeps may repeat it.
    bot.fail_send = NetworkError(
        f"Unauthorized: https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    result = await send(env)

    assert result.message_id is None
    assert_credential_free(result, BOT_TOKEN)
    assert_credential_free(only_row(db_path)["question_text"], BOT_TOKEN)


# --- a row that could not be written ---------------------------------------


async def test_a_question_that_cannot_be_recorded_is_an_error_not_a_message(
    env: ActivityEnvironment, tmp_path: Path, telegram_env: None, bot: FakeBot,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    # `message_id is None` is survivable because the row is still expirable; an
    # unwritten store is not, so it fails before a message exists in a chat that
    # nothing downstream can resolve (the `ESCALATION_NOT_RECORDED` precedent).
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(blocked / "verification.db"))

    with pytest.raises(ApplicationError) as excinfo:
        await send(env)

    assert excinfo.value.type == QUESTION_NOT_RECORDED
    assert bot.sent == []
    assert_error_credential_free(excinfo.value, BOT_TOKEN)


# --- the question's own window (FR-004, the row the expiry path will read) ---


async def test_the_row_advertises_the_questions_own_expiry_window(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # FR-004: a question's default window is its own — 8 hours, not the
    # escalation hour — because a question asked into an operator's sleep is
    # cheaper parked till morning than burned at 3 AM. The row advertises the
    # deadline the workflow's timer (US2) will hold.
    result = await send(env)

    row = only_row(db_path)
    assert parse_iso(row["expires_at"]) - parse_iso(row["sent_at"]) == timedelta(
        seconds=QUESTION_TIMEOUT_S
    )
    assert QUESTION_TIMEOUT_S == 28800  # 8 hours, not 3600


async def test_a_configured_timeout_moves_the_deadline_the_row_advertises(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    result = await send(env, timeout_s=3600)

    row = only_row(db_path)
    assert parse_iso(row["expires_at"]) - parse_iso(row["sent_at"]) == timedelta(
        seconds=3600
    )


# --- 008-US3: the dedup the US1 degrade path asks before re-sending -----------
#
# The ferry ships a question mid-flight; the agent then degrades to the marker
# path before an answer arrives; the workflow reaches the US1 send path and
# asks the store (not the adapter result — D-018's hole stays at one signal)
# whether a question for this attempt already exists. `find_ferried_question` is
# that ask. The row the ferry wrote is the evidence; the workflow reuses its id
# and skips the re-send, so the operator is paged once about one question, not
# twice.


@pytest.mark.parametrize("fn", [find_ferried_question], ids=lambda fn: fn.__name__)
def test_the_ferry_dedup_activity_is_registered_under_its_contract_name(
    fn: Any,
) -> None:
    """The name the workflow invokes is the name the worker serves (R10)."""
    from temporalio import activity as _activity

    definition = _activity._Definition.from_callable(fn)
    assert definition is not None
    assert definition.name == "find_ferried_question"


async def test_find_ferried_question_returns_none_when_no_ferry_shiped(
    env: ActivityEnvironment, db_path: Path
) -> None:
    """No prior row means the US1 path sends fresh, as it did before the ferry."""
    found = await env.run(
        find_ferried_question, FindFerriedQuestionInput(EPIC, NODE, ATTEMPT)
    )
    assert found.question_id is None


async def test_find_ferried_question_reuses_a_pending_row_the_ferry_wrote(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection
) -> None:
    """A pending question for this attempt is the ferry's row — reuse, don't resend.

    This is the dedup: the ferry wrote a `questions` row mid-flight (still
    unanswered, because the agent degraded before an answer arrived), and the
    workflow's US1 path asks the store before re-sending. The same id comes
    back, so the operator is paged once about one question. The store is the
    source of truth, not the adapter result — D-018's hole stays at one signal.
    """
    # A row the ferry would have written: pending (resolution IS NULL),
    # attributed to this attempt.
    store.insert_question(
        conn,
        _pending_question_row(question_id="ferry123456", attempt=ATTEMPT),
    )

    found = await env.run(
        find_ferried_question, FindFerriedQuestionInput(EPIC, NODE, ATTEMPT)
    )
    assert found.question_id == "ferry123456"


async def test_find_ferried_question_ignores_a_row_for_a_different_attempt(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection
) -> None:
    """A question attributed to a different attempt is not this attempt's ferry."""
    store.insert_question(
        conn,
        _pending_question_row(question_id="ferryaaaaaa", attempt=ATTEMPT + 1),
    )

    found = await env.run(
        find_ferried_question, FindFerriedQuestionInput(EPIC, NODE, ATTEMPT)
    )
    assert found.question_id is None


async def test_find_ferried_question_ignores_an_answered_row(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection
) -> None:
    """An answered row was a ferry that got its reply — the agent resumed, not
    degraded, so the US1 send path is never reached and that row is not reused.

    Only a *pending* row (the ferry shipped and the agent then degraded before
    an answer) is the one to reuse; an ANSWERED row belongs to a ferry window
    that closed the other way.
    """
    answered = _pending_question_row(question_id="ferrybbbbbb", attempt=ATTEMPT)
    store.insert_question(conn, answered)
    store.resolve_question(
        conn, "ferrybbbbbb", answer_text="do option A", resolved_at="2026-08-07T10:00:00Z"
    )

    found = await env.run(
        find_ferried_question, FindFerriedQuestionInput(EPIC, NODE, ATTEMPT)
    )
    assert found.question_id is None


async def test_find_ferried_question_degrades_to_none_when_the_store_is_unreadable(
    env: ActivityEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead read degrades to the fresh send (the US1 path), never a hang (FR-009).

    The duplicate page a read failure risks is a tolerable, rare failure mode;
    a hang is not. The same posture as `ferry_read_answer`: a dead read is
    `None`, the signal "send fresh."
    """

    def boom(_conn: sqlite3.Connection, **_kwargs: Any) -> Any:
        raise sqlite3.OperationalError("disk is gone")

    monkeypatch.setattr(store, "find_pending_question_by_attempt", boom)

    found = await env.run(
        find_ferried_question, FindFerriedQuestionInput(EPIC, NODE, ATTEMPT)
    )
    assert found.question_id is None


# --- the row the ferry would have written ------------------------------------


def _pending_question_row(*, question_id: str, attempt: int) -> QuestionRecord:
    """A pending `questions` row, the way the ferry's `send_question` writes one.

    The store is real; the row is constructed directly so the test owns its
    state rather than depending on Telegram-side send plumbing.
    """
    from datetime import datetime, timezone

    from factory.activities.notify_activities import _iso

    sent = datetime(2026, 8, 7, 9, 31, 0, tzinfo=timezone.utc)
    return QuestionRecord(
        question_id=question_id,
        workflow_id=WORKFLOW_ID,
        epic_id=EPIC,
        node_id=NODE,
        attempt=attempt,
        question_text=QUESTION_TEXT,
        message_id=None,
        sent_at=_iso(sent),
        expires_at=_iso(sent + timedelta(seconds=QUESTION_TIMEOUT_S)),
    )