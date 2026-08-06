"""The one test that asks the real Bot API to accept an escalation.

`test_notify_activities.py` proves `send_escalation` against a `FakeBot`: a
stand-in that accepts whatever it is handed. That pins the ordering R11 turns on
— row first, message second — and the fail-safe reporting around a send that
does not happen, and it pins nothing at all about whether Telegram would accept
the message this component builds. The Bot API rejects a `callback_data` over 64
bytes, a body over 4096 characters, and a chat id it does not recognise, and
against the fake every one of those looks like a delivered escalation. An
operator would find out at 3am, when the escalation that was supposed to page
them silently reported `delivered=false` and the ladder killed the node on the
default.

This file closes that gap once, per quickstart §4: it points the notifier at a
scratch (or, if the operator says so, the shared) evidence store, runs the real
`send_escalation` activity with the real bot token out of the worker
environment, and asserts the three things the smoke exists for — Telegram
accepted the message, the buttons came back with the `callback_data` the bridge
parses, and the store holds a pending row that a press can still resolve.

Four deliberate choices:

- **The real `telegram.Bot` sends; the seam only listens.** `open_bot` is
  patched with a wrapper that constructs the production bot and delegates to it,
  because the activity discards the `Message` the API returns and that message is
  the only evidence of what Telegram actually stored. The token still has to come
  out of the worker environment inside the activity for the wrapper to receive it
  — asserted here as a digest, since a failing equality would print the
  credential this component exists to keep out of logs.
- **One message per run.** The fixture is module-scoped: each test below reads a
  different facet of a single escalation, because five smoke runs would be five
  notifications in a human's chat to learn one fact.
- **The row is left pending on purpose.** That is what makes the manual step
  below possible, and `delivered=true` with no pending row would be an escalation
  no button could ever resolve. Cleaning up would delete the thing under test.
- **It skips, it does not fail, without credentials.** No `TELEGRAM_BOT_TOKEN`
  and `TELEGRAM_CHAT_ID` means nobody asked for a live run; `uv run pytest -q`
  stays a pure-unit suite and `-m live_telegram` selects this.

**The manual half (quickstart §4).** Pressing a button is a human's job, and what
happens when they do depends on two things this test cannot arrange for them:

1. `python -m factory.notify.service` must be running against *this* store. Set
   `LIVE_NOTIFY_DB_PATH` to the same path the bridge reads
   (`FACTORY_VERIFICATION_DB` there, or its `.factory/verification.db` default) —
   otherwise this run writes to a temporary file the bridge has never heard of
   and a press is answered "no longer on record".
2. The bridge signals the workflow named in the row before it records anything
   (service.py step 2), so a press against `LIVE_NOTIFY_WORKFLOW_ID`'s default —
   a workflow id nothing is running — is answered "could not reach the
   orchestrator" and correctly leaves the row pending. That answer is itself
   proof the bridge parsed the button, found the row and accepted the choice.
   To see the full path — row resolved, buttons removed, message edited — point
   `LIVE_NOTIFY_WORKFLOW_ID` at a workflow that is actually waiting on
   `escalation_resolved` (the reference flow in `tests/reference_flow.py` is one).

Nothing here asserts on the press: a test that blocked on a human would hang an
operator's terminal for an hour and then fail.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import notify_activities
from factory.activities.notify_activities import (
    ESCALATION_TIMEOUT_S,
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
    SendEscalationInput,
    SentEscalation,
    send_escalation,
)
from factory.activities.verify_activities import VERIFICATION_DB_PATH_ENV
from factory.notify.messages import (
    CALLBACK_DATA_LIMIT,
    MESSAGE_LIMIT,
    callback_data,
)
from factory.verify import store
from factory.verify.models import EscalationChoice

#: Selected with `-m live_telegram`, deselected with `-m "not live_telegram"`;
#: skipped outright without bot credentials (see `live_config`).
pytestmark = pytest.mark.live_telegram

#: Where the escalation is recorded. Unset means a scratch database — set it to
#: the store the bridge reads and the manual press step in this module's
#: docstring becomes possible.
DB_PATH_ENV = "LIVE_NOTIFY_DB_PATH"

#: Whose workflow a press would signal. The default names nothing that is
#: running, which is the honest state for a smoke test; see the docstring.
WORKFLOW_ID_ENV = "LIVE_NOTIFY_WORKFLOW_ID"
DEFAULT_WORKFLOW_ID = "live-notify-smoke"

EPIC = "epic-live-notify-smoke"
NODE = "node-live-notify-smoke"

#: What the operator will read. Framed as a smoke test in its first line — a
#: message that pages someone at 3am has to say immediately that nothing is
#: actually burning — and otherwise shaped exactly like the history the ladder
#: assembles, because the point is to see real evidence render (SC-005).
HISTORY = (
    "This is a live-notifier smoke test. No node is failing and nothing "
    "will be killed.\n"
    "\n"
    "Attempt 1 — FAIL\n"
    "  gate test: FAIL (exit 1, 12.4s)\n"
    "── test output ──\n"
    "E   AssertionError: expected a ledger row, found none\n"
    "\n"
    "Attempt 2 — FAIL\n"
    "  gate test: PASS (exit 0, 11.8s)\n"
    "  judge: RETRY\n"
    "── judge feedback ──\n"
    "US1-S1 fails: the teardown is asserted, the ledger row it writes is not."
)

ALL_CHOICES = [
    EscalationChoice.RETRY,
    EscalationChoice.KILL,
    EscalationChoice.PAUSE_EPIC,
]

#: `2026-08-04T12:34:56Z` — the one timestamp spelling this factory writes (001).
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

#: Stands in for the token wherever a real one would otherwise be quoted back at
#: us: an unauthorized Bot API error carries the token, because the token is in
#: the URL the request failed on.
REDACTED = f"<{TELEGRAM_BOT_TOKEN_ENV}>"


@dataclass(frozen=True)
class LiveConfig:
    """The worker environment a notifying deployment would have."""

    #: Never asserted against directly — only its digest is (see `token_digest`).
    token: str
    chat_id: str
    workflow_id: str
    db_path: Path
    #: True when the operator pointed this run at a store that outlives it, and
    #: therefore at one a running bridge could resolve the press against.
    shared_store: bool


@dataclass(frozen=True)
class LiveEscalation:
    """One real escalation, and everything the assertions below read it through."""

    config: LiveConfig
    result: SentEscalation
    #: The `telegram.Message` the Bot API returned — what Telegram *stored*,
    #: which the activity has no reason to keep and this test has every reason to.
    message: Any
    #: One digest per `open_bot` call, so "the activity read the worker's token"
    #: is assertable without a failure ever printing the token.
    token_digests: list[str]
    #: A redacted rendering of whatever stopped the send, or None.
    failure: str | None


# --- environment -------------------------------------------------------------


@pytest.fixture(scope="module")
def live_config(tmp_path_factory: pytest.TempPathFactory) -> LiveConfig:
    """A bot token and a chat to send to, or a skip."""
    token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)
    chat_id = os.environ.get(TELEGRAM_CHAT_ID_ENV)
    if not token or not chat_id:
        pytest.skip(
            f"live-notify smoke needs {TELEGRAM_BOT_TOKEN_ENV} and "
            f"{TELEGRAM_CHAT_ID_ENV} in the environment (quickstart §4)"
        )

    configured = os.environ.get(DB_PATH_ENV)
    return LiveConfig(
        token=token,
        chat_id=chat_id,
        workflow_id=os.environ.get(WORKFLOW_ID_ENV) or DEFAULT_WORKFLOW_ID,
        db_path=Path(configured)
        if configured
        else tmp_path_factory.mktemp("live-notify-store") / ".factory" / "verification.db",
        shared_store=bool(configured),
    )


@pytest.fixture(scope="module")
def escalation(live_config: LiveConfig) -> LiveEscalation:
    """Send exactly one real escalation, exactly as a stuck node would.

    Only the store path is patched, and only for the duration of the send. The
    bot token and chat id stay as the operator exported them, because reading
    them out of the process environment inside the activity is the behaviour
    under test (FR-009, contracts/activities.md).
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(VERIFICATION_DB_PATH_ENV, str(live_config.db_path))
        recorder = _install_recording_bot(patch)
        result = asyncio.run(_send(live_config))

    return LiveEscalation(
        config=live_config,
        result=result,
        message=recorder.sent[0] if recorder.sent else None,
        token_digests=recorder.token_digests,
        failure=recorder.failure,
    )


