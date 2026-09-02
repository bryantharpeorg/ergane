# Tasks: a killed node leaves no ref to collide with

Read `plan.md` before starting. Its twelve traps are the difference between a fix
that works and a fix that passes. Traps 1 and 2 in particular describe an edit
that is obvious, that a naive test will confirm, and that clears the ref of the
one node in the system that needs to keep it.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

Real git and real repositories throughout, following the fixture discipline
`tests/test_predispatch_landing_preflight.py` already states: the subject is what
git says about a ref, and a fake would only prove the fake agrees with itself.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A dispatch refuses on a ref it would collide with

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002) Given a target repo whose
      origin carries `refs/heads/factory/<epic>/us1` at a commit that is not an
      ancestor of the landing head, assert `landing_readiness_preflight` returns a
      failing `PreflightFinding` for `us1` whose detail contains the full ref, the
      tip's short sha, the landing head it was compared against, and a closing
      sentence stating nothing was dispatched.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003, trap 4) **The control.** Given the same
      repo with `us1`'s remote tip an *ancestor* of the landing head — a node whose
      work already merged — assert the preflight returns no finding for `us1`.
      Without this test the check refuses every completed epic and is worthless
      within a day.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004, trap 9) Given a sixteen-node graph and
      an origin carrying no `factory/<epic>/*` refs, assert the remote is consulted
      exactly **once**. Assert on the call count, never on elapsed time.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005, trap 8) Given an unreachable origin,
      assert the preflight returns an informational finding naming the remote and
      that no finding it returns fails the dispatch.
- [ ] T005 [P] [US1] (trap 3) Given an origin carrying a decoy ref whose *tail*
      matches a node's branch name but whose full name does not — e.g.
      `refs/heads/mirror/factory/<epic>/us1` — assert no finding is raised for
      `us1`. This is the test that catches a pattern match trusted to be precise.
- [ ] T006 [US1] (spec US1-S5, FR-006) Extend the existing parity test so the
      roadmap's `preflight_spec` and `ergane build start`'s `_run_preflight` return
      **equal** finding lists over one fixture that includes a colliding ref. Not
      `[P]`: it edits the shared parity fixture.

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002, FR-003) In `factory/workgraph/preflight.py`, add
      a check-name constant beside `WORKTREE_OWNERSHIP_CHECK`
      (`factory/workgraph/preflight.py:553`) and `LANDING_BRANCH_CHECK`
      (`factory/workgraph/preflight.py:554`), and a `*_findings` function beside
      `worktree_ownership_findings` (`factory/workgraph/preflight.py:557`) and
      `landing_branch_findings` (`factory/workgraph/preflight.py:620`).
      The predicate is ancestry against the landing head, not existence (trap 4).
- [ ] T008 [US1] (FR-004, traps 3 and 9) Implement the remote read as a single
      `ls-remote` for the whole graph, and filter its output on exact, full
      `refs/heads/factory/<epic>/<node>` names in Python. Do not let the pattern
      decide which node a line belongs to.
- [ ] T009 [US1] (FR-005, FR-006) Add the new term to the sum in
      `landing_readiness_preflight` (`factory/workgraph/preflight.py:702`), and
      confirm by reading that neither
      `factory/activities/roadmap_activities.py:661` nor
      `factory/workgraph/cli.py:128` needs an edit — both already call the entry
      point, and that is what FR-006 is protecting.

### Verification for this story

- [ ] T010 [US1] Paste, as committed evidence, the transcript of a real
      `ergane build start` refusing on a real colliding ref in a scratch repo, and
      the same command succeeding once the ref is cleared. The judge sees the diff
      only, so the transcript must be in it.

## Phase 2: User Story 2 — A node the factory ends leaves an archive, not an obstacle

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1, FR-007, FR-008) Given a node whose branch is on
      origin, assert that after the workflow ends it KILLED the live
      `factory/<epic>/<node>` ref is gone from origin and an
      `archive/factory/<epic>/<node>/<short-sha>` ref on origin carries that tip.
- [ ] T012 [P] [US2] (trap 1) **The control that matters most.** Given a node ended
      through the `PAUSE_EPIC` park — which calls `_close_out` with
      `Termination.KILLED` and `state=_PARKED`
      (`factory/workgraph/workflow.py:3287`) — assert its remote ref is
      **untouched**. A fix branched on `termination` passes T011 and fails this.
