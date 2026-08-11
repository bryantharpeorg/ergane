# Tasks: A relaunch that does not resume the dead run

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A test that passes before its
implementation exists has found a defect in the test — except where a task's
docstring says it is a regression guard, written to go red only if the
implementation over-reaches.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Five checks, because the
      finding's own anchors drifted once already (plan.md trap 1): that
      `ensure()`'s three reuse decisions still sit where the inventory says
      (`path.is_dir()` return, `pinned = base_ref or …`, `_branch_exists`
      checkout) and `prepare_worktree` still calls `ensure` without a
      `base_ref`; that `remove()` still leaves the sidecar behind — US2's whole
      premise; that `_branch_exists` still answers with `returncode`, because it
      is trap 3's template; that the `build` noun has gained no `reset` verb
      meanwhile and its `add_parser`/exit-code conventions are unchanged; and
      that `_record_file`/`_read_record` still have no caller outside
      `worktree.py`, because the spec's Assumptions claim it.

---

## Phase 2: User Story 1 — ensure() verifies the pin before reusing it (Priority: P1) 🎯 MVP

**Goal**: a recorded pin or surviving branch is reused only after proving it
still belongs to the target's history; anything that fails the proof is rebuilt
fresh with what was there archived — renamed, never deleted. In-epic reuse is
byte-for-byte unchanged.

**Independent Test**: terminate-shaped survivors against a reset origin rebuild
fresh with the old branch reachable under an archive ref; the same survivors
against a merely-advanced origin come back untouched.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: gate command green;
      `factory/workgraph/worktree.py` and `tests/test_worktree.py` exist and
      plan.md's inventory claims hold — constitution II gate; STOP and report
      blocked if not satisfied.
- [ ] T003 [US1] Write the stale-pin rebuild case FIRST, in
      `tests/test_worktree.py` on the scratch-origin fixtures (plan.md trap 7):
      prepare a node, leave directory + sidecar + branch in place as a terminate
      would, reset the origin's landing branch so the recorded `base_ref` is no
      longer an ancestor of its head, call `ensure()` again, and assert a fresh
      worktree at a freshly captured pin with the sidecar recording the new pin
      (spec US1-S1). This is the test the story exists for — must fail.
- [ ] T004 [US1] Write the reuse-preserved case FIRST: advance the origin
      fast-forward, dirty the worktree, call `ensure()`, and assert the recorded
      `PreparedWorktree` comes back verbatim with the tree's contents untouched
      (spec US1-S2). Assert on file contents, not just the returned dataclass —
      FR-002's promise is the tree. Regression guard: today this passes; it goes
      red if the implementation re-pins or rebuilds what it should keep (plan.md
      trap 2) — say that in the docstring.
- [ ] T005 [US1] Write the archive-reachability case FIRST: force the T003
      rebuild with uncommitted work in the abandoned tree, then assert every
      commit reachable from the old branch tip — plus a commit carrying the
      uncommitted work — is reachable from a ref in the archive namespace, that
      the archive name embeds the archived tip, and that `for-each-ref` shows no
      ref was deleted (spec US1-S3, FR-004) — must fail.
- [ ] T006 [US1] Write the surviving-branch-divergent case FIRST: no directory,
      no sidecar, a node branch whose tip does not descend from the freshly
      captured pin; `ensure()` archives the branch and creates fresh at the
      fresh pin instead of checking the dead branch back out (spec US1-S4,
      FR-005) — must fail.
- [ ] T007 [US1] Write the surviving-branch-continuity case FIRST: no directory,
      no sidecar, a branch whose tip descends from the current pin (nothing
      landed since); `ensure()` checks the branch out exactly as today (spec
      US1-S5). Regression guard — red only if the implementation over-archives;
      say so in the docstring.
- [ ] T008 [US1] Write the fetch-failure case FIRST: with an unreachable
      `origin`, the verification raises `WorktreeError` rather than passing on a
      stale local view (FR-001; `capture_base_ref`'s rationale, and
      `test_capture_base_ref_raises_when_origin_is_unreachable` at
      `tests/test_worktree.py:319` is the shape to mirror) — must fail.

### Implementation for User Story 1

- [ ] T009 [US1] In `factory/workgraph/worktree.py`: the ancestry helper shaped
      like `_branch_exists` — exit code as the answer, raise only on real git
      failure (plan.md trap 3) — and the current-landing-head reader with
      `capture_base_ref`'s fetch/no-origin/raise rules. Until T008 passes.
- [ ] T010 [US1] Wire the verification into `ensure()` at all three reuse
      decisions (plan.md § US1 steps 3-4), plus the shared archive-and-rebuild
      helper (step 5): commit dirty state under `_SALVAGE_IDENTITY`, remove the
      worktree, rename the branch to the per-tip archive name — never delete,
      never overwrite (plan.md trap 5) — delete the sidecar, rebuild fresh with
      a fresh sidecar. Pass leaves today's behaviour byte-for-byte (FR-002).
      Until T003–T007 pass.

---

## Phase 3: User Story 2 — The sweep takes the sidecar with the directory (Priority: P2)

**Goal**: `remove()` deletes the sidecar with the directory, every existing
sweep path inherits it with no workflow edit, and the branch still survives.

**Independent Test**: after `remove()`, directory and `<node>.json` are both
gone, the branch remains, and repeat calls succeed.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T011 [US2] Write the sweep case FIRST, in `tests/test_worktree.py`:
      `remove()` deletes both the directory and the sidecar while the branch and
      its history survive (spec US2-S1), and stays idempotent — a second
      `remove()`, and one for a node never prepared, both succeed (spec US2-S2).
      Extend `test_remove_deletes_the_worktree_and_leaves_the_branch` (:606)
      rather than contradicting it — must fail on the sidecar assertion.
