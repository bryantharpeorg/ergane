# Tasks: a spec that fixes a finding declares it

**Spec**: `specs/089-a-spec-that-fixes-a-finding-declares-it/spec.md`
**Plan**: `specs/089-a-spec-that-fixes-a-finding-declares-it/plan.md`

Read the plan's traps before the first task. Trap 1 (there are two frontmatter
writers and only `_build_spec_md` is yours), trap 2 (never edit
`factory/doctor/triage.py` — the reader is correct), trap 5 (an absent ledger is
`not checked`, never a refusal) and trap 8 (the prose mentions stay) are the four
that decide whether an attempt lands.

## Phase 1: User Story 1 — The promote verb declares what it promoted

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_089_promote_declares_fixes.py`,
      build a findings store under `tmp_path` holding open findings `a/one` and
      `b/two`, run `ergane findings promote --slug s --keys a/one b/two` against
      a `tmp_path` specs root, and assert the generated `spec.md` frontmatter
      carries `fixes:` with exactly those two members in that order.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the generated frontmatter parses
      through `factory.doctor.triage._declaration` and returns both keys, not an
      empty list. This is the proof that the emitted text satisfies the reader.
- [ ] T003 [P] [US1] (spec US1-S3) **The regression guard (trap 8).** Assert the
      generated `spec.md` still contains the promoted key in all four prose
      positions — the Given clause, the functional requirement, the
      addressed-findings bullet and the task.
- [ ] T004 [P] [US1] (spec US1-S4) Assert `ergane spec validate` returns the same
      verdict for a promote-generated trio as it does today, over a trio
      generated in the same test.
- [ ] T005 [P] [US1] **The control (trap 1).** Assert `scaffold_spec` called in
      its *slot* form (`slug`/`title`/`anchor`, no `findings`) writes frontmatter
      containing `state: draft` and **no** `fixes:` key at all.

### Implementation for this story

- [ ] T006 [US1] (FR-001) In `_build_spec_md` (`factory/doctor/scaffold.py:316`),
      after the `state: draft` line at `:320-325`, append a `fixes:` block naming
      each finding's `key`, one `  - <key>` line per finding, in the order the
      findings were given. Append literal lines exactly as the surrounding code
      does — do not reach for `yaml.safe_dump` (trap 3).
- [ ] T007 [US1] (FR-002) Change nothing else in `_build_spec_md`. The key
      emissions at `:347`, `:370`, `:398` and `:415` stay exactly as they are.
- [ ] T008 [US1] (FR-007) Confirm by inspection that no edit was made to
      `factory/roadmap/models.py` or `factory/doctor/triage.py`, and say so in
      the attempt's report.

### The operator's demonstration for this story

- [ ] T009 [US1] Run the loop demonstration in the plan's § *Verification the
      operator will run* against a throwaway store and specs root, and paste the
      `triage` counts output into `specs/089-a-spec-that-fixes-a-finding-declares-it/attempt-report-<story>.md` (the attempt report), showing the promoted
      finding classifying as `fixed` rather than `candidate`. The gate cannot
      establish this; only a landed, dated spec can.

## Phase 2: User Story 2 — A new spec can name its finding when it is created

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) In `tests/test_089_spec_new_fixes.py`, run
      `ergane spec new <slug> --fixes a/one` against a `tmp_path` specs root and
      assert the scaffolded `spec.md` frontmatter carries a `fixes:` list whose
      single member is `a/one`.
- [ ] T011 [P] [US2] (spec US2-S2) Assert two `--fixes` occurrences produce both
      keys, in the order given.
- [ ] T012 [P] [US2] (spec US2-S3) **The control.** Assert that with no `--fixes`
      argument the scaffolded frontmatter is byte-identical to the frontmatter
      the verb writes today, captured in the same test rather than hardcoded.

### Implementation for this story

- [ ] T013 [US2] (FR-003) Add a repeatable `--fixes` option to the `spec new`
      subparser in `factory/cli/nouns/spec.py`, appending to a list and
      defaulting to the empty list.
- [ ] T014 [US2] (FR-003, FR-004) Thread the collected keys into the scaffolder
      and emit the same `fixes:` block shape US1 emits. When the list is empty,
      emit no `fixes:` key at all — an empty list in the frontmatter is not the
      same text as an absent key, and FR-004 requires byte-identical output.

## Phase 3: User Story 3 — A declaration that names nothing is refused

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US3] (spec US3-S1) In `tests/test_089_validate_checks_fixes.py`,
      supply a specs corpus under `tmp_path` whose spec declares
      `fixes: [absent/key]` and a store holding no such key; assert
      `ergane spec validate` refuses, and that the message names both
      `absent/key` and the store path it read.
- [ ] T016 [P] [US3] (spec US3-S2) Assert a spec whose `fixes:` names only keys
      present in the store passes the layer and reports the number of keys
      verified.
- [ ] T017 [P] [US3] (spec US3-S3) **The trap-5 proof.** Point the check at a
      runtime root holding no store at all and assert validate reports the layer
      as `not checked`, names the absent store, and does **not** refuse.
- [ ] T018 [P] [US3] (spec US3-S4) **The control.** Assert a spec omitting
      `fixes:` entirely validates with the same verdict as before this story,
      over a supplied corpus.
- [ ] T019 [P] [US3] (FR-006, trap 6) Assert that running validate against a path
      where no store exists leaves that path still non-existent afterwards — the
      check may not create the store it reads.

### Implementation for this story

- [ ] T020 [US3] (FR-005) Add a `fixes` layer to the checks `spec validate`
      composes in `factory/cli/nouns/spec.py`. For each key declared by the spec
      under test, look it up in the ledger; collect every key that is absent and
      refuse once, naming all of them and the store path.
- [ ] T021 [US3] (FR-006, trap 6) Resolve the store path the way the other
      readers do, and open it with the existence-check-then-readonly idiom used
      by `open_store_readonly` (`factory/cli/status.py`). Emit the standard
      `layer 'fixes' not checked: <reason>` line when the store is absent or
      unreadable, distinguishing the two in the reason.
- [ ] T022 [US3] (FR-004, FR-007) Confirm a spec with no `fixes:` key takes no
      new code path, and that both modules FR-007 names are unchanged by this
      story. State it in `specs/089-a-spec-that-fixes-a-finding-declares-it/attempt-report-<story>.md` (the attempt report); do not restate their paths here,
      because a task that names a file joins that file to its story's slice and
      this story edits neither.
