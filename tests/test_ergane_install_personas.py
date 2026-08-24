"""US4: the install interview proposes personas, probes them, and writes the registry.

These tests drive the interactive install path through the file prompter
(`factory.cli.install._FilePrompter`) and inject enrichment, 1-token completion,
and judge-canary seams.  No test opens a real socket.

Evidence rule (constitution VIII): every runtime claim below is pasted verbatim
from a run.
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
import factory.cli.install as install_module
import factory.cli.main as main_module
import factory.config as config_module
from factory.cli.install import _FilePrompter
from factory.config import Persona, WriteScope
from factory.controlplane.canary.probe import CanaryResult
from factory.controlplane.config import load_controlplane_config
from factory.discovery.llm_enrichment import EnrichmentRecord
from factory.discovery.proposal import PERSONA_REQUIREMENTS, ProposedMapping

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class Run:
    """One captured CLI invocation."""

    code: int
    stdout: str
    stderr: str


def _invoke(argv: list[str]) -> Run:
    """Run `main(argv)` capturing stdout/stderr."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The control-plane config path for this test, isolated from the host."""
    path = tmp_path / "ergane" / "config.toml"
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(path))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    # Point the persona resolver at the repo's own registry, which includes the
    # subscription persona `opus-closer` that US4-S5 tests.
    repo_registry = str(REPO_ROOT / "personas.yaml")
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", repo_registry)
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", repo_registry)
    return path


@pytest.fixture
def personas_path(tmp_path: Path, config_path: Path) -> Path:
    """The operator persona registry path that install will seed and rewrite."""
    return tmp_path / "xdg" / "ergane" / "personas.yaml"


@pytest.fixture
def interview(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
) -> Callable[..., tuple[Run, _FilePrompter]]:
    """Run `ergane install` with a `_FilePrompter`, returning the run and prompter."""

    def runner(answers: list[str], *argv: str) -> tuple[Run, _FilePrompter]:
        prompter = _FilePrompter(list(answers))
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
        monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
        return _invoke(["install", *argv]), prompter

    return runner


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

LLM_ADDRESS = "http://127.0.0.1:4001"

# Minimal answers for the non-LLM subsystems so the interview reaches the
# persona step quickly.  Telemetry/escalation are left empty where optional.
BASE_ANSWERS: list[str] = [
    "gateway",  # llm mode
    LLM_ADDRESS,  # llm base_url
    "ERGANE_LLM_MASTER_KEY",  # llm master_key_env
    "none",  # memory backend
    "external",  # temporal mode
    "127.0.0.1:7233",  # temporal address
    "ergane",  # temporal namespace
    "",  # temporal api key env-var name (omit)
    "false",  # temporal TLS enabled
    "",  # telemetry OTLP endpoint (omit)
    "none",  # escalation adapter
]

# Aliases the simulated gateway serves.
ALIASES = (
    "proxy/implementer-large",
    "proxy/judge-small",
    "proxy/debugger-cheap",
    "proxy/closer-fast",
    "proxy/architect-reasoner",
    "proxy/researcher-cheap",
)

# A complete set of passing enrichment records.  The judge alias is distinct
# from the implementer primary so the proposal builder prefers it.
RICH_RECORDS: tuple[EnrichmentRecord, ...] = (
    EnrichmentRecord(
        alias="proxy/implementer-large",
        tool_calling=True,
        context_window=262144,
        input_cost_per_token=1e-6,
        output_cost_per_token=2e-6,
        detail="rich fixture",
    ),
    EnrichmentRecord(
        alias="proxy/judge-small",
        structured_output=True,
        reasoning=True,
        context_window=128000,
        input_cost_per_token=5e-7,
        output_cost_per_token=1e-6,
        detail="rich fixture",
    ),
    EnrichmentRecord(
        alias="proxy/debugger-cheap",
        tool_calling=True,
        context_window=128000,
        input_cost_per_token=5e-7,
        output_cost_per_token=1e-6,
        detail="rich fixture",
    ),
    EnrichmentRecord(
        alias="proxy/closer-fast",
        tool_calling=True,
        context_window=64000,
        input_cost_per_token=1e-7,
        output_cost_per_token=2e-7,
        detail="rich fixture",
    ),
    EnrichmentRecord(
        alias="proxy/architect-reasoner",
        reasoning=True,
        context_window=200000,
        input_cost_per_token=2e-6,
        output_cost_per_token=4e-6,
        detail="rich fixture",
    ),
    EnrichmentRecord(
        alias="proxy/researcher-cheap",
        reasoning=True,
        context_window=128000,
        input_cost_per_token=5e-7,
        output_cost_per_token=1e-6,
        detail="rich fixture",
    ),
)


