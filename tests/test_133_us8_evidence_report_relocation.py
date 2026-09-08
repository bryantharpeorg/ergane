"""133-US8: the judge-evidence report type and checker leave the CLI module.

The final relocation, and the other half of the family US6 severed: the report
dataclass the verb prints and serialises, its two small companions, and the
checker itself — 9,530 bytes across six top-level names at 57bf698, closing out
the 18,393-byte evidence family. US6 moved the vocabulary first because the
direction of the one seam the family has was checked, not assumed: **the
vocabulary half calls nothing in the report half.** This story moves the half
that reads it, and when it lands no name of the evidence family remains defined
in the CLI module (US8-S5) — the family entered this spec as one span and
arrives whole, in two stories.

Five controls, one per acceptance-scenario concern:

- **US8-S1 (T059)**: the CLI module no longer *defines* any of the six names —
  asserted from the module's AST, not by importing, because the import-back
  T064 binds the same names in the CLI module's namespace and an attribute
  check cannot tell a definition from an import (the helper US6's T026 and
  US7's T067 use). Identity and `__module__` are asserted second, so a
  re-declaration cannot pass as a move.
- **US8-S2 (T060)**: the circular-import control. The moved module's source
  contains no import naming `factory.cli` — the checker reads the vocabulary
  US6 put in `factory.spec.evidence`, and an import back re-enters a
  half-initialised module and raises `ImportError` at interpreter start (trap
  17). Red pre-move in its decisive half: the checker is not yet defined in
  the moved module.
- **US8-S3 (T061)**: the moved report type's `as_dict()` and `lines()` output
  are unchanged — the verb serialises the first into the `--json` document and
  prints the second, so both are stdout (trap 19) — and the moved checker
  still **returns** the report as well as appending to the caller-owned lists
  (trap 7). It is the one checker in the family that does both; a relocation
  that folds the return into the lists deletes the `judge_evidence` key, and
  with it the byte-for-byte golden of that document.
- **US8-S4 (T065)**: the golden comparison over both fixture trios, committed
  as evidence under `tests/_us8_outputs/`, empty on all three streams.
  Standing guard, named by path: `tests/
  test_133_us1_typed_report_and_golden_captures.py`.
- **US8-S5 (T062)**: **no** name of the judge-evidence family is defined in
  the CLI module any longer, read from the module source. The vocabulary
  names US6 moved are asserted absent too — the family leaves in two stories
  and this is the assertion that it arrived whole.

Red first. `uv run pytest tests/test_133_us8_evidence_report_relocation.py
-q --no-header`, run against this tree before T063 moved anything, verbatim::

    FAILED tests/test_133_us8_evidence_report_relocation.py::test_the_cli_module_no_longer_defines_the_report_family
    FAILED tests/test_133_us8_evidence_report_relocation.py::test_the_moved_module_imports_nothing_from_the_cli_module
    FAILED tests/test_133_us8_evidence_report_relocation.py::test_the_moved_report_type_keeps_its_as_dict_and_lines_output
    FAILED tests/test_133_us8_evidence_report_relocation.py::test_the_moved_checker_still_returns_its_report_and_appends_to_the_callers_lists
    FAILED tests/test_133_us8_evidence_report_relocation.py::test_no_name_of_the_evidence_family_is_defined_in_the_cli_module
    5 failed, 0 passed

Green after the move, same command::

    5 passed
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
REPORT_PATH = REPO_ROOT / "factory" / "spec" / "evidence.py"

#: The shared fixture target repository US1 committed: its `ergane.yaml`
#: declares one gate (`smoke`), which is what makes the defective trio's
#: evidence refusal a refusal rather than a skip (plan trap 20).
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "spec_validate" / "target-repo"
DEFECTIVE_TRIO = (
    REPO_ROOT / "tests" / "fixtures" / "spec_validate" / "defective-specs" / "002-defective-trio"
)

#: The six names FR-017 names, spelled exactly as the task list spells them:
#: the report dataclass the verb prints and serialises, its two small
#: companions, the warning composer, the criteria reader and the checker.
REPORT_FAMILY = (
    "_check_evidence",
    "_JudgeEvidenceReport",
    "_StoryCriteria",
    "_BorderlineClause",
    "_borderline_warning",
    "_story_criteria",
)

#: The ten names US6 moved — asserted absent from the CLI module in T062,
#: which is the assertion that the family arrived whole rather than leaving a
#: vocabulary half behind. They are already gone; this tuple is the whole
#: family's final roll call, not a claim about this story's diff.
VOCABULARY_FAMILY = (
    "_RUNTIME_MARKERS",
    "_DIFF_EVIDENCE_RE",
    "_PROVABLE_EXAMPLE",
    "_then_clauses",
    "_runtime_markers",
    "_names_a_declared_gate",
    "_manifest_declares_no_gates",
    "_Declarations",
    "_declared_gates",
    "_evidence_refusal",
)


def _module_bindings(source: str) -> set[str]:
    """Every name the module source binds at top level.

    Read from the AST rather than from `vars(module)`: the import-back T064
    binds these same names in the CLI module's namespace, so an attribute
    check cannot tell a definition from an import. Only the source can (the
    same helper US6's T026 and US7's T067 use).
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


