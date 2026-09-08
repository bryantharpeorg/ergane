"""133-US3: one composition exists, and the verb is untouched.

Every relocation story before this one put the layer bodies where they belong;
this story adds the one call that composes them all and returns the verdict, so
a consumer that may not shell the CLI stops re-composing five exported pieces
and silently under-reporting the other seven layers (PR-8's drift, 133's reason
to exist). The CLI verb is deliberately not touched: US9 makes it a renderer
over this composition, and this story proves the duplication harmless by leaving
it exactly as it is (US3-S4).

Four controls, one per acceptance scenario:

- **US3-S1 (T032)**: the library form — `validate_spec(spec_dir, *,
  target_repo, specs_root)` — returns the typed report with no
  `argparse.Namespace` constructed and no stdout captured. Not built on
  `validate_spec_command` (trap 8): that wrapper has the right name and the
  wrong shape, and it exists only so `build ship` could stream the same stdout.
- **US3-S2 (T033)**: five trios, each defective in one of the five ways a
  re-composing consumer misses today — a stale line anchor, a symbol anchor, an
  unresolvable `fixes:` key, a missing judge-evidence answer and a slice
  contention — each asserted present in the returned report, the contention one
  at severity `advisory`. Written into `tmp_path` at test time, never committed
  (the `tests/test_anchor_resolution.py` docstring's rule); three of the five
  need a fixture a bare trio cannot carry and skip silently without it (trap
  20): a real findings store for `fixes`, a manifest declaring a gate for
  `evidence`, and a target repository carrying the cited file for the anchors.
- **US3-S3 (T034)**: the `checked` sequence equals the seeded-then-appended
  order the verb emits — which is not the order the layers run in. The control
  is paired with the verb itself over the same spec, so the library's sequence
  and the verb's cannot drift apart.
- **US3-S4 (T070)**: `_validate_command` is byte-for-byte unchanged by this
  story, and US1's six golden artifacts still match with it having done nothing
  to them.

Red first. `uv run pytest tests/test_133_us3_validate_spec_composition.py -q
--no-header`, run against this tree before T039 added `validate_spec`: ten
failed on ImportError (every library-form test — the composition did not
exist), and the two T070 controls passed, as they must — the byte-unchanged
reading of `_validate_command` is true until the story edits it, and US1's six
golden comparisons are the standing guard this story must not disturb.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import io
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The fixture repository US1 committed. Its `ergane.yaml` declares one gate
#: (`smoke`), which is what makes the judge-evidence trio's missing answer a
#: refusal rather than a skip (plan trap 20).
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "spec_validate" / "target-repo"
CLEAN_TRIO = (
    REPO_ROOT / "tests" / "fixtures" / "spec_validate" / "clean-specs" / "001-clean-trio"
)
GOLDEN = REPO_ROOT / "tests" / "golden" / "spec_validate"

CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"

#: The clause that no gate the fixture manifest declares can evidence, and
#: whose scenario names no diff-carried evidence — the shape 102's layer
#: refuses.
_EVIDENCE_CLAUSE = "the font renders correctly in the browser."

#: A sound Spec Kit body: one story, one scenario, a work graph that compiles.
_SOUND_BODY = (
    "---\nstate: draft\n---\n"
    "\n"
    "## Requirements *(mandatory)*\n"
    "\n"
    "- **FR-001**: The system MUST do the thing.\n"
    "\n"
    "### User Story 1 - The thing happens (Priority: P1)\n"
    "\n"
    "As the operator, I want the thing.\n"
    "\n"
    "**Acceptance Scenarios**:\n"
    "\n"
    "1. **Given** a thing, **When** I act, **Then** it works.\n"
    "\n"
    "## Work Graph\n"
    "\n"
    "```yaml\n"
    "US1:\n"
    "  depends_on: []\n"
    "  implements: [FR-001]\n"
    "```\n"
)

_SOUND_TASKS = (
    "# Tasks\n\n"
    "## Phase 1: User Story 1 - The thing happens\n\n"
    "- [ ] T001 [US1-S1] prove the thing happens\n"
)


def _write_trio(
    spec_dir: Path,
    *,
    spec_body: str = _SOUND_BODY,
    plan: str = "# Plan\n\nOne thing, one reader.\n",
    tasks: str = _SOUND_TASKS,
) -> Path:
    """Write one spec trio into `spec_dir`, which its parent defines."""
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(spec_body, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks, encoding="utf-8")
    return spec_dir


def _gate_repo(root: Path, name: str = "target") -> Path:
    """A target repository whose manifest declares one gate (plan trap 20)."""
    repo = root / name
    repo.mkdir(parents=True)
    (repo / "ergane.yaml").write_text(
        'version: 2\nruntime: bwrap\ngates:\n  smoke: "bash gates/smoke.sh"\n',
        encoding="utf-8",
    )
    return repo


def _seed_store(db_path: Path, keys: list[str]) -> None:
    """A findings store holding open rows for the given keys."""
    from factory.doctor.models import Finding, Severity, Status
    from factory.doctor.store import connect, report

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


def _call_validate_spec(
    spec_dir: Path, target_repo: Path | str, specs_root: str | Path
) -> Any:
    """One spelling of the library call, imported late so red is an ImportError."""
    from factory.spec import validate_spec

    return validate_spec(spec_dir, target_repo=str(target_repo), specs_root=specs_root)


def _invoke_main(argv: list[str]) -> int:
    """The CLI entry point, SystemExit normalised the way every sibling does."""
    from factory.cli.main import main

    try:
        return main(argv)
    except SystemExit as exit_request:
        return 0 if exit_request.code is None else int(exit_request.code)


def monkeypatch_env(
    monkeypatch: pytest.MonkeyPatch, root: Path, tmp_path: Path
) -> None:
    """Pin both findings-store candidates at this test's own tree.

    The `fixes` layer resolves its store through `ERGANE_ROOT` when set and
    falls back to the legacy root *relative to the working directory* when the
    first candidate is empty, so one pin is not isolation — see
    `tests/test_089_validate_checks_fixes.py:32` — `_own_findings_store`.
    Through `monkeypatch`, so every mutation is undone at teardown and nothing
    leaks into a later test's module-global env (US2 of runtime-root findings
    reads the resolver's cwd-relative logic and would see this test's root).
    """
    import factory.doctor.cli as _doctor_cli

    monkeypatch.setenv("ERGANE_ROOT", str(root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy-runtime-root")


def report_verdict_exit(report: Any) -> int:
    """The exit code the verb's verdict rule gives a report (EXIT_USER on refusal)."""
    from factory.cli.errors import EXIT_OK, EXIT_USER

    return EXIT_USER if report.refusals else EXIT_OK


