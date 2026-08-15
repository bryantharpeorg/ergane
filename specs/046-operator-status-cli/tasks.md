# Tasks: 046-operator-status-cli

Three stories: US2 lands first (US1 merges behind it and consumes its
discovery helper); US3 is independent. Work test-first and commit once per
task. Read plan.md before the first commit — trap 1 (the resolver mkdirs) and
trap 2 (pausing the run is a lie) are the two that turn a green suite into a
wrong verb.

## Phase 1: User Story 2 — The roadmap verbs can see schedule-driven runs

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US2] Write the schedule-discovery case FIRST: with only
      timestamped runs (`roadmap-<root>-<ts>`) and an owning schedule present,
      `roadmap status <root>` reports the newest run and names run id and
      schedule (spec US2-S1, SC-002) — must fail with today's
      `no roadmap '<root>' is running here`.
- [ ] T002 [P] [US2] Write the pause case FIRST: `pause` leaves the schedule
      paused, proven by reading the schedule back, never by the verb's own
      report (spec US2-S2, plan trap 2) — must fail.
- [ ] T003 [P] [US2] Write the resume case FIRST: symmetric unpause, read
      back (spec US2-S3) — must fail.
- [ ] T004 [P] [US2] Write the bare-workflow parity case FIRST: with a
      `roadmap start` workflow and no schedule, all three verbs behave
      byte-identically to today (spec US2-S4) — must pass before and after;
      it pins the parity.
- [ ] T005 [P] [US2] Write the nothing-found case FIRST: the refusal names
      the bare id, the schedule lookup and the run prefix, in the order tried
      (spec US2-S5, FR-007) — must fail.
- [ ] T006 [US2] Write the control: with the discovery seam disabled, the
      schedule-driven floor reproduces the historical refusal verbatim
      (SC-004) — the test that proves the fix changed an outcome.

### Implementation for this story

- [ ] T007 [US2] The resolution helper: bare workflow → owning schedule
      (matched by action-workflow prefix from `roadmap_workflow_id`,
      `factory/roadmap/workflow.py:162` — never a hardcoded schedule id, plan
      trap 3) → newest timestamped run. Returns what it found and how.
- [ ] T008 [US2] Route `status`/`pause`/`resume`
      (`factory/cli/roadmap.py:163-218`) through it: schedule-owned roadmaps
      pause and resume at the schedule; bare workflows exactly as today.

## Phase 2: User Story 1 — `ergane status` answers the morning question in one screen

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US1] Write the five-section case FIRST against a seeded floor —
      running epic with mixed story states, a ready spec blocked on it, a
      draft: disposition, story table, queue with named blockers, drafts,
      pace, in that order (spec US1-S1, SC-001) — must fail.
- [ ] T010 [P] [US1] Write the schedule-disposition case FIRST: a
      schedule-driven floor renders the schedule, its state and newest run
      through US2's helper (spec US1-S2) — must fail.
- [ ] T011 [P] [US1] Write the pace case FIRST: attempt wall-times from
      `verification_results.started_at`/`finished_at` plus remaining-story
      count, and assert the output contains **no** projected completion time
      (spec US1-S3, FR-003, plan trap 5) — must fail.
- [ ] T012 [P] [US1] Write the degraded case FIRST against a closed port
      (`TEMPORAL_ADDRESS=127.0.0.1:1`, the 043-US3 precedent): spec sections
      render, one note names the address, exit code distinguishes degraded
      from clean (spec US1-S4, FR-004, plan trap 6) — must fail.
- [ ] T013 [P] [US1] Write the `--json` case FIRST: one document, every
      section (spec US1-S5, FR-005) — must fail.
- [ ] T014 [P] [US1] Write the read-only case FIRST: run on a checkout with
      no runtime root, then assert nothing was created — the resolver's
      mkdir at `factory/workgraph/worktree.py:180` must not fire (spec
      US1-S6, SC-003, plan trap 1; `monkeypatch.chdir` into tmp, 043's
      discipline) — must fail.

### Implementation for this story

- [ ] T015 [US1] The new top-level `status` noun: running epics via
      `list_workflows` (`factory/activities/roadmap_activities.py:448`
      precedent) joined with the existing per-epic status query; queue and
      drafts via the existing roadmap reader
      (`factory/roadmap/models.py:26`, rendering precedent
      `factory/roadmap/cli.py:47-122` — FR-008, plan trap 4: reuse, never
      re-implement readiness); pace from the store's result columns
      (`factory/verify/store.py:245`, `:275`).
- [ ] T016 [US1] Degraded mode and read-only wiring per traps 6 and 1;
      `--json` renders the same document the human view formats.

## Phase 3: User Story 3 — The build verbs accept the id the operator actually has

### Tests for this story (write FIRST, must fail)

- [ ] T017 [US3] Write the both-forms case FIRST, parametrized across every
      build verb that calls the prefix seam: spec-dir form and
      `epic-`-prefixed form resolve to the same workflow id (spec US3-S1) —
      must fail.
- [ ] T018 [P] [US3] Write the not-found parity case FIRST: an id matching
      neither form fails with today's error naming the dialed id (spec
      US3-S2) — must pass before and after.
- [ ] T019 [P] [US3] Write the collision case FIRST: when an exact
      `epic-`-named id misses, the error names both candidates tried (spec
      US3-S3) — must fail.

### Implementation for this story

- [ ] T020 [US3] Normalize in `workflow_id()`
      (`factory/cli/nouns/build.py:91-93`) and nowhere else (plan trap 7).

## Verification

- [ ] Final gate command passes green.
- [ ] `ergane roadmap status specs` — the exact 2026-08-15 failing invocation
      — reports the schedule's newest run on a live floor.
- [ ] `ergane status` from a scratch checkout creates nothing on disk.
- [ ] No projected completion time appears anywhere in `ergane status` output.
