"""Post-confirmation alias enrichment for `ergane install` (US1).

After the operator confirms the gateway address and master-key env, this step
fetches per-alias capability metadata from the confirmed endpoint. It runs
*after* confirmation so the master key can be presented safely (FR-001).

Every network touch goes through an injected `httpx.AsyncBaseTransport` seam, the
same discipline as `factory.discovery.llm_scanner`.

Two gateway shapes are supported:
  - LiteLLM-shaped: `GET /model/info` plus the wildcard-expanded `GET /v1/models`
    list. Aliases advertised by `/v1/models` are enriched from `/model/info`.
  - Ollama-shaped: `POST /api/show` per alias.

Aliases with no usable metadata are represented as `unclassified` with a detail
naming what was tried; enrichment never aborts by exception (FR-002).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Iterable

import httpx


#: LiteLLM-shaped capability endpoint.
_MODEL_INFO_PATH = "/model/info"
#: OpenAI-compatible wildcard-expanded model list.
_V1_MODELS_PATH = "/v1/models"
#: Ollama model information endpoint.
_OLLAMA_SHOW_PATH = "/api/show"


@dataclass(frozen=True)
class EnrichedAlias:
    """One alias's capability record, the single shape all sources share."""

    alias: str
    #: True if the gateway declares tool/function calling support.
    tool_calling: bool | None
    #: True if the gateway declares structured-output (JSON schema) support.
    structured_output: bool | None
    #: True if the gateway declares reasoning/thinking support.
    reasoning: bool | None
    #: Declared context-window size in tokens, if known.
    context_window: int | None
    #: Declared input cost per token in USD, if known.
    input_cost_per_token: float | None
    #: Declared output cost per token in USD, if known.
    output_cost_per_token: float | None
    #: Where this record came from: "litellm", "ollama", or None.
    source: str | None
    #: When metadata could not be used, this is True and `detail` explains why.
    unclassified: bool
    #: Human-readable explanation of what was tried for unclassified aliases.
    detail: str | None


@dataclass(frozen=True)
class EnrichmentResult:
    """The complete result of an enrichment run."""

    records: tuple[EnrichedAlias, ...]


def enrich_aliases(
    base_url: str,
    master_key_env: str,
    aliases: Iterable[str],
    *,
    source: str = "litellm",
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 10.0,
) -> EnrichmentResult:
    """Fetch capability metadata for `aliases` from the confirmed gateway.

    `master_key_env` names the environment variable holding the operator's
    confirmed master key. The key is read here and attached to every request;
    if the env is unset, every alias is marked unclassified rather than sending
    an empty credential.
    """
    alias_list = tuple(aliases)
    api_key = os.environ.get(master_key_env)

    async def _enrich() -> EnrichmentResult:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            if source == "ollama":
                records = await _enrich_ollama(client, base_url, api_key, alias_list)
            else:
                records = await _enrich_litellm(client, base_url, api_key, alias_list)
            return EnrichmentResult(records=records)

    return asyncio.run(_enrich())


