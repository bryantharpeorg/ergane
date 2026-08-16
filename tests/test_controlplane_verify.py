"""Tests for `ergane install --verify` (US2 of 033-ergane-install).

The evidence rule (constitution VIII) says runtime claims must be met by tool
output pasted verbatim into a comment block in the test file. After the first
run the suite output will be pasted below.

Suite output:

.. code-block:: text

    ........                                                                   [100%]
    8 passed in 0.77s


Follow-up: two defects in `TemporalProbe`
-----------------------------------------

An independent review found that the temporal probe asked Temporal about a
*workflow* (`ergane-install-verify`) and reported a `NOT_FOUND` on it as an
absent namespace, and that nothing bounded the call.  Both were reproduced
before either was fixed.

**Defect 1 — the namespace was never checked.**  On the host the factory runs
on, the namespace exists and the workflow does not:

.. code-block:: text

    $ temporal operator namespace describe -n factory
      NamespaceInfo.Name                    factory
      NamespaceInfo.Id                      d3e55ab2-5a0b-4735-9283-a66d4431ee5d
      NamespaceInfo.Description
      NamespaceInfo.OwnerEmail
      NamespaceInfo.State                   Registered

    $ temporal workflow describe --workflow-id ergane-install-verify --namespace factory
    Error: failed describing workflow: workflow not found for ID: ergane-install-verify

so `ergane install --verify` told the operator to create a namespace that was
already registered.  Reproduced against a live dev server that registers
`ergane-verify` and nothing else, using the probe as it then stood:

.. code-block:: text

    namespace registered on the server: ergane-verify
    [FAIL] temporal: Temporal at 127.0.0.1:41611 does not have namespace `ergane-verify`;
    create it with `temporal operator namespace create ergane-verify`

The landed test hid this by starting a workflow with that exact id before
running verify — it manufactured its own passing condition.  That arrangement
is deleted; `test_verify_all_subsystems_pass` now asserts the workflow is
*absent* and still expects the finding to pass.

**Defect 2 — the call was unbounded.**  `Client.connect` against an address
that accepts and never answers never returns; the old `elapsed >= timeout`
branch could only run after some exception surfaced, so nothing ever fired:

.. code-block:: text

    blackhole at 127.0.0.1:33319
    STILL HANGING after 12.00s -> unbounded

Both new tests, run against the probe before the fix (red):

.. code-block:: text

    E       assert 1 == 0
    E       Failed: TemporalProbe.gather did not return 12s into a 2s timeout
            against a black-holed address — it is unbounded
    =========================== short test summary info ============================
    FAILED tests/test_controlplane_verify.py::test_verify_all_subsystems_pass - a...
    FAILED tests/test_controlplane_verify.py::test_verify_temporal_bounds_a_blackholed_address
    2 failed, 8 passed in 27.80s

"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable

import httpx
import pytest
from temporalio.testing import WorkflowEnvironment

import factory.controlplane.verify as verify_module
from factory.cli.main import main as ergane_main
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.mergequeue.models import Finding


# ---------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------


def _full_config_toml(
    *,
    llm_mode: str = "gateway",
    llm_base_url: str = "http://llm.local/v1",
    llm_master_key_env: str = "ERGANE_LLM_MASTER_KEY",
    memory_backend: str = "hindsight",
    memory_url: str = "http://hindsight.local:8888",
    memory_api_key_env: str = "ERGANE_HINDSIGHT_KEY",
    temporal_address: str = "temporal.local:7233",
    temporal_namespace: str = "ergane",
    temporal_timeout_s: int | None = None,
    telemetry_endpoint: str | None = "http://otel.local:4317",
    escalation_bot_token_env: str = "ERGANE_TELEGRAM_BOT_TOKEN",
    escalation_chat_id_env: str = "ERGANE_TELEGRAM_CHAT_ID",
) -> str:
    lines = [
        'version = 1',
        '',
        '[llm]',
        f'mode = "{llm_mode}"',
        f'base_url = "{llm_base_url}"',
        f'master_key_env = "{llm_master_key_env}"',
        '',
        '[memory]',
        f'backend = "{memory_backend}"',
        f'url = "{memory_url}"',
        f'api_key_env = "{memory_api_key_env}"',
        '',
        '[temporal]',
        'mode = "external"',
        f'address = "{temporal_address}"',
        f'namespace = "{temporal_namespace}"',
    ]
    if temporal_timeout_s is not None:
        lines.append(f'timeout_s = {temporal_timeout_s}')
    lines += [
        '',
        '[telemetry]',
    ]
    if telemetry_endpoint is not None:
        lines.append(f'otlp_endpoint = "{telemetry_endpoint}"')
    lines.extend([
        '',
        '[escalation]',
        'adapter = "telegram"',
        f'bot_token_env = "{escalation_bot_token_env}"',
        f'chat_id_env = "{escalation_chat_id_env}"',
    ])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Live doubles
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _loopback_otlp_listener() -> AsyncIterator[str]:
    """A TCP listener that accepts OTLP/HTTP export and answers 200.

    Returns the `http://127.0.0.1:<port>` endpoint.  Every accepted connection is
    drained and answered so the probe's POST returns cleanly.
    """
    server: asyncio.Server | None = None

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # Drain the request line + headers.
            headers = bytearray()
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                headers.extend(line)
            content_length = 0
            for h in headers.split(b"\r\n"):
                if h.lower().startswith(b"content-length:"):
                    content_length = int(h.split(b":", 1)[1].strip())
            # Read the exact body so httpx can receive a complete response.
            if content_length:
                await reader.readexactly(content_length)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
            # Give the kernel a moment to flush before closing the socket.
            await asyncio.sleep(0.05)
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        yield f"http://127.0.0.1:{port}"
        server.close()
        await server.wait_closed()
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()


def _closed_port() -> str:
    """An address that is certain to refuse a connection: the loopback discard port."""
    return "127.0.0.1:1"


@asynccontextmanager
async def _blackhole_listener() -> AsyncIterator[str]:
    """A TCP listener that completes the handshake and then never answers.

    This is the target US2-S4 actually needs.  `127.0.0.1:1` *refuses*, which
    returns an error immediately and exercises the connection-refused path — it
    says nothing about whether a probe is bounded.  A socket that accepts and
    then goes silent is what makes an unbounded client wait forever, so it is
    the only shape that can tell a timeout from patience.

    Returns a `host:port` address (Temporal's form, no scheme).
    """
    stop = asyncio.Event()

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # Read nothing, write nothing: hold the connection open until teardown.
            await stop.wait()
        finally:
            writer.close()

    server = await asyncio.start_server(_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]  # type: ignore[index]
    try:
        yield f"127.0.0.1:{port}"
    finally:
        stop.set()
        server.close()
        await server.wait_closed()


@asynccontextmanager
async def _loopback_memory_listener() -> AsyncIterator[str]:
    """A tiny HTTP server that answers 200 on /health for the memory probe."""
    server: asyncio.Server | None = None

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            headers = bytearray()
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                headers.extend(line)
            content_length = 0
            for h in headers.split(b"\r\n"):
                if h.lower().startswith(b"content-length:"):
                    content_length = int(h.split(b":", 1)[1].strip())
            if content_length:
                await reader.readexactly(content_length)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
            await asyncio.sleep(0.05)
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        yield f"http://127.0.0.1:{port}"
        server.close()
        await server.wait_closed()
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()


@asynccontextmanager
async def _loopback_llm_listener() -> AsyncIterator[str]:
    """A tiny HTTP server that answers a chat completion on /chat/completions."""
    server: asyncio.Server | None = None

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            headers = bytearray()
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                headers.extend(line)
            content_length = 0
            for h in headers.split(b"\r\n"):
                if h.lower().startswith(b"content-length:"):
                    content_length = int(h.split(b":", 1)[1].strip())
            if content_length:
                await reader.readexactly(content_length)
            body = b'{"choices":[{"message":{"content":"pong"}}]}'
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
            await asyncio.sleep(0.05)
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        yield f"http://127.0.0.1:{port}"
        server.close()
        await server.wait_closed()
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()


@asynccontextmanager
async def _loopback_telegram_listener(token: str) -> AsyncIterator[str]:
    """A tiny HTTP server that answers Telegram's sendMessage with a stored message."""
    server: asyncio.Server | None = None

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            headers = bytearray()
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                headers.extend(line)
            content_length = 0
            for h in headers.split(b"\r\n"):
                if h.lower().startswith(b"content-length:"):
                    content_length = int(h.split(b":", 1)[1].strip())
            if content_length:
                await reader.readexactly(content_length)
            # Telegram returns {"ok":true,"result":{"message_id":42,"chat":{...},"date":1,"text":...}}
            body = (
                b'{"ok":true,"result":{"message_id":42,"chat":{"id":-1,"type":"group"},'
                b'"date":1,"text":"ergane install --verify test message"}}'
            )
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
            await asyncio.sleep(0.05)
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        yield f"http://127.0.0.1:{port}/bot{token}/"
        server.close()
        await server.wait_closed()
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()


@dataclass(frozen=True)
class _LiveDoubles:
    otlp_endpoint: str
    memory_endpoint: str
    temporal_environment: WorkflowEnvironment


#: The namespace the live Temporal double registers.  Nothing else is created in
#: it — no workflow, no task queue — so a probe that passes here can only have
#: passed by asking the server about the namespace itself.
LIVE_NAMESPACE = "ergane-verify"

#: A namespace that is never registered on the live double.
ABSENT_NAMESPACE = "absent-namespace"


@pytest.fixture
async def live_doubles() -> AsyncIterator[_LiveDoubles]:
    """Provide live OTLP / memory listeners and a local Temporal dev server.

    `start_local` rather than `start_time_skipping`: the time-skipping test
    server auto-creates every namespace it is asked about, so a namespace check
    against it can never fail and `ABSENT_NAMESPACE` would answer "exists".
    Measured on temporalio 1.31.0 by describing three namespaces against each
    server -- `test_absent_namespace_is_absent_on_the_live_double` below is the
    committed, always-run form of the second half:

    .. code-block:: text

        # WorkflowEnvironment.start_time_skipping()
        target_host: 127.0.0.1:46623
        ergane-verify -> EXISTS ergane-verify 1
        absent-namespace -> EXISTS absent-namespace 1
        default -> EXISTS default 1

        # WorkflowEnvironment.start_local()
        target_host: 127.0.0.1:39469 ns: default
        default -> EXISTS default
        absent-namespace -> RPCError 5 Namespace absent-namespace is not found.

    Follows trap 10: the Temporal server is shut down in a `finally` block so a
    bare signal cannot orphan it.
    """
    async with _loopback_otlp_listener() as otlp_endpoint:
        async with _loopback_memory_listener() as memory_endpoint:
            environment = await WorkflowEnvironment.start_local(namespace=LIVE_NAMESPACE)
            try:
                yield _LiveDoubles(
                    otlp_endpoint=otlp_endpoint,
                    memory_endpoint=memory_endpoint,
                    temporal_environment=environment,
                )
            finally:
                await environment.shutdown()


# ---------------------------------------------------------------------------
# Fake subsystems
# ---------------------------------------------------------------------------


class _FakeLiteLLMClient:
    """A stand-in for the LLM endpoint that returns a tiny completion."""

    def __init__(self, *, persona_model: str | None = None) -> None:
        self.persona_model = persona_model or "fake-model"
        self.completion_calls: list[dict[str, Any]] = []

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        self.completion_calls.append(request)
        return {"choices": [{"message": {"content": "pong"}}]}

    async def aclose(self) -> None:
        pass


class _FakeLLMFactory:
    """Returns the same fake LiteLLM client for every gateway config."""

    def __init__(self, client: _FakeLiteLLMClient) -> None:
        self.client = client
        self.calls: list[Cfg.LLM] = []

    def __call__(self, config: Cfg.LLM) -> _FakeLiteLLMClient:
        self.calls.append(config)
        return self.client


class _FakeTelegramBot:
    """A stand-in for the Telegram Bot that records its send_message calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(message_id=42)


class _FakeTelegramFactory:
    """Returns the same fake bot for every escalation config."""

    def __init__(self, bot: _FakeTelegramBot) -> None:
        self.bot = bot
        self.calls: list[Cfg.Escalation] = []

    def __call__(self, config: Cfg.Escalation, **kwargs: Any) -> _FakeTelegramBot:
        self.calls.append(config)
        return self.bot


def _fake_memory_client_factory(config: Cfg.Memory) -> httpx.AsyncClient:
    """A seam that points the memory probe at the live loopback listener."""
    assert config.url is not None
    return httpx.AsyncClient(base_url=config.url.rstrip("/"), timeout=config.timeout_s)


@pytest.fixture
def fake_subsystems(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeLLMFactory, _FakeTelegramFactory]:
    """Patch the LLM and Telegram seams with fakes; tests needing live doubles
    patch them back or use the module attributes directly."""
    llm_client = _FakeLiteLLMClient(persona_model="ollama-cloud/kimi-k2.7-code")
    llm_factory = _FakeLLMFactory(llm_client)
    telegram_bot = _FakeTelegramBot()
    telegram_factory = _FakeTelegramFactory(telegram_bot)
    monkeypatch.setattr(verify_module, "_llm_client_factory", llm_factory)
    monkeypatch.setattr(verify_module, "_telegram_bot_factory", telegram_factory)
    return llm_factory, telegram_factory


# ---------------------------------------------------------------------------
# T011 [US2-S1] all findings pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_all_subsystems_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_doubles: _LiveDoubles,
    fake_subsystems: tuple[_FakeLLMFactory, _FakeTelegramFactory],
) -> None:
    """US2-S1: when every subsystem answers, every finding passes and exit is 0.

    Nothing is seeded into the namespace.  The earlier version of this test
    started a workflow whose id was the one the probe happened to describe,
    which meant the test manufactured the very condition it asserted; the
    control below proves that workflow does *not* exist while the finding
    still passes.
    """
    config_path = tmp_path / "config.toml"
    temporal_address = live_doubles.temporal_environment.client.service_client.config.target_host
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
            memory_url=live_doubles.memory_endpoint,
            temporal_address=temporal_address,
            temporal_namespace=LIVE_NAMESPACE,
            telemetry_endpoint=live_doubles.otlp_endpoint,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    monkeypatch.setenv("ERGANE_HINDSIGHT_KEY", "sk-fake-hindsight")
    monkeypatch.setenv("ERGANE_TELEGRAM_BOT_TOKEN", "123456:AAAA")
    monkeypatch.setenv("ERGANE_TELEGRAM_CHAT_ID", "-1")

    # Control: the registered namespace holds no workflow at all, and in
    # particular not the `ergane-install-verify` id the probe used to describe.
    # A probe that answers "namespace exists" from a workflow describe fails
    # here; a probe that asks about the namespace passes.
    from temporalio.client import Client
    from temporalio.service import RPCError, RPCStatusCode

    control_client = await Client.connect(temporal_address, namespace=LIVE_NAMESPACE)
    with pytest.raises(RPCError) as absent_workflow:
        await control_client.get_workflow_handle("ergane-install-verify").describe()
    assert absent_workflow.value.status is RPCStatusCode.NOT_FOUND

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    assert exit_code == 0
    assert len(findings) == 5
    assert {f.check for f in findings} == {"llm", "temporal", "memory", "telemetry", "escalation"}
    assert all(f.passed for f in findings)
    llm_finding = next(f for f in findings if f.check == "llm")
    assert "persona `implementer`" in llm_finding.detail
    assert "1-token" in llm_finding.detail
    temporal_finding = next(f for f in findings if f.check == "temporal")
    assert f"has namespace `{LIVE_NAMESPACE}`" in temporal_finding.detail
    telemetry_finding = next(f for f in findings if f.check == "telemetry")
    assert "exported a test trace span" in telemetry_finding.detail


# ---------------------------------------------------------------------------
# T012 [US2-S2] no masking: one failing subsystem does not hide the rest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_no_masking_temporal_namespace_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_doubles: _LiveDoubles,
    fake_subsystems: tuple[_FakeLLMFactory, _FakeTelegramFactory],
) -> None:
    """US2-S2: a missing Temporal namespace fails only that finding; the other four still render.

    The absence is real: the live double registered `LIVE_NAMESPACE` and
    nothing else, so `ABSENT_NAMESPACE` is unregistered on a server that is
    otherwise answering.
    """
    config_path = tmp_path / "config.toml"
    temporal_address = live_doubles.temporal_environment.client.service_client.config.target_host
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
            memory_url=live_doubles.memory_endpoint,
            temporal_address=temporal_address,
            temporal_namespace=ABSENT_NAMESPACE,
            telemetry_endpoint=live_doubles.otlp_endpoint,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    monkeypatch.setenv("ERGANE_HINDSIGHT_KEY", "sk-fake-hindsight")
    monkeypatch.setenv("ERGANE_TELEGRAM_BOT_TOKEN", "123456:AAAA")
    monkeypatch.setenv("ERGANE_TELEGRAM_CHAT_ID", "-1")

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    assert exit_code == 1
    checks = {f.check: f for f in findings}
    assert len(findings) == 5
    assert checks["temporal"].passed is False
    assert "absent-namespace" in checks["temporal"].detail
    assert "temporal operator namespace create absent-namespace" in checks["temporal"].detail
    for check in ("llm", "memory", "telemetry", "escalation"):
        assert checks[check].passed is True


@pytest.mark.asyncio
async def test_absent_namespace_is_absent_on_the_live_double(
    live_doubles: _LiveDoubles,
) -> None:
    """The double used by US2-S1/S2 answers about namespaces, not about workflows.

    Without this, `test_verify_no_masking_temporal_namespace_missing` could pass
    against a server that auto-registers namespaces — the failure would come
    from an absent *workflow* and the test would still be green while the probe
    was wrong.  This asserts the server itself calls `ABSENT_NAMESPACE` absent
    and `LIVE_NAMESPACE` present, which is the property the probe is read
    against.
    """
    from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
    from temporalio.client import Client
    from temporalio.service import RPCError, RPCStatusCode

    address = live_doubles.temporal_environment.client.service_client.config.target_host
    client = await Client.connect(address, namespace=LIVE_NAMESPACE)
    service = client.service_client.workflow_service

    present = await service.describe_namespace(DescribeNamespaceRequest(namespace=LIVE_NAMESPACE))
    assert present.namespace_info.name == LIVE_NAMESPACE

    with pytest.raises(RPCError) as absent:
        await service.describe_namespace(DescribeNamespaceRequest(namespace=ABSENT_NAMESPACE))
    assert absent.value.status is RPCStatusCode.NOT_FOUND


# ---------------------------------------------------------------------------
# T013 [US2-S3] escalation probe delivers and defers lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_escalation_probe_delivers_and_defers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_subsystems: tuple[_FakeLLMFactory, _FakeTelegramFactory],
) -> None:
    """US2-S3: the escalation finding names the transport, delivery, and the 041 deferral."""
    llm_factory, telegram_factory = fake_subsystems
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
            telemetry_endpoint=None,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    monkeypatch.setenv("ERGANE_TELEGRAM_BOT_TOKEN", "123456:AAAA")
    monkeypatch.setenv("ERGANE_TELEGRAM_CHAT_ID", "-1")

    # Temporal is not reachable in this test; it is fine for escalation to be the focus.
    monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising_temporal_factory)

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    escalation_finding = next(f for f in findings if f.check == "escalation")
    assert escalation_finding.passed is True
    assert "telegram" in escalation_finding.detail
    assert "message_id=42" in escalation_finding.detail
    assert "deferred to epic 041" in escalation_finding.detail
    assert len(telegram_factory.bot.calls) == 1
    assert telegram_factory.bot.calls[0]["text"] == "ergane install --verify test message"


def _raising_temporal_factory(config: Cfg.Temporal) -> Any:
    """A seam that makes the temporal probe fail closed without a live server."""
    raise verify_module.ServiceNotAnswering("temporal", reason="not configured in this test")


# ---------------------------------------------------------------------------
# T014 [US2-S4] timeout: a closed port fails within its bound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_timeout_on_closed_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2-S4: pointing a probe at 127.0.0.1:1 fails within its timeout, naming it."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://127.0.0.1:1/v1",
            temporal_address="127.0.0.1:1",
            telemetry_endpoint="http://127.0.0.1:1",
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    monkeypatch.setenv("ERGANE_HINDSIGHT_KEY", "sk-fake-hindsight")
    # Keep escalation skipped by leaving the env vars unset.

    bounds = {
        "llm": 1,
        "temporal": 5,
        "telemetry": 5,
    }

    for check_name, bound_s in bounds.items():
        start = time.monotonic()
        if check_name == "llm":
            probe = verify_module.LLMProbe()
        elif check_name == "temporal":
            probe = verify_module.TemporalProbe()
        else:
            probe = verify_module.TelemetryProbe()

        from factory.controlplane.config import load_controlplane_config
        config = load_controlplane_config(str(config_path))
        snapshot = await probe.gather(config)
        elapsed = time.monotonic() - start

        finding = probe.evaluate(snapshot)
        assert finding.passed is False, f"{check_name} should have failed"
        assert elapsed < bound_s + 0.5, f"{check_name} took {elapsed}s, expected < {bound_s + 0.5}s"
        assert finding.detail.startswith("timed out") or "127.0.0.1:1" in finding.detail


@pytest.mark.asyncio
async def test_verify_temporal_bounds_a_blackholed_address(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2-S4: a Temporal address that accepts and never answers fails inside its timeout.

    "Hanging is a defect, not patience."  Measured against the unbounded probe,
    `Client.connect` to such an address never returns:

    .. code-block:: text

        blackhole at 127.0.0.1:33319
        STILL HANGING after 12.00s -> unbounded

    so the assertion below is not a formality — nothing in the SDK bounds this
    for us.  The gather is run under an outer `wait_for` well past the declared
    timeout so an unbounded probe fails this test instead of wedging the suite.
    """
    timeout_s = 2
    async with _blackhole_listener() as address:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            _full_config_toml(
                llm_base_url="http://127.0.0.1:1/v1",
                temporal_address=address,
                temporal_namespace="factory",
                temporal_timeout_s=timeout_s,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))

        from factory.controlplane.config import load_controlplane_config

        config = load_controlplane_config(str(config_path))
        assert config.temporal.timeout_s == timeout_s

        probe = verify_module.TemporalProbe()
        start = time.monotonic()
        try:
            snapshot = await asyncio.wait_for(probe.gather(config), timeout_s + 10)
        except TimeoutError:
            pytest.fail(
                f"TemporalProbe.gather did not return {timeout_s + 10}s into a "
                f"{timeout_s}s timeout against a black-holed address — it is unbounded"
            )
        elapsed = time.monotonic() - start

    finding = probe.evaluate(snapshot)
    assert finding.passed is False
    assert elapsed < timeout_s + 1.5, f"gather took {elapsed:.2f}s for a {timeout_s}s timeout"
    assert f"timed out after {timeout_s}s" in finding.detail
    assert address in finding.detail


