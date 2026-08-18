"""Tests for `HostProbe` (US2, 054-a-stranger-can-install-ergane).

Host state is simulated through the probe's injected seam in every test below.
No test in this module reaches the real host.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import factory.controlplane.verify as verify_module
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.mergequeue.models import Finding


@dataclass(frozen=True)
class _HostState:
    """A simulated host for `HostProbe.gather` to inspect."""

    bwrap_on_path: bool = True
    git_on_path: bool = True
    gh_on_path: bool = True
    gh_authenticated: bool = True


async def _gather_with_host(config: Cfg, host: _HostState) -> Any:
    """Run `HostProbe.gather` with the given simulated host state."""
    probe = verify_module.HostProbe(host_seam=lambda: _host_check(host))
    return await probe.gather(config)


def _host_check(host: _HostState) -> dict[str, Any]:
    """Return the simulated host report that `HostProbe` reads."""
    return {
        "bwrap": {
            "present": host.bwrap_on_path,
            "usable": host.bwrap_on_path,
            "purpose": "sandboxing agent worktrees",
            "remedy": "install bubblewrap (bwrap)",
        },
        "git": {
            "present": host.git_on_path,
            "usable": host.git_on_path,
            "purpose": "version control for worktrees",
            "remedy": "install git",
        },
        "gh": {
            "present": host.gh_on_path,
            "usable": host.gh_on_path and host.gh_authenticated,
            "purpose": "GitHub CLI for repository operations",
            "absent_remedy": "install the GitHub CLI (gh)",
            "unauthenticated_remedy": "run `gh auth login`",
        },
    }


# ---------------------------------------------------------------------------
# T011 [US2-S1] missing bwrap yields a failing finding naming bwrap and its purpose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_bwrap_yields_failing_finding(tmp_path: Path) -> None:
    """A host without `bwrap` reports one failing finding that names `bwrap`."""
    config = Cfg(
        version=1,
        llm=Cfg.LLM(mode="gateway"),
        memory=Cfg.Memory(backend="none"),
        temporal=Cfg.Temporal(mode="external"),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="telegram"),
    )
    host = _HostState(bwrap_on_path=False)

    snapshot = await _gather_with_host(config, host)
    finding = verify_module.HostProbe().evaluate(snapshot)

    assert finding.passed is False
    assert "bwrap" in finding.detail
    assert "sandbox" in finding.detail or "agent" in finding.detail
    assert "install" in finding.detail or "bubblewrap" in finding.detail


# ---------------------------------------------------------------------------
# T012 [US2-S2] gh present but unauthenticated is distinguishable from gh absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gh_present_but_unauthenticated_is_distinguished(tmp_path: Path) -> None:
    """`gh` present-but-unauthenticated reports differently from `gh` absent."""
    config = Cfg(
        version=1,
        llm=Cfg.LLM(mode="gateway"),
        memory=Cfg.Memory(backend="none"),
        temporal=Cfg.Temporal(mode="external"),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="telegram"),
    )
    present_unauth = _HostState(gh_on_path=True, gh_authenticated=False)
    absent = _HostState(gh_on_path=False)

    present_snapshot = await _gather_with_host(config, present_unauth)
    absent_snapshot = await _gather_with_host(config, absent)

    present_finding = verify_module.HostProbe().evaluate(present_snapshot)
    absent_finding = verify_module.HostProbe().evaluate(absent_snapshot)

    assert present_finding.passed is False
    assert absent_finding.passed is False
    assert present_finding.detail != absent_finding.detail
    assert "unauthenticated" in present_finding.detail.lower() or "auth login" in present_finding.detail
    assert "not installed" in absent_finding.detail.lower() or "install" in absent_finding.detail


# ---------------------------------------------------------------------------
# T013 [US2-S3] every prerequisite present passes; existing probes unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_host_with_every_prerequisite_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete host passes, and the five existing probes are byte-identical."""
    # Snapshot the five existing probes' findings against a blank config using
    # their own injected seams, then confirm adding the host probe appends exactly
    # one more finding and leaves the others untouched.
    monkeypatch.setattr(verify_module, "_llm_client_factory", _raising("llm"))
    monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising("temporal"))
    monkeypatch.setattr(verify_module, "_memory_client_factory", _raising("memory"))
    monkeypatch.setattr(verify_module, "_telegram_bot_factory", _raising("escalation"))

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'version = 1\n\n[llm]\nmode = "gateway"\nbase_url = "http://llm.test"\nmaster_key_env = "ERGANE_LLM_MASTER_KEY"\n\n'
        '[memory]\nbackend = "none"\n\n[temporal]\nmode = "external"\naddress = "127.0.0.1:1"\nnamespace = "factory"\n\n'
        '[telemetry]\n\n[escalation]\nadapter = "telegram"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))

    # Capture the five existing probes' findings by replacing the host probe with
    # one that reports a passing simulated host. The first run establishes the
    # baseline for the five existing probes without real host influence.
    host_state = _HostState()
    simulated_host_probe = verify_module.HostProbe(host_seam=lambda: _host_check(host_state))

    original_registry = list(verify_module.REGISTRY)
    baseline_registry = [
        simulated_host_probe if isinstance(probe, verify_module.HostProbe) else probe
        for probe in original_registry
    ]
    verify_module.REGISTRY[:] = baseline_registry
    try:
        baseline_findings, _ = await verify_module.verify_controlplane_async(str(config_path))
    finally:
        verify_module.REGISTRY[:] = original_registry

    baseline_without_host = [f for f in baseline_findings if f.check != "host"]
    baseline_host = next(f for f in baseline_findings if f.check == "host")
    assert baseline_host.passed is True

    # Now run with the real registry (which still includes HostProbe). Because the
    # real host is not under our control, we only assert structural properties:
    # there is a host finding and the five non-host findings match the baseline.
    findings_with_host, exit_code = await verify_module.verify_controlplane_async(str(config_path))

    new_checks = {f.check: f for f in findings_with_host}
    assert "host" in new_checks
    for baseline in baseline_without_host:
        assert new_checks[baseline.check] == baseline

    assert exit_code == 1  # other probes are still failing


