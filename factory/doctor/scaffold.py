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

#: Sentinel placed on every mandatory blank in a generated scaffold.
ERGANE_TODO = "ERGANE-TODO:"


def scaffold_spec(
    *,
    slug: str,
    title: str | None = None,
    anchor: str | None = None,
    findings: list[Finding] | None = None,
    fixes: list[str] | None = None,
    specs_root: str = "",
    target_repo: str = "",
    demonstration: bool = False,
) -> tuple[str, str, str]:
    """Generate the three files' contents for a spec directory.

    The US1 variant (trap 1) takes `slug`, `title` and an already-resolved
    `path:line` `anchor`, and returns `(spec_md, plan_md, tasks_md)`.  It is
    pure text in, text out: no filesystem writes and no repository read.

    The legacy findings variant still accepts `findings`, `specs_root` and
    `target_repo` for callers of `ergane findings promote`.

    `demonstration` returns the worked story alone, with no sentinel and no
    skeletal slots, so a throwaway spec can be derived cleanly (trap 14).
    """
    if findings is not None:
        if not findings:
            raise ValueError("cannot scaffold a spec from zero findings")
        safe_findings = [_sanitize_finding(f) for f in findings]
        return (
            _build_spec_md(slug, safe_findings, specs_root, target_repo),
            _build_plan_md(slug, safe_findings),
            _build_tasks_md(slug, safe_findings),
        )

    if not slug:
        raise ValueError("slug is required")
    if not title:
        raise ValueError("title is required")
    if not anchor:
        raise ValueError("anchor is required")

    return _build_trio(slug, title, anchor, fixes=fixes or [], demonstration=demonstration)


def _build_trio(
    slug: str, title: str, anchor: str, *, fixes: list[str], demonstration: bool
) -> tuple[str, str, str]:
    """The US1 generator: three story slots and a tasks.md that validates."""
    safe_slug = _sanitize_text(slug) or slug
    safe_title = _sanitize_text(title) or title
    safe_anchor = _sanitize_text(anchor) or anchor

    slots = _story_slots(safe_title, anchor=safe_anchor, demonstration=demonstration)
    spec_text = _build_spec_md_from_slots(safe_slug, slots, fixes=fixes, demonstration=demonstration)
    plan_text = _build_plan_md_from_slots(safe_slug, slots, demonstration=demonstration)
    tasks_text = _build_tasks_md_from_slots(safe_slug, slots, demonstration=demonstration)
    return spec_text, plan_text, tasks_text


def _story_slots(
    title: str, *, anchor: str, demonstration: bool
) -> list[dict[str, Any]]:
    """Describe the three generated story slots.

    In normal mode the worked slot carries the anchor and concrete tasks; the
    partial and skeletal slots name no file path (trap 4).  In demonstration
    mode only the worked slot is returned.
    """
    worked = {
        "number": 1,
        "title": title,
        "priority": "P1",
        "scenarios": [
            "**Given** a slug, a title and an already-resolved `path:line` anchor, "
            "**When** the generator runs, **Then** it returns three texts — one fully "
            "worked story, one partial, one skeletal — whose story headings, literal "
            "Given/When/Then acceptance scenarios, Work Graph fence with an "
            "explicit `implements:` on every node, and `state: draft` frontmatter are "
            "all present, with an ERGANE-TODO sentinel on every mandatory blank and "
            "no sentinel inside a story heading, the Work Graph fence, or a task id — "
            "proven by committed tests that parse the returned text rather than diff a "
            "golden file.",
        ],
        "tasks": [
            f"[P] [US1-S1] Write the generator's failing tests around `{anchor}` — must fail.",
            f"[US1] Implement the scaffold generator so the tests pass. Anchor with `{anchor}`.",
            "[US1] Paste the validator transcript and the demonstration mode output.",
        ],
    }
    if demonstration:
        return [worked]

    partial = {
        "number": 2,
        "title": f"{title} — partial",
        "priority": "P2",
        "scenarios": [
            "**Given** the returned trio written to a directory, **When** the real "
            "`ergane spec validate` runs over it, **Then** it exits 0 with no refusal "
            "and no scenario-coverage advisory, every compiled node's task slice "
            "resolves, and the generated stories name no file in common with each other — "
            "proven by a committed transcript and committed tests.",
        ],
        "tasks": [
            "[P] [US2-S1] Wire the `spec new` verb and numbering logic.",
            "[US2-S1] Pick a tracked anchor in the target repo and prove it resolves.",
            "ERGANE-TODO: add the next US2 task here.",
        ],
    }
    skeletal = {
        "number": 3,
        "title": f"{title} — skeletal",
        "priority": "P3",
        "scenarios": [
            "**Given** the generator's demonstration mode, **When** it runs, **Then** "
            "it returns the worked story alone with no sentinel and no skeletal slot, so "
            "the result derives cleanly — proven by a committed test.",
        ],
        "tasks": [
            "ERGANE-TODO: write US3-S1 task when the sentinel gate is added.",
            "ERGANE-TODO: write US3-S2 task for the derive refusal.",
            "ERGANE-TODO: write US3-S3 task for the missing assertion.",
        ],
    }
    return [worked, partial, skeletal]


