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
import socket
import time
import uuid
from collections.abc import Callable
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

#: Maximum time to spend polling visibility until the expected condition holds.
#: Kept short because the local dev-server index is near-real-time; the old fixed
#: 5-second sleep paid the full budget every call and pushed this live test over
#: 15 seconds. Polling moves the common case to milliseconds while keeping a
#: bounded timeout.
_VISIBILITY_POLL_TIMEOUT_SECONDS = 3.0
_VISIBILITY_POLL_INTERVAL_SECONDS = 0.2

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


@workflow.defn(name="CapacityContinueAsNewProbeWorkflow")
class _ContinueAsNewProbeWorkflow:
    """Probe that continues-as-new once, then waits for a release signal.

    The original run ends with status ``CONTINUED_AS_NEW``; the new run keeps
    the same workflow id and becomes ``RUNNING``. This lets the live test prove
    the capacity read does not count a continued-as-new execution as open once
    the chain finishes.
    """

    def __init__(self) -> None:
        self._release = False

    @workflow.run
    async def run(self, iteration: int = 0) -> str:
        if iteration == 0:
            workflow.continue_as_new(1)
        await workflow.wait_condition(lambda: self._release)
        return "released"

    @workflow.signal
    def release(self) -> None:
        self._release = True


def _parse_address(address: str) -> tuple[str, int]:
    """Split ``host:port``; default to the Temporal dev-server port."""
    if ":" in address:
        host, port_str = address.rsplit(":", 1)
        return host, int(port_str)
    return address, 7233


def _temporal_reachable(address: str) -> bool:
    """Positive reachability probe: open a TCP socket to the gRPC port.

    A guard that enumerates exception types misses the next SDK release.
    A socket probe catches every "no server there" failure mode, including the
    ``RuntimeError`` the Temporal Python SDK raises against a refused port.
    """
    host, port = _parse_address(address)
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


async def _live_client() -> Client:
    """Connect to the operator's Temporal, or skip with a named reason."""
    address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    if not _temporal_reachable(address):
        pytest.skip(
            f"live capacity read needs a Temporal server at {address} "
            f"(namespace {namespace!r}); the port is unreachable"
        )
    try:
        return await Client.connect(address, namespace=namespace)
    except (OSError, RuntimeError) as exc:
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
        workflows=[_CapacityProbeWorkflow, _ContinueAsNewProbeWorkflow],
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


async def _start_can_probe(client: Client, workflow_id: str) -> object:
    """Start the continue-as-new probe at iteration 0 and return its handle."""
    return await client.start_workflow(
        _ContinueAsNewProbeWorkflow.run,
        id=workflow_id,
        arg=0,
        task_queue=TASK_QUEUE,
    )


async def _running_ids(client: Client) -> set[str]:
    """Call the production capacity read in an activity context and return ids."""
    env = ActivityEnvironment(client=client)
    return await env.run(roadmap_activities._list_open_epics)


async def _running_ids_when(
    client: Client,
    predicate: Callable[[set[str]], bool],
    timeout: float = _VISIBILITY_POLL_TIMEOUT_SECONDS,
) -> set[str]:
    """Poll the production capacity read until ``predicate`` is satisfied.

    The local Temporal dev server's advanced-visibility index updates in tens
    to hundreds of milliseconds; a fixed sleep of several seconds is wasteful
    and pushed this live test over the suite's 15-second budget. This helper
    keeps the test deterministic with a bounded timeout while letting the
    common case complete as soon as visibility converges.
    """
    deadline = time.monotonic() + timeout
    while True:
        found = await _running_ids(client)
        if predicate(found):
            return found
        if time.monotonic() >= deadline:
            assert False, (
                f"visibility predicate not satisfied within {timeout}s; "
                f"found {sorted(found)}"
            )
        await asyncio.sleep(_VISIBILITY_POLL_INTERVAL_SECONDS)


async def test_capacity_seam_is_scriptable() -> None:
    """FR-003 / acceptance 4: the capacity read stays behind a scripted seam.

    Removing ``_open_epics_provider`` would make the time-skipping workflow tests
    red, because the time-skipping server cannot answer the production visibility
    query. This test asserts the seam exists, can be replaced and restored, and
    that ``count_open_epics`` routes through it.
    """
    import factory.activities.roadmap_activities as ra

    original = ra._open_epics_provider

    async def scripted_provider() -> set[str]:
        return {"epic-seam-a", "epic-seam-b"}

    ra._open_epics_provider = scripted_provider
    try:
        result = await ActivityEnvironment().run(
            roadmap_activities.count_open_epics, None
        )
        assert result.open_ids == ("epic-seam-a", "epic-seam-b")
    finally:
        ra._open_epics_provider = original


@pytest.mark.live_capacity
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
            # Wait until visibility indexes all three RUNNING executions.
            found = await _running_ids_when(
                client,
                lambda f: epic_open_id in f
                and non_epic_id not in f
                and epic_closed_id in f,
            )
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

            found_after_close = await _running_ids_when(
                client,
                lambda f: epic_open_id in f
                and epic_closed_id not in f
                and non_epic_id not in f,
            )
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


@pytest.mark.live_capacity
async def test_capacity_read_excludes_continued_as_new_chain() -> None:
    """Acceptance 5: a continued-as-new execution is not counted as open.

    A workflow run that calls ``continue_as_new`` ends with status
    ``CONTINUED_AS_NEW``; the new run keeps the same workflow id. The capacity
    read must not count the finished original run once the new run also
    completes.
    """
    client = await _live_client()

    async with _probe_worker(client):
        can_id = _probe_id("epic-capacity-can")
        can_handle = await _start_can_probe(client, can_id)

        try:
            # The first run continues as new; the second run is RUNNING and
            # waiting on the release signal. Poll until visibility converges.
            found_while_running = await _running_ids_when(
                client, lambda f: can_id in f
            )
            assert can_id in found_while_running, (
                f"capacity read did not find the continued-as-new chain's active "
                f"run {can_id!r}; found {sorted(found_while_running)}"
            )

            # Release the second run and let it complete.
            await can_handle.signal(_ContinueAsNewProbeWorkflow.release)
            await can_handle.result()

            found_after_chain = await _running_ids_when(
                client, lambda f: can_id not in f
            )
            assert can_id not in found_after_chain, (
                f"continued-as-new workflow {can_id!r} still counted as open after "
                f"the chain completed; found {sorted(found_after_chain)}"
            )
        finally:
            # Best-effort cleanup if the test failed mid-chain.
            try:
                await can_handle.signal(_ContinueAsNewProbeWorkflow.release)
                await can_handle.result()
            except Exception:
                pass


@pytest.mark.live_capacity
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