- [ ] T012 [P] [US2] Write the inheritance case FIRST, in
      `tests/test_workgraph_sweep.py` (its worktree harness at `:1609` already
      prepares real nodes): a node swept through the `remove_worktree` activity
      leaves no sidecar under the factory root, with no workflow or activity
      edit having been made (spec US2-S3, FR-007) — must fail.
- [ ] T013 [US2] Write the relaunch-after-clean-kill case FIRST, in
      `tests/test_worktree.py`: prepare, `remove()` (the clean-kill shape),
      advance the origin's landing branch, then `ensure()` again: with no
      sidecar to trust it captures a fresh pin, and the surviving branch is
      handled by US1's ancestry rule (spec US2-S4). The advance is what makes
      the fresh pin observable — before US2 the surviving sidecar still pins
      the old head, so this asserts the *new* head and goes red — must fail.

### Implementation for User Story 2

- [ ] T014 [US2] In `factory/workgraph/worktree.py`: `remove()` unlinks the
      sidecar (`missing_ok=True`) beside the directory sweep, and both "record"
      prose sites are recast — the module docstring's "never the record" bullet
      and the base-ref-record section — so the word stops meaning two things
      (plan.md trap 4). No other file changes. Until T011–T013 pass.

---

## Phase 4: User Story 3 — ergane build reset (Priority: P2)

**Goal**: one supported command replaces the three undocumented hand steps —
archive branches, clear sidecars, remove surviving worktrees, report what it
did — and refuses to touch a running epic.

**Independent Test**: reset over a dead run's leavings performs and reports
every action, deletes no ref, is idempotent, and a subsequent `ensure()` yields
a fresh tree at the current landing head.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T015 [US3] Write the reset-actions case FIRST, in
      `tests/test_ergane_build.py` through the `ergane` dispatcher: against a
      scratch target carrying dirty worktrees, sidecars and node branches for
      the graph's nodes, `ergane build reset <graph>` commits the dirty state,
      archives each branch, removes each directory, deletes each sidecar,
      prints a per-node report naming each action, and exits 0 (spec US3-S1);
      a second run reports nothing to do for every node and exits 0 (spec
      US3-S2) — must fail (the verb does not parse yet).
- [ ] T016 [US3] Write the guard cases FIRST: with the epic's workflow RUNNING
      on the time-skipping `WorkflowEnvironment`, reset refuses before touching
      anything — assert the survivors are intact — names the workflow id, and
      exits nonzero (spec US3-S3); with the same environment up but no workflow
      ever started, `describe()` raises NOT_FOUND and reset proceeds (spec
      US3-S4); and with an unreachable server, reset exits 3 having touched
      nothing — FR-010's third leg, modelled on
      `test_pause_refuses_to_signal_an_epic_that_is_not_running`, which despite
      its name is the dead-address exit-3 template (plan.md trap 7) — must
      fail. No test connects to a real Temporal.
- [ ] T017 [US3] Write the nothing-lost integration case FIRST: after a reset,
      every commit reachable from any pre-reset node branch tip is reachable
      from an archive ref and `for-each-ref` shows no ref deleted (spec US3-S5,
      FR-011); then `ensure()` for a reset node yields a fresh worktree at the
      target's current landing-branch head containing none of the dead run's
      edits — the 020 shape, closed (spec US3-S6, SC-001) — must fail.

### Implementation for User Story 3

- [ ] T018 [US3] Implement the verb: the per-node reset walk in
      `factory/workgraph/worktree.py` reusing US1's archive helper; the
      `reset_command` handler and `add_parser` registration in
      `factory/cli/nouns/build.py` with `load_workgraph`'s argument shape, the
      `FACTORY_ROOT` env rule, the `describe()` RUNNING guard (one Temporal
      read, nothing more — plan.md trap 6), and the exit-code contract
      (EXIT_OK/EXIT_USER/EXIT_TRANSPORT). Until T015–T017 pass.
- [ ] T019 [US3] Final sweep + docs: a `docs/decisions.md` entry claimed at
      landing — the factory previously held that an existing worktree is reused
      unconditionally and its leavings were the operator's to hand-clean; now
      `ensure()` verifies the pin before trusting it, archives rather than ever
      deleting (constitution VI extended across the relaunch boundary), and
      `ergane build reset` is the supported path after a terminate. Name
      `interpreter/cancel-bypasses-kill-sequence` as related and deliberately
      not fixed. Confirm no new dependency, no new activity, no workflow edit.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything: if `remove()` has already
  learned to sweep the sidecar, or a `reset` verb has landed meanwhile, the
  stories change shape and must be re-refined, not dispatched.
- Phase 2 (US1) has no dependency and is the MVP: it is the only story that
  changes what an *attempt* can be handed, and its archive helper is what US3
  reuses.
- Phase 3 (US2) chains on US1 **merged**: both rewrite
  `factory/workgraph/worktree.py` and `tests/test_worktree.py`, and US2's
  relaunch-after-clean-kill test asserts against US1's branch rule by name.
- Phase 4 (US3) chains on US2 **merged**: it reuses US1's archive helper, edits
  `worktree.py` again, and its integration test depends on the sidecar sweep
  being real.

## Implementation Strategy

US1 alone is worth landing: after it, no relaunched epic can silently dispatch
an agent against a base the target's history no longer contains, and nothing an
agent ever committed becomes unreachable in the process. US2 is one deletion
plus prose, and it is what stops the clean-kill path minting new stale sidecars
for US1 to catch. US3 is operator porcelain over machinery US1 already built —
the risk in it is grammar and guard-rails, not git, which is why its tests run
through the real `ergane` dispatcher and a real (time-skipping) workflow
server. None of the three changes what any agent is asked to do, what the judge
scores, or what the merge queue writes.
