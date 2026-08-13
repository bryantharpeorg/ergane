---
state: ready
# Flipped ready 2026-08-13 04:47Z on Bryan's word ("flip 38 and get it moving
# now so I can check on it in the morning") and dispatched immediately.
# specs_root: specs
# target_repo: /home/admin/code/ergane-roadmap-target
# Drafted 2026-08-13 ~04:50Z by the operator session that captured the
# reproducer, supersedes 032-replay-determinism's US1 (parked at draft; see
# specs/032-replay-determinism/RESCOPE-2026-08-12.md, "capture night"
# addendum, for the full evidence chain).
# Evidence in hand: ten dumped histories (artifacts repro-history-1..10 of
# run 31667012586), all clean recordings that replay green locally and
# diverged on loaded CI runners; draft PR #46 is a standing regression bench
# that reproduced 10-for-10.
---

# Feature Specification: An evicted workflow must exit silently, not command from its grave

`test_replay_dispatches_nothing_twice` fails on loaded CI runners with
`[TMPRL1100] … scheduled event 'validate_target_repo' does not match activity
command 'teardown_attempt'` — seven strikes on the findings ledger, two epics
disrupted, one judged-PASS node killed over it. The captured evidence
(2026-08-13) shows the recorded histories are clean and replay green on any
idle machine: the failure is manufactured at replay time, on the loaded
runner, and every failing log carries `RuntimeError: coroutine ignored
GeneratorExit` beside the TMPRL1100.

The mechanism: when Temporal's deadlock detector (2s) fires mid-activation
under load, the SDK evicts the workflow by throwing into its coroutines.
`EpicWorkflow._cancel()` swallows the cancellation instead of letting it
propagate — "coroutine ignored GeneratorExit" is that swallow, verbatim — and
because teardown command emission lives in `finally` blocks on the eviction
path, a dying node coroutine emits `teardown_attempt` into a command stream
that history says should hold `validate_target_repo`. TMPRL1100 is the
symptom; the leak is the disease. The 032 audit had already flagged both
halves as "amplifiers worth their own eventual story" — this is that story,
promoted to cause by fixtures.

### User Story 1 - Cancellation propagates and teardown cannot outlive eviction (Priority: P1)

`_cancel()` stops swallowing `asyncio.CancelledError`/`GeneratorExit` so an
evicted coroutine dies silently, and the teardown path is restructured so
that command emission cannot run when the workflow is being torn down by the
SDK rather than by its own logic. The ten captured histories become the
regression fixtures: replaying each must pass, and the suite must prove an
eviction mid-activation emits no commands.

**Why this priority**: every factory PR rolls this die today — it has ejected
judged-PASS work from the merge queue, and combined with the escalation
RETRY defect it has killed a node outright. It blocks the whole ready queue.

**Independent Test**: replay all ten captured histories green; inject a
cancellation into a live workflow mid-activation and assert the command
stream stays empty; run the capture bench (PR #46's matrix) and observe zero
divergences.

**Acceptance Scenarios**:

1. **Given** the ten captured history fixtures that are ALREADY ON THE BASE
   BRANCH at `tests/fixtures/replay-032/` (operator data, landed a10bea8 —
   they must NOT appear in this story's diff), **When** the new parametrised
   replay test runs, **Then** it asserts exactly ten fixture files are
   present — a missing or short directory fails the test, no existence
   fallback — and replays each against `EpicWorkflow` without
   `NondeterminismError`. The test's hard count is the diff-visible proof
   that the fixtures exist.
2. **Given** a node coroutine cancelled mid-attempt (the SDK eviction path,
   simulated by cancelling the task while an activity is outstanding),
   **When** the coroutine unwinds, **Then** the cancellation propagates —
   no `coroutine ignored GeneratorExit` warning is raisable — and no
   teardown command is emitted by the unwinding coroutine.
3. **Given** a node that fails normally (its own logic reaches teardown),
   **When** the attempt tears down, **Then** teardown activities are
   scheduled exactly as today — the fix removes emission from the eviction
   path only, and every pre-existing interpreter test passes unmodified.
4. **Given** the full suite runs on a loaded machine (the CI gate), **When**
   `test_replay_dispatches_nothing_twice` executes, **Then** its replay is
   pinned to the run it recorded (`result_run_id`) and replays under the
   same runner class that recorded it, so an environmental divergence names
   itself instead of masquerading as workflow nondeterminism.

## Functional Requirements

- **FR-001**: `_cancel()` MUST re-raise `asyncio.CancelledError` after its
  bookkeeping; no coroutine in the workflow may swallow `GeneratorExit`.
- **FR-002**: Teardown command emission MUST NOT execute on the
  SDK-eviction/cancellation path; a workflow being evicted emits no commands.
- **FR-003**: The suite MUST prove the ten captured histories replay green:
  a parametrised test asserts exactly ten fixture files exist at
  `tests/fixtures/replay-032/` and replays each. The fixture files are base
  data already landed at a10bea8 — a diff that adds, moves, or re-commits
  them is over-scope, and a fixture-count fallback that lets zero files pass
  vacuously is a failure of this requirement.
- **FR-004**: `test_replay_dispatches_nothing_twice` MUST fetch the history
  of the exact run it started (`result_run_id`) and replay under the same
  workflow-runner class used to record, and MUST keep the standing
  one-`validate_target_repo` history assertion and dump-on-failure capture.
- **FR-005**: Normal-path teardown behaviour MUST be byte-identical: every
  pre-existing interpreter and sweep test passes unmodified.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
```
