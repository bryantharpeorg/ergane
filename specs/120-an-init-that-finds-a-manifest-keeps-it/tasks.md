# Tasks: an init that finds a manifest keeps it

**Spec**: `specs/120-an-init-that-finds-a-manifest-keeps-it/spec.md`
**Plan**: `specs/120-an-init-that-finds-a-manifest-keeps-it/plan.md`

Read the plan's traps before the first task. Trap 2 (not rewriting the manifest
is not declining the wiring job), trap 3 (an invalid manifest is a conversation,
not a licence to replace it), trap 4 (fix the ordering, not `standards`
specifically) and trap 8 (assert **bytes** — a structural comparison passes on a
rewrite that dropped forty lines of comments) are the four that decide whether an
attempt lands.

## Phase 1: User Story 1 — A valid manifest is not rewritten

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, trap 8) In
      `tests/test_120_wire_keeps_the_manifest.py`, run `init --wire` over a
      repository holding a valid commented manifest and assert the file is
      **byte-identical** afterwards. Compare bytes, not parsed structures.
- [ ] T002 [P] [US1] (spec US1-S2, trap 2) Assert the wiring work still happens
      when the manifest is left alone.
- [ ] T003 [P] [US1] (spec US1-S3) **The control.** Assert a repository with no
      manifest gets one written exactly as today.
- [ ] T004 [P] [US1] (spec US1-S4, trap 3) Assert a manifest the schema refuses
      produces a report and is not replaced.
- [ ] T005 [P] [US1] (FR-001, trap 1) Assert init's notion of validity is the
      loader `init --check` uses, so the two verbs cannot disagree about one file.

### Implementation for this story

- [ ] T006 [US1] (FR-001, trap 1) Decide whether to write the manifest by asking
      the same loader `--check` asks.
- [ ] T007 [US1] (FR-002, trap 2) Separate "write the manifest" from "do the
      wiring" so skipping the first does not skip the second.
- [ ] T008 [US1] (FR-004, trap 3) Report an invalid existing manifest and stop.

## Phase 2: User Story 2 — A rewrite carries everything forward

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1, trap 4) In
      `tests/test_120_rewrite_carries_forward.py`, assert a rewrite on the
      non-interactive path preserves a declared `standards` value.
- [ ] T010 [P] [US2] (spec US2-S2, trap 5) Assert `ladder` and `verify` survive a
      rewrite on both paths — neither is in init's vocabulary today.
- [ ] T011 [P] [US2] (spec US2-S3) Assert an unrecognised key causes a refusal
      naming it, rather than being dropped.
- [ ] T012 [P] [US2] (spec US2-S4) **The control.** Assert optional keys are
      still absent when a manifest is written where none existed.
- [ ] T013 [P] [US2] (spec US2-S5) Assert the operator is told before a write
      that will discard comments.
- [ ] T013a [P] [US2] (spec US2-S6) **The remedy loop.** Assert that following
      the guidance at `factory/cli/init.py:921` — re-run with `--wire` — leaves a
      declared `ladder` block present. The verb's own remedy currently recommends
      the command that deletes it.
- [ ] T013b [P] [US2] (spec US2-S7) Assert `init --check` reports the manifest's
      actual state after such a re-run. Today the schedule is reconciled to the
      stripped file, both sides agree, and a flattened repository reads healthy.
- [ ] T014 [P] [US2] (FR-007, trap 6) Assert init's own output round-trips: write
      a manifest, rewrite it, and confirm no refusal fires on a key init itself
      produced.
- [ ] T015 [P] [US2] (FR-005, trap 4) Assert every member of `_OPTIONAL_KEYS`
      carries forward, not only `standards` — the ordering fix must cover the
      whole tuple.

### Implementation for this story

- [ ] T016 [US2] (FR-005, trap 4) In `_init_default`
      (`factory/cli/init.py`), consult the computed defaults before
      returning absent for an optional key, so a declared value wins and "absent"
      applies only when nothing was declared. Replace the comment that justified
      the old order.
- [ ] T017 [US2] (FR-006, trap 5) Carry `ladder` and `verify` through the rewrite
      path without adding them to the interview.
- [ ] T018 [US2] (FR-007) Refuse an unrecognised key, naming it.
- [ ] T019 [US2] (FR-009) Warn before a write that will discard comments.

## Phase 3: User Story 3 — The roadmap dial is reconciled against the file

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S1, trap 7) Assert a schedule disagreeing with the
      manifest's declared roadmap dial is reported as a disagreement. It
      currently prints "already satisfied" because it compares against its own
      rewrite.
- [ ] T021 [P] [US3] (spec US3-S2) Assert agreement is reported when the two
      agree.
- [ ] T022 [P] [US3] (spec US3-S3) Assert a manifest declaring no roadmap dial is
      reported as such rather than compared against a default.

### Implementation for this story

- [ ] T023 [US3] (FR-010, trap 7) Read the roadmap dial from the manifest as it
      stood before any write, and reconcile the schedule against that.

### The operator's demonstration for this story

- [ ] T024 [US3] Run the checksum demonstration in the plan's § *Verification the
      operator will run* and paste both `sha256sum` outputs and the empty
      `git diff --stat` into `specs/120-an-init-that-finds-a-manifest-keeps-it/attempt-report-<story>.md` (the attempt report). Before this spec the same
      sequence silently removes `standards`, the whole `ladder` block and about
      forty lines of comments — and `init --check` calls the result valid, which
      is why no gate catches it.
