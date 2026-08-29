# Tasks: the sandbox is portable and sealed

**Spec**: `specs/101-the-sandbox-is-portable-and-sealed/spec.md`
**Plan**: `specs/101-the-sandbox-is-portable-and-sealed/plan.md`

Read the plan's traps before the first task. **Trap 1 is the epic.** Guidance
that names the mechanism without the recipe is measurably worse than no guidance:
the undocumented agent solved this in three attempts, the half-documented one
failed 3/3 and stopped searching. Also trap 3 (a declared bind is a hole in the
boundary — bound it to home and resolve symlinks), trap 4 (writable,
conditional-on-existence, paired with its variable — all three were learned) and
trap 5 (every existing manifest must keep the uv bind unchanged).

## Phase 1: User Story 1 — The agent is told what does not survive, as a line it can run

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_101_prompt_states_the_rule.py`,
      assemble an attempt prompt and assert it states that `HOME` at gate time is
      a tmpfs distinct from the attempt's and that only the worktree persists.
- [ ] T002 [P] [US1] (spec US1-S2, trap 1) **The story's whole point.** Assert
      the guidance carries a concrete runnable form rather than a description —
      an assertion on the presence of an executable instruction, not on prose.
- [ ] T003 [P] [US1] (spec US1-S3) Assert the guidance is present for a
      repository declaring no caches, and assert its length stays under a stated
      bound so it reads as an instruction rather than as background.

### Implementation for this story

- [ ] T004 [US1] (FR-001, FR-002, trap 1) Add the guidance to the attempt prompt.
      Write the executable line. If no single line covers every package world,
      state the rule and point at the declared-cache mechanism US2 adds — never
      name a mechanism and omit the recipe (trap 2).
- [ ] T005 [US1] (FR-003) Make the guidance unconditional on what a repository
      declares: it is a property of the boundary.

## Phase 2: User Story 2 — A repository declares the caches its gates need

### Tests for this story (write FIRST, must fail)

- [ ] T006 [P] [US2] (spec US2-S1) In `tests/test_101_declared_caches.py`, assert
      a manifest-declared cache path is bound writable into the boundary.
- [ ] T007 [P] [US2] (spec US2-S2, trap 4) Assert a declared path absent from the
      host does not fail the gate and is reported.
- [ ] T008 [P] [US2] (spec US2-S3, trap 5) **The control.** Assert a manifest
      declaring no caches binds the uv cache exactly as today, over the supplied
      manifest corpus.
- [ ] T009 [P] [US2] (spec US2-S4, trap 3) Assert a declared path outside the
      operator's home is refused at load time naming the path, including the case
      of a symlink inside home resolving outside it.
- [ ] T010 [P] [US2] (spec US2-S5, trap 4) Assert an environment variable named
      by a declaration is set beside its bind.
- [ ] T011 [P] [US2] (FR-004, trap 4) Assert every declared bind is writable — a
      read-only cache is worse than none, as the existing docstring records.

### Implementation for this story

- [ ] T012 [US2] (FR-004) Add the declared-caches key to the manifest schema,
      each entry a path and an optional environment variable name.
- [ ] T013 [US2] (FR-007, trap 3) Refuse a path outside the operator's home at
      load time, resolving symlinks before deciding.
- [ ] T014 [US2] (FR-004, FR-005, FR-006, trap 4) Generalise `_cache_binds`
      (`factory/verify/gates.py:861`) to return the declared binds plus today's
      uv default, preserving writability, the existence condition and the
      variable pairing its docstring argues for.
- [ ] T015 [US2] (FR-008) Set each declaration's variable where `UV_CACHE_DIR` is
      set today (`:693`), through the boundary's existing environment path.

## Phase 3: User Story 3 — A toolchain failure is annotated, not echoed

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US3] (spec US3-S1, trap 7) Assert a gate failure matching a known
      install-a-toolchain signature carries the boundary's `HOME` fact in its
      detail.
- [ ] T017 [P] [US3] (spec US3-S2) **The control.** Assert a failure matching no
      signature is recorded unchanged.
- [ ] T018 [P] [US3] (spec US3-S3, trap 6) Assert the annotation reaches the next
      attempt's prompt end to end. An annotation the retry never sees is a
      comment.

### Implementation for this story

- [ ] T019 [US3] (FR-009, trap 7) Match a small, explicit, anchored set of
      signatures and append the environment fact to the gate's failure detail.
- [ ] T020 [US3] (FR-009, trap 6) Confirm the annotated detail flows through the
      existing path by which gate results reach the retry prompt.
- [ ] T021 [US3] (FR-010) Confirm the three things FR-010 names are unchanged by
      this epic and say so in the attempt report. Do not restate their paths
      here, because a task that names a file joins that file to its story's slice.

### The operator's demonstration for this story

- [ ] T022 [US3] Run the warm-cache demonstration in the plan's § *Verification
      the operator will run* and paste the smoke gate's duration with and without
      the cache declared into the attempt report. The difference between a
      network-bound run and a warm one is the evidence, and it is the same
      evidence `_cache_binds`' own docstring cites for the Python world.
