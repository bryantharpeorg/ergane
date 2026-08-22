"""Where a roadmap actually lives, and what owns its dispatch.

`ergane roadmap start` creates a workflow whose id is `roadmap-<root>`
(`roadmap_workflow_id`). A Temporal *schedule* never runs under that id: it
appends the tick's scheduled time, so the runs are `roadmap-<root>-<timestamp>`
and the bare id resolves to nothing at all. On 2026-08-15 that made
`ergane roadmap status specs` answer `no roadmap 'specs' is running here` while
`temporal workflow list` showed the run, and the operator fell back to raw
`temporal schedule toggle` because `resume` could not find the roadmap it was
resuming (finding `cli/roadmap-verbs-cannot-see-schedule-driven-runs`).

Resolution is a ladder, tried in this order and named in the same order when
none of its rungs hits (FR-007):

1. the bare workflow `roadmap-<root>` — what `roadmap start` creates;
2. the schedule whose action starts workflows whose id begins with that bare
   id. Never a hardcoded schedule id: the live one is `ergane-roadmap`, chosen
   by an operator's hand, and nothing maps a specs root to that string;
3. the newest run named `roadmap-<root>-<timestamp>`.

The bare rung is tried first because it is exact, it is cheap, and it is the
only rung a floor started by `roadmap start` needs — a bare roadmap is resolved
without ever listing a schedule, which is what keeps those verbs byte-identical
to their pre-046 selves and what lets them work against a server with no
schedule support at all.

`owner` is the other half of the answer, and the half `pause`/`resume` need:
pausing the current run of a schedule-driven roadmap is a lie, because the next
tick starts a fresh run and dispatch continues. A caller that means to stop
dispatch must act on `RoadmapOwner.SCHEDULE` at the schedule.

Rungs 2 and 3 treat any RPC failure as a miss. A server that predates schedule
listing or advanced visibility answers `unimplemented`, and the spec's
Assumptions say the verbs degrade rather than abort in that case; a genuinely
unreachable server has already failed at the connect, and a genuinely broken
namespace has already failed on rung 1, which does propagate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from temporalio.service import RPCError, RPCStatusCode

from factory.roadmap.workflow import roadmap_workflow_id


class RoadmapOwner(str, Enum):
    """What owns dispatch — and therefore what `pause`/`resume` must act on."""

    #: A bare `roadmap-<root>` workflow, started by `ergane roadmap start`.
    WORKFLOW = "workflow"
    #: A Temporal schedule; its runs are timestamped and replaced every tick.
    SCHEDULE = "schedule"
    #: A timestamped run with no schedule the client could name. Something
    #: started it on a tick, but this client cannot see what.
    RUN = "run"
    #: Nothing at all.
    NONE = "none"


class RoadmapScheduleState(str, Enum):
    """What a schedule is *doing* — the answer that used to be `not paused`.

    Four answers, because three of them were being collapsed into one. A
    renderer asks for this and prints the word; it does not decide it, and two
    renderers cannot disagree about a fact neither of them computes.

    Named `RoadmapScheduleState` rather than `ScheduleState` because
    `temporalio.client.ScheduleState` already owns that name and the sibling
    module imports it (`factory.roadmap.schedule`, where it carries the paused
    flag a schedule *declares*). Two things called `ScheduleState` in one
    package is a collision a reader resolves by accident.
    """

    #: The operator turned dispatch off. Not a fault, and not starvation.
    PAUSED = "paused"
    #: A tick actually started within the grace window. What `running` was
    #: always meant to claim.
    RUNNING = "running"
    #: Unpaused, and no tick has actually started for longer than the window
    #: allows. Under the `SKIP` overlap policy this is what a wedged run looks
    #: like from outside: every tick fires, every tick is skipped, nothing fails.
    STARVED = "starved"
    #: The reading could not be taken. A third answer on purpose: printing a
    #: guess as a verdict is the defect this module is closing.
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


#: How many cadence intervals may pass with no actual start before a schedule is
#: called starved. Two, not one: a single grace tick absorbs ordinary clock and
#: dispatch jitter, so a tick that lands a second late is not an outage. It is a
#: chosen threshold rather than a measured one, and it is named here so the next
#: operator can move it against evidence instead of rediscovering it inside a
#: conditional (FR-006).
STARVED_AFTER_INTERVALS = 2


def _seconds_since(now: datetime, stamp: str | None) -> float | None:
    """How long ago `stamp` was, or `None` if that cannot be said.

    The location carries times as the strings `_described_time` phrased, so this
    is the read back. Anything unparseable — an absent field, a server phrasing
    the time some other way — is "not known" rather than a guess, because the
    verdict must degrade to `unknown` and never raise (FR-003, FR-008). A naive
    timestamp is read as UTC, which is what Temporal hands back and what the
    alternative — a `TypeError` inside a status render — is worth avoiding.
    """
    if not isinstance(stamp, str):
        return None
    try:
        started = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - started).total_seconds()


def _elapsed(seconds: int) -> str:
    """`21600` at the scale an operator reads it: `6h 0m`.

    Coarsening upward on purpose. The number that matters in a starved line is
    the order of magnitude — minutes is a late tick, hours is the outage — and a
    line that prints `21600` makes the reader do the division that the sentence
    exists to save them.
    """
    if seconds < 60:
        return f"{seconds}s"
    minutes, _ = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def render_schedule_line(
    schedule_id: str,
    state: RoadmapScheduleState | str,
    *,
    seconds_since_last_start: int | None = None,
    skipped_overlap_count: int | None = None,
) -> str:
    """The `schedule:` line both verbs print, phrased once for both of them.

    `ergane status` and `ergane roadmap status` each built this sentence out of
    one boolean, in two files, so `running` meant `not paused` twice over and
    fixing either left the other lying (FR-009). The verdict is decided on the
    location; this is the other half — the words — and it lives beside the
    verdict for the same reason: a third caller inherits the sentence rather
    than reinventing it.

    Three of the four states are a bare word, and the healthy one is
    byte-identical to what both verbs printed before this existed (FR-011):
    `schedule: ergane-roadmap (running)`.

    `starved` is the state that has to argue its case, so it carries its
    evidence inside the parentheses (FR-010): how long since a tick actually
    started, and how many the overlap policy skipped. Neither decides the
    verdict — the count is a lifetime counter and could not — and either may be
    unreadable, in which case the clause says which rather than printing a zero
    that reads as a measurement.
    """
    word = str(state)
    if word != RoadmapScheduleState.STARVED.value:
        return f"schedule: {schedule_id} ({word})"
    age = (
        f"{_elapsed(seconds_since_last_start)} since a tick last started"
        if seconds_since_last_start is not None
        else "no tick has ever started"
    )
    skipped = (
        f"{skipped_overlap_count} tick{'' if skipped_overlap_count == 1 else 's'} skipped"
        if skipped_overlap_count is not None
        else "skipped count unknown"
    )
    return f"schedule: {schedule_id} ({word}: {age}, {skipped})"


@dataclass(frozen=True)
class RoadmapLocation:
    """The answer to "where is roadmap `<root>`, and what owns it?"

    `workflow_id` is the workflow to query or signal — the bare id, or the
    newest timestamped run — and is `None` when a schedule owns dispatch but has
    not ticked yet. `looked_for` is every rung that was tried, in order, phrased
    for the operator: it is what an empty answer has to say (FR-007).

    The last four fields are what the schedule has *done*, as distinct from what
    it declares. They are carried here because a renderer cannot reach back to
    Temporal to phrase a sentence, and because reading them at the describe and
    dropping them is how a schedule that had skipped every tick for six hours
    printed `(running)`. Every one of them is `None` when it could not be read:
    an older server, a description without an `info`, a spec with no interval.
    `None` means "not known", never zero and never a guess (FR-003).
    """

    root_name: str
    bare_workflow_id: str
    run_prefix: str
    owner: RoadmapOwner
    workflow_id: str | None
    schedule_id: str | None
    schedule_paused: bool | None
    next_action_at: str | None
    looked_for: tuple[str, ...]
    #: Lifetime count of ticks the overlap policy skipped. It never decreases,
    #: so it is evidence inside a sentence and never a health signal on its own.
    skipped_overlap_count: int | None = None
    #: When a tick last *actually* started a run — the newest `recent_actions`
    #: entry, not the oldest. `None` on a schedule that has never ticked.
    last_action_started_at: str | None = None
    #: When the schedule itself was created: what to measure against when there
    #: is no last start. A schedule minutes old is not starved.
    schedule_created_at: str | None = None
    #: How often it ticks. Without it, "a tick is overdue" has no scale.
    cadence_s: int | None = None

    @property
    def found(self) -> bool:
        return self.owner is not RoadmapOwner.NONE

    @property
    def refusal(self) -> str:
        """`no roadmap 'specs' is running here (looked for …)`, naming every rung.

        With the full ladder in force this names the bare id, the schedule and
        the run prefix. With the ladder cut back to its bare rung it degrades to
        exactly the pre-046 sentence, which is what makes the control test
        (SC-004) a control and not a re-write.
        """
        return (
            f"no roadmap '{self.root_name}' is running here "
            f"(looked for {', then '.join(self.looked_for)})"
        )

    def schedule_state_at(self, now: datetime) -> RoadmapScheduleState:
        """`paused`, `running`, `starved` or `unknown`, decided here and once.

        Both renderers used to compute this themselves, out of one boolean:
        `running` meant `not paused`, so a schedule that had skipped every tick
        for six hours said `running` beside a near-future `next tick`. Fixing
        one of the two would have left the other lying. This is the fix, in the
        shape `refusal` above already uses — a computed property phrasing a fact
        the renderer is not entitled to invent.

        Read in this order, and the order is the answer:

        - **paused first**, because it is a fact that *was* read, and a paused
          schedule not ticking is the operator's decision rather than a fault.
          It answers even when nothing else could be read, so a degraded
          reading never hides the one state the operator caused themselves.
        - then **what could not be read** — no cadence, an unparseable start,
          no history and no creation time — which is `unknown`. Never
          `running`, never `starved` (FR-008): not knowing is a third answer,
          and printing a guess as a verdict is this module's whole defect.
        - then **how long since a tick actually started**, against the cadence.
          Past `STARVED_AFTER_INTERVALS` intervals it is `starved`; inside them
          it is `running`. A schedule that has never ticked is measured from
          its creation instead, so one that is minutes old is running rather
          than starved — `_find_owning_schedule` already promises such a
          schedule is reported, and a false `starved` makes `ergane init` look
          broken to every new user.

        `skipped_overlap_count` decides nothing here, deliberately. It is a
        lifetime counter that never decreases, so `count > 0` is a warning that
        is permanently on — read once, ignored after, which is this outage in a
        new costume. It is evidence for the sentence, alongside
        `seconds_since_last_start`, and the trigger is the elapsed time.

        The clock is a parameter so a caller can decide against a supplied
        `now`; the property below supplies the wall clock. Nothing here reads a
        client, a file or a socket — the location's own fields are the whole
        input (FR-005).
        """
        if self.schedule_paused is None:
            return RoadmapScheduleState.UNKNOWN
        if self.schedule_paused:
            return RoadmapScheduleState.PAUSED
        if not isinstance(self.cadence_s, int) or self.cadence_s <= 0:
            return RoadmapScheduleState.UNKNOWN
        since = _seconds_since(
            now, self.last_action_started_at or self.schedule_created_at
        )
        if since is None:
            return RoadmapScheduleState.UNKNOWN
        if since > STARVED_AFTER_INTERVALS * self.cadence_s:
            return RoadmapScheduleState.STARVED
        return RoadmapScheduleState.RUNNING

    @property
    def schedule_state(self) -> RoadmapScheduleState:
        """`schedule_state_at`, decided against the wall clock — what a renderer reads."""
        return self.schedule_state_at(datetime.now(timezone.utc))

    def seconds_since_last_start(self, now: datetime) -> int | None:
        """How long since a tick *actually* started, for the sentence to name.

        The evidence half of a starved line, and the other half of what the
        skipped count is for: neither decides the verdict, and neither should
        be derived twice in two renderers. `None` when the schedule has never
        ticked or the time could not be read — "how long since a tick started"
        has no answer when none ever did, and the schedule's own age is not a
        substitute for one.
        """
        elapsed = _seconds_since(now, self.last_action_started_at)
        return None if elapsed is None else int(elapsed)

    def schedule_line_at(self, now: datetime) -> str:
        """The `schedule:` line this location is worth, against a supplied clock.

        One clock for the verdict and for the evidence it names: reading the
        wall clock twice could report `starved` beside an elapsed time measured
        a moment earlier, which is a small lie in the middle of a line whose
        whole job is not to tell one.
        """
        return render_schedule_line(
            self.schedule_id or "",
            self.schedule_state_at(now),
            seconds_since_last_start=self.seconds_since_last_start(now),
            skipped_overlap_count=self.skipped_overlap_count,
        )

    @property
    def schedule_line(self) -> str:
        """`schedule_line_at`, against the wall clock — what a renderer prints."""
        return self.schedule_line_at(datetime.now(timezone.utc))


@dataclass(frozen=True)
class _Found:
    """One rung's hit: what it found and what that means for dispatch."""

    owner: RoadmapOwner
    workflow_id: str | None
    schedule_id: str | None = None
    schedule_paused: bool | None = None
    next_action_at: str | None = None
    skipped_overlap_count: int | None = None
    last_action_started_at: str | None = None
    schedule_created_at: str | None = None
    cadence_s: int | None = None


