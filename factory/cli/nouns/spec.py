"""The `spec` noun: list, validate, derive, new, landed.

Everything that costs money to run lives elsewhere; this noun is the cheap
room.  It reuses the existing handlers from `factory.roadmap.cli` and
`factory.workgraph.cli` for human rendering, and adds `--json` over the same
objects.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

import factory.doctor.cli as _doctor_cli
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.cli.nouns import Noun
from factory.config import ConfigError, Persona, WriteScope, load_personas
from factory.doctor.scaffold import scaffold_spec
from factory.doctor.store import connect_readonly, get_finding
from factory.doctor.triage import _declaration
from factory.roadmap.cli import (
    _OperatorError as RoadmapOperatorError,
    _render_roadmap,
    render_command,
)
from factory.roadmap.models import RoadmapError, SpecState, _split_frontmatter, compute_readiness, read_roadmap
from factory.verify.criteria import mask_fences, parse_spec
from factory.verify.diffbounds import DIFF_INPUT_LIMIT
from factory.verify.factory_yaml import (
    FactoryConfigError,
    load_factory_config,
    resolve_manifest_path,
)
from factory.verify.models import Requirement, RequirementKind, Scenario
from factory.workgraph.cli import (
    DEFAULT_SPECS_ROOT,
    SPEC_NAME,
    _OperatorError as WorkgraphOperatorError,
    _resolve_identity_path,
    _target_repo_for_spec,
    derive_command as _derive_command_impl,
    landed_command,
    workflow_id,
)
from factory.workgraph.contention import _BARE_EXTENSIONS, _FILENAME_RE
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph, WorkGraphError, WorkNode, validate_workgraph
from factory.workgraph.preflight import check_prompt_assembly, check_slice_coverage
from factory.workgraph.prompt import TASKS_DOCUMENT, task_slice_bounds
from factory.workgraph.worktree import landing_branch, resolve_factory_root

#: The id grammar the criteria parser mints for acceptance scenarios.
_SCENARIO_ID_RE = re.compile(r"US\d+-S\d+")

#: A citation inside an inline code span: `path:NN` or `path:NN-MM`.
_ANCHOR_RE = re.compile(r"`([^`]+?:\d+(?:-\d+)?)`")

#: A bare line reference inside an inline code span: `:NN` or `:NN-MM`.
_BARE_LINE_RE = re.compile(r"`:(\d+(?:-\d+)?)`")

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
    new_cmd.add_argument(
        "--fixes",
        action="append",
        default=[],
        help="finding key the spec fixes (repeatable; default: none)",
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
    spec_dir = Path(args.spec_dir)
    sentinels = _scan_sentinels_in_trio(spec_dir)
    if sentinels:
        lines = "\n".join(
            f"  {document}:{line}: {text} — not ready to derive"
            for document, line, text in sentinels
        )
        verb = "ergane spec derive"
        raise OperatorError(
            f"{spec_dir / SPEC_NAME}: refuses to derive until ERGANE-TODO sentinels are resolved; "
            f"resolve them with {verb}:\n"
            f"{lines}"
        )
    try:
        return _derive_command_impl(args)
    except (RoadmapOperatorError, WorkgraphOperatorError) as error:
        raise _translate_old_error(error) from error


def validate_spec_command(args: argparse.Namespace) -> int:
    """Public wrapper around the shipped `spec validate` handler.

    US4's `build ship` streams validate's full labeled output and returns its
    exit code without re-implementing the report.  The private name and its
    `set_defaults(run=...)` wiring stay unchanged so existing imports survive.
    """
    return _validate_command(args)


def derive_spec_command(args: argparse.Namespace) -> int:
    """Public wrapper around the shipped `spec derive` handler.

    US4's `build ship` streams derive's full labeled output and returns its
    exit code.  The sentinel gate lives in the private `_derive_command`, which
    this delegates to unchanged.
    """
    return _derive_command(args)


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
        slug=args.slug, title=title, anchor=anchor, fixes=args.fixes
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
    checked = [
        "frontmatter",
        "workgraph_derivation",
        "persona_registry",
        "scenario_coverage",
    ]
    skipped: list[dict[str, str]] = []

    # 1. Frontmatter grammar against the spec's own corpus.
    _check_frontmatter(spec_dir, epic_id, findings)

    # 2. `fixes:` declarations, if any, against the findings ledger.
    _check_fixes(spec_dir, findings, information, skipped, checked)

    # 3. Work-graph derivation.
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

    # 4. Structural work-graph validation and persona-registry check.
    if graph is not None:
        _check_workgraph(graph, findings)
        _check_personas(graph, findings)
    else:
        # Derivation failed, but the spec still declares stories and the
        # registry check is meaningful: a missing persona is a dispatch-time
        # failure no matter why the graph did not compile (FR-007).
        _check_personas(_candidate_graph(spec_text, epic_id), findings)

    # 5. Scenario coverage across spec.md and tasks.md.
    _check_scenario_coverage(spec_dir, spec_text, findings)

    # 6. Every node's attempt prompt, assembled offline (044 FR-001).
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

    # 8. Sentinels that mark mandatory blanks (106-US3).
    #
    # These are stated, never counted: they ride the `information` channel and do
    # not change the exit code.  The layer runs unconditionally because it only
    # reads text, so it is always reported in `checked`.
    for document, line_no, line_text in _scan_sentinels_in_trio(spec_dir):
        information.append(
            _ValidateFinding(
                "sentinel",
                f"{document}:{line_no}: {line_text.strip()} — not ready to derive",
            )
        )
    checked.append("sentinels")

    # 9. Anchor resolution: every `path:NN` citation in the authored documents
    #    opens the file it names in the target repository and reports stale
    #    anchors before dispatch (072-US1).
    #
    # It runs before the symbol check below because it answers the coarser
    # question — does the file exist, and is that line real — and the symbol
    # check leans on that: a citation whose file cannot be read is left here
    # deliberately, so the operator is told once rather than twice.
    _check_anchor_resolution(
        spec_dir, spec_text, args.target_repo, findings, skipped, checked
    )

    # 10. Whether cited Python symbols land inside their declared spans (072-US2).
    _check_symbol_anchors(spec_dir, spec_text, args.target_repo, findings, skipped, checked)

    # 11. Whether each Then-clause can be evidenced at all (102-US1), and what
    #     the judge will be shown for this spec (102-US2).
    #
    # The layer that would have saved fifteen attempts: the judge is shown the
    # story's diff and the declared gates' results, so a clause asserting an
    # outcome neither can produce is one no correct implementation can pass.
    # It runs last because it is the only layer that reads the target
    # repository's manifest, and it refuses nothing when it cannot.
    #
    # It returns the report as well as raising the refusals, because the report
    # is the answer the refusal assumes the author already has — and assembling
    # it here rather than in a second pass is what keeps the two from ever
    # disagreeing about the same spec.
    evidence = _check_evidence(spec_text, args.target_repo, findings, skipped, checked)

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
    # Absent rather than empty when there is no report to make: a test that
    # disables the evidence layer gets a document with no `judge_evidence` key,
    # which is the honest shape — no layer ran, so nothing was answered.
    if evidence is not None:
        report["judge_evidence"] = evidence.as_dict()

    has_refusal = any(finding.severity == "refusal" for finding in findings)
    has_advisory = any(finding.severity == "advisory" for finding in findings)

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        all_pass_phrases = _all_pass_phrases(checked)
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
                    f"{spec_path}: {', '.join(all_pass_phrases)} all pass; "
                    "see advisory above"
                )
        else:
            print(f"{spec_path}: {', '.join(all_pass_phrases)} all pass")
        # The report the author asked for, on stdout with the verdict rather than
        # on the diagnostic stream: it is an answer, not a complaint, and it is
        # printed whatever the verdict — an author being refused is exactly the
        # author who needs to read what the judge will have (FR-006).
        if evidence is not None:
            for line in evidence.lines(spec_path):
                print(line)
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
        if any(note.layer == "sentinel" for note in information):
            count = sum(1 for note in information if note.layer == "sentinel")
            noun = "sentinel" if count == 1 else "sentinels"
            print(
                f"{count} ERGANE-TODO {noun} remain; "
                "ergane spec derive will refuse until they are resolved.",
                file=sys.stderr,
            )

    return EXIT_USER if has_refusal else EXIT_OK


def _all_pass_phrases(checked: list[str]) -> list[str]:
    """The ordered phrases in the all-pass sentence.

    `fixes` is inserted only when the layer actually ran, so a spec that omits
    the key prints the same sentence as before this story. `anchor_resolution`
    and `symbol_anchors` are likewise appended only when their layer actually
    ran and did not skip, and in the order the layers run — a target repository
    this host does not carry skips both, and the sentence must not name a check
    nobody made.
    """
    phrases = [
        "frontmatter",
        "work-graph derivation",
        "persona registry",
        "scenario coverage",
        "prompt assembly and slice coverage",
    ]
    if "fixes" in checked:
        phrases.insert(1, "fixes")
    if "anchor_resolution" in checked:
        phrases.append("anchor resolution")
    if "symbol_anchors" in checked:
        phrases.append("symbol anchors")
    return phrases


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


#: A citation written as `path.py:NN` — `symbol` or `path.py:NN` -- `symbol`.
#: Group 1 is the path, group 2 is the line number, group 3 is the symbol name.
_SYMBOL_ANCHOR_RE = re.compile(
    r"`([^`\n]+\.py):(\d+)`\s*[-–—]{1,2}\s*`([^`\n]+)`"
)

#: States that can still dispatch; anchor findings for these are refusals.
_DISPATCHABLE_STATES = {"draft", "ready"}


def _spec_state(spec_text: str) -> str | None:
    """The declared state from frontmatter, or None when there is none."""
    block_text, _body = _split_frontmatter(spec_text)
    if block_text is None:
        return None
    try:
        loaded = yaml.safe_load(block_text)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    state = loaded.get("state")
    return state if isinstance(state, str) else None


def _severity_for_state(state: str | None) -> str:
    """Refusal for dispatchable states, advisory otherwise (072 FR-010)."""
    if state in _DISPATCHABLE_STATES:
        return "refusal"
    return "advisory"


def _symbol_spans(module_text: str) -> dict[str, list[tuple[int, int]]]:
    """Map each defined name to its 1-indexed line-span ranges.

    Names are resolved from `FunctionDef`, `AsyncFunctionDef` and `ClassDef`
    nodes using `lineno` and `end_lineno`.  A dotted citation is resolved on
    its last segment: `Widget.do_thing` is accepted if `do_thing` is defined
    inside a class named `Widget`.
    """
    try:
        tree = ast.parse(module_text)
    except SyntaxError:
        return {}

    by_name: dict[str, list[tuple[int, int]]] = {}
    class_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_names.add(node.name)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # `end_lineno` may be None in very old Python versions; the runtime
            # here is 3.12, but the defensive value keeps the type narrow.
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            by_name.setdefault(node.name, []).append((node.lineno, end))

    return by_name, class_names


def _line_hits_symbol(
    line: int, symbol: str, spans: dict[str, list[tuple[int, int]]], class_names: set[str]
) -> tuple[bool, str | None]:
    """True when `line` falls inside any definition of `symbol`.

    For a dotted name the last segment must have a span and the first segment
    must name a class.  A duplicate definition is satisfied by any matching
    span.
    """
    parts = symbol.split(".")
    root = parts[0] if len(parts) > 1 else None
    name = parts[-1]

    if root is not None and root not in class_names:
        # The first segment does not name a class; treat as absent so the
        # operator sees a distinct repair.
        return False, None

    ranges = spans.get(name, [])
    if not ranges:
        return False, "absent"

    for start, end in ranges:
        if start <= line <= end:
            return True, None

    # Outside every span: report the first known span as the actual location.
    actual = ranges[0]
    return False, f"{actual[0]}-{actual[1]}"


def _check_symbol_anchors(
    spec_dir: Path,
    spec_text: str,
    target_repo: str,
    findings: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> None:
    """Report backticked Python citations whose cited line is outside the named symbol's span.

    The convention is `` `path.py:NN` — `symbol` `` or `` `path.py:NN` -- `symbol` ``.
    A citation with no symbol name in its prose is left to the resolution check
    (072-US1).  Paths are resolved against `target_repo`; an unreadable target
    repo causes the whole layer to be skipped rather than reporting every
    citation as an absent file (072 FR-011).
    """
    target_path = Path(target_repo)
    if not target_path.is_dir():
        skipped.append(
            {
                "layer": "symbol_anchors",
                "reason": f"target repository {target_repo} is not a readable directory",
            }
        )
        return

    severity = _severity_for_state(_spec_state(spec_text))
    layer_ran = False

    # Read the authored documents, masking fenced blocks and spec.md frontmatter.
    documents: list[tuple[str, str]] = []
    for name in ("spec.md", "plan.md", TASKS_DOCUMENT):
        path = spec_dir / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if name == "spec.md":
            _block, text = _split_frontmatter(text)
        documents.append((name, text))

    if not documents:
        # No authored documents were read; nothing to check.
        return

    layer_ran = True

    # Cache: one AST parse per cited path, and one file read per path.
    file_cache: dict[str, str | None] = {}
    span_cache: dict[str, tuple[dict[str, list[tuple[int, int]]], set[str]] | None] = {}

    for doc_name, doc_text in documents:
        lines = doc_text.splitlines()
        in_code = mask_fences(lines)
        for line_no, line in enumerate(lines, start=1):
            if in_code[line_no - 1]:
                continue
            for match in _SYMBOL_ANCHOR_RE.finditer(line):
                cited_path = match.group(1)
                cited_line = int(match.group(2))
                symbol = match.group(3)

                full_path = target_path / cited_path
                path_key = str(full_path)

                if path_key not in file_cache:
                    try:
                        file_cache[path_key] = full_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        file_cache[path_key] = None

                module_text = file_cache[path_key]
                if module_text is None:
                    # The file is absent or unreadable; leave that to US1's
                    # resolution check rather than double-reporting here.
                    continue

                if path_key not in span_cache:
                    span_cache[path_key] = _symbol_spans(module_text)

                cached = span_cache[path_key]
                if cached is None:
                    # Syntax error: the layer cannot answer for this file.
                    continue

                spans, class_names = cached
                hit, reason = _line_hits_symbol(cited_line, symbol, spans, class_names)
                if hit:
                    continue

                if reason == "absent":
                    message = (
                        f"{doc_name}:{line_no}: `cited symbol {symbol}` in "
                        f"{cited_path}:{cited_line} is not defined in that file"
                    )
                elif reason is not None:
                    message = (
                        f"{doc_name}:{line_no}: {cited_path}:{cited_line} cites "
                        f"`{symbol}` which actually occupies lines {reason}"
                    )
                else:
                    # Dotted root did not name a class; report as absent symbol.
                    message = (
                        f"{doc_name}:{line_no}: `cited symbol {symbol}` in "
                        f"{cited_path}:{cited_line} is not defined in that file"
                    )

                findings.append(_ValidateFinding("symbol_anchors", message, severity=severity))

    if layer_ran:
        checked.append("symbol_anchors")


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


def _read_citation_files(target_repo: Path, paths: set[str]) -> dict[str, list[str] | None]:
    """Read every cited file once; None means the file could not be read."""
    contents: dict[str, list[str] | None] = {}
    for relative in paths:
        path = target_repo / relative
        try:
            contents[relative] = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            contents[relative] = None
    return contents


def _check_anchor_resolution(
    spec_dir: Path,
    spec_text: str,
    target_repo: str,
    findings: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> None:
    """Report every `path:NN` and `path:NN-MM` citation that does not resolve.

    Citations are read from the body of `spec.md` (frontmatter skipped),
    `plan.md`, and `tasks.md`. Citations inside fenced code blocks are ignored
    by reusing the criteria parser's fence mask. Paths are resolved against the
    target repository the command was given. When that repository cannot be read,
    the layer reports itself as skipped and produces no findings (FR-011).
    """
    target_root = Path(target_repo)

    docs: dict[str, str] = {}
    for name in ("plan.md", "tasks.md"):
        path = spec_dir / name
        try:
            docs[name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # An absent authored document has no citations, per trap 9.
            continue

    # spec.md body, not frontmatter.
    _, body = _split_frontmatter(spec_text)
    if body:
        docs["spec.md"] = body

    if not docs:
        # Nothing to scan, but the layer still ran.
        checked.append("anchor_resolution")
        return

    # Collect citations with their line numbers first, then read each file once.
    #
    # A bare `:NN` reference carries the most recently cited *path* forward within
    # the same markdown section. "Section" is bounded by a markdown heading (any
    # line starting with one or more `#` characters): that is wide enough for a
    # trap several paragraphs below its path (068's traps 3 and 4) and narrow
    # enough that a heading change is a deliberate context switch. A bullet alone
    # is too narrow — a path in one bullet should still resolve a bare reference in
    # the prose or bullets that follow under the same heading (trap 3).
    citations: list[tuple[str, int, str, str, int]] = []
    # Ranges written backwards. Held apart because they are decidable without
    # opening anything, but they are still this layer's findings and so are
    # withheld with the rest when the layer skips.
    inverted: list[tuple[str, int, str, int, int]] = []
    # Bare `:NN` or `:NN-MM` references that cannot be resolved in their section.
    unanchored: list[tuple[str, int, str]] = []
    cited_paths: set[str] = set()
    for doc_name, text in docs.items():
        lines = text.splitlines()
        in_code = mask_fences(lines)
        current_path: str | None = None
        for index, line in enumerate(lines, start=1):
            if in_code[index - 1]:
                continue
            # A heading starts a new section, so any bare reference after it must
            # find a path *below* that heading, not one carried from above.
            if line.lstrip().startswith("#"):
                current_path = None
                continue
            # Resolve bare references first, before this line's own path citation
            # updates the carrier. A bare `:NN` on the same line as a `path:NN` is
            # governed by the path on that line or an earlier one, not by itself.
            bare_match = _BARE_LINE_RE.search(line)
            if bare_match:
                bare_raw = bare_match.group(1)
                if "-" in bare_raw:
                    try:
                        bare_start = int(bare_raw.split("-", 1)[0])
                        bare_end = int(bare_raw.split("-", 1)[1])
                    except ValueError:
                        pass
                    else:
                        if current_path is None:
                            unanchored.append((doc_name, index, bare_match.group(0)))
                        else:
                            citation = f"{current_path}:{bare_raw}"
                            cited_paths.add(current_path)
                            if bare_end < bare_start:
                                inverted.append((doc_name, index, citation, bare_start, bare_end))
                            citations.append((doc_name, index, current_path, citation, bare_start))
                            citations.append((doc_name, index, current_path, citation, bare_end))
                else:
                    try:
                        bare_line = int(bare_raw)
                    except ValueError:
                        pass
                    else:
                        if current_path is None:
                            unanchored.append((doc_name, index, bare_match.group(0)))
                        else:
                            citation = f"{current_path}:{bare_raw}"
                            cited_paths.add(current_path)
                            citations.append((doc_name, index, current_path, citation, bare_line))
            for match in _ANCHOR_RE.finditer(line):
                citation = match.group(1)
                if ":" not in citation:
                    continue
                raw_path, raw_lines = citation.rsplit(":", 1)
                # Update the carrier *after* resolving any bare reference on this
                # line, so a path cited on line N governs a bare `:NN` on line N.
                current_path = raw_path
                if "-" in raw_lines:
                    try:
                        start_line, end_line = raw_lines.split("-", 1)
                        start_int = int(start_line)
                        end_int = int(end_line)
                    except ValueError:
                        continue
                    cited_paths.add(raw_path)
                    # FR-005: both endpoints are checked, and a range that runs
                    # backwards is reported on its own account — a span whose
                    # end precedes its start names no lines at all, so neither
                    # endpoint resolving would otherwise say anything.
                    if end_int < start_int:
                        inverted.append((doc_name, index, citation, start_int, end_int))
                    citations.append((doc_name, index, raw_path, citation, start_int))
                    citations.append((doc_name, index, raw_path, citation, end_int))
                else:
                    try:
                        line_int = int(raw_lines)
                    except ValueError:
                        continue
                    cited_paths.add(raw_path)
                    citations.append((doc_name, index, raw_path, citation, line_int))

    if not citations and not unanchored:
        checked.append("anchor_resolution")
        return

    # FR-010: a refusal only for a spec that can still dispatch. The 998 broken
    # anchors in landed specs are reported, but they do not fail a validate.
    severity = _severity_for_state(_spec_state(spec_text))

    # A range is two entries against one citation, so an absent file would
    # otherwise be reported twice for the same anchor. FR-004 wants the citation
    # named, not counted.
    said: set[str] = set()

    def report(message: str) -> None:
        if message in said:
            return
        said.add(message)
        findings.append(_ValidateFinding("anchor_resolution", message, severity=severity))

    for doc_name, citing_line, citation, start_int, end_int in inverted:
        report(
            f"{doc_name}:{citing_line}: `{citation}` is a range whose end "
            f"({end_int}) precedes its start ({start_int})"
        )

    # FR-009: unanchored bare references are reported even when no file can be
    # opened. They name no path, so the target-repo skip does not apply to them.
    for doc_name, citing_line, bare_text in unanchored:
        report(
            f"{doc_name}:{citing_line}: {bare_text} is unanchorable: no path was cited "
            "before it in the same section"
        )

    if not citations:
        checked.append("anchor_resolution")
        return

    contents = _read_citation_files(target_root, cited_paths)
    any_readable = any(lines is not None for lines in contents.values())
    if not any_readable:
        # FR-011: when *none* of the cited files can be read, the tree the
        # command was given is not the tree the specs cite. Skip the whole layer
        # rather than report every citation as an absent file — validate's
        # `--target-repo` default is a path most hosts do not carry, and a layer
        # that refuses instead of skipping turns every spec into a wall of false
        # refusals (trap 11).
        reason = (
            f"target repository {target_repo} is not a readable directory"
            if not target_root.is_dir()
            else f"none of the cited paths exist under target repository {target_repo}"
        )
        skipped.append({"layer": "anchor_resolution", "reason": reason})
        return

    for doc_name, citing_line, raw_path, citation, line_no in citations:
        file_lines = contents.get(raw_path)
        if file_lines is None:
            # A cited file that does not exist is a finding, even when some
            # other cited files could be read (FR-011 says skip only when the
            # tree as a whole cannot be read).
            report(
                f"{doc_name}:{citing_line}: `{citation}` points at absent file `{raw_path}`"
            )
        elif line_no < 1 or line_no > len(file_lines):
            report(
                f"{doc_name}:{citing_line}: `{citation}` line {line_no} is past end of file "
                f"({len(file_lines)} lines in `{raw_path}`)"
            )
        elif file_lines[line_no - 1].strip() == "":
            report(
                f"{doc_name}:{citing_line}: `{citation}` line {line_no} is blank in `{raw_path}`"
            )

    checked.append("anchor_resolution")


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


# --- criterion evidence (102-US1) ---------------------------------------------
#
# The whole rule, because a refusal has to be able to state it (FR-005): the
# judge is shown the story's diff and the results of the gates the target
# repository declares, and nothing else. A Then-clause is refused when it
# asserts an outcome only a running system shows *and* names neither a declared
# gate nor anything the diff itself carries.
#
# What this deliberately is not is a classifier for "runtime outcome" in English
# (plan trap 3). `_RUNTIME_MARKERS` is a closed list of the ways an author has
# actually written one, and every entry names something a diff cannot contain.
# Everything else about the rule is anchored on declarations: which gates this
# repository declares, and whether the scenario points at its own evidence.
#
# It errs towards admitting. A false refusal teaches an author to phrase around
# the checker rather than to improve the spec (trap 2), and a clause naming a
# gate outcome is exactly what spec 116 makes scoreable (trap 1) — refusing
# those would leave the pair a net loss. Run across every spec in this
# repository, the vocabulary marks thirteen clauses and refuses none of them.

#: Phrase (as the refusal quotes it) → the pattern that finds it.
_RUNTIME_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, re.compile(pattern, re.IGNORECASE))
    for phrase, pattern in (
        ("in the browser", r"in the browser"),
        ("on screen", r"on(?: the)? screen"),
        ("on the page", r"on the (?:page|site)"),
        ("in the UI", r"in the (?:UI|user interface)"),
        ("the user sees", r"(?:the|a) (?:user|visitor|reader) (?:sees|can see|will see)"),
        ("looks correct", r"looks? (?:correct|right|fine|good)"),
        (
            "renders correctly",
            r"(?:renders?|displays?|appears?|behaves?|works?) "
            r"(?:correctly|properly|as expected)",
        ),
        ("visually", r"visually"),
        ("in production", r"in production"),
        (
            "when deployed",
            r"(?:once|when|after) (?:it is |they are )?deployed|after deployment",
        ),
        ("at runtime", r"at runtime|in the running system|on the live \w+"),
        ("in CI", r"in CI\b"),
        (
            "manually verified",
            r"manual(?:ly)? (?:verif|check|confirm|observ|inspect|test)\w*"
            r"|manual (?:verification|inspection|check)",
        ),
        ("by hand", r"by (?:hand|eye|inspection)"),
        (
            "a measured duration",
            r"within \d+\s*(?:ms|milliseconds?|seconds?|minutes?)\b"
            r"|in under \d+|faster than|no slower than|takes less than",
        ),
    )
)

#: What a scenario can point at that the diff itself carries. Scanned over the
#: whole scenario, not just the clause: evidence named in a neighbouring step is
#: still evidence, and this layer's job is to catch the criterion that has none.
#: `gate` is deliberately absent — a clause is admitted by the gates a manifest
#: *declares*, never by the word.
_DIFF_EVIDENCE_RE = re.compile(
    r"proven by|committed test|\btests?\b|\bthe diff\b|paste[ds]?|artefacts?"
    r"|artifacts?|fixture|assert(?:s|ed|ing|ion|ions)?\b|\bcommitted\b",
    re.IGNORECASE,
)

#: The phrasing the refusal offers as the diff-carried alternative.
_PROVABLE_EXAMPLE = '"… — proven by a committed test"'


def _then_clauses(scenario: Scenario) -> list[str]:
    """Every `**Then**` step of one scenario, keyword stripped, lines rejoined.

    Only `**Then**` steps: a Then-clause is what the judge scores a diff against
    and what FR-001 speaks about, and widening this to the `**And**` steps that
    follow one would grow the refusal surface without an author having asked.
    """
    clauses: list[str] = []
    for step in scenario.steps:
        if not step.startswith("**Then**"):
            continue
        clause = " ".join(step[len("**Then**") :].split())
        if clause:
            clauses.append(clause)
    return clauses


def _runtime_markers(clause: str) -> list[str]:
    """The phrases in `clause` that name an outcome only a running system shows."""
    return [phrase for phrase, pattern in _RUNTIME_MARKERS if pattern.search(clause)]


def _names_a_declared_gate(clause: str, gates: frozenset[str]) -> bool:
    """True when the clause names a gate this repository actually declares."""
    return any(
        re.search(rf"\b{re.escape(gate)}\b", clause, re.IGNORECASE) for gate in gates
    )


def _manifest_declares_no_gates(path: Path) -> bool:
    """True when a readable manifest names no gate at all.

    The loader refuses such a manifest outright — schema v1 and v2 both require
    at least one gate — so this re-reads the document to tell "nothing to
    measure with" apart from "a manifest this layer could not read". They earn
    different refusals (FR-004) because they have different remedies.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    if not isinstance(document, dict):
        return False
    gates = document.get("gates")
    return gates is None or (isinstance(gates, dict) and not gates)


