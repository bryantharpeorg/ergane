"""133-US9: the verb renders the composition, and its output is unchanged.

US3 added `validate_spec`; this story deletes the verb's private copy of that
composition and makes `_validate_command` a renderer over it. The rendering is
the only behavioural edit in the spec, so the guards here are the ones that
make a quiet output change red:

- **T035 (US9-S1, FR-006)**: the verb's stdout **and** stderr over both fixture
  trios equal their golden artifacts byte for byte, and the exit codes are
  pinned — a stdout-only comparison would hold none of the four rendered
  prefixes, because every finding, skip and information line prints to stderr.
- **T036 (US9-S2, FR-007, trap 21)**: `--json` equals its golden byte for byte;
  the document's key order and the deliberate absence of `judge_evidence` when
  the evidence layer did not run are asserted separately, because they are what
  a tidied serialisation silently changes.
- **T037 (US9-S3, FR-008, trap 2)**: the CLI module constructs no finding and
  calls no layer — read from the module source, so a construction that moved
  into a helper still in the CLI module does not pass. Five constructions and
  three whole layer wrappers are what the rewrite deletes.
- **T038 (US9-S4, FR-013, trap 14)**: install.py's demonstration reaches the
  library form through the same renderer, `_spec_validate_argv` is gone, and
  the lines the demonstration prints still match US1's clean-trio golden.
- **T052 (US9-S5, FR-015, trap 23)**: the control on the controls — driving the
  two re-pointed corpus helpers over a spec each layer refuses, the disabled
  and enabled runs return **different** findings. A control that cannot fail
  is not a control.
- **T053 (US9-S6, FR-015, FR-008, trap 22)**: the CLI module imports no
  relocated layer function at all, and no file under `tests/` reaches one
  through `factory.cli.nouns.spec` — which forces the relocation-story tests
  and the two corpus controls to their new homes with the rewrite.

Red first. `uv run pytest tests/test_133_us9_verb_renders_the_composition.py -q
--no-header`, run against this tree with these tests committed and the verb
still composing its own layers, verbatim::

    FAILED tests/test_133_us9_verb_renders_the_composition.py::test_the_json_document_omits_judge_evidence_when_the_layer_did_not_run
    FAILED tests/test_133_us9_verb_renders_the_composition.py::test_the_cli_module_constructs_no_finding_and_calls_no_layer
    FAILED tests/test_133_us9_verb_renders_the_composition.py::test_the_demonstration_reaches_the_library_form_through_the_renderer
    FAILED tests/test_133_us9_verb_renders_the_composition.py::test_the_demonstration_prints_the_golden_clean_trio_transcript
    FAILED tests/test_133_us9_verb_renders_the_composition.py::test_no_test_file_reaches_a_relocated_layer_through_the_cli_module
    FAILED tests/test_133_us9_verb_renders_the_composition.py::test_the_cli_module_imports_no_relocated_layer_function
    5 failed, 4 passed in ...

The four that passed red are the guards that must stay green through the
rewrite: the golden comparisons over both trios and both streams, and T052's
disabled-versus-enabled differences — the two corpus helpers still disable
something while the verb reads its own module globals, and they must still
disable something after the re-point.

Green after, same command::

    9 passed in ...
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: US1's fixtures and goldens, and US3's fixture helpers, reused rather than
#: rebuilt — the trios are the ones whose six artifacts freeze the verb's
#: output, and the golden comparison helpers are already normalisation-correct.
from tests.test_133_us1_typed_report_and_golden_captures import (
    CLEAN_TRIO,
    DEFECTIVE_TRIO,
    FIXTURE_REPO,
    GOLDEN,
    _normalise,
    _read_golden,
    _run_validate,
)
from tests.test_133_us3_validate_spec_composition import (
    _gate_repo,
    _seed_store,
    _write_trio,
    monkeypatch_env,
)
from tests.test_089_validate_checks_fixes import Run

CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
INSTALL_PATH = REPO_ROOT / "factory" / "cli" / "install.py"

#: The layer functions the composition relocated, and the two composition-only
#: helpers beside them (`_candidate_graph`, `_tasks_text`). `_scan_sentinels_in_trio`
#: is deliberately absent: it is not a layer of the composition — the derive
#: verb's sentinel gate keeps calling it through the CLI module's import, which
#: is the one relocated name that survives (plan's landing shape for the module).
RELOCATED_LAYER_FUNCTIONS = (
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
)

#: Every spelling a test file can use to reach a relocated name through the
#: CLI module: the `import … as` alias, the bare-module spelling, and
#: `getattr(alias, "name")`.
def _cli_module_reaches(text: str, alias: str, name: str) -> bool:
    patterns = (
        rf"\b{re.escape(alias)}\.{re.escape(name)}\b",
        rf"getattr\(\s*{re.escape(alias)}\s*,\s*[\"']{re.escape(name)}[\"']",
        rf"factory\.cli\.nouns\.spec\.{re.escape(name)}\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


# --- T035 / US9-S1 / FR-006: both streams, both trios, byte for byte ----------


@pytest.mark.parametrize(
    ("trio_dir", "name", "expected_code"),
    [(CLEAN_TRIO, "clean", 0), (DEFECTIVE_TRIO, "defective", 1)],
)
def test_the_verb_matches_both_golden_streams_and_its_exit_code(
    trio_dir: Path, name: str, expected_code: int
) -> None:
    """T035, US9-S1. stdout, stderr and the exit code, against the goldens.

    The clean trio's stdout carries the all-pass sentence and its stderr the
    skipped-layer and information lines; the defective trio's stderr carries
    the advisory and refusal lines and never prints the sentence. All four
    rendered prefixes live only in the stderr artifacts, so a stdout-only
    comparison would pass over a renderer that changed every one of them.
    """
    code, stdout, stderr = _run_validate(trio_dir, as_json=False)
    assert code == expected_code, (code, expected_code)
    assert _normalise(stdout, REPO_ROOT) == _read_golden(name, "stdout")
    assert _normalise(stderr, REPO_ROOT) == _read_golden(name, "stderr")


# --- T036 / US9-S2 / FR-007 / trap 21: the --json document --------------------


@pytest.mark.parametrize(("trio_dir", "name"), [(CLEAN_TRIO, "clean"), (DEFECTIVE_TRIO, "defective")])
def test_the_json_document_matches_its_golden_byte_for_byte(
    trio_dir: Path, name: str
) -> None:
    """T036, US9-S2. The document, byte for byte, key order included.

    The golden artifact was serialised from the verb's inline dict in the order
    `spec_dir, checked, skipped, findings, information, judge_evidence`; a
    `dataclasses.asdict()` over the typed report reorders those keys and turns
    `judge_evidence` into a `null` — the golden goes red for a reason the diff
    does not explain (trap 21). Byte-for-byte comparison is the assertion that
    catches both.
    """
    _code, json_stdout, json_stderr = _run_validate(trio_dir, as_json=True)
    assert json_stderr == "", "the --json face prints nothing on stderr"
    assert _normalise(json_stdout, REPO_ROOT) == _read_golden(name, "json")
    document: dict[str, Any] = json.loads(json_stdout)
    assert list(document) == [
        "spec_dir",
        "checked",
        "skipped",
        "findings",
        "information",
        "judge_evidence",
    ]


def test_the_json_document_omits_judge_evidence_when_the_layer_did_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T036, US9-S2. Absent rather than null when there is no report.

    With the evidence layer disabled the document must carry no
    `judge_evidence` key at all — no layer ran, so nothing was answered — and
    the remaining keys keep their order. Patched on the module the composition
    reads, which is the only patch that disables anything once the verb is a
    renderer (trap 23); before the rewrite the verb read its own globals and
    this assertion failed, which is why it is in the red list.
    """
    import factory.spec.composition as composition

    original = composition._check_evidence
    composition._check_evidence = lambda *args, **kwargs: None
    try:
        _code, json_stdout, _stderr = _run_validate(CLEAN_TRIO, as_json=True)
    finally:
        composition._check_evidence = original

    document: dict[str, Any] = json.loads(json_stdout)
    assert "judge_evidence" not in document, list(document)
    assert list(document) == ["spec_dir", "checked", "skipped", "findings", "information"]


