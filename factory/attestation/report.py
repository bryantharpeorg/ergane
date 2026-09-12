"""Pure report assembly for persisted audit evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Sequence

from factory.attestation.models import AttemptGitEvidence, JudgeEvaluationRecord
from factory.attestation.usage import UsageObservation
from factory.verify.models import GateResult

if TYPE_CHECKING:
    from factory.usage.models import AggregatedUsage


@dataclass(frozen=True)
class Objection:
    """One readable objection retained beside any later resolution."""

    evaluation_id: str
    criterion: str | None
    feedback: str
    status: str = "valid"


@dataclass(frozen=True)
class ObjectionResolution:
    """The exact evidence that later resolved one objection, if any."""

    objection_evaluation_id: str
    criterion: str | None
    status: str
    later_evaluation_id: str | None = None
    later_revision: str | None = None
    disposition_id: str | None = None


@dataclass(frozen=True)
class JudgeUsageAttribution:
    """Per-call metrics only when their authoritative request identity matches."""

    evaluation_id: str
    scoring_call_ordinal: int
    request_id: str | None = None
    serving_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    request_count: int | None = None
    spend_usd: float | None = None
    status: str = "unknown"


@dataclass(frozen=True)
class JudgeUsageReport:
    """The scoring job's authoritative total beside explicit per-call detail."""

    job_total: "AggregatedUsage"
    per_call: tuple[JudgeUsageAttribution, ...]


@dataclass(frozen=True)
class AttestationReport:
    """Bounded report data without live I/O or verdict composition."""

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
    evaluations: Sequence[JudgeEvaluationRecord],
    job_usage: "AggregatedUsage | None",
    observations: Sequence[UsageObservation],
) -> JudgeUsageReport | None:
    if job_usage is None:
        return None

    per_call: list[JudgeUsageAttribution] = []
    for evaluation in evaluations:
        response_ids = {
            delivery.response_id
            for delivery in evaluation.deliveries
            if delivery.status == "delivered" and delivery.response_id is not None
        }
        matches: tuple[UsageObservation, ...] = ()
        if len(response_ids) == 1:
            request_id = next(iter(response_ids))
            matches = tuple(
                observation for observation in observations if observation.source_id == request_id
            )
        if len(response_ids) == 1 and len(matches) == 1:
            observation = matches[0]
            request_id = next(iter(response_ids))
            attribution = JudgeUsageAttribution(
                evaluation_id=evaluation.evaluation_id,
                scoring_call_ordinal=evaluation.scoring_call_ordinal,
                request_id=request_id,
                serving_model=observation.serving_model,
                prompt_tokens=observation.prompt_tokens,
                completion_tokens=observation.completion_tokens,
                cache_read_tokens=observation.cache_read_tokens,
                cache_write_tokens=observation.cache_write_tokens,
                request_count=observation.request_count,
                spend_usd=observation.spend_usd,
                status="attributed",
            )
        else:
            attribution = JudgeUsageAttribution(
                evaluation_id=evaluation.evaluation_id,
                scoring_call_ordinal=evaluation.scoring_call_ordinal,
            )
        per_call.append(attribution)
    return JudgeUsageReport(job_total=job_usage, per_call=tuple(per_call))


def _objections(
    evaluations: Sequence[JudgeEvaluationRecord],
    explicit: Iterable[tuple[str, str, str] | Objection],
    dispositions: Sequence[tuple[str, str, str, str]] = (),
) -> tuple[Objection, ...]:
    records = [
        Objection(
            evaluation_id=evaluation.evaluation_id,
            criterion=scenario,
            feedback=reasoning,
            status=evaluation.status,
        )
        for evaluation in evaluations
        for scenario, passed, reasoning in evaluation.scenario_results
        if not passed
    ]
    for value in explicit:
        if isinstance(value, Objection):
            records.append(value)
        else:
            records.append(
                Objection(
                    evaluation_id=value[0],
                    criterion=value[1],
                    feedback=value[2],
                )
            )
    seen = {item.evaluation_id for item in records}
    for disposition in dispositions:
        if disposition[1] not in seen:
            records.append(
                Objection(
                    evaluation_id=disposition[1],
                    criterion=disposition[2],
                    feedback="",
                )
            )
            seen.add(disposition[1])
    return tuple(records)


