"""`revoke_key` is defined once, and the definition that survives delegates.

A merge put two `revoke_key` bodies into `LiteLLMClient`: a delegating one at the
top of the proxy-operations block and a hand-rolled copy several hundred lines
below it. Python keeps the last one, so the method a maintainer reads is not the
method that runs — a silent divergence waiting for the day the two bodies stop
agreeing.

Three guards, in the order the story asks for them (spec 064, US3):

- **The count.** `revoke_key` appears exactly once in the class body, read from
  the module's AST rather than from `dir()`, because a shadowed definition is
  invisible to the class object and visible only in the source (US3-S1, FR-009).
- **The delegation, observed.** `revoke_key` must route through
  `revoke_key_by_tokens` rather than reimplement the `/key/delete` call. This is
  asserted by patching the delegate and watching the behaviour change — a test
  that greps the method body for the name would pass on a comment mentioning it
  (US3-S2, trap 8).
- **The class of defect, not the instance.** Every class member in
  `factory/usage/litellm_client.py` is checked for redefinition, so the next
  merge that lands two bodies in one class is caught by a test that already
  exists (US3-S3, FR-010).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, Iterable

import httpx
import pytest

from factory.usage import litellm_client
from factory.usage.litellm_client import LiteLLMClient

MODULE_PATH = Path(inspect.getsourcefile(litellm_client) or "")

#: A recognisable stand-in for a virtual key. Distinctive so an assertion about
#: it cannot pass by matching something else in the request.
KEY = "sk-064-us3-revoke-me"


def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))


def _class_body(name: str) -> list[ast.stmt]:
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node.body
    raise AssertionError(f"{name} is not defined in {MODULE_PATH.name}")


def _member_names(statement: ast.stmt) -> Iterable[str]:
    """The names `statement` binds in the class body it sits in.

    Methods, nested classes and annotated or plain class attributes all count:
    the defect this guards against is "two bindings of one name in one class
    body", and a class-level constant redefined by a merge is the same bug with
    a different shape.

    A `@property`'s `@x.setter`/`@x.deleter` companions bind the same name on
    purpose, as do `@typing.overload` stubs, so both are excluded — a guard that
    fired on them would be turned off rather than fixed.
    """
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for decorator in statement.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr in {
                "setter",
                "deleter",
                "getter",
            }:
                return ()
            unwrapped = decorator.func if isinstance(decorator, ast.Call) else decorator
            trailing = getattr(unwrapped, "attr", None) or getattr(unwrapped, "id", None)
            if trailing == "overload":
                return ()
        return (statement.name,)
    if isinstance(statement, ast.ClassDef):
        return (statement.name,)
    if isinstance(statement, ast.AnnAssign):
        return (statement.target.id,) if isinstance(statement.target, ast.Name) else ()
    if isinstance(statement, ast.Assign):
        return tuple(
            target.id for target in statement.targets if isinstance(target, ast.Name)
        )
    return ()


def _redefined_members(body: list[ast.stmt]) -> dict[str, list[int]]:
    """Names bound more than once directly in `body`, with their line numbers."""
    lines: dict[str, list[int]] = {}
    for statement in body:
        for name in _member_names(statement):
            lines.setdefault(name, []).append(statement.lineno)
    return {name: found for name, found in lines.items() if len(found) > 1}


# --- US3-S1: defined once ---------------------------------------------------


def test_revoke_key_is_defined_exactly_once_in_the_class_body() -> None:
    """FR-009. Counted from the source, because a shadowed def leaves no trace.

    `LiteLLMClient.revoke_key` resolves to whichever body came last, so
    `getattr` cannot see the duplicate. The module's own text can.
    """
    definitions = [
        statement
        for statement in _class_body("LiteLLMClient")
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        and statement.name == "revoke_key"
    ]

    lines = [statement.lineno for statement in definitions]
    assert len(definitions) == 1, (
        f"revoke_key is defined {len(definitions)} times in LiteLLMClient "
        f"(lines {lines}); the last one wins and the others are dead source"
    )


# --- US3-S2: the surviving definition delegates -----------------------------


@pytest.fixture
def transport_calls() -> list[httpx.Request]:
    return []


@pytest.fixture
async def client(transport_calls: list[httpx.Request]) -> Any:
    """A client whose transport records every request it is asked to make.

    The recorder is what makes the delegation assertion non-vacuous: a
    `revoke_key` that reimplements the call still succeeds against this
    transport, and is caught by the request it leaves behind rather than by an
    exception it never raises.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        transport_calls.append(request)
        return httpx.Response(200, json={})

    async with LiteLLMClient(
        base_url="http://proxy.invalid",
        master_key="sk-master-064-us3",
        transport=httpx.MockTransport(handle),
    ) as instance:
        yield instance


