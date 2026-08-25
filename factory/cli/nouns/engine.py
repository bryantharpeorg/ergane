"""The `engine` noun: `ergane engine upgrade`.

Thin on purpose: the drain decision, the project resolution and the docker
orchestration live in `factory.supervision.engine_upgrade`, so they can be
tested without a CLI boundary and without a docker daemon.  Noun discovery
re-executes this file, so it holds no state.

Ordered after `worker`: both verbs manage the engine, but `worker` is the
native systemd tier and `engine` is the container tier.
"""

from __future__ import annotations

import argparse
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError, run_cli
from factory.cli.nouns import Noun
from factory.supervision.engine_upgrade import UpgradeReport, upgrade


def _upgrade(args: argparse.Namespace) -> int:
    try:
        report = upgrade(force=args.force)
    except OperatorError:
        raise
    for note in report.notes:
        print(note)
    if report.findings:
        from factory.controlplane.verify import render_findings

        print("")
        print("verification through the new engine:")
        print(render_findings(list(report.findings)))
    return EXIT_USER if report.degraded else EXIT_OK


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "engine",
        help="manage the engine container",
        description=(
            "Commands for the container-tier engine. "
            "`upgrade` drains the running engine, starts the pinned CLI image, "
            "verifies through it, and reaps images older than the previous version."
        ),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    upgrader = verbs.add_parser(
        "upgrade",
        help="upgrade the engine container to this CLI's pinned image version",
        description=(
            "Stop the running engine container, start the image that matches this "
            "CLI version, run the install --verify battery through it, and remove "
            "local images older than the previous version. Refused while any epic "
            "is in flight unless `--force` is passed, because stopping the engine "
            "mid-epic strands the attempt it is running."
        ),
    )
    upgrader.add_argument(
        "--force",
        action="store_true",
        help="proceed even when an epic is in flight",
    )
    upgrader.set_defaults(run=lambda args: run_cli(lambda: _upgrade(args)))


NOUN = Noun(
    name="engine",
    summary="manage the engine container",
    order=7,
    add_parser=add_parser,
)
