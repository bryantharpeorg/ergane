"""The discovery ladder carries what a schedule has *done*, not just what is next.

`_find_owning_schedule` binds the whole `ScheduleInfo` at
`factory/roadmap/discovery.py`, reads one field off it — `next_action_times` —
and drops the rest on the floor. Everything a reader needs to say whether a
schedule is actually running was on that object and never left the describe
call: how many ticks it has skipped because a run was still going, when a tick
last *actually* started, when the schedule was created, and how often it ticks.

So `ergane status` could only phrase the schedule's state from the paused flag,
and a schedule that had skipped every tick for six hours printed `(running)`.
No renderer can tell the truth about a fact that never reached it; this module
is the read that lets it.

Two ends of two lists, and they are opposite ends. `next_action_times` ascends
into the future, so the soonest tick is `[0]`. `recent_actions` is documented by
the SDK as *"10 most recent actions, oldest first"*, so the last actual start is
`[-1]`. Copying the neighbouring idiom one field over compiles, passes the
obvious test, and reports a start up to ten cadences stale — which manufactures
starvation on a schedule that is ticking perfectly. `test_the_last_start_is_the
_newest_action_not_the_oldest` is the assertion that fails at the wrong end.

The last test here is the one that decides this story. FR-008 turns an
unreadable cadence into `unknown`, and `unknown` is a state the code that reads
these facts is *designed* to tolerate — so a fake left half-extended does not
fail, it quietly yields `unknown` and every verdict scenario downstream passes
without exercising a verdict. Each of this tree's four `describe()` fakes has
two holes, in two different objects: the `ScheduleInfo` half, and the `Schedule`
half where the cadence lives. `test_every_describe_fake_in_the_tree_reads_a_
cadence` resolves a location through all four and refuses `unknown` from any of
them, and `test_the_parity_table_names_every_describe_fake_in_the_tree` keeps
that table honest when a fifth fake arrives.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

import pytest
from temporalio.service import RPCError, RPCStatusCode

from factory.roadmap import schedule as schedule_module
from factory.roadmap.discovery import RoadmapLocation, RoadmapOwner, resolve_roadmap
from factory.roadmap.schedule import RoadmapSchedule, disagreements

from tests import fake_schedules
from tests.test_roadmap_schedule_discovery import (
    FakeSchedule,
    FakeTemporalClient,
    _AsyncIter,
)

SPECS_ROOT = "/srv/factory/ergane/specs"
BARE_ID = "roadmap-specs"
SCHEDULE_ID = "ergane-roadmap"

CADENCE = timedelta(minutes=5)
CREATED_AT = datetime(2026, 8, 22, 3, 0, tzinfo=timezone.utc)
NEXT_TICK = datetime(2026, 8, 22, 15, 5, tzinfo=timezone.utc)

#: Three starts, oldest first, exactly as `ScheduleInfo.recent_actions` orders
#: them. An hour apart so the wrong end of the list is unmistakable rather than
#: a near miss.
OLDEST_START = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
MIDDLE_START = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
NEWEST_START = datetime(2026, 8, 22, 11, 0, tzinfo=timezone.utc)


def _schedule(**dials: Any) -> FakeSchedule:
    """One seeded schedule owning this roadmap's dispatch, with dials applied."""
    return FakeSchedule(
        id=SCHEDULE_ID,
        action_workflow_id=BARE_ID,
        next_action_times=[NEXT_TICK],
        cadence=CADENCE,
        created_at=CREATED_AT,
        **dials,
    )


async def _resolve(client: Any) -> RoadmapLocation:
    return await resolve_roadmap(client, SPECS_ROOT)


# --- the facts that used to be dropped ----------------------------------------


async def test_the_skipped_count_and_the_last_start_reach_the_location() -> None:
    """US1-S1 / FR-001: both facts survive the describe call.

    Seven skipped ticks is what six hours of a wedged run looks like at this
    cadence, and it is the number the operator never saw.
    """
    client = FakeTemporalClient(
        schedules=[_schedule(skipped_overlap=7, recent_action_starts=[NEWEST_START])]
    )

    location = await _resolve(client)

    assert location.owner is RoadmapOwner.SCHEDULE
    assert location.skipped_overlap_count == 7
    assert location.last_action_started_at == NEWEST_START.isoformat()


