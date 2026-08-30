"""123-US1: no fixture leases a virtual key against the operator's builder.

`tests/test_poll_usage.py:59` was `PERSONA = "implementer"` — byte-identical to
the line `tests/test_usage_activities.py:74` carried until 122/US2 removed it,
in a file 122's scoping never looked at. Fifteen tests in that module lease a
virtual key against whatever persona the operator has made his default builder,
and `issue_attempt_key` resolves an unspecified `agent` from the registry, so
pointing `implementer` at a subscription route makes every one of them lease a
key the factory deliberately does not mint. This repository's one gate is
`uv run pytest -q` (`factory.yaml`), so those fifteen red the gate for every node
of every epic. That is the seventh recurrence of
`ci/test-suite-pins-the-operator-dial`.

Six of the previous recurrences were closed by deleting one literal, and the
seventh was written the next time somebody needed a persona name and reached for
a convenient one. So the constant is only half of this story. The other half is
`test_no_fixture_leases_a_virtual_key_against_a_registry_persona`, which reads
the suite's own source and refuses the *mechanism*:

> A test that leases a virtual key either names a persona it owns, or declares
> the route it expects. It may not name a persona out of the operator's registry
> and then let the registry decide what the lease does.

Both halves of that "or" are real fixes and the guard accepts either, because
they answer the same question — *what happens when this lease runs?* — without
consulting a file the operator edits. `agent=` is the answer a dispatch already
carries in production (`IssueKeyInput.agent`, 070/US2); an unshipped persona name
is the answer for a fixture that only ever needed *a* persona.

Every test below answers "what edit would make this fail?" in its docstring, the
convention `tests/test_121_manifest_is_not_a_fixture.py` established for this
defect class and `tests/test_122_registry_is_not_pinned.py` kept.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from factory.activities.usage_activities import IssueKeyInput
from factory.config import ERGANE_PERSONAS_PATH_ENV, load_personas
from tests import test_poll_usage as poll

# The registry builders and the placeholder register are 122/US2's, imported
# rather than re-written: this story is the same defect one file over, and a
# second copy of "what a re-routed implementer looks like" is a second thing to
# keep true.
from tests.test_122_usage_fixture_persona import (
    GATEWAY_IMPLEMENTER,
    PLACEHOLDER,
    SUBSCRIPTION_IMPLEMENTER,
    _registry_with_implementer,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"

#: The modules that leased a key against the operator's builder, run together as
#: one pytest session under each route. `tests/test_poll_usage.py` is the file
#: the spec names; the other two are what the guard below found once it was
#: written, which is the entire reason for writing it.
PINNED_MODULES = (
    "tests/test_poll_usage.py",
    "tests/test_final_sweep.py",
    "tests/test_controlplane_direct_mode.py",
)


def _run_under(registry: Path, *modules: str) -> subprocess.CompletedProcess[str]:
    """Run `modules` in a child process against `registry`.

    A child, because `factory.config` resolves the registry path per call from
    the environment: the honest way to ask "would this suite be green on that
    operator's host" is to be that host for one process.
    """
    env = dict(os.environ)
    env[ERGANE_PERSONAS_PATH_ENV] = str(registry)
    return subprocess.run(
        [sys.executable, "-m", "pytest", *modules, "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# T001 / US1-S1: the case that fails today
# ---------------------------------------------------------------------------


def test_the_pinned_modules_pass_with_a_subscription_implementer(
    tmp_path: Path,
) -> None:
    """US1-S1, FR-002 — fifteen of these fail before the constant moves.

    Mutation: restore `PERSONA = "implementer"` in `tests/test_poll_usage.py`
    and this fails, naming the fifteen.
    """
    registry = _registry_with_implementer(tmp_path, **SUBSCRIPTION_IMPLEMENTER)

    # The registry really is the shape that broke — asserted before the run, so
    # a registry that silently failed to mutate cannot pass as a demonstration.
    implementer = load_personas(registry)["implementer"]
    assert implementer.needs_virtual_key is False

    result = _run_under(registry, *PINNED_MODULES)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# T002 / US1-S2: the control
# ---------------------------------------------------------------------------


def test_the_pinned_modules_pass_with_a_gateway_implementer(tmp_path: Path) -> None:
    """US1-S2 — the status quo keeps working.

    Without this, "green under a subscription implementer" would be satisfiable
    by a fixture that leases no key at all, which would delete the coverage
    instead of decoupling it.

    Mutation: swap the pin for its inverse — a persona that exists only on the
    subscription route — and this fails while the test above still passes.
    """
    registry = _registry_with_implementer(tmp_path, **GATEWAY_IMPLEMENTER)

    implementer = load_personas(registry)["implementer"]
    assert implementer.needs_virtual_key is True

    result = _run_under(registry, *PINNED_MODULES)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# T003 / US1-S3, trap 1: the persona is the tests' own
# ---------------------------------------------------------------------------


def test_the_poll_usage_fixtures_lease_against_a_persona_the_tests_own() -> None:
    """US1-S3, FR-001 — an unshipped name, in the module's own register.

    Naming another *real* persona would only move the pin: the next operator to
    re-route the architect would break the poll-usage tests instead. So the
    constant is held to a name nobody ships, wearing the same placeholder marker
    as the `MODELS` aliases beside it.

    Mutation: set `PERSONA` to `architect` — a real persona, and green today —
    and this fails.
    """
    shipped = load_personas(SHIPPED_REGISTRY)

    assert poll.PERSONA not in shipped, (
        f"PERSONA = {poll.PERSONA!r} is a persona the operator's registry "
        "defines, so re-routing it decides whether these tests pass"
    )
    assert PLACEHOLDER in poll.PERSONA, (
        f"PERSONA = {poll.PERSONA!r} must wear the same placeholder marker as "
        f"MODELS ({poll.MODELS!r}), so it reads as a value the tests own"
    )
    assert all(PLACEHOLDER in alias for alias in poll.MODELS)


# ---------------------------------------------------------------------------
# T004 / US1-S4, FR-003, trap 3: the check that ends the class
# ---------------------------------------------------------------------------


#: The activity that mints the key, and the payload that carries the persona
#: into it. A module that calls the first is leasing; every construction of the
#: second in such a module is a lease about to happen.
LEASE_ACTIVITY = "issue_attempt_key"
LEASE_PAYLOAD = "IssueKeyInput"
USAGE_MODULE = "factory.activities.usage_activities"

#: The payload's own field names, read off the dataclass rather than listed
#: here. Half the leases in this suite are built as a `dict` and splatted
#: (`IssueKeyInput(**fields)`) — `tests/test_poll_usage.py` and
#: `tests/test_final_sweep.py` both do, which is to say the file this story
#: exists to fix is one of them. A guard that only read keyword arguments would
#: have found nothing in either and passed on its first run. It did.
LEASE_FIELDS = frozenset(field.name for field in dataclasses.fields(IssueKeyInput))

#: `ActivityEnvironment.run(activity, payload)` is the other way the real
#: activity is invoked, and it reads as a call to `run`.
_RUNNER_CALLS = frozenset({"run"})

#: The calls that move where the loader looks, and the names that say the move
#: is about the persona registry — 122/US1's exemption, kept: a body that points
#: the resolver at a registry of its own owns the names in it.
_REPOINT_CALLS = frozenset({"setenv", "setattr"})
_REGISTRY_SEAMS = (
    "ERGANE_PERSONAS_PATH",
    "FACTORY_PERSONAS_PATH",
    "DEFAULT_REGISTRY_PATH",
    "resolve_default_registry_path",
    "load_personas",
)


def _parse(source: str, filename: str) -> ast.Module:
    """Parse a module. Suppresses `SyntaxWarning` because a regex or a docstring
    in some *other* module is not this guard's business to report."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(source, filename=filename)


