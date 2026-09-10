"""US1: an attempt no worker accepts ends and names the reason.

The scheduled activity is read directly from one epic's recorded history
because a worker never accepting a task cannot be reproduced in this harness;
the test pins the option that makes Temporal report the missing acceptance.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from temporalio.exceptions import ActivityError
from temporalio.exceptions import TimeoutError as ActivityTimeoutError
from temporalio.exceptions import TimeoutType
from temporalio.testing import WorkflowEnvironment

from factory.verify.ladder import _attempts_spent
from factory.verify.models import AttemptRecord, VerificationConfig
from factory.workgraph.models import WorkGraph
from factory.workgraph.models import (
    AdapterResult,
    NodeRecord,
    Termination,
    UsageSnapshot,
)
from factory.workgraph import workflow as workflow_module

from tests.test_interpreter import (
    _EVENT_ACTIVITY_SCHEDULED,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    make_graph,
    make_node,
    passing,
    run_epic,
)


def _agent_scheduled_events(history: Any) -> list[Any]:
    """Scheduled events for the agent activity, in history order."""
    return [
        event
        for event in history.events
        if event.event_type == _EVENT_ACTIVITY_SCHEDULED
        and event.activity_task_scheduled_event_attributes.activity_type.name
        == "run_agent_attempt"
    ]


def _activity_error(timeout: ActivityTimeoutError) -> ActivityError:
    """Wrap a timeout the way Temporal's failure converter does."""
    activity_error = ActivityError(
        "Activity task failed",
        scheduled_event_id=1,
        started_event_id=1,
        identity="",
        activity_type="run_agent_attempt",
        activity_id="us1",
        retry_state=None,
    )
    activity_error.__cause__ = timeout
    return activity_error


def _record() -> NodeRecord:
    """One node's mutable workflow state, with no ladder history yet."""
    return NodeRecord(node_id="us1", branch="factory/demo-loans/us1")


def _heartbeat_details(payload: dict[str, Any]) -> list[Any]:
    """The decoded heartbeat shape the workflow already reads."""
    return [payload]


_PAYLOAD = {"spend_usd": 6.25, "captured_at": "2026-08-05T09:31:00Z"}


async def test_the_activity_names_a_schedule_to_start_bound(
    env: WorkflowEnvironment,
) -> None:
    """The scheduled activity carries the shared no-worker bound (FR-001/FR-014)."""
    graph: WorkGraph = make_graph([make_node("us1", "US1")])
    script = ScriptedWorld({"us1": [passing()]}, client=env.client)

    await run_epic(env, script, graph=graph)

    history = await script.handle.fetch_history()
    scheduled = _agent_scheduled_events(history)
    assert len(scheduled) == 1
    attributes = scheduled[0].activity_task_scheduled_event_attributes
    assert attributes.schedule_to_start_timeout.ToTimedelta() == (
        workflow_module._AGENT_SCHEDULE_TO_START_TIMEOUT
    )
    assert workflow_module._AGENT_SCHEDULE_TO_START_TIMEOUT >= timedelta(minutes=30)


async def test_the_no_worker_bound_is_independent_of_the_work_deadline(
    env: WorkflowEnvironment,
) -> None:
    """Two deadlines get one no-worker bound and unchanged work options."""
    graph: WorkGraph = make_graph(
        [
            make_node("us1", "US1", timeout_override_s=12),
            make_node("us2", "US2", timeout_override_s=1200),
        ]
    )
    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()]},
        client=env.client,
    )

    await run_epic(env, script, graph=graph)

    history = await script.handle.fetch_history()
    scheduled = _agent_scheduled_events(history)
    assert len(scheduled) == 2
    [short, long] = [
        event.activity_task_scheduled_event_attributes for event in scheduled
    ]

    short_start_to_close = short.start_to_close_timeout.ToTimedelta()
    long_start_to_close = long.start_to_close_timeout.ToTimedelta()
    assert short.schedule_to_start_timeout.ToTimedelta() == (
        long.schedule_to_start_timeout.ToTimedelta()
    )
    assert short.schedule_to_start_timeout.ToTimedelta() == (
        workflow_module._AGENT_SCHEDULE_TO_START_TIMEOUT
    )
    assert short.heartbeat_timeout.ToTimedelta() != (
        long.heartbeat_timeout.ToTimedelta()
    )
    assert short_start_to_close == timedelta(seconds=12 + workflow_module._ADAPTER_GRACE_S)
    assert long_start_to_close == timedelta(seconds=1200 + workflow_module._ADAPTER_GRACE_S)
    for retry_policy in (short.retry_policy, long.retry_policy):
        assert retry_policy.initial_interval.ToTimedelta() == timedelta(seconds=5)
        assert retry_policy.maximum_interval.ToTimedelta() == timedelta(seconds=500)
        assert retry_policy.maximum_attempts == 2
        assert retry_policy.backoff_coefficient == 2.0
        assert list(retry_policy.non_retryable_error_types) == []


