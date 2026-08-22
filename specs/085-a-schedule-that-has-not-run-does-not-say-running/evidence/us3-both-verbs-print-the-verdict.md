# US3 evidence — both verbs print the verdict, and stop colliding

SC-006, SC-007 and SC-008, as pasted output rather than description (Principle
VIII). Every block below is stdout from the renderers this story changed, on the
tree this story commits, captured 2026-08-22.

## How these were produced

One script, run twice: once with the working tree stashed (the tree at
`33d3092`, US2 merged and US3 unwritten) for the **before** columns, and once
with this story's diff applied for the **after** columns. Same script, same
seeded location, only the code differing — which is the only way a
"byte-for-byte unchanged" claim means anything.

```python
# /tmp/us3_evidence.py -- run as `uv run python /tmp/us3_evidence.py`
NOW = datetime.now(timezone.utc)
ago = lambda **d: (NOW - timedelta(**d)).isoformat()

def location(**dials):
    fields = dict(
        root_name="specs", bare_workflow_id="roadmap-specs",
        run_prefix="roadmap-specs-", owner=RoadmapOwner.SCHEDULE,
        workflow_id="roadmap-specs-2026-08-22T15:00:00Z",
        schedule_id="ergane-roadmap", schedule_paused=False,
        next_action_at="2026-08-22T16:00:00+00:00",
        looked_for=("workflow id roadmap-specs",),
        skipped_overlap_count=0, last_action_started_at=ago(minutes=1),
        schedule_created_at=ago(hours=12), cadence_s=300)
    fields.update(dials)
    return RoadmapLocation(**fields)

def status_block(loc):                      # `ergane status`, roadmap section
    async def resolved(_c, _r): return loc
    status_cli.resolve_roadmap = resolved
    d = asyncio.run(status_cli._disposition(Stub(), Path("specs")))
    return "\n".join(status_cli._roadmap_lines(SimpleNamespace(roadmap=d)))

def roadmap_block(loc):                     # `ergane roadmap status`
    return roadmap_cli._render_disposition(loc) + roadmap_cli._render_status(doc)

STARVED = location(last_action_started_at=ago(hours=6, minutes=12),
                   skipped_overlap_count=74)
```

The location is handed in whole and the ladder is stubbed, for the reason the
test module gives: US1 owns the read that builds a location off a described
schedule and proves it against four fakes. What runs here is the real
`_disposition`, the real `_roadmap_lines`, the real `_render_disposition` and the
real `_render_status` — the four functions this story changed.

`STARVED` is a five-minute schedule whose last *actual* start was 6h 12m ago,
with 74 lifetime skipped-overlap ticks. That is the 2026-08-15 floor: under the
`SKIP` overlap policy every tick fires, every tick is skipped, nothing fails.

---

## SC-006 — one starved location, both verbs, the same verdict word

**After** (this tree). The two `schedule:` lines are character-for-character
identical, evidence clause included:

```
--- STARVED / ergane status  (roadmap block) ---------------
schedule: ergane-roadmap (starved: 6h 12m since a tick last started, 74 ticks skipped)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
running: 011-agent-sandbox
parked: 0
--- STARVED / ergane roadmap status ------------------------
schedule: ergane-roadmap (starved: 6h 12m since a tick last started, 74 ticks skipped)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
concurrency: 1 epic(s), 1 node(s)
running: 011-agent-sandbox
parked: 0
specs:
  [*] 011-agent-sandbox: ready (landed=False, promoted=False)
```

**Before** (`33d3092`), the same location, the same script — the reported defect,
reproduced:

```
--- STARVED / ergane status  (roadmap block) ---------------
schedule: ergane-roadmap (running)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
running: 011-agent-sandbox
parked: 0
--- STARVED / ergane roadmap status ------------------------
schedule: ergane-roadmap (running)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
roadmap: running
concurrency: 1 epic(s), 1 node(s)
running: 011-agent-sandbox
parked: 0
specs:
  [*] 011-agent-sandbox: ready (landed=False, promoted=False)
```

`schedule: ergane-roadmap (running)` above a near-future `next tick`, above
`roadmap: running`, above `running: 011-agent-sandbox` — three `running`s about
three unrelated things, on a floor that had not started a run in six hours. That
is the screen the reporter read for six hours.

The `next tick:` line is untouched in both verbs and both trees. It was never
false: during starvation the schedule really does tick, it just skips.

---

## SC-007 — the healthy control, byte for byte

`ergane status`, healthy location, **before and after are identical** — the same
six lines, diffed below:

```
--- HEALTHY / ergane status  (roadmap block) ---------------
schedule: ergane-roadmap (running)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
running: 011-agent-sandbox
parked: 0
```

