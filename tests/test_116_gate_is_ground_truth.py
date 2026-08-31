"""A verdict that contradicts a recorded gate is the judge's fault, not the node's.

116-US2. US1 put the factory's own measurements into the judge's prompt, which
improves the odds. It leaves one case exactly where it was: a judge whose
reasoning asserts *"the pytest gate would fail"* about a gate recorded PASS in
the same row. That finding is unwinnable rather than merely wrong — the only way
to satisfy it is to re-add or touch files that are already committed, which is
padding the diff to please the grader, the exact behaviour this repository
teaches its agents to refuse. So the node is not charged for it.

Five claims, and three of them are about restraint:

- **A contradiction is recorded and does not by itself fail the node**
  (US2-S1, FR-006). Recorded, because a neutralisation nobody can see is
  indistinguishable from a judge that agreed.
- **A contradiction spends a judge retry** (US2-S2, FR-007). It rides
  `judge_attempt` / `max_judge_retries`, the budget that already exists — a
  judge fault is the one failure a judge retry is actually for, and a second
  budget would be a second place deciding how often a model is re-asked.
- **With that budget spent, the contradiction is still recorded and still does
  not fail the node on that finding alone** (US2-S3). Exhausting the re-asks
  does not convert the judge's fault into the node's.
- **A verdict whose findings name no gate composes exactly as today**
  (US2-S4) — the control, because this check may not move any verdict it was
  not written for.
- **A finding naming a gate that genuinely failed is honoured** (US2-S5), as is
  one that merely mentions a passing gate. The check is for *contradiction*,
  not for gate mentions, and the difference is the whole safety margin: a false
  positive here turns a real node FAIL into a PASS.

Two hazards from the plan get their own tests. Trap 5: gate names are matched on
boundaries, never as bare substrings, because this repository has already been
bitten once by an unanchored match (`factory/cli/doctor.py:58`) — and a gate
named `test` must not be found inside `test-fixtures` or `smoketest`. Trap 6: a
contradiction neutralises one finding, it does not pass the attempt; a second,
unrelated failing finding still fails the node.

Where the decision is made matters as much as what it decides (trap 7).
`compose_result` already carries the comment that the moment two places can
decide a FAIL, the stored row and the retry prompt can disagree — so the
neutralisation happens where `judge_accepts` is derived and nowhere else, and
`run_judge` only ever decides whether to *re-ask*.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

import pytest

from factory.verify.judge import DEFAULT_MAX_JUDGE_RETRIES, run_judge
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
    compose_result,
    detect_gate_contradictions,
    judge_should_be_reasked,
)

from tests.judge_proxy import JUDGE_MODEL_ALIAS, FakeJudgeProxy

# --- what the node was dispatched against ------------------------------------


def scenario(scenario_id: str, then: str) -> Scenario:
    return Scenario(
        scenario_id=scenario_id,
        steps=[
            "**Given** a verdict whose finding names a gate recorded PASS",
            "**When** the verdict is composed",
            f"**Then** {then}",
        ],
        raw_text=f"{scenario_id}: **Then** {then}",
    )


FIRST = scenario("US2-S1", "the contradiction is recorded")
SECOND = scenario("US2-S2", "the judge is retried rather than the node failed")

CRITERIA = CriteriaSet(
    feature="116-the-judge-scores-against-what-the-factory-measured",
    spec_ref="gate-is-ground-truth/a-contradiction-is-a-judge-fault",
    requirements=[
        Requirement(
            key="US2",
            kind=RequirementKind.STORY,
            title="A verdict that contradicts a recorded gate is a judge fault",
            priority="P1",
            body=(
                "As an operator, when the judge's reasoning asserts a gate would "
                "fail and that gate is recorded PASS in the same row, the node is "
                "not charged for it."
            ),
            scenarios=[FIRST, SECOND],
        )
    ],
    source_path="specs/116-the-judge-scores-against-what-the-factory-measured/spec.md",
    source_sha256="d0cf11e0" + "0" * 56,
    snapshotted_at="2026-08-28T10:00:00Z",
)

DIFF = (
    "diff --git a/factory/verify/models.py b/factory/verify/models.py\n"
    "--- a/factory/verify/models.py\n"
    "+++ b/factory/verify/models.py\n"
    "@@ -712,1 +712,1 @@ def compose_result(\n"
    "-    judge_accepts = judge is None\n"
    "+    judge_accepts = judge is None or not unexplained_failures\n"
)


# --- what the factory measured ------------------------------------------------


def gate(name: str, status: GateStatus = GateStatus.PASS) -> GateResult:
    """One recorded gate. PASS by default, because that is the judged path.

    `judge_required` returns True only when every gate passed, so a green gate
    beside a failing finding is the only shape the contradiction check ever sees
    in production — and the shape the deadlock this story exists for was built
    from.
    """
    return GateResult(
        name=name,
        command=f"uv run {name}",
        status=status,
        exit_code=0 if status is GateStatus.PASS else 1,
        duration_s=0.4,
        output_tail="12 passed in 0.14s" if status is GateStatus.PASS else "1 failed",
    )


GREEN = [gate("test")]

PROVED_OUTPUT = OutputCheck(
    write_scope="worktree",
    has_diff=True,
    expected_artifacts=[],
    artifacts_present=None,
    passed=True,
)


def verdict(
    *findings: JudgeScenarioFinding,
    outcome: JudgeOutcome = JudgeOutcome.FAIL,
    judge_attempt: int = 1,
) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=outcome,
        findings=list(findings),
        feedback="; ".join(f.reasoning for f in findings if not f.passed),
        judge_attempt=judge_attempt,
        truncated_input=False,
        model_alias=JUDGE_MODEL_ALIAS,
    )


def finding(scenario_id: str, reasoning: str, *, passed: bool = False) -> JudgeScenarioFinding:
    return JudgeScenarioFinding(scenario=scenario_id, passed=passed, reasoning=reasoning)


def composed(
    judge: JudgeVerdict | None,
    gate_results: Sequence[GateResult] = GREEN,
    output_check: OutputCheck = PROVED_OUTPUT,
):
    """Compose one attempt's evidence, with everything but the judge held green."""
    return compose_result(
        epic_id="116-the-judge-scores-against-what-the-factory-measured",
        node_id="us2",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=list(gate_results),
        output_check=output_check,
        judge=judge,
        criteria_sha256=CRITERIA.source_sha256,
        spec_ref=CRITERIA.spec_ref,
        started_at="2026-08-28T10:00:00Z",
        finished_at="2026-08-28T10:04:00Z",
    )


