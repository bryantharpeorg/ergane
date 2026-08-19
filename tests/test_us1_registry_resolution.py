"""Persona registry path precedence (062-US1).

Mirrors the shape already used for control-plane config resolution:
env override wins, then XDG_CONFIG_HOME / HOME-relative config, then
package data via importlib.resources. Every call site reaches the same
resolver, and a present-but-broken override fails loudly rather than
silently falling back.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from factory import config as config_module
from factory.activities import agent_activities, roadmap_activities
from factory.cli.nouns import build, spec as spec_noun
from factory.config import ConfigError, REGISTRY_FILENAME, load_personas
from factory.workgraph import cli as workgraph_cli


REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"

ERGANE_PERSONAS_PATH_ENV = "ERGANE_PERSONAS_PATH"
XDG_CONFIG_HOME_ENV = "XDG_CONFIG_HOME"


@pytest.fixture
def minimal_personas() -> dict[str, object]:
    return {
        "implementer": {
            "agent": "claude-code",
            "model": "anthropic/CHANGEME",
            "fallback": None,
            "skills": [],
            "write_scope": "worktree",
            "needs_worktree": True,
            "timeout": 300,
        }
    }


@pytest.fixture
def tmp_config_home(tmp_path: Path) -> Path:
    """A fake XDG_CONFIG_HOME containing an empty ergane directory."""
    config_home = tmp_path / "config"
    (config_home / "ergane").mkdir(parents=True)
    return config_home


def _write_registry(path: Path, personas: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(personas), encoding="utf-8")


def _resolve_default_registry_path() -> Path:
    """Thin wrapper replicating the public seam tests rebind."""
    return config_module.resolve_default_registry_path()


# --- T001: env override wins when set and readable ---------------------------


def test_env_override_wins(
    tmp_path: Path,
    minimal_personas: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = tmp_path / "override" / "personas.yaml"
    override.parent.mkdir(parents=True)
    _write_registry(override, minimal_personas)

    monkeypatch.delenv(XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv(ERGANE_PERSONAS_PATH_ENV, str(override))

    resolved = _resolve_default_registry_path()

    assert resolved == override
    assert set(load_personas()) == {"implementer"}


# --- T002: ~/.config/ergane/personas.yaml wins over package data -------------


def test_xdg_config_home_wins_when_env_override_missing(
    tmp_path: Path,
    tmp_config_home: Path,
    minimal_personas: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xdg_registry = tmp_config_home / "ergane" / "personas.yaml"
    _write_registry(xdg_registry, minimal_personas)

    monkeypatch.delenv(ERGANE_PERSONAS_PATH_ENV, raising=False)
    monkeypatch.setenv(XDG_CONFIG_HOME_ENV, str(tmp_config_home))

    resolved = _resolve_default_registry_path()

    assert resolved == xdg_registry
    assert set(load_personas()) == {"implementer"}


# --- T003: package data resolves when neither env nor XDG present ----------


def test_package_data_resolves_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ERGANE_PERSONAS_PATH_ENV, raising=False)
    monkeypatch.delenv(XDG_CONFIG_HOME_ENV, raising=False)

    resolved = _resolve_default_registry_path()

    assert resolved.is_file()
    assert "personas.yaml" in resolved.name
    assert resolved == SHIPPED_REGISTRY
    assert set(load_personas()) == EXPECTED_SHIPPED_PERSONAS


# --- T004: XDG_CONFIG_HOME honoured rather than hardcoded ~/.config ---------


def test_xdg_config_home_honoured_not_hardcoded(
    tmp_path: Path,
    tmp_config_home: Path,
    minimal_personas: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xdg_registry = tmp_config_home / "ergane" / "personas.yaml"
    _write_registry(xdg_registry, minimal_personas)

    home_config = tmp_path / "home" / ".config" / "ergane" / "personas.yaml"
    home_config.parent.mkdir(parents=True)
    _write_registry(home_config, {"different": minimal_personas["implementer"]})

    monkeypatch.delenv(ERGANE_PERSONAS_PATH_ENV, raising=False)
    monkeypatch.setenv(XDG_CONFIG_HOME_ENV, str(tmp_config_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    resolved = _resolve_default_registry_path()

    assert resolved == xdg_registry


# --- T005: every named call site resolves the override ----------------------


def _call_site_load_function(site_name: str):
    return {
        "roadmap_activities": roadmap_activities._preflight_registry,
        "workgraph_cli": workgraph_cli._preflight_registry,
        "build_cli": build._preflight_registry,
        "agent_activities_resolve_graph": agent_activities.resolve_graph,
        "agent_activities_resolve_persona": agent_activities.resolve_persona,
        "spec_validate": spec_noun._check_personas,
    }[site_name]


@pytest.mark.parametrize(
    "site_name",
    [
        "roadmap_activities",
        "workgraph_cli",
        "build_cli",
        "agent_activities_resolve_graph",
        "agent_activities_resolve_persona",
        "spec_validate",
    ],
)
def test_env_override_changes_resolved_registry_at_call_sites(
    tmp_path: Path,
    minimal_personas: dict[str, object],
    site_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = tmp_path / "override" / "personas.yaml"
    override.parent.mkdir(parents=True)
    # Include a persona name that exists only in the override so that
    # registry-returning call sites can prove the override was read, not
    # the shipped seven-persona registry.
    override_personas = {**minimal_personas, "override_only": minimal_personas["implementer"]}
    _write_registry(override, override_personas)

    # Make sure no XDG/HOME layer masks the env override.
    monkeypatch.delenv(XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv(ERGANE_PERSONAS_PATH_ENV, str(override))

    fn = _call_site_load_function(site_name)

    # agent_activities entry points are async activities expecting typed args.
    if site_name == "agent_activities_resolve_graph":
        from factory.workgraph.models import WorkGraph, WorkNode

        async def run() -> list:
            graph = WorkGraph(
                epic_id="e",
                feature="e",
                specs_root=str(tmp_path / "specs"),
                target_repo=str(tmp_path / "repo"),
                nodes=[
                    WorkNode(
                        id="us1",
                        story_key="US1",
                        persona="implementer",
                        spec_ref="e:US1",
                        requirement_keys=["US1"],
                        depends_on=[],
                        depends_on_merged=[],
                        timeout_override_s=None,
                    )
                ],
            )
            return await fn(graph)

        import asyncio

        result = asyncio.run(run())
        assert result[0].model_alias == "anthropic/CHANGEME"
        return

    if site_name == "agent_activities_resolve_persona":
        from factory.activities.agent_activities import ResolvePersonaInput

        async def run() -> ResolvedPersona:
            return await fn(ResolvePersonaInput(persona="implementer"))

        import asyncio

        result = asyncio.run(run())
        assert result.model_alias == "anthropic/CHANGEME"
        return

    if site_name == "spec_validate":
        from factory.workgraph.models import WorkGraph, WorkNode

        graph = WorkGraph(
            epic_id="e",
            feature="e",
            specs_root="",
            target_repo="",
            nodes=[
                WorkNode(
                    id="us1",
                    story_key="US1",
                    persona="override_only",
                    spec_ref="e:US1",
                    requirement_keys=["US1"],
                    depends_on=[],
                    depends_on_merged=[],
                    timeout_override_s=None,
                )
            ],
        )
        findings: list = []
        fn(graph, findings)
        assert findings == []
        return

    result = fn()
    assert isinstance(result, dict)
    assert set(result) == set(override_personas)


# --- T006: present-but-broken override fails naming path and fault -----------


def test_present_broken_override_fails_loudly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = tmp_path / "override" / "personas.yaml"
    override.parent.mkdir(parents=True)
    override.write_text("not: [valid yaml", encoding="utf-8")

    monkeypatch.delenv(XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv(ERGANE_PERSONAS_PATH_ENV, str(override))

    with pytest.raises(ConfigError) as excinfo:
        load_personas()

    message = str(excinfo.value)
    assert str(override) in message
    assert "malformed" in message.lower() or "cannot read" in message.lower()


def test_present_unreadable_override_fails_loudly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = tmp_path / "override" / "personas.yaml"
    override.parent.mkdir(parents=True)
    _write_registry(override, {"implementer": {"agent": "claude-code", "model": "m"}})
    # Remove read permission to trigger an OSError.
    override.chmod(0o000)

    monkeypatch.delenv(XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv(ERGANE_PERSONAS_PATH_ENV, str(override))

    try:
        with pytest.raises(ConfigError) as excinfo:
            load_personas()

        message = str(excinfo.value)
        assert str(override) in message
        assert "cannot read" in message.lower() or "permission" in message.lower()
    finally:
        override.chmod(0o644)


# --- T007: override pointing at directory is a distinct fault ----------------


def test_override_directory_named_distinctly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override_dir = tmp_path / "override_dir"
    override_dir.mkdir(parents=True)

    monkeypatch.delenv(XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv(ERGANE_PERSONAS_PATH_ENV, str(override_dir))

    with pytest.raises(ConfigError) as excinfo:
        load_personas()

    message = str(excinfo.value)
    assert str(override_dir) in message
    assert "directory" in message.lower() or "is a directory" in message.lower()


EXPECTED_SHIPPED_PERSONAS = {
    "architect",
    "implementer",
    "verifier",
    "judge",
    "debugger",
    "researcher",
    "closer",
}
