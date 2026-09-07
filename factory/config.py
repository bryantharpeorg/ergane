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

#: Alias prefixes that mark a registry as the shipped, unconfigured example.
#: `ergane install --verify` uses these to report one actionable condition.
EXAMPLE_ALIAS_PREFIXES = ("example/",)


def shipped_registry_text() -> str:
    """Return the shipped example registry text.

    Reads from package data when available (the wheel layout).  In a development
    checkout the example source file lives at the repo root, so the same text is
    returned from there as a fallback.
    """
    packaged = importlib.resources.files("factory") / REGISTRY_FILENAME
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    # Development checkout fallback: the source file is at the repo root, not yet
    # packaged.  The load path never falls back here; this is only for seeding.
    example_source = Path(__file__).resolve().parents[1] / "personas.example.yaml"
    return example_source.read_text(encoding="utf-8")


def is_example_alias(alias: str) -> bool:
    """Whether an alias is one of the shipped placeholder prefixes."""
    return any(alias.startswith(prefix) for prefix in EXAMPLE_ALIAS_PREFIXES)


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

#: Sentinel `agent` value marking a persona that runs against the operator's
#: subscription rather than the gateway (US2 FR-005). It is still an LLM — it
#: still spends tokens and still runs the same `claude` binary — but it routes
#: through the CLI's own credential instead of the LiteLLM proxy.
SUBSCRIPTION_AGENT = "subscription"

# The route vocabulary (154-US1, FR-001) ---------------------------------------

#: How an attempt authenticates: through the LiteLLM proxy under a
#: model-constrained virtual key.
ROUTE_GATEWAY = "gateway"
#: Through the operator's own CLI credential — still an LLM, no key minted.
ROUTE_SUBSCRIPTION = "subscription"
#: A persona that runs no LLM at all.
ROUTE_DETERMINISTIC = "deterministic"
#: The no-LLM case a legacy `agent: none` entry reads as (spec §4.1 table).
ROUTE_NONE = "none"

#: Every value an explicit `route:` field may declare. Closed by construction:
#: anything outside it is refused at the load that reads it (FR-001).
ROUTE_VALUES = frozenset(
    {ROUTE_GATEWAY, ROUTE_SUBSCRIPTION, ROUTE_DETERMINISTIC, ROUTE_NONE}
)

#: The derivation table (154-US1 FR-002, plan step 3): what a legacy `agent:`
#: value means as the (agent, route) pair. The split's whole point —
#: `claude-code` names a CLI, `subscription` names a credential route, and the
#: legacy value meant both at once.
_AGENT_DERIVATION: dict[str, tuple[str, str]] = {
    "claude-code": ("claude-code", ROUTE_GATEWAY),
    SUBSCRIPTION_AGENT: ("claude-code", ROUTE_SUBSCRIPTION),
    DETERMINISTIC_AGENT: (DETERMINISTIC_AGENT, ROUTE_NONE),
}


def derive_agent_and_route(agent: str) -> tuple[str, str]:
    """The (agent, route) pair a legacy `agent:` value means.

    Pure and total (FR-003): a function of the text passed in, defined for
    every value the field accepts, no clock, no environment, no probe of
    anything outside the registry. The frozen snapshot a running epic holds
    (`workflow._read_registry`) makes this load-bearing — a worker restarted
    mid-epic must re-read an unedited registry into an identical pair.
    """
    return _AGENT_DERIVATION[agent]

_REQUIRED_FIELDS = ("agent", "model", "write_scope", "needs_worktree")
_OPTIONAL_FIELDS = ("fallback", "skills", "timeout", "context_window", "route")


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
    """One registry entry: how to run a node routed to this persona.

    The `skills` field is parsed for validation and backward compatibility, but
    it is reserved and unused (062-US3 FR-009). No adapter invocation consumes
    it, because the factory constructs a per-node, factory-owned HOME at
    dispatch time (`factory/workgraph/adapter.py:339`) and home-scoped agent
    skills are therefore invisible to the node. Project-scoped skills committed
    at ``<repo>/.claude/skills/`` remain visible, because the node's worktree
    carries committed files.
    """

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
    #: How attempts of this persona authenticate — the credential route, which
    #: the CLI (`agent`) no longer names (154-US1). `None` until the loader
    #: derives or reads it; a `Persona` constructed directly carries whatever
    #: the caller supplied, and every predicate below reads this field.
    route: str | None = None

    @property
    def is_llm(self) -> bool:
        """Whether this persona spends tokens. Reads the CLI axis alone
        (FR-006): `none` runs no agent; every other value does, gateway and
        subscription routes alike."""
        return self.agent != DETERMINISTIC_AGENT

    @property
    def routes_through_gateway(self) -> bool:
        """Whether this persona's model aliases must resolve on the gateway and
        whether its attempts should be preflight-checked against the proxy's
        served-alias list. Reads the route axis alone (FR-006): the CLI named
        in `agent` does not decide this."""
        return self.route == ROUTE_GATEWAY

    @property
    def needs_virtual_key(self) -> bool:
        """Whether this persona's attempts need a model-constrained virtual key
        minted at dispatch. Reads the same axis as `routes_through_gateway`
        (FR-006) — only a gateway persona has a key minted; a subscription
        persona authenticates through the operator's own credential (US2
        FR-006)."""
        return self.route == ROUTE_GATEWAY


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

    # 154-US1 (FR-001/FR-002): the route is read when declared and derived
    # when absent. The derivation is a default, never an override (trap 1) —
    # an explicit `route:` wins in every case — and a declared value outside
    # the vocabulary is refused at this load rather than re-routed silently.
    if "route" in entry:
        route = entry["route"]
        if not isinstance(route, str) or route not in ROUTE_VALUES:
            allowed = ", ".join(sorted(ROUTE_VALUES))
            raise fail(
                f"field 'route' must be one of {allowed} when present, "
                f"got {route!r}"
            )
    else:
        agent, route = derive_agent_and_route(agent)

    model = _optional_alias(entry["model"], "model", fail)
    fallback = _optional_alias(entry.get("fallback"), "fallback", fail)
    timeout_s = _optional_timeout(entry.get("timeout"), fail)
    context_window = _optional_context_window(entry.get("context_window"), fail)

    # data-model.md § Persona: model required iff agent runs an LLM.
    # A subscription persona is like a gateway persona here: it runs the agent
    # and needs a model (the CLI-side name), so the model rule applies.
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
        route=route,
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
