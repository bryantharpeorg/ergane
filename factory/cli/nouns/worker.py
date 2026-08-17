"""The `worker` noun: `ergane worker install` and `ergane worker uninstall`.

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

from factory.cli.errors import EXIT_OK
from factory.cli.nouns import Noun
from factory.supervision.units import install, resolve_layout, uninstall


def _install(args: argparse.Namespace) -> int:
    report = install(resolve_layout(env_command=args.env_command))
    print(report.render())
    return EXIT_OK


def _uninstall(_args: argparse.Namespace) -> int:
    report = uninstall(resolve_layout())
    print(report.render())
    return EXIT_OK


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "worker",
        help="put the worker and the operator bridge under systemd supervision",
        description=(
            "Generate systemd user units for the worker and the notify bridge, "
            "inside a memory- and task-bounded slice that takes their whole "
            "process tree down with them. Uninstall removes exactly what "
            "install wrote, and reports anything it did not."
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


NOUN = Noun(
    name="worker",
    summary="supervise the worker and the operator bridge with systemd",
    order=6,
    add_parser=add_parser,
)
