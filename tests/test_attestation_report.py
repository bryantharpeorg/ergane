"""US2-S3/S4: objection resolution stays honest."""

from dataclasses import replace
import pytest

from factory.attestation import assemble_report
from factory.attestation.models import AttemptGitEvidence, GitFileChange, JudgeDelivery, JudgeEvaluationRecord as Record
from factory.attestation.usage import UsageObservation as Observation
from factory.usage.models import AggregatedUsage
from factory.verify.models import GateResult as Gate, GateStatus

FP = "1" * 64

def evaluation(
    evaluation_id: str, *, status: str = "valid", fingerprint: str = FP,
    revision: str = "rev-1", results: tuple[tuple[str, bool, str], ...] = (("US2-S1", True, "pass"),),
) -> Record:
    return Record(evaluation_id, "job-1", 1, "inv-1", "alias", fingerprint, revision, status, "model", "gateway", "litellm-chat-completions", results, "feedback")


def test_same_criterion_later_evaluation_is_verified_fixed() -> None:
    report = assemble_report(
        evaluations=[
            evaluation("objection", status="contradiction", results=(("US2-S1", False, "gate contradiction"),)),
            replace(evaluation("later", revision="rev-2"), scoring_call_ordinal=2),
        ]
    )
    resolution, objection = report.resolutions[0], report.objections[0]
    assert (
        resolution.status, resolution.objection_id, resolution.criterion, resolution.later_id,
        resolution.later_revision, objection.objection_id, objection.feedback, report.fully_fixed,
    ) == ("verified-fixed", "objection", "US2-S1", "later", "rev-2", "objection", "gate contradiction", True)


@pytest.mark.parametrize(("fingerprint", "status", "ordinal", "revision"), [("2" * 64, "valid", 2, "rev-2"), (FP, "parse_error", 2, "rev-2"), (FP, "valid", 0, "rev-2"), (FP, "valid", 2, "rev-1")])
def test_changed_or_earlier_evidence_is_not_a_fix(fingerprint: str, status: str, ordinal: int, revision: str) -> None:
    later = replace(evaluation("later", fingerprint=fingerprint, status=status, revision=revision), scoring_call_ordinal=ordinal)
    report = assemble_report(evaluations=[evaluation("objection", results=(("US2-S1", False, "no"),)), later])
    assert (report.resolutions[0].status, report.fully_fixed) == ("unverified", False)


@pytest.mark.parametrize(("state", "expected"), [("not_run", "not-run"), ("unavailable", "unavailable"), ("skipped", "skipped")])
def test_absent_judges_are_not_fixes(state: str, expected: str) -> None:
    report = assemble_report(judge_status=state, objections=(("objection", "US2-S1", "objection"),))
    assert (report.judge_status, report.resolutions[0].status, report.fully_fixed) == (state, expected, False)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"evaluations": (evaluation("narrative", results=()),)}, "unverified"),
        ({"dispositions": (("d1", "o", "US2-S1", "accepted"),)}, "explicitly-dispositioned"),
        (
            {
                    "objections": (("o", "US2-S1", "gate"),),
                    "contradictions": (("US2-S1", "test", "PASS", "gate"),),
                "ci_status": "green",
            },
            "unresolved",
        ),
        ({"objections": (("o", "US2-S1", "still failing"),), "composed_verdict": "PASS"}, "unverified"),
    ],
)
def test_non_verified_states_are_not_fully_fixed(kwargs: dict, expected: str) -> None:
    report = assemble_report(**kwargs)
    assert (report.resolutions[0].status, report.fully_fixed) == (expected, False)
    if expected == "explicitly-dispositioned":
        assert report.resolutions[0].disposition_id == "d1"
    if expected == "unresolved":
        assert report.ci_status == "green"
    if "composed_verdict" in kwargs:
        assert report.composed_verdict == "PASS"


def test_report_retains_raw_judge_and_git_evidence() -> None:
    record = evaluation("objection", status="contradiction", results=(("US2-S1", False, "gate"),))
    gate = Gate("test", "pytest", GateStatus.PASS, 0, 1.0, "bounded tail", output_truncated=True)
    files = (GitFileChange("new.txt", "A"), GitFileChange("binary.bin", "A", binary=True))
    git_evidence = AttemptGitEvidence("ev-1", "epic", "node", 1, "d", "a" * 40, "b" * 40, "c" * 40, files, files, "test: bounded", True, ("pytest",), "absent")
    report = assemble_report(evaluations=[record], gates=(gate,), git_evidence=git_evidence)
    assert (report.evaluations, report.gates, report.git_evidence) == ((record,), (gate,), git_evidence)


def test_judge_usage_keeps_the_job_total_and_attribute_real_calls_only() -> None:
    def record(evaluation_id: str, response_id: str | None) -> Record:
        delivery = (JudgeDelivery(1, "delivered", response_id=response_id),) if response_id else ()
        return replace(evaluation(evaluation_id), deliveries=delivery)

    evaluations = (record("call-1", "request-a"), record("call-2", None))
    observation = Observation("job-1", "gateway", "request-a", "served-a", "judge-model", 6, 1, request_count=1)
    job_total = AggregatedUsage(10, 2, 0, 0, 2, 0.02)
    report = assemble_report(evaluations=evaluations, job_usage=job_total, observations=(observation,))
    assert report.usage is not None and report.usage.job_total == job_total
    first, second = report.usage.per_call
    assert first.observation is observation
    assert (second.observation, second.status) == (None, "unknown")
