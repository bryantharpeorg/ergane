"""The production capacity read against a real Temporal namespace (FR-002).

The roadmap's `count_open_epics` delegates to `_open_epics_provider`, which in
production is `_list_open_epics`. The time-skipping workflow tests replace
that provider with a scripted set (`tests/test_roadmap_scheduler.py`), so they
never exercise the real visibility query. This file closes that gap: it calls
the production read directly against the `factory` namespace, with real
workflows started and stopped, and asserts the query behaves as FR-001
requires.

Like `test_live_judge.py`, this lives in the live tier: it skips with a named
reason when no Temporal server answers, and it does not make the offline suite
red. Mark `live_capacity` selects it; `-m "not live_capacity"` deselects it.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from temporalio import workflow
from temporalio.client import Client
from temporalio.service import RPCError
from temporalio.testing import ActivityEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities import roadmap_activities
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.workgraph.workflow import TASK_QUEUE

pytestmark = pytest.mark.live_capacity

#: Seconds to wait for visibility to converge after a workflow starts. Temporal
#: advanced visibility indexing is near-real-time locally; a short wait is
#: enough to make the test deterministic without masking the defect.
_VISIBILITY_SETTLE_SECONDS = 5.0

#: A trivial workflow we can start under controlled ids to observe the capacity
#: read. It must run long enough to be listed as RUNNING, then complete on cue.
@workflow.defn(name="CapacityProbeWorkflow")
class _CapacityProbeWorkflow:
    def __init__(self) -> None:
        self._release = False

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: self._release)
        return "released"

    @workflow.signal
    def release(self) -> None:
        self._release = True


async def _live_client() -> Client:
    """Connect to the operator's Temporal, or skip with a named reason."""
    address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    try:
        return await Client.connect(address, namespace=namespace)
    except OSError as exc:
        pytest.skip(
            f"live capacity read needs a Temporal server at {address} "
            f"(namespace {namespace!r}); could not connect: {exc}"
        )
    except RPCError as exc:
        pytest.skip(
            f"live capacity read needs a reachable Temporal namespace "
            f"{namespace!r} at {address}; RPC failed: {exc}"
        )


@asynccontextmanager
async def _probe_worker(client: Client):
    """Serve the probe workflow so signals complete it against the real server."""
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[_CapacityProbeWorkflow],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        yield


def _probe_id(prefix: str) -> str:
    """Unique, human-readable id for a throwaway probe workflow."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _start_probe(
    client: Client, workflow_id: str
) -> object:
    """Start a probe workflow and return its handle."""
    return await client.start_workflow(
        _CapacityProbeWorkflow.run,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )


async def _running_ids(client: Client) -> set[str]:
    """Call the production capacity read in an activity context and return ids."""
    env = ActivityEnvironment(client=client)
    return await env.run(roadmap_activities._list_open_epics)


async def test_capacity_read_finds_open_epic_workflows_and_excludes_others() -> None:
    """FR-001 / acceptance 1: the production read returns open `epic-*` ids.

    Starts one RUNNING workflow under an `epic-` id and one under a non-epic
    id; the capacity read must include the epic-prefixed id and exclude the
    other. A closed workflow is started under an `epic-` id and released, and
    the next capacity read must not include it.
    """
    client = await _live_client()

    async with _probe_worker(client):
        epic_open_id = _probe_id("epic-capacity-open")
        non_epic_id = _probe_id("capacity-non-epic")
        epic_closed_id = _probe_id("epic-capacity-closed")

        open_handle = await _start_probe(client, epic_open_id)
        non_epic_handle = await _start_probe(client, non_epic_id)
        closed_handle = await _start_probe(client, epic_closed_id)

        try:
            # Give visibility a moment to index all three RUNNING executions.
            await asyncio.sleep(_VISIBILITY_SETTLE_SECONDS)

            found = await _running_ids(client)
            assert epic_open_id in found, (
                f"capacity read did not find the open epic workflow {epic_open_id!r}; "
                f"found {sorted(found)}"
            )
            assert non_epic_id not in found, (
                f"capacity read included non-epic workflow {non_epic_id!r}; "
                f"found {sorted(found)}"
            )
            assert epic_closed_id in found, (
                f"closed workflow {epic_closed_id!r} should appear as RUNNING before "
                f"it is released; found {sorted(found)}"
            )

            # Complete the closed probe and confirm it drops out.
            await closed_handle.signal(_CapacityProbeWorkflow.release)
            await closed_handle.result()

            await asyncio.sleep(_VISIBILITY_SETTLE_SECONDS)
            found_after_close = await _running_ids(client)
            assert epic_open_id in found_after_close, (
                f"capacity read lost the still-open epic workflow {epic_open_id!r} "
                f"after closing another; found {sorted(found_after_close)}"
            )
            assert epic_closed_id not in found_after_close, (
                f"completed epic workflow {epic_closed_id!r} still counted as open; "
                f"found {sorted(found_after_close)}"
            )
            assert non_epic_id not in found_after_close, (
                f"non-epic workflow {non_epic_id!r} included in read; "
                f"found {sorted(found_after_close)}"
            )
        finally:
            # Clean up the deliberately held-open probes.
            await open_handle.signal(_CapacityProbeWorkflow.release)
            await open_handle.result()
            await non_epic_handle.signal(_CapacityProbeWorkflow.release)
            await non_epic_handle.result()


async def test_capacity_read_fails_under_shipped_uppercase_spelling() -> None:
    """Acceptance 2: the live test fails when the query is reverted.

    This is the regression guard. If the visibility query is changed back to
    the uppercase `ExecutionStatus = "RUNNING"` that shipped, the read must
    raise. A test that passes under both spellings has not covered the defect.
    """
    client = await _live_client()

    # Temporarily patch the production provider to use the shipped, broken query.
    original_provider = roadmap_activities._open_epics_provider

    async def _reverted_read() -> set[str]:
        open_ids: set[str] = set()
        async for execution in client.list_workflows(
            'ExecutionStatus = "RUNNING"'
        ):
            if execution.id.startswith("epic-"):
                open_ids.add(execution.id)
        return open_ids

    roadmap_activities._open_epics_provider = _reverted_read
    try:
        env = ActivityEnvironment(client=client)
        with pytest.raises(RPCError, match=r"invalid ExecutionStatus value 'RUNNING'"):
            await env.run(roadmap_activities.count_open_epics, None)
    finally:
        roadmap_activities._open_epics_provider = original_provider