# --- T037 / US9-S3 / FR-008 / trap 2: the CLI composes and constructs nothing --


def test_the_cli_module_constructs_no_finding_and_calls_no_layer() -> None:
    """T037, US9-S3. The module source holds no layer call and no construction.

    Five constructions lived in `_validate_command`'s own body, not one, and a
    `def _check_` sweep found none of them: the `workgraph` DerivationError
    refusal, the `prompt_assembly` and `slice_coverage` wrappers with their
    informational routing, the `slice_contention` advisory and the `sentinel`
    note — plus three whole layer wrappers whose skip-reason strings existed
    nowhere else in the tree. All twelve layers now reach the verb through
    `validate_spec`, so the validate handlers' source must carry neither the
    calls nor the constructions; asserting on the source is what stops a
    construction that moved into a helper still in this module. The scope is
    the two validate handlers, not the whole module: `spec new` derives a
    workgraph of its own, and that is nobody else's job to police.
    """
    import inspect

    import factory.cli.nouns.spec as spec_noun

    source = "\n".join(
        inspect.getsource(getattr(spec_noun, name))
        for name in ("_validate_command", "_render_validation")
    )
    for name in RELOCATED_LAYER_FUNCTIONS:
        assert name not in source, f"the validate handler still names {name}"
    for token in (
        "SpecFinding(",
        "_ValidateFinding(",
        "SpecValidation(",
        "findings.append",
        "information.append",
        "skipped.append",
        "checked.append",
    ):
        assert token not in source, f"the validate handler still constructs: {token}"
    assert "derive_workgraph(" not in source, (
        "the validate handler still derives the work graph; composition is not its job"
    )


