"""An in-memory Temporal schedule server, for 034 US6.

Nothing in the suite may reach a real control plane: one Temporal serves this
host, it holds the live `ergane-roadmap` schedule with real carry-over state,
and a fixture that created or deleted a schedule there would be destroying
production (034 plan, trap 11).  So
`factory.roadmap.schedule._schedule_client_factory` is bound to this, shaped
like the pieces of `temporalio.client.Client` the lifecycle touches and only
those, so a call to anything else fails loudly.

Stored actions hold real `Payload` protos from `temporalio.converter.default()`,
exactly as a described schedule does (measured live; transcript in
`tests/test_ergane_init_schedule.py`), so the production decode path runs for
real — a decoder that only worked on plain dicts would fail here.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from temporalio.api.common.v1 import Payload
from temporalio.client import (
    Schedule,
    ScheduleActionExecutionStartWorkflow,
    ScheduleActionResult,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.converter import default as default_converter
from temporalio.service import RPCError, RPCStatusCode

from factory.roadmap import schedule as schedule_module
from factory.roadmap.schedule import RoadmapSchedule, schedule_id_for

_CONVERTER = default_converter()

#: When a fake schedule was created, unless a test says otherwise. Fixed rather
#: than relative to now: a description is data, and a fixture whose facts move
#: with the clock cannot be asserted on byte for byte.
SCHEDULE_CREATED_AT = datetime(2026, 8, 22, 3, 0, tzinfo=timezone.utc)


def action_results(starts: Iterable[datetime]) -> list[ScheduleActionResult]:
    """`ScheduleInfo.recent_actions`, from the times its actions started.

    The real SDK type, not a namespace shaped like one, and built the way the
    SDK builds it: every entry carries a `first_execution_run_id`, because every
    entry is decoded from a `start_workflow_result`. That is also why a *skipped*
    tick leaves no entry at all — it starts no workflow and there is nothing to
    put there — and why the newest entry means "when this last really ran".

    Order is the caller's, and the SDK's order is **oldest first**: the field is
    documented "10 most recent actions, oldest first", so a fake that seeds
    ascending times is seeding what a real describe returns. Every reader of
    this list therefore wants its last element.
    """
    return [
        ScheduleActionResult(
            scheduled_at=started,
            started_at=started,
            action=ScheduleActionExecutionStartWorkflow(
                workflow_id=f"roadmap-{started.isoformat()}",
                first_execution_run_id=f"run-{index}",
            ),
        )
        for index, started in enumerate(starts)
    ]


def _encoded(args: Iterable[Any]) -> list[Payload]:
    """Store arguments the way the server does: as encoded payloads."""
    plain = [arg for arg in args if not isinstance(arg, Payload)]
    return [arg for arg in args if isinstance(arg, Payload)] + list(
        _CONVERTER.payload_converter.to_payloads(plain)
    )


class _Handle:
    """One schedule's handle: describe, update, delete — nothing else."""

    def __init__(self, server: "FakeScheduleServer", schedule_id: str) -> None:
        self._server = server
        self.id = schedule_id

    def _stored(self) -> Schedule:
        stored = self._server.schedules.get(self.id)
        if stored is None:
            raise RPCError(f"schedule not found: {self.id}", RPCStatusCode.NOT_FOUND, b"")
        return stored

    async def describe(self) -> Any:
        # Recorded before the lookup: a describe that 404s is still a call made
        # against the server, and "looked before it leapt" is what create proves.
        self._server.calls.append(("describe", self.id))
        return SimpleNamespace(
            id=self.id,
            schedule=self._stored(),
            data_converter=_CONVERTER,
            # The observed half. `schedule` needs nothing added for the cadence:
            # `_stored()` hands back the real `Schedule` the factory built, spec
            # and intervals included. `info` is the half nothing built, and a
            # description silent about what a schedule has actually done is how
            # a starved schedule reads as a healthy one (085/US1).
            info=SimpleNamespace(
                next_action_times=[],
                num_actions_skipped_overlap=self._server.skipped_overlap.get(self.id, 0),
                recent_actions=action_results(
                    self._server.recent_action_starts.get(self.id, ())
                ),
                created_at=self._server.created_at,
            ),
        )

    async def update(self, updater: Any, **_kwargs: Any) -> None:
        described = await self.describe()
        self._server.calls.append(("update", self.id))
        result = updater(ScheduleUpdateInput(description=described))
        assert isinstance(result, ScheduleUpdate), f"updater returned {result!r}"
        result.schedule.action.args = _encoded(result.schedule.action.args)
        self._server.schedules[self.id] = result.schedule

    async def delete(self, **_kwargs: Any) -> None:
        self._stored()
        self._server.calls.append(("delete", self.id))
        del self._server.schedules[self.id]


