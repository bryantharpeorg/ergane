"""The `install` noun: `ergane install` and `ergane install --verify`.

This noun is intentionally small.  It lists what `ergane init` would configure,
and `--verify` probes the five declared subsystems and prints one finding per
check.  The heavy lifting lives in `factory.controlplane.verify` so it can be
tested without the CLI boundary.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.cli.nouns import Noun
from factory.controlplane.verify import render_findings, verify_controlplane


def _verify_command(_args: argparse.Namespace) -> int:
    """Run every verify probe, print findings, and return 0 only if all pass."""
    findings, exit_code = verify_controlplane()
    print(render_findings(findings))
    return EXIT_OK if exit_code == 0 else EXIT_USER


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "install",
        help="verify or repair the Ergane control plane",
        description="Install and verify the Ergane control-plane configuration.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="probe the five declared subsystems and report one finding per check",
    )
    parser.set_defaults(run=_run)


def _run(args: argparse.Namespace) -> int:
    if args.verify:
        return _verify_command(args)
    # Bare `ergane install` prints a concise pointer; repair is handled by init.
    print("Run `ergane install --verify` to probe the configured subsystems.")
    print("Run `ergane init` to create or repair the control-plane configuration.")
    return EXIT_OK


NOUN = Noun(
    name="install",
    summary="verify the control-plane configuration",
    order=5,
    add_parser=add_parser,
)
