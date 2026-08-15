# Tasks: 045-judge-diff-hygiene

Three stories, chained: US1 → US2 → US3. Work test-first and commit once per
task. Read plan.md before the first commit — trap 1 (`check-ignore` lies about
tracked files) and trap 5 (old rows must deserialize) are the two that cost a
rejected attempt each if met late.

## Phase 1: User Story 1 — A diff carrying ignore-pattern or runtime-root paths fails before the judge

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the homes replay FIRST: a fixture worktree whose
      commits include files under `.ergane/homes/`; the output check fails
      naming each path and the verification result records no judge verdict
      (spec US1-S1, SC-001) — must fail.
- [ ] T002 [P] [US1] Write the tracked-ignored case FIRST: a fixture that
      *commits* a file matching the target's own `.gitignore`, then asserts the
      check fails naming path and pattern — the fixture must make the file
      tracked, because that is the case plain `check-ignore` reports clean
      (spec US1-S2, plan trap 1) — must fail.
- [ ] T003 [P] [US1] Write the parity case: a clean worktree's output check is
      byte-identical to today's (spec US1-S3, plan trap 6) — must fail only if
      parity breaks.
- [ ] T004 [P] [US1] Write the untracked-ignored case: build noise neither fails
      hygiene nor counts as diff, exactly as today (spec US1-S4, plan trap 2) —
      must pass before and after; it pins the exemption.
- [ ] T005 [P] [US1] Write the read-scope case: an artifact-proof node with no
      git repository is untouched by hygiene (spec US1-S5, FR-008, plan
      trap 3) — must fail if hygiene raises there.
- [ ] T006 [P] [US1] Write the unreadable case: ignore rules git cannot answer
      surface as `WorktreeMissingError`, never as a pass (FR-006) — must fail.

### Implementation for this story

- [ ] T007 [US1] Collect the changed-path list in
      `factory/verify/diffcheck.py` — the porcelain read at `:167` plus
      `git diff <base> --name-only` at `:182` already run; keep both through the
      existing `_git` runner (`:186`).
- [ ] T008 [US1] Evaluate each changed path with `--no-index` ignore semantics
      plus the runtime-root prefixes derived from both root names per
      `factory/env.py:37` (FR-007, plan route choice — never a hardcoded
      literal; 043/US2 exists because of one).
- [ ] T009 [US1] Record offending paths on `OutputCheck`
      (`factory/verify/models.py:241`) with a default that leaves every stored
      row loading unchanged (plan trap 5), and fold the verdict into
      `OutputCheck.passed` only — `judge_required` (`models.py:355`) and
      `compose_result` (`:376`) are read, not edited (FR-002, plan trap 4).

## Phase 2: User Story 2 — An oversized diff is refused deterministically, not judged truncated

### Tests for this story (write FIRST, must fail)

- [ ] T010 [US2] Write the oversize case FIRST: a worktree whose diff exceeds
      `DIFF_INPUT_LIMIT` — read the constant from `factory/verify/judge.py:59`,
      never restate it (plan trap 8) — fails before any judge call, recording
      total size, the limit, and the largest contributing files with sizes
      (spec US2-S1, plan trap 9) — must fail.
- [ ] T011 [P] [US2] Write the under-limit parity case: the judge is invoked
      exactly as today, result unchanged (spec US2-S2) — must fail only if
      parity breaks.
- [ ] T012 [US2] Write the control FIRST, against the disable-seam: with the
      size check off, the same oversized worktree reaches the judge truncated
      (spec US2-S3, SC-004) — this is the test that proves the check is doing
      the work.

### Implementation for this story

- [ ] T013 [US2] The size check, per plan.md's route choice — prefer inside
      `check_output` so one floor decides and the evidence rides the same
      record; an explicit disable-seam for T012, never an environment read.
- [ ] T014 [US2] Leave `prepare_diff` (`judge.py:316`) untouched as defense in
      depth, and state in the commit message that `truncated_input` remains as
      a record (spec US2-S4).

## Phase 3: User Story 3 — A failed output check reaches the next attempt

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US3] Write the empty-diff case FIRST: evidence with
      `has_diff: false` renders a block stating the attempt produced no diff
      against its base (spec US3-S1, SC-002) — must fail.
- [ ] T016 [P] [US3] Write the hygiene case: a US1 failure renders every
      offending path verbatim (spec US3-S2, plan trap 10) — must fail.
- [ ] T017 [P] [US3] Write the size case: a US2 failure renders size, limit and
      named files (spec US3-S3) — must fail.
- [ ] T018 [P] [US3] Write the byte-parity case: evidence whose output check
      passed renders byte-identical to today, asserted against the current
      fixture corpus (spec US3-S4, FR-004, plan trap 6) — must pass before and
      after.

### Implementation for this story

- [ ] T019 [US3] Extend `_attempt_block` (`factory/workgraph/prompt.py:556`)
      with an output-check block emitted only when the check failed, quoting
      the recorded evidence through `_quote` (`:589`) — verbatim, never
      summarized (FR-005, plan trap 10).

## Verification

- [ ] Final gate command passes green.
