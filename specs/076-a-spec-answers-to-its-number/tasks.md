# Tasks: a spec answers to its number

**Spec**: `specs/076-a-spec-answers-to-its-number/spec.md`
**Plan**: `specs/076-a-spec-answers-to-its-number/plan.md`

Read the plan's traps before the first task. Trap 1 (ambiguity refuses, never
picks), trap 2 (the path form must not regress) and trap 5 (`show` must work with
no control plane) are the three that decide whether an attempt lands.

## Phase 1: User Story 1 — Every spec verb takes a number

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_spec_number_resolution.py`,
      supply a corpus and assert a verb given `075` operates on
      `075-a-stronger-rung-…`. Supply the corpus; never depend on this
      repository's own `specs/`, which changes under the test.
- [ ] T002 [P] [US1] (spec US1-S2) Assert `75` resolves the same as `075`.
- [ ] T003 [P] [US1] (spec US1-S3) **The control.** Assert the full-path form
      behaves exactly as today, including an absolute path outside the specs
      root (trap 2).
- [ ] T004 [P] [US1] (spec US1-S4) Assert an ambiguous prefix is refused naming
      every candidate — never resolved to one (trap 1).
- [ ] T005 [P] [US1] (spec US1-S5) Assert an unmatched number is refused naming
      the value and the specs root searched.
- [ ] T006 [P] [US1] (spec US1-S6) Assert a number resolves against a
      non-default `--specs-root` (trap 3).

### Implementation for this story

- [ ] T007 [US1] (FR-002) Write one resolver: leading numeric segment, leading
      zeros optional, returning the **real directory path** so
      `epic_id = spec_dir.resolve().name` (`factory/cli/nouns/spec.py:238`) still
      yields the full slug (trap 4). Import an existing `SPEC_NAME` — there are
      already two, at `factory/workgraph/cli.py:47` and
      `factory/roadmap/models.py:57`; do not add a third.
- [ ] T008 [US1] (FR-005) Try the path form first and fall back to number
      resolution only when it is not a directory, so no existing caller changes
      behaviour (trap 2).
- [ ] T009 [US1] (FR-003, FR-004) Refuse ambiguity by naming candidates, and
      refuse a miss by naming the value and the root.
- [ ] T010 [US1] (FR-001, FR-006) Apply it at the three argument sites —
      `factory/cli/nouns/spec.py:112` (validate), `:134` (derive), `:167`
      (landed) — and at `factory/cli/nouns/spec.py:231`, where `validate`
      currently does a bare `Path(args.spec_dir)`. Check which verbs actually
      carry `--specs-root` before assuming the flag is there (trap 3).

## Phase 2: User Story 2 — One spec's whole picture, in one command

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) In `tests/test_spec_show.py`, assert `show`
      reports state, story count, landed count and task count.
- [ ] T012 [P] [US2] (spec US2-S2) Assert landed is read against the declared
      landing branch, not `main`, over a corpus where the two differ (trap 6).
- [ ] T013 [P] [US2] (spec US2-S3) Assert a blocked spec's blockers are named.
- [ ] T014 [P] [US2] (spec US2-S4) **The control.** Assert `show` succeeds with
      no reachable control plane, reporting epic state unknown (trap 5). Prove it
      can fail by making the connection unconditional.
- [ ] T015 [P] [US2] (spec US2-S5) Assert a dispatched epic's state is reported
      when a control plane is reachable.
- [ ] T016 [P] [US2] (spec US2-S6) Assert `--json` emits the same facts.

### Implementation for this story

- [ ] T017 [US2] (FR-007) Add the `show` verb to `_add_spec_parser`
      (`factory/cli/nouns/spec.py:88-179`), taking a number or a path.
- [ ] T018 [US2] (FR-008) Read landed facts through the existing reader behind
      `landed_command` (`factory/workgraph/cli.py:151`) rather than a second
      implementation (trap 6).
- [ ] T019 [US2] (FR-009) Reach for the control plane, catch the failure, report
      unknown.
- [ ] T020 [US2] (FR-010) Emit `--json`.

## Phase 3: User Story 3 — The corpus view answers "what should I look at"

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1) In `tests/test_spec_list_filters.py`, assert
      each row carries a landed-versus-total count.
- [ ] T022 [P] [US3] (spec US3-S2) Assert `--state ready` renders only ready
      specs.
- [ ] T023 [P] [US3] (spec US3-S3) **The control.** Assert a filter matching
      nothing renders nothing and says so — never the unfiltered list (trap 7).
- [ ] T024 [P] [US3] (spec US3-S4) Assert the unflagged output is unchanged,
      including that a blocked spec still names its blockers on its line
      (trap 8).

### Implementation for this story

- [ ] T025 [US3] (FR-011) Add the count to each row in `render_command`
      (`factory/roadmap/cli.py:46`), taken from the same corpus pass that
      computes readiness — not a second walk (trap 9).
- [ ] T026 [US3] (FR-012) Add the state filter, rendering nothing and saying so
      on an empty match.

## Verification

- [ ] T027 (SC-001) Run each verb against a number and against the full path;
      paste both. They must agree.
- [ ] T028 (SC-002) Run a verb against an ambiguous prefix; paste the refusal.
- [ ] T029 (SC-003) Paste `ergane spec show` beside
      `ergane spec landed --default-branch ergane-buildout` for the same spec.
      The counts must agree.
- [ ] T030 (SC-004) Stop the control plane, run `show`, paste the output.
- [ ] T031 (SC-005) Paste `list --state ready` beside the unfiltered list.
