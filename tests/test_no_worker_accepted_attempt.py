"""US1: an attempt no worker accepts ends and names the reason.

The scheduled activity is read directly from one epic's recorded history
because a worker never accepting a task cannot be reproduced in this harness;
the test pins the option that makes Temporal report the missing acceptance.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.workgraph import workflow as workflow_module
from factory.workgraph.models import WorkGraph

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
