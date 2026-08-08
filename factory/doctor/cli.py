"""The factory-doctor command surface.

`factory-doctor report|list|resolve` is US1's operator CLI over the findings
ledger. It mirrors the other factory CLIs' exit-code contract:

- 0 success
- 1 operator-fixable refusal (bad grammar, unknown key, missing flags)
- 2 service not answering (reserved; US2's `check` is the first user)

The store path resolves from the working directory the same way the ledger and
verification stores do.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from factory.doctor.models import Finding, Severity, Status, parse_findings_batch
from factory.doctor.store import connect, list_findings, report, resolve

EXIT_OK = 0
EXIT_USER = 1
EXIT_TRANSPORT = 2

DEFAULT_DB_PATH = Path(".factory") / "doctor.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store_path(args: argparse.Namespace) -> Path:
    return Path(args.db)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    path = _store_path(args)
    conn = connect(path)
    try:
        return int(args.run(args, conn))
    except _UserError as error:
        print(f"factory-doctor: {error}", file=sys.stderr)
        return error.code
    finally:
        conn.close()


class _UserError(Exception):
    """Something an operator can act on."""

    def __init__(self, message: str, code: int = EXIT_USER) -> None:
        super().__init__(message)
        self.code = code


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="factory-doctor")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"path to the findings store (default: {DEFAULT_DB_PATH})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="record a finding")
    report_parser.add_argument("--key", help="category/slug identity")
    report_parser.add_argument("--category", help="finding category")
    report_parser.add_argument(
        "--severity", help="critical|warning|info"
    )
    report_parser.add_argument("--summary", help="short description")
    report_parser.add_argument(
        "--refs", nargs="+", default=[], help="file:line reference strings"
    )
    report_parser.add_argument("--notes", default=None, help="extra evidence")
    report_parser.add_argument("--source", default="operator", help="reporter source")
    report_parser.add_argument(
        "--batch",
        metavar="FILE",
        help="ingest findings from a JSON batch file (all-or-nothing)",
    )
    report_parser.set_defaults(run=_report_command)

    list_parser = subparsers.add_parser("list", help="list findings")
    list_parser.set_defaults(run=_list_command)

    resolve_parser = subparsers.add_parser("resolve", help="resolve a finding")
    resolve_parser.add_argument("--key", required=True, help="finding to resolve")
    resolve_parser.add_argument("--reason", required=True, help="why it is resolved")
    resolve_parser.set_defaults(run=_resolve_command)

    return parser.parse_args(argv)


def _report_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    if args.batch:
        try:
            findings = parse_findings_batch(Path(args.batch).read_text())
        except (ValueError, OSError) as exc:
            raise _UserError(f"batch refused: {exc}")
        for finding in findings:
            report(conn, finding, seen_at=seen_at)
        return EXIT_OK

    missing = [
        name
        for name in ("key", "category", "severity", "summary")
        if getattr(args, name) is None
    ]
    if missing:
        raise _UserError(f"missing required flags: {', '.join(missing)}")

    try:
        severity = Severity(args.severity)
    except ValueError as exc:
        raise _UserError(f"unknown severity: {args.severity}") from exc

    finding = Finding(
        key=args.key,
        category=args.category,
        severity=severity,
        status=Status.OPEN,
        summary=args.summary,
        refs=args.refs,
        notes=args.notes,
        source=args.source,
        occurrences=1,
        first_seen=seen_at,
        last_seen=seen_at,
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    report(conn, finding, seen_at=seen_at)
    return EXIT_OK


def _list_command(_args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    findings = list_findings(conn)
    now = datetime.fromisoformat(_utcnow().replace("Z", "+00:00"))
    header = f"{'KEY':<45} {'SEV':<8} {'STATUS':<10} {'#':>5} {'AGE':<6}"
    print(header)
    for f in findings:
        age = _render_age(now, f.last_seen)
        print(f"{f.key:<45} {f.severity.value:<8} {f.status.value:<10} {f.occurrences:>5} {age:<6}")
    return EXIT_OK


def _render_age(now: datetime, last_seen: str) -> str:
    if not last_seen:
        return "-"
    try:
        seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    delta = now - seen
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "-"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h"
    return f"{total_seconds // 86400}d"


def _resolve_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    if not resolve(conn, args.key, reason=args.reason, resolved_at=seen_at):
        raise _UserError(f"finding {args.key!r} is not known or already resolved")
    return EXIT_OK
