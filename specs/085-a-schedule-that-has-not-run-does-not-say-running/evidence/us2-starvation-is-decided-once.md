# 085-US2 evidence — SC-004, SC-005

Every block below is pasted verbatim from a run in this worktree on 2026-08-22.
The tables come from a driver over the helpers committed in
`tests/test_a_starved_schedule_is_not_running.py` — `NOW`, `CADENCE_S`,
`GRACE_S`, `_location` and `_started` — so what produced the evidence is the same
fixture code the tests run on, and the same constant the source uses:

```python
from tests.test_a_starved_schedule_is_not_running import NOW, CADENCE_S, GRACE_S, _location, _started
from factory.roadmap.discovery import STARVED_AFTER_INTERVALS

loc = _location(last_action_started_at=_started(timedelta(hours=6)), skipped_overlap_count=76)
print(loc.schedule_state_at(NOW), loc.seconds_since_last_start(NOW))
```

`_location` builds a schedule-owned `RoadmapLocation` by hand and dials one field
at a time. There is no client anywhere in this story's tests: US1 proved the read
that fills these fields, and the verdict may reach for nothing but the fields
themselves.

## The suite this story added

```
tests/test_a_starved_schedule_is_not_running.py .............................. [100%]
30 passed in 0.06s
```

Full declared gate (`uv run pytest -q`, this worktree, all of it):

```
4400 passed, 52 skipped, 6 warnings in 336.85s (0:05:36)
```

## SC-004 — the verdict table

One line per case. `paused`, `cad_s`, `last actual start`, `created` and
`skipped` are the inputs; `verdict` is what `schedule_state_at(NOW)` answered.
Elapsed times are in seconds so the two boundary rows can be told apart —
`600s` and `601s` against a `600s` grace window.

```
now = 2026-08-22T15:00:00+00:00;  STARVED_AFTER_INTERVALS = 2;  cadence_s = 300  ->  grace = 600s (10m)

== SC-004: the verdict table ==
  case                        verdict  paused cad_s last actual start  created    skipped
  last start 6h ago           starved  False 300   21600s             43200s     76
  last start 1m ago           running  False 300   60s                43200s     0
  exactly two intervals       running  False 300   600s               43200s     0
  one second past two         starved  False 300   601s               43200s     0
  paused, last tick 90d ago   paused   True  300   7776000s           43200s     0
  paused, nothing else read   paused   True  None  -                  -          0
  never ticked, 1m old        running  False 300   -                  60s        0
  never ticked, 12h old       starved  False 300   -                  43200s     0
  no cadence read             unknown  False None  60s                43200s     0
  zero cadence                unknown  False 0     60s                43200s     0
  no history at all           unknown  False 300   -                  -          0
  unparseable last start      unknown  False 300   unreadable         43200s     0
  paused flag unreadable      unknown  None  300   60s                43200s     0
```

Read down the `verdict` column and the four answers are all there, each with the
input that produced it.

**starved** — row 1 is the reported outage, to the number: a five-minute cadence,
76 skipped ticks and a last actual start six hours old. Before this story every
field on that row except `paused` was thrown away at the describe call, and
`paused=False` was the whole of the reasoning behind `schedule: ergane-roadmap
(running)`.

**The threshold, from both sides.** `600s` is running and `601s` is starved, so
the boundary is asserted rather than assumed, and it is spelled from
`STARVED_AFTER_INTERVALS * CADENCE_S` in both the test and this driver — a
threshold moved in the source moves these rows with it instead of leaving them
pinned to a number the code no longer uses. Two intervals rather than one because
one grace tick absorbs ordinary clock and dispatch jitter; at one interval a tick
landing a second late reads as an outage.

**paused wins over everything.** Row 5 is 90 days without a tick and it is not
starved: the operator turned dispatch off, and that is their decision, not a
fault. Row 6 is the same flag with nothing else readable — no cadence, no
history, no creation time — and it still answers `paused`, because the flag is a
fact that *was* read. Degrading it to `unknown` would hide the one state the
operator caused themselves.

**Never ticked is a window, not a verdict.** Rows 7 and 8 are the same schedule
with no recorded actions at all, measured against `created_at`: one minute old is
`running`, twelve hours old is `starved`. A false `starved` on the first of those
makes `ergane init` look broken to every new user thirty seconds in, which is why
`_find_owning_schedule` already promises a never-ticked schedule is reported
rather than hidden. `tests/test_roadmap_first_tick_on_fresh_init.py` reads as
though it guards this window and does not — it drives the *workflow's* first tick
against a freshly-initialised tree and imports neither
`factory.roadmap.discovery` nor a renderer — so rows 7 and 8 are new coverage,
not preserved coverage.

**Five ways not to know, and none of them guesses.** The last five rows are
`unknown`: no cadence (an overdue tick has no scale), a zero cadence (which is
not a schedule that ticks constantly), no history and no creation time (nothing
to measure against), a start time this reader cannot parse, and a paused flag
that could not be read. None answers `running` and none answers `starved`.
Printing a guess as a verdict is the whole of the reported defect, and 052's
principle is the other half: the reading degrades, the rest of the report still
renders, and nothing raises inside a status render.

