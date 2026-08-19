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

import importlib.resources
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

from factory.env import resolve_env_path

#: The registry's basename, identical in both layouts below.
REGISTRY_FILENAME = "personas.yaml"

#: Default relative path under XDG_CONFIG_HOME / HOME (FR-001).
DEFAULT_REGISTRY_REL = Path("ergane") / REGISTRY_FILENAME

#: Modern env variable name for the persona registry path.
ERGANE_PERSONAS_PATH_ENV = "ERGANE_PERSONAS_PATH"

#: Legacy env variable name honoured during the 062 rename.
FACTORY_PERSONAS_PATH_ENV = "FACTORY_PERSONAS_PATH"


def _resolve_default_registry_path() -> Path:
    """Where the shipped registry lives, in an install and in a checkout.

    Resolved as **package data** first. An installed wheel carries the registry
    inside the package — `pyproject.toml` force-includes the repo-root file to
    `factory/personas.yaml` at build time — so `importlib.resources` finds it
    wherever the package was unpacked, with no repo above it and no assumption
    about the caller's working directory.

    The walk to `parents[1]` is the *development checkout* and only that: there
    it is the repo root, holding the operator-editable file that the build
    copies. In an installed wheel it is `site-packages/`, where nothing has ever
    put a file — which is precisely the bug this ordering fixes. Every install
    from a wheel failed its own `ergane install` verification with
    `cannot read persona registry .../site-packages/personas.yaml`, because the
    walk was the only mechanism and packaging shipped no registry to walk to.
    """
    packaged = importlib.resources.files("factory") / REGISTRY_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    return Path(__file__).resolve().parents[1] / REGISTRY_FILENAME


def _xdg_config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def resolve_default_registry_path() -> Path:
    """Return the persona registry path: env override, then XDG/HOME, then package.

    Mirrors ``factory/controlplane/config.py:resolve_config_path`` (FR-001):
    ``ERGANE_PERSONAS_PATH`` wins, the legacy ``FACTORY_PERSONAS_PATH`` is
    honored with one deprecation warning per process, and the default falls back
    to ``~/.config/ergane/personas.yaml`` via ``XDG_CONFIG_HOME`` when set.

    The final branch is the unchanged package-data resolver, so an installed
    wheel with no operator config still resolves the shipped registry (FR-004,
    trap 2). A present override that is unreadable or unparseable is the loader's
    job to surface; this resolver does not silently fall back (FR-003, trap 1).
    """
    default = _xdg_config_home() / DEFAULT_REGISTRY_REL
    env_path = resolve_env_path(
        ERGANE_PERSONAS_PATH_ENV,
        FACTORY_PERSONAS_PATH_ENV,
        default,
    )
    if env_path != default:
        return env_path
    if default.is_file():
        return default
    return _resolve_default_registry_path()


#: The shipped registry. A module-level constant because it is also the seam
#: tests rebind (`monkeypatch.setattr(factory.config, "DEFAULT_REGISTRY_PATH", …)`)
#: to point a whole activity at a fixture registry.
DEFAULT_REGISTRY_PATH = _resolve_default_registry_path()

#: Sentinel `agent` value marking a persona as deterministic (no LLM, no key).
DETERMINISTIC_AGENT = "none"

_REQUIRED_FIELDS = ("agent", "model", "write_scope", "needs_worktree")
_OPTIONAL_FIELDS = ("fallback", "skills", "timeout", "context_window")


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
    #: Model context-window tokens, declared by the operator per persona. None
    #: means undeclared; the adapter emits no variable (FR-010).
    context_window: int | None = None

    @property
    def is_llm(self) -> bool:
        """Whether this persona spends tokens — and so needs a virtual key."""
        return self.agent != DETERMINISTIC_AGENT


def load_personas(path: Path | str | None = None) -> dict[str, Persona]:
    """Parse and validate a persona registry, keyed by persona name.

    Defaults to the resolved default registry path (env override, then
    ``XDG_CONFIG_HOME`` / ``HOME``-relative, then package data). Raises
    `ConfigError` for anything that would leave a node unroutable: unreadable
    or malformed YAML, a missing or unknown field, a `write_scope` outside the
    enum, or a persona whose agent and model disagree.
    """
    registry_path = Path(path) if path is not None else resolve_default_registry_path()

    if registry_path.is_dir():
        raise ConfigError(
            f"persona registry path is a directory, expected a file: {registry_path}"
        )

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
    context_window = _optional_context_window(entry.get("context_window"), fail)

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
        # US4: no agent runs, so there is no environment to put the window in.
        if context_window is not None:
            raise fail(
                f"field 'context_window' must be null when agent is "
                f"'{DETERMINISTIC_AGENT}', got {context_window!r}"
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
        context_window=context_window,
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


def _optional_context_window(value: object, fail) -> int | None:
    """Tokens, and a real count of them: same validation shape as timeout.

    A declared window is optional and per-persona; None means the adapter emits
    no `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and the factory keeps today's behavior.
    """
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise fail(f"field 'context_window' must be a positive integer or null, got {value!r}")
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