#: The assertion the deadlock was built from, in the judge's own voice.
CONTRADICTION = "The test gate would fail, because the font file is not in the diff."


# --- US2-S1: recorded, and not by itself a node FAIL --------------------------


def test_a_contradiction_is_recorded_and_does_not_by_itself_fail_the_node() -> None:
    """US2-S1, FR-006. The gate is ground truth; the judge's guess is not.

    Both halves are asserted, because either one alone is a defect. Recorded
    without neutralised is today's unwinnable attempt with better paperwork;
    neutralised without recorded is a verdict that quietly disagreed with the
    judge and left nobody a way to notice.
    """
    result = composed(verdict(finding("US2-S1", CONTRADICTION)))

    assert result.verdict is OverallVerdict.PASS, (
        "a finding that contradicts a gate recorded PASS charged the node for "
        "the judge's fault"
    )

    assert len(result.gate_contradictions) == 1
    recorded = result.gate_contradictions[0]
    assert recorded.scenario == "US2-S1"
    assert recorded.gate == "test"
    assert recorded.recorded_status is GateStatus.PASS
    assert "would fail" in recorded.claim, (
        "the record must quote what was asserted, or an operator reading it has "
        "to go and find the reasoning themselves"
    )


def test_the_neutralised_finding_survives_on_the_record() -> None:
    """FR-006. Neutralising a finding is not deleting it.

    The judge's verdict is carried onto the row exactly as it was returned — the
    contradiction is a note *beside* it, not an edit to it. A row that rewrote
    the finding would make the judge look like it agreed, which is the one thing
    the recording exists to prevent.
    """
    scored = verdict(finding("US2-S1", CONTRADICTION))

    result = composed(scored)

    assert result.judge == scored
    assert result.judge is not None
    assert result.judge.outcome is JudgeOutcome.FAIL
    assert result.judge.findings[0].passed is False


