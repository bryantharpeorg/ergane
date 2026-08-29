# Tasks: the judge scores against what the factory measured

**Spec**: `specs/116-the-judge-scores-against-what-the-factory-measured/spec.md`
**Plan**: `specs/116-the-judge-scores-against-what-the-factory-measured/plan.md`

Read the plan's traps before the first task. Trap 1 (the system prompt must
change or US1 does nothing), trap 4 (the gate section is inside the judge's input
budget, not beside it), trap 5 (match gate names on boundaries, never as
substrings) and trap 6 (a contradiction neutralises one finding, it does not pass
the attempt) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — The judge is shown the gate results

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_116_judge_sees_gates.py`,
      assemble a prompt from a criteria set and a list of gate results, and
      assert each gate's name, status and exit code appear in it.
- [ ] T002 [P] [US1] (spec US1-S2) Assert a non-PASS gate contributes a bounded
      output tail, and that the bound is enforced on a tail longer than it.
- [ ] T003 [P] [US1] (spec US1-S3) **The control (trap 3).** Assert a prompt
      assembled with no gate results is byte-identical to one assembled by the
      current code path.
- [ ] T004 [P] [US1] (spec US1-S4, trap 4) Assert the gate section is counted
      against the judge's input budget by the same measurement the diff is —
      an assembly at the cap with a gate section must abridge the diff, not
      overflow.
- [ ] T005 [P] [US1] (spec US1-S5) Assert section order: scenarios, then gate
      results, then the diff.
- [ ] T006 [P] [US1] (FR-001, trap 1) Assert the system prompt instructs the
      judge that the gate results are the factory's own measurement of this
      attempt and that a scenario naming a gate outcome is scored against it —
      and that it still forbids passing a scenario because the change looks
      reasonable overall (trap 2).

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002, FR-005) Add an optional gate-results parameter
      to `build_prompt` (`factory/verify/judge.py:240`) and render its section
      between the scenarios and the diff. Default absent (trap 3).
- [ ] T008 [US1] (FR-004, trap 4) Include the section in the assembly whose size
      is fitted under the judge's input limit, reading that limit through its
      existing name rather than restating the number.
- [ ] T009 [US1] (FR-001, trap 1) Amend `SYSTEM_PROMPT`
      (`factory/verify/judge.py:133`) as T006 asserts. Keep the
      looks-reasonable prohibition intact.
- [ ] T010 [US1] (FR-001) Thread the gate results from the caller at
      `factory/verify/judge.py:616` — they are already in the caller's hand,
      because `judge_required` was given them one step earlier.

## Phase 2: User Story 2 — A verdict that contradicts a recorded gate is a judge fault

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) In `tests/test_116_gate_is_ground_truth.py`,
      assert a finding asserting a PASS-recorded gate would fail is recorded as a
      contradiction and does not by itself produce a node FAIL.
- [ ] T012 [P] [US2] (spec US2-S2) Assert the judge is retried while its retry
      budget is unspent, riding the existing budget rather than a new one.
- [ ] T013 [P] [US2] (spec US2-S3) Assert that with the budget spent the
      contradiction is still recorded and still does not fail the node on that
      finding alone.
- [ ] T014 [P] [US2] (spec US2-S4) **The control.** Assert a verdict whose
      findings name no gate composes exactly as today.
- [ ] T015 [P] [US2] (spec US2-S5) Assert a finding naming a gate that genuinely
      failed is honoured — the check is for contradiction, not for mentions.
- [ ] T016 [P] [US2] (FR-006, trap 5) Assert gate-name matching is exact or on a
      word boundary: a repo with gates `test` and `typecheck` must not match one
      inside the other.
- [ ] T017 [P] [US2] (FR-006, trap 6) Assert a contradiction alongside a second,
      unrelated failing finding still fails the node — neutralising one finding
      is not passing the attempt.

### Implementation for this story

- [ ] T018 [US2] (FR-006) Detect a finding that names a gate recorded PASS on
      this attempt and asserts it would fail. Match on boundaries (trap 5).
- [ ] T019 [US2] (FR-006, trap 7) Neutralise that finding where `judge_accepts`
      is derived in `compose_result` (`factory/verify/models.py:565,:608`) and
      recompose, so exactly one place decides.
- [ ] T020 [US2] (FR-007) Make a contradiction request a judge retry through the
      existing `judge_attempt` / `max_judge_retries` path
      (`factory/verify/judge.py:637-640`).

## Phase 3: User Story 3 — The record says what the judge was shown

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1) Assert an attempt judged with gate results
      records that fact on its row.
- [ ] T022 [P] [US3] (spec US3-S2, trap 8) Assert an attempt judged without them
      records their absence explicitly — silence is not a statement.
- [ ] T023 [P] [US3] (spec US3-S3) Assert a recorded contradiction is visible
      through the CLI without reading the store.
- [ ] T024 [P] [US3] (FR-008) Assert both fields survive a store round trip.

### Implementation for this story

- [ ] T025 [US3] (FR-008) Carry both facts onto the verdict and the verification
      row, following the precedent of `truncated_input`, which is already carried
      from the prompt onto the verdict.
- [ ] T026 [US3] (FR-008) Render the contradiction in the attempt view.
- [ ] T027 [US3] (FR-009) Confirm the three things FR-009 names are unchanged by
      this epic and say so in the attempt report. Do not restate their paths
      here, because a task that names a file joins that file to its story's
      slice and no story here edits them.

### The operator's demonstration for this story

- [ ] T028 [US3] Run the paired demonstration in the plan's § *Verification the
      operator will run*: score one scenario whose Then-clause names a runtime
      outcome against the live judge twice, once with the gate section and once
      without, and paste both verdicts into the attempt report. The
      demonstration succeeds when the with-gates run passes and the without-gates
      run fails. No gate can produce this evidence, because it requires a model.
