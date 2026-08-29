# Tasks: the ladder charges only the story

**Spec**: `specs/095-the-ladder-charges-only-the-story/spec.md`
**Plan**: `specs/095-the-ladder-charges-only-the-story/plan.md`

Read the plan's traps before the first task. Trap 1 (detect the pre-agent case
structurally, never by matching the adapter's message), trap 2 (an exclusion
without a bound of its own is a starvation bug), trap 4 (`_attempts_spent`'s
`config` is optional and a config-dependent exclusion silently will not apply
where it is None) and trap 7 (the veto is read-only) are the four that decide
whether an attempt lands.

## Phase 1: User Story 1 — A pre-agent failure says what it was

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_095_pre_agent_failure.py`,
      drive an attempt whose agent process never produced a token and assert its
      terminal reason names authentication rather than a generic agent error.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the reason and its remedy are readable
      through the CLI without opening a transcript.
- [ ] T003 [P] [US1] (spec US1-S3) **The control.** Assert an attempt whose agent
      started and then failed records the terminal reason it records today.
- [ ] T004 [P] [US1] (spec US1-S4, trap 3) Assert the record states that the
      gates ran against a worktree no agent prepared, and that the gate results
      themselves are still recorded rather than suppressed.
- [ ] T005 [P] [US1] (FR-001, trap 1) Assert the detection is structural: an
      attempt matching the pre-agent shape is classified even when its stdout
      carries a message the code has never seen.

### Implementation for this story

- [ ] T006 [US1] (FR-001) Add the pre-agent termination alongside the existing
      values described at `factory/workgraph/adapter.py:45`, and assign it where
      `AGENT_ERROR` is assigned today (`:1272`).
- [ ] T007 [US1] (FR-001, trap 1) Detect the case from the process outcome — no
      token produced, an untouched worktree — and use the adapter's message only
      to enrich the operator-facing text.
- [ ] T008 [US1] (FR-002, FR-004) Carry the reason, its remedy, and the
      no-agent-prepared-this-worktree context onto the record and render them.

## Phase 2: User Story 2 — A pre-agent failure does not consume the attempt budget

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1) In `tests/test_095_ladder_excludes_pre_agent.py`,
      assert a history of three pre-agent failures under a `max_attempts` of
      three still grants another attempt.
- [ ] T010 [P] [US2] (spec US2-S2) Assert a mixed history counts only the real
      attempts.
- [ ] T011 [P] [US2] (spec US2-S3) **The control.** Assert a history of only real
      attempts produces the same spent count as today.
- [ ] T012 [P] [US2] (spec US2-S4, trap 2) Assert an unbroken run of pre-agent
      failures escalates on its own bound rather than retrying without end.
- [ ] T013 [P] [US2] (spec US2-S5, trap 6) Assert that escalation names
      authentication and does not carry KILL as its default.
- [ ] T014 [P] [US2] (FR-005, trap 4) Assert the exclusion applies at every
      `_attempts_spent` call site, including any that passes no config.
- [ ] T015 [P] [US2] (FR-006) Assert the new bound is refused outside its range
      in the shape the other ladder dials are refused.

### Implementation for this story

- [ ] T016 [US2] (FR-005) Add the exclusion to `_attempts_spent`
      (`factory/verify/ladder.py:231-245`), following the two exclusions its
      docstring already argues for. If the exclusion needs config, resolve trap 4
      before relying on it.
- [ ] T017 [US2] (FR-006) Add the consecutive-pre-agent bound to the ladder
      config and its bounds table (`factory/verify/factory_yaml.py:127-141`),
      with a manifest omitting it behaving as a sensible default.
- [ ] T018 [US2] (FR-006) Escalate when that bound is spent, through
      `next_action`'s existing escalate path rather than a new exit.
- [ ] T019 [US2] (FR-007) Give the authentication escalation its cause and its
      remedy, and change its default away from KILL, saying so in the text.

## Phase 3: User Story 3 — An exhausted ladder names the rung that ended it

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S1) Assert an escalation raised with judge
      rewrites spent names that bound and its configured value.
- [ ] T021 [P] [US3] (spec US3-S2) Assert an escalation raised with deterministic
      attempts spent names that bound instead.
- [ ] T022 [P] [US3] (spec US3-S3) Assert an escalation raised with debugger
      cycles spent names that bound.
- [ ] T023 [P] [US3] (spec US3-S4) Assert the status view shows the ladder's
      dials beside the landing dials.
- [ ] T024 [P] [US3] (FR-008, trap 5) Assert the rendered reason comes from the
      ladder's own decision rather than a second derivation in the CLI.

### Implementation for this story

- [ ] T025 [US3] (FR-008, trap 5) Have the ladder report which bound ended the
      node alongside its decision, and carry that onto the escalation.
- [ ] T026 [US3] (FR-009) Render the three dials in the status view beside the
      landing dials.
- [ ] T027 [US3] (FR-010) Confirm the two things FR-010 names are unchanged by
      this epic and say so in the attempt report. Do not restate their paths
      here, because a task that names a file joins that file to its story's slice
      and this story edits neither.

### The operator's demonstration for this story

- [ ] T028 [US3] Run the dead-credential demonstration in the plan's
      § *Verification the operator will run* and paste the status output and any
      escalation text into the attempt report. The demonstration succeeds when
      the status names authentication, the attempt count has not run past the new
      bound, and the escalation names the remedy. Before this spec the same run
      shows four attempts, a typecheck failure naming a missing binary, and
      nothing about a credential anywhere.