async def test_the_last_start_is_the_newest_action_not_the_oldest() -> None:
    """US1-S6 / FR-001: the ordering control, and it fails at the wrong end.

    The SDK documents `recent_actions` as *"10 most recent actions, oldest
    first"*, so the newest is `[-1]`. The neighbouring read takes
    `next_action_times[0]` because future times ascend; the same index one field
    over reports a start up to ten cadences stale and calls a healthy schedule
    starved.
    """
    client = FakeTemporalClient(
        schedules=[
            _schedule(recent_action_starts=[OLDEST_START, MIDDLE_START, NEWEST_START])
        ]
    )

    location = await _resolve(client)

    assert location.last_action_started_at == NEWEST_START.isoformat()
    assert location.last_action_started_at != OLDEST_START.isoformat()
    assert location.last_action_started_at != MIDDLE_START.isoformat()


async def test_the_location_carries_the_schedules_cadence() -> None:
    """US1-S2 / FR-002: read off `described.schedule.spec.intervals`.

    Not off `info`: this is the second of the two halves of a description, and
    the one three of the tree's four fakes had no attribute for at all. Without
    a cadence, "a tick is overdue" has no scale and means nothing.
    """
    client = FakeTemporalClient(schedules=[_schedule()])

    location = await _resolve(client)

    assert location.cadence_s == int(CADENCE.total_seconds()) == 300


async def test_a_schedule_that_has_never_ticked_carries_its_creation_instead() -> None:
    """US1-S3 / FR-002: a schedule minutes old is not starved.

    `_find_owning_schedule`'s docstring already promises a schedule that owns
    dispatch is reported even when it has not ticked yet, so the location is
    found and its `workflow_id` is `None`. `created_at` is what a reader
    measures against when there is no last start to measure against.
    """
    client = FakeTemporalClient(schedules=[_schedule(recent_action_starts=[])])

    location = await _resolve(client)

    assert location.found and location.owner is RoadmapOwner.SCHEDULE
    assert location.workflow_id is None
    assert location.last_action_started_at is None
    assert location.schedule_created_at == CREATED_AT.isoformat()


# --- the degrade control ------------------------------------------------------


class _DescribesLikeAnOlderServer:
    """The tree's own fake with the observed half of its description taken off.

    Two shapes degrade and FR-003 covers both: a description carrying no `info`
    at all, and one whose `info` is present but silent about the new fields.
    Both are real — they are what every fake in this tree returned before this
    story, and what a server older than the fields returns today.

    Wrapping the real fake rather than inventing a fifth one is what makes this
    a control instead of a rewrite: every *existing* field is still produced by
    the code the other tests exercise, so "every existing field intact" is an
    assertion about this tree and not about a shape invented here.
    """

    #: `info` present, only `next_action_times` on it, and no `spec` on the
    #: schedule — the four fakes, verbatim, as they stood before this story.
    PRE_085 = "pre-085"
    #: No `info` attribute whatsoever.
    NO_INFO = "no-info"

    def __init__(self, client: Any, *, shape: str) -> None:
        self._client = client
        self._shape = shape

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def get_schedule_handle(self, schedule_id: str) -> Any:
        return _OlderDescription(self._client.get_schedule_handle(schedule_id), self._shape)


class _OlderDescription:
    def __init__(self, handle: Any, shape: str) -> None:
        self._handle = handle
        self._shape = shape

    async def describe(self) -> Any:
        described = await self._handle.describe()
        aged = SimpleNamespace(
            id=described.id,
            schedule=SimpleNamespace(
                action=described.schedule.action,
                state=described.schedule.state,
            ),
        )
        if self._shape == _DescribesLikeAnOlderServer.PRE_085:
            aged.info = SimpleNamespace(
                next_action_times=list(described.info.next_action_times)
            )
        return aged


