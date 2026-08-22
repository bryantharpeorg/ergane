# Tasks: a schedule that has not run does not say running

**Spec**: `specs/085-a-schedule-that-has-not-run-does-not-say-running/spec.md`
**Plan**: `specs/085-a-schedule-that-has-not-run-does-not-say-running/plan.md`

Read the plan's traps before the first task. Five decide whether an attempt lands.

**Trap 6 first, because it is the one that produces a *passing* wrong answer.**
Each of the four `describe()` fakes has **two** holes, in two different objects.
The `info` half — `tests/fake_schedules.py:65`,
`tests/test_roadmap_schedule_discovery.py:156-158`,
`tests/test_roadmap_wedge_visibility.py:97-99` and `tests/test_ergane_status.py:355`
— is missing in all four. The `schedule` half is missing in **three of the four**:
FR-002 reads the cadence from `described.schedule.spec.intervals`, and
`tests/test_roadmap_schedule_discovery.py:146-155`,
`tests/test_roadmap_wedge_visibility.py:89-96` and
`tests/test_ergane_status.py:347-354` each build a `schedule` with `action` and
`state` and **no `spec` attribute at all**. Only `tests/fake_schedules.py:63`
(`schedule=self._stored(),`, returning a real `Schedule` via `_stored()` at `:51`)
already carries one. FR-008 turns an unreadable cadence into `unknown`, and
`unknown` is a state this code tolerates **by design** — so a fake left without a
`spec` does not fail, it silently makes US2-S1/S2/S3/S5 and every starved
rendering in US3 unreachable while the suite reports green. T009a and SC-009 are
the control.

**Trap 15: `recent_actions` is oldest-first.** The newest is `[-1]`. The line you
are widening ends in `next_times[0]` (`factory/roadmap/discovery.py:174`), which is
right for future times and wrong for this one; the SDK documents the field as
*"10 most recent actions, oldest first."* Taking `[0]` raises nothing and reports a
start up to ten cadences stale.

**Trap 1: a lifetime counter is not a health signal** — the trigger is time since a
tick actually started, and the skipped count is only evidence printed in the
sentence. **Trap 2: two renderers, one sentence** — the verdict is computed once on
`RoadmapLocation`, never twice in two CLI files. **Trap 17: 083 is pulled toward
`factory/cli/roadmap.py` and has ruled itself out of it** (083's FR-017 makes it a
MUST NOT), so you are its only editor — US3 stays inside `_render_disposition`
(`factory/cli/roadmap.py:456`) and `_render_status` (`:478`) and touches no client
seam.

## Phase 1: User Story 1 — The read stops throwing the fact away

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) In
      `tests/test_schedule_ticks_survive_the_read.py`, assert a described schedule
      whose `info` carries `num_actions_skipped_overlap` and `recent_actions`
      resolves to a location carrying the count and the newest action's
      `started_at`.
- [ ] T001a [P] [US1] (spec US1-S6, FR-001) **The ordering control.** Give the
      fake several `recent_actions` entries with distinct `started_at` times and
      assert the location carries the **newest** — `recent_actions[-1]`, because
      the SDK documents the field as *"10 most recent actions, oldest first."* An
      implementer copying the `next_times[0]` idiom at
      `factory/roadmap/discovery.py:174` one field over passes T001 and fails here
      (trap 15).
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert the location carries the
      schedule's cadence, read from `described.schedule.spec.intervals` — the field
      `factory/roadmap/schedule.py:188` and `:197` already decode off the same
      object. Note that this is a read against `described.schedule`, **not**
      `described.info`: it is the second of the two fixture holes in trap 6, and
      three of the four fakes have no `spec` attribute to read.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) Assert a schedule with no recorded
      actions resolves with no last-start and its `created_at` instead.
      `factory/roadmap/discovery.py:147-148` already promises a never-ticked
      schedule is reported (trap 10).
- [ ] T004 [P] [US1] (spec US1-S4, FR-003) **The degrade control.** Assert a
      description with no readable `info` resolves to a complete location, new
      facts unset, `schedule_paused` and `next_action_at` intact, no exception
      (trap 3).
