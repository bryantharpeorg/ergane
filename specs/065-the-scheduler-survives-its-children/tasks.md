# Tasks: the scheduler survives its children

**Spec**: `specs/065-the-scheduler-survives-its-children/spec.md`
**Plan**: `specs/065-the-scheduler-survives-its-children/plan.md`

Read the plan's traps before the first task. Trap 1 (the annotation is the bug),
trap 10 (US3 is a contract story, not a debugging expedition) and trap 12 (one
test file per story) are the three that decide whether an attempt lands.

## Phase 1: User Story 1 — The scheduler survives a child result it cannot read

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_roadmap_child_result.py`, script a
      child epic whose result is `None` via `tests/roadmap_script.py`'s
      `_SCRIPT.statuses`, and assert the roadmap **dispatches the next
      dispatchable spec** in the same run. Assert the subsequent dispatch, not
      the absence of an exception (trap 3 of the spec's own reasoning: a roadmap
      that silently stopped would pass a no-raise assertion).
- [ ] T002 [P] [US1] (spec US1-S2) Assert the spec whose child returned `None` is
      recorded `landed=False` with kind `OBSERVED`.
- [ ] T003 [P] [US1] (spec US1-S4) Assert the same three outcomes for at least one
      non-null malformed result — an object with no `epic_state`, or a dict.
      `None` is one member of the class, not the class (trap 2).
- [ ] T004 [P] [US1] (spec US1-S5) Assert the guard is a runtime check: a test that
      fails when the guard is removed. Not a test that the annotation says
      `EpicStatus` (trap 1).
- [ ] T005 [P] [US1] (spec US1-S3) In `tests/test_roadmap_failure_notifications.py`,
      assert a roadmap failure is recorded and the notifier reached when a child
      result is discarded (trap 3).
- [ ] T006 [P] [US1] (spec US1-S6) Assert the healthy path is unchanged: run the
      existing scheduler tests and confirm a well-formed `EpicStatus` derives
      landed status exactly as before (trap 4).

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-005) Replace the bare
      `status: EpicStatus = handle.result()` at `factory/roadmap/workflow.py:832`
      with a runtime check that asks whether the value can be interpreted as an
      `EpicStatus`, covering `None` and malformed values alike. Keep the existing
      comment at `:828-831` explaining why `result()` is non-async — it is correct
      and non-obvious.
- [ ] T008 [US1] (FR-002, FR-003) On an uninterpretable result, record
      `LandedStatus(landed=False, kind=LandedKind.OBSERVED)` and continue the
      loop. Add no new state: `OBSERVED` already means "the system observed this,
      the operator did not attest it", and finished-but-not-landed is already
      what a child with a FAILED node gets.
- [ ] T009 [US1] (FR-004) Await `_report_roadmap_failure`
      (`factory/roadmap/workflow.py:955`) with a failure text naming the spec dir
      and what was received. Mind trap 5: the loop iterates
      `list(self._children.items())` while deleting from `self._children` — do
      not restructure that iteration.
- [ ] T010 [US1] (FR-006) Confirm nothing inside `_landed_status_for`'s derivation
      changed. The guard belongs before or at that function's entry, never inside
      its `completed and all_merged` logic (trap 4).

## Phase 2: User Story 2 — A wedged scheduler is visible without an operator guessing

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) In `tests/test_roadmap_wedge_visibility.py`, assert
      `ergane roadmap status` against a roadmap whose workflow task is failing
      states that the roadmap is wedged, names the run, and names the remedy.
      Today it forwards Temporal's own sentence from
      `factory/cli/roadmap.py:382`.
- [ ] T012 [P] [US2] (spec US2-S2) Assert a registered doctor probe reports a finding
      naming the wedged run.
- [ ] T013 [P] [US2] (spec US2-S3) Assert the probe reports nothing for a roadmap
      running normally.
- [ ] T014 [P] [US2] (spec US2-S4) Assert the probe reports nothing for a roadmap that
      is running but has dispatched nothing because it is at its epic cap. Idle
      is not wedged, and a probe that conflates them gets switched off (trap 7).
- [ ] T015 [P] [US2] (spec US2-S5) Assert an unreachable Temporal is reported as a
      skipped probe via the existing `ServiceNotAnswering`, not as a wedged
      roadmap (trap 9).
- [ ] T016 [P] [US2] (spec Edge Cases) Assert a roadmap run that has completed and
      exited is read as normal — the schedule's runs drain and exit by design
      (trap 8).

### Implementation for this story

- [ ] T017 [US2] (FR-007) Recognise `Unable to query workflow due to Workflow Task
      in failed state` at `factory/cli/roadmap.py:382` and render it as a wedged
      roadmap with the run id and the remedy, rather than forwarding it.
- [ ] T018 [US2] (FR-008, FR-009) Add a probe to `factory/doctor/probes.py`'s
      `REGISTRY` that resolves the live roadmap the way
      `factory/roadmap/discovery.py` does — never a hardcoded schedule id — and
      reports a finding only for a failing workflow task.

## Phase 3: User Story 3 — The epic returns the status it declares

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US3] (spec US3-S1) In `tests/test_epic_returns_status.py`, drive an epic
      to completion in the workflow test environment and assert the **returned
      value** is an `EpicStatus` whose `epic_state` is `COMPLETED`. Assert the
      return, not the `epic_status` query — the query worked throughout both
      incidents (trap 11).
- [ ] T020 [P] [US3] (spec US3-S2) Assert the same for a killed conclusion:
      `epic_state` is `KILLED`. Both branches of `run`'s final `if` reach the
      same return at `factory/workgraph/workflow.py:811`.
- [ ] T021 [P] [US3] (spec US3-S4) Run the new test against unfixed `HEAD`, confirm it
      fails, and **paste the failing output into the diff** (trap 13). Get the
      red test before looking for the cause (trap 10).

### Implementation for this story

- [ ] T022 [US3] (FR-010) Make the assertion true. Start from the red test, not from
      reading the SDK.
- [ ] T023 [US3] (spec US3-S3) State the cause — in the commit message, or in a comment
      where it was fixed. If the investigation ends without one, say that
      explicitly. A passing test presented as a fix when nobody knows why the
      value changed is the outcome this task exists to prevent.

## Verification

- [ ] T024 (SC-001) Run the scripted-null test, confirm the next spec dispatches,
      then remove the guard and confirm the test fails. Paste both runs.
- [ ] T025 (SC-002) Let two epics complete back to back under one roadmap run chain
      with no operator intervention between them. This has never happened on this
      host; it is the only proof that counts.
- [ ] T026 (SC-003) Run `ergane roadmap status` against a wedged fixture and paste
      the output. Read it as a stranger: does it say what to do next?
- [ ] T027 (SC-004) Run `ergane doctor` against a wedged roadmap and a healthy one
      and paste both outputs.
- [ ] T028 (SC-005) Confirm the US3 test fails against `HEAD` before the fix. If it
      passes before the fix, it is testing something else.
