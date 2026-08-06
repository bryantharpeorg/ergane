"""What the mechanical criteria parser must extract, and what it must refuse.

This is the ground truth everything downstream consumes: the judge scores a diff
against exactly these scenarios (FR-003), and a node is dispatched against exactly
these requirement keys. So the tests run against the fixture corpus in
`tests/fixtures/speckit/` — real files with real wrapping, fences and template
boilerplate — rather than against strings inlined here, which would only prove the
parser agrees with whatever the test author imagined Spec Kit looks like. The
corpus ends with a verbatim copy of `specs/001-usage-tracking/spec.md`, so the
grammar is pinned against a spec nobody wrote for the parser (SC-001, D-024).

Four properties carry the weight:

- **Identity is positional and stable.** `US<n>` comes from the story header's
  number, not from its position in the file, and `US<n>-S<k>` from the item's
  1-based position in that story's list. The judge must echo these ids back
  exactly, so a parser that renumbered stories after a deletion would silently
  re-point every stored verdict.
- **Fences are inert.** The factory hands agents the Spec Kit template itself,
  quoted in fenced blocks inside real specs. A header or `- **FR-###**:` bullet
  in a fence must never become a requirement — that would fabricate criteria the
  node was never dispatched against.
- **Nothing unverifiable gets through.** A story with no scenarios, an FR with no
  obligation keyword, a scenario item with no Given/When/Then steps, a duplicated
  key: each is rejected *naming the offender*, because the error's audience is an
  operator who has to go fix one line in one spec. The corpus gives each defect
  its own file with everything else well-formed, so "names the right one" is
  assertable.
- **Bodies and steps are the spec's words.** `raw_text` keeps the source item
  verbatim, newlines and all; `steps` unwrap the line breaks but change nothing
  else, markers included — the judge prompt quotes both (contracts/judge.md), and
  a paraphrase there is a paraphrase of the acceptance criteria themselves.

Two deliberate divisions of labour show up as assertions and are worth stating
outright, since a reader could reasonably expect either:

- `Scenario.raw_text` is byte-verbatim (enumerator, indentation, line breaks);
  `Scenario.steps` and `Requirement.body` collapse wrapped lines to single
  spaces. One is for quoting the source, the other for reading.
- A spec is validated whole. Requesting only `US1` from a file whose `FR-002` is
  malformed still fails: the system of record is either well-formed or it is not,
  and a lazily-validated spec would hand different nodes different verdicts about
  whether the same file is usable.

Written before `factory/verify/criteria.py` exists (T008 precedes T009): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pytest

from factory.verify.criteria import (
    CriteriaParseError,
    load_criteria,
    parse_spec,
    select_requirements,
)
from factory.verify.models import CriteriaSet, Requirement, RequirementKind, Scenario

CORPUS = Path(__file__).resolve().parent / "fixtures" / "speckit"

#: The fixture exercising every production of the grammar (architecture §2).
FULL_GRAMMAR = "010-full-grammar"

#: The real-world fixture: a verbatim copy of component 1's shipped spec.
REAL_WORLD = "001-usage-tracking"


def spec_path(feature: str) -> Path:
    return CORPUS / feature / "spec.md"


def spec_text(feature: str) -> str:
    return spec_path(feature).read_text(encoding="utf-8")


def parse(feature: str) -> list[Requirement]:
    return parse_spec(spec_text(feature))


def by_key(requirements: Sequence[Requirement]) -> dict[str, Requirement]:
    return {requirement.key: requirement for requirement in requirements}


def keys(requirements: Sequence[Requirement]) -> list[str]:
    return [requirement.key for requirement in requirements]


# Story headers ---------------------------------------------------------------


def test_story_headers_yield_keyed_requirements() -> None:
    """`### User Story <n> - <title> (Priority: P<m>)` → `US<n>` + title + priority."""
    stories = [r for r in parse(FULL_GRAMMAR) if r.kind is RequirementKind.STORY]

    assert keys(stories) == ["US1", "US2", "US3"]
    assert [s.title for s in stories] == [
        "Borrow a book",
        "Return a book",
        "Renew a loan",
    ]
    assert [s.priority for s in stories] == ["P1", "P2", "P3"]


def test_story_body_is_the_narrative_not_the_template_scaffolding() -> None:
    """The body is what the story says, not the `**Why this priority**` boilerplate.

    The judge prompt carries the body verbatim (contracts/judge.md); prioritisation
    notes and the human's independent-test recipe are process metadata, not
    acceptance criteria.
    """
    us1 = by_key(parse(FULL_GRAMMAR))["US1"]

    assert us1.body == (
        "As a library member, I can borrow an available copy so that I can read "
        "it at home."
    )
    assert "Why this priority" not in us1.body
    assert "Independent Test" not in us1.body
    assert "Acceptance Scenarios" not in us1.body


def test_wrapped_story_narrative_collapses_to_one_line() -> None:
    """A narrative wrapped across source lines reads as one paragraph."""
    us1 = by_key(parse(REAL_WORLD))["US1"]

    assert us1.body.startswith("As the factory operator, every LLM-consuming node's")
    assert us1.body.endswith("without relying on the agent to self-report.")
    assert "\n" not in us1.body
    assert "Why this priority" not in us1.body


# Acceptance scenarios --------------------------------------------------------


def test_scenario_ids_are_story_key_plus_one_based_position() -> None:
    us1 = by_key(parse(FULL_GRAMMAR))["US1"]

    assert [s.scenario_id for s in us1.scenarios] == ["US1-S1", "US1-S2", "US1-S3"]
    assert all(isinstance(s, Scenario) for s in us1.scenarios)


def test_scenario_steps_are_captured_in_order_with_their_markers() -> None:
    us1 = by_key(parse(FULL_GRAMMAR))["US1"]

    assert us1.scenarios[0].steps == [
        "**Given** an available copy of a book,",
        "**When** a member in good standing borrows it,",
        "**Then** a loan is recorded with a 21-day due date.",
    ]


def test_multiple_and_steps_are_each_their_own_step() -> None:
    """`**And**` repeats; each segment is a separate step, in source order."""
    us1 = by_key(parse(FULL_GRAMMAR))["US1"]

    assert us1.scenarios[1].steps == [
        "**Given** a member already holding the maximum number of loans,",
        "**When** they try to borrow another copy,",
        "**Then** the request is refused,",
        "**And** the refusal states how many loans they currently hold,",
        "**And** the copy stays available.",
    ]


def test_wrapped_scenario_item_keeps_raw_text_verbatim_and_unwraps_steps() -> None:
    """The two representations differ on purpose: source fidelity vs readability."""
    wrapped = by_key(parse(FULL_GRAMMAR))["US1"].scenarios[2]

    assert wrapped.raw_text == (
        "3. **Given** a copy already on loan, **When** another member requests it,"
        " **Then** the\n"
        "   member is offered a hold, **And** the hold is queued behind any hold"
        " already\n"
        "   standing against that copy."
    )
    assert wrapped.steps == [
        "**Given** a copy already on loan,",
        "**When** another member requests it,",
        "**Then** the member is offered a hold,",
        "**And** the hold is queued behind any hold already standing against that copy.",
    ]


def test_bold_text_that_is_not_a_keyword_does_not_start_a_step() -> None:
    """`**no spend cap**` is emphasis inside a Then, not a fifth step.

    Splitting on "some bold run" instead of on the four keywords would shred the
    real-world spec's scenarios into fragments the judge could not score.
    """
    first = by_key(parse(REAL_WORLD))["US1"].scenarios[0]

    assert len(first.steps) == 3
    assert first.steps[0].startswith("**Given** a node `n1` in epic `e1`")
    assert first.steps[1] == "**When** the node is dispatched,"
    assert first.steps[2].endswith("a TTL backstop — and **no spend cap**.")


# Functional requirements -----------------------------------------------------


def test_functional_requirement_bullets_yield_declarative_requirements() -> None:
    functional = [
        r for r in parse(FULL_GRAMMAR) if r.kind is RequirementKind.FUNCTIONAL
    ]

    assert keys(functional) == ["FR-001", "FR-002", "FR-003", "FR-004"]
    assert all(r.title is None and r.priority is None for r in functional)
    assert all(r.scenarios == [] for r in functional)
    assert functional[0].body.startswith("The system MUST record one loan per")


def test_wrapped_functional_requirement_body_collapses_to_one_line() -> None:
    fr004 = by_key(parse(FULL_GRAMMAR))["FR-004"]

    assert fr004.body == (
        "The system MUST queue holds per copy in request order, and MUST offer a "
        "returned copy to the first hold in that queue before making it generally "
        "available."
    )


def test_bold_bullets_that_are_not_requirements_are_ignored() -> None:
    """`- **Loan**:` (Key Entities) and `- **SC-001**:` (Success Criteria) are not
    requirement keys — only `FR-###` bullets are."""
    parsed_keys = keys(parse(FULL_GRAMMAR))

    assert parsed_keys == ["US1", "US2", "US3", "FR-001", "FR-002", "FR-003", "FR-004"]
    assert not any(k.startswith("SC-") for k in parsed_keys)
    assert "Loan" not in parsed_keys


# Fence masking ---------------------------------------------------------------


def test_fenced_headers_and_bullets_are_inert() -> None:
    """011 puts a story header and an FR bullet inside markdown, bare and tagged
    fences; exactly one story and one FR live outside them."""
    parsed = parse("011-fenced-decoys")

    assert keys(parsed) == ["US1", "FR-001"]
    for decoy in ("US5", "US6", "US7", "FR-555", "FR-666", "FR-777"):
        assert decoy not in keys(parsed)


def test_a_fence_inside_a_story_does_not_hijack_its_scenario_list() -> None:
    """010's US2 quotes a template excerpt — header, scenario list and FR bullet —
    between its narrative and its real `**Acceptance Scenarios**:` list.

    A parser that missed the fence would bind US2 to the decoy's single scenario
    and never see the two real ones.
    """
    us2 = by_key(parse(FULL_GRAMMAR))["US2"]

    assert [s.scenario_id for s in us2.scenarios] == ["US2-S1", "US2-S2"]
    assert all("fenced decoy" not in s.raw_text for s in us2.scenarios)
    assert "US8" not in keys(parse(FULL_GRAMMAR))
    assert "FR-900" not in keys(parse(FULL_GRAMMAR))
    assert "FR-901" not in keys(parse(FULL_GRAMMAR))


# Validation ------------------------------------------------------------------

#: (fixture, the requirement the error must name, siblings it must not name).
#: Each fixture carries exactly one defect; everything else in it is well-formed.
INVALID_FIXTURES: list[tuple[str, str, tuple[str, ...]]] = [
    ("012-story-without-scenarios", "US2", ("US1",)),
    ("013-story-empty-scenario-list", "US2", ("US1",)),
    ("014-fr-missing-modal", "FR-002", ("FR-001", "FR-003")),
    ("015-scenario-without-keywords", "US1-S2", ("US1-S1", "US1-S3")),
    ("016-duplicate-story-key", "US2", ("US1",)),
    ("017-duplicate-fr-key", "FR-002", ("FR-001", "FR-003")),
]


@pytest.mark.parametrize(
    "feature, offender, innocents",
    INVALID_FIXTURES,
    ids=[fixture for fixture, _, _ in INVALID_FIXTURES],
)
def test_validation_errors_name_the_exact_offender(
    feature: str, offender: str, innocents: tuple[str, ...]
) -> None:
    with pytest.raises(CriteriaParseError) as excinfo:
        parse(feature)

    assert excinfo.value.offender == offender
    message = str(excinfo.value)
    assert offender in message
    for innocent in innocents:
        assert innocent not in message


def test_the_whole_spec_is_validated_even_when_one_key_is_requested() -> None:
    """A malformed spec is unusable, not partially usable.

    Lazily validating only the requested requirement would let two nodes disagree
    about whether the same system-of-record file is well-formed.
    """
    with pytest.raises(CriteriaParseError) as excinfo:
        load_criteria(
            spec_path("014-fr-missing-modal"),
            feature="014-fr-missing-modal",
            spec_ref="epic/US1",
            requirement_keys=["US1"],
        )

    assert excinfo.value.offender == "FR-002"


# Requirement filtering -------------------------------------------------------


def test_requested_keys_select_exactly_those_requirements_in_request_order() -> None:
    parsed = parse(FULL_GRAMMAR)

    selected = select_requirements(parsed, ["FR-003", "US2"])

    assert keys(selected) == ["FR-003", "US2"]
    assert selected[1].scenarios == by_key(parsed)["US2"].scenarios


def test_no_requested_keys_selects_every_requirement_in_document_order() -> None:
    parsed = parse(FULL_GRAMMAR)

    assert keys(select_requirements(parsed, [])) == keys(parsed)


def test_a_requested_key_absent_from_the_spec_names_the_missing_key() -> None:
    """Spec US1 scenario 4: dispatching against a key the spec does not declare is
    a parse failure, not an empty CriteriaSet."""
    with pytest.raises(CriteriaParseError) as excinfo:
        select_requirements(parse(FULL_GRAMMAR), ["US1", "FR-404"])

    assert excinfo.value.offender == "FR-404"
    assert "FR-404" in str(excinfo.value)


def test_load_criteria_filters_to_the_requested_keys() -> None:
    criteria = load_criteria(
        spec_path(FULL_GRAMMAR),
        feature=FULL_GRAMMAR,
        spec_ref="e1/n1",
        requirement_keys=["US2", "FR-001"],
    )

    assert isinstance(criteria, CriteriaSet)
    assert keys(criteria.requirements) == ["US2", "FR-001"]


# CriteriaSet: the dispatch-time snapshot -------------------------------------


def test_criteria_set_carries_its_attribution_and_source() -> None:
    path = spec_path(FULL_GRAMMAR)

    criteria = load_criteria(
        str(path),
        feature=FULL_GRAMMAR,
        spec_ref="e1/n1",
        requirement_keys=["US1"],
    )

    assert criteria.feature == FULL_GRAMMAR
    assert criteria.spec_ref == "e1/n1"
    assert criteria.source_path == str(path)


def test_source_sha256_hashes_the_raw_file_bytes(tmp_path: Path) -> None:
    """Drift detection re-hashes the file at verify time (R8), so the hash must
    move on any byte change — including one that changes no requirement."""
    original = spec_path(FULL_GRAMMAR).read_bytes()
    target = tmp_path / "spec.md"
    target.write_bytes(original)

    before = load_criteria(target, feature=FULL_GRAMMAR, spec_ref="e1/n1")
    target.write_bytes(original + b"\n")
    after = load_criteria(target, feature=FULL_GRAMMAR, spec_ref="e1/n1")

    assert before.source_sha256 == hashlib.sha256(original).hexdigest()
    assert after.source_sha256 != before.source_sha256
    assert keys(after.requirements) == keys(before.requirements)


def test_snapshotted_at_defaults_to_utc_now_and_accepts_a_caller_stamp() -> None:
    criteria = load_criteria(
        spec_path(FULL_GRAMMAR), feature=FULL_GRAMMAR, spec_ref="e1/n1"
    )

    assert criteria.snapshotted_at.endswith("Z")
    stamped = datetime.fromisoformat(criteria.snapshotted_at.replace("Z", "+00:00"))
    assert stamped.utcoffset() == timedelta(0)
    assert abs(datetime.now(timezone.utc) - stamped) < timedelta(minutes=5)

    fixed = load_criteria(
        spec_path(FULL_GRAMMAR),
        feature=FULL_GRAMMAR,
        spec_ref="e1/n1",
        snapshotted_at="2026-08-04T00:00:00Z",
    )
    assert fixed.snapshotted_at == "2026-08-04T00:00:00Z"


def test_a_missing_spec_file_raises_file_not_found(tmp_path: Path) -> None:
    """Distinct from a parse failure: the activity maps this to
    `CRITERIA_FILE_MISSING` and the other to `CRITERIA_PARSE_FAILED`."""
    with pytest.raises(FileNotFoundError):
        load_criteria(tmp_path / "spec.md", feature="404-nope", spec_ref="e1/n1")


# The real-world fixture (SC-001) ---------------------------------------------


def test_component_ones_shipped_spec_parses_completely() -> None:
    """A spec written months before this parser, with no fixture accommodations."""
    parsed = parse(REAL_WORLD)
    stories = [r for r in parsed if r.kind is RequirementKind.STORY]
    functional = [r for r in parsed if r.kind is RequirementKind.FUNCTIONAL]

    assert keys(stories) == ["US1", "US2", "US3"]
    assert keys(functional) == [f"FR-{n:03d}" for n in range(1, 13)]
    assert all("MUST" in r.body or "SHALL" in r.body for r in functional)


def test_component_ones_scenarios_are_all_captured() -> None:
    parsed = by_key(parse(REAL_WORLD))

    assert [s.scenario_id for s in parsed["US1"].scenarios] == [
        f"US1-S{k}" for k in range(1, 6)
    ]
    assert [s.scenario_id for s in parsed["US2"].scenarios] == [
        f"US2-S{k}" for k in range(1, 5)
    ]
    assert [s.scenario_id for s in parsed["US3"].scenarios] == ["US3-S1", "US3-S2"]
    assert all(
        scenario.steps for story in parsed.values() for scenario in story.scenarios
    )


def test_the_fixture_is_a_verbatim_copy_of_the_shipped_spec() -> None:
    """The point of the real-world fixture is that nobody adjusted it to pass.

    If component 1's spec is edited, this fails loudly rather than letting the
    corpus drift into a private dialect of Spec Kit.
    """
    shipped = Path(__file__).resolve().parents[1] / "specs" / REAL_WORLD / "spec.md"

    assert spec_path(REAL_WORLD).read_bytes() == shipped.read_bytes()
