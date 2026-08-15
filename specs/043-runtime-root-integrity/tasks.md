# Tasks: 043-runtime-root-integrity

Each node works its own story's slice, test-first, and commits once per task. Read
`plan.md` before the first commit — its traps are the difference between a one-line
fix and a repeat of the defect this spec exists to close.

## Phase 1: User Story 1 — The leak detector stops requiring the live store's absence

- [ ] T001 Add a fixture that records the default store path's existence, size and
      modification time before the leaking-writer body runs (spec US1-S1).
- [ ] T002 Replace the non-existence assertion at `tests/test_store_isolation.py:201`
      with a non-mutation assertion built on T001's fixture, so the test's outcome
      depends on what the test did rather than on what the host already held
      (spec US1-S1).
- [ ] T003 Commit the pasted output of the test passing against a populated
      `.factory/verification.db` — a layout the test constructs in tmp, never the
      operator's live store (plan trap 10) — showing the recorded size and mtime
      identical before and after (spec US1-S1).
- [ ] T004 Add a control that introduces a writer resolving its path from the cwd
      default, assert the detector fails and names the offending path, and commit
      the pasted failure output (spec US1-S2).
- [ ] T005 Prove the test passes on a checkout with no runtime root directory and
      creates none, committing the pasted output (spec US1-S3).
- [ ] T006 Audit every non-existence assertion in `tests/test_store_isolation.py`
      and confirm each remaining one targets a pytest tmp path or a deliberately
      impossible path; record the audit in the diff (spec US1-S4, plan trap 8).
- [ ] T007 Reinstate the original assertion against the populated layout, capture
      the failure, and commit it as the control that the fix changed an outcome
      (spec US1-S1, SC-004, plan trap 6).

## Phase 2: User Story 2 — The findings ledger is addressed through the resolver

- [ ] T008 Write the split-state test first — `.ergane/` present without a ledger,
      `.factory/doctor.db` populated to recurrence three — and watch it fail before
      changing any path default (spec US2-S5, plan trap 1).
- [ ] T009 Write the new-root test: a tmp layout holding `.ergane/doctor.db`
      populated to recurrence three and no `.factory/` at all; the doctor reads it
      through the resolver and the recurrence count is intact (spec US2-S1).
- [ ] T010 Route `factory/cli/doctor.py:41` through `resolve_factory_root()`,
      chdir-ing into tmp in every test that touches it (spec US2-S1, plan trap 2).
- [ ] T011 Route `factory/doctor/cli.py:40` the same way (spec US2-S1).
- [ ] T012 Route all **five** `probes.py` literals the same way — `:133`, `:134`,
      `:135`, `:268` and `:375`; walk the module rather than grepping for the
      literal, and leave the prose at `:370` and `:415` alone (spec US2-S3, plan
      trap 9).
- [ ] T013 Implement FR-006 — follow the populated ledger or refuse naming both
      paths — and state which route you took and why in the commit message
      (spec US2-S5).
- [ ] T014 Prove a legacy-only repo still reads `.factory/doctor.db` and emits the
      one-time deprecation, resetting the warning sentinel in a fixture
      (spec US2-S2, plan trap 3).
- [ ] T015 Prove an explicit `--db` argument still wins over the resolver
      (spec US2-S4).
- [ ] T016 Assert in a test that none of the three doctor modules carries a path
      default built from a runtime-root directory literal (spec US2-S3).

## Phase 3: User Story 3 — `ergane repo migrate-runtime-root` can start

- [ ] T017 Write the closed-port test first, leaving `_temporal_client_factory` at
      its default, and watch it raise `NameError` before you fix anything
      (spec US3-S1, plan trap 5).
- [ ] T018 Add the missing `import os` to `factory/cli/repo.py` and confirm T017 now
      raises `OperatorError` naming the address and carrying `EXIT_TRANSPORT`
      (spec US3-S1).
- [ ] T019 Add a test that walks `factory/cli/repo.py`'s AST and fails if any global
      name it references is neither imported nor defined in the module
      (spec US3-S3, FR-004).
- [ ] T020 Run the verb without `--yes` against a scratch repo holding only a legacy
      runtime root and a reachable Temporal with no epics open; commit the pasted
      dry-run output (spec US3-S2, plan trap 7).

## Phase 4: User Story 4 — The migration refusal names the variable the operator set

- [ ] T021 Teach the resolver to report which variable supplied the override, or
      read the precedence from `factory/env.py`; state the route and the reason in
      the commit message (spec US4-S1, plan route choices).
- [ ] T022 If you changed the resolver's signature, fix every unpacking caller in
      the same diff — `factory/activities/agent_activities.py:171` (the dispatch
      path), `factory/cli/repo.py:143` and
      `factory/activities/merge_activities.py:310` all unpack the tuple;
      `merge_activities.py:375` and `:485` take `[0]` and survive — and prove the
      dispatch path still works (spec US4-S1, plan route choices).
- [ ] T023 Prove the refusal names `ERGANE_ROOT` and quotes its value when only
      `ERGANE_ROOT` is set (spec US4-S1).
- [ ] T024 Prove it names `FACTORY_ROOT` when only `FACTORY_ROOT` is set
      (spec US4-S2).
- [ ] T025 Prove it names `ERGANE_ROOT` when both are set, matching
      `factory/env.py:resolve_env_path` precedence (spec US4-S3).

## Verification

- [ ] Final gate command passes green.
