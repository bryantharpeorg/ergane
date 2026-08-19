"""US2-S5: the roadmap schedule's first tick completes and renders zero rows.

Drives the workflow's read path against a freshly-initialised tree. The
control plane is bound offline; the only thing under test is that the
roadmap can read the `specs/` root `ergane init` created and finish its
first tick without raising.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

import factory.cli.init as init_module
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapStatus,
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.workgraph.workflow import TASK_QUEUE

from tests.test_ergane_init import DEFAULT_ANSWERS, ScriptedPrompter, _git
from tests.test_ergane_init_check import bind_offline_seams
from tests.test_roadmap_scheduler import RoadmapWorld


TARGET_REPO = "/srv/factory/targets/library"
PROXY_URL = "http://litellm.test"


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """Run a full `ergane init` with scripted seams."""

    def runner(repo: Path, *, answers: list[str] | None = None) -> Any:
        prompter = ScriptedPrompter(list(answers or DEFAULT_ANSWERS))
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        bind_offline_seams(monkeypatch)
        monkeypatch.chdir(repo)
        # Run the synchronous CLI in a thread so it does not compete with the
        # test's event loop. The CLI uses `asyncio.run()` internally; calling it
        # from a running async loop raises.
        import factory.cli.main as main_module
        import io
        import sys

        old_stdout, old_stderr = sys.stdout, sys.stderr
        buf_out, buf_err = io.StringIO(), io.StringIO()
        try:
            sys.stdout, sys.stderr = buf_out, buf_err
            try:
                code = main_module.main(["init", str(repo)])
            except SystemExit as exit_request:
                code = 0 if exit_request.code is None else int(exit_request.code)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
        return type("Run", (), {"code": code, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue()})

    return runner


@pytest.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[WorkflowEnvironment]:
    from factory.usage.litellm_client import PROXY_URL_ENV

    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@asynccontextmanager
async def _run_roadmap(
    env: WorkflowEnvironment,
    specs_root: str,
) -> AsyncIterator[Any]:
    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_escalation,
        send_roadmap_notice,
    )
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
        read_loop_config,
    )
    from factory.roadmap.workflow import read_corpus_activity, read_spec_text_activity

    world = RoadmapWorld()
    world.apply()
    try:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[RoadmapWorkflow],
            activities=[
                clone_target,
                derive_spec,
                drift_for_spec,
                preflight_spec,
                onboard_target,
                count_open_epics,
                read_corpus_activity,
                read_loop_config,
                read_spec_text_activity,
                record_roadmap_failure,
                reset_roadmap_failures,
                send_roadmap_notice,
                send_escalation,
            ],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                RoadmapWorkflow.run,
                RoadmapInput(
                    specs_root=specs_root,
                    target_repo=TARGET_REPO,
                    proxy_url=PROXY_URL,
                    max_concurrent_epics=1,
                ),
                id=roadmap_workflow_id(specs_root),
                task_queue=TASK_QUEUE,
            )
            yield handle
    finally:
        world.restore()


async def test_first_tick_on_fresh_init_renders_zero_rows(
    env: WorkflowEnvironment,
    tmp_path: Path,
    init: Callable[..., Any],
) -> None:
    """US2-S5: a freshly-initialised tree's first roadmap tick completes with zero specs."""
    repo = tmp_path / "app"
    repo.mkdir()
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text("# app\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")

    result = await asyncio.to_thread(init, repo)
    assert result.code == 0

    specs_root = repo / "specs"
    assert specs_root.is_dir()
    assert list(specs_root.iterdir()) == []

    async with _run_roadmap(env, str(specs_root)) as handle:
        status: RoadmapStatus = await handle.result()

    assert status.specs == []
    assert status.running == []
    assert status.parked == []
