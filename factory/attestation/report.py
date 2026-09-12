"""Pure report assembly for persisted audit evidence."""

from typing import Any, NamedTuple, Sequence

from factory.attestation.models import AttemptGitEvidence, JudgeEvaluationRecord
from factory.attestation.usage import UsageObservation
from factory.verify.models import GateResult


class Objection(NamedTuple):
    evaluation_id: str
    criterion: str | None
    feedback: str


class ObjectionResolution(NamedTuple):
    objection_evaluation_id: str
    criterion: str | None
    status: str
    later_evaluation_id: str | None = None
    later_revision: str | None = None
    disposition_id: str | None = None


class JudgeUsageAttribution(NamedTuple):
    evaluation_id: str
    scoring_call_ordinal: int
    request_id: str | None = None
    observation: UsageObservation | None = None
    status: str = "unknown"


class JudgeUsageReport(NamedTuple):
    job_total: Any
    per_call: tuple[JudgeUsageAttribution, ...]


class AttestationReport(NamedTuple):
    judge_status: str
    evaluations: tuple[JudgeEvaluationRecord, ...]
    composed_verdict: str | None
    objections: tuple[Objection, ...]
    resolutions: tuple[ObjectionResolution, ...]
    contradictions: tuple[tuple[str, str, str, str], ...]
    ci_status: str
    fully_fixed: bool
    gates: tuple[GateResult, ...]
    git_evidence: AttemptGitEvidence | None
    usage: JudgeUsageReport | None = None


def _usage_report(
    evaluations: Sequence[JudgeEvaluationRecord], job_usage: Any | None,
    observations: Sequence[UsageObservation],
) -> JudgeUsageReport | None:
    if job_usage is None:
        return None
    by_request_id = {observation.source_id: observation for observation in observations}
    attributed = []
    for evaluation in evaluations:
        response_ids = {
            delivery.response_id for delivery in evaluation.deliveries
            if delivery.status == "delivered" and delivery.response_id is not None
        }
        observation = by_request_id.get(next(iter(response_ids))) if len(response_ids) == 1 else None
        attributed.append(
            JudgeUsageAttribution(
                evaluation.evaluation_id, evaluation.scoring_call_ordinal,
                observation.source_id if observation else None, observation,
                "attributed" if observation else "unknown",
            )
        )
    return JudgeUsageReport(job_usage, tuple(attributed))


def _objections(
    evaluations: Sequence[JudgeEvaluationRecord],
    explicit: Sequence[tuple[str, str, str] | Objection],
    dispositions: Sequence[tuple[str, str, str, str]] = (),
) -> tuple[Objection, ...]:
    records = [
        Objection(evaluation.evaluation_id, scenario, reasoning)
        for evaluation in evaluations for scenario, passed, reasoning in evaluation.scenario_results
        if not passed
    ]
    for value in explicit:
        records.append(value if isinstance(value, Objection) else Objection(*value))
    seen = {item.evaluation_id for item in records}
    for disposition in dispositions:
        if disposition[1] not in seen:
            records.append(Objection(disposition[1], disposition[2], "")); seen.add(disposition[1])
    return tuple(records)


def _resolution(
    objection: Objection,
    evaluations: Sequence[JudgeEvaluationRecord],
    dispositions: Sequence[tuple[str, str, str, str]],
    judge_status: str,
    contradictions: Sequence[tuple[str, str, str, str]],
) -> ObjectionResolution:
    def result(status: str, later: JudgeEvaluationRecord | None = None, disposition_id: str | None = None):
        return ObjectionResolution(
            objection.evaluation_id, objection.criterion, status,
            later_evaluation_id=later.evaluation_id if later else None,
            later_revision=later.tested_revision if later else None,
            disposition_id=disposition_id,
        )

    disposition_id = next((item[0] for item in dispositions if item[1] == objection.evaluation_id), None)
    if disposition_id is not None:
        return result("explicitly-dispositioned", disposition_id=disposition_id)
    if contradictions:
        return result("unresolved")
    if judge_status in {"not_run", "unavailable"}:
        return result(judge_status.replace("_", "-"))
    if objection.criterion is None or objection.evaluation_id == "":
        return result("unverified")
    original = next((item for item in evaluations if item.evaluation_id == objection.evaluation_id), None)
    later = next(
        (item for item in reversed(evaluations)
         if item.evaluation_id != objection.evaluation_id
         and any(scenario == objection.criterion and passed for scenario, passed, _ in item.scenario_results)),
        None,
    )
    if later is None or later.status != "valid" or original is None or later.criteria_fingerprint != original.criteria_fingerprint or later.criteria_fingerprint == "":
        return result("unverified")
    return result("verified-fixed", later)


def assemble_report(
    *,
    evaluations: Sequence[JudgeEvaluationRecord] = (),
    judge_status: str | None = None,
    composed_verdict: str | None = None,
    objections: Sequence[tuple[str, str, str] | Objection] = (),
    dispositions: Sequence[tuple[str, str, str, str]] = (),
    contradictions: Sequence[tuple[str, str, str, str]] = (),
    ci_status: str = "unknown",
    gates: Sequence[GateResult] = (),
    git_evidence: AttemptGitEvidence | None = None,
    job_usage: Any | None = None,
    usage_observations: Sequence[UsageObservation] = (),
) -> AttestationReport:
    """Assemble explicit evidence without live reads or verdict changes."""
    objection_records = _objections(evaluations, objections, dispositions)
    contradiction_values = tuple(tuple(item) for item in contradictions)
    resolutions = [
        _resolution(objection, evaluations, dispositions, judge_status or "valid", contradiction_values)
        for objection in objection_records
    ]
    resolutions.extend(
        ObjectionResolution(evaluation.evaluation_id, None, "unverified")
        for evaluation in evaluations
        if evaluation.status == "valid" and not evaluation.scenario_results and evaluation.feedback
    )
    fully_fixed = (
        bool(resolutions)
        and all(item.status == "verified-fixed" for item in resolutions)
        and not contradiction_values
        and not dispositions
        and judge_status in (None, "valid")
    )
    return AttestationReport(
        judge_status=judge_status or ("valid" if evaluations else "not_run"), evaluations=tuple(evaluations),
        composed_verdict=composed_verdict, objections=objection_records, resolutions=tuple(resolutions),
        contradictions=contradiction_values, ci_status=ci_status, fully_fixed=fully_fixed,
        gates=tuple(gates), git_evidence=git_evidence,
        usage=_usage_report(evaluations, job_usage, usage_observations),
    )
