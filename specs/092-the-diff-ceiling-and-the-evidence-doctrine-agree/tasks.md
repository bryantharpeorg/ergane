# Tasks: the diff ceiling and the evidence doctrine agree

**Spec**: `specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md`
**Plan**: `specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/plan.md`

Read the plan's traps before the first task. Trap 1 (never exempt a path by name
or pattern — that is the fix that hid this defect last time), trap 2 (two names,
never two copies of a number), trap 3 (both limits must keep measuring the same
assembly) and trap 4 (a threshold below the attention budget recreates the
defect) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — The two limits have two names

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_092_two_limits.py`, with the
      refusal threshold set above the attention budget, assert a diff sized
      between them records **no** size refusal.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the same diff, prepared for the judge,
      comes back abridged to the attention budget with its truncation disclosed.
- [ ] T003 [P] [US1] (spec US1-S3) Assert a diff above the refusal threshold
      still records a refusal naming the total and the biggest files, in the
      rendering the retry prompt quotes (trap 7).
- [ ] T004 [P] [US1] (spec US1-S4) **The control.** Assert that at default
      configuration the check's outcome is identical to today's for diffs either
      side of the current constant — a rename and a split, not a behaviour
      change.
- [ ] T005 [P] [US1] (FR-002, trap 3) Assert the refusal and the abridger agree
      at the margin: a diff whose assembly is exactly at the attention budget is
      not abridged and not refused, computed from the same assembly both already
      weigh.

### Implementation for this story

- [ ] T006 [US1] (FR-001) In `factory/verify/diffbounds.py`, give the refusal
      threshold its own name beside `DIFF_INPUT_LIMIT` (`:42`), defaulting to a
      value that preserves today's behaviour. Keep exactly one definition of
      each (trap 2) and carry the existing comment's argument forward — it
      explains what the attention budget is for and now needs to say what the
      threshold is for.
- [ ] T007 [US1] (FR-002) Point `size_refusal` (`:113`) at the refusal threshold
      and leave `prepare_diff` reading the attention budget. Do not change what
      either measures (trap 3).
- [ ] T008 [US1] (FR-003) Thread the threshold through `diff_size_refusal`
      (`factory/verify/diffcheck.py:293`) and `check_output`'s
      `diff_size_limit` seam (`:162`), preserving `None` as *disabled* for tests
      only (trap 5).

## Phase 2: User Story 2 — The refusal threshold belongs to the operator

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1) In `tests/test_092_manifest_threshold.py`,
      assert a manifest declaring a threshold makes the check refuse at that
      value rather than the default.
- [ ] T010 [P] [US2] (spec US2-S2) **The control (trap 8).** Assert every
      manifest in the supplied corpus, none of which declares the key, loads and
      behaves exactly as before.
- [ ] T011 [P] [US2] (spec US2-S3, trap 4) Assert a threshold below the judge's
      attention budget is refused at load time, naming both values.
- [ ] T012 [P] [US2] (spec US2-S4) Assert a non-integer and a negative threshold
      are each refused in the shape the ladder's numeric keys are refused.

### Implementation for this story

- [ ] T013 [US2] (FR-004) Add the threshold key to the manifest schema in
      `factory/verify/factory_yaml.py`, absent meaning the default, following the
      numeric-key idiom at `:648-660`.
- [ ] T014 [US2] (FR-005, FR-006) Add the two refusals: below the attention
      budget, and not a whole positive number. Name the offending value in both,
      and both bounds in the first.
- [ ] T015 [US2] (FR-004) Pass the loaded value into the verification path so the
      declared threshold reaches `check_output`; do not read it a second time
      anywhere else (trap 2).

## Phase 3: User Story 3 — An abridged verdict is auditable

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US3] (spec US3-S1) In `tests/test_092_abridged_is_recorded.py`,
      assert an attempt whose judge input was abridged writes that fact and the
      amount onto its verification row.
- [ ] T017 [P] [US3] (spec US3-S2, trap 6) Assert an attempt the judge saw whole
      records that explicitly — the absence of a flag must be a statement, not a
      silence.
- [ ] T018 [P] [US3] (spec US3-S3) Assert the abridgement is visible through the
      CLI without reading the store.
- [ ] T019 [P] [US3] (FR-007) Assert the field survives a store round trip, in
      the shape the size refusal already round-trips.

### Implementation for this story

- [ ] T020 [US3] (FR-007) Carry the abridgement fact and its amount from
      `prepare_diff`'s result onto the check record, alongside the existing
      `size_refusal` field (`factory/verify/models.py:433`).
- [ ] T021 [US3] (FR-007) Serialise and deserialise it beside the size refusal in
      `factory/verify/store.py:717-770`, following that field's existing pair of
      helpers rather than inventing a second idiom.
- [ ] T022 [US3] (FR-007) Render it in the attempt view so an operator can tell
      an abridged PASS from a whole-diff PASS.
- [ ] T023 [US3] (FR-008) Confirm the abridgement algorithm named by FR-008 is
      unchanged and that no path is exempted by name or pattern anywhere in this
      epic, and say so in the attempt report. Do not restate the module path
      here, because a task that names a file joins that file to its story's
      slice and no story here edits it.

### The operator's demonstration for this story

- [ ] T024 [US3] Run the demonstration in the plan's § *Verification the operator
      will run*: confirm the default-configuration behaviour is preserved, then
      build one real node whose diff exceeds the old constant and paste its
      status output into the attempt report. The demonstration succeeds when that
      node reaches a judge verdict at all — PASS or FAIL, either is proof — and
      its record says the input was abridged. Before this spec no such node can
      reach a verdict by any route, which is the one fact the gate cannot show.
