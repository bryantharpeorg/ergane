"""The registry type shared by every noun module.

A noun is one module under `factory/cli/nouns/` that declares a module-level
`NOUN`. Discovery walks the package directory; there is no list elsewhere.

Shared seams that tests can patch without reloading individual noun modules
also live here, because this package `__init__.py` is not exec'd by discovery.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from temporalio.client import Client
from temporalio.service import RPCError

from factory.controlplane.resolve import resolve_temporal_target
from factory.usage.litellm_client import LiteLLMClient
from factory.cli.errors import EXIT_TRANSPORT, OperatorError


@dataclass(frozen=True)
class Noun:
    name: str
    summary: str
    order: int
    add_parser: Callable[[Any], None]


def _open_preflight_client() -> LiteLLMClient:
    """Default preflight client factory; tests patch this seam."""
    return LiteLLMClient.from_env()


def _open_forge(repo_path: str) -> Any:
    """Default forge factory for `build reset`; tests patch this seam.

    The forge the *repository* declares, through the one door `049-US5` put in
    front of that decision — never a `GhClient` built here. Only
    `factory/mergequeue/github_forge.py` constructs the GitHub-native client, and
    `tests/test_forge_seam.py` holds that to a literal set of one, so a fourth
    construction site would be a door with no seam behind it.

    On the package for the reason `_open_client` below spells out: noun modules
    are `exec_module`-d into fresh module objects at discovery, so a patch on a
    test file's imported `build` never reaches the module the parser dispatches
    into. A `reset` test that patched the wrong object would talk to the real
    forge, against whatever repository the operator running the suite is logged
    into.

    Imported here rather than at module scope so the package stays free of the
    merge surface for every noun that never touches a forge.
    """
    from factory.mergequeue.forge import resolve_forge_for_repo

    return resolve_forge_for_repo(repo_path=repo_path)


def _cli_revision_for_tests() -> str | None:
    """Tests override this package-level seam to avoid a real `git rev-parse`."""
    return None


async def _open_client() -> Client:
    """Default Temporal client factory; tests patch this seam.

    `factory.cli.main` discovers noun modules by `exec_module`-ing each file
    into a fresh module object. A `monkeypatch` on the test file's imported
    `build` module therefore does not reach the module object the parser's
    `set_defaults(run=...)` function references. Putting this seam on the
    package, which discovery never reloads, makes the patch stick.
    """
    target = resolve_temporal_target()
    address, namespace = target.address, target.namespace
    try:
        return await Client.connect(address, namespace=namespace)
    except (RPCError, RuntimeError, OSError) as error:
        raise OperatorError(
            f"cannot reach Temporal at {address} (namespace '{namespace}'): {error}",
            EXIT_TRANSPORT,
        ) from error
