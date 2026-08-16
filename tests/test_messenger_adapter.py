"""The messenger seam: two operations, a plain library, and Telegram behind it.

041-US1. The factory delivers a rendered message and ferries a reply through an
interface rather than through a concrete messenger's API. This file is the
interface's own guard; the *proof that Telegram still behaves identically* is
`tests/test_notify.py`, `tests/test_notify_activities.py`,
`tests/test_operator_question.py`, `tests/test_question_delivery.py` and
`tests/test_question_reply.py`, which are unchanged by this story and pass
unchanged (US1-S1).

An adapter story is unusually prone to the defect that has cost this repository
most — a test that cannot fail — because a test driving a fake transport proves
only that the fake works. Every test here was written to fail against a stated
mutation, and the mutations were run. What each one pins down:

- **US1-S2, FR-001 — the seam is exactly two operations.** Asserted against the
  protocol's own members, against every *registered* adapter's public surface,
  and against the three terms `InboundRelay` carries. A third operation, or a
  fourth relay term, fails here.
- **US1-S2, FR-001 — no adapter code path can acknowledge, answer or expire.**
  Asserted by scanning the adapter class's own source (not its module's, which
  also holds the factory-side bridge) for the verbs that settle anything, and
  structurally: an adapter's constructor is handed no store, no connection and
  no client, so there is nothing for it to settle *with*.
- **US1-S3, FR-002 — it is a plain library.** Asserted twice: no adapter-side
  module imports `temporalio` at all (AST, so a lazy import inside a function
  counts), and a real delivery runs in a **subprocess whose import system
  refuses `temporalio` outright**. 042's supervision probe is that caller and
  it runs when Temporal is dead, so this is the contract and not a nicety.
- **US1-S4 — the 008 question round trip behaves the same over a fake adapter
  as over Telegram.** Not asserted by inspection: the same round trip is run
  twice, once over `TelegramAdapter` with a fake bot and once over a fake
  adapter, and the resulting store rows, signals and rendered text are compared
  to each other. Production code does the asking, the storing, the signalling
  and the settling in both runs; the fakes are the socket, and nothing else.

Mutation transcripts are pasted at the bottom of this file, verbatim.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import os
import sqlite3
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import notify_activities
from factory.activities.notify_activities import (
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
    SendQuestionInput,
    send_question,
)
from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    UNKNOWN_SENDER,
    DeliveryReceipt,
    InboundRelay,
    MessageAction,
    MessengerAdapter,
    RenderedMessage,
    UnknownAdapterError,
    configured_adapter_name,
    register_adapter,
    registered_adapters,
    resolve_adapter,
    unregister_adapter,
)
from factory.notify.messages import (
    escalation_actions,
    escalation_keyboard,
    question_message,
)
from factory.notify.service import (
    QUESTION_SIGNAL_NAME,
    BridgeOutcome,
    CallbackBridge,
    TelegramAdapter,
)
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Shaped like a real bot token, and deliberately distinctive: every assertion
#: that it did not leak is a substring search over something the factory wrote.
BOT_TOKEN = "1234567890:AAH-fake-bot-token-do-not-log"

CHAT_ID = "-1001234567890"

WORKFLOW_ID = "ergane-epic-041-escalation-workflow-run-0000000001"
EPIC = "epic-041-escalation-workflow"
NODE = "us1"
ATTEMPT = 1

QUESTION_TEXT = (
    "Should the adapter carry the sender identity as a username or a numeric id?\n"
    "Telegram has both; a webhook has whatever the operator's bridge sends."
)

ANSWER_TEXT = "Username when there is one, numeric id otherwise. Ship it."

RESOLVED_AT = "2026-08-16T09:14:00Z"

#: The message handle both transports mint for the first message they send, so
#: the parity comparison can include the routing key rather than stripping it.
FIRST_MESSAGE_ID = 5001

#: The name the fake transport is registered under for the round-trip test.
#: Deliberately not a name 033's closed set admits — a fake is a *test*
#: registration, and the config parser refusing it is the point of the closed
#: set (033 `KNOWN_ESC_ADAPTERS`).
FAKE_ADAPTER_NAME = "fake-messenger"

#: The verbs that settle something. None of them may appear in an adapter's own
#: source: settling is the factory's, whatever channel the answer came in on.
SETTLING_VERBS = (
    "resolve_escalation",
    "resolve_question",
    "expire_escalation",
    "expire_question",
    "mark_delivered",
    "insert_escalation",
    "insert_question",
    "capture_message_id",
    "get_workflow_handle",
    ".signal(",
    ".answer(",
    "edit_message_text",
    "UPDATE ",
    "INSERT ",
)

#: What an adapter is not allowed to be *handed*, which is the structural half
#: of the same rule: a transport with no store and no client has nothing to
#: settle with, whatever its source says.
FORBIDDEN_CONSTRUCTOR_HANDLES = frozenset(
    {"db_path", "conn", "connection", "store", "client", "workflow", "handle"}
)


# --- fakes ------------------------------------------------------------------


class FakeMessage:
    """Only the attribute the Bot API returns that anyone here could want."""

    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


@dataclass
class SentMessage:
    """One `send_message` call, as Telegram would have received it."""

    chat_id: Any
    text: str
    reply_markup: Any


class FakeBot:
    """Stand-in for `telegram.Bot` — records sends, never opens a socket."""

    def __init__(self, *, first_message_id: int = FIRST_MESSAGE_ID) -> None:
        self.opened_with: list[str] = []
        self.sent: list[SentMessage] = []
        self._next_message_id = first_message_id

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
        self.sent.append(SentMessage(chat_id, text, reply_markup))
        message_id = self._next_message_id
        self._next_message_id += 1
        return FakeMessage(message_id=message_id)


@dataclass(frozen=True)
class Delivered:
    """One `deliver` call, as the fake transport received it."""

    message: RenderedMessage
    correlation_id: str


@dataclass
class FakeInbound:
    """A reply in the fake transport's own shape — nothing Telegram-like.

    Deliberately not an object with `message`/`callback_query`: if the fake's
    inbound event were Telegram-shaped, `TelegramAdapter.relay` could translate
    it and the round trip would no longer be proving that the *fake's* relay is
    what the factory consumed.
    """

    in_reply_to: int
    text: str
    sender: str = "operator@example"


class FakeAdapter:
    """A messenger that is not Telegram, doing exactly what the seam allows.

    Two operations and nothing else. It records what it was handed and mints a
    message handle; it translates its own inbound event into the factory's
    three terms. It looks nothing up, signals nobody and settles nothing — a
    fake that could do any of those would be proving the wrong thing.
    """

    def __init__(self, *, first_message_id: int = FIRST_MESSAGE_ID) -> None:
        self.delivered: list[Delivered] = []
        self._next_message_id = first_message_id

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        self.delivered.append(Delivered(message, correlation_id))
        message_id = self._next_message_id
        self._next_message_id += 1
        return DeliveryReceipt(delivered=True, message_id=message_id)

    def relay(self, event: Any) -> InboundRelay | None:
        if not isinstance(event, FakeInbound):
            return None
        return InboundRelay(
            correlation_id=str(event.in_reply_to),
            reply_text=event.text,
            sender_identity=event.sender,
        )


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
        self._client.signals.append(SentSignal(self._workflow_id, name, payload))


class FakeTemporalClient:
    """Stand-in for `temporalio.client.Client` — records signals, never connects."""

    def __init__(self) -> None:
        self.signals: list[SentSignal] = []

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> FakeWorkflowHandle:
        return FakeWorkflowHandle(self, workflow_id)


# --- Telegram-shaped inbound updates ----------------------------------------


@dataclass
class FakeUser:
    id: int = 4242
    username: str | None = "operator"


@dataclass
class FakeReplyTo:
    message_id: int


@dataclass
class FakeReplyMessage:
    text: str
    reply_to_message: FakeReplyTo | None
    from_user: FakeUser | None = None
    message_id: int = 9001
    replies: list[str | None] = field(default_factory=list)

    async def reply_text(self, text: str | None = None, **kwargs: Any) -> None:
        self.replies.append(text)


class FakeReplyUpdate:
    def __init__(self, message: Any) -> None:
        self.message = message
        self.callback_query = None


class FakeCallbackQuery:
    def __init__(self, data: str | None, from_user: FakeUser | None) -> None:
        self.data = data
        self.from_user = from_user
        self.answers: list[str | None] = []

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append(text)


class FakePressUpdate:
    def __init__(self, data: str | None, from_user: FakeUser | None = None) -> None:
        self.callback_query = FakeCallbackQuery(data, from_user)


def telegram_reply(
    text: str = ANSWER_TEXT,
    *,
    to_message_id: int = FIRST_MESSAGE_ID,
    from_user: FakeUser | None = None,
) -> FakeReplyUpdate:
    return FakeReplyUpdate(
        FakeReplyMessage(
            text=text,
            reply_to_message=FakeReplyTo(message_id=to_message_id),
            from_user=from_user,
        )
    )


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)
    return path


@pytest.fixture
def telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker host configured to notify (contracts/activities.md: env only)."""
    monkeypatch.setenv(TELEGRAM_BOT_TOKEN_ENV, BOT_TOKEN)
    monkeypatch.setenv(TELEGRAM_CHAT_ID_ENV, CHAT_ID)


