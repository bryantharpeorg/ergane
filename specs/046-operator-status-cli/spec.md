---
state: ready
# Drafted 2026-08-15 by an operator session at the operator's request: "what's
# the CLI-native way to get the status table" — answer: there isn't one, and
# probing for one found cli/roadmap-verbs-cannot-see-schedule-driven-runs
# (filed the same hour). Scoped deliberately small: two paper cuts named in the
# same conversation turned out to already be fixed (`build kill --yes` exists;
# `spec landed` reads landing_branch from the manifest since 020-US1), and the
# plan records that evidence so nobody re-fixes them.
---

# Feature Specification: 046-operator-status-cli

## Context

The operator's morning question is always the same: what is running, what is
it doing story by story, what is queued behind it, what is waiting on a ready
flip, and how fast is it moving. Today that answer is assembled by hand from
three commands and one database:

- `ergane build status <epic-id>` — one epic's stories, but you must already
  know which epic is running.
- `ergane spec list specs` — every spec's state and blockers, but nothing
  about the live floor.
- `ergane roadmap status specs` — should be the top half, and answers
  `no roadmap 'specs' is running here` whenever the roadmap is driven by a
  Temporal schedule, which spawns runs named `roadmap-specs-<timestamp>` while
  the verb looks only for the bare `roadmap-specs`
  (`cli/roadmap-verbs-cannot-see-schedule-driven-runs`, filed 2026-08-15 after
  it failed live with a run visible in `temporal workflow list`).
- Pace — attempt wall-times, the only honest input to "when will this land" —
  exists as `started_at`/`finished_at` on every row of
  `verification_results`, and no verb computes over it.

The same session hit a smaller wall twice: `ergane build status
epic-011-agent-sandbox` dials `epic-epic-011-agent-sandbox`, because the verb
prefixes unconditionally and the operator pasted an id from Temporal's own
output.

One new verb and two fixes. Nothing here writes anything.

---

### User Story 1 - `ergane status` answers the morning question in one screen (Priority: P1)

As an operator, I run `ergane status` with no arguments and read, in order:
the roadmap's disposition (schedule or bare workflow, running or paused, next
tick when a schedule owns it); every running epic with its per-story state and
attempt table; the ready queue with each blocked spec's blockers; drafts
awaiting a flip; and each running epic's measured pace — completed stories'
attempt wall-times and the count remaining — labeled as measurement, never as
a promise.

**Why this priority**: it is the verb the operator reconstructs by hand every
few hours, and every piece of it already exists in some store — this story is
a join, not a mechanism.

**Independent Test**: on a floor with one running epic, one ready-blocked
spec and one draft, `ergane status` renders all five sections; with Temporal
stopped, the spec-derived sections still render and the Temporal-derived ones
degrade to a named note instead of an error.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree (constitution VIII).
Runtime claims are met by tool output pasted verbatim into a comment block in
the test file.

**Acceptance Scenarios**:

1. **Given** a seeded floor — a running epic with mixed story states, a ready
   spec blocked on it, a draft — **When** `ergane status` runs, **Then** the
   output contains the roadmap disposition, the epic's story table, the queue
   with its blockers named, and the drafts, in that order, proven by a
   committed test.

2. **Given** a roadmap driven by a Temporal schedule, **When** `ergane status`
   runs, **Then** the disposition names the schedule, its paused/running
   state, and its most recent run — not `no roadmap is running` — proven by a
   committed test.

3. **Given** completed attempts in the verification store, **When**
   `ergane status` runs, **Then** each running epic shows its stories'
   measured attempt wall-times (from `started_at`/`finished_at`) and the
   remaining-story count, worded as measurement, with no projected completion
   time anywhere in the output — proven by a committed test.

4. **Given** no reachable Temporal, **When** `ergane status` runs, **Then**
   the spec-derived sections render, the Temporal-derived sections carry one
   note naming the unreachable address, and the exit code distinguishes
   degraded from clean — proven by a committed test against a closed port.

5. **Given** `--json`, **When** the same floor is queried, **Then** the
   result is one machine-readable document carrying every section the human
   view renders, proven by a committed test.

6. **Given** any invocation of `ergane status`, **When** it completes on a
   checkout with no runtime root, **Then** no directory was created and no
   store was opened for write — status is read-only, and the resolver's
   directory-creating side effect must not fire — proven by a committed test.

---

### User Story 2 - The roadmap verbs can see schedule-driven runs (Priority: P1)

As an operator, `ergane roadmap status specs` finds the roadmap whether it was
started bare or by a schedule, and `pause`/`resume` act on the thing that
actually owns dispatch: when a schedule owns the roadmap, pausing the schedule
— pausing only the current run is a lie, because the next tick spawns a fresh
run and dispatch continues.

**Why this priority**: the filed finding, plus the operational record — on
2026-08-14 the operator had to fall back to raw `temporal schedule toggle`
because `resume` could not find the roadmap it was resuming.

**Independent Test**: with a schedule spawning timestamped runs, `status`
reports the newest run; `pause` leaves the schedule paused (visible in a
schedule describe) and `resume` unpauses it; with a bare `roadmap start`
workflow and no schedule, all three verbs behave exactly as today.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** a schedule whose runs are named `roadmap-<root>-<timestamp>` and
   no bare `roadmap-<root>` workflow, **When** `ergane roadmap status <root>`
   runs, **Then** it reports the newest run's status and names both the run id
   and the owning schedule, proven by a committed test.

2. **Given** the same floor, **When** `ergane roadmap pause <root>` runs,
   **Then** the schedule is paused — proven by reading the schedule back —
   and the human output says the schedule, not merely the run, was paused.

