---
state: draft
fixes:
  - roadmap/a-wedged-run-silently-eats-every-subsequent-tick-under-skip-overlap
# FLIP APPROVED, STAGED. 2026-08-22 the operator ruled (Q&A after the review
# docket): this spec flips to ready — its hold condition, "the floor is back on
# its own scheduler", was observed met (schedule-owned, unpaused, ticking
# unattended since 2026-08-21 night) — but the flip is DELIBERATELY STAGED
# until 083's US3 has landed, so the factory/cli/roadmap.py collision window
# never opens. Whoever holds this file next: flip to ready once
# `ergane spec landed specs/083-* --default-branch ergane-buildout` shows US3.
#
# RE-ANCHORED 2026-08-22 against 732ff88. Every citation re-printed (~230
# anchors, the densest of the trio):
#   - ZERO broken constructs. discovery.py, schedule.py, cli/status.py,
#     doctor/probes.py, and ALL FIVE cited test files are byte-identical to
#     the draft-time tree. The four-fakes inventory RE-CONFIRMED: exactly
#     four describe() fakes exist today, the same three still build
#     schedule=SimpleNamespace with no `spec` attribute, and no fifth has
#     appeared. US1-S7 / FR-002 / SC-009 stand exactly as written.
#   - factory/cli/roadmap.py drifted wholesale when 081 landed (+11/+32):
#     US3's two target lines are now :464 (_render_disposition at :456) and
#     :480 (_render_status at :478); _connect :200, Client.connect :204
#     (still the file's only occurrence), pause command :342. All updated —
#     and note: the exact silent-shift hazard this spec's own trap section
#     warned about has now happened once, caused by 081. The four re-derive
#     rules were right.
#   - The 065 guard's caller moved +5 (:887-900). And the frontmatter's own
#     "correction to the finding" about workflow.py:849 had itself gone
#     stale — :849 now holds a comprehension clause, the capacity comment is
#     at :854. Corrected below; the ruling (065 landed, do not rebuild) is
#     unaffected.
#
# A CROSS-SPEC CRITIC PASS WAS APPLIED 2026-08-21 ~6:50 PM CT, reading 083, 084
# and 085 as one batch against the same tree at `dcc854d`. **The state stays
# `draft`** — the pass fixed defects, it did not clear the hold below. Four
# material rulings came out of it, all four verified line by line:
#
#   1. THE CADENCE HAD NO SOURCE IN THREE OF THE FOUR TEST FAKES, and neither
#      the plan nor the tasks said to add one. FR-002 reads the cadence from
#      `described.schedule.spec.intervals`, and three of this tree's four
#      `describe()` fakes build `schedule=SimpleNamespace(action=..., state=...)`
#      with **no `spec` attribute at all**:
#      `tests/test_roadmap_schedule_discovery.py:146-155`,
#      `tests/test_roadmap_wedge_visibility.py:89-96` and
#      `tests/test_ergane_status.py:347-354`. Only `tests/fake_schedules.py:63`
#      returns a real `Schedule` (via `_stored()` at `:51`) and so carries one.
#      FR-008 turns an unreadable cadence into `unknown`, so under the old text
#      every verdict scenario in US2 and every starved rendering in US3 would
#      have been unreachable **and the suite would have gone green proving
#      nothing**. Trap 6 and T009 now name `schedule.spec.intervals` and both
#      halves of the split; US1-S7, T009a and SC-009 are the control that fails
#      when a fake yields `unknown` where a scenario intends a real verdict.
#
#   2. `recent_actions` IS OLDEST-FIRST, AND THE NEWEST IS `[-1]`. Read out of
#      the installed SDK source on this host (temporalio 1.31.0), not
#      remembered: `ScheduleInfo.recent_actions` is documented *"10 most recent
#      actions, oldest first."* The neighbouring read this spec widens takes
#      `next_times[0]` (`factory/roadmap/discovery.py:174`) because future times
#      ascend — copying that idiom one field over yields a start up to ten
#      cadences stale, which manufactures `starved` on a healthy schedule. New
#      US1-S6, trap 15, T001a.
#
#   3. THE ONE ASSUMPTION THAT COULD HAVE CHANGED THE DESIGN IS NOW SETTLED, by
#      type rather than by observation. `ScheduleActionResult.action` is built
#      from `res.start_workflow_result` as a
#      `ScheduleActionExecutionStartWorkflow`, whose only two fields are
#      `workflow_id` and `first_execution_run_id`. A skipped tick starts no
#      workflow and has no run id, so the type cannot represent one — the
#      question is closed. `started_at` comes from `res.actual_time`, documented
#      *"When the action actually started."* Trap 16 carries the probe and the
#      fallback branch in case a live server ever disagrees.
#
#   4. 083 IS PULLED TOWARD THE SAME FILE AS THIS SPEC'S US3, and neither spec
#      said so. 083 has since ruled itself out of `factory/cli/roadmap.py`
#      (its FR-017 makes it a MUST NOT), so the expected collision is none and
#      the declared hazard is an 083 attempt breaking that rule.
#      See *The other spec that reaches for this file*, below, and trap 17.
#
# HELD AT DRAFT deliberately, 2026-08-21 ~5:30 PM CT, by an operator session.
# The roadmap schedule is the thing this spec instruments, and it is currently
# being steered by hand through `temporal schedule toggle` because `ergane
# roadmap resume/pause` is itself broken by a stale bare workflow. Landing a
# change to how the schedule is *read* while the operator drives it by hand is
# how a fix and a symptom get confused. Ready it once the floor is back on its
# own scheduler.
#
# WHAT THIS IS. On 2026-08-19 a consumer agent operated a build session, hit an
# epic death four times, terminated four workflows by hand, and spent six hours
# in front of an `ergane status` reading `schedule: ergane-roadmap (running)`
# with a near-future `next tick`. Dispatch was dead the whole time. The schedule
# had recorded 76 SKIPPED OVERLAPS — an unambiguous, already-stored,
# already-queryable fact meaning "this schedule has not actually run in six
# hours" — and nothing in this repository reads it.
#
# THE MEASUREMENT, every line printed individually on 2026-08-21 against
# `dcc854d` (byte-identical to `origin/ergane-buildout`):
#   `factory/cli/status.py:729`
#       state = "paused" if disposition.schedule_paused else "running"
#   `factory/cli/roadmap.py:464` — the same sentence, in a second file:
#       state = "paused" if location.schedule_paused else "running"
#   `running` is *defined* as `not paused`. No reading of the schedule's health
#   enters either line, so both actively assert health while dispatch is dead.
#   `factory/roadmap/discovery.py:166-168` is where the fact is thrown away:
#       state = getattr(getattr(described, "schedule", None), "state", None)
#       info = getattr(described, "info", None)
#       next_times = list(getattr(info, "next_action_times", None) or [])
#   `info` is bound, one field is read off it, and the rest is discarded at
#   `:169-175`.
#
# THE LOAD-BEARING CLAIM, probed live rather than remembered (`.venv/bin/python`,
# temporalio 1.31.0, 2026-08-21):
#   fields(temporalio.client.ScheduleInfo) -> num_actions,
#     num_actions_missed_catchup_window, num_actions_skipped_overlap,
#     running_actions, recent_actions, next_action_times, created_at,
#     last_updated_at
#   fields(temporalio.client.ScheduleActionResult) -> scheduled_at, started_at,
#     action
# The count and the per-tick history are already on the object the factory
# already describes. This spec is plumbing, not research.
#
# WHAT IS ALREADY FIXED, so nobody rebuilds it. Spec 065 landed 3/3 on
# 2026-08-19 and is live in the running worker. Its child-result guard is at
# `factory/roadmap/workflow.py:139` and `:148`, its caller at `:887-900`. 065
# also shipped `RoadmapWedgeProbe` (`factory/doctor/probes.py:474`), which
# catches a roadmap whose *workflow task is in a failed state*. That is a
# different condition: a run can be perfectly healthy as a workflow and still be
# stuck forever, and 065's probe sees nothing.
#
# A CORRECTION TO THE FINDING, which the implementer must carry. The finding
# cites the 065 guard at `factory/roadmap/workflow.py:849`. THAT ANCHOR IS
# STALE. As of the 2026-08-22 re-anchor: line 849 holds a comprehension clause
# (`and entry.spec_dir not in self._children`) and the capacity comment sits at
# :854 — either way, unrelated content, no guard. An implementer
# sent there finds no guard and concludes 065 never landed.
#
# Filed as, critical and open:
#   roadmap/a-wedged-run-silently-eats-every-subsequent-tick-under-skip-overlap
---

