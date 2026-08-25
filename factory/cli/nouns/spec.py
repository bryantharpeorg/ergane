"""The `spec` noun: list, validate, derive, new, landed.

Everything that costs money to run lives elsewhere; this noun is the cheap
room.  It reuses the existing handlers from `factory.roadmap.cli` and
`factory.workgraph.cli` for human rendering, and adds `--json` over the same
objects.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.cli.nouns import Noun
from factory.config import ConfigError, Persona, WriteScope, load_personas
from factory.doctor.scaffold import scaffold_spec
from factory.roadmap.cli import (
    _OperatorError as RoadmapOperatorError,
    _render_roadmap,
    render_command,
)
from factory.roadmap.models import RoadmapError, SpecState, compute_readiness, read_roadmap
from factory.verify.criteria import parse_spec
from factory.verify.models import RequirementKind
from factory.workgraph.cli import (
    DEFAULT_SPECS_ROOT,
    SPEC_NAME,
    _OperatorError as WorkgraphOperatorError,
    _resolve_identity_path,
    _target_repo_for_spec,
    derive_command,
    landed_command,
    workflow_id,
)
from factory.workgraph.contention import _BARE_EXTENSIONS, _FILENAME_RE
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph, WorkGraphError, WorkNode, validate_workgraph
from factory.workgraph.preflight import check_prompt_assembly, check_slice_coverage
from factory.workgraph.prompt import TASKS_DOCUMENT, task_slice_bounds
from factory.workgraph.worktree import landing_branch

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


def _translate_old_error(error: Exception) -> OperatorError:
    """Convert the old per-module _OperatorError to the shared boundary type."""
    if isinstance(error, (RoadmapOperatorError, WorkgraphOperatorError)):
        code = error.code if error.code != EXIT_USER else EXIT_USER
        # The old EXIT_TRANSPORT value is 2, which is EXIT_USAGE under the new
        # contract.  Map it to the new transport code.
        if code == 2:
            code = EXIT_TRANSPORT
        return OperatorError(str(error), code=code)
    raise error


def _add_spec_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("spec", help="work with specs: list, validate, derive, landed")
    commands = parser.add_subparsers(dest="verb", required=True)

    list_cmd = commands.add_parser(
        "list", help="render every spec under <specs-root>/spec.md with state and blockers"
    )
    list_cmd.add_argument(
        "specs_root",
        nargs="?",
        default=DEFAULT_SPECS_ROOT,
        help=f"the specs root to scan (default: {DEFAULT_SPECS_ROOT})",
    )
    list_cmd.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the roadmap and readiness documents instead of the table",
    )
    list_cmd.set_defaults(run=_list_command)

    validate_cmd = commands.add_parser(
        "validate", help="run frontmatter, work-graph and persona checks on one spec"
    )
    validate_cmd.add_argument("spec_dir", help="the feature directory holding spec.md")
    validate_cmd.add_argument(
        "--target-repo",
        default="/srv/factory/targets/short-links",
        help="worker-host path to the target repo (default: /srv/factory/targets/short-links)",
    )
    validate_cmd.add_argument(
        "--specs-root",
        default=DEFAULT_SPECS_ROOT,
        help=f"where the worker finds feature specs (default: {DEFAULT_SPECS_ROOT})",
    )
    validate_cmd.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print a JSON report instead of the human summary",
    )
    validate_cmd.set_defaults(run=_validate_command)

    derive_cmd = commands.add_parser(
        "derive", help="compile <spec-dir>/spec.md into workgraph.json"
    )
    derive_cmd.add_argument("spec_dir", help="the feature directory holding spec.md")
    derive_cmd.add_argument(
        "--target-repo",
        required=True,
        help="worker-host path to the repository the epic builds in",
    )
    derive_cmd.add_argument(
        "--specs-root",
        default=DEFAULT_SPECS_ROOT,
        help=f"where the worker finds feature specs (default: {DEFAULT_SPECS_ROOT})",
    )
    derive_cmd.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the artifact here instead of <spec-dir>/workgraph.json",
    )
    derive_cmd.add_argument(
        "--delta",
        action="store_true",
        help="derive only the work that remains against the landed baseline",
    )
    derive_cmd.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the compiled graph as JSON instead of the artifact path",
    )
    derive_cmd.set_defaults(run=_derive_command)

    new_cmd = commands.add_parser(
        "new", help="scaffold a numbered spec directory under <specs-root>"
    )
    new_cmd.add_argument("slug", help="the feature slug for the new spec")
    new_cmd.add_argument(
        "--target-repo",
        required=True,
        help="worker-host path to the repository the epic builds in",
    )
    new_cmd.add_argument(
        "--specs-root",
        default=DEFAULT_SPECS_ROOT,
        help=f"where the new spec directory is created (default: {DEFAULT_SPECS_ROOT})",
    )
    new_cmd.add_argument(
        "--title",
        default=None,
        help="human-readable title for the worked story (default: the slug)",
    )
    new_cmd.set_defaults(run=_new_command)

    landed_cmd = commands.add_parser(
        "landed", help="report landed facts for <spec-dir>/spec.md"
    )
    landed_cmd.add_argument("spec_dir", help="the feature directory holding spec.md")
    landed_cmd.add_argument(
        "--default-branch",
        default=None,
        help="default branch to scan for landing attributions (default: read from manifest, else main)",
    )
    landed_cmd.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the landed facts as JSON instead of the human view",
    )
    landed_cmd.set_defaults(run=_landed_command)


NOUN = Noun(
    name="spec",
    summary="work with specs: list, validate, derive, new, landed",
    order=20,
    add_parser=_add_spec_parser,
)


# --- list --------------------------------------------------------------------


def _list_command(args: argparse.Namespace) -> int:
    try:
        return render_command(args)
    except (RoadmapOperatorError, WorkgraphOperatorError) as error:
        raise _translate_old_error(error) from error


# --- derive ------------------------------------------------------------------


def _derive_command(args: argparse.Namespace) -> int:
    try:
        return derive_command(args)
    except (RoadmapOperatorError, WorkgraphOperatorError) as error:
        raise _translate_old_error(error) from error


# --- new ---------------------------------------------------------------------


#: Direct child directory name matching `<NNN>-<slug>`.
_SPEC_NUMBER_RE = re.compile(r"^(\d+)-")


def _pick_spec_number(specs_root: Path, slug: str) -> str:
    """Return the next free three-digit spec number, or raise OperatorError."""
    seen: dict[int, list[str]] = {}
    slug_pattern = re.compile(rf"^\d+-{re.escape(slug)}$")
    for entry in specs_root.iterdir():
        if not entry.is_dir():
            continue
        if slug_pattern.match(entry.name):
            raise OperatorError(
                f"spec directory {entry.resolve()} already exists; spec new refuses to overwrite"
            )
        match = _SPEC_NUMBER_RE.match(entry.name)
        if not match:
            continue
        number = int(match.group(1))
        seen.setdefault(number, []).append(entry.name)

    duplicates = [number for number, names in seen.items() if len(names) > 1]
    if duplicates:
        duplicates.sort()
        raise OperatorError(
            f"specs root {specs_root} has multiple directories claiming number "
            f"{', '.join(f'{n:03d}' for n in duplicates)}; refusing to guess"
        )

    next_number = max(seen, default=0) + 1
    return f"{next_number:03d}"


def _pick_anchor(target_repo: Path) -> str:
    """Pick a tracked `path:line` anchor that resolves, or raise OperatorError."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(target_repo), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise OperatorError(
            f"cannot list tracked files in {target_repo.resolve()}: {error.stderr.strip()}",
            code=EXIT_USER,
        ) from error

    candidates: list[str] = []
    for line in completed.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        tail = path.rpartition("/")[2]
        if _FILENAME_RE.match(tail) is None:
            continue
        _, _, extension = tail.rpartition(".")
        if not path.rpartition("/")[1] and extension.lower() not in _BARE_EXTENSIONS:
            continue
        candidates.append(path)

    candidates.sort()

    for path in candidates:
        file_path = target_repo / path
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for index, text in enumerate(lines, start=1):
            if text.strip():
                return f"{path}:{index}"

    raise OperatorError(
        f"target repository {target_repo.resolve()} offers no tracked file with an "
        f"eligible extension ({', '.join(sorted(_BARE_EXTENSIONS))}) that contains a "
        "resolvable line for an anchor"
    )


