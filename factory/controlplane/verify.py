"""Probes for `ergane install --verify`.

Each probe follows the doctor's `Probe` protocol: a thin `gather()` that touches
one subsystem, a frozen snapshot, and a pure `evaluate()` over that snapshot.
Findings are rendered in the mergequeue `Finding(check, passed, detail)` grammar
that FR-006 actually describes — never written to the findings ledger.

The three "did not really run" cases are kept distinct:
- skipped-by-declaration: the operator set `memory = none` or left no OTLP endpoint;
- deferred: escalation lifecycle verification belongs to 041, so today's probe
  reports delivery only and says so;
- not-answering: a dependency that failed within its timeout is a failed finding.

All probe gathers are async coroutines so they can be driven from either sync CLI
context (`verify_controlplane()`) or async test context (`verify_controlplane_async()`).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from factory.controlplane.config import ControlPlaneConfig
from factory.controlplane.resolve import temporal_target_for
from factory.mergequeue.models import Finding
from factory.usage.litellm_client import LiteLLMClient

#: What a Temporal value's source is called here. Nothing renders it: findings
#: report the address, never where it came from.
_DECLARED_SOURCE = "the control-plane config"


class ServiceNotAnswering(Exception):
    """A probe's dependency would not answer — the probe fails, not masks."""

    def __init__(self, service: str, *, reason: str | None = None) -> None:
        super().__init__(f"{service} is not answering" + (f": {reason}" if reason else ""))
        self.service = service


class Probe(Protocol):
    """One verify check: a name, a thin gather, and a pure evaluation."""

    name: str

    async def gather(self, config: ControlPlaneConfig) -> Any: ...
    def evaluate(self, snapshot: Any) -> Finding: ...


# --- snapshots ----------------------------------------------------------------


@dataclass(frozen=True)
class LLMSnapshot:
    """What the LLM probe gathered: persona used, model resolved, completion shape."""

    persona: str
    model: str | None
    completed: bool
    detail: str


@dataclass(frozen=True)
class TemporalSnapshot:
    """What the Temporal probe gathered: namespace and whether it exists."""

    address: str
    namespace: str
    namespace_exists: bool
    detail: str


@dataclass(frozen=True)
class MemorySnapshot:
    """What the memory probe gathered: backend choice and reachability result."""

    backend: str
    reachable: bool
    detail: str


@dataclass(frozen=True)
class TelemetrySnapshot:
    """What the telemetry probe gathered: mode and export result."""

    mode: str
    exported: bool
    detail: str


@dataclass(frozen=True)
class EscalationSnapshot:
    """What the escalation probe gathered: transport and delivery result."""

    adapter: str
    delivered: bool
    detail: str


# --- seams for tests / live doubles ------------------------------------------


def _llm_client_factory(config: ControlPlaneConfig.LLM) -> LiteLLMClient:
    """Build the real LiteLLM admin client from the environment.

    `gateway` is the only mode that reaches here: the parser refuses every other
    value before a probe is constructed (048-US2, D-048).
    """
    assert config.gateway is not None
    return LiteLLMClient.from_env()


async def _temporal_client_factory(config: ControlPlaneConfig.Temporal) -> Any:
    """Build the real Temporalio client, under the one precedence (048-US4).

    This read `config.address or os.environ.get("TEMPORAL_ADDRESS", ...)` — the
    config *first*, one of only two such sites in the tree. Since the parser
    requires `temporal.address` the fallback never fired, so the probe dialed
    the declared address and ignored `TEMPORAL_ADDRESS` outright: where the two
    disagreed, `ergane install --verify` reported on one server while the worker
    connected to another (FR-016, SC-006). `temporal_target_for` rather than
    `resolve_temporal_target` because the caller was pointed at one specific
    file and has already parsed it.
    """
    from temporalio.client import Client

    target = temporal_target_for(config, source=_DECLARED_SOURCE)
    return await Client.connect(target.address, namespace=target.namespace)


async def _describe_temporal_namespace(
    config: ControlPlaneConfig.Temporal,
    namespace: str,
) -> str:
    """Connect and ask the server about `namespace`, returning the name it reports.

    Raises `RPCError` with `NOT_FOUND` when the namespace is not registered —
    the one condition that means "create it".  Kept separate from the probe so
    the whole connect-plus-describe round trip can be wrapped in a single
    timeout by the caller.
    """
    from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

    client = await _temporal_client_factory(config)
    response = await client.service_client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=namespace)
    )
    return response.namespace_info.name


