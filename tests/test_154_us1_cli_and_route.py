"""154-US1: a persona names its CLI and its route separately.

The registry says which CLI runs and how it is authenticated as two
independent facts. Written before the implementation (constitution II): on the
tree as received every test here fails — a `route:` key is refused as an
unknown field, and no `route` attribute exists to read.

The derivation table (spec FR-002, plan "What to build" step 3) is the whole
contract:

    claude-code   ->  ("claude-code", "gateway")
    subscription  ->  ("claude-code", "subscription")
    none          ->  ("none", "none")

An explicit `route:` wins over derivation in every case (trap 1: the
derivation is a default, never an override), the derivation is pure and total
(FR-003: same text, same pair, no clock, no environment), and `route_of` reads
the field rather than re-deriving it from the agent name (FR-006, trap 3).
"""

from pathlib import Path

import pytest
import yaml

from factory.config import ConfigError, load_personas
from factory.config import (
    ROUTE_GATEWAY,
    ROUTE_NONE,
    ROUTE_SUBSCRIPTION,
)
from factory.verify.models import UNKNOWN_BUILDER, route_of

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The route each legacy `agent:` value derives, entry for entry (FR-002).
DERIVED_ROUTES = {
    "claude-code": ROUTE_GATEWAY,
    "subscription": ROUTE_SUBSCRIPTION,
    "none": ROUTE_NONE,
}


