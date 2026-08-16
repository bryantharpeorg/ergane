"""Implementation of `ergane roadmap`.

`start` compiles a `RoadmapInput` from the operator's flags and starts the
long-running `RoadmapWorkflow`. `pause`, `resume`, and `promote` send signals;
`status` queries `roadmap_status`. All traffic uses the notify bridge's
environment contract for Temporal.

The four verbs that act on a *running* roadmap reach it through
`factory.roadmap.discovery`, because `roadmap-<root>` is only where a roadmap
lives when an operator started it by hand: a schedule's runs are
`roadmap-<root>-<timestamp>`, so the bare id resolves to nothing and the verbs
used to refuse a roadmap Temporal could plainly see (finding
`cli/roadmap-verbs-cannot-see-schedule-driven-runs`, 2026-08-15). `pause` and
`resume` then act on whatever owns *dispatch* — the schedule, when a schedule
owns it, since pausing one of its runs stops nothing: the next tick starts
another.
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
from temporalio.service import RPCError

from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, OperatorError
from factory.mergequeue.models import LandingConfig
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.roadmap.discovery import (
    RoadmapLocation,
    RoadmapOwner,
    resolve_roadmap,
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


async def _locate(args: argparse.Namespace) -> tuple[Client, RoadmapLocation]:
    """Connect and resolve the roadmap, or refuse by naming every rung tried.

    The refusal is the location's own (FR-007): with the full ladder in force it
    names the bare workflow id, the schedule and the run prefix, in the order
    they were tried, so the operator's next move is on the line.
    """
    client = await _connect()
    try:
        location = await resolve_roadmap(client, args.specs_root)
    except RPCError as error:
        raise OperatorError(
            f"cannot reach roadmap '{Path(args.specs_root).name}': {error}",
            EXIT_TRANSPORT,
        ) from error
    if not location.found:
        raise OperatorError(location.refusal)
    return client, location


async def _get_handle(args: argparse.Namespace) -> Any:
    """The workflow handle for a roadmap's current run — bare or timestamped."""
    client, location = await _locate(args)
    return _handle_for(client, location)


def _handle_for(client: Client, location: RoadmapLocation) -> Any:
    """The run to signal or query, or a refusal naming why there is none."""
    if location.workflow_id is None:
        raise OperatorError(
            f"schedule {location.schedule_id} owns roadmap "
            f"'{location.root_name}' but has started no run yet "
            f"(looked for {location.run_prefix}*)"
        )
    return client.get_workflow_handle(location.workflow_id)


async def roadmap_pause_command(args: argparse.Namespace) -> int:
    """Stop dispatch at whatever owns it.

    A schedule-owned roadmap pauses at the schedule: signalling the run it
    happens to be on would report success while the next tick started a fresh
    one and dispatch continued — worse than refusing, because it lies. A run
    with no schedule this client can name is signalled, and the operator is told
    what could not be established, on stderr, because it is a caveat and not the
    output they asked for.
    """
    client, location = await _locate(args)
    if location.owner is RoadmapOwner.SCHEDULE:
        await client.get_schedule_handle(location.schedule_id).pause()
        print(
            f"paused schedule {location.schedule_id}: the schedule owns "
            "dispatch, so no further run will start"
        )
        return EXIT_OK
    handle = _handle_for(client, location)
    await handle.signal("pause_roadmap")
    _warn_unowned(location, "paused")
    return EXIT_OK


async def roadmap_resume_command(args: argparse.Namespace) -> int:
    """Release dispatch at whatever owns it — the symmetric half of `pause`."""
    client, location = await _locate(args)
    if location.owner is RoadmapOwner.SCHEDULE:
        await client.get_schedule_handle(location.schedule_id).unpause()
        print(
            f"resumed schedule {location.schedule_id}: the schedule owns "
            "dispatch, so the next tick will start a run"
        )
        return EXIT_OK
    handle = _handle_for(client, location)
    await handle.signal("resume_roadmap")
    _warn_unowned(location, "resumed")
    return EXIT_OK


def _warn_unowned(location: RoadmapLocation, verb: str) -> None:
    """Say so when only a run could be acted on and no schedule could be named."""
    if location.owner is not RoadmapOwner.RUN:
        return
    print(
        f"ergane: warning: no owning schedule was found for "
        f"{location.bare_workflow_id}, so only run {location.workflow_id} was "
        f"{verb}; a schedule tick would start a fresh run",
        file=sys.stderr,
    )


async def roadmap_promote_command(args: argparse.Namespace) -> int:
    handle = await _get_handle(args)
    await handle.signal("promote_spec", args.spec)
    return EXIT_OK


async def roadmap_status_command(args: argparse.Namespace) -> int:
    client, location = await _locate(args)
    if location.workflow_id is None:
        # A schedule that owns dispatch but has not ticked: the disposition is
        # the whole answer, because there is no run to query.
        print(_render_disposition(location) + "no run has started yet")
        return EXIT_OK

    handle = client.get_workflow_handle(location.workflow_id)
    try:
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
    except RPCError as error:
        raise OperatorError(
            f"cannot query roadmap '{Path(args.specs_root).name}': {error}",
            EXIT_TRANSPORT,
        ) from error

    if args.as_json:
        # Still the query result verbatim, which is what `--json` promises and
        # what a bare roadmap has always printed. The joined document — the
        # disposition beside the status — is `ergane status --json` (US1).
        print(json.dumps(asdict(status), indent=2))
    else:
        print(_render_disposition(location) + _render_status(status))
    return EXIT_OK


def _render_disposition(location: RoadmapLocation) -> str:
    """The lines that say what owns dispatch, above the status document.

    A bare workflow renders none of them: it *is* the roadmap, there is no
    schedule to name, and its output stays byte-identical to the pre-046 verb.
    """
    lines: list[str] = []
    if location.schedule_id is not None:
        state = "paused" if location.schedule_paused else "running"
        lines.append(f"schedule: {location.schedule_id} ({state})")
    if location.owner is RoadmapOwner.RUN:
        lines.append(
            f"schedule: none found (no schedule starts "
            f"{location.bare_workflow_id}*)"
        )
    if location.owner is not RoadmapOwner.WORKFLOW and location.workflow_id:
        lines.append(f"run: {location.workflow_id}")
    if location.next_action_at is not None:
        lines.append(f"next tick: {location.next_action_at}")
    return "".join(f"{line}\n" for line in lines)


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
