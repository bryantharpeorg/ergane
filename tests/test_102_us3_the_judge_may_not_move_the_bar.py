"""US3 of 102: a judge may say a criterion cannot be met; it may not say to change it.

The measured case behind this story: a criterion was unsatisfiable as drafted, the
judge refused the attempt — correctly — and its feedback offered two remediations,
the second being "reconcile the scenario text with…". The verdict was right, which
is exactly why it is worth defending against: the same sentence carried into the
next attempt's prompt is an instruction from the one authority the agent is not
allowed to argue with, telling it to edit its own acceptance criteria.
`criteria_drift` never fires on this, because nothing has drifted yet — the judge
has merely proposed that it should.

Four things are asserted, and the split between them is the whole design:

- **T016** — the instruction (FR-008). A string assertion, and weak on its own,
  which is why it is the smallest of the four.
- **T017** — the enforceable half (FR-009, trap 6). The proposal is *recorded* on
  the verdict and *kept out* of the next attempt's prompt. Build the filter and
  test the filter; the instruction only reduces how often it fires.
- **T018** — the signal that must survive (FR-010, trap 7). "This criterion cannot
  be satisfied" and "change this criterion" are one sentence apart in English, and
  a filter that eats both silences the report this whole spec exists to surface
  earlier. It reaches the agent *and* it is named to the operator.
- **T019** — the control (US3-S4). Feedback that proposes nothing reaches the next
  attempt byte-for-byte. A false positive here deletes a retry's only guidance,
  so the corpus below is deliberately full of sentences that mention criteria,
  scenarios and the word "update" without proposing anything.
- **T020** — visibility (trap 8). Withheld is not discarded: the operator surface
  names the proposal, and the evidence store round-trips the feedback verbatim.

Plain unit tests over text fixtures — every seam under test is a pure function.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from factory.notify.messages import render_history
from factory.usage.models import Termination
from factory.verify.judge import SYSTEM_PROMPT, build_prompt, parse_verdict
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationForm,
    VerificationResult,
)
from factory.verify.remediation import WITHHELD_NOTICE, screen_feedback
from factory.verify.store import connect, node_history, upsert_result
from factory.workgraph.models import WorkNode
from factory.workgraph.prompt import AttemptEvidence, build_attempt_prompt

EPIC_ID = "demo-loans"

# --- feedback fixtures --------------------------------------------------------

#: The actionable half of a real rejection: what failed and where. This must
#: reach the next attempt in every case below, or the filter has cost more than
#: it saved.
ACTIONABLE = (
    "US1-S2 fails: borrow() records a second loan for a book already on loan, so "
    "nothing in the diff refuses it."
)

#: The measured sentence, near enough. This is what must never reach an agent.
PROPOSAL = (
    "Alternatively, reconcile the scenario text with the implementation you "
    "produced."
)

#: The other half of the same rejection, and the one the operator most needs:
#: the judge saying the bar cannot be cleared at all. This must reach the agent
#: too — it is the sentence that makes the next attempt ask rather than thrash.
REPORT = (
    "Scenario US1-S3 cannot be satisfied by any diff: it asserts a font rendering "
    "in a browser, and no declared gate measures that."
)

#: Report and proposal welded into one sentence, which is where trap 7 bites: a
#: filter that carries this has carried the proposal, and one that drops it
#: without recording the report has silenced the signal.
WELDED = (
    "US1-S3 cannot be met as written, so reword the acceptance criterion to name "
    "something the diff can show."
)

#: Feedback that proposes nothing and must survive byte-for-byte. Every entry
#: names a criterion, a scenario or a change — the vocabulary the filter keys on
#: — while proposing no edit to the bar at all.
INNOCENT_CORPUS = (
    ACTIONABLE,
    "US1-S1 passes. US1-S2 does not: the criterion requires a refusal path and "
    "the diff has none.\n\nUpdate the loan repository to reject a second loan, "
    "and update the test to cover it.",
    "The scenario asks for a SIGKILL escalation. Change the timeout path in "
    "runner.py so it escalates, then rerun the gates.",
    "Nothing in the diff satisfies the acceptance criteria for US1-S2. Move the "
    "assertion out of the fixture and into the test so it actually runs.",
    "The judge could not read your previous response. Answer again with only the "
    "JSON verdict object described above.",
    # This factory builds itself, so its own judge writes remediations *about*
    # code named after the criteria. Losing these to the filter would cost a
    # retry the only guidance it had, on exactly the specs this one belongs to.
    "The diff does not update the criteria snapshot the judge is given. Change "
    "the criteria parser so a Then-clause is captured whole, and update the "
    "criteria set in the fixture to match.",
)


# --- prompt fixtures ----------------------------------------------------------

SPEC_TEXT = """# Feature Specification: Library Loans

