"""055-US3: the install interview offers the mode the scan found.

The walkthrough in `factory/cli/install.py` now runs an LLM scan before the
first question and uses its classification to choose the offered mode and the
default address. These tests drive the interview through the same scripted
prompter seam as 033's walkthrough tests; no real sockets are opened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import pytest

import factory.cli.init as init_module
import factory.cli.main as main_module
from factory.cli.errors import EXIT_USER
from factory.controlplane.config import DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT
from factory.discovery.llm_scanner import EndpointClassification, ScanResult

# The 033 walkthrough harness.
from tests.test_ergane_install_walkthrough import (  # noqa: F401
    GATEWAY_ANSWERS,
    Asked,
    Run,
    ScriptedPrompter,
    _answers,
    _blocks,
    _invoke,
    config_path,
    walkthrough,
)


# ---------------------------------------------------------------------------
# Fake transport seam for the scanner, independent of the LiteLLM admin seam.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedProbe:
    method: str
    url: str
    path: str
    headers: dict[str, str]


class FakeTransport(httpx.AsyncBaseTransport):
    """Canned scanner answers; records every request for FR-003 assertions."""

    def __init__(
        self,
        *,
        models: dict[str, list[str]] | None = None,
        key_generate: dict[str, bool] | None = None,
        dead: set[str] | None = None,
    ) -> None:
        self.models = models or {}
        self.key_generate = key_generate or {}
        self.dead = dead or set()
        self.calls: list[RecordedProbe] = []

    def _answer(self, address: str, method: str, path: str) -> httpx.Response:
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


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


def _run_with_scan_result(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    monkeypatch: pytest.MonkeyPatch,
    result: ScanResult,
    answers: list[str],
) -> tuple[Run, ScriptedPrompter]:
    """Run `ergane install` after injecting a scan that returns ``result``."""

    def _fake_scan(
        addresses: list[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 5.0,
    ) -> list[ScanResult]:
        # The scan result should be driven by what the operator names, if
        # anything. Keep the signature; ignore the transport.
        return [result]

    # Patch the scanner at the module where install.py imports it.
    from factory.cli import install as install_module

    monkeypatch.setattr(install_module, "_scan_endpoints", _fake_scan)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-not-a-real-key")
    return walkthrough(answers)


def _gateway_result(address: str = "http://127.0.0.1:4000") -> ScanResult:
    return ScanResult(
        address=address,
        reachable=True,
        aliases=("claude-opus",),
        classification=EndpointClassification.DISPATCHABLE,
        detail="LiteLLM gateway: /v1/models and /key/generate both answer",
    )


def _inference_result(address: str = "http://127.0.0.1:11434") -> ScanResult:
    return ScanResult(
        address=address,
        reachable=True,
        aliases=("llama3",),
        classification=EndpointClassification.INFERENCE_ONLY,
        detail=(
            "inference-only: /v1/models answers but the key-management API "
            "(/key/generate) does not"
        ),
    )


def _empty_scan_result() -> ScanResult:
    return ScanResult(
        address="http://127.0.0.1:4000",
        reachable=False,
        aliases=(),
        classification=None,
        detail="could not reach http://127.0.0.1:4000: ConnectError",
    )


# ---------------------------------------------------------------------------
# T024: a dispatchable scan result offers `gateway` with that address defaulted.
# ---------------------------------------------------------------------------


def test_dispatchable_scan_offers_gateway_with_address_defaulted(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1: the scan's dispatchable address becomes the gateway default."""
    address = "http://127.0.0.1:4000"
    answers = _answers()
    result, prompter = _run_with_scan_result(
        walkthrough, monkeypatch, _gateway_result(address), answers
    )

    mode_defaults = prompter.defaults_for("llm mode (gateway)")
    assert mode_defaults == ["gateway"], mode_defaults
    assert prompter.defaults_for("llm gateway base_url") == [address]

    assert config_path.is_file()
    config_text = config_path.read_text(encoding="utf-8")
    assert 'mode = "gateway"' in config_text


# ---------------------------------------------------------------------------
# T025: an inference-only result offers `direct`, names missing capability.
# ---------------------------------------------------------------------------


