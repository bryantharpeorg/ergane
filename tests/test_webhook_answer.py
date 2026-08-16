"""Any messenger, and only authorized answers.

041-US4. Two things ship together here on purpose. `webhook` is the second
adapter — the universal glue an operator bridges Signal, Slack or a wall
display with — and it is also the adapter that *introduces an identity
problem*, because Telegram never had one: a single chat is the identity. So the
second transport and the rule that decides whether a reply may become an answer
land in the same story.

What each test is built to fail against is stated where it sits; the mutations
were run and the transcripts are pasted at the bottom of this file verbatim
(constitution VIII / D-037).

Three design facts a reader needs before the assertions make sense:

- **The authorization check is factory-side, not adapter-side (FR-001, FR-011).**
  An adapter that filtered replies would be deciding answer-or-not, which is the
  one decision the seam exists to keep out of the transport. It is also not
  workflow-side: it reads the control-plane file, and workflow code may read
  neither files nor the environment (constitution IV, FR-012). It lives in
  `CallbackBridge`, which is where an inbound reply already meets every other
  is-this-an-answer question, and by the time a signal crosses the workflow
  boundary the sender has already been checked.

- **`ergane answer` is not a second settling core.** It builds the webhook
  adapter's three inbound terms and hands them to `CallbackBridge.handle_relay`
  — the same core a Telegram reply reaches. There is exactly one place that
  signals a workflow and settles a row, and this verb is not it.

- **An unauthorized reply is recorded, never silently dropped.** A drop that
  logs nothing is indistinguishable from a message that was lost in transit, so
  the identity and the correlation id are written to the log and the outcome is
  its own value rather than a reused one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import closing
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, NamedTuple

import pytest
from temporalio import workflow
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.notify_activities import (
    SendQuestionInput,
    send_question,
)
from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.cli import nouns
from factory.cli.main import main as ergane_main
from factory.controlplane.config import KNOWN_ESC_ADAPTERS
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    UNKNOWN_SENDER,
    DeliveryReceipt,
    InboundRelay,
    RenderedMessage,
    resolve_adapter,
)
from factory.notify.service import (
    QUESTION_SIGNAL_NAME,
    BridgeOutcome,
    CallbackBridge,
    configured_responders,
)
from factory.notify.webhook import (
    WEBHOOK_ADAPTER,
    WEBHOOK_URL_ENV,
    WebhookAdapter,
)
from factory.verify import store

from tests.test_messenger_adapter import (
    FakeTemporalClient,
    FakeUser,
    telegram_reply,
)

EPIC = "041-escalation-workflow"
NODE = "us4"
ATTEMPT = 1

QUESTION_TEXT = (
    "The webhook has no chat, so who is allowed to answer it?\n"
    "Telegram never had to say; a bridged messenger does."
)

ANSWER_TEXT = "ship it"

#: The operator the configured list admits, and one it does not. Spelled the way
#: `TelegramAdapter._identity` spells a username so one list can cover both
#: transports — an authorized-responders list is about people, not protocols.
AUTHORIZED = "@bryan"
INTRUDER = "@not-bryan"

RESOLVED_AT = "2026-08-16T15:04:00Z"

#: The workflow a question parks, in this file's own namespace. 008 parks the
#: epic workflow on `question_answered`; US3 moves that park into a child. Either
#: way the row's `workflow_id` names whoever is waiting, and this is a stand-in
#: for it that can actually be observed resuming.
WAITER_QUEUE = "webhook-answers-under-test"


# --- the world ---------------------------------------------------------------


@workflow.defn
class WaitingForAnswer:
    """A workflow parked on `question_answered`, and nothing else.

    Deliberately minimal: the claim in US4-S1 is that `ergane answer` *resumes
    the waiting workflow with that text*, which a recorded signal only
    approximates. This one completes with the answer it was given, so the
    assertion is the workflow's own result rather than a fake's log.
    """

    def __init__(self) -> None:
        self._answer = ""

    @workflow.signal(name=QUESTION_SIGNAL_NAME)
    def question_answered(self, question_id: str, answer_text: str) -> None:
        self._answer = answer_text

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: bool(self._answer))
        return self._answer


@dataclass(frozen=True)
class Posted:
    """One POST the listener received, in the terms the seam promised."""

    path: str
    document: dict[str, Any]


class Listener:
    """A real HTTP endpoint on an ephemeral loopback port.

    Ephemeral and loopback on purpose: other nodes share this host, and a fixed
    port is a collision waiting for the second concurrent run. `posted` is what
    the operator's own bridge would have received.
    """

    def __init__(self) -> None:
        self.posted: list[Posted] = []
        self.status = 200
        listener = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8")
                listener.posted.append(Posted(self.path, json.loads(body)))
                self.send_response(listener.status)
                self.end_headers()

            def log_message(self, *_args: Any) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/escalations"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        code = ergane_main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def listener() -> Iterator[Listener]:
    endpoint = Listener()
    try:
        yield endpoint
    finally:
        endpoint.close()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)
    return path


@pytest.fixture
def webhook(listener: Listener, monkeypatch: pytest.MonkeyPatch) -> Listener:
    """A worker paging over the webhook, selected the way an operator selects it."""
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, WEBHOOK_ADAPTER)
    monkeypatch.setenv(WEBHOOK_URL_ENV, listener.url)
    return listener


@pytest.fixture
def no_control_plane(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No config file: unrestricted, which is what every 008 deployment is."""
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(tmp_path / "absent.toml"))
    monkeypatch.delenv(FACTORY_CONFIG_PATH_ENV, raising=False)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@pytest.fixture