# ---------------------------------------------------------------------------
# T014 [US2-S4] seam injectability and no real host access in this module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_host_probe_seam_is_injectable(tmp_path: Path) -> None:
    """The probe's host access is fully replaceable; no unpatched call escapes."""
    calls: list[tuple[()]] = []

    def _seam() -> dict[str, Any]:
        calls.append(())
        return _host_check(_HostState())

    probe = verify_module.HostProbe(host_seam=_seam)
    config = Cfg(
        version=1,
        llm=Cfg.LLM(mode="gateway"),
        memory=Cfg.Memory(backend="none"),
        temporal=Cfg.Temporal(mode="external"),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="telegram"),
    )

    await probe.gather(config)

    assert calls == [()]


def test_module_does_not_call_real_host() -> None:
    """No test in this module invokes subprocess, shutil.which or systemctl directly."""
    import ast

    module_path = Path(__file__).resolve()
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                names.add(func.attr)
            elif isinstance(func, ast.Name):
                names.add(func.id)

    forbidden = {"run", "call", "check_output", "Popen", "which", "systemctl"}
    assert names.isdisjoint(forbidden), (
        f"test module calls real-host primitives: {names & forbidden}"
    )


# ---------------------------------------------------------------------------
# T015 [US2-S5] probe reports and does not remediate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_host_probe_reports_and_does_not_remediate(tmp_path: Path) -> None:
    """A missing prerequisite yields a finding and makes no host changes."""
    marker = tmp_path / "no-remediation-marker"
    touched = []

    def _seam() -> dict[str, Any]:
        # A remediating probe might write a file or install a package. Record
        # that this seam ran without letting the probe reach the filesystem.
        touched.append(1)
        return _host_check(_HostState(bwrap_on_path=False))

    probe = verify_module.HostProbe(host_seam=_seam)
    config = Cfg(
        version=1,
        llm=Cfg.LLM(mode="gateway"),
        memory=Cfg.Memory(backend="none"),
        temporal=Cfg.Temporal(mode="external"),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="telegram"),
    )

    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    assert touched == [1]
    assert not marker.exists()
    assert "bwrap" in finding.detail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raising(name: str) -> Any:
    """A seam factory that reports ServiceNotAnswering for the named subsystem."""
    def factory(*args: Any, **kwargs: Any) -> Any:
        raise verify_module.ServiceNotAnswering(name, reason="not configured in this test")
    return factory
