"""The `worker` noun: `ergane worker install`, `uninstall` and `deploy`.

Thin on purpose, like every other noun here: the generation, the provenance and
the refusals live in `factory.supervision.units`, so they can be tested without
a CLI boundary and without a systemd session. Noun discovery re-executes this
file, so it holds no state.

Ordered immediately after `install`: configuring the control plane and putting
the worker under supervision are the same sitting, and the bare `ergane`
listing is read top to bottom.
"""

from __future__ import annotations

import argparse
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.cli.install import _systemd_user_session_available
from factory.cli.nouns import Noun
from factory.supervision.deploy import deploy
from factory.supervision.units import (
    declared_layout,
    install,
    migrate_off_legacy_unit,
    removal_layout,
    resolve_layout,
    uninstall,
)


def _require_systemd_user_session() -> None:
    """Refuse by name when no systemd user session is available (FR-015)."""
    if _systemd_user_session_available():
        return
    raise OperatorError(
        "no systemd user session is available (systemctl --user cannot connect "
        "to the bus); this usually means the command is running inside a "
        "container, where systemd user units are not available. Use the "
        "container supervisor to manage the worker instead of this verb."
    )


def _install(args: argparse.Namespace) -> int:
    """119-US1: the verb that writes the units is the caller that knows the mode.

    `declared_layout` reads `temporal.mode` from the control-plane config and
    hands it to the resolver, so a host that declared managed Temporal gets the
    server unit — and one whose declaration cannot be read is refused here,
    before anything is written, naming the file.
    """
    _require_systemd_user_session()
    report = install(declared_layout(env_command=args.env_command))
    print(report.render())
    return EXIT_OK


def _uninstall(_args: argparse.Namespace) -> int:
    """Removal resolves its layout the way removal may: without a refusal.

    A verb whose job is to remove what install wrote has to work on the
    installation whose declaration is broken; `removal_layout` says what it
    offers instead when the mode cannot be read, and removes nothing on the
    strength of it.
    """
    report = uninstall(removal_layout())
    print(report.render())
    return EXIT_OK


def _migrate(_args: argparse.Namespace) -> int:
    """088-US4. Thin like the rest; the refusal is now the noun's (FR-015)."""
    _require_systemd_user_session()
    report = migrate_off_legacy_unit(resolve_layout())
    print(report.render())
    return EXIT_OK


def _deploy(args: argparse.Namespace) -> int:
    """082-US2. Thin like the two above; the refusals are the engine's.

    The exit code is the one decision here: a degraded deploy left a unit
    running and made nothing current (US2-S5), and exiting 0 would tell a
    script the floor moved when it has not. The report prints either way —
    it names every version, which is what that path most needs read."""
    _require_systemd_user_session()
    report = deploy(resolve_layout(), args.revision)
    print(report.render())
    return EXIT_USER if report.degraded else EXIT_OK


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "worker",
        help="put the worker and the operator bridge under systemd supervision",
        description=(
            "Generate systemd user units for the worker and the notify bridge, "
            "inside a memory- and task-bounded slice that takes their whole "
            "process tree down with them, plus a probe timer that reports "
            "degradation out of band and reaps orphaned test servers. "
            "Uninstall removes exactly what install wrote."
        ),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    installer = verbs.add_parser("install", help="write, enable and start the units")
    installer.add_argument(
        "--env-command",
        default=None,
        help=(
            "a command emitting `export NAME=value` lines, evaluated at unit "
            "start; use it to keep credentials out of the unit files"
        ),
    )
    installer.set_defaults(run=_install)

    remover = verbs.add_parser("uninstall", help="remove exactly what install wrote")
    remover.set_defaults(run=_uninstall)

    deployer = verbs.add_parser(
        "deploy",
        help="put a committed revision on the floor beside the running worker",
        description=(
            "Freeze a commit into a checkout of its own outside this one, give "
            "it its own environment, start it as a versioned worker unit beside "
            "whatever is running, and make it current. Nothing is restarted, so "
            "every attempt in flight finishes on the version it started with."
        ),
    )
    deployer.add_argument(
        "revision",
        nargs="?",
        default=None,
        help=(
            "the commit to deploy — sha, tag or branch. Defaults to HEAD, and is "
            "refused while the tree is dirty: a deploy ships commits"
        ),
    )
    deployer.set_defaults(run=_deploy)

    migrator = verbs.add_parser(
        "migrate",
        help="retire the unversioned worker unit this engine no longer writes",
        description=(
            "Remove `ergane-worker.service`, the in-place-restart worker unit "
            "installs before this one wrote. Refused while any epic that "
            "predates versioning is still open: stopping that unit takes the "
            "agents it is running with it, and whatever survives is adopted "
            "onto whichever version is current at its next workflow task, "
            "which is not the code it started with. Removes the file only "
            "while it still matches what install wrote."
        ),
    )
    migrator.set_defaults(run=_migrate)


NOUN = Noun(
    name="worker",
    summary="supervise the worker and the operator bridge with systemd",
    order=6,
    add_parser=add_parser,
)