def _called_name(node: ast.Call) -> str | None:
    """The bare name a call invokes, whether it is `f()` or `obj.f()`."""
    target = node.func
    if isinstance(target, ast.Attribute):
        return target.attr
    return getattr(target, "id", None)


def _leases_virtual_keys(tree: ast.Module) -> bool:
    """Whether this module actually runs the real key-issuing activity.

    Three conditions, all structural, because a list of file names is a list
    that goes stale:

    - it imports `issue_attempt_key` from the usage module;
    - it does not define an activity of that name itself — the workflow tests
      register stubs under the contract name, and a stub reads no registry;
    - it *calls* it, directly or through `ActivityEnvironment.run`. Naming it as
      an argument to `workflow.execute_activity` is not a call: Temporal
      resolves that by name against whatever the worker registered, which in
      this suite is always a stub. `tests/reference_flow.py` is that case, and
      it is why the discriminator is the call rather than the import.
    """
    imports_it = any(
        isinstance(node, ast.ImportFrom)
        and node.module == USAGE_MODULE
        and any(alias.name == LEASE_ACTIVITY for alias in node.names)
        for node in ast.walk(tree)
    )
    if not imports_it:
        return False

    defines_a_stub = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == LEASE_ACTIVITY
        for node in ast.walk(tree)
    )
    if defines_a_stub:
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node) == LEASE_ACTIVITY:
            return True
        if _called_name(node) in _RUNNER_CALLS and node.args:
            if getattr(node.args[0], "id", None) == LEASE_ACTIVITY:
                return True
    return False