def test_inference_only_scan_offers_direct_and_names_missing_capability(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S2: only /v1/models means direct, and the reason names /key/generate."""
    address = "http://127.0.0.1:11434"
    # Accept the offered direct default and supply the API key env var; the rest
    # of the answers are the same gateway shape.
    answers = _answers(
        llm_mode="direct",
        llm_base_url=address,
        llm_master_key_env="ERGANE_DIRECT_LLM_KEY",
    )
    result, prompter = _run_with_scan_result(
        walkthrough, monkeypatch, _inference_result(address), answers
    )

    mode_defaults = prompter.defaults_for("llm mode (direct)")
    assert mode_defaults == ["direct"], mode_defaults
    assert prompter.defaults_for("llm direct base_url") == [address]

    # The reason `gateway` is unavailable must name the missing capability.
    # It is printed, not stored as a re-ask error, because it is advisory.
    output = result.stdout + result.stderr
    assert "`gateway` is unavailable" in output
    assert "key-management" in output.lower() or "/key/generate" in output

    assert config_path.is_file()
    config_text = config_path.read_text(encoding="utf-8")
    assert 'mode = "direct"' in config_text
    assert f'base_url = "{address}"' in config_text
    assert 'api_key_env = "ERGANE_DIRECT_LLM_KEY"' in config_text


# ---------------------------------------------------------------------------
# T026: choosing `direct` states the three surrendered properties before write.
# ---------------------------------------------------------------------------


def test_choosing_direct_states_surrendered_properties_before_write(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S3: the trade is disclosed before the config is written."""
    address = "http://127.0.0.1:11434"
    answers = _answers(
        llm_mode="direct",
        llm_base_url=address,
        llm_master_key_env="ERGANE_DIRECT_LLM_KEY",
    )
    result, prompter = _run_with_scan_result(
        walkthrough, monkeypatch, _inference_result(address), answers
    )

    # The surrendered text should appear in stdout (or stderr) before the
    # "wrote" line that marks the config write.
    output = result.stdout + result.stderr
    wrote_pos = output.find(f"wrote {config_path}")
    assert wrote_pos != -1
    text = DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT
    for phrase in (
        "credential is neither per-attempt nor expiring",
        "persona-to-model binding is advisory",
        "Spend attribution is unavailable",
    ):
        assert phrase in text
        pos = output.find(phrase)
        assert pos != -1, f"missing surrendered property: {phrase!r}"
        assert pos < wrote_pos, f"property {phrase!r} appeared after the write"


# ---------------------------------------------------------------------------
# T027: a scan finding nothing falls back to today's question, unchanged.
# ---------------------------------------------------------------------------


def test_empty_scan_falls_back_to_todays_question(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S4: discovery improves the question but is never required to answer it."""
    # Without a scan result, the interview must offer the same default it does
    # today and accept the operator's typed answers.
    answers = _answers()
    result, prompter = _run_with_scan_result(
        walkthrough, monkeypatch, _empty_scan_result(), answers
    )

    assert prompter.defaults_for("llm mode (gateway)") == ["gateway"]
    assert prompter.defaults_for("llm gateway base_url") == ["http://127.0.0.1:4000"]

    assert config_path.is_file()
    config_text = config_path.read_text(encoding="utf-8")
    assert 'mode = "gateway"' in config_text
    assert 'base_url = "http://127.0.0.1:1/v1"' in config_text


# ---------------------------------------------------------------------------
# T028: an operator-declared address overrides any scan result.
# ---------------------------------------------------------------------------


def test_operator_declared_address_overrides_scan_result(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S5: the operator wins over discovery."""
    scan_address = "http://127.0.0.1:11434"
    declared_address = "http://127.0.0.1:1/v1"
    answers = _answers(llm_base_url=declared_address)
    result, prompter = _run_with_scan_result(
        walkthrough, monkeypatch, _inference_result(scan_address), answers
    )

    # The scan offers direct and defaults the discovered address, but the
    # operator typed a different address and kept gateway mode.
    assert prompter.defaults_for("llm mode (direct)") == ["direct"]
    # Because the operator typed gateway mode, the follow-up question is the
    # gateway one; the default still carries the discovered address so the
    # operator can see what was found.
    assert prompter.defaults_for("llm gateway base_url") == [scan_address]

    assert config_path.is_file()
    config_text = config_path.read_text(encoding="utf-8")
    assert 'mode = "gateway"' in config_text
    assert f'base_url = "{declared_address}"' in config_text
    assert scan_address not in config_text
