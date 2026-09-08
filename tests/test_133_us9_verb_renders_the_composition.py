"""133-US9: the verb renders the composition, and its output is unchanged.

US3 added `validate_spec`; this story deletes the verb's private copy and makes
`_validate_command` a renderer over it. The rendering is the only behavioural
edit in the spec, so the guards are the ones that make a quiet output change
red: T035 (US9-S1, FR-006) stdout **and** stderr over both trios against their
goldens, exit codes pinned — the four rendered prefixes live only on stderr;
T036 (US9-S2, FR-007, trap 21) the `--json` document byte for byte, key order
and the absent-not-null `judge_evidence` included; T037 (US9-S3, FR-008, trap
2) the CLI module constructs no finding and calls no layer, read from the
validate handlers' source; T038 (US9-S4, FR-013, trap 14) the demonstration
reaches the library form through the same renderer, `_spec_validate_argv` gone;
T052 (US9-S5, FR-015, trap 23) the control on the controls — the two re-pointed
corpus helpers return **different** findings on a refusing spec; T053 (US9-S6,
FR-015, FR-008, trap 22) no relocated layer imported by the CLI module, no test
reaching one through it.

Red first (`uv run pytest tests/test_133_us9_verb_renders_the_composition.py
-q --no-header`, verb still composing its own layers): 8 failed, 4 passed —
the guards red, the goldens and the then-working control differences green.
Green after the rewrite: 12 passed.
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

#: US1's fixtures, goldens and comparison helpers, reused rather than rebuilt.
from tests.test_133_us1_typed_report_and_golden_captures import (
    CLEAN_TRIO,
    DEFECTIVE_TRIO,
    FIXTURE_REPO,
    _normalise,
    _read_golden,
    _run_validate,
)
from tests.test_133_us3_validate_spec_composition import (
    _SOUND_BODY,
    _seed_store,
    _write_trio,
    monkeypatch_env,
)
from tests.test_089_validate_checks_fixes import Run

CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
INSTALL_PATH = REPO_ROOT / "factory" / "cli" / "install.py"

#: The layer functions the composition relocated, and the two composition-only
#: helpers beside them (`_candidate_graph`, `_tasks_text`). `_scan_sentinels_in_trio`
#: is absent on purpose: the derive verb's sentinel gate keeps calling it through
#: the CLI module's import — the one relocated name that survives.
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

def _cli_module_reaches(text: str, alias: str, name: str) -> bool:
    """The spellings a test uses to reach a relocated name: attribute or
    `getattr(alias, "name")`."""
    return bool(
        re.search(rf"\b{re.escape(alias)}\.{re.escape(name)}\b", text)
        or re.search(rf"getattr\(\s*{re.escape(alias)}\s*,\s*[\"']{re.escape(name)}[\"']", text)
    )


# --- T035 / US9-S1 / FR-006: both streams, both trios, byte for byte ----------


TRIOS = [(CLEAN_TRIO, "clean", 0), (DEFECTIVE_TRIO, "defective", 1)]


@pytest.mark.parametrize(("trio_dir", "name", "expected_code"), TRIOS)
def test_the_verb_matches_both_golden_streams_and_its_exit_code(
    trio_dir: Path, name: str, expected_code: int
) -> None:
    """T035, US9-S1. Both streams and the exit code, against the goldens.

    The four rendered prefixes live only on stderr (trap 19), so a stdout-only
    comparison would pass over a renderer that changed every one of them.
    """
    code, stdout, stderr = _run_validate(trio_dir, as_json=False)
    assert code == expected_code, (code, expected_code)
    assert _normalise(stdout, REPO_ROOT) == _read_golden(name, "stdout")
    assert _normalise(stderr, REPO_ROOT) == _read_golden(name, "stderr")


@pytest.mark.parametrize(("trio_dir", "name", "expected_code"), TRIOS)
def test_the_json_document_matches_its_golden_byte_for_byte(
    trio_dir: Path, name: str, expected_code: int
) -> None:
    """T036, US9-S2. Byte for byte, key order included (trap 21): an
    `asdict()` serialisation would reorder the keys and emit
    `judge_evidence: null`, and the golden goes red for a reason the diff does
    not explain.
    """
    code, json_stdout, json_stderr = _run_validate(trio_dir, as_json=True)
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

    Patched on the module the composition reads — the only patch that disables
    anything once the verb is a renderer (trap 23); before the rewrite this
    assertion failed, which is why it is in the red list.
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
    """T037, US9-S3. The validate handlers hold no layer call and no construction.

    Five constructions lived in `_validate_command`'s own body, not one, and a
    `def _check_` sweep found none of them (trap 2). Asserting on the handlers'
    source is what stops a construction that moved into a helper still in this
    module; the scope is the two validate handlers, not the whole module —
    `spec new` derives a workgraph of its own, and that is nobody else's job
    to police.
    """
    import inspect

    import factory.cli.nouns.spec as spec_noun

    source = "\n".join(
        inspect.getsource(getattr(spec_noun, name))
        for name in ("_validate_command", "_render_validation")
    )
    assert not any(name in source for name in RELOCATED_LAYER_FUNCTIONS), (
        "the validate handler still names a relocated layer"
    )
    assert not any(
        token in source
        for token in (
            "SpecFinding(",
            "_ValidateFinding(",
            "SpecValidation(",
            "findings.append",
            "information.append",
            "skipped.append",
            "checked.append",
        )
    ), "the validate handler still constructs a finding"
    assert "derive_workgraph(" not in source, "composition is not the verb's job"


# --- T038 / US9-S4 / FR-013 / trap 14: the demonstration's validate stage -----


def test_the_demonstration_reaches_the_library_form_through_the_renderer() -> None:
    """T038, US9-S4. No argv list; the library form and the verb's renderer.

    The stage streamed labeled output on purpose (trap 14), so it renders
    through the verb's renderer — a stranger watching `ergane install` sees
    the verb's lines.
    """
    source = INSTALL_PATH.read_text(encoding="utf-8")
    assert "_spec_validate_argv" not in source, "the stage still builds an argv list"
    assert "validate_spec(" in source, "the stage does not call the library form"
    assert "_render_validation(" in source, "the stage does not use the verb's renderer"


def test_the_demonstration_prints_the_golden_clean_trio_transcript() -> None:
    """T038, US9-S4. The stage's lines are the verb's lines, artifact-checked
    against US1's goldens over the clean fixture trio."""
    from factory.cli.install import _demo_validate

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = _demo_validate(CLEAN_TRIO, FIXTURE_REPO)
    assert code == 0
    assert _normalise(stdout.getvalue(), REPO_ROOT) == _read_golden("clean", "stdout")
    assert _normalise(stderr.getvalue(), REPO_ROOT) == _read_golden("clean", "stderr")


