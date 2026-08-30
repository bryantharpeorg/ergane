# Tasks: the last two fixtures that choose for the operator

**Spec**: `specs/123-the-last-two-fixtures-that-choose-for-the-operator/spec.md`
**Plan**: `specs/123-the-last-two-fixtures-that-choose-for-the-operator/plan.md`

Read the plan's traps first. Trap 1 (naming another real persona moves the pin rather than
removing it), trap 2 (`PERSONA` is one module-level constant — editing fifteen tests
produces a diff this repo refuses unjudged), trap 3 (US1-S4 ends the class and will look
like over-engineering) and trap 4 (the store test must pass with a real ledger present
*and* absent) decide whether this lands.

Two stories, two files, no merge edges. They dispatch together.

## Phase 1: User Story 1 — The poll-usage fixtures own their persona

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_123_no_fixture_pins_the_builder.py`,
      assert the poll-usage tests pass with the implementer on the subscription route.
      Fifteen fail today.
- [ ] T002 [P] [US1] (spec US1-S2) **The control.** Assert they pass unchanged with a
      gateway-routed implementer.
- [ ] T003 [P] [US1] (spec US1-S3, trap 1) Assert the persona those fixtures lease against
      is one the tests own, not a name read from the shipped registry.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, trap 3) **The check that ends the class.**
      Assert no fixture anywhere in the suite leases a virtual key against a persona name
      read from the registry. Seven occurrences have each been fixed by deleting one
      literal; this is what makes an eighth fail here.

### Implementation for this story

- [ ] T005 [US1] (FR-001, traps 1 and 2) Change `PERSONA` (`tests/test_poll_usage.py:59`)
      to a fixture-owned name in the register of the `MODELS` constant beside it. **One
      constant.** Read 122/US2's landed diff to `tests/test_usage_activities.py:74` first —
      this is the same edit in a file that spec did not look at.

## Phase 2: User Story 2 — A spec-declaration test builds its own store

### Tests for this story (write FIRST, must fail)

- [ ] T006 [P] [US2] (spec US2-S1, trap 4) Assert
      `test_validate_reports_the_same_result_with_and_without_fixes` passes on a host with
      a populated `.factory/doctor.db`. It fails there today with `assert 'fixes' in []`.
- [ ] T007 [P] [US2] (spec US2-S2, trap 4) **The other direction.** Assert it passes where
      no findings store exists.
- [ ] T008 [P] [US2] (spec US2-S3, FR-004) Assert the test resolves its store under its own
      temporary directory and never under the operator's runtime root.
- [ ] T009 [P] [US2] (spec US2-S4, FR-005, trap 5) **The control.** Assert the fixes layer
      still reports `not checked` for an absent store rather than refusing.

### Implementation for this story

- [ ] T010 [US2] (FR-004, trap 4) Point the test at a findings store built under
      `tmp_path`, seeded with whatever keys its fixture spec declares.

### The operator's demonstration

- [ ] T011 [US2] Run the sequence in the plan's § *Verification the operator will run*,
      which swaps the implementer to the subscription route, runs the **whole suite**, and
      restores `personas.yaml`. Paste the run into
      `specs/123-the-last-two-fixtures-that-choose-for-the-operator/attempt-report-<story>.md`.
      Run the whole suite, not a subset: scoping spec 122 from four predicted files is
      precisely how this spec came to exist.
