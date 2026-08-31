"""102 US2: `ergane spec validate` says what the judge will be shown.

US1 refuses the worst case. This story makes the rule learnable instead of a wall
an author meets repeatedly: every run of validate reports the three things a node
is scored on — the diff, its story's criteria, and the gates whose results
accompany them — and a clause that is merely *hard* to prove is named rather than
refused.

Two properties are asserted throughout:

- **The report is accountable, not decorative.** `test_validate_reports_what_the
  _judge_will_be_shown` takes the scenario ids the report lists and asserts they
  are the ones `factory.verify.judge.build_prompt` actually carries, and takes
  the gate names it lists and asserts they are the ones the target repository's
  manifest actually declares. A report assembled from a second, hand-rolled
  derivation would drift from the prompt it describes and nothing would notice.

- **A warning is not a quiet refusal.** The borderline case is asserted twice
  over: the exit code stays 0 and the `findings` list stays empty (it is not
  refused), and the *same clause* stripped of its committed evidence is refused
  (the warning is not a refusal that was merely downgraded).

Red first. `uv run pytest tests/test_102_judge_evidence_report.py -q --no-header`,
run against this tree with these tests committed and `factory/cli/nouns/spec.py`
restored to its pre-story state (US1's layer present, US2's report absent),
verbatim::

    FAILED tests/test_102_judge_evidence_report.py::test_validate_reports_what_the_judge_will_be_shown
    FAILED tests/test_102_judge_evidence_report.py::test_a_fully_provable_spec_is_reported_provable_with_no_refusal
    FAILED tests/test_102_judge_evidence_report.py::test_a_borderline_clause_is_named_as_a_warning_not_refused
    FAILED tests/test_102_judge_evidence_report.py::test_the_report_is_produced_even_when_the_gates_cannot_be_read
    4 failed in 0.46s

Each of the four fails on `KeyError: 'judge_evidence'` and none on a verdict:
the fixtures validate cleanly against this tree today, so what is missing is the
report and nothing else.

Green after, same command::

    PLACEHOLDER-GREEN
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Callable, NamedTuple, Sequence

import pytest

from factory.cli.main import main
from factory.verify.criteria import parse_spec
from factory.verify.diffbounds import DIFF_INPUT_LIMIT
from factory.verify.factory_yaml import load_factory_config, resolve_manifest_path
from factory.verify.judge import build_prompt
from factory.verify.models import CriteriaSet, RequirementKind

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


# --- fixtures: a sound trio whose only variable is its Then-clauses ------------


#: One gate, named `smoke` — a schema v2 manifest, where gate names are free.
_SMOKE_MANIFEST = 'version: 2\nruntime: bwrap\ngates:\n  smoke: "bash gates/smoke.sh"\n'

#: A clause the diff carries whole: the shape almost every clause in this
#: repository's corpus already uses.
_PROVABLE = "the page is drawn — proven by a committed test."

#: A runtime outcome resting on the evidence its own scenario promises. Neither
#: refusable (the diff will carry the test) nor plainly provable (what the test
#: asserts about a browser is the author's problem) — the borderline case FR-007
#: exists for.
_BORDERLINE = "the font renders correctly in the browser — proven by a committed test."


def _spec_text(stories: Sequence[tuple[str, Sequence[str]]]) -> str:
    """A Spec Kit trio body that passes every layer validate already runs.

    Only the Then-clauses vary. Nothing outside a Then-step may mention a test,
    an artifact, a gate or the diff: the evidence layer reads the whole scenario
    looking for something that can evidence the clause, so a stray "proven by"
    in a Given would admit every case here and the tests would pass vacuously.
    """
    blocks = ["---", "state: draft", "---", "", "## Requirements *(mandatory)*", ""]
    for index in range(len(stories)):
        blocks.append(f"- **FR-{index + 1:03d}**: The system MUST draw part {index + 1}.")
    for index, (title, clauses) in enumerate(stories, start=1):
        blocks += [
            "",
            f"### User Story {index} - {title} (Priority: P{index})",
            "",
            f"As an operator, I want part {index}.",
            "",
            "**Acceptance Scenarios**:",
            "",
        ]
        for position, clause in enumerate(clauses, start=1):
            blocks.append(
                f"{position}. **Given** a built page, **When** the operator opens "
                f"it, **Then** {clause}"
            )
    blocks += ["", "## Work Graph", "", "```yaml"]
    for index in range(1, len(stories) + 1):
        blocks += [
            f"US{index}:",
            "  depends_on: []",
            f"  implements: [FR-{index:03d}]",
        ]
    blocks += ["```", ""]
    return "\n".join(blocks)


def _tasks_text(stories: Sequence[tuple[str, Sequence[str]]]) -> str:
    lines = ["# Tasks", ""]
    task = 0
    for index, (title, clauses) in enumerate(stories, start=1):
        lines += [f"## Phase {index}: User Story {index} - {title}", ""]
        for position in range(1, len(clauses) + 1):
            task += 1
            lines.append(f"- [ ] T{task:03d} [US{index}-S{position}] do the work")
        lines.append("")
    return "\n".join(lines)


def _spec_dir(
    specs_root: Path, name: str, stories: Sequence[tuple[str, Sequence[str]]]
) -> Path:
    directory = specs_root / name
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text(_spec_text(stories), encoding="utf-8")
    (directory / "plan.md").write_text("# Plan\n\nOne page, one reader.\n", encoding="utf-8")
    (directory / "tasks.md").write_text(_tasks_text(stories), encoding="utf-8")
    return directory


def _repo(root: Path, name: str, manifest: str | None) -> Path:
    """A target repository whose manifest is exactly `manifest`, or absent."""
    repo = root / name
    repo.mkdir(parents=True)
    if manifest is not None:
        (repo / "ergane.yaml").write_text(manifest, encoding="utf-8")
    return repo


def _validate(run: Callable[..., Run], spec_dir: Path, repo: Path, *flags: str) -> Run:
    return run(
        "spec",
        "validate",
        *flags,
        "--target-repo",
        str(repo),
        "--specs-root",
        str(spec_dir.parent),
        str(spec_dir),
    )


def _evidence_findings(document: Any) -> list[dict[str, str]]:
    return [f for f in document["findings"] if f["layer"] == "evidence"]


# --- T011 / US2-S1: the report names the diff, the criteria and the gates ------


def test_validate_reports_what_the_judge_will_be_shown(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """FR-006: the three things a node is scored on, named before an epic is spent.

    Every claim the report makes is checked against the thing it describes: the
    scenario ids against the prompt `build_prompt` assembles, the gate names
    against the manifest `load_factory_config` reads, the diff cap against
    `DIFF_INPUT_LIMIT`. A report that merely asserted its own strings would say
    nothing about what the judge sees.
    """
    stories = [
        ("The page is drawn", [_PROVABLE, "the second part is drawn — the diff shows it."]),
        ("The page is measured", ["the measurement is asserted by a committed test."]),
    ]
    spec_dir = _spec_dir(tmp_path / "specs", "001-report", stories)
    repo = _repo(tmp_path, "declares-smoke", _SMOKE_MANIFEST)

    result = _validate(run, spec_dir, repo, "--json")

    assert result.code == 0, result.stderr
    evidence = result.json["judge_evidence"]

    # The criteria, story by story — a node is judged on its own story's
    # scenarios, not on the spec's.
    assert [(entry["story"], entry["scenarios"]) for entry in evidence["criteria"]] == [
        ("US1", ["US1-S1", "US1-S2"]),
        ("US2", ["US2-S1"]),
    ]

    # The declared gates, from the manifest that owns them (constitution IX).
    manifest_path, _name = resolve_manifest_path(str(repo))
    assert evidence["gates"]["declared"] == sorted(load_factory_config(manifest_path).gates)
    assert evidence["gates"]["declared"] == ["smoke"]
    assert evidence["gates"]["manifest"] == str(manifest_path)

    # The diff, and the size above which the story never reaches the judge.
    assert evidence["diff"]["abridged_above_bytes"] == DIFF_INPUT_LIMIT
    assert evidence["diff"]["refused_above_bytes"] == (
        load_factory_config(manifest_path).diff_refusal_bytes
    )

    # And the report is true of the prompt the judge is actually sent: the ids it
    # lists for US1 are the ids `build_prompt` carries, and the diff is there.
    spec_text = (spec_dir / "spec.md").read_text(encoding="utf-8")
    us1 = [
        requirement
        for requirement in parse_spec(spec_text)
        if requirement.kind is RequirementKind.STORY and requirement.key == "US1"
    ]
    prompt = build_prompt(
        CriteriaSet(
            feature="001-report",
            spec_ref="US1",
            requirements=us1,
            source_path=str(spec_dir / "spec.md"),
            source_sha256="0" * 64,
            snapshotted_at="2026-08-30T00:00:00Z",
        ),
        "diff --git a/page.py b/page.py\n+drawn\n",
    )
    user_message = prompt.messages[1]["content"]
    for scenario_id in evidence["criteria"][0]["scenarios"]:
        assert scenario_id in user_message
    assert "diff --git a/page.py b/page.py" in user_message

    # The human transcript carries the same three answers.
    human = _validate(run, spec_dir, repo)
    assert human.code == 0
    assert "what the judge will be shown" in human.stdout
    assert "US1-S1" in human.stdout and "US2-S1" in human.stdout
    assert "smoke" in human.stdout
    assert str(DIFF_INPUT_LIMIT) in human.stdout


# --- T012 / US2-S2: all provable is stated, and nothing is refused -------------


def test_a_fully_provable_spec_is_reported_provable_with_no_refusal(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """US2-S2: the report says so, and adds nothing to the refusal channel.

    The half that matters is the second: a report is only useful to an author if
    reading it is not the same event as being refused.
    """
    stories = [("The page is drawn", [_PROVABLE, "the diff shows the second part."])]
    spec_dir = _spec_dir(tmp_path / "specs", "001-provable", stories)
    repo = _repo(tmp_path, "declares-smoke", _SMOKE_MANIFEST)

    result = _validate(run, spec_dir, repo, "--json")

    assert result.code == 0, result.stderr
    evidence = result.json["judge_evidence"]
    assert evidence["all_provable"] is True
    assert evidence["warnings"] == []
    assert _evidence_findings(result.json) == []

    human = _validate(run, spec_dir, repo)
    assert human.code == 0
    assert "what the judge will be shown" in human.stdout
    assert "every Then-clause names evidence" in human.stdout
    assert "refusal" not in human.stderr


# --- T013 / US2-S3, trap 2: a borderline clause is named, never refused --------


def test_a_borderline_clause_is_named_as_a_warning_not_refused(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """FR-007: a hard-to-prove clause earns a warning, and the exit code stays 0.

    Not every hard-to-prove clause is an unprovable one. An author refused for a
    legitimate clause learns to phrase around the checker rather than to improve
    the spec (plan trap 2), so the warning form is where low confidence goes.

    The contrast at the end is what stops this being a refusal in a softer voice:
    strip the committed evidence from the same clause and it is refused.
    """
    spec_dir = _spec_dir(
        tmp_path / "specs", "001-borderline", [("The page is drawn", [_BORDERLINE])]
    )
    repo = _repo(tmp_path, "declares-smoke", _SMOKE_MANIFEST)

    result = _validate(run, spec_dir, repo, "--json")

    assert result.code == 0, result.stderr
    assert _evidence_findings(result.json) == []

    evidence = result.json["judge_evidence"]
    assert evidence["all_provable"] is False
    assert len(evidence["warnings"]) == 1
    warning = evidence["warnings"][0]
    assert warning["scenario"] == "US1-S1"
    assert _BORDERLINE in warning["clause"]
    # It names the phrase that made the clause borderline, so the author can see
    # which words the checker read — not a bare "this one is risky".
    assert "in the browser" in warning["phrases"]
    assert "in the browser" in warning["message"]

    human = _validate(run, spec_dir, repo)
    assert human.code == 0
    assert _BORDERLINE in human.stdout
    assert "not a refusal" in human.stdout
    assert "refusal: [evidence]" not in human.stderr

    # The same clause with its evidence removed is refused: the warning marks a
    # clause that is merely hard to prove, not one that is unprovable.
    unprovable = _spec_dir(
        tmp_path / "other-specs",
        "001-unprovable",
        [("The page is drawn", ["the font renders correctly in the browser."])],
    )
    refused = _validate(run, unprovable, repo, "--json")
    assert refused.code == 1
    assert len(_evidence_findings(refused.json)) == 1
    assert refused.json["judge_evidence"]["all_provable"] is False


# --- US2-S1, trap 4: "any spec" includes one whose gates cannot be read --------


def test_the_report_is_produced_even_when_the_gates_cannot_be_read(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """The report answers what it can and names what it could not (trap 4).

    `spec validate` runs against a `--target-repo` that need not exist on this
    host, and the two answers that do not depend on a manifest — the diff and the
    criteria — are still owed to the author. The third says why it is missing,
    and still nothing is refused.
    """
    spec_dir = _spec_dir(
        tmp_path / "specs", "001-no-manifest", [("The page is drawn", [_PROVABLE])]
    )
    repo = _repo(tmp_path, "no-manifest", None)

    result = _validate(run, spec_dir, repo, "--json")

    assert result.code == 0, result.stderr
    evidence = result.json["judge_evidence"]
    assert [entry["scenarios"] for entry in evidence["criteria"]] == [["US1-S1"]]
    assert evidence["diff"]["abridged_above_bytes"] == DIFF_INPUT_LIMIT
    assert evidence["gates"]["declared"] is None
    assert str(repo / "ergane.yaml") in evidence["gates"]["reason"]
    assert _evidence_findings(result.json) == []

    human = _validate(run, spec_dir, repo)
    assert human.code == 0
    assert "what the judge will be shown" in human.stdout
    assert "US1-S1" in human.stdout
    assert "refusal" not in human.stderr