- [ ] T005 [P] [US1] (spec US1-S5, FR-004) Assert `_DECLARED`
      (`factory/roadmap/schedule.py:98-101`) is unchanged and no new field appears
      in a drift report from `disagreements` (`:104`) (trap 4).

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002) Widen the read at
      `factory/roadmap/discovery.py:166-168` to carry the skipped count, the newest
      `recent_actions` entry's `started_at`, `created_at` and the cadence, using the
      `getattr(..., default)` discipline already there (trap 3).
- [ ] T007 [US1] (FR-001, FR-002) Add the fields to `_Found`
      (`factory/roadmap/discovery.py:104-111`) and `RoadmapLocation` (`:65-82`), and
      pass them at the `_Found(...)` site `:169-175`.
- [ ] T008 [US1] (FR-003) Handle **both** `RoadmapLocation(...)` constructions in
      `resolve_roadmap` — `:265-275` and `:276-286`. The second is the path a new
      user's first `ergane status` takes (trap 8).
- [ ] T009 [US1] (FR-001, FR-002) Extend the fakes on **both** halves — eight
      edits, not four (trap 6). *The `info` half, all four:*
      `tests/fake_schedules.py:65`,
      `tests/test_roadmap_schedule_discovery.py:156-158`,
      `tests/test_roadmap_wedge_visibility.py:97-99` and
      `tests/test_ergane_status.py:355` each need
      `num_actions_skipped_overlap`, `recent_actions` and `created_at` alongside
      `next_action_times`. *The `schedule` half, three of the four:* add
      `spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=...)])` to
      `tests/test_roadmap_schedule_discovery.py:146-155`,
      `tests/test_roadmap_wedge_visibility.py:89-96` and
      `tests/test_ergane_status.py:347-354`, whose `schedule=SimpleNamespace(...)`
      carries only `action` and `state` today. **`tests/fake_schedules.py` needs no
      `spec`** — `:63` is `schedule=self._stored(),` and `_stored()` (`:51`) returns
      the real `Schedule` the factory built with
      `spec=ScheduleSpec(intervals=[...])` at
      `factory/roadmap/schedule.py:236-237`. Both names import from
      `temporalio.client`, the same module those three files already import
      `ScheduleActionStartWorkflow` from (`tests/test_roadmap_schedule_discovery.py:86`,
      `tests/test_roadmap_wedge_visibility.py:29`,
      `tests/test_ergane_status.py:201`) and the same import
      `factory/roadmap/schedule.py:222` and `:225` use. Reach schedules only through
      the seam — `_refuse_live_client` (`factory/roadmap/schedule.py:247`) records
      what happened last time (trap 5).
- [ ] T009a [US1] (spec US1-S7, FR-002) **The fake-parity control, and the task
      that decides US1.** One committed test that resolves a location through
      **every** `describe()` fake in the tree and asserts each yields a readable
      cadence — never `unknown`. Write it before T009 and watch it fail three
      times, then pass. Without it, extending only the `info` half leaves a green
      suite that exercises no verdict at all, which is the exact failure this spec
      exists to close arriving through the test suite (trap 6).
- [ ] T010 [US1] (FR-004) Leave `_DECLARED` exactly as it is.

### Verification for this story

- [ ] T011 [US1] (SC-001) Commit the SDK probe as pasted output: the installed
      `temporalio` version and the field lists of `ScheduleInfo` and
      `ScheduleActionResult`. Include the two docstring lines the plan calls
      load-bearing — `recent_actions` as *"10 most recent actions, oldest first."*
      (trap 15) and `started_at` as *"When the action actually started."* with the
      `res.start_workflow_result` construction that settles the skipped-tick
      question (trap 16). This is the load-bearing claim of the spec (trap 12).
- [ ] T012 [US1] (SC-002) Paste the resolved location for a described schedule
      carrying a skipped count and an action history.
- [ ] T013 [US1] (SC-003) Paste the degrade control: no readable `info`, complete
      location, new facts unset.
- [ ] T013a [US1] (SC-009) Paste the fake-parity table: one row per `describe()`
      fake, naming the fake and the cadence the discovery ladder read through it.
      No row may read `unknown`. This is T009a's evidence, and it is what a
      reviewer checks instead of taking a green suite as proof (trap 12).

## Phase 2: User Story 2 — Starvation is decided once, from the last tick that actually ran

