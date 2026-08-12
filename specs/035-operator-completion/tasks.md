# Tasks: An operator may finish what an agent could not — visibly, and counted

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

**Read plan.md trap 1 before anything else.** This is the one spec in the corpus
whose feature can quietly end the factory. If a change you are considering makes
this hatch *easier* to reach, that is a reason to reject the change.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm before dispatch and record the answers here. Four
      things. (1) That the signal precedent still holds: `workflow.py` carries
      `pause_epic`/`resume_epic`/`kill_epic` and the payload-bearing
      `escalation_resolved`/`question_answered`, and the name constants still
      live in `factory/notify/service.py` rather than in the workflow. (2) That
      `factory/verify/ladder.py`'s `next_action` is still the single computation
      of "out of road" — if a second notion of exhaustion has appeared, US1's
      guard must read the right one and the implementer must be told which.
      (3) That `verification_results` is still written through
      `factory/verify/store.py` with an explicit column list, so adding
      `provenance` is a schema change in one place. (4) **That this spec is
      still wanted.** It is the only spec here whose value falls as the factory
      improves; if the floor has stopped producing unbuildable stories, the
      right move is to close it rather than build it.

---

## Phase 2: User Story 1 — The operator hands finished work back, recorded as theirs (Priority: P1) 🎯 MVP

**Goal**: a stuck node has a third exit, and the record of what happened is
complete at the moment it happens.