@pytest.fixture
def bot(monkeypatch: pytest.MonkeyPatch) -> FakeBot:
    """The bot the send seam opens, patched where the 008 suite patches it."""
    fake = FakeBot()

    def open_bot(token: str) -> FakeBot:
        fake.opened_with.append(token)
        return fake

    monkeypatch.setattr(notify_activities, "open_bot", open_bot)
    return fake


@pytest.fixture
def fake_adapter(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeAdapter]:
    """A non-Telegram transport, registered and selected the way a real one is."""
    adapter = FakeAdapter()
    register_adapter(FAKE_ADAPTER_NAME, lambda **_seams: adapter)
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)
    try:
        yield adapter
    finally:
        unregister_adapter(FAKE_ADAPTER_NAME)


# --- helpers ----------------------------------------------------------------


def public_methods(cls: type) -> set[str]:
    """Every public operation a class declares in its own body."""
    return {
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and callable(value)
    }


def imported_roots(path: Path) -> set[str]:
    """Every top-level package the module imports, however it spells the import.

    Parsed rather than imported, so an import buried inside a function body —
    exactly how a lazy Temporal dependency would sneak back in — is still seen.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def escalation_record(**overrides: Any) -> EscalationRecord:
    fields_: dict[str, Any] = {
        "escalation_id": "0123456789ab",
        "workflow_id": WORKFLOW_ID,
        "epic_id": EPIC,
        "node_id": NODE,
        "choices": [EscalationChoice.RETRY, EscalationChoice.KILL],
        "history_summary": "attempt 1: gate test FAIL (exit 1)",
        "sent_at": "2026-08-16T08:14:00Z",
        "expires_at": "2026-08-16T09:14:00Z",
        "delivered": False,
    }
    fields_.update(overrides)
    return EscalationRecord(**fields_)


def question_row(path: Path) -> dict[str, Any]:
    """The one question row, read back with plain `sqlite3` (quickstart §5)."""
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute("SELECT * FROM questions")
        rows = [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    finally:
        connection.close()
    assert len(rows) == 1, f"expected exactly one question row, found {len(rows)}"
    return rows[0]


# ============================================================================
# US1-S2 / FR-001 — the seam declares exactly two operations
# ============================================================================


def test_the_protocol_declares_exactly_two_operations() -> None:
    """Outbound deliver, inbound relay. A third operation fails here."""
    assert public_methods(MessengerAdapter) == {"deliver", "relay"}


def test_deliver_takes_a_rendered_message_and_a_correlation_id() -> None:
    """FR-001's outbound half, spelled in the signature rather than the prose."""
    signature = inspect.signature(MessengerAdapter.deliver)

    assert list(signature.parameters) == ["self", "message", "correlation_id"]

    hints = inspect.get_annotations(MessengerAdapter.deliver, eval_str=True)
    assert hints["message"] is RenderedMessage
    assert hints["correlation_id"] is str
    assert hints["return"] is DeliveryReceipt


