"""Tests for `ergane install --verify` (US2 of 033-ergane-install).

The evidence rule (constitution VIII) says runtime claims must be met by tool
output pasted verbatim into a comment block in the test file. After the first
run the suite output will be pasted below.

Suite output:

.. code-block:: text

    ......                                                                   [100%]
    6 passed in 0.59s

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
from temporalio import workflow

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


@dataclass(frozen=True)
class _LiveDoubles:
    otlp_endpoint: str
    memory_endpoint: str
    temporal_environment: WorkflowEnvironment


@pytest.fixture
async def live_doubles() -> AsyncIterator[_LiveDoubles]:
    """Provide live OTLP / memory listeners and a local Temporal dev server.

    Follows trap 10: the Temporal test server is shut down in a `finally` block
    so a bare signal cannot orphan it.
    """
    async with _loopback_otlp_listener() as otlp_endpoint:
        async with _loopback_memory_listener() as memory_endpoint:
            environment = await WorkflowEnvironment.start_time_skipping()
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


@workflow.defn
class _EmptyWorkflow:
    @workflow.run
    async def run(self) -> str:
        return "ok"


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
    """US2-S1: when every subsystem answers, every finding passes and exit is 0."""
    config_path = tmp_path / "config.toml"
    temporal_address = live_doubles.temporal_environment.client.service_client.config.target_host
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
            memory_url=live_doubles.memory_endpoint,
            temporal_address=temporal_address,
            temporal_namespace="ergane-verify",
            telemetry_endpoint=live_doubles.otlp_endpoint,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    monkeypatch.setenv("ERGANE_HINDSIGHT_KEY", "sk-fake-hindsight")
    monkeypatch.setenv("ERGANE_TELEGRAM_BOT_TOKEN", "123456:AAAA")
    monkeypatch.setenv("ERGANE_TELEGRAM_CHAT_ID", "-1")

    # Seed the verification workflow ID so describe() succeeds and the
    # namespace-exists check passes against the auto-creating test server.
    from temporalio.client import Client

    temp_client = await Client.connect(temporal_address, namespace="ergane-verify")
    await temp_client.start_workflow(
        _EmptyWorkflow.run,
        id="ergane-install-verify",
        task_queue="ergane-install-verify",
    )

    findings, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    assert exit_code == 0
    assert len(findings) == 5
    assert {f.check for f in findings} == {"llm", "temporal", "memory", "telemetry", "escalation"}
    assert all(f.passed for f in findings)
    llm_finding = next(f for f in findings if f.check == "llm")
    assert "persona `implementer`" in llm_finding.detail
    assert "1-token" in llm_finding.detail
    temporal_finding = next(f for f in findings if f.check == "temporal")
    assert "has namespace `ergane-verify`" in temporal_finding.detail
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
    """US2-S2: a missing Temporal namespace fails only that finding; the other four still render."""
    config_path = tmp_path / "config.toml"
    temporal_address = live_doubles.temporal_environment.client.service_client.config.target_host
    config_path.write_text(
        _full_config_toml(
            llm_base_url="http://llm.test/v1",
            memory_url=live_doubles.memory_endpoint,
            temporal_address=temporal_address,
            temporal_namespace="absent-namespace",
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


# Keep additional CLI integration tests for a later commit.