async def test_revoke_key_delegates_to_revoke_key_by_tokens(
    client: LiteLLMClient,
    transport_calls: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009, observed rather than read (trap 8).

    Patching the delegate changes what `revoke_key` returns and stops the
    request from being made. A body that mentions `revoke_key_by_tokens` only in
    a comment fails both halves.
    """
    seen: list[list[str]] = []

    async def fake_revoke_key_by_tokens(self: LiteLLMClient, keys: Iterable[str]) -> bool:
        seen.append(list(keys))
        return False

    monkeypatch.setattr(
        LiteLLMClient, "revoke_key_by_tokens", fake_revoke_key_by_tokens
    )

    result = await client.revoke_key(KEY)

    assert seen == [[KEY]], "revoke_key did not call revoke_key_by_tokens with the key"
    assert result is False, "revoke_key ignored what revoke_key_by_tokens returned"
    assert transport_calls == [], (
        "revoke_key issued its own HTTP request instead of delegating: "
        f"{[str(request.url) for request in transport_calls]}"
    )


async def test_revoke_key_still_deletes_the_key_when_nothing_is_patched(
    client: LiteLLMClient, transport_calls: list[httpx.Request]
) -> None:
    """The delegation assertion above proves nothing if revocation is broken.

    So the unpatched path is exercised too: one `POST /key/delete` carrying the
    key, and `True` for "this call removed it" (R3, FR-002).
    """
    assert await client.revoke_key(KEY) is True

    (request,) = transport_calls
    assert request.method == "POST"
    assert request.url.path == "/key/delete"
    assert KEY in request.content.decode()


# --- US3-S3: no class member in the module is redefined ---------------------


def test_no_class_member_in_the_litellm_client_module_is_redefined() -> None:
    """FR-010. The guard is against the defect class, not against `revoke_key`.

    Every class in `factory/usage/litellm_client.py` is checked, and every kind
    of binding a class body can make — method, nested class, attribute — counts.
    A merge that lands two definitions of any one of them fails here.
    """
    offenders: dict[str, dict[str, list[int]]] = {}
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.ClassDef):
            continue
        redefined = _redefined_members(node.body)
        if redefined:
            offenders[node.name] = redefined

    assert offenders == {}, (
        f"redefined class members in {MODULE_PATH.name}: {offenders} — "
        "the later definition silently replaces the earlier one"
    )


def test_the_redefinition_guard_can_actually_fail() -> None:
    """The guard above is worthless if it cannot detect a redefinition.

    Ergane has already shipped four tests found structurally unable to fail, so
    this one is shown red against a class body that carries the exact defect:
    two `revoke_key` definitions, as the module held before this story.
    """
    source = (
        "class Doubled:\n"
        "    LIMIT = 1\n"
        "    async def revoke_key(self, key):\n"
        "        return True\n"
        "    async def revoke_key(self, key):\n"
        "        return False\n"
    )
    body = ast.parse(source).body[0]
    assert isinstance(body, ast.ClassDef)

    assert _redefined_members(body.body) == {"revoke_key": [3, 5]}


def test_the_redefinition_guard_tolerates_property_setters_and_overloads() -> None:
    """And it must not fire on the two legal ways to rebind a class name.

    A guard that flags `@x.setter` or `@typing.overload` gets deleted the first
    time someone writes one, which is how a defect class quietly loses its
    guard.
    """
    source = (
        "class Legal:\n"
        "    @property\n"
        "    def size(self): ...\n"
        "    @size.setter\n"
        "    def size(self, value): ...\n"
        "    @overload\n"
        "    def read(self, key: str) -> str: ...\n"
        "    @typing.overload\n"
        "    def read(self, key: int) -> int: ...\n"
        "    def read(self, key): ...\n"
    )
    body = ast.parse(source).body[0]
    assert isinstance(body, ast.ClassDef)

    assert _redefined_members(body.body) == {}