@pytest.mark.parametrize(
    "shape", [_DescribesLikeAnOlderServer.PRE_085, _DescribesLikeAnOlderServer.NO_INFO]
)
async def test_an_unreadable_description_degrades_instead_of_raising(shape: str) -> None:
    """US1-S4 / FR-003: the new facts unset, every existing field intact.

    052 landed the principle that a degraded reading still renders the rest, and
    a floor report that dies on a schedule it cannot fully read is a worse
    regression than the bug being fixed. This is the whole of it: no exception,
    a found location, and `None` where a fact could not be read rather than a
    guess.
    """
    client = _DescribesLikeAnOlderServer(
        FakeTemporalClient(schedules=[_schedule(paused=True)]), shape=shape
    )

    location = await _resolve(client)

    assert location.found and location.owner is RoadmapOwner.SCHEDULE
    assert location.schedule_id == SCHEDULE_ID
    assert location.schedule_paused is True
    assert location.skipped_overlap_count is None
    assert location.last_action_started_at is None
    assert location.schedule_created_at is None
    assert location.cadence_s is None
    # The one existing field that comes off `info`: kept where `info` is
    # readable, absent where it is not — which is what it did before this story.
    expected = NEXT_TICK.isoformat() if shape == _DescribesLikeAnOlderServer.PRE_085 else None
    assert location.next_action_at == expected


async def test_the_empty_answer_still_constructs() -> None:
    """FR-003, and the path a new user's very first `ergane status` takes.

    `resolve_roadmap` builds a `RoadmapLocation` twice, and the second one is
    reached when no rung hits. A new field passed at only one site is a
    `TypeError` here, on the emptiest floor there is.
    """
    location = await _resolve(FakeTemporalClient())

    assert not location.found and location.owner is RoadmapOwner.NONE
    assert location.refusal.startswith("no roadmap 'specs' is running here")
    assert (
        location.skipped_overlap_count,
        location.last_action_started_at,
        location.schedule_created_at,
        location.cadence_s,
    ) == (None, None, None, None)


# --- the observed facts stay out of the declared set --------------------------

#: What this story added: facts about what a schedule has done. None of them is
#: a declaration, so none may enter `_DECLARED` (`cadence_s` is absent from this
#: tuple because it was already declared — a manifest states a cadence).
_OBSERVED = ("skipped_overlap_count", "last_action_started_at", "schedule_created_at")


def _declaring(**dials: Any) -> RoadmapSchedule:
    return RoadmapSchedule(
        schedule_id=SCHEDULE_ID,
        workflow_id=BARE_ID,
        specs_root=SPECS_ROOT,
        target_repo="/srv/factory/ergane",
        landing_branch="ergane-buildout",
        proxy_url="http://proxy:4000",
        cadence_s=300,
        max_concurrent_epics=1,
        max_concurrent_nodes=1,
        **dials,
    )


def test_no_observed_fact_can_appear_in_a_drift_report() -> None:
    """US1-S5 / FR-004: `_DECLARED` is unchanged, byte for byte.

    An observed fact in the declared set is a permanent phantom disagreement:
    `apply_schedule` would report drift on every run against something no
    manifest can state, and the module's own comment says `paused` is
    deliberately absent for exactly that reason.
    """
    assert schedule_module._DECLARED == (
        "workflow_id", "specs_root", "target_repo", "landing_branch",
        "proxy_url", "cadence_s", "max_concurrent_epics", "max_concurrent_nodes",
    )
    assert set(_OBSERVED).isdisjoint(schedule_module._DECLARED)

    desired = _declaring()
    live = dataclasses.replace(desired, target_repo="/srv/somebody-elses", paused=True)
    moved = disagreements(desired, live)

    assert [line.split(":")[0] for line in moved] == ["target_repo"]
    assert not any(fact in line for line in moved for fact in _OBSERVED)


# --- the fake-parity control --------------------------------------------------


class _MissingWorkflow:
    """Rung 1's miss, so the ladder climbs to the schedule under test."""

    async def describe(self) -> Any:
        raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")