def run_async(capsys: pytest.CaptureFixture[str]) -> Callable[..., Awaitable[Run]]:
    async def invoke(*argv: str) -> Run:
        code = await asyncio.to_thread(_invoke, argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


# --- helpers -----------------------------------------------------------------


def a_question(workflow_id: str) -> SendQuestionInput:
    return SendQuestionInput(
        workflow_id=workflow_id,
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        question_text=QUESTION_TEXT,
    )


def question(db_path: Path, question_id: str) -> Any:
    with closing(store.connect(db_path)) as conn:
        return store.get_question(conn, question_id)


def relay_from(correlation_id: str, text: str, identity: str) -> InboundRelay:
    """The three terms, produced by the webhook adapter's own translation.

    Built through `relay` rather than by hand so a test that says "an inbound
    reply" is describing the same path `ergane answer` takes.
    """
    built = resolve_adapter(WEBHOOK_ADAPTER).relay(
        {
            "correlation_id": correlation_id,
            "reply_text": text,
            "sender_identity": identity,
        }
    )
    assert built is not None
    return built


def write_config(path: Path, *, responders: str) -> Path:
    path.write_text(
        "version = 1\n\n"
        '[llm]\nmode = "gateway"\nbase_url = "http://llm.local/v1"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n\n'
        '[memory]\nbackend = "none"\n\n'
        '[temporal]\nmode = "external"\naddress = "127.0.0.1:7233"\n'
        'namespace = "ergane"\n\n'
        "[telemetry]\n\n"
        f'[escalation]\nadapter = "webhook"\nauthorized_responders = {responders}\n',
        encoding="utf-8",
    )
    return path


# ============================================================================
# T024 — US4-S1 / FR-003: the webhook round trip
# ============================================================================


async def test_a_question_posts_the_rendered_message_and_the_correlation_id(
    db_path: Path, webhook: Listener
) -> None:
    """US4-S1's outbound half, against a real socket rather than a double.

    The listener is an actual HTTP server, so what is asserted is what an
    operator's own bridge would receive. The rendered text comes from
    `factory/notify/messages.py`, which the adapter never composes: an adapter
    that wrote its own message would make what the operator is asked a property
    of the transport.
    """
    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))

    assert len(webhook.posted) == 1
    document = webhook.posted[0].document
    assert document["correlation_id"] == sent.question_id
    assert QUESTION_TEXT in document["text"]
    assert document["actions"] == []

    record = question(db_path, sent.question_id)
    assert record is not None
    assert record.message_id is None, (
        "a webhook mints no message handle, which is exactly why `ergane answer` "
        "has to route by the factory's own id"
    )