# --- US3-S1 / FR-003 / trap 8: the library form -------------------------------


def test_the_library_form_constructs_no_namespace_and_captures_no_stdout() -> None:
    """T032, US3-S1. Namespace in, stdout out — neither.

    The signature takes a `Path` and two keyword-only values: there is no
    `argparse.Namespace` parameter to build and no stdout to capture, which is
    the whole of FR-003 and exactly what `validate_spec_command` cannot offer
    (trap 8). The stdout half is asserted by running the call with both streams
    redirected: the verb prints, the library returns.
    """
    from factory.spec import validate_spec

    parameters = inspect.signature(validate_spec).parameters
    assert list(parameters) == ["spec_dir", "target_repo", "specs_root"]
    assert parameters["target_repo"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["specs_root"].kind is inspect.Parameter.KEYWORD_ONLY

    composition_source = inspect.getsource(validate_spec)
    assert "argparse" not in composition_source.replace(
        "argparse.Namespace` and prints nothing", ""
    ), "the composition body references argparse"

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        report = _call_validate_spec(CLEAN_TRIO, FIXTURE_REPO, "specs")
    assert report is not None
    assert stdout.getvalue() == "", "the library form prints nothing on stdout"
    assert stderr.getvalue() == "", "the library form prints nothing on stderr"


def test_the_library_form_returns_the_typed_report_over_the_clean_trio() -> None:
    """T032, US3-S1. A `SpecValidation`, channels populated, verdict readable.

    The clean fixture trio validates clean: one information note (its
    ERGANE-TODO sentinel), one skipped layer (`anchor_resolution`, whose cited
    path the shared fixture repository does not carry), and no finding. The
    evidence layer ran — the fixture manifest declares a gate — so the report
    carries its answer too.
    """
    from factory.spec import SpecValidation, validate_spec

    report = _call_validate_spec(CLEAN_TRIO, FIXTURE_REPO, "specs")

    assert type(report) is SpecValidation
    assert validate_spec.__module__ == "factory.spec.composition"
    assert report.verdict == "pass"
    assert report.findings == []
    assert report.refusals == []
    assert report.advisories == []
    assert [note.layer for note in report.information] == ["sentinel"]
    assert [entry["layer"] for entry in report.skipped] == ["anchor_resolution"]
    assert report.judge_evidence is not None
    assert report.judge_evidence.all_provable is True


# --- US3-S2 / FR-004 / traps 2 and 20: the five defects ------------------------


def _layers(report: Any) -> list[tuple[str, str]]:
    return [(finding.layer, finding.severity) for finding in report.findings]


def test_a_stale_line_anchor_reaches_the_report(tmp_path: Path) -> None:
    """T033, US3-S2. A `path:NN` citation past end of file is a refusal.

    The target repository must carry the cited file (plan trap 20): with no
    readable cited path the whole layer skips with "none of the cited paths
    exist …", which would make this assertion vacuous.
    """
    repo = tmp_path / "target"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "module.py").write_text("line one\nline two\nline three\n", encoding="utf-8")
    specs_root = tmp_path / "specs"
    spec_dir = _write_trio(
        specs_root / "001-stale",
        plan="# Plan\n\n- see `src/module.py:10` for context.\n",
    )

    report = _call_validate_spec(spec_dir, repo, str(specs_root))

    assert ("anchor_resolution", "refusal") in _layers(report), _layers(report)
    assert "anchor_resolution" in report.checked
    message = next(f.message for f in report.findings if f.layer == "anchor_resolution")
    assert "`src/module.py:10`" in message
    assert report.verdict == "fail"