**Depends on US1 having merged** (`depends_on_merged`). Both stories edit
`factory/roadmap/discovery.py`: US1 the fields and the read at `:166-175`, US2 a
property beside `refusal` at `:89`. Contention, not logic (trap 2).

### Tests for this story (write FIRST, must fail)

- [ ] T014 [P] [US2] (spec US2-S1, FR-005, FR-006) In
      `tests/test_a_starved_schedule_is_not_running.py`, assert an unpaused schedule
      whose newest action started more than two cadence intervals ago is `starved`.
- [ ] T015 [P] [US2] (spec US2-S2, FR-005) Assert one whose newest action started
      within two cadence intervals is `running`.
- [ ] T016 [P] [US2] (spec US2-S3, FR-007) **The false-alarm control, and the
      scenario that decides this story.** Assert a large non-zero lifetime
      `num_actions_skipped_overlap` with a one-minute-old actual start is `running`.
      A verdict wired to the counter passes T014 and T015 and fails here (trap 1).
- [ ] T017 [P] [US2] (spec US2-S4, FR-005) Assert a paused schedule is `paused`
      however long since its last tick.
- [ ] T018 [P] [US2] (spec US2-S5, FR-005) Assert a schedule with no recorded
      actions and a `created_at` under two cadence intervals old is `running`
      (trap 10). New coverage — despite its name,
      `tests/test_roadmap_first_tick_on_fresh_init.py` tests the workflow's first
      tick, not a never-ticked schedule's verdict, and touches neither
      `factory.roadmap.discovery` nor a renderer.
- [ ] T019 [P] [US2] (spec US2-S6, FR-008) Assert an unreadable cadence or tick
      history is `unknown` — never `running`, never `starved` (trap 3).
- [ ] T020 [P] [US2] (spec US2-S7, FR-005) Assert the verdict is computed from a
      constructed location with no client bound at all: pure, no I/O.

### Implementation for this story

- [ ] T021 [US2] (FR-005) Add the computed property to `RoadmapLocation`, beside
      `refusal` (`factory/roadmap/discovery.py:84-100`) and in its shape — a
      docstring that says what it degrades to (trap 2).
- [ ] T022 [US2] (FR-006) State the threshold as a named module constant set at two
      cadence intervals, not as a literal inside a conditional.
- [ ] T023 [US2] (FR-007) Carry the skipped count as evidence for the renderer to
      print; never let it decide the verdict (trap 1).
- [ ] T024 [US2] (FR-005) Keep the word `starved`. Not `stalled`
      (`factory/mergequeue/models.py:77`), not `parked`
      (`factory/cli/roadmap.py:484`, two lines below the one FR-012 rewrites), not
      `blocked` (`CONTEXT.md:132`). Only the third is in `CONTEXT.md`, so a
      fruitless grep there is not permission to reuse the other two (trap 11).

### Verification for this story

- [ ] T025 [US2] (SC-004) Paste the verdict table, one line per case: starved,
      running, paused, never-ticked, unknown, each with the inputs that produced it.
- [ ] T026 [US2] (SC-005) Paste the false-alarm control: a large lifetime skipped
      count with a recent actual start, rendering `running`.

## Phase 3: User Story 3 — Both verbs print the verdict, and stop colliding

**Depends on US2 having merged** (`depends_on_merged`) — a real content dependency:
this story renders a verdict it does not compute.

**And it shares a file with a spec the work graph cannot see** (trap 17).
`specs/083-teardown-is-a-verb-that-names-what-it-removed/`'s US3 wires
`ergane uninstall` to `roadmap_pause_command` (`factory/cli/roadmap.py:342`), and
the obvious way to make that testable is a client seam here, because `_connect()`
at `:200` calls `Client.connect` inline at `:204` and that is the file's only
occurrence. **083 ruled that out** — its FR-017 makes `factory/cli/roadmap.py` a
file 083 MUST NOT edit — so you are the only editor and the hazard is an 083
attempt that breaks its own rule. Both stories sit at the tail of their chain, so
they land in the same window. **Every task below stays inside
`_render_disposition` (`factory/cli/roadmap.py:456`) and `_render_status`
(`:478`).** Add no seam near `:200`/`:204`; touch nothing in
`roadmap_pause_command` at `:310`. If 083 landed first, re-derive every anchor in
this file by exact line text with `grep -n` — never by offset, because there is
real content at the old numbers and the misreading resolves silently.