@dataclass(frozen=True)
class _Lookup:
    """One rung of the ladder: how it is described, and how it is tried."""

    describe: Callable[[str], str]
    find: Callable[[Any, str], Awaitable[_Found | None]]


async def _find_bare_workflow(client: Any, bare_id: str) -> _Found | None:
    """Rung 1: the exact id `ergane roadmap start` uses.

    A NOT_FOUND is a miss and the ladder climbs. Any other RPC failure is a real
    transport problem and propagates, so a broken namespace still reports itself
    as a transport error rather than as an empty floor.
    """
    handle = client.get_workflow_handle(bare_id)
    try:
        await handle.describe()
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            return None
        raise
    return _Found(owner=RoadmapOwner.WORKFLOW, workflow_id=bare_id)


async def _find_owning_schedule(client: Any, bare_id: str) -> _Found | None:
    """Rung 2: the schedule whose action starts this roadmap's workflows.

    The list entry carries the action's workflow *type*, not its id, so each
    schedule is described to read `action.id` — the field that actually says
    which workflow a tick would start. Matching is on that id, never on the
    schedule's own name, because the schedule's name is an operator's choice.

    A schedule that owns dispatch is reported even when it has not ticked yet:
    `workflow_id` is then the newest run if one exists, and `None` otherwise.

    The description is read for what the schedule has *done* as well as for what
    is next. Those four reads are the helpers below, and each degrades to `None`
    on its own: a description this ladder cannot fully read still resolves.
    """
    try:
        schedules = await client.list_schedules()
        entries = [entry async for entry in schedules]
    except RPCError:
        # A server without schedule support: the spec's Assumptions say degrade.
        return None

    for entry in entries:
        try:
            described = await client.get_schedule_handle(entry.id).describe()
        except RPCError:
            continue
        action_id = getattr(getattr(described, "schedule", None), "action", None)
        action_id = getattr(action_id, "id", None)
        if not isinstance(action_id, str) or not action_id.startswith(bare_id):
            continue
        state = getattr(getattr(described, "schedule", None), "state", None)
        info = getattr(described, "info", None)
        next_times = list(getattr(info, "next_action_times", None) or [])
        return _Found(
            owner=RoadmapOwner.SCHEDULE,
            workflow_id=await _newest_run(client, f"{bare_id}-"),
            schedule_id=entry.id,
            schedule_paused=bool(getattr(state, "paused", False)),
            next_action_at=next_times[0].isoformat() if next_times else None,
            skipped_overlap_count=_skipped_overlap(info),
            last_action_started_at=_last_action_started_at(info),
            schedule_created_at=_described_time(getattr(info, "created_at", None)),
            cadence_s=_cadence_seconds(described),
        )
    return None