def test_a_symbol_anchor_reaches_the_report(tmp_path: Path) -> None:
    """T033, US3-S2. A citation outside the named symbol's span is a refusal."""
    repo = tmp_path / "target"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "widget.py").write_text(
        "class Widget:\n    def do_thing(self):\n        return 1\n", encoding="utf-8"
    )
    specs_root = tmp_path / "specs"
    spec_dir = _write_trio(
        specs_root / "001-symbol",
        plan="# Plan\n\nThe drawing lives at `src/widget.py:1` -- `do_thing`.\n",
    )

    report = _call_validate_spec(spec_dir, repo, str(specs_root))

    assert ("symbol_anchors", "refusal") in _layers(report), _layers(report)
    assert "symbol_anchors" in report.checked
    message = next(f.message for f in report.findings if f.layer == "symbol_anchors")
    assert "do_thing" in message

def test_an_unresolvable_fixes_key_reaches_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T033, US3-S2. A `fixes:` key absent from the ledger is a refusal.

    The store must exist (plan trap 20): with no store the layer appends a
    `skipped` entry and returns, which would make this assertion vacuous. The
    store is put under this test's own `tmp_path` the way
    `tests/test_089_validate_checks_fixes.py:32` — `_own_findings_store` does —
    both candidates pinned, because the resolver falls back to the legacy root
    relative to the working directory when the first candidate is empty.
    """
    import factory.doctor.cli as _doctor_cli

    root = tmp_path / "ergane-root"
    root.mkdir()
    _seed_store(root / "doctor.db", ["present/key"])
    monkeypatch.setenv("ERGANE_ROOT", str(root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    monkeypatch.setattr(_doctor_cli, "LEGACY_FACTORY_ROOT", tmp_path / "legacy")

    specs_root = tmp_path / "specs"
    spec_body = _SOUND_BODY.replace(
        "---\nstate: draft\n---\n",
        "---\nstate: draft\nfixes:\n  - absent/key\n---\n",
    )
    spec_dir = _write_trio(specs_root / "001-fixes", spec_body=spec_body)

    report = _call_validate_spec(spec_dir, FIXTURE_REPO, str(specs_root))

    assert ("fixes", "refusal") in _layers(report), _layers(report)
    assert "fixes" in report.checked
    message = next(f.message for f in report.findings if f.layer == "fixes")
    assert "absent/key" in message
    assert report.verdict == "fail"


def test_a_missing_judge_evidence_answer_reaches_the_report(tmp_path: Path) -> None:
    """T033, US3-S2. A Then-clause nothing declared can evidence is a refusal.

    The manifest must declare a gate (plan trap 20): with none readable the
    layer skips instead of refusing and the finding is never composed. The
    repository here declares one, the scenario names no diff-carried evidence,
    and the clause asserts a runtime outcome — the exact shape 102 refuses.
    """
    specs_root = tmp_path / "specs"
    spec_body = _SOUND_BODY.replace(
        "1. **Given** a thing, **When** I act, **Then** it works.",
        f"1. **Given** a thing, **When** I act, **Then** {_EVIDENCE_CLAUSE}",
    )
    spec_dir = _write_trio(specs_root / "001-evidence", spec_body=spec_body)
    repo = _gate_repo(tmp_path)

    report = _call_validate_spec(spec_dir, repo, str(specs_root))

    assert ("evidence", "refusal") in _layers(report), _layers(report)
    assert "evidence" in report.checked
    message = next(f.message for f in report.findings if f.layer == "evidence")
    assert _EVIDENCE_CLAUSE in message
    assert "in the browser" in message
    assert report.verdict == "fail"


def test_a_slice_contention_reaches_the_report_as_an_advisory(tmp_path: Path) -> None:
    """T033, US3-S2. Two slices naming one file advise; they do not refuse.

    `slice_contention` is inline in `_validate_command` today — no `def _check_`
    function holds it (plan trap 2) — and it grades `advisory` (FR-005): the
    author is owed that their declared independence and their own task prose
    disagree, but derivation has already ordered the pair.
    """
    spec_body = (
        "---\nstate: draft\n---\n"
        "\n"
        "## Requirements *(mandatory)*\n"
        "\n"
        "- **FR-001**: The system MUST draw the page.\n"
        "\n"
        "### User Story 1 - Draw the page (Priority: P1)\n"
        "\n"
        "As an operator, I want the page drawn.\n"
        "\n"
        "**Acceptance Scenarios**:\n"
        "\n"
        "1. **Given** a page, **When** I open it, **Then** it is drawn.\n"
        "\n"
        "### User Story 2 - Paint the page (Priority: P2)\n"
        "\n"
        "As an operator, I want the page painted.\n"
        "\n"
        "**Acceptance Scenarios**:\n"
        "\n"
        "1. **Given** a page, **When** I paint it, **Then** it is painted.\n"
        "\n"
        "## Work Graph\n"
        "\n"
        "```yaml\n"
        "US1:\n"
        "  depends_on: []\n"
        "  implements: [FR-001]\n"
        "US2:\n"
        "  depends_on: []\n"
        "  implements: [FR-001]\n"
        "```\n"
    )
    tasks = (
        "# Tasks\n\n"
        "## Phase 1: User Story 1 - Draw the page\n\n"
        "- [ ] T001 [US1-S1] draw the page in app/page.py\n"
        "\n"
        "## Phase 2: User Story 2 - Paint the page\n\n"
        "- [ ] T001 [US2-S1] paint the page in app/page.py\n"
    )
    specs_root = tmp_path / "specs"
    spec_dir = _write_trio(specs_root / "001-contention", spec_body=spec_body, tasks=tasks)

    report = _call_validate_spec(spec_dir, FIXTURE_REPO, str(specs_root))

    assert ("slice_contention", "advisory") in _layers(report), _layers(report)
    assert "slice_contention" in report.checked
    message = next(f.message for f in report.findings if f.layer == "slice_contention")
    assert "app/page.py" in message
    # Advisory alone: a contention never moves the verdict by itself.
    assert not any(f.severity == "refusal" for f in report.findings)
    assert report.verdict == "pass"


# --- US3-S3 / FR-005 / trap 3: the checked-sequence control --------------------


def test_the_checked_sequence_is_the_seeded_then_appended_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T034, US3-S3. The control. `checked` is the seed plus the appends.

    Four names are written before any layer runs; `fixes` — which runs second —
    lands fifth. The run order would put `fixes` second, so a composition that
    tidied `checked` into run order fails here. `_all_pass_phrases` reads
    `checked` for membership only, so stdout cannot catch the tidying (trap 3):
    this assertion and the golden JSON comparison are the only two that can.
    """
    root = tmp_path / "ergane-root"
    root.mkdir()
    _seed_store(root / "doctor.db", ["present/key"])
    monkeypatch_env(monkeypatch, root, tmp_path)

    specs_root = tmp_path / "specs"
    spec_body = _SOUND_BODY.replace(
        "---\nstate: draft\n---\n",
        "---\nstate: draft\nfixes:\n  - present/key\n---\n",
    )
    spec_dir = _write_trio(specs_root / "001-order", spec_body=spec_body)

    report = _call_validate_spec(spec_dir, FIXTURE_REPO, str(specs_root))

    assert report.checked == [
        "frontmatter",
        "workgraph_derivation",
        "persona_registry",
        "scenario_coverage",
        "fixes",
        "prompt_assembly",
        "slice_coverage",
        "slice_contention",
        "sentinels",
        "anchor_resolution",
        "symbol_anchors",
        "evidence",
    ]