# Feature Specification: a schedule that has not run does not say running

## The gap, stated precisely

The roadmap's schedule uses Temporal's `SKIP` overlap policy, and that is the
right choice: `factory/roadmap/schedule.py:239-241` argues it correctly, and two
roadmap runs dispatching against one corpus would double-dispatch. The cost of
`SKIP` is that the health of the whole schedule is staked on one run being able
to finish. A run stuck for any reason silently converts every subsequent tick
into a skip, with no error, no failure and no end.

Temporal records that. `ScheduleInfo` carries `num_actions_skipped_overlap` and
`recent_actions`, and the factory already holds a described schedule with both on
it. At `factory/roadmap/discovery.py:167` it binds `info`, reads
`next_action_times` off it at `:168`, and drops everything else.

So the operator's floor report renders health from one boolean:

```
schedule: ergane-roadmap (running)
next tick: 2026-08-19T22:15:00+00:00
```

Neither line ever asks whether a tick has run. `running` means `not paused`. It
is not a stale reading or a lagging one — it is a claim about a fact that was
never read, still being printed six hours into an outage in which 76 consecutive
ticks had been eaten.

## The rule this spec is asking for

**A schedule is called running only when a tick has actually run; a schedule
whose ticks are being eaten says so, in the same line that used to say
`running`, with the count that proves it.**