async def test_ergane_answer_resumes_the_waiting_workflow_with_that_text(
    env: WorkflowEnvironment,
    db_path: Path,
    webhook: Listener,
    no_control_plane: None,
    monkeypatch: pytest.MonkeyPatch,
    run_async: Callable[..., Awaitable[Run]],
) -> None:
    """US4-S1 end to end: ask over the webhook, answer at the CLI, resume.

    The workflow is real and really parked, so "resumes the waiting workflow
    with that text" is its own result and not a recorded call. The question's
    row carries no message id — the webhook minted none — so a verb that had
    kept Telegram's message-handle routing would find nothing here.
    """
    async with Worker(
        env.client,
        task_queue=WAITER_QUEUE,
        workflows=[WaitingForAnswer],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        waiting = await env.client.start_workflow(
            WaitingForAnswer.run, id="waiting-on-us4", task_queue=WAITER_QUEUE
        )
        sent = await ActivityEnvironment().run(
            send_question, a_question(waiting.id)
        )
        assert webhook.posted[0].document["correlation_id"] == sent.question_id

        async def open_client() -> Any:
            return env.client

        monkeypatch.setattr(nouns, "_open_client", open_client)

        answered = await run_async(
            "answer", sent.question_id, ANSWER_TEXT, "--as", AUTHORIZED
        )
        assert answered.code == 0, answered.stderr
        assert sent.question_id in answered.stdout

        assert await waiting.result() == ANSWER_TEXT

    record = question(db_path, sent.question_id)
    assert record is not None
    assert record.resolution == store.ANSWERED
    assert record.answer_text == ANSWER_TEXT


@pytest.mark.parametrize(
    ("outcome", "phrase"),
    [
        (BridgeOutcome.UNKNOWN, "no question this factory ever asked"),
        (BridgeOutcome.ALREADY_RESOLVED, "already answered"),
        (BridgeOutcome.EXPIRED, "expired"),
    ],
)
async def test_an_id_with_nothing_waiting_says_which_of_the_three_it_was(
    db_path: Path,
    webhook: Listener,
    no_control_plane: None,
    monkeypatch: pytest.MonkeyPatch,
    run_async: Callable[..., Awaitable[Run]],
    outcome: BridgeOutcome,
    phrase: str,
) -> None:
    """T029: answered, expired, or never existed — not one generic failure.

    Driven through the real verb against a real store: the row is put into each
    terminal state and the settling core is what classifies it, so a verb that
    printed a single "could not answer" line fails on two of the three.
    """
    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))
    with closing(store.connect(db_path)) as conn:
        if outcome is BridgeOutcome.ALREADY_RESOLVED:
            assert store.resolve_question(
                conn, sent.question_id, answer_text="already", resolved_at=RESOLVED_AT
            )
        elif outcome is BridgeOutcome.EXPIRED:
            assert store.expire_question(
                conn, sent.question_id, resolved_at=RESOLVED_AT
            )

    async def open_client() -> Any:
        return FakeTemporalClient()

    monkeypatch.setattr(nouns, "_open_client", open_client)

    correlation = "0" * 12 if outcome is BridgeOutcome.UNKNOWN else sent.question_id
    reported = await run_async("answer", correlation, ANSWER_TEXT)

    assert reported.code == 1
    assert phrase in reported.stderr
    assert correlation in reported.stderr


# ============================================================================
# T025 — US4-S2 / FR-011: an unauthorized reply is refused and recorded
# ============================================================================


async def test_an_unauthorized_reply_does_not_resume_and_is_recorded(
    db_path: Path,
    webhook: Listener,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """US4-S2: no signal, no state change, no touched clock — and a record.

    Every half of the scenario is asserted separately because they fail
    separately: a check that refused the reply but settled the row would satisfy
    "does not resume", and one that dropped it silently would satisfy everything
    except the sentence that makes a drop distinguishable from a lost message.
    """
    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))
    before = question(db_path, sent.question_id)
    assert before is not None

    client = FakeTemporalClient()
    bridge = CallbackBridge(
        db_path=db_path,
        client=client,
        now=lambda: RESOLVED_AT,
        authorized_responders=(AUTHORIZED,),
    )

    with caplog.at_level(logging.WARNING):
        outcome = await bridge.handle_relay(
            relay_from(sent.question_id, "kill it", INTRUDER)
        )

    assert outcome is BridgeOutcome.UNAUTHORIZED
    assert client.signals == []

    after = question(db_path, sent.question_id)
    assert after is not None
    assert after.resolution is None
    assert after.answer_text is None
    assert after.expires_at == before.expires_at, "the expiry clock was touched"

    recorded = "\n".join(record.getMessage() for record in caplog.records)
    assert INTRUDER in recorded, "an unauthorized reply that logs nothing is a lost one"
    assert sent.question_id in recorded


