"""A managed repo's roadmap schedule: create it, reconcile it, delete it.

Until 034/US6 nothing in `factory/` created a Temporal schedule, so a repo could
pass `ergane init --check` and still dispatch nothing when a spec was flipped to
`ready` — forever, with no error.  Three decisions, so they are not re-derived:

- **The identifier carries the slug; the action's workflow id does not.**  One
  control plane serves every repo, so `ergane-roadmap-<slug>` keeps their
  schedules apart (FR-014), while the workflow keeps the id
  `roadmap_workflow_id` builds — what `factory.roadmap.discovery` matches on, so
  the `ergane roadmap` verbs can still find it.  Two repos whose specs roots
  share a basename still alias each other's *runs*: the workflow-id gap the spec
  names, and not this story.
- **`landing_branch` is a declaration in the arguments, not an input.**
  `RoadmapInput` has no such field and the converter drops unknown keys (proven
  in the tests).  Adding one would be a second answer to "which branch does the
  factory land on", which `roadmap_activities` already derives from the target
  clone's manifest.  Recorded so `--check` can report drift.
- **Reconciliation never touches `paused`.**  An operator who paused a roadmap
  paused it for a reason; `--check` reports it with the remedy instead.

Isolation follows D-045's shape because the convention failed here once: the
seam binding in `tests/` is the convention, and two independent guards are the
enforcement — `_default_schedule_client` will not connect under
`PYTEST_CURRENT_TEST`, and `_refuse_live_client` will not mutate through a real
client under it.  Removing either alone still refuses.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from factory.roadmap.workflow import roadmap_workflow_id
from factory.verify.models import FactoryConfig, RoadmapDials
from factory.workgraph.workflow import TASK_QUEUE as EPIC_TASK_QUEUE

SCHEDULE_ID_PREFIX = "ergane-roadmap-"
SPECS_DIR_NAME = "specs"
CREATED, UPDATED, UNCHANGED, FAILED = "created", "updated", "unchanged", "failed"


def schedule_id_for(slug: str) -> str:
    """`ergane-roadmap-<slug>` — the identifier FR-014 requires."""
    return f"{SCHEDULE_ID_PREFIX}{slug}"


class ScheduleUnavailable(Exception):
    """The control plane would not answer. Distinct from "there is no schedule": an
    absent one is a fact a caller can act on, an unreachable engine is not, and FR-017
    turns on the difference."""


@dataclasses.dataclass(frozen=True)
class RoadmapSchedule:
    """One repo's roadmap schedule — what it declares, or what is live."""

    schedule_id: str
    workflow_id: str
    specs_root: str
    target_repo: str
    landing_branch: str
    proxy_url: str
    cadence_s: int
    max_concurrent_epics: int
    max_concurrent_nodes: int
    #: A fact about a live schedule, never a declaration.
    paused: bool = False
    task_queue: str = EPIC_TASK_QUEUE

    def arguments(self) -> dict[str, Any]:
        """`RoadmapInput`'s fields, plus the `landing_branch` declaration."""
        return {
            "specs_root": self.specs_root,
            "target_repo": self.target_repo,
            "proxy_url": self.proxy_url,
            "max_concurrent_epics": self.max_concurrent_epics,
            "max_concurrent_nodes": self.max_concurrent_nodes,
            "landing_branch": self.landing_branch,
        }


@dataclasses.dataclass(frozen=True)
class ScheduleStep:
    """One reported act, in the shape `ergane init` prints its other steps."""

    action: str
    schedule_id: str
    detail: str


#: Every field a manifest declares, in the order a drift report names them.
#: `paused` is deliberately absent — see this module's third decision.
_DECLARED = (
    "workflow_id", "specs_root", "target_repo", "landing_branch",
    "proxy_url", "cadence_s", "max_concurrent_epics", "max_concurrent_nodes",
)


def disagreements(desired: RoadmapSchedule, live: RoadmapSchedule) -> tuple[str, ...]:
    """Every declared field the live schedule states differently — pure, and
    shared by `apply_schedule` and `--check`."""
    moved: list[str] = []
    for name in _DECLARED:
        want, have = getattr(desired, name), getattr(live, name)
        if want != have:
            moved.append(f"{name}: schedule has {have!r}, manifest declares {want!r}")
    return tuple(moved)