## What this spec does not change

- **`SKIP` stays.** `factory/roadmap/schedule.py:242` keeps
  `policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP)`, and the reasoning
  at `:239-241` stands unedited. The fix is visibility, not concurrency.
- **No bound on how long a run may hold the slot.** The finding's second remedy
  is real and deliberately out of scope: what "yield" means for a workflow that
  may be mid-dispatch, and what the bound should be, are judgements this spec
  cannot make from the data it has, and a wrong bound terminates a healthy long
  epic — a worse outage than the one being closed.
- **065's child-result guard and its wedge probe.**
  `factory/roadmap/workflow.py:139`, `:148`, `:887-900` and
  `factory/doctor/probes.py:474` are landed and correct.
- **The `next tick:` line.** Its value is correct even during starvation — the
  schedule really will tick, it will just skip again. It keeps its wording and
  its value. The false claim lived on the `schedule:` line.
- **`_DECLARED` (`factory/roadmap/schedule.py:98-101`)**, the set of fields a
  manifest declares and a drift report names. Nothing added here is a
  declaration.
- **The discovery ladder's rungs, order, or refusal sentence**
  (`factory/roadmap/discovery.py:89-100`, `:241-245`).

## The other spec that reaches for this file

`specs/083-teardown-is-a-verb-that-names-what-it-removed/` works on
`factory/cli/roadmap.py`'s neighbourhood, and until 2026-08-21 neither spec said
so. Both are being drafted in the same batch, both put the hazard in their
**US3**, and US3 is the tail of both chains — so if the two epics run together
they reach that file in the same window. This section is that hazard declared as
scope. The mechanism, verified line by line:

- **This spec's US3 rewrites two rendering lines**: `factory/cli/roadmap.py:464`
  (`state = "paused" if location.schedule_paused else "running"`, inside
  `_render_disposition` at `:456`) and `:480`
  (`f"roadmap: {'paused' if status.paused else 'running'}",` inside
  `_render_status` at `:478`). **This spec is the only one of the two that edits
  the file at all.**
- **083 was pulled toward the same file and has ruled itself out of it.** `ergane
  uninstall` composes `roadmap_pause_command` (`factory/cli/roadmap.py:342`), and
  that file has **no injectable client seam**: `_connect()` at `:200` calls
  `Client.connect` inline at `:204`, and that is the only occurrence in the file.
  Contrast `factory/cli/repo.py:93` — `_temporal_client_factory: Callable[[],
  Awaitable[Client]] = _open_client`, read at `:98` — a real module-attribute
  seam a test can rebind. That asymmetry is why 083's implementer would reach
  here. 083's plan settles it the other way: the seam goes in teardown's own step
  table, and 083's **FR-017 makes `factory/cli/roadmap.py` a file it MUST NOT
  edit**, with its US3-S6 control and `git diff --stat` check to prove it.
