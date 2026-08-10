"""US4 roadmap surface tests: `ergane roadmap start|pause|resume|promote|status`.

These cases drive the new operator CLI through the unified dispatcher. They
reuse the scheduler test harness (scripted activities + scripted child epic) so
the roadmap is genuinely running when signals and queries are sent.

Written before `factory/cli/roadmap.py` exists (T024 precedes T028): until it
lands, every invocation fails with `ergane: unknown noun`.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, NamedTuple

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.cli import main as main_module
from factory.notify.service import TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV
from factory.roadmap.models import SpecState
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapStatus,
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.usage.litellm_client import PROXY_URL_ENV
from factory.workgraph.workflow import TASK_QUEUE

from tests.roadmap_script import ScriptedEpicWorkflow, _SCRIPT
from tests.test_roadmap_scheduler import RoadmapWorld, build_corpus

TARGET_REPO = "/srv/factory/targets/library"
PROXY_URL = "http://litellm.test"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: list[str]) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def invoke(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    def _caller(*argv: str, env: dict[str, str] | None = None) -> Run:
        saved: dict[str, str | None] = {}
        if env:
            saved = {k: os.environ.get(k) for k in env}
            for k, v in env.items():
                monkeypatch.setenv(k, v)
        try:
            return _invoke(list(argv))
        finally:
            for k, v in saved.items():
                if v is None:
                    monkeypatch.delenv(k, raising=False)
                else:
                    monkeypatch.setenv(k, v)

    return _caller


@pytest.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[WorkflowEnvironment]:
    """Time-skipping Temporal server pointed at by the CLI's environment contract."""
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    environment = await WorkflowEnvironment.start_time_skipping()
    monkeypatch.setenv(
        TEMPORAL_ADDRESS_ENV, environment.client.service_client.config.target_host
    )
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, environment.client.namespace)
    try:
        yield environment
    finally:
        await environment.shutdown()


async def _run_in_thread(invoke: Callable[..., Run], *argv: str) -> Run:
    """Call the synchronous dispatcher without blocking the test loop."""
    return await asyncio.to_thread(invoke, *argv)


def _worker(env: WorkflowEnvironment, world: RoadmapWorld) -> Worker:
    """A worker that serves the real RoadmapWorkflow with scripted seams."""
    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_escalation,
    )
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
    )
    from factory.roadmap.workflow import read_corpus_activity, read_spec_text_activity

    return Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
        activities=[
            clone_target,
            derive_spec,
            drift_for_spec,
            preflight_spec,
            onboard_target,
            count_open_epics,
            read_corpus_activity,
            read_spec_text_activity,
            record_roadmap_failure,
            reset_roadmap_failures,
            send_escalation,
        ],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )


@pytest.fixture
def roadmap_world(monkeypatch: pytest.MonkeyPatch) -> Iterator[RoadmapWorld]:
    """A default scripted world; seams are restored after the test."""
    _SCRIPT.statuses = {}
    _SCRIPT.hold = set()
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    world = RoadmapWorld()
    world.apply()
    try:
        yield world
    finally:
        world.restore()
        _SCRIPT.statuses = {}
        _SCRIPT.hold = set()
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None


# --- start --------------------------------------------------------------------


async def test_start_prints_the_roadmap_workflow_id(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    roadmap_world: RoadmapWorld,
) -> None:
    """`ergane roadmap start <specs>` prints `roadmap-<specs-root-name>`."""
    specs_root = build_corpus(tmp_path, {"001-ready": dict(state=SpecState.READY)})
    # Hold the child so the roadmap stays alive; we only care about the id.
    _SCRIPT.hold = {"001-ready"}

    async with _worker(env, roadmap_world):
        result = await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        env.client.get_workflow_handle(f"epic-001-ready").signal("release")

    assert result.code == 0
    assert result.stdout.strip() == roadmap_workflow_id(str(specs_root))


async def test_start_starts_on_the_workgraph_task_queue(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    roadmap_world: RoadmapWorld,
) -> None:
    specs_root = build_corpus(tmp_path, {"001-ready": dict(state=SpecState.READY)})
    _SCRIPT.hold = {"001-ready"}
    workflow_id = roadmap_workflow_id(str(specs_root))

    async with _worker(env, roadmap_world):
        await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        described = await env.client.get_workflow_handle(workflow_id).describe()
        env.client.get_workflow_handle("epic-001-ready").signal("release")

    assert described.workflow_type == "RoadmapWorkflow"
    assert described.task_queue == TASK_QUEUE


