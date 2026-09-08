"""133-US9: the verb is a renderer over `validate_spec`, and its output is unchanged.

US3 built the composition and left `_validate_command` running its own copy
beside it; this story deletes the duplication and proves nothing the operator
sees moved. Each task's control carries its own docstring below; the two
halves of the story are:

- **Output unchanged** (T035, T036): the verb's stdout, stderr, exit code and
  `--json` document over US1's two fixture trios still equal US1's six golden
  artifacts byte for byte — key order and the deliberate absence of
  `judge_evidence` included — with the renderer now serialising the typed
  report rather than an inline dict.
- **The seams moved** (T037, T038, T052, T053): the CLI module constructs no
  finding of its own and imports no relocated layer; the demonstration stage
  reaches the library form; the two corpus controls, re-pointed at the module
  the composition reads, still disable something; and no test reaches a
  relocated layer through the CLI module.

Red first. `uv run pytest
tests/test_133_us9_the_verb_renders_the_composition.py -q --no-header`, against
the tree as received: six failed — the typed serialisation, the finding
constructions, the argv-building demonstration stage, the vacuous corpus
controls and the import-backs FR-015 retires — and the four output guards
passed, as they must: the pre-change verb already produces the goldens, so
those assert output unchanged rather than detect a defect. T052's red ran
deeper than trap 23 predicted: `main()` re-executes every noun module per call
(`factory/cli/main.py:74`), so a rebinding on `factory.cli.nouns.spec` was lost
before the very call it wrapped — the two corpus controls had passed vacuously
since they landed. The live seam is `factory.spec.composition`, which the
re-executed module re-imports cached; T054 re-points both helpers there.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: US1's fixtures and goldens, read rather than rebuilt: the trios and their
#: six artifacts are the composition US3 tested and this story renders.
from tests.test_133_us1_typed_report_and_golden_captures import (  # noqa: E402
    CLEAN_TRIO,
    DEFECTIVE_TRIO,
    FIXTURE_REPO,
    _normalise,
    _run_validate,
)

GOLDEN = REPO_ROOT / "tests" / "golden" / "spec_validate"

CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
INSTALL_PATH = REPO_ROOT / "factory" / "cli" / "install.py"

#: The relocated layer functions and composition-only helpers FR-015 retires
#: from the CLI module. `_scan_sentinels_in_trio` is deliberately absent:
#: `_derive_command`'s sentinel gate keeps calling it through the import.
RELOCATED = (
    "_check_frontmatter",
    "_check_fixes",
    "_check_workgraph",
    "_check_personas",
    "_check_scenario_coverage",
    "_check_anchor_resolution",
    "_check_symbol_anchors",
    "_check_evidence",
    "_candidate_graph",
    "_tasks_text",
    "_vacuous_registry",
)

#: The `--json` document's key order, load-bearing byte for byte (trap 21).
JSON_KEYS = ["spec_dir", "checked", "skipped", "findings", "information", "judge_evidence"]


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """The 089 fixture's shape: one `main` call, both streams captured."""

    def invoke(*argv: str, ergane_root: Path | None = None) -> Run:
        if ergane_root is not None:
            monkeypatch.setenv("ERGANE_ROOT", str(ergane_root))
            monkeypatch.delenv("FACTORY_ROOT", raising=False)
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    from factory.cli.main import main

    return invoke


def _read_golden(name: str, stream: str) -> str:
    return (GOLDEN / name / f"{stream}.txt").read_text(encoding="utf-8")


# --- T035 / US9-S1 / FR-006: both streams, both trios, byte for byte ----------


@pytest.mark.parametrize(
    ("trio_dir", "name", "exit_code"),
    [(CLEAN_TRIO, "clean", 0), (DEFECTIVE_TRIO, "defective", 1)],
)
def test_the_trio_matches_its_goldens_on_both_streams_and_its_exit_code(
    trio_dir: Path, name: str, exit_code: int
) -> None:
    """T035. The four rendered prefixes print on no stdout capture (trap 19);
    the stderr comparison is what holds them."""
    code, stdout, stderr = _run_validate(trio_dir, as_json=False)
    assert code == exit_code, (name, code)
    assert _normalise(stdout, REPO_ROOT) == _read_golden(name, "stdout")
    assert _normalise(stderr, REPO_ROOT) == _read_golden(name, "stderr")


# --- T036 / US9-S2 / FR-007: the typed report is what --json serialises -------


@pytest.mark.parametrize(("trio_dir", "name"), [(CLEAN_TRIO, "clean"), (DEFECTIVE_TRIO, "defective")])
def test_the_json_document_matches_its_golden_byte_for_byte(
    trio_dir: Path, name: str
) -> None:
    """T036's golden half: `--json` byte for byte, key order included (trap 21)."""
    _code, json_stdout, json_stderr = _run_validate(trio_dir, as_json=True)
    assert json_stderr == "", "the --json face prints nothing on stderr"
    assert _normalise(json_stdout, REPO_ROOT) == _read_golden(name, "json")
    assert list(json.loads(json_stdout)) == JSON_KEYS


