"""109-US3: the epic halts at PASSED.

The halting mode is a workflow dispatch flag.  With it on, a node that passes its
gate and judge ends at `PASSED`; the landing phase never begins and no forge seam
is touched.  With it off, behaviour is exactly today's through `MERGED`.  A node
that fails reports failure exactly as today.

These tests exercise the workflow directly with the same scripted world the
interpreter suite uses, so they pin the decision-making rather than any one CLI
path into it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.mergequeue.forge import (
    ALREADY_SATISFIED,
    APPLIED,
    Forge,
    ForgeError,
    LandingPolicy,
    Proposal,
    RepositoryDescription,
    WiringRefused,
    WiringStep,
)
from factory.mergequeue.models import CheckFailure, Finding, PrSnapshot
from factory.workgraph.models import EpicState, NodeState
from factory.workgraph.workflow import EpicInput, EpicWorkflow
from factory.escalation.workflow import EscalationWorkflow
from factory.escalation.question import QuestionWorkflow

from tests.test_interpreter import (
    PROXY_URL,
    TASK_QUEUE,
    WORKFLOW_ID,
    ScriptedWorld,
    all_passing,
    make_graph,
    make_node,
    one_node,
    passing,
    failing,
    scored_world,
    judge_pass,
    gate_pass,
)

HALT_WORKFLOW_ID = f"{WORKFLOW_ID}-halt"


class _RaisingForge(Forge):
    """A forge whose every method raises — the US3 spy (FR-013, trap T7).

    A double that returns sentinel values lets a call through and still passes; the
    assertion that the run completed is only true if nothing called the seam.
    """

    def describe_repository(self) -> RepositoryDescription:
        raise AssertionError("forge.describe_repository was called in halting mode")

    def landing_policy(self, branch: str) -> LandingPolicy:
        raise AssertionError("forge.landing_policy was called in halting mode")

    def find_proposal(self, head: str) -> Proposal | None:
        raise AssertionError("forge.find_proposal was called in halting mode")

    def open_proposal(
        self, *, base: str, head: str, title: str, body_file: str
    ) -> Proposal:
        raise AssertionError("forge.open_proposal was called in halting mode")

    def request_landing(self, proposal: int, *, declared_method: str = "") -> None:
        raise AssertionError("forge.request_landing was called in halting mode")

    def observe_proposal(self, proposal: int) -> PrSnapshot:
        raise AssertionError("forge.observe_proposal was called in halting mode")

    def withdraw_landing(self, proposal: int) -> None:
        raise AssertionError("forge.withdraw_landing was called in halting mode")

    def failing_check_evidence(
        self, proposal: int, check_names: tuple[str, ...]
    ) -> tuple[CheckFailure, ...]:
        raise AssertionError("forge.failing_check_evidence was called in halting mode")

    def close_proposal(self, proposal: int, *, note: str) -> None:
        raise AssertionError("forge.close_proposal was called in halting mode")

    def retire_head(self, head: str, *, archive_prefix: str) -> str:
        raise AssertionError("forge.retire_head was called in halting mode")

    def apply_landing_policy(
        self, branch: str, required_checks: Sequence[str]
    ) -> tuple[WiringStep, ...]:
        raise AssertionError("forge.apply_landing_policy was called in halting mode")


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@asynccontextmanager
async def _run_halt_epic(
    env: WorkflowEnvironment,
    script: ScriptedWorld,
    *,
    graph: Any = None,
    workflow_id: str = HALT_WORKFLOW_ID,
    **overrides: Any,
) -> AsyncIterator[Any]:
    """Start the epic in halting mode and hold the worker open."""
    request: dict[str, Any] = {
        "graph": graph if graph is not None else one_node(),
        "proxy_url": PROXY_URL,
        "halt_after_pass": True,
    }
    request.update(overrides)

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow, EscalationWorkflow, QuestionWorkflow],
        activities=script.activities(),
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(**request),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
        script.handle = handle
        yield handle


async def _run_halt_epic_to_result(
    env: WorkflowEnvironment, script: ScriptedWorld, **overrides: Any
) -> Any:
    async with _run_halt_epic(env, script, **overrides) as handle:
        return await handle.result()


# --- T016 [US3-S1, FR-012] terminal state is PASSED ----------------------------


async def test_halting_mode_ends_at_passed(env: WorkflowEnvironment) -> None:
    """A node that passes its gate and judge ends at PASSED and never lands."""
    script = ScriptedWorld(all_passing(), client=env.client)

    status = await _run_halt_epic_to_result(env, script)

    assert status.epic_state == EpicState.COMPLETED
    assert status.nodes["us1"].state == NodeState.PASSED
    assert status.nodes["us1"].verified is True
    assert status.nodes["us1"].landing_state is None
    assert status.nodes["us1"].pr_number is None

    # No landing-phase activity was ever invoked.
    assert not script.body_prepare_requests
    assert not script.landing_requests
    assert not script.enqueue_requests
    assert not script.poll_requests
    # The worktree is removed once PASSED becomes terminal in halting mode.
    assert len(script.removals) == 1
    assert script.removals[0].node_id == "us1"


# --- T017 [US3-S1, FR-013] the forge spy --------------------------------------


async def test_halting_mode_never_touches_the_forge_seam(
    env: WorkflowEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising forge proves the run completes without any forge call."""
    from factory.activities import merge_activities

    script = ScriptedWorld(all_passing(), client=env.client)
    spy = _RaisingForge()
    monkeypatch.setattr(merge_activities, "_client_factory", lambda *, repo_path: spy)

    status = await _run_halt_epic_to_result(env, script)

    assert status.epic_state == EpicState.COMPLETED
    assert status.nodes["us1"].state == NodeState.PASSED


# --- T018 [US3-S2, FR-014] output states landing was not attempted -------------


async def test_halting_mode_output_says_landing_not_attempted(
    env: WorkflowEnvironment,
) -> None:
    """The returned EpicStatus states landing was not attempted and why."""
    script = ScriptedWorld(all_passing(), client=env.client)

    status = await _run_halt_epic_to_result(env, script)

    # FR-014: the wording distinguishes an absent landing from a failed one.
    assert status.halt_after_pass is True
    assert status.nodes["us1"].state == NodeState.PASSED
    assert status.nodes["us1"].landing_state is None
    assert status.nodes["us1"].terminal_reason is None


# --- T019 [US3-S3/S4, FR-015/FR-016] two guards --------------------------------


async def test_halting_mode_off_runs_through_merged(env: WorkflowEnvironment) -> None:
    """With the mode off, the existing behaviour runs through MERGED."""
    script = ScriptedWorld(all_passing(), client=env.client)

    status = await _run_halt_epic_to_result(env, script, halt_after_pass=False)

    assert status.epic_state == EpicState.COMPLETED
    assert status.nodes["us1"].state == NodeState.MERGED
    assert status.nodes["us1"].pr_number is not None

    # The landing phase ran normally.
    assert script.landing_requests
    assert script.enqueue_requests


async def test_halting_mode_failure_reports_as_today(
    env: WorkflowEnvironment,
) -> None:
    """With the mode on and a failing gate, the node reports KILLED as today."""
    script = ScriptedWorld(
        {"us1": [failing(1), failing(2), failing(3), failing(4)]},
        client=env.client,
    )

    status = await _run_halt_epic_to_result(env, script)

    assert status.nodes["us1"].state == NodeState.KILLED
    # Failure is unchanged by the mode: no landing phase ran.
    assert not script.landing_requests
    assert not script.enqueue_requests
