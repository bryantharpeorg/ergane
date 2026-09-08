"""133-US7: the anchor-resolution checker leaves the CLI module.

The narrowest story in the chain and the second tightest by budget — one
function, `_check_anchor_resolution` (9,795 bytes at 57bf698) — and nothing
else moves. Everything the checker reads (`_spec_state`, `_severity_for_state`,
`_read_citation_files`, `_ANCHOR_RE`, `_BARE_LINE_RE`) went with US2 and is
already imported back under its own name; the moved body reads those five names
from `factory.spec.anchors`, so no import-back out of the CLI module is
possible (plan trap 17).

Four controls, one per acceptance scenario:

- **US7-S1 (T067)**: the CLI module no longer *defines*
  `_check_anchor_resolution` — asserted from the module's AST, not by
  importing a name that would still resolve through the import-back. Nothing
  else moved in this story: `_read_citation_files`, `_ANCHOR_RE` and
  `_BARE_LINE_RE` left with US2 and are asserted there (T012); the checkers
  US5 and US6 own are asserted to still be defined here.
- **US7-S2 (T068)**: the circular-import control. The moved module's source
  names no import of `factory.cli.nouns.spec`, and the five vocabulary names
  are one object in both modules — the shape trap 17 names, which can pass
  every behavioural test while doing it.
- **US7-S5 (T069)**: the checker the CLI module calls is the object defined in
  `factory.spec`, compared by identity and `__module__` (T013's assertion, one
  tier later).
- **US7-S3 (T055)**: the moved function keeps its six parameters and still
  appends `anchor_resolution` to the caller-owned `checked` list at each of
  its four exits — no documents, no citations, no citations after reporting
  the unanchorable ones, and the normal end — driven over the four conditions
  (plan trap 5), never merged into one.

Red first. `uv run pytest
tests/test_133_us7_anchor_resolution_relocation.py -q --no-header`, run against
this tree before T056 moved anything, verbatim::

    FAILED tests/test_133_us7_anchor_resolution_relocation.py::test_the_cli_module_no_longer_defines_the_resolution_checker
    FAILED tests/test_133_us7_anchor_resolution_relocation.py::test_the_moved_module_imports_nothing_from_the_cli_module
    FAILED tests/test_133_us7_anchor_resolution_relocation.py::test_the_vocabulary_the_moved_checker_reads_is_one_object_in_both_modules
    FAILED tests/test_133_us7_anchor_resolution_relocation.py::test_the_resolution_checker_the_cli_module_calls_is_defined_in_factory_spec
    FAILED tests/test_133_us7_anchor_resolution_relocation.py::test_the_moved_checker_keeps_its_parameters_and_appends_checked_at_each_of_its_four_exits
    5 failed, 0 passed

Green after the move, same command::

    5 passed
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
ANCHORS_PATH = REPO_ROOT / "factory" / "spec" / "anchors.py"

#: The five names the moved checker reads, spelled exactly as FR-016 spells
#: them. All five went with US2; this story moves only the checker.
VOCABULARY = (
    "_spec_state",
    "_severity_for_state",
    "_read_citation_files",
    "_ANCHOR_RE",
    "_BARE_LINE_RE",
)

#: The checkers US5 and US6 still own. Defined in the CLI module when this
#: story lands — their presence is the "nothing else moved" half of T067.
STILL_HERE = (
    "_check_frontmatter",
    "_check_fixes",
    "_check_workgraph",
    "_check_personas",
    "_check_scenario_coverage",
    "_check_evidence",
    "_scan_sentinels_in_trio",
    "_vacuous_registry",
)


def _module_bindings(source: str) -> set[str]:
    """Every name the module source binds at top level.

    Read from the AST rather than from `vars(module)`: the import-back T057
    binds the checker's name in the CLI module's namespace, so an attribute
    check cannot tell a definition from an import. Only the source can (the
    same helper US2's T012 uses).
    """
    bound: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)
    return bound


def _factory_spec_imports(source: str) -> set[str]:
    """Names the CLI module imports from `factory.spec` (any submodule)."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("factory.spec"):
            names.update(alias.name for alias in node.names)
    return names


def _write_trio(
    spec_dir: Path,
    *,
    state: str = "ready",
    plan: str = "# Plan\n\n",
    tasks: str = "# Tasks\n\n",
    spec_body: str = "# Feature\n\nBody.\n",
) -> str:
    """Write a minimal Spec Kit trio; return the spec.md text.

    The text is returned because `_check_anchor_resolution` takes the spec
    *text*, not the directory, for spec.md — the caller owns the read.
    """
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_text = f"---\nstate: {state}\n---\n{spec_body}"
    (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks, encoding="utf-8")
    return spec_text


def _target_tree(target_repo: Path, *, module_text: str) -> Path:
    """A target repository carrying one readable module the trios cite."""
    (target_repo / "src").mkdir(parents=True, exist_ok=True)
    (target_repo / "src" / "mod.py").write_text(module_text, encoding="utf-8")
    return target_repo


class Run(NamedTuple):
    """What one exit of `_check_anchor_resolution` left in the caller's lists."""

    result: None
    findings: list[Any]
    skipped: list[dict[str, str]]
    checked: list[str]


def _drive(
    spec_noun: Any,
    spec_dir: Path,
    spec_text: str,
    target_repo: Path,
) -> Run:
    """Drive the checker with caller-owned lists, through the CLI module's
    attribute exactly as `_validate_command` reaches it — the binding T057
    keeps alive is what this exercises.
    """
    findings: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    result = spec_noun._check_anchor_resolution(
        spec_dir, spec_text, str(target_repo), findings, skipped, checked
    )
    return Run(result, findings, skipped, checked)


# --- US7-S1 / FR-016 / trap 17: nothing left behind ---------------------------


def test_the_cli_module_no_longer_defines_the_resolution_checker() -> None:
    """T067, US7-S1. Defined in `factory.spec`, imported back, gone here.

    `_read_citation_files`, `_ANCHOR_RE` and `_BARE_LINE_RE` left with US2 and
    are asserted there (T012); a test here that re-asserts them is testing
    US2's landing, not this one. The checkers US5 and US6 own are asserted to
    still be defined here, which is the "nothing else moved" half of the
    scenario.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    bindings = _module_bindings(source)
    assert "_check_anchor_resolution" not in bindings, (
        "the resolution checker is still defined in the CLI module"
    )

    imported = _factory_spec_imports(source)
    assert "_check_anchor_resolution" in imported, (
        "the checker is not imported back from factory.spec"
    )

    still_defined = sorted(name for name in STILL_HERE if name not in bindings)
    assert still_defined == [], f"moved something this story does not own: {still_defined}"


# --- US7-S2 / FR-016 / trap 17: the circular-import control -------------------


def test_the_moved_module_imports_nothing_from_the_cli_module() -> None:
    """T068, US7-S2. The moved body reads its vocabulary from `factory.spec`.

    The task's letter: read the moved module's source and assert it contains
    no import naming `factory.cli.nouns.spec`. Asserted over every import
    statement in the AST, in both the `from … import` and the `import … as …`
    spellings, and widened to the whole of `factory.cli` because nothing in
    `factory/spec/` may import from the CLI module at all. Red pre-move: the
    no-back-import half is true today, so the control is completed by the
    decisive half — the checker must be *defined* in the moved module, which
    is false until T056 moves it.
    """
    anchors_source = ANCHORS_PATH.read_text(encoding="utf-8")
    back_imports: list[str] = []
    for node in ast.parse(anchors_source).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("factory.cli"):
            back_imports.append(f"from {node.module} import …")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("factory.cli"):
                    back_imports.append(f"import {alias.name}")
    assert back_imports == [], (
        f"factory/spec/anchors.py imports from the CLI module (trap 17): {back_imports}"
    )

    # The decisive half: the checker's home is where it is defined. A body
    # still living in the CLI module has not moved, and a body re-declared
    # here with an import back out is exactly the shape trap 17 forbids.
    assert "_check_anchor_resolution" in _module_bindings(anchors_source), (
        "the checker is not defined in factory.spec.anchors — it has not moved"
    )


def test_the_vocabulary_the_moved_checker_reads_is_one_object_in_both_modules() -> None:
    """T068's second half: the five names resolve to `factory.spec`'s objects.

    `_spec_state` and `_severity_for_state` are the pair FR-016 names
    explicitly; all five are asserted because the moved body reads them all.
    Identity — not a name match — is what distinguishes the import-back from a
    second copy of the severity rule, which the golden captures cannot catch.
    Red pre-move for the same reason T068's first half is: the checker must be
    defined in the moved module before its body can be shown to read these
    objects from there.
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec.anchors as anchors

    assert "_check_anchor_resolution" in _module_bindings(ANCHORS_PATH.read_text(encoding="utf-8")), (
        "the checker is not defined in factory.spec.anchors — it has not moved"
    )

    for name in VOCABULARY:
        assert getattr(spec_noun, name) is getattr(anchors, name), (
            f"{name} must be one object in both modules"
        )
    assert anchors._spec_state.__module__.startswith("factory.spec")
    assert anchors._severity_for_state.__module__.startswith("factory.spec")


# --- US7-S5 / FR-016: the object the CLI calls is the moved one ---------------


def test_the_resolution_checker_the_cli_module_calls_is_defined_in_factory_spec() -> None:
    """T069, US7-S5. Compare identity and `__module__`, so a re-declaration
    cannot pass as a move (T013's assertion, one tier later).
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec.anchors as anchors

    checker = spec_noun._check_anchor_resolution
    assert checker is anchors._check_anchor_resolution
    assert checker.__module__.startswith("factory.spec")


# --- US7-S3 / FR-016 / traps 5 and 7: parameters and the four exits -----------


def test_the_moved_checker_keeps_its_parameters_and_appends_checked_at_each_of_its_four_exits(
    tmp_path: Path,
) -> None:
    """T055, US7-S3. Every exit, driven against the caller's own lists.

    The moved checker accumulates into caller-owned `findings`, `skipped` and
    `checked` rather than returning a report (trap 7). It appends
    `anchor_resolution` to `checked` at four separate exits (trap 5), guarding
    "no documents", "no citations", "no citations after reporting the
    unanchorable ones" and the normal end. Hoisting them into one append at
    the caller makes the layer report as checked on a path where today it does
    not, so all four are driven and never merged. The signature is asserted
    from `inspect` so a "convenient" parameter reshuffle cannot slip through.
    """
    from factory.spec.anchors import _check_anchor_resolution

    parameters = list(inspect.signature(_check_anchor_resolution).parameters)
    assert parameters == [
        "spec_dir",
        "spec_text",
        "target_repo",
        "findings",
        "skipped",
        "checked",
    ]

    import factory.cli.nouns.spec as spec_noun
    # The CLI module must drive the very same object, not a re-declaration.
    assert spec_noun._check_anchor_resolution is _check_anchor_resolution

    module_text = "def present() -> None:\n    return None\n"
    _target_tree(tmp_path / "repo", module_text=module_text)

    # Exit 1: no authored documents — nothing to scan, but the layer still ran.
    # An empty directory with no spec text at all: plan.md and tasks.md are
    # unreadable and the spec body is empty, so `docs` stays empty.
    silent_dir = tmp_path / "specs-a" / "001-empty"
    silent_dir.mkdir(parents=True, exist_ok=True)
    run = _drive(spec_noun, silent_dir, "", tmp_path / "repo")
    assert run.result is None
    assert run.findings == []
    assert run.skipped == []
    assert run.checked == ["anchor_resolution"]

    # Exit 2: documents were read but hold no citation and no bare reference —
    # the layer ran and checked itself, with nothing to open a file for.
    trio = tmp_path / "specs-b" / "002-no-citations"
    spec_text = _write_trio(trio, plan="# Plan\n\nPlain prose, no citations.\n")
    run = _drive(spec_noun, trio, spec_text, tmp_path / "repo")
    assert run.result is None
    assert run.findings == []
    assert run.skipped == []
    assert run.checked == ["anchor_resolution"]

    # Exit 3: only unanchorable bare references — they are reported (FR-009)
    # and the layer still checks itself, with no citation to open a file for.
    trio = tmp_path / "specs-c" / "003-unanchorable"
    spec_text = _write_trio(
        trio, plan="# Plan\n\n- see `:99` for the shape of the citation.\n"
    )
    run = _drive(spec_noun, trio, spec_text, tmp_path / "repo")
    assert run.result is None
    assert run.skipped == []
    assert run.checked == ["anchor_resolution"]
    assert len(run.findings) == 1
    finding = run.findings[0]
    assert finding.layer == "anchor_resolution"
    assert finding.severity == "refusal"
    assert "is unanchorable" in finding.message
    assert "no path was cited before it in the same section" in finding.message

    # Exit 4: the normal end — the layer ran past the citation checks and
    # appends itself to `checked` whatever it found. A stale line number in a
    # readable file is a finding, graded by the moved severity rule.
    trio = tmp_path / "specs-d" / "004-stale"
    spec_text = _write_trio(
        trio, plan="# Plan\n\n- see `src/mod.py:999` for context.\n"
    )
    run = _drive(spec_noun, trio, spec_text, tmp_path / "repo")
    assert run.result is None
    assert run.skipped == []
    assert run.checked == ["anchor_resolution"]
    assert len(run.findings) == 1
    finding = run.findings[0]
    assert finding.layer == "anchor_resolution"
    assert finding.severity == "refusal"
    assert "line 999 is past end of file" in finding.message
    assert "(2 lines in `src/mod.py`)" in finding.message

    # The same stale citation in a landed spec is graded advisory (072 FR-010)
    # — the moved body reads the state rule where US2 put it.
    trio = tmp_path / "specs-e" / "005-landed"
    landed_text = _write_trio(
        trio,
        state="landed",
        plan="# Plan\n\n- see `src/mod.py:999` for context.\n",
    )
    run = _drive(spec_noun, trio, landed_text, tmp_path / "repo")
    assert run.checked == ["anchor_resolution"]
    assert [finding.severity for finding in run.findings] == ["advisory"]

    # The fifth path is not one of the four: an unreadable target repository
    # with citations to read skips the layer, and on that path `checked` is
    # NOT appended — the distinction the four separate exits carry.
    trio = tmp_path / "specs-f" / "006-unreadable-repo"
    spec_text = _write_trio(
        trio, plan="# Plan\n\n- see `src/mod.py:999` for context.\n"
    )
    run = _drive(spec_noun, trio, spec_text, tmp_path / "no-such-repo")
    assert run.result is None
    assert run.findings == []
    assert run.checked == []
    assert run.skipped == [
        {
            "layer": "anchor_resolution",
            "reason": (
                f"target repository {tmp_path / 'no-such-repo'} is not a readable directory"
            ),
        }
    ]