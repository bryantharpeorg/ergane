# Tasks: the landing dials belong to the operator

**Spec**: `specs/081-the-landing-dials-belong-to-the-operator/spec.md`
**Plan**: `specs/081-the-landing-dials-belong-to-the-operator/plan.md`

Read the plan's traps before the first task. Trap 1 (**do not change a
default**), trap 2 (**storing the value is not implementing the dial**) and trap
3 (all three `EpicInput` sites) are the three that decide whether an attempt
lands.

## Phase 1: User Story 1 — A hand-started epic runs the dials its operator set

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) In
      `tests/test_landing_dials_reach_the_epic.py`, assert a dial set at dispatch
      reaches the constructed `EpicInput`.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) **The control.** Assert that with
      nothing set, all four dials hold today's values — `squash`, `60`, `7200`,
      `1`. Name all four explicitly (trap 1).
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) **Drive the behaviour, not the
      dataclass.** Assert a node recovers twice under a raised
      `max_recovery_cycles` and once under the default, through the recovery path
      at `factory/workgraph/workflow.py:2813` / `:2851` (trap 2).
- [ ] T004 [P] [US1] (spec US1-S4, FR-003) Assert a landing classifies as stalled
      at a lowered `stall_after_s`, driving the classifier. Find and cite the
      comparison — this plan deliberately does not guess its line (trap 6).
- [ ] T005 [P] [US1] (spec US1-S5, FR-004) Assert an invalid dial is refused by
      name at the command: a negative interval, a zero poll, an unknown merge
      method. `factory/cli/nouns/build.py:226-230` is the existing refusal shape
      (trap 4, trap 8).
- [ ] T006 [P] [US1] (spec US1-S6, FR-005) Assert none of the three `EpicInput`
      construction sites drops an operator-set landing config:
      `factory/cli/nouns/build.py:592`, `factory/workgraph/cli.py:571`,
      `factory/roadmap/workflow.py:1258` (trap 3).

### Implementation for this story

- [ ] T007 [US1] (FR-001) Add the flags to `build start`, following
      `factory/cli/nouns/build.py:1405-1406`'s shape.
- [ ] T008 [US1] (FR-004) Validate them at the command.
- [ ] T009 [US1] (FR-005) Pass the landing config at
      `factory/cli/nouns/build.py:592` and at `factory/workgraph/cli.py:571`.
- [ ] T010 [US1] (FR-002) Leave every default exactly where it is
      (`factory/mergequeue/models.py:388-391`).

### Verification for this story

- [ ] T011 [US1] (SC-001) Paste an epic started with a raised recovery bound and
      the running epic's landing config showing it.
- [ ] T012 [US1] (SC-002) Paste the control run with no dials, showing all four
      defaults.
- [ ] T013 [US1] (SC-003) Paste the recovery-path evidence **both ways**: a
      second recovery cycle granted under a raised bound, and refused under the
      default. The comparison is the evidence (trap 10).
- [ ] T014 [US1] (SC-004) Paste a stall classified at a lowered threshold.
- [ ] T015 [US1] (SC-005) Paste an invalid dial refused by name at the command.

## Phase 2: User Story 2 — A scheduled epic runs the dials its operator set

**Depends on US1 having merged** (`depends_on_merged`). Both stories reach
`EpicInput`'s landing config (trap 3, trap 11).

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US2] (spec US2-S1, FR-006) In
      `tests/test_scheduled_epics_carry_the_dials.py`, assert a roadmap-dispatched
      child epic carries an operator-set dial.
- [ ] T017 [P] [US2] (spec US2-S2, FR-006) **The control.** Assert that with
      nothing set, the child carries today's defaults.
- [ ] T018 [P] [US2] (spec US2-S3, FR-007) Assert whether a dial change reaches
      an already-running epic or only the next dispatch — **whichever it is, the
      test states it and the spec section says it in words** (trap 5).
- [ ] T019 [P] [US2] (spec US2-S4, FR-006) Assert `factory/cli/roadmap.py:247` no
      longer constructs `LandingConfig()` bare.

### Implementation for this story

- [ ] T020 [US2] (FR-006) Give the roadmap path an operator surface for the dials
      and carry them to `factory/roadmap/workflow.py:1258`.
- [ ] T021 [US2] (FR-007) Write down, in the code and in the diff, what a change
      does to a running epic.

### Verification for this story

- [ ] T022 [US2] (SC-006) Paste a roadmap-dispatched child epic carrying an
      operator-set dial.

## Phase 3: User Story 3 — The dials in force are readable

**Depends on US2 having merged** (`depends_on_merged`). Shares
`factory/cli/nouns/build.py` with US1.

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1, FR-008) In
      `tests/test_status_shows_the_dials_in_force.py`, assert the rendered status
      output shows the landing dials a running epic is using.
- [ ] T024 [P] [US3] (spec US3-S2, FR-009) Assert a defaulted value is shown as
      defaulted and a set value as set. Distinguishing "set to 60" from
      "defaulted to 60" is the value of the line.
- [ ] T025 [P] [US3] (spec US3-S3, FR-010) **The control.** Assert a status query
      that cannot read the dials still renders the rest of the epic. Spec 052
      landed that principle; do not regress it (trap 9).

### Implementation for this story

- [ ] T026 [US3] (FR-008, FR-009) Render the dials and their provenance.
- [ ] T027 [US3] (FR-010) Degrade rather than raise.

### Verification for this story

- [ ] T028 [US3] (SC-007) Paste status output showing the dials in force, once
      for a set value and once for a default.
</content>
