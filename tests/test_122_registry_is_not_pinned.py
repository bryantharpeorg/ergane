"""122-US1: the registry test asserts that the wiring loads, not who wired it.

`tests/test_us2_shipped_registry.py` carried two lines about this repository's
own `personas.yaml`::

    assert registry["implementer"].model
    assert "/" in registry["implementer"].model

The first is the real check — a registry entry that failed to resolve is a
defect the suite must keep catching. The second is a vendor-routing decision
written as a format check: every gateway alias carries a slash and no
subscription model does, so pointing the implementer at `opus-closer` (or at
any other `agent: subscription` persona) turned an operator instruction into
25 red tests. This repository's gate *is* the suite, so a pinned dial does not
merely block a push — it reds every node of every epic until the dial is put
back.

The line this module holds is the spec's own:

> A test may assert that the operator's wiring *resolves*. It may not assert
> what the operator *chose*.

The first three tests drive the surviving shipped-registry check against
synthetic registries — gateway, subscription, unresolvable — because the thing
under test is which registries that check accepts, and the operator's own file
can only ever be one of them. Nothing here edits `personas.yaml`: which model
the implementer names stays the operator's decision.

The fourth is the anti-recurrence guard. This defect class has recurred six
times and every previous fix removed one literal and left the mechanism — 037
un-pinned `context_window` and re-pinned `model` in the same breath, and 121
un-pinned the manifest's version a file away. So the guard reads the suite's
own assertions about the shipped registry and fails if any of them constrains
a vendor or a route, which is what makes the seventh recurrence a red test
here instead of a blocked operator.

Every test answers "what edit would make this fail?" in its docstring, the
convention `tests/test_121_manifest_is_not_a_fixture.py` established for the
same defect class one spec ago.
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest
import yaml

import factory.config as config_module
from tests import test_us2_shipped_registry as shipped

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"

#: The surviving check, held by reference rather than re-implemented: these
#: tests are about *that* assertion's verdict, so a rewrite of it must move
#: them too rather than leave them passing against a copy.
SHIPPED_REGISTRY_CHECK = (
    shipped.test_repo_root_registry_still_resolves_real_wiring_in_checkout
)


# --- the shipped-registry check, driven against registries it could be -------


def _registry_text(**overrides: object) -> str:
    """A one-persona registry naming the implementer, with fields overridden.

    The aliases are the suite's own placeholder register (`example/...`), never
    an alias any operator's proxy serves: a fixture that borrows a real vendor
    name is how the pin this spec removes got written in the first place.
    """
    entry: dict[str, object] = {
        "agent": "claude-code",
        "model": "example-gateway/your-model",
        "fallback": None,
        "skills": ["implement"],
        "write_scope": "worktree",
        "needs_worktree": True,
        "timeout": 3600,
    }
    entry.update(overrides)
    return yaml.safe_dump({"implementer": entry})


def _verdict(
    registry_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> BaseException | None:
    """Run the shipped-registry check against `registry_text`; `None` if it passes.

    The registry is written under the test's own `tmp_path` and both seams that
    name the shipped file — the module constant the check compares against and
    the resolver `load_personas()` consults — are pointed at it. Nothing reads
    or writes the operator's `personas.yaml`, so this test gives the same
    verdict whatever that file says today.
    """
    path = tmp_path / "personas.yaml"
    path.write_text(registry_text, encoding="utf-8")
    monkeypatch.setattr(shipped, "SHIPPED_REGISTRY", path)
    monkeypatch.setattr(config_module, "resolve_default_registry_path", lambda: path)

    try:
        SHIPPED_REGISTRY_CHECK(tmp_path, monkeypatch)
    except (AssertionError, config_module.ConfigError) as failure:
        return failure
    return None


def test_a_subscription_implementer_passes_the_shipped_registry_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S2, FR-001 — the case that fails today, and the whole reason for the spec.

    `agent: subscription` with `model: claude-opus-5` is a legitimate, shipped
    shape: `opus-closer` and `debugger` are both written exactly this way, and
    a subscription model is a name the `claude` CLI accepts rather than a
    LiteLLM alias, so it carries no slash. The operator asked for this wiring on
    2026-08-29, and the suite refused it.

    Mutation: restore `assert "/" in registry["implementer"].model` — or any
    other alias-shape check — and this fails.
    """
    verdict = _verdict(
        _registry_text(agent="subscription", model="claude-opus-5", fallback=None),
        tmp_path,
        monkeypatch,
    )

    assert verdict is None, f"a subscription implementer was refused: {verdict}"


