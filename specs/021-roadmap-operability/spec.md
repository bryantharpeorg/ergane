---
state: landed
# Landed 2026-08-09 2:35 PM CT. Four stories, PRs #24-#26 and #28. us1, us2 and
# us4 first attempt; us3 attempt 2, its first landing rejected by a flaky
# concurrency test in tests/test_interpreter.py that its diff never touched
# (ci/flaky-concurrency-test-is-a-random-epic-killer). Worker restarted on the
# result at 2:46 PM, which is when the capacity fix became live.
#
# ATTESTATION CAVEAT: `factory-epic landed` reports US1, US2 and US3 only. US4 is
# fully in the tree at e4e90c3 but its merge subject is a salvage line, because
# PR #28 held exactly one commit and GitHub's squash rule used it -- see
# targets/salvage-only-pr-lands-invisible. Do NOT read the missing US4 as
# unlanded, and do not run a delta over this spec until that setting is fixed.
# Drafted 2026-08-09 from the roadmap's first real run, which failed 24 times in
# six hours and dispatched nothing. The scheduler landed in 009, was registered
# in the worker, passed a 1947-test suite, and had never completed a single pass
# in its existence.
#
# Numbered 021: 010–014 stay reserved for audit-triage epics, 015 doctor, 016
# delta, 017 peer channel, 018 agent home isolation, 019 operator CLI, 020
# landing attribution.
#
# Three defects and one blind spot, all in the same component, all found by
# running the thing rather than reading it. They are one spec because they share
# `factory/roadmap/workflow.py` and because each alone leaves the scheduler
# unfit for the unattended operation it exists to provide.
depends_on_landed: [007-parallel-dispatch, 009-roadmap-scheduler]
---

# Feature Specification: Roadmap Operability

**Feature Branch**: `021-roadmap-operability`

**Created**: 2026-08-09

**Status**: Drafted the morning the scheduler was switched on for the first
time. It ran every fifteen minutes for six hours, failed every time, told
nobody, and was discovered only because an operator asked "status?". Nothing in
this spec is a design disagreement with 009 — the architecture held. What failed
is everything 009 could not test, plus two capabilities it never expressed.

**Input**: Four items, in the order they cost something.

**The capacity read has never worked.** `_list_open_epics` asks Temporal for
`ExecutionStatus = "RUNNING"`. The visibility grammar requires `"Running"`.
Every pass calls `count_open_epics` before dispatching, so every pass dies:
`invalid query: invalid expression: invalid ExecutionStatus value 'RUNNING'`.
Verified live 2026-08-09 — the uppercase spelling raises `RPCError`, the
title-case one returns cleanly.

**And it could not have been caught.** The source says so three lines above the
defect: *"the time-skipping test server does not answer it, which is exactly why
the seam below lets a test script the count instead."* `_open_epics_provider`
exists so tests can hand back a scripted set. The one line in the component that
speaks to real Temporal visibility therefore had **zero coverage by
construction**. A green suite is not evidence about code no test can reach, and
the seam that made the workflow testable is the same seam that made this
untestable. That is the finding worth more than the typo.

**Nothing reported the failures.** Twenty-four failed workflow executions over
six hours produced no Telegram message, no ledger row, no finding. The operator
channel carries an agent's questions and escalations — things that happen
*inside* a dispatch. A scheduler that dies *before* dispatching is outside every
notification path the factory has.

**Two capabilities the scheduler cannot express.** It has no way to set its
children's node concurrency, so a spec with a declared fan-out runs serially
under it — 019 is exactly that spec, and 007's parallel dispatch would go
unused. And it drains and exits rather than idling, so "flip a spec to `ready`
and walk away" does not work: the flip is only seen by a pass, and passes only
happen while something is already running.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The capacity read works, and is proved against a real server (Priority: P1)

As the factory operator, the roadmap completes a scheduling pass against the
Temporal I actually run, and the query that talks to it is covered by a test
that would have failed on the day it was written.

The one-word fix is not the story. The story is that a seam introduced to make
a workflow testable left its production side unreachable by every test, and the
component shipped anyway. Whatever replaces the query must be exercised against
a real server, in the live tier the repository already has
(`tests/test_live_judge.py` is the precedent — it skips without credentials and
runs when they are present).

**Why this priority**: nothing else in this spec matters while every pass dies
at the first activity.