`ergane roadmap status`, healthy location. **After:**

```
schedule: ergane-roadmap (running)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
concurrency: 1 epic(s), 1 node(s)
running: 011-agent-sandbox
parked: 0
specs:
  [*] 011-agent-sandbox: ready (landed=False, promoted=False)
```

**Before:**

```
schedule: ergane-roadmap (running)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
roadmap: running
concurrency: 1 epic(s), 1 node(s)
running: 011-agent-sandbox
parked: 0
specs:
  [*] 011-agent-sandbox: ready (landed=False, promoted=False)
```

One line differs across the whole healthy rendering of both verbs, and it is the
line FR-012 renames. The `schedule:` line, the `run:` line and the `next tick:`
line are unchanged in both verbs — which is FR-011, and which is what protects
the operator's own muscle memory.

The committed controls behind this: `tests/test_both_verbs_agree_about_the_schedule.py`
asserts the six-line `ergane status` block and the three-line
`ergane roadmap status` disposition as list and string equality, and
`tests/test_roadmap_schedule_discovery.py::test_a_schedule_that_has_not_ticked_yet_still_reports_its_disposition`
still asserts `schedule: ergane-roadmap (running)\n…` on a full end-to-end
`ergane roadmap status` run, with its expected string untouched by this diff.

---

## SC-008 — the dispatch line under its new name, beside the schedule line

`ergane roadmap status` on the starved floor, whole, with the two lines marked:

```
schedule: ergane-roadmap (starved: 6h 12m since a tick last started, 74 ticks skipped)   <-- the schedule
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running                                                                        <-- dispatch
concurrency: 1 epic(s), 1 node(s)
running: 011-agent-sandbox
parked: 0
specs:
  [*] 011-agent-sandbox: ready (landed=False, promoted=False)
```

Both facts are true at once, and that is the point: the roadmap workflow is not
paused (`dispatch: running`), and no tick has started a run in six hours
(`starved`). Under the old wording those two lines both said `running`, so the
one that was reporting the outage was indistinguishable from the one that was
not.

`dispatch:` is the word `factory/cli/status.py` already used for this fact, and
it now sits above `running:` and `parked:` in both verbs — the layout
`ergane status` already had.

---

## The four states, both verbs, as the renderers answer them

The full matrix the committed parametrised control asserts. `unknown` is the row
that matters most after `starved`: a description this tree cannot fully read —
here, a calendar-only schedule with no readable interval — is said rather than
guessed.

| state | `ergane status` | `ergane roadmap status` |
| --- | --- | --- |
| running | `schedule: ergane-roadmap (running)` | `schedule: ergane-roadmap (running)` |
| paused | `schedule: ergane-roadmap (paused)` | `schedule: ergane-roadmap (paused)` |
| starved | `schedule: ergane-roadmap (starved: 6h 12m since a tick last started, 74 ticks skipped)` | `schedule: ergane-roadmap (starved: 6h 12m since a tick last started, 74 ticks skipped)` |
| unknown | `schedule: ergane-roadmap (unknown)` | `schedule: ergane-roadmap (unknown)` |

Pasted rendering of the `unknown` row, showing that every other line of the
report still renders (US3-S4, 052's principle):

```
--- UNKNOWN / ergane status  (roadmap block) ---------------
schedule: ergane-roadmap (unknown)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
running: 011-agent-sandbox
parked: 0
--- UNKNOWN / ergane roadmap status ------------------------
schedule: ergane-roadmap (unknown)
run: roadmap-specs-2026-08-22T15:00:00Z
next tick: 2026-08-22T16:00:00+00:00
dispatch: running
concurrency: 1 epic(s), 1 node(s)
running: 011-agent-sandbox
parked: 0
specs:
  [*] 011-agent-sandbox: ready (landed=False, promoted=False)
```

Before this story, that same unreadable description printed `(running)` in both
verbs — the guess this spec exists to stop.

---

## The gate

`uv run pytest -q` on this tree:

```
$ uv run pytest -q tests/test_both_verbs_agree_about_the_schedule.py
......................                                                   [100%]
22 passed in 0.10s
```

Full suite, this tree, recorded in the final commit.

## What the gate cannot catch, and the operator should run

Two verdicts agreeing in tests and disagreeing in production is what trap 2
exists for, and no fixture can rule it out. On the live floor:

- `ergane status` and `ergane roadmap status` back to back, and diff the
  `schedule:` line. It should be the same characters, not merely the same word.
- `ergane init` on a scratch repo, read the schedule line inside the first
  cadence. `running`, not `starved` — a false `starved` on a thirty-second-old
  schedule makes every new install look broken.
- Wedge a roadmap run the way the reporter did and watch the line change from
  `running` to `starved` as the second cadence interval passes.
