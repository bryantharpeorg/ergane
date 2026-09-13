"""US2-S1/S2: the scoring loop keeps every evaluation and one job total."""

from pathlib import Path
from typing import Any, Callable
import pytest

from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities, verify_activities
from factory.activities.usage_activities import ERGANE_LEDGER_PATH_ENV, IssueKeyInput, TeardownInput, issue_attempt_key, teardown_attempt
from factory.activities.verify_activities import RunJudgeInput
from factory.attestation import read_scoring_evaluations, read_usage_evidence
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import Termination
from factory.verify.judge import JudgeOutcome, run_judge
from factory.verify.models import CriteriaSet, GateResult, Requirement, RequirementKind, Scenario
from tests.conftest import FakeLiteLLM
from tests.judge_proxy import FakeJudgeProxy, verdict_json
from tests.test_usage_activities import issue_input


JOB = "us2:1:score"
INV = "run-167:us2:judge:score:1"
REV = "attempt-tree-1"
MODEL = "judge-model"
FP = "1" * 64
SCENARIOS = tuple(Scenario(f"US2-S{i}", [f"**Then** scenario {i} survives"], f"{i}. ...") for i in (1, 2))
CRITERIA = CriteriaSet(
    feature="167-audit-packet", spec_ref="167/spec.md",
    requirements=[Requirement("US2", RequirementKind.STORY, "Judge history", "P1", "Every evaluation survives.", list(SCENARIOS))],
    source_path="167/spec.md", source_sha256=FP, snapshotted_at="2026-09-12T00:00:00Z",
)


def judge_input(**overrides: Any) -> IssueKeyInput:
    return issue_input(
        persona="judge", epic_id="epic-167", node_id="us2", attempt=1,
        spec_ref=CRITERIA.spec_ref, models=[MODEL], target="bryantharpeorg/ergane",
        spec_revision=CRITERIA.source_path, spec_fingerprint=CRITERIA.source_sha256,
        epic_workflow_id="workflow-167", epic_run_id="run-167",
        invocation_id=INV, launch_ordinal=1, ladder_ordinal=1,
        scoring_job_id=JOB, transition_reason="judge scoring job", agent="", route="gateway", **overrides,
    )


async def score(proxy: FakeJudgeProxy, *, sink: Callable[[Any], None], **kwargs: Any) -> Any:
    prior_feedback = None
    for judge_attempt in range(1, kwargs.pop("max_judge_retries") + 2):
        verdict = await run_judge(
        CRITERIA, "diff", scoring_job_id=JOB, invocation_id=INV,
        tested_revision=REV, proxy_url=proxy.base_url,
            virtual_key=proxy.virtual_key, model_alias=MODEL,
            transport=proxy.transport, retry_backoff_s=0.0,
            judge_attempt=judge_attempt, prior_feedback=prior_feedback,
            evaluation_sink=sink, **kwargs,
        )
        if verdict.outcome != JudgeOutcome.RETRY:
            return verdict
        prior_feedback = verdict.feedback


async def test_the_real_reask_loop_keeps_transport_and_every_evaluation() -> None:
    proxy = FakeJudgeProxy()
    proxy.fail_next(times=1)
    proxy.reply("this is not a verdict object")
    proxy.reply('{"verdict":"pass","scenarios":[{"scenario":"US2-S1","pass":false,"reasoning":"the test gate would fail"},{"scenario":"US2-S2","pass":true,"reasoning":"S2 passed"}],"feedback":"contradictory draft"}')
    proxy.reply(verdict_json(scenarios=(("US2-S1", True), ("US2-S2", True)), feedback="the gate is recorded PASS"))
    records: list[Any] = []
    verdict = await score(
        proxy, sink=records.append, max_judge_retries=2,
        gate_results=[GateResult("test", "pytest", "PASS", 0, 1.0, "1 passed")],
    )
    assert (verdict.judge_attempt, verdict.outcome.value) == (3, "PASS")
    assert [(record.scoring_call_ordinal, record.status) for record in records] == [
        (1, "parse_error"), (2, "contradiction"), (3, "valid"),
    ]
    first_delivery = records[0].deliveries
    assert [item.status for item in first_delivery] == ["transport_error", "delivered"]
    assert first_delivery[0].error
    assert all(
        (record.criteria_fingerprint, record.tested_revision, record.model_alias,
         record.prompt_tokens, record.completion_tokens, record.usage_status) == (FP, REV, MODEL, 1200, 180, "partial") for record in records
    )
    assert len({record.evaluation_id for record in records}) == 3
    assert [result[:2] for result in records[1].scenario_results] == [("US2-S1", False), ("US2-S2", True)]


