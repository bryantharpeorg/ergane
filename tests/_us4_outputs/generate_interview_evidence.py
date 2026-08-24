"""Generate US4-SC-004 evidence: interview transcript, registry diff, verify.

Runs `ergane install` with injected enrichment/probe seams against a fresh
operator config directory.  Captures stdout+stderr, diffs the written
personas.yaml against the shipped example, and reports the in-run verify
findings.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import factory.cli.init as init_module
import factory.cli.install as install_module
import factory.cli.main as main_module
import factory.config as config_module
import factory.controlplane.verify as verify_module
from factory.cli.install import _FilePrompter
from factory.controlplane.canary.probe import CanaryResult
from factory.discovery.llm_enrichment import EnrichmentRecord


LLM_ADDRESS = "http://127.0.0.1:4001"

BASE_ANSWERS = [
    "gateway",
    LLM_ADDRESS,
    "ERGANE_LLM_MASTER_KEY",
    "none",
    "external",
    "127.0.0.1:7233",
    "ergane",
    "",
    "false",
    "",
    "none",
]

ALIASES = [
    "proxy/implementer-large",
    "proxy/judge-small",
    "proxy/debugger-cheap",
    "proxy/closer-fast",
    "proxy/architect-reasoner",
    "proxy/researcher-cheap",
]

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


class _RecordingProbeSeam:
    def __init__(self) -> None:
        self.one_token_calls: list[tuple[str, dict[str, object]]] = []
        self.canary_calls: list[str] = []

    def one_token(
        self,
        alias: str,
        base_url: str,
        master_key_env: str,
        timeout: float = 30.0,
    ) -> tuple[bool, str]:
        self.one_token_calls.append(
            (alias, {"base_url": base_url, "master_key_env": master_key_env})
        )
        return True, f"passed 1-token completion for {alias}"

    def canary(
        self, alias: str, base_url: str, master_key_env: str, **_: object
    ) -> CanaryResult:
        self.canary_calls.append(alias)
        return CanaryResult(
            alias=alias,
            passed=True,
            detail=f"passed canary for {alias}",
        )


def _invoke(argv: list[str]) -> tuple[int, str, str]:
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
    return code, buf_out.getvalue(), buf_err.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config = tmp_path / "ergane" / "config.toml"
        os.environ["ERGANE_CONFIG_PATH"] = str(config)
        os.environ["FACTORY_CONFIG_PATH"] = str(config)
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
        os.environ["HOME"] = str(tmp_path / "home")
        os.environ["ERGANE_LLM_MASTER_KEY"] = "sk-fake-master"
        os.environ.pop("ERGANE_PERSONAS_PATH", None)
        os.environ.pop("FACTORY_PERSONAS_PATH", None)
        os.environ.pop("TEMPORAL_ADDRESS", None)
        os.environ.pop("TEMPORAL_NAMESPACE", None)

        install_module._enrich_aliases = (
            lambda _base_url, _aliases, *, master_key_env=None, transport=None, timeout=10.0: RICH_RECORDS
        )
        install_module._fetch_aliases_from_gateway = lambda _b, _m: list(ALIASES)
        seam = _RecordingProbeSeam()
        install_module._probe_one_token = seam.one_token
        install_module._probe_judge_canary = seam.canary

        # Stub verify probes that depend on the host/network so the in-run verify
        # passes on the registry we just wrote.
        verify_module.HostProbe.gather = _stub_host_probe
        verify_module.ForgeCapabilityProbe.gather = _stub_forge_probe
        verify_module.TemporalProbe.gather = _stub_temporal_probe

        async def _stub_llm_gather(_self, _config):
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

        verify_module.LLMProbe.gather = _stub_llm_gather

        answers = list(BASE_ANSWERS) + [""] * 13
        prompter = _FilePrompter(list(answers))
        init_module._prompter_factory = lambda: prompter

        code, stdout, stderr = _invoke(["install"])

        personas_path = tmp_path / "xdg" / "ergane" / "personas.yaml"
        print("=== interview transcript ===")
        print(stdout)
        if stderr.strip():
            print("=== stderr ===")
            print(stderr)

        print(f"exit code: {code}")
        print(f"answers consumed: {prompter._index} / {len(answers)}")
        print("")
        print(f"one-token probes: {len(seam.one_token_calls)}")
        for alias, _ in seam.one_token_calls:
            print(f"  - {alias}")
        print(f"judge canary probes: {seam.canary_calls}")
        print("")

        print("=== personas.yaml diff against shipped example ===")
        example_lines = config_module.shipped_registry_text().splitlines()
        written_lines = personas_path.read_text(encoding="utf-8").splitlines()
        # Simple line-by-line diff for human review.
        import difflib

        diff = difflib.unified_diff(
            example_lines,
            written_lines,
            fromfile="personas.example.yaml",
            tofile="personas.yaml",
            lineterm="",
        )
        for line in diff:
            print(line)

        print("")
        print("=== written personas.yaml (head) ===")
        for line in written_lines[:20]:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
