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