async def test_an_unauthorized_press_is_refused_on_the_button_path_too(
    db_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard covers every act behind it, not only the one it was added for.

    `CallbackBridge` has two inbound entries — a press and a reply — and they do
    not share a settling core. A guard proven on one of them is a guard proven
    on one of them; this is the other. Driven over Telegram's own update shape,
    because the rule is about people and not about which transport carried them.
    """
    monkeypatch.delenv(ESCALATION_ADAPTER_ENV, raising=False)
    store.connect(db_path).close()
    client = FakeTemporalClient()
    bridge = CallbackBridge(
        db_path=db_path,
        client=client,
        now=lambda: RESOLVED_AT,
        authorized_responders=(AUTHORIZED,),
    )

    update = telegram_reply(from_user=FakeUser(username="not-bryan"))
    with caplog.at_level(logging.WARNING):
        outcome = await bridge.handle_reply(update)

    assert outcome is BridgeOutcome.UNAUTHORIZED
    assert client.signals == []
    assert INTRUDER in "\n".join(r.getMessage() for r in caplog.records)


async def test_the_authorized_list_is_read_from_the_control_plane_file(
    tmp_path: Path,
    db_path: Path,
    webhook: Listener,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-011's list is `escalation.authorized_responders`, really parsed.

    A bridge built without an explicit list must find the operator's declared
    one. Asserted through a real config file rather than a patched attribute:
    the failure this guards against is a field that parses and reaches nobody,
    which is exactly how `check_evidence` was dropped for three weeks.
    """
    monkeypatch.setenv(
        ERGANE_CONFIG_PATH_ENV,
        str(write_config(tmp_path / "config.toml", responders=f'["{AUTHORIZED}"]')),
    )
    monkeypatch.delenv(FACTORY_CONFIG_PATH_ENV, raising=False)
    assert configured_responders() == (AUTHORIZED,)

    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))
    client = FakeTemporalClient()
    bridge = CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)

    refused = await bridge.handle_relay(
        relay_from(sent.question_id, ANSWER_TEXT, INTRUDER)
    )
    accepted = await bridge.handle_relay(
        relay_from(sent.question_id, ANSWER_TEXT, AUTHORIZED)
    )

    assert refused is BridgeOutcome.UNAUTHORIZED
    assert accepted is BridgeOutcome.RESOLVED
    assert [signal.args[1] for signal in client.signals] == [ANSWER_TEXT]


async def test_an_unconfigured_list_admits_everyone(
    db_path: Path, webhook: Listener, no_control_plane: None
) -> None:
    """No list is not an empty list: 008's deployments declared none and page on.

    The single Telegram chat *was* the identity, so a factory that started
    refusing every reply the day this shipped would have taken the operator
    channel down. Unrestricted is the documented default and this is what makes
    it one.
    """
    assert configured_responders() == ()

    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))
    client = FakeTemporalClient()
    bridge = CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)

    outcome = await bridge.handle_relay(
        relay_from(sent.question_id, ANSWER_TEXT, UNKNOWN_SENDER)
    )

    assert outcome is BridgeOutcome.RESOLVED
    assert [signal.args[1] for signal in client.signals] == [ANSWER_TEXT]


# ============================================================================
# T026 — US4-S3 / SC-002: the intruder does not poison the question
# ============================================================================


