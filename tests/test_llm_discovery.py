"""US1: `ergane install --scan` discovers and classifies LLM endpoints.

Every test here routes through the injected transport seam; none opens a real
socket. The fake is reused from `conftest.py`, but the scanner's own transport
seam is the unit under test, not the LiteLLM admin client (which carries a
credential by design and is therefore the wrong boundary for FR-003).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import pytest

from factory.discovery.llm_scanner import (
    EndpointClassification,
    ScanResult,
    default_candidates,
    scan_endpoints,
)


@dataclass(frozen=True)
class RecordedProbe:
    """One unauthenticated request the scanner's seam actually made."""

    method: str
    url: str
    path: str
    headers: dict[str, str]


class FakeTransport(httpx.AsyncBaseTransport):
    """A stand-in HTTP transport that records requests and returns canned answers.

    This is the scanner's injected seam: the scanner builds an `httpx` client
    with this transport and no credentials, so no probe can carry an
    authorization header by construction, and no real socket is opened.
    """

    def __init__(
        self,
        *,
        models: dict[str, list[str]] | None = None,
        key_generate: dict[str, bool] | None = None,
        dead: set[str] | None = None,
    ) -> None:
        #: address -> aliases served by /v1/models
        self.models = models or {}
        #: address -> whether /key/generate answers
        self.key_generate = key_generate or {}
        #: addresses that are unreachable
        self.dead = dead or set()
        self.calls: list[RecordedProbe] = []

    def _answer(
        self, address: str, method: str, path: str
    ) -> httpx.Response:
        route = (method, path)
        if address in self.dead:
            raise httpx.ConnectError("connection refused", request=None)
        if route == ("GET", "/v1/models"):
            aliases = sorted(self.models.get(address, []))
            return httpx.Response(200, json={"data": [{"id": a} for a in aliases]})
        if route == ("POST", "/key/generate"):
            if self.key_generate.get(address, False):
                return httpx.Response(
                    200,
                    json={
                        "key": "sk-fake-key",
                        "key_alias": "probe",
                        "models": [],
                        "metadata": {},
                        "duration": "24h",
                        "max_budget": None,
                        "spend": 0.0,
                        "expires": None,
                    },
                )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        address = f"{parsed.scheme}://{parsed.netloc}"
        self.calls.append(
            RecordedProbe(
                method=request.method,
                url=str(request.url),
                path=parsed.path,
                headers=dict(request.headers),
            )
        )
        return self._answer(address, request.method, parsed.path)


@pytest.fixture
def transport_factory() -> Callable[..., FakeTransport]:
    def make(
        *,
        models: dict[str, list[str]] | None = None,
        key_generate: dict[str, bool] | None = None,
        dead: set[str] | None = None,
    ) -> FakeTransport:
        return FakeTransport(models=models, key_generate=key_generate, dead=dead)

    return make


# T001: an endpoint answering /v1/models reports address + aliases.
def test_scan_reports_address_and_aliases(
    transport_factory: Callable[..., FakeTransport],
) -> None:
    transport = transport_factory(
        models={"http://127.0.0.1:4000": ["claude-opus", "claude-sonnet"]}
    )
    results = scan_endpoints(
        addresses=["http://127.0.0.1:4000"],
        transport=transport,
    )

    assert len(results) == 1
    result = results[0]
    assert result.address == "http://127.0.0.1:4000"
    assert result.reachable is True
    assert set(result.aliases) == {"claude-opus", "claude-sonnet"}


# T002: dispatchable vs inference-only, naming the missing capability.
def test_scan_classifies_dispatchable_and_inference_only(
    transport_factory: Callable[..., FakeTransport],
) -> None:
    transport = transport_factory(
        models={
            "http://127.0.0.1:4000": ["claude-opus"],
            "http://127.0.0.1:11434": ["llama3"],
        },
        key_generate={"http://127.0.0.1:4000": True},
    )
    results = scan_endpoints(
        addresses=[
            "http://127.0.0.1:4000",
            "http://127.0.0.1:11434",
        ],
        transport=transport,
    )

    by_address = {r.address: r for r in results}
    assert by_address["http://127.0.0.1:4000"].classification == EndpointClassification.DISPATCHABLE
    assert by_address["http://127.0.0.1:11434"].classification == EndpointClassification.INFERENCE_ONLY
    assert "key-management" in by_address["http://127.0.0.1:11434"].detail.lower()


# T003: no probe request carries an authorization header.
def test_scan_sends_no_authorization_header(
    transport_factory: Callable[..., FakeTransport],
) -> None:
    transport = transport_factory(
        models={"http://127.0.0.1:4000": ["claude-opus"]},
        key_generate={"http://127.0.0.1:4000": True},
    )
    scan_endpoints(
        addresses=["http://127.0.0.1:4000"],
        transport=transport,
    )

    auth_headers = [
        call.headers.get("authorization", call.headers.get("Authorization"))
        for call in transport.calls
    ]
    assert all(h is None for h in auth_headers), auth_headers


# T004: loopback by default; non-loopback only when named.
def test_scan_defaults_to_loopback_only(transport_factory: Callable[..., FakeTransport]) -> None:
    transport = transport_factory(
        models={"http://127.0.0.1:4000": ["a"]},
        dead={"http://192.168.1.5:4000"},
    )
    results = scan_endpoints(transport=transport)
    scanned = {r.address for r in results}
    assert "http://127.0.0.1:4000" in scanned
    assert "http://192.168.1.5:4000" not in scanned


def test_scan_probes_non_loopback_when_named(
    transport_factory: Callable[..., FakeTransport],
) -> None:
    transport = transport_factory(
        models={"http://192.168.1.5:4000": ["a"]},
    )
    results = scan_endpoints(
        addresses=["http://192.168.1.5:4000"],
        transport=transport,
    )
    assert len(results) == 1
    assert results[0].address == "http://192.168.1.5:4000"
    assert results[0].reachable is True


# T005: a scan that finds nothing says so plainly and names what it looked for.
def test_scan_finding_nothing_reports_plainly(
    transport_factory: Callable[..., FakeTransport],
) -> None:
    transport = transport_factory(dead=set(default_candidates()))
    results = scan_endpoints(transport=transport)
    assert not any(r.reachable for r in results)


# T006: network reached only through injected seam; no real socket opened.
def test_scan_uses_injected_seam_and_no_real_socket(
    monkeypatch: pytest.MonkeyPatch,
    transport_factory: Callable[..., FakeTransport],
) -> None:
    transport = transport_factory(
        models={"http://127.0.0.1:4000": ["claude-opus"]},
    )

    # Any accidental construction of a client whose transport is not the
    # injected one would open a real socket. Monkeypatch AsyncClient so it
    # refuses any transport that is not our injected seam.
    injected = transport

    original_async_client_init = httpx.AsyncClient.__init__

    def strict_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("transport") is not injected:
            raise AssertionError("scanner opened a client without the injected seam")
        return original_async_client_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", strict_init)

    results = scan_endpoints(
        addresses=["http://127.0.0.1:4000"],
        transport=transport,
    )
    assert len(results) == 1
    assert results[0].reachable is True
    assert len(transport.calls) >= 1
