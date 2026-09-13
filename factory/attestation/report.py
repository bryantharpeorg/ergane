from typing import Any, NamedTuple, Sequence

from factory.attestation.models import AttemptGitEvidence, JudgeEvaluationRecord as Record
from factory.attestation.usage import UsageObservation as Observation
from factory.verify.models import GateResult as Gate

class Objection(NamedTuple):
    objection_id: str
    criterion: str | None
    feedback: str


class ObjectionResolution(NamedTuple):
    objection_id: str
    criterion: str | None
    status: str
    later_id: str | None = None
    later_revision: str | None = None
    disposition_id: str | None = None

class UsageCall(NamedTuple):
    evaluation_id: str
    call_ordinal: int
    observation: Observation | None = None
    status: str = "unknown"

class JudgeUsageReport(NamedTuple):
    job_total: Any
    per_call: tuple[UsageCall, ...]


class AttestationReport(NamedTuple):
    judge_status: str
    evaluations: tuple[Record, ...]
    composed_verdict: str | None
    objections: tuple[Objection, ...]
    resolutions: tuple[ObjectionResolution, ...]
    contradictions: tuple[tuple[str, str, str, str], ...]
    ci_status: str
    fully_fixed: bool
    gates: tuple[Gate, ...]
    git_evidence: AttemptGitEvidence | None
    usage: JudgeUsageReport | None = None


ObjectionInput = tuple[str, str, str] | Objection
Disposition = tuple[str, str, str, str]
Contradiction = tuple[str, ...]


def _usage_report(evaluations: Sequence[Record], job_usage: Any | None, observations: Sequence[Observation]) -> JudgeUsageReport | None:
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
        attributed.append(UsageCall(evaluation.evaluation_id, evaluation.scoring_call_ordinal, observation, "attributed" if observation else "unknown"))
    return JudgeUsageReport(job_usage, tuple(attributed))


def _objections(evaluations: Sequence[Record], explicit: Sequence[ObjectionInput], dispositions: Sequence[Disposition] = ()) -> tuple[Objection, ...]:
    records = [Objection(evaluation.evaluation_id, scenario, reasoning) for evaluation in evaluations for scenario, passed, reasoning in evaluation.scenario_results if not passed]
    records.extend(value if isinstance(value, Objection) else Objection(*value) for value in explicit)
    seen = {item.objection_id for item in records}
    for disposition in dispositions:
        if disposition[1] not in seen:
            records.append(Objection(disposition[1], disposition[2], "")); seen.add(disposition[1])
    return tuple(records)


def _resolution(
    objection: Objection, evaluations: Sequence[Record], dispositions: Sequence[Disposition],
    judge_status: str, contradictions: Sequence[Contradiction],
) -> ObjectionResolution:
    def result(status: str, later: Record | None = None, disposition_id: str | None = None):
        return ObjectionResolution(objection.objection_id, objection.criterion, status, later.evaluation_id if later else None, later.tested_revision if later else None, disposition_id)

    disposition_id = next((item[0] for item in dispositions if item[1] == objection.objection_id), None)
    if disposition_id is not None:
        return result("explicitly-dispositioned", disposition_id=disposition_id)
    if contradictions:
        return result("unresolved")
    if judge_status in {"not_run", "unavailable", "skipped"}:
        return result(judge_status.replace("_", "-"))
    if objection.criterion is None or objection.objection_id == "":
        return result("unverified")
    original = next((item for item in evaluations if item.evaluation_id == objection.objection_id), None)
    later = next((item for item in reversed(evaluations) if original is not None
        and item.evaluation_id != objection.objection_id
        and item.scoring_call_ordinal > original.scoring_call_ordinal
        and item.tested_revision != original.tested_revision and any(
        scenario == objection.criterion and passed for scenario, passed, _ in item.scenario_results
    )), None)
    if later is None or later.status != "valid" or original is None or later.criteria_fingerprint != original.criteria_fingerprint or later.criteria_fingerprint == "":
        return result("unverified")
    return result("verified-fixed", later)


def assemble_report(
    *,
    evaluations: Sequence[Record] = (), judge_status: str | None = None,
    composed_verdict: str | None = None, objections: Sequence[ObjectionInput] = (),
    dispositions: Sequence[Disposition] = (), contradictions: Sequence[Contradiction] = (),
    ci_status: str = "unknown", gates: Sequence[Gate] = (),
    git_evidence: AttemptGitEvidence | None = None, job_usage: Any | None = None,
    observations: Sequence[Observation] = (),
) -> AttestationReport:
    """Assemble explicit evidence without live reads or verdict changes."""
    objection_records = _objections(evaluations, objections, dispositions)
    contradiction_values = tuple(tuple(item) for item in contradictions)
    resolutions = [_resolution(item, evaluations, dispositions, judge_status or "valid", contradiction_values) for item in objection_records]
    resolutions.extend(ObjectionResolution(evaluation.evaluation_id, None, "unverified") for evaluation in evaluations if evaluation.status == "valid" and not evaluation.scenario_results and evaluation.feedback)
    fully_fixed = bool(resolutions) and all(item.status == "verified-fixed" for item in resolutions) and not contradiction_values and not dispositions and judge_status in (None, "valid")
    return AttestationReport(
        judge_status=judge_status or ("valid" if evaluations else "not_run"), evaluations=tuple(evaluations),
        composed_verdict=composed_verdict, objections=objection_records, resolutions=tuple(resolutions),
        contradictions=contradiction_values, ci_status=ci_status, fully_fixed=fully_fixed,
        gates=tuple(gates), git_evidence=git_evidence,
        usage=_usage_report(evaluations, job_usage, observations),
    )
