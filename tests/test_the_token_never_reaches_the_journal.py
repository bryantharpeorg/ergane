"""The bot token never reaches the journal, and the request stays visible.

064-US1. `factory/supervision/units.py:425` states the commitment this file
defends: an operator's credentials are not written to disk in a file the journal
echoes back. The journal broke it anyway, from a direction nothing here owned —
`python-telegram-bot` builds its own `httpx` client, and httpx logs every request
line at INFO with the full URL, and a Telegram URL *is*
`https://api.telegram.org/bot<TOKEN>/sendMessage`. Every escalation, every
long-poll, printed the credential into a file operators paste into chat windows.

What is asserted here, and why each assertion is shaped the way it is:

- **The send really happened.** A "the token is not in the logs" assertion passes
  trivially when nothing was sent, nothing was logged, or the token was empty
  (plan trap 2). So each test drives the adapter against a real `httpx` client on
  a `MockTransport` — the actual library that emits the actual leaking line, with
  no socket — and asserts the request was made, that records were captured, and
  only then that the credential is absent.
- **The leak is demonstrated before it is fixed.** `unredacted` strips the
  protection at the top of every test, and the tests that install it assert the
  token *is* rendered first. A test for an absence that never observed the
  presence proves nothing about the mechanism.
- **The line survives.** Silencing `httpx` to WARNING would pass an
  absence assertion and cost an operator every request line they debug delivery
  failures with (trap 1). US1-S2 is asserted positively: host, operation and
  status still read back.
- **Nobody has to remember.** US1-S3 pins both entry points; US1-S4 pins that
  constructing an adapter is itself enough, with no logging configured by the
  caller. A convention that must be remembered is forgotten by the next adapter,
  which is why US1-S5 pins the webhook — same shape, secret-bearing URL, and the
  next instance of this spec if it were left out.

The fake token is distinctive and token-shaped on purpose: shaped, so it
exercises the pattern rule a never-registered credential falls back on; and
distinctive, so an assertion cannot pass by matching something innocuous.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import inspect
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import pytest

from factory.notify import redact
from factory.notify.adapter import MessageAction, RenderedMessage
from factory.notify.redact import REDACTED, configure_logging, install_redaction
from factory.notify.service import BOT_TOKEN_ENV, CHAT_ID_ENV, TelegramAdapter
from factory.notify.webhook import WEBHOOK_URL_ENV, WebhookAdapter

#: Distinctive, and shaped like the real thing (`<digits>:<secret>`) so the
#: pattern rule is exercised as well as the registered value.
FAKE_TOKEN = "8100000042:AAFake-do-not-log-me-0000000000000000000"

#: A webhook whose secret is its path, which is how Slack, Discord and most
#: incoming-webhook endpoints are configured (US1-S5).
FAKE_WEBHOOK_URL = "https://hooks.example.test/services/T000/B000/FakeHookSecret"

#: The origin of that URL — what an operator still needs to see afterwards.
FAKE_WEBHOOK_ORIGIN = "https://hooks.example.test"

#: The two processes an operator runs, and the two journals this story is about.
ENTRY_POINTS = ("factory.worker", "factory.notify.service")

MESSAGE = RenderedMessage(
    text="node n1 has run out of attempts",
    actions=(MessageAction(label="Kill", payload="esc:0123456789ab:KILL"),),
)


# --- capturing a journal, and starting each test without the protection ------


class _Journal(logging.Handler):
    """Every record emitted while it is attached, rendered as a handler would.

    `rendered` matters as much as `messages`: a traceback reaches the journal
    through the formatter, not through `getMessage`, and trap 4 is about exactly
    that path.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self._formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]

    @property
    def rendered(self) -> list[str]:
        return [self._formatter.format(record) for record in self.records]

    def text(self) -> str:
        return "\n".join(self.rendered)


