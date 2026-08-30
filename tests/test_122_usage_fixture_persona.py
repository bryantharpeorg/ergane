"""The usage fixtures name their own persona, not the operator's builder (122-US2).

`tests/test_usage_activities.py` is about key leasing: the proxy call, the alias,
the ledger row. It is not about who the default builder is. But its fixture
persona used to be the literal string `implementer`, and `issue_attempt_key`
resolves an unspecified `agent` from the persona registry — so the moment the
operator pointed `implementer` at a subscription route, twenty-four of those
tests started leasing a key the factory deliberately does not mint, and the
repo's one gate (`test: "uv run pytest -q"`) went red for every node of every
epic. That is `ci/test-suite-pins-the-operator-dial`.

The two subprocess tests below are the ones that could not be written in-process:
the defect is *which registry the usage tests resolve*, so proving it gone means
running that module under a registry the operator might plausibly ship. They
build one in `tmp_path`, point `ERGANE_PERSONAS_PATH` at it, and require green on
both routes — the subscription registry because it is the case that failed, and
the gateway registry as the control, because a fix that passed only under the
new shape would have moved the pin rather than removed it.

Neither registry names a real vendor or alias. A test asserting that the suite
does not choose the operator's builder may not choose one itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from factory.config import ERGANE_PERSONAS_PATH_ENV, SUBSCRIPTION_AGENT, load_personas
from tests import test_usage_activities as usage

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"
USAGE_TESTS = "tests/test_usage_activities.py"

#: The marker the usage module's own placeholders carry (`MODELS`). A fixture
#: constant that stands in for a value the operator owns wears it, so the
#: substitution is legible at the point of use.
PLACEHOLDER = "CHANGEME"

#: The route that works today: an implementer behind the gateway, holding a
#: slash-shaped alias and minting a virtual key.
GATEWAY_IMPLEMENTER = {
    "agent": "claude-code",
    "model": f"gateway/{PLACEHOLDER}",
    "fallback": f"local/{PLACEHOLDER}",
}

#: The route the operator asked for on 2026-08-29 and the suite refused: no
#: gateway key, and a bare CLI model name with no slash in it.
SUBSCRIPTION_IMPLEMENTER = {
    "agent": SUBSCRIPTION_AGENT,
    "model": PLACEHOLDER,
    "fallback": None,
}


def _registry_with_implementer(tmp_path: Path, **fields: Any) -> Path:
    """The shipped registry with `implementer` re-routed, written to `tmp_path`.

    Round-tripped from the real file rather than hand-built, so the registry the
    subprocess loads differs from the operator's in exactly the keys under test
    and passes the same validation his does.
    """
    raw = yaml.safe_load(SHIPPED_REGISTRY.read_text(encoding="utf-8"))
    raw["implementer"] = {**raw["implementer"], **fields}
    path = tmp_path / "personas.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def _run_usage_tests(registry: Path) -> subprocess.CompletedProcess[str]:
    """Run the usage module in a child process against `registry`.

    A child, because `factory.config` resolves the registry path per call from
    the environment: the honest way to ask "would this suite be green on that
    operator's host" is to be that host for one process.
    """
    env = dict(os.environ)
    env[ERGANE_PERSONAS_PATH_ENV] = str(registry)
    return subprocess.run(
        [sys.executable, "-m", "pytest", USAGE_TESTS, "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# T006 / US2-S3: the case that fails today
# ---------------------------------------------------------------------------


def test_the_usage_tests_pass_with_a_subscription_implementer(tmp_path: Path) -> None:
    registry = _registry_with_implementer(tmp_path, **SUBSCRIPTION_IMPLEMENTER)

    # The registry really is the shape that broke: subscription-routed, and a
    # model alias with no slash in it. Asserted before the run so a registry
    # that silently failed to mutate cannot pass as a demonstration.
    implementer = load_personas(registry)["implementer"]
    assert implementer.agent == SUBSCRIPTION_AGENT
    assert implementer.needs_virtual_key is False
    assert "/" not in (implementer.model or "")

    result = _run_usage_tests(registry)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# T007 / US2-S2: the control
# ---------------------------------------------------------------------------


def test_the_usage_tests_pass_with_a_gateway_implementer(tmp_path: Path) -> None:
    """The status quo keeps working.

    Without this, "green under a subscription implementer" would be satisfiable
    by a fixture that leases no key at all — which would delete the coverage
    instead of decoupling it.
    """
    registry = _registry_with_implementer(tmp_path, **GATEWAY_IMPLEMENTER)

    implementer = load_personas(registry)["implementer"]
    assert implementer.needs_virtual_key is True

    result = _run_usage_tests(registry)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# T008 / US2-S1: the persona is the tests' own
# ---------------------------------------------------------------------------


def test_the_usage_fixtures_lease_against_a_persona_the_tests_own() -> None:
    """No name in that module's leasing fixtures is read from the registry.

    Naming another *real* persona would only move the pin: the next operator to
    re-route the architect would break the usage tests instead. The fixture
    needs a persona nobody ships, in the same placeholder register as its own
    `MODELS`.
    """
    shipped = load_personas(SHIPPED_REGISTRY)

    for constant, value in (
        ("PERSONA", usage.PERSONA),
        ("SUBSCRIPTION_PERSONA", usage.SUBSCRIPTION_PERSONA),
    ):
        assert value not in shipped, (
            f"{constant} = {value!r} is a persona the operator's registry "
            "defines, so re-routing it decides whether these tests pass"
        )
        assert PLACEHOLDER in value, (
            f"{constant} = {value!r} must wear the same placeholder marker as "
            f"MODELS ({usage.MODELS!r}), so it reads as a value the tests own"
        )

    assert all(PLACEHOLDER in alias for alias in usage.MODELS)
    # The alias is built from the constant, so the whole module follows it.
    assert usage.ALIAS.endswith(f":{usage.PERSONA}")


# ---------------------------------------------------------------------------
# T009 / US2-S4, FR-005: the no-key coverage survived the decoupling
# ---------------------------------------------------------------------------


def test_the_suite_still_covers_a_subscription_persona_minting_no_key() -> None:
    """The pin was accidentally exercising real behaviour; it is now deliberate.

    While `PERSONA` was the operator's builder, pointing that builder at a
    subscription route was the only thing in the suite that drove
    `issue_attempt_key`'s no-key path. Decoupling from the dial must not take
    that path's coverage with it, so the module now owns a subscription persona
    of its own — and this asserts it is still there, whatever the operator's
    registry says.
    """
    module = Path(usage.__file__).read_text(encoding="utf-8")

    assert "SUBSCRIPTION_PERSONA" in module
    assert usage.SUBSCRIPTION_PERSONA not in load_personas(SHIPPED_REGISTRY)

    covering = [
        name
        for name in dir(usage)
        if name.startswith("test_") and "subscription" in name and "key" in name
    ]
    assert covering, (
        "no test in the usage module covers a subscription persona minting no "
        "virtual key; that coverage is FR-005 and must not evaporate"
    )


@pytest.mark.parametrize("route", ["gateway", "subscription"])
def test_the_registries_this_file_builds_name_no_real_vendor(
    tmp_path: Path, route: str
) -> None:
    """The fix may not be demonstrated with a vendor choice of its own.

    Both registries above stand in for a route, not for a product. If a later
    edit reaches for a real alias to make one of them "realistic", it has
    re-introduced the defect inside its own regression test.
    """
    fields = GATEWAY_IMPLEMENTER if route == "gateway" else SUBSCRIPTION_IMPLEMENTER
    implementer = load_personas(_registry_with_implementer(tmp_path, **fields))[
        "implementer"
    ]

    for alias in (implementer.model, implementer.fallback):
        assert alias is None or PLACEHOLDER in alias, (
            f"{alias!r} names something the operator chose; use a "
            f"{PLACEHOLDER} placeholder"
        )
