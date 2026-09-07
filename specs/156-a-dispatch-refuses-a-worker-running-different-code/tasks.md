# Tasks: a dispatch refuses a worker running different code

## Phase 1: User Story 1 — build start refuses when the worker's revision is not the tree's

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (US1-S1, US1-S2, FR-001, FR-006) Write the failing
  pair: with the worker-revision seam patched to a differing value,
  `build start` exits non-zero, prints the refusal naming both revisions
  and the restart remedy, and the fake client records NO
  `start_workflow` call; with the seam patched equal, the same command
  dispatches, and its output contains no skew text (the aligned case is
  byte-identical, trap 1).
- [ ] T002 [P] [US1] (US1-S3, FR-003) Write the failing case: a worker
  revision of `None` refuses with the "worker revision is unknown"
  wording; a CLI revision of `None` does NOT refuse (dispatch proceeds).

### Implementation for this story

- [ ] T003 [US1] (FR-002) Implement `skew_refusal` beside `_skew_notice`
  (`factory/cli/nouns/build.py:986` region), sharing its `None` arms
  verbatim; `_skew_notice` itself unchanged (trap 1).
- [ ] T004 [US1] (FR-001) Call the seam in `_start_epic`
  (`factory/cli/nouns/build.py:883`) after preflight and before
  `start_workflow` (`:929`); on refusal print to stderr and exit non-zero.
- [ ] T005 [US1] (US1-S5, FR-001) Assert the one-line shape: worker
  revision, tree revision, restart command — three facts, one line.

## Phase 2: User Story 2 — a roadmap tick parks the spec under skew

### Tests for this story (write FIRST, must fail)

- [ ] T006 [P] [US2] (US2-S1, FR-004) Write the failing roadmap test: with
  the stamped boot revision differing from the tree-revision activity's
  answer, the tick parks the spec with `check: "dispatch"` and both
  revisions in the detail, no child is started (the scripted world records
  no `EpicWorkflow` start), and the tick proceeds to the next spec.
- [ ] T007 [P] [US2] (US2-S3) Write the unpark round trip: park under
  skew, clear the skew, send the unpark signal, read a dispatch on the
  next tick (the existing unpark grammar, no new surface).
- [ ] T008 [P] [US2] (US2-S4, FR-003) Write the `None` case: a worker
  revision of `None` parks with the "unknown" wording.

### Implementation for this story

- [ ] T009 [US2] (FR-005, traps 2, 3, 4) Widen
  `_WorkerRevisionInterceptor` (`factory/worker.py:299`) to stamp
  `RoadmapInput` exactly as `EpicInput` is stamped (by-name match, `None`
  guard — trap 2); add `worker_revision: str | None = None` to
  `RoadmapInput` (`factory/roadmap/workflow.py:229`); add the
  tree-revision ACTIVITY (workflow-legal: runs in the worker process,
  `git rev-parse --short HEAD` in the package directory — trap 3) to the
  worker's registration.
- [ ] T010 [US2] (FR-004, trap 5) In `_dispatch`
  (`factory/roadmap/workflow.py:1170`), before the child start at
  `:1294`: execute the tree-revision activity, compare against the stamped
  boot revision, and on inequality `self._park(spec_dir, "dispatch",
  detail)` then `return` — the park never raises (trap 5).
- [ ] T011 [US2] (trap 6) Extend the test fakes' `epic_status` answer with
  `worker_revision` rather than minting a second fake; the existing
  scripted-world tests must stay green unmodified except for the field.

## Phase 3: User Story 3 — the record an hour later

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US3] (US3-S1) Write the visibility pair: after a US1
  refusal, the skew is recomputable from live sources (re-run reads both
  revisions from the status path at `factory/cli/nouns/build.py:1172`);
  after a US2 park, `ergane roadmap status` carries both revisions in the
  park detail (US3-S2).
- [ ] T013 [P] [US3] (US3-S3) Write the no-residue case: after the worker
  is restarted and the skew clears, re-running the same commands shows no
  residue — no store was minted (this test must FAIL any implementation
  that adds durable skew state).

### Implementation for this story

- [ ] T014 [US3] Nothing to implement unless a test says otherwise: the
  refusal message and the park detail are the record. If T012/T013 pass
  without production changes, record that here and close the phase.

## Verification

- [ ] T015 Run the thing: a scratch-worktree `build start` under a
  deliberately skewed worker-revision seam refuses with both revisions
  named; aligned, it dispatches. Paste the output.
- [ ] T016 A scripted roadmap pass under skew parks and proceeds; paste
  the parked entry with both revisions.
- [ ] T017 Full `uv run pytest -q` green; re-read every anchor in
  spec.md/plan.md against the tree and record any drift.