def test_the_renderer_serialises_the_typed_report_and_leaves_judge_evidence_absent(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T036's typed half: with the evidence layer disabled the report carries
    `judge_evidence=None`, and the key must be absent rather than null — what a
    `dataclasses.asdict()` over the report type would get wrong."""
    import factory.spec.composition as composition

    specs_root = tmp_path / "specs"
    spec_dir = _write_trio(specs_root / "001-json-absent", clause=None)
    monkeypatch.setenv("ERGANE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)

    original = composition._check_evidence
    composition._check_evidence = lambda *args, **kwargs: None
    try:
        result = run(
            "spec", "validate", "--json", "--target-repo", str(FIXTURE_REPO),
            "--specs-root", str(specs_root), str(spec_dir),
        )
    finally:
        composition._check_evidence = original

    document: Any = json.loads(result.stdout)
    assert "judge_evidence" not in document, "absent rather than null (trap 21)"
    assert list(document) == JSON_KEYS[:-1]
    assert document["findings"] == []
    assert "evidence" not in document["checked"]


# --- T037 / US9-S3 / FR-008: the CLI constructs no finding of its own ---------


def test_the_cli_module_constructs_no_finding_of_its_own() -> None:
    """T037, US9-S3. Five constructions sit in `_validate_command`'s body today
    (trap 2) and no `def _check_` sweep finds any of them, so the assertion is
    on the source: a construction moved into a helper still in the CLI module
    does not pass."""
    source = CLI_PATH.read_text(encoding="utf-8")
    assert "_ValidateFinding(" not in source and "SpecFinding(" not in source, (
        "the CLI module constructs a finding of its own — FR-008 names twelve "
        "layers reached through the library form, none built here"
    )
    # The AST reading, so a construction spelled across lines still fails.
    constructed = [
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("_ValidateFinding", "SpecFinding")
    ]
    assert constructed == [], f"finding constructions in the CLI module: {constructed}"


# --- T038 / US9-S4 / FR-013: the demonstration reaches the library form -------


def test_the_demonstration_obtains_its_verdict_through_the_library_form() -> None:
    """T038, US9-S4. The stage calls the library form and prints through the
    same renderer the verb uses (trap 14 — the streaming was the point, the
    argv was not)."""
    source = INSTALL_PATH.read_text(encoding="utf-8")
    assert "_spec_validate_argv" not in source, (
        "the demonstration still builds an argv list for the validate stage"
    )
    assert "validate_spec(" in source, "the stage does not reach the library form"

    # The stage is the renderer, byte for byte: drive both over the same
    # throwaway repository and assert the stage prints the verb's rendering.
    stage_lines, code = _drive_demonstration()
    assert code == 0
    assert stage_lines == _expected_rendering(), (
        "the demonstration's validate stage no longer prints what the verb "
        "prints — FR-013 requires the lines unchanged"
    )


def _drive_demonstration() -> tuple[list[str], int]:
    """Run the demonstration's validate stage, returning its lines and exit."""
    from factory.cli import install as install_module

    repo_root = _write_demo_repository()
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = install_module._demonstrate_validate(repo_root / "specs" / "001-demo", repo_root)
    assert stderr.getvalue() == "", stderr.getvalue()
    return stdout.getvalue().splitlines(), code


def _expected_rendering() -> list[str]:
    """What the verb's renderer prints for the same repository and spec."""
    from factory.cli.nouns.spec import _render_validation
    from factory.spec import validate_spec

    repo_root = _write_demo_repository()
    spec_dir = repo_root / "specs" / "001-demo"
    report = validate_spec(
        spec_dir, target_repo=str(repo_root), specs_root=str(repo_root / "specs")
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = _render_validation(report, spec_dir, as_json=False)
    assert code == 0
    assert stderr.getvalue() == ""
    return stdout.getvalue().splitlines()


#: The throwaway demonstration repository, written once and reused by both
#: drivers above so they read one tree.
_DEMO_REPO: Path | None = None


def _write_demo_repository() -> Path:
    """A throwaway repository with the demonstration spec, as install writes it."""
    global _DEMO_REPO
    if _DEMO_REPO is None:
        from factory.cli import init as init_module
        from factory.cli import install as install_module

        repo_root = Path(tempfile.mkdtemp(prefix="us9-demo-"))
        install_module._git_init(repo_root)
        init_module._write_scaffold(repo_root, install_module._demo_manifest_text())
        spec_dir = repo_root / "specs" / "001-demo"
        spec_dir.mkdir(parents=True)
        spec_text, plan_text, tasks_text = install_module.scaffold_spec(
            slug="demo", title="Demonstration",
            anchor=install_module._demo_anchor(repo_root), demonstration=True,
        )
        (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
        (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
        (spec_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")
        _DEMO_REPO = repo_root
    return _DEMO_REPO


# --- T052 / US9-S5 / FR-015: the re-pointed controls still disable something --


def test_the_re_pointed_controls_still_disable_something(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T052, US9-S5. The control on the controls: on a spec the layer refuses,
    the disabled and enabled runs must return **different** findings (trap 23
    — after T040 the CLI-module rebinding lands on a name nothing calls and
    both corpus comparisons cover nothing)."""
    from tests.test_089_validate_checks_fixes import (
        _seed_store,
        _sound_spec_dir,
        _validate_without_fixes_layer,
    )
    from tests.test_102_unprovable_criteria import _validate_without_evidence_layer

    # The 089 fixture's own pins, applied by hand: the resolved runtime root
    # holds the seeded store, the legacy candidate names a directory never
    # created, so no host ledger can answer instead (trap 6).
    import factory.doctor.cli as _doctor_cli

    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("ERGANE_ROOT", str(root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-runtime-root")
    _seed_store(root / "doctor.db", ["present/key"])

    # --- the fixes helper ---------------------------------------------------
    specs_root = tmp_path / "specs"
    fixes_dir = _sound_spec_dir(
        specs_root, "001-fixes-refusal", "state: draft\nfixes:\n  - absent/key\n"
    )
    with_layer = run(
        "spec", "validate", "--json", "--target-repo", str(REPO_ROOT),
        "--specs-root", str(specs_root), str(fixes_dir),
    )
    assert [f["layer"] for f in with_layer.json["findings"]] == ["fixes"], (
        "the fixture must carry a fixes refusal, or the comparison below is vacuous"
    )
    _code, without_doc = _validate_without_fixes_layer(run, fixes_dir, REPO_ROOT, specs_root)
    assert without_doc["findings"] != with_layer.json["findings"], (
        "disabling the fixes layer changed nothing — the control is vacuous (trap 23)"
    )

    # --- the evidence helper -------------------------------------------------
    evidence_specs_root = tmp_path / "specs-evidence"
    evidence_dir = _write_trio(evidence_specs_root / "002-evidence-refusal", clause="the page renders correctly in the browser.")
    with_layer_evidence = run(
        "spec", "validate", "--json", "--target-repo", str(REPO_ROOT),
        "--specs-root", str(evidence_specs_root), str(evidence_dir),
    )
    assert [f["layer"] for f in with_layer_evidence.json["findings"]] == ["evidence"], (
        "the fixture must carry an evidence refusal, or the comparison below is vacuous"
    )
    _code_e, without_doc_e = _validate_without_evidence_layer(run, evidence_dir, evidence_specs_root)
    assert without_doc_e["findings"] != with_layer_evidence.json["findings"], (
        "disabling the evidence layer changed nothing — the control is vacuous (trap 23)"
    )


# --- T053 / US9-S6 / FR-015, FR-008: the import-backs are retired -------------


def test_the_cli_module_imports_no_relocated_layer_function() -> None:
    """T053, US9-S6. The CLI composes no layer, so it imports none of the
    relocated ones (FR-015) — the import-back is not a contract."""
    source = CLI_PATH.read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("factory.spec"):
            imported.update(alias.name for alias in node.names)
    stranded = sorted(set(RELOCATED) & imported)
    assert stranded == [], f"the CLI module still imports relocated layers: {stranded}"


def test_no_test_reaches_a_relocated_layer_through_the_cli_module() -> None:
    """T053's second half: read each test file's AST, resolve every alias
    importing `factory.cli.nouns.spec`, and fail when a relocated name is read
    through such an alias — the scan that stops the next reacher being
    written."""
    reachers: list[str] = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cli_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "factory.cli.nouns.spec":
                cli_aliases.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "factory.cli.nouns.spec":
                        cli_aliases.add(alias.asname or alias.name.split(".")[-1])
                    elif alias.name.startswith("factory.cli.nouns.spec."):
                        cli_aliases.add(alias.asname or alias.name.rpartition(".")[2])
        if not cli_aliases:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in cli_aliases
                and node.attr in RELOCATED
            ):
                reachers.append(f"{path.relative_to(REPO_ROOT)}: {node.value.id}.{node.attr}")
    assert reachers == [], (
        "tests still reach relocated layers through factory.cli.nouns.spec: "
        + ", ".join(reachers)
    )


# --- the trio writer ----------------------------------------------------------


def _write_trio(spec_dir: Path, *, clause: str | None) -> Path:
    """A sound trio; `clause` swaps in a refusal-grade Then-clause (T052) or
    keeps "it works", which no layer refuses (T036)."""
    then = clause or "it works."
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        "---\nstate: draft\n---\n\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST do the thing.\n\n"
        "### User Story 1 - The thing happens (Priority: P1)\n\n"
        "As an operator, I want the thing.\n\n"
        "**Acceptance Scenarios**:\n\n"
        f"1. **Given** a thing, **When** I act, **Then** {then}\n\n"
        "## Work Graph\n\n```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n\nOne reader, one key.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n## Phase 1: User Story 1 - The thing happens\n\n"
        "- [ ] T001 [US1-S1] prove the thing happens\n",
        encoding="utf-8",
    )
    return spec_dir