@contextlib.contextmanager
def journal_at_info() -> Iterator[_Journal]:
    """Capture what a worker journal would hold, with `httpx` at INFO.

    The level is the *precondition of the leak*, not part of the protection: the
    line only exists at INFO, and INFO is what both entry points configure. What
    no test here configures is any redaction — that is what is under test.
    """
    handler = _Journal()
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    previous_root_level, previous_httpx_level = root.level, httpx_logger.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    httpx_logger.setLevel(logging.NOTSET)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_root_level)
        httpx_logger.setLevel(previous_httpx_level)


@pytest.fixture(autouse=True)
def unredacted() -> Iterator[None]:
    """Start every test in the leaking world, and leave the process as found.

    The protection is process-global by design (US1-S4: it cannot depend on a
    caller remembering anything), so without this a test could inherit an
    install from an earlier one and assert an absence the mechanism under test
    never produced.
    """
    previous_factory = logging.getLogRecordFactory()
    previous_hook = sys.excepthook
    previous_secrets = dict(redact._SECRETS)

    bare = previous_factory
    while getattr(bare, "__ergane_redacting__", False):
        bare = bare.__ergane_wrapped__
    logging.setLogRecordFactory(bare)
    sys.excepthook = sys.__excepthook__
    redact._SECRETS.clear()
    try:
        yield
    finally:
        logging.setLogRecordFactory(previous_factory)
        sys.excepthook = previous_hook
        redact._SECRETS.clear()
        redact._SECRETS.update(previous_secrets)


# --- a Telegram that answers without a socket --------------------------------


def telegram_on_a_mock_transport(
    seen: list[httpx.Request],
) -> Callable[[str], Any]:
    """An `open_bot` whose bot is real, whose transport is not.

    The point of substituting the *transport* rather than the bot is that the
    leaking code stays in the picture: `python-telegram-bot` builds its own
    `httpx.AsyncClient` (plan trap 12) and that client emits the `HTTP Request:`
    line this story is about, token and all. A `FakeBot` would prove nothing —
    it never logs a URL.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getMe":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "id": 42,
                        "is_bot": True,
                        "first_name": "Stub",
                        "username": "stub_bot",
                    },
                },
            )
        if method == "sendMessage":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 7,
                        "date": 1700000000,
                        "chat": {"id": 99, "type": "private"},
                        "text": MESSAGE.text,
                    },
                },
            )
        return httpx.Response(404, json={"ok": False, "description": "not stubbed"})

    def open_bot(token: str) -> Any:
        from telegram import Bot
        from telegram.request import HTTPXRequest

        transport = httpx.MockTransport(handle)
        return Bot(
            token,
            request=HTTPXRequest(httpx_kwargs={"transport": transport}),
            get_updates_request=HTTPXRequest(httpx_kwargs={"transport": transport}),
        )

    return open_bot


async def send_one_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, list[httpx.Request], _Journal]:
    """One real send through one real httpx client, captured at INFO."""
    monkeypatch.setenv(BOT_TOKEN_ENV, FAKE_TOKEN)
    monkeypatch.setenv(CHAT_ID_ENV, "99")

    seen: list[httpx.Request] = []
    adapter = TelegramAdapter(open_bot=telegram_on_a_mock_transport(seen))
    with journal_at_info() as captured:
        receipt = await adapter.deliver(MESSAGE, correlation_id="esc-1")
    return receipt, seen, captured


# --- US1-S1: the token is not in the journal ---------------------------------


async def test_a_telegram_send_writes_no_token_to_the_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S1. Three assertions, because any one alone passes vacuously.

    The send happened, something was written down about it, and the credential
    is in none of it (trap 2).
    """
    receipt, seen, captured = await send_one_escalation(monkeypatch)

    # 1. The send occurred — against the real Bot API shapes, over the real
    #    client, and Telegram's own `message_id` came back.
    assert receipt.delivered is True
    assert receipt.message_id == 7
    assert [request.url.path.rsplit("/", 1)[-1] for request in seen] == [
        "getMe",
        "sendMessage",
    ]

    # 2. The journal is not empty — an absence in an empty journal is not
    #    evidence of anything.
    assert captured.records, "nothing was logged; the absence below proves nothing"

    # 3. The credential is in none of it, in any rendering.
    assert FAKE_TOKEN not in captured.text()
    assert not [message for message in captured.messages if FAKE_TOKEN in message]


