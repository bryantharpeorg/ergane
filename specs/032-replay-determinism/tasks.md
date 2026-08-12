# Tasks: The epic's command sequence is a fact, not a race

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

**One clarification for US1, because misreading it has already cost four
attempts.** Two different things are easy to conflate here:

- **T005 is a normal fail-first test.** The 3-cycle determinism case fails on
  the unfixed tree and passes once T006 lands the fix. Both live in the same
  diff, so the suite you hand to the gate is green. This is ordinary
  constitution II and you should follow it exactly.
- **T004 is not a test at all.** Reproducing the defect produces an *evidence
  file*, committed under `evidence/`. Do not express it as a test that stays
  red — the gate runs the suite over your diff and a red suite fails the
  attempt. The previous version of these tasks asked for exactly that, which is
  why four attempts in a row shipped tests-only diffs and were rejected.

If the harness cannot reproduce the signature at all, the story stops and
reports blocked rather than shipping a fix nothing proved.

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

      **RE-VERIFIED 2026-08-12 after the epic was killed at attempt 4 and this
      trio was re-split.** All three still hold, and none of the numbers moved —
      nothing landed in the interval, which is the whole reason they didn't.
      (1) Floor quiet: 032 killed (worktree swept, keys revoked, sidecar
      cleared), 018 still paused with every node terminal, 031 still Completed
      with us2 on open PR #40. Nothing is dispatching. (2) Signature unchanged:
      PRs #40 and #38 both fail on `test_replay_dispatches_nothing_twice` with
      `validate_target_repo` vs `teardown_attempt`, 1 failed / 2126 passed —
      still the incident, still the only red. (3) Anchors re-grepped and current:
      `workflow.py:829` (`validate_target_repo`), `:754`/`:758` (`create_task`),
      `tests/test_interpreter.py:2685` (replay test), `:837` (`ScriptedWorld`),
      `:1659` (`start_time_skipping`).

      **One thing this preflight did NOT catch last time, recorded so the next
      one does:** it verified the tree, the floor and the signature — but not
      whether the story was *satisfiable*. It was not. Before flipping ready,
      ask of each story: can one diff satisfy both the gate and the judge? For
      the old US1 the answer was no, and four attempts paid to discover it.

---

## Phase 2: User Story 1 — Make the command order a pure function, diagnosis evidenced (Priority: P1) 🎯 MVP

> **Re-scoped 2026-08-12 after four failed attempts.** The previous version of
> T004 told you to leave a *failing* reproduction test in the diff. The gate runs
> the suite over that diff, so that instruction could not be satisfied together
> with a green gate — and all four attempts died on the contradiction, every one
> of them shipping a tests-only diff. **Read plan.md trap 8 before starting.**
> The reproduction is now a committed evidence file; the fix is mandatory.

**Goal**: the activity-command sequence is invariant under scheduling
pressure — proven by a seeded adversarial harness whose pre-fix failure is
captured as committed evidence, and which is green after the fix.

**Independent Test**: the full suite is green including
`test_replay_dispatches_nothing_twice`; the harness passes 3 consecutive
record-replay cycles at a fixed seed; the committed evidence file shows the
same harness reproducing the signature before the fix; and the diff changes
`factory/workgraph/workflow.py`.

### Tests for User Story 1 (write FIRST)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green in a clean env (plan.md trap 7 — scratch store, no operator env);
      the replay test passes unforced; plan.md's inventory claims hold —
      constitution II gate; STOP and report blocked if not satisfied.
- [ ] T003 [US1] Build the seeded adversarial-interleaving harness: a scripted
      world (or parameter on the existing one) applying deterministic,
      seed-derived completion delays to activities, biased across the
      epic-onboarding/node-dispatch boundary (plan.md §Approach step 1). The
      harness is a test instrument only — production code must not import,
      detect, or special-case it (spec US1-S4).
