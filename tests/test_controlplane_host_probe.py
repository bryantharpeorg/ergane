"""Tests for `HostProbe` (US2, 054-a-stranger-can-install-ergane).

Host state is simulated through the probe's injected seam in every test below.
No test in this module reaches the real host.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import factory.controlplane.verify as verify_module
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.mergequeue.gh import FORGE_CAPABLE, ForgeCapability


@dataclass(frozen=True)
class _HostState:
    """A simulated host for `HostProbe.gather` to inspect."""

    bwrap_on_path: bool = True
    git_on_path: bool = True
    gh_on_path: bool = True
    gh_authenticated: bool = True


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


def _blank_config() -> Cfg:
    """A config whose subsystems are disabled or stubbed; the host probe ignores it."""
    return Cfg(
        version=1,
        llm=Cfg.LLM(mode="gateway"),
        memory=Cfg.Memory(backend="none"),
        temporal=Cfg.Temporal(mode="external"),
        telemetry=Cfg.Telemetry(mode="none"),
        escalation=Cfg.Escalation(adapter="telegram"),
    )


# ---------------------------------------------------------------------------
# T011 [US2-S1] missing bwrap yields a failing finding naming bwrap and its purpose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_bwrap_yields_failing_finding() -> None:
    """A host without `bwrap` reports one failing finding that names `bwrap`."""
    host = _HostState(bwrap_on_path=False)
    probe = verify_module.HostProbe(host_seam=lambda: _host_check(host))

    snapshot = await probe.gather(_blank_config())
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    assert "bwrap" in finding.detail
    assert "sandbox" in finding.detail or "agent" in finding.detail
    assert "install" in finding.detail or "bubblewrap" in finding.detail


# ---------------------------------------------------------------------------
# T012 [US2-S2] gh present but unauthenticated is distinguishable from gh absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gh_present_but_unauthenticated_is_distinguished() -> None:
    """`gh` present-but-unauthenticated reports differently from `gh` absent."""
    present_unauth = _HostState(gh_on_path=True, gh_authenticated=False)
    absent = _HostState(gh_on_path=False)

    present_probe = verify_module.HostProbe(host_seam=lambda: _host_check(present_unauth))
    absent_probe = verify_module.HostProbe(host_seam=lambda: _host_check(absent))

    present_snapshot = await present_probe.gather(_blank_config())
    absent_snapshot = await absent_probe.gather(_blank_config())

    present_finding = present_probe.evaluate(present_snapshot)
    absent_finding = absent_probe.evaluate(absent_snapshot)

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
    # Simulate a passing host for the default HostProbe() installed in REGISTRY.
    monkeypatch.setattr(verify_module, "_host_seam_factory", lambda: _host_check(_HostState()))
    # 078-US2 added a second host-facing probe, which asks the installed `gh`
    # which `--json` fields it declares. Simulated here for the same reason the
    # host is: this test is about the five subsystem probes, and neither of the
    # two host-facing ones may make its verdict depend on the runner's machine.
    monkeypatch.setattr(
        verify_module, "_forge_capability_seam_factory", _capable_forge_seam
    )

    # Make the five subsystem probes deterministic so their findings do not depend
    # on real services in this environment.
    monkeypatch.setattr(verify_module, "_llm_client_factory", _raising("llm"))
    monkeypatch.setattr(verify_module, "_temporal_client_factory", _raising("temporal"))
    monkeypatch.setattr(verify_module, "_memory_client_factory", _raising("memory"))
    monkeypatch.setattr(verify_module, "_telegram_bot_factory", _raising("escalation"))

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'version = 1\n\n[llm]\nmode = "gateway"\nbase_url = "http://llm.test"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n\n[memory]\nbackend = "none"\n\n'
        '[temporal]\nmode = "external"\naddress = "127.0.0.1:1"\nnamespace = "factory"\n\n'
        '[telemetry]\n\n[escalation]\nadapter = "telegram"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))

    # Full registry: the two host-facing probes + engine + five existing probes.
    full_findings, _ = await verify_module.verify_controlplane_async(str(config_path))
    full_non_host = [
        f
        for f in full_findings
        if f.check not in ("host", "forge", "engine")
    ]
    host_finding = next(f for f in full_findings if f.check == "host")
    assert host_finding.passed is True
    assert "prerequisites are present" in host_finding.detail

    # Registry without the host-facing or engine probes: the five pre-105 probes in isolation.
    original_registry = list(verify_module.REGISTRY)
    five_probe_registry = [
        p
        for p in original_registry
        if not isinstance(
            p,
            (
                verify_module.HostProbe,
                verify_module.ForgeCapabilityProbe,
                verify_module.EngineIdentityProbe,
            ),
        )
    ]
    assert len(five_probe_registry) == 5
    verify_module.REGISTRY[:] = five_probe_registry
    try:
        baseline_findings, _ = await verify_module.verify_controlplane_async(str(config_path))
    finally:
        verify_module.REGISTRY[:] = original_registry

    assert {f.check for f in baseline_findings} == {"llm", "temporal", "memory", "telemetry", "escalation"}
    assert full_non_host == list(baseline_findings)


# ---------------------------------------------------------------------------
# T014 [US2-S4] seam injectability and no real host access in this module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_host_probe_seam_is_injectable() -> None:
    """The probe's host access is fully replaceable; no unpatched call escapes."""
    calls: list[tuple[()]] = []

    def _seam() -> dict[str, Any]:
        calls.append(())
        return _host_check(_HostState())

    probe = verify_module.HostProbe(host_seam=_seam)
    await probe.gather(_blank_config())

    assert calls == [()]


