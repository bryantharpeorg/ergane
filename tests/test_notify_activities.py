"""The two activities that page a human, and the promises they keep when nobody answers.

`factory/notify/` renders an escalation and turns a button press back into a
signal; this module is the other half — the calls the workflow makes when the
ladder has run out of ideas (`send_escalation`) and when the hour has run out
(`expire_escalation`). Neither talks to the real Bot API here: the bot is a
module-level seam, exactly as component 1's `open_client` and the judge's
`judge_transport` are, so the credential still has to come out of the worker
environment inside the activity and a worker without one still fails the way
production would. The store, by contrast, is real — the guarded UPDATE is what
decides who wins the race between a press and the hour, and a faked store would
be a test of the fake.

What these tests pin down:

- **The row exists before the message does (R11).** Every other ordering can
  lose an escalation: a message sent before the row is written is one that a
  crash turns into a button pointing at nothing, answered by a bridge that has
  never heard of it, waited on by a workflow that will never be signalled. The
  ordering is asserted from inside the send itself — the fake bot reads the
  store at the moment it is called — because asserting it afterwards only proves
  both things happened.
- **A notifier that is down is data, not an error.** No token, no chat id, a
  network that refuses, an API that says no: all of them come back as
  `delivered=false` with the row retained, because the workflow's response is to
  apply the fail-safe default (kill) immediately rather than wait out an hour for
  a message nobody received. An exception here would instead hand the escalation
  to Temporal's retry policy and stall the node on the notifier's availability —
  the one dependency R11 exists to remove from the send path.
- **A row that could not be written is the one real error.** `delivered=false`
  is survivable because the row is still expirable; a *missing* row is not
  recoverable by anything downstream, so it raises before the message is sent
  rather than leaving an untracked button in a chat.
- **The bot token reaches the bot and nothing else (FR-009).** It is not an
  input, it is not in the result, it is not in the row, and a send failure whose
  own message quotes the token — which is exactly what an unauthorized Bot API
  error looks like — does not republish it.
- **Expiry is a transition, not an assertion.** `expire_escalation` reports what
  the state machine did: `EXPIRED` when it was still pending, the operator's
  choice when a button already won, and nothing at all for an id the store has
  never heard of. The workflow applies its default either way — an activity that
  raised on an unknown id would block the fail-safe kill on the same store
  failure that lost the row.

Written before `factory/activities/notify_activities.py` exists (T025 precedes
T028): until it lands, every test here fails at import.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from telegram import InlineKeyboardMarkup
from telegram.error import NetworkError
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities import notify_activities
from factory.activities.notify_activities import (
    ESCALATION_NOT_RECORDED,
    ESCALATION_TIMEOUT_S,
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
    ExpireEscalationInput,
    SendEscalationInput,
    expire_escalation,
    send_escalation,
)
from factory.activities.verify_activities import VERIFICATION_DB_PATH_ENV
from factory.notify.messages import callback_data
from factory.verify import store
from factory.verify.models import EscalationChoice

#: Shaped like a real bot token, and deliberately distinctive: every assertion
#: that it did not leak is a substring search over something the factory wrote.
BOT_TOKEN = "1234567890:AAH-fake-bot-token-do-not-log"

CHAT_ID = "-1001234567890"

#: Longer than 64 bytes on its own — the reason `callback_data` carries the
#: escalation id instead (R11), and worth keeping realistic here so a design that
#: smuggled it into the payload would fail on length.
WORKFLOW_ID = "ergane-epic-002-verification-gating-interpreter-run-0000000001"

EPIC = "epic-002-verification-gating"
NODE = "node-implement-gates"

#: What the ladder had to say before it gave up. Multi-line and quoted verbatim
#: into the message (SC-005), short enough that Telegram's 4096-character cap
#: never enters into it.
HISTORY = (
    "attempt 1: gate test FAIL (exit 1)\n"
    "  E   AssertionError: expected a ledger row, found none\n"
    "attempt 2: judge RETRY — US1-S1 fails: nothing asserts the ledger row\n"
    "attempt 3: debugger FAIL — gate test FAIL (exit 1)"
)

ALL_CHOICES = [
    EscalationChoice.RETRY,
    EscalationChoice.KILL,
    EscalationChoice.PAUSE_EPIC,
]

#: What `secrets.token_hex(6)` produces, and what `callback_data` will accept.
ESCALATION_ID_RE = re.compile(r"^[0-9a-f]{12}$")

#: `2026-08-04T12:34:56Z` — the one timestamp spelling this factory writes (001).
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# --- fakes ------------------------------------------------------------------


class FakeMessage:
    """Only the attribute the Bot API returns that anyone here could want."""

    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class SentMessage:
    """One `send_message` call, as Telegram would have received it."""

    def __init__(self, chat_id: Any, text: str, reply_markup: Any) -> None:
        self.chat_id = chat_id
        self.text = text
        self.reply_markup = reply_markup


class FakeBot:
    """Stand-in for `telegram.Bot` — records sends, never opens a socket.

    Constructed through the activity's seam, so `opened_with` is evidence about
    where the token came from: an activity that read it from anywhere but the
    worker environment would show up here.
    """

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
        return FakeMessage(message_id=len(self.sent))


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the notifier at a scratch copy of the shared evidence store.

    The same file and the same environment variable the verification activities
    record into: escalations are evidence about a node, and an operator reading
    one epic opens one database (quickstart §5).
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


def send_input(**overrides: Any) -> SendEscalationInput:
    fields_: dict[str, Any] = {
        "workflow_id": WORKFLOW_ID,
        "epic_id": EPIC,
        "node_id": NODE,
        "history_summary": HISTORY,
        "choices": list(ALL_CHOICES),
    }
    fields_.update(overrides)
    return SendEscalationInput(**fields_)


async def send(env: ActivityEnvironment, **overrides: Any) -> Any:
    return await env.run(send_escalation, send_input(**overrides))


async def expire(env: ActivityEnvironment, escalation_id: str) -> Any:
    return await env.run(expire_escalation, ExpireEscalationInput(escalation_id))


def escalation_rows(path: Path) -> list[dict[str, Any]]:
    """Every escalation row, read back with plain `sqlite3` (quickstart §5)."""
    if not path.exists():
        return []
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute("SELECT * FROM escalations ORDER BY sent_at")
        return [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    finally:
        connection.close()


def only_row(path: Path) -> dict[str, Any]:
    rows = escalation_rows(path)
    assert len(rows) == 1, f"expected exactly one escalation row, found {len(rows)}"
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
    """…including anywhere in a raised chain (FR-009, SC-004)."""
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


@pytest.mark.parametrize(
    "fn", [send_escalation, expire_escalation], ids=lambda fn: fn.__name__
)
def test_every_activity_is_registered_under_its_contract_name(fn: Any) -> None:
    # The workflow calls these by the names in contracts/activities.md; a rename
    # here is a reference flow that waits on a call nothing answers.
    definition = activity._Definition.from_callable(fn)
    assert definition is not None, f"{fn.__name__} must carry @activity.defn"
    assert definition.name == fn.__name__


# --- a delivered escalation -------------------------------------------------


async def test_a_sent_escalation_is_recorded_and_reported_delivered(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    result = await send(env)

    assert result.delivered is True
    assert ESCALATION_ID_RE.match(result.escalation_id), result.escalation_id

    row = only_row(db_path)
    assert row["escalation_id"] == result.escalation_id
    assert row["workflow_id"] == WORKFLOW_ID
    assert row["epic_id"] == EPIC
    assert row["node_id"] == NODE
    # The store keeps the history in full; only the message is ever clipped.
    assert row["history_summary"] == HISTORY
    assert row["delivered"] == 1
    assert row["resolution"] is None
    assert row["resolved_at"] is None


async def test_the_recorded_escalation_offers_exactly_the_choices_it_was_given(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection,
    telegram_env: None, bot: FakeBot
) -> None:
    # The row's choices are what the bridge validates a press against, so a
    # narrowed offer has to survive the round trip or a button the workflow will
    # refuse becomes a button the bridge accepts.
    offered = [EscalationChoice.RETRY, EscalationChoice.KILL]

    result = await send(env, choices=offered)

    record = store.get_escalation(conn, result.escalation_id)
    assert record is not None
    assert record.choices == offered


async def test_the_hour_starts_when_the_escalation_was_sent(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # The workflow's own timer runs against the same hour (R12); a row whose
    # deadline disagreed would make the bridge and the workflow answer
    # differently about whether a press was still in time.
    result = await send(env)

    row = only_row(db_path)
    assert result.expires_at == row["expires_at"]
    assert ESCALATION_TIMEOUT_S == 3600
    assert parse_iso(row["expires_at"]) - parse_iso(row["sent_at"]) == timedelta(
        seconds=ESCALATION_TIMEOUT_S
    )


async def test_a_configured_timeout_moves_the_deadline_the_row_advertises(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # `escalation_timeout_s` is operator-configurable (data-model.md), and the
    # row has to advertise the deadline the workflow is actually holding.
    result = await send(env, timeout_s=1800)

    row = only_row(db_path)
    assert parse_iso(result.expires_at) - parse_iso(row["sent_at"]) == timedelta(
        seconds=1800
    )


async def test_the_message_carries_the_history_and_one_button_per_choice(
    env: ActivityEnvironment, telegram_env: None, bot: FakeBot
) -> None:
    # SC-005: the operator decides from the message, not from the database.
    result = await send(env)

    assert len(bot.sent) == 1
    message = bot.sent[0]
    assert str(message.chat_id) == CHAT_ID
    assert HISTORY in message.text
    assert NODE in message.text

    assert isinstance(message.reply_markup, InlineKeyboardMarkup)
    buttons = [
        button for row in message.reply_markup.inline_keyboard for button in row
    ]
    assert [button.callback_data for button in buttons] == [
        callback_data(result.escalation_id, choice) for choice in ALL_CHOICES
    ]


async def test_two_escalations_get_two_ids_and_two_rows(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection,
    telegram_env: None, bot: FakeBot
) -> None:
    # Ids key `callback_data`; a reused one would let a press on last week's
    # escalation resolve this one's.
    first = await send(env)
    second = await send(env, node_id="node-implement-judge")

    assert first.escalation_id != second.escalation_id
    assert {record.escalation_id for record in store.pending_escalations(conn)} == {
        first.escalation_id,
        second.escalation_id,
    }


# --- the row comes first (R11) ----------------------------------------------


async def test_the_row_is_written_before_the_message_goes_out(
    env: ActivityEnvironment, conn: sqlite3.Connection, telegram_env: None,
    bot: FakeBot
) -> None:
    # Asserted from inside the send: afterwards, both orderings look identical.
    # A message that exists before its row is a button pointing at nothing.
    pending_at_send: list[list[str]] = []
    bot.on_send = lambda: pending_at_send.append(
        [record.escalation_id for record in store.pending_escalations(conn)]
    )

    result = await send(env)

    assert pending_at_send == [[result.escalation_id]]


async def test_a_send_that_never_happened_leaves_an_expirable_row(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection,
    telegram_env: None, bot: FakeBot
) -> None:
    # The crash-between-insert-and-send case, injected at the send. The row is
    # what makes the escalation recoverable: the workflow's hour still runs, the
    # timeout path still finds something to expire, and nothing is left pending
    # forever because a message failed.
    bot.fail_send = NetworkError("connection reset by peer")

    result = await send(env)

    assert result.delivered is False
    row = only_row(db_path)
    assert row["delivered"] == 0
    assert row["resolution"] is None
    assert [record.escalation_id for record in store.pending_escalations(conn)] == [
        result.escalation_id
    ]

    expired = await expire(env, result.escalation_id)
    assert expired.final_state == store.EXPIRED


# --- a notifier that is down ------------------------------------------------


@pytest.mark.parametrize("missing", [TELEGRAM_BOT_TOKEN_ENV, TELEGRAM_CHAT_ID_ENV])
async def test_an_unconfigured_worker_records_the_escalation_and_reports_undelivered(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot,
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    # R11: the workflow applies the fail-safe default immediately rather than
    # waiting an hour for a message that was never addressed to anyone. The row
    # is still written, because "we could not tell the operator" is exactly the
    # kind of thing an operator later goes looking for.
    monkeypatch.delenv(missing, raising=False)

    result = await send(env)

    assert result.delivered is False
    assert bot.opened_with == []
    assert bot.sent == []
    assert only_row(db_path)["delivered"] == 0


@pytest.mark.parametrize(
    "failure",
    [NetworkError("connection reset by peer"), RuntimeError("bot is misconfigured")],
    ids=["telegram-error", "unexpected-error"],
)
async def test_a_failed_send_is_data_and_never_an_error(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot,
    failure: BaseException
) -> None:
    # Raising would hand the escalation to Temporal's retry policy and stall the
    # node on the notifier being alive — the one dependency the send path was
    # designed not to have.
    bot.fail_send = failure

    result = await send(env)

    assert result.delivered is False
    assert result.escalation_id == only_row(db_path)["escalation_id"]
    assert result.expires_at == only_row(db_path)["expires_at"]


# --- credentials (FR-009) ---------------------------------------------------


def test_the_activity_input_has_no_place_to_put_a_credential() -> None:
    # Credentials are read from the worker environment inside the activity; a
    # field for one would put it in the workflow's history forever.
    names = {field.name for field in fields(SendEscalationInput)}

    assert not [name for name in names if "token" in name or "chat" in name]


async def test_the_token_reaches_the_bot_and_nothing_else(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    request = send_input()

    result = await env.run(send_escalation, request)

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

    assert result.delivered is False
    assert_credential_free(result, BOT_TOKEN)
    assert_credential_free(only_row(db_path)["history_summary"], BOT_TOKEN)


# --- a row that could not be written ----------------------------------------


async def test_an_escalation_that_cannot_be_recorded_is_an_error_not_a_message(
    env: ActivityEnvironment, tmp_path: Path, telegram_env: None, bot: FakeBot,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    # `delivered=false` is survivable because the row is still expirable; an
    # unwritable store is not, so it fails before a button exists in a chat that
    # nothing downstream can resolve.
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(blocked / "verification.db"))

    with pytest.raises(ApplicationError) as excinfo:
        await send(env)

    assert excinfo.value.type == ESCALATION_NOT_RECORDED
    assert bot.sent == []
    assert_error_credential_free(excinfo.value, BOT_TOKEN)


# --- expiry ------------------------------------------------------------------


async def test_expiry_marks_a_pending_escalation_expired(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    result = await send(env)

    expired = await expire(env, result.escalation_id)

    assert expired.final_state == store.EXPIRED
    row = only_row(db_path)
    assert row["resolution"] == store.EXPIRED
    assert row["resolved_via"] == "TIMEOUT"
    parse_iso(row["resolved_at"])


async def test_expiry_leaves_a_decision_an_operator_already_made(
    env: ActivityEnvironment, db_path: Path, conn: sqlite3.Connection,
    telegram_env: None, bot: FakeBot
) -> None:
    # The press and the hour race by design (R12). The workflow's timeout path
    # runs anyway — it cannot know it lost until it asks — and must be told what
    # the answer was rather than overwriting it with a kill.
    result = await send(env)
    pressed_at = "2026-08-04T11:59:59Z"
    store.resolve_escalation(
        conn, result.escalation_id, EscalationChoice.RETRY, resolved_at=pressed_at
    )

    expired = await expire(env, result.escalation_id)

    assert expired.final_state == EscalationChoice.RETRY.value
    row = only_row(db_path)
    assert row["resolution"] == EscalationChoice.RETRY.value
    assert row["resolved_at"] == pressed_at
    assert row["resolved_via"] == "BUTTON"


async def test_expiring_twice_keeps_the_first_expiry(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # Temporal runs an activity at least once; a second expiry must not restamp
    # a terminal row, or the evidence would say the hour ran out twice.
    result = await send(env)
    first = await expire(env, result.escalation_id)
    resolved_at = only_row(db_path)["resolved_at"]

    second = await expire(env, result.escalation_id)

    assert first.final_state == second.final_state == store.EXPIRED
    assert only_row(db_path)["resolved_at"] == resolved_at


async def test_expiring_an_unknown_escalation_reports_nothing_and_writes_nothing(
    env: ActivityEnvironment, db_path: Path, telegram_env: None, bot: FakeBot
) -> None:
    # A store rebuilt under a running epic. Raising would block the fail-safe
    # kill on the same failure that lost the row; the workflow applies its
    # default either way, and there is no final state to report.
    expired = await expire(env, "ffffffffffff")

    assert expired.final_state is None
    assert escalation_rows(db_path) == []