- [ ] T004 [US1] Reproduce the defect and **capture it to a file**: sweep seeds
      until a recording under the harness produces a history whose replay fails
      with the incident's signature — `[TMPRL1100]` naming
      `validate_target_repo` against `teardown_attempt` — on this host, against
      the still-unfixed tree. Write the seed, the exact command, and the
      **verbatim** failure output to
      `specs/032-replay-determinism/evidence/pre-fix-repro.txt` and commit it
      (spec US1-S3, FR-002).
      **Do NOT leave a failing test in the diff to represent this.** That is the
      instruction that killed four attempts: the gate runs the suite over your
      diff and a red suite fails you. Capture, commit, move on.
      If no seed in a reasonable sweep reproduces it, STOP and report blocked
      with the sweep's evidence — do not proceed to a fix nothing demonstrates.
- [ ] T005 [P] [US1] Write the determinism case: at T004's seed, **3**
      consecutive record-replay cycles all succeed — the assertion the fixed
      tree must meet (spec US1-S2). Three, not fifteen; the 15-cycle standing
      proof is US2's, deliberately kept off the story that must clear a red
      check to land. And the preservation case:
      `test_replay_dispatches_nothing_twice` is byte-unmodified in the diff and
      green (spec US1-S6, FR-004).

### Implementation for User Story 1