def _function_patches_host_seam(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if `func` replaces `verify_module._host_seam_factory`."""
    for node in ast.walk(func):
        # `monkeypatch.setattr(verify_module, "_host_seam_factory", ...)`
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "_host_seam_factory"
        ):
            return True
        # `verify_module._host_seam_factory = ...`
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "_host_seam_factory"
        ):
            return True
    return False


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


def test_module_does_not_call_real_host() -> None:
    """No test reaches the real host: no forbidden primitives and no unpatched seam."""
    module_path = Path(__file__).resolve()
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Direct forbidden host calls.
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

    # Every HostProbe() must be constructed with an explicit host_seam.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_host_probe = (
            (isinstance(func, ast.Attribute) and func.attr == "HostProbe")
            or (isinstance(func, ast.Name) and func.id == "HostProbe")
        )
        if not is_host_probe:
            continue
        kw_names = {kw.arg for kw in node.keywords if kw.arg is not None}
        assert "host_seam" in kw_names, (
            "HostProbe() constructed without an injected host_seam"
        )

    # Every verify_controlplane_async call must live in a function that also
    # replaces the default host seam.
    parent_map = _build_parent_map(tree)
    function_patch_status: dict[ast.FunctionDef | ast.AsyncFunctionDef, bool] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_patch_status[node] = _function_patches_host_seam(node)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_verify = (
            (isinstance(func, ast.Attribute) and func.attr == "verify_controlplane_async")
            or (isinstance(func, ast.Name) and func.id == "verify_controlplane_async")
        )
        if not is_verify:
            continue
        current: ast.AST | None = parent_map.get(node)
        enclosing: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                enclosing = current
                break
            current = parent_map.get(current)
        assert enclosing is not None, (
            "verify_controlplane_async called outside a test function"
        )
        assert function_patch_status[enclosing], (
            "verify_controlplane_async called without patching _host_seam_factory"
        )


# ---------------------------------------------------------------------------
# T015 [US2-S5] probe reports and does not remediate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_host_probe_reports_and_does_not_remediate(tmp_path: Path) -> None:
    """A missing prerequisite yields a finding and makes no host changes."""
    marker = tmp_path / "no-remediation-marker"
    touched: list[int] = []

    def _seam() -> dict[str, Any]:
        # A remediating probe might write a file or install a package. Record
        # that this seam ran without letting the probe reach the filesystem.
        touched.append(1)
        return _host_check(_HostState(bwrap_on_path=False))

    probe = verify_module.HostProbe(host_seam=_seam)
    snapshot = await probe.gather(_blank_config())
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    assert touched == [1]
    assert not marker.exists()
    assert "bwrap" in finding.detail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capable_forge_seam() -> ForgeCapability:
    """Simulate a `gh` that declares every `--json` field the landing poller sends."""
    return ForgeCapability(
        condition=FORGE_CAPABLE,
        binary="/usr/bin/gh",
        version="gh version 9.9.9 (2026-01-01)",
        command=("pr", "view"),
        fields=("state",),
        undeclared=(),
        detail="simulated: this binary declares every field the poller sends",
    )


def _raising(name: str) -> Any:
    """A seam factory that reports ServiceNotAnswering for the named subsystem."""
    def factory(*args: Any, **kwargs: Any) -> Any:
        raise verify_module.ServiceNotAnswering(name, reason="not configured in this test")
    return factory
