# Tasks: A scheduler that cannot report its own success

Two stories, strictly serial: US2's guard would fail on the un-fixed tree, so it
chains on US1 **merged**. Work test-first within a story and commit once per
task.

## Format: `[ID] [P?] [Story] Description`

Read `plan.md` before starting. Traps 1 and 2 rule out the two fixes that
suggest themselves first, and trap 8 says the transcripts are deliverables
rather than steps you performed.

## Phase 1: User Story 1 — The success path must not read the environment (Priority: P1) 🎯 MVP

The schedule has been paused since 2026-08-13 17:53Z and stays paused until this
lands. Nothing in the factory dispatches unattended before it.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [US1] Confirm the base is right: `grep -n 'def _isolated_test_store'
      tests/conftest.py` must find 030's session fixture. If it does not, your
      worktree predates 030 and your test will fight the store guard — stop and
      say so.

- [ ] T002 [US1] Write the regression test FIRST, beside the existing roadmap
      tests. It must use a real `WorkflowEnvironment` with the workflow sandbox
      ENABLED — not a stub, not `sandboxed=False` (plan trap 2). Script a prior
      recorded failure, then drive a roadmap pass to clean completion so
      `_report_run_success` is reached (plan trap 3). Assert the run reaches a
      completed state (spec US1-S2). Do not redirect the evidence store; 030's
      fixture already did, and pointing at a real path is now refused outright.

- [ ] T003 [US1] Run it against the unfixed code and capture the failure
      verbatim — it must be `RestrictedWorkflowAccessError` naming
      `os.environ.get` (spec US1-S3, first half). If it passes, the test does not
      exercise the sandbox and T002 is not done.

### Implementation for User Story 1

- [ ] T004 [US1] Remove both workflow-scope reads. Take the route argued in the
      plan's Approach — making `db_path` optional on the two activity inputs and
      resolving inside the activity is the smaller diff — or carry the path on
      `RoadmapInput`, which also satisfies FR-002 but must fill both
      construction sites (`factory/cli/roadmap.py:180` and
      `factory/roadmap/workflow.py:871`) and default the new field so recorded
      histories still deserialize (spec US1-S1). Do not disable the sandbox or
      mark any module pass-through (spec US1-S4, plan trap 1). State which route
      you took, and why, in the commit message.

- [ ] T005 [US1] Delete `_verification_db_path` if nothing else calls it
      (`grep -rn '_verification_db_path' factory/`). A dead workflow-scope
      environment reader left in the module is an invitation to reintroduce the
      bug.

- [ ] T006 [US1] Verify FR-009's fence held: `uv run pytest -q
      tests/test_roadmap_failure_notifications.py` green, unchanged. The failure
      count, its reset semantics and the notice text are 031's contract and are
      not yours to improve here (plan trap 4).

- [ ] T007 [US1] Produce the FR-004 evidence and COMMIT IT: run the new test
      green, revert only the T004 change and run it again capturing the
      `RestrictedWorkflowAccessError`, restore the fix and run it green. Paste
      all three runs verbatim into a comment block in the test file (spec US1-S3)
      — the judge sees the diff and nothing else (plan trap 8).

- [ ] T008 [US1] Full suite green: `uv run pytest -q`. No env scrubbing needed
      as of 030.

## Phase 2: User Story 2 — No workflow module may read the environment again (Priority: P2)

Chains on US1 merged.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T009 [US2] Verify the base first: `grep -rn 'environ' factory/roadmap/workflow.py`
      must show no workflow-scope read. If it still does, US1 has not merged into
      your base — stop; the guard cannot be written green against a broken tree.

- [ ] T010 [US2] Write the guard FIRST. Discover workflow-defining modules by
      scanning `factory/` for the workflow decorator — never by naming the known
      modules (plan trap 6) — and assert the discovery is non-empty, so a
      scanner that finds nothing cannot pass silently. Parse each with `ast`,
      collect functions reachable at workflow scope, and flag reads of
      `os.environ` / `environ.get` / `os.getenv`. Fail naming the module and the
      function (spec US2-S1, and US2-S3's naming half).

- [ ] T011 [US2] Prove it does not over-reach (plan trap 7, FR-008): add a case
      showing an environment read in an *activity* function and one at module
      import time are both accepted (spec US2-S4). `notify_activities._store_path`
      does this legitimately today and must not be flagged.

### Implementation for User Story 2

- [ ] T012 [US2] Produce the two-way evidence and COMMIT IT: the guard green on
      the fixed tree, then red — naming the function — with a read reintroduced
      into a workflow-scoped function, then green again once reverted (spec
      US2-S2, US2-S3). Paste all three verbatim into a comment block in the test
      file.

- [ ] T013 [US2] Full suite green: `uv run pytest -q`. The guard reads source
      and runs no workflow, so it must add no live-service dependency and no
      measurable time (SC-003).

## Verification

- [ ] Final gate command passes green.
- [ ] Both transcripts are in the diff, verbatim, not described.
- [ ] The sandbox is still enabled and no module was marked pass-through.