# --- US1-S2: and the request is still visible --------------------------------


async def test_the_request_is_still_observable_in_redacted_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S2. The line survives; only the secret leaves it (trap 1).

    Setting `httpx` to WARNING would satisfy S1 and cost the operator every
    request line they debug a delivery failure with. What is asserted here is
    what such a fix would delete: the host, the operation, and the status.
    """
    _, _, captured = await send_one_escalation(monkeypatch)

    request_lines = [
        message for message in captured.messages if "sendMessage" in message
    ]
    assert request_lines, captured.messages

    line = request_lines[-1]
    assert "api.telegram.org" in line
    assert "200" in line
    assert REDACTED in line, line
    assert FAKE_TOKEN not in line


# --- US1-S3: both entry points, not one --------------------------------------


def main_block(module: Any) -> ast.If:
    """The `if __name__ == "__main__":` guard of a module, from its own source."""
    source = Path(inspect.getsourcefile(module) or "").read_text()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            return node
    raise AssertionError(f"{module.__name__} has no process entry point")


def called_names(node: ast.AST) -> set[str]:
    """Every callee spelled as it is written, e.g. `logging.basicConfig`."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            names.add(ast.unparse(child.func))
    return names


@pytest.mark.parametrize("module_name", ENTRY_POINTS)
def test_both_entry_points_configure_a_redacting_journal(module_name: str) -> None:
    """US1-S3. The worker and the operator bridge, or the fix leaks from one.

    Two claims, because either alone is satisfiable without the other: the entry
    point's logging configuration *is* the redacting one — asserted against the
    real `__main__` block and the object the name resolves to, not a grep — and
    that configuration actually redacts.
    """
    module = importlib.import_module(module_name)

    configured = called_names(main_block(module))
    assert "configure_logging" in configured, configured
    # The bare call is what used to be here, and what a future edit would
    # reintroduce: it configures a journal with no protection in it.
    assert "logging.basicConfig" not in configured, configured
    assert module.configure_logging is configure_logging

    with journal_at_info() as captured:
        logging.getLogger("httpx").info("HTTP Request: POST %s", telegram_url())
        assert FAKE_TOKEN in captured.text(), "the leak is not reproduced"

    module.configure_logging()

    with journal_at_info() as captured:
        logging.getLogger("httpx").info("HTTP Request: POST %s", telegram_url())
    assert captured.records
    assert FAKE_TOKEN not in captured.text()
    assert "api.telegram.org" in captured.text()


def telegram_url() -> str:
    return f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"


# --- US1-S4: constructing the adapter is enough ------------------------------


def test_constructing_an_adapter_is_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    """US1-S4. No `basicConfig`, no `install_redaction`, no convention to recall.

    A protection the caller has to switch on is a protection the next caller
    forgets. This asserts the negative first — the same emission leaks before
    the adapter exists — so the assertion after it cannot pass vacuously.
    """
    with journal_at_info() as leaking:
        logging.getLogger("httpx").info("HTTP Request: POST %s", telegram_url())
    assert FAKE_TOKEN in leaking.text(), "the leak is not reproduced"

    TelegramAdapter()

    with journal_at_info() as captured:
        logging.getLogger("httpx").info("HTTP Request: POST %s", telegram_url())
    assert captured.records
    assert FAKE_TOKEN not in captured.text()
    assert "api.telegram.org" in captured.text()


def test_constructing_the_webhook_adapter_is_enough() -> None:
    """US1-S4, for the other adapter. Neither may depend on the caller."""
    WebhookAdapter()

    with journal_at_info() as captured:
        logging.getLogger("httpx").info("HTTP Request: POST %s", telegram_url())
    assert captured.records
    assert FAKE_TOKEN not in captured.text()


# --- US1-S5: the webhook is the next instance, not a nice-to-have ------------