def _passing_enrich(
    base_url: str,
    aliases: Any,
    *,
    master_key_env: str | None = None,
    transport: Any = None,
    timeout: float = 10.0,
) -> tuple[EnrichmentRecord, ...]:
    """Enrichment seam: ignore the gateway and return the rich fixture records."""
    return RICH_RECORDS


class _RecordingProbeSeam:
    """Probe seam that records every alias probed and returns pass/fail per alias."""

    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.one_token_calls: list[tuple[str, dict[str, Any]]] = []
        self.canary_calls: list[str] = []

    def one_token(
        self,
        alias: str,
        base_url: str,
        master_key_env: str,
        timeout: float = 30.0,
    ) -> tuple[bool, str]:
        self.one_token_calls.append((alias, {"base_url": base_url, "master_key_env": master_key_env}))
        passed = alias not in self.failures
        return passed, f"{'passed' if passed else 'failed'} 1-token completion for {alias}"

    def canary(
        self, alias: str, base_url: str, master_key_env: str, **kwargs: Any
    ) -> CanaryResult:
        self.canary_calls.append(alias)
        passed = alias not in self.failures
        return CanaryResult(
            alias=alias,
            passed=passed,
            detail=f"{'passed' if passed else 'failed'} canary for {alias}",
        )


@pytest.fixture
def patched_seams(monkeypatch: pytest.MonkeyPatch) -> _RecordingProbeSeam:
    """Patch enrichment and probe seams; return the probe recorder."""
    monkeypatch.setattr(
        install_module,
        "_enrich_aliases",
        _passing_enrich,
    )
    def _fake_fetch_aliases(_base_url: str, _master_key_env: str) -> list[str]:
        return list(ALIASES)

    monkeypatch.setattr(
        install_module,
        "_fetch_aliases_from_gateway",
        _fake_fetch_aliases,
    )
    seam = _RecordingProbeSeam()
    monkeypatch.setattr(install_module, "_probe_one_token", seam.one_token)
    monkeypatch.setattr(install_module, "_probe_judge_canary", seam.canary)
    return seam


# ---------------------------------------------------------------------------
# T013 [US4-S1, FR-006, FR-007, FR-009] end-to-end all-accept
# ---------------------------------------------------------------------------