## User Scenarios & Testing

### User Story 1 - Borrow a book (Priority: P1)

A member borrows an available book and the catalogue records the loan.

**Acceptance Scenarios**:

1. **Given** a member with no loans, **When** they borrow, **Then** the loan is recorded.

## Requirements

### Functional Requirements

- **FR-001**: The catalogue MUST record every loan against the borrowing member.
"""

PLAN_TEXT = """# Implementation Plan: Library Loans

## Summary

One `loans` table is the system of record.
"""

TASKS_TEXT = """# Tasks: Library Loans

## Phase 2: User Story 1 - Borrow a book (Priority: P1)

- [ ] T002 [US1] Write tests/test_loans.py FIRST
- [ ] T003 [US1] Implement library/loans.py until T002 passes
"""

SCENARIO = Scenario(
    scenario_id="US1-S1",
    steps=[
        "**Given** a member with no loans",
        "**When** they borrow",
        "**Then** the loan is recorded",
    ],
    raw_text=(
        "1. **Given** a member with no loans, **When** they borrow, **Then** the "
        "loan is recorded."
    ),
)

CRITERIA = CriteriaSet(
    feature="demo-loans",
    spec_ref="demo-loans/US1",
    requirements=[
        Requirement(
            key="US1",
            kind=RequirementKind.STORY,
            title="Borrow a book",
            priority="P1",
            body="A member borrows an available book.",
            scenarios=[SCENARIO],
        )
    ],
    source_path="specs/demo-loans/spec.md",
    source_sha256="c0ffee" + "0" * 58,
    snapshotted_at="2026-08-30T09:15:00Z",
)

DIFF_TEXT = (
    "diff --git a/library/loans.py b/library/loans.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/library/loans.py\n"
    "+++ b/library/loans.py\n"
    "@@ -1 +1,2 @@\n"
    "+def borrow(member, book):\n"
    "+    return Loan(member, book)\n"
)


def make_verdict(feedback: str) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=JudgeOutcome.RETRY,
        findings=[
            JudgeScenarioFinding(
                scenario="US1-S1", passed=False, reasoning="no refusal path"
            )
        ],
        feedback=feedback,
        judge_attempt=1,
        truncated_input=False,
        model_alias="judge",
    )


def make_result(judge: JudgeVerdict) -> VerificationResult:
    return VerificationResult(
        epic_id=EPIC_ID,
        node_id="us1",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=11.5,
                output_tail="1 passed",
            )
        ],
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=judge,
        verdict=OverallVerdict.FAIL,
        judge_unavailable=False,
        criteria_drift=False,
        criteria_sha256="c" * 64,
        spec_ref="demo-loans/US1",
        started_at="2026-08-30T10:00:00Z",
        finished_at="2026-08-30T10:20:00Z",
    )


def retry_prompt(feedback: str) -> str:
    """The next attempt's prompt, with one failed attempt's judge verdict in it."""
    return build_attempt_prompt(
        node=WorkNode(
            id="us1",
            story_key="US1",
            persona="implementer",
            spec_ref="demo-loans/US1",
            requirement_keys=["US1", "FR-001"],
            depends_on=[],
        ),
        epic_id=EPIC_ID,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text=TASKS_TEXT,
        prior_attempts=[
            AttemptEvidence(
                termination=Termination.COMPLETED,
                result=make_result(make_verdict(feedback)),
            )
        ],
    )


def judge_retry_prompt(feedback: str) -> str:
    """The judge's own next invocation, which is handed the same text (FR-006)."""
    prompt = build_prompt(CRITERIA, DIFF_TEXT, prior_feedback=feedback)
    return prompt.messages[1]["content"]


def response(feedback: str) -> str:
    """A judge response carrying `feedback`, as the model would return it."""
    import json

    return json.dumps(
        {
            "verdict": "retry",
            "scenarios": [
                {
                    "scenario": "US1-S1",
                    "pass": False,
                    "reasoning": "the diff records no loan",
                }
            ],
            "feedback": feedback,
        }
    )


# --- T016 (spec US3-S1, FR-008) -----------------------------------------------