def desired_for_repo(
    *, slug: str, repo_root: Path, config: FactoryConfig, proxy_url: str | None = None
) -> RoadmapSchedule:
    """The schedule `repo_root` declares. The specs root is `<repo>/specs` by
    convention: a manifest key would be a second place answering where the specs are."""
    specs_root = str(Path(repo_root) / SPECS_DIR_NAME)
    dials = config.roadmap or RoadmapDials()
    return RoadmapSchedule(
        schedule_id=schedule_id_for(slug),
        workflow_id=roadmap_workflow_id(specs_root),
        specs_root=specs_root,
        target_repo=str(repo_root),
        landing_branch=config.landing_branch,
        proxy_url=proxy_url if proxy_url is not None else resolve_proxy_url(),
        cadence_s=dials.cadence_s,
        max_concurrent_epics=dials.max_concurrent_epics,
        max_concurrent_nodes=dials.max_concurrent_nodes,
    )


def resolve_proxy_url() -> str:
    """Where child epics get their virtual keys. Empty is not a refusal — the created
    step says so instead, because a repo that could not be joined until every
    subsystem was provisioned is the coupling FR-017 rejects."""
    from factory.usage.litellm_client import PROXY_URL_ENV

    return os.environ.get(PROXY_URL_ENV) or ""


async def _default_schedule_client() -> Any:
    """Connect to the operator's Temporal, or refuse and say why (guard one)."""
    from temporalio.client import Client

    from factory.notify.service import (
        DEFAULT_TEMPORAL_ADDRESS,
        DEFAULT_TEMPORAL_NAMESPACE,
        TEMPORAL_ADDRESS_ENV,
        TEMPORAL_NAMESPACE_ENV,
    )

    address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE

    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise ScheduleUnavailable(
            f"refusing to reach the control plane at {address} (namespace "
            f"'{namespace}') while PYTEST_CURRENT_TEST is set: schedules are "
            "shared state, so a test must bind "
            "factory.roadmap.schedule._schedule_client_factory instead"
        )

    try:
        return await Client.connect(address, namespace=namespace)
    except Exception as error:  # noqa: BLE001 - every connect failure reads alike
        raise ScheduleUnavailable(
            f"cannot reach Temporal at {address} (namespace '{namespace}'): {error}"
        ) from None


#: Seam: how this module reaches Temporal.  Rebound in tests.
_schedule_client_factory: Callable[[], Awaitable[Any]] = _default_schedule_client


async def describe_schedule(client: Any, schedule_id: str) -> RoadmapSchedule | None:
    """Read one schedule back, decoded, or `None` when there is no such schedule."""
    from temporalio.service import RPCError, RPCStatusCode

    try:
        described = await client.get_schedule_handle(schedule_id).describe()
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            return None
        raise ScheduleUnavailable(f"cannot read schedule {schedule_id}: {error}") from None

    args = _decoded_arguments(described)
    intervals = list(described.schedule.spec.intervals)
    defaults = RoadmapDials()
    return RoadmapSchedule(
        schedule_id=schedule_id,
        workflow_id=str(described.schedule.action.id),
        specs_root=str(args.get("specs_root", "")),
        target_repo=str(args.get("target_repo", "")),
        landing_branch=str(args.get("landing_branch", "")),
        proxy_url=str(args.get("proxy_url", "")),
        cadence_s=int(intervals[0].every.total_seconds()) if intervals else 0,
        max_concurrent_epics=int(args.get("max_concurrent_epics", defaults.max_concurrent_epics)),
        max_concurrent_nodes=int(args.get("max_concurrent_nodes", defaults.max_concurrent_nodes)),
        paused=bool(described.schedule.state.paused),
    )


def _decoded_arguments(described: Any) -> dict[str, Any]:
    """The action's argument as a mapping, decoded through the description's own
    converter: a described schedule hands them back as the encoded payloads scenario 2
    complains about, never as the dicts that were handed in."""
    args = list(described.schedule.action.args)
    if not args:
        return {}
    if isinstance(args[0], dict):
        return dict(args[0])
    decoded = described.data_converter.payload_converter.from_payloads(args)
    return dict(decoded[0]) if decoded and isinstance(decoded[0], dict) else {}


def _schedule_for(desired: RoadmapSchedule, *, paused: bool) -> Any:
    """Build the Temporal schedule one `RoadmapSchedule` describes."""
    from temporalio.client import (
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleIntervalSpec,
        ScheduleOverlapPolicy,
        SchedulePolicy,
        ScheduleSpec,
        ScheduleState,
    )

    return Schedule(
        action=ScheduleActionStartWorkflow(
            "RoadmapWorkflow",
            args=[desired.arguments()],
            id=desired.workflow_id,
            task_queue=desired.task_queue,
        ),
        spec=ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(seconds=desired.cadence_s))]
        ),
        # Skip, not buffer: a tick landing while the previous roadmap run still
        # works must not queue a second behind it, or a slow epic turns one
        # cadence into an unbounded backlog of duplicate dispatch.
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
        state=ScheduleState(paused=paused),
    )


