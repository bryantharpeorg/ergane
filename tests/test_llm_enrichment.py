"""US1: post-confirmation alias enrichment over an injected transport.

Enrichment runs *after* the operator confirms the gateway address and master-key
env, so it is authenticated and may reach gateway metadata endpoints.  Every test
here injects an `httpx.AsyncBaseTransport` double; none opens a real socket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import pytest

from factory.discovery.llm_enrichment import enrich_aliases, EnrichmentRecord


@dataclass(frozen=True)
class RecordedRequest:
    """One request the enrichment transport actually made."""

    method: str
    url: str
    path: str
    headers: dict[str, str]


class FakeLiteLLMTransport(httpx.AsyncBaseTransport):
    """Return LiteLLM-shaped /model/info and /v1/models responses.

    Records every request so tests can prove credential discipline.
    """

    def __init__(
        self,
        *,
        model_info: dict[str, dict[str, Any]] | None = None,
        models: dict[str, list[str]] | None = None,
        dead: set[str] | None = None,
        model_info_status: dict[str, int] | None = None,
    ) -> None:
        self.model_info = model_info or {}
        self.models = models or {}
        self.dead = dead or set()
        self.model_info_status = model_info_status or {}
        self.calls: list[RecordedRequest] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        address = f"{parsed.scheme}://{parsed.netloc}"
        self.calls.append(
            RecordedRequest(
                method=request.method,
                url=str(request.url),
                path=parsed.path,
                headers=dict(request.headers),
            )
        )
        if address in self.dead:
            raise httpx.ConnectError("connection refused", request=None)
        if parsed.path == "/model/info":
            status = self.model_info_status.get(address, 200)
            if status == 404:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json=self.model_info.get(address, {}))
        if parsed.path == "/v1/models":
            aliases = sorted(self.models.get(address, []))
            return httpx.Response(
                200,
                json={
                    "data": [{"id": a} for a in aliases],
                },
            )
        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def litellm_transport_factory() -> Callable[..., FakeLiteLLMTransport]:
    def make(
        *,
        model_info: dict[str, dict[str, Any]] | None = None,
        models: dict[str, list[str]] | None = None,
        dead: set[str] | None = None,
        model_info_status: dict[str, int] | None = None,
    ) -> FakeLiteLLMTransport:
        return FakeLiteLLMTransport(
            model_info=model_info,
            models=models,
            dead=dead,
            model_info_status=model_info_status,
        )

    return make


# T001 [US1]: LiteLLM-shaped gateway returns one record per alias with ranking
# fields; no credential is sent until the confirmed document provides one.
def test_enrich_litellm_returns_capability_records(
    litellm_transport_factory: Callable[..., FakeLiteLLMTransport],
) -> None:
    model_info = {
        "http://127.0.0.1:4000": {
            "model1": {
                "litellm_params": {
                    "custom_llm_provider": "openai",
                },
                "model_info": {
                    "max_tokens": 131072,
                    "max_input_tokens": 131072,
                    "input_cost_per_token": 0.000000015,
                    "output_cost_per_token": 0.000000060,
                    "supports_function_calling": True,
                    "supports_parallel_function_calling": True,
                    "supports_vision": False,
                    "supports_response_schema": True,
                },
            },
            "model2": {
                "model_info": {
                    "max_tokens": 200000,
                    "supports_reasoning": True,
                    "supports_function_calling": False,
                    "supports_response_schema": False,
                },
            },
            "wildcard": {
                "model_info": {
                    "max_tokens": 4096,
                    "supports_function_calling": False,
                    "supports_response_schema": False,
                },
            },
        }
    }
    # model1 and model2 are returned by wildcard expansion
    models = {
        "http://127.0.0.1:4000": ["model1", "model2"],
    }
    transport = litellm_transport_factory(
        model_info=model_info,
        models=models,
    )

    # Pre-confirmation: no request should be made.  Calling without a master-key
    # env must return unclassified records and not reach the gateway.
    pre_records = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        aliases=("model1", "model2"),
        transport=transport,
    )
    assert all(r.unclassified for r in pre_records)
    pre_auth_calls = [
        c for c in transport.calls if "authorization" in {k.lower() for k in c.headers}
    ]
    assert not pre_auth_calls, "credential sent before confirmation"

    # Post-confirmation: master key env is named; we set it in the environment.
    transport.calls.clear()
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("FAKE_MASTER_KEY", "sk-fake-master")
        records = enrich_aliases(
            base_url="http://127.0.0.1:4000",
            aliases=("model1", "model2"),
            master_key_env="FAKE_MASTER_KEY",
            transport=transport,
        )

    by_alias = {r.alias: r for r in records}
    assert set(by_alias) == {"model1", "model2"}

    model1 = by_alias["model1"]
    assert model1.tool_calling is True
    assert model1.structured_output is True
    assert model1.reasoning is False
    assert model1.context_window == 131072
    assert model1.input_cost_per_token == 0.000000015
    assert model1.output_cost_per_token == 0.000000060

    model2 = by_alias["model2"]
    assert model2.tool_calling is False
    assert model2.structured_output is False
    assert model2.reasoning is True
    assert model2.context_window == 200000

    # Post-confirmation calls carried the named credential.
    for call in transport.calls:
        assert "authorization" in {k.lower() for k in call.headers}
        assert call.headers["authorization"].startswith("Bearer ")


# T002 [US1]: metadata endpoint answers 404 or garbage -> every alias
# unclassified with a detail naming what was tried; no exception escapes.
def test_enrich_unclassified_on_bad_metadata(
    litellm_transport_factory: Callable[..., FakeLiteLLMTransport],
) -> None:
    transport = litellm_transport_factory(
        model_info_status={"http://127.0.0.1:4000": 404},
        models={"http://127.0.0.1:4000": []},
    )

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("FAKE_MASTER_KEY", "sk-fake-master")
        records = enrich_aliases(
            base_url="http://127.0.0.1:4000",
            aliases=("model1", "model2"),
            master_key_env="FAKE_MASTER_KEY",
            transport=transport,
        )

    assert len(records) == 2
    for r in records:
        assert r.unclassified is True
        assert "404" in r.detail or "/model/info" in r.detail


# T002b: garbage JSON from /model/info and /v1/models missing.
def test_enrich_unclassified_on_garbage_metadata(
    litellm_transport_factory: Callable[..., FakeLiteLLMTransport],
) -> None:
    transport = litellm_transport_factory(
        model_info={"http://127.0.0.1:4000": "not-a-dict"},  # type: ignore[arg-type]
        models={"http://127.0.0.1:4000": []},
    )

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("FAKE_MASTER_KEY", "sk-fake-master")
        records = enrich_aliases(
            base_url="http://127.0.0.1:4000",
            aliases=("model1",),
            master_key_env="FAKE_MASTER_KEY",
            transport=transport,
        )

    assert len(records) == 1
    assert records[0].unclassified is True


# T003 [US1]: Ollama-shaped endpoint populates the same record type.
class FakeOllamaTransport(httpx.AsyncBaseTransport):
    """Return Ollama /api/show responses with capability families."""

    def __init__(
        self,
        *,
        show: dict[str, dict[str, Any]] | None = None,
        dead: set[str] | None = None,
    ) -> None:
        self.show = show or {}
        self.dead = dead or set()
        self.calls: list[RecordedRequest] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        address = f"{parsed.scheme}://{parsed.netloc}"
        self.calls.append(
            RecordedRequest(
                method=request.method,
                url=str(request.url),
                path=parsed.path,
                headers=dict(request.headers),
            )
        )
        if address in self.dead:
            raise httpx.ConnectError("connection refused", request=None)
        if parsed.path == "/api/show":
            name = request.content and json.loads(request.content).get("name")
            data = self.show.get(address, {}).get(name)
            if data is None:
                return httpx.Response(404, json={"error": "model not found"})
            return httpx.Response(200, json=data)
        return httpx.Response(404, json={"error": "not found"})


def test_enrich_ollama_returns_capability_records() -> None:
    show = {
        "http://127.0.0.1:11434": {
            "llama3.1": {
                "capabilities": {
                    "tools": True,
                    "structured_output": True,
                },
                "details": {
                    "context_length": 131072,
                    "parameter_size": "8B",
                },
            },
            "qwq": {
                "capabilities": {
                    "reasoning": True,
                },
                "details": {
                    "context_length": 32768,
                    "parameter_size": "32B",
                },
            },
        }
    }
    transport = FakeOllamaTransport(show=show)

    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OLLAMA_KEY", "no-matter")
        records = enrich_aliases(
            base_url="http://127.0.0.1:11434",
            aliases=("llama3.1", "qwq"),
            master_key_env="OLLAMA_KEY",
            transport=transport,
        )

    by_alias = {r.alias: r for r in records}
    assert set(by_alias) == {"llama3.1", "qwq"}

    llama = by_alias["llama3.1"]
    assert llama.tool_calling is True
    assert llama.structured_output is True
    assert llama.reasoning is False
    assert llama.context_window == 131072

    qwq = by_alias["qwq"]
    assert qwq.tool_calling is False
    assert qwq.structured_output is False
    assert qwq.reasoning is True
    assert qwq.context_window == 32768