# --- US8-S1 / FR-017 / trap 17: nothing left behind ---------------------------


def test_the_cli_module_no_longer_defines_the_report_family() -> None:
    """T059, US8-S1. Six names defined in `factory.spec`, imported back, gone here.

    `_JudgeEvidenceReport` is the type the verb binds at the call site, prints
    through `lines()` and serialises under the `judge_evidence` key through
    `as_dict()`; a second copy left behind would pass the name assertion and
    fail the pair that follows. Leaving any of the six behind makes a moved
    body reach back into the module it just left, which cannot import (trap
    17): the CLI module imports from `factory.spec` at module scope.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    bindings = _module_bindings(source)
    stranded = sorted(set(REPORT_FAMILY) & bindings)
    assert stranded == [], f"still defined in the CLI module: {stranded}"

    # The import-back each relocation story left behind is retired as of US9
    # (133 FR-015): the verb is a renderer over `validate_spec` and imports
    # none of the relocated layers, so the family is asserted absent from the
    # CLI module outright — defined in `factory.spec.evidence`.
    present = sorted(
        name
        for name in REPORT_FAMILY
        if name not in _module_bindings(REPORT_PATH.read_text(encoding="utf-8"))
    )
    assert present == [], f"not defined in factory.spec.evidence: {present}"


def test_the_moved_module_imports_nothing_from_the_cli_module() -> None:
    """T060, US8-S2. The circular-import control (trap 17). The direction is one-way.

    Read the moved module's source and assert it contains no import naming
    `factory.cli`, in both the `from … import` and the `import … as …`
    spellings, over the whole of `factory.spec`'s evidence module — the
    checker this story moves reads the vocabulary US6 put there, so it reads
    everything it needs from its own package. Red pre-move only in its
    decisive half: the no-back-import half is true today, so the control is
    completed by the checker being *defined* in the moved module, which is
    false until T063 moves it.
    """
    source = REPORT_PATH.read_text(encoding="utf-8")
    back_imports: list[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("factory.cli"):
            back_imports.append(f"from {node.module} import …")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("factory.cli"):
                    back_imports.append(f"import {alias.name}")
    assert back_imports == [], (
        f"factory/spec/evidence.py imports from the CLI module (trap 17): {back_imports}"
    )

    assert set(REPORT_FAMILY) <= _module_bindings(source), (
        "the report family is not defined in factory.spec.evidence — it has not moved"
    )


# --- US8-S3 / FR-017 / traps 7 and 19: the report type, unchanged -------------


def test_the_moved_report_type_keeps_its_as_dict_and_lines_output() -> None:
    """T061, US8-S3. The verb prints `lines()` and serialises `as_dict()`.

    Both are stdout, so both are already frozen by US1's golden comparisons —
    the `--json` document carries `as_dict()`'s output under `judge_evidence`
    and the report block rides the stdout artifact (trap 19). What a golden
    cannot catch is a drift that only shows off the golden's two fixture trios,
    so the two methods are driven here over a shape the trios do not carry: a
    report with a *borderline* warning and a manifest that declares nothing,
    both of which the fixture trios exercise empty. The fixture-manifest read
    is the real one — the same `_declared_gates` read the verb's run performs —
    because a report's `as_dict()` answers with what a manifest declares, not
    with a shape this test invents.
    """
    import factory.spec.evidence as spec_noun
    import factory.spec.evidence as evidence

    report_type = spec_noun._JudgeEvidenceReport
    assert report_type is evidence._JudgeEvidenceReport
    assert report_type.__module__.startswith("factory.spec")

    # A report carrying one borderline warning over the fixture repository's
    # real manifest read — the warnings channel renders through `lines()` and
    # `as_dict()` alike, and the fixture trios leave it empty.
    declared = evidence._declared_gates(str(FIXTURE_REPO))
    criteria = evidence._StoryCriteria(story="US1", title="The page is drawn", scenarios=["US1-S1"])
    warning = evidence._BorderlineClause(
        scenario_id="US1-S1",
        clause="the font renders correctly in the browser.",
        phrases=["in the browser", "renders correctly"],
        message=evidence._borderline_warning(
            "US1-S1", "the font renders correctly in the browser.", ["in the browser", "renders correctly"], declared.gates
        ),
    )
    report = evidence._JudgeEvidenceReport([criteria], declared, [warning], 0, False)

    document = report.as_dict()
    assert document["diff"] == {
        "abridged_above_bytes": 65536,
        "refused_above_bytes": declared.refusal_bytes,
    }
    assert document["criteria"] == [
        {"story": "US1", "title": "The page is drawn", "scenarios": ["US1-S1"]}
    ]
    assert document["gates"]["declared"] == ["smoke"]
    assert document["gates"]["manifest"] == str(declared.manifest)
    assert len(document["warnings"]) == 1
    assert document["warnings"][0]["scenario_id"] == "US1-S1"
    assert document["warnings"][0]["phrases"] == ["in the browser", "renders correctly"]
    assert document["warnings"][0]["message"] == warning.message
    assert document["all_provable"] is False

    rendered = report.lines(DEFECTIVE_TRIO / "spec.md")
    assert rendered[0].endswith(": what the judge will be shown for each node")
    assert any("a warning, not a refusal: " + warning.message in line for line in rendered)
    assert any("the criteria — each node is shown its own story's scenarios" in line for line in rendered)
    assert any("the gates — the results of the gates" in line and "smoke" in line for line in rendered)
    # `all_provable` is False here — the clause is borderline, not provable — so
    # the closing sentence is not rendered and the warning line is last.
    assert "every Then-clause names evidence" not in "\n".join(rendered)
    assert rendered[-1].startswith("  a warning, not a refusal: ")


def test_the_moved_checker_still_returns_its_report_and_appends_to_the_callers_lists() -> None:
    """T061, US8-S3. The one checker in the family that both accumulates and returns.

    `_check_evidence` appends refusals and skips into the caller-owned lists
    exactly like every other checker in the family *and* returns the
    `_JudgeEvidenceReport` the verb binds at the call site, prints through and
    serialises under the `judge_evidence` key. A relocation that folds the
    return into the lists deletes that key — and with it the byte-for-byte
    golden of the `--json` document, which the verb's output comparisons
    freeze. Driven over the defective fixture trio, whose single unevidenceable
    clause is the one refusal the family composes.
    """
    import factory.spec.evidence as spec_noun
    import factory.spec.evidence as evidence

    assert spec_noun._check_evidence is evidence._check_evidence
    assert evidence._check_evidence.__module__.startswith("factory.spec")

    parameters = list(__import__("inspect").signature(evidence._check_evidence).parameters)
    assert parameters == ["spec_text", "target_repo", "findings", "skipped", "checked"]

    spec_text = (DEFECTIVE_TRIO / "spec.md").read_text(encoding="utf-8")
    findings: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    report = spec_noun._check_evidence(spec_text, str(FIXTURE_REPO), findings, skipped, checked)

    # The accumulations, unchanged.
    assert checked == ["evidence"]
    assert skipped == []
    assert len(findings) == 1
    assert findings[0].layer == "evidence"
    assert findings[0].severity == "refusal"

    # The return, unchanged — the shape the verb binds, prints and serialises.
    assert isinstance(report, evidence._JudgeEvidenceReport)
    assert report.refused == 1
    assert report.all_provable is False
    assert report.criteria[0].story == "US1"
    assert report.criteria[0].scenarios == ["US1-S1"]
    assert report.declarations.gates == frozenset({"smoke"})

    document = json.loads(json.dumps(report.as_dict()))
    assert document["all_provable"] is False
    assert document["criteria"] == [
        {"story": "US1", "title": "The page is drawn", "scenarios": ["US1-S1"]}
    ]


# --- US8-S5 / FR-017: the family arrived whole --------------------------------


def test_no_name_of_the_evidence_family_is_defined_in_the_cli_module() -> None:
    """T062, US8-S5. The whole sixteen-name family, read from the module source.

    The family entered this spec as one span, leaves it in two stories and
    arrives whole: US6 moved the vocabulary half, this story the report half.
    T059's AST read covers the six names this story moves; this test covers
    the sixteen together — the vocabulary names as well, asserted absent from
    the CLI module's bindings, so a story that restored one of them could not
    pass by the others staying gone. US9 retired the import-backs (133 FR-015):
    the verb imports none of the family, so the arrival-whole half reads the
    moved module's bindings — every name defined in `factory.spec.evidence`.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    bindings = _module_bindings(source)
    whole_family = tuple(VOCABULARY_FAMILY) + tuple(REPORT_FAMILY)
    stranded = sorted(set(whole_family) & bindings)
    assert stranded == [], f"still defined in the CLI module: {stranded}"

    present = sorted(
        name
        for name in whole_family
        if name not in _module_bindings(REPORT_PATH.read_text(encoding="utf-8"))
    )
    assert present == [], f"not defined in factory.spec.evidence: {present}"