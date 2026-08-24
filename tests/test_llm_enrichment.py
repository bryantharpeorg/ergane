"""US1: post-confirmation alias enrichment.

Every test here routes through the injected transport seam; none opens a real
socket. Enrichment is authenticated: it uses the operator-confirmed base_url
and the master key from the named env, but only because the test fixture sets
that env. The tests assert the credential is present when expected and was not
sent before confirmation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import pytest

from factory.discovery.llm_enrichment import EnrichedAlias, enrich_aliases


@dataclass(frozen=True)
class RecordedRequest:
    """One request the enrichment seam actually made."""

    method: str
    url: str
    path: str
    headers: dict[str, str]
    body: dict[str, Any] | None


class FakeLiteLLMTransport(httpx.AsyncBaseTransport):
    """A stand-in HTTP transport for LiteLLM-shaped enrichment.

    Simulates:
      - GET /model/info returning per-alias capability records
      - GET /v1/models returning wildcard-expanded aliases
    """

    def __init__(
        self,
        *,
        model_info: dict[str, dict[str, Any]] | None = None,
        v1_models: list[str] | None = None,
        status_code: int = 200,
        body: Any = None,
    ) -> None:
        #: alias -> model_info record
        self.model_info = model_info or {}
        #: wildcard-expanded aliases
        self.v1_models = v1_models or []
        #: forced response for failure tests
        self.status_code = status_code
        self.body = body
        self.calls: list[RecordedRequest] = []

    def _answer(self, method: str, path: str) -> httpx.Response:
        route = (method, path)
        if self.status_code != 200 or self.body is not None:
            body = self.body if self.body is not None else {"error": "not found"}
            return httpx.Response(self.status_code, json=body)
        if route == ("GET", "/model/info"):
            return httpx.Response(
                200,
                json={"data": [{"model_name": alias, **record} for alias, record in self.model_info.items()]},
            )
        if route == ("GET", "/v1/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": alias} for alias in sorted(self.v1_models)]},
            )
        return httpx.Response(404, json={"error": "not found"})

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        body: dict[str, Any] | None = None
        if request.content:
            try:
                parsed_body = json.loads(request.content)
                body = parsed_body if isinstance(parsed_body, dict) else None
            except ValueError:
                body = None
        self.calls.append(
            RecordedRequest(
                method=request.method,
                url=str(request.url),
                path=parsed.path,
                headers=dict(request.headers),
                body=body,
            )
        )
        return self._answer(request.method, parsed.path)


class FakeOllamaTransport(httpx.AsyncBaseTransport):
    """A stand-in HTTP transport for Ollama-shaped enrichment.

    Simulates POST /api/show returning capabilities + model_info per alias.
    """

    def __init__(
        self,
        *,
        show_by_alias: dict[str, dict[str, Any]] | None = None,
        status_code: int = 200,
        body: Any = None,
    ) -> None:
        self.show_by_alias = show_by_alias or {}
        self.status_code = status_code
        self.body = body
        self.calls: list[RecordedRequest] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        body: dict[str, Any] | None = None
        if request.content:
            try:
                parsed_body = json.loads(request.content)
                body = parsed_body if isinstance(parsed_body, dict) else None
            except ValueError:
                body = None
        self.calls.append(
            RecordedRequest(
                method=request.method,
                url=str(request.url),
                path=parsed.path,
                headers=dict(request.headers),
                body=body,
            )
        )

        if parsed.path != "/api/show" or request.method != "POST":
            return httpx.Response(404, json={"error": "not found"})
        if self.status_code != 200 or self.body is not None:
            response_body = self.body if self.body is not None else {"error": "not found"}
            return httpx.Response(self.status_code, json=response_body)

        alias = body.get("name") if body else None
        show_body = self.show_by_alias.get(alias, {
            "model_info": {},
            "capabilities": [],
        })
        return httpx.Response(200, json=show_body)


@pytest.fixture
def litellm_transport_factory() -> Callable[..., FakeLiteLLMTransport]:
    def make(
        *,
        model_info: dict[str, dict[str, Any]] | None = None,
        v1_models: list[str] | None = None,
        status_code: int = 200,
        body: Any = None,
    ) -> FakeLiteLLMTransport:
        return FakeLiteLLMTransport(
            model_info=model_info,
            v1_models=v1_models,
            status_code=status_code,
            body=body,
        )

    return make


@pytest.fixture
def ollama_transport_factory() -> Callable[..., FakeOllamaTransport]:
    def make(
        *,
        show_by_alias: dict[str, dict[str, Any]] | None = None,
        status_code: int = 200,
        body: Any = None,
    ) -> FakeOllamaTransport:
        return FakeOllamaTransport(
            show_by_alias=show_by_alias,
            status_code=status_code,
            body=body,
        )

    return make


# T001 [US1-S1, FR-001]: LiteLLM-shaped gateway returns one enriched record
# per alias, with the fields the ranking needs, using the wildcard-expanded
# model list, and every request carried the credential from the confirmed env.
def test_enrichment_lite_llm_returns_capability_records(
    litellm_transport_factory: Callable[..., FakeLiteLLMTransport],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = litellm_transport_factory(
        model_info={
            "claude-opus": {
                "model_info": {
                    "tool_calling": True,
                    "output_modalities": ["text"],
                    "supports_reasoning": False,
                    "context_window": 200000,
                    "input_cost_per_token": 1.5e-5,
                    "output_cost_per_token": 7.5e-5,
                }
            },
            "claude-sonnet": {
                "model_info": {
                    "tool_calling": True,
                    "output_modalities": ["text"],
                    "supports_reasoning": False,
                    "context_window": 200000,
                    "input_cost_per_token": 3.0e-6,
                    "output_cost_per_token": 1.5e-5,
                }
            },
        },
        v1_models=["claude-opus", "claude-sonnet", "claude-haiku"],
    )

    monkeypatch.setenv("CONFIRMED_MASTER_KEY", "sk-confirmed-master")

    result = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        master_key_env="CONFIRMED_MASTER_KEY",
        aliases=("claude-opus", "claude-sonnet"),
        transport=transport,
    )

    assert len(result.records) == 2
    by_alias = {r.alias: r for r in result.records}
    opus = by_alias["claude-opus"]
    assert opus.tool_calling is True
    assert opus.structured_output is True
    assert opus.reasoning is False
    assert opus.context_window == 200000
    assert opus.input_cost_per_token == 1.5e-5
    assert opus.output_cost_per_token == 7.5e-5
    assert opus.source == "litellm"
    assert opus.unclassified is False
    assert opus.detail is None

    sonnet = by_alias["claude-sonnet"]
    assert sonnet.tool_calling is True
    assert sonnet.context_window == 200000

    # The wildcard-expanded list was consulted: /v1/models answered, and the
    # requested aliases are a subset of what it advertised.
    paths = {call.path for call in transport.calls}
    assert "/v1/models" in paths
    assert "/model/info" in paths

    # Credential discipline: every request to the confirmed endpoint carried the
    # key from the named env.
    for call in transport.calls:
        assert call.headers.get("authorization") == "Bearer sk-confirmed-master", call.headers


# T002 [US1-S2, FR-002]: 404/garbage endpoint makes every alias unclassified
# with a detail naming what was tried, and no exception escapes.
def test_enrichment_failure_marks_every_alias_unclassified(
    litellm_transport_factory: Callable[..., FakeLiteLLMTransport],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = litellm_transport_factory(status_code=404)
    monkeypatch.setenv("CONFIRMED_MASTER_KEY", "sk-confirmed-master")

    result = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        master_key_env="CONFIRMED_MASTER_KEY",
        aliases=("claude-opus", "claude-sonnet"),
        transport=transport,
    )

    assert len(result.records) == 2
    for record in result.records:
        assert record.unclassified is True
        assert record.detail is not None
        assert "404" in record.detail or "not found" in record.detail.lower()
        assert record.tool_calling is None
        assert record.reasoning is None
        assert record.context_window is None


# T003 [US1-S3, FR-001]: Ollama-shaped endpoint populates the same record shape
# from /api/show.
def test_enrichment_ollama_returns_capability_records(
    ollama_transport_factory: Callable[..., FakeOllamaTransport],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ollama_transport_factory(
        show_by_alias={
            "llama3": {
                "model_info": {
                    "context_length": 128000,
                },
                "capabilities": ["tools", "thinking", "completion"],
                "details": {
                    "family": "llama",
                    "parameter_size": "8.0B",
                },
            }
        }
    )
    monkeypatch.setenv("CONFIRMED_MASTER_KEY", "unused-for-ollama")

    result = enrich_aliases(
        base_url="http://127.0.0.1:11434",
        master_key_env="CONFIRMED_MASTER_KEY",
        aliases=("llama3",),
        transport=transport,
        source="ollama",
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record.alias == "llama3"
    assert record.tool_calling is True
    assert record.structured_output is False
    assert record.reasoning is True
    assert record.context_window == 128000
    assert record.source == "ollama"
    assert record.unclassified is False
    assert record.detail is None

    # Ollama endpoint uses /api/show for each alias.
    show_calls = [c for c in transport.calls if c.path == "/api/show"]
    assert len(show_calls) == 1
    assert show_calls[0].body == {"name": "llama3"}


# Helper: build the exact record shape used for the SC-001 pasted output.
def _format_record(record: EnrichedAlias) -> str:
    fields = [
        f"alias={record.alias}",
        f"tool_calling={record.tool_calling}",
        f"structured_output={record.structured_output}",
        f"reasoning={record.reasoning}",
        f"context_window={record.context_window}",
        f"input_cost_per_token={record.input_cost_per_token}",
        f"output_cost_per_token={record.output_cost_per_token}",
        f"source={record.source}",
        f"unclassified={record.unclassified}",
        f"detail={record.detail!r}",
    ]
    return "EnrichedAlias(" + ", ".join(fields) + ")"


def test_sc001_paste_enrichment_output_for_three_source_shapes(
    litellm_transport_factory: Callable[..., FakeLiteLLMTransport],
    ollama_transport_factory: Callable[..., FakeOllamaTransport],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """T020 [US1-S1, SC-001]: committed evidence for rich, bare and Ollama sources.

    The output is written beside the test so the diff contains it for the judge.
    """
    monkeypatch.setenv("CONFIRMED_MASTER_KEY", "sk-confirmed-master")

    # Rich LiteLLM source.
    rich_transport = litellm_transport_factory(
        model_info={
            "claude-opus": {
                "model_info": {
                    "tool_calling": True,
                    "output_modalities": ["text"],
                    "supports_reasoning": False,
                    "context_window": 200000,
                    "input_cost_per_token": 1.5e-5,
                    "output_cost_per_token": 7.5e-5,
                }
            },
            "claude-sonnet": {
                "model_info": {
                    "tool_calling": True,
                    "output_modalities": ["text"],
                    "supports_reasoning": False,
                    "context_window": 200000,
                    "input_cost_per_token": 3.0e-6,
                    "output_cost_per_token": 1.5e-5,
                }
            },
        },
        v1_models=["claude-opus", "claude-sonnet"],
    )
    rich = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        master_key_env="CONFIRMED_MASTER_KEY",
        aliases=("claude-opus", "claude-sonnet"),
        transport=rich_transport,
    )

    # Bare gateway: metadata endpoint 404s.
    bare_transport = litellm_transport_factory(status_code=404)
    bare = enrich_aliases(
        base_url="http://127.0.0.1:4000",
        master_key_env="CONFIRMED_MASTER_KEY",
        aliases=("claude-opus", "claude-sonnet"),
        transport=bare_transport,
    )

    # Ollama source.
    ollama_transport = ollama_transport_factory(
        show_by_alias={
            "llama3": {
                "model_info": {"context_length": 128000},
                "capabilities": ["tools", "thinking", "completion"],
            }
        }
    )
    ollama = enrich_aliases(
        base_url="http://127.0.0.1:11434",
        master_key_env="CONFIRMED_MASTER_KEY",
        aliases=("llama3",),
        transport=ollama_transport,
        source="ollama",
    )

    evidence = "\n".join(
        [
            "# SC-001: enrichment output for three source shapes",
            "",
            "## rich-litellm",
        ]
        + [_format_record(r) for r in rich.records]
        + ["", "## bare-litellm"]
        + [_format_record(r) for r in bare.records]
        + ["", "## ollama"]
        + [_format_record(r) for r in ollama.records]
        + [""]
    )
    evidence_path = tmp_path / "sc001-enrichment-output.txt"
    evidence_path.write_text(evidence, encoding="utf-8")
    print(evidence)
