# Tasks: the record outlives the build

**Spec**: `specs/117-the-record-outlives-the-build/spec.md`
**Plan**: `specs/117-the-record-outlives-the-build/plan.md`

Read the plan's traps before the first task. Trap 1 (a UNIQUE constraint cannot
be altered in place — use the rebuild shape already in this file), trap 2 (a
migrated store's column order must match a fresh one, and the file says so),
trap 3 (old rows need a reserved dispatch value; NULL will not do, because SQLite
treats NULLs as distinct in a UNIQUE index) and trap 4 (the discriminator must
survive a Temporal retry) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — A re-dispatch adds to the history

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_117_dispatch_scoped_rows.py`,
      record attempts one to three for a node, then record a second dispatch's
      attempt one, and assert both attempt-one rows exist and are
      distinguishable.
- [ ] T002 [P] [US1] (spec US1-S2) **The idempotence control.** Assert recording
      the same attempt twice within one dispatch updates the first row rather
      than adding another.
- [ ] T003 [P] [US1] (spec US1-S3, trap 2) Assert a store created before this
      change migrates in place, keeps its rows readable, and ends with the same
      column order as a freshly created store — compare the two orders directly.
- [ ] T004 [P] [US1] (spec US1-S4, trap 3) Assert pre-existing rows carry a
      reserved dispatch value, and that a later dispatch of the same node does
      not merge into them.
- [ ] T005 [P] [US1] (FR-002, trap 4) Assert the discriminator is stable across a
      simulated activity retry: the same dispatch retried writes one row.

### Implementation for this story

- [ ] T006 [US1] (FR-001) Add the dispatch to `_RESULT_KEY`
      (`factory/verify/store.py:486`) and to the table's UNIQUE constraint
      (`:176`). The upsert SQL is generated from that tuple (`:512-521`) and
      should need no hand-editing.
- [ ] T007 [US1] (FR-003, trap 1) Write the migration using the rebuild shape
      already in this file at `:362-383` — new table, rows copied, old dropped,
      renamed — because a UNIQUE constraint cannot be altered in place.
- [ ] T008 [US1] (FR-004, trap 3) Supply the reserved dispatch value for copied
      rows. Do not use NULL.
- [ ] T009 [US1] (FR-001, trap 4) Carry the dispatch identity from the workflow
      run into the recording path, so a retry reuses it.

## Phase 2: User Story 2 — The row says who built it

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) In `tests/test_117_row_names_its_builder.py`,
      assert a gateway-routed attempt records persona, model alias and route.
- [ ] T011 [P] [US2] (spec US2-S2) Assert a subscription-routed attempt records
      the subscription route rather than leaving it null.
- [ ] T012 [P] [US2] (spec US2-S3, trap 5) Assert a debugger-rung attempt records
      the model alias that actually ran, not the one the relabelled persona would
      resolve to.
- [ ] T013 [P] [US2] (spec US2-S4, trap 6) Assert rows predating these columns
      read as unknown rather than as an empty value that renders like a real one.

### Implementation for this story

- [ ] T014 [US2] (FR-005) Add the three columns to the table and to
      `_RESULT_COLUMNS` (`:488`), keeping DDL order (trap 2).
- [ ] T015 [US2] (FR-005, FR-006, trap 5) Populate them at the point the route
      and alias were resolved for the attempt, not by re-deriving from the
      persona at write time.
- [ ] T016 [US2] (FR-007, trap 6) Decide the unknown representation once and use
      it for migrated rows.

## Phase 3: User Story 3 — A reader can tell two dispatches apart

### Tests for this story (write FIRST, must fail)

- [ ] T017 [P] [US3] (spec US3-S1) Assert a node with two dispatches reads
      grouped by dispatch, oldest first within each.
- [ ] T018 [P] [US3] (spec US3-S2) Assert the CLI states how many dispatches a
      node has had.
- [ ] T019 [P] [US3] (spec US3-S3, trap 8) **The control.** Assert a
      single-dispatch node reads exactly as it does today, through the exported
      readers.
- [ ] T020 [P] [US3] (spec US3-S4, trap 7) Assert ordering is by write time, not
      by row id — construct two dispatches whose id order and chronological order
      disagree.

### Implementation for this story

- [ ] T021 [US3] (FR-008, trap 7) Group and order the node's history by dispatch
      and write time.
- [ ] T022 [US3] (FR-009, trap 8) Keep the exported readers' single-dispatch
      shape unchanged.
- [ ] T023 [US3] (FR-010) Confirm the two things FR-010 names are unchanged by
      this epic and say so in `specs/117-the-record-outlives-the-build/attempt-report-<story>.md` (the attempt report). Do not restate their paths
      here, because a task that names a file joins that file to its story's slice.

### The operator's demonstration for this story

- [ ] T024 [US3] Run the reset-and-re-dispatch demonstration in the plan's
      § *Verification the operator will run* and paste the node history into the
      attempt report. The demonstration succeeds when both dispatches' attempt-one
      rows are present, distinguishable and ordered, each naming its persona and
      model. Before this spec the second dispatch's attempt one has silently
      replaced the first's, and no gate can show that, because a gate never
      dispatches twice.
