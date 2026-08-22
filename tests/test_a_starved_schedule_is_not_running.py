"""The schedule's state is decided once, on the location, from what it has done.

Two files printed the same sentence — `state = "paused" if …schedule_paused else
"running"` in `factory/cli/status.py` and again in `factory/cli/roadmap.py` — so
`running` was *defined* as `not paused`, and a schedule whose every tick had been
skipped for six hours printed `(running)` beside a near-future `next tick`.
Fixing one of the two leaves the other lying and a third caller inherits it, so
the verdict belongs on `RoadmapLocation`, beside `refusal`: one computation, four
possible answers, no renderer inventing a fifth.

The trigger is **how long since a tick actually started**, and the case that
decides this module is the one where it isn't. `num_actions_skipped_overlap` is a
lifetime counter — it never decreases, so a schedule that skipped twice last
Tuesday reports non-zero forever. Wiring the verdict to it passes the starved
test and the running test and produces a permanent warning, which is read once
and ignored: the same outage in a new costume.
`test_a_large_lifetime_skipped_count_with_a_recent_start_is_running` is that
control, and `test_the_verdict_ignores_the_skipped_count_in_both_directions`
proves the count moves nothing at all.

`unknown` is the third answer and it is load-bearing. A description this tree
cannot fully read — an older server, a fake predating the fields, a
calendar-only schedule with no interval — must not be guessed into `running` or
`starved`. Printing a guess as a verdict is the whole of the reported defect.

Every location here is constructed by hand: no client, no describe call, no
clock the test does not supply. That is US2-S7, and
`test_the_verdict_is_pure_and_no_socket_is_opened` holds it to it.
"""

from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from factory.roadmap.discovery import (
    STARVED_AFTER_INTERVALS,
    RoadmapLocation,
    RoadmapOwner,
    RoadmapScheduleState,
)

SPECS_ROOT = "/srv/factory/ergane/specs"
BARE_ID = "roadmap-specs"
SCHEDULE_ID = "ergane-roadmap"

#: The clock every verdict below is decided against. Supplied, never read from
#: the host: a test whose answer depends on when it runs is not a control.
NOW = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)

CADENCE_S = 300
#: The grace window, spelled from the constant rather than from `600`, so a
#: threshold moved in the source moves these cases with it instead of leaving
#: them asserting a number the code no longer uses.
GRACE_S = STARVED_AFTER_INTERVALS * CADENCE_S


def _location(**dials: Any) -> RoadmapLocation:
    """A schedule-owned location that is healthy until a dial says otherwise.

    Nothing here is fetched. `resolve_roadmap` builds one of these off a
    described schedule, and US1's tests prove that read; this module starts from
    the built object, because the verdict may reach for nothing else.
    """
    fields: dict[str, Any] = dict(
        root_name="specs",
        bare_workflow_id=BARE_ID,
        run_prefix=f"{BARE_ID}-",
        owner=RoadmapOwner.SCHEDULE,
        workflow_id=f"{BARE_ID}-2026-08-22T14:55:00Z",
        schedule_id=SCHEDULE_ID,
        schedule_paused=False,
        next_action_at=(NOW + timedelta(minutes=5)).isoformat(),
        looked_for=(f"workflow id {BARE_ID}",),
        skipped_overlap_count=0,
        last_action_started_at=(NOW - timedelta(minutes=1)).isoformat(),
        schedule_created_at=(NOW - timedelta(hours=12)).isoformat(),
        cadence_s=CADENCE_S,
    )
    fields.update(dials)
    return RoadmapLocation(**fields)


def _started(ago: timedelta) -> str:
    return (NOW - ago).isoformat()


# --- the two verdicts that were one boolean -----------------------------------


