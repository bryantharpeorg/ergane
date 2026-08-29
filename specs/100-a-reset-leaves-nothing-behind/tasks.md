# Tasks: a reset leaves nothing behind

**Spec**: `specs/100-a-reset-leaves-nothing-behind/spec.md`
**Plan**: `specs/100-a-reset-leaves-nothing-behind/plan.md`

Read the plan's traps before the first task. Trap 1 (delete a remote ref only
when its tip is reachable from an archive ref — "teardown ran" is not that
claim), trap 3 (never force-push, never delete an archive ref), trap 5 (classify
narrowly and fall back to retryable when unsure) and trap 6 (escalating is not
swallowing the failure) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — A killed node leaves no remote ref behind

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_100_teardown_clears_origin.py`,
      build a repository with a local `origin`, push a node branch, archive it,
      run teardown, and assert the remote branch is gone while the archive ref
      still resolves.
- [ ] T002 [P] [US1] (spec US1-S2) Assert a fresh dispatch of the same node then
      pushes successfully.
- [ ] T003 [P] [US1] (spec US1-S3, trap 1) **The safety proof.** Assert a remote
      branch whose tip is not reachable from any archive ref is left alone and
      reported.
- [ ] T004 [P] [US1] (spec US1-S4) Assert a node whose branch was never pushed
      tears down unchanged and reports no remote work.
- [ ] T005 [P] [US1] (spec US1-S5) Assert teardown run twice over the same node
      succeeds both times.
- [ ] T006 [P] [US1] (FR-003, trap 2) Assert an unreachable origin does not fail
      teardown: it reports what it could not reach and completes.

### Implementation for this story

- [ ] T007 [US1] (FR-001, trap 1) In teardown
      (`factory/workgraph/worktree.py:1354-1370`), after the local archive, ask
      git whether the remote tip is reachable from the archive namespace and
      delete the remote branch only when it is.
- [ ] T008 [US1] (FR-002) Report a remote branch left in place, naming it and
      the reason.
- [ ] T009 [US1] (FR-003, trap 2) Keep teardown idempotent and non-fatal when
      origin cannot be reached.

## Phase 2: User Story 2 — A refused push says why

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) In `tests/test_100_push_reports_refusal.py`,
      drive a push refused by the remote and assert git's own stderr is carried
      into the raised error.
- [ ] T011 [P] [US2] (spec US2-S2) Assert the node's terminal reason names the
      refusal rather than reading as a generic activity failure.
- [ ] T012 [P] [US2] (spec US2-S3, trap 4) **The control.** Assert a successful
      push emits no more output than it does today.

### Implementation for this story

- [ ] T013 [US2] (FR-004, trap 4) In `push_branch`
      (`factory/workgraph/worktree.py:509`), capture git's stderr on failure and
      carry it into the error, without making the success path noisier.
- [ ] T014 [US2] (FR-005) Ensure the captured reason reaches the node's terminal
      reason rather than being flattened on the way.

## Phase 3: User Story 3 — A deterministic ref conflict escalates instead of killing the epic

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US3] (spec US3-S1, trap 5) Assert a push refused non-fast-forward
      fails non-retryably.
- [ ] T016 [P] [US3] (spec US3-S2, trap 6) Assert the node escalates rather than
      terminating, and that the underlying failure is still recorded.
- [ ] T017 [P] [US3] (spec US3-S3) Assert the escalation names the ref, the
      reason and the command that clears it.
- [ ] T018 [P] [US3] (spec US3-S4, trap 5) **The control.** Assert a transient
      push failure remains retryable, and that an unclassifiable stderr falls
      back to the retryable path.
- [ ] T019 [P] [US3] (spec US3-S5, trap 7) Assert no PENDING sibling is killed
      when a node escalates on a ref conflict. If the cascade still fires,
      report it as a finding rather than softening this assertion.

### Implementation for this story

- [ ] T020 [US3] (FR-007, trap 5) Carve the non-fast-forward refusal out of
      `PUSH_FAILED` in `factory/activities/merge_activities.py`, following the
      precedent whose rationale is written at `:90-95`, and update `land_node`'s
      docstring at `:430-434` to say which errors are now retryable.
- [ ] T021 [US3] (FR-008) Route the new failure to an escalation carrying the
      ref, the reason and the clearing command.
- [ ] T022 [US3] (FR-009, FR-010) Confirm every other push failure keeps today's
      retryable path, and that no force push and no archive-ref deletion was
      added anywhere in this epic. Say so in the attempt report.

### The operator's demonstration for this story

- [ ] T023 [US3] Run the kill-and-redispatch demonstration in the plan's
      § *Verification the operator will run* and paste all three outputs into the
      attempt report, including the empty `ls-remote` — the absence of the stale
      ref is the evidence. The demonstration succeeds when the second dispatch
      lands. Before this spec it fails at the push *after* passing verification,
      which is what makes the defect expensive: the work is done and discarded.
