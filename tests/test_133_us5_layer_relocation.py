"""133-US5: the six remaining non-evidence layer bodies leave the CLI module.

The third relocation, and the one that moves the most *named* things: nine
functions, one compiled grammar and one constant, with the persona registry
they construct riding along. Every acceptance scenario has a control:

- **US5-S1 (T018)**: the CLI module no longer *defines* any of the eleven names
  — asserted from the module's AST, not by importing, because the import-back
  T023 binds the same names in the CLI module's namespace and an attribute
  check cannot tell a definition from an import (the helper US2 and US7 use).
  The three module-level names are the easily-stranded ones: `_SCENARIO_ID_RE`
  and `_vacuous_registry`/`_STRUCTURAL_TIMEOUT_S` sit at the top of the module
  a thousand lines from the bodies that read them.
- **US5-S2 (T019)**: `_check_fixes` keeps its four early returns (trap 4),
  driven over each — the silent unreadable-`spec.md` return, the no-`fixes:`
  key return, the absent-store skip, and the unopenable-store skip — with only
  the success path appending `fixes` to `checked`. The silent return is the
  one a relocation "normalises" into a skip, because it has no output to
  preserve, and normalising it double-reports the exact input the frontmatter
  layer already refuses.
- **US5-S4 (T020)**: every refusal string is unchanged and the moved
  `_check_fixes` still calls `resolve_factory_root()` rather than resolving
  the path itself — draft 129 will change what the resolver returns and says
  it will not edit its callers (trap 16), so a caller that resolves the path
  itself goes stale the day 129 lands.
- **US5-S5 (T021)**: `_vacuous_registry` is reachable at its new home and
  still answers every persona the graph names with empty `skills` — the
  assertion `tests/test_062_us3_skills.py` makes today through the CLI module
  (trap 18), which is 062-US3 FR-009's standing proof.

Red first. `uv run pytest tests/test_133_us5_layer_relocation.py -q --no-header`,
run against this tree before T022 moved anything, verbatim::

    FAILED tests/test_133_us5_layer_relocation.py::test_the_cli_module_no_longer_defines_the_layer_family
    FAILED tests/test_133_us5_layer_relocation.py::test_the_objects_the_cli_module_calls_are_defined_in_factory_spec
    FAILED tests/test_133_us5_layer_relocation.py::test_check_fixes_keeps_its_four_early_returns_and_one_appending_exit
    FAILED tests/test_133_us5_layer_relocation.py::test_the_moved_fixes_checker_still_resolves_the_store_through_resolve_factory_root
    FAILED tests/test_133_us5_layer_relocation.py::test_the_moved_bodies_keep_their_refusal_strings
    FAILED tests/test_133_us5_layer_relocation.py::test_vacuous_registry_answers_at_its_new_home_with_empty_skills
    FAILED tests/test_133_us5_layer_relocation.py::test_the_scenario_id_grammar_is_one_object_in_both_modules
    7 failed, 0 passed

Green after the move, same command::

    7 passed
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
LAYERS_PATH = REPO_ROOT / "factory" / "spec" / "layers.py"

#: The eleven names FR-011 names, spelled exactly as the task list spells them.
LAYER_FAMILY = (
    "_check_frontmatter",
    "_check_fixes",
    "_check_workgraph",
    "_check_personas",
    "_candidate_graph",
    "_check_scenario_coverage",
    "_scan_sentinels_in_trio",
    "_tasks_text",
    "_SCENARIO_ID_RE",
    "_vacuous_registry",
    "_STRUCTURAL_TIMEOUT_S",
)


def _module_bindings(source: str) -> set[str]:
    """Every name the module source binds at top level.

    Read from the AST rather than from `vars(module)`: the import-back T023
    binds these same names in the CLI module's namespace, so an attribute
    check cannot tell a definition from an import. Only the source can (the
    same helper US2's T012 and US7's T067 use).
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


# --- US5-S1 / FR-011 / trap 17: nothing left behind ---------------------------


