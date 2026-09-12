"""US2-S3/S4: report assembly resolves objections honestly."""

from __future__ import annotations

import pytest
from dataclasses import replace

from factory.attestation import assemble_report
from factory.attestation.models import (
    AttemptGitEvidence,
    GitFileChange,
    JudgeDelivery,
    JudgeEvaluationRecord,
)
from factory.attestation.usage import UsageObservation
from factory.usage.models import AggregatedUsage
from factory.verify.models import GateResult, GateStatus


def evaluation(
    evaluation_id: str,
    *,
    status: str = "valid",
    fingerprint: str = "1" * 64,
    revision: str = "rev-1",
    results: tuple[tuple[str, bool, str], ...] = (("US2-S1", True, "pass"),),
) -> JudgeEvaluationRecord:
    return JudgeEvaluationRecord(
        evaluation_id=evaluation_id,
        scoring_job_id="job-1",
        scoring_call_ordinal=1,
        invocation_id="inv-1",
        key_alias="judge-alias",
        criteria_fingerprint=fingerprint,
        tested_revision=revision,
        status=status,
        model_alias="judge-model",
        scenario_results=results,
        feedback="bounded feedback",
    )


def test_a_same_criterion_later_evaluation_becomes_verified_fixed() -> None:
    report = assemble_report(
        evaluations=[
            evaluation(
                "objection",
                status="contradiction",
                results=(("US2-S1", False, "the test gate would fail"),),
            ),
            evaluation(
                "later",
                revision="rev-2",
                results=(("US2-S1", True, "recorded PASS"),),
            ),
        ]
    )

    resolution = report.resolutions[0]
    assert resolution.status == "verified-fixed"
    assert resolution.objection_evaluation_id == "objection"
    assert resolution.criterion == "US2-S1"
    assert resolution.later_evaluation_id == "later"
    assert resolution.later_revision == "rev-2"
    objection = report.objections[0]
    assert objection.evaluation_id == "objection"
    assert objection.feedback == "the test gate would fail"
    assert report.fully_fixed is True


@pytest.mark.parametrize(
    ("later_fingerprint", "later_status", "expected"),
    [
        ("2" * 64, "valid", "unverified"),
        ("1" * 64, "parse_error", "unverified"),
    ],
)
def test_changed_or_unverified_criteria_do_not_become_verified_fixed(
    later_fingerprint: str, later_status: str, expected: str
) -> None:
    report = assemble_report(
        evaluations=[
            evaluation("objection", results=(("US2-S1", False, "no"),)),
            evaluation(
                "later",
                fingerprint=later_fingerprint,
                status=later_status,
                results=(("US2-S1", True, "yes"),),
            ),
        ]
    )

    assert report.resolutions[0].status == expected
    assert report.fully_fixed is False


@pytest.mark.parametrize(
    ("status", "findings", "judge_state", "expected"),
    [
        ("no-judge", (), "not_run", "not-run"),
        ("unavailable", (), "unavailable", "unavailable"),
    ],
)
def test_absent_judges_are_not_fixes(status: str, findings: tuple, judge_state: str, expected: str) -> None:
    report = assemble_report(
        evaluations=[],
        judge_status=judge_state,
        objections=(("objection", "US2-S1", status),),
    )

    assert report.judge_status == judge_state
    assert report.resolutions[0].status == expected
    assert report.fully_fixed is False


def test_narrative_feedback_without_a_scenario_is_not_verified_fixed() -> None:
    report = assemble_report(
        evaluations=[
            evaluation(
                "narrative",
                status="valid",
                results=(),
            )
        ]
    )

    assert report.resolutions[0].status == "unverified"
    assert report.fully_fixed is False


def test_an_explicit_disposition_is_labeled_separately() -> None:
    report = assemble_report(
        evaluations=[],
        dispositions=(
            ("disposition-1", "objection", "US2-S1", "operator accepted risk"),
        ),
    )

    resolution = report.resolutions[0]
    assert resolution.status == "explicitly-dispositioned"
    assert resolution.disposition_id == "disposition-1"
    assert report.fully_fixed is False