async def _find_newest_run(client: Any, bare_id: str) -> _Found | None:
    """Rung 3: the newest `roadmap-<root>-<timestamp>` run, schedule or not.

    Reached when no schedule could be named — either because none exists or
    because the server would not list them. Something started the run on a tick
    this client cannot see, so `pause` on this rung can only signal the run, and
    its caller has to say so.
    """
    run_id = await _newest_run(client, f"{bare_id}-")
    if run_id is None:
        return None
    return _Found(owner=RoadmapOwner.RUN, workflow_id=run_id)


async def _newest_run(client: Any, prefix: str) -> str | None:
    """The most recently started workflow whose id begins with `prefix`.

    The id prefix goes into the list filter so the server does the narrowing,
    and is re-checked here so a server that ignores the predicate cannot widen
    the answer. Ordering is by start time, falling back to the id itself — the
    timestamp a schedule appends sorts lexicographically anyway.
    """
    try:
        executions = [
            execution
            async for execution in client.list_workflows(
                f'WorkflowId STARTS_WITH "{prefix}"'
            )
            if str(execution.id).startswith(prefix)
        ]
    except RPCError:
        # A server without advanced visibility: degrade, per the Assumptions.
        return None
    if not executions:
        return None
    newest = max(
        executions,
        key=lambda execution: (
            getattr(execution, "start_time", None) is not None,
            getattr(execution, "start_time", None),
            execution.id,
        ),
    )
    return str(newest.id)