def test_the_judges_instructions_forbid_proposing_a_change_to_the_criteria() -> None:
    """The prohibition itself, beside the looks-reasonable one it is modelled on."""
    assert "Never pass a scenario because the change looks reasonable overall." in (
        SYSTEM_PROMPT
    ), "the prohibition this one sits beside has moved; check they are still together"

    prohibition = re.search(
        r"[^.]*\b(never|not|no)\b[^.]*\b(propose|proposing|suggest|suggesting|"
        r"recommend|recommending|offer|offering|ask)\w*[^.]*"
        r"\b(criteri(?:on|a)|scenario|acceptance)\b[^.]*\.",
        SYSTEM_PROMPT,
        re.IGNORECASE,
    )
    assert prohibition is not None, (
        "the judge's instructions do not forbid proposing a change to the "
        "acceptance criteria as a remediation"
    )
    assert re.search(
        r"\b(chang\w*|reword\w*|rephras\w*|rewrit\w*|relax\w*|edit\w*|amend\w*|"
        r"reconcil\w*|revis\w*|adjust\w*|updat\w*)\b",
        prohibition.group(0),
        re.IGNORECASE,
    ), (
        "the prohibition names no edit; forbidding an unnamed thing teaches "
        f"nothing: {prohibition.group(0)!r}"
    )


def test_the_instructions_still_invite_the_report_they_forbid_the_proposal_of() -> None:
    """Trap 7, in the instruction. Forbidding the proposal without inviting the
    report would suppress the judge's most useful signal at the source, and no
    downstream filter can recover a sentence that was never written."""
    assert re.search(
        r"\b(cannot|can never|impossible)\b[^.]*\b(satisf\w*|met|meet|prove\w*|"
        r"eviden\w*|show\w*)\b",
        SYSTEM_PROMPT,
        re.IGNORECASE,
    ), (
        "the instructions forbid proposing a criterion change without saying the "
        "judge may report that a criterion cannot be satisfied"
    )


def test_the_prohibition_reaches_the_model_not_only_the_module() -> None:
    """A constant nobody sends is a comment. It rides in the system message."""
    system = build_prompt(CRITERIA, DIFF_TEXT).messages[0]
    assert system["role"] == "system"
    assert system["content"] == SYSTEM_PROMPT


# --- T017 (spec US3-S2, FR-009, trap 6) ---------------------------------------


def test_a_proposal_to_change_a_criterion_is_recorded_on_the_verdict() -> None:
    """Recorded, not discarded: the verdict keeps the judge's words verbatim."""
    verdict = parse_verdict(
        response(f"{ACTIONABLE}\n\n{PROPOSAL}"),
        ["US1-S1"],
        judge_attempt=1,
        model_alias="judge",
    )

    assert PROPOSAL in verdict.feedback
    assert ACTIONABLE in verdict.feedback


def test_the_proposal_does_not_reach_the_next_attempts_prompt() -> None:
    """The enforceable half. What an agent is told to do, an agent will do."""
    prompt = retry_prompt(f"{ACTIONABLE}\n\n{PROPOSAL}")

    assert PROPOSAL not in prompt, (
        "the judge's proposal to change the acceptance criteria reached the agent"
    )
    assert "reconcile the scenario text" not in prompt.lower()
    assert ACTIONABLE in prompt, (
        "the actionable half of the feedback was filtered out with the proposal"
    )
    assert WITHHELD_NOTICE in prompt, (
        "the prompt drops the proposal silently; the agent should be told the "
        "criteria are fixed rather than left with an amputated verdict"
    )


def test_the_proposal_does_not_reach_the_judges_own_next_invocation() -> None:
    """The same text is carried into the next judge attempt (FR-006), and a
    proposal quoted back at the judge as "what was said then" is a proposal the
    judge is being invited to repeat."""
    user = judge_retry_prompt(f"{ACTIONABLE}\n\n{PROPOSAL}")

    assert PROPOSAL not in user
    assert ACTIONABLE in user


def test_the_proposal_is_recognised_when_it_names_the_scenario_by_id() -> None:
    """The shortest form of the same sentence. A judge that has been told not to
    propose a criterion change will not phrase the next one the same way."""
    for text in (
        "Consider rewording US1-S2 to name an artefact the diff carries.",
        "The acceptance criterion should be relaxed to something the diff shows.",
        "Reword the Then-clause so it names a file.",
        "Or move the bar to what this implementation actually does.",
    ):
        screened = screen_feedback(text)
        assert screened.proposals == (text,), (
            f"not recognised as a proposal to change the bar: {text!r}"
        )
        assert text not in screened.carried