async def test_a_webhook_send_writes_no_url_secret_to_the_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S5. A secret in the path is an ordinary webhook configuration.

    The same three assertions as S1 — the POST happened, the journal is not
    empty, the secret is absent — plus S2's other half: the origin and the
    status still read back, so an operator can still see where the escalation
    went and whether it landed.
    """
    monkeypatch.setenv(WEBHOOK_URL_ENV, FAKE_WEBHOOK_URL)

    seen: list[httpx.Request] = []

    async def post(endpoint: str, body: dict[str, Any]) -> int:
        # The production poster's body, verbatim (`factory/notify/webhook.py`):
        # a real client on a mock transport, so the real `HTTP Request:` line is
        # what the journal receives.
        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            response = await http.post(endpoint, json=body)
        return int(response.status_code)

    adapter = WebhookAdapter(post=post)
    with journal_at_info() as captured:
        receipt = await adapter.deliver(MESSAGE, correlation_id="esc-1")

    assert receipt.delivered is True
    assert [str(request.url) for request in seen] == [FAKE_WEBHOOK_URL]
    assert captured.records, "nothing was logged; the absence below proves nothing"

    assert "FakeHookSecret" not in captured.text()
    assert FAKE_WEBHOOK_URL not in captured.text()

    request_lines = [
        message for message in captured.messages if FAKE_WEBHOOK_ORIGIN in message
    ]
    assert request_lines, captured.messages
    assert "200" in request_lines[-1]
    assert REDACTED in request_lines[-1]


# --- Edge case: a traceback is a rendering too -------------------------------


def a_real_status_error() -> httpx.HTTPStatusError:
    """The exception httpx raises for a rejected Telegram call.

    Its message quotes the URL it failed on, which is why a 401 — the most
    likely error an operator has, since it means the token is wrong — is the one
    that hands them the token back (trap 4).
    """
    request = httpx.Request("POST", telegram_url())
    response = httpx.Response(401, request=request, json={"ok": False})
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc
    raise AssertionError("raise_for_status did not raise on a 401")


def test_a_traceback_does_not_render_the_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Edge case, trap 4: the paste-into-chat path.

    httpx puts the failing URL in the exception's own message, so both renderings
    of it leak: a logged traceback, and the uncaught traceback the interpreter
    prints to stderr. Both are asserted, and both keep the exception's class and
    the host so the failure is still diagnosable.
    """
    exc = a_real_status_error()
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert FAKE_TOKEN in rendered, "the leak is not reproduced"

    TelegramAdapter()

    with journal_at_info() as captured:
        logging.getLogger("factory.notify.service").error(
            "esc-1: not delivered", exc_info=exc
        )
    assert captured.records
    assert FAKE_TOKEN not in captured.text()
    assert "HTTPStatusError" in captured.text()
    assert "api.telegram.org" in captured.text()

    sys.excepthook(type(exc), exc, exc.__traceback__)
    printed = capsys.readouterr().err
    assert printed, "the excepthook rendered nothing"
    assert FAKE_TOKEN not in printed
    assert "HTTPStatusError" in printed


def test_install_is_idempotent_and_keeps_a_callers_own_record_factory() -> None:
    """Installed twice is installed once, and it composes rather than replaces.

    The mechanism is a process-global seam, so a second install that wrapped the
    first would redact twice per record and grow a chain per adapter
    constructed; one that clobbered a caller's own factory would silently drop
    whatever they had put on their records.
    """
    marks: list[str] = []

    def caller_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = logging.LogRecord(*args, **kwargs)
        marks.append(record.name)
        return record

    logging.setLogRecordFactory(caller_factory)
    install_redaction()
    first = logging.getLogRecordFactory()
    install_redaction()
    assert logging.getLogRecordFactory() is first

    with journal_at_info() as captured:
        logging.getLogger("httpx").info("HTTP Request: POST %s", telegram_url())

    assert marks, "the caller's own record factory was replaced, not wrapped"
    assert FAKE_TOKEN not in captured.text()
