# Tasks: managed Temporal is a path or a refusal

**Spec**: `specs/119-managed-temporal-is-a-path-or-a-refusal/spec.md`
**Plan**: `specs/119-managed-temporal-is-a-path-or-a-refusal/plan.md`

Read the plan's traps before the first task. Trap 1 (the wrapper fix is **not**
`"$@"` — positionals two and three are the working directory and the interpreter),
trap 3 (do not keep a silent default; a silent default is the defect), trap 6
(uninstall may not dial the service its own units run) and trap 7 (the verify fix
must fail closed) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — The declared mode reaches the layout, or the verb refuses

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_119_declared_mode.py`, assert a
      resolved layout carries managed mode when managed was declared.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the Temporal server unit is among the
      generated files for a managed layout.
- [ ] T003 [P] [US1] (spec US1-S3) **The control.** Assert an external
      declaration produces external mode and no Temporal unit.
- [ ] T004 [P] [US1] (spec US1-S4, trap 3) Assert an undeterminable mode is
      refused naming what could not be read, rather than defaulting.
- [ ] T005 [P] [US1] (spec US1-S5, trap 4) Assert the behaviour
      `_temporal_managed`'s docstring claims — a test, so prose and code cannot
      drift again.

### Implementation for this story

- [ ] T006 [US1] (FR-001, trap 2) Add the mode as a parameter of
      `resolve_layout` (`factory/supervision/units.py:255`), passed in by the
      caller that knows it. Do not make the resolver read configuration.
- [ ] T007 [US1] (FR-003, trap 3) Refuse when the mode cannot be determined,
      naming the source that could not be read.
- [ ] T008 [US1] (FR-004) Rewrite `_temporal_managed`'s docstring (`:324-332`) to
      describe the mechanism that now exists.

## Phase 2: User Story 2 — A unit's arguments reach the process

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1) In `tests/test_119_wrapper_forwards_args.py`,
      assert a unit passing a module and three flags delivers all three flags to
      the process.
- [ ] T010 [P] [US2] (spec US2-S2) **The control.** Assert a unit passing only a
      module name behaves exactly as today — worker and bridge take this path.
- [ ] T011 [P] [US2] (spec US2-S3, trap 1) **The wrong-fix catcher.** Assert a
      unit overriding the working directory and interpreter still applies both
      overrides *and* does not pass either to the module. A naive `"$@"` fails
      this.

### Implementation for this story

- [ ] T012 [US2] (FR-005, FR-006, trap 1) Correct the wrapper template ending at
      `factory/supervision/units.py:600`: capture the three positionals, consume
      them, and forward what remains.

## Phase 3: User Story 3 — The server can start, and verification proves it

### Tests for this story (write FIRST, must fail)

- [ ] T013 [P] [US3] (spec US3-S1) Assert a missing database directory is created
      when the server starts.
- [ ] T014 [P] [US3] (spec US3-S2, trap 5) Assert worker and bridge units each
      declare an ordering dependency on the Temporal unit in a managed
      installation, and that the generated unit says which systemd pair was used
      and why.
- [ ] T015 [P] [US3] (spec US3-S3, trap 7) Assert `--verify` fails, naming the
      unreachable server, when no server is running. It currently passes.
- [ ] T016 [P] [US3] (spec US3-S4) Assert `--verify` passes only after actually
      dialling a running server.
- [ ] T017 [P] [US3] (spec US3-S5, trap 8) Assert worker install reports every
      service it started and each service's state.
- [ ] T018 [P] [US3] (spec US3-S6, trap 6) Assert worker uninstall removes the
      units with Temporal unreachable.

### Implementation for this story

- [ ] T019 [US3] (FR-007) Create the database directory before the server needs
      it.
- [ ] T020 [US3] (FR-008, trap 5) Emit the ordering dependency in the generated
      worker and bridge units, with the reasoning in the unit's own comment.
- [ ] T021 [US3] (FR-009, trap 7) Make the managed-Temporal check at
      `factory/controlplane/verify.py:606-616` dial the server, and fail closed
      when it cannot be reached.
- [ ] T022 [US3] (FR-010, trap 8) Report every started service and its state at
      worker install's return.
- [ ] T023 [US3] (FR-011, trap 6) Remove the Temporal dial from worker
      uninstall's path.

### The operator's demonstration for this story

- [ ] T024 [US3] Run the fresh-host demonstration in the plan's § *Verification
      the operator will run* and paste the unit states and both `--verify`
      outputs — the passing one with the server up, and the failing one with the
      server deliberately stopped. A check that can only pass proves nothing, and
      the ability to fail is what this spec is buying. No gate can produce this,
      because it requires systemd and a real host.
