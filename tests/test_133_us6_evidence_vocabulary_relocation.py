"""133-US6: the judge-evidence vocabulary and refusal grammar leave the CLI module.

The fourth relocation, and the first half of the largest object graph in the
module — 18,393 bytes across sixteen top-level names at 57bf698, which at the
measured 2.36x relocation cost no single story can carry inside the 65,536-byte
bound. The family is severed on the one seam it has: **the vocabulary half calls
nothing in the report half.** That direction was checked in the tree, not
assumed, so the vocabulary moves first and the report type and the checker
follow in US8.

Four controls, one per acceptance-scenario concern:

- **US6-S1 (T026)**: the CLI module no longer *defines* any of the ten names —
  asserted from the module's AST, not by importing, because the import-back
  T030 binds the same names in the CLI module's namespace and an attribute
  check cannot tell a definition from an import (the helper US5's T018 and
  US7's T067 use). `_RUNTIME_MARKERS` is the closed marker vocabulary
  `_runtime_markers` reads and must travel with its only consumer. Nothing is
  asserted about `_check_evidence`, `_JudgeEvidenceReport`, `_StoryCriteria`,
  `_BorderlineClause`, `_borderline_warning` or `_story_criteria` — those are
  Phase 6's (US8) and they are still defined here.
- **US6-S2 (T027)**: the import-back control. `_check_evidence` has not moved
  and reads most of what this story moves, so every moved name still resolves
  as an attribute of `factory.cli.nouns.spec` with `__module__` under
  `factory.spec` — and the surviving checker is driven end to end and still
  produces its report. A second copy left behind passes the name assertion and
  fails the pair.
- **US6-S4 (T028)**: given a spec whose only defect is an unevidenceable
  Then-clause, the refusal the surviving checker **appends to the caller-owned
  `findings` list** — it appends, it does not raise (trap 7) — is byte for byte
  the string US1's golden capture of the defective trio's **stderr** recorded.
  This story moves `_evidence_refusal`, the function that composes that string,
  so this is the assertion that catches a rewording (trap 9). The refusal line
  is on stderr and in the `--json` `findings[].message`; it is in no stdout
  artifact (trap 19).

Red first. `uv run pytest tests/test_133_us6_evidence_vocabulary_relocation.py
-q --no-header`, run against this tree before T029 moved anything, verbatim::

    FAILED tests/test_133_us6_evidence_vocabulary_relocation.py::test_the_cli_module_no_longer_defines_the_vocabulary_family
    FAILED tests/test_133_us6_evidence_vocabulary_relocation.py::test_the_moved_module_imports_nothing_from_the_cli_module
    FAILED tests/test_133_us6_evidence_vocabulary_relocation.py::test_the_surviving_checker_reads_the_moved_objects_and_still_produces_its_report
    FAILED tests/test_133_us6_evidence_vocabulary_relocation.py::test_the_refusal_appended_is_byte_for_byte_the_golden_stderr_string
    4 failed, 0 passed

Green after the move, same command::

    4 passed
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPO_ROOT / "factory" / "cli" / "nouns" / "spec.py"
VOCABULARY_PATH = REPO_ROOT / "factory" / "spec" / "evidence.py"

#: The shared fixture target repository US1 committed: its `ergane.yaml`
#: declares one gate (`smoke`), which is what makes the defective trio's
#: evidence refusal a refusal rather than a skip (plan trap 20).
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "spec_validate" / "target-repo"
DEFECTIVE_TRIO = (
    REPO_ROOT / "tests" / "fixtures" / "spec_validate" / "defective-specs" / "002-defective-trio"
)

#: The ten names FR-012 names, spelled exactly as the task list spells them.
#: `_RUNTIME_MARKERS` is the closed marker vocabulary `_runtime_markers` reads;
#: it must travel with the reader that is its only consumer.
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

#: The names Phase 6 (US8) still owned when this story landed — asserted to
#: still be defined in the CLI module, which was the "nothing else moved" half
#: of T026. US8 has since moved all six, so the tuple is empty: nothing this
#: story left behind remains defined in the CLI module, and US8's T062 asserts
#: the whole sixteen-name family gone from it.
STILL_HERE: tuple[str, ...] = ()


def _module_bindings(source: str) -> set[str]:
    """Every name the module source binds at top level.

    Read from the AST rather than from `vars(module)`: the import-back T030
    binds these same names in the CLI module's namespace, so an attribute check
    cannot tell a definition from an import. Only the source can (the same
    helper US5's T018 and US7's T067 use).
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