class _LadderOverTheScheduleServer:
    """The three client methods the ladder calls, over `FakeScheduleServer`.

    `tests/fake_schedules.py` models a schedule *server* and deliberately
    nothing more — create, describe, update, delete, and a loud failure for
    anything else — so the ladder cannot reach its `describe()` unaided. This
    supplies only the reaching. The description under test is the fake's own,
    which is the point of the parity table.
    """

    def __init__(self, server: fake_schedules.FakeScheduleServer) -> None:
        self._server = server

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _MissingWorkflow:
        return _MissingWorkflow()

    def get_schedule_handle(self, schedule_id: str) -> Any:
        return self._server.get_schedule_handle(schedule_id)

    async def list_schedules(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        return _AsyncIter(SimpleNamespace(id=id) for id in self._server.schedules)

    def list_workflows(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        return _AsyncIter([])


async def _through_the_schedule_server_fake() -> RoadmapLocation:
    server = fake_schedules.FakeScheduleServer()
    desired = fake_schedules.desired_for(
        Path("/srv/factory/ergane"), specs_root=SPECS_ROOT, cadence_s=300
    )
    fake_schedules.seed(server, desired)
    return await _resolve(_LadderOverTheScheduleServer(server))


async def _through_the_discovery_fake() -> RoadmapLocation:
    return await _resolve(FakeTemporalClient(schedules=[_schedule()]))


async def _through_the_wedge_fake() -> RoadmapLocation:
    from tests import test_roadmap_wedge_visibility as wedge

    return await _resolve(
        wedge.FakeTemporalClient(
            schedules=[wedge.FakeSchedule(id=SCHEDULE_ID, action_workflow_id=BARE_ID)]
        )
    )


async def _through_the_status_fake() -> RoadmapLocation:
    from tests import test_ergane_status as status

    return await _resolve(
        status.FakeTemporalClient(
            schedules=[status.FakeSchedule(id=SCHEDULE_ID, action_workflow_id=BARE_ID)]
        )
    )


#: Every `describe()` fake in this tree that answers for a schedule, and how to
#: resolve a location through it. Kept honest by the census test below.
DESCRIBE_FAKES: tuple[tuple[str, Callable[[], Awaitable[RoadmapLocation]]], ...] = (
    ("tests/fake_schedules.py", _through_the_schedule_server_fake),
    ("tests/test_roadmap_schedule_discovery.py", _through_the_discovery_fake),
    ("tests/test_roadmap_wedge_visibility.py", _through_the_wedge_fake),
    ("tests/test_ergane_status.py", _through_the_status_fake),
)


@pytest.mark.parametrize(
    "fake,resolve", DESCRIBE_FAKES, ids=[name for name, _ in DESCRIBE_FAKES]
)
async def test_every_describe_fake_in_the_tree_reads_a_cadence(
    fake: str, resolve: Callable[[], Awaitable[RoadmapLocation]]
) -> None:
    """US1-S7 / FR-002: the green-for-nothing control.

    An unreadable cadence is `unknown`, and `unknown` is a state the reader is
    designed to tolerate — so a fake that supplies no cadence does not fail, it
    passes while exercising nothing. That is this defect arriving through the
    test suite instead of the CLI, and this is the assertion that refuses it.
    """
    location = await resolve()

    assert location.owner is RoadmapOwner.SCHEDULE, f"{fake} did not resolve a schedule"
    assert isinstance(location.cadence_s, int) and location.cadence_s > 0, (
        f"{fake} resolves cadence_s={location.cadence_s!r}: an unreadable cadence "
        "is `unknown`, and `unknown` makes every verdict scenario downstream pass "
        "without exercising a verdict"
    )


def test_the_parity_table_names_every_describe_fake_in_the_tree() -> None:
    """The census that keeps the table above from going quietly stale.

    A schedule `describe()` fake is exactly a test module that mentions
    `next_action_times` — the field every one of them builds and nothing else
    in `tests/` has reason to name. A fifth fake fails here rather than slipping
    past the parity check unmeasured.
    """
    tests_dir = Path(__file__).parent
    census = {
        path.name
        for path in sorted(tests_dir.glob("*.py"))
        if "next_action_times" in path.read_text(encoding="utf-8")
    }

    assert census - {Path(__file__).name} == {
        Path(name).name for name, _ in DESCRIBE_FAKES
    }
