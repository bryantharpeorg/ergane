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
# Verify-stubbing helper (used by tests that need a passing in-run verify)
# ---------------------------------------------------------------------------


def _stub_verify_for_passing_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the host/forge/temporal/LLM verify probes so the in-run verify
    reports the LLM registry as configured without touching real services.
    """
    import factory.controlplane.verify as verify_module

    async def _stub_host_probe(_self: object, _config: object) -> object:
        from factory.controlplane.verify import HostItem, HostSnapshot

        return HostSnapshot(
            items=(
                HostItem(name="bwrap", present=True, usable=True, purpose="sandbox", detail="ok"),
                HostItem(name="git", present=True, usable=True, purpose="version control", detail="ok"),
                HostItem(name="gh", present=True, usable=True, purpose="forge", detail="ok"),
            ),
            detail="stubbed host prerequisites are present",
        )

    async def _stub_forge_probe(_self: object, _config: object) -> object:
        from factory.mergequeue.gh import FORGE_CAPABLE, ForgeCapability

        return ForgeCapability(
            condition=FORGE_CAPABLE,
            binary="gh",
            version="stubbed",
            command=("gh", "pr", "view", "--json"),
            fields=("number", "state"),
            undeclared=(),
            detail="stubbed forge capability is present",
        )

    async def _stub_temporal_probe(_self: object, _config: object) -> object:
        from factory.controlplane.verify import TemporalSnapshot

        return TemporalSnapshot(
            address="127.0.0.1:7233",
            namespace="ergane",
            namespace_exists=True,
            detail="stubbed temporal namespace exists",
        )

    async def _stub_llm_gather(_self: object, _config: object) -> object:
        from factory.controlplane.verify import LLMAliasResult, LLMSnapshot

        registry = config_module.load_personas()
        aliases: set[str] = set()
        for p in registry.values():
            if p.routes_through_gateway:
                if p.model:
                    aliases.add(p.model)
                if p.fallback:
                    aliases.add(p.fallback)
        results = [
            LLMAliasResult(
                alias=a,
                model=a,
                completed=True,
                persona_names=("stubbed",),
                detail=f"stubbed 1-token completion for {a}",
            )
            for a in sorted(aliases)
        ]
        return LLMSnapshot(
            aliases=tuple(sorted(aliases)),
            persona_by_alias={a: ("stubbed",) for a in aliases},
            results=tuple(results),
            detail=f"stubbed LLM probe passed for {len(results)} aliases",
        )

    monkeypatch.setattr(verify_module.HostProbe, "gather", _stub_host_probe)
    monkeypatch.setattr(verify_module.ForgeCapabilityProbe, "gather", _stub_forge_probe)
    monkeypatch.setattr(verify_module.TemporalProbe, "gather", _stub_temporal_probe)
    monkeypatch.setattr(verify_module.LLMProbe, "gather", _stub_llm_gather)


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

    def runner(
        answers: list[str],
        *argv: str,
        prompter: _FilePrompter | None = None,
    ) -> tuple[Run, _FilePrompter]:
        if prompter is None:
            prompter = _FilePrompter(list(answers))
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
        monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
        return _invoke(["install", *argv]), prompter

    return runner


def _assert_only_model_and_fallback_changed(
    written_path: Path,
) -> dict[str, Persona]:
    """Load `written_path` and the shipped example and assert every persona is
    identical except for possible changes to `model` and `fallback`.

    Returns the written personas for further assertions.
    """
    import yaml

    written = config_module.load_personas(str(written_path))
    example_raw = yaml.safe_load(config_module.shipped_registry_text())
    assert isinstance(example_raw, dict)

    assert set(written.keys()) == set(example_raw.keys())
    for name, persona in written.items():
        example_fields = example_raw[name]
        comparisons = (
            ("agent", "agent", lambda v: v),
            ("skills", "skills", lambda v: tuple(v) if isinstance(v, list) else v),
            ("write_scope", "write_scope", lambda v: v),
            ("needs_worktree", "needs_worktree", lambda v: v),
            ("timeout_s", "timeout", lambda v: v),
            ("context_window", "context_window", lambda v: v),
        )
        for field, yaml_key, normalize in comparisons:
            written_val = getattr(persona, field)
            raw_val = example_fields.get(yaml_key)
            example_val = normalize(raw_val) if raw_val is not None else None
            assert written_val == example_val, (
                f"persona '{name}' field '{yaml_key}' changed: "
                f"{written_val!r} != {example_val!r}"
            )
    return written


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
    """Probe seam that records every alias probed and returns pass/fail per alias.

    `failures` controls the 1-token completion seam.  `canary_failures`
    controls the judge canary seam independently so US4-S3 can test the case
    where an alias passes the 1-token probe but fails the canary.
    """

    def __init__(
        self,
        failures: set[str] | None = None,
        canary_failures: set[str] | None = None,
    ) -> None:
        self.failures = failures or set()
        self.canary_failures = canary_failures or set()
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
        passed = alias not in self.canary_failures
        return CanaryResult(
            alias=alias,
            passed=passed,
            detail=f"{'passed' if passed else 'failed'} canary for {alias}",
        )


class _RecordingFilePrompter(_FilePrompter):
    """File prompter that records every prompt/default it was asked."""

    def __init__(self, answers: list[str]) -> None:
        super().__init__(answers)
        self.prompts: list[tuple[str, str | None]] = []

    def ask(
        self, prompt: str, *, default: str | None = None, error: str | None = None
    ) -> str:
        self.prompts.append((prompt, default))
        return super().ask(prompt, default=default, error=error)


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
    `fallback`.  The same run invokes verify_controlplane on it and reports
    the LLM probe as passing.
    """
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    # One empty answer per gateway persona primary (6) and fallback (6).
    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    # Stub the post-write verify probes so the same run reports [PASS] llm:.
    _stub_verify_for_passing_llm(monkeypatch)

    result, prompter = interview(answers)

    # The interview consumed every planned answer.
    assert prompter._index == len(answers)

    # The registry was written, parses, and preserves every field except
    # model/fallback.
    assert personas_path.exists()
    personas = _assert_only_model_and_fallback_changed(personas_path)

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

    # stdout names the file that was written and summarises each persona.
    assert f"wrote {personas_path}" in result.stdout
    for name in ("implementer", "judge", "debugger", "closer", "architect", "researcher", "opus-closer"):
        model = personas[name].model
        fallback = personas[name].fallback
        assert f"  {name}: model={model}, fallback={fallback}" in result.stdout

    # Verify ran in the same install invocation and reported the LLM probe passing.
    assert "verifying the control plane..." in result.stdout
    assert "[PASS] llm:" in result.stdout


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
    """US4-S3: the judge alias passes the 1-token probe but fails the canary.

    Install exits nonzero naming the judge, the requirement and every alias
    tried, and the on-disk registry stays the seeded example byte-for-byte.
    """
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    # 1-token passes for every alias; only the judge alias fails the canary.
    patched_seams.canary_failures = {"proxy/judge-small"}

    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    result, _ = interview(answers)

    assert result.code != 0
    output = result.stderr.lower() + result.stdout.lower()
    assert "judge" in output
    assert (
        "structured output" in output or "structured-output" in output
    ), "error must name the judge requirement"
    for alias in ALIASES:
        assert alias in output, f"error must name every alias tried, missing {alias!r}"

    # The judge canary was actually invoked for the chosen judge alias.
    assert patched_seams.canary_calls == ["proxy/judge-small"]

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
    """US4-S4: even with an all-Enter answer file, the judge primary and every
    fallback are explicitly asked; none are defaulted through by a blanket
    accept mechanism."""
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")
    # 11 base answers + 6 primary + 6 fallback + 1 subscription = 24.
    answers = list(BASE_ANSWERS) + [""] * 13

    prompter = _RecordingFilePrompter(list(answers))
    result, _ = interview(answers, prompter=prompter)

    # The interview consumed every planned answer, one per recorded prompt.
    assert prompter._index == len(answers)
    assert prompter._index == len(prompter.prompts)

    # The judge primary prompt was explicitly presented (it is the only
    # primary line that requires confirmation and is exempt from blanket accept).
    judge_primary_prompts = [
        (p, d) for p, d in prompter.prompts if "judge primary" in p.lower()
    ]
    assert len(judge_primary_prompts) == 1, "judge primary must be asked exactly once"

    # Every gateway persona had its fallback explicitly presented with a default.
    for name in PERSONA_REQUIREMENTS:
        fallback_prompts = [
            (p, d)
            for p, d in prompter.prompts
            if p.lower().startswith(f"{name} fallback")
        ]
        assert len(fallback_prompts) == 1, f"{name} fallback must be asked exactly once"
        assert fallback_prompts[0][1] is not None, f"{name} fallback must have a default"


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
