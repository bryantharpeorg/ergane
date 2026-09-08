"""133-US1: a typed report exists in `factory.spec`, and today's output is frozen.

Two halves, and the order between them is the point of the story:

- **The typed report.** `factory.spec` exports `SpecValidation` and the finding
  type every relocated body will construct. The finding keeps
  `_ValidateFinding`'s constructor shape exactly — positional layer, positional
  message, keyword-only `severity` defaulting to `"refusal"` — so a checker
  moved in US2/US5/US6 needs no signature edit (plan trap 7). The report holds
  all four channels as separate members (FR-002): collapsing "skipped" into
  "passed" or "failed" destroys information the verb prints today (plan trap
  10). Information notes and skipped layers never move the verdict (US1-S3) —
  the deliberate non-effect on the exit code is what makes the sentinel channel
  safe to state.

- **The golden captures.** Six artifacts — each of two fixture trios' stdout,
  stderr and `--json` document — committed before any layer body moves, with
  the repository root normalised out. Three of the four rendered channels print
  to **stderr** (`factory/cli/nouns/spec.py:710`, `:733`, `:739`), so a
  stdout-only capture would freeze none of the four prefixes US3 is forbidden
  to change (plan trap 19). Two trios because a run carrying a refusal never
  prints the all-pass sentence (plan trap 3), so one trio cannot cover both
  shapes. Synthetic fixtures under `tests/`, never a corpus spec (plan trap 12),
  each in a parent directory holding nothing else because the frontmatter layer
  reads `spec_dir.parent` as the specs root (plan trap 13).

Red first. `uv run pytest tests/test_133_us1_typed_report_and_golden_captures.py
-q --no-header`, run against this tree with these tests committed and no
`factory/spec/` package, verbatim::

    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_factory_spec_exports_the_typed_report_and_finding
    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_report_holds_all_four_channels_as_separate_members
    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_information_only_report_verdicts_as_a_pass
    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_finding_type_keeps_the_validate_finding_constructor_shape
    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_cli_module_no_longer_defines_the_finding_type_but_binds_the_import
    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_clean_trio_matches_its_three_golden_artifacts
    FAILED tests/test_133_us1_typed_report_and_golden_captures.py::test_the_defective_trio_matches_its_three_golden_artifacts
    7 failed, 3 passed in 1.29s

The three that passed red are the controls the story needs before any capture
is trusted: the golden comparison helpers themselves (normalisation is
idempotent, both directions), and the assertion that the fixture layout is
exactly two trios in two parents plus one shared target repository — true from
the moment T009's fixtures were committed, and load-bearing for T006, which
compares against artifacts these same tests freeze.

Green after, same command::

    10 passed in 1.88s
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The fixture trios and the target repository they share (T009). The parent of
#: each trio is that trio's specs root — the frontmatter layer reads
#: `spec_dir.parent` (`factory/cli/nouns/spec.py:1001`), so the layout is two
#: sibling parents under one fixtures root, holding nothing else.
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "spec_validate"
CLEAN_TRIO = FIXTURES / "clean-specs" / "001-clean-trio"
DEFECTIVE_TRIO = FIXTURES / "defective-specs" / "002-defective-trio"
FIXTURE_REPO = FIXTURES / "target-repo"

#: The golden artifacts, three per trio (FR-014, plan trap 19).
GOLDEN = Path(__file__).resolve().parent / "golden" / "spec_validate"


def _normalise(text: str, root: Path) -> str:
    """Replace the repository root with a placeholder, on every stream.

    The fixes layer's information note embeds the absolute store path, the
    evidence report the absolute manifest path, and every skipped-layer reason
    the `--target-repo` string; a verbatim capture goes red on every other
    checkout, the merge-group build included (plan trap 11). Normalise on both
    sides of every comparison so the committed artifact is host-independent.
    """
    return text.replace(str(root), "<REPO_ROOT>")


def _run_validate(spec_dir: Path, *, as_json: bool) -> tuple[int, str, str]:
    """Run the verb over one trio, capturing the two streams separately.

    In-process through the CLI entry point: the same face an operator drives,
    with stdout and stderr captured apart because exactly three writes reach
    stdout (the all-pass sentence, the judge-evidence report and the `--json`
    document) and every finding, skip and information line reaches stderr
    (plan trap 19).
    """
    from factory.cli.main import main

    argv = ["spec", "validate", str(spec_dir), "--target-repo", str(FIXTURE_REPO)]
    if as_json:
        argv.append("--json")
    import contextlib
    import io

    # `main` prints via `print`, so swap the two streams around the call. The
    # capsys fixture is deliberately not used here: the golden tests are the one
    # place the captured streams must be exactly what a subprocess would see,
    # and swapping the real objects keeps that guarantee independent of
    # whatever else a future fixture does to capsys.
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _read_golden(trio: str, stream: str) -> str:
    path = GOLDEN / trio / f"{stream}.txt"
    return path.read_text(encoding="utf-8")


# --- US1-S1 / FR-001: the package and its two exported types ------------------


def test_factory_spec_exports_the_typed_report_and_finding() -> None:
    """T001, US1-S1. Import the package; assert what a consumer gets.

    `SpecValidation` is the type the ledger row asks for, and the finding type
    carries the three fields every relocated body constructs: layer, severity,
    message. Both must live in `factory.spec` — the import direction is one-way
    from US1 onward (plan trap 17), so a type still defined in the CLI module
    would make the first relocation unimportable.
    """
    import factory.spec

    assert hasattr(factory.spec, "SpecValidation")
    finding_type = factory.spec.SpecFinding
    fields = {field.name for field in dataclasses.fields(finding_type)}
    assert {"layer", "severity", "message"} <= fields


# --- US1-S2 / FR-002: four channels, four members -----------------------------


def test_the_report_holds_all_four_channels_as_separate_members() -> None:
    """T002, US1-S2. Refusals, advisories, notes and skips, each its own member.

    The skipped channel is what makes today's refusals useful (plan trap 10):
    when the work graph does not compile, later layers are reported as *not
    checked* with a reason, and a report that folds that into passed or failed
    destroys information the verb prints and the exit code cannot carry.
    """
    from factory.spec import SpecFinding, SpecValidation

    report = SpecValidation(
        refusals=[SpecFinding("evidence", "a refusal")],
        advisories=[SpecFinding("slice_contention", "an advisory", severity="advisory")],
        information=[SpecFinding("sentinel", "a note")],
        skipped=[{"layer": "anchor_resolution", "reason": "none of the cited paths"}],
    )
    assert [finding.message for finding in report.refusals] == ["a refusal"]
    assert [finding.message for finding in report.advisories] == ["an advisory"]
    assert [note.message for note in report.information] == ["a note"]
    assert report.skipped == [
        {"layer": "anchor_resolution", "reason": "none of the cited paths"}
    ]
    # Skips carry their reason string, per the table in the spec.
    assert report.skipped[0]["reason"]


def test_information_only_report_verdicts_as_a_pass() -> None:
    """T003, US1-S3. The control. Notes and skips never move the verdict.

    The sentinel channel is stated, never counted (`factory/cli/nouns/spec.py`
    comment above the sentinel loop): a report carrying only information
    entries has no refusal, and the exit code reads refusals alone. A verdict
    that moved on notes or skips would make every ERGANE-TODO blank a failing
    spec — the opposite of the deliberate non-effect the verb's behaviour
    freezes.
    """
    from factory.spec import SpecFinding, SpecValidation

    notes_only = SpecValidation(
        refusals=[],
        advisories=[],
        information=[
            SpecFinding("sentinel", "spec.md:3: ERGANE-TODO: fill me"),
            SpecFinding("fixes", "verified 2 finding key(s)"),
        ],
        skipped=[{"layer": "anchor_resolution", "reason": "no readable target"}],
    )
    assert notes_only.verdict == "pass"

    refusals_only = SpecValidation(
        refusals=[SpecFinding("evidence", "refusal")],
        advisories=[],
        information=[],
        skipped=[],
    )
    assert refusals_only.verdict == "fail"


# --- US1-S4 / FR-001: the constructor shape a relocation cannot change --------


def test_the_finding_type_keeps_the_validate_finding_constructor_shape() -> None:
    """T004, US1-S4. Same shape as `_ValidateFinding` has today.

    Constructed with a layer and a message alone it defaults its severity to
    `refusal`, and it accepts `advisory` as the keyword — the same constructor
    shape the CLI module's private class has
    (`factory/cli/nouns/spec.py:483`), so no relocated checker needs a signature
    edit (plan trap 7).
    """
    from factory.spec import SpecFinding

    default = SpecFinding("workgraph", "the work graph did not compile")
    assert default.severity == "refusal"
    assert default.layer == "workgraph"
    assert default.message == "the work graph did not compile"

    advisory = SpecFinding(
        "slice_contention", "us1 and us2 both touch prompt.py", severity="advisory"
    )
    assert advisory.severity == "advisory"


# --- US1-S6 / FR-001: the CLI module binds, it does not define ----------------


def test_the_cli_module_no_longer_defines_the_finding_type_but_binds_the_import() -> None:
    """T005, US1-S6. The class statement is gone; the name still resolves.

    Read the module source for `class _ValidateFinding` — a module-level
    attribute check would also pass on an import — and assert the object bound
    under the old local name reports its `__module__` under `factory.spec`.
    Binding the import under the same local name is what keeps the module's
    twenty-odd construction sites out of this story's diff (plan T008).

    US9 retired the binding with every construction site (FR-015): the
    definition is gone from the CLI module and the type's home is asserted
    where every construction site now lives — `factory.spec`.
    """
    import factory.cli.nouns.spec as spec_noun

    module_source = Path(spec_noun.__file__).read_text(encoding="utf-8")
    assert "class _ValidateFinding" not in module_source
    assert "_ValidateFinding" not in module_source, (
        "the CLI module no longer constructs findings of its own (FR-008)"
    )

    import factory.spec

    assert factory.spec.SpecFinding.__module__.split(".")[:2] == ["factory", "spec"]


# --- US1-S5 / FR-014: six golden artifacts, six comparisons --------------------


def test_both_trios_and_the_shared_repo_are_laid_out_as_the_spec_declares() -> None:
    """T009's layout control. Two trios, two parents, one target repository.

    The frontmatter layer reads `spec_dir.parent` as the specs root, so each
    trio sits in a parent directory holding nothing else (plan trap 13); both
    trios share one target repository whose committed manifest declares one
    gate (plan trap 20). This test is the reason T006's comparison cannot be
    green against an empty or reorganised fixtures tree.
    """
    assert CLEAN_TRIO.is_dir()
    assert DEFECTIVE_TRIO.is_dir()
    assert FIXTURE_REPO.is_dir()
    assert (FIXTURE_REPO / "ergane.yaml").is_file()

    clean_parent = CLEAN_TRIO.parent
    assert sorted(path.name for path in clean_parent.iterdir()) == [
        "001-clean-trio"
    ], "the clean trio's parent is its specs root and holds nothing else"
    defective_parent = DEFECTIVE_TRIO.parent
    assert sorted(path.name for path in defective_parent.iterdir()) == [
        "002-defective-trio"
    ], "the defective trio's parent is its specs root and holds nothing else"


@pytest.mark.parametrize(
    ("trio_dir", "name"), [(CLEAN_TRIO, "clean"), (DEFECTIVE_TRIO, "defective")]
)
def test_the_trio_matches_its_three_golden_artifacts(
    trio_dir: Path, name: str
) -> None:
    """T006, US1-S5. Three streams, three artifacts, byte for byte.

    The two streams are captured separately (`>stdout.txt 2>stderr.txt` is the
    plan's spelling) because every finding, skip and information line prints to
    stderr while the all-pass sentence and the judge-evidence report print to
    stdout (plan trap 19). The repository root is normalised out on both sides
    of every comparison (plan trap 11).
    """
    code, stdout, stderr = _run_validate(trio_dir, as_json=False)
    expected_stdout = _read_golden(name, "stdout")
    expected_stderr = _read_golden(name, "stderr")
    assert _normalise(stdout, REPO_ROOT) == expected_stdout
    assert _normalise(stderr, REPO_ROOT) == expected_stderr

    # The `--json` document is the third artifact, compared byte for byte after
    # normalisation (FR-014).
    _code, json_stdout, json_stderr = _run_validate(trio_dir, as_json=True)
    expected_json = _read_golden(name, "json")
    assert _normalise(json_stdout, REPO_ROOT) == expected_json
    assert json_stderr == "", "the --json face prints nothing on stderr"
    document: Any = json.loads(json_stdout)
    assert isinstance(document, dict)
    assert document["spec_dir"].endswith(trio_dir.name)


def test_the_clean_trio_prints_the_all_pass_sentence_and_the_defective_one_refuses() -> None:
    """T010's committed content control, asserted rather than trusted.

    The clean trio's stdout artifact carries the all-pass sentence and its
    stderr artifact carries an information note and a skipped-layer line; the
    defective trio's stderr carries a refusal line and an advisory line while
    its stdout carries the judge-evidence report and no all-pass sentence. A
    golden that silently lost one of these shapes would freeze nothing for the
    stories that follow (plan traps 3 and 4).
    """
    clean_stdout = _read_golden("clean", "stdout")
    clean_stderr = _read_golden("clean", "stderr")
    assert "all pass" in clean_stdout
    assert "noted, not a refusal" in clean_stderr
    assert "not checked" in clean_stderr

    defective_stdout = _read_golden("defective", "stdout")
    defective_stderr = _read_golden("defective", "stderr")
    assert "— refusal:" in defective_stderr
    assert "— advisory:" in defective_stderr
    assert "what the judge will be shown" in defective_stdout
    assert "all pass" not in defective_stdout
    assert "all pass" not in defective_stderr