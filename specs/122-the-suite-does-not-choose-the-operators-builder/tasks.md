# Tasks: the suite does not choose the operator's builder

**Spec**: `specs/122-the-suite-does-not-choose-the-operators-builder/spec.md`
**Plan**: `specs/122-the-suite-does-not-choose-the-operators-builder/plan.md`

Read the plan's traps first. Trap 3 (`PERSONA` is one module-level constant —
changing thirteen tests individually is the wrong diff and this repo refuses
oversized ones before the judge sees them), trap 4 (naming another real persona
moves the pin rather than removing it), trap 6 (the 089 tests must pass with a
real ledger present *and* absent) and trap 8 (US1-S4 is the anti-recurrence
guard and will look like over-engineering) are the four that decide whether this
lands.

The three stories touch three different files and have no merge edges. They
dispatch together.

## Phase 1: User Story 1 — The registry test asserts loading, not vendor

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S2) In
      `tests/test_122_registry_is_not_pinned.py`, assert a registry whose
      implementer is a subscription persona — model `claude-opus-5`, no slash —
      passes the shipped-registry checks. This is the case that fails today.
- [ ] T002 [P] [US1] (spec US1-S1) **The control.** Assert a gateway-routed
      implementer still passes, unchanged.
- [ ] T003 [P] [US1] (spec US1-S3, trap 1) Assert an entry with an empty model
      still fails. The resolve check is real and is kept.
- [ ] T004 [P] [US1] (spec US1-S4, FR-008, trap 8) **The anti-recurrence
      guard.** Read this suite's own assertions about the shipped registry and
      fail if any constrains a vendor, route or alias shape. Six recurrences
      were each fixed by deleting one literal; this is what makes the seventh
      fail here instead of blocking an operator.

### Implementation for this story

- [ ] T005 [US1] (FR-001, traps 1 and 2) Remove
      `assert "/" in registry["implementer"].model`
      (`tests/test_us2_shipped_registry.py:345`). Keep the line above it. Update
      the comment at `:338-343` so it no longer describes a rule the file then
      breaks — it already states this spec's argument correctly.

## Phase 2: User Story 2 — A fixture that needs a gateway persona names one

### Tests for this story (write FIRST, must fail)

- [ ] T006 [P] [US2] (spec US2-S3) Assert the usage tests pass with the
      implementer on the subscription route. Today thirteen of them fail.
- [ ] T007 [P] [US2] (spec US2-S2) **The control.** Assert they pass unchanged
      with a gateway implementer.
- [ ] T008 [P] [US2] (spec US2-S1, trap 4) Assert the persona these fixtures
      lease against is one the tests own, not a name read from the operator's
      registry.
- [ ] T009 [P] [US2] (spec US2-S4, FR-005, trap 5) Assert the suite still covers
      a subscription persona minting no virtual key. That coverage exists today
      only as an accident of the pin; make it deliberate.

### Implementation for this story

- [ ] T010 [US2] (FR-003, traps 3 and 4) Change `PERSONA`
      (`tests/test_usage_activities.py:74`) to a fixture-owned name in the same
      register as `MODELS = ["anthropic/CHANGEME", "local/CHANGEME"]` one line
      below. **One constant.** `ALIAS` on `:76` follows it. Do not edit the
      thirteen tests individually.

## Phase 3: User Story 3 — A test that reads a findings store builds its own

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US3] (spec US3-S1, trap 6) Assert the three failing 089 tests
      pass on a host with a populated `.factory/doctor.db`. They fail there
      today:
      `[fixes] spec declares unknown finding key(s): any/key (store: .factory/doctor.db)`
- [ ] T012 [P] [US3] (spec US3-S2, trap 6) **The other direction.** Assert they
      pass where no findings store exists — which is where they pass today, and
      passing only there is the defect.
- [ ] T013 [P] [US3] (spec US3-S3, FR-006) Assert no test in those two files
      resolves a store path under the operator's runtime root.
- [ ] T014 [P] [US3] (spec US3-S4, FR-007, trap 7) **The control.** Assert the
      fixes layer still reports `not checked` for an absent store rather than
      refusing. That behaviour is correct and must survive.

### Implementation for this story

- [ ] T015 [US3] (FR-006, trap 6) Point the three tests at a findings store
      built under `tmp_path`, seeded with whatever keys their fixture spec
      declares. 089's own plan asked for this as trap 7: "fixtures are supplied
      trees, never `.factory/`."

### The operator's demonstration for this story

- [ ] T016 [US3] Run the sequence in the plan's § *Verification the operator
      will run*, which swaps the implementer to the subscription route, runs the
      four affected files, and restores `personas.yaml`. Paste **both** the
      before and after runs into
      `specs/122-the-suite-does-not-choose-the-operators-builder/attempt-report-<story>.md`.
      Either alone proves nothing: a suite already green proves no fix, and one
      green only afterwards proves no regression was avoided. Before this spec
      the after-run reports 28 failed.