# --- T038 / US9-S4 / FR-013 / trap 14: the demonstration's validate stage -----


def test_the_demonstration_reaches_the_library_form_through_the_renderer() -> None:
    """T038, US9-S4. No argv list; the library form and the verb's renderer.

    `_run_cli` streamed labeled output on purpose (trap 14): converting the
    stage to a bare call that prints nothing would delete the demonstration's
    whole point. The new seam calls `validate_spec` and renders through the
    same renderer the verb uses, so the lines a stranger watching `ergane
    install` sees are the verb's lines.
    """
    source = INSTALL_PATH.read_text(encoding="utf-8")
    assert "_spec_validate_argv" not in source, (
        "the demonstration still builds an argv list for validate"
    )
    assert "validate_spec(" in source, "the demonstration does not call the library form"
    assert "_render_validation(" in source, (
        "the demonstration does not render through the verb's renderer"
    )


def test_the_demonstration_prints_the_golden_clean_trio_transcript() -> None:
    """T038, US9-S4. The stage's lines are the verb's lines, artifact-checked.

    Driven over US1's clean fixture trio, the demonstration stage must print
    exactly what the verb prints for the same trio — which US1's golden
    artifacts already freeze. A stage that dropped the verdict, reordered the
    streams or printed through a different renderer fails here byte for byte.
    """
    from factory.cli.install import _demo_validate

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = _demo_validate(CLEAN_TRIO, FIXTURE_REPO)
    assert code == 0
    assert _normalise(stdout.getvalue(), REPO_ROOT) == _read_golden("clean", "stdout")
    assert _normalise(stderr.getvalue(), REPO_ROOT) == _read_golden("clean", "stderr")