def _write_registry(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "personas.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- T002 [P] (US1-S2, FR-002, trap 1): the derivation table -----------------


def test_legacy_subscription_agent_derives_the_pair(tmp_path: Path) -> None:
    """US1-S2: `agent: subscription` with no `route:` loads as the pair
    ("claude-code", "subscription") — a legacy value refactored into the new
    pair, not an error."""
    path = _write_registry(
        tmp_path,
        """\
implementer:
  agent: subscription
  model: claude-opus-5
  fallback: null
  write_scope: worktree
  needs_worktree: true
""",
    )

    persona = load_personas(path)["implementer"]

    assert persona.agent == "claude-code"
    assert persona.route == ROUTE_SUBSCRIPTION


def test_the_derivation_table_holds_entry_for_entry(tmp_path: Path) -> None:
    """US1-S2 / FR-002: every legacy `agent:` value derives exactly the pair
    the table names — no more, no less."""
    path = _write_registry(
        tmp_path,
        """\
gateway:
  agent: claude-code
  model: proxy/model
  fallback: null
  write_scope: worktree
  needs_worktree: true
subscription:
  agent: subscription
  model: claude-opus-5
  fallback: null
  write_scope: worktree
  needs_worktree: true
deterministic:
  agent: none
  model: null
  fallback: null
  write_scope: read
  needs_worktree: true
""",
    )

    personas = load_personas(path)

    assert (personas["gateway"].agent, personas["gateway"].route) == (
        "claude-code",
        ROUTE_GATEWAY,
    )
    assert (personas["subscription"].agent, personas["subscription"].route) == (
        "claude-code",
        ROUTE_SUBSCRIPTION,
    )
    assert (personas["deterministic"].agent, personas["deterministic"].route) == (
        "none",
        ROUTE_NONE,
    )


# --- T003 [P] (US1-S4, FR-003): byte-identical load of a route-less manifest


@pytest.mark.parametrize(
    "manifest",
    [
        REPO_ROOT / "personas.example.yaml",
        REPO_ROOT / "container" / "personas.demo.yaml",
        REPO_ROOT / "personas.yaml",
    ],
    ids=["example", "demo", "shipped"],
)
def test_a_shipped_manifest_honors_explicit_routes_and_derives_legacy_routes(
    manifest: Path,
) -> None:
    """US1-S4: legacy example/demo entries retain the table-derived behavior.

    The operator registry may select another supported CLI and declare its
    route explicitly (FR-001/FR-003); that declaration, not a legacy-only CLI
    table, determines its predicates. Keep all three real manifests exercised.
    """
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    personas = load_personas(manifest)

    for name, entry in raw.items():
        persona = personas[name]
        expected_route = (
            entry["route"] if "route" in entry else DERIVED_ROUTES[entry["agent"]]
        )

        # The explicit declaration or legacy derivation, entry for entry.
        assert persona.route == expected_route, name
        # The agent half normalizes only where the table says so: a legacy
        # `subscription` names Claude Code either way.
        expected_agent = "claude-code" if entry["agent"] == "subscription" else entry["agent"]
        assert persona.agent == expected_agent, name

        # The behavior, byte for byte: single-axis reads that answer today's
        # answers for every persona these manifests ship.
        assert persona.is_llm == (entry["agent"] != "none"), name
        assert persona.routes_through_gateway == (expected_route == ROUTE_GATEWAY), name
        assert persona.needs_virtual_key == (expected_route == ROUTE_GATEWAY), name


# --- T004 [P] (US1-S1, US1-S3, US1-S5; FR-001, FR-002, trap 1) ---------------


def test_an_explicit_route_parses_and_the_persona_carries_both_fields(
    tmp_path: Path,
) -> None:
    """US1-S1: `agent: claude-code` + `route: gateway` parses, the persona
    carries both fields, and `routes_through_gateway` reads `route` and answers
    true."""
    path = _write_registry(
        tmp_path,
        """\
implementer:
  agent: claude-code
  route: gateway
  model: proxy/model
  fallback: null
  write_scope: worktree
  needs_worktree: true
""",
    )

    persona = load_personas(path)["implementer"]

    assert persona.agent == "claude-code"
    assert persona.route == ROUTE_GATEWAY
    assert persona.routes_through_gateway is True


def test_an_explicit_route_wins_over_derivation_in_every_case(tmp_path: Path) -> None:
    """US1-S3 / trap 1: the derivation is a default, never an override. A
    legacy `agent:` value whose table route differs from the explicit
    `route:` loses, in both directions."""
    path = _write_registry(
        tmp_path,
        """\
promoted:
  agent: subscription
  route: gateway
  model: proxy/model
  fallback: null
  write_scope: worktree
  needs_worktree: true
demoted:
  agent: claude-code
  route: subscription
  model: claude-opus-5
  fallback: null
  write_scope: worktree
  needs_worktree: true
""",
    )

    personas = load_personas(path)

    # The table would derive `subscription` for `agent: subscription`;
    # the explicit `route: gateway` wins.
    assert personas["promoted"].route == ROUTE_GATEWAY
    assert personas["promoted"].routes_through_gateway is True
    assert personas["promoted"].needs_virtual_key is True

    # The old agent-name reading would call this persona gateway-routed
    # (`agent: claude-code`); the field says otherwise, and the field wins.
    assert personas["demoted"].route == ROUTE_SUBSCRIPTION
    assert personas["demoted"].routes_through_gateway is False
    assert personas["demoted"].needs_virtual_key is False


def test_the_derivation_is_pure_same_text_same_pair_twice(tmp_path: Path) -> None:
    """US1-S5 / FR-003: the derivation is a function of the registry text
    alone. A worker restarted mid-epic re-reads the unedited registry into an
    identical pair — two fresh loads of the same text, and of two copies of
    that text at different paths, agree entry for entry."""
    text = """\
implementer:
  agent: subscription
  model: claude-opus-5
  fallback: null
  write_scope: worktree
  needs_worktree: true
verifier:
  agent: none
  model: null
  fallback: null
  write_scope: read
  needs_worktree: true
"""
    first = load_personas(_write_registry(tmp_path / "a", text))
    second = load_personas(_write_registry(tmp_path / "b", text))

    for name in first:
        assert (first[name].agent, first[name].route) == (
            second[name].agent,
            second[name].route,
        ), name


def test_an_explicit_route_outside_the_vocabulary_is_refused(tmp_path: Path) -> None:
    """FR-001: a present `route:` must be one of the routes the factory
    declares. Anything else is refused at the load that reads it, naming the
    value."""
    path = _write_registry(
        tmp_path,
        """\
implementer:
  agent: claude-code
  route: carrier-pigeon
  model: proxy/model
  fallback: null
  write_scope: worktree
  needs_worktree: true
""",
    )

    with pytest.raises(ConfigError, match="carrier-pigeon"):
        load_personas(path)


# --- FR-006 / trap 3: route_of reads the field, it does not derive -----------


def test_route_of_reads_the_route_field_not_the_agent_name(tmp_path: Path) -> None:
    """FR-006 / trap 3: `route_of` reads the `route` field. For a persona whose
    explicit route disagrees with what its agent name would derive, the field
    is what the row records."""
    path = _write_registry(
        tmp_path,
        """\
demoted:
  agent: claude-code
  route: subscription
  model: claude-opus-5
  fallback: null
  write_scope: worktree
  needs_worktree: true
""",
    )

    persona = load_personas(path)["demoted"]

    # The agent name would derive the gateway; the field says subscription,
    # and the field is what route_of reports.
    assert persona.route == ROUTE_SUBSCRIPTION
    assert route_of(persona.route) == ROUTE_SUBSCRIPTION


def test_route_of_still_refuses_an_empty_route() -> None:
    """The one behavior route_of keeps: an attempt nobody recorded a route for
    reads as UNKNOWN_BUILDER, never as the gateway."""
    assert route_of("") == UNKNOWN_BUILDER
