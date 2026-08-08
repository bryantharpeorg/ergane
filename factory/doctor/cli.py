"""The factory-doctor command surface.

`factory-doctor report|list|resolve|check|promote` is the operator CLI over the
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
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import yaml

from factory.doctor.models import Finding, Severity, Status, parse_findings_batch
from factory.doctor.probes import REGISTRY, FindingReport, Probe, ServiceNotAnswering
from factory.doctor.scaffold import scaffold_spec
from factory.doctor.store import (
    connect,
    get_finding,
    list_findings,
    promote,
    report,
    resolve,
    resolve_by_spec,
)
from factory.roadmap.models import _split_frontmatter
from factory.workgraph.derive import DerivationError, derive_workgraph

EXIT_OK = 0
EXIT_USER = 1
EXIT_TRANSPORT = 2

DEFAULT_DB_PATH = Path(".factory") / "doctor.db"

#: Credential-like values must never reach findings, events, snapshots,
#: scaffolds, or output. This pattern mirrors the 001 sweep.
_CREDENTIAL_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store_path(args: argparse.Namespace) -> Path:
    return Path(args.db)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    path = _store_path(args)
    conn = connect(path)
    try:
        _resolve_promoted_findings(conn)
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

    promote_parser = subparsers.add_parser("promote", help="scaffold a spec from findings")
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
    promote_parser.set_defaults(run=_promote_command)

    return parser.parse_args(argv)


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


def _report_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    seen_at = _utcnow()
    if args.batch:
        try:
            findings = parse_findings_batch(Path(args.batch).read_text())
        except (ValueError, OSError) as exc:
            raise _UserError(f"batch refused: {exc}")
        for raw in findings:
            if _contains_secret(raw.summary) or _contains_secret(raw.notes):
                raise _UserError(
                    f"batch refused: finding {raw.key!r} contains a credential-like value"
                )
            if any(_contains_secret(ref) for ref in raw.refs):
                raise _UserError(
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
        raise _UserError(f"missing required flags: {', '.join(missing)}")

    try:
        severity = Severity(args.severity)
    except ValueError as exc:
        raise _UserError(f"unknown severity: {args.severity}") from exc

    if _contains_secret(args.summary) or _contains_secret(args.notes):
        raise _UserError("finding evidence contains a credential-like value; refusing")
    if any(_contains_secret(ref) for ref in args.refs):
        raise _UserError("finding evidence contains a credential-like value; refusing")

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
            finding = _sanitize_finding(report.to_finding(source=probe.name))
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


def _promote_command(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    """Scaffold a spec directory from named findings and record the promotion.

    Refuses to overwrite an existing directory. Writes to a temporary directory,
    runs the deriver on the scaffold, and only renames into place on a clean
    compile. A failed derivation removes the temporary directory so retrying the
    same slug is not blocked.
    """
    seen_at = _utcnow()
    specs_root = Path(args.specs_root)
    target_repo = Path(args.target_repo)
    slug: str = args.slug
    keys: list[str] = list(args.keys)

    if not keys:
        raise _UserError("promote requires at least one --keys value")

    # Validate the findings are eligible before touching the filesystem.
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
        raise _UserError("promote refused:\n" + "\n".join(unknown_or_bad))

    specs_root.mkdir(parents=True, exist_ok=True)

    spec_dir = specs_root / slug
    if spec_dir.exists():
        raise _UserError(
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
            raise _UserError(f"scaffold does not compile: {error}") from error

        # Rename into place: the directory did not exist when checked.
        temp_dir.rename(spec_dir)

    spec_dir_abs = spec_dir.resolve()
    promote(conn, keys, spec_dir=str(spec_dir_abs), seen_at=seen_at)
    print(spec_dir_abs)
    return EXIT_OK


def _resolve_promoted_findings(conn: sqlite3.Connection) -> None:
    """Close the loop: a promoted finding whose spec attests `landed` resolves.

    This runs at the top of every doctor invocation. It reads the promoted spec's
    frontmatter through the roadmap grammar and, if the state is `landed`, marks
    the finding resolved with the spec directory recorded as the resolution.
    Attested frontmatter only — observed-landed lives in RoadmapWorkflow state and
    is deliberately not queried here (FR-009).
    """
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
    """Read the `state` value from a spec's leading frontmatter block, if any.

    Uses the roadmap's frontmatter splitter so the definition of "frontmatter"
    stays in one place. Unknown or malformed blocks are treated as having no
    attested state, which leaves the finding promoted.
    """
    block_text, _body = _split_frontmatter(text)
    if block_text is None:
        return None
    try:
        loaded = yaml.safe_load(block_text)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    state = loaded.get("state")
    if not isinstance(state, str):
        return None
    return state
