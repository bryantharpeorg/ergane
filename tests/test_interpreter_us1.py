"""tests for US1 of epic 010-interpreter-bugfixes.

Fixes the scheduler reaper so that when a node coroutine raises an unhandled
exception, the node ends in state KILLED, records the exception text in a new
terminal_reason field, locks out dependent nodes, and leaves every other in-flight
node untouched.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from temporalio import workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.workgraph.workflow import EpicWorkflow, EpicInput
from factory.workgraph.models import WorkGraph, EpicState, NodeState
from factory.verify.models import VerificationConfig
from factory.mergequeue.models import LandingConfig

TASK_QUEUE = "workgraph"
PROXY_URL = "http://litellm.test"

_original_run_node = EpicWorkflow._run_node


# Reconstruct nested dataclasses because subclass workflow receives raw dict.
def _reconstruct_request(raw):
    if not isinstance(raw, dict):
        return raw
    graph = WorkGraph(**raw["graph"])
    config = VerificationConfig(**raw.get("config", {}))
    landing_config = LandingConfig(**raw.get("landing_config", {}))
    kwargs = dict(raw)
    kwargs.update(graph=graph, config=config, landing_config=landing_config)
    return EpicInput(**kwargs)


def _reconstruct_status(raw):
    from factory.workgraph.workflow import EpicStatus, NodeStatus

    if isinstance(raw, EpicStatus):
        return raw
    nodes = {k: NodeStatus(**v) for k, v in raw["nodes"].items()}
    return EpicStatus(epic_state=EpicState(raw["epic_state"]), nodes=nodes)


async def _crashing_run_node(self, resolved, request, sources, judge):
    if resolved.node.id == "us1":
        raise RuntimeError("simulated node crash")
    return await _original_run_node(self, resolved, request, sources, judge)


async def _normal_run_node(self, resolved, request, sources, judge):
    return await _original_run_node(self, resolved, request, sources, judge)


@workflow.defn
class _CrashingEpicWorkflow(EpicWorkflow):
    _run_node = _crashing_run_node

    @workflow.run
    async def run(self, request):
        request = _reconstruct_request(request)
        return await super().run(request)


@workflow.defn
class _NormalEpicWorkflow(EpicWorkflow):
    _run_node = _normal_run_node

    @workflow.run
    async def run(self, request):
        request = _reconstruct_request(request)
        return await super().run(request)


@pytest.fixture
async def env():
    e = await WorkflowEnvironment.start_time_skipping()
    try:
        yield e
    finally:
        await e.shutdown()


@asynccontextmanager
async def _start_epic(
    env: WorkflowEnvironment,
    script,
    workflow_cls,
    *,
    graph=None,
    workflow_id: str = "epic-us1",
    **input_overrides: Any,
):
    from tests.test_interpreter import EpicInput as TestEpicInput

    request = {"graph": graph, "proxy_url": PROXY_URL}
    request.update(input_overrides)
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[workflow_cls],
        activities=script.activities(),
        max_heartbeat_throttle_interval=timedelta(seconds=5),
        default_heartbeat_throttle_interval=timedelta(seconds=5),
    ):
        handle = await env.client.start_workflow(
            workflow_cls.run,
            TestEpicInput(**request),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
        script.handle = handle
        yield handle


async def _run_epic(
    env, script, workflow_cls, *, workflow_id, graph=None, **overrides
):
    async with _start_epic(
        env,
        script,
        workflow_cls,
        graph=graph,
        workflow_id=workflow_id,
        **overrides,
    ) as handle:
        return _reconstruct_status(await handle.result())


def _make_crashing_graph():
    from tests.test_interpreter import make_graph, make_node

    return make_graph(
        [
            make_node("us1", "US1"),
            make_node("us2", "US2", depends_on=["us1"]),
            make_node("us3", "US3"),
        ]
    )


# T003
async def test_unhandled_node_exception_kills_node(env):
    from tests.test_interpreter import ScriptedWorld, passing

    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    status = await _run_epic(
        env,
        script,
        _CrashingEpicWorkflow,
        graph=_make_crashing_graph(),
        max_concurrent_nodes=1,
        workflow_id="epic-us1-t003",
    )
    assert status.nodes["us1"].state == NodeState.KILLED
    assert "simulated node crash" in status.nodes["us1"].terminal_reason


# T004
async def test_unhandled_exception_locks_out_dependents(env):
    from tests.test_interpreter import ScriptedWorld, passing

    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    status = await _run_epic(
        env,
        script,
        _CrashingEpicWorkflow,
        graph=_make_crashing_graph(),
        max_concurrent_nodes=1,
        workflow_id="epic-us1-t004",
    )
    assert status.nodes["us2"].state == NodeState.KILLED


# T005
async def test_unhandled_exception_leaves_other_nodes_untouched(env):
    from tests.test_interpreter import ScriptedWorld, passing

    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    status = await _run_epic(
        env,
        script,
        _CrashingEpicWorkflow,
        graph=_make_crashing_graph(),
        max_concurrent_nodes=2,
        workflow_id="epic-us1-t005",
    )
    assert status.nodes["us3"].state == NodeState.MERGED
    assert status.nodes["us1"].state == NodeState.KILLED


# T006
async def test_unhandled_exception_during_pause_drains_cleanly(env):
    from tests.test_interpreter import ScriptedWorld, passing, PAUSE_SIGNAL

    # Crash us1; pause while us3 is in flight. The pause is raised from inside
    # us3's run_agent_attempt activity, so us3 is genuinely in flight.
    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
        signal_during={"us3": PAUSE_SIGNAL},
    )
    async with _start_epic(
        env,
        script,
        _CrashingEpicWorkflow,
        graph=_make_crashing_graph(),
        max_concurrent_nodes=2,
        workflow_id="epic-us1-t006",
    ) as handle:
        import asyncio

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10.0
        while True:
            raw = await handle.query(_CrashingEpicWorkflow.epic_status)
            status = _reconstruct_status(raw)
            if status.epic_state == EpicState.PAUSED:
                break
            if loop.time() >= deadline:
                raise AssertionError("timed out waiting for pause")
            await asyncio.sleep(0.05)

    # After pause, us1 is KILLED by the crash, us2 is KILLED by lock-out, and
    # us3 is paused mid-attempt (still in flight and not terminal).
    assert status.nodes["us1"].state == NodeState.KILLED
    assert status.nodes["us1"].terminal_reason == "simulated node crash"
    assert status.nodes["us2"].state == NodeState.KILLED
    assert status.nodes["us3"].state not in {NodeState.KILLED, NodeState.MERGED, NodeState.FAILED}


# T007
async def test_no_op_when_no_unhandled_exceptions(env):
    from tests.test_interpreter import ScriptedWorld, passing

    script = ScriptedWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    status = await _run_epic(
        env,
        script,
        _NormalEpicWorkflow,
        graph=_make_crashing_graph(),
        max_concurrent_nodes=1,
        workflow_id="epic-us1-t007",
    )
    assert status.epic_state == EpicState.COMPLETED
    assert all(n.state == NodeState.MERGED for n in status.nodes.values())
    assert all(n.terminal_reason is None for n in status.nodes.values())
