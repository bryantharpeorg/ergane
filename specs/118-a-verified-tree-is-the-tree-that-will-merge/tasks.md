# Tasks: a verified tree is the tree that will merge

**Spec**: `specs/118-a-verified-tree-is-the-tree-that-will-merge/spec.md`
**Plan**: `specs/118-a-verified-tree-is-the-tree-that-will-merge/plan.md`

Read the plan's traps before the first task. **Trap 1 is the spec**: the existing
guard tests whether the pin is an *ancestor*, and a base three landings behind
passes that trivially — an implementer who reads the docstring as already
covering staleness will land nothing. Also trap 3 (the currency test never runs
between attempts, or you cause the failure R5 exists to prevent), trap 5 (take the
base from the prepared worktree, never re-derive it) and trap 7 (a standards
fetch may not fail a node).

## Phase 1: User Story 1 — A worktree too far behind is rebuilt at dispatch

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, trap 1) In
      `tests/test_118_stale_base_is_rebuilt.py`, record a pin that is an ancestor
      of the landing-branch head but behind it by more than the tolerance, and
      assert the worktree is rebuilt and the old branch archived.
- [ ] T002 [P] [US1] (spec US1-S2) **The reuse control.** Assert a pin within the
      tolerance is returned untouched — no fetch, no rebase, no reset.
- [ ] T003 [P] [US1] (spec US1-S3) **The validity control.** Assert a pin that is
      not an ancestor at all is rebuilt exactly as today.
- [ ] T004 [P] [US1] (spec US1-S4, trap 3) **The R5 proof.** Assert a second
      attempt of a prepared node opens the same tree untouched regardless of what
      the landing branch has done since.
- [ ] T005 [P] [US1] (spec US1-S5) Assert an explicit caller-supplied `base_ref`
      is honoured without a currency test.
- [ ] T006 [P] [US1] (FR-001, trap 4) Assert an adopted worktree — one whose
      record was swept — is not rebuilt by the currency test.

### Implementation for this story

- [ ] T007 [US1] (FR-001, trap 2) Add the tolerance to the configuration with a
      sane default, expressed in commits behind rather than in wall-clock time.
- [ ] T008 [US1] (FR-001, FR-002, trap 1) Add the currency test in
      `prepare_worktree` (`factory/workgraph/worktree.py:365-369`) between the
      validity test and its diverged arm, reusing the existing `_archive_node`
      rebuild path rather than adding a second one.
- [ ] T009 [US1] (FR-004, trap 3) Confirm the test runs only on the preparation
      path and cannot fire for a retry of a prepared node.
- [ ] T010 [US1] (FR-005, trap 4) Leave the explicit-pin and adopt arms alone,
      and say in a comment why each was left — a future reader will ask.

## Phase 2: User Story 2 — The record says what the verdict was measured against

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1, trap 5) In
      `tests/test_118_record_names_its_base.py`, assert a verified attempt's row
      carries the base the worktree was pinned to, taken from the prepared
      worktree rather than re-derived.
- [ ] T012 [P] [US2] (spec US2-S2) Assert the status view shows that base beside
      the landing branch's current head.
- [ ] T013 [P] [US2] (spec US2-S3) Assert rows predating this change read as
      unknown rather than as a wrong value.

### Implementation for this story

- [ ] T014 [US2] (FR-006, trap 5) Carry `PreparedWorktree.base_ref` onto the
      verification row.
- [ ] T015 [US2] (FR-006) Give old rows an unknown representation, deciding it
      once.
- [ ] T016 [US2] (FR-007) Render the base beside the landing head in the status
      view, on one line.

## Phase 3: User Story 3 — An attempt reads the standards on the landing branch

### Tests for this story (write FIRST, must fail)

- [ ] T017 [P] [US3] (spec US3-S1) In `tests/test_118_standards_per_attempt.py`,
      update a standards document on the landing branch after a node was
      dispatched and assert the next attempt's standards text is the updated one.
- [ ] T018 [P] [US3] (spec US3-S2, trap 7) Assert an unreadable landing branch
      falls back to the pinned tree's copy, reports the fallback, and does not
      fail the attempt.
- [ ] T019 [P] [US3] (spec US3-S3, trap 8) Assert the archived prompt records
      which source the standards came from.
- [ ] T020 [P] [US3] (spec US3-S4) **The control.** Assert a repository declaring
      no standards path behaves exactly as today.
- [ ] T021 [P] [US3] (FR-008, trap 6) Assert the prompt builder remains pure —
      it still takes a path and reads no repository.

### Implementation for this story

- [ ] T022 [US3] (FR-008, trap 6) Resolve the standards text from the landing
      branch in the caller that already reads the repository, leaving
      `factory/workgraph/prompt.py`'s builder unaware and pure.
- [ ] T023 [US3] (FR-008, trap 7) Fall back to the pinned copy on any read
      failure and report it.
- [ ] T024 [US3] (FR-009, FR-010) Record the source on the archived prompt, and
      confirm the two things FR-010 names are unchanged by this epic. Say so in
      the attempt report without restating their paths, because a task that names
      a file joins that file to its story's slice.

### The operator's demonstration for this story

- [ ] T025 [US3] Run the live-floor demonstration in the plan's § *Verification
      the operator will run* and paste the status line showing the node's base
      beside the landing branch head into the attempt report. That single line is
      the diagnosis the finding says would have made a stale-base PASS visible in
      seconds, and no gate can produce it because it requires a landing branch
      that moves under a running node.