# ---------------------------------------------------------------------------
# T015 [US2-S5] skipped-by-declaration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_skipped_by_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2-S5: subsystems declared `none` render explicit skipped findings,
    distinguishable from a ServiceNotAnswering or a deferral."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
            memory_backend="none",
            telemetry_endpoint=None,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")

    monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising_temporal_factory)
    monkeypatch.setattr(verify_module, "_llm_client_factory", _raising_llm_factory)
    monkeypatch.setattr(verify_module, "_telegram_bot_factory", _raising_telegram_factory)

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    checks = {f.check: f for f in findings}
    assert checks["memory"].passed is True
    assert "skipped by declaration" in checks["memory"].detail
    assert checks["telemetry"].passed is True
    assert "skipped by declaration" in checks["telemetry"].detail

    # ServiceNotAnswering findings should look different from skipped.
    assert "skipped by declaration" not in checks["llm"].detail
    assert "not answering" in checks["llm"].detail or "did not answer" in checks["llm"].detail
    assert "skipped by declaration" not in checks["temporal"].detail
    assert "not answering" in checks["temporal"].detail or "did not answer" in checks["temporal"].detail


def _raising_llm_factory(config: Cfg.LLM) -> Any:
    raise verify_module.ServiceNotAnswering("llm", reason="no proxy in this test")


