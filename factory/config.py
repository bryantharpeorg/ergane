"""The persona registry: the one place a model name is allowed to appear.

Principle VII routes nodes by persona, never by model tier, so `personas.yaml`
is the only binding between "implementer" and whatever alias the operator's
LiteLLM proxy actually serves. Code reads personas; it never names models.

The loader is strict on purpose. A registry is operator-edited config that is
read once, at dispatch, and whose mistakes surface much later as a key issued
against a model that does not exist — so a typo'd field name is an error here
rather than a silent default, and every message names the offending persona.

Two consistency rules come from data-model.md § Persona and are enforced in
both directions: an LLM persona (`agent != "none"`) must resolve a model, and a
deterministic one must carry neither a model nor a fallback. `verifier` is the
shipped deterministic persona — it gets no virtual key, which is exactly why it
must not look like it wants one.

The optional `timeout` field (005, research R8) is the attempt wall-clock
default in seconds, so no timeout is ever hardcoded (FR-010). It follows the
same shape as the model rule: forbidden on a deterministic persona, which has
no attempt to bound. The loader stays lenient about its *absence* — a producing
node whose persona resolves no timeout fails WorkGraph validation at epic
start, before anything dispatches, rather than making the field mandatory for
personas that never run an adapter.

`budget_usd` and `breach_policy` are absent by design (D-021); they return with
spec 004, and until then unknown-field rejection keeps them from creeping back
in as dead config.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

#: The shipped registry, resolved relative to this package rather than the
#: caller's working directory, so activities load the same file from anywhere.
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "personas.yaml"

#: Sentinel `agent` value marking a persona as deterministic (no LLM, no key).
DETERMINISTIC_AGENT = "none"

_REQUIRED_FIELDS = ("agent", "model", "write_scope", "needs_worktree")
_OPTIONAL_FIELDS = ("fallback", "skills", "timeout")


class ConfigError(Exception):
    """A registry that cannot be trusted to route work."""


class WriteScope(str, Enum):
    """What a persona is permitted to write; component 2 derives its
    diff-exemption rule from this, so the set is closed.
    """

    WORKTREE = "worktree"
    DOCS = "docs"
    READ = "read"


@dataclass(frozen=True)
class Persona:
    """One registry entry: how to run a node routed to this persona."""

    name: str
    agent: str
    model: str | None
    fallback: str | None
    skills: tuple[str, ...]
    write_scope: WriteScope
    needs_worktree: bool
    #: Attempt wall-clock bound in seconds; None means the registry resolves
    #: none for this persona (YAML key: `timeout`).
    timeout_s: int | None = None

    @property
    def is_llm(self) -> bool:
        """Whether this persona spends tokens — and so needs a virtual key."""
        return self.agent != DETERMINISTIC_AGENT


def load_personas(path: Path | str | None = None) -> dict[str, Persona]:
    """Parse and validate a persona registry, keyed by persona name.

    Defaults to the shipped `personas.yaml`. Raises `ConfigError` for anything
    that would leave a node unroutable: unreadable or malformed YAML, a missing
    or unknown field, a `write_scope` outside the enum, or a persona whose
    agent and model disagree.
    """
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH

    try:
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read persona registry {registry_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"malformed persona registry {registry_path}: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise ConfigError(
            f"persona registry {registry_path} must be a non-empty mapping of "
            "persona name to persona fields"
        )

    return {name: _build_persona(registry_path, name, entry) for name, entry in raw.items()}


def _build_persona(registry_path: Path, name: object, entry: object) -> Persona:
    if not isinstance(name, str) or not name:
        raise ConfigError(f"{registry_path}: persona names must be non-empty strings, got {name!r}")
    if not isinstance(entry, dict):
        raise ConfigError(f"{registry_path}: persona '{name}' must be a mapping of fields")

    def fail(message: str) -> ConfigError:
        return ConfigError(f"{registry_path}: persona '{name}': {message}")

    for field in _REQUIRED_FIELDS:
        if field not in entry:
            raise fail(f"missing required field '{field}'")

    unknown = set(entry) - set(_REQUIRED_FIELDS) - set(_OPTIONAL_FIELDS)
    if unknown:
        raise fail(f"unknown field(s): {', '.join(sorted(unknown))}")

    agent = entry["agent"]
    if not isinstance(agent, str) or not agent:
        raise fail(f"field 'agent' must be a non-empty string, got {agent!r}")

    model = _optional_alias(entry["model"], "model", fail)
    fallback = _optional_alias(entry.get("fallback"), "fallback", fail)
    timeout_s = _optional_timeout(entry.get("timeout"), fail)

    # data-model.md § Persona: model required iff agent != "none".
    if agent == DETERMINISTIC_AGENT:
        if model is not None:
            raise fail(
                f"field 'model' must be null when agent is "
                f"'{DETERMINISTIC_AGENT}', got {model!r}"
            )
        if fallback is not None:
            raise fail(
                f"field 'fallback' must be null when agent is "
                f"'{DETERMINISTIC_AGENT}', got {fallback!r}"
            )
        # research R8: no agent runs, so there is no attempt to bound.
        if timeout_s is not None:
            raise fail(
                f"field 'timeout' must be null when agent is "
                f"'{DETERMINISTIC_AGENT}', got {timeout_s!r}"
            )
    elif model is None:
        raise fail(f"field 'model' is required when agent is '{agent}'")

    raw_scope = entry["write_scope"]
    try:
        write_scope = WriteScope(raw_scope)
    except ValueError:
        allowed = ", ".join(scope.value for scope in WriteScope)
        raise fail(f"field 'write_scope' must be one of {allowed}, got {raw_scope!r}") from None

    needs_worktree = entry["needs_worktree"]
    if not isinstance(needs_worktree, bool):
        raise fail(f"field 'needs_worktree' must be a boolean, got {needs_worktree!r}")

    return Persona(
        name=name,
        agent=agent,
        model=model,
        fallback=fallback,
        skills=_skills(entry.get("skills"), fail),
        write_scope=write_scope,
        needs_worktree=needs_worktree,
        timeout_s=timeout_s,
    )


def _optional_alias(value: object, field: str, fail) -> str | None:
    """A model alias: a non-empty string, or None meaning "not applicable"."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise fail(f"field '{field}' must be a non-empty string or null, got {value!r}")
    return value


def _optional_timeout(value: object, fail) -> int | None:
    """Seconds, and a real count of them: a bool or a stringified number is a
    typo the loader must not coerce into a wall-clock bound.
    """
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise fail(f"field 'timeout' must be a positive integer of seconds or null, got {value!r}")
    return value


def _skills(value: object, fail) -> tuple[str, ...]:
    """Skills default to empty; a bare string is a mistake, not a one-item list."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise fail(f"field 'skills' must be a list of strings, got {value!r}")
    for skill in value:
        if not isinstance(skill, str) or not skill:
            raise fail(f"field 'skills' must contain non-empty strings, got {skill!r}")
    return tuple(value)