def _refuse_live_client(client: Any, act: str) -> None:
    """Refuse to mutate a schedule through a real client from a test (guard two).

    It exists because guard one alone was not enough: removing its sentinel
    check and running the suite created five schedules on the operator's live
    namespace, reached by `tests/test_ergane_registry.py` driving a full `ergane
    init` without binding the seam.  D-045's answer, in D-045's shape.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return
    from temporalio.client import Client

    if isinstance(client, Client):
        raise ScheduleUnavailable(
            f"refusing to {act} a schedule through a real Temporal client while "
            "PYTEST_CURRENT_TEST is set: schedules are shared state and this "
            "host's control plane holds the live roadmap"
        )


async def create_schedule(
    client: Any, desired: RoadmapSchedule, *, paused: bool = False
) -> None:
    """Create it.  Nothing rides in the memo: `ScheduleUpdate` has no memo
    field, so a memo could never be reconciled."""
    _refuse_live_client(client, "create")
    await client.create_schedule(desired.schedule_id, _schedule_for(desired, paused=paused))


async def update_schedule(client: Any, desired: RoadmapSchedule) -> None:
    """Reconcile to the declarations, carrying the live `paused` flag across."""
    _refuse_live_client(client, "reconcile")

    from temporalio.client import ScheduleUpdate

    def updater(inputs: Any) -> Any:
        schedule = inputs.description.schedule
        rebuilt = _schedule_for(desired, paused=bool(schedule.state.paused))
        schedule.action, schedule.spec, schedule.policy = (
            rebuilt.action,
            rebuilt.spec,
            rebuilt.policy,
        )
        return ScheduleUpdate(schedule=schedule)

    await client.get_schedule_handle(desired.schedule_id).update(updater)


async def delete_schedule(client: Any, schedule_id: str) -> bool:
    """Delete the schedule; `False` when there was none to delete."""
    _refuse_live_client(client, "delete")

    from temporalio.service import RPCError, RPCStatusCode

    try:
        await client.get_schedule_handle(schedule_id).delete()
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            return False
        raise ScheduleUnavailable(f"cannot delete schedule {schedule_id}: {error}") from None
    return True


def apply_schedule(desired: RoadmapSchedule) -> ScheduleStep:
    """Create or reconcile the repo's schedule, and never raise (FR-017): an
    unreachable engine is a failed *step*, so the scaffold and registry entry the
    operator already has are not lost to it."""
    try:
        return asyncio.run(_apply(desired))
    except ScheduleUnavailable as unavailable:
        return ScheduleStep(FAILED, desired.schedule_id, str(unavailable))


async def _apply(desired: RoadmapSchedule) -> ScheduleStep:
    client = await _schedule_client_factory()
    live = await describe_schedule(client, desired.schedule_id)

    if live is None:
        await create_schedule(client, desired)
        note = "" if desired.proxy_url else " (note: LITELLM_PROXY_URL is unset, so child epics cannot issue keys)"
        return ScheduleStep(
            CREATED,
            desired.schedule_id,
            f"created, starting {desired.workflow_id} every {desired.cadence_s}s "
            f"over {desired.specs_root}{note}",
        )

    moved = disagreements(desired, live)
    if not moved:
        return ScheduleStep(UNCHANGED, desired.schedule_id, "already satisfied; nothing changed")

    await update_schedule(client, desired)
    return ScheduleStep(
        UPDATED, desired.schedule_id, "reconciled to the manifest — " + "; ".join(moved)
    )


def read_schedule(schedule_id: str) -> RoadmapSchedule | None:
    """Read one schedule for `--check`; raises `ScheduleUnavailable`, writes nothing."""

    async def read() -> RoadmapSchedule | None:
        return await describe_schedule(await _schedule_client_factory(), schedule_id)

    return asyncio.run(read())


def remove_schedule(schedule_id: str) -> bool:
    """Delete one schedule for `repo forget`; raises `ScheduleUnavailable`."""

    async def remove() -> bool:
        return await delete_schedule(await _schedule_client_factory(), schedule_id)

    return asyncio.run(remove())


def format_step(step: ScheduleStep) -> str:
    """The one line `ergane init` prints about the schedule."""
    return f"schedule: {step.action} {step.schedule_id} — {step.detail}"
