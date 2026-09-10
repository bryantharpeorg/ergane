"""Executable examples in the gateway guide, without provider or account access."""

from pathlib import Path
import re
import shlex
import tomllib
from types import SimpleNamespace

from factory.config import load_personas
from factory.workgraph.adapter import CODEX_GATEWAY_PROVIDER, _seed_codex_config


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/codex-gateway-setup.md"


def _blocks(language: str) -> list[str]:
    return re.findall(
        rf"^```{language}\n(.*?)^```", GUIDE.read_text(), re.MULTILINE | re.DOTALL
    )


def test_builder_example_loads_as_a_gateway_codex_persona(tmp_path: Path) -> None:
    examples = _blocks("yaml")
    assert len(examples) == 1
    registry = tmp_path / "personas.yaml"
    registry.write_text(examples[0])
    persona = load_personas(registry)["implementer"]
    assert persona.agent == "codex"
    assert persona.route == "gateway"
    assert persona.needs_virtual_key
    assert persona.needs_worktree
    assert persona.model


def test_operator_example_uses_the_api_url_but_not_a_builder_or_master_key(
    tmp_path: Path,
) -> None:
    examples = [tomllib.loads(block) for block in _blocks("toml")]
    assert len(examples) == 2
    assert examples[0]["web_search"] == "disabled"
    provider = examples[1]["model_providers"]["ergane_gateway"]
    assert set(provider) == {"name", "base_url", "env_key", "wire_api"}
    assert provider["base_url"].endswith("/v1")
    assert re.fullmatch(r"[A-Z][A-Z0-9_]+", provider["env_key"])

    # Exercise the actual builder seeder: its input is a proxy root, whereas
    # the operator's native Codex config already includes the API prefix.
    seeded = tmp_path / "builder-config"
    _seed_codex_config(
        seeded, SimpleNamespace(proxy_url=provider["base_url"].removesuffix("/v1"))
    )
    builder = tomllib.loads((seeded / "config.toml").read_text())["model_providers"][
        CODEX_GATEWAY_PROVIDER
    ]
    assert provider["base_url"] == builder["base_url"]
    assert provider["wire_api"] == builder["wire_api"]
    assert provider["env_key"] not in {
        builder["env_key"], "LITELLM_MASTER_KEY", "ERGANE_LLM_MASTER_KEY"
    }


def test_operator_command_selects_the_documented_provider_without_a_bypass() -> None:
    examples = _blocks("bash")
    assert len(examples) == 1
    command = shlex.split(examples[0])
    assert command[0] == "codex"
    overrides = {}
    for index, word in enumerate(command):
        if word == "-c":
            overrides.update(tomllib.loads(command[index + 1]))
    assert overrides["model_provider"] == "ergane_gateway"
    assert overrides["web_search"] == "disabled"
    assert command[command.index("--model") + 1]
    assert not any("bypass" in argument or argument == "--yolo" for argument in command)


def test_refreshed_setup_links_resolve_to_repository_documents() -> None:
    documents = (
        "docs/getting-started.md",
        "docs/codex-gateway-setup.md",
        "docs/cli/README.md",
        "docs/cli/build.md",
        "docs/cli/install.md",
        "docs/cli/worker.md",
    )
    checked = []
    for document in documents:
        path = ROOT / document
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            destination = (path.parent / target.split("#", 1)[0]).resolve()
            assert destination.is_relative_to(ROOT), (document, target)
            assert destination.is_file(), (document, target)
            checked.append((document, target))
    assert checked