def test_a_gateway_routed_implementer_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S1 — the control. The status quo must keep working.

    Un-pinning must widen what the check accepts, not swap one accepted shape
    for another: an operator on the gateway route is the configuration this
    repository has run under since 2026-08-07 and it stays green.

    Mutation: replace the alias-shape pin with its inverse (a check that the
    model carries *no* slash) and this fails while the subscription test above
    still passes.
    """
    verdict = _verdict(
        _registry_text(model="example-gateway/your-model", fallback="example/fallback"),
        tmp_path,
        monkeypatch,
    )

    assert verdict is None, f"a gateway-routed implementer was refused: {verdict}"


def test_an_implementer_that_resolves_no_model_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S3, FR-002, plan trap 1 — the coverage that must survive the removal.

    Two registries whose implementer resolves no model to route work to, and
    the check must refuse both:

    - `model: ""` is refused by the loader, which never yields a persona at all;
    - a deterministic implementer (`agent: none`, and therefore `model: null`)
      loads cleanly and is refused by `assert registry["implementer"].model`
      itself. That second case is the one that proves the surviving line is
      load-bearing rather than decorative, which is why the assertion type is
      pinned here.

    Mutation: delete `assert registry["implementer"].model` along with the
    alias-shape pin and this fails.
    """
    refused_by_loader = _verdict(_registry_text(model=""), tmp_path, monkeypatch)
    assert isinstance(refused_by_loader, config_module.ConfigError), refused_by_loader

    refused_by_assertion = _verdict(
        _registry_text(agent="none", model=None, fallback=None, timeout=None),
        tmp_path,
        monkeypatch,
    )
    assert isinstance(refused_by_assertion, AssertionError), refused_by_assertion


# --- US1-S4: the anti-recurrence guard ---------------------------------------


#: The persona fields that name a vendor or a route. `model` and `fallback` are
#: the aliases themselves; `agent` is which route they are reached over.
_PINNABLE_FIELDS = frozenset({"model", "fallback", "agent"})

#: The calls that can move where the loader looks, and the names that say the
#: move is about the persona registry. A body that makes one of these reads a
#: fixture registry of its own, so its literals are its own to choose.
#:
#: The verbs matter as much as the names: `monkeypatch.delenv("ERGANE_PERSONAS_PATH")`
#: is how the shipped-registry check *insists* on the operator's own file, and
#: reading only the name would exclude the one test this story exists to fix.
_REPOINT_CALLS = frozenset({"setenv", "setattr"})
_REGISTRY_SEAMS = (
    "ERGANE_PERSONAS_PATH",
    "FACTORY_PERSONAS_PATH",
    "DEFAULT_REGISTRY_PATH",
    "resolve_default_registry_path",
    "load_personas",
)

#: Arguments that still name the operator's own registry, so a body passing one
#: is a shipped-registry test even though the call is not bare.
_SHIPPED_ARGUMENTS = frozenset({"SHIPPED_REGISTRY"})


def _permitted_literals() -> frozenset[str]:
    """The only strings an assertion about a persona's route may name.

    Two kinds, and neither is a value the operator picked between:

    - the sentinels `factory/config.py` defines — "this persona runs no LLM",
      "this one runs off the operator's own login". They are kinds of persona
      the code itself knows about, not vendors.
    - the persona names themselves. Naming a persona is how a test says *which*
      entry it means (`ResolvedPersona(persona="judge", model_alias=…)`), and
      the factory routes by persona (constitution VII), so the roster is its
      vocabulary rather than anybody's choice.

    Both are read from the registry and the module that defines them rather
    than frozen as literals here, so this guard names no operator choice while
    refusing them.
    """
    return frozenset(
        {config_module.DETERMINISTIC_AGENT, config_module.SUBSCRIPTION_AGENT}
        | set(config_module.load_personas())
    )


