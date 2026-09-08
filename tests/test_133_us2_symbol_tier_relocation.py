"""133-US2: the symbol tier and the anchor family's shared vocabulary leave the CLI module.

The first relocation ("it is the first relocation, so it sets the pattern the
next five follow"). Four controls, one per acceptance scenario:

- **US2-S1 (T012)**: the CLI module no longer *defines* any of the ten names —
  asserted from the module's AST, not by importing, because an import-back
  still resolves the name and would let the assertion pass over an un-moved
  symbol. `_ANCHOR_RE`/`_BARE_LINE_RE` are the two most easily stranded names:
  they sit a thousand lines above the surviving checker that reads them and
  nothing in `_validate_command` reads them at all.
- **US2-S5 (T013)**: the checker the CLI module calls is the object defined in
  `factory.spec` — compared by `__module__`, so a re-declaration cannot pass
  as a move. Re-declaring 072's symbol grammar inside `factory/spec/` is
  exactly the duplication this spec exists to end.
- **US2-S2 (T014)**: the shared-helper control. `_spec_state` and
  `_severity_for_state` are read from two call sites — the symbol checker this
  story moves and `_check_anchor_resolution`, which stays in the CLI module
  until US7. The import-back is the shape (trap 17, already solved once for
  `_ValidateFinding` in US1); a second copy of the severity rule is the defect
  the golden captures cannot catch. The pair `(still resolves as an attribute
  of the CLI module, `__module__` under `factory.spec`)` distinguishes the one
  from the other, and the surviving checker is driven over specs whose state
  moves the severity to prove the moved rule still answers it.
- **US2-S3 (T066)**: the moved checkers keep their parameters and still append
  into caller-owned `findings`, `skipped` and `checked` lists rather than
  returning a report (trap 7), across every exit of `_check_symbol_anchors`.

Red first. `uv run pytest
tests/test_133_us2_symbol_tier_relocation.py -q --no-header`, run against this
tree before T015/T016 moved anything::

    FAILED tests/test_133_us2_symbol_tier_relocation.py::test_the_cli_module_no_longer_defines_the_symbol_family
    FAILED tests/test_133_us2_symbol_tier_relocation.py::test_the_symbol_checker_the_cli_module_calls_is_defined_in_factory_spec
    FAILED tests/test_133_us2_symbol_tier_relocation.py::test_the_shared_severity_helpers_are_bound_back_and_the_surviving_checker_still_grades_by_state
    FAILED tests/test_133_us2_symbol_tier_relocation.py::test_the_moved_checker_keeps_its_signature_and_appends_into_caller_owned_lists
    4 failed, 0 passed

Green after the move, same command::

    4 passed
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"

#: The ten names FR-010 names, spelled exactly as the task list spells them.
SYMBOL_FAMILY = (
    "_check_symbol_anchors",
    "_symbol_spans",
    "_line_hits_symbol",
    "_spec_state",
    "_severity_for_state",
    "_read_citation_files",
    "_SYMBOL_ANCHOR_RE",
    "_DISPATCHABLE_STATES",
    "_ANCHOR_RE",
    "_BARE_LINE_RE",
)


def _module_bindings(source: str) -> set[str]:
    """Every name the module source binds at top level.

    Read from the AST rather than from `vars(module)`: the import-back T016
    adds binds these same names in the CLI module's namespace, so an
    attribute check cannot tell a definition from an import. Only the source
    can.
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


def _write_spec(
    spec_dir: Path,
    *,
    state: str = "ready",
    plan: str = "# Plan\n\n",
    tasks: str = "# Tasks\n\n",
    spec_body: str = "# Feature\n\nBody.\n",
) -> str:
    """Write a minimal Spec Kit trio; return the spec.md text.

    The text is returned because `_check_symbol_anchors` and
    `_check_anchor_resolution` take the spec *text*, not the directory, for
    spec.md — the caller owns the read.
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


# --- US2-S1 / FR-010 / trap 17: nothing left behind ---------------------------


def test_the_cli_module_no_longer_defines_the_symbol_family() -> None:
    """T012, US2-S1. Ten names defined in `factory.spec`, imported back, gone here.

    `_SYMBOL_ANCHOR_RE` is read only inside the checker this story moves;
    `_DISPATCHABLE_STATES` only from `_severity_for_state`; `_ANCHOR_RE` and
    `_BARE_LINE_RE` only from inside US7's checker, a thousand lines below
    where they are bound. Leaving any of them behind makes a moved body reach
    back into the module it just left, which cannot import (trap 17).
    `_check_anchor_resolution` is deliberately absent from this list — it is
    Phase 3's (US7), and it is still defined here when this story lands.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    bindings = _module_bindings(source)
    stranded = sorted(set(SYMBOL_FAMILY) & bindings)
    assert stranded == [], f"still defined in the CLI module: {stranded}"

    imported = _factory_spec_imports(source)
    unbacked = sorted(set(SYMBOL_FAMILY) - imported)
    assert unbacked == [], f"not imported back from factory.spec: {unbacked}"


