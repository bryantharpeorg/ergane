# Tasks: the poller asks only what the forge can answer

**Spec**: `specs/078-the-poller-asks-only-what-the-forge-can-answer/spec.md`
**Plan**: `specs/078-the-poller-asks-only-what-the-forge-can-answer/plan.md`

Read the plan's traps before the first task. Trap 1 (**do not remove
`baseRefOid`** — that undoes a landed story), trap 4 (a check that denies
everything is not an improvement) and trap 5 (derive the field set, do not copy
it) are the three that decide whether an attempt lands.

## Phase 1: User Story 1 — A refused `gh` command fails the suite

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_gh_argv_contract.py`, assert
      that an argv the installed `gh` refuses with a non-zero exit and a message
      matching none of "unknown flag", "unknown command" or "usage:" is
      classified as a refusal. Use a real `--json` field name no `gh` has; the
      refusal shape is identical to the one that cost 2026-08-20 (plan,
      "The refusal, run by hand").
- [ ] T002 [P] [US1] (spec US1-S2) **The control, and the failure mode of this
      change.** Assert an argv `gh` accepts but cannot complete without
      credentials is classified as ACCEPTED. `gh` exits 4 when it needs
      authentication. A check that denies on any non-zero exit is unrunnable in
      CI and is the same as deleting it (trap 3, trap 4).
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) Assert the poller's `--json` field set
      is validated as a set, read from the same object the poller sends
      (`factory/mergequeue/gh.py:68`), not from a copy. 071-US2 enumerated the
      methods correctly; the argument it could not read was inside one of them.
- [ ] T004 [P] [US1] (spec US1-S5, FR-002) Assert the check still catches a
      refused field with `GH_TOKEN` unset, outside any git repository, with no
      network.
- [ ] T005 [P] [US1] (spec US1-S6, FR-004) Assert the check skips on a real
      runtime condition when `gh` is absent, never on a bare `pytest` marker
      (trap 9). `tests/test_gh_argv_contract.py:196` already has the right
      shape.

### Implementation for this story

- [ ] T006 [US1] (FR-001) Rewrite `_gh_would_refuse`
      (`tests/test_gh_argv_contract.py:164`) to classify by
      `completed.returncode`. Delete the three-way prose match at `:188-190` and
      the sentence in the docstring at `:169` that describes it — that sentence
      is the defect written down.
- [ ] T007 [US1] (FR-002) Keep the authentication exit as acceptance, named as
      such in the code so the next reader does not "tighten" it away.
- [ ] T008 [US1] (FR-003) Make the field set flow from `_VIEW_FIELDS` into the
      check rather than being restated in the test.

### Verification for this story

- [ ] T009 [US1] (SC-001, spec US1-S4) Paste the corrected check refusing a real
      bad `--json` field, showing the refusal it now sees. State in the diff
      whether the refusal came from a field no `gh` has or from a stub `gh` on
      `PATH` (trap 10) — do not claim a gh 2.45.0 run you did not perform.
- [ ] T010 [US1] (SC-002) Paste the control: a well-formed unauthenticated
      command still classified as accepted.
- [ ] T011 [US1] (SC-003) Paste the check running with `GH_TOKEN` unset outside
      any git repository, still catching the refused field.

## Phase 2: User Story 2 — The operator learns their `gh` cannot answer before they dispatch

**Depends on US1 having merged** (`depends_on_merged`). Both stories reach the
poller's field set; the edge is contention, not logic (plan trap 6 is US3's, this
is trap 5's). If `gh.py` does not look as the plan describes, US1 has landed —
re-read it.

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-005) In
      `tests/test_forge_capability_probe.py`, assert that a `gh` refusing one of
      the poller's fields makes install verification fail, naming the field and
      the installed version.
- [ ] T013 [P] [US2] (spec US2-S2, FR-007) Assert a passing check states what it
      verified and which binary answered. A green line that does not say what it
      checked is the defect class named in
      `verify/readiness-proves-a-thing-is-declared-not-that-it-works`.
- [ ] T014 [P] [US2] (spec US2-S3, FR-006) Assert an absent `gh` is a distinct
      named condition from an incapable one. Absent and incapable have different
      remedies.
- [ ] T015 [P] [US2] (spec US2-S4, FR-003) **The mutation.** Change the poller's
      field set and assert the probe follows it without being edited. If it does
      not follow, the probe has copied the list and this story has rebuilt the
      defect one layer up (trap 5).

### Implementation for this story

- [ ] T016 [US2] (FR-005, FR-006, FR-007) Add the capability check. **Decide
      deliberately whether it belongs in `factory/controlplane/verify.py` (the
      `install --verify` surface, probe protocol at `:54`) or
      `factory/doctor/probes.py` (the recurring health surface), build exactly
      one, and say which and why in the diff** (trap 11).
- [ ] T017 [US2] Give the refusal a remedy line an operator can act on. The
      only `gh`-version prose in the tree today is
      `factory/mergequeue/wiring.py:266`; do not duplicate it — reuse or replace.

### Verification for this story

- [ ] T018 [US2] (SC-004, spec US2-S5) Paste verification failing against a `gh`
      that refuses a poller field, naming the field and the version. State how
      the refusing `gh` was produced — a stub earlier on `PATH` is acceptable and
      must be said out loud.
- [ ] T019 [US2] (SC-005) Paste verification passing on this host, including the
      line naming which binary answered.
- [ ] T020 [US2] (SC-006) Paste the mutation: change the field set, run the probe
      unchanged, show it following.

## Phase 3: User Story 3 — A landing poll that dies is visible

Independent of US1 and US2: this story touches `factory/workgraph/workflow.py`
and its own test file, and shares no file with either.

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1, FR-008) In
      `tests/test_landing_poller_failure_is_visible.py`, make the poll activity
      raise and assert the node does not go on reporting `ENQUEUED`.
- [ ] T022 [P] [US3] (spec US3-S2, FR-009) Assert the reason is readable from the
      **rendered operator status output**, not from the internal record. The
      record was already right on 2026-08-20; the thing nobody could read was the
      status.
- [ ] T023 [P] [US3] (spec US3-S3, FR-010) **The control.** A poll that fails
      once and succeeds on the next beat must land normally and raise nothing
      operator-visible. Read `_FAST`'s retry policy
      (`factory/workgraph/workflow.py:338`) before deciding what "stopped" means
      (trap 8).
- [ ] T024 [P] [US3] (spec US3-S4) **The second control.** Assert the
      cancel-on-kill path at `factory/workgraph/workflow.py:1369-1371` behaves
      exactly as it does today.

### Implementation for this story

- [ ] T025 [US3] (FR-008, FR-009) Observe the landing task's failure at **both**
      `ensure_future` sites — `factory/workgraph/workflow.py:2637` and `:3239`.
      The second is the requeue path and it is the one that runs during a busy
      epic (trap 6).
- [ ] T026 [US3] (FR-010) Distinguish a stopped poller from a slow one.
- [ ] T027 [US3] (spec US3-S5) Do not convert the poller to a foreground await
      (trap 7). Riding the landing in the background is deliberate; the defect is
      the unobserved exception, not the concurrency. If the
      narrow fix proves impossible without restructuring the loop, implement the
      smallest thing that satisfies FR-008 and FR-009 and say so in the diff.

### Verification for this story

- [ ] T028 [US3] (SC-007) Paste a node whose poller raised, showing the status
      output that now names it, next to the same status before the change.
</content>