# --- US2-S2: a contradiction spends a judge retry ------------------------------


def scored_response(*findings: tuple[str, bool, str], verdict_word: str = "fail") -> str:
    """The JSON a judge returns, scored per scenario."""
    return json.dumps(
        {
            "verdict": verdict_word,
            "scenarios": [
                {"scenario": name, "pass": passed, "reasoning": reasoning}
                for name, passed, reasoning in findings
            ],
            "feedback": "; ".join(reasoning for _, _, reasoning in findings),
        }
    )


async def judged(
    proxy: FakeJudgeProxy, *, gate_results: Sequence[GateResult] = GREEN, **kwargs: Any
) -> JudgeVerdict:
    return await run_judge(
        CRITERIA,
        DIFF,
        proxy_url=proxy.base_url,
        virtual_key=proxy.virtual_key,
        model_alias=JUDGE_MODEL_ALIAS,
        gate_results=list(gate_results),
        transport=proxy.transport,
        retry_backoff_s=0.0,
        **kwargs,
    )


CONTRADICTING_RESPONSE = scored_response(
    ("US2-S1", False, CONTRADICTION),
    ("US2-S2", True, "the retry rides the existing budget"),
)


async def test_a_contradiction_asks_for_a_judge_retry_while_the_budget_is_unspent() -> None:
    """US2-S2, FR-007. The budget it rides is the one that already exists.

    `run_judge` answers RETRY rather than FAIL — the same RETRY a response the
    parser could not read produces, on the same `judge_attempt` /
    `max_judge_retries` ladder. It does not decide the node's fate; that is
    `compose_result`'s, and one decider is the point (trap 7).
    """
    proxy = FakeJudgeProxy()
    proxy.reply(CONTRADICTING_RESPONSE)

    scored = await judged(proxy, judge_attempt=1, max_judge_retries=2)

    assert scored.outcome is JudgeOutcome.RETRY, (
        "a verdict contradicting a green gate ended the attempt instead of "
        "re-asking the judge that produced it"
    )
    assert "test" in scored.feedback and "PASS" in scored.feedback, (
        "the re-ask must tell the judge what it contradicted, or it buys the "
        "same verdict at twice the price"
    )
    assert scored.findings, "the findings are the answer; a retry does not erase them"


async def test_the_re_ask_happens_rather_than_being_merely_requested() -> None:
    """US2-S2. A RETRY nobody acts on is a FAIL with extra words.

    The judge loop breaks out of its budget on a RETRY that names scenarios,
    because re-asking a real objection about an unchanged diff buys the same
    verdict twice. A contradiction is the exception the loop has to know about,
    so the rule lives in one predicate both the workflow and this test read.
    """
    contradicting = verdict(
        finding("US2-S1", CONTRADICTION), outcome=JudgeOutcome.RETRY
    )
    ordinary = verdict(
        finding("US2-S1", "the diff adds no test for the new branch"),
        outcome=JudgeOutcome.RETRY,
    )

    assert judge_should_be_reasked(contradicting, GREEN) is True
    assert judge_should_be_reasked(ordinary, GREEN) is False, (
        "a real objection re-asked about an unchanged diff is the same verdict "
        "at twice the price"
    )
    assert judge_should_be_reasked(
        verdict(finding("US2-S1", CONTRADICTION), outcome=JudgeOutcome.FAIL), GREEN
    ) is False, "only a RETRY is re-asked; the loop's other exits are unchanged"


