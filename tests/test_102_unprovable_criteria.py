"""102 US1: `ergane spec validate` refuses a Then-clause nothing can evidence.

The incident this story exists for: one story deadlocked for a combined fifteen
attempts on a single scenario whose Then-clause asserted a runtime outcome. The
judge sees a diff and the declared gates' results and nothing else, so the
scenario could not have passed on any attempt, and the information that it could
not was available the moment it was written.

Two properties are asserted throughout, and the second is the one that decides
whether this story is worth having:

- **The refusal quotes the clause and teaches.** An author told "unprovable" has
  to guess which of five scenarios and what to do about it (FR-001, FR-005).

- **A clause a declared gate can evidence is admitted.** Spec 116 puts the gate
  results in the judge's prompt, which makes a clause naming a *gate* outcome
  scoreable. A check that refused those would refuse exactly the scenarios 116
  makes answerable, and the two specs would cancel out (plan trap 1). The pair
  `test_a_clause_naming_a_declared_gate_is_admitted` /
  `test_the_same_clause_is_refused_when_that_gate_is_not_declared` is that whole
  argument: same spec, two repositories, and the *declaration* is what moves the
  verdict.

Red first. `uv run pytest tests/test_102_unprovable_criteria.py -q --no-header`,
run against this tree with these tests committed and `factory/cli/nouns/spec.py`
restored to its pre-story state, verbatim::

    FAILED tests/test_102_unprovable_criteria.py::test_a_clause_naming_a_declared_gate_is_admitted
    FAILED tests/test_102_unprovable_criteria.py::test_the_same_clause_is_refused_when_that_gate_is_not_declared
    FAILED tests/test_102_unprovable_criteria.py::test_a_runtime_clause_no_gate_measures_is_refused_quoting_it
    FAILED tests/test_102_unprovable_criteria.py::test_a_repository_declaring_no_gates_says_so_specifically
    FAILED tests/test_102_unprovable_criteria.py::test_the_refusal_suggests_how_to_make_the_criterion_provable[gates-declared]
    FAILED tests/test_102_unprovable_criteria.py::test_the_refusal_suggests_how_to_make_the_criterion_provable[no-gates-declared]
    FAILED tests/test_102_unprovable_criteria.py::test_an_unreadable_manifest_is_not_checked_never_refused
    FAILED tests/test_102_unprovable_criteria.py::test_the_real_corpus_verdict_is_unchanged
    8 failed, 1 passed in 1.10s

The one that passed red is the control, and it had to:
`test_a_clause_proven_by_a_committed_test_is_admitted` asserts a clause is *not*
refused, which is true of a tree with no layer in it. A control that failed red
would mean something else was already refusing it.

Green after, same command::

    9 passed, 1 warning in 28.33s

And the whole suite, `uv run pytest -q --no-header -p no:randomly`::

    5322 passed, 58 skipped, 8 warnings in 416.42s (0:06:56)

Run the thing, not the tests about it. The plan's demonstration is the pair: the
same outcome refused when nothing declared can measure it, and admitted when a
declared gate can. Against a scratch trio and this repository as the target repo
(it declares one gate, `test`), verbatim::

    $ uv run ergane spec validate /tmp/102-demo/specs/001-fonts --target-repo . \
        --specs-root /tmp/102-demo/specs
    ergane spec validate — refusal: [evidence] US1-S1: "the font renders correctly in the browser." asserts an outcome only a running system shows ("in the browser", "renders correctly"); the judge is shown the diff and the results of the gates this repository declares (test), and the clause names neither — no declared gate, and nothing the diff itself carries. To make it provable: name a declared gate (test) whose result will reach the judge with the diff, or restate the clause as something the diff carries — e.g. "… — proven by a committed test"
    exit=1

...and with the clause rephrased to "the test gate reports that the font renders
correctly in the browser", same command::

    /tmp/102-demo/specs/001-fonts/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
    exit=0

The other two shapes, on the original clause. A repository whose manifest
declares nothing to measure with::

    $ uv run ergane spec validate /tmp/102-demo/specs/001-fonts --target-repo /tmp/102-demo/bare ...
    ergane spec validate — refusal: [evidence] US1-S1: "the font renders correctly in the browser." asserts an outcome only a running system shows ("in the browser", "renders correctly"); /tmp/102-demo/bare/ergane.yaml declares no gates, so no gate result will reach the judge with the diff, and the clause names nothing the diff itself carries. To make it provable: declare in /tmp/102-demo/bare/ergane.yaml a gate that measures this and name that gate in the clause, or restate the clause as something the diff carries — e.g. "… — proven by a committed test"
    exit=1

...and a target repo with no manifest at all, which refuses nothing::

    $ uv run ergane spec validate /tmp/102-demo/specs/001-fonts --target-repo /tmp/102-demo/nothing ...
    ergane spec validate — layer 'evidence' not checked: cannot read the gates /tmp/102-demo/nothing declares: /tmp/102-demo/nothing/ergane.yaml: [missing_manifest] cannot be read (No such file or directory); every target repo must commit a ergane.yaml declaring its gates
    /tmp/102-demo/specs/001-fonts/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
    exit=0
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Deprecation warnings leak into stderr from the legacy manifest name; suppress
#: them once so tests see only validate's own transcript.
warnings.filterwarnings("ignore", category=DeprecationWarning)


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


# --- fixtures: a sound trio whose only variable is one Then-clause -------------


def _spec_text(then_clause: str) -> str:
    """A Spec Kit trio body that passes every layer validate already runs.

    Only the Then-clause varies. Nothing else in the scenario may mention a test,
    an artifact, a gate or the diff: the layer reads the whole scenario looking
    for something that can evidence the clause, so a stray "proven by" in the
    Given would admit every case here and the tests would all pass vacuously.
    """
    return (
        "---\nstate: draft\n---\n"
        "\n"
        "## Requirements *(mandatory)*\n"
        "\n"
        "- **FR-001**: The system MUST draw the page.\n"
        "\n"
        "### User Story 1 - The page is drawn (Priority: P1)\n"
        "\n"
        "As an operator, I want the page drawn.\n"
        "\n"
        "**Acceptance Scenarios**:\n"
        "\n"
        f"1. **Given** a built page, **When** the operator opens it, **Then** {then_clause}\n"
        "\n"
        "## Work Graph\n"
        "\n"
        "```yaml\n"
        "US1:\n"
        "  depends_on: []\n"
        "  implements: [FR-001]\n"
        "```\n"
    )


_TASKS = (
    "# Tasks\n\n"
    "## Phase 1: User Story 1 - The page is drawn\n\n"
    "- [ ] T001 [US1-S1] draw the page\n"
)


def _spec_dir(specs_root: Path, name: str, then_clause: str) -> Path:
    directory = specs_root / name
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text(_spec_text(then_clause), encoding="utf-8")
    (directory / "plan.md").write_text("# Plan\n\nOne page, one reader.\n", encoding="utf-8")
    (directory / "tasks.md").write_text(_TASKS, encoding="utf-8")
    return directory


def _repo(root: Path, name: str, manifest: str | None) -> Path:
    """A target repository whose manifest is exactly `manifest`, or absent."""
    repo = root / name
    repo.mkdir(parents=True)
    if manifest is not None:
        (repo / "ergane.yaml").write_text(manifest, encoding="utf-8")
    return repo


#: One gate, named `smoke` — a schema v2 manifest, where gate names are free.
_SMOKE_MANIFEST = 'version: 2\nruntime: bwrap\ngates:\n  smoke: "bash gates/smoke.sh"\n'

#: One gate, named `test`, and nothing that measures a page.
_TEST_MANIFEST = 'version: 1\nruntime: bwrap\ngates:\n  test: "pytest -q"\n'

#: A manifest a repository committed without declaring anything to measure with.
_NO_GATES_MANIFEST = "version: 1\nruntime: bwrap\n"

#: The clause the deadlock was made of: a runtime outcome, named as one.
_RUNTIME_CLAUSE = "the font renders correctly in the browser."

#: The same outcome, asserted through a gate that can report it.
_GATED_CLAUSE = "the smoke gate reports that the font renders correctly in the browser."


def _validate(run: Callable[..., Run], spec_dir: Path, repo: Path) -> Run:
    return run(
        "spec",
        "validate",
        "--json",
        "--target-repo",
        str(repo),
        "--specs-root",
        str(spec_dir.parent),
        str(spec_dir),
    )


def _evidence_findings(document: Any) -> list[dict[str, str]]:
    return [f for f in document["findings"] if f["layer"] == "evidence"]


# --- T002 / US1-S2: the scenario that keeps 102 and 116 from cancelling out -----


def test_a_clause_naming_a_declared_gate_is_admitted(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A runtime outcome a declared gate measures is not refused (FR-002).

    Written first, and it constrains everything else here: the rule is not "the
    clause mentions running something", it is "nothing this repository declares
    can produce evidence for this clause".
    """
    spec_dir = _spec_dir(tmp_path / "specs", "001-gated", _GATED_CLAUSE)
    repo = _repo(tmp_path, "declares-smoke", _SMOKE_MANIFEST)

    result = _validate(run, spec_dir, repo)

    assert result.code == 0, result.stderr
    assert _evidence_findings(result.json) == []
    assert "evidence" in result.json["checked"]


