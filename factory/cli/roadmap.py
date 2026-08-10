"""Implementation of `ergane roadmap`.

`start` compiles a `RoadmapInput` from the operator's flags and starts the
long-running `RoadmapWorkflow`. `pause`, `resume`, and `promote` send signals;
`status` queries `roadmap_status`. All traffic uses the notify bridge's
environment contract for Temporal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, OperatorError
from factory.mergequeue.models import LandingConfig
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.roadmap.workflow import (
    TASK_QUEUE,
    RoadmapInput,
    RoadmapStatus,
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.usage.litellm_client import PROXY_URL_ENV
from factory.verify.models import VerificationConfig
from factory.workgraph.workflow import TASK_QUEUE as EPIC_TASK_QUEUE


DEFAULT_MAX_CONCURRENT_EPICS = 1
DEFAULT_MAX_CONCURRENT_NODES = 1
DEFAULT_POLL_INTERVAL_S = 30


def add_roadmap_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "roadmap",
        help="run and steer the roadmap scheduler",
        description="Start, signal, and query a roadmap over a specs corpus.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    start = verbs.add_parser("start", help="start a roadmap")
    start.add_argument("specs_root", help="path to the specs corpus")
    start.add_argument(
        "--target-repo",
        required=True,
        help="worker-host path to the target repo clone",
    )
    start.add_argument(
        "--proxy-url",
        default=os.environ.get(PROXY_URL_ENV, ""),
        help=f"proxy URL for child epic keys (default: ${PROXY_URL_ENV})",
    )
    start.add_argument(
        "--max-concurrent-epics",
        type=_positive_int,
        default=DEFAULT_MAX_CONCURRENT_EPICS,
        help=f"concurrent child epics (default: {DEFAULT_MAX_CONCURRENT_EPICS})",
    )
    start.add_argument(
        "--max-concurrent-nodes",
        type=_positive_int,
        default=DEFAULT_MAX_CONCURRENT_NODES,
        help=f"ready nodes per child epic (default: {DEFAULT_MAX_CONCURRENT_NODES})",
    )
    start.add_argument(
        "--poll-interval-s",
        type=_positive_int,
        default=DEFAULT_POLL_INTERVAL_S,
        help=f"child-poll interval in seconds (default: {DEFAULT_POLL_INTERVAL_S})",
    )
    start.add_argument(
        "--idle-rescan-s",
        type=_optional_positive_int,
        default=None,
        metavar="SECONDS",
        help="idle rescan interval; omit to drain and exit",
    )
    start.set_defaults(run=_run_async(roadmap_start_command))

    pause = verbs.add_parser("pause", help="pause dispatch")
    pause.add_argument("specs_root", help="path to the specs corpus")
    pause.set_defaults(run=_run_async(roadmap_pause_command))

    resume = verbs.add_parser("resume", help="resume dispatch")
    resume.add_argument("specs_root", help="path to the specs corpus")
    resume.set_defaults(run=_run_async(roadmap_resume_command))

    status = verbs.add_parser("status", help="query roadmap status")
    status.add_argument("specs_root", help="path to the specs corpus")
    status.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the query result verbatim instead of the human view",
    )
    status.set_defaults(run=_run_async(roadmap_status_command))

    promote = verbs.add_parser("promote", help="promote a draft spec to ready")
    promote.add_argument("specs_root", help="path to the specs corpus")
    promote.add_argument(
        "--spec",
        required=True,
        help="spec directory name to promote",
    )
    promote.set_defaults(run=_run_async(roadmap_promote_command))

    return parser


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}")
    return parsed


def _optional_positive_int(value: str) -> int | None:
    if value.lower() in ("", "none"):
        return None
    return _positive_int(value)


def _run_async(command: Any) -> Any:
    """Wrap an async command so argparse's `run` is synchronous."""

    def run(args: argparse.Namespace) -> int:
        return asyncio.run(command(args))

    return run


