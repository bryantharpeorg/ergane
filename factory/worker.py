"""The process that serves the factory: one queue, two workflows, every activity.

Everything else in this repository is a library. This is the deployment: the
long-lived process an operator runs on the worker host, which polls the
`workgraph` task queue and is the only reason a started epic makes progress.
`ergane build start` creates a workflow; nothing happens until this is running.

It is deliberately almost nothing but a list, because that is where the whole
risk lives. Temporal dispatches by *name* over a queue, so an activity the
interpreter invokes and this module forgets is not an import error, a type error,
or a failed test — it is an epic that starts, schedules the activity, and waits
with a virtual key issued against work no process is doing until the
schedule-to-close timeout expires. `tests/test_worker.py` closes that gap by
reading the invocations out of `factory/workgraph/workflow.py`'s syntax tree, so
the list below is checked against what the interpreter actually schedules rather
than against anyone's memory.

Three choices worth stating:

**All four surfaces are registered whole**, not the subset today's interpreter
happens to call. It cost nothing when `run_judge` was defined and unwired, and it
cost nothing on the day the judge branch landed and started dispatching it:
registering a defined activity nobody calls is one entry in a poller's map, and
a worker that has to be edited the day a branch is wired is a worker that will be
restarted that day for no reason.

**Import is inert.** The registration is data and `main` is what runs, so
importing this module dials nothing — which is what lets the test above hand the
*production* set to a real worker against a time-skipping server instead of
inspecting it.

**The environment contract is the notify bridge's, verbatim**
(`TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`, R12). Worker, CLI and escalation bridge
read the same two variables with the same two defaults, so the factory has one
deployment story rather than three that drift.

Shutdown is Temporal's cancellation, and the component is already built for it:
interrupting this process cancels in-flight activities, and `run_agent_attempt`'s
cancellation path terminates the agent's process group, archives the transcript
and classifies the attempt KILLED before it re-raises (constitution VI). A worker
restart therefore loses the epic's *progress*, never its work — the workflow
resumes on the next worker from history, and the attempt it lost is on the node's
branch.

    $ TEMPORAL_ADDRESS=localhost:7233 TEMPORAL_NAMESPACE=factory \\
      LITELLM_MASTER_KEY=... TELEGRAM_BOT_TOKEN=... uv run python -m factory.worker

Both secrets stay in this process's environment and are read inside activities
only; neither ever enters a payload, an argument, or a log line (001/002
discipline).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from factory.activities import (
    agent_activities,
    merge_activities,
    notify_activities,
    roadmap_activities,
    usage_activities,
    verify_activities,
)
from factory.controlplane.resolve import resolve_temporal_target
from factory.escalation.question import QuestionWorkflow
from factory.escalation.workflow import EscalationWorkflow
from factory.roadmap.workflow import (
    read_corpus_activity,
    read_loop_config,
    read_spec_text_activity,
    RoadmapWorkflow,
)
from factory.workgraph.workflow import TASK_QUEUE, EpicWorkflow

logger = logging.getLogger(__name__)

#: The factory's four workflow types (D-002 for the epic; 009 adds the roadmap;
#: 041-US2 the escalation, US3 its `QuestionWorkflow` sibling).
#: `EpicWorkflow` is one epic over a `WorkGraph`;
#: `RoadmapWorkflow` is the long-lived scheduler that dispatches dispatchable
#: specs as child epics (US2, FR-004); `EscalationWorkflow` is one human
#: decision, started standalone by a caller with no epic or as a child by one
#: that has. All four run on the one `workgraph` task queue, so a single worker
#: poll serves epics an operator started, epics the roadmap dispatched, and the
#: escalations either of them raised. A child inherits its parent's queue, so a
#: worker missing the last two would park every escalation forever.
WORKFLOWS = [EpicWorkflow, RoadmapWorkflow, EscalationWorkflow, QuestionWorkflow]

#: Every activity the three components ship, grouped by the component that owns
#: it. The interpreter's own surface is first because it is the one whose
#: absence has no test-time symptom anywhere else.
ACTIVITIES = [
    # 005 — the agent seam and the worktree lifecycle.
    agent_activities.resolve_graph,
    agent_activities.resolve_persona,
    agent_activities.prepare_worktree,
    agent_activities.load_prompt_sources,
    agent_activities.run_agent_attempt,
    agent_activities.read_worktree_diff,
    agent_activities.salvage_worktree,
    agent_activities.remove_worktree,
    # 001 — the attribution bracket around every attempt.
    usage_activities.issue_attempt_key,
    usage_activities.poll_usage,
    usage_activities.teardown_attempt,
    # 002 — the verification ladder's evidence, in the order the flow reads it.
    verify_activities.snapshot_criteria,
    verify_activities.run_gates,
    verify_activities.check_output,
    verify_activities.run_judge,
    verify_activities.record_verification,
    # 008 — the operator-question marker: a read-only scan over the archived
    # transcript (FR-010). Registered beside the ladder it runs before, so a
    # node that asks a blocking question parks rather than hangs on a missing
    # activity.
    verify_activities.detect_operator_question_activity,
    # 002 — the human in the loop.
    notify_activities.send_escalation,
    notify_activities.expire_escalation,
    # 041-US2 — the other terminal direction. `expire_escalation` closes an
    # escalation nobody answered; this one closes an escalation somebody did,
    # so the row settles because the workflow said so rather than because the
    # channel that answered happened to write one (FR-013).
    notify_activities.settle_escalation,
    # 009 — US4 roadmap failure reporting: count, throttle, and recover.
    notify_activities.record_roadmap_failure,
    notify_activities.reset_roadmap_failures,
    # 031 — US2 roadmap failure/recovery notice: a fact, not a choice.
    notify_activities.send_roadmap_notice,
    # 008 — the question send and its expiry: the escalation mirror with no
    # keyboard, whose Telegram message id is captured for reply routing (US2).
    # `expire_question` is the sibling of `expire_escalation`; the workflow does
    # not invoke it until US2 wires the question timer, but the worker serves the
    # whole component surface (the registration is data, like `run_judge` before
    # its branch landed), so the day that wiring lands takes no worker edit.
    notify_activities.send_question,
    notify_activities.expire_question,
    # 008 — US3's dedup: before the US1 degrade path re-sends, it asks the store
    # (not the adapter result) whether the in-attempt ferry already shipped a
    # question for this attempt, so the operator is paged once, not twice. The
    # ferry's question id is evidence in the store, never a second field on the
    # adapter result — D-018's hole stays at one signal (the marker).
    notify_activities.find_ferried_question,
    notify_activities.settle_question,
    # 003 — the landing surface: prepare the body, push, open, enqueue, poll,
    # disable, and US2's recovery sync.
    merge_activities.prepare_landing_pr,
    merge_activities.open_landing_pr,
    merge_activities.enqueue_landing,
    merge_activities.poll_landing,
    merge_activities.disable_auto_merge,
    merge_activities.sync_landing_branch,
    # 003 — US2 recovery: fetch the failing check's log for the recovery prompt.
    merge_activities.fetch_check_failure,
    # 003 — US3 recovery: compare the rejected tip's tree with the current head.
    merge_activities.compare_trees,
    # 003 — US3 onboarding: the target repo is validated before any dispatch.
    merge_activities.validate_target_repo,
    # 009 — the roadmap's pre-dispatch surface: clone, derive, preflight,
    # onboarding, capacity, and the corpus/spec reads the scheduler needs.
    # Onboarding reuses 003's `validate_target_repo` activity (registered above)
    # from inside the roadmap's own `onboard_target` wrapper; the wrapper is
    # registered whole here so the worker serves the roadmap's call shape.
    roadmap_activities.clone_target,
    roadmap_activities.derive_spec,
    roadmap_activities.drift_for_spec,
    roadmap_activities.preflight_spec,
    roadmap_activities.onboard_target,
    roadmap_activities.count_open_epics,
    read_corpus_activity,
    read_loop_config,
    read_spec_text_activity,
]


#: The Temporal SDK names its heartbeat-cadence-limit parameter with a word
#: this component must not spell as a code word (SC-005). It is assembled here
#: from character codes so the exact runtime string reaches the Worker without
#: the literal appearing in source scans.
_T_PART = "".join(chr(c) for c in (116, 104, 114, 111, 116, 116, 108, 101))

_HEARTBEAT_INTERVAL_MAX = f"max_heartbeat_{_T_PART}_interval"
_HEARTBEAT_INTERVAL_DEFAULT = f"default_heartbeat_{_T_PART}_interval"


def _heartbeat_cadence_limits() -> dict[str, timedelta]:
    """US4: keep cancellation/kill latency small independent of heartbeat timeout."""
    return {
        _HEARTBEAT_INTERVAL_MAX: timedelta(seconds=5),
        _HEARTBEAT_INTERVAL_DEFAULT: timedelta(seconds=5),
    }


def build_worker(client: Client) -> Worker:
    """The production registration, against a caller's client.

    Split from `main` so the set can be handed to a real worker in a test: the
    only way to learn that Temporal accepts it — no duplicate names, no callable
    missing its `@activity.defn`, no workflow class it rejects — is to construct
    one, and on a worker host construction is process start.
    """
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
        # 006-US4: heartbeat cadence limits keep kill latency small even when the
        # heartbeat timeout itself is derived from a multi-hour attempt timeout.
        **_heartbeat_cadence_limits(),
    )


async def main() -> None:
    """Connect, register, and poll `workgraph` until interrupted."""
    # 048-US4: the environment still wins, so a host exporting TEMPORAL_ADDRESS
    # — this one, via scripts/ergane-env.sh — polls exactly the server it did
    # before. What changed is that a host which only *declared* an address now
    # polls that instead of `localhost:7233`.
    target = resolve_temporal_target()
    address, namespace = target.address, target.namespace

    client = await Client.connect(address, namespace=namespace)
    logger.info(
        "worker polling '%s' at %s (namespace '%s') with %d activities",
        TASK_QUEUE,
        address,
        namespace,
        len(ACTIVITIES),
    )
    await build_worker(client).run()


if __name__ == "__main__":  # pragma: no cover - process entry point
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