# --- the live send -----------------------------------------------------------


async def _send(config: LiveConfig) -> SentEscalation:
    return await ActivityEnvironment().run(
        send_escalation,
        SendEscalationInput(
            workflow_id=config.workflow_id,
            epic_id=EPIC,
            node_id=NODE,
            history_summary=HISTORY,
            choices=list(ALL_CHOICES),
        ),
    )


class RecordingBot:
    """The production `telegram.Bot`, with the `Message` it returns kept.

    A wrapper rather than a fake: every byte still goes to the Bot API, and what
    comes back is the only account of what Telegram accepted. A send that fails
    is re-raised so the activity takes its ordinary `delivered=false` path — the
    reason is kept, redacted, purely so a failing assertion can say what went
    wrong instead of just that nothing arrived.
    """

    def __init__(self, inner: Any, token: str) -> None:
        self._inner = inner
        self._token = token
        self.sent: list[Any] = []
        self.failure: str | None = None

    async def __aenter__(self) -> RecordingBot:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> Any:
        return await self._inner.__aexit__(*exc_info)

    async def send_message(self, *args: Any, **kwargs: Any) -> Any:
        try:
            message = await self._inner.send_message(*args, **kwargs)
        except BaseException as exc:
            self.failure = f"{type(exc).__name__}: {_redacted(str(exc), self._token)}"
            raise

        self.sent.append(message)
        return message