# --- US2-S5 / FR-010: the object the CLI calls is the moved one ---------------


def test_the_symbol_checker_the_cli_module_calls_is_defined_in_factory_spec() -> None:
    """T013, US2-S5. Compare `__module__`, so a re-declaration cannot pass.

    The identity assertion is stricter than the scenario's letter and costs
    one line: an import-back binds the very object, a re-declaration binds a
    different one with the same name. Both assertions together make the
    shortcut fail loudly rather than quietly.
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec.anchors as anchors

    checker = spec_noun._check_symbol_anchors
    assert checker is anchors._check_symbol_anchors
    assert checker.__module__.startswith("factory.spec")
    # A compiled regex carries `re` as its `__module__`, so identity — not
    # `__module__` — is what proves the grammar was moved and not re-declared.
    assert spec_noun._SYMBOL_ANCHOR_RE is anchors._SYMBOL_ANCHOR_RE


# --- US2-S2 / FR-010 / trap 17: the shared-helper control ---------------------


def test_the_shared_severity_helpers_are_bound_back_and_the_surviving_checker_still_grades_by_state(
    tmp_path: Path,
) -> None:
    """T014, US2-S2. Import-back for the two names the surviving checker reads.

    `_spec_state` and `_severity_for_state` are read from two call sites: the
    symbol checker this story moves and `_check_anchor_resolution`, which does
    not move until US7. Both names must still resolve as attributes of the CLI
    module *and* have their `__module__` under `factory.spec` — that pair is
    what distinguishes an import-back from a second copy. Then the surviving
    checker is driven over specs whose declared state moves the severity, so a
    stale second copy of the rule would grade wrong and fail here.
    """
    import factory.cli.nouns.spec as spec_noun

    assert spec_noun._spec_state.__module__.startswith("factory.spec")
    assert spec_noun._severity_for_state.__module__.startswith("factory.spec")

    # The state rule the two helpers encode, straight from the moved source.
    module_text = "def thing() -> None:\n    pass\n"
    spec_text = _write_spec(
        tmp_path / "001-state-spec",
        state="ready",
        plan="# Plan\n\n- see `src/mod.py:999` for context.\n",
    )
    target_repo = _target_tree(tmp_path / "repo", module_text=module_text)

    run = _run_resolution(spec_noun, tmp_path, spec_text, target_repo)
    assert [finding.severity for finding in run["findings"]] == ["refusal"]

    landed_text = _write_spec(
        tmp_path / "002-landed-spec",
        state="landed",
        plan="# Plan\n\n- see `src/mod.py:999` for context.\n",
    )
    run = _run_resolution(spec_noun, tmp_path, landed_text, target_repo)
    assert [finding.severity for finding in run["findings"]] == ["advisory"]


def _run_resolution(
    spec_noun: Any, tmp_path: Path, spec_text: str, target_repo: Path
) -> dict[str, list[Any]]:
    """Drive the surviving `_check_anchor_resolution` with caller-owned lists.

    Called through the CLI module's attribute, exactly as `_validate_command`
    reaches it — the binding T016 keeps alive is what this exercises.
    """
    spec_dir = tmp_path / "resolution-specs" / "003-resolution-trio"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "plan.md").write_text("# Plan\n\n- see `src/mod.py:999` for context.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] T001 [US1-S1] first\n", encoding="utf-8")
    findings: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    result = spec_noun._check_anchor_resolution(
        spec_dir, spec_text, str(target_repo), findings, skipped, checked
    )
    assert result is None
    assert checked == ["anchor_resolution"]
    assert skipped == []
    return {"findings": findings, "skipped": skipped, "checked": checked}


# --- US2-S3 / FR-010 / traps 5 and 7: parameters and caller-owned lists -------


class Run(NamedTuple):
    """What one exit of `_check_symbol_anchors` left in the caller's lists."""

    result: None
    findings: list[Any]
    skipped: list[dict[str, str]]
    checked: list[str]


