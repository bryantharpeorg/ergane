"""Any messenger, and only authorized answers.

041-US4. The second adapter and the identity rule ship together because the
second adapter creates the problem: Telegram never had one, since a single chat
*was* the identity. Three facts the assertions turn on:

- **The check is factory-side**, in `CallbackBridge` — not adapter-side
  (answer-or-not is the decision the seam keeps out of the transport, FR-001)
  and not workflow-side (it reads a file, which workflow code may not —
  constitution IV, FR-012). A signal crossing the boundary is pre-checked.
- **`ergane answer` is not a second settling core.** It hands three terms to
  `CallbackBridge.handle_relay`, the core a Telegram reply reaches.
- **An unauthorized reply is recorded.** A silent drop is indistinguishable
  from a message lost in transit.

Evidence is pasted at the bottom, verbatim (constitution VIII / D-037).
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

import pytest
from temporalio import workflow
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.notify_activities import (
    SendQuestionInput,
    send_question,
)
from factory.cli import nouns
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    UNKNOWN_SENDER,
    DeliveryReceipt,
    InboundRelay,
    RenderedMessage,
    resolve_adapter,
)
from factory.escalation.client import start_escalation
from factory.escalation.workflow import OUTCOME_EXPIRED
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

# Fixtures, imported rather than re-declared: `db_path` and `env` are US2's and
# `run_async` is the `escalations` noun's, and this story needs the same three.
from tests.test_ergane_escalations import Run, run_async  # noqa: F401 - fixture
from tests.test_escalation_workflow import (  # noqa: F401 - db_path/env are fixtures
    TASK_QUEUE,
    a_request,
    db_path,
    env,
    escalation_worker,
    row,
)
from tests.test_messenger_adapter import (
    FakePressUpdate,
    FakeTemporalClient,
    FakeUser,
    escalation_record,
)

EPIC = "041-escalation-workflow"
NODE = "us4"
ATTEMPT = 1

QUESTION_TEXT = (
    "The webhook has no chat, so who is allowed to answer it?\n"
    "Telegram never had to say; a bridged messenger does."
)

ANSWER_TEXT = "ship it"

#: The operator the list admits and one it does not, spelled the way
#: `TelegramAdapter._identity` spells a username — one list covers both
#: transports, because it is about people rather than protocols.
AUTHORIZED = "@bryan"
INTRUDER = "@not-bryan"

RESOLVED_AT = "2026-08-16T15:04:00Z"

#: This file's own queue: nothing here should be servable by a worker an
#: operator happens to be running.
QUEUE = "webhook-answers-under-test"


# --- the world ---------------------------------------------------------------


@workflow.defn
class WaitingForAnswer:
    """Parked on `question_answered`, so US4-S1's "resumes the waiting workflow
    with that text" is a real result rather than a recorded call."""

    def __init__(self) -> None:
        self._answer = ""

    @workflow.signal(name=QUESTION_SIGNAL_NAME)
    def question_answered(self, question_id: str, answer_text: str) -> None:
        self._answer = answer_text

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: bool(self._answer))
        return self._answer


class Listener:
    """A real HTTP endpoint on an ephemeral loopback port — other nodes share
    this host, so a fixed port is a collision waiting to happen."""

    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []
        self.status = 200
        listener = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8")
                listener.posted.append(json.loads(body))
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


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def listener() -> Iterator[Listener]:
    endpoint = Listener()
    try:
        yield endpoint
    finally:
        endpoint.close()


@pytest.fixture
def webhook(listener: Listener, monkeypatch: pytest.MonkeyPatch) -> Listener:
    """A worker paging over the webhook, selected the way an operator does."""
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, WEBHOOK_ADAPTER)
    monkeypatch.setenv(WEBHOOK_URL_ENV, listener.url)
    return listener