class BotRecorder:
    """The `open_bot` seam, standing in front of the real one.

    The wrapper it builds lives for one activity invocation; this outlives the
    send, so what a test reads is derived from the bots it handed out rather
    than copied out of them at a moment that might be the wrong one.
    """

    def __init__(self) -> None:
        self.token_digests: list[str] = []
        self.bots: list[RecordingBot] = []

    @property
    def sent(self) -> list[Any]:
        return [message for bot in self.bots for message in bot.sent]

    @property
    def failure(self) -> str | None:
        return next((bot.failure for bot in self.bots if bot.failure), None)


def _install_recording_bot(patch: pytest.MonkeyPatch) -> BotRecorder:
    """Wrap the seam so the real bot still sends and the result is observable."""
    real_open_bot = notify_activities.open_bot
    recorder = BotRecorder()

    def open_bot(token: str) -> RecordingBot:
        # The token the activity read out of the worker environment, fingerprinted
        # on its way past — the value itself goes no further than the real bot.
        recorder.token_digests.append(token_digest(token))
        bot = RecordingBot(real_open_bot(token), token)
        recorder.bots.append(bot)
        return bot

    patch.setattr(notify_activities, "open_bot", open_bot)
    return recorder


# --- helpers -----------------------------------------------------------------


def token_digest(token: str) -> str:
    """A credential's fingerprint — comparable, and safe in a failure message."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _redacted(text: str, token: str) -> str:
    return text.replace(token, REDACTED)


def delivery_note(live: LiveEscalation) -> str:
    return live.failure or "the Bot API accepted nothing and said nothing"


def escalation_row(live: LiveEscalation) -> dict[str, Any]:
    """The stored row, read the way quickstart §5 reads it: plain `sqlite3`."""
    connection = sqlite3.connect(live.config.db_path)
    try:
        cursor = connection.execute(
            "SELECT * FROM escalations WHERE escalation_id = ?",
            (live.result.escalation_id,),
        )
        row = cursor.fetchone()
        assert row is not None, "the escalation this run sent is not in the store"
        return {column[0]: value for column, value in zip(cursor.description, row)}
    finally:
        connection.close()


def parse_iso(value: str) -> datetime:
    assert ISO_UTC_RE.match(value), f"{value!r} is not an ISO-8601 UTC timestamp"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def buttons(message: Any) -> list[Any]:
    markup = message.reply_markup
    assert markup is not None, "Telegram stored the message without its keyboard"
    return [button for row in markup.inline_keyboard for button in row]


# --- Telegram accepted the escalation ----------------------------------------


def test_the_bot_api_accepted_the_message_this_component_builds(
    escalation: LiveEscalation,
) -> None:
    """The thing the fake cannot prove: a real chat received a real escalation.

    `send_escalation` reports a refused send as data rather than raising (R11),
    so `delivered=false` is the failure mode here, and the redacted reason the
    wrapper kept is what makes it diagnosable rather than merely disappointing.
    """
    assert escalation.result.delivered is True, delivery_note(escalation)
    assert escalation.message is not None
    assert escalation.message.message_id


def test_the_message_went_to_the_configured_chat(escalation: LiveEscalation) -> None:
    # The chat id is worker configuration, not a credential, and an escalation
    # delivered to the wrong chat is an escalation nobody answers.
    chat = escalation.message.chat
    configured = escalation.config.chat_id

    assert str(chat.id) == configured or f"@{chat.username or ''}" == configured


def test_telegram_stored_the_failure_history_verbatim(
    escalation: LiveEscalation,
) -> None:
    """SC-005 against the real API: the operator decides from the message.

    Read back off the `Message` Telegram returned rather than off the text this
    process composed — the round trip is the part the fake could not exercise,
    and a body the API silently reshaped would be evidence an operator is
    comparing against a retry prompt that says something else (FR-006).
    """
    text = escalation.message.text

    assert HISTORY in text
    assert NODE in text and EPIC in text
    assert escalation.result.expires_at in text
    assert len(text) <= MESSAGE_LIMIT


def test_the_buttons_carry_the_callback_data_the_bridge_parses(
    escalation: LiveEscalation,
) -> None:
    """FR-008 end to end: one button per offered choice, and the API kept them all.

    The Bot API rejects a `callback_data` over 64 bytes outright, so a delivered
    message is already proof the ≤64-byte construction holds against a real
    workflow id (R11) — this asserts the payloads came back *intact*, since a
    button whose data Telegram altered is one the bridge would answer "not one of
    this factory's escalations".
    """
    pressable = buttons(escalation.message)

    assert [button.callback_data for button in pressable] == [
        callback_data(escalation.result.escalation_id, choice) for choice in ALL_CHOICES
    ]
    for button in pressable:
        assert len(button.callback_data.encode("utf-8")) <= CALLBACK_DATA_LIMIT
        assert button.text.strip()


# --- the store holds something a press can resolve ---------------------------


def test_the_escalation_is_recorded_pending_and_expirable(
    escalation: LiveEscalation,
) -> None:
    """What the bridge looks up and what the workflow's hour would expire.

    Pending is the whole point: `delivered=true` with a terminal row would be an
    escalation whose buttons could never do anything, and no row at all would be
    a button pointing at nothing (R11).
    """
    row = escalation_row(escalation)

    assert row["delivered"] == 1
    assert row["resolution"] is None
    assert row["resolved_at"] is None
    assert row["resolved_via"] is None
    assert row["workflow_id"] == escalation.config.workflow_id
    # The store keeps the history whole; only a message is ever clipped.
    assert row["history_summary"] == HISTORY


def test_the_row_advertises_the_hour_the_message_promised(
    escalation: LiveEscalation,
) -> None:
    # The operator was told, in writing, when silence becomes a kill; the row the
    # timeout path reads has to hold the same deadline (R12).
    row = escalation_row(escalation)

    assert escalation.result.expires_at == row["expires_at"]
    assert parse_iso(row["expires_at"]) - parse_iso(row["sent_at"]) == timedelta(
        seconds=ESCALATION_TIMEOUT_S
    )


def test_a_bridge_starting_now_would_find_this_escalation_outstanding(
    escalation: LiveEscalation,
) -> None:
    """The stateless-bridge property (R11), against the store this run wrote.

    A bridge holds nothing of its own: it answers a press from the row alone. So
    the record has to come back with the choices it offered and the workflow to
    signal — which is also the state the manual step in this module's docstring
    depends on.
    """
    conn = store.connect(escalation.config.db_path)
    try:
        pending = {record.escalation_id for record in store.pending_escalations(conn)}
        record = store.get_escalation(conn, escalation.result.escalation_id)
    finally:
        conn.close()

    assert escalation.result.escalation_id in pending
    assert record is not None
    assert record.choices == ALL_CHOICES
    assert record.workflow_id == escalation.config.workflow_id
    assert record.resolution is None


# --- credentials (FR-009) ----------------------------------------------------


def test_the_token_came_from_the_worker_environment_and_reached_only_the_bot(
    escalation: LiveEscalation,
) -> None:
    """The credential's whole journey, asserted without ever printing it.

    Digests rather than values: an equality failure here would otherwise publish
    a live bot token into a terminal and a CI log, which is precisely the outcome
    the discipline under test exists to prevent.
    """
    assert escalation.token_digests == [token_digest(escalation.config.token)]

    token = escalation.config.token
    assert token not in repr(escalation.result)
    for value in escalation_row(escalation).values():
        assert token not in (value if isinstance(value, str) else repr(value))


def test_no_stored_byte_of_the_evidence_repeats_the_token(
    escalation: LiveEscalation,
) -> None:
    # The database file itself, not just the columns read back through it: WAL
    # frames and freed pages are stored bytes too, and a scratch store this run
    # created is small enough to read whole.
    if escalation.config.shared_store:
        pytest.skip(
            f"{DB_PATH_ENV} points at a store this run did not create; its other "
            "rows are not this test's to read"
        )

    secret = escalation.config.token.encode("utf-8")
    artifacts = sorted(escalation.config.db_path.parent.iterdir())
    assert artifacts, "the notifier wrote nothing to inspect"

    for artifact in artifacts:
        assert secret not in artifact.read_bytes(), (
            f"the bot token is stored in {artifact.name}"
        )