- **So the expected collision is none — and the hazard is that 083 breaks its own
  ruling.** If an 083 attempt adds the seam anyway, it lands above
  `factory/cli/roadmap.py:456` and moves every anchor below. That is the case the
  four rules under this heading exist for; it is not the expected case.

**What this spec's implementer does about it, as declared scope:**

- **Confine every edit to the two render functions**, `_render_disposition`
  (`factory/cli/roadmap.py:456`) and `_render_status` (`:478`). Lines `:464` and
  `:480` are the whole of this spec's business in that file.
- **Do not add, move or refactor a client seam** near `_connect`
  (`factory/cli/roadmap.py:200`, `:204`). 083 has ruled that seam out of its own
  scope rather than into it, so building it here does not help 083 — it just adds
  an unowned edit to a file two epics are reading at once.
- **Do not touch `roadmap_pause_command` (`factory/cli/roadmap.py:342`)** even
  though reading this file will pass over it, and even though its ownership
  behaviour is a real defect. It is 083's defect and 083's story.
- **If 083 landed first, re-derive the line numbers rather than trusting them.**
  Under 083's ruling this file is untouched and the anchors hold; but that is a
  rule an attempt can break, and an inserted seam above
  `factory/cli/roadmap.py:456` shifts every anchor in this section silently,
  because there is real content at the old numbers. Re-derive by exact line text
  — `grep -n` the construct — never by applying an offset. A plan citing a line
  that has moved is the most expensive defect class in this repository.

## User Scenarios & Testing

### User Story 1 - The read stops throwing the fact away (Priority: P1)

As the code that resolves where a roadmap lives, I carry the schedule's observed
tick history alongside the next tick time, instead of reading one field off the
description and discarding the rest.

**Why this priority**: P1 and it is the spine. No renderer can tell the truth
about a fact that never left the describe call.

**Independent Test**: describe a schedule with a skipped-overlap count and a
recent-action history through the discovery ladder, and assert the resolved
location carries both.

**Acceptance Scenarios**:

1. **Given** a described schedule whose `info` carries
   `num_actions_skipped_overlap` and `recent_actions`, **When** the ladder
   resolves it, **Then** the location carries the count and the newest action's
   `started_at` — proven by a committed test asserting both on the location.
2. **Given** the same description, **When** the ladder resolves it, **Then** the
   location also carries the schedule's cadence, read from the described
   schedule's interval — proven by a committed test. Without a cadence, "a tick
   is overdue" has no scale and means nothing.
3. **Given** a schedule that has never ticked, **When** the ladder resolves it,
   **Then** the location carries no last-start and the schedule's `created_at`
   instead — proven by a committed test. A schedule minutes old is not starved,
   and `factory/roadmap/discovery.py:147-148` already promises such a schedule is
   reported rather than hidden.
4. **Given** a description whose `info` is absent or whose fields are missing,
   **When** the ladder resolves it, **Then** it returns a location with the new
   facts unset and every existing field intact — proven by a committed test.
   **This is the degrade control**: 052 landed the principle that a degraded
   reading renders the rest, and a floor report that dies on a schedule it cannot
   fully read is a worse regression than the bug being fixed.
5. **Given** the new observed facts, **When** a drift report is produced, **Then**
   none of them appears in it — proven by a committed test asserting `_DECLARED`
   (`factory/roadmap/schedule.py:98-101`) is unchanged. An observed fact in the
   declared set is a permanent phantom disagreement.
6. **Given** a described schedule whose `recent_actions` carries several entries
   with distinct times, **When** the ladder resolves it, **Then** the last-start
   it carries is the **newest** entry's `started_at`, not the oldest — proven by a
   committed test whose assertion fails if the wrong end is taken. The SDK
   documents `recent_actions` as *"10 most recent actions, oldest first"*, so the
   newest is the last element. The neighbouring read this story widens takes
   `next_times[0]` (`factory/roadmap/discovery.py:174`) because future times
   ascend; copying that idiom one field over reports a start up to ten cadences
   stale and manufactures `starved` on a perfectly healthy schedule.
