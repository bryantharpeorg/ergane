"""The read side of the ledger — an answer an operator can trust, and cannot bend.

`factory-usage` is the one command this component ships (FR-012, US2). It exists
to answer "what did this persona / epic / requirement / retry cost?", and its
design is dominated by the two ways that answer could go wrong.

**It must not be able to change the answer.** The ledger is opened through a
`file:...?mode=ro` URI, so "no CLI invocation ever writes to the ledger" is
SQLite refusing the statement rather than this module happening never to issue
one (US2 scenario 4). The same choice buys a second guarantee for free: a
read-only open never creates a file, so pointing `--db` at a typo is an error
(exit 3) instead of a brand-new empty ledger reporting zero spend — which
`factory.usage.ledger.connect`, the writer's door, would cheerfully produce.

**It must not invent numbers.** `rollup` already returns exactly the document
`contracts/cli.md` publishes, so `--json` is a dump and the table is a
formatting pass over the same dict. Nothing here re-aggregates, which keeps
FR-004/FR-005's never-fabricate-a-zero rule in the one place that implements it
(the SQL's bare `SUM`, NULL over all-NULL input). The table renders that NULL as
a placeholder that is deliberately not a numeral: a printed `0` would read as
"this attempt used nothing" when the truth is "nobody measured it".

Exit codes are the scripting contract: 0 for any answer including an empty one,
2 for arguments the CLI cannot honour, 3 for a ledger it cannot read. Nothing
but the requested output ever reaches stdout, so a `--json` consumer parses
stdout whole or gets nothing to parse.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from factory.usage.ledger import ROLLUP_DIMENSIONS, rollup

#: Where the rest of the factory writes, so the quickstart's invocation works
#: from a repo root with no flags.
DEFAULT_LEDGER_PATH = Path(".factory") / "ledger.db"

#: Deployments that keep the ledger elsewhere set this once instead of passing
#: `--db` on every call; an explicit `--db` still wins.
LEDGER_PATH_ENV = "FACTORY_LEDGER_PATH"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_LEDGER = 3

#: `--since` is compared against ISO 8601 `torn_down_at` values as a string, so
#: a date in any other shape would silently match the wrong rows. Refusing it is
#: the only honest option.
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

#: The metric block of `contracts/cli.md`, as ledger field -> column heading, in
#: the order the contract lists them.
_COLUMNS = (
    ("prompt_tokens", "PROMPT"),
    ("completion_tokens", "COMPLETION"),
    ("cache_read_tokens", "CACHE_READ"),
    ("cache_write_tokens", "CACHE_WRITE"),
    ("requests", "REQUESTS"),
    ("spend_usd", "SPEND_USD"),
    ("rows", "ROWS"),
    ("unconfirmed_rows", "UNCONFIRMED"),
)

#: What a metric nobody reported looks like in the table. Anything parseable as
#: a number here would be a fabricated measurement (FR-005).
UNMEASURED = "-"

#: Heading for the key column. Only `node` needs saying out loud: its key is a
#: pair, because a node is identified within its epic (cli.md).
_KEY_HEADINGS = {"node": "EPIC:NODE"}


def main(argv: Sequence[str] | None = None) -> int:
    """Render one rollup. Returns the process exit status; never raises on a
    ledger it cannot read."""
    args = _parse_args(argv)

    try:
        conn = open_readonly(args.db)
        try:
            document = rollup(conn, by=args.by, epic=args.epic, since=args.since)
        finally:
            conn.close()
    except sqlite3.Error as error:
        # A missing file, a directory, or something that is not a database at
        # all: all the same to a reader, and none of them a reason to print a
        # half-answer on stdout.
        print(f"factory-usage: cannot read ledger {args.db}: {error}", file=sys.stderr)
        return EXIT_NO_LEDGER

    print(json.dumps(document, indent=2) if args.as_json else render_table(document))
    return EXIT_OK


def open_readonly(path: str | Path) -> sqlite3.Connection:
    """Open the ledger for reading only, and only if it already exists.

    `mode=ro` makes both properties structural: SQLite rejects every mutating
    statement on this connection, and raises `OperationalError` rather than
    creating a database that is not there.
    """
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse `contracts/cli.md`'s invocation; exits 2 on anything it does not name."""
    parser = argparse.ArgumentParser(
        prog="factory-usage",
        description="Read-only usage rollups over the factory ledger.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_ledger_path(),
        help=f"ledger file (default: ${LEDGER_PATH_ENV} or {DEFAULT_LEDGER_PATH})",
    )
    parser.add_argument(
        "--by",
        # The dimension names a grouping expression in generated SQL, so it is
        # validated at the argument boundary and never reaches the query
        # unvalidated. Sharing the ledger's tuple also means a dimension cannot
        # exist in SQL and be unreachable from the command line.
        choices=ROLLUP_DIMENSIONS,
        required=True,
        help="rollup dimension (FR-006)",
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
    return parser.parse_args(argv)


def _default_ledger_path() -> Path:
    """Resolved per invocation, so the environment is read when the CLI runs."""
    return Path(os.environ.get(LEDGER_PATH_ENV) or DEFAULT_LEDGER_PATH)


def _iso_day(value: str) -> str:
    if not _ISO_DAY.match(value):
        raise argparse.ArgumentTypeError(f"expected a YYYY-MM-DD day, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{value!r} is not a real date: {error}") from error
    return value


def render_table(document: dict[str, Any]) -> str:
    """The human view: one line per group, then the grand totals.

    Purely a formatting pass — every number printed comes from `document`, and
    a metric it reports as `None` is printed as `UNMEASURED`, not as a zero.
    """
    headings = [_KEY_HEADINGS.get(document["by"], document["by"].upper())]
    headings += [heading for _, heading in _COLUMNS]

    body = [_row(str(group["key"]), group) for group in document["groups"]]
    totals = _row("TOTAL", document["totals"])

    widths = [
        max(len(cell) for cell in column)
        for column in zip(headings, totals, *body)
    ]
    rule = ["-" * width for width in widths]

    return "\n".join(
        _line(cells, widths)
        for cells in [_caption(document), headings, rule, *body, rule, totals]
    )


def _caption(document: dict[str, Any]) -> list[str]:
    """One line of context above the table: what was asked, and of which rows."""
    filters = document["filters"]
    return [
        "by {by} | epic: {epic} | since: {since}".format(
            by=document["by"],
            epic=filters["epic"] or "all",
            since=filters["since"] or "all",
        )
    ]


def _row(key: str, metrics: dict[str, Any]) -> list[str]:
    return [key] + [_cell(field, metrics[field]) for field, _ in _COLUMNS]


def _cell(field: str, value: Any) -> str:
    if value is None:
        return UNMEASURED
    if field == "spend_usd":
        # Four places: a real sub-cent spend must not round into a number that
        # reads as "free".
        return f"{value:,.4f}"
    return f"{value:,}"


def _line(cells: Sequence[str], widths: Sequence[int]) -> str:
    """Key column left, numbers right, trailing padding trimmed."""
    padded = [cells[0].ljust(widths[0])] if cells else []
    padded += [cell.rjust(width) for cell, width in zip(cells[1:], widths[1:])]
    return "  ".join(padded).rstrip()


if __name__ == "__main__":  # pragma: no cover - console script uses `main`
    sys.exit(main())