def test_a_welded_report_and_proposal_is_withheld_and_still_recorded() -> None:
    """One sentence carrying both: the agent gets neither, the operator gets both."""
    screened = screen_feedback(WELDED)

    assert WELDED not in screened.carried, (
        "a sentence proposing the criterion be reworded reached the agent because "
        "it also reported the criterion cannot be met"
    )
    assert WELDED in screened.proposals
    assert WELDED in screened.unsatisfiable_reports, (
        "the report half of the sentence was lost; the operator is never told the "
        "judge thinks the criterion cannot be met"
    )


# --- T018 (spec US3-S3, FR-010, trap 7) ---------------------------------------


def test_an_unsatisfiability_report_is_preserved_for_the_next_attempt() -> None:
    """Saying a criterion cannot be met is exactly what the judge should do."""
    prompt = retry_prompt(f"{ACTIONABLE}\n\n{REPORT}")

    assert REPORT in prompt, (
        "the filter silenced the judge reporting an unsatisfiable criterion — the "
        "one signal this spec exists to surface earlier"
    )
    assert WITHHELD_NOTICE not in prompt, (
        "a report of unsatisfiability was treated as a proposal to change the bar"
    )


def test_an_unsatisfiability_report_is_surfaced_to_the_operator() -> None:
    """It is named as such, not left for the operator to find in a wall of text:
    an unsatisfiable criterion is an operator defect, and the operator is the
    only one who can fix it."""
    summary = render_history([make_result(make_verdict(f"{ACTIONABLE}\n\n{REPORT}"))])

    assert REPORT in summary
    assert re.search(r"unsatisfiable|cannot be (satisfied|met)", summary, re.I), (
        "the operator surface does not name the judge's unsatisfiability report"
    )


def test_the_report_is_recognised_in_several_spellings() -> None:
    """The judge writes English, not a schema. A rule this narrow is only worth
    having if it fires on the phrasings a judge actually reaches for."""
    for text in (
        "US1-S3 is unsatisfiable: no diff can evidence a browser rendering.",
        "This criterion cannot be met by any diff.",
        "The scenario cannot be proven from the diff alone.",
        "It is impossible to satisfy US1-S3 as written.",
    ):
        assert screen_feedback(text).unsatisfiable_reports, (
            f"not recognised as an unsatisfiability report: {text!r}"
        )


# --- T019 (spec US3-S4) — the control ------------------------------------------


def test_feedback_proposing_no_criterion_change_reaches_the_agent_unchanged() -> None:
    """Byte-for-byte. A retry shown a mangled verdict has been handed a summary
    of its failure instead of the failure (002 FR-006)."""
    for feedback in INNOCENT_CORPUS:
        screened = screen_feedback(feedback)
        assert screened.carried == feedback, (
            f"the filter altered feedback that proposes nothing: {feedback!r}"
        )
        assert not screened.proposals

        prompt = retry_prompt(feedback)
        assert feedback in prompt
        assert WITHHELD_NOTICE not in prompt


def test_empty_and_whitespace_feedback_is_left_alone() -> None:
    """The degenerate inputs, so the filter cannot invent a notice out of nothing."""
    for feedback in ("", "   ", "\n\n"):
        screened = screen_feedback(feedback)
        assert screened.carried == feedback
        assert not screened.proposals
        assert not screened.unsatisfiable_reports


# --- T020 (FR-009, trap 8) — a withheld proposal is still visible --------------


def test_the_operator_sees_the_proposal_the_agent_was_not_shown() -> None:
    """Withheld is not discarded. An operator asking why an epic struggled needs
    to see that the judge wanted the bar moved; the agent does not."""
    summary = render_history([make_result(make_verdict(f"{ACTIONABLE}\n\n{PROPOSAL}"))])

    assert PROPOSAL in summary
    assert re.search(r"withheld|not shown|kept out", summary, re.IGNORECASE), (
        "the operator surface reproduces the proposal without saying it was kept "
        "out of the retry, so nothing tells the operator it happened"
    )


def test_the_evidence_store_round_trips_the_proposal_verbatim(tmp_path: Any) -> None:
    """The recording outlives the process. The store is where an operator reads
    an epic back weeks later, and a filtered prompt must not filter the record."""
    feedback = f"{ACTIONABLE}\n\n{PROPOSAL}"
    conn: sqlite3.Connection = connect(tmp_path / "verification.db")
    try:
        upsert_result(conn, make_result(make_verdict(feedback)))
        stored = node_history(conn, EPIC_ID, "us1")
    finally:
        conn.close()

    assert len(stored) == 1
    judge = stored[0].judge
    assert judge is not None
    assert judge.feedback == feedback