async def test_one_scoring_job_has_one_usage_total_and_unknown_request_metrics(
    tmp_path: Path, litellm_env: FakeLiteLLM, monkeypatch
) -> None:
    ledger, journal = tmp_path / "usage.db", tmp_path / "attestation.db"
    monkeypatch.setenv(ERGANE_LEDGER_PATH_ENV, str(ledger))
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    monkeypatch.setattr(usage_activities, "open_client", lambda: LiteLLMClient.from_env(transport=litellm_env.transport))
    environment = ActivityEnvironment()
    lease = await environment.run(issue_attempt_key, judge_input())
    await environment.run(teardown_attempt, TeardownInput(lease=lease, termination=Termination.COMPLETED))
    evidence = read_usage_evidence(ledger)
    assert (len(evidence), evidence[0].builder_or_judge) == (1, "judge")
    metrics = evidence[0].metrics
    assert [metrics[name].value for name in ("prompt_tokens", "completion_tokens", "request_count")] == [None] * 3
    assert metrics["request_count"].complete is False
    assert read_scoring_evaluations(journal) == ()


def judge_run(proxy: FakeJudgeProxy, *, judge_attempt: int = 1, max_judge_retries: int = 0, prior_feedback: str | None = None) -> RunJudgeInput:
    return RunJudgeInput(
        criteria=CRITERIA, diff_text="diff", virtual_key=proxy.virtual_key,
        proxy_url=proxy.base_url, model_alias=MODEL, judge_attempt=judge_attempt,
        prior_feedback=prior_feedback, max_judge_retries=max_judge_retries,
        scoring_job_id=JOB,
        invocation_id=INV, tested_revision=REV,
    )


async def judge_activity(monkeypatch, proxy: FakeJudgeProxy, run: RunJudgeInput) -> Any:
    monkeypatch.setattr(verify_activities, "judge_transport", lambda: proxy.transport)
    monkeypatch.setattr(verify_activities, "JUDGE_RETRY_BACKOFF_S", 0.0)
    return await ActivityEnvironment().run(verify_activities.run_judge, run)


async def test_run_judge_activity_persists_with_us1_identity(tmp_path: Path, monkeypatch) -> None:
    proxy = FakeJudgeProxy()
    proxy.reply("not a verdict object")
    proxy.reply(verdict_json(scenarios=(("US2-S1", True), ("US2-S2", True))))
    journal = tmp_path / "attestation.db"
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    first = await judge_activity(monkeypatch, proxy, judge_run(proxy, max_judge_retries=1))
    assert first.outcome.value == "RETRY"
    second = await judge_activity(
        monkeypatch, proxy,
        judge_run(proxy, judge_attempt=2, max_judge_retries=1, prior_feedback=first.feedback),
    )
    assert second.outcome.value == "PASS"
    records = read_scoring_evaluations(journal)
    assert [(record.status, record.scoring_call_ordinal) for record in records] == [("parse_error", 1), ("valid", 2)]
    assert all((record.scoring_job_id, record.invocation_id, record.tested_revision) == (JOB, INV, REV) for record in records)


async def test_run_judge_activity_persists_an_unavailable_scoring_failure(
    tmp_path: Path, monkeypatch
) -> None:
    journal = tmp_path / "attestation.db"
    proxy = FakeJudgeProxy()
    proxy.fail_always(503)
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    with pytest.raises(Exception):
        await judge_activity(
            monkeypatch, proxy,
            judge_run(proxy, max_judge_retries=0),
        )
    records = read_scoring_evaluations(journal)
    assert [(record.status, record.scoring_call_ordinal) for record in records] == [("unavailable", 1)]
    record = records[0]
    assert (record.scoring_job_id, record.invocation_id, record.tested_revision) == (JOB, INV, REV)
    assert [item.status for item in record.deliveries] == ["transport_error"] * 3
    assert all(item.error for item in record.deliveries)
    assert record.feedback
    assert proxy.virtual_key not in record.feedback