## SC-005 — the false-alarm control

The scenario that decides this story. A large lifetime skipped-overlap count with
a one-minute-old actual start is `running`.

```
== SC-005: the false-alarm control ==
  case                        verdict  paused cad_s last actual start  created    skipped
  skipped=0, start 1m ago     running  False 300   60s                43200s     0
  skipped=1, start 1m ago     running  False 300   60s                43200s     1
  skipped=76, start 1m ago    running  False 300   60s                43200s     76
  skipped=100000, start 1m ago running  False 300   60s                43200s     100000
  skipped=0, start 6h ago     starved  False 300   21600s             43200s     0
  skipped=76, start 6h ago    starved  False 300   21600s             43200s     76
```

Six rows, one dial. The count runs from zero to a hundred thousand across four
identical schedules and the verdict does not move; the last start moves once and
the verdict moves with it. That is the whole claim: **the count is evidence, the
elapsed time is the trigger.**

`num_actions_skipped_overlap` is a lifetime counter — it never decreases. A
schedule that skipped two ticks last Tuesday reports non-zero for the rest of its
life, so `count > 0 → unhealthy` is a warning that is permanently on. A permanent
warning is read once and ignored, and the operator is back in front of a floor
report that tells them nothing: the same six hours, in a new costume. The bottom
two rows are the mirror of that — a `skipped=0` schedule six hours dead is still
`starved`, which is what a schedule whose runs fail outright rather than overlap
looks like, and a counter-driven verdict calls it healthy.

### The counter-driven verdict, failing

`count > 0 → starved` is the wrong answer that passes the obvious tests. This is
that mutation — two lines added ahead of the elapsed-time read in
`factory/roadmap/discovery.py`, nothing else touched:

```python
        if self.skipped_overlap_count:
            return RoadmapScheduleState.STARVED
```

```
>       assert location.schedule_state_at(NOW) is RoadmapScheduleState.RUNNING
E       AssertionError: assert <RoadmapScheduleState.STARVED: 'starved'> is <RoadmapScheduleState.RUNNING: 'running'>
E        +  where <RoadmapScheduleState.STARVED: 'starved'> = schedule_state_at(datetime.datetime(2026, 8, 22, 15, 0, tzinfo=datetime.timezone.utc))
E        +    where schedule_state_at = RoadmapLocation(root_name='specs', ... skipped_overlap_count=76,
        last_action_started_at='2026-08-22T14:59:00+00:00', schedule_created_at='2026-08-22T03:00:00+00:00',
        cadence_s=300).schedule_state_at

FAILED tests/test_a_starved_schedule_is_not_running.py::test_a_large_lifetime_skipped_count_with_a_recent_start_is_running
FAILED tests/test_a_starved_schedule_is_not_running.py::test_the_verdict_ignores_the_skipped_count_in_both_directions[1]
FAILED tests/test_a_starved_schedule_is_not_running.py::test_the_verdict_ignores_the_skipped_count_in_both_directions[76]
FAILED tests/test_a_starved_schedule_is_not_running.py::test_the_verdict_ignores_the_skipped_count_in_both_directions[100000]
4 failed, 26 passed in 0.09s
```

Twenty-six of the thirty tests still pass under it — including the starved case
and the running case, which is exactly why this control has to exist as its own
scenario. The `[0]` parametrisation passes too, and that is the tell: a
counter-driven verdict is only correct on schedules that have never skipped. The
mutation was reverted before the commit; `git status --porcelain` is empty in the
tree this diff was taken from.

## FR-005, FR-006 — the shape of the answer

The four words are asserted as a set, so a fifth answer or a renamed one fails
here rather than at a renderer:

```python
assert {state.value for state in RoadmapScheduleState} == {"paused", "running", "starved", "unknown"}
assert RoadmapScheduleState.STARVED.value == "starved"
assert f"{RoadmapScheduleState.STARVED}" == "starved"
```

`starved`, and not the three neighbours. `stalled` belongs to
`factory/mergequeue/models.py`, the outcome a merge attempt reaches past its
stall window. `parked` belongs to `factory/cli/roadmap.py`, printed two lines
below the schedule line for parked epics. `blocked` belongs to `CONTEXT.md`, an
agent's question. Only the last of the three is in `CONTEXT.md`, so a fruitless
grep there is not permission to reuse the other two.

`STARVED_AFTER_INTERVALS = 2` is a module constant with its own committed
assertion, not a literal inside a conditional: the threshold is chosen rather
than measured, and it is named so the next operator can move it against evidence.

## FR-005 — no I/O, and no client to bind

The verdict reads the location's own fields and the clock, and nothing else. That
is hard to assert by inspection, so it is made mechanical: `socket.socket` is
replaced with a function that fails the test, and the verdict is computed under
it.

```python
def _refuse(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("the verdict opened a socket: it must read only the location")

monkeypatch.setattr(socket, "socket", _refuse)
```

`schedule_state_at(now)` takes the clock as a parameter so a test can supply one
— every row of both tables above is decided against `2026-08-22T15:00:00+00:00`,
so no verdict here depends on when the suite runs. `schedule_state` supplies
`datetime.now(timezone.utc)`, and that is what a renderer reads.