async def test_a_scheduled_timeout_with_no_measurement_is_not_an_attempt() -> None:
    """An expiry before any worker accepted raises `_LaunchFailed` (FR-004).

    Called directly because the expiry is not reachable through the harness
    (a worker polling an unregistered activity produces an application error
    rather than the schedule-to-start timeout), and the classification is the
    claim. The error is built empty because this is the attempt nobody ever
    accepted; the test below covers its twin, the attempt that ran first.
    """
    workflow_under_test = workflow_module.EpicWorkflow()
    record = _record()
    timeout = ActivityTimeoutError(
        "schedule-to-start timeout",
        type=TimeoutType.SCHEDULE_TO_START,
        last_heartbeat_details=[],
    )
    exc = _activity_error(timeout)

    with pytest.raises(workflow_module._LaunchFailed):
        workflow_under_test._attempt_timeout(record, exc)

    assert record.history == []
    assert (
        _attempts_spent(
            [
                AttemptRecord(attempt=row.attempt, persona="implementer")
                for row in record.history
            ],
            VerificationConfig(),
        )
        == 0
    )
    assert record.last_snapshot is None


async def test_a_heartbeat_timeout_keeps_its_measurement() -> None:
    """A worker death remains a recorded timeout with its last figure (FR-005)."""
    workflow_under_test = workflow_module.EpicWorkflow()
    record = _record()
    timeout = ActivityTimeoutError(
        "heartbeat timeout",
        type=TimeoutType.HEARTBEAT,
        last_heartbeat_details=_heartbeat_details(_PAYLOAD),
    )

    result = workflow_under_test._attempt_timeout(
        record, _activity_error(timeout)
    )

    assert result.termination == Termination.TIMEOUT
    assert result.last_snapshot is not None
    assert result.last_snapshot.spend_usd == 6.25
    assert result.last_snapshot.captured_at == "2026-08-05T09:31:00Z"
    assert record.last_snapshot == result.last_snapshot


async def test_a_scheduled_timeout_with_a_measurement_is_still_a_timeout() -> None:
    """A retry's retained heartbeat keeps the measured attempt (FR-015).

    Both shapes are constructed because the repository does not pin which of
    the two Temporal populates: the timeout's own retained details and a
    `TimeoutError` found through its cause chain.
    """
    own_timeout = ActivityTimeoutError(
        "schedule-to-start timeout",
        type=TimeoutType.SCHEDULE_TO_START,
        last_heartbeat_details=_heartbeat_details(_PAYLOAD),
    )
    nested_timeout = ActivityTimeoutError(
        "schedule-to-start timeout",
        type=TimeoutType.SCHEDULE_TO_START,
        last_heartbeat_details=_heartbeat_details(_PAYLOAD),
    )
    outer_timeout = ActivityTimeoutError(
        "schedule-to-start timeout",
        type=TimeoutType.SCHEDULE_TO_START,
        last_heartbeat_details=[],
    )
    outer_timeout.__cause__ = nested_timeout

    own_result = workflow_module.EpicWorkflow()._attempt_timeout(
        _record(), _activity_error(own_timeout)
    )
    chain_result = workflow_module.EpicWorkflow()._attempt_timeout(
        _record(), _activity_error(outer_timeout)
    )

    for result in (own_result, chain_result):
        assert isinstance(result, AdapterResult)
        assert result.termination == Termination.TIMEOUT
        assert result.last_snapshot is not None
        assert result.last_snapshot.spend_usd == 6.25
        assert result.last_snapshot.captured_at == "2026-08-05T09:31:00Z"
