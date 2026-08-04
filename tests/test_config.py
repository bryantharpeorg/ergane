"""Persona registry loading and validation.

Covers data-model.md § Persona and research R8: the shipped `personas.yaml`
parses, the verifier persona is keyless, `write_scope` is a closed enum, and the
agent/model consistency rules are enforced.

Written before `factory/config.py` exists (T006 precedes T009): until the loader
lands, every test here fails at import.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

from factory.config import ConfigError, Persona, WriteScope, load_personas

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"

EXPECTED_PERSONAS = {
    "architect",
    "implementer",
    "verifier",
    "judge",
    "debugger",
    "researcher",
}

# Fields removed by D-021; budget enforcement returns with spec 004.
DEFERRED_FIELDS = ("budget_usd", "breach_policy")


def _entry(**overrides: object) -> dict[str, object]:
    """A minimal valid LLM-persona entry, overridable per test."""
    entry: dict[str, object] = {
        "agent": "claude-code",
        "model": "anthropic/CHANGEME",
        "fallback": None,
        "skills": [],
        "write_scope": "worktree",
        "needs_worktree": True,
    }
    entry.update(overrides)
    return entry


def _write_registry(tmp_path: Path, personas: dict[str, object]) -> Path:
    path = tmp_path / "personas.yaml"
    path.write_text(yaml.safe_dump(personas), encoding="utf-8")
    return path


# --- shipped registry ------------------------------------------------------


def test_shipped_registry_has_six_personas() -> None:
    registry = load_personas(SHIPPED_REGISTRY)

    assert set(registry) == EXPECTED_PERSONAS
    assert all(isinstance(persona, Persona) for persona in registry.values())
    assert all(name == persona.name for name, persona in registry.items())


def test_load_personas_defaults_to_shipped_registry() -> None:
    assert set(load_personas()) == EXPECTED_PERSONAS


def test_verifier_is_deterministic_and_keyless() -> None:
    verifier = load_personas(SHIPPED_REGISTRY)["verifier"]

    assert verifier.agent == "none"
    assert verifier.model is None
    assert verifier.fallback is None
    assert verifier.is_llm is False


def test_llm_personas_resolve_a_model() -> None:
    registry = load_personas(SHIPPED_REGISTRY)

    llm_personas = [p for p in registry.values() if p.name != "verifier"]
    assert llm_personas, "shipped registry should contain LLM personas"
    for persona in llm_personas:
        assert persona.is_llm is True
        assert persona.agent != "none"
        assert isinstance(persona.model, str) and persona.model


def test_shipped_write_scopes_are_enum_members() -> None:
    registry = load_personas(SHIPPED_REGISTRY)

    for persona in registry.values():
        assert isinstance(persona.write_scope, WriteScope)
    assert {s.value for s in WriteScope} == {"worktree", "docs", "read"}
    assert registry["implementer"].write_scope is WriteScope.WORKTREE
    assert registry["architect"].write_scope is WriteScope.DOCS
    assert registry["verifier"].write_scope is WriteScope.READ


def test_skills_are_an_immutable_tuple() -> None:
    registry = load_personas(SHIPPED_REGISTRY)

    assert registry["verifier"].skills == ()
    assert isinstance(registry["implementer"].skills, tuple)
    assert all(isinstance(skill, str) for skill in registry["implementer"].skills)


def test_persona_is_frozen() -> None:
    persona = load_personas(SHIPPED_REGISTRY)["implementer"]

    with pytest.raises(dataclasses.FrozenInstanceError):
        persona.model = "anthropic/other"  # type: ignore[misc]


def test_persona_carries_no_deferred_budget_fields() -> None:
    persona = load_personas(SHIPPED_REGISTRY)["implementer"]

    for field in DEFERRED_FIELDS:
        assert not hasattr(persona, field), f"{field} is deferred to spec 004 (D-021)"


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("missing", ["agent", "write_scope", "needs_worktree"])
def test_missing_required_field_is_rejected(tmp_path: Path, missing: str) -> None:
    entry = _entry()
    del entry[missing]

    with pytest.raises(ConfigError) as excinfo:
        load_personas(_write_registry(tmp_path, {"implementer": entry}))

    assert missing in str(excinfo.value)
    assert "implementer" in str(excinfo.value)


def test_optional_fields_may_be_omitted(tmp_path: Path) -> None:
    entry = _entry()
    del entry["fallback"]
    del entry["skills"]

    persona = load_personas(_write_registry(tmp_path, {"implementer": entry}))["implementer"]

    assert persona.fallback is None
    assert persona.skills == ()


def test_unknown_write_scope_is_rejected(tmp_path: Path) -> None:
    registry = {"implementer": _entry(write_scope="everything")}

    with pytest.raises(ConfigError) as excinfo:
        load_personas(_write_registry(tmp_path, registry))

    assert "write_scope" in str(excinfo.value)
    assert "everything" in str(excinfo.value)


def test_llm_persona_without_a_model_is_rejected(tmp_path: Path) -> None:
    registry = {"implementer": _entry(model=None)}

    with pytest.raises(ConfigError) as excinfo:
        load_personas(_write_registry(tmp_path, registry))

    assert "model" in str(excinfo.value)


def test_llm_persona_with_model_key_absent_is_rejected(tmp_path: Path) -> None:
    entry = _entry()
    del entry["model"]

    with pytest.raises(ConfigError):
        load_personas(_write_registry(tmp_path, {"implementer": entry}))


def test_deterministic_persona_with_a_model_is_rejected(tmp_path: Path) -> None:
    registry = {
        "verifier": _entry(
            agent="none",
            model="anthropic/CHANGEME",
            write_scope="read",
        )
    }

    with pytest.raises(ConfigError) as excinfo:
        load_personas(_write_registry(tmp_path, registry))

    assert "model" in str(excinfo.value)
    assert "verifier" in str(excinfo.value)


def test_deterministic_persona_with_a_fallback_is_rejected(tmp_path: Path) -> None:
    registry = {
        "verifier": _entry(
            agent="none",
            model=None,
            fallback="local/CHANGEME",
            write_scope="read",
        )
    }

    with pytest.raises(ConfigError) as excinfo:
        load_personas(_write_registry(tmp_path, registry))

    assert "fallback" in str(excinfo.value)
