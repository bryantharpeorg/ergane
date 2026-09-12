"""US2-S3/S4: report assembly resolves objections honestly."""

from dataclasses import replace

import pytest

from factory.attestation import assemble_report
from factory.attestation.models import (
    AttemptGitEvidence, GitFileChange, JudgeDelivery, JudgeEvaluationRecord,
)
from factory.attestation.usage import UsageObservation
from factory.usage.models import AggregatedUsage
from factory.verify.models import GateResult, GateStatus


def evaluation(
    evaluation_id: str, *, status: str = "valid", fingerprint: str = "1" * 64,
    revision: str = "rev-1", results: tuple[tuple[str, bool, str], ...] = (("US2-S1", True, "pass"),),
) -> JudgeEvaluationRecord:
    return JudgeEvaluationRecord(
        evaluation_id, "job-1", 1, "inv-1", "judge-alias", fingerprint, revision,
        status, "judge-model", scenario_results=results, feedback="bounded feedback",
    )


def test_a_same_criterion_later_evaluation_becomes_verified_fixed() -> None:
    report = assemble_report(
        evaluations=[
            evaluation(
                "objection", status="contradiction",
                results=(("US2-S1", False, "the test gate would fail"),),
            ),
            evaluation("later", revision="rev-2", results=(("US2-S1", True, "PASS"),)),
        ]
    )
    resolution, objection = report.resolutions[0], report.objections[0]
    assert (
        resolution.status, resolution.objection_evaluation_id, resolution.criterion,
        resolution.later_evaluation_id, resolution.later_revision,
        objection.evaluation_id, objection.feedback, report.fully_fixed,
    ) == (
        "verified-fixed", "objection", "US2-S1", "later", "rev-2",
        "objection", "the test gate would fail", True,
    )


@pytest.mark.parametrize(
    ("later_fingerprint", "later_status"),
    [("2" * 64, "valid"), ("1" * 64, "parse_error")],
)
def test_changed_or_unverified_criteria_do_not_become_verified_fixed(later_fingerprint: str, later_status: str) -> None:
    report = assemble_report(
        evaluations=[
            evaluation("objection", results=(("US2-S1", False, "no"),)),
            evaluation("later", fingerprint=later_fingerprint, status=later_status, results=(("US2-S1", True, "yes"),)),
        ]
    )
    assert (report.resolutions[0].status, report.fully_fixed) == ("unverified", False)


@pytest.mark.parametrize(
    ("status", "judge_state", "expected"),
    [("no-judge", "not_run", "not-run"), ("unavailable", "unavailable", "unavailable")],
)
def test_absent_judges_are_not_fixes(status: str, judge_state: str, expected: str) -> None:
    report = assemble_report(judge_status=judge_state, objections=(("objection", "US2-S1", status),))
    assert (report.judge_status, report.resolutions[0].status, report.fully_fixed) == (
        judge_state, expected, False,
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"evaluations": (evaluation("narrative", results=()),)}, "unverified"),
        ({"dispositions": (("disposition-1", "objection", "US2-S1", "operator accepted risk"),)}, "explicitly-dispositioned"),
        (
            {
                "objections": (("objection", "US2-S1", "the test gate would fail"),),
                "contradictions": (("US2-S1", "test", "PASS", "the test gate would fail"),),
                "ci_status": "green",
            },
            "unresolved",
        ),
        (
            {"objections": (("objection", "US2-S1", "still failing"),), "composed_verdict": "PASS"},
            "unverified",
        ),
    ],
)
def test_non_verified_states_are_not_fully_fixed(kwargs: dict, expected: str) -> None:
    report = assemble_report(**kwargs)
    assert report.resolutions[0].status == expected
    if expected == "explicitly-dispositioned":
        assert report.resolutions[0].disposition_id == "disposition-1"
    if expected == "unresolved":
        assert report.ci_status == "green"
    if expected == "unverified" and "composed_verdict" in kwargs:
        assert report.composed_verdict == "PASS"
    assert report.fully_fixed is False


def test_the_report_retains_raw_judge_and_exact_git_evidence() -> None:
    evaluation_record = evaluation(
        "objection", status="contradiction",
        results=(("US2-S1", False, "the test gate would fail"),),
    )
    gate = GateResult("test", "pytest", GateStatus.PASS, 0, 1.0, "bounded tail", output_truncated=True)
    git_evidence = AttemptGitEvidence(
        "evidence-1", "epic", "node", 1, "dispatch", "a" * 40, "b" * 40, "c" * 40,
        (GitFileChange("new.txt", "A"), GitFileChange("binary.bin", "A", binary=True)),
        "test: bounded tail", True, ("pytest",), "absent",
    )
    report = assemble_report(evaluations=[evaluation_record], gates=(gate,), git_evidence=git_evidence)
    assert (report.evaluations, report.gates, report.git_evidence) == ((evaluation_record,), (gate,), git_evidence)


def test_judge_usage_keeps_the_job_total_and_attribute_real_calls_only() -> None:
    def evaluation_record(evaluation_id: str, response_id: str | None) -> JudgeEvaluationRecord:
        deliveries = ((JudgeDelivery(1, "delivered", response_id=response_id),) if response_id is not None else ())
        return replace(evaluation(evaluation_id), deliveries=deliveries)

    evaluations = (evaluation_record("call-1", "request-a"), evaluation_record("call-2", None))
    observations = (
        UsageObservation(
            invocation_id="job-1", source="gateway", source_id="request-a",
            serving_model="served-a", model_alias="judge-model", prompt_tokens=6,
            completion_tokens=1, request_count=1,
        ),
    )
    job_total = AggregatedUsage(
        prompt_tokens=10, completion_tokens=2, cache_read_tokens=0,
        cache_write_tokens=0, request_count=2, spend_usd=0.02,
    )
    report = assemble_report(evaluations=evaluations, job_usage=job_total, usage_observations=observations)
    assert report.usage is not None
    assert report.usage.job_total == job_total
    first, second = report.usage.per_call
    assert (first.evaluation_id, first.request_id, first.observation.prompt_tokens,
            first.observation.completion_tokens, first.observation.request_count) == (
        "call-1", "request-a", 6, 1, 1,
    )
    assert second.observation is None