7. **Given** each of the four `describe()` fakes this tree already has, **When** a
   location is resolved through it, **Then** the cadence is set rather than
   absent — proven by one committed test asserting a readable cadence for every
   one of the four. **This is the green-for-nothing control.** Three of them build
   `schedule=SimpleNamespace(action=..., state=...)` with no `spec` attribute at
   all (`tests/test_roadmap_schedule_discovery.py:146-155`,
   `tests/test_roadmap_wedge_visibility.py:89-96`,
   `tests/test_ergane_status.py:347-354`); only `tests/fake_schedules.py:63`
   returns a real `Schedule` — via `_stored()` at `:51` — and so carries one.
   FR-008 turns an unreadable cadence into `unknown`, so without this control
   three fakes yield `unknown`, every US2 verdict scenario and every starved
   rendering in US3 becomes unreachable, and the suite passes proving nothing.

---

### User Story 2 - Starvation is decided once, from the last tick that actually ran (Priority: P1)

As the model that holds a roadmap's location, I answer what state the schedule is
in — paused, running, starved or unknown — so no renderer invents the answer and
no two renderers can disagree.

**Why this priority**: P1. The defect is one sentence duplicated in two files
(`factory/cli/status.py:729`, `factory/cli/roadmap.py:464`); fixing one leaves
the other lying, and a third caller would inherit it again. The verdict belongs
beside `refusal` (`factory/roadmap/discovery.py:89`), already a computed property
that phrases a fact for the operator.

**Independent Test**: build locations with known tick histories and assert the
verdict each yields, rendering nothing.

**Acceptance Scenarios**:

1. **Given** an unpaused schedule whose newest action started more than two
   cadence intervals ago, **When** its state is asked for, **Then** it is
   `starved` — proven by a committed test. Two intervals, not one: one grace tick
   absorbs ordinary clock and dispatch jitter.
2. **Given** an unpaused schedule whose newest action started within two cadence
   intervals, **When** its state is asked for, **Then** it is `running` — proven
   by a committed test.
3. **Given** an unpaused schedule with a large non-zero lifetime
   `num_actions_skipped_overlap` whose newest action started one minute ago,
   **When** its state is asked for, **Then** it is `running` — proven by a
   committed test. **This is the false-alarm control and it decides the spec.**
   The count is a lifetime counter, not a rate: a schedule that skipped twice last
   Tuesday reports non-zero forever, so `count > 0 → unhealthy` is a permanent
   warning, and a permanent warning is read once and ignored — this same outage in
   a new costume. The count is evidence printed in the sentence, never the trigger.
4. **Given** a paused schedule, however long since its last tick, **When** its
   state is asked for, **Then** it is `paused` — proven by a committed test. A
   paused schedule not ticking is the operator's decision, not a fault.
5. **Given** a schedule with no recorded actions and a `created_at` less than two
   cadence intervals old, **When** its state is asked for, **Then** it is
   `running` — proven by a committed test. This is new coverage, not preserved
   coverage: `tests/test_roadmap_first_tick_on_fresh_init.py` reads as though it
   guards this window and does not — its docstring at `:1-7` scopes it to the
   *workflow's* first tick against a freshly-initialised tree, and it imports
   neither `factory.roadmap.discovery` nor either renderer.
6. **Given** a schedule whose cadence or tick history could not be read, **When**
   its state is asked for, **Then** it is `unknown` rather than `running` or
   `starved` — proven by a committed test. Not knowing is a third answer, and
   printing a guess as a verdict is what caused this finding.
7. **Given** any location, **When** its state is computed, **Then** the
   computation reads only the location's own fields and performs no I/O — proven
   by a committed test computing a verdict from a constructed location with no
   client bound at all.

---

### User Story 3 - Both verbs print the verdict, and stop colliding (Priority: P2)