def _persona_install_hint() -> bool:
    """True when the deriver's default persona is not resolvable from the registry."""
    from factory.config import load_personas as _load_personas
    from factory.workgraph.derive import IMPLEMENTER

    try:
        personas = _load_personas()
    except ConfigError:
        return True
    return IMPLEMENTER not in personas


def _new_command(args: argparse.Namespace) -> int:
    specs_root = Path(args.specs_root)
    specs_root.mkdir(parents=True, exist_ok=True)

    try:
        target_repo = Path(
            _resolve_identity_path(args.target_repo, "--target-repo", must_exist=True)
        )
    except WorkgraphOperatorError as error:
        raise _translate_old_error(error) from error

    number = _pick_spec_number(specs_root, args.slug)
    anchor = _pick_anchor(target_repo)
    title = args.title or args.slug

    spec_text, plan_text, tasks_text = scaffold_spec(
        slug=args.slug, title=title, anchor=anchor
    )

    spec_dir = specs_root / f"{number}-{args.slug}"
    with tempfile.TemporaryDirectory(
        dir=specs_root, prefix=f".tmp-new-{args.slug}-"
    ) as tmp:
        temp_dir = Path(tmp)
        (temp_dir / "spec.md").write_text(spec_text, encoding="utf-8")
        (temp_dir / "plan.md").write_text(plan_text, encoding="utf-8")
        (temp_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")

        try:
            graph = derive_workgraph(
                spec_text,
                epic_id=f"{number}-{args.slug}",
                feature=f"{number}-{args.slug}",
                specs_root=str(specs_root.resolve()),
                target_repo=str(target_repo.resolve()),
                tasks_text=tasks_text,
            )
        except DerivationError as error:
            raise OperatorError(f"scaffold does not compile: {error}") from error

        for node in graph.nodes:
            try:
                task_slice_bounds(node, tasks_text)
            except Exception as error:
                raise OperatorError(
                    f"scaffold task slice for {node.id} does not resolve: {error}"
                ) from error

        temp_dir.rename(spec_dir)

    spec_dir_abs = spec_dir.resolve()
    print(spec_dir_abs)
    print("next, run:")
    print(f"  ergane spec validate {spec_dir_abs} --target-repo {target_repo.resolve()}")
    if _persona_install_hint():
        print("  ergane install")
    return EXIT_OK


# --- landed ------------------------------------------------------------------


def _landed_command(args: argparse.Namespace) -> int:
    try:
        return landed_command(args)
    except (RoadmapOperatorError, WorkgraphOperatorError) as error:
        raise _translate_old_error(error) from error


# --- validate ----------------------------------------------------------------


class _ValidateFinding:
    def __init__(self, layer: str, message: str, *, severity: str = "refusal") -> None:
        self.layer = layer
        self.message = message
        self.severity = severity


def _validate_command(args: argparse.Namespace) -> int:
    spec_dir = Path(args.spec_dir)
    spec_path = spec_dir / SPEC_NAME
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError as error:
        raise OperatorError(f"cannot read {spec_path}: {error}") from error

    epic_id = spec_dir.resolve().name
    findings: list[_ValidateFinding] = []
    # Stated, never counted: 044 FR-006's orphan task ids are a fact the author
    # confirms or acts on, not a refusal, so they ride a separate list and the
    # exit code below reads `findings` alone.
    information: list[_ValidateFinding] = []

    # 1. Frontmatter grammar against the spec's own corpus.
    _check_frontmatter(spec_dir, epic_id, findings)

    # 2. Work-graph derivation.
    #
    # Derived against `tasks.md` when there is one (069-US2): an overlap whose
    # only ordering would close a cycle is a refusal an author must meet here
    # rather than at `spec derive`.
    tasks_text = _tasks_text(spec_dir)
    graph: WorkGraph | None = None
    try:
        graph = derive_workgraph(
            spec_text,
            epic_id=epic_id,
            feature=epic_id,
            specs_root=args.specs_root,
            target_repo=args.target_repo,
            tasks_text=tasks_text,
        )
    except DerivationError as error:
        findings.append(_ValidateFinding("workgraph", str(error)))

    # 3. Structural work-graph validation and persona-registry check.
    if graph is not None:
        _check_workgraph(graph, findings)
        _check_personas(graph, findings)
    else:
        # Derivation failed, but the spec still declares stories and the
        # registry check is meaningful: a missing persona is a dispatch-time
        # failure no matter why the graph did not compile (FR-007).
        _check_personas(_candidate_graph(spec_text, epic_id), findings)

    # 4. Scenario coverage across spec.md and tasks.md.
    _check_scenario_coverage(spec_dir, spec_text, findings)

    checked = [
        "frontmatter",
        "workgraph_derivation",
        "persona_registry",
        "scenario_coverage",
    ]
    skipped: list[dict[str, str]] = []

    # 5. Every node's attempt prompt, assembled offline (044 FR-001).
    #
    # The layer that would have caught the 2026-08-15 kill: a `tasks.md` whose
    # phase headings name no story leaves every node without a task slice, and
    # until now the first thing to notice was the dispatch tick that killed the
    # epic. It runs last because it is the only layer that needs both a compiled
    # graph and the other two authored documents.
    if graph is not None:
        for assembly in check_prompt_assembly(graph, spec_dir, spec_text=spec_text):
            findings.append(_ValidateFinding("prompt_assembly", str(assembly)))
        checked.append("prompt_assembly")
    else:
        # Honesty over coverage: assembly is per node, derivation failed, and
        # there are no nodes. Reporting it as checked would grow the `checked`
        # list by a layer nobody ran — the way a preflight comes to be trusted
        # for something it never did.
        skipped.append(
            {
                "layer": "prompt_assembly",
                "reason": (
                    "the work graph did not compile, so there are no nodes to "
                    "assemble a prompt for"
                ),
            }
        )

    # 6. Which authored tasks the assembled slices drop (044 FR-005/006).
    #
    # The layer that catches what a refusal cannot: every node assembling a
    # slice is not every node being handed its work. A task written for one
    # story and left outside that story's slice is a defect; a task in no
    # slice naming no story is stated and costs nothing.
    coverage = (
        None
        if graph is None
        else check_slice_coverage(graph, spec_dir, tasks_text=tasks_text)
    )
    if coverage is not None:
        for entry in coverage:
            target = information if entry.informational else findings
            target.append(_ValidateFinding("slice_coverage", str(entry)))
        checked.append("slice_coverage")
    else:
        skipped.append(
            {
                "layer": "slice_coverage",
                "reason": (
                    "the work graph did not compile, so there are no nodes to "
                    "assemble a prompt for"
                    if graph is None
                    else "tasks.md could not be read, so it holds no slice to "
                    "measure a task against"
                ),
            }
        )

    # 7. Stories the spec declares disjoint whose task slices are not (069-US2
    #    FR-009).
    #
    # The check 060 needed: it asserted its stories were file-disjoint, its
    # diffs contradicted that, and only landing order saved it. An advisory, not
    # a refusal — derivation has already ordered the pair — because what the
    # author is owed is that their declared independence and their own task
    # prose disagree.
    if graph is not None and tasks_text is not None:
        for edge in graph.inferred_edges:
            findings.append(
                _ValidateFinding("slice_contention", edge.reason, severity="advisory")
            )
        checked.append("slice_contention")
    else:
        skipped.append(
            {
                "layer": "slice_contention",
                "reason": (
                    "the work graph did not compile, so there are no stories to "
                    "compare slices for"
                    if graph is None
                    else "tasks.md could not be read, so no story has a slice"
                ),
            }
        )

    report = {
        "spec_dir": str(spec_dir),
        "checked": checked,
        "skipped": skipped,
        "findings": [
            {"layer": finding.layer, "message": finding.message, "severity": finding.severity}
            for finding in findings
        ],
        "information": [
            {"layer": note.layer, "message": note.message} for note in information
        ],
    }

    has_refusal = any(finding.severity == "refusal" for finding in findings)
    has_advisory = any(finding.severity == "advisory" for finding in findings)

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        if findings:
            for finding in findings:
                if finding.severity == "advisory":
                    label = "advisory"
                else:
                    label = "refusal"
                print(
                    f"ergane spec validate — {label}: [{finding.layer}] {finding.message}",
                    file=sys.stderr,
                )
            if has_advisory and not has_refusal:
                print(
                    f"{spec_path}: frontmatter, work-graph derivation, persona registry, "
                    "scenario coverage, prompt assembly and slice coverage all pass; "
                    "see advisory above"
                )
        else:
            print(
                f"{spec_path}: frontmatter, work-graph derivation, persona registry, "
                "scenario coverage, prompt assembly and slice coverage all pass"
            )
        # Deliberately not the finding prefix, on either line below: a layer that
        # did not run is not a refusal, and neither is a fact the author is
        # merely told. A reader counting refusals must not count them.
        for entry in skipped:
            print(
                f"ergane spec validate — layer '{entry['layer']}' not checked: "
                f"{entry['reason']}",
                file=sys.stderr,
            )
        for note in information:
            print(
                f"ergane spec validate — noted, not a refusal: "
                f"[{note.layer}] {note.message}",
                file=sys.stderr,
            )

    return EXIT_USER if has_refusal else EXIT_OK


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