- [ ] T013 [P] [US2] (trap 2) **The control.** Given a node that PASSED —
      `_close_out` with `state=None`, the early return at `:3117` — assert its
      remote ref is untouched, because a PR is about to open from that branch.
- [ ] T014 [P] [US2] (spec US2-S2, FR-008, trap 5) Given a node whose remote tip is
      reachable from no archive ref of that node, assert the live ref is left in
      place and the node's terminal record reports it.
- [ ] T015 [P] [US2] (spec US2-S3, FR-009, trap 8) Given an unreachable remote at
      kill time, assert the kill completes, the node reaches its terminal state,
      and the surviving ref is reported as an action still owed. A kill that hangs
      on a network failure is worse than the ref.
- [ ] T016 [P] [US2] (spec US2-S4, FR-010, trap 6) Assert a second kill of the same
      node succeeds having found nothing to do, and that no archive ref is
      overwritten or force-updated on either run.

### Implementation for this story

- [ ] T017 [US2] (FR-007, trap 10) In `factory/workgraph/worktree.py`, factor a
      small public helper that runs `_archive_node`
      (`factory/workgraph/worktree.py:1711`) then `_clear_remote_branch`
      (`factory/workgraph/worktree.py:1763`) in that order, and make `reset()`
      (`factory/workgraph/worktree.py:1558`) call it so the ordering comment at
      `factory/workgraph/worktree.py:1618` has exactly one home. Do not call
      `reset()` from the kill path: it also sweeps a worktree and a sidecar that
      `_close_out` has already removed.
- [ ] T018 [US2] (FR-009, traps 7 and 8) Add an activity beside `remove_worktree`
      that calls the new helper and returns its report lines. It must not raise on
      an unreachable remote — `_clear_remote_branch` returns report lines by
      design, and that property is what FR-009 rests on.
- [ ] T019 [US2] (FR-007, traps 1 and 2) Call the activity from `_close_out`
      (`factory/workgraph/workflow.py:3083`) with `**_GIT`, following
      `salvage_worktree` (`:3115`) and `remove_worktree` (`:3130`). Branch on the
      terminal **`state`**, not on `termination`, and place the call after the
      `state is None` early return at `:3117`.
- [ ] T020 [US2] (FR-008) Record the helper's report lines on the node's terminal
      record, so an operator reading the epic result learns which refs were cleared
      and which were kept and why.

### Verification for this story

- [ ] T021 [US2] Paste, as committed evidence, `git ls-remote` output from a real
      scratch remote before and after a real kill, showing the live ref gone and
      the archive ref present at the same tip.

## Phase 3: User Story 3 — An escalation names the ref that is in the way

### Tests for this story (write FIRST, must fail)

- [ ] T022 [P] [US3] (spec US3-S1, FR-011) Given a node escalating on a terminal
      reason carrying `_NON_FAST_FORWARD` (`factory/workgraph/worktree.py:679`),
      assert the composed message names the full ref, the tip's short sha, and
      whether that tip is reachable from an archive ref of the node.
- [ ] T023 [P] [US3] (spec US3-S2, FR-011) Given that tip **is** archived, assert
      the message carries the exact command that would clear the ref.
- [ ] T024 [P] [US3] (spec US3-S3, FR-011) **The control.** Given that tip is
      archived nowhere, assert the message says so and carries **no** clearing
      command. A command offered for an unarchived tip is an invitation to lose
      work.
- [ ] T025 [P] [US3] (spec US3-S4, FR-012, trap 12) **The control.** Given a node
      escalating for any other cause, assert the message is byte-identical to
      today's.

### Implementation for this story

- [ ] T026 [US3] (FR-011, FR-012, trap 12) Branch the escalation message
      composition on the terminal cause using the existing `_NON_FAST_FORWARD`
      marker, and compose the ref facts from the node record. Add no new remote
      read on the escalation path.

### Verification for this story

- [ ] T027 [US3] Paste the rendered message for both branches — a non-fast-forward
      escalation and an unrelated one — as committed evidence.

## Verification

- [ ] T028 The full gate command passes green.
- [ ] T029 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end, and step 5 — re-dispatching a node that was
      previously killed, and watching it push without a non-fast-forward refusal —
      is the falsifiable test of this whole spec. It is the exact sequence that ran
      four times on 2026-09-01 and failed four times.
