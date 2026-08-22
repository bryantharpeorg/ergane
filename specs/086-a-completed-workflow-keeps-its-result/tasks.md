# Tasks: a completed workflow keeps its result

**Spec**: `specs/086-a-completed-workflow-keeps-its-result/spec.md`
**Plan**: `specs/086-a-completed-workflow-keeps-its-result/plan.md`

Read the plan's traps before the first task. Two decide whether the attempt
lands. Trap 3: the test reads the interceptor list off
`build_worker(env.client).config()` — the wired list is the contract, the
private class name is not. Trap 5: the round-trip test's failing run against
the unfixed tree is committed evidence, so it is written and run red before
anything is fixed.

## Phase 1: User Story 1 — The worker hands back what the workflow returned

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-002) In
      `tests/test_a_completed_workflow_keeps_its_result.py`, copy the
      time-skipping `env` fixture shape (`tests/test_worker.py:348-354`),
      define a test-local echo workflow returning a known non-None value,
      register it on a scratch task queue on a Worker whose `interceptors` are
      read off `build_worker(env.client).config()["interceptors"]` — a verified
      `WorkerConfig` key, the `tests/test_worker.py:368-369` pattern — execute
      it, and assert the
      client-observed result equals the returned value. **Run it against the
      unfixed tree and capture the red** — the observed None is SC-001's first
      half (trap 5).
- [ ] T002 [P] [US1] (spec US1-S2, FR-003) **The control.** Same harness, a
      workflow that genuinely returns None: assert the client observes None.
      This test passes before and after the fix; it is committed so a null
      result forever after means "the workflow said None".

### Implementation for this story

- [ ] T003 [US1] (FR-001) In `factory/worker.py`: make the inner
      `execute_workflow` (`:265`) `return await
      self.next.execute_workflow(input)` (`:270`), change its annotation from
      `-> None` to `-> Any`, and add `from typing import Any` to the import
      block (`:55-61` — the file imports no `typing` name today). Both
      properties are the SDK base class's own, quoted in the plan — restoring,
      not inventing. The injection branch at `:266-269` is 053-US3's landed
      behavior — untouched (trap 2 in the plan notes the operator tree's
      equivalent dirt; it is not yours to reconcile).

### Verification for this story

- [ ] T004 [US1] (FR-004, spec US1-S3, SC-003) Run
      `tests/test_ergane_build.py` and
      `tests/test_ergane_build_status_refusal.py` unmodified and paste the
      passing output naming both files — injection preserved by tests this
      story did not edit.
- [ ] T005 [US1] (SC-001) Paste the T001 test red against the unfixed tree and
      green after T003 — both runs in the diff.
- [ ] T006 [US1] (SC-002) Paste the None-control test passing.