**Independent Test**: against a running Temporal, the capacity read returns the
set of open `epic-*` workflow ids without raising; a scripted seam still serves
the time-skipping tests; and the live test fails if the query string is reverted
to the uppercase spelling.

**Acceptance Scenarios**:

1. **Given** a running Temporal namespace, **When** the capacity read executes,
   **Then** it returns the open `epic-*` ids and raises nothing — asserted
   against a real server, not a scripted seam.
2. **Given** the query reverted to `ExecutionStatus = "RUNNING"`, **When** the
   live test runs, **Then** it fails. A test that passes under both spellings
   has not covered the defect.
3. **Given** no credentials or no reachable Temporal, **When** the suite runs,
   **Then** the live case skips with a named reason and the rest of the suite is
   unaffected — the live tier must not make the offline suite red.
4. **Given** the time-skipping test server, **When** the workflow tests run,
   **Then** they still script the capacity count through the seam — this story
   keeps the seam and adds coverage on the other side of it, rather than
   removing the seam.
5. **Given** a completed or continued-as-new epic workflow, **When** capacity is
   read, **Then** it is not counted as open.

---

### User Story 2 - The scheduler can express node concurrency (Priority: P1)

As the factory operator, a spec whose work graph declares a fan-out runs that
fan-out when the roadmap dispatches it, so that scheduled epics get the
parallelism hand-started ones already have.

`RoadmapInput` carries `max_concurrent_epics` and nothing for nodes;
`_dispatch` builds its child's `EpicInput` without one, so every scheduled epic
takes the default of 1. 007 built node concurrency and proved it five-for-five;
the scheduler simply has no vocabulary for it.

**Why this priority**: 019 is queued behind this with a declared
`US1 → (US2 ‖ US3 ‖ US4) → US5` diamond. Dispatched by the roadmap today, it
would run five nodes in a row and the fan-out would be decoration.

**Independent Test**: a scripted roadmap dispatches a child whose `EpicInput`
carries the bound the roadmap was given; absent a value, today's default is
preserved exactly.

**Acceptance Scenarios**:

1. **Given** a roadmap started with a node bound of 3, **When** it dispatches a
   child epic, **Then** that child's input carries 3.
2. **Given** a roadmap started without a node bound, **When** it dispatches,
   **Then** the child carries today's default of 1 — this story adds an
   expression, it does not change what an unconfigured roadmap does.
3. **Given** a non-positive or non-integer bound, **When** the roadmap starts,
   **Then** it refuses immediately with the value named, the way
   `max_concurrent_epics` already does.
4. **Given** the bound, **When** it is reported, **Then** `roadmap_status` names
   it alongside the epic bound — a knob the operator cannot read is a knob they
   will set twice.

---

### User Story 3 - The roadmap idles instead of exiting (Priority: P1)

As the factory operator, I flip a spec to `ready` and walk away, and the
scheduler picks it up without me starting anything, so that "unattended" means
what it says.

Today the loop returns when nothing is dispatchable and nothing is in flight.
That is drain-and-exit, and it is why the schedule that wraps it starts a fresh
run every fifteen minutes — paying a full corpus read, a spec-text read per
spec, and a git-shelling drift call per landed spec, every tick, forever, on a
corpus that is usually unchanged.

The wake signal must be a signal first and a timer second. A `rescan` signal
costs nothing while idle and reacts immediately; a long timer catches a
frontmatter edit made in an editor. Continue-as-new on each idle wake keeps
history flat, and idle is the safest boundary that exists — zero children are
open, so no completion event can be lost across it.

**Why this priority**: it is the behaviour the operator asked for, and without
it the schedule is a workaround that re-reads the world on a timer — the exact
polling 009's FR-004 refused.

**Independent Test**: under time skipping, an idle roadmap does not return; a
`rescan` signal wakes it and it dispatches a spec readied since the last pass; a
run with no idle configuration returns exactly as it does today; history stays
bounded across many idle wakes.

**Acceptance Scenarios**:

1. **Given** an idle roadmap with idle-wait configured, **When** nothing is
   dispatchable, **Then** it waits rather than returning, and consumes no
   activity while waiting.
2. **Given** an idle roadmap, **When** a `rescan` signal arrives, **Then** it
   re-reads the corpus in the same pass and dispatches anything newly ready.
3. **Given** an idle roadmap and no signal, **When** the idle interval elapses,
   **Then** it re-reads the corpus once — the timer is the safety net for an
   edit made outside the CLI, not the primary path.