### Tests for this story (write FIRST, must fail)

- [ ] T027 [P] [US3] (spec US3-S1, FR-009, FR-010) In
      `tests/test_both_verbs_agree_about_the_schedule.py`, assert `ergane status`'s
      roadmap block renders a starved schedule line naming the elapsed time since
      the last actual start and the skipped count
      (`factory/cli/status.py:723-736`). Assert the starved sentence **positively**
      — the word, the elapsed time and the count — never merely that the line is
      not `running`. A negative assertion is satisfied by `unknown`, which is what
      `tests/test_ergane_status.py`'s fake yields if T009 skipped its `spec` half,
      and this test would then pass on a fixture that never produced a verdict
      (trap 6).
- [ ] T028 [P] [US3] (spec US3-S2, FR-009) Render both verbs from **one** location
      and assert they produce the same verdict word (`factory/cli/status.py:729`,
      `factory/cli/roadmap.py:464`). A diff where each renderer computes its own
      answer fails here and nowhere else (trap 2).
- [ ] T029 [P] [US3] (spec US3-S3, FR-011) **The control.** Assert a healthy
      location renders byte for byte what it renders today — `schedule: <id>
      (running)` and `next tick: <time>` — in both verbs. Do not touch the `next
      tick:` line (trap 9). Today's output is pinned at
      `tests/test_roadmap_schedule_discovery.py:491-498` (the only `==` assertion
      on the string) and by containment at `tests/test_ergane_status.py:753-756`.
      `tests/test_ergane_roadmap.py` pins no rendered line and is not the file to
      read for this.
- [ ] T030 [P] [US3] (spec US3-S4, FR-009) Assert an `unknown` schedule state
      renders as such and every other line of the report still renders (trap 3).
- [ ] T031 [P] [US3] (spec US3-S5, FR-012) Assert `factory/cli/roadmap.py:480` no
      longer says `roadmap: running`, names dispatch instead — matching
      `factory/cli/status.py:738` — and that the schedule line and the dispatch line
      cannot be read as one another.

### Implementation for this story

- [ ] T032 [US3] (FR-009) Replace `factory/cli/status.py:729` and
      `factory/cli/roadmap.py:464` with a read of US2's computed verdict. Neither
      renderer recomputes anything. `:464` sits inside `_render_disposition`
      (`factory/cli/roadmap.py:456`); that function and `_render_status` (`:478`)
      are the only two this story may enter in that file (trap 17).
- [ ] T033 [US3] (FR-009, FR-010) Carry the verdict and its evidence onto
      `RoadmapDisposition` (`factory/cli/status.py:157-178`) alongside the copies at
      `:522-523`, and render the starved sentence with both pieces of evidence:
      elapsed time since the last actual start, and the skipped count.
- [ ] T034 [US3] (FR-012) Rename the line at `factory/cli/roadmap.py:480` to name
      dispatch, using the word `factory/cli/status.py:738` already uses. Note the
      block already prints `running:` for the epic list at
      `factory/cli/roadmap.py:483` and `parked:` at `:484` — the same
      `dispatch:` / `running:` / `parked:` order `factory/cli/status.py:738-740`
      already uses. Adopt it. This is a rename inside `_render_status`
      (`factory/cli/roadmap.py:478`) and nothing else in the file moves (trap 17).
- [ ] T034a [US3] (FR-012) Update the byte-for-byte assertion the rename breaks:
      `tests/test_roadmap_schedule_discovery.py:491-498`, whose first element is
      `"roadmap: running\n"` at `:492`, plus the docstrings quoting that block at
      `:47`, `:351`, `:479` and `:648`. Update the expected string; do **not**
      weaken `==` to `in` to make it pass (trap 14).

### Verification for this story

- [ ] T035 [US3] (SC-006) Paste `ergane status`'s roadmap block and `ergane roadmap
      status`'s disposition block for one starved location, side by side, showing
      the same verdict word.
- [ ] T036 [US3] (SC-007) Paste the healthy control for both verbs, byte for byte as
      they render today.
- [ ] T037 [US3] (SC-008) Paste `ergane roadmap status` showing the dispatch line
      under its new name alongside the schedule line.