# --- T052 / US9-S5 / FR-015 / trap 23: the control on the controls ------------


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """The verb in-process, captured, shaped like test_089's `run` fixture."""

    def invoke(*argv: str) -> Run:
        from factory.cli.main import main

        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def _refusing_fixes_trio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A spec the fixes layer refuses (trap 20: the store exists, the key is
    absent from it) and the store seeded beside it."""
    root = tmp_path / "ergane-root"
    root.mkdir()
    _seed_store(root / "doctor.db", ["present/key"])
    monkeypatch_env(monkeypatch, root, tmp_path)
    return _write_trio(
        tmp_path / "specs" / "001-fixes-control",
        spec_body=_SOUND_BODY.replace("---\n", "---\nfixes:\n  - absent/key\n", 1),
    )


def _refusing_evidence_trio(tmp_path: Path) -> Path:
    """A spec the evidence layer refuses (trap 20: the manifest declares a gate)."""
    return _write_trio(
        tmp_path / "specs" / "001-evidence-control",
        spec_body=_SOUND_BODY.replace(
            "**Then** it works.", "**Then** the page renders correctly in the browser."
        ),
    )


def test_the_repointed_fixes_control_still_disables_a_refusing_layer(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T052, US9-S5. The fixes control disables something, provably.

    Before the re-point the helper rebound a name nothing called and both runs
    were the same run.
    """
    from tests.test_089_validate_checks_fixes import _validate_without_fixes_layer

    spec_dir = _refusing_fixes_trio(tmp_path, monkeypatch)
    specs_root = tmp_path / "specs"
    with_run = run(
        "spec", "validate", "--json", "--target-repo", str(FIXTURE_REPO),
        "--specs-root", str(specs_root), str(spec_dir),
    )
    without_code, without_doc = _validate_without_fixes_layer(
        run, spec_dir, FIXTURE_REPO, specs_root
    )
    _assert_control_fires(with_run, without_code, without_doc, "fixes")