def test_a_schedule_whose_last_actual_start_is_stale_is_starved() -> None:
    """US2-S1 / FR-005, FR-006: the reported outage, decided correctly.

    Seventy-six skipped ticks at a five-minute cadence is six hours in which
    nothing ran, and the only thing either renderer asked was whether the
    schedule was paused. It was not, so both said `running`.
    """
    location = _location(
        last_action_started_at=_started(timedelta(hours=6)), skipped_overlap_count=76
    )

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.STARVED
    assert location.schedule_state_at(NOW) == "starved"


def test_a_schedule_that_started_a_tick_within_the_grace_window_is_running() -> None:
    """US2-S2 / FR-005: a schedule that is ticking is running, as it always was."""
    location = _location(last_action_started_at=_started(timedelta(minutes=1)))

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING


@pytest.mark.parametrize(
    "ago_s,expected",
    [
        (GRACE_S - 1, RoadmapScheduleState.RUNNING),
        (GRACE_S, RoadmapScheduleState.RUNNING),
        (GRACE_S + 1, RoadmapScheduleState.STARVED),
    ],
    ids=["just inside", "exactly two intervals", "just outside"],
)
def test_the_threshold_is_two_cadence_intervals(
    ago_s: int, expected: RoadmapScheduleState
) -> None:
    """US2-S1 / FR-006: two intervals, and the boundary is asserted from both sides.

    Two rather than one because a single grace tick absorbs ordinary clock and
    dispatch jitter; a one-interval threshold calls a healthy schedule starved
    every time a tick lands a second late. The number is a named constant so the
    next operator moves it against evidence instead of finding it inside a
    conditional.
    """
    location = _location(last_action_started_at=_started(timedelta(seconds=ago_s)))

    assert location.schedule_state_at(NOW) is expected


def test_the_threshold_constant_is_two() -> None:
    """FR-006: stated in the code, not spelled into a comparison."""
    assert STARVED_AFTER_INTERVALS == 2


# --- the false-alarm control, which decides this story ------------------------


def test_a_large_lifetime_skipped_count_with_a_recent_start_is_running() -> None:
    """US2-S3 / FR-007: **the control**. The count is evidence, never the trigger.

    `num_actions_skipped_overlap` never decreases. A schedule that skipped two
    ticks last Tuesday reports non-zero for the rest of its life, so a verdict
    wired to `count > 0` is a warning that is permanently on — read once,
    ignored thereafter, and the operator is back in front of a floor report that
    tells them nothing. This is the assertion a counter-driven verdict fails.
    """
    location = _location(
        skipped_overlap_count=76, last_action_started_at=_started(timedelta(minutes=1))
    )

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING
    # The evidence is still there for the sentence to print — carried, not acted on.
    assert location.skipped_overlap_count == 76


@pytest.mark.parametrize("count", [None, 0, 1, 76, 100_000])
def test_the_verdict_ignores_the_skipped_count_in_both_directions(
    count: int | None,
) -> None:
    """FR-007: the count moves nothing, in either direction.

    The pair matters as a pair. A recent start is `running` however high the
    count, and a stale start is `starved` however low it is — including zero,
    which is what a schedule whose runs are failing outright reports.
    """
    recent = _location(
        skipped_overlap_count=count, last_action_started_at=_started(timedelta(minutes=1))
    )
    stale = _location(
        skipped_overlap_count=count, last_action_started_at=_started(timedelta(hours=6))
    )

    assert recent.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING
    assert stale.schedule_state_at(NOW) is RoadmapScheduleState.STARVED


# --- the operator's own decision is not a fault -------------------------------


@pytest.mark.parametrize(
    "ago", [timedelta(minutes=1), timedelta(hours=6), timedelta(days=90)]
)
def test_a_paused_schedule_is_paused_however_long_since_its_last_tick(
    ago: timedelta,
) -> None:
    """US2-S4 / FR-005: a paused schedule not ticking is the operator's decision."""
    location = _location(schedule_paused=True, last_action_started_at=_started(ago))

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.PAUSED