4. **Given** many consecutive idle wakes, **When** history is measured, **Then**
   no run's event count grows with the number of wakes.
5. **Given** no idle configuration, **When** nothing is dispatchable, **Then**
   the roadmap returns exactly as it does today — drain-and-exit stays the
   default, so nothing that runs it today changes behaviour underneath.
6. **Given** an idle wake, **When** continue-as-new fires, **Then** zero
   children are open at that moment.

---

### User Story 4 - A scheduler that dies says so (Priority: P2)

As the factory operator, a roadmap run that fails reaches me the way an agent's
question does, so that a broken scheduler costs one message rather than six
hours of silence.

Twenty-four consecutive failures produced nothing. The operator channel is
built for events inside a dispatch; a workflow that fails before dispatching has
no path to a phone. Repetition is the signal that matters — one failed run may
be a restart, twenty-four is a defect — so the report must carry the count and
must not send twenty-four messages.

**Why this priority**: real, and the reason this spec exists at all, but the
factory is operable once US1–US3 land. This is what makes the *next* silent
failure loud.

**Independent Test**: a scripted roadmap failure produces one operator
notification carrying the failure and its consecutive count; N further identical
failures do not produce N further messages; a successful pass resets the count.

**Acceptance Scenarios**:

1. **Given** a roadmap run that fails, **When** it terminates, **Then** the
   operator is notified once with the failure message verbatim.
2. **Given** repeated identical failures, **When** they accumulate, **Then** the
   operator is not notified once per failure; the notification carries the
   consecutive count instead.
3. **Given** a successful pass after failures, **When** it completes, **Then**
   the count resets and the recovery is reported.
4. **Given** the notifier being down, **When** a roadmap failure occurs,
   **Then** the failure is still recorded durably — a notification path that
   loses the event when it cannot deliver is the blind spot again, one layer
   further in.

### Edge Cases

- A visibility query that is *accepted* but returns the wrong set — a namespace
  with no `epic-*` workflows looks identical to a broken filter. The live test
  must assert against known-open ids, not merely that no exception was raised.
- An idle roadmap that receives `pause_roadmap`: pause must win, and `rescan`
  while paused must not dispatch.
- A `rescan` signal arriving while a child is in flight: it is not an error, it
  is a no-op for dispatch and the normal completion path still applies.
- The node bound interacting with the epic bound: `max_concurrent_epics` × node
  bound is the real agent count. Both must be reportable, because the product is
  what consumes the host.
- A roadmap failing during continue-as-new rather than during a pass: the
  notification path must not assume the failure happened inside the loop.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The capacity read MUST use a visibility query the running Temporal
  accepts, and MUST return the open `epic-*` workflow ids. A completed or
  continued-as-new execution MUST NOT count as open.
- **FR-002**: The production capacity read MUST be covered by a test that
  executes it against a **real** Temporal, in the repository's existing live
  tier, skipping with a named reason when no server is reachable. The test MUST
  fail if the query is reverted to the spelling that shipped.
- **FR-003**: The scripted seam MUST remain for the time-skipping workflow
  tests. This spec adds coverage on the production side of the seam; it MUST NOT
  remove the seam, because the seam is what makes the workflow testable at all.
- **FR-004**: `RoadmapInput` MUST carry a node-concurrency bound and `_dispatch`
  MUST pass it to every child `EpicInput`. Absent a value, the child MUST
  receive today's default of 1.
- **FR-005**: A non-positive or non-integer node bound MUST be refused at
  roadmap start with the value named, matching `max_concurrent_epics`'s existing
  validation. `roadmap_status` MUST report both bounds.
- **FR-006**: The roadmap MUST support an optional idle mode: when nothing is
  dispatchable and nothing is in flight, it waits instead of returning. Absent
  configuration, it MUST return exactly as it does today.
- **FR-007**: A `rescan` signal MUST wake an idle roadmap and cause a corpus
  re-read in the same pass. An idle timeout MUST do the same as a safety net.
  While idle and unsignalled, the roadmap MUST execute no activity.
- **FR-008**: Continue-as-new MUST fire on an idle wake with zero children open,
  and no run's history event count MUST grow with the number of idle wakes.
- **FR-009**: A roadmap run that fails MUST reach the operator through the
  existing notification surface, carrying the failure verbatim and the count of
  consecutive failures, without emitting one message per failure. A successful
  pass MUST reset the count and report recovery.