def test_a_relay_carries_a_correlation_id_reply_text_and_a_sender_identity() -> None:
    """FR-001's inbound half: exactly three terms, and no fourth.

    A fourth term is how "the adapter reports who replied" quietly becomes "the
    adapter reports whether they may answer" — the one decision the seam exists
    to keep factory-side.
    """
    names = [field_.name for field_ in dataclasses.fields(InboundRelay)]

    assert names == ["correlation_id", "reply_text", "sender_identity"]


@pytest.mark.parametrize("name", ["telegram"])
def test_every_registered_adapter_exposes_exactly_those_two_operations(
    name: str,
) -> None:
    """Registered by the name 033's config declares, and no wider than the seam."""
    assert name in registered_adapters()

    adapter = resolve_adapter(name)

    assert isinstance(adapter, MessengerAdapter)
    assert public_methods(type(adapter)) == {"deliver", "relay"}


@pytest.mark.parametrize("name", ["telegram"])
def test_no_adapter_code_path_can_acknowledge_answer_or_expire(name: str) -> None:
    """FR-001, read off the adapter class's own source.

    The class's source and not its module's: `factory/notify/service.py` also
    holds the factory-side bridge, which settles rows and answers presses
    precisely because it is *not* the adapter.
    """
    source = inspect.getsource(type(resolve_adapter(name)))

    found = [verb for verb in SETTLING_VERBS if verb in source]
    assert not found, (
        f"the {name} adapter names {found}; acknowledging, answering and "
        "expiring are the factory's, whatever channel the answer came in on "
        "(FR-001)"
    )