@dataclass(frozen=True)
class _Declarations:
    """What the target repository's manifest says about verifying a node.

    One read of one manifest, answering both questions this module asks of it:
    which gates a clause may name (102-US1) and how large a diff may be before
    the story is refused unjudged (102-US2's report). Read from the declaration
    that owns them, never inferred (constitution IX).
    """

    #: The declared gate names, or None when the manifest could not be read.
    gates: frozenset[str] | None
    #: The manifest path, quoted in every refusal and in the report.
    manifest: str
    #: The size above which a story never reaches the judge, or None when the
    #: manifest could not be read — never the default in disguise.
    refusal_bytes: int | None
    #: Why the gates are unknown; empty exactly when `gates` is not None.
    reason: str


def _declared_gates(target_repo: str) -> _Declarations:
    """What the target repository declares about verification.

    `gates` is None exactly when `reason` is set, and that pair means *skip*:
    the gates are read from the manifest that owns them (constitution IX), and a
    manifest this layer cannot read has proven no clause wrong. `validate` runs
    against a `--target-repo` that need not exist on this host at all, so this
    is the ordinary case, not the exotic one (plan trap 4).

    An empty set is not that case: it is a repository whose committed manifest
    declares nothing to measure with, which is a fact worth refusing on.
    """
    path, _name = resolve_manifest_path(target_repo)
    try:
        config = load_factory_config(path)
    except FactoryConfigError as error:
        if error.rule == "gates" and _manifest_declares_no_gates(path):
            return _Declarations(frozenset(), str(path), None, "")
        return _Declarations(
            None,
            str(path),
            None,
            f"cannot read the gates {target_repo} declares: {error}",
        )
    return _Declarations(
        frozenset(config.gates), str(path), config.diff_refusal_bytes, ""
    )


