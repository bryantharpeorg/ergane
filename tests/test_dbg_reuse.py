"""Hypothesis: reusing env.client (not a fresh _connect) fixes the CLI hang."""
import asyncio

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import factory.workgraph.cli as cli_module
from factory.notify.service import TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV
from factory.usage.litellm_client import PROXY_URL_ENV
from factory.workgraph.cli import load_workgraph
from factory.workgraph.workflow import TASK_QUEUE, EpicWorkflow
from tests.test_epic_cli import ScriptedEpic, WORKFLOW_ID


@pytest.fixture
async def env():
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


async def test_reuse_env_client(env, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, env.client.service_client.config.target_host)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, env.client.namespace)
    monkeypatch.setenv(PROXY_URL_ENV, "http://proxy.invalid")

    async def fake_connect():
        return env.client

    cli_module._connect = fake_connect

    script = ScriptedEpic(spec_text="spec")

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow],
        activities=script.activities(),
    ):
        from factory.workgraph.cli import _start_epic, derive_command
        import argparse
        from tests.test_epic_cli import plant_text, CORPUS, VALID, TARGET_REPO
        spec_dir = plant_text(tmp_path, (CORPUS / VALID / "spec.md").read_text(encoding="utf-8"))
        args = argparse.Namespace(
            spec_dir=spec_dir,
            output=None,
            specs_root=str(spec_dir.parent),
            target_repo=TARGET_REPO,
        )
        derive_command(args)
        graph = load_workgraph(spec_dir / "workgraph.json")
        code = await _start_epic(graph, "http://proxy.invalid")
        print("start code", code, flush=True)
        handle = env.client.get_workflow_handle(WORKFLOW_ID)
        try:
            result = await asyncio.wait_for(handle.result(), timeout=20)
            print("COMPLETED", result, flush=True)
        except asyncio.TimeoutError:
            print("HUNG", flush=True)
        raise AssertionError("done")