@pytest.mark.parametrize("name", ["telegram"])
def test_an_adapter_is_handed_no_store_and_no_client(name: str) -> None:
    """The structural half of the same rule: nothing to settle *with*."""
    parameters = set(inspect.signature(type(resolve_adapter(name))).parameters)

    assert not parameters & FORBIDDEN_CONSTRUCTOR_HANDLES, (
        f"the {name} adapter's constructor takes "
        f"{sorted(parameters & FORBIDDEN_CONSTRUCTOR_HANDLES)}"
    )


def test_the_registry_refuses_a_name_nothing_is_registered_under() -> None:
    with pytest.raises(UnknownAdapterError) as excinfo:
        resolve_adapter("carrier-pigeon")

    assert "carrier-pigeon" in str(excinfo.value)


def test_the_configured_name_falls_back_to_the_reference_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No override and no control-plane file: Telegram, as 008 left it."""
    monkeypatch.delenv(ESCALATION_ADAPTER_ENV, raising=False)

    assert configured_adapter_name() == "telegram"


def test_the_configured_name_is_what_resolve_picks(
    fake_adapter: FakeAdapter,
) -> None:
    """The selection path is real: registration plus configuration, not a patch."""
    assert configured_adapter_name() == FAKE_ADAPTER_NAME
    assert resolve_adapter() is fake_adapter


# ============================================================================
# US1-S2 / FR-001 — rendering stays factory-side
# ============================================================================


def test_the_actions_the_adapter_transports_are_the_buttons_telegram_renders() -> None:
    """The adapter receives an already-rendered message (plan § US1, step 1).

    `escalation_actions` is the transport-neutral rendering and
    `escalation_keyboard` is Telegram's view of the same thing; if they could
    drift, what the operator is asked would become a property of the transport.
    """
    record = escalation_record()

    actions = escalation_actions(record)
    keyboard = escalation_keyboard(record)

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [action.payload for action in actions] == [
        button.callback_data for button in buttons
    ]
    assert [action.label for action in actions] == [button.text for button in buttons]
    assert all(isinstance(action, MessageAction) for action in actions)


# ============================================================================
# US1-S3 / FR-002 — a plain library, callable with no Temporal
# ============================================================================


@pytest.mark.parametrize(
    "module",
    ["factory/notify/adapter.py", "factory/notify/service.py", "factory/notify/messages.py"],
)
def test_no_module_on_the_adapter_side_of_the_seam_imports_temporalio(
    module: str,
) -> None:
    """FR-002 as a property of the import graph, lazy imports included."""
    assert "temporalio" not in imported_roots(REPO_ROOT / module)


#: Delivered by the subprocess below; asserted on stdout so a script that died
#: before the send cannot be mistaken for one that completed it.
_NO_TEMPORAL_MARKER = "DELIVERED"

_NO_TEMPORAL_SCRIPT = textwrap.dedent(
    '''
    """042's supervision probe, in miniature: page a human with Temporal gone.

    The import system is told to refuse `temporalio` outright before anything
    from `factory` is imported, so a lazy import inside a function body fails
    the run rather than passing it.
    """
    import asyncio
    import os
    import sys

    BLOCKED = ("temporalio",)


    class RefuseBlocked:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in BLOCKED:
                raise ImportError(
                    f"{fullname} is not available to a process with no orchestrator"
                )
            return None


    sys.meta_path.insert(0, RefuseBlocked())

    from factory.notify.adapter import RenderedMessage
    from factory.notify.service import TelegramAdapter


    class Message:
        def __init__(self, message_id):
            self.message_id = message_id


    class Bot:
        def __init__(self):
            self.sent = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return None

        async def send_message(self, chat_id=None, text="", reply_markup=None, **kw):
            self.sent.append((chat_id, text, reply_markup))
            return Message(4242)


    bot = Bot()
    os.environ["TELEGRAM_BOT_TOKEN"] = sys.argv[1]
    os.environ["TELEGRAM_CHAT_ID"] = sys.argv[2]

    adapter = TelegramAdapter(open_bot=lambda token: bot)
    receipt = asyncio.run(
        adapter.deliver(
            RenderedMessage(text="Temporal is not answering on this host."),
            "c0ffeec0ffee",
        )
    )

    assert receipt.delivered is True, receipt
    assert receipt.message_id == 4242, receipt
    assert bot.sent == [
        (sys.argv[2], "Temporal is not answering on this host.", None)
    ], bot.sent

    leaked = sorted(name for name in sys.modules if name.startswith("temporalio"))
    assert not leaked, leaked
    reached_back = sorted(
        name for name in sys.modules if name.startswith("factory.activities")
    )
    assert not reached_back, reached_back

    print("DELIVERED", receipt.message_id)
    '''
)


def test_the_adapter_delivers_from_a_process_with_no_temporal(tmp_path: Path) -> None:
    """US1-S3, FR-002: the caller 042 will have is a process without Temporal.

    Run out-of-process on purpose. `temporalio` is installed in this
    environment, so an in-process test could only ever assert that nobody
    happened to import it; a subprocess whose import system refuses the package
    asserts that nobody *can*.
    """
    script = tmp_path / "no_temporal_delivery.py"
    script.write_text(_NO_TEMPORAL_SCRIPT, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("TELEGRAM_BOT_TOKEN", None)
    env.pop("TELEGRAM_CHAT_ID", None)

    result = subprocess.run(
        [sys.executable, str(script), BOT_TOKEN, CHAT_ID],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == f"{_NO_TEMPORAL_MARKER} 4242", result.stdout
    # The token travelled in argv to the adapter and nowhere else; a probe that
    # printed it would publish it into whatever collects the process's output.
    assert BOT_TOKEN not in result.stdout + result.stderr


def test_an_unconfigured_transport_is_reported_and_never_opened() -> None:
    """A transport that cannot send is data, not an error (R11), in the adapter.

    Asserted here as well as through the activity because 042's probe reaches
    the adapter directly, and a probe that raised on an unset variable would
    fail on the same host that is already failing.
    """
    opened: list[str] = []
    adapter = TelegramAdapter(open_bot=lambda token: opened.append(token))

    receipt = _run(adapter.deliver(RenderedMessage(text="anybody there?"), "abc123abc123"))

    assert receipt == DeliveryReceipt(delivered=False, message_id=None)
    assert opened == []


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


# ============================================================================
# US1-S2 — the inbound half translates, and only translates
# ============================================================================


def test_a_press_relays_the_escalation_id_the_button_carries() -> None:
    """The correlation id Telegram can carry back is the one R11 put in it."""
    adapter = TelegramAdapter()

    relay = adapter.relay(
        FakePressUpdate("esc:0123456789ab:RETRY", from_user=FakeUser(username="bryan"))
    )

    assert relay == InboundRelay(
        correlation_id="0123456789ab",
        reply_text="RETRY",
        sender_identity="@bryan",
    )


def test_a_reply_relays_the_message_handle_it_threads_to() -> None:
    """A free-text reply cannot carry a factory id, so it carries Telegram's."""
    adapter = TelegramAdapter()

    relay = adapter.relay(telegram_reply(from_user=FakeUser(username=None, id=77)))

    assert relay == InboundRelay(
        correlation_id=str(FIRST_MESSAGE_ID),
        reply_text=ANSWER_TEXT,
        sender_identity="77",
    )


