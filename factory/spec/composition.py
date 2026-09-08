"""The one composition: `validate_spec`, the library face of `spec validate`.

US3 of 133. Every relocation story before this one put the twelve layers where
they belong; this story adds the one call that composes them all and returns
the typed report, so a consumer that may not shell the CLI stops re-composing
five exported pieces and silently under-reporting the other seven layers
(133's reason to exist, PR-8's drift). The CLI verb is deliberately untouched:
`_validate_command` still runs its own copy of this composition, and US9 makes
it a renderer over this module — which is why every finding construction here
is carried verbatim, wrapper and all, including the four that no `def _check_`
function holds (plan trap 2).

The shape is the verb's body with two things removed: the `args` parameter and
the rendering. Everything else travels unchanged — the seeded `checked` list
(trap 3: its order is not the run order and must not be tidied into it), the
four-channel split with the `informational` routing, both spellings of the two
layer names (`workgraph` on the derivation finding but `workgraph_derivation`
in `checked`; `sentinel` on the note but `sentinels` in `checked` — both are
rendered, so folding either pair is an output change FR-005 forbids). The exit
code is not carried either: the report's `verdict` is the answer, and mapping
`fail` to `EXIT_USER` is the CLI renderer's job, not a second copy of the rule.

Nothing here imports from `factory.cli` at all (plan trap 17, widened): the CLI
module imports from `factory.spec` at module scope, so an import back re-enters
a half-initialised module before its names exist. A body that needs a CLI-module
name means that name moves here instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.workgraph.cli import SPEC_NAME
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph
from factory.workgraph.preflight import check_prompt_assembly, check_slice_coverage

from factory.spec.report import SpecFinding as _ValidateFinding
from factory.spec.report import SpecValidation
from factory.spec.anchors import _check_anchor_resolution, _check_symbol_anchors
from factory.spec.evidence import _check_evidence
from factory.spec.layers import (
    _candidate_graph,
    _check_fixes,
    _check_frontmatter,
    _check_personas,
    _check_scenario_coverage,
    _check_workgraph,
    _scan_sentinels_in_trio,
    _tasks_text,
)


class SpecReadError(Exception):
    """The spec directory holds no readable `spec.md`.

    The verb raises `OperatorError` with this exact message and the CLI
    boundary renders it at exit 1; the library carries the same message on its
    own type so `factory.spec` imports nothing from `factory.cli` (plan trap
    17) and the renderer — US9's — translates at the seam it owns.
    """


def validate_spec(
    spec_dir: Path, *, target_repo: str, specs_root: str
) -> SpecValidation:
    """Run every validation layer over one spec directory, and return the report.

    The library face of `ergane spec validate`: same twelve layers, same run
    order, same severities, same `checked` sequence the verb emits — none of
    which is the order the layers run in (plan trap 3). Takes a `Path` and two
    keyword-only values; constructs no `argparse.Namespace` and prints nothing
    (FR-003). The exit code is the CLI renderer's question: `verdict == "fail"`
    is what it maps to `EXIT_USER`.
    """
    spec_dir = Path(spec_dir)
    spec_path = spec_dir / SPEC_NAME
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SpecReadError(f"cannot read {spec_path}: {error}") from error

    epic_id = spec_dir.resolve().name
    findings: list[_ValidateFinding] = []
    # Stated, never counted: 044 FR-006's orphan task ids are a fact the author
    # confirms or acts on, not a refusal, so they ride a separate list and the
    # verdict below reads `findings` alone.
    information: list[_ValidateFinding] = []
    checked = [
        "frontmatter",
        "workgraph_derivation",
        "persona_registry",
        "scenario_coverage",
    ]
    skipped: list[dict[str, str]] = []

    # 1. Frontmatter grammar against the spec's own corpus.
    _check_frontmatter(spec_dir, epic_id, findings)

    # 2. `fixes:` declarations, if any, against the findings ledger.
    _check_fixes(spec_dir, findings, information, skipped, checked)

    # 3. Work-graph derivation.
    #
    # Derived against `tasks.md` when there is one (069-US2): an overlap whose
    # only ordering would close a cycle is a refusal an author must meet here
    # rather than at `spec derive`.
    tasks_text = _tasks_text(spec_dir)
    graph: WorkGraph | None = None
    try:
        graph = derive_workgraph(
            spec_text,
            epic_id=epic_id,
            feature=epic_id,
            specs_root=specs_root,
            target_repo=target_repo,
            tasks_text=tasks_text,
        )
    except DerivationError as error:
        findings.append(_ValidateFinding("workgraph", str(error)))

    # 4. Structural work-graph validation and persona-registry check.
    if graph is not None:
        _check_workgraph(graph, findings)
        _check_personas(graph, findings)
    else:
        # Derivation failed, but the spec still declares stories and the
        # registry check is meaningful: a missing persona is a dispatch-time
        # failure no matter why the graph did not compile (FR-007).
        _check_personas(_candidate_graph(spec_text, epic_id), findings)

    # 5. Scenario coverage across spec.md and tasks.md.
    _check_scenario_coverage(spec_dir, spec_text, findings)

    # 6. Every node's attempt prompt, assembled offline (044 FR-001).
    #
    # The layer that would have caught the 2026-08-15 kill: a `tasks.md` whose
    # phase headings name no story leaves every node without a task slice, and
    # until now the first thing to notice was the dispatch tick that killed the
    # epic. It runs last because it is the only layer that needs both a compiled
    # graph and the other two authored documents.
    if graph is not None:
        for assembly in check_prompt_assembly(graph, spec_dir, spec_text=spec_text):
            findings.append(_ValidateFinding("prompt_assembly", str(assembly)))
        checked.append("prompt_assembly")
    else:
        # Honesty over coverage: assembly is per node, derivation failed, and
        # there are no nodes. Reporting it as checked would grow the `checked`
        # list by a layer nobody ran — the way a preflight comes to be trusted
        # for something it never did.
        skipped.append(
            {
                "layer": "prompt_assembly",
                "reason": (
                    "the work graph did not compile, so there are no nodes to "
                    "assemble a prompt for"
                ),
            }
        )

    # 6. Which authored tasks the assembled slices drop (044 FR-005/006).
    #
    # The layer that catches what a refusal cannot: every node assembling a
    # slice is not every node being handed its work. A task written for one
    # story and left outside that story's slice is a defect; a task in no
    # slice naming no story is stated and costs nothing.
    coverage = (
        None
        if graph is None
        else check_slice_coverage(graph, spec_dir, tasks_text=tasks_text)
    )
    if coverage is not None:
        for entry in coverage:
            target = information if entry.informational else findings
            target.append(_ValidateFinding("slice_coverage", str(entry)))
        checked.append("slice_coverage")
    else:
        skipped.append(
            {
                "layer": "slice_coverage",
                "reason": (
                    "the work graph did not compile, so there are no nodes to "
                    "assemble a prompt for"
                    if graph is None
                    else "tasks.md could not be read, so it holds no slice to "
                    "measure a task against"
                ),
            }
        )

    # 7. Stories the spec declares disjoint whose task slices are not (069-US2
    #    FR-009).
    #
    # The check 060 needed: it asserted its stories were file-disjoint, its
    # diffs contradicted that, and only landing order saved it. An advisory, not
    # a refusal — derivation has already ordered the pair — because what the
    # author is owed is that their declared independence and their own task
    # prose disagree.
    if graph is not None and tasks_text is not None:
        for edge in graph.inferred_edges:
            findings.append(
                _ValidateFinding("slice_contention", edge.reason, severity="advisory")
            )
        checked.append("slice_contention")
    else:
        skipped.append(
            {
                "layer": "slice_contention",
                "reason": (
                    "the work graph did not compile, so there are no stories to "
                    "compare slices for"
                    if graph is None
                    else "tasks.md could not be read, so no story has a slice"
                ),
            }
        )

    # 8. Sentinels that mark mandatory blanks (106-US3).
    #
    # These are stated, never counted: they ride the `information` channel and do
    # not change the exit code.  The layer runs unconditionally because it only
    # reads text, so it is always reported in `checked`.
    for document, line_no, line_text in _scan_sentinels_in_trio(spec_dir):
        information.append(
            _ValidateFinding(
                "sentinel",
                f"{document}:{line_no}: {line_text.strip()} — not ready to derive",
            )
        )
    checked.append("sentinels")

    # 9. Anchor resolution: every `path:NN` citation in the authored documents
    #    opens the file it names in the target repository and reports stale
    #    anchors before dispatch (072-US1).
    #
    # It runs before the symbol check below because it answers the coarser
    # question — does the file exist, and is that line real — and the symbol
    # check leans on that: a citation whose file cannot be read is left here
    # deliberately, so the operator is told once rather than twice.
    _check_anchor_resolution(
        spec_dir, spec_text, target_repo, findings, skipped, checked
    )

    # 10. Whether cited Python symbols land inside their declared spans (072-US2).
    _check_symbol_anchors(spec_dir, spec_text, target_repo, findings, skipped, checked)

    # 11. Whether each Then-clause can be evidenced at all (102-US1), and what
    #     the judge will be shown for this spec (102-US2).
    #
    # The layer that would have saved fifteen attempts: the judge is shown the
    # story's diff and the declared gates' results, so a clause asserting an
    # outcome neither can produce is one no correct implementation can pass.
    # It runs last because it is the only layer that reads the target
    # repository's manifest, and it refuses nothing when it cannot.
    #
    # It returns the report as well as raising the refusals, because the report
    # is the answer the refusal assumes the author already has — and assembling
    # it here rather than in a second pass is what keeps the two from ever
    # disagreeing about the same spec.
    evidence = _check_evidence(spec_text, target_repo, findings, skipped, checked)

    # The typed report, assembled from the caller-owned lists — the one place
    # the four channels and the run-order list are filled together, so they
    # cannot disagree (FR-003). `findings` is the run-order list the verb
    # renders from; the split members are the four-channel view of the same
    # findings, and neither moves the verdict on its own account (FR-002).
    report = SpecValidation(
        refusals=[f for f in findings if f.severity == "refusal"],
        advisories=[f for f in findings if f.severity == "advisory"],
        information=list(information),
        skipped=list(skipped),
        checked=list(checked),
        findings=list(findings),
        judge_evidence=evidence,
    )

    return report


def serialise_report(report: SpecValidation, spec_dir: str) -> dict[str, Any]:
    """The `--json` document, built from the typed report in the verb's key order.

    US9 took this dict out of `_validate_command`'s body: the key order —
    `spec_dir`, `checked`, `skipped`, `findings`, `information`, with
    `judge_evidence` appended only when there is a report — and the deliberate
    absence of that key when the evidence layer produced nothing are load-bearing
    (plan trap 21), so the serialiser walks the report field by field rather than
    delegating to a `dataclasses.asdict()`, which would emit every field in
    declaration order and `judge_evidence: null`.

    `spec_dir` is an argument: the report does not carry it — the verb knows the
    path it was given, and the library form's report describes the run, not the
    directory it ran over — so the one key the report cannot answer is this
    serialiser's second parameter.
    """

    document: dict[str, Any] = {
        "spec_dir": spec_dir,
        "checked": list(report.checked),
        "skipped": [dict(entry) for entry in report.skipped],
        "findings": [
            {"layer": finding.layer, "message": finding.message, "severity": finding.severity}
            for finding in report.findings
        ],
        "information": [
            {"layer": note.layer, "message": note.message} for note in report.information
        ],
    }
    # Absent rather than empty when there is no report to make: a test that
    # disables the evidence layer gets a document with no `judge_evidence` key,
    # which is the honest shape — no layer ran, so nothing was answered.
    if report.judge_evidence is not None:
        document["judge_evidence"] = report.judge_evidence.as_dict()
    return document