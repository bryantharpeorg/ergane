"""The `install` noun: `ergane install` and `ergane install --verify`.

This noun is intentionally small.  Bare `ergane install` runs the walkthrough
(`factory.cli.install`), which interviews the operator, writes the control-plane
config and ends by verifying it; `--verify` runs that verification alone.  The
heavy lifting lives outside this module — in `factory.cli.install` and
`factory.controlplane.verify` — so both can be tested without the CLI boundary
and so noun discovery, which re-executes this file, holds no state.
"""

from __future__ import annotations

import argparse
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.cli.install import add_install_arguments, install_command
from factory.cli.nouns import Noun
from factory.controlplane.config import ControlPlaneConfigError
from factory.controlplane.verify import render_findings, verify_controlplane


def _verify_command(_args: argparse.Namespace) -> int:
    """Run every verify probe, print findings, and return 0 only if all pass.

    A config the parser refuses — most often one that is simply not there yet —
    is an *expected* condition on a first run, not a bug. Left uncaught it
    reached `run_cli`'s defensive boundary and came back as `ergane: unexpected
    error (…); re-run with --debug for the traceback`, which tells a new user
    the tool is broken when in fact they have not run `ergane install` yet. The
    guidance was already inside the message; only the wrapper was wrong.
    """
    try:
        findings, exit_code = verify_controlplane()
    except ControlPlaneConfigError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    print(render_findings(findings))
    return EXIT_OK if exit_code == 0 else EXIT_USER


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "install",
        help="configure and verify the Ergane control plane",
        description=(
            "Interview the operator for the five control-plane subsystems, "
            "write ~/.config/ergane/config.toml, and verify what was written. "
            "Re-running loads the existing file as defaults."
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="skip the interview: probe the declared subsystems and report one finding per check",
    )
    add_install_arguments(parser)
    parser.set_defaults(run=_run)


def _run(args: argparse.Namespace) -> int:
    if args.verify:
        return _verify_command(args)
    return install_command(args)


NOUN = Noun(
    name="install",
    summary="configure and verify the control plane",
    order=5,
    add_parser=add_parser,
)
