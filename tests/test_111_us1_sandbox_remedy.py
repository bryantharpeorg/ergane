"""US1 of 111: a refused sandbox names the restriction that refused it.

These tests drive the refusal formatter over captured stderr strings and read
back which remedy it produced. No bwrap, no container — the failure this
story is about requires a host this host is not.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Sequence

import pytest

import factory.controlplane.verify as verify_module
from factory.mergequeue.models import Finding
from factory.supervision import demo_driver as driver_mod
from factory.verify.sandbox_remedy import sandbox_remedy


# ---------------------------------------------------------------------------
# fixtures and helpers
# ---------------------------------------------------------------------------


class ScriptedProbe:
    """A stand-in for the bwrap probe that records the argv it was handed."""

    def __init__(self, *, ok: bool, stderr: str = "") -> None:
        self.ok = ok
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]):
        self.calls.append(list(argv))
        return driver_mod.ProbeOutcome(ok=self.ok, stderr=self.stderr)


class DemoPaths:
    """The scratch paths one prepare-phase run is driven against."""

    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        self.state = tmp_path / "state"
        self.repo = tmp_path / "repo"
        self.config = tmp_path / "config.toml"
        self.answers = (
            Path(__file__).resolve().parents[1]
            / "container"
            / "ergane-install-answer.demo.toml"
        )


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DemoPaths:
    """Point config, state and git identity resolution at scratch directories."""
    paths = DemoPaths(tmp_path)
    paths.home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(paths.home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(paths.home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(paths.home / ".local" / "state"))
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(paths.config))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(paths.state))
    monkeypatch.delenv("FACTORY_CONFIG_PATH", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "absent-gitconfig-system"))
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    return paths


class FakeCli:
    """A stand-in for `_run_cli` that records argv and fakes install's writes."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if list(argv[:1]) == ["install"]:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text("version = 1\n", encoding="utf-8")
        return 0


def _passing_preflight() -> Finding:
    """A preflight finding that lets the prepare phase continue."""
    return Finding(check="llm", passed=True, detail="probe ok")


# ---------------------------------------------------------------------------
# T001 [US1] (spec US1-S1, FR-002, FR-003) AppArmor remedy
# ---------------------------------------------------------------------------


def test_apparmor_remedy_names_restriction_profile_and_load_commands() -> None:
    """The uid-map refusal names AppArmor, the right sysctl, and the shipped profile."""
    text = sandbox_remedy("bwrap: setting up uid map: Permission denied")

    assert "AppArmor's unprivileged-userns restriction" in text
    assert "kernel.apparmor_restrict_unprivileged_userns" in text
    assert "apparmor=unconfined" in text
    assert "attaches by executable path on exec" in text
    assert "container/ergane-bwrap.apparmor" in text
    assert "sudo apparmor_parser -r" in text
    assert "unprivileged_userns_clone" not in text


# ---------------------------------------------------------------------------
# T002 [US1] (spec US1-S2, FR-004) Masked-/proc remedy
# ---------------------------------------------------------------------------


def test_masked_proc_remedy_names_systempaths_unconfined_and_no_apparmor() -> None:
    """The proc-mount refusal names Docker's masked /proc and no AppArmor content."""
    text = sandbox_remedy("bwrap: Can't mount proc on /newroot/proc: Operation not permitted")

    assert "systempaths=unconfined" in text
    assert "apparmor_restrict_unprivileged_userns" not in text
    assert sandbox_remedy("bwrap: setting up uid map: Permission denied") != text


# ---------------------------------------------------------------------------
# T003 [US1] (spec US1-S3, FR-005) Unrecognised stderr
# ---------------------------------------------------------------------------


def test_unrecognised_stderr_remedy_admits_it_does_not_know() -> None:
    """A stderr that matches neither pattern gets a fallback naming both remedies."""
    text = sandbox_remedy("bwrap: some other failure")

    assert "not one of the two known shapes" in text
    assert "kernel.apparmor_restrict_unprivileged_userns" in text
    assert "systempaths=unconfined" in text


def test_driver_refusal_prints_stderr_then_fallback_for_unrecognised_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """For an unrecognised stderr the driver prints the stderr verbatim, then the fallback."""
    paths = _isolate(monkeypatch, tmp_path)
    stderr = "bwrap: some other failure"
    status = driver_mod.run_prepare_phase(
        state_home=paths.state,
        repo_root=paths.repo,
        answers_path=paths.answers,
        run_cli=FakeCli(paths.config),
        probe=ScriptedProbe(ok=False, stderr=stderr),
        preflight=_passing_preflight,
    )
    printed = capsys.readouterr().out

    assert status != 0
    assert stderr in printed
    assert "not one of the two known shapes" in printed


# ---------------------------------------------------------------------------
# T004 [US1] (spec US1-S4, FR-001) One source by identity
# ---------------------------------------------------------------------------


def test_demo_driver_and_host_probe_resolve_same_remedy_callable() -> None:
    """Both tiers import the same callable, not two copies of the advice."""
    assert driver_mod.sandbox_remedy is sandbox_remedy
    assert verify_module.sandbox_remedy is sandbox_remedy


# ---------------------------------------------------------------------------
# T005 [US1] (spec US1-S4, FR-001) Host-probe finding
# ---------------------------------------------------------------------------


def test_host_probe_finding_carries_apparmor_remedy_for_uid_map_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nonzero bwrap probe with the uid-map stderr renders the AppArmor remedy."""
    monkeypatch.setattr(verify_module.shutil, "which", lambda name: "/usr/bin/bwrap")

    def _uid_map_run(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=1,
            stdout="",
            stderr="bwrap: setting up uid map: Permission denied",
        )

    monkeypatch.setattr(verify_module, "_run_bwrap_probe", _uid_map_run)

    probe = verify_module.HostProbe(host_seam=verify_module._host_seam_factory)
    snapshot = asyncio.run(probe.gather(None))  # type: ignore[arg-type]
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    assert finding.check == "host"
    assert "kernel.apparmor_restrict_unprivileged_userns" in finding.detail
    assert "unprivileged_userns_clone" not in finding.detail