def test_the_repointed_evidence_control_still_disables_a_refusing_layer(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """T052, US9-S5. The evidence control disables something, provably.

    The helper pins `--target-repo` at this repository, whose manifest declares
    one gate — a runtime-outcome clause is refused, not skipped (trap 20).
    """
    from tests.test_102_unprovable_criteria import _validate_without_evidence_layer

    spec_dir = _refusing_evidence_trio(tmp_path)
    with_run = run(
        "spec", "validate", "--json", "--target-repo", str(REPO_ROOT),
        "--specs-root", str(tmp_path / "specs"), str(spec_dir),
    )
    without_code, without_doc = _validate_without_evidence_layer(run, spec_dir, tmp_path / "specs")
    _assert_control_fires(with_run, without_code, without_doc, "evidence")


def _refusing_evidence_trio(tmp_path: Path) -> Path:
    return _write_trio(
        tmp_path / "specs" / "001-evidence-control",
        spec_body=_SOUND_BODY.replace(
            "**Then** it works.", "**Then** the page renders correctly in the browser."
        ),
    )


def _assert_control_fires(
    with_run: Run, without_code: int, without_doc: Any, layer: str
) -> None:
    """The proof a control disables something: enabled carries the layer's
    refusal, disabled does not, the findings lists differ. Disabling a refusing
    layer removes its refusal, so exit codes differ too; findings are the
    channel the task names."""
    assert with_run.code != without_code
    assert with_run.json["findings"] != without_doc["findings"], (
        "the disabled run returned the same findings — the control disables nothing"
    )
    assert any(f["layer"] == layer for f in with_run.json["findings"])
    assert not any(f["layer"] == layer for f in without_doc["findings"])


# --- T053 / US9-S6 / FR-015, FR-008 / trap 22: the import seam is closed ------


def test_the_cli_module_imports_no_relocated_layer_function() -> None:
    """T053, US9-S6. The import-backs the relocations needed are gone (trap 22,
    FR-015). `_scan_sentinels_in_trio` is the one relocated name still imported
    — `_derive_command`'s sentinel gate calls it — asserted too, so the derive
    verb's refusal text cannot be silently broken by an over-eager tidy-up.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    imported = {
        alias.asname or alias.name
        for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("factory.spec")
        for alias in node.names
    }
    assert not set(RELOCATED_LAYER_FUNCTIONS) & imported, (
        "the CLI module still imports relocated layers"
    )
    # The derive verb's gate keeps the one relocated scanner alive.
    assert "_scan_sentinels_in_trio" in imported
    assert "_scan_sentinels_in_trio(spec_dir)" in source


def test_no_test_file_reaches_a_relocated_layer_through_the_cli_module() -> None:
    """T053, US9-S6. No test reaches a relocated layer as a CLI-module attribute.

    The relocation-story tests reached the moved bodies through the CLI module
    because that was the only object calling them; once the verb stopped
    composing, those reaches became the next trap-22 waiting to happen.
    """

    offenders: list[str] = []
    alias_pattern = re.compile(r"import factory\.cli\.nouns\.spec(?:\s+as\s+(\w+))?")
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        aliases = [m.group(1) or "factory.cli.nouns.spec" for m in alias_pattern.finditer(text)]
        for name in RELOCATED_LAYER_FUNCTIONS:
            for alias in aliases:
                if _cli_module_reaches(text, alias, name):
                    offenders.append(f"{path.name}: {alias}.{name}")
    assert offenders == [], f"tests still reach relocated layers through the CLI module: {offenders}"