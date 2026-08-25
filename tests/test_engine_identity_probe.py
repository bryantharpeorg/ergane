"""105-US3: the `install --verify` engine-identity probe (T022, T023)."""

from __future__ import annotations

import asyncio

import pytest

import factory.controlplane.verify as verify_module
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.mergequeue.models import Finding
from factory.supervision.engine_identity import (
    EngineIdentity,
    identity_path,
    image_reference,
    write_identity,
)


def _full_config() -> Cfg:
    return Cfg(
        version=1,
        llm=Cfg.LLM(
            mode="gateway",
            gateway=Cfg.LLMGateway(
                base_url="http://llm.test/v1",
                master_key_env="ERGANE_LLM_MASTER_KEY",
            ),
        ),
        memory=Cfg.Memory(backend="hindsight", url="http://memory.test"),
        temporal=Cfg.Temporal(
            mode="external", address="temporal.test:7233", namespace="ergane"
        ),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="none"),
    )


@pytest.fixture
def isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return state


def test_engine_probe_mismatch_fails_with_sentence(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T022 / US3-S2 / FR-014: mismatched identity file yields a failing Finding."""
    from factory.supervision import engine_identity as identity_module

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    identity = EngineIdentity(
        version="0.3.0",
        started_at="2026-08-25T12:00:00+00:00",
        image_reference=image_reference("0.3.0"),
        image_digest=None,
    )
    write_identity(isolated_state_home, identity)

    probe = verify_module.EngineIdentityProbe()
    snapshot = asyncio.run(probe.gather(_full_config()))
    finding = probe.evaluate(snapshot)

    assert finding.check == "engine"
    assert finding.passed is False
    assert "engine is running ergane 0.3.0" in finding.detail
    assert "this CLI is 0.4.0" in finding.detail
    assert "ergane engine upgrade" in finding.detail
    assert str(identity_path(isolated_state_home)) in finding.detail


@pytest.mark.asyncio
async def test_engine_probe_match_passes(
    isolated_state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T022 / US3-S2: a matching identity file yields a green Finding."""
    from factory.supervision import engine_identity as identity_module

    # The package version in this test environment is "0.3.0".
    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.3.0")

    identity = EngineIdentity(
        version="0.3.0",
        started_at="2026-08-25T12:00:00+00:00",
        image_reference=image_reference("0.3.0"),
        image_digest=None,
    )
    write_identity(isolated_state_home, identity)

    probe = verify_module.EngineIdentityProbe()
    snapshot = await probe.gather(_full_config())
    finding = probe.evaluate(snapshot)

    assert finding.check == "engine"
    assert finding.passed is True
    assert "matches" in finding.detail


@pytest.mark.asyncio
async def test_engine_probe_absent_is_green(
    isolated_state_home: Path,
) -> None:
    """T023 / US3-S3 / FR-014: no identity file anywhere is a green pass."""
    probe = verify_module.EngineIdentityProbe()
    snapshot = await probe.gather(_full_config())
    finding = probe.evaluate(snapshot)

    assert finding.check == "engine"
    assert finding.passed is True
    assert "no engine identity record" in finding.detail
    assert "activates only on evidence" in finding.detail