def test_the_checked_sequence_matches_the_verb_over_the_same_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T034, US3-S3. The library's sequence and the verb's cannot drift.

    Driven over the same spec, both faces: the composition's `checked` and the
    `--json` document the verb prints. Until US9 makes the verb a renderer over
    this composition these are two compositions, and this is the assertion that
    they agree today and stay agreeing through the rewrite.
    """
    from factory.cli.main import main

    root = tmp_path / "ergane-root"
    root.mkdir()
    _seed_store(root / "doctor.db", ["present/key"])
    monkeypatch_env(monkeypatch, root, tmp_path)

    specs_root = tmp_path / "specs"
    spec_body = _SOUND_BODY.replace(
        "---\nstate: draft\n---\n",
        "---\nstate: draft\nfixes:\n  - present/key\n---\n",
    )
    spec_dir = _write_trio(specs_root / "001-agree", spec_body=spec_body)

    report = _call_validate_spec(spec_dir, FIXTURE_REPO, str(specs_root))

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = _invoke_main(
            ["spec", "validate", "--json", "--target-repo", str(FIXTURE_REPO),
             "--specs-root", str(specs_root), str(spec_dir)]
        )
    document = json.loads(stdout.getvalue())

    assert code == report_verdict_exit(report)
    assert document["checked"] == report.checked


def test_the_fixes_and_evidence_layers_run_but_land_out_of_run_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T034, US3-S3. The two members whose position proves the seed, named.

    `fixes` runs second and appends fifth; `anchor_resolution` runs ninth and
    appends tenth. This is the shape "seeded-then-appended" means, spelled out
    so a future reader cannot mistake it for an accident of this fixture.
    """
    root = tmp_path / "ergane-root"
    root.mkdir()
    _seed_store(root / "doctor.db", ["present/key"])
    monkeypatch_env(monkeypatch, root, tmp_path)

    specs_root = tmp_path / "specs"
    spec_body = _SOUND_BODY.replace(
        "---\nstate: draft\n---\n",
        "---\nstate: draft\nfixes:\n  - present/key\n---\n",
    )
    spec_dir = _write_trio(specs_root / "001-seed", spec_body=spec_body)

    report = _call_validate_spec(spec_dir, FIXTURE_REPO, str(specs_root))

    assert report.checked.index("fixes") == 4
    assert report.checked.index("sentinels") > report.checked.index("slice_contention")
    assert report.checked.index("evidence") == len(report.checked) - 1