@pytest.fixture
def no_control_plane(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No config file: unrestricted, which is what every 008 deployment is."""
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(tmp_path / "absent.toml"))
    monkeypatch.delenv(FACTORY_CONFIG_PATH_ENV, raising=False)


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


def press(data: str, *, username: str) -> Any:
    """One press from `username`, ready for `handle`, which strips the keyboard
    on resolve — the one attribute the US1 fakes lack."""
    update = FakePressUpdate(data, from_user=FakeUser(username=username))

    async def edited(*_args: Any, **_kwargs: Any) -> None:
        return None

    update.callback_query.edit_message_text = edited
    return update


def relay_from(correlation_id: str, text: str, identity: str) -> InboundRelay:
    """The three terms, through the adapter's own `relay` rather than by hand,
    so "an inbound reply" here is `ergane answer`'s path."""
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
    """A real control-plane file, minimal but complete enough to parse."""
    path.write_text(
        'version = 1\n[llm]\nmode = "gateway"\nbase_url = "http://llm.local/v1"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n[memory]\nbackend = "none"\n'
        '[temporal]\nmode = "external"\naddress = "127.0.0.1:7233"\n'
        'namespace = "ergane"\n[telemetry]\n[escalation]\nadapter = "webhook"\n'
        f"authorized_responders = {responders}\n",
        encoding="utf-8",
    )
    return path


# --- T024 — US4-S1 / FR-003: the webhook round trip ----------------------------


async def test_a_question_posts_the_rendered_message_and_the_correlation_id(
    db_path: Path, webhook: Listener
) -> None:
    """US4-S1's outbound half, against a real socket: what is asserted is what
    an operator's bridge receives. The text is `factory/notify/messages.py`'s
    and never the adapter's, or what the operator is asked would become a
    property of the transport."""
    sent = await ActivityEnvironment().run(send_question, a_question("epic-w"))

    assert len(webhook.posted) == 1
    document = webhook.posted[0]
    assert document["correlation_id"] == sent.question_id
    assert QUESTION_TEXT in document["text"]
    assert document["actions"] == []

    record = question(db_path, sent.question_id)
    assert record is not None
    assert record.message_id is None, (
        "a webhook mints no message handle, which is why `ergane answer` routes "
        "by the factory's own id"
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

    The row carries no message id — the webhook minted none — so a verb keeping
    Telegram's message-handle routing finds nothing here.
    """
    async with Worker(
        env.client,
        task_queue=QUEUE,
        workflows=[WaitingForAnswer],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        waiting = await env.client.start_workflow(
            WaitingForAnswer.run, id="waiting-on-us4", task_queue=QUEUE
        )
        sent = await ActivityEnvironment().run(
            send_question, a_question(waiting.id)
        )
        assert webhook.posted[0]["correlation_id"] == sent.question_id

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
    """T029: answered, expired, or never asked — three cases, three sentences.
    A verb printing one "could not answer" line fails two of them."""
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


# --- T025 — US4-S2 / FR-011: an unauthorized reply is refused and recorded -----


async def test_an_unauthorized_reply_does_not_resume_and_is_recorded(
    db_path: Path,
    webhook: Listener,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """US4-S2: no signal, no state change, no touched clock — and a record.

    Four separate assertions because they fail separately: one that refused the
    reply but settled the row still satisfies "does not resume".
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

    Two inbound entries, no shared settling core: a press goes through `handle`,
    a reply through `_settle_question`. Measured, not assumed — see mutation 5.

    Both directions against one seeded escalation, because a press refused for
    want of a row looks exactly like one refused for want of an identity.
    """
    monkeypatch.delenv(ESCALATION_ADAPTER_ENV, raising=False)
    with closing(store.connect(db_path)) as conn:
        store.insert_escalation(conn, escalation_record(workflow_id="epic-w"))
    client = FakeTemporalClient()
    bridge = CallbackBridge(
        db_path=db_path,
        client=client,
        now=lambda: RESOLVED_AT,
        authorized_responders=(AUTHORIZED,),
    )
    payload = "esc:0123456789ab:RETRY"

    with caplog.at_level(logging.WARNING):
        refused = await bridge.handle(press(payload, username="not-bryan"))

    assert refused is BridgeOutcome.UNAUTHORIZED
    assert client.signals == []
    recorded = "\n".join(record.getMessage() for record in caplog.records)
    assert INTRUDER in recorded
    assert "0123456789ab" in recorded

    with closing(store.connect(db_path)) as conn:
        assert store.get_escalation(conn, "0123456789ab").resolution is None

    accepted = await bridge.handle(press(payload, username="bryan"))

    assert accepted is BridgeOutcome.RESOLVED
    assert [signal.args[1] for signal in client.signals] == ["RETRY"]


async def test_the_authorized_list_is_read_from_the_control_plane_file(
    tmp_path: Path,
    db_path: Path,
    webhook: Listener,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-011's list is `escalation.authorized_responders`, really parsed.

    Through a real config file and a bridge given no explicit list: what this
    guards against is a field that parses and reaches nobody, which is how
    `check_evidence` was dropped for three weeks.
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


def test_an_unconfigured_list_admits_everyone(no_control_plane: None) -> None:
    """No list is not an empty list: 008's deployments declared none and page
    on. That such a deployment still answers is the round trip above, which runs
    under this same fixture and resolves."""
    assert configured_responders() == ()


# --- T026 — US4-S3 / SC-002: the intruder does not poison the question ---------


async def test_an_authorized_reply_after_an_unauthorized_one_is_accepted(
    db_path: Path, webhook: Listener
) -> None:
    """US4-S3: ignoring an intruder must not cost the operator their answer.

    The order is the whole test. Refusing the second reply because a first
    arrived is invisible to any test that sends one, and turns every intruder
    into a denial of service on what they touched.
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


# --- T027 — US4-S4: no adapter code path can expire, answer or acknowledge -----


async def test_expiry_over_the_webhook_is_the_workflows_and_never_the_transports(
    env: WorkflowEnvironment, db_path: Path, webhook: Listener
) -> None:
    """US4-S4: a real `EscalationWorkflow` delivered over the second adapter,
    expiring on its own durable timer. One POST is the whole of the transport's
    participation: the hour is the workflow's and the terminal row is a factory
    activity's, neither of which the adapter can reach.
    """
    async with escalation_worker(env):
        handle = await start_escalation(env.client, a_request(), task_queue=TASK_QUEUE)
        outcome = await handle.result()  # nobody answers; the timer runs out

    assert outcome.outcome == OUTCOME_EXPIRED
    assert outcome.delivered is True
    record = row(db_path, handle.id)
    assert record is not None and record.resolution == store.EXPIRED

    assert [post["correlation_id"] for post in webhook.posted] == [handle.id]


async def test_a_transport_that_cannot_send_is_data_and_not_an_error(
    webhook: Listener, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R11 through the second adapter: `delivered=False` is the vocabulary.

    A refusing endpoint and an unconfigured one are the same fact, and neither
    raises — 042's probe reaches an adapter on a host that is already failing,
    and one that raised would fail the alert about the failure.
    """
    webhook.status = 503
    refused = await WebhookAdapter().deliver(
        RenderedMessage(text="anybody there?"), "abc123abc123"
    )

    monkeypatch.delenv(WEBHOOK_URL_ENV, raising=False)
    attempted: list[Any] = []
    unset = await WebhookAdapter(post=lambda *a, **k: attempted.append(a)).deliver(
        RenderedMessage(text="anybody there?"), "abc123abc123"
    )

    assert refused == DeliveryReceipt(delivered=False, message_id=None)
    assert unset == DeliveryReceipt(delivered=False, message_id=None)
    assert attempted == []


def test_the_webhook_relays_only_what_it_can_translate() -> None:
    """`None` is "not one of ours". An empty answer is not an answer — 008
    refuses one over Telegram too, because a node parked on nothing is worse
    than one that asked again."""
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


# --- EVIDENCE, pasted verbatim (constitution VIII / D-037) --------------------
#
# Every mutation was applied to a committed HEAD with `git status --porcelain`
# empty and reverted after. Not ceremony: the first run predated `webhook.py`
# and `answer.py` being tracked, so mutation 3's edit survived the revert and
# made runs 4, 5 and 6 meaningless. These are the re-run.

MUTATIONS = """
1  `_refuse_unauthorized` returns None unconditionally — the guard does nothing
   E  assert <BridgeOutcome.RESOLVED> is <BridgeOutcome.UNAUTHORIZED>
   4 failed, 9 passed   (both inbound entries, the config case, and US4-S3)

2  `configured_responders()` returns () — the guard never learns the list
   E  assert () == ('@bryan',)
   1 failed, 12 passed

3  `status = 200` without POSTing — the webhook claims a delivery it never made
   E  assert 0 == 1   +  where 0 = len([]) = <Listener>.posted
   4 failed, 9 passed   (both round trips, the expiry case, and the R11 case)

4  `_question_for` drops the `get_question` fallback — Telegram's routing only
   E  assert 'already answered' in 'ergane: 38330e52d6d1 names no question this
      factory ever asked; nothing was signalled'
   5 failed, 8 passed

5  the guard is deleted from the PRESS path only, leaving the reply path's
   E  assert <BridgeOutcome.RESOLVED> is <BridgeOutcome.UNAUTHORIZED>
   1 failed, 12 passed  ::test_an_unauthorized_press_is_refused_on_the_button_path_too

   The mutation that mattered. On its first run it came back **green, 15
   passed** — the test then drove `handle_reply`, which reaches the reply core,
   so the press call site had no coverage at all. A guard's existence is not the
   assertion that it covers what was put behind it.

6  the refusal logs nothing — no signal, no state change, and no record
   E  AssertionError: an unauthorized reply that logs nothing is a lost one
      assert '@not-bryan' in ''
   2 failed, 11 passed  (both inbound entries)

7  `authorized_responders` parses and is never rendered back
   E  authorized_responders: () != ('@bryan', '4242')
   1 failed, 22 passed  ::test_a_responder_list_survives_the_render_round_trip

8  the SECOND adapter breaks the seam: `mark_delivered` named in its own source
   E  AssertionError: the webhook adapter names ['mark_delivered']
   1 failed, 30 passed
     ::test_no_adapter_code_path_can_acknowledge_answer_or_expire[webhook]

   The conformance fix, measured. Against the parametrisation this story
   replaces — `@pytest.mark.parametrize("name", ["telegram"])` — this mutation
   is invisible: there is no `[webhook]` case to run.
"""

FINAL_SUITE = """
$ uv run pytest -q
2904 passed, 44 skipped, 5 warnings in 306.46s (0:05:06)
"""
