# Tasks: the factory reads origin, not the operator's checkout

**Spec**: `specs/090-the-factory-reads-origin-not-the-operators-checkout/spec.md`
**Plan**: `specs/090-the-factory-reads-origin-not-the-operators-checkout/plan.md`

Read the plan's traps before the first task. Trap 1 (a refused clone is not an
exception), trap 2 (`reset --hard` to a remote ref destroys local commits too),
trap 3 (ignored files park nothing) and trap 4 (`resolve_landing_base` is
read-only to this epic) are the four that decide whether an attempt lands.

## Phase 1: User Story 1 — The refresh follows the manifest, not the checkout

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_090_refresh_follows_manifest.py`,
      build a repository under `tmp_path` with a local `origin`, a `dev` branch
      declared as `landing_branch` in its manifest, and HEAD on `spec/x`. Drive
      the refresh and assert the clone ends on `dev` at `origin/dev`, and that
      `spec/x` was neither checked out nor reset.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the returned result names `dev` as the
      branch and `origin/dev`'s SHA as the head.
- [ ] T003 [P] [US1] (spec US1-S3) Assert a clone whose manifest is absent falls
      back to the checked-out HEAD and records that the fallback arm answered —
      the same failing-open behaviour `resolve_landing_base` already has.
- [ ] T004 [P] [US1] (spec US1-S4) **The single-derivation proof (trap 7).**
      Patch `resolve_landing_base` to return a known branch and assert the
      refresh used it, while asserting `_default_branch` was not called directly
      by the refresh.

### Implementation for this story

- [ ] T005 [US1] (FR-001) In `_refresh_to_default`
      (`factory/activities/roadmap_activities.py:105`), add
      `resolve_landing_base` to the deferred import at `:117` (trap 5) and
      replace the `default = _default_branch(repo)` read at `:118` with it.
- [ ] T006 [US1] (FR-002, FR-007) Leave the fetch / checkout / reset sequence
      otherwise unchanged, so a clean clone on the declared branch behaves
      exactly as it does today.
- [ ] T007 [US1] (FR-006) Carry the arm that answered onto `CloneResult`
      (`:98-102`) so US3 has a field to report; populating it is US3's job.

## Phase 2: User Story 2 — A refresh that would destroy work parks the spec

### Tests for this story (write FIRST, must fail)

- [ ] T008 [P] [US2] (spec US2-S1) Assert a clone on the declared landing branch
      with an uncommitted modification to a tracked file is refused, no reset is
      performed, and the modification survives.
- [ ] T009 [P] [US2] (spec US2-S2) **Trap 2.** Assert a clone carrying a commit
      absent from the remote ref is refused and the commit survives. A dirty-tree
      check alone passes this repository's own worst case and must not.
- [ ] T010 [P] [US2] (spec US2-S3) **The control.** Assert a clean clone on the
      declared landing branch is fetched and reset exactly as before.
- [ ] T011 [P] [US2] (spec US2-S4) **Trap 3.** Assert files matched by the target
      repository's own ignore rules do not cause a refusal.
- [ ] T012 [P] [US2] (spec US2-S1, FR-003) Assert the workflow parks the spec
      when the activity reports a refusal, using the scripted `_clone_runner`
      seam rather than a real repository.

### Implementation for this story

- [ ] T013 [US2] (FR-003) Before the checkout, ask git whether the reset would
      discard anything: a dirty working tree over tracked paths, or commits on
      the current branch that are not ancestors of the ref the reset targets.
      Use git's own ignore handling; do not enumerate directory names (trap 3).
- [ ] T014 [US2] (FR-003, trap 1) Report the refusal **on `CloneResult`**, not by
      raising. `clone_target`'s contract says a refused clone does not raise and
      only a git error does; keep that line intact.
- [ ] T015 [US2] (FR-003, FR-004) In `factory/roadmap/workflow.py:1186-1194`, park
      the spec when the result carries a refusal, alongside the existing
      `FailureError` arm rather than in place of it.
- [ ] T016 [US2] (FR-004) Make the refusal name the branch, the paths or commits
      at risk, and the operator act that clears it.

### The operator's demonstration for this story

- [ ] T017 [US2] Run the reflog demonstration in the plan's § *Verification the
      operator will run* against a live roadmap schedule, and paste the branch,
      status and reflog output into the attempt report. The reflog is the
      load-bearing evidence: a clean `git status` after a reset is
      indistinguishable from one that was never touched, and only the absence of
      a `reset: moving to` entry proves the tick left the checkout alone.

## Phase 3: User Story 3 — The tick says which branch it used and who named it

### Tests for this story (write FIRST, must fail)

- [ ] T018 [P] [US3] (spec US3-S1) Assert that when the manifest declared the
      branch, the result carries the manifest arm as a distinguishable value and
      not merely the branch name.
- [ ] T019 [P] [US3] (spec US3-S2) Assert a fallback records the loader's own
      complaint, so an operator learns why the guess was made.
- [ ] T020 [P] [US3] (spec US3-S3) Assert a park reason produced by US2 names the
      branch, the paths at risk, and the clearing act.

### Implementation for this story

- [ ] T021 [US3] (FR-006) Populate the arm and detail fields on `CloneResult`
      from the `LandingBase` US1 already obtained, and log the base, the
      repository it was read from and the arm — the shape `_log_landing_base`
      (`factory/activities/merge_activities.py:385`) uses for the landing path.
- [ ] T022 [US3] (FR-008) Confirm the two functions FR-008 names are unchanged by
      this epic, and say so in the attempt report. Do not restate their paths in
      this task, because a task that names a file joins that file to its story's
      slice and no story here edits that module.

