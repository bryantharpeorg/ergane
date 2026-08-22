# 085-US1 evidence — SC-001, SC-002, SC-003, SC-009

Every block below is pasted verbatim from a run in this worktree on 2026-08-22.
The location pastes come from a driver over the helpers committed in
`tests/test_schedule_ticks_survive_the_read.py` — `_schedule`, `_resolve`,
`_DescribesLikeAnOlderServer` and `DESCRIBE_FAKES` — so what produced the
evidence is the same fixture code the tests run on:

```python
from tests.test_schedule_ticks_survive_the_read import (
    DESCRIBE_FAKES, FakeTemporalClient, _DescribesLikeAnOlderServer, _resolve, _schedule,
)
loc = await _resolve(FakeTemporalClient(schedules=[_schedule(skipped_overlap=7, ...)]))
```

## The suite this story added

```
tests/test_schedule_ticks_survive_the_read.py ............. [100%]
13 passed, 1 warning in 0.20s
```

Full declared gate (`uv run pytest -q`, this worktree, all of it):

```
4370 passed, 52 skipped, 6 warnings in 338.40s (0:05:38)
```

Run four times on this branch, green four times. A fifth run — between the
fixture commit and this one — reported `1 failed, 4369 passed`, and the failing
test's name was lost to a `tail -3` on that invocation. It did not recur, and it
is not in this diff's blast radius: the four modules this story edits were then
run three times in a row clean (`96 passed`), and the suite's known intermittent
surface is the 38 modules that drive a real time-skipping Temporal server, none
of which reads the fields added here. Recorded rather than dropped, because a
run that failed once is a fact.

## SC-001 — the SDK probe

The facts this story carries are already on the object the factory describes.
Nothing here is research; it is a read of the installed package.

```
$ python -c "import importlib.metadata as md; print(md.version('temporalio'))"
1.31.0

$ ... dataclasses.fields(c.ScheduleInfo) ...
num_actions : int
num_actions_missed_catchup_window : int
num_actions_skipped_overlap : int
running_actions : Sequence[ScheduleActionExecution]
recent_actions : Sequence[ScheduleActionResult]
next_action_times : Sequence[datetime]
created_at : datetime
last_updated_at : datetime | None

$ ... dataclasses.fields(c.ScheduleActionResult) ...
scheduled_at : datetime
started_at : datetime
action : ScheduleActionExecution
```

`next_action_times` is the one field `_find_owning_schedule` read. Three of the
other seven are what this story adds.

**The two load-bearing docstring lines.** The first decides which end of a list
to take; the second decides whether the list means what the verdict needs.

```
$ ... inspect.getsource(c.ScheduleInfo) ... (the recent_actions field)
    recent_actions: Sequence[ScheduleActionResult]
    """10 most recent actions, oldest first."""

$ ... inspect.getsource(c.ScheduleActionResult) ...
    scheduled_at: datetime
    """Scheduled time of the action including jitter."""

    started_at: datetime
    """When the action actually started."""

    action: ScheduleActionExecution
    """Action that took place."""

    @staticmethod
    def _from_proto(
        res: temporalio.api.schedule.v1.ScheduleActionResult,
    ) -> ScheduleActionResult:
        return ScheduleActionResult(
            scheduled_at=res.schedule_time.ToDatetime().replace(tzinfo=timezone.utc),
            started_at=res.actual_time.ToDatetime().replace(tzinfo=timezone.utc),
            action=ScheduleActionExecutionStartWorkflow._from_proto(
                res.start_workflow_result
            ),
        )

$ ... dataclasses.fields(c.ScheduleActionExecutionStartWorkflow) ...
['workflow_id', 'first_execution_run_id']
```

Two things settle out of that source. **"oldest first"**, so the newest actual
start is `recent_actions[-1]` — the opposite end from the `next_action_times[0]`
read one line away in the same function, which takes `[0]` because future times
ascend. And every entry is built from `res.start_workflow_result` and carries a
`first_execution_run_id`: a *skipped* tick starts no workflow and has nothing to
put there, so it leaves no entry, and `started_at` — from `res.actual_time`,
documented *"When the action actually started."* — is a true last-actually-ran
rather than a last-tick-was-due.

### The ordering control, failing at the wrong end

With `recent[-1]` changed to `recent[0]` in `factory/roadmap/discovery.py` and
nothing else touched. The seeded starts are three hours apart, oldest first:

```
E       AssertionError: assert '2026-08-22T09:00:00+00:00' == '2026-08-22T11:00:00+00:00'
E         - 2026-08-22T11:00:00+00:00
E         + 2026-08-22T09:00:00+00:00
1 failed, 12 deselected in 0.64s
```

Two hours stale on a three-entry list; on a full ten-entry one it is ten
cadences, which is what would manufacture starvation on a healthy schedule. The
mutation was reverted before the commit — `git status --porcelain` is empty in
the tree this diff was taken from.

## SC-002 — the facts survive the read

```
== SC-002: a described schedule carrying a skipped count and a history ==
  info.num_actions_skipped_overlap = 7
  info.recent_actions started_at   = ['2026-08-22T09:00:00+00:00', '2026-08-22T10:00:00+00:00', '2026-08-22T11:00:00+00:00']
                                     (oldest first, as the SDK orders them)
  the resolved location:
  owner = <RoadmapOwner.SCHEDULE: 'schedule'>
  schedule_id = 'ergane-roadmap'
  schedule_paused = False
  next_action_at = '2026-08-22T15:05:00+00:00'
  skipped_overlap_count = 7
  last_action_started_at = '2026-08-22T11:00:00+00:00'
  schedule_created_at = '2026-08-22T03:00:00+00:00'
  cadence_s = 300
```