def _build_spec_md_from_slots(
    slug: str, slots: list[dict[str, Any]], *, fixes: list[str], demonstration: bool
) -> str:
    lines: list[str] = []
    lines.append("---")
    lines.append("state: draft")
    if fixes:
        lines.append("fixes:")
        for key in fixes:
            lines.append(f"  - {key}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Feature Specification: {slug}")
    lines.append("")
    if demonstration:
        lines.append(
            "This is a throwaway demonstration spec. It carries one worked story, no "
            "sentinels, and no skeletal slots so that `ergane spec derive` can compile "
            "it cleanly."
        )
    else:
        lines.append(
            "This spec was scaffolded by `ergane spec new`. Each user story below is a "
            "teaching slot: one fully worked story to imitate, one partial slot with "
            "blanks to complete, and one skeletal slot holding only structure."
        )
    lines.append("")

    for slot in slots:
        number = slot["number"]
        title = slot["title"]
        priority = slot["priority"]
        lines.append(f"### User Story {number} - {title} (Priority: {priority})")
        lines.append("")
        lines.append(
            f"As a developer reading my first scaffold, I see a {'worked' if number == 1 else 'teaching'} "
            f"story slot for US{number}."
        )
        lines.append("")
        lines.append("**Acceptance Scenarios**:")
        lines.append("")
        for scenario in slot["scenarios"]:
            lines.append(f"1. {scenario}")
        lines.append("")
        lines.append("**Why this priority**: " + ("Core teaching story" if number == 1 else "Teaching slot"))
        lines.append("")
        lines.append("**Independent Test**: Verify the scaffold structure parses cleanly.")
        lines.append("")

    if demonstration:
        lines.append("## Functional Requirements")
        lines.append("")
        lines.append(f"- **FR-001**: The system MUST support the worked story `{slug}`.")
        lines.append("")
    else:
        lines.append("## Functional Requirements")
        lines.append("")
        for slot in slots:
            lines.append(
                f"- **FR-{slot['number']:03d}**: The system MUST satisfy the "
                f"acceptance scenarios of User Story {slot['number']}."
            )
        lines.append("")

    lines.append("## Work Graph")
    lines.append("")
    lines.append("```yaml")
    for slot in slots:
        story = f"US{slot['number']}"
        fr = f"FR-{slot['number']:03d}"
        lines.append(f"{story}:")
        lines.append("  depends_on: []")
        lines.append(f"  implements: [{fr}]")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _build_plan_md_from_slots(
    slug: str, slots: list[dict[str, Any]], *, demonstration: bool
) -> str:
    lines = [f"# Plan: {slug}", ""]
    if demonstration:
        lines.append("A one-story throwaway plan for the install demonstration.")
    else:
        lines.append(
            "A teaching plan: one worked story to imitate, one partial slot to complete, "
            "and one skeletal slot to fill in."
        )
    lines.append("")
    for slot in slots:
        lines.append(f"## User Story {slot['number']} — {slot['title']}")
        lines.append("")
        if demonstration:
            lines.append("The demonstration story; no contention, no sentinel.")
        elif slot["number"] == 1:
            lines.append(f"Worked story anchored at the resolved file:line given to the generator.")
        elif slot["number"] == 2:
            lines.append("Partial slot: keep the tasks the generator wrote and add the rest.")
        else:
            lines.append("Skeletal slot: replace each ERGANE-TODO with a real task.")
        lines.append("")
    return "\n".join(lines)


def _build_tasks_md_from_slots(
    slug: str, slots: list[dict[str, Any]], *, demonstration: bool
) -> str:
    lines = [f"# Tasks: {slug}", ""]
    for slot in slots:
        number = slot["number"]
        title = slot["title"]
        lines.append(f"## Phase {number}: User Story {number} — {title}")
        lines.append("")
        for task in slot["tasks"]:
            lines.append(f"- [ ] {task}")
        lines.append("")
    if not demonstration:
        lines.append("## Verification")
        lines.append("")
        lines.append("- [ ] Final gate command passes green.")
    return "\n".join(lines)


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _CREDENTIAL_RE.sub("[REDACTED]", value)


def scan_sentinels(text: str) -> list[tuple[int, str]]:
    """Return every line containing the ERGANE-TODO sentinel, 1-indexed.

    Pure: text in, (line_no, line_text) list out.  Used by US3 to append
    sentinels to the validate report and by tests to assert their placement.
    """
    return [
        (index, line)
        for index, line in enumerate(text.splitlines(), start=1)
        if ERGANE_TODO in line
    ]


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
    lines.append("fixes:")
    for finding in findings:
        lines.append(f"  - {finding.key}")
    lines.append(f"# specs_root: {specs_root}")
    lines.append(f"# target_repo: {target_repo}")
    lines.append("# Auto-scaffolded by ergane findings promote; review before flipping to ready.")
    lines.append("---")
    lines.append("")
    lines.append(f"# Feature Specification: {slug}")
    lines.append("")
    lines.append(
        "This spec was scaffolded from accepted findings in the ergane findings ledger. "
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
