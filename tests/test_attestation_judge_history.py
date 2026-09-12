"""US2-S1/S2: the scoring loop keeps every evaluation and one job total."""

from pathlib import Path
from typing import Any, Callable

from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities, verify_activities
from factory.activities.usage_activities import (
    ERGANE_LEDGER_PATH_ENV, IssueKeyInput, TeardownInput, issue_attempt_key, teardown_attempt,
)
from factory.activities.verify_activities import RunJudgeInput
from factory.attestation import read_scoring_evaluations, read_usage_evidence
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import Termination
from factory.verify.judge import run_scoring_job
from factory.verify.models import CriteriaSet, GateResult, Requirement, RequirementKind, Scenario
from tests.conftest import FakeLiteLLM
from tests.judge_proxy import FakeJudgeProxy, verdict_json
from tests.test_usage_activities import issue_input


JOB_ID = "us2:1:score"
INVOCATION_ID = "run-167:us2:judge:score:1"
TESTED_REVISION = "attempt-tree-1"
MODEL = "judge-model"
FP = "1" * 64
SCENARIOS = (
    Scenario("US2-S1", ["**Then** one scenario result survives"], "1. ..."),
    Scenario("US2-S2", ["**Then** a second result survives"], "2. ..."),
)
CRITERIA = CriteriaSet(
    feature="167-audit-packet", spec_ref="167/spec.md",
    requirements=[Requirement("US2", RequirementKind.STORY, "Judge history", "P1", "Every evaluation survives.", list(SCENARIOS))],
    source_path="167/spec.md", source_sha256=FP,
    snapshotted_at="2026-09-12T00:00:00Z",
)


def judge_input(**overrides: Any) -> IssueKeyInput:
    return issue_input(
        persona="judge", epic_id="epic-167", node_id="us2", attempt=1,
        spec_ref=CRITERIA.spec_ref, models=[MODEL], target="bryantharpeorg/ergane",
        spec_revision=CRITERIA.source_path, spec_fingerprint=CRITERIA.source_sha256,
        epic_workflow_id="workflow-167", epic_run_id="run-167",
        invocation_id=INVOCATION_ID, launch_ordinal=1, ladder_ordinal=1,
        scoring_job_id=JOB_ID, transition_reason="judge scoring job", agent="", route="gateway", **overrides,
    )


async def score(proxy: FakeJudgeProxy, *, sink: Callable[[Any], None] | None = None, **kwargs: Any) -> Any:
    return await run_scoring_job(
        CRITERIA, "diff", scoring_job_id=JOB_ID, invocation_id=INVOCATION_ID,
        tested_revision=TESTED_REVISION, proxy_url=proxy.base_url, virtual_key=proxy.virtual_key,
        model_alias=MODEL, transport=proxy.transport, retry_backoff_s=0.0,
        evaluation_sink=sink, **kwargs,
    )


async def test_the_real_reask_loop_keeps_transport_and_every_evaluation() -> None:
    proxy = FakeJudgeProxy()
    proxy.fail_next(times=1)
    proxy.reply("this is not a verdict object")
    proxy.reply('{"verdict":"pass","scenarios":[{"scenario":"US2-S1","pass":false,"reasoning":"the test gate would fail"},{"scenario":"US2-S2","pass":true,"reasoning":"S2 passed"}],"feedback":"contradictory draft"}')
    proxy.reply(
        verdict_json(scenarios=(("US2-S1", True), ("US2-S2", True)), feedback="the gate is recorded PASS")
    )
    records: list[Any] = []
    verdict = await score(
        proxy, sink=records.append, max_judge_retries=2,
        gate_results=[GateResult("test", "pytest", "PASS", 0, 1.0, "1 passed")],
    )
    assert (verdict.judge_attempt, verdict.outcome.value) == (3, "PASS")
    assert [(record.scoring_call_ordinal, record.status) for record in records] == [
        (1, "parse_error"), (2, "contradiction"), (3, "valid"),
    ]
    first_delivery = records[0].deliveries[0]
    assert (len(records[0].deliveries), [item.status for item in records[0].deliveries], bool(first_delivery.error)) == (
        2, ["transport_error", "delivered"], True,
    )
    assert all(
        (record.criteria_fingerprint, record.tested_revision, record.model_alias,
         record.prompt_tokens, record.completion_tokens, record.usage_status)
        == (FP, TESTED_REVISION, MODEL, 1200, 180, "partial") for record in records
    )
    assert (len({record.evaluation_id for record in records}), records[0].parse_error) == (3, records[0].parse_error)
    assert [result[:2] for result in records[1].scenario_results] == [
        ("US2-S1", False), ("US2-S2", True),
    ]
    assert all(record.prompt_tokens == 1200 for record in records)
    assert all(record.completion_tokens == 180 for record in records)
    assert all(record.usage_status == "partial" for record in records)


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
    assert [metrics[name].value for name in ("prompt_tokens", "completion_tokens", "request_count")] == [None, None, None]
    assert metrics["request_count"].complete is False
    assert read_scoring_evaluations(journal) == ()


def judge_run(
    proxy: FakeJudgeProxy, journal: Path, *, judge_attempt: int = 1,
    max_judge_retries: int = 0, prior_feedback: str | None = None,
) -> RunJudgeInput:
    return RunJudgeInput(
        criteria=CRITERIA, diff_text="diff", virtual_key=proxy.virtual_key,
        proxy_url=proxy.base_url, model_alias=MODEL, judge_attempt=judge_attempt,
        prior_feedback=prior_feedback, max_judge_retries=max_judge_retries,
        journal_path=str(journal), scoring_job_id=JOB_ID,
        invocation_id=INVOCATION_ID, tested_revision=TESTED_REVISION,
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
    first = await judge_activity(monkeypatch, proxy, judge_run(proxy, journal, max_judge_retries=1))
    assert first.outcome.value == "RETRY"
    second = await judge_activity(
        monkeypatch, proxy,
        judge_run(proxy, journal, judge_attempt=2, max_judge_retries=1, prior_feedback=first.feedback),
    )
    assert second.outcome.value == "PASS"
    records = read_scoring_evaluations(journal)
    assert [(record.status, record.scoring_call_ordinal) for record in records] == [
        ("parse_error", 1), ("valid", 2),
    ]
    assert all((record.scoring_job_id, record.invocation_id, record.tested_revision) == (JOB_ID, INVOCATION_ID, TESTED_REVISION) for record in records)
    assert records[0].parse_error