- [ ] T006 [US1] **Change production code.** Diagnose with T004's reproducing
      seed in hand: find the construct whose command-emission order varies with
      wakeup order (plan.md §Approach step 3 — the docstring's suspect list is
      the checklist; the mismatch pair brackets the neighborhood). Then impose
      deterministic emission with the smallest change that makes the order a
      pure function of inputs and history (trap 4: same activities, same
      inputs, same outcomes — order only; no dispatch redesign, which is
      `temporal/node-child-workflows`' scope). Until T004's seed goes silent
      and T005 passes (spec US1-S1, US1-S2, US1-S5, FR-001, FR-003).
- [ ] T007 [US1] Run the full suite clean and confirm three things, in this
      order — the first two are what four failed attempts missed:
      1. `git diff --name-only` lists at least one path under `factory/`. If it
         does not, the story is not done, whatever the suite says. All four
         failed attempts had a green suite.
      2. `specs/032-replay-determinism/evidence/pre-fix-repro.txt` exists and
         contains real `[TMPRL1100]` output — not a description of it.
      3. Suite green, no new dependency, diff confined to
         `factory/workgraph/workflow.py` plus test files and that evidence file
         (spec US1-S5, US1-S6, SC-004).

---

## Phase 3: User Story 2 — The harness becomes a standing regression (Priority: P2)

**Goal**: the determinism US1 established cannot silently regress — the next
ordering change fails at the gate, not at 3 a.m. in a live epic.

**Independent Test**: the suite carries a 15-cycle record-replay run at a fixed
seed plus a committed pre-fix fixture history, and is green in a clean env.

### Tests for User Story 2 (write FIRST)

- [ ] T008 [US2] Verify prerequisites: US1 is **merged** in the base (the
      harness, the fix and the evidence file are present; T004's seed is
      readable from the evidence file) and the suite is green — constitution II
      gate; STOP and report blocked if not.
- [ ] T009 [US2] Promote the harness to a standing regression: **15**
      consecutive record-replay cycles at a fixed seed, running in the default
      suite with no marker and no tier, so it executes in every gate and every
      CI pass (spec US2-S1, FR-008). Prove it can fail by a temporary,
      **never-committed** command-order mutation, then revert it.

### Implementation for User Story 2

- [ ] T010 [US2] Capture and commit the pre-fix benign fixture history and wire
      its replay into the default suite (spec US2-S2, FR-008). Provenance: use
      `git worktree add` at US1's base ref to reach pre-fix code, and name the
      commit in a comment beside the fixture. Never fabricate a fixture. Keep
      the run inside the gate's time budget — if 15 cycles do not fit, **the
      cycle count gives, not the `tmp_path` store isolation** (spec US2-S3,
      FR-007, plan.md trap 7).

---

## Phase 4: User Story 3 — A worker restart cannot wedge the epics that recorded under the old order (Priority: P1)

**Goal**: pre-fix histories replay green through the fixed code, proven by
committed fixtures, standing in the suite forever.

**Independent Test**: the benign pre-fix fixture replays green through the
fixed workflow; the fixture test rides the default suite.

### Tests for User Story 3 (write FIRST)

- [ ] T011 [US3] Verify prerequisites: US1 is **merged** in the base (the fix
      is present) and the suite is green — constitution II gate; STOP and
      report blocked if not. This story does **not** depend on US2; if US2 has
      already landed its fixture, reuse it rather than committing a second one.
- [ ] T012 [US3] Capture the fixture history from the *pre-fix* code (check out
      the base commit US1's merge names as its parent to record it, or
      regenerate via the harness with the fix reverted in a scratch worktree —
      the fixture's provenance commit must be named in a comment beside it).
      Then write the replay-compatibility case: the benign fixture replays
      green through the current workflow code (spec US3-S1, FR-005) — prove the
      test can fail by a temporary, never-committed order perturbation, else it
      proves nothing.
- [ ] T013 [P] [US3] Write the standing-guard case: a temporary, uncommitted
      command-order mutation in the workflow turns the fixture replay red
      (spec US3-S3, FR-006). State in the docstring that this test is the
      gate-time tripwire for every future command-order change, and revert
      the mutation.

### Implementation for User Story 3

- [ ] T014 [US3] Wire the fixture replay into the default suite (no marker,
      no tier — it must run in every gate and every CI pass), storing
      fixtures under the test tree with their provenance comments. If the
      adverse-seed fixture cannot replay through the fixed code, implement
      the test as the documented-impossibility shape US3-S2 requires: assert
      the benign class, and carry the operator rule — no worker restart
      while an epic that recorded under adverse scheduling is in flight — in
      the test docstring and the landing notes (spec US3-S2).
- [ ] T015 [US3] Final sweep + docs: `docs/decisions.md` gains a numbered
      entry claimed at landing — an epic's command sequence is a pure
      function of inputs and history; pre-fix histories provably replay; the
      fixture guard stands in the suite — and `docs/architecture.md`'s
      workflow row notes the determinism guarantee and the fixture guard.
      Name 018 in the landing notes as the parked epic whose restart-safety
      US3-S1 proves. Confirm no new dependency and the full suite green in a
      clean env (spec US3-S1, US3-S2, US3-S3; SC-003, SC-004).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — its first check most of
  all: this epic must be the only one dispatching, because its whole subject
  is the machinery every other epic runs on.
- Phase 2 (US1) is the MVP and the only story that can land first. Its PR is
  the one that turns the required check green; **no other story in this spec
  can merge before it does**, because every PR runs the check US1 repairs.
  Its hardest task is T004 (reproduction), and its most-failed task is T006
  (actually changing production code).
- Phase 3 (US2) and Phase 4 (US3) both chain on US1 **merged**, and are
  independent of each other — either order, or concurrently. US2 carries the
  slow standing proof that US1 could not afford; US3 carries deploy safety.
- If US2 lands before US3, US3 reuses its fixture instead of committing a
  second one. The tasks are written so either order works.

## Implementation Strategy

US1 alone unblocks the floor: a green replay test on GitHub runners lets 031
relaunch, 018's remainder proceed, and the roadmap unpause. That is why it
carries the fix and the *minimum* proof around it — three cycles and an
evidence file — and why the 15-cycle standing guard was moved out. Everything
US1 carries has to clear a red check on the way in; loading the heavy proof
onto the unblock is precisely what made the original single story unbuildable,
at a measured cost of four attempts, roughly nine hours and 128M input tokens.

US3 is what makes deploying US1 safe for the epic already parked across the
boundary — small in diff, decisive in consequence. US2 is what stops the whole
class from coming back. Neither story changes what any node does, what the
judge scores, or what the merge queue writes; the entire observable change is
that the same commands now always arrive in the same order.
