"""US2-S1/S2: the scoring loop keeps every evaluation and one job total."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities, verify_activities
from factory.activities.usage_activities import (
    ERGANE_LEDGER_PATH_ENV,
    IssueKeyInput,
    issue_attempt_key,
    teardown_attempt,
)
from factory.activities.verify_activities import RunJudgeInput
from factory.attestation import read_scoring_evaluations, read_usage_evidence
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import Termination
from factory.verify.judge import run_scoring_job
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    Requirement,
    RequirementKind,
    Scenario,
)


GATE_RESULTS = (
    GateResult(
        name="test",
        command="pytest",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=1.0,
        output_tail="1 passed",
    ),
)
from tests.conftest import FakeLiteLLM
from tests.judge_proxy import FakeJudgeProxy, verdict_json
from tests.test_usage_activities import issue_input


SCENARIOS = (
    Scenario("US2-S1", ["**Then** one scenario result survives"], "1. ..."),
    Scenario("US2-S2", ["**Then** a second result survives"], "2. ..."),
)
REQUIREMENTS = (
    Requirement(
        "US2",
        RequirementKind.STORY,
        "Judge history",
        "P1",
        "Every evaluation survives.",
        list(SCENARIOS),
    ),
)
CRITERIA = CriteriaSet(
    feature="167-audit-packet",
    spec_ref="167/spec.md",
    requirements=list(REQUIREMENTS),
    source_path="167/spec.md",
    source_sha256="1" * 64,
    snapshotted_at="2026-09-12T00:00:00Z",
)


def verdict_json_(
    *, verdict: str, results: tuple[tuple[str, bool, str], ...], feedback: str = "ok"
) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "scenarios": [
                {"scenario": scenario, "pass": passed, "reasoning": reasoning}
                for scenario, passed, reasoning in results
            ],
            "feedback": feedback,
        }
    )


def judge_input(**overrides: Any) -> IssueKeyInput:
    fields = {
        "persona": "judge",
        "epic_id": "epic-167",
        "node_id": "us2",
        "attempt": 1,
        "spec_ref": CRITERIA.spec_ref,
        "models": ["judge-model"],
        "target": "bryantharpeorg/ergane",
        "spec_revision": CRITERIA.source_path,
        "spec_fingerprint": CRITERIA.source_sha256,
        "epic_workflow_id": "workflow-167",
        "epic_run_id": "run-167",
        "invocation_id": "run-167:us2:judge:score:1",
        "launch_ordinal": 1,
        "ladder_ordinal": 1,
        "scoring_job_id": "us2:1:score",
        "transition_reason": "judge scoring job",
        "agent": "",
        "route": "gateway",
    }
    fields.update(overrides)
    return issue_input(**fields)


async def score(
    proxy: FakeJudgeProxy,
    *,
    sink: Callable[[Any], None] | None = None,
    **kwargs: Any,
) -> Any:
    return await run_scoring_job(
        CRITERIA,
        "diff",
        scoring_job_id="us2:1:score",
        invocation_id="run-167:us2:judge:score:1",
        tested_revision="attempt-tree-1",
        proxy_url=proxy.base_url,
        virtual_key=proxy.virtual_key,
        model_alias="judge-model",
        transport=proxy.transport,
        retry_backoff_s=0.0,
        evaluation_sink=sink,
        **kwargs,
    )


async def test_the_real_reask_loop_keeps_malformed_contradictory_and_valid_evaluations(
    tmp_path: Path,
) -> None:
    proxy = FakeJudgeProxy()
    proxy.reply("this is not a verdict object")
    proxy.reply(
        verdict_json_(
            verdict="pass",
            results=(
                ("US2-S1", False, "the test gate would fail"),
                ("US2-S2", True, "S2 passed"),
            ),
            feedback="contradictory draft",
        )
    )
    proxy.reply(
        verdict_json_(
            verdict="pass",
            results=(
                ("US2-S1", True, "the gate is recorded PASS"),
                ("US2-S2", True, "unchanged"),
            ),
        )
    )

    records: list[Any] = []
    verdict = await score(
        proxy,
        sink=records.append,
        max_judge_retries=2,
        gate_results=GATE_RESULTS,
    )

    assert verdict.judge_attempt == 3
    assert verdict.outcome.value == "PASS"
    assert [(record.scoring_call_ordinal, record.status) for record in records] == [
        (1, "parse_error"),
        (2, "contradiction"),
        (3, "valid"),
    ]
    assert all(record.criteria_fingerprint == CRITERIA.source_sha256 for record in records)
    assert all(record.tested_revision == "attempt-tree-1" for record in records)
    assert all(record.model_alias == "judge-model" for record in records)
    assert len({record.evaluation_id for record in records}) == 3
    assert records[0].parse_error
    assert records[1].scenario_results == (
        ("US2-S1", False, "the test gate would fail"),
        ("US2-S2", True, "S2 passed"),
    )
    assert all(record.prompt_tokens == 1200 for record in records)
    assert all(record.completion_tokens == 180 for record in records)
    assert all(record.request_count is None for record in records)
    assert all(record.usage_status == "partial" for record in records)


async def test_transport_redelivery_is_one_evaluation_with_two_deliveries(
    tmp_path: Path,
) -> None:
    proxy = FakeJudgeProxy()
    proxy.fail_next(times=1)
    proxy.reply(
        verdict_json_(
            verdict="pass",
            results=(("US2-S1", True, "yes"), ("US2-S2", True, "yes")),
        )
    )

    records: list[Any] = []
    verdict = await score(proxy, sink=records.append, max_judge_retries=0)

    assert verdict.outcome.value == "PASS"
    assert len(records) == 1
    evaluation = records[0]
    assert evaluation.status == "valid"
    assert [
        (item.status, item.delivery_ordinal) for item in evaluation.deliveries
    ] == [
        ("transport_error", 1),
        ("delivered", 2),
    ]
    assert evaluation.deliveries[0].error
    assert evaluation.usage_status == "partial"


async def test_one_scoring_job_has_one_usage_total_and_unknown_request_metrics(
    tmp_path: Path,
    litellm_env: FakeLiteLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "usage.db"
    journal = tmp_path / "attestation.db"
    monkeypatch.setenv(ERGANE_LEDGER_PATH_ENV, str(ledger))
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=litellm_env.transport),
    )
    environment = ActivityEnvironment()
    lease = await environment.run(issue_attempt_key, judge_input())
    await environment.run(
        teardown_attempt,
        __import__("factory.activities.usage_activities", fromlist=["TeardownInput"]).TeardownInput(
            lease=lease, termination=Termination.COMPLETED
        ),
    )

    evidence = read_usage_evidence(ledger)
    assert len(evidence) == 1
    assert evidence[0].builder_or_judge == "judge"
    assert evidence[0].metrics["prompt_tokens"].value is None
    assert evidence[0].metrics["completion_tokens"].value is None
    assert evidence[0].metrics["request_count"].value is None
    assert evidence[0].metrics["request_count"].complete is False
    assert read_scoring_evaluations(journal) == ()


async def test_run_judge_activity_persists_with_us1_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = FakeJudgeProxy()
    proxy.reply("not a verdict object")
    proxy.reply(
        verdict_json_(
            verdict="pass",
            results=(
                ("US2-S1", True, "yes"),
                ("US2-S2", True, "yes"),
            ),
        )
    )
    journal = tmp_path / "attestation.db"
    monkeypatch.setattr(verify_activities, "judge_transport", lambda: proxy.transport)
    monkeypatch.setattr(verify_activities, "JUDGE_RETRY_BACKOFF_S", 0.0)

    first = await ActivityEnvironment().run(
        verify_activities.run_judge,
        RunJudgeInput(
            criteria=CRITERIA,
            diff_text="diff",
            virtual_key=proxy.virtual_key,
            proxy_url=proxy.base_url,
                model_alias="judge-model",
                judge_attempt=1,
                max_judge_retries=1,
            journal_path=str(journal),
            scoring_job_id="us2:1:score",
            invocation_id="run-167:us2:judge:score:1",
            tested_revision="attempt-tree-1",
        ),
    )

    assert first.outcome.value == "RETRY"
    second = await ActivityEnvironment().run(
        verify_activities.run_judge,
        RunJudgeInput(
            criteria=CRITERIA,
            diff_text="diff",
            virtual_key=proxy.virtual_key,
            proxy_url=proxy.base_url,
            model_alias="judge-model",
            judge_attempt=2,
            prior_feedback=first.feedback,
            max_judge_retries=1,
            journal_path=str(journal),
            scoring_job_id="us2:1:score",
            invocation_id="run-167:us2:judge:score:1",
            tested_revision="attempt-tree-1",
        ),
    )
    assert second.outcome.value == "PASS"
    records = read_scoring_evaluations(journal)
    assert [(record.status, record.scoring_call_ordinal) for record in records] == [
        ("parse_error", 1),
        ("valid", 2),
    ]
    assert all(record.scoring_job_id == "us2:1:score" for record in records)
    assert all(record.invocation_id == "run-167:us2:judge:score:1" for record in records)
    assert all(record.tested_revision == "attempt-tree-1" for record in records)
    assert records[0].parse_error


async def test_run_judge_activity_persists_transport_redelivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = FakeJudgeProxy()
    proxy.fail_next(times=1)
    proxy.reply(
        verdict_json_(
            verdict="pass",
            results=(("US2-S1", True, "yes"), ("US2-S2", True, "yes")),
        )
    )
    journal = tmp_path / "attestation.db"
    monkeypatch.setattr(verify_activities, "judge_transport", lambda: proxy.transport)
    monkeypatch.setattr(verify_activities, "JUDGE_RETRY_BACKOFF_S", 0.0)

    await ActivityEnvironment().run(
        verify_activities.run_judge,
        RunJudgeInput(
            criteria=CRITERIA,
            diff_text="diff",
            virtual_key=proxy.virtual_key,
            proxy_url=proxy.base_url,
            model_alias="judge-model",
            max_judge_retries=0,
            journal_path=str(journal),
            scoring_job_id="us2:1:score",
            invocation_id="run-167:us2:judge:score:1",
            tested_revision="attempt-tree-1",
        ),
    )

    record = read_scoring_evaluations(journal)[0]
    assert len(record.deliveries) == 2
    assert record.deliveries[0].status == "transport_error"
    assert record.deliveries[1].status == "delivered"
