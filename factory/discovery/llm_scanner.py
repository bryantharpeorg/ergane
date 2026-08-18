"""Unauthenticated LLM endpoint discovery for `ergane install --scan` (US1).

Every network touch goes through an injected `httpx.AsyncBaseTransport` seam so
that tests can simulate endpoints without opening real sockets (FR-005). The
scan is deliberately unauthenticated: it probes addresses the operator has not
confirmed yet, and presenting any credential to whatever answers a local port
would hand that credential away (FR-003).
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass
from typing import Any, Iterable

import httpx


class EndpointClassification(enum.Enum):
    """What an endpoint can do for Ergane."""

    DISPATCHABLE = "dispatchable"
    INFERENCE_ONLY = "inference-only"


@dataclass(frozen=True)
class ScanResult:
    """What the scan learned about one candidate address."""

    address: str
    reachable: bool
    aliases: tuple[str, ...]
    classification: EndpointClassification | None
    detail: str


#: LiteLLM proxy's default port and the standard Ollama API port, on loopback
#: only. Anything outside loopback must be named by the operator (FR-004).
_DEFAULT_LOOPBACK_CANDIDATES = (
    "http://127.0.0.1:4000",
    "http://127.0.0.1:11434",
)

#: Shape expected from a LiteLLM-shaped `/v1/models` response.
_MODELS_PATH = "/v1/models"
_KEY_GENERATE_PATH = "/key/generate"


def default_candidates() -> tuple[str, ...]:
    """The addresses the scan probes when the operator names none."""
    return _DEFAULT_LOOPBACK_CANDIDATES


def _is_loopback(address: str) -> bool:
    """Whether `address` names a loopback host by literal IP."""
    from urllib.parse import urlparse

    netloc = urlparse(address).netloc
    host = netloc.rsplit(":", 1)[0] if ":" in netloc else netloc
    return host in ("127.0.0.1", "::1", "localhost")


def scan_endpoints(
    addresses: Iterable[str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 5.0,
) -> list[ScanResult]:
    """Probe candidate LLM endpoints and classify each one.

    If `addresses` is omitted, the scan probes the default loopback candidates.
    If a non-loopback address is supplied, it is probed as-is; loopback-only is
    the default, not a hard whitelist. The scan is unauthenticated: no API key
    is attached to any probe request.
    """
    candidates = list(addresses) if addresses is not None else list(default_candidates())

    async def _probe() -> list[ScanResult]:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            results: list[ScanResult] = []
            for address in candidates:
                result = await _probe_one(client, address)
                results.append(result)
            return results

    return asyncio.run(_probe())


async def _probe_one(client: httpx.AsyncClient, address: str) -> ScanResult:
    """Probe one address unauthenticated and classify it."""
    base = address.rstrip("/")
    aliases: list[str] = []

    try:
        models_response = await client.get(f"{base}{_MODELS_PATH}")
    except httpx.HTTPError as exc:
        return ScanResult(
            address=address,
            reachable=False,
            aliases=(),
            classification=None,
            detail=f"could not reach {address}: {type(exc).__name__}",
        )

    if models_response.status_code == 200:
        try:
            body = models_response.json()
            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, list):
                aliases = sorted(
                    entry["id"]
                    for entry in data
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str)
                )
        except ValueError:
            aliases = []
    else:
        return ScanResult(
            address=address,
            reachable=False,
            aliases=(),
            classification=None,
            detail=f"{_MODELS_PATH} answered {models_response.status_code}",
        )

    # A second, still-unauthenticated probe decides dispatchability.
    has_key_management = False
    try:
        key_response = await client.post(f"{base}{_KEY_GENERATE_PATH}")
        has_key_management = key_response.status_code == 200
    except httpx.HTTPError:
        has_key_management = False

    if has_key_management:
        classification = EndpointClassification.DISPATCHABLE
        detail = "LiteLLM gateway: /v1/models and /key/generate both answer"
    else:
        classification = EndpointClassification.INFERENCE_ONLY
        detail = (
            "inference-only: /v1/models answers but the key-management API "
            "(/key/generate) does not"
        )

    return ScanResult(
        address=address,
        reachable=True,
        aliases=tuple(aliases),
        classification=classification,
        detail=detail,
    )


def render_scan_results(results: list[ScanResult]) -> str:
    """Render scan results as a plain-text table for the CLI."""
    if not results:
        return "No LLM endpoints were probed."

    lines: list[str] = []
    lines.append(f"Probed {len(results)} candidate(s):")
    for result in results:
        status = "reachable" if result.reachable else "unreachable"
        aliases = ", ".join(result.aliases) if result.aliases else "none"
        cls = result.classification.value if result.classification else "unknown"
        lines.append(f"  {result.address} — {status}, {cls}")
        lines.append(f"    aliases: {aliases}")
        lines.append(f"    detail: {result.detail}")

    if not any(r.reachable for r in results):
        lines.append("")
        lines.append(
            "The scan found no reachable LLM endpoint. "
            "It looked for /v1/models and /key/generate on the loopback candidates."
        )

    return "\n".join(lines)
