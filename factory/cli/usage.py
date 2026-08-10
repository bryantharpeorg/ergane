"""Implementation of `ergane usage`.

Reuses the legacy `factory.usage.cli` rollup logic but wraps it in the unified
error boundary and exit-code contract. A missing or unreadable ledger exits 3
without creating any file.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, OperatorError
from factory.usage.cli import UNMEASURED, open_readonly, render_table
from factory.usage.ledger import ROLLUP_DIMENSIONS, rollup

LEDGER_PATH_ENV = "FACTORY_LEDGER_PATH"
DEFAULT_LEDGER_PATH = Path(".factory") / "ledger.db"


def add_usage_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "usage",
        help="read-only usage rollups over the factory ledger",
        description="Render one rollup from the ledger without writing to it.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_ledger_path(),
        help=f"ledger file (default: ${LEDGER_PATH_ENV} or {DEFAULT_LEDGER_PATH})",
    )
    parser.add_argument(
        "--by",
        choices=ROLLUP_DIMENSIONS,
        required=True,
        help="rollup dimension",
    )
    parser.add_argument("--epic", default=None, help="restrict to one epic")
    parser.add_argument(
        "--since",
        type=_iso_day,
        default=None,
        metavar="YYYY-MM-DD",
        help="only attempts torn down on or after this day (UTC)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the machine-readable document instead of the table",
    )
    parser.set_defaults(run=usage_command)
    return parser


def usage_command(args: argparse.Namespace) -> int:
    import json

    try:
        conn = open_readonly(args.db)
    except sqlite3.Error as error:
        print(f"ergane usage: cannot read ledger {args.db}: {error}", file=sys.stderr)
        return EXIT_TRANSPORT

    try:
        document = rollup(conn, by=args.by, epic=args.epic, since=args.since)
    finally:
        conn.close()

    print(json.dumps(document, indent=2) if args.as_json else render_table(document))
    return EXIT_OK


def _default_ledger_path() -> Path:
    from os import environ

    return Path(environ.get(LEDGER_PATH_ENV) or DEFAULT_LEDGER_PATH)


def _iso_day(value: str) -> str:
    from datetime import date
    import re

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError(f"expected a YYYY-MM-DD day, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{value!r} is not a real date: {error}") from error
    return value