async def test_an_unreadable_response_is_still_re_asked() -> None:
    """FR-007 takes nothing away. The parse-failure re-ask is untouched."""
    unreadable = JudgeVerdict(
        outcome=JudgeOutcome.RETRY,
        findings=[],
        feedback="The judge's response could not be read",
        judge_attempt=1,
        truncated_input=False,
        model_alias=JUDGE_MODEL_ALIAS,
    )

    assert judge_should_be_reasked(unreadable, GREEN) is True


# --- US2-S3: the budget spent -------------------------------------------------


async def test_a_contradiction_with_the_budget_spent_is_still_not_the_nodes_fault() -> None:
    """US2-S3. Exhausting the re-asks does not transfer the fault.

    On the last judge attempt there is nothing left to ask, so `run_judge`
    returns what the judge said. What it may not do is let that stand as a node
    FAIL: the contradiction is recorded and the attempt does not fail on that
    finding alone.
    """
    proxy = FakeJudgeProxy()
    proxy.reply(CONTRADICTING_RESPONSE)

    spent = await judged(
        proxy, judge_attempt=1 + DEFAULT_MAX_JUDGE_RETRIES, max_judge_retries=DEFAULT_MAX_JUDGE_RETRIES
    )

    assert len(proxy.calls) == 1, "one response, one attempt — no hidden re-ask"
    assert spent.outcome is JudgeOutcome.FAIL, (
        "with the budget spent the judge's own verdict stands; it is the "
        "composition that refuses to charge the node for it"
    )

    result = composed(spent)
    assert result.verdict is OverallVerdict.PASS
    assert [c.gate for c in result.gate_contradictions] == ["test"]


# --- US2-S4: the control ------------------------------------------------------


@pytest.mark.parametrize(
    "reasoning",
    [
        "the diff adds no test for the new branch",
        "US2-S1 fails because the helper is never called",
        "the diff fails to add the artifact the scenario names",
        "nothing here demonstrates the Then-clause",
    ],
    ids=["no-gate-named", "scenario-fails", "fails-to-idiom", "silent"],
)
def test_a_verdict_whose_findings_name_no_gate_composes_exactly_as_today(
    reasoning: str,
) -> None:
    """US2-S4. The control, and the false-positive guard in one.

    Two of these say the word `fail` and one of them says `test`; none of them
    asserts that a gate would fail. A check that neutralised any of them would
    turn a real node FAIL into a PASS, which is a worse defect than the one this
    story fixes.
    """
    result = composed(verdict(finding("US2-S1", reasoning)))

    assert result.verdict is OverallVerdict.FAIL
    assert result.gate_contradictions == ()


def test_a_passing_verdict_is_unchanged() -> None:
    """US2-S4. Nothing about the agreeing path moves."""
    result = composed(
        verdict(
            finding("US2-S1", "the scenario is demonstrated", passed=True),
            outcome=JudgeOutcome.PASS,
        )
    )

    assert result.verdict is OverallVerdict.PASS
    assert result.gate_contradictions == ()


def test_a_judge_that_never_ran_is_unchanged() -> None:
    """US2-S4. `None` still means the judge never ran, and still passes."""
    result = composed(None)

    assert result.verdict is OverallVerdict.PASS
    assert result.gate_contradictions == ()


# --- US2-S5: the check is for contradiction, not for mentions -----------------


def test_a_finding_naming_a_gate_that_genuinely_failed_is_honoured() -> None:
    """US2-S5. A gate that really failed is not contradicted by saying so."""
    measured = [gate("lint"), gate("test", GateStatus.FAIL)]

    result = composed(verdict(finding("US2-S1", CONTRADICTION)), measured)

    assert result.gate_contradictions == (), (
        "the judge agreed with the recorded result; there is no contradiction "
        "to record"
    )
    assert result.verdict is OverallVerdict.FAIL