def test_the_same_clause_is_refused_when_that_gate_is_not_declared(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """The declaration is what moves the verdict, not the word "gate" (FR-001).

    Same spec, same clause, a repository that declares `test` instead of
    `smoke`. If this passed, the check above would be admitting every clause
    that says "gate" and proving nothing.
    """
    spec_dir = _spec_dir(tmp_path / "specs", "001-gated", _GATED_CLAUSE)
    repo = _repo(tmp_path, "declares-test", _TEST_MANIFEST)

    result = _validate(run, spec_dir, repo)

    assert result.code == 1
    findings = _evidence_findings(result.json)
    assert len(findings) == 1
    message = findings[0]["message"]
    assert _GATED_CLAUSE in message
    # It names the gates this repository does declare, so the author can see
    # that `smoke` is not among them.
    assert "test" in message


# --- T001 / US1-S1: the refusal, quoting the clause ----------------------------


def test_a_runtime_clause_no_gate_measures_is_refused_quoting_it(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """FR-001: the clause is quoted, the scenario named, the reason given."""
    spec_dir = _spec_dir(tmp_path / "specs", "001-runtime", _RUNTIME_CLAUSE)
    repo = _repo(tmp_path, "declares-test", _TEST_MANIFEST)

    result = _validate(run, spec_dir, repo)

    assert result.code == 1
    findings = _evidence_findings(result.json)
    assert len(findings) == 1
    message = findings[0]["message"]
    assert "US1-S1" in message
    assert _RUNTIME_CLAUSE in message
    # The reason names the phrase that made it a runtime outcome and the gates
    # that could have measured it — not a bare "unprovable".
    assert "in the browser" in message
    assert "test" in message
    assert findings[0]["severity"] == "refusal"

    human = run(
        "spec",
        "validate",
        "--target-repo",
        str(repo),
        "--specs-root",
        str(spec_dir.parent),
        str(spec_dir),
    )
    assert human.code == 1
    assert "refusal: [evidence]" in human.stderr
    assert _RUNTIME_CLAUSE in human.stderr


def test_a_clause_proven_by_a_committed_test_is_admitted(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """FR-002 / trap 2: evidence the diff itself carries admits the clause.

    A false refusal is worse than a missed one — an author refused for a
    legitimate clause phrases around the checker rather than improving the spec.
    A clause that names its own committed evidence is provable whatever it
    asserts, and this is the shape almost every clause in this repository's
    corpus already uses.
    """
    spec_dir = _spec_dir(
        tmp_path / "specs",
        "001-proven",
        "the font renders correctly in the browser — proven by a committed test.",
    )
    repo = _repo(tmp_path, "declares-test", _TEST_MANIFEST)

    result = _validate(run, spec_dir, repo)

    assert result.code == 0, result.stderr
    assert _evidence_findings(result.json) == []


# --- T004 / US1-S4: a repository with nothing to measure with ------------------


def test_a_repository_declaring_no_gates_says_so_specifically(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """FR-004: no gate declared is a different conversation from no gate covering.

    The remedy differs — declare a gate versus name one — so the refusal must
    not collapse the two into one sentence.
    """
    spec_dir = _spec_dir(tmp_path / "specs", "001-runtime", _RUNTIME_CLAUSE)
    repo = _repo(tmp_path, "declares-nothing", _NO_GATES_MANIFEST)

    result = _validate(run, spec_dir, repo)

    assert result.code == 1
    findings = _evidence_findings(result.json)
    assert len(findings) == 1
    message = findings[0]["message"]
    assert "declares no gates" in message
    assert str(repo / "ergane.yaml") in message
    # And it is not the other refusal wearing the same words.
    covered = _validate(
        run, _spec_dir(tmp_path / "other-specs", "001-runtime", _RUNTIME_CLAUSE),
        _repo(tmp_path, "declares-test", _TEST_MANIFEST),
    )
    assert "declares no gates" not in _evidence_findings(covered.json)[0]["message"]


# --- T005 / US1-S5: a refusal that only forbids teaches nothing ----------------


@pytest.mark.parametrize(
    "manifest, expected",
    [
        pytest.param(_TEST_MANIFEST, "test", id="gates-declared"),
        pytest.param(_NO_GATES_MANIFEST, "ergane.yaml", id="no-gates-declared"),
    ],
)
def test_the_refusal_suggests_how_to_make_the_criterion_provable(
    run: Callable[..., Run], tmp_path: Path, manifest: str, expected: str
) -> None:
    """FR-005: both refusal shapes carry a suggestion, and it is actionable."""
    spec_dir = _spec_dir(tmp_path / "specs", "001-runtime", _RUNTIME_CLAUSE)
    repo = _repo(tmp_path, "target", manifest)

    result = _validate(run, spec_dir, repo)

    assert result.code == 1
    message = _evidence_findings(result.json)[0]["message"]
    suggestion = message.split("To make it provable:")[-1]
    assert suggestion != message, "the refusal carries no suggestion"
    assert expected in suggestion
    # The other half of the menu: say it as something the diff carries.
    assert "proven by a committed test" in suggestion


# --- T006 / FR-001, trap 4: no manifest is `not checked`, never a refusal -------


def test_an_unreadable_manifest_is_not_checked_never_refused(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A layer that could not run says so, naming the reason (trap 4).

    `spec validate` runs against a `--target-repo` that may not exist on this
    host at all — its default names a path an operator's laptop does not carry.
    A repository whose gates cannot be read has not proven any clause wrong.
    """
    spec_dir = _spec_dir(tmp_path / "specs", "001-runtime", _RUNTIME_CLAUSE)
    repo = _repo(tmp_path, "no-manifest", None)

    result = _validate(run, spec_dir, repo)

    assert result.code == 0, result.stderr
    document = result.json
    assert _evidence_findings(document) == []
    assert "evidence" not in document["checked"]
    skipped = [entry for entry in document["skipped"] if entry["layer"] == "evidence"]
    assert len(skipped) == 1
    assert str(repo / "ergane.yaml") in skipped[0]["reason"]

    human = run(
        "spec",
        "validate",
        "--target-repo",
        str(repo),
        "--specs-root",
        str(spec_dir.parent),
        str(spec_dir),
    )
    assert human.code == 0
    assert "layer 'evidence' not checked" in human.stderr
    assert "refusal" not in human.stderr


# --- T003 / US1-S3: the corpus control -----------------------------------------


def _validate_without_evidence_layer(
    run: Callable[..., Run], spec_dir: Path, specs_root: Path
) -> tuple[int, Any]:
    """Run validate with the `_check_evidence` layer monkeypatched to a no-op.

    Patched on `factory.spec.composition` — the module the verb's composition
    reads — and not on `factory.cli.nouns.spec`, where the name was only ever
    an import binding. Since US9 the verb is a renderer over `validate_spec`,
    so a rebinding on the CLI module lands on a name nothing calls and both
    runs become the same run (133-US9's T052 is the assertion that proves the
    re-point took); patching the composition's own global is what still
    disables the layer.
    """
    import factory.spec.composition as _composition_module

    original = _composition_module._check_evidence
    _composition_module._check_evidence = lambda *args, **kwargs: None
    try:
        result = run(
            "spec",
            "validate",
            "--json",
            "--target-repo",
            str(_REPO_ROOT),
            "--specs-root",
            str(specs_root),
            str(spec_dir),
        )
        return result.code, result.json
    finally:
        _composition_module._check_evidence = original


def test_the_real_corpus_verdict_is_unchanged(run: Callable[..., Run]) -> None:
    """US1-S3 / trap 5: every spec in this repository validates as it did before.

    The regression surface of a heuristic is the corpus it was not written for.
    Each spec is validated twice — once with the layer and once with it disabled
    — and the verdict (exit code and the full findings list) must be identical.
    Costs roughly half a minute, once, and it is the only thing standing between
    this layer and a hundred and fifteen specs it was never tried against.

    It passes before the layer exists, in the sense that matters: with the layer
    disabled both runs are the same run.
    """
    specs_root = _REPO_ROOT / "specs"
    compared = 0
    for spec_dir in sorted(specs_root.iterdir()):
        if not (spec_dir / "spec.md").is_file():
            continue

        with_layer = run(
            "spec",
            "validate",
            "--json",
            "--target-repo",
            str(_REPO_ROOT),
            "--specs-root",
            str(specs_root),
            str(spec_dir),
        )
        without_code, without_doc = _validate_without_evidence_layer(
            run, spec_dir, specs_root
        )

        assert with_layer.code == without_code, (
            f"{spec_dir.name}: exit code changed by the evidence layer"
        )
        assert with_layer.json["findings"] == without_doc["findings"], (
            f"{spec_dir.name}: findings changed by the evidence layer"
        )
        compared += 1

    assert compared > 100, f"only {compared} specs were compared; the corpus is larger"
