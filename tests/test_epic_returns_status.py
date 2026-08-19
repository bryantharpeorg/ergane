"""US3: `EpicWorkflow.run` returns the `EpicStatus` it declares.

The query (`epic_status`) worked throughout both 2026-08-19 incidents; the
workflow result came back `binary/null`. These tests assert the *returned value*
from `EpicWorkflow.run`, not the query, for both completed and killed
conclusions.

The tests are written first and must fail against the unfixed behaviour
(T021 / US3-S4). The output of that failing run is committed alongside the
test as evidence.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.workgraph.models import EpicState
from factory.workgraph.workflow import EpicInput, EpicStatus, EpicWorkflow

from tests.test_interpreter import (
    EPIC_ID,
    FEATURE,
    PROXY_URL,
    SPECS_ROOT,
    TARGET_REPO,
    TASK_QUEUE,
    WORKFLOW_ID,
    ScriptedWorld,
    all_passing,
    exhausted,
    one_node,
)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@asynccontextmanager
async def _run_epic(
    env: WorkflowEnvironment,
    script: ScriptedWorld,
    **overrides: Any,
) -> AsyncIterator[Any]:
    """Start the epic and hold the worker open while the test steers it."""
    request: dict[str, Any] = {
        "graph": one_node(),
        "proxy_url": PROXY_URL,
    }
    request.update(overrides)

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow],
        activities=script.activities(),
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(**request),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        yield handle


async def test_epic_run_returns_epic_status_completed(
    env: WorkflowEnvironment,
) -> None:
    """US3-S1: the workflow's returned value is an EpicStatus with epic_state COMPLETED.

    This asserts the *result* of `EpicWorkflow.run`, not the `epic_status` query.
    The query has worked throughout both incidents; the return was `binary/null`.
    """
    script = ScriptedWorld(all_passing(), client=env.client)
    async with _run_epic(env, script) as handle:
        result = await handle.result()

    assert result is not None, "workflow result is None (US3 regression)"
    assert type(result) is EpicStatus, (
        f"expected EpicStatus, got {type(result).__name__}: {result!r}"
    )
    assert result.epic_state is EpicState.COMPLETED
    assert result.nodes["us1"].state.name == "MERGED"


async def test_epic_run_returns_epic_status_killed(
    env: WorkflowEnvironment,
) -> None:
    """US3-S2: the workflow's returned value is an EpicStatus with epic_state KILLED.

    Both branches of `run`'s final `if` reach the same return
    (`factory/workgraph/workflow.py:811`). Killing the epic exercises the other
    branch and pins that the return value survives it too.
    """
    script = exhausted("KILL", env.client)
    async with _run_epic(env, script) as handle:
        # Signal kill while the first node is in flight. The scripted agent sends
        # the signal from inside the attempt, which is the same timing the
        # existing interpreter tests use for the kill path.
        await env.client.get_workflow_handle(WORKFLOW_ID).signal("kill_epic")
        result = await handle.result()

    assert result is not None, "workflow result is None (US3 regression)"
    assert type(result) is EpicStatus, (
        f"expected EpicStatus, got {type(result).__name__}: {result!r}"
    )
    assert result.epic_state is EpicState.KILLED
