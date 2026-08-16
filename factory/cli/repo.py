"""Implementation of the `ergane repo` verbs.

`onboard` delegates to the legacy `factory.workgraph.cli.onboard_command` and
converts its `_OperatorError` to the new `OperatorError` so the unified boundary
handles it.

`migrate-runtime-root` moves a populated `.factory/` to `.ergane/` (040 US2).  It
lives under `repo` because the runtime root is a repository-local state tree,
and putting it here keeps it visible rather than burying it inside an unrelated
verb.

`forget` (034 US6, FR-016) is registration's inverse: it deletes the repo's
roadmap schedule and then removes the registry entry, in that order.  The order
is the contract — a control plane that will not answer refuses the whole verb
rather than leaving a schedule firing at a repo the engine has forgotten, which
would dispatch work nobody is watching against a specs root that may no longer
exist.  Nothing in the repository itself is touched: the manifest, the gitignore
line and `.ergane/` belong to it.

`list` and `rebuild` (034 US2) are the registry's two faces.  `list` renders
every entry *with its manifest status*, so a repo whose manifest was deleted
after registration shows as drifted rather than disappearing — the cache reports
disagreement with the authority, it never hides it.  `rebuild` re-derives the
cache: it adopts the repo paths it is given, prunes entries whose repos are
gone, and leaves live entries alone.  Both refuse through `OperatorError`
directly rather than growing the legacy `_OperatorError` path.
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

from factory import registry
from factory.activities import roadmap_activities
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.locking import LockUnavailable, lock_path_for
from factory.mergequeue.gh import GhClient
from factory.roadmap import schedule as roadmap_schedule
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

#: STUB (red run only).
RUNTIME_ROOT_TEST_ISOLATION_FINDING = "hardening/test-suite-empties-a-live-runtime-root"


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

    list_parser = verbs.add_parser(
        "list",
        help="list the repositories the engine knows about",
        description=(
            "Render the repo registry: one line per entry with the current "
            "status of its committed manifest (valid, invalid or missing)."
        ),
    )
    list_parser.set_defaults(run=repo_list_command)

    rebuild_parser = verbs.add_parser(
        "rebuild",
        help="re-derive the repo registry from committed manifests",
        description=(
            "The registry is a cache. Rebuilding adopts the repository paths "
            "given, prunes entries whose repositories are gone, and leaves live "
            "entries untouched. Safe to run at any time."
        ),
    )
    rebuild_parser.add_argument(
        "repo_path",
        nargs="*",
        help="repository paths to adopt (each must carry a committed manifest)",
    )
    rebuild_parser.add_argument(
        "--lock-timeout",
        type=float,
        default=registry.DEFAULT_LOCK_TIMEOUT_S,
        metavar="SECONDS",
        help=(
            "how long to wait for another writer to release the registry lock "
            f"before refusing (default: {registry.DEFAULT_LOCK_TIMEOUT_S:g})"
        ),
    )
    rebuild_parser.set_defaults(run=repo_rebuild_command)

    forget_parser = verbs.add_parser(
        "forget",
        help="remove a repository's registry entry and its roadmap schedule",
        description=(
            "Delete the repository's roadmap schedule from the control plane "
            "and remove its registry entry.  The repository's own files - the "
            "manifest, the .gitignore line and .ergane/ - are left exactly as "
            "they are; removing them is the operator's git work."
        ),
    )
    forget_parser.add_argument("slug", help="the slug the repository is registered under")
    # STUB (red run only): the flags exist so argparse admits them and the tests
    # fail on behaviour rather than on exit code 2.
    forget_parser.add_argument("--clean-runtime", dest="clean_runtime", action="store_true")
    forget_parser.add_argument("--export", dest="export", metavar="DIR", default=None)
    forget_parser.add_argument(
        "--lock-timeout",
        type=float,
        default=registry.DEFAULT_LOCK_TIMEOUT_S,
        metavar="SECONDS",
        help=(
            "how long to wait for another writer to release the registry lock "
            f"before refusing (default: {registry.DEFAULT_LOCK_TIMEOUT_S:g})"
        ),
    )
    forget_parser.set_defaults(run=repo_forget_command)

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


def repo_list_command(args: argparse.Namespace) -> int:
    """Render the registry, one line per entry, with each manifest's status."""
    try:
        entries = registry.load_registry().entries
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None

    if not entries:
        print(
            "no repos are registered; run `ergane init` inside a repository "
            "to join one"
        )
        return EXIT_OK

    # Written with plain loops rather than comprehensions: `tests/test_repo_ast.py`
    # walks this module for names used without a binding it can see, and its
    # scope checker does not model comprehension scopes.
    rows: list[tuple[str, str, str]] = []
    for entry in entries:
        rows.append((entry.slug, registry.manifest_status(entry), str(entry.path)))

    headers = ("slug", "manifest", "path")
    widths: list[int] = []
    for column in range(len(headers)):
        width = len(headers[column])
        for row in rows:
            width = max(width, len(row[column]))
        widths.append(width)

    print(_render_row(headers, widths))
    for row in rows:
        print(_render_row(row, widths))
    return EXIT_OK