def test_a_paused_schedule_is_paused_even_when_nothing_else_could_be_read() -> None:
    """US2-S4: the paused flag is a fact that *was* read, so it answers first.

    Degrading a paused schedule to `unknown` because its cadence was unreadable
    would hide the one thing the operator most needs to see — that dispatch is
    off because they turned it off.
    """
    location = _location(
        schedule_paused=True,
        cadence_s=None,
        last_action_started_at=None,
        schedule_created_at=None,
    )

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.PAUSED


# --- a schedule minutes old has not failed at anything yet --------------------


def test_a_never_ticked_schedule_inside_its_first_intervals_is_running() -> None:
    """US2-S5 / FR-005: `created_at` is the reference when there is no start.

    New coverage, not preserved coverage. `tests/test_roadmap_first_tick_on_
    fresh_init.py` reads as though it guards this window: it does not — it drives
    the *workflow's* first tick against a freshly-initialised tree and imports
    neither `factory.roadmap.discovery` nor a renderer. A false `starved` here
    makes `ergane init` look broken to every new user, thirty seconds in.
    """
    location = _location(
        last_action_started_at=None,
        schedule_created_at=_started(timedelta(minutes=1)),
    )

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING


def test_a_never_ticked_schedule_past_its_first_intervals_is_starved() -> None:
    """US2-S1, US2-S5: the other half of the never-ticked window.

    A schedule created twelve hours ago that has still started nothing is not in
    its grace period; it is the outage, on its very first tick.
    """
    location = _location(
        last_action_started_at=None,
        schedule_created_at=_started(timedelta(hours=12)),
    )

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.STARVED


def test_a_last_start_is_preferred_over_creation_as_the_reference() -> None:
    """US2-S1: `created_at` is the fallback, never the measure when a start exists.

    Reversed, a long-lived healthy schedule reads as starved forever, because
    its creation recedes while its ticks stay current.
    """
    ticking = _location(
        last_action_started_at=_started(timedelta(minutes=1)),
        schedule_created_at=_started(timedelta(days=30)),
    )
    stopped = _location(
        last_action_started_at=_started(timedelta(hours=6)),
        schedule_created_at=_started(timedelta(minutes=1)),
    )

    assert ticking.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING
    assert stopped.schedule_state_at(NOW) is RoadmapScheduleState.STARVED


# --- not knowing is the third answer ------------------------------------------


@pytest.mark.parametrize(
    "dials,why",
    [
        ({"cadence_s": None}, "no cadence: 'overdue' has no scale"),
        ({"cadence_s": 0}, "a zero cadence is not a schedule that ticks constantly"),
        (
            {"last_action_started_at": None, "schedule_created_at": None},
            "no tick history and no creation time: nothing to measure against",
        ),
        (
            {"last_action_started_at": "not a timestamp"},
            "a start time this reader cannot parse",
        ),
        ({"schedule_paused": None}, "the paused flag itself could not be read"),
    ],
    ids=["no cadence", "zero cadence", "no history", "unparseable start", "no flag"],
)
def test_a_reading_that_could_not_be_taken_is_unknown(
    dials: dict[str, Any], why: str
) -> None:
    """US2-S6 / FR-008: never `running`, never `starved`.

    052 landed the principle that a degraded reading still renders the rest, and
    this is its verdict half: the report is complete and the schedule line says
    it does not know. Printing a guess as a verdict is what caused this finding
    in the first place.
    """
    state = _location(**dials).schedule_state_at(NOW)

    assert state is RoadmapScheduleState.UNKNOWN, why
    assert state not in (RoadmapScheduleState.RUNNING, RoadmapScheduleState.STARVED)


def test_the_empty_location_is_unknown_rather_than_running() -> None:
    """FR-008 on the emptiest floor there is: a location where no rung hit.

    This is the shape a new user's very first `ergane status` resolves, and the
    one where every observed fact is `None`.
    """
    location = RoadmapLocation(
        root_name="specs",
        bare_workflow_id=BARE_ID,
        run_prefix=f"{BARE_ID}-",
        owner=RoadmapOwner.NONE,
        workflow_id=None,
        schedule_id=None,
        schedule_paused=None,
        next_action_at=None,
        looked_for=(f"workflow id {BARE_ID}",),
    )

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.UNKNOWN