# --- T052 / US9-S5 / FR-015 / trap 23: the control on the controls ------------


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """The verb in-process, captured, shaped like test_089's `run` fixture."""

    def invoke(*argv: str) -> Run:
        try:
            from factory.cli.main import main

            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def test_the_repointed_fixes_control_still_disables_a_refusing_layer(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T052, US9-S5. The fixes control disables something, provably.

    The helper is driven as the corpus control drives it, over a spec the
    `fixes` layer refuses — the store exists (trap 20) and the declared key is
    absent from it. With the layer enabled the run carries the refusal; with it
    disabled the findings differ. Before the re-point the helper rebound a name
    on `factory.cli.nouns.spec` that nothing called, both runs were the same
    run, and a hundred and thirty specs were compared while covering nothing.
    """
    from tests.test_089_validate_checks_fixes import _validate_without_fixes_layer

    root = tmp_path / "ergane-root"
    root.mkdir()
    _seed_store(root / "doctor.db", ["present/key"])
    monkeypatch_env(monkeypatch, root, tmp_path)

    specs_root = tmp_path / "specs"
    spec_body = (
        "---\nstate: draft\nfixes:\n  - absent/key\n---\n"
        "\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST do the thing.\n\n"
        "### User Story 1 - The thing happens (Priority: P1)\n\n"
        "As the operator, I want the thing.\n\n**Acceptance Scenarios**:\n\n"
        "1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        "## Work Graph\n\n```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n"
    )
    spec_dir = _write_trio(specs_root / "001-fixes-control", spec_body=spec_body)

    with_run = run(
        "spec", "validate", "--json", "--target-repo", str(FIXTURE_REPO),
        "--specs-root", str(specs_root), str(spec_dir),
    )
    without_code, without_doc = _validate_without_fixes_layer(
        run, spec_dir, FIXTURE_REPO, specs_root
    )

    # The exit codes differ too — disabling a refusing layer removes its
    # refusal — but findings are the channel the task names, so that is what
    # is asserted.
    assert with_run.code != without_code
    assert with_run.json["findings"] != without_doc["findings"], (
        "the disabled run returned the same findings — the control disables nothing"
    )
    assert any(f["layer"] == "fixes" for f in with_run.json["findings"])
    assert not any(f["layer"] == "fixes" for f in without_doc["findings"])


def test_the_repointed_evidence_control_still_disables_a_refusing_layer(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """T052, US9-S5. The evidence control disables something, provably.

    The helper pins `--target-repo` at this repository, whose committed
    manifest declares one gate — so a Then-clause asserting a runtime outcome
    is refused, not skipped (trap 20). Disabled, the refusal disappears; the
    two runs differ, which is the proof the re-point took.
    """
    from tests.test_102_unprovable_criteria import _validate_without_evidence_layer

    specs_root = tmp_path / "specs"
    spec_body = (
        "---\nstate: draft\n---\n"
        "\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST draw the page.\n\n"
        "### User Story 1 - The page is drawn (Priority: P1)\n\n"
        "As an operator, I want the page drawn.\n\n**Acceptance Scenarios**:\n\n"
        "1. **Given** a built page, **When** the operator opens it, **Then** "
        "the page renders correctly in the browser.\n\n"
        "## Work Graph\n\n```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n"
    )
    spec_dir = _write_trio(specs_root / "001-evidence-control", spec_body=spec_body)

    with_run = run(
        "spec", "validate", "--json", "--target-repo", str(REPO_ROOT),
        "--specs-root", str(specs_root), str(spec_dir),
    )
    without_code, without_doc = _validate_without_evidence_layer(run, spec_dir, specs_root)

    # The exit codes differ too — disabling a refusing layer removes its
    # refusal — but findings are the channel the task names, so that is what
    # is asserted.
    assert with_run.code != without_code
    assert with_run.json["findings"] != without_doc["findings"], (
        "the disabled run returned the same findings — the control disables nothing"
    )
    assert any(f["layer"] == "evidence" for f in with_run.json["findings"])
    assert not any(f["layer"] == "evidence" for f in without_doc["findings"])


# --- T053 / US9-S6 / FR-015, FR-008 / trap 22: the import seam is closed ------


def test_the_cli_module_imports_no_relocated_layer_function() -> None:
    """T053, US9-S6. The import-backs the relocations needed are gone.

    While the verb composed its own layers, every relocated name had to be
    bound back under the CLI module's namespace (trap 22) or four test files
    died at collection. The verb composes nothing now, so the bindings are
    dead imports — and FR-015 forbids them outright. `_scan_sentinels_in_trio`
    is the one relocated name still imported, because `_derive_command`'s
    sentinel gate calls it; that is asserted here too, so the derive verb's
    refusal text cannot be silently broken by an over-eager tidy-up.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
            "factory.spec"
        ):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
    stranded = sorted(set(RELOCATED_LAYER_FUNCTIONS) & imported)
    assert stranded == [], f"the CLI module still imports relocated layers: {stranded}"

    # The derive verb's gate keeps the one relocated scanner alive.
    assert "_scan_sentinels_in_trio" in imported
    assert "_scan_sentinels_in_trio(spec_dir)" in source


def test_no_test_file_reaches_a_relocated_layer_through_the_cli_module() -> None:
    """T053, US9-S6. No test reaches a relocated layer as a CLI-module attribute.

    The relocation-story tests reached the moved bodies as attributes of
    `factory.cli.nouns.spec` because that was the only object calling them;
    once the verb stopped composing, those reaches became the next trap-22
    waiting to happen — an ordinary tidy-up of a dead binding would break them.
    Every file under `tests/` is scanned for the import spellings and for
    attribute or `getattr` access naming a relocated layer function.
    """
    offenders: list[str] = []
    import_pattern = re.compile(
        r"import factory\.cli\.nouns\.spec(?:\s+as\s+(\w+))?"
        r"|from factory\.cli\.nouns\.spec import ([^\n#]+)"
    )
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        aliases: list[str] = []
        for match in import_pattern.finditer(text):
            if match.group(1):
                aliases.append(match.group(1))
            if match.group(2):
                names = [
                    part.strip().split(" as ")[0].strip().split("(")[0].strip()
                    for part in match.group(2).split(",")
                ]
                offenders.extend(
                    f"{path.name}: from factory.cli.nouns.spec import {n}"
                    for n in names
                    if n in RELOCATED_LAYER_FUNCTIONS
                )
        aliases.append("factory.cli.nouns.spec")
        for name in RELOCATED_LAYER_FUNCTIONS:
            for alias in aliases:
                if _cli_module_reaches(text, alias, name):
                    offenders.append(f"{path.name}: {alias}.{name}")
    assert offenders == [], f"tests still reach relocated layers through the CLI module: {offenders}"