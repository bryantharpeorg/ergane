"""The six non-evidence validate layers and the vocabulary only they read.

US5 of 133 moves the rest of the cheap-room family out of
`factory/cli/nouns/spec.py`: the frontmatter and ledger layers, the work-graph
and persona layers, scenario coverage, the sentinel scanner, the tasks-text
reader, and the three module-level names those bodies alone read
(`_SCENARIO_ID_RE`, `_STRUCTURAL_TIMEOUT_S` and the `_vacuous_registry` that
reads it). The CLI module imports every one of them back under its own private
name, so `_validate_command` calls them exactly as it did and `_derive_command`
keeps its sentinel gate (plan T023).

Nothing here imports from `factory.cli.nouns.spec` (plan trap 17): the CLI
module imports from `factory.spec` at module scope, so an import back re-enters
a half-initialised module before its names exist. A moved body that needs a
CLI-module name means that name moves too — which is why
`_STRUCTURAL_TIMEOUT_S` and `_vacuous_registry` ride this story rather than
staying behind.

The checkers keep their shapes unchanged (plan trap 7): every one accumulates
into caller-owned `findings`/`information`/`skipped`/`checked` lists rather
than returning a report, `_check_fixes` keeps its four early returns with only
the success path appending to `checked` (plan trap 4), and every refusal
string is carried verbatim (plan trap 9) — including its call to
`resolve_factory_root()`, which draft 129 will change the return of and says
it will not edit its callers (plan trap 16).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import factory.doctor.cli as _doctor_cli
from factory.config import ConfigError, Persona, WriteScope, load_personas
from factory.doctor.store import connect_readonly, get_finding
from factory.doctor.triage import _declaration
from factory.roadmap.models import RoadmapError, _split_frontmatter, read_roadmap
from factory.verify.criteria import parse_spec
from factory.verify.models import RequirementKind
from factory.workgraph.cli import SPEC_NAME
from factory.workgraph.models import (
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.prompt import TASKS_DOCUMENT
from factory.workgraph.worktree import resolve_factory_root

from factory.spec import SpecFinding as _ValidateFinding

#: The id grammar the criteria parser mints for acceptance scenarios.
_SCENARIO_ID_RE = re.compile(r"US\d+-S\d+")

#: A registry that answers for every persona the graph names, so
# `validate_workgraph` checks only structural rules, not persona resolution.
# Persona resolution is checked separately against the real registry.
_STRUCTURAL_TIMEOUT_S = 1


def _vacuous_registry(graph: WorkGraph) -> dict[str, Persona]:
    """A registry that answers every persona the graph names for structural checks.

    `skills` is reserved and unused (062-US3 FR-009); the empty tuple is here only
    to satisfy the `Persona` dataclass.
    """
    return {
        node.persona: Persona(
            name=node.persona,
            agent="",
            model=None,
            fallback=None,
            # skills is reserved and unused; the empty tuple keeps the dataclass happy.
            skills=(),
            write_scope=WriteScope.WORKTREE,
            needs_worktree=True,
            timeout_s=_STRUCTURAL_TIMEOUT_S,
        )
        for node in graph.nodes
    }




def _scan_sentinels_in_trio(spec_dir: Path) -> list[tuple[str, int, str]]:
    """Return every ERGANE-TODO sentinel in the authored documents.

    Each tuple is `(document_name, 1-indexed_line, line_text)`.  Only the
    authored documents are scanned; a sentinel inside `workgraph.json` or any
    other file is not a blank the author is meant to fill.
    """
    from factory.doctor.scaffold import ERGANE_TODO, scan_sentinels

    results: list[tuple[str, int, str]] = []
    for name in ("spec.md", "plan.md", TASKS_DOCUMENT):
        path = spec_dir / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line_text in scan_sentinels(text):
            results.append((name, line_no, line_text))
    return results


def _tasks_text(spec_dir: Path) -> str | None:
    """The epic's `tasks.md`, or None when there is none to read (069-US2).

    None means **not read**, and every layer that takes it reports a skip rather
    than a pass: a document nobody opened has no findings, and calling that a
    clean bill of health is how a check comes to be trusted for something it
    never did (044 plan trap 5).
    """
    try:
        return (spec_dir / TASKS_DOCUMENT).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _check_frontmatter(spec_dir: Path, epic_id: str, findings: list[_ValidateFinding]) -> None:
    specs_root = spec_dir.parent
    try:
        read_roadmap(specs_root)
    except RoadmapError as error:
        for finding in error.findings:
            if finding.spec_dir == epic_id:
                findings.append(_ValidateFinding("frontmatter", str(finding)))
    except OSError as error:
        findings.append(_ValidateFinding("frontmatter", f"cannot read specs root {specs_root}: {error}"))


def _check_fixes(
    spec_dir: Path,
    findings: list[_ValidateFinding],
    information: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> None:
    """Verify every `fixes:` key names a row in the findings ledger.

    A spec that omits the key takes no new code path.  An absent ledger is
    reported as `not checked` rather than a refusal, because a freshly
    initialised target repo has no store by construction.  The store is opened
    read-only and only when it already exists, so validate cannot create it.
    """
    spec_path = spec_dir / SPEC_NAME
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError:
        # The frontmatter layer already reports a missing spec.md; do not double-report.
        return

    block_text, _body = _split_frontmatter(spec_text)
    _state, fixes = _declaration(block_text)
    if not fixes:
        return

    root, _choice, _source = resolve_factory_root()
    store_path = _doctor_cli._resolve_store_path(root)

    if not store_path.exists():
        skipped.append(
            {
                "layer": "fixes",
                "reason": f"no findings store at {store_path}",
            }
        )
        return

    conn: sqlite3.Connection | None = None
    try:
        conn = connect_readonly(store_path)
    except sqlite3.Error as exc:
        skipped.append(
            {
                "layer": "fixes",
                "reason": f"cannot read findings store at {store_path}: {exc}",
            }
        )
        return

    try:
        missing = [key for key in fixes if get_finding(conn, key) is None]
        if missing:
            findings.append(
                _ValidateFinding(
                    "fixes",
                    f"spec declares unknown finding key(s): {', '.join(missing)} "
                    f"(store: {store_path})",
                )
            )
        else:
            information.append(
                _ValidateFinding(
                    "fixes",
                    f"verified {len(fixes)} finding key(s) against {store_path}",
                )
            )
    finally:
        conn.close()

    checked.append("fixes")


def _check_workgraph(graph: WorkGraph, findings: list[_ValidateFinding]) -> None:
    try:
        validate_workgraph(graph, _vacuous_registry(graph))
    except WorkGraphError as error:
        findings.append(_ValidateFinding("workgraph", str(error)))


def _check_personas(graph: WorkGraph, findings: list[_ValidateFinding]) -> None:
    try:
        personas = load_personas()
    except ConfigError as error:
        findings.append(_ValidateFinding("persona_registry", str(error)))
        return

    for node in graph.nodes:
        if node.persona not in personas:
            known = ", ".join(sorted(personas)) or "<empty registry>"
            findings.append(
                _ValidateFinding(
                    "persona_registry",
                    f"node '{node.id}': persona '{node.persona}' is not in the "
                    f"persona registry (known: {known})",
                )
            )


def _candidate_graph(spec_text: str, epic_id: str) -> WorkGraph:
    """A minimal graph from parsed stories so persona checks survive derivation failures.

    Every derived node uses the minimal interpreter's persona (the deriver never
    reads personas), so when the real graph is unavailable we build the same
    shape from the story keys the criteria parser found. A parse failure yields
    an empty graph, which simply means no persona finding is possible this layer.
    """
    try:
        requirements = parse_spec(spec_text)
    except Exception:
        return WorkGraph(
            epic_id=epic_id,
            feature=epic_id,
            specs_root="",
            target_repo="",
            nodes=[],
        )

    nodes: list[WorkNode] = []
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.kind is not RequirementKind.STORY:
            continue
        node_id = requirement.key.lower()
        if node_id in seen:
            continue
        seen.add(node_id)
        nodes.append(
            WorkNode(
                id=node_id,
                story_key=requirement.key,
                persona="implementer",
                spec_ref=f"{epic_id}:{requirement.key}",
                requirement_keys=[requirement.key],
                depends_on=[],
                depends_on_merged=[],
                timeout_override_s=None,
            )
        )
    return WorkGraph(
        epic_id=epic_id,
        feature=epic_id,
        specs_root="",
        target_repo="",
        nodes=nodes,
    )


def _check_scenario_coverage(
    spec_dir: Path, spec_text: str, findings: list[_ValidateFinding]
) -> None:
    try:
        requirements = parse_spec(spec_text)
    except Exception as error:
        # A spec that does not parse is already reported by the work-graph layer;
        # do not double-report here.
        return

    declared: set[str] = set()
    for requirement in requirements:
        for scenario in getattr(requirement, "scenarios", ()):
            scenario_id = getattr(scenario, "scenario_id", None)
            if scenario_id is not None:
                declared.add(scenario_id)

    tasks_path = spec_dir / "tasks.md"
    if not tasks_path.is_file():
        findings.append(
            _ValidateFinding(
                "scenario_coverage",
                f"{tasks_path} is missing; cannot check scenario coverage",
            )
        )
        return

    tasks_text = tasks_path.read_text(encoding="utf-8")
    referenced = set(_SCENARIO_ID_RE.findall(tasks_text))
    uncovered = sorted(declared - referenced)
    if uncovered:
        findings.append(
            _ValidateFinding(
                "scenario_coverage",
                f"acceptance scenarios with no task reference: {', '.join(uncovered)}",
                severity="advisory",
            )
        )