def _described_time(value: Any) -> str | None:
    """A described timestamp, phrased the way `next_action_at` already is.

    Anything that is not a datetime — an absent field, an older server's `None`,
    a description that predates the field — is "not known" rather than a guess,
    because this read must degrade and never raise (FR-003).
    """
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else None


def _skipped_overlap(info: Any) -> int | None:
    """How many ticks the overlap policy has skipped, over this schedule's life.

    `_schedule_for` sets `ScheduleOverlapPolicy.SKIP` deliberately, so a tick
    landing on a still-working run is skipped rather than queued. This is the
    count of those skips, and it is a lifetime counter: it never decreases, so a
    reader states it as evidence and never triggers on it.
    """
    count = getattr(info, "num_actions_skipped_overlap", None)
    return int(count) if isinstance(count, int) else None


def _last_action_started_at(info: Any) -> str | None:
    """When this schedule last *actually* started a run.

    `recent_actions` is documented by the SDK as "10 most recent actions, oldest
    first", so the newest is its **last** element — the opposite end from
    `next_action_times` above, which ascends into the future and wants its
    first. Taking `[0]` here compiles, raises nothing, and reports a start up to
    ten cadences stale, which reads as starvation on a schedule that is ticking
    perfectly.

    A skipped tick leaves no entry: every result is built from the SDK's
    `start_workflow_result` and carries a run id, and a skipped tick starts no
    workflow. So the newest entry is a true "when did this last really run", not
    "when was a tick last due".
    """
    recent = list(getattr(info, "recent_actions", None) or [])
    if not recent:
        return None
    return _described_time(getattr(recent[-1], "started_at", None))


