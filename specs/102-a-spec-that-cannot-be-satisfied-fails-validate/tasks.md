# Tasks: a spec that cannot be satisfied fails validate

**Spec**: `specs/102-a-spec-that-cannot-be-satisfied-fails-validate/spec.md`
**Plan**: `specs/102-a-spec-that-cannot-be-satisfied-fails-validate/plan.md`

Read the plan's traps before the first task. **Trap 1 is the epic**: this spec
and 116 cancel out if the refusal catches clauses a declared gate can evidence —
write T002 first and let it constrain everything else. Also trap 2 (a false
refusal is worse than a missed one; prefer the warning form), trap 4 (no manifest
means `not checked`, never a refusal) and trap 7 ("this criterion cannot be met"
must survive while "change this criterion" is withheld).

## Phase 1: User Story 1 — An unprovable criterion is refused at validate time

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_102_unprovable_criteria.py`,
      assert a Then-clause asserting a runtime outcome no declared gate measures
      is refused, with the clause quoted.
- [ ] T002 [P] [US1] (spec US1-S2, trap 1) **Write this first.** Assert a
      Then-clause asserting an outcome a declared gate *does* measure is NOT
      refused. This is what keeps this spec from undoing 116.
- [ ] T003 [P] [US1] (spec US1-S3, trap 5) **The corpus control.** Assert every
      spec under `specs/` validates with the same verdict as before this layer.
- [ ] T004 [P] [US1] (spec US1-S4) Assert a repository declaring no gates
      produces a refusal that says so specifically.
- [ ] T005 [P] [US1] (spec US1-S5) Assert the refusal suggests how to make the
      criterion provable.
- [ ] T006 [P] [US1] (FR-001, trap 4) Assert an unreadable manifest yields
      `layer … not checked` naming the reason, never a refusal.

### Implementation for this story

- [ ] T007 [US1] (FR-001, trap 3) Add the layer to validate's composition in
      `factory/cli/nouns/spec.py`, reading clauses through the existing criteria
      parser and gate names through the manifest loader. Keep the rule small
      enough to state in the refusal text.
- [ ] T008 [US1] (FR-002, trap 1) Admit any clause a declared gate can evidence.
- [ ] T009 [US1] (FR-004, FR-005) Give the refusal its two shapes — no gates
      declared, versus gates that do not cover the claim — and a suggestion in
      both.
- [ ] T010 [US1] (FR-001, trap 4) Emit `not checked` when the target manifest
      cannot be read, following the idiom the other layers use.

## Phase 2: User Story 2 — Validate says what the judge will see

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) Assert validate reports what the judge will be
      shown: the diff, the criteria, and the declared gates whose results
      accompany them.
- [ ] T012 [P] [US2] (spec US2-S2) Assert a fully provable spec gets the report
      and no refusal.
- [ ] T013 [P] [US2] (spec US2-S3, trap 2) Assert a borderline clause is named as
      a warning rather than refused.

### Implementation for this story

- [ ] T014 [US2] (FR-006) Assemble the report from what US1's layer already
      computed rather than re-deriving it.
- [ ] T015 [US2] (FR-007, trap 2) Add the warning form and route low-confidence
      clauses to it.

## Phase 3: User Story 3 — The judge may not propose moving the bar

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US3] (spec US3-S1) Assert the judge's instructions forbid
      proposing a change to the acceptance criteria as a remediation.
- [ ] T017 [P] [US3] (spec US3-S2, trap 6) **The enforceable half.** Assert a
      verdict whose feedback proposes changing a criterion has that proposal
      recorded and kept out of the next attempt's prompt.
- [ ] T018 [P] [US3] (spec US3-S3, trap 7) Assert a verdict reporting that a
      criterion appears unsatisfiable is preserved and surfaced to the operator —
      the filter must not silence the judge's most useful signal.
- [ ] T019 [P] [US3] (spec US3-S4) **The control.** Assert a verdict proposing no
      criterion change reaches the next attempt unchanged.
- [ ] T020 [P] [US3] (FR-009, trap 8) Assert a filtered proposal remains visible
      to an operator reading the attempt.

### Implementation for this story

- [ ] T021 [US3] (FR-008) Add the prohibition to the judge's instructions
      (`factory/verify/judge.py:133`), beside the existing
      looks-reasonable prohibition.
- [ ] T022 [US3] (FR-009, trap 6) Filter a criterion-change proposal out of the
      text carried as prior feedback into the next attempt's prompt.
- [ ] T023 [US3] (FR-010, trap 7) Preserve and surface an unsatisfiability
      report, which is the signal US1 exists to catch earlier.
- [ ] T024 [US3] (FR-011) Confirm `criteria_drift`'s hashing is unchanged by this
      epic and say so in the attempt report. Do not restate its path here,
      because a task that names a file joins that file to its story's slice.

### The operator's demonstration for this story

- [ ] T025 [US3] Run the paired demonstration in the plan's § *Verification the
      operator will run*: validate a spec whose Then-clause names a runtime
      outcome no gate covers, then rephrase it against a declared gate and
      validate again. Paste both outputs into the attempt report. The pair is the
      whole argument — the check must refuse the unprovable clause **and** admit
      the one a gate can evidence, because refusing both would undo spec 116.
