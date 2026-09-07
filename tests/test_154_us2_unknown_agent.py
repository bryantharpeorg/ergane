"""154-US2: a registry naming an agent the factory cannot run is refused at load.

The adapter seam already refuses an unknown name — `adapter_for` raises
`AdapterError` naming it and listing the known agents — but the guard is
unreachable from production: the one dispatch call site passes a constant, so a
persona declaring `agent: codex` minted a key and dispatched Claude Code anyway.
That was the defect. This story moves the refusal to the load that reads the
registry: `load_personas` validates the (derived) `agent` against the adapter
registry, and a typo fails loudly there.

Written before the implementation (constitution II): on the tree as received,
the unknown-agent tests fail — today's load mints the key and dispatches the
wrong CLI, and no `ConfigError` ever names `codex`.

The scenarios, entry for entry:

- US2-S1: `agent: codex` raises `ConfigError` naming `codex` and listing the
  agents the factory can run.
- US2-S2 (control): `agent: claude-code` loads against the one-adapter
  registry — the refusal is of the unknown, not of the field.
- US2-S3: the error text carries the full known-agent list, so an operator
  learns every valid value in one message rather than one typo at a time.
- US2-S4: `agent: none` is NOT refused — a deterministic persona runs no CLI
  and must stay loadable with no adapter registered for it.
- FR-004, derived-axis: a legacy `agent: subscription` names no adapter either;
  it loads because the derivation reads it as Claude Code. The refusal is of
  the unknown, never of a sentinel the field no longer names.
- Trap 6: the known-agent list is read from `_ADAPTERS`, not copied. A second
  adapter registered in the registry is admitted by the load the moment it is
  registered — the mutation half of the control-and-mutation pair.
"""

from pathlib import Path
from typing import Any

import pytest

from factory.config import ConfigError, load_personas

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_registry(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "personas.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _entry(agent: str, **overrides: Any) -> str:
    """A minimal valid persona entry naming `agent`, as YAML text."""
    model = "null" if agent == "none" else f"model-for-{agent}"
    fields = {
        "agent": agent,
        "model": model,
        "fallback": "null",
        "skills": "[]",
        "write_scope": "worktree",
        "needs_worktree": "true",
    }
    fields.update(overrides)
    body = "\n".join(f"  {key}: {value}" for key, value in fields.items())
    return f"implementer:\n{body}\n"


# --- T008 (US2-S1, US2-S3, US2-S4; FR-004, trap 6) ----------------------------


def test_an_unknown_agent_is_refused_at_load_naming_the_value(tmp_path: Path) -> None:
    """US2-S1: `agent: codex` with no registered adapter of that name raises
    `ConfigError` naming `codex` — the load that reads the registry refuses,
    rather than minting a key and dispatching Claude Code."""
    path = _write_registry(tmp_path, _entry("codex"))

    with pytest.raises(ConfigError) as excinfo:
        load_personas(path)

    assert "codex" in str(excinfo.value)


def test_the_refusal_lists_the_known_agents_in_one_message(tmp_path: Path) -> None:
    """US2-S3: the error text is the known-agent list. One message names every
    value the factory can run, so an operator reading it never discovers them
    one typo at a time."""
    path = _write_registry(tmp_path, _entry("codex"))

    with pytest.raises(ConfigError) as excinfo:
        load_personas(path)

    message = str(excinfo.value)
    assert "claude-code" in message


def test_the_deterministic_agent_is_not_refused(tmp_path: Path) -> None:
    """US2-S4: `agent: none` loads with no adapter registered for it — a
    deterministic persona runs no CLI, and the refusal is of the unknown
    adapter, never of the sentinel that means "no adapter at all"."""
    path = _write_registry(tmp_path, _entry("none"))

    persona = load_personas(path)["implementer"]

    assert persona.agent == "none"


def test_a_legacy_subscription_agent_loads_through_the_derivation(tmp_path: Path) -> None:
    """FR-004, derived axis: `agent: subscription` names no adapter — the
    derivation reads it as Claude Code on the subscription route, and the load
    admits it. The refusal validates the derived agent, not the raw text."""
    path = _write_registry(tmp_path, _entry("subscription"))

    persona = load_personas(path)["implementer"]

    assert persona.agent == "claude-code"


def test_the_known_agent_list_is_read_from_the_adapter_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trap 6 / mutation half: the known-agent list is `_ADAPTERS`, read at
    load. Registering a second adapter in the registry admits an entry naming
    it the moment the registry holds it — a second list in `config.py` would
    still refuse, and that disagreement is the defect this test pins shut."""
    from factory.workgraph import adapter as adapter_module

    class CodexAdapter:
        name = "codex"

    monkeypatch.setitem(adapter_module._ADAPTERS, "codex", CodexAdapter)

    path = _write_registry(tmp_path, _entry("codex"))

    persona = load_personas(path)["implementer"]

    assert persona.agent == "codex"


# --- T009 (US2-S2, FR-004): the control ---------------------------------------


def test_a_registered_agent_loads_with_the_one_entry_registry(tmp_path: Path) -> None:
    """US2-S2: `agent: claude-code` loads against the adapter registry holding
    its one entry — the refusal is of the unknown, not of the field."""
    path = _write_registry(tmp_path, _entry("claude-code"))

    persona = load_personas(path)["implementer"]

    assert persona.agent == "claude-code"