def _cadence_seconds(described: Any) -> int | None:
    """How often this schedule ticks — the scale an overdue tick is judged on.

    Read off `described.schedule.spec.intervals`, the same field
    `factory.roadmap.schedule.describe_schedule` decodes from the same object.
    This is the `Schedule` half of a description, not the `ScheduleInfo` half:
    a description with no `spec`, and a spec with no interval (a calendar-only
    schedule), both answer "not known" — never zero, which would say it ticks
    constantly.
    """
    spec = getattr(getattr(described, "schedule", None), "spec", None)
    intervals = list(getattr(spec, "intervals", None) or [])
    if not intervals:
        return None
    total_seconds = getattr(getattr(intervals[0], "every", None), "total_seconds", None)
    return int(total_seconds()) if callable(total_seconds) else None


BARE_WORKFLOW_LOOKUP = _Lookup(
    describe=lambda bare_id: f"workflow id {bare_id}",
    find=_find_bare_workflow,
)
OWNING_SCHEDULE_LOOKUP = _Lookup(
    describe=lambda bare_id: f"a schedule starting workflows named {bare_id}*",
    find=_find_owning_schedule,
)
NEWEST_RUN_LOOKUP = _Lookup(
    describe=lambda bare_id: f"runs named {bare_id}-*",
    find=_find_newest_run,
)

