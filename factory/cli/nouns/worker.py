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

from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.cli.nouns import Noun
from factory.supervision.deploy import deploy
from factory.supervision.units import install, resolve_layout, uninstall


def _install(args: argparse.Namespace) -> int:
    report = install(resolve_layout(env_command=args.env_command))
    print(report.render())
    return EXIT_OK


def _uninstall(_args: argparse.Namespace) -> int:
    report = uninstall(resolve_layout())
    print(report.render())
    return EXIT_OK


def _deploy(args: argparse.Namespace) -> int:
    """082-US2. Thin like the two above; the refusals are the engine's.

    The exit code is the one decision here: a deploy whose version never
    registered left a unit running and made nothing current (US2-S5), and
    exiting 0 would tell a script the floor moved when it has not. The report
    prints either way — it names every version, which is what an operator needs
    most on exactly that path."""
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


NOUN = Noun(
    name="worker",
    summary="supervise the worker and the operator bridge with systemd",
    order=6,
    add_parser=add_parser,
)