async def test_an_authorized_reply_after_an_unauthorized_one_is_accepted(
    db_path: Path, webhook: Listener
) -> None:
    """US4-S3: ignoring an intruder must not cost the operator their answer.

    The order is the whole test. Refusing the second reply because a first one
    arrived would look identical to working code in every test that sends one
    reply, and would silently convert every intruder into a denial of service
    against the escalation they touched.
    """
    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))
    client = FakeTemporalClient()
    bridge = CallbackBridge(
        db_path=db_path,
        client=client,
        now=lambda: RESOLVED_AT,
        authorized_responders=(AUTHORIZED,),
    )

    first = await bridge.handle_relay(
        relay_from(sent.question_id, "kill it", INTRUDER)
    )
    second = await bridge.handle_relay(
        relay_from(sent.question_id, ANSWER_TEXT, AUTHORIZED)
    )

    assert first is BridgeOutcome.UNAUTHORIZED
    assert second is BridgeOutcome.RESOLVED
    assert [signal.args[1] for signal in client.signals] == [ANSWER_TEXT]

    record = question(db_path, sent.question_id)
    assert record is not None
    assert record.resolution == store.ANSWERED
    assert record.answer_text == ANSWER_TEXT


# ============================================================================
# T027 — US4-S4: no adapter code path can expire, answer or acknowledge
# ============================================================================


async def test_expiry_over_the_webhook_is_the_factorys_and_never_the_transports(
    db_path: Path, webhook: Listener
) -> None:
    """US4-S4: the transport delivered once and settled nothing.

    The webhook is handed a question and then the factory's own expiry activity
    closes it out. What the listener received is the whole of the transport's
    participation — one POST — and the terminal row was written by a factory
    activity that the adapter has no way to reach.
    """
    from factory.activities.notify_activities import (
        ExpireQuestionInput,
        expire_question,
    )

    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))
    expired = await ActivityEnvironment().run(
        expire_question, ExpireQuestionInput(question_id=sent.question_id)
    )

    assert expired.final_state == store.EXPIRED
    record = question(db_path, sent.question_id)
    assert record is not None
    assert record.resolution == store.EXPIRED

    # One delivery, and nothing else ever crossed the seam.
    assert [post.document["correlation_id"] for post in webhook.posted] == [
        sent.question_id
    ]


async def test_a_transport_that_refuses_the_post_is_data_and_not_an_error(
    db_path: Path, webhook: Listener
) -> None:
    """R11 through the second adapter: `delivered=False` is the vocabulary.

    042's supervision probe reaches an adapter on a host that is already
    failing. One that raised on a refused endpoint would fail the alert about
    the failure.
    """
    webhook.status = 503

    receipt = await WebhookAdapter().deliver(
        RenderedMessage(text="anybody there?"), "abc123abc123"
    )

    assert receipt == DeliveryReceipt(delivered=False, message_id=None)


async def test_an_unset_endpoint_pages_nobody_and_never_opens_a_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unconfigured case, which is every deployment that never set one up."""
    monkeypatch.delenv(WEBHOOK_URL_ENV, raising=False)
    posted: list[Any] = []

    receipt = await WebhookAdapter(post=lambda *a, **k: posted.append(a)).deliver(
        RenderedMessage(text="anybody there?"), "abc123abc123"
    )

    assert receipt == DeliveryReceipt(delivered=False, message_id=None)
    assert posted == []


def test_the_webhook_relays_only_what_it_can_translate() -> None:
    """`None` is "not one of ours", and the factory decides what to say about it.

    An empty answer is not an answer: 008 refuses one over Telegram because a
    node parked on nothing is worse than a node that asked again, and the rule
    is the factory's rather than the transport's.
    """
    adapter = WebhookAdapter()

    assert adapter.relay(
        {"correlation_id": "abc123abc123", "reply_text": "yes", "sender_identity": "@b"}
    ) == InboundRelay("abc123abc123", "yes", "@b")
    assert adapter.relay(
        {"correlation_id": "abc123abc123", "reply_text": "yes"}
    ) == InboundRelay("abc123abc123", "yes", UNKNOWN_SENDER)
    assert adapter.relay({"correlation_id": "abc123abc123", "reply_text": ""}) is None
    assert adapter.relay({"reply_text": "yes"}) is None
    assert adapter.relay(object()) is None


def test_the_config_admits_the_second_adapter_by_name() -> None:
    """SC-001: switching transports is a config-only change.

    An adapter the registry ships and the parser refuses is not selectable, and
    the refusal would arrive as a broken config rather than as a missing feature.
    """
    assert WEBHOOK_ADAPTER in KNOWN_ESC_ADAPTERS