**Independent Test**: signalling `complete_node_externally` for a node whose
ladder is exhausted drives it through VERIFYING to its normal terminal state
with provenance stored; the same signal against a healthy node is refused and
changes nothing.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` green
      in a clean env (plan.md trap 7 — scratch stores, no operator env), and
      plan.md's inventory anchors resolve — constitution II gate; STOP and
      report blocked if not satisfied.
- [ ] T003 [US1] Write the guard cases FIRST: the signal is **refused** for a
      node that is PENDING, for one that is RUNNING, and for one with attempts
      remaining — in each case the node is untouched and the refusal is recorded
      (spec US1-S3, FR-002). Refusal is the behaviour most likely to be built
      permissively, so it is tested before the happy path deliberately.
- [ ] T004 [US1] Write the acceptance case FIRST: for a node whose ladder is
      exhausted, the signal drives it through VERIFYING and on through the
      normal gates/judge/PR/queue path, reaching the same terminal states an
      agent-completed node reaches (spec US1-S1, FR-001).
- [ ] T005 [P] [US1] Write the provenance case FIRST: the stored
      `verification_results` row for an externally-completed node carries the
      provenance, and the column is **not nullable on this path** — a completion
      that stores no provenance must be impossible, not merely discouraged
      (spec US1-S2, FR-005, plan.md trap 2).
- [ ] T006 [P] [US1] Write the **failure** case FIRST, and treat it as the most
      important test in this story: externally-supplied work that breaks the
      gates **fails the node**, exactly as agent work would (spec US1-S4,
      FR-004, plan.md trap 4). If this test cannot be made to fail before the
      implementation exists, the feature is a merge bypass wearing a provenance
      field.

### Implementation for User Story 1

- [ ] T007 [US1] Implement the signal end to end until T003–T006 pass: the name
      constant beside its siblings in `factory/notify/service.py`; the handler
      beside `question_answered` in `workflow.py`, buffering without validating
      at receipt (the `escalation_resolved` precedent); the guard read where the
      ladder outcome is decided, reading `ladder.next_action`'s existing notion
      of exhaustion rather than a new one; and the `provenance` column added to
      `_RESULT_COLUMNS` in `factory/verify/store.py`.
- [ ] T008 [US1] Add the operator CLI verb beside `build.py`'s existing signal
      verbs. It MUST require the provenance argument rather than defaulting it,
      and MUST require the node and branch explicitly. The friction is the
      feature (plan.md trap 1).
- [ ] T009 [US1] Prove FR-003 structurally, and record it: grep the tree for any
      call path from ladder exhaustion, recovery cycles, attempt timeouts or
      escalation expiry to the completion signal. There must be none. State in
      the PR body what you grepped for and what you found — SC-003 is graded by
      that statement, not by a passing test (spec US1-S5, plan.md trap 3).

---

## Phase 3: User Story 2 — Every surface says it was built externally (Priority: P1)

Dispatches after US1 has **merged**.

**Goal**: nobody can mistake an externally-completed story for an agent-built
one, and nobody has to know to go looking.

**Independent Test**: for an externally-completed node the status output, commit
trailer, PR body and spec attestation each state it; for an agent-completed node
none of them do.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Verify prerequisites: US1 is **merged** in the base (the signal,
      the guard and the provenance column are present) and the suite is green —
      constitution II gate; STOP and report blocked if not.
- [ ] T011 [US2] Write the four surface cases FIRST, one assertion each: an
      externally-completed node is marked in `ergane build status` without a
      flag; its landing commit carries a provenance trailer; its PR body states
      external completion and the exhausted ladder; and its spec's `state:
      landed` attestation states the spec contains externally-completed work
      (spec US2-S1, US2-S2, US2-S3, US2-S4; FR-006).
- [ ] T012 [P] [US2] Write the negative case FIRST: an agent-completed node
      carries **none** of the four markings (spec US2-S5). A marking that fires
      on everything carries no information, and this is the test that keeps it
      meaningful.

### Implementation for User Story 2

- [ ] T013 [US2] Implement the four surfaces until T011 and T012 pass. The
      attestation change extends what `factory/workgraph/landed.py` already
      means by `state: landed` rather than adding a parallel notion — read
      `_attesting_commit` and the frontmatter contract before writing.

---

## Phase 4: User Story 3 — The count is a fact, and the target is zero (Priority: P2)

Dispatches after US1 has **merged**; independent of US2.

**Goal**: the escape hatch measures itself, so its own overuse is visible before
it becomes normal.

**Independent Test**: two external completions across two specs yield a total of
2 and per-spec counts of 1 each; a corpus that never used it reports 0.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T014 [US3] Verify prerequisites: US1 is **merged** in the base and the
      suite is green — constitution II gate; STOP and report blocked if not.
- [ ] T015 [US3] Write the counting cases FIRST: each external completion
      increments a durable count carrying spec, node, provenance and timestamp;
      the read surface reports total and per-spec breakdown (spec US3-S1,
      US3-S2; FR-007). **And the idempotence case**: recording the same completion twice
      counts once (plan.md trap 5 — a double-count invents a trend, and this
      count is the evidence for whether bail-outs are rising).
- [ ] T016 [P] [US3] Write the measured-zero case FIRST: a corpus that has never
      used the hatch reports an explicit `0`, distinguishable from a broken or
      absent counter, and the surface states that zero is the target (spec
      US3-S3, US3-S4; FR-008, plan.md trap 6).

### Implementation for User Story 3

- [ ] T017 [US3] Implement the counter and its read surface until T015 and T016
      pass. Copy the increment shape from `factory/doctor/store.py`'s recurrence
      machine but **not** its overwrite semantics — key the write so a repeat is
      a no-op rather than a second occurrence.
- [ ] T018 [US3] Final sweep + docs: `docs/decisions.md` gains a numbered entry,
      claimed at landing, recording that D-024's "no production code here is
      written by a human" now has one sanctioned, recorded, counted exception —
      and why it is deliberately awkward to reach. `docs/architecture.md` notes
      the third exit from a stuck node beside kill and escalate. Confirm no new
      dependency and the full suite green in a clean env (SC-004, SC-006).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything, including the question of
  whether this spec should be built at all.
- Phase 2 (US1) is the MVP and is safety-critical: it carries the mechanism and
  its provenance record together, because a merge window between them is
  unrecoverable (plan.md trap 2). T006 (external work can fail) and T009 (no
  automatic path) are the two tasks that keep this feature from being a merge
  bypass; neither is optional.
- Phase 3 (US2) and Phase 4 (US3) both chain on US1 **merged** and are
  independent of each other — either order, or concurrently.

## Implementation Strategy

The measure of success for this spec is that its own counter stays at zero.

It exists because on 2026-08-11 one story took four attempts, ~9h and 128M input
tokens and landed nothing, while the floor stayed blocked behind it — and the
operator, who could have finished it in minutes, had no way to hand the work
back. That is the case this is for: rare, expensive, and already diagnosed.

It is not for a story that is merely hard, and it is not a substitute for
refinement. Every use is a signal that a spec reached an agent in a state it
could not build, which is a refinement failure upstream. The count in US3 is
what turns that signal into something you can watch rather than something you
remember.