def _repoints_the_registry(scope: ast.AST) -> bool:
    """Whether this scope pointed the loader at a registry of its own."""
    for node in ast.walk(scope):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node) not in _REPOINT_CALLS:
            continue
        if any(seam in ast.unparse(node) for seam in _REGISTRY_SEAMS):
            return True
    return False


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """The module-level string constants, which is where a fixture persona lives.

    `PERSONA = "implementer"` is the shape all seven recurrences took: one name
    at the top of the file, referenced by every test below it. Resolving it here
    is what lets the guard report the constant rather than the call sites.
    """
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def _resolved_string(node: ast.expr | None, constants: dict[str, str]) -> str | None:
    """A keyword's value as a string, if it can be read without running anything.

    A literal, or a module constant holding one. Anything else — an attribute, a
    parameter, an f-string — is not a name this file can decide about, and the
    locator test below is what keeps that from quietly becoming the whole suite.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _declares_its_route(node: ast.expr | None, constants: dict[str, str]) -> bool:
    """Whether the payload says, itself, which route the lease takes.

    `IssueKeyInput.agent` is the field a real dispatch carries, and
    `_is_subscription_persona` reads the registry only when it is empty. So a
    payload that sets it to anything non-empty has already answered the question
    the registry would otherwise be asked, and the persona name beside it is an
    attribution dimension rather than a decision.
    """
    if node is None:
        return False
    resolved = _resolved_string(node, constants)
    if resolved is not None:
        return resolved != ""
    # A parameter, an attribute, a fixture value: the payload names the field
    # deliberately, and what it resolves to is that test's own business.
    return True


def _enclosing_scopes(tree: ast.Module, target: ast.AST) -> list[ast.AST]:
    """Every function body that contains `target`, outermost first."""
    scopes: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(child is target for child in ast.walk(node)):
            scopes.append(node)
    return scopes


def _payload_fields(tree: ast.Module) -> list[tuple[ast.AST, dict[str, ast.expr]]]:
    """Every lease payload the module builds, however it spells it.

    Two spellings, because the suite uses both:

    - `IssueKeyInput(persona=..., ...)` — the keyword form;
    - `{"persona": ..., ...}` splatted into it — the dict form, which is how a
      module with a shared `issue()` helper lets each test override one field.

    A dict counts only when every key is a literal string, one of them is
    `persona`, and all of them are fields of the payload. That is a mapping
    built to *be* an `IssueKeyInput` and nothing else — no other dict in this
    suite has that key set, and requiring the whole set is what keeps the guard
    from reporting on, say, an `AttemptRecord`.
    """
    payloads: list[tuple[ast.AST, dict[str, ast.expr]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node) == LEASE_PAYLOAD:
            payloads.append(
                (node, {kw.arg: kw.value for kw in node.keywords if kw.arg})
            )
        elif isinstance(node, ast.Dict):
            keys = [
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            if len(keys) != len(node.keys) or "persona" not in keys:
                continue
            if not set(keys) <= LEASE_FIELDS:
                continue
            payloads.append((node, dict(zip(keys, node.values))))
    return payloads


def _key_lease_pins(source: str, filename: str) -> list[str]:
    """Every lease in `source` that lets the shipped registry decide its outcome.

    An offence is a lease payload whose persona resolves to a name in the
    operator's registry, in a module that runs the real activity, where neither
    the payload nor the enclosing test says which route it expects. That is the
    discriminator the whole guard turns on:
    `IssueKeyInput(persona="implementer", ...)` offends;
    `IssueKeyInput(persona=SUBSCRIPTION.name, ..., agent=SUBSCRIPTION_AGENT)`
    does not, because it declares the route; and
    `IssueKeyInput(persona="gateway-CHANGEME", ...)` does not, because no
    registry defines that name to route anywhere.
    """
    tree = _parse(source, filename)
    if not _leases_virtual_keys(tree):
        return []

    shipped = set(load_personas(SHIPPED_REGISTRY))
    constants = _module_constants(tree)
    offences: list[str] = []

    for node, fields in _payload_fields(tree):
        persona = _resolved_string(fields.get("persona"), constants)
        if persona is None or persona not in shipped:
            continue
        if _declares_its_route(fields.get("agent"), constants):
            continue
        if any(
            _repoints_the_registry(scope) for scope in _enclosing_scopes(tree, node)
        ):
            continue
        held_by = fields["persona"]
        via = f" (via {held_by.id})" if isinstance(held_by, ast.Name) else ""
        offences.append(
            f"{filename}:{node.lineno}: leases a virtual key as persona "
            f"{persona!r}{via}, a name the operator's registry defines — so his "
            "routing decides whether this test passes. Name a persona the tests "
            "own, or declare `agent`."
        )
    return offences


def _key_leasing_modules() -> list[str]:
    """Every module in the suite that runs the real key-issuing activity."""
    located: list[str] = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if _leases_virtual_keys(_parse(source, str(path))):
            located.append(path.relative_to(REPO_ROOT).as_posix())
    return located


def test_no_fixture_leases_a_virtual_key_against_a_registry_persona() -> None:
    """US1-S4, FR-003, trap 3 — the check that ends the class.

    Seven recurrences of `ci/test-suite-pins-the-operator-dial` have each been
    closed by deleting one literal, and 122 shipped this guard's sibling for the
    *assertions* about the registry
    (`test_no_assertion_about_the_shipped_registry_constrains_a_vendor_or_route`)
    — which did not cover key-leasing fixtures, which is why this spec exists.
    This one covers them.

    Scanned across every module under `tests/`, not just the file this story
    edits, because the last four recurrences each appeared in a different one.

    Mutation: write `persona="implementer"` into any lease payload in a module
    that runs the real activity, and this fails naming the file, the line and
    the constant.
    """
    offences = [
        offence
        for path in sorted(TESTS_DIR.rglob("*.py"))
        for offence in _key_lease_pins(
            path.read_text(encoding="utf-8"), path.relative_to(REPO_ROOT).as_posix()
        )
    ]

    assert offences == [], "\n".join(offences)


#: The pin exactly as `tests/test_poll_usage.py` carried it until this story,
#: reduced to the lines that matter — including the splatted `dict`, because
#: that spelling is what the first draft of this guard walked straight past.
#: Driving the guard against source of its own is how it proves it is not
#: vacuous, with the demonstration in the diff rather than in a terminal.
_PINNED_SOURCE = f"""
from {USAGE_MODULE} import {LEASE_PAYLOAD}, {LEASE_ACTIVITY}