def _memory_client_factory(config: ControlPlaneConfig.Memory) -> httpx.AsyncClient:
    """Build an HTTP client for the memory backend if it has a URL."""
    assert config.url is not None
    return httpx.AsyncClient(base_url=config.url.rstrip("/"), timeout=config.timeout_s)


def _telegram_bot_factory(config: ControlPlaneConfig.Escalation, *, timeout_s: int | None = None) -> Any:
    """Build the real Telegram bot from the environment.

    Tests can patch this seam; the default uses HTTPXRequest so connect/read/write
    timeouts are honored and a dead port fails within its bound.
    """
    from telegram import Bot
    from telegram.request import HTTPXRequest

    token_env = config.bot_token_env or "TELEGRAM_BOT_TOKEN"
    token = os.environ.get(token_env)
    if not token:
        raise ServiceNotAnswering("escalation", reason=f"{token_env} is not set")
    request = HTTPXRequest(
        connection_pool_size=1,
        connect_timeout=timeout_s,
        read_timeout=timeout_s,
        write_timeout=timeout_s,
    )
    return Bot(token, request=request)


# --- probes -------------------------------------------------------------------


class LLMProbe:
    """Completes one token through the configured LLM endpoint."""

    name = "llm"

    async def gather(self, config: ControlPlaneConfig) -> LLMSnapshot:
        from factory.config import load_personas

        # `gateway` is the only mode a parsed config can carry (048-US2).
        persona = "implementer"
        registry = load_personas()
        p = registry.get(persona)
        model = p.model if p else None
        gateway = config.llm.gateway
        assert gateway is not None
        base_url = gateway.base_url
        api_key_env = gateway.master_key_env
        api_key = os.environ.get(api_key_env)
        timeout = config.llm.timeout_s

        if not api_key:
            return LLMSnapshot(
                persona=persona,
                model=model,
                completed=False,
                detail=f"{api_key_env} is not set; no credential to complete a round trip",
            )

        async def _do_completion() -> bool:
            """POST a 1-token completion to the configured endpoint and return whether choices arrived."""
            async with httpx.AsyncClient(
                base_url=base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            ) as http_client:
                response = await http_client.post("/chat/completions", json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                })
                response.raise_for_status()
                data = response.json()
                return bool(data.get("choices"))

        try:
            client = _llm_client_factory(config.llm)
            if hasattr(client, "chat_completion"):
                response_data = await client.chat_completion(
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    }
                )
                completed = bool(response_data.get("choices"))
                await client.aclose()
            else:
                completed = await _do_completion()
        except httpx.TimeoutException:
            return LLMSnapshot(
                persona=persona,
                model=model,
                completed=False,
                detail=f"timed out after {timeout}s waiting for LLM completion at {base_url}",
            )
        except Exception as exc:
            # A refused or unreachable host should still name the endpoint so the
            # operator knows which subsystem did not answer.
            detail = f"LLM completion failed at {base_url}: {type(exc).__name__}: {exc}"
            return LLMSnapshot(
                persona=persona,
                model=model,
                completed=False,
                detail=detail,
            )
        return LLMSnapshot(
            persona=persona,
            model=model,
            completed=completed,
            detail=(
                f"completed a 1-token completion against persona `{persona}`"
                f"{' (model ' + model + ')' if model else ''}"
            )
            if completed
            else f"completion returned no choices for persona `{persona}`",
        )

    def evaluate(self, snapshot: LLMSnapshot) -> Finding:
        return Finding(
            check="llm",
            passed=snapshot.completed,
            detail=snapshot.detail,
        )


