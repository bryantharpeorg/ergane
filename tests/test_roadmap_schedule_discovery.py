"""046 US2: the roadmap verbs can see schedule-driven runs.

`ergane roadmap start` creates a workflow whose id is `roadmap-<root>`. A
Temporal *schedule* never runs under that id — it appends the tick's scheduled
time, so the runs are `roadmap-<root>-<timestamp>` and the bare id resolves to
nothing at all. On 2026-08-15 that made `ergane roadmap status specs` refuse a
roadmap that `temporal workflow list` could see, and the operator fell back to
raw `temporal schedule toggle` because `resume` could not find the roadmap it
was resuming (finding `cli/roadmap-verbs-cannot-see-schedule-driven-runs`).

The verbs now resolve through `factory.roadmap.discovery`: bare workflow →
owning schedule → newest timestamped run, in that order, naming all three when
none of them hits (FR-007). `pause`/`resume` act on the thing that owns
dispatch — the schedule, when one owns it — because pausing the current run of
a scheduled roadmap is a lie: the next tick starts a fresh run and dispatch
continues (plan trap 2). Every schedule assertion here reads the schedule
*back* rather than trusting the verb's own report.

Nothing here needs a Temporal server, and it could not use one: the
time-skipping test server implements neither schedules nor workflow listing,
measured in this worktree before these tests were written --

    $ uv run python -c "... create_schedule / list_workflows on the test env ..."
    SCHEDULE ERROR: RPCError Method temporal.api.workflowservice.v1.WorkflowService/CreateSchedule is unimplemented
    LIST WF ERROR: RPCError Method temporal.api.workflowservice.v1.WorkflowService/ListWorkflowExecutions is unimplemented

so the floor is a fake client installed at `Client.connect`, the precedent
`tests/test_doctor_probes.py::fake_temporal` set. The *action* objects it hands
back are the real SDK `ScheduleActionStartWorkflow`, so the field the discovery
reads (`action.id`) is a genuine one.

------------------------------------------------------------------------------
Verbatim output, run in this worktree (see the per-test docstrings for which
case each block belongs to).

Before the fix -- the 2026-08-15 failure, reproduced by the control test with
the discovery ladder cut back to its bare-workflow rung (SC-004):

    ergane: no roadmap 'specs' is running here (looked for workflow id roadmap-specs)

After the fix -- `ergane roadmap status specs` on the same schedule-driven
floor (stdout, captured by test_status_reports_the_newest_run_and_names_both):

    schedule: ergane-roadmap (running)
    run: roadmap-specs-2026-08-15T15:00:00Z
    next tick: 2026-08-15T16:00:00+00:00
    dispatch: running
    concurrency: 1 epic(s), 1 node(s)
    running: 011-agent-sandbox
    parked: 0
    specs:
      [*] 011-agent-sandbox: ready (landed=False, promoted=False)

`ergane roadmap pause specs`, same floor (stdout):

    paused schedule ergane-roadmap: the schedule owns dispatch, so no further run will start

`ergane roadmap resume specs`, same floor (stdout):

    resumed schedule ergane-roadmap: the schedule owns dispatch, so the next tick will start a run

Nothing at all on the floor -- the refusal names every rung, in the order tried
(stderr):

    ergane: no roadmap 'specs' is running here (looked for workflow id roadmap-specs, then a schedule starting workflows named roadmap-specs*, then runs named roadmap-specs-*)

`uv run pytest -q` in this worktree, with this file and the discovery it drives
in place:

    2398 passed, 44 skipped, 4 warnings in 259.78s (0:04:19)
------------------------------------------------------------------------------
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable, Iterable, NamedTuple

import pytest
import temporalio.client
from temporalio.client import (
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.service import RPCError, RPCStatusCode

from factory.cli import main as main_module
from factory.roadmap import discovery
from factory.roadmap.workflow import RoadmapSpecStatus, RoadmapStatus
from factory.roadmap.models import SpecState
from tests.fake_schedules import SCHEDULE_CREATED_AT, action_results

SPECS_ROOT = "/srv/factory/ergane/specs"
#: What a fake schedule ticks at, unless a test says otherwise. Every fake in
#: this tree must supply one: an unreadable cadence resolves to `unknown`, which
#: the reader tolerates by design, so a fake without one exercises nothing.
DEFAULT_CADENCE = timedelta(minutes=5)
BARE_ID = "roadmap-specs"
RUN_PREFIX = "roadmap-specs-"
OLDER_RUN = "roadmap-specs-2026-08-15T14:00:00Z"
NEWEST_RUN = "roadmap-specs-2026-08-15T15:00:00Z"
#: Named by an operator's hand; nothing maps a specs root to it, which is why
#: discovery matches on the action's workflow id and never on this string
#: (plan trap 3). It appears here only as seed data.
SCHEDULE_ID = "ergane-roadmap"


# --- the floor ---------------------------------------------------------------


def _status_document() -> RoadmapStatus:
    return RoadmapStatus(
        specs=[
            RoadmapSpecStatus(
                spec_dir="011-agent-sandbox",
                state=SpecState.READY,
                dispatchable=True,
                blockers=[],
                landed=False,
                unlanded=[],
            )
        ],
        running=["011-agent-sandbox"],
        parked=[],
        max_concurrent_epics=1,
        max_concurrent_nodes=1,
        paused=False,
    )


@dataclass
class FakeSchedule:
    """One schedule, with the paused flag the handle mutates and reads back.

    The last three dials are what it has *done* rather than what it declares
    (085/US1). They default to a schedule created but never ticked, which is a
    real state and the one a fresh `ergane init` is in; a test that means a
    ticking schedule seeds `recent_action_starts` and says so.
    """

    id: str
    action_workflow_id: str
    paused: bool = False
    next_action_times: list[datetime] = field(default_factory=list)
    cadence: timedelta = DEFAULT_CADENCE
    skipped_overlap: int = 0
    #: Ticks that actually started, oldest first, as the SDK orders them.
    recent_action_starts: list[datetime] = field(default_factory=list)
    created_at: datetime = SCHEDULE_CREATED_AT


class _FakeScheduleHandle:
    def __init__(self, client: "FakeTemporalClient", schedule: FakeSchedule) -> None:
        self._client = client
        self._schedule = schedule

    async def describe(self) -> Any:
        return SimpleNamespace(
            id=self._schedule.id,
            schedule=SimpleNamespace(
                # The real SDK action type: `action.id` is the field discovery
                # matches on, not a shape invented for this test.
                action=ScheduleActionStartWorkflow(
                    "RoadmapWorkflow",
                    id=self._schedule.action_workflow_id,
                    task_queue="ergane",
                ),
                state=SimpleNamespace(paused=self._schedule.paused, note=None),
                # The real SDK spec type, for the same reason: the cadence
                # discovery reads is `spec.intervals[0].every`, the field
                # `describe_schedule` already decodes off this same object.
                spec=ScheduleSpec(
                    intervals=[ScheduleIntervalSpec(every=self._schedule.cadence)]
                ),
            ),
            info=SimpleNamespace(
                next_action_times=list(self._schedule.next_action_times),
                num_actions_skipped_overlap=self._schedule.skipped_overlap,
                recent_actions=action_results(self._schedule.recent_action_starts),
                created_at=self._schedule.created_at,
            ),
        )

    async def pause(self, *, note: str | None = None) -> None:
        self._client.schedule_calls.append(("pause", self._schedule.id))
        self._schedule.paused = True

    async def unpause(self, *, note: str | None = None) -> None:
        self._client.schedule_calls.append(("unpause", self._schedule.id))
        self._schedule.paused = False


class _FakeWorkflowHandle:
    def __init__(self, client: "FakeTemporalClient", workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    async def describe(self) -> Any:
        self._client.described.append(self.id)
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(id=self.id, workflow_type="RoadmapWorkflow")

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self._client.queried.append((self.id, name))
        return self._client.workflows[self.id].status

    async def signal(self, name: str, *args: Any, **kwargs: Any) -> None:
        self._client.signals.append((self.id, name))


@dataclass
class FakeWorkflow:
    status: RoadmapStatus
    start_time: datetime


class _AsyncIter:
    def __init__(self, items: Iterable[Any]) -> None:
        self._items = list(items)

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for item in self._items:
                yield item

        return gen()


class FakeTemporalClient:
    """Just enough Temporal to resolve a roadmap and act on what owns it."""

    def __init__(
        self,
        *,
        workflows: dict[str, FakeWorkflow] | None = None,
        schedules: list[FakeSchedule] | None = None,
        schedules_unimplemented: bool = False,
        listing_unimplemented: bool = False,
    ) -> None:
        self.workflows = dict(workflows or {})
        self.schedules = list(schedules or [])
        self._schedules_unimplemented = schedules_unimplemented
        self._listing_unimplemented = listing_unimplemented
        self.described: list[str] = []
        self.queried: list[tuple[str, str]] = []
        self.signals: list[tuple[str, str]] = []
        self.schedule_calls: list[tuple[str, str]] = []
        self.schedule_lists = 0
        self.workflow_list_queries: list[str | None] = []

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _FakeWorkflowHandle:
        return _FakeWorkflowHandle(self, workflow_id)

    def get_schedule_handle(self, schedule_id: str) -> _FakeScheduleHandle:
        for schedule in self.schedules:
            if schedule.id == schedule_id:
                return _FakeScheduleHandle(self, schedule)
        raise AssertionError(f"no such schedule seeded: {schedule_id}")

    async def list_schedules(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        self.schedule_lists += 1
        if self._schedules_unimplemented:
            raise RPCError(
                "Method temporal.api.workflowservice.v1.WorkflowService/ListSchedules "
                "is unimplemented",
                RPCStatusCode.UNIMPLEMENTED,
                b"",
            )
        return _AsyncIter(SimpleNamespace(id=s.id) for s in self.schedules)

    def list_workflows(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        self.workflow_list_queries.append(query)
        if self._listing_unimplemented:
            raise RPCError(
                "Method temporal.api.workflowservice.v1.WorkflowService/"
                "ListWorkflowExecutions is unimplemented",
                RPCStatusCode.UNIMPLEMENTED,
                b"",
            )
        prefix = _prefix_from(query)
        return _AsyncIter(
            SimpleNamespace(id=wf_id, start_time=wf.start_time)
            for wf_id, wf in sorted(self.workflows.items())
            if prefix is None or wf_id.startswith(prefix)
        )


def _prefix_from(query: str | None) -> str | None:
    """Honour a `WorkflowId STARTS_WITH "..."` filter, the only one sent."""
    if query is None:
        return None
    assert "STARTS_WITH" in query, f"unexpected list filter: {query}"
    return query.split('"')[1]


@pytest.fixture
def fake_temporal(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeTemporalClient]:
    def setup(**kwargs: Any) -> FakeTemporalClient:
        client = FakeTemporalClient(**kwargs)

        async def _connect(target_host: str, **connect_kwargs: Any) -> FakeTemporalClient:
            return client

        monkeypatch.setattr(temporalio.client.Client, "connect", _connect)
        return client

    return setup


def _at(hour: int) -> datetime:
    return datetime(2026, 8, 15, hour, 0, 0, tzinfo=timezone.utc)


def _just_ticked() -> list[datetime]:
    """A tick that actually started a moment ago, as `recent_actions` carries it.

    Relative to the wall clock, unlike every other stamp in this module, and
    deliberately: 085 made the schedule's rendered state a judgement about *how
    long since a tick started*, so a fixed last-start would read `running` the
    day it was written and `starved` every day after. The floor around it stays
    2026-08-15 — those are ids and next-tick times, which are data — while this
    is the one fact whose age is the point.
    """
    return [datetime.now(timezone.utc) - timedelta(seconds=30)]


def scheduled_floor(
    setup: Callable[..., FakeTemporalClient], **kwargs: Any
) -> FakeTemporalClient:
    """The 2026-08-15 floor: two timestamped runs, a schedule, no bare workflow.

    The schedule is *ticking*: it started a run half a minute ago, so it renders
    `(running)` on its own merits rather than because nothing paused it. A
    schedule seeded with no starts at all is a different floor — and, once its
    creation is more than a grace window old, a starved one.
    """
    return setup(
        workflows={
            OLDER_RUN: FakeWorkflow(_status_document(), _at(14)),
            NEWEST_RUN: FakeWorkflow(_status_document(), _at(15)),
        },
        schedules=[
            FakeSchedule(
                id=SCHEDULE_ID,
                action_workflow_id=BARE_ID,
                next_action_times=[_at(16)],
                recent_action_starts=_just_ticked(),
            )
        ],
        **kwargs,
    )


# --- the CLI -----------------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def invoke(*argv: str) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


# ============================================================================
# T001 / US2-S1 — status finds the schedule-driven run
# ============================================================================


def test_status_reports_the_newest_run_and_names_both(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S1: the newest run's status, naming the run id and the schedule.

    Two timestamped runs are seeded; the 15:00 one is newer, and it is the one
    queried. Verbatim stdout of this run:

        schedule: ergane-roadmap (running)
        run: roadmap-specs-2026-08-15T15:00:00Z
        next tick: 2026-08-15T16:00:00+00:00
        dispatch: running
        concurrency: 1 epic(s), 1 node(s)
        running: 011-agent-sandbox
        parked: 0
        specs:
          [*] 011-agent-sandbox: ready (landed=False, promoted=False)
    """
    client = scheduled_floor(fake_temporal)

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 0, result.stderr
    assert f"run: {NEWEST_RUN}" in result.stdout
    assert f"schedule: {SCHEDULE_ID}" in result.stdout
    # The status document itself, not merely the disposition.
    assert "running: 011-agent-sandbox" in result.stdout
    # It queried the newest run and nothing else.
    assert client.queried == [(NEWEST_RUN, "roadmap_status")]
    # And it did not invent the schedule id: it read the action's workflow id.
    assert client.schedule_lists == 1