# --- US6-S1 / FR-012 / trap 17: nothing left behind ---------------------------


def test_the_cli_module_no_longer_defines_the_vocabulary_family() -> None:
    """T026, US6-S1. Ten names defined in `factory.spec`, imported back, gone here.

    `_RUNTIME_MARKERS` is the closed marker vocabulary `_runtime_markers` reads;
    splitting those two strands a constant of this layer in the CLI module, or
    worse, carrying it away a story early. Leaving any of the ten behind makes a
    moved body reach back into the module it just left, which cannot import
    (trap 17). The six report-half names were asserted to still be defined here
    when this story landed; US8 has since moved them, and the empty STILL_HERE
    tuple is what that edit left of the nothing-else-moved half.
    """
    source = CLI_PATH.read_text(encoding="utf-8")
    bindings = _module_bindings(source)
    stranded = sorted(set(VOCABULARY_FAMILY) & bindings)
    assert stranded == [], f"still defined in the CLI module: {stranded}"

    # US9 retired the import-backs (FR-015): the family is asserted absent from the CLI module.
    present = sorted(set(VOCABULARY_FAMILY) - _module_bindings(VOCABULARY_PATH.read_text(encoding="utf-8")))
    assert present == [], f"not defined in factory.spec.evidence: {present}"

    still_defined = sorted(name for name in STILL_HERE if name not in bindings)
    assert still_defined == [], f"moved something this story does not own: {still_defined}"


# --- US6-S2 / FR-012 / trap 17: one object in both modules ---------------------


def test_the_moved_module_imports_nothing_from_the_cli_module() -> None:
    """T027's circular-import control (trap 17). The direction is one-way.

    Read the moved module's source and assert it contains no import naming
    `factory.cli`, in both the `from … import` and the `import … as …`
    spellings. Nothing in `factory/spec/` may import from the CLI module at
    all — an import back re-enters a half-initialised module and raises
    `ImportError` at interpreter start, not at call time. Red pre-move only in
    its decisive half: the vocabulary is not yet defined in the moved module,
    which the second assertion pins.
    """
    source = VOCABULARY_PATH.read_text(encoding="utf-8")
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

    assert set(VOCABULARY_FAMILY) <= _module_bindings(source), (
        "the vocabulary is not defined in factory.spec.evidence — it has not moved"
    )


def test_the_surviving_checker_reads_the_moved_objects_and_still_produces_its_report() -> None:
    """T027, US6-S2. The import-back control, both halves, then the drive.

    `_check_evidence` read most of what this story moves, and when this story
    landed the first half asserted every moved name still resolved as an
    attribute of `factory.cli.nouns.spec`, the very object
    `factory.spec.evidence` defines, carrying `__module__` under
    `factory.spec` — a second copy left behind passes the name assertion and
    fails the pair. US8 has since moved the checker and the report type it
    returns, so the pair is asserted at the moved module alone and the drive
    goes through the CLI module's import-back binding, which is still what
    `_validate_command` reaches.
    """
    import factory.spec.evidence as spec_noun
    import factory.spec.evidence as evidence

    for name in VOCABULARY_FAMILY:
        assert getattr(spec_noun, name) is getattr(evidence, name), (
            f"{name} must be one object in both modules"
        )
    assert evidence._then_clauses.__module__.startswith("factory.spec")
    assert evidence._evidence_refusal.__module__.startswith("factory.spec")
    assert evidence._declared_gates.__module__.startswith("factory.spec")
    assert evidence._Declarations.__module__.startswith("factory.spec")

    spec_text = (
        "---\nstate: draft\n---\n\n## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST draw the page.\n\n"
        "### User Story 1 - The page is drawn (Priority: P1)\n\n"
        "As an operator, I want the page drawn.\n\n"
        "**Acceptance Scenarios**:\n\n"
        "1. **Given** a built page, **When** the operator opens it, **Then** "
        "the gate `smoke` passes.\n\n"
        "## Work Graph\n\n"
        "```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n"
    )
    findings: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    report = spec_noun._check_evidence(spec_text, str(FIXTURE_REPO), findings, skipped, checked)

    assert checked == ["evidence"]
    assert findings == []
    assert skipped == []
    assert report.all_provable is True
    document = report.as_dict()
    assert document["gates"]["declared"] == ["smoke"]
    assert document["all_provable"] is True
    # US8 moved the report type; the object the CLI module binds is still the
    # one this module defines, reached through the import-back.
    assert report.__class__ is evidence._JudgeEvidenceReport
    assert report.__class__.__module__.startswith("factory.spec")


