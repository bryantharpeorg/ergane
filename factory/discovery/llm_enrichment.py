"""Post-confirmation per-alias capability enrichment (US1).

Enrichment runs after the operator has confirmed the gateway address and named
its master-key env.  It is therefore authenticated, unlike the unauthenticated
discovery scan in `llm_scanner.py`.  Every network touch goes through an injected
`httpx.AsyncBaseTransport` seam so tests can simulate endpoints without opening
real sockets (FR-001).

Three sources feed one shared record type:

- LiteLLM-shaped gateway: `/model/info` is preferred, `/v1/models` is the
  wildcard-expanded model list fallback.
- Ollama-shaped gateway: `/api/show` per model.
- Missing or unusable metadata: every alias comes back unclassified with a
  detail naming what was tried (FR-002).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

import httpx


#: LiteLLM metadata endpoint and the wildcard-expanded models list.
_MODEL_INFO_PATH = "/model/info"
_MODELS_PATH = "/v1/models"

#: Ollama capability endpoint.
_OLLAMA_SHOW_PATH = "/api/show"


@dataclass(frozen=True)
class EnrichmentRecord:
    """One alias's capabilities as declared by the gateway, or an honest unclassified."""

    alias: str
    tool_calling: bool = False
    structured_output: bool = False
    reasoning: bool = False
    context_window: int | None = None
    input_cost_per_token: float | None = None
    output_cost_per_token: float | None = None
    unclassified: bool = False
    detail: str = ""


def enrich_aliases(
    base_url: str,
    aliases: Iterable[str],
    *,
    master_key_env: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 10.0,
) -> tuple[EnrichmentRecord, ...]:
    """Fetch per-alias capability metadata from a confirmed gateway.

    `master_key_env` is the environment variable name the operator confirmed for
    the gateway's master key.  If it is not set, the returned records are all
    unclassified with a detail naming the missing env.  No credential is sent
    unless `master_key_env` is provided and the named variable is present.

    LiteLLM-shaped gateways are probed at `/model/info` and `/v1/models`.
    Ollama-shaped gateways are probed at `/api/show`.  Aliases without usable
    metadata are returned as unclassified; enrichment never aborts by exception.
    """
    alias_tuple = tuple(aliases)

    api_key: str | None = None
    if master_key_env is not None:
        api_key = os.environ.get(master_key_env)

    if not api_key:
        return tuple(
            EnrichmentRecord(
                alias=alias,
                unclassified=True,
                detail=(
                    f"{master_key_env} is not set; no credential to reach "
                    f"gateway metadata at {base_url}"
                    if master_key_env
                    else "no master-key env named before confirmation"
                ),
            )
            for alias in alias_tuple
        )

    headers = {"Authorization": f"Bearer {api_key}"}

    async def _enrich() -> tuple[EnrichmentRecord, ...]:
        async with httpx.AsyncClient(
            transport=transport, timeout=timeout, headers=headers
        ) as client:
            # Prefer a LiteLLM-shaped gateway first; if /model/info is absent,
            # try Ollama-shaped next.
            litellm_info = await _fetch_litellm_model_info(client, base_url)
            litellm_aliases = await _fetch_litellm_models(client, base_url)

            if litellm_info is not None or litellm_aliases is not None:
                return _records_from_litellm(alias_tuple, base_url, litellm_info, litellm_aliases)

            ollama_info = await _fetch_ollama_models(client, base_url, alias_tuple)
            if ollama_info is not None:
                return _records_from_ollama(alias_tuple, base_url, ollama_info)

            # Neither shape answered recognisably: every alias unclassified.
            return tuple(
                EnrichmentRecord(
                    alias=alias,
                    unclassified=True,
                    detail=(
                        f"no usable metadata endpoint at {base_url}: "
                        f"tried {_MODEL_INFO_PATH} and {_OLLAMA_SHOW_PATH}"
                    ),
                )
                for alias in alias_tuple
            )

    try:
        return asyncio.run(_enrich())
    except Exception as exc:
        # Enrichment failure must never abort install by exception (FR-002).
        return tuple(
            EnrichmentRecord(
                alias=alias,
                unclassified=True,
                detail=f"enrichment failed for {base_url}: {type(exc).__name__}: {exc}",
            )
            for alias in alias_tuple
        )


async def _fetch_litellm_model_info(
    client: httpx.AsyncClient, base_url: str
) -> dict[str, Any] | None:
    """Return LiteLLM /model/info payload, or None if the endpoint is absent/garbage."""
    try:
        response = await client.get(f"{base_url.rstrip('/')}{_MODEL_INFO_PATH}")
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    # Some LiteLLM proxies return a flat mapping keyed by alias, others nest under
    # `model_info` for each entry.  We return the body as-is and let the record
    # builder look up the alias and then unwrap the inner `model_info`.
    return body


