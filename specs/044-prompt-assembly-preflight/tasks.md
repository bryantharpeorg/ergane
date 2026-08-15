# Tasks: 044-prompt-assembly-preflight

Three stories: US1 → {US2, US3}. Work test-first and commit once per task. Read
plan.md before the first commit — trap 1 (workflow code cannot read files) and
trap 2 (fence-masking) are the two that turn a clean design into a rejected one.

## Phase 1: User Story 1 — `ergane spec validate` assembles every node's prompt

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the 043-defect case FIRST: a committed fixture trio
      whose tasks.md phase headings omit `User Story <n>`; validate reports a
      `prompt_assembly` finding naming the node, the story key and tasks.md, and
      exits non-zero (spec US1-S1) — must fail.
- [ ] T002 [P] [US1] Write the missing-story-section case: a fixture spec.md
      declaring no section for a derived story; the finding names the node and
      spec.md (spec US1-S2) — must fail.
- [ ] T003 [P] [US1] Write the clean case: a well-formed fixture trio validates
      with `prompt_assembly` in the report's `checked` list and no findings
      (spec US1-S3) — must fail.
- [ ] T004 [P] [US1] Write the missing-file case: a trio without plan.md (and one
      without tasks.md) reports the missing path as a finding, never a traceback
      (spec US1-S4, plan trap 4) — must fail.
- [ ] T005 [P] [US1] Write the one-grammar guard: a test that fails if the module
      implementing the layer defines its own story-heading regex instead of
      calling the assembler (spec US1-S5, FR-004) — must fail.
- [ ] T006 [P] [US1] Write the control: the T001 and T002 fixtures pass the four
      existing layers with no finding, proven by running only those layers
      (SC-004) — must fail until the fixtures exist, then pass unchanged.

### Implementation for this story

- [ ] T007 [US1] The shared pure check, per plan.md route choice — prefer
      `factory/workgraph/preflight.py` beside `check_aliases` (`:110`): given a
      derived graph and the three texts, call `build_attempt_prompt`
      (`factory/workgraph/prompt.py:282`) per node and collect each
      `PromptAssemblyError` as a finding naming node and document. No proxy, no
      Temporal, no network (FR-002).
- [ ] T008 [US1] Wire it into `_validate_command` as layer five, reusing the
      graph already derived at `factory/cli/nouns/spec.py:239` and appending
      `prompt_assembly` to the `checked` list at `:262-267` — honestly: when
      derivation failed, the layer is reported skipped, not passed (plan trap 5).

## Phase 2: User Story 2 — The roadmap refuses to dispatch an epic whose prompts cannot assemble

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US2] Write the park case FIRST: a ready spec with the T001 fixture's
      defect parks with a preflight finding whose check is `prompt-assembly`
      quoting the `PromptAssemblyError` verbatim, and no agent attempt was
      dispatched for any node (spec US2-S1, SC-003) — must fail.
- [ ] T010 [P] [US2] Write the clean-dispatch case: a well-formed ready spec
      dispatches exactly as before (spec US2-S2) — must fail.
- [ ] T011 [P] [US2] Write the offline case: the assembly preflight runs with no
      network and no client constructed (spec US2-S3, FR-002) — must fail.
- [ ] T012 [US2] Write the recovery case: fix the parked spec's tasks.md, unpark,
      and the next tick dispatches it (spec US2-S4) — must fail.

### Implementation for this story

- [ ] T013 [US2] Run the shared check inside the roadmap's pre-epic preflight
      activity beside `check_aliases` (`factory/activities/roadmap_activities.py:353`)
      — in the activity, never in workflow code (plan trap 1) — reading the trio
      through the same reads the dispatch path performs (FR-007, plan trap 8).
- [ ] T014 [US2] Emit the failure as a `PreflightFinding` with
      `check="prompt-assembly"`, following the `model-aliases-served` naming at
      `factory/workgraph/preflight.py:133`, and add the check to
      `ergane build preflight`'s path at `factory/cli/nouns/build.py:165`.

## Phase 3: User Story 3 — Tasks that reach no agent are named

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US3] Write the 011-defect case FIRST: a committed fixture
      reproducing the phase-level Tests/Implementation split; the
      `slice_coverage` finding names each task id that references the story but
      falls outside its slice, and names the story (spec US3-S1, SC-002) — must
      fail.
- [ ] T016 [P] [US3] Write the wrong-slice case: a task tagged for one story
      sitting inside another story's slice is named with both (spec US3-S2) —
      must fail.
- [ ] T017 [P] [US3] Write the orphan case: task ids inside no slice with no
      story reference are reported as information, exit code unchanged, and a
      trailing section with no task ids reports nothing (spec US3-S3, plan
      trap 6) — must fail.
- [ ] T018 [P] [US3] Write the clean case: a trio where every task id sits in the
      slice its reference names produces no `slice_coverage` output
      (spec US3-S4) — must fail.

### Implementation for this story

- [ ] T019 [US3] The lint, in the same shared module as T007: recompute each
      node's slice with the assembler, locate every `T\d{3}[a-z]?` task line
      with `mask_fences` applied (plan trap 2 — a heading or task quoted in a
      fence is not a task), classify each as in-its-story's-slice /
      wrong-slice / orphan, and emit defect or info findings per FR-005/FR-006.
      Match both reference forms — `[US<n>]` tags and `spec US<n>-` citations
      (plan route choice).
- [ ] T020 [US3] Wire it into validate as the `slice_coverage` layer with the
      same honesty rule as T008.

## Verification

- [ ] Final gate command passes green.
