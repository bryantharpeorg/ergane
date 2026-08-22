"""The seam where a completed workflow's result reaches its parent.

`factory/worker.py` wires one interceptor into every production worker, and its
inbound `execute_workflow` used to `await self.next.execute_workflow(input)`
without returning it — so every workflow this worker ran completed with `None`
no matter what its code returned. The parent sees the loss, never the child: a
roadmap awaiting an epic reads a discarded child result, an epic awaiting a
question reads `.answered` off `None`.

Three earlier test files stopped short of this. `tests/test_worker.py` builds
the production worker and proves it *polls*, never that a workflow run through
it keeps its answer. `tests/test_epic_returns_status.py` executes `EpicWorkflow`
to completion and asserts the returned `EpicStatus` — but on a hand-rolled
worker with no interceptors, so it passed against the broken tree the whole
time (its own `..._red_run.log` records the failed reproduction).

So the claim here is deliberately not "the interceptor returns its value" — it
is **what a client observes through the interceptor list `build_worker`
actually wires**. The list is read off `build_worker(env.client).config()`
rather than by importing the private interceptor class, because the wired list
is the contract and the private name is not; a future interceptor added to
`build_worker` that swallows results fails this test without anyone editing it.

The workflows executed are test-local echoes, not production ones: the
interceptor is type-agnostic past its `EpicWorkflow` injection branch, so an
echo exercises the exact seam, while `EpicWorkflow` and its siblings would
schedule real activities (Telegram sends, agent spawns) the moment they ran.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
from temporalio import workflow as workflow_api
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

import factory.worker as worker_module

#: A scratch queue, never `factory.workgraph.workflow.TASK_QUEUE`: nothing here
#: should be reachable by, or reach, a real epic's registration.
SCRATCH_QUEUE = "test-a-completed-workflow-keeps-its-result"

#: The value the echo workflow returns. Non-None, and structured enough that
#: "the client observed the workflow's own value" cannot be confused with "the
#: client observed some truthy default".
ECHO_RESULT = {"epic": "086", "kept": True}


@workflow_api.defn(name="ResultKeepingEchoWorkflow")
class _EchoWorkflow:
    """Returns what it was told to, and touches nothing else."""

    @workflow_api.run
    async def run(self, value: dict[str, Any]) -> dict[str, Any]:
        return value


@workflow_api.defn(name="ResultKeepingNoneWorkflow")
class _NoneWorkflow:
    """Genuinely returns None — the control for the fix."""

    @workflow_api.run
    async def run(self) -> None:
        return None


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


def _production_interceptors(env: WorkflowEnvironment) -> list[Any]:
    """The interceptor list `build_worker` wires, lifted off its own construction.

    `tests/test_worker.py:368-369`'s pattern: construct the production worker,
    read `config()`. Nothing about the private interceptor class is named.
    """
    built = worker_module.build_worker(env.client)
    interceptors = list(built.config()["interceptors"])
    assert interceptors, "build_worker wires no interceptors — the seam moved"
    return interceptors


def _scratch_worker(env: WorkflowEnvironment) -> Worker:
    """A minimal worker carrying the production interceptors and nothing else."""
    return Worker(
        env.client,
        task_queue=SCRATCH_QUEUE,
        workflows=[_EchoWorkflow, _NoneWorkflow],
        interceptors=_production_interceptors(env),
        workflow_runner=UnsandboxedWorkflowRunner(),
    )


async def test_the_client_observes_the_value_the_workflow_returned(
    env: WorkflowEnvironment,
) -> None:
    """US1-S1 / FR-002: a non-None result survives the production interceptor list."""
    async with _scratch_worker(env):
        observed = await env.client.execute_workflow(
            _EchoWorkflow.run,
            ECHO_RESULT,
            id="result-kept-echo",
            task_queue=SCRATCH_QUEUE,
        )
    assert observed == ECHO_RESULT


async def test_a_workflow_that_returns_none_is_observed_as_none(
    env: WorkflowEnvironment,
) -> None:
    """US1-S2 / FR-003: the control.

    This passes before and after the fix, and that is the point of committing
    it: with the round-trip test beside it, a null result observed by a parent
    from here on means the workflow said `None`, never that the worker lost the
    answer on the way back.
    """
    async with _scratch_worker(env):
        observed = await env.client.execute_workflow(
            _NoneWorkflow.run,
            id="result-kept-none",
            task_queue=SCRATCH_QUEUE,
        )
    assert observed is None
