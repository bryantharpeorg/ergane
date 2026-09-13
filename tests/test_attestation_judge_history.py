"""US2-S1/S2: every evaluation and one job total survives."""

from pathlib import Path
from typing import Any, Callable
import pytest

from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities, verify_activities
from factory.activities.usage_activities import ERGANE_LEDGER_PATH_ENV, TeardownInput, issue_attempt_key, teardown_attempt
from factory.activities.verify_activities import RunJudgeInput
from factory.attestation import read_scoring_evaluations, read_usage_evidence
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import Termination
from factory.verify.judge import JudgeOutcome, run_judge
from factory.verify.models import CriteriaSet, GateResult, Requirement, RequirementKind, Scenario
from tests.conftest import FakeLiteLLM
from tests.judge_proxy import FakeJudgeProxy, verdict_json
from tests.test_usage_activities import issue_input


JOB = "job"
INV = "run:judge:score"
REV = "attempt-tree"
MODEL = "judge-model"
KEY_ALIAS = "judge-key"
FP = "1" * 64
SCENARIOS = tuple(Scenario(f"US2-S{i}", [f"Then {i} survives"], f"{i}. ...") for i in (1, 2))
CRITERIA = CriteriaSet("167", "167/spec.md", [Requirement("US2", RequirementKind.STORY, "history", "P1", "Evaluations survive.", list(SCENARIOS))], "167/spec.md", FP, "now")


async def score(proxy: FakeJudgeProxy, *, sink: Callable[[Any], None], **kwargs: Any) -> Any:
    prior_feedback = None
    for judge_attempt in range(1, kwargs.pop("max_judge_retries") + 2):
        verdict = await run_judge(CRITERIA, "diff", scoring_job_id=JOB, invocation_id=INV, tested_revision=REV, proxy_url=proxy.base_url, virtual_key=proxy.virtual_key, model_alias=MODEL, key_alias=KEY_ALIAS, transport=proxy.transport, retry_backoff_s=0.0, judge_attempt=judge_attempt, prior_feedback=prior_feedback, evaluation_sink=sink, **kwargs)
        if verdict.outcome != JudgeOutcome.RETRY:
            return verdict
        prior_feedback = verdict.feedback


async def test_reask_loop_keeps_every_evaluation() -> None:
    proxy = FakeJudgeProxy()
    proxy.fail_next(times=1)
    proxy.reply("this is not a verdict object")
    contradiction = verdict_json(verdict="pass", scenarios=(("US2-S1", False), ("US2-S2", True)))
    proxy.reply(contradiction.replace("the diff does not satisfy", "the test gate would fail"))
    proxy.reply(verdict_json(scenarios=(("US2-S1", True), ("US2-S2", True))))
    records: list[Any] = []
    verdict = await score(
        proxy, sink=records.append, max_judge_retries=2,
        gate_results=[GateResult("test", "pytest", "PASS", 0, 1.0, "passed")],
    )
    assert (verdict.judge_attempt, verdict.outcome.value) == (3, "PASS")
    assert [(record.scoring_call_ordinal, record.status) for record in records] == [(1, "parse_error"), (2, "contradiction"), (3, "valid")]
    first_delivery = records[0].deliveries
    assert [item.status for item in first_delivery] == ["transport_error", "delivered"] and first_delivery[0].error
    assert all(
        (record.criteria_fingerprint, record.tested_revision, record.model_alias,
         record.prompt_tokens, record.completion_tokens, record.usage_status, record.route)
        == (FP, REV, MODEL, 1200, 180, "partial", "gateway") for record in records
    )
    assert len({record.evaluation_id for record in records}) == 3
    assert all(record.key_alias == KEY_ALIAS and proxy.virtual_key not in record.feedback for record in records)
    assert [result[:2] for result in records[1].scenario_results] == [("US2-S1", False), ("US2-S2", True)]