# --- US3-S4 / FR-003 / trap 9: the story stays additive ------------------------


#: The SHA-256 of `factory/cli/nouns/spec.py` as this story's base commit has
#: it (`git show d63ad49:factory/cli/nouns/spec.py | sha256sum`, verified
#: against the base object before being pinned here). Pinning the digest rather
#: than shelling out to `git show <base>:…` at test time is deliberate: CI
#: checks the merge ref out with `actions/checkout@v4` at depth 1, so the base
#: commit is not an object the runner has and the subprocess form failed the
#: merge-queue gate with exit 128 — a failure of the checkout's history, not of
#: this branch's content. A digest is decidable from the diff alone, which is
#: what constitution VIII asks of a control, and it fails exactly when the CLI
#: module changes by a single byte.
#:
#: US9 has since landed and made the verb a renderer over this composition,
#: which is the rewrite this story's pin held the line against — the pin's job
#: was to prove *US3* stayed additive, and the golden artifacts below prove the
#: rewrite stayed byte-identical. What survives here is the standing control
#: the pin left behind: the composition must never import from the CLI module
#: (trap 17), asserted on its source.
_CLI_MODULE_DIGEST_AT_BASE = (
    "88acd311a027d91d9f846b0dd44603d657eab3afa46be0e40b8ec33355b1cd0e"
)


