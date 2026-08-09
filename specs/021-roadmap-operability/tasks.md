# Tasks: Roadmap Operability

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

That rule is the whole point of this spec. The defect it repairs shipped under a
green suite because the only line that mattered had no test that could reach it.
A test here that cannot fail has not covered anything.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      will host the work, and settle the one open design call. Line numbers were
      taken 2026-08-09; 019 and 020 may move them.
      (a) `factory/activities/roadmap_activities.py` still holds the query at
      `:443-445`, the comment at `:440-442`, the seam at `:454`;
      (b) `RoadmapInput` still lacks a node bound and `_dispatch`'s `EpicInput`
      at `:870` still omits one;
      (c) the loop tail is still `break` at `:686`, and the post-child
      continue-as-new at `:656-657` is untouched by anything since;
      (d) `RoadmapCarryOver`'s field list, so US2 and US3 know what they are
      extending;
      (e) the name of 009's roadmap workflow test module, since T004 and T009
      must keep it green.
      **Decide and record here: US4's shape** — supervising surface, or
      try/except at the loop boundary (plan § US4). The supervising option
      covers a failure during continue-as-new; the cheap option does not. Write
      the choice and the reason into this task before deriving, because US4's
      tasks below are written to whichever is chosen.

---

## Phase 2: User Story 1 — The capacity read works, and is proved (Priority: P1) 🎯 MVP

**Goal**: a scheduling pass completes against a real Temporal, and the query is
covered by a test that would have caught this on day one.