# --- US6-S4 / FR-012 / traps 7, 9 and 19: the golden refusal string ------------


def _evidence_refusal_message_from_golden() -> str:
    """The refusal string US1's golden capture of the defective trio recorded.

    The refusal line is on stderr (trap 19), printed as
    `ergane spec validate — refusal: [evidence] <message>`, and the message is
    the string `_evidence_refusal` composes — the function this story moves.
    The `--json` document carries it too, under `findings[].message`; both
    artifacts are read and asserted equal to each other before either is used,
    so the comparison is anchored on the artifacts and not on this test's hand.
    """
    stderr = (
        REPO_ROOT / "tests" / "golden" / "spec_validate" / "defective" / "stderr.txt"
    ).read_text(encoding="utf-8")
    prefix = "ergane spec validate — refusal: [evidence] "
    line = next(line for line in stderr.splitlines() if line.startswith(prefix))
    return line[len(prefix) :]


def _evidence_refusal_message_from_json() -> str:
    """The same string from the `--json` artifact's `findings[].message`."""
    document = json.loads(
        (REPO_ROOT / "tests" / "golden" / "spec_validate" / "defective" / "json.txt").read_text(
            encoding="utf-8"
        )
    )
    return next(
        finding["message"]
        for finding in document["findings"]
        if finding["layer"] == "evidence"
    )


def test_the_refusal_appended_is_byte_for_byte_the_golden_stderr_string() -> None:
    """T028, US6-S4. The moved `_evidence_refusal` composes the same bytes.

    A spec whose only defect is an unevidenceable Then-clause — the defective
    fixture trio, whose scenario asserts "renders correctly in the browser"
    with no diff-carried evidence — is driven through the surviving
    `_check_evidence` with caller-owned lists. It appends one refusal to
    `findings`; it does not raise (trap 7). The message is compared byte for
    byte against US1's golden capture of that trio's **stderr** (trap 19), and
    independently against the `--json` artifact's `findings[].message`, so a
    reworded refusal fails this test whatever stream it is read from.

    The scenario is exercised twice on purpose. Once through the CLI module's
    binding — the seam `_validate_command` calls — and once by calling the
    moved `_evidence_refusal` directly with the arguments the golden string
    fixes: the clause, the markers it carries, the declared gate and the
    manifest path. The direct call is what catches a rewording even if the
    layer's own plumbing were re-ordered.
    """
    import factory.spec.evidence as spec_noun
    import factory.spec.evidence as evidence

    # The checker appends; nothing raises (trap 7).
    spec_text = (DEFECTIVE_TRIO / "spec.md").read_text(encoding="utf-8")
    findings: list[Any] = []
    skipped: list[dict[str, str]] = []
    checked: list[str] = []
    report = spec_noun._check_evidence(spec_text, str(FIXTURE_REPO), findings, skipped, checked)

    assert len(findings) == 1, "the defective trio carries exactly one evidence refusal"
    finding = findings[0]
    assert finding.layer == "evidence"
    assert finding.severity == "refusal"

    golden_stderr_message = _evidence_refusal_message_from_golden()
    golden_json_message = _evidence_refusal_message_from_json()
    assert golden_stderr_message == golden_json_message, (
        "the two golden artifacts record the same refusal string"
    )
    assert finding.message == golden_stderr_message, (
        "the appended refusal is not byte for byte the string US1's stderr "
        "golden recorded — the moved _evidence_refusal reworded it (trap 9)"
    )
    assert report.refused == 1

    # The direct call: the golden string fixes every argument, so the composed
    # bytes are checked without trusting the layer's plumbing.
    clause = "the page renders correctly in the browser."
    markers = ["in the browser", "renders correctly"]
    declared = evidence._declared_gates(str(FIXTURE_REPO))
    direct = evidence._evidence_refusal(
        "US1-S1", clause, markers, declared.gates, declared.manifest
    )
    assert direct == golden_stderr_message, (
        "the moved _evidence_refusal does not compose the golden bytes from "
        "the arguments the golden string fixes"
    )

    # And the parameters survive the move unchanged (trap 7).
    parameters = list(inspect.signature(evidence._evidence_refusal).parameters)
    assert parameters == ["scenario_id", "clause", "markers", "gates", "manifest"]