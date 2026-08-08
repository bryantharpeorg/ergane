"""Pure scaffolding: findings in, spec-directory text out (FR-008).

The generator produces a `spec.md` whose frontmatter reads `state: draft`, one
user story per finding carrying its evidence verbatim, one obligation-bearing
functional requirement per finding, and a `## Work Graph` block that covers every
story with `depends_on: []` and `implements` pointing at that story's FR.

Everything here is pure text generation; no filesystem writes live in this
module.  The caller (`factory.doctor.cli._promote_command`) writes to a temporary
directory, runs the deriver on the generated spec text, and only renames into
place when derivation reports zero rejections.
"""

from __future__ import annotations

import re

from factory.doctor.models import Finding

#: Credential-like values must never reach scaffold text. Mirrors the 001 sweep.
_CREDENTIAL_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def scaffold_spec(
    *,
    slug: str,
    findings: list[Finding],
    specs_root: str,
    target_repo: str,
) -> tuple[str, str, str]:
    """Generate the three files' contents for a promoted spec directory.

    Returns `(spec_md, plan_md, tasks_md)`.  The spec text is the only file the
    deriver validates; plan.md and tasks.md are human-facing skeletons pointing
    back at the finding keys.

    `specs_root` and `target_repo` are recorded in the generated frontmatter as
    comments and are supplied to `derive_workgraph` by the caller; they are not
    otherwise consulted by the generator.
    """
    if not findings:
        raise ValueError("cannot scaffold a spec from zero findings")

    safe_findings = [_sanitize_finding(f) for f in findings]

    spec_text = _build_spec_md(slug, safe_findings, specs_root, target_repo)
    plan_text = _build_plan_md(slug, safe_findings)
    tasks_text = _build_tasks_md(slug, safe_findings)
    return spec_text, plan_text, tasks_text


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _CREDENTIAL_RE.sub("[REDACTED]", value)


def _sanitize_finding(finding: Finding) -> Finding:
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


def _title_from_summary(summary: str) -> str:
    """Use the finding summary as the story title, verbatim but for whitespace."""
    return summary.rstrip()


def _build_spec_md(
    slug: str, findings: list[Finding], specs_root: str, target_repo: str
) -> str:
    lines: list[str] = []
    lines.append("---")
    lines.append("state: draft")
    lines.append(f"# specs_root: {specs_root}")
    lines.append(f"# target_repo: {target_repo}")
    lines.append("# Auto-scaffolded by factory-doctor promote; review before flipping to ready.")
    lines.append("---")
    lines.append("")
    lines.append(f"# Feature Specification: {slug}")
    lines.append("")
    lines.append(
        "This spec was scaffolded from accepted findings in the factory-doctor ledger. "
        "Each user story below carries the original finding's evidence verbatim; "
        "the operator or an architect session refines the prose before flipping "
        "`state` to `ready`."
    )
    lines.append("")

    for idx, finding in enumerate(findings, start=1):
        title = _title_from_summary(finding.summary)
        lines.append(f"### User Story {idx} - {title} (Priority: P2)")
        lines.append("")
        lines.append(finding.summary)
        lines.append("")
        lines.append("**Acceptance Scenarios**:")
        lines.append("")
        # Scenario stubs that satisfy criteria._STEP_RE with Given/When/Then.
        lines.append(
            f"1. **Given** the finding `{finding.key}`, **When** the work scoped here is "
            f"implemented, **Then** the ledger records a resolution tied to this spec."
        )
        lines.append("")
        lines.append("**Why this priority**: Promoted from the doctor ledger; the recurrence count "
                      "motivates building the fix.")
        lines.append("")
        lines.append("**Independent Test**: Verify the fix closes the finding and the scaffold "
                      "compiles with zero rejections.")
        lines.append("")
        lines.append("**Evidence**:")
        if finding.refs:
            for ref in finding.refs:
                lines.append(f"- `{ref}`")
        if finding.notes:
            lines.append(f"- {finding.notes}")
        lines.append("")

    lines.append("## Functional Requirements")
    lines.append("")
    for idx, finding in enumerate(findings, start=1):
        # FR body must contain MUST so the criteria parser accepts it.
        lines.append(
            f"- **FR-{idx:03d}**: The factory MUST address `{finding.key}`: "
            f"{finding.summary.rstrip('. ')}."
        )
    lines.append("")

    lines.append("## Work Graph")
    lines.append("")
    lines.append("```yaml")
    for idx, _finding in enumerate(findings, start=1):
        story = f"US{idx}"
        fr = f"FR-{idx:03d}"
        lines.append(f"{story}:")
        lines.append("  depends_on: []")
        lines.append(f"  implements: [{fr}]")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _build_plan_md(slug: str, findings: list[Finding]) -> str:
    lines = [
        f"# Plan: {slug}",
        "",
        "Scaffolded from the following ledger findings:",
        "",
    ]
    for finding in findings:
        lines.append(f"- `{finding.key}` — {finding.severity.value}: {finding.summary}")
    lines.extend(["", "Refine the approach before the spec is readied.", ""])
    return "\n".join(lines)


def _build_tasks_md(slug: str, findings: list[Finding]) -> str:
    lines = [
        f"# Tasks: {slug}",
        "",
        "This task list is a skeleton. The implementer node works its slice "
        "test-first and commits once per task.",
        "",
        "## Implementation",
        "",
    ]
    for idx, finding in enumerate(findings, start=1):
        lines.append(
            f"- [ ] T{idx:03d} Implement the fix for `{finding.key}` and run the gate command."
        )
    lines.extend(["", "## Verification", "", "- [ ] Final gate command passes green.", ""])
    return "\n".join(lines)
