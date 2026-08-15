"""Implementation of `ergane doctor` and `ergane findings`.

`doctor` runs every registered probe under the unified error boundary. A probe
whose service is unreachable is reported and forces exit 3; a probe that raises
any other exception is reported as one line naming `--debug` and continues so the
rest of the examination still runs.

`findings` exposes the other four legacy doctor verbs (report, list,
resolve, promote) with the unified prefix and exit-code contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.doctor.models import Finding, Severity, Status, parse_findings_batch
import factory.doctor.probes as _probes
from factory.doctor.scaffold import scaffold_spec
from factory.doctor.store import (
    connect,
    get_finding,
    list_findings,
    promote,
    report,
    resolve,
    resolve_by_spec,
    resolved_doctor_db_path,
)
from factory.roadmap.models import _split_frontmatter
from factory.workgraph.derive import DerivationError, derive_workgraph

#: Credential-like values must never reach findings or output.
_CREDENTIAL_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store_path(args: argparse.Namespace) -> Path:
    return Path(args.db)


def _contains_secret(value: str | None) -> bool:
    if value is None:
        return False
    return bool(_CREDENTIAL_RE.search(value))


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _CREDENTIAL_RE.sub("[REDACTED]", value)


def _sanitize_finding(finding: Finding) -> Finding:
    """Return a finding with any credential-like strings redacted."""
    return Finding(
        key=finding.key,
        category=finding.category,
        severity=finding.severity,
        status=finding.status,
        summary=_sanitize_text(finding.summary),
        refs=[_sanitize_text(ref) or "" for ref in finding.refs],
        notes=_sanitize_text(finding.notes),
        source=finding.source,
        occurrences=finding.occurrences,
        first_seen=finding.first_seen,
        last_seen=finding.last_seen,
        promoted_spec=finding.promoted_spec,
        resolved_at=finding.resolved_at,
        resolution=finding.resolution,
    )


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


def _resolve_promoted_findings(conn: sqlite3.Connection) -> None:
    """Resolve promoted findings whose spec now attests `state: landed`."""
    resolved_at = _utcnow()
    for finding in list_findings(conn):
        if finding.status is not Status.PROMOTED or not finding.promoted_spec:
            continue
        spec_path = Path(finding.promoted_spec) / "spec.md"
        try:
            text = spec_path.read_text(encoding="utf-8")
        except OSError:
            continue
        state = _read_spec_state(text)
        if state == "landed":
            resolve_by_spec(
                conn,
                finding.key,
                spec_dir=finding.promoted_spec,
                resolved_at=resolved_at,
            )


def _read_spec_state(text: str) -> str | None:
    block_text, _body = _split_frontmatter(text)
    if block_text is None:
        return None
    import yaml

    try:
        loaded = yaml.safe_load(block_text)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded.get("state")


# --- doctor -------------------------------------------------------------------


def add_doctor_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "doctor",
        help="run all registered probes",
        description="Run every registered probe and file any findings.",
    )
    default_path = resolved_doctor_db_path()
    parser.add_argument(
        "--db",
        default=str(default_path),
        help=f"path to the findings store (default: {default_path})",
    )
    parser.set_defaults(run=doctor_command)
    return parser


def doctor_command(args: argparse.Namespace) -> int:
    """Run every probe, file findings, and return the unified exit code."""
    path = _store_path(args)
    conn = connect(path)
    try:
        _resolve_promoted_findings(conn)
        return _run_all_probes(conn)
    finally:
        conn.close()


def _run_all_probes(conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    skipped_services: list[str] = []
    new_findings: list[Finding] = []
    unexpected_seen = False

    for probe in _probes.REGISTRY:
        reports, probe_unexpected = _run_one_probe(probe, skipped_services)
        if probe_unexpected:
            unexpected_seen = True
        if reports is None:
            continue
        for report in reports:
            finding = _sanitize_finding(report.to_finding(source=probe.name))
            was_new = _report_if_new(conn, finding, seen_at=seen_at)
            if was_new and finding.severity is Severity.CRITICAL:
                new_findings.append(finding)

    if skipped_services:
        return EXIT_TRANSPORT
    if unexpected_seen:
        return EXIT_USER
    if new_findings:
        return EXIT_USER
    return EXIT_OK


def _run_one_probe(
    probe: _probes.Probe,
    skipped_services: list[str],
) -> tuple[list[_probes.FindingReport] | None, bool]:
    """Gather and evaluate one probe, swallowing non-service exceptions."""
    try:
        snapshot = probe.gather()
    except _probes.ServiceNotAnswering as exc:
        reason = f" ({exc})" if str(exc) else ""
        print(
            f"ergane doctor: {probe.name}: skipped ({exc.service} not answering){reason}",
            file=sys.stderr,
        )
        skipped_services.append(exc.service)
        return None, False
    except Exception as exc:
        print(
            f"ergane doctor: {probe.name}: unexpected error ({exc}); "
            "re-run with --debug for the traceback",
            file=sys.stderr,
        )
        return None, True
    return probe.evaluate(snapshot), False


def _report_if_new(
    conn: sqlite3.Connection, finding: Finding, *, seen_at: str
) -> bool:
    prior = get_finding(conn, finding.key)
    report(conn, finding, seen_at=seen_at)
    return prior is None


# --- findings -----------------------------------------------------------------


def add_findings_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    default_path = resolved_doctor_db_path()
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument(
        "--db",
        default=str(default_path),
        help=f"path to the findings store (default: {default_path})",
    )

    parser = subparsers.add_parser(
        "findings",
        help="manage the findings ledger",
        description="Report, list, resolve, or promote findings.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    list_parser = verbs.add_parser("list", help="list findings", parents=[db_parent])
    list_parser.add_argument(
        "--severity", choices=[s.value for s in Severity], help="filter by severity"
    )
    list_parser.add_argument(
        "--status", choices=[s.value for s in Status], help="filter by status"
    )
    list_parser.add_argument("--json", action="store_true", help="emit JSON")
    list_parser.set_defaults(run=_with_store(findings_list_command))

    report_parser = verbs.add_parser("report", help="record a finding", parents=[db_parent])
    report_parser.add_argument("--key", help="category/slug identity")
    report_parser.add_argument("--category", help="finding category")
    report_parser.add_argument(
        "--severity", choices=[s.value for s in Severity], help="critical|warning|info"
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
    report_parser.set_defaults(run=_with_store(findings_report_command))

    resolve_parser = verbs.add_parser("resolve", help="resolve a finding", parents=[db_parent])
    resolve_parser.add_argument("--key", required=True, help="finding to resolve")
    resolve_parser.add_argument("--reason", required=True, help="why it is resolved")
    resolve_parser.set_defaults(run=_with_store(findings_resolve_command))

    promote_parser = verbs.add_parser("promote", help="scaffold a spec from findings", parents=[db_parent])
    promote_parser.add_argument("--slug", required=True, help="target spec directory name")
    promote_parser.add_argument(
        "--keys", nargs="+", default=[], help="finding keys to promote"
    )
    promote_parser.add_argument(
        "--specs-root",
        required=True,
        help="parent directory where the spec directory will be created",
    )
    promote_parser.add_argument(
        "--target-repo",
        required=True,
        help="target repo path recorded in the compiled workgraph",
    )
    promote_parser.set_defaults(run=_with_store(findings_promote_command))

    return parser


def _with_store(command: Any) -> Any:
    """Return a runner that opens the store and calls the verb."""

    def run(args: argparse.Namespace) -> int:
        path = _store_path(args)
        conn = connect(path)
        try:
            _resolve_promoted_findings(conn)
            return int(command(args, conn))
        finally:
            conn.close()

    return run


def findings_list_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    severity = Severity(args.severity) if args.severity else None
    status = Status(args.status) if args.status else None

    findings = list_findings(conn)
    if severity is not None:
        findings = [f for f in findings if f.severity is severity]
    if status is not None:
        findings = [f for f in findings if f.status is status]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
        return EXIT_OK

    now = datetime.fromisoformat(_utcnow().replace("Z", "+00:00"))
    header = f"{'KEY':<45} {'SEV':<8} {'STATUS':<10} {'#':>5} {'AGE':<6}"
    print(header)
    for finding in findings:
        age = _render_age(now, finding.last_seen)
        print(
            f"{finding.key:<45} {finding.severity.value:<8} "
            f"{finding.status.value:<10} {finding.occurrences:>5} {age:<6}"
        )
    return EXIT_OK


def findings_report_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    if args.batch:
        try:
            findings = parse_findings_batch(Path(args.batch).read_text())
        except (ValueError, OSError) as exc:
            raise OperatorError(f"batch refused: {exc}") from exc
        for raw in findings:
            if _contains_secret(raw.summary) or _contains_secret(raw.notes):
                raise OperatorError(
                    f"batch refused: finding {raw.key!r} contains a credential-like value"
                )
            if any(_contains_secret(ref) for ref in raw.refs):
                raise OperatorError(
                    f"batch refused: finding {raw.key!r} contains a credential-like value"
                )
            report(conn, raw, seen_at=seen_at)
        return EXIT_OK

    missing = [
        name
        for name in ("key", "category", "severity", "summary")
        if getattr(args, name) is None
    ]
    if missing:
        raise OperatorError(f"missing required flags: {', '.join(missing)}")

    try:
        severity = Severity(args.severity)
    except ValueError as exc:
        raise OperatorError(f"unknown severity: {args.severity}") from exc

    if _contains_secret(args.summary) or _contains_secret(args.notes):
        raise OperatorError("finding evidence contains a credential-like value; refusing")
    if any(_contains_secret(ref) for ref in args.refs):
        raise OperatorError("finding evidence contains a credential-like value; refusing")

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


def findings_resolve_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    if not resolve(conn, args.key, reason=args.reason, resolved_at=seen_at):
        raise OperatorError(f"finding {args.key!r} is not known or already resolved")
    return EXIT_OK


def findings_promote_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    specs_root = Path(args.specs_root)
    target_repo = Path(args.target_repo)
    slug: str = args.slug
    keys: list[str] = list(args.keys)

    if not keys:
        raise OperatorError("promote requires at least one --keys value")

    unknown_or_bad: list[str] = []
    findings: list[Finding] = []
    for key in keys:
        finding = get_finding(conn, key)
        if finding is None:
            unknown_or_bad.append(f"{key}: not known")
            continue
        if finding.status in (Status.PROMOTED, Status.RESOLVED):
            unknown_or_bad.append(
                f"{key}: already {finding.status.value}"
                + (f" into {finding.promoted_spec}" if finding.promoted_spec else "")
            )
            continue
        findings.append(_sanitize_finding(finding))

    if unknown_or_bad:
        raise OperatorError("promote refused:\n" + "\n".join(unknown_or_bad))

    specs_root.mkdir(parents=True, exist_ok=True)

    spec_dir = specs_root / slug
    if spec_dir.exists():
        raise OperatorError(
            f"spec directory {spec_dir} already exists; promote refuses to overwrite"
        )

    spec_text, plan_text, tasks_text = scaffold_spec(
        slug=slug,
        findings=findings,
        specs_root=str(specs_root),
        target_repo=str(target_repo),
    )

    with tempfile.TemporaryDirectory(
        dir=specs_root, prefix=f".tmp-promote-{slug}-"
    ) as tmp:
        temp_dir = Path(tmp)
        (temp_dir / "spec.md").write_text(spec_text, encoding="utf-8")
        (temp_dir / "plan.md").write_text(plan_text, encoding="utf-8")
        (temp_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")

        try:
            derive_workgraph(
                spec_text,
                epic_id=slug,
                feature=slug,
                specs_root=str(specs_root),
                target_repo=str(target_repo),
            )
        except DerivationError as error:
            raise OperatorError(f"scaffold does not compile: {error}") from error

        temp_dir.rename(spec_dir)

    spec_dir_abs = spec_dir.resolve()
    promote(conn, keys, spec_dir=str(spec_dir_abs), seen_at=seen_at)
    print(spec_dir_abs)
    return EXIT_OK


def findings_command(args: argparse.Namespace) -> int:
    """Entry point the noun module wires in."""
    return _findings_command(args)
