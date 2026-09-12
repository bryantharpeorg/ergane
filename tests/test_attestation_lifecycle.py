"""US1-S3: every launch path leaves an attributable outcome behind."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities
from factory.activities.usage_activities import (
    ERGANE_LEDGER_PATH_ENV,
    KEY_ISSUANCE_FAILED,
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    teardown_attempt,
)
from factory.attestation import read_launches
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import Termination
from tests.test_attestation_identity import identity_input, stores
from tests.test_usage_activities import ledger_rows


@pytest.mark.parametrize(
    ("termination", "outcome"),
    [
        (Termination.TIMEOUT, "timeout"),
        (Termination.KILLED, "cancelled"),
        (Termination.QUESTION, "question"),
        (Termination.PRE_AGENT_FAILURE, "pre_agent_failure"),
    ],
)
async def test_terminal_paths_without_verification_or_usage(
    stores: tuple[Any, Any, Any],
    termination: Termination,
    outcome: str,
) -> None:
    ledger, journal, proxy = stores
    environment = ActivityEnvironment()
    lease = await environment.run(issue_attempt_key, identity_input())
    record = await environment.run(
        teardown_attempt,
        TeardownInput(
            lease=lease,
            termination=termination,
            launch_outcome=outcome,
            launch_reason="no verification was reached",
        ),
    )
    stored = ledger_rows(ledger)[0]

    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.request_count is None
    assert record.final_usage_confirmed is False
    assert stored["request_count"] is None
    launch = read_launches(journal)[0]
    assert launch.outcome == outcome
    assert launch.outcome_reason == "no verification was reached"
    assert launch.usage_id == record.id
    assert proxy.calls_to("/key/generate") == [proxy.calls_to("/key/generate")[0]]


async def test_question_reuse_is_recorded_without_spending_a_rung(
    stores: tuple[Any, Any, Any],
) -> None:
    ledger, journal, proxy = stores
    environment = ActivityEnvironment()
    question = await environment.run(
        issue_attempt_key,
        identity_input(
            invocation_id="run-one:question:1",
            launch_ordinal=2,
            ladder_ordinal=1,
        ),
    )
    record = await environment.run(
        teardown_attempt,
        TeardownInput(
            lease=question,
            termination=Termination.QUESTION,
            launch_outcome="question",
        ),
    )

    launch = read_launches(journal)[0]
    assert launch.ladder_ordinal == 1
    assert launch.launch_ordinal == 2
    assert launch.outcome == "question"
    assert record.request_count is None
    assert record.prompt_tokens is None
    assert len(proxy.calls_to("/key/generate")) == 1


async def test_failed_issuance_is_recorded_and_not_attributed_to_a_usage(
    stores: tuple[Any, Any, Any],
) -> None:
    ledger, journal, proxy = stores
    proxy.fail_next("/key/generate", status=503)
    environment = ActivityEnvironment()

    with pytest.raises(ApplicationError) as raised:
        await environment.run(issue_attempt_key, identity_input())

    assert raised.value.type == KEY_ISSUANCE_FAILED
    launches = read_launches(journal)
    assert len(launches) == 1
    assert launches[0].outcome == "issuance_failed"
    assert launches[0].usage_id is None
    assert launches[0].ladder_ordinal == 1
    assert not Path(ledger).is_file()