def test_status_names_the_schedules_paused_state_and_next_tick(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S1: paused/running belongs to the schedule when the schedule owns dispatch.

    Verbatim first line of stdout with the schedule paused:

        schedule: ergane-roadmap (paused)
    """
    client = scheduled_floor(fake_temporal)
    client.schedules[0].paused = True

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 0, result.stderr
    assert f"schedule: {SCHEDULE_ID} (paused)" in result.stdout
    assert "next tick: 2026-08-15T16:00:00+00:00" in result.stdout


# ============================================================================
# T002 / US2-S2 — pause pauses the schedule, read back
# ============================================================================


def test_pause_pauses_the_schedule_not_the_run(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S2 and plan trap 2: the schedule owns dispatch, so the schedule is paused.

    The proof is the schedule read back, never the verb's own report — a verb
    that signalled the run would print success while the next tick started a
    fresh run and dispatch continued. Verbatim stdout:

        paused schedule ergane-roadmap: the schedule owns dispatch, so no further run will start
    """
    client = scheduled_floor(fake_temporal)
    assert client.schedules[0].paused is False

    result = invoke("roadmap", "pause", SPECS_ROOT)

    assert result.code == 0, result.stderr
    # Read the schedule back.
    assert client.schedules[0].paused is True
    assert client.schedule_calls == [("pause", SCHEDULE_ID)]
    # The run was not signalled: pausing it would have been the lie.
    assert client.signals == []
    # The human output says the schedule, not merely the run, was paused.
    assert "schedule" in result.stdout
    assert SCHEDULE_ID in result.stdout


# ============================================================================
# T003 / US2-S3 — resume unpauses the schedule, read back
# ============================================================================


def test_resume_unpauses_the_schedule_symmetrically(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S3: the symmetric unpause, read back off the schedule.

    Verbatim stdout:

        resumed schedule ergane-roadmap: the schedule owns dispatch, so the next tick will start a run
    """
    client = scheduled_floor(fake_temporal)
    client.schedules[0].paused = True

    result = invoke("roadmap", "resume", SPECS_ROOT)

    assert result.code == 0, result.stderr
    assert client.schedules[0].paused is False
    assert client.schedule_calls == [("unpause", SCHEDULE_ID)]
    assert client.signals == []
    assert SCHEDULE_ID in result.stdout


def test_pause_then_resume_round_trips_the_schedules_paused_state(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """SC-002's round trip: pause, read back paused; resume, read back running."""
    client = scheduled_floor(fake_temporal)

    assert invoke("roadmap", "pause", SPECS_ROOT).code == 0
    assert client.schedules[0].paused is True
    assert invoke("roadmap", "resume", SPECS_ROOT).code == 0
    assert client.schedules[0].paused is False


# ============================================================================
# T004 / US2-S4 — the bare-workflow floor is byte-identical to today
# ============================================================================


def bare_floor(setup: Callable[..., FakeTemporalClient]) -> FakeTemporalClient:
    """A `roadmap start` workflow and no schedule at all."""
    return setup(workflows={BARE_ID: FakeWorkflow(_status_document(), _at(9))})


def test_bare_workflow_status_output_is_unchanged(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S4: no schedule, so no disposition — the pre-046 rendering, byte for byte.

    085/US3 renamed the first line: it said `roadmap: running` while the block
    below it said `running: …` about the epic list and, on a schedule-driven
    floor, `schedule: … (running)` above it said it about the schedule. It names
    dispatch now, the word `ergane status` already used for that fact (FR-012).
    The assertion stays an equality — that is what this control is worth, and
    weakening it to a containment to absorb the rename would be a regression
    dressed as a fix (085 plan, trap 14).

    Verbatim stdout:

        dispatch: running
        concurrency: 1 epic(s), 1 node(s)
        running: 011-agent-sandbox
        parked: 0
        specs:
          [*] 011-agent-sandbox: ready (landed=False, promoted=False)
    """
    client = bare_floor(fake_temporal)

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 0, result.stderr
    assert result.stdout == (
        "dispatch: running\n"
        "concurrency: 1 epic(s), 1 node(s)\n"
        "running: 011-agent-sandbox\n"
        "parked: 0\n"
        "specs:\n"
        "  [*] 011-agent-sandbox: ready (landed=False, promoted=False)\n"
    )
    assert "schedule" not in result.stdout
    assert client.queried == [(BARE_ID, "roadmap_status")]
    # The bare rung hit, so the ladder never climbed: no schedule was listed.
    assert client.schedule_lists == 0
    assert client.workflow_list_queries == []


def test_bare_workflow_status_json_is_the_query_result_verbatim(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S4: `--json` still prints the query result verbatim, as its help says."""
    bare_floor(fake_temporal)

    result = invoke("roadmap", "status", SPECS_ROOT, "--json")

    assert result.code == 0, result.stderr
    assert result.stdout == json.dumps(asdict(_status_document()), indent=2) + "\n"


def test_bare_workflow_pause_and_resume_signal_the_workflow_silently(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S4: the signals, the silence, and the exit codes are today's."""
    client = bare_floor(fake_temporal)

    pause = invoke("roadmap", "pause", SPECS_ROOT)
    resume = invoke("roadmap", "resume", SPECS_ROOT)

    assert (pause.code, pause.stdout, pause.stderr) == (0, "", "")
    assert (resume.code, resume.stdout, resume.stderr) == (0, "", "")
    assert client.signals == [
        (BARE_ID, "pause_roadmap"),
        (BARE_ID, "resume_roadmap"),
    ]
    assert client.schedule_calls == []


def test_bare_workflow_promote_signals_the_workflow(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S4: `promote` rides the same resolution and is unchanged on a bare floor."""
    client = bare_floor(fake_temporal)

    result = invoke("roadmap", "promote", SPECS_ROOT, "--spec", "011-agent-sandbox")

    assert (result.code, result.stdout, result.stderr) == (0, "", "")
    assert client.signals == [(BARE_ID, "promote_spec")]


# ============================================================================
# T005 / US2-S5 — the refusal names every rung, in the order tried
# ============================================================================


def test_nothing_found_names_the_bare_id_the_schedule_and_the_run_prefix(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S5 / FR-007: an empty floor refuses by naming all three lookups.

    Verbatim stderr:

        ergane: no roadmap 'specs' is running here (looked for workflow id roadmap-specs, then a schedule starting workflows named roadmap-specs*, then runs named roadmap-specs-*)
    """
    client = fake_temporal()

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 1
    assert result.stderr == (
        "ergane: no roadmap 'specs' is running here (looked for workflow id "
        "roadmap-specs, then a schedule starting workflows named "
        "roadmap-specs*, then runs named roadmap-specs-*)\n"
    )
    # In the order tried: the bare id, then the schedule, then the runs.
    order = [
        result.stderr.index("workflow id roadmap-specs"),
        result.stderr.index("a schedule starting"),
        result.stderr.index("runs named"),
    ]
    assert order == sorted(order)
    assert client.described == [BARE_ID]
    assert client.schedule_lists == 1
    assert client.workflow_list_queries == [f'WorkflowId STARTS_WITH "{RUN_PREFIX}"']


def test_a_schedule_that_starts_another_roadmap_is_not_this_roadmap(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """Discovery matches the action's workflow id, so a neighbour's schedule misses."""
    fake_temporal(
        schedules=[FakeSchedule(id="ergane-roadmap", action_workflow_id="roadmap-other")]
    )

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 1
    assert "no roadmap 'specs' is running here" in result.stderr


# ============================================================================
# T006 / SC-004 — the control: the fix changed an outcome
# ============================================================================


def test_control_the_bare_rung_alone_reproduces_the_2026_08_15_refusal(
    fake_temporal: Callable[..., FakeTemporalClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-004: with the discovery seam cut back to its pre-046 rung, the same
    schedule-driven floor that `test_status_reports_the_newest_run_and_names_both`
    reads reproduces the historical refusal — verbatim.

    This is the control the whole story turns on. The floor is identical; only
    the ladder differs. Verbatim stderr with the seam disabled:

        ergane: no roadmap 'specs' is running here (looked for workflow id roadmap-specs)

    which is exactly what the operator saw on 2026-08-15 with a run visible in
    `temporal workflow list`.
    """
    scheduled_floor(fake_temporal)
    monkeypatch.setattr(discovery, "LOOKUPS", (discovery.BARE_WORKFLOW_LOOKUP,))

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 1
    assert result.stderr == (
        "ergane: no roadmap 'specs' is running here "
        "(looked for workflow id roadmap-specs)\n"
    )


# ============================================================================
# Degrading honestly — the spec's Assumptions, plan trap 3
# ============================================================================


def test_status_falls_through_to_the_newest_run_when_schedules_cannot_be_listed(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """A server that does not implement ListSchedules still gets an answer.

    The spec's Assumptions: "If the Temporal server predates schedule listing,
    the verbs degrade per FR-007." Degrading means falling through to the run,
    not aborting — the run is real and the operator can read it — and saying
    which half could not be established. Verbatim stdout:

        schedule: none found (no schedule starts roadmap-specs*)
        run: roadmap-specs-2026-08-15T15:00:00Z
        dispatch: running
        concurrency: 1 epic(s), 1 node(s)
        running: 011-agent-sandbox
        parked: 0
        specs:
          [*] 011-agent-sandbox: ready (landed=False, promoted=False)
    """
    client = scheduled_floor(fake_temporal, schedules_unimplemented=True)

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 0, result.stderr
    assert f"run: {NEWEST_RUN}" in result.stdout
    assert "schedule: none found (no schedule starts roadmap-specs*)" in result.stdout
    assert client.queried == [(NEWEST_RUN, "roadmap_status")]


def test_pause_without_a_discoverable_schedule_says_what_it_could_not_do(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """Signalling a run is all that is left when no schedule can be found — and the
    operator is told, because a tick may start a fresh run (plan trap 2).

    Verbatim stderr:

        ergane: warning: no owning schedule was found for roadmap-specs, so only run roadmap-specs-2026-08-15T15:00:00Z was paused; a schedule tick would start a fresh run
    """
    client = scheduled_floor(fake_temporal, schedules_unimplemented=True)

    result = invoke("roadmap", "pause", SPECS_ROOT)

    assert result.code == 0
    assert client.signals == [(NEWEST_RUN, "pause_roadmap")]
    assert client.schedule_calls == []
    assert "no owning schedule was found" in result.stderr


def test_a_schedule_that_has_not_ticked_yet_still_reports_its_disposition(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """A schedule owns dispatch before its first tick; there is simply no run to query.

    Created just now, so it is inside its first cadence intervals and running
    rather than starved: `_find_owning_schedule` promises a never-ticked
    schedule is reported, and a `ergane init` that answered `starved` thirty
    seconds after creating a schedule would look broken to every new user (085,
    trap 10). Its creation time is therefore the wall clock's, not this module's
    fixed default — the same reason `_just_ticked` exists.

    Verbatim stdout:

        schedule: ergane-roadmap (running)
        next tick: 2026-08-15T16:00:00+00:00
        no run has started yet
    """
    fake_temporal(
        schedules=[
            FakeSchedule(
                id=SCHEDULE_ID,
                action_workflow_id=BARE_ID,
                next_action_times=[_at(16)],
                created_at=datetime.now(timezone.utc),
            )
        ]
    )

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code == 0, result.stderr
    assert result.stdout == (
        f"schedule: {SCHEDULE_ID} (running)\n"
        "next tick: 2026-08-15T16:00:00+00:00\n"
        "no run has started yet\n"
    )
