"""US2-S3/S4: report assembly resolves objections honestly."""

from __future__ import annotations

import pytest

from factory.attestation import assemble_report
from factory.attestation.models import JudgeEvaluationRecord


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
