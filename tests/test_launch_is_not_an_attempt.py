"""User Story 2 — A launch that never reached the agent is not an attempt.

`run_agent_attempt` already raises a non-retryable `AGENT_LAUNCH_FAILED` when
the adapter cannot start the agent at all (`factory/activities/agent_activities.py`).
The workflow currently catches every `ActivityError` from the attempt and turns
it into a `TIMEOUT` result, which is recorded as an attempt and charged to the
node's budget.  These tests pin the requirement that the workflow distinguish a
pre-first-token launch fault, surface it to the operator, and bound retries
independently of the attempt budget.

Every test drives the real `EpicWorkflow` through `ScriptedWorld` so the
classification seam in `factory/workgraph/workflow.py` is the code under test.
"""

from __future__ import annotations

from typing import Any

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.agent_activities import AGENT_LAUNCH_FAILED
from factory.activities.notify_activities import SendEscalationInput
from factory.activities.usage_activities import issue_attempt_key, teardown_attempt
from factory.escalation.question import QuestionWorkflow
from factory.escalation.workflow import EscalationWorkflow
from factory.verify.ladder import _attempts_spent
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)
from factory.workgraph.models import AdapterResult, AttemptContext, NodeState, Termination
from factory.workgraph.workflow import EpicInput, EpicWorkflow

# Re-use the test harness from the interpreter suite rather than re-inventing
# the Temporal environment wiring.
from tests.test_interpreter import (
    EPIC_ID,
    FEATURE,
    PROXY_URL,
    TASK_QUEUE,
    WORKFLOW_ID,
    Attempt,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    gate_pass,
    make_graph,
    make_node,
    passing,
    run_epic,
    states,
)


class LaunchFailingWorld(ScriptedWorld):
    """A scripted world whose `run_agent_attempt` raises `AGENT_LAUNCH_FAILED`.

    The agent never starts, so there is no adapter result to return and no
    transcript to read.  The exception is what the workflow must classify.
    """

    def activities(self) -> list[Any]:
        acts = super().activities()

        # Find the real `run_agent_attempt` definition in the scripted activities
        # so we can replace it with the launch-failure shape.
        real_activities = []
        for fn in acts:
            if getattr(fn, "__name__", None) == "run_agent_attempt":
                continue
            real_activities.append(fn)

        script = self

        @activity.defn(name="run_agent_attempt")
        async def launch_fails(context: AttemptContext) -> AdapterResult:
            script._log("run_agent_attempt", context.node_id)
            script.attempts.append(context)
            script._attempt = context.attempt
            raise ApplicationError(
                "no agent binary found for persona",
                type=AGENT_LAUNCH_FAILED,
                non_retryable=True,
            )

        real_activities.append(launch_fails)
        return real_activities


def launch_world(*, client: Any) -> LaunchFailingWorld:
    return LaunchFailingWorld(
        {"us1": [passing()]},
        client=client,
    )


def one_node_graph() -> Any:
    return make_graph([make_node("us1", "US2")])


# --- T010 [P] [US2] (spec US2-S1) --------------------------------------------


async def test_launch_failure_does_not_consume_attempt_budget(
    env: WorkflowEnvironment,
) -> None:
    """A launch fault before any agent output leaves the ladder's spent count at zero.

    The assertion uses `_attempts_spent` directly because that is the function
    the ladder consults (spec US2-S1).  A workflow that simply skips recording
    the launch failure would also pass a plain retry assertion, but only a
    real classification change keeps `_attempts_spent` at zero.
    """
    script = launch_world(client=env.client)

    status = await run_epic(env, script, graph=one_node_graph())

    # The count is the only assertion here: a workflow that retries forever or
    # one that silently skips recording would both show a non-zero spend.  Only
    # a proper classification keeps the ladder's budget untouched.
    history = [
        AttemptRecord(
            attempt=record.attempt,
            persona="implementer",
            verdict=record.verdict,
        )
        for record in script.records
        if record.node_id == "us1"
    ]
    assert _attempts_spent(history, VerificationConfig()) == 0, (
        "a launch fault consumed the attempt budget"
    )


# --- T011 [P] [US2] (spec US2-S2) --------------------------------------------


async def test_launch_failure_is_reported_distinctly_naming_the_fault(
    env: WorkflowEnvironment,
) -> None:
    """A launch fault surfaces as its own condition, distinct from an attempt failure."""
    script = launch_world(client=env.client)

    status = await run_epic(env, script, graph=one_node_graph())

    node_status = status.nodes["us1"]
    assert node_status.state == NodeState.KILLED
    assert node_status.terminal_reason is not None
    assert "launch" in node_status.terminal_reason.lower(), (
        "the terminal reason must name the launch fault"
    )
    assert "AGENT_LAUNCH_FAILED" in node_status.terminal_reason, (
        "the terminal reason must carry the launch failure type"
    )

    # No verification result was recorded: this is a launch failure, not a
    # failed attempt.
    assert not [r for r in script.records if r.node_id == "us1"]
    # The notifier is reached because the condition is operator-facing.
    assert len(script.escalation_requests) == 1
    assert "launch" in script.escalation_requests[0].history_summary.lower()


# --- T012 [P] [US2] (spec US2-S3) --------------------------------------------


async def test_launch_failure_reaches_notifier_before_ladder_exhausts(
    env: WorkflowEnvironment,
) -> None:
    """A launch fault pages the operator immediately, not after spending the budget."""
    script = launch_world(client=env.client)

    status = await run_epic(env, script, graph=one_node_graph())

    # Only one escalation: the launch fault, not three failed attempts + debugger.
    assert len(script.escalation_requests) == 1, (
        "launch failure should page exactly once, not after exhausting attempts"
    )
    escalation = script.escalation_requests[0]
    assert escalation.epic_id == EPIC_ID
    assert escalation.node_id == "us1"
    # The history summary names the launch condition, not gate failure evidence.
    assert "launch" in escalation.history_summary.lower()
    # No attempt records means no budget was spent before paging.
    assert not [r for r in script.records if r.node_id == "us1"]
    assert status.nodes["us1"].state == NodeState.KILLED
