"""Temporary evidence capture for US1; removed after the committed artifact."""
from typing import Any
from datetime import timedelta
from temporalio.testing import WorkflowEnvironment
from temporalio.exceptions import ActivityError, TimeoutError as ActivityTimeoutError, TimeoutType
from factory.verify.models import EscalationChoice
from factory.mergequeue.models import LandingState
from factory.activities.agent_activities import AGENT_LAUNCH_FAILED
from factory.workgraph import workflow as workflow_module
from tests.test_interpreter import (
    ScriptedWorld, checks_failed_snapshot, env, failing, make_graph, make_node,
    one_node, passing, run_epic,
)
from tests.test_launch_is_not_an_attempt import launch_world

PAYLOAD = {"spend_usd": 6.25, "captured_at": "2026-08-05T09:31:00Z"}

def activity_error(timeout):
    exc = ActivityError("Activity task failed", scheduled_event_id=1, started_event_id=1,
                        identity="", activity_type="run_agent_attempt", activity_id="us1",
                        retry_state=None)
    exc.__cause__ = timeout
    return exc

async def test_capture_us1_evidence(env: WorkflowEnvironment) -> None:
    graph = make_graph([make_node("us1", "US1", timeout_override_s=12),
                        make_node("us2", "US2", timeout_override_s=1200)])
    script = ScriptedWorld({"us1": [passing()], "us2": [passing()]}, client=env.client)
    await run_epic(env, script, graph=graph)
    history = await script.handle.fetch_history()
    print("=== SCHEDULED EVENTS ===")
    for event in history.events:
        attrs = event.activity_task_scheduled_event_attributes
        if event.event_type != 10 or attrs.activity_type.name != "run_agent_attempt":
            continue
        print(
            "activity_type=run_agent_attempt "
            f"schedule_to_start_timeout={attrs.schedule_to_start_timeout.ToTimedelta()} "
            f"heartbeat_timeout={attrs.heartbeat_timeout.ToTimedelta()} "
            f"start_to_close_timeout={attrs.start_to_close_timeout.ToTimedelta()}"
        )

    adapter = workflow_module._LaunchFailed("no agent binary found for persona", fault=AGENT_LAUNCH_FAILED)
    no_worker = workflow_module._LaunchFailed(
        "no worker accepted the scheduled attempt", fault=workflow_module._NO_AGENT_STARTED)
    print("=== TERMINAL REASONS ===")
    print("adapter=_launch_failed_reason(adapter, 2) ->",
          repr(workflow_module._launch_failed_reason(adapter, 2)))
    print("no_worker=_launch_failed_reason(no_worker, 1) ->",
          repr(workflow_module._launch_failed_reason(no_worker, 1)))

    print("=== TIMEOUT CLASSIFICATION ===")
    own = ActivityTimeoutError("schedule-to-start timeout", type=TimeoutType.SCHEDULE_TO_START,
                               last_heartbeat_details=[PAYLOAD])
    nested = ActivityTimeoutError("schedule-to-start timeout", type=TimeoutType.SCHEDULE_TO_START,
                                  last_heartbeat_details=[PAYLOAD])
    outer = ActivityTimeoutError("schedule-to-start timeout", type=TimeoutType.SCHEDULE_TO_START,
                                 last_heartbeat_details=[])
    outer.__cause__ = nested
    result = workflow_module.EpicWorkflow()._attempt_timeout(
        workflow_module.NodeRecord(node_id="us1", branch="factory/demo-loans/us1"),
        activity_error(own))
    print("with_measurement=AdapterResult ->", repr(result))
    empty = ActivityTimeoutError("schedule-to-start timeout", type=TimeoutType.SCHEDULE_TO_START,
                                 last_heartbeat_details=[])
    try:
        workflow_module.EpicWorkflow()._attempt_timeout(
            workflow_module.NodeRecord(node_id="us1", branch="factory/demo-loans/us1"),
            activity_error(empty))
    except workflow_module._LaunchFailed as exc:
        print("without_measurement=raises ->", repr(exc))
    else:
        raise AssertionError("empty timeout did not raise")

    recovery_script = ScriptedWorld(
        {"us1": [passing(), failing(2)]}, client=env.client,
        press=EscalationChoice.KILL.value)
    recovery_script.script_landing("us1", checks_failed_snapshot(), checks_failed_snapshot())
    recovery_script.script_sync("us1", clean=True, base_ref="c0ffee")
    original_attempt = workflow_module.EpicWorkflow._attempt

    async def recovery_attempt_raises(*args: Any, **kwargs: Any):
        if args[2].attempt == 2:
            raise workflow_module._LaunchFailed(
                "no worker accepted the scheduled attempt",
                fault=workflow_module._NO_AGENT_STARTED)
        return await original_attempt(*args, **kwargs)

    workflow_module.EpicWorkflow._attempt = recovery_attempt_raises
    try:
        recovery_status = await run_epic(env, recovery_script, graph=one_node())
    finally:
        workflow_module.EpicWorkflow._attempt = original_attempt
    recovery_teardowns = [t for t in recovery_script.teardowns
                          if t.lease.node_id == "us1" and t.lease.attempt == 2]
    print("=== RECOVERY ENDING ===")
    print("escalation_count=", len(recovery_script.escalation_requests))
    print("landing_state=", recovery_status.nodes["us1"].landing_state)
    print("terminal_reason=", repr(recovery_status.nodes["us1"].terminal_reason))
    print("recovery_teardown_count=", len(recovery_teardowns))