class TemporalProbe:
    """Pings Temporal and confirms the configured namespace exists.

    The question this probe asks is `DescribeNamespace`, not "does some workflow
    exist".  Those are different objects: a healthy factory host answers
    `NOT_FOUND` for the workflow id `ergane-install-verify` while the namespace
    is registered, so describing a workflow reports every correctly-installed
    host as missing its namespace and tells the operator to create one that is
    already there.

    `describe_namespace` lives on the *workflow* service in temporalio 1.31.0
    (the operator service carries only `delete_namespace`), which is why the
    call below goes through `service_client.workflow_service`.
    """

    name = "temporal"

    async def gather(self, config: ControlPlaneConfig) -> TemporalSnapshot:
        from temporalio.service import RPCError, RPCStatusCode

        # Resolved once, and the same resolution the connect below is built
        # from, so the address this finding names is the one it dialed (SC-006).
        target = temporal_target_for(config.temporal, source=_DECLARED_SOURCE)
        address, namespace = target.address, target.namespace
        timeout = config.temporal.timeout_s

        try:
            # The whole round trip is bounded, connect included.  An address that
            # accepts and never answers — as opposed to one that refuses — leaves
            # `Client.connect` waiting forever, and a timeout branch that can only
            # be reached after an exception surfaces never runs at all.
            await asyncio.wait_for(
                _describe_temporal_namespace(config.temporal, namespace),
                timeout,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return TemporalSnapshot(
                address=address,
                namespace=namespace,
                namespace_exists=False,
                detail=f"timed out after {timeout}s waiting for Temporal at {address}",
            )
        except RPCError as exc:
            if exc.status is RPCStatusCode.NOT_FOUND:
                # The server answered, and it does not know this namespace.
                return TemporalSnapshot(
                    address=address,
                    namespace=namespace,
                    namespace_exists=False,
                    detail=(
                        f"Temporal at {address} does not have namespace `{namespace}`; "
                        f"create it with `temporal operator namespace create {namespace}`"
                    ),
                )
            return TemporalSnapshot(
                address=address,
                namespace=namespace,
                namespace_exists=False,
                detail=f"Temporal at {address} could not confirm namespace `{namespace}`: {type(exc).__name__}: {exc}",
            )
        except Exception as exc:
            return TemporalSnapshot(
                address=address,
                namespace=namespace,
                namespace_exists=False,
                detail=f"Temporal at {address} did not answer: {type(exc).__name__}: {exc}",
            )

        return TemporalSnapshot(
            address=address,
            namespace=namespace,
            namespace_exists=True,
            detail=f"Temporal at {address} has namespace `{namespace}`",
        )

    def evaluate(self, snapshot: TemporalSnapshot) -> Finding:
        return Finding(
            check="temporal",
            passed=snapshot.namespace_exists,
            detail=snapshot.detail,
        )


class MemoryProbe:
    """Reaches the configured memory backend, or reports skipped if `none`."""

    name = "memory"

    async def gather(self, config: ControlPlaneConfig) -> MemorySnapshot:
        if config.memory.backend == "none":
            return MemorySnapshot(
                backend="none",
                reachable=False,
                detail="skipped by declaration: memory.backend is `none`",
            )

        if config.memory.backend == "hindsight":
            url = config.memory.url
            if not url:
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=False,
                    detail="memory.backend is `hindsight` but no url is configured",
                )
            client: httpx.AsyncClient | None = None
            try:
                client = _memory_client_factory(config.memory)
                response = await client.get("/health")
                response.raise_for_status()
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=True,
                    detail=f"reached hindsight memory backend at {url}",
                )
            except httpx.TimeoutException:
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=False,
                    detail=f"timed out after {config.memory.timeout_s}s waiting for hindsight at {url}",
                )
            except Exception as exc:
                return MemorySnapshot(
                    backend="hindsight",
                    reachable=False,
                    detail=f"could not reach hindsight at {url}: {type(exc).__name__}: {exc}",
                )
            finally:
                if client is not None:
                    await client.aclose()

        return MemorySnapshot(
            backend=config.memory.backend,
            reachable=False,
            detail=f"memory backend `{config.memory.backend}` has no gather implementation",
        )

    def evaluate(self, snapshot: MemorySnapshot) -> Finding:
        if snapshot.backend == "none":
            return Finding(check="memory", passed=True, detail=snapshot.detail)
        return Finding(
            check="memory",
            passed=snapshot.reachable,
            detail=snapshot.detail,
        )


class TelemetryProbe:
    """Resolves and exports a test datapoint to the OTLP endpoint, or reports skipped."""

    name = "telemetry"

    async def gather(self, config: ControlPlaneConfig) -> TelemetrySnapshot:
        if config.telemetry.mode == "none":
            return TelemetrySnapshot(
                mode="none",
                exported=False,
                detail="skipped by declaration: telemetry has no otlp_endpoint",
            )

        endpoint = config.telemetry.otlp_endpoint
        assert endpoint is not None
        timeout = config.telemetry.timeout_s

        client: httpx.AsyncClient | None = None
        try:
            client = httpx.AsyncClient(timeout=timeout)
            # OTLP/HTTP trace export: a minimal JSON body the collector accepts.
            payload = {
                "resourceSpans": [
                    {
                        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "ergane-verify"}}]},
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "traceId": "00000000000000000000000000000000",
                                        "spanId": "0000000000000000",
                                        "name": "ergane-install-verify",
                                        "kind": 1,
                                        "startTimeUnixNano": str(int(time.time() * 1e9)),
                                        "endTimeUnixNano": str(int(time.time() * 1e9)),
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
            url = endpoint.rstrip("/") + "/v1/traces"
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return TelemetrySnapshot(
                mode="otlp",
                exported=True,
                detail=f"exported a test trace span to OTLP endpoint {endpoint}",
            )
        except httpx.TimeoutException:
            return TelemetrySnapshot(
                mode="otlp",
                exported=False,
                detail=f"timed out after {timeout}s waiting for OTLP endpoint {endpoint}",
            )
        except Exception as exc:
            return TelemetrySnapshot(
                mode="otlp",
                exported=False,
                detail=f"could not export to OTLP endpoint {endpoint}: {type(exc).__name__}: {exc}",
            )
        finally:
            if client is not None:
                await client.aclose()

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding:
        if snapshot.mode == "none":
            return Finding(check="telemetry", passed=True, detail=snapshot.detail)
        return Finding(
            check="telemetry",
            passed=snapshot.exported,
            detail=snapshot.detail,
        )


