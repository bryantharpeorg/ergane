"""Compare: start epic via env.client on test loop vs via CLI thread flow."""
import asyncio
import os

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.notify.service import TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV
from factory.usage.litellm_client import PROXY_URL_ENV
from factory.workgraph.workflow import TASK_QUEUE, EpicWorkflow
from tests.test_epic_cli import (
    EPIC_ID,
    ScriptedEpic,
    WORKFLOW_ID,
    plant_text,
    CORPUS,
    VALID,
    TARGET_REPO,
)


@pytest.fixture
async def env():
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


def spec_text() -> str:
    return (CORPUS / VALID / "spec.md").read_text(encoding="utf-8")


async def test_start_via_env_client_direct(env, tmp_path) -> None:
    """Baseline: start with env.client on the test loop."""
    script = ScriptedEpic(spec_text=spec_text())
    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[EpicWorkflow], activities=script.activities()
    ):
        from factory.workgraph.cli import derive_command, load_workgraph
        import argparse

        spec_dir = plant_text(tmp_path, spec_text())
        args = argparse.Namespace(
            spec_dir=spec_dir, output=None, specs_root=str(spec_dir.parent), target_repo=TARGET_REPO
        )
        derive_command(args)
        graph = load_workgraph(spec_dir / "workgraph.json")

        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            graph_input_like(graph),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        try:
            result = await asyncio.wait_for(handle.result(), timeout=20)
            print("DIRECT COMPLETED", result, flush=True)
        except asyncio.TimeoutError:
            print("DIRECT HUNG", flush=True)
        # Now try via get_workflow_handle
        h2 = env.client.get_workflow_handle(WORKFLOW_ID)
        try:
            r2 = await asyncio.wait_for(h2.result(), timeout=20)
            print("DIRECT-GWH COMPLETED", r2, flush=True)
        except asyncio.TimeoutError:
            print("DIRECT-GWH HUNG", flush=True)


def graph_input_like(graph):
    from factory.workgraph.workflow import EpicInput
    return EpicInput(graph=graph, proxy_url=os.environ.get(PROXY_URL_ENV, "http://proxy.invalid"))


async def test_start_via_fresh_client_on_loop(env, monkeypatch, tmp_path) -> None:
    """Fresh Client.connect() on the test loop (no thread)."""
    from temporalio.client import Client
    script = ScriptedEpic(spec_text=spec_text())
    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[EpicWorkflow], activities=script.activities()
    ):
        client = await Client.connect(
            env.client.service_client.config.target_host,
            namespace=env.client.namespace,
        )
        from factory.workgraph.cli import derive_command, load_workgraph
        import argparse

        spec_dir = plant_text(tmp_path, spec_text())
        args = argparse.Namespace(
            spec_dir=spec_dir, output=None, specs_root=str(spec_dir.parent), target_repo=TARGET_REPO
        )
        derive_command(args)
        graph = load_workgraph(spec_dir / "workgraph.json")
        handle = await client.start_workflow(
            EpicWorkflow.run,
            graph_input_like(graph),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        try:
            result = await asyncio.wait_for(handle.result(), timeout=20)
            print("FRESHCLIENT COMPLETED", result, flush=True)
        except asyncio.TimeoutError:
            print("FRESHCLIENT HUNG", flush=True)


async def test_start_via_cli_thread(env, monkeypatch, tmp_path) -> None:
    """CLI flow: _invoke in asyncio.to_thread."""
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, env.client.service_client.config.target_host)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, env.client.namespace)
    monkeypatch.setenv(PROXY_URL_ENV, "http://proxy.invalid")

    script = ScriptedEpic(spec_text=spec_text())
    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[EpicWorkflow], activities=script.activities()
    ):
        from factory.workgraph.cli import derive_command, load_workgraph
        import argparse

        spec_dir = plant_text(tmp_path, spec_text())
        args = argparse.Namespace(
            spec_dir=spec_dir, output=None, specs_root=str(spec_dir.parent), target_repo=TARGET_REPO
        )
        derive_command(args)
        graph_path = spec_dir / "workgraph.json"

        from factory.workgraph.cli import _start_epic
        import factory.workgraph.cli as cli_module

        async def fake_connect():
            print("fake_connect CALLED returning env.client", flush=True)
            return env.client

        cli_module._connect = fake_connect

        code = await _start_epic(load_workgraph(graph_path), os.environ[PROXY_URL_ENV])
        print("cli._connect is fake:", cli_module._connect is fake_connect, flush=True)
        print("async start code", code, flush=True)
        handle = env.client.get_workflow_handle(WORKFLOW_ID)
        try:
            result = await asyncio.wait_for(handle.result(), timeout=20)
            print("ASYNC-ENVCLIENT COMPLETED", result, flush=True)
        except asyncio.TimeoutError:
            print("ASYNC-ENVCLIENT HUNG", flush=True)
            desc = await handle.describe()
            print("state:", desc.status.name, flush=True)
            try:
                status = await handle.query("epic_status")
                print("status:", status, flush=True)
            except Exception as e:
                print("query error:", e, flush=True)
