"""The factory-doctor command surface.

`factory-doctor report|list|resolve|check` is the operator CLI over the
findings ledger and the probe registry. It mirrors the other factory CLIs'
exit-code contract:

- 0 success
- 1 operator-fixable refusal (bad grammar, unknown key, missing flags) or a
  newly filed `critical` finding from a probe
- 2 service not answering or a probe that was skipped because a service it needs
  did not answer

When a run both files a new critical finding and skips a probe, the exit is 2:
an incomplete examination outranks a bad one, because the operator's next action
is to re-run with the service up, not to read the finding (FR-007).

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
from factory.doctor.probes import REGISTRY, FindingReport, Probe, ServiceNotAnswering
from factory.doctor.store import connect, get_finding, list_findings, report, resolve

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

    check_parser = subparsers.add_parser("check", help="run all registered probes")
    check_parser.set_defaults(run=_check_command)

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


def _check_command(_args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    """Run every registered probe, file findings, and compute the exit code.

    A skipped probe (its service did not answer) is reported and forces exit 2.
    A new critical finding forces exit 1. If both happen, skip wins (FR-007).
    """
    seen_at = _utcnow()
    skipped_services: list[str] = []
    new_findings: list[Finding] = []

    for probe in REGISTRY:
        reports = _run_probe(probe, skipped_services)
        if reports is None:
            # Probe was skipped; the service name is already printed.
            continue
        for report in reports:
            finding = report.to_finding(source=probe.name)
            was_new = _report_if_new(conn, finding, seen_at=seen_at)
            if was_new and finding.severity is Severity.CRITICAL:
                new_findings.append(finding)

    if skipped_services:
        return EXIT_TRANSPORT
    if new_findings:
        return EXIT_USER
    return EXIT_OK


def _run_probe(
    probe: Probe, skipped_services: list[str]
) -> list[FindingReport] | None:
    """Gather and evaluate one probe. Returns None when the probe is skipped."""
    try:
        snapshot = probe.gather()
    except ServiceNotAnswering as exc:
        print(f"check: {probe.name}: skipped ({exc.service} not answering)", file=sys.stderr)
        skipped_services.append(exc.service)
        return None
    except Exception as exc:  # pragma: no cover - probe bugs propagate
        raise
    return probe.evaluate(snapshot)


def _report_if_new(
    conn: sqlite3.Connection, finding: Finding, *, seen_at: str
) -> bool:
    """File a finding if it is new this run. Returns True when a row was inserted."""
    prior = get_finding(conn, finding.key)
    report(conn, finding, seen_at=seen_at)
    return prior is None