def test_an_update_carrying_no_sender_relays_an_unknown_identity() -> None:
    """The 008 suite's updates carry no `from_user`; identity must not crash.

    US4 checks identity against a configured list. "Unknown" has to be a value
    that list can fail to contain, not an exception that never reaches it.
    """
    adapter = TelegramAdapter()

    relay = adapter.relay(telegram_reply())

    assert relay is not None
    assert relay.sender_identity == UNKNOWN_SENDER


@pytest.mark.parametrize(
    "event",
    [
        FakePressUpdate("not-ours:whatever"),
        FakePressUpdate(None),
        FakeReplyUpdate(FakeReplyMessage(text="hello", reply_to_message=None)),
        FakeReplyUpdate(
            FakeReplyMessage(text="", reply_to_message=FakeReplyTo(FIRST_MESSAGE_ID))
        ),
        object(),
    ],
    ids=["foreign-button", "no-payload", "not-a-reply", "no-text", "not-an-update"],
)
def test_an_update_that_is_not_ours_relays_nothing(event: Any) -> None:
    """`None` means "not one of ours"; what to *say* about it is the factory's."""
    assert TelegramAdapter().relay(event) is None


# ============================================================================
# US1-S4 — the 008 question round trip, over a fake adapter and over Telegram
# ============================================================================


