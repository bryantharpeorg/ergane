"""111-US3: the demo refuses a credential the control plane has proven unusable.

Every test here drives the prepare phase's preflight seam with an injected
`Finding`. No container, no gateway, no network: the story is about what
`run_prepare_phase` decides after the control plane reports its own verdict.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import pytest

from factory.mergequeue.models import Finding
from factory.supervision.demo_driver import (
    CREDENTIAL_REMEDY,
    PREPARED_SENTINEL,
    UPSTREAM_MODEL_API_KEY,
    run_prepare_phase,
    sentinel_path,
)


class FakeCli:
    """A stand-in for `_run_cli` that writes a config file and records calls."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if list(argv[:1]) == ["install"]:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text("version = 1\n", encoding="utf-8")
        return 0


def _isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path, Path]:
    """Return scratch state, repo, config and answers paths.

    `ERGANE_CONFIG_PATH` is pointed at the scratch config so the prepare phase
    reads the same file the fake CLI writes, not the session default.
    """
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    config = tmp_path / "config.toml"
    answers = tmp_path / "answers.toml"
    answers.write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.delenv("FACTORY_CONFIG_PATH", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    return state, repo, config, answers


def _passing_llm_finding() -> Finding:
    return Finding(check="llm", passed=True, detail="all aliases passed")


def _failing_llm_finding(detail: str = "the gateway's own error") -> Finding:
    return Finding(check="llm", passed=False, detail=detail)


# -----------------------------------------------------------------------------
# T101 [US3-S1, FR-013, FR-015] fatal llm finding refuses before prepared
# -----------------------------------------------------------------------------


def test_fatal_llm_finding_refuses_before_prepared_sentinel(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed llm finding stops the phase, prints detail+remedy, no sentinel."""
    state, repo, config, answers = _isolated_paths(tmp_path, monkeypatch)
    detail = "401: Authentication Error - the gateway rejected the upstream key"

    status = run_prepare_phase(
        state_home=state,
        repo_root=repo,
        answers_path=answers,
        run_cli=FakeCli(config),
        preflight=lambda: _failing_llm_finding(detail),
    )
    printed = capsys.readouterr().out

    assert status != 0
    assert detail in printed
    assert "UPSTREAM_MODEL_API_KEY" in printed
    assert CREDENTIAL_REMEDY in printed
    assert not sentinel_path(state, PREPARED_SENTINEL).exists()


# -----------------------------------------------------------------------------
# T102 [US3-S2, FR-014] non-fatal finding lets preparation continue
# -----------------------------------------------------------------------------


def test_non_fatal_finding_continues_to_sandbox_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed host finding with passing llm continues to the sandbox probe."""
    from factory.supervision import demo_driver

    state, repo, config, answers = _isolated_paths(tmp_path, monkeypatch)
    probe_ran = False

    def probe(argv: Sequence[str]) -> demo_driver.ProbeOutcome:
        nonlocal probe_ran
        probe_ran = True
        return demo_driver.ProbeOutcome(ok=True, stderr="")

    def preflight() -> Finding:
        # host fails, but llm passes: the demo must not refuse here.
        return Finding(check="host", passed=False, detail="gh is unauthenticated")

    status = run_prepare_phase(
        state_home=state,
        repo_root=repo,
        answers_path=answers,
        run_cli=FakeCli(config),
        probe=probe,
        preflight=preflight,
    )

    assert status == 0
    assert probe_ran
    assert sentinel_path(state, PREPARED_SENTINEL).exists()


# -----------------------------------------------------------------------------
# T103 [US3-S3, FR-014] fatal set is exactly {"llm"}
# -----------------------------------------------------------------------------


def test_fatal_check_set_is_exactly_llm() -> None:
    """The checks that stop the demo are a named, tested constant."""
    from factory.supervision.demo_driver import FATAL_PREPARE_CHECKS

    assert FATAL_PREPARE_CHECKS == {"llm"}


# -----------------------------------------------------------------------------
# T104 [US3-S1, FR-016] remedy names the variable and driver never looks it up
# -----------------------------------------------------------------------------


def test_remedy_names_variable_and_driver_never_reads_it() -> None:
    """The refusal names UPSTREAM_MODEL_API_KEY; the driver never reads it from env."""
    from factory.supervision import demo_driver

    assert "UPSTREAM_MODEL_API_KEY" in demo_driver.CREDENTIAL_REMEDY

    source = (Path(__file__).resolve().parents[1] / "factory" / "supervision" / "demo_driver.py").read_text(encoding="utf-8")
    # The variable is set on the gateway service only; the engine container
    # (and therefore the driver) must not look it up in the environment.
    assert not re.search(
        r'os\.environ\.get\(["\']?UPSTREAM_MODEL_API_KEY["\']?\)',
        source,
    )
    assert 'os.environ["UPSTREAM_MODEL_API_KEY"]' not in source


# -----------------------------------------------------------------------------
# T105 [FR-017] raising probe becomes a failed finding with exception named
# -----------------------------------------------------------------------------


def test_raising_preflight_becomes_failed_finding_not_traceback_handler(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising preflight is caught, named, and refused inside the phase."""
    state, repo, config, answers = _isolated_paths(tmp_path, monkeypatch)

    def preflight() -> Finding:
        raise RuntimeError("gateway module import failed")

    status = run_prepare_phase(
        state_home=state,
        repo_root=repo,
        answers_path=answers,
        run_cli=FakeCli(config),
        preflight=preflight,
    )
    printed = capsys.readouterr().out

    assert status != 0
    assert "RuntimeError" in printed
    assert "gateway module import failed" in printed
    assert "UPSTREAM_MODEL_API_KEY" in printed
    assert CREDENTIAL_REMEDY in printed
    assert "first boot failed" not in printed
    assert not sentinel_path(state, PREPARED_SENTINEL).exists()
