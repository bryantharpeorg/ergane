"""133-US9: the verb is a renderer over `validate_spec`, and its output is unchanged.

The one behavioural story in the epic: US3 built the composition and left
`_validate_command` running its own copy beside it; this story deletes the
duplication and proves nothing the operator sees moved. Six controls, one per
task:

- **T035 (US9-S1, FR-006)**: the verb's stdout **and stderr** over each of
  US1's two fixture trios each equal that trio's golden artifact byte for
  byte, and the exit code is unchanged. Both streams, because three of the
  four rendered channels print to stderr (plan trap 19) — a stdout-only
  comparison would hold none of the four prefixes.
- **T036 (US9-S2, FR-007, trap 21)**: `--json` equals each trio's golden JSON
  artifact byte for byte — key order and the deliberate absence of
  `judge_evidence` included — asserted twice: against the goldens, and
  directly against the renderer over a report whose evidence layer did not
  run, which is the shape a `dataclasses.asdict()` serialiser gets wrong.
- **T037 (US9-S3, FR-008, trap 2)**: the CLI module constructs no finding of
  its own. There are five such constructions in `_validate_command`'s body
  today, and a `def _check_` sweep finds none of them; the assertion reads
  the module source, so a construction that moved into a helper still in the
  CLI module does not pass.
- **T038 (US9-S4, FR-013, trap 14)**: `factory/cli/install.py`'s
  demonstration stage obtains its verdict through the library form rather
  than an argv list, and the lines it prints are the verb's own rendering.
- **T052 (US9-S5, FR-015, trap 23)**: the control on the controls — for a
  spec the layer refuses, the layer-disabled run and the layer-enabled run
  return **different** findings, for both re-pointed corpus helpers. Before
  T040 the rebinding lands on a name nothing calls and both runs are the same
  run; this assertion is what makes that failure red instead of green.
- **T053 (US9-S6, FR-015, FR-008, trap 22)**: the CLI module no longer
  imports the relocated layer functions at all, and no file under `tests/`
  reaches one of them as an attribute of `factory.cli.nouns.spec`.

Red first. `uv run pytest tests/test_133_us9_the_verb_renders_the_composition.py
-q --no-header`, against the tree as received (US3's verb, US8's evidence
module, the controls still rebinding `factory.cli.nouns.spec`)::

    FAILED ...::test_the_cli_module_constructs_no_finding_of_its_own
    FAILED ...::test_the_demonstration_obtains_its_verdict_through_the_library_form
    FAILED ...::test_the_re_pointed_controls_still_disable_something
    FAILED ...::test_the_cli_module_imports_no_relocated_layer_function
    4 failed, 3 passed in ...

The three that pass red are the output guards: the golden comparisons
(T035/T036) assert output *unchanged*, and the pre-change verb already
produces it — they are the artifact US9 must not disturb, not a defect
detector. The four that fail red fail on the seams this story moves: the
five finding constructions, the argv-building demonstration stage, the
vacuous corpus controls and the import-backs FR-015 retires.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import re
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

#: The relocated layer functions and the composition-only helpers FR-015
#: retires from the CLI module. `_scan_sentinels_in_trio` is deliberately
#: absent: `_derive_command`'s sentinel gate keeps calling it through the
#: import (the plan's what-is-left list).
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


# --- T035 / US9-S1 / FR-006: both streams, both trios, byte for byte ----------


@pytest.mark.parametrize(
    ("trio_dir", "name", "exit_code"),
    [(CLEAN_TRIO, "clean", 0), (DEFECTIVE_TRIO, "defective", 1)],
)
def test_the_trio_matches_its_goldens_on_both_streams_and_its_exit_code(
    trio_dir: Path, name: str, exit_code: int
) -> None:
    """T035. stdout, stderr and the exit code, each against US1's artifacts.

    The clean trio's stdout carries the all-pass sentence; the defective trio
    never prints one. The four rendered prefixes this story's rewrite of the
    renderer would otherwise change unobserved live only in the stderr
    artifacts — `— refusal:`, `— advisory:`, `— layer 'X' not checked:` and
    `— noted, not a refusal:` are printed on no stdout capture (plan trap 19).
    """
    code, stdout, stderr = _run_validate(trio_dir, as_json=False)
    assert code == exit_code, (name, code)
    assert _normalise(stdout, REPO_ROOT) == _read_golden(name, "stdout")
    assert _normalise(stderr, REPO_ROOT) == _read_golden(name, "stderr")


def _read_golden(name: str, stream: str) -> str:
    return (GOLDEN / name / f"{stream}.txt").read_text(encoding="utf-8")


# --- T036 / US9-S2 / FR-007: the typed report is what --json serialises -------


@pytest.mark.parametrize(("trio_dir", "name"), [(CLEAN_TRIO, "clean"), (DEFECTIVE_TRIO, "defective")])
def test_the_json_document_matches_its_golden_byte_for_byte(
    trio_dir: Path, name: str
) -> None:
    """T036's golden half. The `--json` face, byte for byte after normalising.

    Key order (`spec_dir`, `checked`, `skipped`, `findings`, `information`,
    `judge_evidence` appended only when there is a report) and the deliberate
    absence of `judge_evidence` are part of what byte-for-byte means (trap
    21) — the artifact encodes both, so a serialiser that reorders or emits
    `null` fails here.
    """
    _code, json_stdout, json_stderr = _run_validate(trio_dir, as_json=True)
    assert json_stderr == "", "the --json face prints nothing on stderr"
    assert _normalise(json_stdout, REPO_ROOT) == _read_golden(name, "json")

    document: Any = json.loads(json_stdout)
    assert list(document) == [
        "spec_dir",
        "checked",
        "skipped",
        "findings",
        "information",
        "judge_evidence",
    ]


def test_the_renderer_serialises_the_typed_report_and_leaves_judge_evidence_absent(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T036's typed half. The document comes from the report, key order intact.

    Driven with the evidence layer disabled (the same rebinding T054 proves
    effective), so the report carries `judge_evidence=None` and the document
    must leave the key absent rather than null — the shape the inline dict
    had and a `dataclasses.asdict()` over the report type would not.
    """
    import factory.spec.composition as composition

    specs_root = tmp_path / "specs"
    spec_dir = _write_sound_trio(specs_root / "001-json-absent")
    monkeypatch.setenv("ERGANE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)

    original = composition._check_evidence
    composition._check_evidence = lambda *args, **kwargs: None
    try:
        result = run(
            "spec",
            "validate",
            "--json",
            "--target-repo",
            str(FIXTURE_REPO),
            "--specs-root",
            str(specs_root),
            str(spec_dir),
        )
    finally:
        composition._check_evidence = original

    document: Any = json.loads(result.stdout)
    assert "judge_evidence" not in document, "absent rather than null (trap 21)"
    assert list(document) == [
        "spec_dir",
        "checked",
        "skipped",
        "findings",
        "information",
    ]
    assert document["findings"] == []
    assert "evidence" not in document["checked"]


# --- T037 / US9-S3 / FR-008: the CLI constructs no finding of its own ---------


def test_the_cli_module_constructs_no_finding_of_its_own() -> None:
    """T037, US9-S3. Read the module source; assert no finding construction.

    There are five constructions in `_validate_command`'s body today (plan
    trap 2): the `DerivationError` refusal, `prompt_assembly`,
    `slice_coverage` — the line that routes on `entry.informational` —
    `slice_contention` and the `sentinel` note. A `def _check_` sweep finds
    none of them, so the assertion is on the source: a construction that
    moved into a helper still in the CLI module does not pass.
    """
    source = CLI_PATH.read_text(encoding="utf-8")

    assert "_ValidateFinding(" not in source, (
        "the CLI module constructs a finding of its own — FR-008 names twelve "
        "layers reached through the library form, none built here"
    )
    assert "SpecFinding(" not in source

    # The AST reading, so a construction spelled across lines still fails:
    # no call in the module may target the finding type under either name.
    tree = ast.parse(source)
    constructed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("_ValidateFinding", "SpecFinding"):
                constructed.append(node.func.id)
    assert constructed == [], f"finding constructions in the CLI module: {constructed}"


# --- T038 / US9-S4 / FR-013: the demonstration reaches the library form -------


def test_the_demonstration_obtains_its_verdict_through_the_library_form() -> None:
    """T038, US9-S4. The validate stage builds a report, not an argv list.

    `_run_cli(_spec_validate_argv(...))` streamed the verb's stdout, but the
    stage assembled argv to do it (trap 14). FR-013's letter: the stage calls
    the library form and prints through the same renderer the verb uses —
    so a stranger watching `ergane install` still sees the real verdict, and
    the lines printed are `_render_validation`'s own output.
    """
    source = INSTALL_PATH.read_text(encoding="utf-8")

    assert "_spec_validate_argv" not in source, (
        "the demonstration still builds an argv list for the validate stage"
    )
    assert "validate_spec(" in source, "the stage does not reach the library form"

    # The stage is the renderer, byte for byte: drive both over the same
    # throwaway repository and assert the stage prints the verb's rendering.
    stage_lines, code = _drive_demonstration()
    report_lines = _expected_rendering()

    assert code == 0
    assert stage_lines == report_lines, (
        "the demonstration's validate stage no longer prints what the verb "
        "prints — FR-013 requires the lines unchanged"
    )


def _drive_demonstration() -> tuple[list[str], int]:
    """Run the demonstration's validate stage, returning its lines and exit."""
    from factory.cli import install as install_module

    repo_root = _write_demo_repository()
    spec_dir = repo_root / "specs" / "001-demo"

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = install_module._demonstrate_validate(spec_dir, repo_root)
    assert stderr.getvalue() == "", stderr.getvalue()
    return stdout.getvalue().splitlines(), code


def _expected_rendering() -> list[str]:
    """What the verb's renderer prints for the same repository and spec."""
    from factory.cli.nouns.spec import _render_validation
    from factory.spec import validate_spec

    repo_root = _demo_repo_path()
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


#: The throwaway demonstration repository, written once per test run and
#: reused by both drivers above so they read one tree.
_DEMO_REPO: Path | None = None


def _write_demo_repository() -> Path:
    """A throwaway repository with the demonstration spec, as install writes it."""
    global _DEMO_REPO
    if _DEMO_REPO is None:
        from factory.cli import install as install_module

        repo_root = Path(tempfile.mkdtemp(prefix="us9-demo-"))
        install_module._git_init(repo_root)
        install_module._write_scaffold(repo_root, install_module._demo_manifest_text())
        spec_dir = repo_root / "specs" / "001-demo"
        spec_dir.mkdir(parents=True)
        spec_text, plan_text, tasks_text = install_module.scaffold_spec(
            slug="demo",
            title="Demonstration",
            anchor=install_module._demo_anchor(repo_root),
            demonstration=True,
        )
        (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
        (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
        (spec_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")
        _DEMO_REPO = repo_root
    return _DEMO_REPO


def _demo_repo_path() -> Path:
    return _write_demo_repository()


# --- T052 / US9-S5 / FR-015: the re-pointed controls still disable something --


def test_the_re_pointed_controls_still_disable_something(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T052, US9-S5. The control on the controls, one assertion per helper.

    Both helpers rebind a name on `factory.cli.nouns.spec` today; after T040
    that rebinding lands on a name nothing calls, both runs become the same
    run, and both corpus comparisons pass over a hundred and thirty specs
    while covering nothing (trap 23). The re-point (T054) lands the rebinding
    on the module the composition reads; this assertion is what proves it
    took — on a spec the layer refuses, the disabled and enabled runs return
    **different** findings.
    """
    from tests.test_089_validate_checks_fixes import (
        _seed_store,
        _sound_spec_dir,
        _validate_without_fixes_layer,
    )
    from tests.test_102_unprovable_criteria import _validate_without_evidence_layer

    # --- the fixes helper ---------------------------------------------------
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("ERGANE_ROOT", str(root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    # The 089 fixture's legacy pin, applied by hand: the resolved runtime root
    # holds the seeded store, and the legacy candidate must name a directory
    # that is never created so no host ledger can answer instead (trap 6).
    import factory.doctor.cli as _doctor_cli

    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-runtime-root")
    _seed_store(root / "doctor.db", ["present/key"])

    specs_root = tmp_path / "specs"
    fixes_dir = _sound_spec_dir(
        specs_root, "001-fixes-refusal", "state: draft\nfixes:\n  - absent/key\n"
    )

    with_layer = run(
        "spec",
        "validate",
        "--json",
        "--target-repo",
        str(REPO_ROOT),
        "--specs-root",
        str(specs_root),
        str(fixes_dir),
    )
    assert [f["layer"] for f in with_layer.json["findings"]] == ["fixes"], (
        "the fixture must carry a fixes refusal, or the comparison below is vacuous"
    )
    without_code, without_doc = _validate_without_fixes_layer(
        run, fixes_dir, REPO_ROOT, specs_root
    )
    assert without_doc["findings"] != with_layer.json["findings"], (
        "disabling the fixes layer changed nothing — the control is vacuous (trap 23)"
    )

    # --- the evidence helper -------------------------------------------------
    evidence_specs_root = tmp_path / "specs-evidence"
    evidence_dir = _write_evidence_refusal_trio(evidence_specs_root / "002-evidence-refusal")

    with_layer_evidence = run(
        "spec",
        "validate",
        "--json",
        "--target-repo",
        str(REPO_ROOT),
        "--specs-root",
        str(evidence_specs_root),
        str(evidence_dir),
    )
    assert [f["layer"] for f in with_layer_evidence.json["findings"]] == ["evidence"], (
        "the fixture must carry an evidence refusal, or the comparison below is vacuous"
    )
    without_code_e, without_doc_e = _validate_without_evidence_layer(
        run, evidence_dir, evidence_specs_root
    )
    assert without_doc_e["findings"] != with_layer_evidence.json["findings"], (
        "disabling the evidence layer changed nothing — the control is vacuous (trap 23)"
    )


def _write_evidence_refusal_trio(spec_dir: Path) -> Path:
    """A sound trio whose one Then-clause no declared gate can evidence."""
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        "---\nstate: draft\n---\n\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST draw the page.\n\n"
        "### User Story 1 - The page is drawn (Priority: P1)\n\n"
        "As an operator, I want the page drawn.\n\n"
        "**Acceptance Scenarios**:\n\n"
        "1. **Given** a built page, **When** the operator opens it, **Then** "
        "the page renders correctly in the browser.\n\n"
        "## Work Graph\n\n```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n\nOne story, one page.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n## Phase 1: User Story 1 - The page is drawn\n\n"
        "- [ ] T001 [US1-S1] draw the page\n",
        encoding="utf-8",
    )
    return spec_dir


def _write_sound_trio(spec_dir: Path) -> Path:
    """A sound trio: one story, one scenario its tasks name, a compiling graph."""
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        "---\nstate: draft\n---\n\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST do the thing.\n\n"
        "### User Story 1 - The thing happens (Priority: P1)\n\n"
        "As an operator, I want the thing.\n\n"
        "**Acceptance Scenarios**:\n\n"
        "1. **Given** a thing, **When** I act, **Then** it works.\n\n"
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


# --- T053 / US9-S6 / FR-015, FR-008: the import-backs are retired -------------


def test_the_cli_module_imports_no_relocated_layer_function() -> None:
    """T053, US9-S6. Read the module source; the layer functions are not there.

    Once the CLI composes no layer it imports none of the relocated ones
    (FR-015) — the import-back each relocation story left behind kept the
    four trap-22 files green, and it is not a contract.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("factory.spec"):
            imported.update(alias.name for alias in node.names)
    stranded = sorted(set(RELOCATED) & imported)
    assert stranded == [], f"the CLI module still imports relocated layers: {stranded}"


def test_no_test_reaches_a_relocated_layer_through_the_cli_module() -> None:
    """T053's second half. No file under `tests/` reaches one through the CLI.

    The four trap-22 files and the two corpus controls were the whole in-tree
    set at 602a92c; the sibling 133 stories' tests drove the moved checkers
    through the CLI module's import-back as well. This scan is what stops the
    next one being written: attribute access spelled through any of the
    module's import aliases fails here.
    """
    reachers: list[str] = []
    aliases = ("spec_noun", "spec_module", "_spec_module", "spec_mod")
    pattern = re.compile(
        r"(?:"
        + "|".join(re.escape(alias) for alias in aliases)
        + r")\.("
        + "|".join(re.escape(name) for name in RELOCATED)
        + r")\b"
    )
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        match = pattern.search(path.read_text(encoding="utf-8"))
        if match:
            reachers.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)}")
    assert reachers == [], (
        "tests still reach relocated layers through factory.cli.nouns.spec: "
        + ", ".join(reachers)
    )