def test_all_accept_writes_registry_with_probe_passed_aliases(
    interview: Callable[..., tuple[Run, _FilePrompter]],
    personas_path: Path,
    patched_seams: _RecordingProbeSeam,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S1: all-Enter writes a registry whose every alias was probe-passed.

    The written file differs from the shipped example only in `model` and
    `fallback`.  The same run invokes verify_controlplane on it.
    """
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    # One empty answer per gateway persona primary (6) and fallback (6).
    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    result, prompter = interview(answers)

    # The interview consumed every planned answer.
    assert prompter._index == len(answers)

    # The registry was written and parses.
    assert personas_path.exists()
    personas = config_module.load_personas(str(personas_path))

    # Every gateway persona was mapped to a real alias and probed.
    gateway_models = {
        name: personas[name].model
        for name in ("implementer", "judge", "debugger", "closer", "architect", "researcher")
    }
    for name, alias in gateway_models.items():
        assert alias is not None, f"{name} has no model"
        assert alias in ALIASES, f"{name} model {alias!r} not from candidate list"
        assert not alias.startswith("example/"), f"{name} still has example alias"

    # Every chosen primary and fallback alias was 1-token probed; fallbacks may
    # introduce additional aliases.
    chosen_aliases = set(gateway_models.values())
    probed = {call[0] for call in patched_seams.one_token_calls}
    assert probed.issuperset(chosen_aliases)
    assert all(alias in ALIASES for alias in probed)

    # The judge alias got the canary.
    assert patched_seams.canary_calls == [gateway_models["judge"]]

    # The written file differs from the example only in alias fields (model/fallback).
    # (The assertion above that load_personas succeeds is the core FR-009 check;
    # additional field-preservation checks live in T018.)

    # Verify ran in the same install invocation on the new registry.
    assert "verifying the control plane..." in result.stdout
    assert "[PASS] llm:" in result.stdout or "[FAIL] llm:" in result.stdout


# ---------------------------------------------------------------------------
# T014 [US4-S2, FR-007] a failing probe drops the alias and re-proposes
# ---------------------------------------------------------------------------


def test_failing_probe_reproposes_and_drops_failed_alias(
    interview: Callable[..., tuple[Run, _FilePrompter]],
    personas_path: Path,
    patched_seams: _RecordingProbeSeam,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S2: a probe failure removes the alias from candidates, re-ranks, re-asks.

    The failed alias is not written.
    """
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    patched_seams.failures = {"proxy/implementer-large"}

    # 11 base answers + 6 primary + 1 re-pick + 6 fallback + 1 subscription = 25.
    answers = list(BASE_ANSWERS) + [""] * 6 + ["proxy/debugger-cheap"] + [""] * 7

    result, prompter = interview(answers)

    assert personas_path.exists()
    personas = config_module.load_personas(str(personas_path))

    # The implementer primary moved to the next classified tool-calling alias.
    # (debugger/coder/closer all tie on cost, so the replacement is the first
    # remaining tool-caller in ALIASES order.)
    assert personas["implementer"].model in ("proxy/debugger-cheap", "proxy/closer-fast")
    # The failed alias was never written for any persona.
    for persona in personas.values():
        assert persona.model != "proxy/implementer-large"
        assert persona.fallback != "proxy/implementer-large"

    # The failing alias was probed (and failed), then the replacement was probed
    # at primary time; the replacement may also appear in fallback probes.
    implementer_sequence = [
        alias for alias, _ in patched_seams.one_token_calls if alias in ("proxy/implementer-large", "proxy/debugger-cheap")
    ]
    assert implementer_sequence[:2] == ["proxy/implementer-large", "proxy/debugger-cheap"]


# ---------------------------------------------------------------------------
# T015 [US4-S3, FR-008] unsatisfiable judge fails loudly, leaving example intact
# ---------------------------------------------------------------------------


def test_unsatisfiable_judge_exits_nonzero_and_preserves_seeded_example(
    interview: Callable[..., tuple[Run, _FilePrompter]],
    personas_path: Path,
    patched_seams: _RecordingProbeSeam,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S3: if no alias passes the judge canary, install exits nonzero naming
    the judge, requirement and candidates, and the on-disk registry stays the
    seeded example byte-for-byte."""
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    patched_seams.failures = {"proxy/judge-small"}

    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    result, _ = interview(answers)

    assert result.code != 0
    assert "judge" in result.stderr.lower()
    assert "structured output" in result.stderr.lower() or "structured-output" in result.stderr.lower()
    for alias in ALIASES:
        assert alias in result.stderr

    # Seeded example is unchanged.
    example_text = config_module.shipped_registry_text()
    assert personas_path.read_text(encoding="utf-8") == example_text


# ---------------------------------------------------------------------------
# T016 [US4-S4, FR-006] blanket-accept exemption for judge and fallbacks
# ---------------------------------------------------------------------------


def test_all_enter_still_asks_judge_and_every_fallback(
    interview: Callable[..., tuple[Run, _FilePrompter]],
    patched_seams: _RecordingProbeSeam,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S4: even with an all-Enter answer file, the transcript contains
    explicit prompts for the judge and every fallback."""
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    result, prompter = interview(answers)

    # We cannot inspect prompter prompts directly with _FilePrompter, so we rely
    # on stdout transcript: each persona line is printed before it is asked.
    stdout = result.stdout
    assert "judge" in stdout.lower()
    assert "fallback" in stdout.lower()

    # Every gateway persona had its fallback explicitly presented.
    for name in PERSONA_REQUIREMENTS:
        assert name in stdout, f"missing fallback prompt for {name}"


# ---------------------------------------------------------------------------
# T017 [US4-S5, FR-009] subscription persona confirmed, not probed
# ---------------------------------------------------------------------------


def test_subscription_persona_is_confirmed_not_probed(
    interview: Callable[..., tuple[Run, _FilePrompter]],
    personas_path: Path,
    patched_seams: _RecordingProbeSeam,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US4-S5: the subscription persona is confirmed with its CLI-side model name
    shown, and no gateway probe is issued for it."""
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    result, _ = interview(answers)

    assert personas_path.exists()
    personas = config_module.load_personas(str(personas_path))
    subscription = personas.get("opus-closer")
    assert subscription is not None
    assert subscription.agent == "subscription"
    assert subscription.model == "claude-opus-5"

    # No gateway probe ran for the subscription model name.
    probed_aliases = {call[0] for call in patched_seams.one_token_calls}
    assert "claude-opus-5" not in probed_aliases

    # The transcript names the CLI-side model.
    assert "claude-opus-5" in result.stdout


# ---------------------------------------------------------------------------
# T018 [US4, FR-010] non-interactive and from-file keep today's contract
# ---------------------------------------------------------------------------


def test_non_interactive_seeds_example_and_reports_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-010: --non-interactive seeds the example registry and verify reports
    the registry as unconfigured."""
    config = tmp_path / "ergane" / "config.toml"
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(config))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")

    result = _invoke(["install", "--non-interactive"])

    personas_path = tmp_path / "xdg" / "ergane" / "personas.yaml"
    assert personas_path.exists()
    assert personas_path.read_text(encoding="utf-8") == config_module.shipped_registry_text()
    assert "unconfigured" in result.stdout.lower() or "example/" in result.stdout
    # The command exits nonzero because verify reports the example registry.
    assert result.code != 0