**Independent Test**: the production read returns open `epic-*` ids against a
running server, excludes non-epic and closed workflows, and the test fails if
the query is reverted.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` runs;
      `factory/roadmap/workflow.py` and `factory/activities/roadmap_activities.py`
      exist. Note the live tier's **pre-existing** failures
      (`tests/test_live_judge.py`, ~19 errors, "no spend-log row appeared") and
      confirm they are unrelated before starting — trap 3. STOP and report
      blocked if anything else is red.
- [ ] T003 [US1] Write the **live** capacity test FIRST (FR-002), in the
      `tests/test_live_judge.py` tier's style — reads the environment, skips
      with a named reason when no Temporal answers. It must:
      start a throwaway workflow under an `epic-`-prefixed id and assert the
      production read finds it; start one under a non-`epic-` id and assert it
      is excluded; assert a closed or continued-as-new execution is not counted.
      **It must fail against the shipped query string.** Run it against
      `ExecutionStatus = "RUNNING"` and record that it fails before you change
      anything — a test that passes under both spellings has covered nothing
      (trap 2) — must fail.
- [ ] T004 [P] [US1] Write the seam-preservation case FIRST (FR-003): the
      time-skipping workflow tests still script the capacity count through
      `_open_epics_provider`, and 009's existing roadmap workflow tests stay
      green. This is a guard against "fixing" the defect by deleting the seam
      (trap 1) — must fail only if the seam is removed.

### Implementation for User Story 1

- [ ] T005 [US1] Fix the query until T003 passes. First check whether the SDK
      exposes a symbol whose string form the visibility grammar accepts; if it
      does, build the query from it and remove the class of defect rather than
      this instance. If it does not, use a module-level constant with the live
      test pinned to it, and say in a comment why a literal was unavoidable.
      Leave the `:440-442` comment in place but correct it: the production query
      is now covered, by T003, on the far side of the seam.

---

## Phase 3: User Story 2 — The scheduler can express node concurrency (Priority: P1)

**Goal**: `RoadmapInput` carries a node bound and every child epic receives it.

**Independent Test**: a scripted roadmap dispatches a child whose input carries
the bound; absent a value the child gets 1; a bad value is refused at start.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T006 [US2] Write dispatch cases FIRST under time skipping: a roadmap given
      a node bound of 3 starts its child with `max_concurrent_nodes=3`; a
      roadmap given none starts it with 1 — assert the child's `EpicInput`
      directly, because "the default happens to be 1 on both sides" would pass a
      weaker test while the value is never plumbed — must fail.
- [ ] T007 [P] [US2] Write validation and reporting cases FIRST: a zero,
      negative, non-integer, or **boolean** bound is refused at roadmap start
      with the value named (trap 5 — `isinstance(True, int)` is `True`, and the
      existing `max_concurrent_epics` check excludes `bool` for exactly this
      reason); `roadmap_status` reports both the epic bound and the node bound —
      must fail.
- [ ] T008 [P] [US2] Write the carry-over case FIRST (trap 4): a roadmap that
      continues-as-new preserves the node bound across the boundary. Without
      this, CAN silently reverts it to 1 after the first epic and the bug looks
      intermittent — must fail.

### Implementation for User Story 2

- [ ] T009 [US2] Add `max_concurrent_nodes` to `RoadmapInput` (default 1),
      validate beside `max_concurrent_epics`, pass it in `_dispatch`'s
      `EpicInput`, carry it through `RoadmapCarryOver`, and report it in
      `roadmap_status`, until T006, T007 and T008 pass. Use the name
      `max_concurrent_nodes` exactly — one concept, one word, and the D-021
      sweep bans the synonyms.

---

## Phase 4: User Story 3 — The roadmap idles instead of exiting (Priority: P1)

**Goal**: an idle roadmap waits on a signal (with a timer as safety net) instead
of returning, at no activity cost and with flat history.

**Independent Test**: an idle roadmap does not return; `rescan` wakes it and it
dispatches a newly-ready spec; unconfigured, it returns exactly as today;
history stays bounded across many wakes.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T010 [US3] Write idle-behaviour cases FIRST under time skipping: with idle
      configured and nothing dispatchable, the workflow does not complete; a
      `rescan` signal causes a corpus re-read and dispatches a spec readied
      since the last pass; the idle timeout does the same with no signal;
      **while idle and unsignalled, no activity executes** (assert the activity
      call count does not move — trap 6) — must fail.
- [ ] T011 [P] [US3] Write the no-regression case FIRST (FR-006, acceptance 5):
      with no idle configuration, a roadmap that finds nothing dispatchable
      returns exactly as it does today. Every current caller depends on this —
      must fail.
- [ ] T012 [P] [US3] Write durability cases FIRST: continue-as-new fires on each
      idle wake with **zero children open**; history event count does not grow
      with the number of idle wakes (the 006-US1 history-bound proof, applied to
      idling); idle config and the node bound both survive the boundary — must
      fail.
- [ ] T013 [P] [US3] Write the pause-precedence case FIRST: a paused roadmap
      that receives `rescan` dispatches nothing and stays parked until
      `resume_roadmap`; idle must not route around the existing pause wait —
      must fail.

### Implementation for User Story 3

- [ ] T014 [US3] Add `idle_rescan_s` to `RoadmapInput` (default `None`), the
      `rescan` signal, and the idle wait at the loop tail, until T010–T013 pass.
      `workflow.wait_condition(..., timeout=...)` only — never `asyncio.sleep`,
      never a re-read on a beat. Continue-as-new on **every** idle wake rather
      than counting: zero children are open there, so the boundary is trivially
      safe and history stays flat by construction. Do not disturb the
      post-child quiescence CAN.

---

## Phase 5: User Story 4 — A scheduler that dies says so (Priority: P2)

**Goal**: a failed roadmap run reaches the operator once, with its consecutive
count, and is recorded whether or not the send succeeds.

**Independent Test**: a scripted failure produces one notification carrying the
failure and the count; N further identical failures do not produce N messages; a
success resets and reports recovery; a down notifier still leaves the record.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T015 [US4] Write reporting cases FIRST, against the shape T001 chose: one
      failed run notifies once with the failure message verbatim; repeated
      identical failures do not notify per failure but carry a consecutive
      count; a success resets the count and reports recovery — must fail.
- [ ] T016 [P] [US4] Write the durability case FIRST (FR-010): with the notifier
      unavailable, the failure is still recorded. Write-before-send, the
      escalation precedent — a path that loses the event when it cannot deliver
      recreates this spec's own blind spot one layer in — must fail.

### Implementation for User Story 4

- [ ] T017 [US4] Implement the reporting path T001 chose until T015 and T016
      pass. Record durably **before** attempting the send. No credential value
      may reach a notification body.
- [ ] T018 [US4] Final sweep and docs: record the decision-log entry at the next
      free number (the seam-coverage lesson, spec § Decision), extend
      `docs/architecture.md`'s roadmap row with the node bound, idle mode and
      the failure path, and grep-assert that no credential reaches a roadmap
      signal payload, status document, or notification body.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything, including the one design call
  (US4's shape) that the tasks below are written against.
- Phase 2 (US1) is the MVP and must land first: while every pass dies at the
  first activity, none of the later stories is observable.
- Phases 3, 4 and 5 each chain on the previous **merged**. They all add to
  `RoadmapInput` or the run loop in one module, and unlike 019 there is no
  registry trick available to split it — three worktrees on one file is the
  collision 009's own first run demonstrated. This is a chain because the files
  say so, not out of habit.
- Dispatch this epic **by hand**, not through the roadmap (trap 7): US1's node
  edits the capacity read a scheduling parent would be calling between passes.

## Implementation Strategy

US1 alone is worth landing if anything must be cut — it is the difference
between a scheduler that has never worked and one that does. US2 unblocks 019's
declared fan-out, which is otherwise decoration. US3 is the always-on behaviour
and retires the Temporal Schedule standing in for it. US4 is what makes the next
silent failure loud, and it is the story whose absence turned a one-word defect
into six hours.

Nothing here changes the epic interpreter, an agent, or a probe. The roadmap
consumes `EpicWorkflow` through its public contract exactly as it does today;
this spec teaches the scheduler to complete a pass, to say how wide, to wait,
and to complain.
