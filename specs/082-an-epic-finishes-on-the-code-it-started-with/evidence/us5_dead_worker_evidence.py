"""T033 / SC-002: SIGKILL a worker mid-attempt and time the replacement.

    uv run python specs/082-an-epic-finishes-on-the-code-it-started-with/evidence/us5_dead_worker_evidence.py

Its stdout is pasted into `us5-t033-dead-worker.md`. A script and not a test
because SC-002 asks for *wall-clock output* against a real server, and the judge
sees only the diff (constitution VIII): committing it beside the output is what
lets anyone re-run it and get the same page.

Two deliberate departures from the acceptance scenario's literal wording, both
because this node is itself an attempt running on the floor it would be killing:

  * the worker killed is a **subprocess this script starts**, not
    `ergane-worker.service`. SIGKILLing the unit would kill the activity running
    this very agent, reschedule this node, and reap the process writing these
    words. The mechanism under test is identical — an uncleanly killed worker
    stops heartbeating and the server times the activity out — and the worker
    started here is configured with the production heartbeat cadence
    (`factory.worker._heartbeat_cadence_limits`), which is what decides how
    stale the server's last beat is when the kill lands.
  * namespace `default`, never `factory`: that namespace holds the epic that
    dispatched this node, and evidence must not appear where an operator reads
    for real (the shape 079's US2 evidence established).

The heartbeat timeout is not a number typed here. It comes from the shipped
`_agent_heartbeat_timeout`, called on a four-hour attempt deadline, and is
printed beside what the same call returned before this story capped it.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from temporalio import activity, workflow  # noqa: E402
from temporalio.client import Client  # noqa: E402
from temporalio.common import RetryPolicy  # noqa: E402

LIVE_TEMPORAL = "127.0.0.1:7233"
LIVE_NAMESPACE = "default"

#: The attempt this story exists for: a multi-hour deadline, the shape the
#: shipped implementer persona hands the adapter.
DEADLINE_S = 4 * 60 * 60

#: How long the parent will wait for the replacement before calling the run a
#: failure. Comfortably past the cap, far short of the 2h baseline.
PATIENCE_S = 300


@activity.defn(name="run_agent_attempt_probe")
async def run_agent_attempt_probe() -> str:
    """Stands in for the agent: beats on wall clock and never finishes.

    The real pump beats the same way and is not output-gated
    (`factory/activities/agent_activities.py`), which is why a tight timeout is
    safe from a quiet agent — only a dead *worker* stops these.
    """
    while True:
        activity.heartbeat("alive")
        await asyncio.sleep(1.0)


@workflow.defn(name="HeartbeatCapProbe")
class HeartbeatCapProbe:
    @workflow.run
    async def run(self, heartbeat_timeout_s: float) -> str:
        return await workflow.execute_activity(
            "run_agent_attempt_probe",
            start_to_close_timeout=timedelta(seconds=DEADLINE_S),
            heartbeat_timeout=timedelta(seconds=heartbeat_timeout_s),
            # `_AGENT_RETRIES`' shape: one replacement attempt, which is the one
            # being timed. Untouched by this story (plan trap 9).
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


async def _serve(task_queue: str) -> None:
    """The worker half: run until SIGKILLed, with the production beat cadence."""
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker

    from factory.worker import _heartbeat_cadence_limits

    client = await Client.connect(LIVE_TEMPORAL, namespace=LIVE_NAMESPACE)
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[HeartbeatCapProbe],
        activities=[run_agent_attempt_probe],
        # This file re-imports itself in the worker subprocess and the sandbox
        # refuses its module-level `Path.resolve`. Determinism is not what is
        # being measured here, so the sandbox is not what is wanted.
        workflow_runner=UnsandboxedWorkflowRunner(),
        **_heartbeat_cadence_limits(),
    ):
        print(f"worker up on {task_queue}", flush=True)
        await asyncio.Event().wait()


def _spawn_worker(task_queue: str) -> subprocess.Popen[bytes]:
    """Its own session, so the kill below is a process *group* kill — an
    uncleanly dead worker host, not a polite shutdown."""
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--serve", task_queue],
        start_new_session=True,
    )


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _pending(description) -> object | None:
    activities = description.raw_description.pending_activities
    return activities[0] if activities else None


async def _await_pending(handle, predicate, what: str):
    deadline = asyncio.get_running_loop().time() + PATIENCE_S
    while asyncio.get_running_loop().time() < deadline:
        pending = _pending(await handle.describe())
        if pending is not None and predicate(pending):
            return pending
        await asyncio.sleep(0.5)
    raise SystemExit(f"timed out after {PATIENCE_S}s waiting for {what}")


async def main() -> None:
    from factory.workgraph.workflow import (
        _AGENT_HEARTBEAT_TIMEOUT_CEILING,
        _AGENT_HEARTBEAT_TIMEOUT_FLOOR,
        _agent_heartbeat_timeout,
    )

    capped = _agent_heartbeat_timeout(DEADLINE_S)
    uncapped = max(timedelta(seconds=DEADLINE_S / 2), _AGENT_HEARTBEAT_TIMEOUT_FLOOR)
    print(f"attempt deadline                     {DEADLINE_S}s (4h)")
    print(f"heartbeat timeout, before this story {uncapped.total_seconds():.0f}s")
    print(f"heartbeat timeout, shipped derivation {capped.total_seconds():.0f}s"
          f" (cap {_AGENT_HEARTBEAT_TIMEOUT_CEILING.total_seconds():.0f}s)")

    run_id = uuid.uuid4().hex[:8]
    task_queue = f"us5-heartbeat-cap-{run_id}"
    client = await Client.connect(LIVE_TEMPORAL, namespace=LIVE_NAMESPACE)
    handle = await client.start_workflow(
        HeartbeatCapProbe.run,
        capped.total_seconds(),
        id=f"us5-heartbeat-cap-{run_id}",
        task_queue=task_queue,
    )

    victim = _spawn_worker(task_queue)
    replacement: subprocess.Popen[bytes] | None = None
    try:
        first = await _await_pending(
            handle, lambda p: p.attempt == 1 and p.HasField("last_heartbeat_time"),
            "the first attempt to start beating",
        )
        beat = first.last_heartbeat_time.ToDatetime(tzinfo=timezone.utc)
        print(f"\nlast heartbeat the server received   {_stamp(beat)}  (attempt 1)")

        os.killpg(os.getpgid(victim.pid), signal.SIGKILL)
        killed = datetime.now(timezone.utc)
        victim.wait(timeout=30)
        print(f"SIGKILL delivered to the worker      {_stamp(killed)}"
              f"  (exit {victim.returncode})")

        # A worker has to exist for the replacement to *run*; systemd's
        # Restart=on-failure is what does this in production. It cannot make the
        # server declare attempt 1 dead any sooner — only the heartbeat timeout
        # does that — so the interval below is the timeout's, not the restart's.
        replacement = _spawn_worker(task_queue)

        second = await _await_pending(
            handle, lambda p: p.attempt == 2, "the replacement attempt"
        )
        scheduled = second.scheduled_time.ToDatetime(tzinfo=timezone.utc)
        print(f"replacement attempt scheduled        {_stamp(scheduled)}  (attempt 2)")

        gap = (scheduled - killed).total_seconds()
        print(f"\nkill -> replacement scheduled        {gap:.1f}s")
        print(f"2026-08-19 baseline (half of 4h)     {uncapped.total_seconds():.0f}s")
        print(f"within the 3-minute bound            {gap <= 180}")
    finally:
        await handle.terminate(reason="probe complete")
        for process in (victim, replacement):
            if process is not None and process.poll() is None:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--serve":
        asyncio.run(_serve(sys.argv[2]))
    else:
        asyncio.run(main())