As an operator, `ergane status` and `ergane roadmap status` both tell me whether
the schedule has actually run, and no two lines in either say "running" about
unrelated things.

**Why this priority**: P2 by dependency, not by importance — it is the half the
operator sees. Both verbs get it because both printed the lie and the same person
reads them for different reasons: `ergane status` is the floor report watched
during a run, `ergane roadmap status` the verb run when the roadmap is already
suspected. Neither recomputes; both read US2's verdict.

**Independent Test**: render both verbs against one starved location and one
healthy location and compare the four outputs.

**Acceptance Scenarios**:

1. **Given** a starved location, **When** `ergane status` renders its roadmap
   block, **Then** the `schedule:` line says starved, names how long since a tick
   actually started, and names the skipped count — proven by a committed test
   asserting the rendered line.
2. **Given** the same starved location, **When** `ergane roadmap status` renders
   its disposition, **Then** it produces the same verdict word as `ergane status`
   — proven by a committed test rendering both from one location and asserting
   they agree. Two renderers that can drift are how this defect survives being
   fixed once.
3. **Given** a healthy location, **When** either verb renders, **Then** the output
   is unchanged from today, word for word: `schedule: <id> (running)` and
   `next tick: <time>` — proven by a committed test pinning both strings. **This
   is the control**, and it is what keeps every existing status test honest.
4. **Given** a location whose schedule state is `unknown`, **When** either verb
   renders, **Then** the schedule line says so and every other line of the report
   still renders — proven by a committed test. 052's principle again.
5. **Given** `ergane roadmap status` on a running roadmap, **When** its status
   block renders, **Then** the line at `factory/cli/roadmap.py:480` no longer says
   `roadmap: running` but names its actual subject, dispatch, matching the word
   `factory/cli/status.py:738` already uses for that fact — proven by a committed
   test asserting the new line and that the schedule line and the dispatch line
   cannot be read as one another. Two lines both saying "running" for unrelated
   reasons is how the reporter lost six hours.

## Requirements

### Functional Requirements

- **FR-001**: The discovery ladder MUST carry the described schedule's
  `num_actions_skipped_overlap` and the `started_at` of its newest action onto
  the resolved location. `recent_actions` is ordered oldest-first, so the newest
  is its **last** element.
- **FR-002**: The location MUST carry the schedule's cadence — read from
  `described.schedule.spec.intervals`, the field
  `factory/roadmap/schedule.py:188` and `:197` already decode — and its
  `created_at`, so an overdue tick can be judged against a scale. Every one of
  this tree's four `describe()` fakes MUST supply that field, because a fake that
  does not yields `unknown` under FR-008 and makes the verdict suite pass without
  exercising a verdict.
- **FR-003**: A description whose `info` cannot be read MUST yield a location with
  the new facts unset and every existing field intact, never an exception.
- **FR-004**: The new facts MUST NOT be added to `_DECLARED`.
- **FR-005**: The location MUST answer its own schedule state as one of `paused`,
  `running`, `starved` or `unknown`, computed from its own fields with no I/O.
- **FR-006**: `starved` MUST be decided by how long since a tick actually started,
  measured in cadence intervals, with the threshold stated in the code as a named
  constant set at two.
- **FR-007**: A non-zero lifetime skipped-overlap count with a recent actual start
  MUST be `running`; the count MAY appear as evidence in the rendered sentence and
  MUST NOT be the trigger.
- **FR-008**: An unreadable cadence or tick history MUST be `unknown`, never
  `running` and never `starved`.
- **FR-009**: Both `ergane status` and `ergane roadmap status` MUST render the
  location's computed state and MUST NOT recompute it.
- **FR-010**: A starved schedule's rendered line MUST name the elapsed time since
  the last actual start and the skipped-overlap count.
- **FR-011**: A healthy schedule's rendered output MUST be unchanged from today in
  both verbs.
- **FR-012**: `factory/cli/roadmap.py:480` MUST name dispatch rather than
  `roadmap`, matching `factory/cli/status.py:738`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010, FR-011, FR-012]
  persona: opus-closer
