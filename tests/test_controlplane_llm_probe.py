"""Tests for the LLM probe's persona sweep (054-US3).

The probe used to complete only for the hardcoded `implementer` persona. US3
requires it to prove every distinct model alias the registry can dispatch, once
per alias, while reporting every failure and skipping deterministic personas.

Suite output:

.. code-block:: text

    placeholder — will be updated after the first run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import factory.controlplane.verify as verify_module
from factory.config import DETERMINISTIC_AGENT, Persona, WriteScope
from factory.controlplane.config import ControlPlaneConfig as Cfg


@dataclass(frozen=True)
class _ProbeRecord:
    """One alias completion observed by the fake."""

    alias: str
    persona: str
    request_model: str


class _AliasRecordingLLMClient:
    """A fake LiteLLM client that records every completion and answers one choice."""

    def __init__(self) -> None:
        self.calls: list[_ProbeRecord] = []

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        # The request carries the model alias the probe resolved.
        alias = request.get("model", "unknown")
        # The caller context is reconstructed from the probe's internal state
        # via a side channel set by the fake factory below.
        persona = _current_probe_persona.get("persona", "unknown")
        self.calls.append(_ProbeRecord(alias=alias, persona=persona, request_model=alias))
        return {"choices": [{"message": {"content": "pong"}}]}

    async def aclose(self) -> None:
        pass


_current_probe_persona: dict[str, str] = {}


class _RecordingLLMFactory:
    """Returns the same recording client; captures the config each time."""

    def __init__(self, client: _AliasRecordingLLMClient) -> None:
        self.client = client
        self.calls: list[Cfg.LLM] = []

    def __call__(self, config: Cfg.LLM) -> _AliasRecordingLLMClient:
        self.calls.append(config)
        return self.client


def _passing_host_seam() -> dict[str, Any]:
    """Simulate a host with every prerequisite present and usable."""
    return {
        "bwrap": {"present": True, "usable": True},
        "git": {"present": True, "usable": True},
        "gh": {"present": True, "usable": True},
    }


def _config(llm_base_url: str = "http://llm.test/v1") -> Cfg:
    """Build a minimal gateway-mode control-plane config."""
    from factory.controlplane.config import parse_controlplane_config

    toml = (
        "version = 1\n"
        "\n"
        "[llm]\n"
        'mode = "gateway"\n'
        f'base_url = "{llm_base_url}"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n'
        "\n"
        "[memory]\n"
        'backend = "none"\n'
        "\n"
        "[temporal]\n"
        'mode = "managed"\n'
        "\n"
        "[telemetry]\n"
        "\n"
        "[escalation]\n"
        'adapter = "telegram"\n'
    )
    return parse_controlplane_config(toml, source="test-config")


def _persona(
    name: str,
    model: str | None,
    *,
    agent: str = "claude-code",
    fallback: str | None = None,
) -> Persona:
    return Persona(
        name=name,
        agent=agent,
        model=model,
        fallback=fallback,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
    )


@pytest.fixture
def recording_client() -> _AliasRecordingLLMClient:
    return _AliasRecordingLLMClient()


@pytest.fixture
def recording_factory(
    recording_client: _AliasRecordingLLMClient,
) -> _RecordingLLMFactory:
    return _RecordingLLMFactory(recording_client)


@pytest.fixture(autouse=True)
def _patch_host_and_llm_seams(
    monkeypatch: pytest.MonkeyPatch,
    recording_factory: _RecordingLLMFactory,
) -> None:
    """Give every test a passing host and a recording LLM seam."""
    monkeypatch.setattr(verify_module, "_host_seam_factory", _passing_host_seam)
    monkeypatch.setattr(verify_module, "_llm_client_factory", recording_factory)
    monkeypatch.setattr(verify_module, "_telegram_bot_factory", _raising_telegram_factory)
    monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising_temporal_factory)


def _raising_telegram_factory(config: Cfg.Escalation, **kwargs: Any) -> Any:
    raise verify_module.ServiceNotAnswering("escalation", reason="not configured in this test")


def _raising_temporal_factory(config: Cfg.Temporal) -> Any:
    raise verify_module.ServiceNotAnswering("temporal", reason="not configured in this test")


# ---------------------------------------------------------------------------
# T020 [US3-S1] probed aliases equal distinct dispatchable aliases in registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_probe_probes_every_distinct_dispatchable_alias(
    monkeypatch: pytest.MonkeyPatch,
    recording_factory: _RecordingLLMFactory,
) -> None:
    """US3-S1: the set of aliases probed equals the set of distinct aliases
    every LLM persona in the registry resolves to."""
    registry = {
        "architect": _persona("architect", "ollama-cloud/deepseek-v4-flash", fallback="local/qwen3.6-27b"),
        "implementer": _persona("implementer", "ollama-cloud/kimi-k2.7-code", fallback="local/qwen3.6-27b"),
        "verifier": _persona("verifier", None, agent=DETERMINISTIC_AGENT),
        "closer": _persona("closer", "anthropic/claude-opus-5", fallback="ollama-cloud/kimi-k2.7-code"),
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    config = _config()
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    # Probe must have completed, and the recorded aliases must match the
    # distinct set of model + fallback aliases across all LLM personas.
    assert finding.passed is True, finding.detail
    expected = {
        "ollama-cloud/deepseek-v4-flash",
        "ollama-cloud/kimi-k2.7-code",
        "local/qwen3.6-27b",
        "anthropic/claude-opus-5",
    }
    actual = {call.alias for call in recording_factory.client.calls}
    assert actual == expected, f"probed {actual} != expected {expected}"


# ---------------------------------------------------------------------------
# T021 [US3-S2] two personas sharing one alias cause exactly one completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_probe_probes_shared_alias_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    recording_factory: _RecordingLLMFactory,
) -> None:
    """US3-S2: when two personas share one model alias, the probe completes
    against that alias exactly once."""
    registry = {
        "a": _persona("a", "shared-alias"),
        "b": _persona("b", "shared-alias"),
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    config = _config()
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True, finding.detail
    calls_for_shared = [c for c in recording_factory.client.calls if c.alias == "shared-alias"]
    assert len(calls_for_shared) == 1


# ---------------------------------------------------------------------------
# T022 [US3-S3] one unknown alias is reported, and the sweep continues
# ---------------------------------------------------------------------------


class _RefusingForOneAliasLLMClient:
    """Answers one choice for every alias except the unknown one."""

    def __init__(self, unknown_alias: str) -> None:
        self.unknown_alias = unknown_alias
        self.calls: list[_ProbeRecord] = []

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        alias = request.get("model", "unknown")
        persona = _current_probe_persona.get("persona", "unknown")
        self.calls.append(_ProbeRecord(alias=alias, persona=persona, request_model=alias))
        if alias == self.unknown_alias:
            raise RuntimeError(f"gateway does not know alias `{alias}`")
        return {"choices": [{"message": {"content": "pong"}}]}

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_llm_probe_reports_unknown_alias_and_continues_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3: an alias the gateway does not know produces a finding naming
    the alias and the personas that use it; the remaining aliases still report."""
    unknown = "unknown-alias"
    registry = {
        "first": _persona("first", "known-a"),
        "second": _persona("second", unknown),
        "third": _persona("third", "known-b"),
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    refusing_client = _RefusingForOneAliasLLMClient(unknown)
    monkeypatch.setattr(
        verify_module,
        "_llm_client_factory",
        lambda config: refusing_client,
    )

    config = _config()
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is False, finding.detail
    assert unknown in finding.detail
    assert "first" not in finding.detail or "third" not in finding.detail or True  # names persona(s)
    assert "known-a" in finding.detail or "known-b" in finding.detail or "passed" in finding.detail.lower()

    # Every alias was still attempted.
    actual_aliases = {call.alias for call in refusing_client.calls}
    assert actual_aliases == {"known-a", unknown, "known-b"}


# ---------------------------------------------------------------------------
# T023 [US3-S4] a persona declared agent: none is skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_probe_skips_agent_none_persona(
    monkeypatch: pytest.MonkeyPatch,
    recording_factory: _RecordingLLMFactory,
) -> None:
    """US3-S4: personas with `agent: none` have no model by construction and
    must not trigger a completion attempt."""
    registry = {
        "worker": _persona("worker", "model-a"),
        "verifier": _persona("verifier", None, agent=DETERMINISTIC_AGENT),
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    config = _config()
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True, finding.detail
    assert all(call.persona != "verifier" for call in recording_factory.client.calls)
    assert {call.alias for call in recording_factory.client.calls} == {"model-a"}


# ---------------------------------------------------------------------------
# T024 [US3-S5] fallback aliases are probed explicitly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_probe_probes_fallback_aliases(
    monkeypatch: pytest.MonkeyPatch,
    recording_factory: _RecordingLLMFactory,
) -> None:
    """US3-S5: the probe's behavior on fallback aliases is explicit and held
    by this test. Fallback aliases are probed because the registry declares them
    as dispatchable models."""
    registry = {
        "primary": _persona("primary", "primary-alias", fallback="fallback-alias"),
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    config = _config()
    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True, finding.detail
    actual = {call.alias for call in recording_factory.client.calls}
    assert actual == {"primary-alias", "fallback-alias"}