3. **Given** a paused schedule, **When** `ergane roadmap resume <root>` runs,
   **Then** the schedule is unpaused, symmetrically, proven by a committed
   test.

4. **Given** a bare workflow started by `ergane roadmap start` and no
   schedule, **When** any of the three verbs runs, **Then** behavior is
   byte-identical to today, proven by a committed test.

5. **Given** neither a bare workflow, a schedule, nor any timestamped run,
   **When** `status` runs, **Then** the refusal names everything it looked
   for — the bare id, the schedule, the run prefix — so the operator's next
   move is legible, proven by a committed test.

---

### User Story 3 - The build verbs accept the id the operator actually has (Priority: P2)

As an operator, I paste `epic-011-agent-sandbox` — the workflow id Temporal's
own output shows — into `ergane build status`, and it reaches the same epic
as `011-agent-sandbox` instead of dialing `epic-epic-011-agent-sandbox`.

**Why this priority**: cosmetic against the other two, observed twice in one
morning, and a one-function fix at the prefixing seam.

**Independent Test**: both id forms reach the same workflow across every
build verb; an id that matches nothing still fails with today's error.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** a running epic, **When** any build verb receives the spec-dir
   form or the `epic-`-prefixed form, **Then** both resolve to the same
   workflow id, proven by a committed test covering every verb that calls the
   prefixing function.

2. **Given** an id that exists as neither form, **When** a verb runs, **Then**
   the error is today's, naming the workflow id it dialed — normalization
   MUST NOT widen what counts as found.

3. **Given** a hypothetical spec directory legitimately named with an `epic-`
   prefix, **When** the exact id fails to resolve, **Then** the error names
   both candidates it tried, so the collision is legible rather than silent.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ergane status` MUST render, in one invocation: roadmap
  disposition, running epics with per-story state and attempts, the ready
  queue with named blockers, drafts, and measured pace per running epic.
- **FR-002**: `ergane status` MUST be read-only: no store opened for write,
  no directory created — including the runtime-root resolver's mkdir side
  effect — and MUST NOT signal, start, or mutate anything.
- **FR-003**: Pace MUST be computed from `verification_results` timestamps
  and presented as measurement; the output MUST NOT contain a projected
  completion time.
- **FR-004**: With Temporal unreachable, `ergane status` MUST still render
  every section derivable from files, degrade the rest to a note naming the
  address, and exit with a code that distinguishes degraded from clean.
- **FR-005**: `--json` MUST emit one document carrying every section the
  human view renders.
- **FR-006**: `roadmap status`, `pause` and `resume` MUST resolve
  schedule-driven roadmaps: status reports the newest run and names the
  owning schedule; pause and resume act on the schedule when one owns the
  roadmap, and on the bare workflow otherwise, unchanged.
- **FR-007**: A roadmap verb that finds nothing MUST name everything it
  looked for: the bare workflow id, the schedule, and the run prefix.
- **FR-008**: Readiness and blocker computation MUST come from the existing
  roadmap reader — a second implementation of "ready" is a defect.
- **FR-009**: Every build verb MUST accept both the spec-dir id and the
  `epic-`-prefixed workflow id, normalizing at the single existing prefix
  seam, without widening what counts as found.

### Key Entities

- **FloorStatus**: the joined view — roadmap disposition, running epics with
  stories, queue, drafts, pace — rendered human or `--json`.
- **RoadmapDisposition**: which thing owns dispatch (schedule or bare
  workflow), its paused/running state, newest run, next tick when scheduled.
- **StoryPace**: one epic's measured attempt wall-times and remaining-story
  count.

## Success Criteria *(mandatory)*

- **SC-001**: The morning question is one command: a seeded floor with a
  running epic, a blocked ready spec and a draft renders all five sections in
  one `ergane status` invocation.
- **SC-002**: The 2026-08-15 failure is reproducible and fixed: with only
  timestamped schedule runs present, `roadmap status` reports the newest run,
  and `pause`/`resume` round-trip the schedule's paused state.
- **SC-003**: `ergane status` on a checkout with no runtime root creates
  nothing — asserted on the filesystem after the run.
- **SC-004**: **Control.** With US2 unapplied (its resolution seam disabled),
  the schedule-driven floor reproduces today's `no roadmap 'specs' is running
  here` — establishing the fix changed an outcome.

## Assumptions

- The schedule is operator-created (`temporal schedule create`) and its id is
  not derivable from the specs root; discovery goes through the schedule
  list, matching schedules whose action starts runs with the roadmap's id
  prefix. If the Temporal server predates schedule listing, the verbs degrade
  per FR-007.
- `ergane status` is a new top-level noun; it does not replace
  `build status` or `spec list`, which remain the per-object deep views.

## Out of Scope

- A `--watch` mode or any TUI; one shot, one screen.
- The web status board — it renders its own view from its own reads.
- Projected completion times. Pace is measurement; forecasting is the
  operator's judgment.
- The remaining two legs of `cli/landed-defaults-to-the-wrong-branch`
  (`derive --delta` hardcoding `main`; the workflow path asking the clone) —
  they are tangled in the operator's pending 016 decision, and this spec
  MUST NOT pre-empt it. The `landed` leg is already fixed (manifest
  `landing_branch`, 020-US1); the plan records the verification.
- `ergane build kill` confirmation ergonomics — `--yes` already exists
  (`factory/cli/nouns/build.py:708`).

## Work Graph

```yaml
US1:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-008]
US2:
  depends_on: []
  implements: [FR-006, FR-007]
US3:
  depends_on: []
  implements: [FR-009]
```