async def test_one_job_total_has_unknown_request_metrics(
    tmp_path: Path, litellm_env: FakeLiteLLM, monkeypatch
) -> None:
    ledger, journal = tmp_path / "usage.db", tmp_path / "attestation.db"
    monkeypatch.setenv(ERGANE_LEDGER_PATH_ENV, str(ledger))
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    monkeypatch.setattr(usage_activities, "open_client", lambda: LiteLLMClient.from_env(transport=litellm_env.transport))
    environment = ActivityEnvironment()
    lease = await environment.run(issue_attempt_key, issue_input(
        persona="judge", epic_id="epic", node_id="us2", attempt=1, spec_ref="spec.md",
        models=[MODEL], target="org/repo", spec_revision="spec.md", spec_fingerprint=FP,
        epic_workflow_id="wf", epic_run_id="run", invocation_id=INV, launch_ordinal=1,
        ladder_ordinal=1, scoring_job_id=JOB, transition_reason="judge", agent="", route="gateway",
    ))
    await environment.run(teardown_attempt, TeardownInput(lease=lease, termination=Termination.COMPLETED))
    evidence = read_usage_evidence(ledger)
    assert (len(evidence), evidence[0].builder_or_judge) == (1, "judge")
    metrics = evidence[0].metrics
    assert all(metrics[name].value is None for name in ("prompt_tokens", "completion_tokens", "request_count"))
    assert metrics["request_count"].complete is False
    assert read_scoring_evaluations(journal) == ()


def judge_run(proxy: FakeJudgeProxy, *, judge_attempt: int = 1, retries: int = 0, feedback: str | None = None) -> RunJudgeInput:
    return RunJudgeInput(criteria=CRITERIA, diff_text="diff", virtual_key=proxy.virtual_key, proxy_url=proxy.base_url, model_alias=MODEL, judge_attempt=judge_attempt, prior_feedback=feedback, max_judge_retries=retries, scoring_job_id=JOB, invocation_id=INV, tested_revision=REV)


async def judge_activity(monkeypatch, proxy: FakeJudgeProxy, run: RunJudgeInput) -> Any:
    monkeypatch.setattr(verify_activities, "judge_transport", lambda: proxy.transport)
    monkeypatch.setattr(verify_activities, "JUDGE_RETRY_BACKOFF_S", 0.0)
    return await ActivityEnvironment().run(verify_activities.run_judge, run)


async def test_activity_persists_reask_identity(tmp_path: Path, monkeypatch) -> None:
    proxy = FakeJudgeProxy()
    proxy.reply("not a verdict object")
    proxy.reply(verdict_json(scenarios=(("US2-S1", True), ("US2-S2", True))))
    journal = tmp_path / "attestation.db"
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    first = await judge_activity(monkeypatch, proxy, judge_run(proxy, retries=1))
    assert first.outcome.value == "RETRY"
    second = await judge_activity(
        monkeypatch, proxy,
        judge_run(proxy, judge_attempt=2, retries=1, feedback=first.feedback),
    )
    assert second.outcome.value == "PASS"
    records = read_scoring_evaluations(journal)
    assert [(record.status, record.scoring_call_ordinal) for record in records] == [("parse_error", 1), ("valid", 2)]
    assert all((record.scoring_job_id, record.invocation_id, record.tested_revision) == (JOB, INV, REV) for record in records)


async def test_activity_persists_an_unavailable_failure(tmp_path: Path, monkeypatch) -> None:
    journal = tmp_path / "attestation.db"
    proxy = FakeJudgeProxy()
    proxy.fail_always(503)
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    with pytest.raises(Exception):
        await judge_activity(monkeypatch, proxy, judge_run(proxy))
    records = read_scoring_evaluations(journal)
    assert [(record.status, record.scoring_call_ordinal) for record in records] == [("unavailable", 1)]
    record = records[0]
    assert (record.scoring_job_id, record.invocation_id, record.tested_revision) == (JOB, INV, REV)
    assert [item.status for item in record.deliveries] == ["transport_error"] * 3
    assert all(item.error for item in record.deliveries)
    assert record.feedback and proxy.virtual_key not in record.feedback