def _parse(path: Path) -> ast.Module:
    """Parse a test module. Suppresses `SyntaxWarning` because a regex or a
    docstring in some *other* module is not this guard's business to report."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _called_name(node: ast.Call) -> str | None:
    """The bare name a call invokes, whether it is `f()` or `obj.f()`."""
    target = node.func
    if isinstance(target, ast.Attribute):
        return target.attr
    return getattr(target, "id", None)


def _repoints_the_registry(function: ast.AST) -> bool:
    """Whether a function body pointed the loader at a registry of its own."""
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        verb = _called_name(node)
        if verb not in _REPOINT_CALLS:
            continue
        rendered = ast.unparse(node)
        if any(seam in rendered for seam in _REGISTRY_SEAMS):
            return True
    return False


def _reads_the_shipped_registry(function: ast.AST) -> bool:
    """Whether this function loads the operator's own registry.

    Located structurally, not by name: the only way a test obtains the
    operator's wiring is a `load_personas()` with no path — or one naming the
    shipped path constant — so a renamed or newly written test is covered by
    having been written rather than by appearing on a list.
    """
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node) != "load_personas":
            continue
        if not node.args and not node.keywords:
            return True
        if len(node.args) == 1:
            argument = node.args[0]
            resolved = (
                argument.attr
                if isinstance(argument, ast.Attribute)
                else getattr(argument, "id", None)
            )
            if resolved in _SHIPPED_ARGUMENTS:
                return True
    return False


def _free_string_literals(node: ast.AST) -> list[str]:
    """Every string literal in an expression that is not a subscript key.

    A key is how a persona is *named* (`registry["implementer"]`), which no
    operator can change without changing the factory's own vocabulary. A
    literal anywhere else in an assertion about a persona's route is a value
    the operator chose — the shape this defect keeps coming back in.
    """
    if isinstance(node, ast.Subscript):
        return _free_string_literals(node.value)
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    literals: list[str] = []
    for child in ast.iter_child_nodes(node):
        literals.extend(_free_string_literals(child))
    return literals


def _vendor_pins(path: Path) -> list[str]:
    """Every assertion in `path` that constrains a shipped persona's vendor or route.

    An assertion offends when it reads `model`, `fallback` or `agent` off a
    persona from the operator's registry *and* names a string literal that is
    not a route sentinel. That is the discriminator the whole guard turns on:
    `assert item.model_alias == persona.model` asserts that the code reads the
    registry and is fine; `assert "/" in registry["implementer"].model`,
    `... .model == "anthropic/claude-opus-5"`, `... .model.startswith("ollama")`
    and `assert len(...model.split("/")) == 2` all smuggle in a literal, and
    all fail here.
    """
    permitted = _permitted_literals()
    offences: list[str] = []
    for function in _parse(path).body:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _reads_the_shipped_registry(function):
            continue
        if _repoints_the_registry(function):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Assert):
                continue
            touched = {
                child.attr
                for child in ast.walk(node.test)
                if isinstance(child, ast.Attribute) and child.attr in _PINNABLE_FIELDS
            }
            if not touched:
                continue
            named = [
                literal
                for literal in _free_string_literals(node.test)
                if literal not in permitted
            ]
            if named:
                offences.append(
                    f"{path.name}:{node.lineno} in {function.name}: "
                    f"{ast.unparse(node)} — names {named} while reading "
                    f"{sorted(touched)} off the operator's registry"
                )
    return offences


def _shipped_registry_tests() -> list[str]:
    """Every test in the suite that asserts something about the shipped registry."""
    located: list[str] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        for function in _parse(path).body:
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _reads_the_shipped_registry(function):
                continue
            if _repoints_the_registry(function):
                continue
            if any(isinstance(node, ast.Assert) for node in ast.walk(function)):
                located.append(f"{path.name}::{function.name}")
    return located


def test_no_assertion_about_the_shipped_registry_constrains_a_vendor_or_route() -> None:
    """US1-S4, FR-008, plan trap 8 — the guard that makes the seventh recurrence
    fail here instead of surprising an operator.

    Six recurrences of `ci/test-suite-pins-the-operator-dial` were each closed
    by deleting one literal, and the seventh was written the next time somebody
    reached for a convenient one. So this reads the suite's own source and
    refuses the *mechanism*: no assertion made against the operator's registry
    may name which vendor or route a persona resolves to.

    Scanned across every `tests/test_*.py`, not just the file this story edits,
    because the last three recurrences each appeared in a different module.

    Mutation: write `assert "/" in registry["implementer"].model`, or any
    equality against a vendor alias, into a test that loads the shipped
    registry, and this fails naming the file, the line and the literal.
    """
    offences = [
        offence
        for path in sorted(TESTS_DIR.glob("test_*.py"))
        for offence in _vendor_pins(path)
    ]

    assert offences == [], offences


def test_the_guard_reads_the_shipped_registry_assertions_that_exist_today() -> None:
    """The locator, kept honest — a guard that matches nothing passes forever.

    The check this story edits must be among what the guard reads, and the scan
    must reach beyond the one file this story touches, or the coverage claimed
    above is imaginary.

    Mutation: break `_reads_the_shipped_registry`, or delete the surviving
    shipped-registry check, and this fails.
    """
    located = _shipped_registry_tests()

    assert (
        "test_us2_shipped_registry.py::"
        "test_repo_root_registry_still_resolves_real_wiring_in_checkout" in located
    ), located
    modules = {entry.split("::")[0] for entry in located}
    assert len(modules) >= 2, located