async def _enrich_litellm(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str | None,
    aliases: tuple[str, ...],
) -> tuple[EnrichedAlias, ...]:
    base = base_url.rstrip("/")
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Start with the wildcard-expanded model list so we only enrich what the
    # gateway says it can serve.
    try:
        models_response = await client.get(
            f"{base}{_V1_MODELS_PATH}",
            headers=headers,
        )
        models_response.raise_for_status()
        body = models_response.json()
        advertised = {
            entry["id"]
            for entry in body.get("data", [])
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
    except Exception as exc:
        status = getattr(exc, "response", None) and getattr(exc.response, "status_code", None)
        status_text = f" ({status})" if status else ""
        return tuple(
            EnrichedAlias(
                alias=alias,
                tool_calling=None,
                structured_output=None,
                reasoning=None,
                context_window=None,
                input_cost_per_token=None,
                output_cost_per_token=None,
                source="litellm",
                unclassified=True,
                detail=f"could not fetch {_V1_MODELS_PATH}{status_text}: {type(exc).__name__}",
            )
            for alias in aliases
        )

    # Then pull /model/info and index it by model_name.
    try:
        info_response = await client.get(
            f"{base}{_MODEL_INFO_PATH}",
            headers=headers,
        )
        info_response.raise_for_status()
        info_body = info_response.json()
        info_data = info_body.get("data", []) if isinstance(info_body, dict) else []
        info_by_alias: dict[str, dict[str, Any]] = {}
        if isinstance(info_data, list):
            for entry in info_data:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("model_name")
                if not isinstance(name, str):
                    continue
                info_by_alias[name] = entry.get("model_info") or {}
    except Exception as exc:
        status = getattr(exc, "response", None) and getattr(exc.response, "status_code", None)
        status_text = f" ({status})" if status else ""
        return tuple(
            EnrichedAlias(
                alias=alias,
                tool_calling=None,
                structured_output=None,
                reasoning=None,
                context_window=None,
                input_cost_per_token=None,
                output_cost_per_token=None,
                source="litellm",
                unclassified=True,
                detail=f"could not fetch {_MODEL_INFO_PATH}{status_text}: {type(exc).__name__}",
            )
            for alias in aliases
        )

    records: list[EnrichedAlias] = []
    for alias in aliases:
        if alias not in advertised:
            records.append(
                EnrichedAlias(
                    alias=alias,
                    tool_calling=None,
                    structured_output=None,
                    reasoning=None,
                    context_window=None,
                    input_cost_per_token=None,
                    output_cost_per_token=None,
                    source="litellm",
                    unclassified=True,
                    detail=f"alias not advertised by {_V1_MODELS_PATH}",
                )
            )
            continue

        info = info_by_alias.get(alias, {})
        if not isinstance(info, dict):
            info = {}

        tool_calling = _bool(info.get("tool_calling")) or _bool(info.get("supports_function_calling"))
        output_modalities = info.get("output_modalities") or []
        structured_output = "text" in output_modalities if isinstance(output_modalities, list) else None
        reasoning = _bool(info.get("supports_reasoning")) or _bool(info.get("reasoning"))
        context_window = _int(info.get("context_window"))
        input_cost = _float(info.get("input_cost_per_token"))
        output_cost = _float(info.get("output_cost_per_token"))

        if info:
            records.append(
                EnrichedAlias(
                    alias=alias,
                    tool_calling=tool_calling if tool_calling is not None else False,
                    structured_output=structured_output if structured_output is not None else False,
                    reasoning=reasoning if reasoning is not None else False,
                    context_window=context_window,
                    input_cost_per_token=input_cost,
                    output_cost_per_token=output_cost,
                    source="litellm",
                    unclassified=False,
                    detail=None,
                )
            )
        else:
            records.append(
                EnrichedAlias(
                    alias=alias,
                    tool_calling=None,
                    structured_output=None,
                    reasoning=None,
                    context_window=None,
                    input_cost_per_token=None,
                    output_cost_per_token=None,
                    source="litellm",
                    unclassified=True,
                    detail=f"no {_MODEL_INFO_PATH} record for advertised alias",
                )
            )

    return tuple(records)


async def _enrich_ollama(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str | None,
    aliases: tuple[str, ...],
) -> tuple[EnrichedAlias, ...]:
    base = base_url.rstrip("/")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    records: list[EnrichedAlias] = []
    for alias in aliases:
        try:
            response = await client.post(
                f"{base}{_OLLAMA_SHOW_PATH}",
                headers=headers,
                json={"name": alias},
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            records.append(
                EnrichedAlias(
                    alias=alias,
                    tool_calling=None,
                    structured_output=None,
                    reasoning=None,
                    context_window=None,
                    input_cost_per_token=None,
                    output_cost_per_token=None,
                    source="ollama",
                    unclassified=True,
                    detail=f"{_OLLAMA_SHOW_PATH} failed for {alias}: {type(exc).__name__}",
                )
            )
            continue

        if not isinstance(body, dict):
            records.append(
                EnrichedAlias(
                    alias=alias,
                    tool_calling=None,
                    structured_output=None,
                    reasoning=None,
                    context_window=None,
                    input_cost_per_token=None,
                    output_cost_per_token=None,
                    source="ollama",
                    unclassified=True,
                    detail=f"{_OLLAMA_SHOW_PATH} returned non-object for {alias}",
                )
            )
            continue

        model_info = body.get("model_info") or {}
        capabilities = body.get("capabilities") or []
        if not isinstance(capabilities, list):
            capabilities = []
        capability_set = {str(c).lower() for c in capabilities}

        tool_calling = "tools" in capability_set
        structured_output = (
            "structured_outputs" in capability_set
            or _bool(model_info.get("supports_structured_output"))
            or False
        )
        reasoning = "thinking" in capability_set
        context_window = _int(model_info.get("context_length"))

        records.append(
            EnrichedAlias(
                alias=alias,
                tool_calling=tool_calling,
                structured_output=structured_output,
                reasoning=reasoning,
                context_window=context_window,
                input_cost_per_token=None,
                output_cost_per_token=None,
                source="ollama",
                unclassified=False,
                detail=None,
            )
        )

    return tuple(records)


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