class EscalationProbe:
    """Delivers a test message through the configured Telegram transport.

    Lifecycle verification (deliver and watch the timer expire) belongs to 041;
    this probe reports delivery and explicitly defers lifecycle proof.
    """

    name = "escalation"

    async def gather(self, config: ControlPlaneConfig) -> EscalationSnapshot:
        if config.escalation.adapter != "telegram":
            return EscalationSnapshot(
                adapter=config.escalation.adapter,
                delivered=False,
                detail=f"escalation adapter `{config.escalation.adapter}` has no gather implementation",
            )

        chat_id_env = config.escalation.chat_id_env or "TELEGRAM_CHAT_ID"
        bot_token_env = config.escalation.bot_token_env or "TELEGRAM_BOT_TOKEN"
        chat_id = os.environ.get(chat_id_env)
        bot_token = os.environ.get(bot_token_env)
        if not chat_id or not bot_token:
            return EscalationSnapshot(
                adapter="telegram",
                delivered=False,
                detail=f"{chat_id_env if not chat_id else bot_token_env} is not set; cannot deliver a test escalation",
            )

        try:
            bot = _telegram_bot_factory(config.escalation, timeout_s=config.escalation.timeout_s)
            message = await bot.send_message(
                chat_id=chat_id,
                text="ergane install --verify test message",
            )
            return EscalationSnapshot(
                adapter="telegram",
                delivered=True,
                detail=(
                    f"delivered a test message through telegram (message_id={message.message_id}); "
                    "lifecycle verification (deliver + expire) is deferred to epic 041"
                ),
            )
        except Exception as exc:
            return EscalationSnapshot(
                adapter="telegram",
                delivered=False,
                detail=f"could not deliver telegram test message: {type(exc).__name__}: {exc}",
            )

    def evaluate(self, snapshot: EscalationSnapshot) -> Finding:
        passed = snapshot.delivered
        detail = snapshot.detail
        if passed and "deferred" not in detail.lower():
            detail += "; lifecycle verification is deferred to epic 041"
        return Finding(check="escalation", passed=passed, detail=detail)


REGISTRY: list[Probe] = [
    LLMProbe(),
    TemporalProbe(),
    MemoryProbe(),
    TelemetryProbe(),
    EscalationProbe(),
]


# --- public entries -----------------------------------------------------------


async def verify_controlplane_async(config_path: str | None = None) -> tuple[list[Finding], int]:
    """Async entry: run every probe and return findings plus an exit code."""
    from factory.controlplane.config import load_controlplane_config

    config = load_controlplane_config(config_path)
    findings: list[Finding] = []
    for probe in REGISTRY:
        try:
            snapshot = await probe.gather(config)
        except ServiceNotAnswering as exc:
            findings.append(Finding(check=probe.name, passed=False, detail=str(exc)))
            continue
        except Exception as exc:
            findings.append(
                Finding(
                    check=probe.name,
                    passed=False,
                    detail=f"probe failed unexpectedly: {type(exc).__name__}: {exc}",
                )
            )
            continue
        findings.append(probe.evaluate(snapshot))

    exit_code = 0 if all(f.passed for f in findings) else 1
    return findings, exit_code


def verify_controlplane(config_path: str | None = None) -> tuple[list[Finding], int]:
    """Sync entry for the CLI: run every probe in a fresh event loop."""
    return asyncio.run(verify_controlplane_async(config_path))


def render_findings(findings: list[Finding]) -> str:
    """Render findings as a concise report for the operator."""
    lines: list[str] = []
    for finding in findings:
        status = "PASS" if finding.passed else "FAIL"
        lines.append(f"[{status}] {finding.check}: {finding.detail}")
    return "\n".join(lines)
