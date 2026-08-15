"""Implementation of `ergane repo onboard` and `ergane repo migrate-runtime-root`.

`onboard` delegates to the legacy `factory.workgraph.cli.onboard_command` and
converts its `_OperatorError` to the new `OperatorError` so the unified boundary
handles it.

`migrate-runtime-root` moves a populated `.factory/` to `.ergane/` (US2).  It
lives under `repo` because the runtime root is a repository-local state tree,
and putting it here keeps it visible rather than burying it inside an unrelated
verb.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable

from temporalio.client import Client
from temporalio.testing import ActivityEnvironment

from factory.activities import roadmap_activities
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.mergequeue.gh import GhClient
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.workgraph.cli import (
    EXIT_OK as EPIC_EXIT_OK,
    EXIT_USER as EPIC_EXIT_USER,
    _OperatorError,
    _onboard_client_factory,
    _render_onboard,
    onboard_command as epic_onboard_command,
)
from factory.workgraph.worktree import (
    DEFAULT_RUNTIME_ROOT,
    LEGACY_FACTORY_ROOT,
    RuntimeRootChoice,
    resolve_factory_root,
)

async def _open_client() -> Client:
    """Connect to the operator's Temporal for the capacity read."""
    address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    try:
        return await Client.connect(address, namespace=namespace)
    except Exception as error:
        raise OperatorError(
            f"cannot reach Temporal at {address} (namespace '{namespace}'): {error}",
            EXIT_TRANSPORT,
        ) from error


#: Seam so tests can supply a fake Temporal client for the capacity read.
_temporal_client_factory: Callable[[], Awaitable[Client]] = _open_client


async def _running_epic_ids() -> set[str]:
    """Open `epic-*` workflow ids, using the same seam the roadmap uses."""
    client = await _temporal_client_factory()
    env = ActivityEnvironment(client=client)
    result = await env.run(roadmap_activities.count_open_epics, roadmap_activities.CountOpenInput())
    return set(result.open_ids)


def add_repo_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "repo",
        help="manage target repositories",
        description="Validate a target repository and manage its runtime state.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    onboard_parser = verbs.add_parser("onboard", help="validate a target repo")
    onboard_parser.add_argument("target_repo", help="path to the target repository")
    onboard_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the machine-readable profile",
    )
    onboard_parser.set_defaults(run=repo_onboard_command)

    migrate_parser = verbs.add_parser(
        "migrate-runtime-root",
        help="move runtime state from .factory/ to .ergane/",
        description=(
            "Move the worker-host runtime root from the legacy .factory/ name "
            "to .ergane/.  Refuses when any epic is running."
        ),
    )
    migrate_parser.add_argument(
        "--yes",
        action="store_true",
        help="perform the move without prompting (default is a dry run)",
    )
    migrate_parser.set_defaults(run=migrate_runtime_root_command)

    return parser


class _Args:
    """Lightweight namespace that satisfies what `epic_onboard_command` expects."""

    def __init__(self, target_repo: str, as_json: bool) -> None:
        self.target_repo = target_repo
        self.as_json = as_json
        self.json = as_json


def repo_onboard_command(args: argparse.Namespace) -> int:
    """Run the onboard check under the unified boundary."""
    try:
        code = epic_onboard_command(_Args(args.target_repo, bool(args.as_json)))
    except _OperatorError as error:
        raise OperatorError(str(error), code=error.code) from error
    if code == EPIC_EXIT_OK:
        return 0
    if code == EPIC_EXIT_USER:
        return 1
    return code


def migrate_runtime_root_command(args: argparse.Namespace) -> int:
    """Move a populated legacy runtime root to `.ergane/` (US2).

    Refuses while any epic is running, because moving the evidence store out
    from under a live workflow would make its next write land in a directory the
    reader no longer looks at.

    Idempotent: if `.ergane/` already exists, it reports already-migrated and does
    nothing.  With `--yes` it performs the move; otherwise it is a dry run that
    says what it would do.
    """
    root, choice, source = resolve_factory_root()

    if choice is RuntimeRootChoice.OVERRIDE:
        # An env override wins over both directory names; treat that as an
        # explicit, non-migratable configuration.
        raise OperatorError(
            f"{source} is set to {root}; migration only moves the default "
            "legacy root when no override is present"
        )

    if choice is RuntimeRootChoice.NEW:
        if root.resolve().name == str(DEFAULT_RUNTIME_ROOT):
            print("runtime root already migrated to .ergane/")
            return EXIT_OK
        # A non-default new root should not happen given the resolver's rules,
        # but guard it rather than silently moving the wrong directory.
        raise OperatorError(
            f"unexpected runtime root {root}; migration only moves the default "
            "legacy root when no override is present"
        )

    # At this point only the legacy root exists.
    assert choice is RuntimeRootChoice.LEGACY
    assert root.resolve().name == str(LEGACY_FACTORY_ROOT)

    open_epics = asyncio.run(_running_epic_ids())
    if open_epics:
        raise OperatorError(
            f"refusing to migrate while epic(s) are running: {', '.join(sorted(open_epics))}",
            code=EXIT_USER,
        )

    target = root.parent / DEFAULT_RUNTIME_ROOT
    if not args.yes:
        print(f"would move {LEGACY_FACTORY_ROOT}/ to {DEFAULT_RUNTIME_ROOT}/")
        print("re-run with --yes to perform the move")
        return EXIT_OK

    shutil.move(str(root), str(target))
    print(f"moved {LEGACY_FACTORY_ROOT}/ to {DEFAULT_RUNTIME_ROOT}/")
    return EXIT_OK
