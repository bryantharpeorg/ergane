# Tasks: a verdict is a fact about the code

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Three stories, serial on merge edges. US1 fixes the test that fired and lands the
delay knob; US2 promotes the wait into a shared helper and converts the rest;
US3 guards the pattern.

Read `evidence/055-us1-attempt1-gate.txt` before anything else. It is the actual
gate output of the run this spec exists for, and the source was already misread
once in the direction that not reading it produces.

## Format: `[ID] [P?] [Story] Description`

`[P]` marks tasks that may run in parallel with their siblings.

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm `bwrap` is on the worker host, so the boundary
      suites run rather than skip (`tests/test_us4_boundary.py:209`). Record the
      baseline `passed` and `skipped` counts from a clean `uv run pytest -q` —
      3567 / 47 at drafting — and confirm the floor is otherwise quiet, because
      a story about contention should not be measured under it.

---

## Phase 2: User Story 1 — The boundary test measures the boundary, not the host (Priority: P1) 🎯 MVP

**Goal**: the affected test stops depending on how quickly the host scheduled a
subprocess, and still fails on a real boundary defect.

**Independent Test**: with handler installation delayed past the deadline, the
pre-fix test fails and the fixed test passes — at concurrency 1, idle host,
deterministic.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`.
      Quote `passed` and `skipped`, never the warning count. Confirm
      `test_hanging_agent_is_killed_at_deadline_with_no_survivors` **ran** —
      a skip here makes every later measurement meaningless.
- [ ] T003 [US1] (FR-002) Add the stub delay knob: a control value that makes
      `tests/stub_agent.py` wait a configurable interval before installing its
      SIGTERM handler at `:414`. Model it on `ignore_sigterm` (`:411`), which is
      the knob mechanism that already exists. Nothing under `factory/` may read
      it (FR-008).
- [ ] T004 [US1] (spec US1-S2, FR-002, SC-002) **Reproduce before fixing.** With
      the knob set beyond the attempt's deadline, run the *unmodified* test and
      confirm it fails with the committed signature — `SIGTERM not delivered;
      signals=[]` at `tests/test_us4_boundary.py:236`. Capture that run verbatim
      to `evidence/pre-fix-under-knob.txt` with the command and the knob value,
      and commit it. If it does **not** reproduce, stop and report blocked —
      the mechanism is not what the plan says and a fix you cannot demonstrate
      was needed is not this story (constitution II).
- [ ] T005 [US1] (plan § two candidate mechanisms) Discriminate: with the knob at
      zero, raise `grace_s` alone and re-run. Record which mechanism reproduces
      and which does not, in the PR body. If both are real, both are fixed and
      T006 says so.
- [ ] T006 [P] [US1] (spec US1-S1, US1-S5, FR-001, FR-004) Write the fixed test's
      synchronisation cases FIRST: the launch waits on an observable readiness
      condition with a bounded deadline before the attempt's clock is allowed to
      matter; the wait reports the condition and the elapsed time when it
      expires; with the knob at its maximum the test reports no boundary defect
      — must fail.
- [ ] T007 [P] [US1] (spec US1-S3, SC-003) Write the still-sensitive case FIRST:
      with the boundary genuinely broken — a leaked namespaced child, or a
      deadline that does not terminate the agent — the fixed test goes **red**.
      Prove it by mutation on a scratch branch, not by argument, and quote the
      failure in the PR body. A test that cannot fail is worse than the flake it
      replaced.

### Implementation for User Story 1

- [ ] T008 [US1] (spec US1-S4, FR-001, FR-003, FR-004) Fix the synchronisation in
      `tests/test_us4_boundary.py:202` until T006 and T007 pass. Do **not**
      delete, weaken, retry or mark any assertion: the termination
      classification at `:229`, the SIGTERM check at `:236`, and the two
      survivor checks at `:245-251` all survive. The reap sleep at `:241` is not
      the defect and is US2's to convert (plan trap 1).
- [ ] T009 [US1] (FR-009, SC-005) Run `uv run pytest -q` and confirm passed and
      skipped match T002's baseline. A new skip is a hidden test — declare it or
      remove it.

---

## Phase 3: User Story 2 — Every test that launches the stub waits for it the same way (Priority: P1)

**Goal**: the readiness wait is one shared helper, used by every launch in the
boundary suites whose deadline could race it.

**Independent Test**: the count of racing launches not using the helper is zero,
established by a test; the suites stay green.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] (spec US2-S2, FR-004) Write the helper's own cases FIRST: it
      returns when the condition becomes true; it raises at its bounded deadline
      when the condition never does; the failure names the file it waited on and
      how long it waited. Test the helper directly — a helper proven only
      through the tests that use it is a helper whose failure path is untested —
      must fail.
- [ ] T011 [P] [US2] (spec US2-S1, FR-005, FR-006, SC-004) Write the call-site
      census FIRST: a test that counts stub launches in `test_us4_boundary.py`
      and `test_us3_boundary.py` whose deadline could race readiness and asserts
      that every one goes through the shared helper. Count mechanically; a
      census by reading is not a census — must fail.

### Implementation for User Story 2

- [ ] T012 [US2] (FR-005) Extract US1's readiness wait into the tests' shared
      support module as one helper, and convert every racing launch the census
      names — including the reap window at `tests/test_us4_boundary.py:241`,
      which is a fixed sleep gating an assertion about host process state even
      though it is not what fired.
- [ ] T013 [US2] (spec US2-S3, FR-009, SC-005) Run `uv run pytest -q`, confirm the baseline
      holds, and confirm the boundary suites' wall-clock has not grown beyond
      the gate's budget. If it has, the readiness deadline is too generous —
      tighten the bound, never the assertions.

---

## Phase 4: User Story 3 — The pattern cannot come back (Priority: P2)

**Goal**: a mechanical guard refuses a new fixed sleep used to wait for another
process's state in the boundary suites.

**Independent Test**: the guard passes on the converted tree and fails when the
pattern is reintroduced.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T014 [US3] (spec US3-S1, US3-S2, FR-007) Write the guard's cases FIRST:
      it passes on the fixed tree; it fails naming file and line when a fixed
      sleep is reintroduced ahead of an assertion about another process's state
      — must fail.
- [ ] T015 [P] [US3] (spec US3-S3, FR-007) Write the false-positive case FIRST:
      a fixed sleep that only yields the event loop and gates no such assertion
      passes the guard. There are 37 such call sites across 15 files and most
      are legitimate; a guard that bans the construct outright gets deleted by
      the next person who needs one — must fail.
- [ ] T016 [P] [US3] (FR-008) Write the boundary case FIRST: no module under
      `factory/` imports, detects, or branches on the stub's delay knob — must
      fail.

### Implementation for User Story 3

- [ ] T017 [US3] (FR-007, FR-008) Implement the guard in
      `tests/test_final_sweep.py`'s existing D-021 vocabulary — extended, not
      forked — until T014, T015 and T016 pass.
- [ ] T018 [US3] (SC-001, SC-005) Run `uv run pytest -q`, confirm the baseline,
      and re-run the affected test with the delay knob at its maximum to confirm
      SC-001: no assertion in it can fail from scheduling delay alone.

---

## Phase 5: Verification (operator, by hand — dispatched to no node)

- [ ] T019 Operator: dispatch the next epic at
      `ergane build start --max-concurrent-nodes 3` and confirm it completes
      with no gate failure attributable to a neighbour (SC-006). This is an
      observation over time, not something a node can prove from its diff, and
      it is the criterion the spec exists for.
- [ ] T020 Operator: resolve `ci/flaky-concurrency-test-is-a-random-epic-killer`
      in the findings ledger once T019 holds — and not before. The finding
      regressed once already after being treated as closed.

---

## Dependencies & Execution Order

- **Phase 1** is operator work and gates everything: a host without `bwrap`
  skips the test this spec is about.
- **Phase 2 (US1)** is the MVP — the fix, the knob, and the reproduction.
- **Phase 3 (US2)** merge-depends on US1: the helper it extracts is the one US1
  writes.
- **Phase 4 (US3)** merge-depends on US2: a guard written before the conversion
  fails on the tree it is meant to protect.
- **Phase 5** is the operator's acceptance and cannot run until all three land.

## Implementation Strategy

US1 alone stops the bleeding — the one test that has actually killed attempts
stops doing it, and cap 2 becomes as safe as cap 1. US2 is what makes that true
of the next boundary test rather than only this one. US3 is what keeps it true.

The spec's own payoff is not in the diff: it is that
`--max-concurrent-nodes 3` becomes a choice the operator can make without paying
a third of a story's ladder at random. Nothing here raises the dials; it only
makes raising them defensible.