```

US1 and US2 both edit `factory/roadmap/discovery.py` — US1 the fields and the read
at `:166-175`, US2 a computed property beside `refusal` at `:89`. That is
contention, not logic. US3's edge is a real content dependency: it renders a
verdict it does not compute, so it needs US2's code in its base.

US3 also carries the only **cross-spec** hazard in this batch: it edits
`factory/cli/roadmap.py`, the file 083's US3 is pulled toward and has ruled itself
out of (083's FR-017). Both are the tail of their chain, so they land in the same
window. See *The other spec that reaches for this file* above for the mechanism and the
four rules that keep this spec's edit the only one. This graph cannot express that edge —
the factory schedules within a spec, not across two — so it is declared as scope
and enforced by the implementer, not by the workflow.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Commit the SDK probe as pasted output — the installed `temporalio`
  version and the field lists of `ScheduleInfo` and `ScheduleActionResult` —
  proving `num_actions_skipped_overlap` and `recent_actions` are already on the
  object the factory describes.
- **SC-002**: Paste the resolved location for a described schedule carrying a
  skipped count and an action history, showing both facts survived the read.
- **SC-003**: Paste the degrade control: a description with no readable `info`
  resolving to a complete location with the new facts unset.
- **SC-004**: Paste the verdict table — one line per case — for starved, running,
  paused, never-ticked and unknown, each with the inputs that produced it.
- **SC-005**: Paste the false-alarm control: a large non-zero lifetime skipped
  count with a one-minute-old actual start, rendering `running`.
- **SC-006**: Paste `ergane status`'s roadmap block and `ergane roadmap status`'s
  disposition block for one starved location, side by side, same verdict word.
- **SC-007**: Paste the healthy control for both verbs, showing today's output
  byte for byte.
- **SC-008**: Paste `ergane roadmap status` showing the dispatch line under its
  new name alongside the schedule line.
- **SC-009**: Paste the fake-parity table — one row per `describe()` fake in this
  tree, each naming the fake and the cadence the discovery ladder read through
  it — proving that no fake yields `unknown` where a scenario intends a real
  verdict.

## Assumptions

- `recent_actions` records only actions that actually started, so a skipped tick
  leaves no entry and the newest entry's `started_at` is a true "when did this
  schedule last actually run". **This is now settled by type rather than by
  observation**, read out of the installed SDK source on 2026-08-21 (temporalio
  1.31.0): `ScheduleActionResult.started_at` is built from `res.actual_time` and
  documented *"When the action actually started."*, and its `action` is built
  from `res.start_workflow_result` as a `ScheduleActionExecutionStartWorkflow`
  carrying `workflow_id` and `first_execution_run_id`. A skipped tick starts no
  workflow and has no run id, so the type has nothing to put there. It was the
  one assumption that could have changed the design; the plan carries the probe
  that settles it and the fallback branch if a live server ever disagrees.
- The `recent_actions` window is exactly ten entries, **ordered oldest-first** —
  the SDK documents the field as *"10 most recent actions, oldest first."* Only
  the newest is needed, so the bound does not matter: a schedule starved far
  longer than ten cadences still has its newest entry, which is what makes this
  work. The **order** does matter, and it is the opposite of the neighbouring
  `next_action_times` read at `factory/roadmap/discovery.py:174`.
- The cadence is readable from `described.schedule.spec.intervals`, the same field
  `factory/roadmap/schedule.py:188` and `:197` already decode from the same object.
  Verified as source lines, and verified as **absent from three of the four test
  fakes**: `tests/test_roadmap_schedule_discovery.py:146-155`,
  `tests/test_roadmap_wedge_visibility.py:89-96` and
  `tests/test_ergane_status.py:347-354` build a `schedule` with `action` and
  `state` and no `spec`; only `tests/fake_schedules.py:63` returns a real
  `Schedule`. The discovery path does not touch `described.schedule.spec` today,
  so this is new ground on both the source side and the fixture side, and US1-S7
  is the control that proves the fixture side was done.
- Two cadence intervals is a chosen threshold, not a measured one. It is a named
  constant precisely so the next operator can change it against evidence rather
  than rediscover it inside a conditional.
- The finding's own anchor `factory/roadmap/workflow.py:849` is stale; the
  correction in this frontmatter was re-verified 2026-08-22 at 732ff88.