async def _fetch_litellm_models(
    client: httpx.AsyncClient, base_url: str
) -> dict[str, dict[str, Any]] | None:
    """Return LiteLLM /v1/models payload keyed by alias, or None."""
    try:
        response = await client.get(f"{base_url.rstrip('/')}{_MODELS_PATH}")
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, list):
        return None
    result: dict[str, dict[str, Any]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        alias = entry.get("id")
        if not isinstance(alias, str) or not alias:
            continue
        result[alias] = entry
    return result if result else None


async def _fetch_ollama_models(
    client: httpx.AsyncClient, base_url: str, aliases: tuple[str, ...]
) -> dict[str, dict[str, Any]] | None:
    """Return Ollama /api/show payload keyed by alias, or None if the shape is wrong."""
    result: dict[str, dict[str, Any]] = {}
    any_success = False
    for alias in aliases:
        try:
            response = await client.post(
                f"{base_url.rstrip('/')}{_OLLAMA_SHOW_PATH}",
                json={"name": alias},
            )
        except httpx.HTTPError:
            continue
        if response.status_code != 200:
            continue
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(body, dict):
            continue
        any_success = True
        result[alias] = body
    return result if any_success else None


def _records_from_litellm(
    aliases: tuple[str, ...],
    base_url: str,
    model_info: dict[str, Any] | None,
    models: dict[str, dict[str, Any]] | None,
) -> tuple[EnrichmentRecord, ...]:
    """Build records from LiteLLM /model/info (preferred) or /v1/models."""
    records: list[EnrichmentRecord] = []
    for alias in aliases:
        info: dict[str, Any] | None = None
        source_detail = ""
        if isinstance(model_info, dict):
            info = model_info.get(alias)
            if info is not None:
                source_detail = f"from {_MODEL_INFO_PATH}"
        if info is None and isinstance(models, dict):
            info = models.get(alias)
            if info is not None:
                source_detail = f"from {_MODELS_PATH}"

        if info is None:
            records.append(
                EnrichmentRecord(
                    alias=alias,
                    unclassified=True,
                    detail=f"no metadata found for `{alias}` at {base_url}",
                )
            )
            continue

        inner = info.get("model_info") if isinstance(info, dict) else None
        if not isinstance(inner, dict):
            inner = info

        tool_calling = bool(inner.get("supports_function_calling"))
        structured_output = bool(inner.get("supports_response_schema"))
        reasoning = bool(inner.get("supports_reasoning"))
        context_window = _coerce_positive_int(inner.get("max_tokens"))
        if context_window is None:
            context_window = _coerce_positive_int(inner.get("max_input_tokens"))

        input_cost = _coerce_float(inner.get("input_cost_per_token"))
        output_cost = _coerce_float(inner.get("output_cost_per_token"))

        records.append(
            EnrichmentRecord(
                alias=alias,
                tool_calling=tool_calling,
                structured_output=structured_output,
                reasoning=reasoning,
                context_window=context_window,
                input_cost_per_token=input_cost,
                output_cost_per_token=output_cost,
                detail=f"LiteLLM metadata {source_detail} for `{alias}`" if source_detail else f"LiteLLM metadata for `{alias}`",
            )
        )
    return tuple(records)


def _records_from_ollama(
    aliases: tuple[str, ...],
    base_url: str,
    ollama_info: dict[str, dict[str, Any]],
) -> tuple[EnrichmentRecord, ...]:
    """Build records from Ollama /api/show responses."""
    records: list[EnrichmentRecord] = []
    for alias in aliases:
        info = ollama_info.get(alias)
        if info is None:
            records.append(
                EnrichmentRecord(
                    alias=alias,
                    unclassified=True,
                    detail=f"no /api/show response for `{alias}` at {base_url}",
                )
            )
            continue

        capabilities = info.get("capabilities") if isinstance(info, dict) else None
        details = info.get("details") if isinstance(info, dict) else None
        if not isinstance(capabilities, dict):
            capabilities = {}
        if not isinstance(details, dict):
            details = {}

        tool_calling = bool(capabilities.get("tools"))
        structured_output = bool(capabilities.get("structured_output"))
        reasoning = bool(capabilities.get("reasoning"))
        context_window = _coerce_positive_int(details.get("context_length"))

        records.append(
            EnrichmentRecord(
                alias=alias,
                tool_calling=tool_calling,
                structured_output=structured_output,
                reasoning=reasoning,
                context_window=context_window,
                detail=f"Ollama /api/show metadata for `{alias}`",
            )
        )
    return tuple(records)


def _coerce_positive_int(value: Any) -> int | None:
    """Keep a positive integer, ignore bools and non-numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _coerce_float(value: Any) -> float | None:
    """Keep a finite number, ignore strings masquerading as numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
