"""US1-S1/S2: execution identity, question reuse, and frozen ladder evidence."""

from __future__ import annotations

from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities
from factory.activities.usage_activities import (
    ERGANE_LEDGER_PATH_ENV,
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    teardown_attempt,
)
from factory.attestation import (
    RungSelection,
    record_launch,
    read_launches,
)
from factory.usage.models import Termination
from tests.conftest import FakeLiteLLM
from tests.test_usage_activities import issue_input, tear_down
from factory.usage.litellm_client import LiteLLMClient


LADDER = (
    RungSelection(
        persona="implementer",
        runner="claude-code",
        route="gateway",
        model_aliases=("builder-a",),
        reason="node's own routing",
    ),
    RungSelection(
        persona="debugger",
        runner="codex",
        route="subscription",
        model_aliases=("debugger-a",),
        reason="debugger rung",
    ),
)


def identity_input(**overrides: Any) -> IssueKeyInput:
    fields = {
        "persona": "implementer",
        "target": "bryantharpeorg/ergane",
        "spec_revision": "69fc9a780091257e6ac03637d717a2bab659ec17",
        "spec_fingerprint": "0" * 64,
        "epic_workflow_id": "epic-demo",
        "epic_run_id": "run-one",
        "invocation_id": "run-one:launch:1",
        "launch_ordinal": 1,
        "ladder_ordinal": 1,
        "ladder": LADDER,
        "transition_reason": "node's own routing",
        "agent": "claude-code",
        "route": "gateway",
    }
    fields.update(overrides)
    return issue_input(**fields)


@pytest.fixture
def stores(
    tmp_path: Any, litellm_env: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, Any, FakeLiteLLM]:
    ledger = tmp_path / "ledger.db"
    journal = tmp_path / "attestation.db"
    monkeypatch.setenv(ERGANE_LEDGER_PATH_ENV, str(ledger))
    monkeypatch.setenv("ERGANE_ATTESTATION_DB", str(journal))
    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=litellm_env.transport),
    )
    return ledger, journal, litellm_env


async def test_reused_ordinals_keep_distinct_usages(
    stores: tuple[Any, Any, FakeLiteLLM],
) -> None:
    ledger, journal, proxy = stores
    environment = ActivityEnvironment()

    first = await environment.run(issue_attempt_key, identity_input())
    second = await environment.run(
        issue_attempt_key,
        identity_input(epic_run_id="run-two", invocation_id="run-two:launch:1"),
    )
    question_one = await environment.run(
        issue_attempt_key,
        identity_input(invocation_id="run-one:question:1", launch_ordinal=2),
    )
    question_two = await environment.run(
        issue_attempt_key,
        identity_input(invocation_id="run-one:question:2", launch_ordinal=3),
    )
    for lease in (first, second, question_one, question_two):
        proxy.add_spend_row(
            lease.key,
            prompt_tokens=10,
            completion_tokens=1,
            spend=0.01,
            request_id=f"request-{lease.invocation_id}",
        )
        record = await environment.run(
            teardown_attempt,
            TeardownInput(lease=lease, termination=Termination.COMPLETED),
        )
        assert record.id is not None

    rows = read_launches(journal)
    assert [row.invocation_id for row in rows] == [
        "run-one:launch:1",
        "run-two:launch:1",
        "run-one:question:1",
        "run-one:question:2",
    ]
    assert len({row.key_alias for row in rows}) == 4
    assert len({record.key_alias for record in read_launches(journal)}) == 4
    assert len({row.usage_id for row in read_launches(journal)}) == 4
    assert [row.ladder_ordinal for row in rows] == [1, 1, 1, 1]


async def test_a_redelivered_teardown_does_not_duplicate_spend(
    stores: tuple[Any, Any, FakeLiteLLM],
) -> None:
    ledger, journal, proxy = stores
    environment = ActivityEnvironment()
    lease = await environment.run(issue_attempt_key, identity_input())
    proxy.add_spend_row(lease.key, prompt_tokens=4, completion_tokens=2, spend=0.03)
    record = await environment.run(
        teardown_attempt,
        TeardownInput(lease=lease, termination=Termination.COMPLETED),
    )
    redelivered = await environment.run(
        teardown_attempt,
        TeardownInput(lease=lease, termination=Termination.COMPLETED),
    )

    assert redelivered.id == record.id
    rows = read_launches(journal)
    assert len(rows) == 1
    assert rows[0].usage_id == record.id
    assert proxy.rows_for(lease.key)[0]["spend"] == 0.03


async def test_a_frozen_ladder_survives_a_rung_transition(
    stores: tuple[Any, Any, FakeLiteLLM],
) -> None:
    ledger, journal, proxy = stores
    environment = ActivityEnvironment()
    failed = await environment.run(issue_attempt_key, identity_input())
    await environment.run(
        teardown_attempt,
        TeardownInput(
            lease=failed,
            termination=Termination.AGENT_ERROR,
            launch_outcome="agent_error",
            launch_reason="ordinary launch failed",
        ),
    )
    promoted = await environment.run(
        issue_attempt_key,
        identity_input(
            invocation_id="run-one:launch:2",
                launch_ordinal=2,
                persona="debugger",
                agent="codex",
            route="subscription",
            ladder_ordinal=2,
            transition_reason="debugger rung",
        ),
    )
    await environment.run(
        teardown_attempt,
        TeardownInput(
            lease=promoted,
            termination=Termination.COMPLETED,
            launch_outcome="completed",
        ),
    )

    rows = read_launches(journal)
    assert [row.actual_rung.persona for row in rows] == ["implementer", "debugger"]
    assert [row.actual_rung.runner for row in rows] == ["claude-code", "codex"]
    assert [row.actual_rung.route for row in rows] == ["gateway", "subscription"]
    assert rows[0].ladder == LADDER
    assert rows[1].transition_reason == "debugger rung"
    assert [row.outcome for row in rows] == ["agent_error", "completed"]
