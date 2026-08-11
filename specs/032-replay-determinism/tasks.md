# Tasks: The epic's command sequence is a fact, not a race

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip. US1's
fail-first is the adversarial harness reproducing the CI signature — if it
cannot, the story stops and reports blocked rather than shipping a fix nothing
proved.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm the floor before dispatch and record the answers
      here. Three things: that no epic has an attempt in flight while this
      spec's stories run (018 parked with all nodes terminal; 031 killed or
      parked — this epic must be the only one dispatching), because trap 6's
      "do not restart the worker" only holds if nobody else needs one; that
      the three red CI runs' signature is still the incident's
      (`validate_target_repo` vs `teardown_attempt` — if a *different*
      mismatch pair has appeared since, the diagnosis neighborhood in plan.md
      §Approach widens and the implementer must be told); and that plan.md's
      inventory anchors still resolve at the dispatch commit —
      `validate_target_repo` scheduled from the onboarding step
      (`workflow.py:829` at c6ad7d6), node `create_task` sites (`:754`,
      `:758`), and the replay test at `tests/test_interpreter.py:2685`.

      **Verified 2026-08-11 ~5:55 PM CT (operator preflight, pre-dispatch):**
      all three hold. (1) Floor quiet: 018 paused with every node terminal,
      031 COMPLETED (us1 MERGED; us2 KILLED by operator choice at the flake
      escalation, remainder queued behind this spec) — this epic is the only
      one dispatching. (2) The latest red run (031/us2's landing, 22:43Z)
      carries the incident's exact signature: `validate_target_repo` vs
      `teardown_attempt`. Tally at dispatch: 5 red / 3 green on GitHub
      runners, 9/9 green locally. (3) Anchors resolve at the dispatch commit:
      `validate_target_repo` scheduled at `workflow.py:829`, `create_task` at
      `:754`, the replay test at `tests/test_interpreter.py:2685`.

---

## Phase 2: User Story 1 — Find the racy construct and make the command order a pure function (Priority: P1) 🎯 MVP

**Goal**: the activity-command sequence is invariant under scheduling
pressure, proven by a seeded adversarial harness that reproduces the CI
failure before the fix and cannot after.

**Independent Test**: the harness fails with the incident signature on the
pre-fix tree, passes 15 consecutive record-replay cycles on the fixed tree,
and the original replay test survives unmodified and green.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green in a clean env (plan.md trap 7 — scratch store, no operator env);
      the replay test passes unforced; plan.md's inventory claims hold —
      constitution II gate; STOP and report blocked if not satisfied.
- [ ] T003 [US1] Build the seeded adversarial-interleaving harness: a scripted
      world (or parameter on the existing one) applying deterministic,
      seed-derived completion delays to activities, biased across the
      epic-onboarding/node-dispatch boundary (plan.md §Approach step 1). The
      harness is a test instrument only — production code must not import,
      detect, or special-case it (spec Edge Cases) (spec US1-S1).
- [ ] T004 [US1] Write the reproduction case FIRST: sweep seeds until a
      recording under the harness produces a history whose replay fails with
      the incident's signature — `[TMPRL1100]` naming `validate_target_repo`
      against `teardown_attempt` — on this host, against the pre-fix tree.
      Record the reproducing seed(s) in the test as constants. This is the
      fail-first evidence for the whole spec (spec US1-S1, FR-002) — must
      fail (that is: the replay must break) before T006 may begin. If no seed
      in a reasonable sweep reproduces it, STOP and report blocked with the
      sweep's evidence — do not proceed to a fix nothing demonstrates.
- [ ] T005 [P] [US1] Write the determinism case FIRST: under the reproducing
      seed(s), 15 consecutive record-replay cycles all succeed — the
      assertion the fixed tree must meet (spec US1-S2). And the preservation
      case: `test_replay_dispatches_nothing_twice` is byte-unmodified in the
      diff and green (spec US1-S4, FR-004) — must fail on the pre-fix tree
      via T004's seed.

### Implementation for User Story 1

- [ ] T006 [US1] Diagnose with T004's reproducing seed in hand: find the
      construct whose command-emission order varies with wakeup order (plan.md
      §Approach step 2 — the docstring's suspect list is the checklist; the
      mismatch pair brackets the neighborhood). Then impose deterministic
      emission with the smallest change that makes the order a pure function
      of inputs and history (trap 4: same activities, same inputs, same
      outcomes — order only; no dispatch redesign, which is
      `temporal/node-child-workflows`' scope). Until T004's seeds go silent
      and T005 passes (spec US1-S2, US1-S3, FR-001, FR-003).
- [ ] T007 [US1] Run the full suite clean and confirm: green, no new
      dependency, the diff confined to `factory/workgraph/workflow.py` plus
      test files (spec US1-S3, US1-S4, SC-004). Record before/after runs of
      the harness in the story's evidence.

---

## Phase 3: User Story 2 — A worker restart cannot wedge the epics that recorded under the old order (Priority: P1)

**Goal**: pre-fix histories replay green through the fixed code, proven by
committed fixtures, standing in the suite forever.

**Independent Test**: the benign pre-fix fixture replays green through the
fixed workflow; the fixture test rides the default suite.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T008 [US2] Verify prerequisites: US1 is merged in the base (the harness
      and the fix are present; T004's seed constants importable) and the
      suite is green — constitution II gate; STOP and report blocked if not.
- [ ] T009 [US2] Capture and commit the fixture histories FIRST, generated
      from the *pre-fix* code (check out the base commit US1's merge names as
      its parent to record them, or regenerate via the harness with the fix
      reverted in a scratch worktree — the fixture's provenance commit must
      be named in a comment beside it): one benign-scheduling recording, and
      one adverse-seed recording if it yields a complete history. Then write
      the replay-compatibility case: the benign fixture replays green through
      the current workflow code (spec US2-S1, FR-005) — must fail if pointed
      at a deliberately order-perturbed workflow (prove the test can fail by
      temporary mutation, never committed), else it proves nothing.
- [ ] T010 [P] [US2] Write the standing-guard case: a temporary, uncommitted
      command-order mutation in the workflow turns the fixture replay red
      (spec US2-S3, FR-006). State in the docstring that this test is the
      gate-time tripwire for every future command-order change, and revert
      the mutation.

### Implementation for User Story 2

- [ ] T011 [US2] Wire the fixture replay into the default suite (no marker,
      no tier — it must run in every gate and every CI pass), storing
      fixtures under the test tree with their provenance comments. If the
      adverse-seed fixture cannot replay through the fixed code, implement
      the test as the documented-impossibility shape US2-S2 requires: assert
      the benign class, and carry the operator rule — no worker restart
      while an epic that recorded under adverse scheduling is in flight — in
      the test docstring and the landing notes (spec US2-S2).
- [ ] T012 [US2] Final sweep + docs: `docs/decisions.md` gains a numbered
      entry claimed at landing — an epic's command sequence is a pure
      function of inputs and history; pre-fix histories provably replay; the
      fixture guard stands in the suite — and `docs/architecture.md`'s
      workflow row notes the determinism guarantee and the fixture guard.
      Name 018 in the landing notes as the parked epic whose restart-safety
      US2-S1 proves. Confirm no new dependency and the full suite green in a
      clean env (spec US2-S1, US2-S2, US2-S3; SC-003, SC-004).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — its first check most of
  all: this epic must be the only one dispatching, because its whole subject
  is the machinery every other epic runs on.
- Phase 2 (US1) is the MVP and carries the spec's hardest task (T004): no
  reproduction, no story. Everything after T004 is ordinary engineering.
- Phase 3 (US2) chains on US1 **merged**: the fixtures' provenance is defined
  relative to US1's merge, and the compatibility test replays through US1's
  fixed code. The merge-edge is content, not just conflict avoidance.

## Implementation Strategy

US1 alone unblocks the floor: a green replay test on GitHub runners lets 031
relaunch, 018's remainder proceed, and the roadmap unpause. US2 is what makes
deploying US1 safe for the epic already parked across the boundary — small in
diff, decisive in consequence. Neither story changes what any node does, what
the judge scores, or what the merge queue writes; the entire observable change
is that the same commands now always arrive in the same order.