PERSONA = "implementer"


async def issue(env, **overrides):
    fields = {{
        "node_id": "n",
        "epic_id": "e",
        "attempt": 1,
        "persona": PERSONA,
        "spec_ref": "s",
        "models": ["a/CHANGEME"],
    }}
    fields.update(overrides)
    return await env.run({LEASE_ACTIVITY}, {LEASE_PAYLOAD}(**fields))
"""


@pytest.mark.parametrize(
    ("edit", "still_pinned"),
    [
        ("", True),
        # The fix this story makes: a name no registry defines.
        ('PERSONA = "implementer"|PERSONA = "gateway-CHANGEME"', False),
        # The other fix the guard accepts: the payload declares its own route.
        ('"persona": PERSONA,|"persona": PERSONA, "agent": "claude-code",', False),
        # Trap 1: another real persona moves the pin instead of removing it.
        ('PERSONA = "implementer"|PERSONA = "architect"', True),
    ],
)
def test_the_guard_catches_the_pin_this_story_removes(
    edit: str, still_pinned: bool
) -> None:
    """The guard, driven against the defect and against each of its fixes.

    Without this the check above could pass by matching nothing at all, which is
    how a guard becomes decoration. Note the last case: substituting `architect`
    makes the poll-usage tests green today and is still reported, because the
    pin is the mechanism and not the word `implementer`.

    Mutation: make `_leases_virtual_keys` or `_module_constants` return nothing,
    and this fails while the scan above still passes.
    """
    source = _PINNED_SOURCE
    if edit:
        before, after = edit.split("|")
        assert before in source
        source = source.replace(before, after)

    offences = _key_lease_pins(source, "tests/test_synthetic.py")

    assert bool(offences) is still_pinned, offences


def test_the_guard_reads_the_key_leasing_fixtures_that_exist_today() -> None:
    """The locator, kept honest — a guard that matches nothing passes forever.

    The module this story edits must be among what the guard reads, and the scan
    must reach beyond it, or the coverage claimed above is imaginary.

    Mutation: narrow `_leases_virtual_keys` to the import alone, or to the call
    alone, and this fails — the first by admitting `tests/reference_flow.py`,
    which registers no real activity, the second by dropping every module that
    leases through a helper.
    """
    located = _key_leasing_modules()

    assert "tests/test_poll_usage.py" in located, located
    assert len(located) >= 4, located
    # The workflow tests register a stub under the contract name; a guard that
    # counted those would be reporting on payloads no registry ever sees.
    assert "tests/test_interpreter.py" not in located, located
