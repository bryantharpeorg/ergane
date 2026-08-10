"""Implementation of `ergane repo onboard`.

Delegates to the legacy `factory.workgraph.cli.onboard_command` and converts its
`_OperatorError` to the new `OperatorError` so the unified boundary handles it.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from factory.cli.errors import OperatorError
from factory.mergequeue.gh import GhClient
from factory.workgraph.cli import (
    EXIT_OK as EPIC_EXIT_OK,
    EXIT_USER as EPIC_EXIT_USER,
    _OperatorError,
    _onboard_client_factory,
    _render_onboard,
    onboard_command as epic_onboard_command,
)


def add_repo_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "repo",
        help="manage target repositories",
        description="Validate a target repository before it is used for dispatch.",
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