async def _connect() -> Client:
    address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    try:
        return await Client.connect(address, namespace=namespace)
    except (RPCError, RuntimeError, OSError) as error:
        raise OperatorError(
            f"cannot reach Temporal at {address} (namespace '{namespace}'): {error}",
            EXIT_TRANSPORT,
        ) from error


def _workflow_id(args: argparse.Namespace) -> str:
    return roadmap_workflow_id(args.specs_root)


async def roadmap_start_command(args: argparse.Namespace) -> int:
    specs_root = Path(args.specs_root).resolve()
    if not specs_root.exists():
        raise OperatorError(f"specs root {specs_root} does not exist")

    proxy_url = args.proxy_url or os.environ.get(PROXY_URL_ENV, "")
    if not proxy_url:
        raise OperatorError(
            f"{PROXY_URL_ENV} is not set; child epics need a proxy to issue virtual keys"
        )

    client = await _connect()
    workflow_id = _workflow_id(args)
    input_data = RoadmapInput(
        specs_root=str(specs_root),
        target_repo=args.target_repo,
        proxy_url=proxy_url,
        max_concurrent_epics=args.max_concurrent_epics,
        max_concurrent_nodes=args.max_concurrent_nodes,
        landing_config=LandingConfig(),
        config=VerificationConfig(),
        poll_interval_s=args.poll_interval_s,
        idle_rescan_s=args.idle_rescan_s,
        carry_over=None,
    )
    try:
        await client.start_workflow(
            RoadmapWorkflow.run,
            input_data,
            id=workflow_id,
            task_queue=EPIC_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError:
        raise OperatorError(
            f"roadmap '{specs_root.name}' is already running "
            f"(workflow id {workflow_id})"
        ) from None
    print(workflow_id)
    return EXIT_OK


async def _get_handle(args: argparse.Namespace) -> Any:
    client = await _connect()
    workflow_id = _workflow_id(args)
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.describe()
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            raise OperatorError(
                f"no roadmap '{Path(args.specs_root).name}' is running here "
                f"(looked for workflow id {workflow_id})"
            ) from error
        raise OperatorError(
            f"cannot reach roadmap '{Path(args.specs_root).name}': {error}",
            EXIT_TRANSPORT,
        ) from error
    return handle


async def roadmap_pause_command(args: argparse.Namespace) -> int:
    handle = await _get_handle(args)
    await handle.signal("pause_roadmap")
    return EXIT_OK


async def roadmap_resume_command(args: argparse.Namespace) -> int:
    handle = await _get_handle(args)
    await handle.signal("resume_roadmap")
    return EXIT_OK


async def roadmap_promote_command(args: argparse.Namespace) -> int:
    handle = await _get_handle(args)
    await handle.signal("promote_spec", args.spec)
    return EXIT_OK


async def roadmap_status_command(args: argparse.Namespace) -> int:
    handle = await _get_handle(args)
    try:
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
    except RPCError as error:
        raise OperatorError(
            f"cannot query roadmap '{Path(args.specs_root).name}': {error}",
            EXIT_TRANSPORT,
        ) from error

    if args.as_json:
        print(json.dumps(asdict(status), indent=2))
    else:
        print(_render_status(status))
    return EXIT_OK


def _render_status(status: RoadmapStatus) -> str:
    lines = [
        f"roadmap: {'paused' if status.paused else 'running'}",
        f"concurrency: {status.max_concurrent_epics} epic(s), "
        f"{status.max_concurrent_nodes} node(s)",
        f"running: {', '.join(status.running) or '-'}",
        f"parked: {len(status.parked)}",
    ]
    if status.specs:
        lines.append("specs:")
        for spec in status.specs:
            flag = "*" if spec.dispatchable else " "
            lines.append(
                f"  [{flag}] {spec.spec_dir}: {spec.rendered_state or spec.state.value} "
                f"(landed={spec.landed}, promoted={spec.promoted})"
            )
    return "\n".join(lines)