def test_the_verb_is_byte_for_byte_unchanged_by_this_story() -> None:
    """T070, US3-S4. The composition and the verb are two modules, one direction.

    The digest pin held while this story ran; US9's renderer has since replaced
    the duplicated body it guarded, and the golden comparisons at the bottom of
    this file are the proof the replacement moved no printed byte. What must
    stay true for the life of the composition is the import direction: the
    module US3 added reads nothing from `factory.cli` — an import back re-enters
    a half-initialised module before its names exist (plan trap 17).
    """
    source = composition_module_path().read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("factory.cli"), (
                f"the composition imports from {node.module} (trap 17)"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("factory.cli"), (
                    f"the composition imports {alias.name} (trap 17)"
                )


def composition_module_path() -> Path:
    """The composition module's path, beside the CLI module's."""
    return CLI_PATH.parent.parent.parent / "spec" / "composition.py"


def test_us1_goldens_still_match_with_this_story_having_done_nothing() -> None:
    """T070, US3-S4. The six golden artifacts, compared as US1 left them.

    Re-runs the three-stream comparison US1's own test makes, straight from the
    same helpers, so the composition module's arrival provably moved no output.
    """
    from tests.test_133_us1_typed_report_and_golden_captures import (
        DEFECTIVE_TRIO,
        _normalise,
        _run_validate,
    )

    for trio_dir, name in [(CLEAN_TRIO, "clean"), (DEFECTIVE_TRIO, "defective")]:
        code, stdout, stderr = _run_validate(trio_dir, as_json=False)
        expected_stdout = (GOLDEN / name / "stdout.txt").read_text(encoding="utf-8")
        expected_stderr = (GOLDEN / name / "stderr.txt").read_text(encoding="utf-8")
        assert _normalise(stdout, REPO_ROOT) == expected_stdout
        assert _normalise(stderr, REPO_ROOT) == expected_stderr

        _code, json_stdout, json_stderr = _run_validate(trio_dir, as_json=True)
        expected_json = (GOLDEN / name / "json.txt").read_text(encoding="utf-8")
        assert _normalise(json_stdout, REPO_ROOT) == expected_json
