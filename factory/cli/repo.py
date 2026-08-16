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

034 US5 adds the two flags that make leaving complete without making it the
default.  `--clean-runtime` empties the repo's own runtime root once no epic is
running; `--export <dir>` writes the engine's records for the repo into open
formats outside that root, delegating to `factory/cli/repo_export.py`.  Both are
opt-in, because the portability principle is that a repo can leave cleanly, not
that leaving takes its history with it whether the operator asked or not.

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
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable

from temporalio.client import Client
from temporalio.testing import ActivityEnvironment

from factory import registry
from factory.activities import roadmap_activities
from factory.cli import repo_export
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

#: Finding key the removal guard names when it refuses a runtime root that a test
#: has no business emptying.  Same grammar as the store guard D-045 put at
#: `factory/verify/store.py::connect()`, for the same class of accident.
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
    forget_parser.add_argument(
        "--clean-runtime",
        dest="clean_runtime",
        action="store_true",
        help=(
            "also empty the repository's runtime root, once no epic is running; "
            "the directory itself stays, because the repo still ignores it"
        ),
    )
    forget_parser.add_argument(
        "--export",
        dest="export",
        metavar="DIR",
        default=None,
        help=(
            "first write this repository's engine-side records - findings, "
            "usage, escalations - into DIR as one JSONL file per store plus a "
            "markdown digest; DIR must lie outside the runtime root"
        ),
    )
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

    US5 adds two optional acts around that spine, and their order is the contract
    (FR-011, FR-013): every refusal is taken before any act, because a departure
    that half-happened is worse than one that was refused - the operator cannot
    tell which half ran by looking; `--export` runs before `--clean-runtime`,
    because the records it reads live in the root that flag empties; and
    `--clean-runtime` runs last, so state is deleted only once nothing points at
    it.
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

    runtime_root = runtime_root_for(entry.path)
    clean_runtime = bool(getattr(args, "clean_runtime", False))
    export_dir = getattr(args, "export", None)
    destination = Path(export_dir).resolve() if export_dir is not None else None

    if destination is not None:
        _refuse_export_inside_runtime_root(destination, runtime_root)
    if clean_runtime:
        _refuse_while_epics_run(slug)

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

    exported = None
    if destination is not None:
        exported = repo_export.export_records(
            slug=slug,
            repo=entry.path,
            runtime_root=runtime_root,
            destination=destination,
        )

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

    if exported is not None:
        for store in exported.stores:
            print(f"wrote {store.rows} {store.name} record(s) to {store.file}")
        print(f"wrote {exported.digest}")

    if clean_runtime:
        emptied = _empty_runtime_root(runtime_root)
        print(f"emptied {runtime_root} ({emptied} entr{'y' if emptied == 1 else 'ies'})")
        legacy = entry.path / LEGACY_FACTORY_ROOT
        if runtime_root.name != str(LEGACY_FACTORY_ROOT) and legacy.is_dir():
            print(
                f"left {legacy} alone; it is a second runtime root this repo "
                "never migrated, and only the resolved one is emptied"
            )
        print(f"forgot {slug} ({entry.path}); its own files are untouched")
    else:
        print(f"forgot {slug} ({entry.path}); the repository itself is untouched")
    return EXIT_OK


def runtime_root_for(repo: Path) -> Path:
    """The runtime root *of this repository*, decided by directory name alone.

    `resolve_factory_root()` answers a different question - which root the
    current process should use - from the working directory and from
    `ERGANE_ROOT`/`FACTORY_ROOT`.  Neither is a fact about the repository a slug
    names, and `--clean-runtime` deletes what this returns.  On 2026-08-14 this
    repository lost its whole runtime root to a process acting on a root it had
    been handed rather than one it had derived; the environment is not consulted
    here for that reason, and the result is a child of `repo` by construction
    rather than by check.

    Precedence is the resolver's own (034 plan, trap 12): `.ergane/` wins,
    `.factory/` is honoured while it is the only one, neither gets the modern name.
    """
    modern = repo / DEFAULT_RUNTIME_ROOT
    if modern.is_dir():
        return modern
    legacy = repo / LEGACY_FACTORY_ROOT
    if legacy.is_dir():
        return legacy
    return modern


def _refuse_export_inside_runtime_root(destination: Path, runtime_root: Path) -> None:
    """FR-013: the export lands outside the root `--clean-runtime` may empty."""
    root = runtime_root.resolve()
    if destination == root or root in destination.parents:
        raise OperatorError(
            f"refusing to export into {destination}: it is inside the runtime "
            f"root {runtime_root}, which --clean-runtime empties in this same "
            "command; name a directory outside it",
            code=EXIT_USER,
        )


def _refuse_while_epics_run(slug: str) -> None:
    """Refuse `--clean-runtime` while any epic is open (FR-011, plan trap 6).

    Any epic, not this repo's.  A workflow id is `epic-{epic_id}` and carries no
    repo token, so "is an epic running against *this* repo" has no answer yet; a
    filter over ids that cannot be filtered would match nothing, pass every test
    anyone thought to write, and delete a live epic's evidence the first time it
    mattered.  The blunt refusal is the honest one, and it says so.
    """
    open_epics = asyncio.run(_running_epic_ids())
    if not open_epics:
        return
    raise OperatorError(
        f"refusing to empty {slug!r}'s runtime root while epic(s) are running: "
        f"{', '.join(sorted(open_epics))}. A running epic's runtime root is "
        "evidence in use. Workflow ids carry no repo token, so this refuses on "
        "any open epic rather than guessing which repository one belongs to; "
        "nothing was changed",
        code=EXIT_USER,
    )


def _refuse_unsafe_removal(root: Path) -> None:
    """Refuse to empty a runtime root outside the tmp tree while a test runs.

    The enforcement D-045 put at `factory/verify/store.py::connect()`, at the one
    choke point every deletion in this verb goes through, and for the same
    reason: on 2026-08-14 this repository's live runtime root was emptied by a
    process satisfying a test, and the convention meant to prevent that had
    already decayed three times.  A convention is not a boundary for an act that
    deletes.

    Unlike D-045 there is no acknowledgment variable.  D-045 has one because a
    sanctioned live smoke must open a real store; nothing needs to empty a real
    runtime root from inside a test, and a door with no user is only a way in.
    Production never sets `PYTEST_CURRENT_TEST`, so an operator's own
    `--clean-runtime` is byte-identical to the pre-guard behaviour, and the
    refusal fires before any filesystem side effect.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return
    tmp_root = Path(tempfile.gettempdir()).resolve()
    try:
        root.resolve().relative_to(tmp_root)
    except ValueError:
        raise RuntimeError(
            f"refusing to empty the runtime root at {root}: a test-time deletion "
            f"must stay under the tmp tree ({RUNTIME_ROOT_TEST_ISOLATION_FINDING})"
        ) from None


def _empty_runtime_root(root: Path) -> int:
    """Delete everything inside `root`, keeping `root` itself, and count it.

    The directory survives its own emptying because the repository's `.gitignore`
    names it, and an operator who cleaned the state has not stopped ignoring the
    directory.  Written as a plain loop: `tests/test_repo_ast.py` walks this
    module for names used without a binding it can see, and its scope checker
    does not model comprehension scopes.
    """
    _refuse_unsafe_removal(root)
    if not root.is_dir():
        return 0
    removed = 0
    for child in sorted(root.iterdir()):
        removed += 1
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    return removed


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
