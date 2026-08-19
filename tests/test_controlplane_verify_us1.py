"""US1 of 061: `ergane install --verify` proves the gateway can mint a key.

These tests drive `LLMProbe.gather` through its injected seam and assert the
*verdict* changes between a simulated dispatchable gateway and a simulated
inference-only one.  Asserting only that `/key/generate` is called would be a
presence test — the defect this spec is fixing.  The evidence rule
(constitution VIII) means runtime claims are met by test output pasted into the
file.

Suite output after implementation:

.. code-block:: text

    7 passed in 0.07s
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import httpx
import pytest

import factory.controlplane.verify as verify_module
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.controlplane.config import load_controlplane_config
from factory.discovery.llm_scanner import EndpointClassification
from factory.mergequeue.models import Finding
from factory.usage.litellm_client import LiteLLMClient


# ---------------------------------------------------------------------------
# Simulated gateway seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RecordedGatewayRequest:
    """One request the simulated gateway received."""

    method: str
    path: str
    params: dict[str, str]
    body: dict[str, Any] | None


class _GatewayTransport(httpx.AsyncBaseTransport):
    """Stateful double for the LLM gateway's authenticated admin + chat API.

    This is the transport injected into the LiteLLM admin client the probe
    builds via `_llm_client_factory`.  It answers every endpoint the full
    key-management probe touches, so no real socket is opened.
    """

    def __init__(
        self,
        *,
        served_aliases: list[str] | None = None,
        key_generate_200: bool = True,
        key_models: list[str] | None = None,
        key_generate_body_hook: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        spend_logs_200: bool = True,
        chat_200: bool = True,
    ) -> None:
        self.served_aliases = served_aliases or ["ollama-cloud/kimi-k2.7-code"]
        self.key_generate_200 = key_generate_200
        self.key_models = key_models if key_models is not None else ["ollama-cloud/kimi-k2.7-code"]
        self.key_generate_body_hook = key_generate_body_hook
        self.spend_logs_200 = spend_logs_200
        self.chat_200 = chat_200

        self.keys: dict[str, dict[str, Any]] = {}
        self.calls: list[_RecordedGatewayRequest] = []
        self._issued = 0

    def _record(self, request: httpx.Request) -> None:
        body: dict[str, Any] | None = None
        if request.content:
            try:
                parsed = json.loads(request.content)
                body = parsed if isinstance(parsed, dict) else None
            except ValueError:
                body = None
        self.calls.append(
            _RecordedGatewayRequest(
                method=request.method,
                path=request.url.path,
                params=dict(request.url.params),
                body=body,
            )
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._record(request)
        path = request.url.path
        route = (request.method, path)

        if route == ("GET", "/v1/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": a} for a in sorted(self.served_aliases)]},
            )

        if route == ("POST", "/chat/completions"):
            if not self.chat_200:
                return httpx.Response(503, json={"error": {"message": "chat unavailable"}})
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "pong"}}]},
            )

        if route == ("POST", "/key/generate"):
            if not self.key_generate_200:
                return httpx.Response(404, json={"error": {"message": "Unknown route"}})
            body = self._recorded_body(request)
            self._issued += 1
            key = f"sk-verify-us1-{self._issued}"
            stored = dict(body)
            if self.key_generate_body_hook:
                stored = self.key_generate_body_hook(stored)
            models = list(stored.get("models") if stored.get("models") is not None else self.key_models)
            self.keys[key] = {
                "key": key,
                "key_alias": stored.get("key_alias", "verify-probe"),
                "models": models,
                "metadata": dict(stored.get("metadata") or {}),
                "duration": stored.get("duration"),
            }
            return httpx.Response(
                200,
                json={
                    "key": key,
                    "key_alias": self.keys[key]["key_alias"],
                    "models": self.keys[key]["models"],
                    "metadata": self.keys[key]["metadata"],
                    "duration": self.keys[key]["duration"],
                    "max_budget": None,
                    "spend": 0.0,
                    "expires": None,
                },
            )

        if route == ("GET", "/key/info"):
            key = request.url.params.get("key")
            record = self.keys.get(key)
            if record is None:
                return httpx.Response(404, json={"error": {"message": "key not found"}})
            return httpx.Response(
                200,
                json={
                    "key": key,
                    "info": {
                        "key_alias": record["key_alias"],
                        "spend": 0.0,
                        "models": record["models"],
                        "metadata": record["metadata"],
                        "max_budget": None,
                        "expires": None,
                    },
                },
            )

        if route == ("POST", "/key/delete"):
            body = self._recorded_body(request)
            keys = body.get("keys") or []
            deleted: list[str] = []
            for token in keys:
                raw = token
                if raw.startswith("hash-"):
                    raw = raw[5:]
                if raw in self.keys:
                    del self.keys[raw]
                    deleted.append(raw)
            if not deleted:
                return httpx.Response(404, json={"error": {"message": "no matching keys found"}})
            return httpx.Response(200, json={"deleted_keys": deleted})

        if route == ("GET", "/spend/logs/v2"):
            if not self.spend_logs_200:
                return httpx.Response(404, json={"error": {"message": "Unknown route"}})
            return httpx.Response(
                200,
                json={"data": [], "total_records": 0, "current_page": 1, "total_pages": 1},
            )

        return httpx.Response(404, json={"error": {"message": f"Unknown route {path}"}})

    @staticmethod
    def _recorded_body(request: httpx.Request) -> dict[str, Any]:
        if not request.content:
            return {}
        try:
            parsed = json.loads(request.content)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}


class _GatewayClient:
    """LiteLLM-shaped client that funnels admin + chat calls through the transport."""

    def __init__(self, config: Cfg.LLM, transport: _GatewayTransport) -> None:
        assert config.gateway is not None
        self._base_url = config.gateway.base_url.rstrip("/")
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=5.0,
            )
        return self._client

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        client = await self._ensure_client()
        response = await client.post("/chat/completions", json=request)
        response.raise_for_status()
        return response.json()

    async def issue_key(
        self,
        *,
        key_alias: str,
        models: list[str],
        metadata: dict[str, Any] | None = None,
        ttl: str | None = None,
    ) -> str:
        client = await self._ensure_client()
        payload: dict[str, Any] = {
            "key_alias": key_alias,
            "models": models,
            "metadata": metadata or {},
        }
        if ttl is not None:
            payload["duration"] = ttl
        response = await client.post("/key/generate", json=payload)
        response.raise_for_status()
        body = response.json()
        key = body.get("key")
        if not isinstance(key, str) or not key:
            raise RuntimeError("/key/generate returned no key")
        return key

    async def get_key_info(self, key: str) -> dict[str, Any]:
        client = await self._ensure_client()
        response = await client.get("/key/info", params={"key": key})
        response.raise_for_status()
        return response.json()

    async def revoke_key_by_tokens(self, keys: list[str]) -> bool:
        client = await self._ensure_client()
        response = await client.post("/key/delete", json={"keys": keys})
        response.raise_for_status()
        return True

    async def fetch_spend_log_rows(self, key: str, *, issued_at: str) -> list[dict[str, Any]]:
        import hashlib
        from datetime import datetime, timedelta, timezone

        client = await self._ensure_client()
        now = datetime.now(timezone.utc)
        try:
            issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
        except ValueError:
            issued = now - timedelta(days=1)
        start = min(issued, now) - timedelta(days=1)
        end = now + timedelta(days=1)
        response = await client.get(
            "/spend/logs/v2",
            params={
                "api_key": hashlib.sha256(key.encode()).hexdigest(),
                "start_date": start.date().isoformat(),
                "end_date": end.date().isoformat(),
                "page": 1,
                "page_size": 100,
            },
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data")
        if not isinstance(data, list):
            raise RuntimeError("/spend/logs/v2 returned no row array")
        return data

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class _GatewayClientFactory:
    """Build a client wired to a `_GatewayTransport`."""

    def __init__(self, transport: _GatewayTransport) -> None:
        self.transport = transport

    def __call__(self, config: Cfg.LLM) -> _GatewayClient:
        return _GatewayClient(config, self.transport)


@pytest.fixture
def gateway_transport() -> _GatewayTransport:
    return _GatewayTransport()


@pytest.fixture
def gateway_client_factory(gateway_transport: _GatewayTransport) -> _GatewayClientFactory:
    return _GatewayClientFactory(gateway_transport)


def _write_config(tmp_path: Path, *, llm_base_url: str = "http://gateway.test") -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'version = 1\n\n[llm]\nmode = "gateway"\nbase_url = "{llm_base_url}"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n\n[memory]\nbackend = "none"\n\n'
        '[temporal]\nmode = "managed"\n\n[telemetry]\n\n[escalation]\nadapter = "none"\n',
        encoding="utf-8",
    )
    return config_path


# ---------------------------------------------------------------------------
# T001 [US1-S1] inference-only gateway fails, naming key management + database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_verify_fails_when_key_management_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_transport: _GatewayTransport,
    gateway_client_factory: _GatewayClientFactory,
) -> None:
    """US1-S1: a gateway that answers chat but 404s /key/generate fails the llm check.

    The failure must name key management as the missing capability and the
    database backing (a config-only LiteLLM proxy) as its usual cause.
    """
    gateway_transport.key_generate_200 = False
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-verify-master")
    monkeypatch.setattr(verify_module, "_llm_client_factory", gateway_client_factory)

    config = load_controlplane_config(str(config_path))
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    lowered = finding.detail.lower()
    assert "key management" in lowered or "/key/generate" in lowered
    assert "database" in lowered or "database_url" in lowered


# ---------------------------------------------------------------------------
# T002 [US1-S2] fully-dispatchable gateway passes (trap 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_verify_passes_when_gateway_is_dispatchable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_transport: _GatewayTransport,
    gateway_client_factory: _GatewayClientFactory,
) -> None:
    """US1-S2: a gateway that answers /v1/models, /chat/completions and /key/generate passes."""
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-verify-master")
    monkeypatch.setattr(verify_module, "_llm_client_factory", gateway_client_factory)

    config = load_controlplane_config(str(config_path))
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True
    assert "1-token" in finding.detail
    assert "distinct alias" in finding.detail


# ---------------------------------------------------------------------------
# T003 [US1-S3] mint, assert model constraint, revoke — even on assertion fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_verify_mints_asserts_revokes_and_revokes_on_assertion_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_transport: _GatewayTransport,
    gateway_client_factory: _GatewayClientFactory,
) -> None:
    """US1-S3: the probe calls /key/generate, /key/info, /key/delete; finally revokes.

    Even when the model-constraint assertion between mint and revoke raises,
    the key is still revoked (FR-002).  The key work is not multiplied per
    persona, only per distinct alias.
    """
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-verify-master")
    monkeypatch.setattr(verify_module, "_llm_client_factory", gateway_client_factory)

    config = load_controlplane_config(str(config_path))
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True
    routes = [call.path for call in gateway_transport.calls]
    assert routes.count("/key/generate") == 1
    assert routes.count("/key/info") >= 1
    assert routes.count("/spend/logs/v2") >= 1
    assert routes.count("/key/delete") == 1
    generate_call = next(c for c in gateway_transport.calls if c.path == "/key/generate")
    assert generate_call.body is not None
    assert generate_call.body.get("duration") is not None
    # The probe sends every distinct alias the registry can dispatch.
    expected_aliases = {
        alias
        for persona in verify_module._load_personas_for_probe().values()
        if getattr(persona, "is_llm", True)
        for alias in (persona.model, persona.fallback)
        if alias
    }
    assert set(generate_call.body.get("models") or []) == expected_aliases

    # Force an assertion failure between mint and revoke by making the constraint
    # check deliberately fail, and confirm /key/delete still ran.
    forced_transport = _GatewayTransport(
        served_aliases=gateway_transport.served_aliases,
        key_generate_200=True,
        key_models=gateway_transport.key_models,
        key_generate_body_hook=lambda body: {**body, "models": []},
    )
    forced_factory = _GatewayClientFactory(forced_transport)
    monkeypatch.setattr(verify_module, "_llm_client_factory", forced_factory)

    probe2 = verify_module.LLMProbe()
    snapshot2 = await probe2.gather(config)
    finding2 = probe2.evaluate(snapshot2)

    # The minted key had an empty models list, so the assertion should fail.
    assert finding2.passed is False
    forced_routes = [call.path for call in forced_transport.calls]
    assert forced_routes.count("/key/generate") == 1
    assert forced_routes.count("/key/delete") == 1
    assert len(forced_transport.keys) == 0, "the minted key must be revoked even on assertion failure"


# ---------------------------------------------------------------------------
# T004 [US1-S4] classification comes from llm_scanner, not redefined
# ---------------------------------------------------------------------------


def test_llm_verify_imports_classification_from_scanner() -> None:
    """US1-S4: the probe reuses `EndpointClassification` from `llm_scanner`.

    We verify this by checking the module-level symbol used by `verify.py` is
    the same object as the one exported by `llm_scanner`.
    """
    from factory.discovery import llm_scanner

    assert verify_module.EndpointClassification is EndpointClassification
    assert verify_module.EndpointClassification is llm_scanner.EndpointClassification
    assert {e.name for e in EndpointClassification} == {"DISPATCHABLE", "INFERENCE_ONLY"}


# ---------------------------------------------------------------------------
# T005 [US1-S5] unconstrained key fails, naming the missing model constraint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_verify_fails_when_key_is_unconstrained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_transport: _GatewayTransport,
) -> None:
    """US1-S5: a gateway that mints a key with no model constraint fails the check.

    Per-attempt model constraint is the property `llm.mode = "direct"` was
    refused to protect.
    """
    # Make the gateway mint a key whose returned `models` list is empty even
    # though the request asked for the registry aliases.
    transport = _GatewayTransport(
        served_aliases=gateway_transport.served_aliases,
        key_generate_200=True,
        key_generate_body_hook=lambda body: {**body, "models": []},
    )
    factory = _GatewayClientFactory(transport)
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-verify-master")
    monkeypatch.setattr(verify_module, "_llm_client_factory", factory)

    config = load_controlplane_config(str(config_path))
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    lowered = finding.detail.lower()
    assert "model" in lowered and "constraint" in lowered
    routes = [call.path for call in transport.calls]
    assert routes.count("/key/generate") == 1
    assert routes.count("/key/delete") == 1
    assert len(transport.keys) == 0


# ---------------------------------------------------------------------------
# T006 [Edge] /spend/logs/v2 404 names which endpoint failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_verify_fails_naming_spend_logs_when_it_404s(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_transport: _GatewayTransport,
) -> None:
    """US1 edge: when /spend/logs/v2 404s, the failure names that endpoint."""
    transport = _GatewayTransport(
        served_aliases=gateway_transport.served_aliases,
        key_generate_200=True,
        key_models=gateway_transport.key_models,
        spend_logs_200=False,
    )
    factory = _GatewayClientFactory(transport)
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-verify-master")
    monkeypatch.setattr(verify_module, "_llm_client_factory", factory)

    config = load_controlplane_config(str(config_path))
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    lowered = finding.detail.lower()
    assert "/spend/logs/v2" in lowered or "spend logs" in lowered


# ---------------------------------------------------------------------------
# T007 [054/US3] per-distinct-alias behaviour survives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_verify_distinct_alias_count_not_persona_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1/054-US3: completions are issued per distinct alias, not per persona.

    We inject a registry with two personas sharing one alias and a second persona
    using a distinct alias; the number of chat completions is two, not three, and
    the key-management work happens once.
    """
    registry = {
        "architect": SimpleNamespace(
            is_llm=True,
            model="shared-alias",
            fallback=None,
        ),
        "implementer": SimpleNamespace(
            is_llm=True,
            model="shared-alias",
            fallback="other-alias",
        ),
        "judge": SimpleNamespace(
            is_llm=True,
            model="other-alias",
            fallback=None,
        ),
    }

    transport = _GatewayTransport(
        served_aliases=["shared-alias", "other-alias"],
        key_generate_200=True,
        key_models=["shared-alias", "other-alias"],
    )
    factory = _GatewayClientFactory(transport)

    config_path = _write_config(tmp_path)
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-verify-master")
    monkeypatch.setattr(verify_module, "_llm_client_factory", factory)
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)

    config = load_controlplane_config(str(config_path))
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True
    chat_calls = [c for c in transport.calls if c.path == "/chat/completions"]
    assert len(chat_calls) == 2, "one completion per distinct alias, not per persona"
    model_names = {c.body.get("model") for c in chat_calls if c.body}
    assert model_names == {"shared-alias", "other-alias"}
    # Key management is not multiplied by persona.
    assert [c.path for c in transport.calls].count("/key/generate") == 1
    assert [c.path for c in transport.calls].count("/key/delete") == 1