- **FR-010**: A roadmap failure MUST be recorded durably regardless of whether
  the notification was delivered.

### Key Entities

- **Scheduling pass** — one iteration of the roadmap loop: corpus read,
  readiness computation, capacity read, dispatch. The unit that has never
  completed.
- **Capacity read** — the count of open `epic-*` workflows, roadmap-started and
  operator-started alike. The activity that fails today.
- **Idle wake** — the roadmap resuming from an idle wait, by signal or by
  timeout. The safest continue-as-new boundary, because no child is open.
- **Consecutive failure count** — how many roadmap runs have failed since the
  last success. The number that turns a restart into a defect.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The roadmap completes a scheduling pass against the operator's own
  Temporal and dispatches a dispatchable spec — the thing it has never done.
- **SC-002**: Reverting the capacity query to its shipped spelling turns the
  suite red. Today it stays green.
- **SC-003**: A roadmap given a node bound of 3 dispatches 019's diamond as
  `US1 → (US2 ‖ US3 ‖ US4) → US5` with three agents concurrent, not five in
  sequence.
- **SC-004**: A spec flipped to `ready` while the roadmap is idle is dispatched
  without any command being run.
- **SC-005**: An idle roadmap left overnight executes no activity while idle and
  its history does not grow.
- **SC-006**: A roadmap failure reaches the operator's phone within one pass,
  and twenty-four consecutive failures produce one notification carrying the
  count, not twenty-four notifications.

## Work Graph

A chain, and this one is honest rather than habitual. US2, US3 and US4 all add
to `RoadmapInput` or to the run loop in `factory/roadmap/workflow.py` — a single
module, with no registry trick available to split it the way 019's nouns were
split. Three concurrent worktrees on one file is the collision 009's own first
run demonstrated, so they go in sequence.

US1 leads because nothing downstream is observable while every pass dies at the
first activity: US2's dispatch never happens, US3's idle state is never reached,
and US4 would report a failure the operator already knows about.

Every edge is a **merge** edge, for the usual reason — a pass edge would let a
node build against a base without its predecessor's field.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-006, FR-007, FR-008]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-009, FR-010]
```

## Assumptions

- **009's architecture is not in question.** Child workflows, completion-event
  waking, continue-as-new at quiescence, and the parked-finding discipline all
  held. This spec fixes one string, adds two inputs, and closes a reporting gap.
- **The live test tier exists and is the right home for FR-002.**
  `tests/test_live_judge.py` already skips without credentials and runs with
  them. FR-002 joins that tier rather than inventing a second convention. Note
  that the tier is currently failing for an unrelated reason (the proxy writes
  no `SpendLogs` rows), which is a defect in its own right and must not be
  confused with this spec's tests failing.
- **Idle mode stays opt-in.** Drain-and-exit remains the default so nothing that
  runs the roadmap today changes behaviour underneath it. The operator turns
  idling on deliberately.
- **The Temporal Schedule is a workaround this spec retires.** Once US3 lands, a
  15-minute schedule re-reading the corpus is strictly worse than one idle
  workflow waiting on a signal. Delete the schedule rather than leaving two
  mechanisms racing to dispatch the same spec.
- **`stall_after_s` is not this spec's business**, though it is the next thing to
  look at before any unattended concurrent run: a merge-queue ejection stays
  invisible to the landing poller for 7200s, and US2 makes concurrent landings
  more likely.

## Decision: the seam that made it testable is the seam that hid it (recorded 2026-08-09)

The defect is one word. The lesson is not, and it is the reason these four
stories are one spec:

1. **A seam introduced for testability creates an untested surface on its far
   side, and that surface needs its own coverage.** `_open_epics_provider` was
   correct — the time-skipping server genuinely cannot answer the production
   query. What was missing is the other half: a test on the real thing. Any
   future seam of this shape owes the same debt.
2. **A green suite is evidence about covered code only.** 1947 tests passed
   while the scheduler could not complete one pass. This is CLAUDE.md's "verify
   what the factory believes, not what it reports", and it now has a price tag.
3. **Unattended requires reporting.** A component that runs without an operator
   watching must be able to say it is broken; otherwise "unattended" means
   "unobserved", and the two are only the same while nothing goes wrong.

**The decision-log number is deliberately unassigned here** — claimed at landing
time in `docs/decisions.md`, after whatever 019 and 020 consume.
