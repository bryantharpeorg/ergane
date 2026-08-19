# Tasks: the world moving is not the code being wrong

**Spec**: `specs/069-the-world-moving-is-not-the-code-being-wrong/spec.md`
**Plan**: `specs/069-the-world-moving-is-not-the-code-being-wrong/plan.md`

Read the plan's traps before the first task. Trap 1 (every free path needs its
paired control), trap 2 (classify by cause, never by message text) and trap 3
(the free path needs its own bound) are the three that decide whether an attempt
lands.

## Phase 1: User Story 1 — A moved base costs a rebase, not an attempt

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_moved_base_is_not_charged.py`,
      reject an enqueued landing because the base moved and assert **both** the
      attempt count and the debugger-cycle count are unchanged. Assert the counts
      directly (`factory/verify/ladder.py:122-130`).
- [ ] T002 [P] [US1] (spec US1-S3) **The control.** Reject a landing because the
      node's own code fails a required check on an unchanged tree, and assert it
      IS charged as today (trap 1).
- [ ] T003 [P] [US1] (spec US1-S2) Assert the node rebases and requeues, not merely
      that it spent nothing. A node that stops cheaply is not a fix.
- [ ] T004 [P] [US1] (spec US1-S4) Assert a recovery that would produce a tree
      identical to the one the queue already rejected does not requeue, preserving
      `factory/workgraph/workflow.py:2539-2565` (trap 4).
- [ ] T005 [P] [US1] (spec US1-S5) Assert the free rebase path is bounded (trap 3).
- [ ] T006 [P] [US1] (spec US1-S6) Assert the classification is by cause, over at
      least two distinct moved-base causes and one code-fault cause, and that it
      does not depend on a retry count or a message match (trap 2).

### Implementation for this story

- [ ] T007 [US1] (FR-005) Classify rejections by cause at the rejection sites
      (`factory/workgraph/workflow.py:2163`, `:2629`), using the structural facts
      already present at `:2539-2565` — `rejected_tip` against the current base —
      rather than the forge's wording.
- [ ] T008 [US1] (FR-001, FR-002) Route a moved-base rejection to rebase-and-requeue
      without incrementing either counter.
- [ ] T009 [US1] (FR-003) Leave the code-fault path charged exactly as today.
- [ ] T010 [US1] (FR-004) Bound the free path.
- [ ] T011 [US1] (FR-006) Confirm the identical-tree refusal still fires.

## Phase 2: User Story 2 — Siblings that will collide are not raced

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1) In `tests/test_colliding_slices_are_ordered.py`,
      derive a graph whose two undeclared-independent stories name a common file
      and assert an ordering edge is inferred.
- [ ] T013 [P] [US2] (spec US2-S2) **The control.** Assert no edge is inferred
      between stories whose slices share no file (trap 6).
- [ ] T014 [P] [US2] (spec US2-S3) Assert an inferred edge is distinguishable from
      a declared one and states why it was inferred.
- [ ] T015 [P] [US2] (spec US2-S4) Assert validation reports a spec that declares
      stories disjoint while their slices overlap — the check 060 needed.
- [ ] T016 [P] [US2] (spec US2-S5) Assert an explicit declaration in the spec
      overrides the inference.
- [ ] T017 [P] [US2] (spec Edge Cases) Assert an inference that would create a cycle
      refuses naming both stories rather than emitting an uncompilable graph.

### Implementation for this story

- [ ] T018 [US2] (FR-007) Infer a `depends_on_merged` edge between stories whose
      task slices name a common file, reusing the existing slice parser rather
      than writing a second one (trap 7).
- [ ] T019 [US2] (FR-008) Mark inferred edges, state the reason, and honour an
      explicit override.
- [ ] T020 [US2] (FR-009) Report the declared-disjoint / actually-overlapping
      disagreement at validate time.

## Phase 3: User Story 3 — A reset epic can be rebuilt without hand-cleaning the forge

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1) In `tests/test_reset_clears_the_forge.py`, assert
      reset closes the node's open pull request with a comment naming the reset.
- [ ] T022 [P] [US3] (spec US3-S2) Assert the remote `factory/<epic>/<node>` branch
      is deleted or archive-renamed.
- [ ] T023 [P] [US3] (spec US3-S3) Assert a rebuilt node's push succeeds — no
      non-fast-forward rejection.
- [ ] T024 [P] [US3] (spec US3-S4) **The negative.** Assert a pull request outside
      the `factory/<epic>/<node>` namespace is untouched (trap 8).
- [ ] T025 [P] [US3] (spec US3-S5) Assert an unreachable forge still leaves the
      local reset complete, with the undone forge work reported (trap 9).
- [ ] T026 [P] [US3] (spec Edge Cases) Assert a second reset succeeds when the pull
      request is already closed and the branch already gone.

### Implementation for this story

- [ ] T027 [US3] (FR-010) Add the forge cleanup to `_reset_epic`
      (`factory/cli/nouns/build.py:878-900`), scoped to the
      `factory/<epic>/<node>` namespace.
- [ ] T028 [US3] (FR-011) Degrade rather than fail when the forge is unreachable.

## Verification

- [ ] T029 (SC-001) Paste the attempt and debugger counts before and after a
      moved-base rejection. Neither may move.
- [ ] T030 (SC-002) Paste the control: a code-fault rejection, still charged.
- [ ] T031 (SC-003) Land a three-way fan-out sharing one file at the shipped
      default `debugger_cycles: 1` and paste the result. This is the reported
      failure, reproduced and survived.
- [ ] T032 (SC-004) Paste the inferred edge for overlapping slices, and the
      absence of one for disjoint slices.
- [ ] T033 (SC-005) Reset an epic with an open node PR and remote branch, paste
      the forge calls, and push a rebuilt node.