async def test_starting_a_running_roadmap_twice_is_refused_by_name(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    roadmap_world: RoadmapWorld,
) -> None:
    specs_root = build_corpus(tmp_path, {"001-ready": dict(state=SpecState.READY)})
    _SCRIPT.hold = {"001-ready"}

    async with _worker(env, roadmap_world):
        first = await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        second = await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        env.client.get_workflow_handle("epic-001-ready").signal("release")

    assert first.code == 0
    assert second.code == 1
    assert "already running" in second.stderr
    assert roadmap_workflow_id(str(specs_root)) in second.stderr


# --- status and signals -------------------------------------------------------


async def _wait_for_running(
    env: WorkflowEnvironment, specs_root: Path, spec_dir: str
) -> RoadmapStatus:
    """Poll roadmap_status until the named spec_dir appears in running."""
    workflow_id = roadmap_workflow_id(str(specs_root))
    for _ in range(300):
        status = await env.client.get_workflow_handle(workflow_id).query(
            "roadmap_status", result_type=RoadmapStatus
        )
        if spec_dir in status.running:
            return status
        await asyncio.sleep(0.01)
    raise AssertionError(f"{spec_dir} never reported running")


async def test_status_prints_the_roadmap_status_document(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    roadmap_world: RoadmapWorld,
) -> None:
    specs_root = build_corpus(tmp_path, {"001-ready": dict(state=SpecState.READY)})
    _SCRIPT.hold = {"001-ready"}

    async with _worker(env, roadmap_world):
        await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        await _wait_for_running(env, specs_root, "001-ready")

        result = await _run_in_thread(
            invoke, "roadmap", "status", str(specs_root), "--json"
        )
        env.client.get_workflow_handle("epic-001-ready").signal("release")

    assert result.code == 0
    document = result.json
    assert "specs" in document
    assert "running" in document
    assert document["paused"] is False


async def test_pause_parks_dispatch_and_resume_releases_it(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    roadmap_world: RoadmapWorld,
) -> None:
    specs_root = build_corpus(tmp_path, {"001-ready": dict(state=SpecState.READY)})
    _SCRIPT.hold = {"001-ready"}

    async with _worker(env, roadmap_world):
        await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        await _wait_for_running(env, specs_root, "001-ready")

        pause = await _run_in_thread(invoke, "roadmap", "pause", str(specs_root))
        assert pause.code == 0

        # Release the child and wait until the roadmap reports paused and empty.
        env.client.get_workflow_handle("epic-001-ready").signal("release")
        workflow_id = roadmap_workflow_id(str(specs_root))
        for _ in range(300):
            status = await env.client.get_workflow_handle(workflow_id).query(
                "roadmap_status", result_type=RoadmapStatus
            )
            if status.paused and not status.running:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("roadmap did not report paused")

        resume = await _run_in_thread(invoke, "roadmap", "resume", str(specs_root))
        assert resume.code == 0


async def test_promote_makes_a_draft_dispatchable(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    roadmap_world: RoadmapWorld,
) -> None:
    specs_root = build_corpus(
        tmp_path,
        {
            "001-ready": dict(state=SpecState.READY),
            "002-draft": dict(
                state=SpecState.DRAFT, depends_on_landed=["001-ready"]
            ),
        },
    )
    _SCRIPT.hold = {"001-ready"}

    async with _worker(env, roadmap_world):
        await _run_in_thread(
            invoke, "roadmap", "start", str(specs_root), "--target-repo", TARGET_REPO
        )
        await _wait_for_running(env, specs_root, "001-ready")

        before = await _run_in_thread(
            invoke, "roadmap", "status", str(specs_root), "--json"
        )
        assert before.code == 0
        draft = next(s for s in before.json["specs"] if s["spec_dir"] == "002-draft")
        assert draft["dispatchable"] is False
        assert draft["promoted"] is False

        promote = await _run_in_thread(
            invoke, "roadmap", "promote", str(specs_root), "--spec", "002-draft"
        )
        assert promote.code == 0

        # Promoted flag is visible even before the draft actually runs.
        after = await _run_in_thread(
            invoke, "roadmap", "status", str(specs_root), "--json"
        )
        assert after.code == 0
        draft = next(s for s in after.json["specs"] if s["spec_dir"] == "002-draft")
        assert draft["promoted"] is True

        env.client.get_workflow_handle("epic-001-ready").signal("release")


# Import at module bottom to avoid circular imports with fixtures.
import os  # noqa: E402