def _raising_telegram_factory(config: Cfg.Escalation, **kwargs: Any) -> Any:
    raise verify_module.ServiceNotAnswering("escalation", reason="no telegram in this test")


# ---------------------------------------------------------------------------
# T015a absent-client-library renders a failing finding naming the dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_absent_client_library_fails_naming_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2 edge case: a probe whose library cannot be imported fails naming the missing package."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")

    # Simulate an environment where the Telegram package is not installed by
    # making the factory raise ModuleNotFoundError.
    monkeypatch.setattr(
        verify_module,
        "_telegram_bot_factory",
        lambda config, **kwargs: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'telegram'")),
    )
    monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising_temporal_factory)
    monkeypatch.setattr(verify_module, "_llm_client_factory", _raising_llm_factory)

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    escalation_finding = next(f for f in findings if f.check == "escalation")
    assert escalation_finding.passed is False
    assert "telegram" in escalation_finding.detail.lower() or "dependency" in escalation_finding.detail.lower()
    assert "ModuleNotFoundError" not in escalation_finding.detail or "missing dependency" in escalation_finding.detail.lower()


# ---------------------------------------------------------------------------
# T018 [US2-SC-006] live doubles: every gather executes against a real transport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_llm_gather_against_live_double(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-006/T018: the LLM probe's real gather runs against a loopback HTTP double.

    The probe first builds a LiteLLMClient from env, so we set the env variables
    it expects to dummy values; the client has no chat_completion path, so the
    gather falls back to httpx against the configured base_url — that is the code
    path being exercised here.
    """
    async with _loopback_llm_listener() as llm_endpoint:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            _full_config_toml(
                llm_base_url=llm_endpoint,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
        monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
        # LiteLLMClient.from_env() is called first and requires these env vars.
        monkeypatch.setenv("LITELLM_PROXY_URL", "http://127.0.0.1:1")
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-dummy")

        from factory.controlplane.config import load_controlplane_config

        config = load_controlplane_config(str(config_path))
        probe = verify_module.LLMProbe()
        snapshot = await probe.gather(config)

    finding = probe.evaluate(snapshot)
    assert finding.passed is True
    assert "persona `implementer`" in finding.detail
    assert "1-token" in finding.detail


@pytest.mark.asyncio
async def test_verify_escalation_gather_against_live_double(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-006/T018: the escalation probe's real gather runs against a loopback Telegram double.

    We patch the bot factory to point the production Bot at the local HTTP
    server via its base_url.  The real send_message path executes, including the
    HTTPXRequest timeout wiring.
    """
    token = "123456:AAAA"
    async with _loopback_telegram_listener(token) as telegram_base_url:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            _full_config_toml(
                llm_base_url="http://llm.test/v1",
                telemetry_endpoint=None,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
        monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
        monkeypatch.setenv("ERGANE_TELEGRAM_BOT_TOKEN", token)
        monkeypatch.setenv("ERGANE_TELEGRAM_CHAT_ID", "-1")

        def _local_telegram_bot_factory(config: Cfg.Escalation, *, timeout_s: int | None = None) -> Any:
            from telegram import Bot
            from telegram.request import HTTPXRequest

            return Bot(
                token,
                base_url=telegram_base_url,
                request=HTTPXRequest(
                    connection_pool_size=1,
                    connect_timeout=timeout_s,
                    read_timeout=timeout_s,
                    write_timeout=timeout_s,
                ),
            )

        monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising_temporal_factory)
        monkeypatch.setattr(verify_module, "_telegram_bot_factory", _local_telegram_bot_factory)

        from factory.controlplane.config import load_controlplane_config

        config = load_controlplane_config(str(config_path))
        probe = verify_module.EscalationProbe()
        snapshot = await probe.gather(config)

    finding = probe.evaluate(snapshot)
    assert finding.passed is True
    assert "telegram" in finding.detail
    assert "message_id=42" in finding.detail
    assert "deferred to epic 041" in finding.detail


# Keep additional CLI integration tests for a later commit.