#: The ladder, in the order it is tried and in the order a refusal names it.
#: This is the seam the control test (SC-004) cuts back to `BARE_WORKFLOW_LOOKUP`
#: alone to reproduce the pre-046 outcome on a schedule-driven floor.
LOOKUPS: tuple[_Lookup, ...] = (
    BARE_WORKFLOW_LOOKUP,
    OWNING_SCHEDULE_LOOKUP,
    NEWEST_RUN_LOOKUP,
)


async def resolve_roadmap(client: Any, specs_root: str) -> RoadmapLocation:
    """Resolve roadmap `<root>` to what runs it and what owns its dispatch.

    Returns a location whose `found` is False rather than raising, so the caller
    owns the refusal: `status` refuses, and a later reader (US1's floor status)
    renders "no roadmap" as one line of a larger picture.
    """
    from pathlib import PurePosixPath

    bare_id = roadmap_workflow_id(specs_root)
    root_name = PurePosixPath(specs_root.rstrip("/")).name
    tried: list[str] = []
    for lookup in LOOKUPS:
        tried.append(lookup.describe(bare_id))
        found = await lookup.find(client, bare_id)
        if found is None:
            continue
        return RoadmapLocation(
            root_name=root_name,
            bare_workflow_id=bare_id,
            run_prefix=f"{bare_id}-",
            owner=found.owner,
            workflow_id=found.workflow_id,
            schedule_id=found.schedule_id,
            schedule_paused=found.schedule_paused,
            next_action_at=found.next_action_at,
            looked_for=tuple(tried),
            skipped_overlap_count=found.skipped_overlap_count,
            last_action_started_at=found.last_action_started_at,
            schedule_created_at=found.schedule_created_at,
            cadence_s=found.cadence_s,
        )
    # Nothing was found, so nothing is known about a schedule's ticks. Passed
    # explicitly rather than left to the defaults: this is the path a new user's
    # very first `ergane status` takes, and a field added at one site only is a
    # `TypeError` on the emptiest floor there is.
    return RoadmapLocation(
        root_name=root_name,
        bare_workflow_id=bare_id,
        run_prefix=f"{bare_id}-",
        owner=RoadmapOwner.NONE,
        workflow_id=None,
        schedule_id=None,
        schedule_paused=None,
        next_action_at=None,
        looked_for=tuple(tried),
        skipped_overlap_count=None,
        last_action_started_at=None,
        schedule_created_at=None,
        cadence_s=None,
    )