def _drive_symbol_anchors(
    spec_noun: Any,
    spec_dir: Path,
    spec_text: str,
    target_repo: Path,
) -> Run:
    findings: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    result = spec_noun._check_symbol_anchors(
        spec_dir, spec_text, str(target_repo), findings, skipped, checked
    )
    return Run(result, findings, skipped, checked)


def test_the_moved_checker_keeps_its_signature_and_appends_into_caller_owned_lists(
    tmp_path: Path,
) -> None:
    """T066, US2-S3. Every exit, driven against the caller's own lists.

    The moved checkers accumulate into caller-owned `findings`, `skipped` and
    `checked` rather than returning a report (trap 7); converting any of them
    to return a typed result while moving turns a mechanical move into a
    rewrite. `_check_symbol_anchors` has three exits (trap 5's shape, one
    story early): the target-repo skip, the silent no-documents return, and
    the normal end. All three are driven, and the signature is asserted from
    `inspect` so a "convenient" parameter reshuffle cannot slip through.
    """
    from factory.spec.anchors import _check_symbol_anchors

    parameters = list(inspect.signature(_check_symbol_anchors).parameters)
    assert parameters == ["spec_dir", "spec_text", "target_repo", "findings", "skipped", "checked"]

    import factory.cli.nouns.spec as spec_noun
    # The CLI module must drive the very same object, not a re-declaration.
    assert spec_noun._check_symbol_anchors is _check_symbol_anchors

    module_text = "def present() -> None:\n    return None\n"

    # Exit 1: unreadable target repository — the layer skips, with its reason.
    spec_text = _write_spec(tmp_path / "specs-a" / "001-trio")
    run = _drive_symbol_anchors(spec_noun, tmp_path / "specs-a" / "001-trio", spec_text, tmp_path / "no-such-repo")
    assert run.result is None
    assert run.findings == []
    assert run.checked == []
    assert run.skipped == [
        {"layer": "symbol_anchors", "reason": f"target repository {tmp_path / 'no-such-repo'} is not a readable directory"}
    ]

    # Exit 2: no authored documents read — a silent return touching no list,
    # the exit a relocation is most tempted to normalise into a skipped entry.
    # The repo must be readable so the skip does not fire first; the layer is
    # silent only because spec.md/plan.md/tasks.md are all absent.
    _target_tree(tmp_path / "repo-b", module_text=module_text)
    silent_dir = tmp_path / "specs-b" / "002-empty"
    silent_dir.mkdir(parents=True, exist_ok=True)
    run = _drive_symbol_anchors(spec_noun, silent_dir, "", tmp_path / "repo-b")
    assert run.result is None
    assert run.findings == []
    assert run.skipped == []
    assert run.checked == []

    # Exit 3: the layer ran — it appends itself to `checked`, whatever it found.
    trio = tmp_path / "specs-c" / "003-trio"
    spec_text = _write_spec(trio, state="ready")
    run = _drive_symbol_anchors(spec_noun, trio, spec_text, tmp_path / "repo-b")
    assert run.result is None
    assert run.findings == []
    assert run.skipped == []
    assert run.checked == ["symbol_anchors"]

    # And the finding path still constructs into the caller's list, graded by
    # the moved severity rule: dispatchable state means refusal.
    trio = tmp_path / "specs-d" / "004-trio"
    spec_text = _write_spec(
        trio,
        state="ready",
        plan="# Plan\n\n- built on `src/mod.py:1` -- `absent_symbol`.\n",
    )
    run = _drive_symbol_anchors(spec_noun, trio, spec_text, tmp_path / "repo-b")
    assert run.result is None
    assert run.skipped == []
    assert run.checked == ["symbol_anchors"]
    assert len(run.findings) == 1
    finding = run.findings[0]
    assert finding.layer == "symbol_anchors"
    assert finding.severity == "refusal"
    assert "absent_symbol" in finding.message
    assert "is not defined in that file" in finding.message

    # The same citation in a landed spec is graded advisory (072 FR-010).
    trio = tmp_path / "specs-e" / "005-trio"
    spec_text = _write_spec(
        trio,
        state="landed",
        plan="# Plan\n\n- built on `src/mod.py:1` -- `absent_symbol`.\n",
    )
    run = _drive_symbol_anchors(spec_noun, trio, spec_text, tmp_path / "repo-b")
    assert [finding.severity for finding in run.findings] == ["advisory"]