@pytest.mark.parametrize(
    "reasoning",
    [
        "the test gate passes, but the diff never adds the helper it exercises",
        "the test gate is green and the scenario is still not demonstrated",
        "the test gate would not fail; the diff simply does not show the artifact",
    ],
    ids=["passes-but", "green-and-still", "would-not-fail"],
)
def test_mentioning_a_passing_gate_is_not_contradicting_it(reasoning: str) -> None:
    """US2-S5. Naming a gate is not asserting it would fail.

    Each of these names the `test` gate in the same sentence as an objection,
    and none of them claims the gate would fail — the last one claims the
    opposite. The check keys on the assertion, not on the co-occurrence.
    """
    result = composed(verdict(finding("US2-S1", reasoning)))

    assert result.gate_contradictions == ()
    assert result.verdict is OverallVerdict.FAIL


# --- trap 5: names are matched on boundaries ----------------------------------


def test_one_gate_name_is_never_found_inside_another() -> None:
    """FR-006, trap 5. Exact or word-boundary, never a bare substring.

    `test` and `typecheck` are the pair the plan names; `test-fixtures` and
    `smoketest` are the pair that would actually bite, because a naive `\\b`
    anchor matches `test` inside `test-fixtures` — a hyphen is a word boundary.
    """
    measured = [gate("test"), gate("typecheck")]

    found = detect_gate_contradictions(
        verdict(finding("US2-S1", "The typecheck gate would fail on this diff.")),
        measured,
    )

    assert [c.gate for c in found] == ["typecheck"], (
        "a gate name matched inside another gate's name; this repository has "
        "been bitten by an unanchored match before (factory/cli/doctor.py:58)"
    )


@pytest.mark.parametrize(
    "reasoning",
    [
        "The test-fixtures gate would fail on this diff.",
        "The smoketest gate would fail on this diff.",
        "The pytest gate would fail on this diff.",
    ],
    ids=["hyphen-suffix", "prefixed", "prefixed-tool-name"],
)
def test_a_gate_the_repository_never_declared_is_not_a_contradiction(
    reasoning: str,
) -> None:
    """FR-006, trap 5. Names come from the manifest, not from the prose.

    None of these names the gate `test`: a repository that declared `test` and
    a judge talking about `test-fixtures` disagree about something the factory
    never measured, and a verdict about an unmeasured thing is the judge's
    ordinary business rather than a contradiction.
    """
    result = composed(verdict(finding("US2-S1", reasoning)))

    assert result.gate_contradictions == ()
    assert result.verdict is OverallVerdict.FAIL


# --- trap 6: neutralising one finding is not passing the attempt --------------


def test_a_second_unrelated_failing_finding_still_fails_the_node() -> None:
    """FR-006, trap 6. One finding is neutralised, not the verdict.

    This is the difference between "the node is not charged for the judge's
    fault" and "a contradiction is a free pass". The contradiction is still
    recorded — it happened, and the operator reading this row needs to see both
    facts.
    """
    result = composed(
        verdict(
            finding("US2-S1", CONTRADICTION),
            finding("US2-S2", "the diff never adds the retry the scenario names"),
        )
    )

    assert result.verdict is OverallVerdict.FAIL, (
        "neutralising one finding passed an attempt that had a real objection "
        "standing against it"
    )
    assert [c.scenario for c in result.gate_contradictions] == ["US2-S1"]


def test_the_gates_and_the_output_check_still_stand() -> None:
    """FR-006, trap 6. A contradiction neutralises a finding and nothing else."""
    on_a_failing_gate = composed(
        verdict(finding("US2-S1", "The lint gate would fail on this diff.")),
        [gate("lint"), gate("test", GateStatus.FAIL)],
    )
    assert on_a_failing_gate.verdict is OverallVerdict.FAIL

    empty_diff = composed(
        verdict(finding("US2-S1", CONTRADICTION)),
        GREEN,
        OutputCheck(
            write_scope="worktree",
            has_diff=False,
            expected_artifacts=[],
            artifacts_present=None,
            passed=False,
        ),
    )
    assert empty_diff.verdict is OverallVerdict.FAIL
    assert empty_diff.gate_contradictions != (), (
        "the contradiction still happened; the output check is what failed"
    )