def _render_row(values: tuple[str, ...], widths: list[int]) -> str:
    """One left-aligned listing row, with no trailing whitespace."""
    cells: list[str] = []
    for column in range(len(values)):
        cells.append(values[column].ljust(widths[column]))
    return "  ".join(cells).rstrip()


def repo_rebuild_command(args: argparse.Namespace) -> int:
    """Adopt the given repo paths, prune dead entries, report both."""
    try:
        result = registry.rebuild(
            list(args.repo_path),
            timeout_s=float(args.lock_timeout),
        )
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    except LockUnavailable as error:
        raise OperatorError(_lock_refusal(error), code=EXIT_USER) from None

    if result.recovered:
        print("the previous registry could not be read; rebuilt from the paths given")
    for entry in result.adopted:
        print(f"adopted {entry.slug} -> {entry.path}")
    for slug, path in result.pruned:
        print(f"pruned {slug} ({path} is gone)")
    kept = len(result.kept)
    print(f"{kept} {'entry' if kept == 1 else 'entries'} kept, {len(result.pruned)} pruned")
    return EXIT_OK


def repo_forget_command(args: argparse.Namespace) -> int:
    """Delete the repo's schedule, then its registry entry - in that order.

    The schedule goes first because the failure this verb exists to prevent is
    an orphan: a schedule still ticking at a specs root no entry explains.  So a
    control plane that cannot be reached refuses the whole verb and says the
    entry is unchanged, rather than removing the entry and leaving the schedule
    to dispatch unwatched work.
    """
    slug = str(args.slug)
    try:
        entry = registry.load_registry().get(slug)
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None

    if entry is None:
        raise OperatorError(
            f"no repository is registered as {slug!r}; "
            "`ergane repo list` names the ones that are",
            code=EXIT_USER,
        )

    schedule_id = roadmap_schedule.schedule_id_for(slug)
    try:
        deleted = roadmap_schedule.remove_schedule(schedule_id)
    except roadmap_schedule.ScheduleUnavailable as unavailable:
        raise OperatorError(
            f"{unavailable}; refusing to forget {slug!r} while its roadmap "
            f"schedule {schedule_id} may still be firing - a schedule with no "
            "registry entry dispatches work nobody is watching.  The entry is "
            "unchanged; re-run this once the control plane answers",
            code=EXIT_USER,
        ) from None

    try:
        registry.forget(slug, timeout_s=float(args.lock_timeout))
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    except LockUnavailable as error:
        raise OperatorError(_lock_refusal(error), code=EXIT_USER) from None

    if deleted:
        print(f"deleted roadmap schedule {schedule_id}")
    else:
        print(f"no roadmap schedule {schedule_id} existed")
    print(f"forgot {slug} ({entry.path}); the repository itself is untouched")
    return EXIT_OK


def _lock_refusal(error: LockUnavailable) -> str:
    """One line naming the lock file, so a stale lock can be cleared by hand."""
    return (
        f"another writer holds the registry lock {lock_path_for(error.target)} "
        f"(waited {error.timeout_s:g}s); wait for it to finish, or remove that "
        "file if no `ergane` command is running"
    )


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