def test_gate_contradictions_and_green_ci_are_not_full_fixes() -> None:
    report = assemble_report(
        evaluations=[],
        objections=(("objection", "US2-S1", "the test gate would fail"),),
        contradictions=(("US2-S1", "test", "PASS", "the test gate would fail"),),
        ci_status="green",
    )

    assert report.contradictions == (("US2-S1", "test", "PASS", "the test gate would fail"),)
    assert report.resolutions[0].status == "unresolved"
    assert report.ci_status == "green"
    assert report.fully_fixed is False


def test_a_composed_pass_does_not_label_an_objection_fixed() -> None:
    report = assemble_report(
        objections=(("objection", "US2-S1", "still failing"),),
        composed_verdict="PASS",
    )

    assert report.composed_verdict == "PASS"
    assert report.resolutions[0].status == "unverified"
    assert report.fully_fixed is False


def test_the_report_retains_raw_judge_and_exact_git_evidence() -> None:
    evaluation_record = evaluation(
        "objection",
        status="contradiction",
        results=(("US2-S1", False, "the test gate would fail"),),
    )
    gate = GateResult(
        name="test",
        command="pytest",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=1.0,
        output_tail="bounded tail",
        output_truncated=True,
    )
    git_evidence = AttemptGitEvidence(
        evidence_id="evidence-1",
        epic_id="epic",
        node_id="node",
        attempt=1,
        dispatch="dispatch",
        base_commit="a" * 40,
        attempted_commit="b" * 40,
        verified_commit="c" * 40,
        files=(
            GitFileChange(path="new.txt", status="A"),
            GitFileChange(path="binary.bin", status="A", binary=True),
        ),
        log_tail="test: bounded tail",
        log_truncated=True,
        tests_executed=("pytest",),
        coverage_status="absent",
    )

    report = assemble_report(
        evaluations=[evaluation_record],
        gates=(gate,),
        git_evidence=git_evidence,
    )

    assert report.evaluations == (evaluation_record,)
    assert report.gates == (gate,)
    assert report.git_evidence == git_evidence
    assert report.git_evidence.files[1].binary is True
    assert report.git_evidence.base_commit == "a" * 40
    assert report.git_evidence.attempted_commit == "b" * 40
    assert report.git_evidence.verified_commit == "c" * 40
    assert report.git_evidence.log_truncated is True
    assert report.git_evidence.coverage_status == "absent"


def test_judge_usage_keeps_the_job_total_and_attribute_real_calls_only() -> None:
    def evaluation_record(
        evaluation_id: str, response_id: str | None
    ) -> JudgeEvaluationRecord:
        deliveries: tuple[JudgeDelivery, ...] = ()
        if response_id is not None:
            deliveries = (
                JudgeDelivery(
                    delivery_ordinal=1,
                    status="delivered",
                    response_id=response_id,
                ),
            )
        return replace(evaluation(evaluation_id), deliveries=deliveries)

    evaluations = (
        evaluation_record("call-1", "request-a"),
        evaluation_record("call-2", None),
    )
    observations = (
        UsageObservation(
            invocation_id="job-1",
            source="gateway",
            source_id="request-a",
            serving_model="served-a",
            model_alias="judge-model",
            prompt_tokens=6,
            completion_tokens=1,
            request_count=1,
        ),
    )
    job_total = AggregatedUsage(
        prompt_tokens=10,
        completion_tokens=2,
        cache_read_tokens=0,
        cache_write_tokens=0,
        request_count=2,
        spend_usd=0.02,
    )

    report = assemble_report(
        evaluations=evaluations,
        job_usage=job_total,
        usage_observations=observations,
    )

    assert report.usage is not None
    assert report.usage.job_total == job_total
    first = report.usage.per_call[0]
    assert first.evaluation_id == "call-1"
    assert first.request_id == "request-a"
    assert (first.prompt_tokens, first.completion_tokens, first.request_count) == (6, 1, 1)
    second = report.usage.per_call[1]
    assert second.evaluation_id == "call-2"
    assert second.prompt_tokens is None
    assert second.completion_tokens is None
    assert second.request_count is None