def test_the_cli_module_no_longer_defines_the_layer_family() -> None:
    """T018, US5-S1. Eleven names defined in `factory.spec`, imported back, gone here.

    `_SCENARIO_ID_RE` is read only inside `_check_scenario_coverage`
    (`factory/cli/nouns/spec.py:1407` in the plan's tree); `_vacuous_registry`
    and the `_STRUCTURAL_TIMEOUT_S` it alone reads are read from `_check_fixes`'
    neighbours `_check_workgraph` and `_validate_command`'s persona branch.
    Leaving any of them behind makes a moved body reach back into the module it
    just left, which cannot import (trap 17).
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    bindings = _module_bindings(source)
    stranded = sorted(set(LAYER_FAMILY) & bindings)
    assert stranded == [], f"still defined in the CLI module: {stranded}"

    imported = _factory_spec_imports(source)
    unbacked = sorted(set(LAYER_FAMILY) - imported)
    assert unbacked == [], f"not imported back from factory.spec: {unbacked}"


def test_the_objects_the_cli_module_calls_are_defined_in_factory_spec() -> None:
    """T018's second half. Identity and `__module__`, so a re-declaration cannot pass.

    A compiled regex carries `re` as its `__module__`, so the grammar is
    compared by identity — the same reading US2's test gives `_SYMBOL_ANCHOR_RE`
    — and every callable by both. An import-back binds the very object; a
    re-declaration binds a different one with the same name, and that is the
    duplication this spec exists to end.
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec.layers as layers

    for name in ("_check_frontmatter", "_check_fixes", "_check_workgraph", "_check_personas",
                 "_candidate_graph", "_check_scenario_coverage", "_scan_sentinels_in_trio",
                 "_tasks_text", "_vacuous_registry"):
        obj = getattr(spec_noun, name)
        assert obj is getattr(layers, name), f"{name} must be one object in both modules"
        assert obj.__module__.startswith("factory.spec"), (
            f"{name} must carry __module__ under factory.spec, got {obj.__module__}"
        )
    assert spec_noun._SCENARIO_ID_RE is layers._SCENARIO_ID_RE
    assert spec_noun._STRUCTURAL_TIMEOUT_S == layers._STRUCTURAL_TIMEOUT_S
    assert layers._STRUCTURAL_TIMEOUT_S == 1


# --- US5-S2 / FR-011 / trap 4: the four early returns of _check_fixes ---------


class Run(NamedTuple):
    """What one exit of `_check_fixes` left in the caller's lists."""

    result: None
    findings: list[Any]
    information: list[Any]
    skipped: list[dict[str, str]]
    checked: list[str]


def _drive_check_fixes(spec_dir: Path) -> Run:
    """Drive the moved checker with caller-owned lists, through the CLI module.

    Reached as an attribute of `factory.cli.nouns.spec` exactly as
    `_validate_command` calls it — the import-back T023 keeps alive is what
    this exercises, and the object driven is asserted to be the one defined in
    `factory.spec`.
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec.layers as layers

    assert spec_noun._check_fixes is layers._check_fixes
    findings: list[Any] = []
    information: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    result = spec_noun._check_fixes(spec_dir, findings, information, skipped, checked)
    return Run(result, findings, information, skipped, checked)


_SOUND_BODY = """
## Requirements *(mandatory)*

- **FR-001**: The system MUST do the thing.

### User Story 1 - The thing happens (Priority: P1)

As the operator, I want the thing.

**Acceptance Scenarios**:

1. **Given** a thing, **When** I act, **Then** it works.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
"""


def _write_trio(
    spec_dir: Path,
    *,
    frontmatter: str = "state: draft\nfixes:\n  - a/one\n",
    tasks: str = "# Tasks\n\n## Phase 1: User Story 1 - The thing happens\n\n- [ ] T001 [US1-S1] prove it\n",
) -> Path:
    """A trio whose frontmatter is the only variable, and its tasks.md."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        f"---\n{frontmatter}---\n{_SOUND_BODY}", encoding="utf-8"
    )
    (spec_dir / "plan.md").write_text("# Plan\n\nOne reader.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks, encoding="utf-8")
    return spec_dir


def _own_store_pins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, runtime: str = "runtime"
) -> Path:
    """Point both store candidates at this test's own tree (122's rule).

    `ERGANE_ROOT` names the first candidate; `_check_fixes` resolves the store
    through `resolve_factory_root()` and `_resolve_store_path`, and the legacy
    candidate is pinned to a directory that is never created because the state
    these tests need from it is absence. Without both pins a test asserting the
    absent-store skip is vacuous on a host that has a real ledger.
    """
    import factory.doctor.cli as _doctor_cli

    runtime_root = tmp_path / runtime
    runtime_root.mkdir(exist_ok=True)
    monkeypatch.setenv("ERGANE_ROOT", str(runtime_root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-root")
    return runtime_root


def _seed_store(db_path: Path, keys: list[str]) -> None:
    """A findings store holding open rows for the given keys."""
    from factory.doctor.models import Finding, Severity, Status
    from factory.doctor.store import connect, report

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        for key in keys:
            category, _, slug = key.partition("/")
            report(
                conn,
                Finding(
                    key=key,
                    category=category,
                    severity=Severity.INFO,
                    status=Status.OPEN,
                    summary=f"Summary for {key}",
                    refs=["factory/foo.py:1"],
                    notes=None,
                    source="test",
                    occurrences=1,
                    first_seen="2026-08-29T00:00:00Z",
                    last_seen="2026-08-29T00:00:00Z",
                    promoted_spec=None,
                    resolved_at=None,
                    resolution=None,
                ),
                seen_at="2026-08-29T00:00:00Z",
            )
    finally:
        conn.close()


def test_check_fixes_keeps_its_four_early_returns_and_one_appending_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T019, US5-S2. Four early returns, one appending exit, each driven.

    The four exits are trap 4's list, and the signature is asserted from
    `inspect` so a "convenient" reshuffle cannot slip through. The silent
    OSError return appends to *no* list — the frontmatter layer already
    reports a missing spec.md, and normalising this into a skip double-reports
    the exact input that already refuses.
    """
    from factory.spec.layers import _check_fixes

    parameters = list(inspect.signature(_check_fixes).parameters)
    assert parameters == ["spec_dir", "findings", "information", "skipped", "checked"]

    # Exit 1: unreadable spec.md — silent, touching no list at all.
    runtime = _own_store_pins(monkeypatch, tmp_path)
    _seed_store(runtime / "doctor.db", ["a/one"])
    silent_dir = tmp_path / "specs-silent" / "001-unreadable"
    silent_dir.mkdir(parents=True)
    os_unreadable = silent_dir / "spec.md"
    os_unreadable.write_text("---\nstate: draft\nfixes:\n  - a/one\n---\n", encoding="utf-8")
    import os as _os

    _os.chmod(os_unreadable, 0o000)
    try:
        run = _drive_check_fixes(silent_dir)
    finally:
        _os.chmod(os_unreadable, 0o644)
    assert run.result is None
    assert run.findings == [] and run.information == [] and run.skipped == [] and run.checked == [], (
        "an unreadable spec.md must return silently and add nothing to any list"
    )

    # Exit 2: no `fixes:` key — neither checked nor skipped. A store exists, so
    # a bug that always ran the layer would have data to compare against.
    runtime = _own_store_pins(monkeypatch, tmp_path, runtime="runtime-b")
    _seed_store(runtime / "doctor.db", ["a/one"])
    trio = _write_trio(tmp_path / "specs-nofixes" / "002-no-fixes", frontmatter="state: draft\n")
    run = _drive_check_fixes(trio)
    assert run.result is None
    assert run.findings == [] and run.information == [] and run.skipped == [] and run.checked == [], (
        "a spec with no fixes: key adds neither a checked nor a skipped entry"
    )

    # Exit 3: absent store — one `skipped` entry only.
    runtime = _own_store_pins(monkeypatch, tmp_path, runtime="runtime-c")
    trio = _write_trio(tmp_path / "specs-nostore" / "003-no-store")
    run = _drive_check_fixes(trio)
    assert run.result is None
    assert run.findings == [] and run.information == [] and run.checked == []
    assert [entry["layer"] for entry in run.skipped] == ["fixes"]
    assert "no findings store at" in run.skipped[0]["reason"]
    assert str(runtime / "doctor.db") in run.skipped[0]["reason"]

    # Exit 4: unopenable store — a *different* `skipped` entry only.
    runtime = _own_store_pins(monkeypatch, tmp_path, runtime="runtime-d")
    unopenable = runtime / "doctor.db"
    unopenable.write_text("", encoding="utf-8")
    import os as _os

    _os.chmod(unopenable, 0o000)
    trio = _write_trio(tmp_path / "specs-badstore" / "004-bad-store")
    try:
        run = _drive_check_fixes(trio)
    finally:
        _os.chmod(unopenable, 0o644)
    assert run.result is None
    assert run.findings == [] and run.information == [] and run.checked == []
    assert [entry["layer"] for entry in run.skipped] == ["fixes"]
    assert "cannot read findings store at" in run.skipped[0]["reason"]

    # The success path is the only one that appends `fixes` to `checked` —
    # and the refusal for unknown keys is still graded refusal, the
    # information note for known ones still names the store path.
    runtime = _own_store_pins(monkeypatch, tmp_path, runtime="runtime-e")
    _seed_store(runtime / "doctor.db", ["a/one"])
    trio = _write_trio(tmp_path / "specs-success" / "005-success")
    run = _drive_check_fixes(trio)
    assert run.findings == []
    assert [note.message for note in run.information] == [
        f"verified 1 finding key(s) against {runtime / 'doctor.db'}"
    ]
    assert run.checked == ["fixes"]
    assert run.skipped == []

    unknown = _write_trio(tmp_path / "specs-unknown" / "006-unknown", frontmatter="state: draft\nfixes:\n  - absent/key\n")
    run = _drive_check_fixes(unknown)
    assert run.checked == ["fixes"]
    assert len(run.findings) == 1
    assert run.findings[0].layer == "fixes"
    assert run.findings[0].severity == "refusal"
    assert "spec declares unknown finding key(s): absent/key" in run.findings[0].message


# --- US5-S4 / FR-011 / trap 16: the resolver call and the refusal strings -----


def test_the_moved_fixes_checker_still_resolves_the_store_through_resolve_factory_root() -> None:
    """T020, US5-S4. The call is carried verbatim, not inlined (trap 16).

    Draft 129 changes what `resolve_factory_root()` returns and states it will
    not edit its roughly fifteen callers, so the moved body must still call it
    and hand the result to `_resolve_store_path` — not resolve or absolutise
    the path itself. Asserted from the moved module's AST: the call expression
    `resolve_factory_root()` appears, and `_resolve_store_path` is reached with
    the root it returned.
    """
    source = LAYERS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    fixes_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_check_fixes"
    )
    calls = [
        ast.unparse(node)
        for node in ast.walk(fixes_node)
        if isinstance(node, ast.Call)
    ]
    assert "resolve_factory_root()" in calls, (
        "the moved _check_fixes no longer calls resolve_factory_root() (trap 16)"
    )
    assert "_resolve_store_path" in ast.unparse(fixes_node), (
        "the moved _check_fixes no longer reaches the store path helper"
    )
    # And the resolver itself is imported from where it has always lived.
    imports = [
        ast.unparse(node)
        for node in tree.body
        if isinstance(node, (ast.ImportFrom, ast.Import))
    ]
    assert any("resolve_factory_root" in unparsed for unparsed in imports), (
        "the moved body must import resolve_factory_root from its own module"
    )


def test_the_moved_bodies_keep_their_refusal_strings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T020's second half, US5-S4. Every refusal string, character for character.

    `spec validate`'s refusals are read closely by operators and quoted in
    specs; 072's lesson is that naming the line, the rule and what the refusal
    costs downstream is the shape worth keeping (trap 9). Each string is
    asserted as the whole message, not a fragment.
    """
    import factory.cli.nouns.spec as spec_noun

    runtime = _own_store_pins(monkeypatch, tmp_path)

    # frontmatter: both branches.
    specs_root = tmp_path / "specs-fm"
    spec_dir = specs_root / "001-trio"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text("---\nstate: draft\nbogus: 1\n---\n# F\n", encoding="utf-8")
    findings: list[Any] = []
    spec_noun._check_frontmatter(spec_dir, "001-trio", findings)
    assert [f.message for f in findings] == [
        "001-trio: [unknown_key] frontmatter carries unknown key(s) 'bogus'; "
        "the grammar is 'state', 'depends_on_landed', 'fixes'"
    ]

    spec_dir_ok = specs_root / "002-ok"
    spec_dir_ok.mkdir()
    (spec_dir_ok / "spec.md").write_text("---\nstate: draft\n---\n# F\n", encoding="utf-8")
    findings = []
    import os as _os

    _os.chmod(specs_root, 0o000)
    try:
        spec_noun._check_frontmatter(spec_dir_ok, "002-ok", findings)
    finally:
        _os.chmod(specs_root, 0o755)
    assert [f.message for f in findings] == [
        f"cannot read specs root {specs_root}: [Errno 13] Permission denied: '{specs_root}'"
    ]
    assert all(f.layer == "frontmatter" and f.severity == "refusal" for f in findings)

    # workgraph: the structural refusal rides WorkGraphError's own string.
    from factory.workgraph.models import WorkGraph, WorkNode

    graph = WorkGraph(
        epic_id="e",
        feature="e",
        specs_root="s",
        target_repo="r",
        nodes=[
            WorkNode(id="us1", story_key="US1", persona="p", spec_ref="e:US1",
                     requirement_keys=["US1"], depends_on=["us2"], depends_on_merged=[], timeout_override_s=None),
            WorkNode(id="us2", story_key="US2", persona="p", spec_ref="e:US2", requirement_keys=["US2"],
                     depends_on=["us1"], depends_on_merged=[], timeout_override_s=None),
        ],
    )
    findings = []
    spec_noun._check_workgraph(graph, findings)
    assert [f.message for f in findings] == [
        "workgraph 'e': dependency cycle: us1 -> us2 -> us1"
    ]

    # persona_registry: both the ConfigError branch and the unknown-persona one.
    from factory.config import Persona, WriteScope
    import factory.config as config_module

    graph = WorkGraph(
        epic_id="e",
        feature="e",
        specs_root="s",
        target_repo="r",
        nodes=[
            WorkNode(id="us1", story_key="US1", persona="ghost", spec_ref="e:US1",
                     requirement_keys=["US1"], depends_on=[], depends_on_merged=[], timeout_override_s=None),
        ],
    )
    findings = []
    spec_noun._check_personas(graph, findings)
    known = ", ".join(sorted(config_module.load_personas()))
    assert [f.message for f in findings] == [
        f"node 'us1': persona 'ghost' is not in the persona registry (known: {known})"
    ]

    def _broken_loader() -> dict[str, Persona]:
        raise config_module.ConfigError("registry is broken on purpose")

    import factory.spec.layers as layers

    # Patched on the module the moved body reads — the body binds
    # `load_personas` at module scope, so the seam moved with it.
    original = layers.load_personas
    layers.load_personas = _broken_loader  # type: ignore[assignment]
    try:
        findings = []
        spec_noun._check_personas(graph, findings)
    finally:
        layers.load_personas = original  # type: ignore[assignment]
    assert [f.message for f in findings] == ["registry is broken on purpose"]
    assert all(f.layer == "persona_registry" and f.severity == "refusal" for f in findings)

    # scenario_coverage: the missing-tasks refusal and the advisory.
    trio = tmp_path / "specs-sc" / "003-sc"
    trio.mkdir(parents=True)
    spec_text = (
        "---\nstate: draft\n---\n\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST draw.\n\n### User Story 1 - Draw (Priority: P1)\n\n"
        "As an operator, I want it drawn.\n\n**Acceptance Scenarios**:\n\n"
        "1. **Given** a page, **When** opened, **Then** it draws.\n\n"
        "## Work Graph\n\n```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n"
    )
    (trio / "spec.md").write_text(spec_text, encoding="utf-8")
    findings = []
    spec_noun._check_scenario_coverage(trio, spec_text, findings)
    assert [f.message for f in findings] == [
        f"{trio / 'tasks.md'} is missing; cannot check scenario coverage"
    ]

    (trio / "tasks.md").write_text("# Tasks\n\n- [ ] T001 no scenario id\n", encoding="utf-8")
    findings = []
    spec_noun._check_scenario_coverage(trio, spec_text, findings)
    assert [(f.severity, f.message) for f in findings] == [
        ("advisory", "acceptance scenarios with no task reference: US1-S1")
    ]

    # fixes: the unknown-key refusal (already asserted whole in T019's success
    # block) and the two skipped strings, the second carrying the sqlite error.
    runtime = _own_store_pins(monkeypatch, tmp_path, runtime="runtime-f")
    unopenable = runtime / "doctor.db"
    unopenable.write_text("", encoding="utf-8")
    import os as _os

    _os.chmod(unopenable, 0o000)
    trio = _write_trio(tmp_path / "specs-badstore2" / "004-bad-store")
    try:
        run = _drive_check_fixes(trio)
    finally:
        _os.chmod(unopenable, 0o644)
    assert len(run.skipped) == 1
    reason = run.skipped[0]["reason"]
    assert reason.startswith(f"cannot read findings store at {unopenable}: ")

    # The fixes success-path information note is host-dependent only in the
    # store path it embeds — the note's wording is asserted whole in T019.
    assert run.skipped[0]["layer"] == "fixes"


# --- US5-S5 / FR-011 / trap 18: the vacuous registry at its new home ----------


def test_vacuous_registry_answers_at_its_new_home_with_empty_skills() -> None:
    """T021, US5-S5. The assertion `tests/test_062_us3_skills.py` makes today.

    The registry answers for every persona the graph names — `_vacuous_registry`
    exists so `validate_workgraph` checks only structural rules, not persona
    resolution — and `skills` stays empty for each (062-US3 FR-009's standing
    proof), reached at the new home rather than through the CLI module.
    """
    from factory.config import WriteScope
    from factory.spec.layers import _vacuous_registry
    from factory.workgraph.models import WorkGraph, WorkNode

    graph = WorkGraph(
        epic_id="e",
        feature="e",
        specs_root="s",
        target_repo="r",
        nodes=[
            WorkNode(id="us1", story_key="US1", persona="implementer", spec_ref="e:US1",
                     requirement_keys=["US1"], depends_on=[], depends_on_merged=[], timeout_override_s=None),
            WorkNode(id="us2", story_key="US2", persona="verifier", spec_ref="e:US2",
                     requirement_keys=["US2"], depends_on=[], depends_on_merged=[], timeout_override_s=None),
        ],
    )
    registry = _vacuous_registry(graph)
    assert sorted(registry) == ["implementer", "verifier"]
    for persona in registry.values():
        assert persona.skills == ()
        assert persona.write_scope is WriteScope.WORKTREE
        assert persona.timeout_s == 1
        assert persona.needs_worktree is True

    # The structural check the registry exists to satisfy still passes with it.
    from factory.workgraph.models import validate_workgraph

    validate_workgraph(graph, registry)

    # And the CLI module still binds the same object, so `_check_workgraph`
    # reaches the registry the story moved (trap 18's shape, asserted).
    import factory.cli.nouns.spec as spec_noun

    assert spec_noun._vacuous_registry is _vacuous_registry


# --- the module-level grammar moved with its only reader ----------------------


def test_the_scenario_id_grammar_is_one_object_in_both_modules() -> None:
    """`_SCENARIO_ID_RE` moved with `_check_scenario_coverage`, not re-declared.

    A second copy of a grammar is exactly the duplication this spec exists to
    end (trap 17's letter). The moved checker reads it from its own module;
    the CLI module binds the same object.
    """
    import factory.cli.nouns.spec as spec_noun
    import factory.spec.layers as layers

    assert spec_noun._SCENARIO_ID_RE is layers._SCENARIO_ID_RE
    assert layers._SCENARIO_ID_RE.findall("US1-S1 and US12-S34") == ["US1-S1", "US12-S34"]