class FakeScheduleServer:
    """The schedules one control plane holds, and every call made against it."""

    def __init__(self) -> None:
        self.schedules: dict[str, Schedule] = {}
        #: Every call, in order: `("create"|"describe"|"update"|"delete", id)`.
        self.calls: list[tuple[str, str]] = []
        #: What a schedule has *done*, by id — the half of a description no
        #: manifest declares and this server would otherwise be silent about.
        #: Ticks that actually started, oldest first, as the SDK orders them:
        self.recent_action_starts: dict[str, list[datetime]] = {}
        #: and the lifetime count of ticks the SKIP policy dropped instead.
        self.skipped_overlap: dict[str, int] = {}
        self.created_at: datetime = SCHEDULE_CREATED_AT

    async def create_schedule(self, id: str, schedule: Schedule, **_kwargs: Any) -> _Handle:
        if id in self.schedules:
            raise RPCError(f"already exists: {id}", RPCStatusCode.ALREADY_EXISTS, b"")
        self.calls.append(("create", id))
        stored = replace(schedule, action=schedule.action)
        stored.action.args = _encoded(schedule.action.args)
        self.schedules[id] = stored
        return _Handle(self, id)

    def get_schedule_handle(self, id: str) -> _Handle:
        return _Handle(self, id)

    # Reading a stored schedule back, for assertions.

    def arguments(self, schedule_id: str) -> dict[str, Any]:
        """The stored action's decoded arguments — never the ones handed in."""
        action = self.schedules[schedule_id].action
        return dict(_CONVERTER.payload_converter.from_payloads(action.args)[0])

    def snapshot(self, schedule_id: str) -> tuple[Any, ...]:
        """Everything a re-run could change, for the idempotence comparison."""
        stored = self.schedules[schedule_id]
        return (
            stored.action.id,
            stored.action.task_queue,
            tuple(sorted(self.arguments(schedule_id).items())),
            tuple(interval.every for interval in stored.spec.intervals),
            stored.state.paused,
        )


def desired_for(
    repo_root: Path,
    *,
    slug: str = "widgets",
    specs_root: str | None = None,
    landing_branch: str = "main",
    cadence_s: int = 300,
    epics: int = 1,
    nodes: int = 1,
) -> RoadmapSchedule:
    """The schedule a conforming repo declares, with named breaks applied."""
    root = specs_root if specs_root is not None else str(repo_root / "specs")
    return RoadmapSchedule(
        schedule_id=schedule_id_for(slug),
        workflow_id=f"roadmap-{Path(root).name}",
        specs_root=root,
        target_repo=str(repo_root),
        landing_branch=landing_branch,
        proxy_url=schedule_module.resolve_proxy_url(),
        cadence_s=cadence_s,
        max_concurrent_epics=epics,
        max_concurrent_nodes=nodes,
    )


def seed(
    server: FakeScheduleServer, desired: RoadmapSchedule, *, paused: bool = False
) -> None:
    """Put `desired` on `server` as a previous `ergane init` would have."""
    asyncio.run(schedule_module.create_schedule(server, desired, paused=paused))
    server.calls.clear()