def _evidence_refusal(
    scenario_id: str,
    clause: str,
    markers: list[str],
    gates: frozenset[str],
    manifest: str,
) -> str:
    """The refusal for one clause: what it says, why nothing can show it, what to do."""
    phrases = ", ".join(f'"{phrase}"' for phrase in markers)
    if gates:
        declared = ", ".join(sorted(gates))
        reason = (
            "the judge is shown the diff and the results of the gates this "
            f"repository declares ({declared}), and the clause names neither — no "
            "declared gate, and nothing the diff itself carries"
        )
        suggestion = (
            f"name a declared gate ({declared}) whose result will reach the judge "
            f"with the diff, or restate the clause as something the diff carries — "
            f"e.g. {_PROVABLE_EXAMPLE}"
        )
    else:
        reason = (
            f"{manifest} declares no gates, so no gate result will reach the judge "
            "with the diff, and the clause names nothing the diff itself carries"
        )
        suggestion = (
            f"declare in {manifest} a gate that measures this and name that gate in "
            f"the clause, or restate the clause as something the diff carries — "
            f"e.g. {_PROVABLE_EXAMPLE}"
        )
    return (
        f'{scenario_id}: "{clause}" asserts an outcome only a running system shows '
        f"({phrases}); {reason}. To make it provable: {suggestion}"
    )


# --- what the judge will be shown (102-US2) -----------------------------------
#
# FR-006 asks validate to answer, for any spec, the question US1 answers only for
# the clauses it refuses: what evidence will this spec's judge actually have?
# Three things and no fourth — the node's diff, its own story's criteria, and the
# results of the gates the target repository declares — and an author who has
# read that sentence once needs the refusal less often.
#
# It is assembled from what the layer above already computed (FR-006, plan
# sizing): the same parse, the same manifest read, the same clause
# classification. A report that re-derived its answers could disagree with the
# check printed beside it, and the disagreement would be invisible until an epic
# was spent on whichever half was wrong.
#
# The warning form (FR-007) lives here for the same reason. A clause asserting a
# runtime outcome that rests on the committed evidence its own scenario promises
# is not unprovable — the diff will carry that test — but it is the shape the
# deadlock was made of, and an author is better served by seeing it named than by
# a false refusal that teaches them to phrase around the checker (trap 2).


@dataclass(frozen=True)
class _StoryCriteria:
    """One story's scenarios: exactly what its node's judge is given to score."""

    story: str
    title: str | None
    scenarios: list[str]


@dataclass(frozen=True)
class _BorderlineClause:
    """A clause named rather than refused (FR-007)."""

    scenario_id: str
    clause: str
    phrases: list[str]
    message: str


@dataclass(frozen=True)
class _JudgeEvidenceReport:
    """What the judge will be shown for this spec (FR-006)."""

    criteria: list[_StoryCriteria]
    declarations: _Declarations
    warnings: list[_BorderlineClause]
    refused: int
    #: True when every Then-clause names evidence one of the three can produce,
    #: False when one does not, and None when the clauses were not checked at
    #: all — an unread manifest has proven nothing either way.
    all_provable: bool | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "diff": {
                "abridged_above_bytes": DIFF_INPUT_LIMIT,
                "refused_above_bytes": self.declarations.refusal_bytes,
            },
            "criteria": [asdict(story) for story in self.criteria],
            "gates": {
                "manifest": self.declarations.manifest,
                "declared": (
                    None
                    if self.declarations.gates is None
                    else sorted(self.declarations.gates)
                ),
                "reason": self.declarations.reason,
            },
            "warnings": [asdict(warning) for warning in self.warnings],
            "all_provable": self.all_provable,
        }

    def lines(self, spec_path: Path) -> list[str]:
        """The human transcript: the three answers, then anything borderline."""
        declared = self.declarations
        diff = (
            "the diff — the node's own worktree diff and nothing else: not the "
            "tree it changed, not a terminal, not the running system. Abridged "
            f"for the judge above {DIFF_INPUT_LIMIT} bytes"
        )
        if declared.refusal_bytes is not None:
            diff += (
                f", and refused unjudged above {declared.refusal_bytes} "
                f"(`diff_refusal_bytes` in {declared.manifest})"
            )
        rendered = [f"{spec_path}: what the judge will be shown for each node", f"  {diff}."]

        rendered.append(
            "  the criteria — each node is shown its own story's scenarios, "
            "snapshotted at dispatch:"
        )
        if self.criteria:
            for story in self.criteria:
                title = f" ({story.title})" if story.title else ""
                rendered.append(
                    f"    {story.story}{title} — {', '.join(story.scenarios)}"
                )
        else:
            rendered.append("    none: this spec declares no acceptance scenario")

        if declared.gates is None:
            rendered.append(f"  the gates — not known: {declared.reason}")
        elif declared.gates:
            rendered.append(
                "  the gates — the results of the gates "
                f"{declared.manifest} declares: {', '.join(sorted(declared.gates))}"
            )
        else:
            rendered.append(
                f"  the gates — none: {declared.manifest} declares nothing to "
                "measure with"
            )

        for warning in self.warnings:
            rendered.append(f"  a warning, not a refusal: {warning.message}")
        if self.all_provable:
            rendered.append(
                "  every Then-clause names evidence one of those three can produce."
            )
        return rendered


def _borderline_warning(
    scenario_id: str, clause: str, markers: list[str], gates: frozenset[str]
) -> str:
    """Name a clause that rests entirely on the evidence its scenario promises."""
    phrases = ", ".join(f'"{phrase}"' for phrase in markers)
    if gates:
        uncovered = (
            f"no gate this repository declares ({', '.join(sorted(gates))}) measures it"
        )
    else:
        uncovered = "this repository declares no gate that could measure it"
    return (
        f'{scenario_id}: "{clause}" asserts an outcome only a running system shows '
        f"({phrases}), and {uncovered}. It is not refused — its scenario names "
        "evidence the diff will carry — but the judge will score it on that "
        "evidence and on nothing else, so the committed test has to assert what "
        "the clause claims."
    )


def _story_criteria(requirements: Sequence[Requirement]) -> list[_StoryCriteria]:
    """The scenarios each story's node will be judged against."""
    return [
        _StoryCriteria(
            story=requirement.key,
            title=requirement.title,
            scenarios=[scenario.scenario_id for scenario in requirement.scenarios],
        )
        for requirement in requirements
        if requirement.kind is RequirementKind.STORY
    ]


def _check_evidence(
    spec_text: str,
    target_repo: str,
    findings: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> _JudgeEvidenceReport:
    """Refuse what nothing can evidence, name what is borderline, report the rest.

    102-US1's refusal (FR-001) and 102-US2's report (FR-006) are one pass over
    one parse: the scenarios the report lists are the scenarios the clauses were
    read from, and the gates it names are the gates they were measured against.
    """
    declared = _declared_gates(target_repo)

    try:
        requirements = parse_spec(spec_text)
    except Exception:
        # A spec that does not parse is already reported by the work-graph
        # layer; it declares no scenario this layer could have read. Reported
        # ahead of an unreadable manifest, as it was before the report existed:
        # a spec with no scenarios is the nearer cause.
        skipped.append(
            {
                "layer": "evidence",
                "reason": (
                    "spec.md does not parse, so it declares no acceptance scenario "
                    "to check"
                ),
            }
        )
        return _JudgeEvidenceReport([], declared, [], 0, None)

    criteria = _story_criteria(requirements)
    if declared.gates is None:
        skipped.append({"layer": "evidence", "reason": declared.reason})
        return _JudgeEvidenceReport(criteria, declared, [], 0, None)

    gates = declared.gates
    warnings: list[_BorderlineClause] = []
    refused = 0

    for requirement in requirements:
        if requirement.kind is not RequirementKind.STORY:
            continue
        for scenario in requirement.scenarios:
            carries_evidence = _DIFF_EVIDENCE_RE.search(scenario.raw_text) is not None
            for clause in _then_clauses(scenario):
                markers = _runtime_markers(clause)
                if not markers:
                    continue
                if _names_a_declared_gate(clause, gates):
                    # A declared gate can produce the evidence, and its result
                    # reaches the judge with the diff. Nothing to say (trap 1).
                    continue
                if carries_evidence:
                    warnings.append(
                        _BorderlineClause(
                            scenario_id=scenario.scenario_id,
                            clause=clause,
                            phrases=markers,
                            message=_borderline_warning(
                                scenario.scenario_id, clause, markers, gates
                            ),
                        )
                    )
                    continue
                refused += 1
                findings.append(
                    _ValidateFinding(
                        "evidence",
                        _evidence_refusal(
                            scenario.scenario_id,
                            clause,
                            markers,
                            gates,
                            declared.manifest,
                        ),
                    )
                )

    checked.append("evidence")
    return _JudgeEvidenceReport(
        criteria, declared, warnings, refused, not warnings and not refused
    )
