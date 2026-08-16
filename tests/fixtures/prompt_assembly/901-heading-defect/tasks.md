# Tasks: Runtime root integrity (reconstructed)

**This is the defect.** Every phase below names its story's *title* and never
the story key, so the assembler — which looks for a phase heading naming a user
story by number — finds no slice for any node. Scenario coverage still passes:
every acceptance-scenario id the spec declares is referenced by a task.

## Phase 1: The leak detector stops requiring the live store's absence

- [ ] T001 [P] Write the failing test: the detector passes on a host carrying a
      live store (spec US1-S1) — must fail.
- [ ] T002 Make it pass without deleting anything.

## Phase 2: The findings ledger is addressed through the resolver

- [ ] T003 [P] Write the failing test: a relocated root is read from
      (spec US2-S1) — must fail.
- [ ] T004 Route the ledger read through the resolver.

## Phase 3: The runtime root can be migrated

- [ ] T005 [P] Write the failing test: every store is present under the new root
      (spec US3-S1) — must fail.
- [ ] T006 Implement the migration.

## Phase 4: The migration refusal names the variable the operator set

- [ ] T007 [P] Write the failing test: the refusal names the variable
      (spec US4-S1) — must fail.
- [ ] T008 Name the variable in the refusal.

## Verification

- [ ] Final gate command passes green.