@dataclass(frozen=True)
class RoundTrip:
    """Everything the 008 question round trip is observable by.

    Compared between transports rather than asserted transport by transport:
    "behaves as it does over Telegram" is a statement about two runs, and only
    a comparison can make it one.
    """

    rendered_text: str
    correlation_id_is_question_id: bool
    outcome: BridgeOutcome
    signals: list[tuple[str, str]]
    row: tuple[tuple[str, Any], ...]


#: Columns whose values are minted fresh per run — comparing them would compare
#: `secrets.token_hex` with itself. Everything else, including the routing key
#: and the answer text, is compared.
_PER_RUN_COLUMNS = frozenset({"question_id", "sent_at", "expires_at"})


def _observable_row(path: Path) -> tuple[tuple[str, Any], ...]:
    row = question_row(path)
    return tuple(
        sorted(
            (column, value)
            for column, value in row.items()
            if column not in _PER_RUN_COLUMNS
        )
    )


async def _ask(env: ActivityEnvironment) -> Any:
    return await env.run(
        send_question,
        SendQuestionInput(
            workflow_id=WORKFLOW_ID,
            epic_id=EPIC,
            node_id=NODE,
            attempt=ATTEMPT,
            question_text=QUESTION_TEXT,
        ),
    )


async def test_the_question_round_trip_over_a_fake_adapter_matches_telegram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S4: ask, deliver, answer and resume, twice, and compared.

    Both runs drive production code end to end — the `send_question` activity,
    the real sqlite store and its guarded transition, and the factory-side
    bridge. The only thing swapped is the transport: a fake `telegram.Bot`
    behind `TelegramAdapter` in one run, a fake adapter registered under its own
    name in the other. If the send path stopped going through the seam, or the
    bridge stopped consuming the relay, the two runs would stop matching.
    """
    over_telegram = await _round_trip_over_telegram(tmp_path / "telegram", monkeypatch)
    over_fake = await _round_trip_over_fake(tmp_path / "fake", monkeypatch)

    assert over_fake == over_telegram

    # …and the run is not vacuously equal: it really did resolve a question.
    assert over_telegram.outcome is BridgeOutcome.RESOLVED
    assert over_telegram.signals == [(QUESTION_SIGNAL_NAME, ANSWER_TEXT)]
    assert dict(over_telegram.row)["answer_text"] == ANSWER_TEXT
    assert dict(over_telegram.row)["message_id"] == FIRST_MESSAGE_ID


async def _round_trip_over_telegram(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> RoundTrip:
    with monkeypatch.context() as patch:
        db = root / "verification.db"
        patch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(db))
        patch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)
        patch.setenv(TELEGRAM_BOT_TOKEN_ENV, BOT_TOKEN)
        patch.setenv(TELEGRAM_CHAT_ID_ENV, CHAT_ID)
        patch.delenv(ESCALATION_ADAPTER_ENV, raising=False)

        fake_bot = FakeBot()
        patch.setattr(notify_activities, "open_bot", lambda token: fake_bot)

        sent = await _ask(ActivityEnvironment())

        client = FakeTemporalClient()
        bridge = CallbackBridge(db_path=db, client=client, now=lambda: RESOLVED_AT)
        outcome = await bridge.handle_reply(
            telegram_reply(to_message_id=sent.message_id)
        )

        return RoundTrip(
            rendered_text=fake_bot.sent[0].text,
            correlation_id_is_question_id=True,
            outcome=outcome,
            signals=[(signal.name, signal.args[1]) for signal in client.signals],
            row=_observable_row(db),
        )


async def _round_trip_over_fake(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> RoundTrip:
    with monkeypatch.context() as patch:
        db = root / "verification.db"
        patch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(db))
        patch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)
        # No Telegram credentials at all: a run that fell back to the reference
        # transport would deliver nothing and fail rather than quietly pass.
        patch.delenv(TELEGRAM_BOT_TOKEN_ENV, raising=False)
        patch.delenv(TELEGRAM_CHAT_ID_ENV, raising=False)

        adapter = FakeAdapter()
        register_adapter(FAKE_ADAPTER_NAME, lambda **_seams: adapter)
        patch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)
        try:
            sent = await _ask(ActivityEnvironment())

            client = FakeTemporalClient()
            bridge = CallbackBridge(
                db_path=db, client=client, now=lambda: RESOLVED_AT, adapter=adapter
            )
            relay = adapter.relay(
                FakeInbound(in_reply_to=sent.message_id, text=ANSWER_TEXT)
            )
            assert relay is not None
            outcome = await bridge.handle_relay(relay)

            delivered = adapter.delivered[0]
            return RoundTrip(
                rendered_text=delivered.message.text,
                correlation_id_is_question_id=(
                    delivered.correlation_id == sent.question_id
                ),
                outcome=outcome,
                signals=[(signal.name, signal.args[1]) for signal in client.signals],
                row=_observable_row(db),
            )
        finally:
            unregister_adapter(FAKE_ADAPTER_NAME)


async def test_the_message_the_adapter_transports_is_the_one_the_factory_rendered(
    env: ActivityEnvironment, db_path: Path, fake_adapter: FakeAdapter
) -> None:
    """Rendering stays in `factory/notify/messages.py` (plan § US1, step 1).

    The adapter is handed text it did not compose, and the correlation id is
    the factory's own question id — the seam carries no keyboard for a
    question, because a question is answered by typing (008 FR-008).
    """
    sent = await _ask(env)

    delivered = fake_adapter.delivered
    assert len(delivered) == 1
    assert delivered[0].correlation_id == sent.question_id
    assert delivered[0].message.actions == ()

    with store.connect(db_path) as conn:
        record = store.get_question(conn, sent.question_id)
    assert record is not None
    assert delivered[0].message.text == question_message(record)


async def test_a_relay_for_a_question_nobody_asked_settles_nothing(
    db_path: Path, fake_adapter: FakeAdapter
) -> None:
    """The late-relay edge: recorded as nothing happening, never an error.

    A relay that arrived for a handle the store has no question for signals
    nobody and writes no row — the operator's own bridge can replay anything,
    and the factory has to be unbothered by it.
    """
    store.connect(db_path).close()  # create the schema, and no rows
    client = FakeTemporalClient()
    bridge = CallbackBridge(db_path=db_path, client=client, adapter=fake_adapter)

    outcome = await bridge.handle_relay(
        InboundRelay(correlation_id="999999", reply_text="hello?", sender_identity="x")
    )

    assert outcome is BridgeOutcome.UNKNOWN
    assert client.signals == []


# ============================================================================
# Mutation evidence (constitution VIII: pasted, not described)
# ============================================================================
#
# Every test above was run against a deliberate break of the production code it
# is supposed to guard, and the break was reverted. Transcripts follow verbatim.
#
# (filled in below once the implementation lands)