def _resolution(
    objection: Objection,
    evaluations: Sequence[JudgeEvaluationRecord],
    dispositions: Sequence[tuple[str, str, str, str]],
    judge_status: str,
    contradictions: Sequence[tuple[str, str, str, str]],
) -> ObjectionResolution:
    disposition_id = None
    for disposition in dispositions:
        if disposition[1] == objection.evaluation_id:
            disposition_id = disposition[0]
            break
    if disposition_id is not None:
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="explicitly-dispositioned",
            disposition_id=disposition_id,
        )
    if contradictions:
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="unresolved",
        )

    if judge_status == "not_run":
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="not-run",
        )
    if judge_status == "unavailable":
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="unavailable",
        )

    if objection.criterion is None or objection.evaluation_id == "":
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="unverified",
        )

    original = next(
        (item for item in evaluations if item.evaluation_id == objection.evaluation_id),
        None,
    )
    later = next(
        (
            item
            for item in reversed(evaluations)
            if item.evaluation_id != objection.evaluation_id
            and any(
                scenario == objection.criterion and passed
                for scenario, passed, _reason in item.scenario_results
            )
        ),
        None,
    )
    if (
        later is None
        or later.status != "valid"
        or original is None
        or later.criteria_fingerprint != original.criteria_fingerprint
        or later.criteria_fingerprint == ""
    ):
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="unverified",
        )
    if contradictions:
        return ObjectionResolution(
            objection_evaluation_id=objection.evaluation_id,
            criterion=objection.criterion,
            status="unresolved",
        )

    return ObjectionResolution(
        objection_evaluation_id=objection.evaluation_id,
        criterion=objection.criterion,
        status="verified-fixed",
        later_evaluation_id=later.evaluation_id,
        later_revision=later.tested_revision,
    )


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
    job_usage: AggregatedUsage | None = None,
    usage_observations: Sequence[UsageObservation] = (),
) -> AttestationReport:
    """Assemble explicit evidence without live reads or verdict changes."""
    objection_records = _objections(evaluations, objections, dispositions)
    contradiction_values = tuple(tuple(item) for item in contradictions)
    resolutions = tuple(
        _resolution(objection, evaluations, dispositions, judge_status or "valid", contradiction_values)
        for objection in objection_records
    )

    # A parsed evaluation with no scenario is a narrative response. It is
    # evidence of an answer, never evidence that any criterion was verified.
    narrative = tuple(
        evaluation
        for evaluation in evaluations
        if evaluation.status == "valid" and not evaluation.scenario_results and evaluation.feedback
    )
    narrative_resolutions = tuple(
        ObjectionResolution(
            objection_evaluation_id=evaluation.evaluation_id,
            criterion=None,
            status="unverified",
        )
        for evaluation in narrative
    )
    resolutions += narrative_resolutions
    disposition_ids = {item[0] for item in dispositions}
    fully_fixed = bool(resolutions) and all(
        resolution.status == "verified-fixed" for resolution in resolutions
    ) and not contradiction_values and not disposition_ids and judge_status in (None, "valid")
    return AttestationReport(
        judge_status=judge_status or ("valid" if evaluations else "not_run"),
        evaluations=tuple(evaluations),
        composed_verdict=composed_verdict,
        objections=objection_records,
        resolutions=resolutions,
        contradictions=contradiction_values,
        ci_status=ci_status,
        fully_fixed=fully_fixed,
        gates=tuple(gates),
        git_evidence=git_evidence,
        usage=_usage_report(evaluations, job_usage, usage_observations),
    )