Seven skipped ticks and a last actual start, on a location whose
`schedule_paused` is `False` — which is the whole of the reported outage: the
only fact a renderer had was the flag on the third line, and the flag says
nothing is wrong. `last_action_started_at` is the newest of the three seeded
starts, not the oldest. `cadence_s = 300` is the scale that makes
"`11:00`, and it is now `15:00`" mean something.

## SC-003 — the degrade control

Three descriptions this ladder cannot fully read. `pre-085` is what every fake
in this tree returned before this story and what a server older than the fields
returns today: an `info` carrying only `next_action_times`, and a schedule with
no `spec`. `no-info` has no `info` attribute at all.

```
== SC-003: the degrade control ==
  description shape: pre-085
  found = True
  owner = <RoadmapOwner.SCHEDULE: 'schedule'>
  schedule_id = 'ergane-roadmap'
  schedule_paused = True
  next_action_at = '2026-08-22T15:05:00+00:00'
  skipped_overlap_count = None
  last_action_started_at = None
  schedule_created_at = None
  cadence_s = None
  description shape: no-info
  found = True
  owner = <RoadmapOwner.SCHEDULE: 'schedule'>
  schedule_id = 'ergane-roadmap'
  schedule_paused = True
  next_action_at = None
  skipped_overlap_count = None
  last_action_started_at = None
  schedule_created_at = None
  cadence_s = None
  description shape: nothing found at all (the empty answer)
  found = False
  owner = <RoadmapOwner.NONE: 'none'>
  skipped_overlap_count = None
  last_action_started_at = None
  schedule_created_at = None
  cadence_s = None
```

No exception on any of the three. The schedule is still `found`, still named,
still reports its paused flag, and the new facts are `None` — "not known",
never a zero that would read as "never skipped a tick" and never a cadence of
zero that would read as "ticks constantly". `next_action_at` is intact where
`info` is readable and absent where it is not, which is exactly what it did
before this story.

The third block is the path a new user's very first `ergane status` takes:
`resolve_roadmap` builds a `RoadmapLocation` at two sites, and a field passed at
one of them only is a `TypeError` on the emptiest floor there is.

## SC-009 — the fake-parity table

One row per `describe()` fake in this tree, naming the cadence the discovery
ladder read *through that fake*. No row reads `unknown`.

```
== SC-009: the fake-parity table ==
  describe() fake                                cadence_s   owner
  tests/fake_schedules.py                              300   schedule
  tests/test_roadmap_schedule_discovery.py             300   schedule
  tests/test_roadmap_wedge_visibility.py               300   schedule
  tests/test_ergane_status.py                          300   schedule
```

Four fakes, and each had **two** holes in two different objects. The `info` half
— the skipped count, the action history, `created_at` — was missing from all
four. The `Schedule` half, where the cadence lives, was missing from three:
their `schedule=SimpleNamespace(...)` carried `action` and `state` and no `spec`
attribute at all. `tests/fake_schedules.py` needed no `spec`: its `_stored()`
hands back the real `Schedule` the factory itself built, intervals included.

**Why the second half is the one that decides this story.** An unreadable
cadence resolves to `unknown` under FR-008, and `unknown` is a state the reader
is *designed* to tolerate. A fake extended on the `info` half alone therefore
does not fail — it goes green having exercised nothing. This is that state,
produced by removing only the `spec=ScheduleSpec(...)` block from the three
fakes and changing nothing else:

```
E  AssertionError: tests/test_roadmap_schedule_discovery.py resolves cadence_s=None: an
   unreadable cadence is `unknown`, and `unknown` makes every verdict scenario downstream
   pass without exercising a verdict
E  assert (False)
E   +  where False = isinstance(None, int)
E   +    where None = RoadmapLocation(root_name='specs', ... skipped_overlap_count=0,
        last_action_started_at=None, schedule_created_at='2026-08-22T03:00:00+00:00',
        cadence_s=None).cadence_s
E  AssertionError: tests/test_roadmap_wedge_visibility.py resolves cadence_s=None: ...
E  AssertionError: tests/test_ergane_status.py resolves cadence_s=None: ...
3 failed, 1 passed, 9 deselected, 1 warning in 0.22s
```

Three failures and one pass — `tests/fake_schedules.py`, the one that needs no
`spec` — which is the table above, inverted. Read the repr on the fourth line:
`skipped_overlap_count=0` and a real `schedule_created_at` say the `info` half
*was* extended in that state. That is the half-answered diff, and without this
control it ships green. The removal was reverted before the commit.

The table is kept honest by a census rather than by hand: a schedule
`describe()` fake is exactly a module under `tests/` that mentions
`next_action_times`, and
`test_the_parity_table_names_every_describe_fake_in_the_tree` asserts that set
equals the four rows above. A fifth fake fails there instead of slipping past
unmeasured.

## FR-004 — nothing here entered the declared set

`_DECLARED` (`factory/roadmap/schedule.py`) is asserted byte for byte against
its eight names, and the three observed facts are asserted disjoint from it.
`cadence_s` is absent from that disjointness check on purpose: a manifest really
does declare a cadence, and it was in `_DECLARED` before this story. What may
not enter it is a fact about what a schedule has *done* — the module's own
comment says `paused` is deliberately absent for exactly that reason, and an
observed fact in the declared set makes `apply_schedule` report a permanent
disagreement against something no manifest can state.