# --- the word, and the shape of the answer ------------------------------------


def test_the_four_answers_are_the_four_words_the_spec_names() -> None:
    """FR-005, and the word is `starved`.

    Not `stalled` — `factory/mergequeue/models.py` owns that for a merge attempt
    past its stall window. Not `parked`, which `factory/cli/roadmap.py` prints
    two lines below the schedule line for parked epics. Not `blocked`, which
    `CONTEXT.md` gives to an agent's question. Only the last of the three is in
    `CONTEXT.md`, so a fruitless grep there is not permission to reuse the other
    two. One token, so the two renderers stay grep-comparable.
    """
    assert {state.value for state in RoadmapScheduleState} == {
        "paused",
        "running",
        "starved",
        "unknown",
    }
    assert RoadmapScheduleState.STARVED.value == "starved"
    # A renderer interpolating the state directly gets the word, not the repr.
    assert f"{RoadmapScheduleState.STARVED}" == "starved"


# --- the verdict reads the location and nothing else --------------------------


def test_the_verdict_is_pure_and_no_socket_is_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2-S7 / FR-005: computed from a constructed location, no client bound.

    There is no client in this module to bind — the location is built by hand —
    so the assertion that would otherwise be untestable is made mechanical: any
    socket opened during the computation fails the test. The property that reads
    the wall clock is exercised too, because that is what a renderer calls.
    """

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the verdict opened a socket: it must read only the location")

    monkeypatch.setattr(socket, "socket", _refuse)

    location = _location(last_action_started_at=_started(timedelta(minutes=1)))

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING
    assert location.schedule_state_at(NOW) is location.schedule_state_at(NOW)
    assert location.schedule_state in RoadmapScheduleState


def test_the_property_decides_against_the_wall_clock() -> None:
    """FR-005: the no-argument property is what a renderer reads.

    `schedule_state_at` exists so a test can supply the clock; `schedule_state`
    supplies it from `datetime.now`, which is the only reason a verdict needs
    anything beyond the location's own fields — and it is a clock read, not I/O.
    """
    now = datetime.now(timezone.utc)
    ticking = _location(last_action_started_at=(now - timedelta(seconds=30)).isoformat())
    starved = _location(last_action_started_at=(now - timedelta(hours=6)).isoformat())

    assert ticking.schedule_state is RoadmapScheduleState.RUNNING
    assert starved.schedule_state is RoadmapScheduleState.STARVED


# --- the evidence half of the sentence ----------------------------------------


def test_the_elapsed_time_since_the_last_actual_start_is_available_as_evidence() -> None:
    """FR-007, FR-010: what the starved sentence says *besides* the verdict.

    The renderer needs two numbers it must not derive twice — how long since a
    tick actually started, and how many ticks were skipped — and neither decides
    anything. `None` when the schedule has never ticked: "how long since a tick
    started" has no answer when none ever did, and a renderer says so rather
    than printing the schedule's age as though it were a tick.
    """
    ticking = _location(last_action_started_at=_started(timedelta(hours=6)))
    never = _location(last_action_started_at=None)
    unreadable = _location(last_action_started_at="not a timestamp")

    assert ticking.seconds_since_last_start(NOW) == 6 * 60 * 60
    assert never.seconds_since_last_start(NOW) is None
    assert unreadable.seconds_since_last_start(NOW) is None


def test_a_start_time_in_the_future_is_not_starved() -> None:
    """Clock skew between this host and the server is not an outage.

    A negative elapsed time is closer to "just started" than to "never started",
    and a floor report that cries starvation because two clocks disagree by a
    second is the false alarm this spec exists to avoid.
    """
    location = _location(last_action_started_at=(NOW + timedelta(minutes=1)).isoformat())

    assert location.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING
