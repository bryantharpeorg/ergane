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
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.cli.nouns import Noun
from factory.config import ConfigError, load_personas
from factory.doctor.scaffold import scaffold_spec
from factory.roadmap.cli import (
    _OperatorError as RoadmapOperatorError,
    render_command,
)
from factory.spec.composition import SpecReadError, serialise_report, validate_spec
from factory.spec.layers import _scan_sentinels_in_trio
from factory.workgraph.cli import (
    DEFAULT_SPECS_ROOT,
    SPEC_NAME,
    _OperatorError as WorkgraphOperatorError,
    _resolve_identity_path,
    derive_command as _derive_command_impl,
    landed_command,
)
from factory.workgraph.contention import _BARE_EXTENSIONS, _FILENAME_RE
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph
from factory.workgraph.prompt import TASKS_DOCUMENT, task_slice_bounds


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


def _render_validation(
    report: SpecValidation, spec_dir: Path, *, as_json: bool
) -> int:
    """Print one `SpecValidation` the way the verb has always printed it.

    The rendering US1 froze, applied to whatever report it is handed: every
    line, `_all_pass_phrases` included, stays where it is and on the stream it
    is on today — findings, skipped layers, information notes and the sentinel
    count to stderr, the all-pass sentence and the judge-evidence report to
    stdout (plan trap 19). The exit code reads the refusal channel alone: a
    finding's severity decides, never a skip or a note.

    The composition runs the layers and constructs every finding (FR-008); this
    function formats what it returns and maps `fail` to `EXIT_USER` — the one
    rule the composition deliberately left to its CLI face.
    """
    if as_json:
        print(json.dumps(serialise_report(report, str(spec_dir)), indent=2))
        return EXIT_USER if report.verdict == "fail" else EXIT_OK

    spec_path = spec_dir / SPEC_NAME
    has_refusal = report.verdict == "fail"
    has_advisory = bool(report.advisories)

    if report.findings:
        for finding in report.findings:
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
                f"{spec_path}: {', '.join(_all_pass_phrases(report.checked))} all pass; "
                "see advisory above"
            )
    else:
        print(f"{spec_path}: {', '.join(_all_pass_phrases(report.checked))} all pass")
    # The report the author asked for, on stdout with the verdict rather than
    # on the diagnostic stream: it is an answer, not a complaint, and it is
    # printed whatever the verdict — an author being refused is exactly the
    # author who needs to read what the judge will have (FR-006).
    if report.judge_evidence is not None:
        for line in report.judge_evidence.lines(spec_path):
            print(line)
    # Deliberately not the finding prefix, on either line below: a layer that
    # did not run is not a refusal, and neither is a fact the author is
    # merely told. A reader counting refusals must not count them.
    for entry in report.skipped:
        print(
            f"ergane spec validate — layer '{entry['layer']}' not checked: "
            f"{entry['reason']}",
            file=sys.stderr,
        )
    for note in report.information:
        print(
            f"ergane spec validate — noted, not a refusal: "
            f"[{note.layer}] {note.message}",
            file=sys.stderr,
        )
    if any(note.layer == "sentinel" for note in report.information):
        count = sum(1 for note in report.information if note.layer == "sentinel")
        noun = "sentinel" if count == 1 else "sentinels"
        print(
            f"{count} ERGANE-TODO {noun} remain; "
            "ergane spec derive will refuse until they are resolved.",
            file=sys.stderr,
        )

    return EXIT_USER if has_refusal else EXIT_OK


def _validate_command(args: argparse.Namespace) -> int:
    """Run the validation over one spec directory and render its report.

    US9 made this a renderer over `factory.spec.validate_spec` (FR-003, FR-008):
    the composition — all twelve layers, every finding construction, the seeded
    `checked` order — lives in `factory/spec/composition.py`, and what remains
    here is the reading of the argv, the one seam translation (a `SpecReadError`
    becomes an `OperatorError` at the boundary that owns it) and the printing.
    """
    spec_dir = Path(args.spec_dir)
    try:
        report = validate_spec(
            spec_dir,
            target_repo=args.target_repo,
            specs_root=args.specs_root,
        )
    except SpecReadError as error:
        raise OperatorError(str(error)) from error
    return _render_validation(report, spec_dir, as_json=args.as_json)


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
