---
state: ready
# Dispatched 2026-08-11 ~5:55 PM CT under the standing order ("carry on to 32")
# the moment 031 concluded; T001 preflight recorded in tasks.md.
# Flipped ready by the operator 2026-08-11 ~2:15 PM CT ("flip 32 to ready").
# Dispatch condition per T001: the floor must be otherwise quiet — 031 (in
# flight at the flip) concludes first.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `interpreter/replay-test-nondeterminism-under-load` (critical), drafted by the
# operator session against the tree at c6ad7d6 on 2026-08-11, the same day the
# defect took the required check hostage. This spec is the unblock for every
# landing behind it: 031 (in flight at drafting), 018's remainder, and the
# roadmap unpause all queue behind a green required check.
---

# Feature Specification: The epic's command sequence is a fact, not a race

## The incident, and why this spec exists

On 2026-08-11 the required check went red three times in under two hours, on
two branches carrying **unrelated diffs** — 018/us2 (adapter only) twice, then
031/us1 (roadmap/notify only) — every time on the same test with the same
signature:

```
tests/test_interpreter.py::test_replay_dispatches_nothing_twice
[TMPRL1100] Nondeterminism error: Activity type of scheduled event
'validate_target_repo' does not match activity type of activity command
'teardown_attempt'
```

The same trees are green everywhere else: two worker-host gate runs (018/us2,
verified twice), six isolated runs of the failing test pinned to two CI-like
cores, and one full-suite run under the exact CI command and core count. One
GitHub run of the merged tree (the post-merge push build at 14:22Z) also
passed. GitHub PR runners: 3 red of 3. Everything local: 9 green of 9.

The test is doing its job. Its docstring names its purpose: *"a scheduler that
consulted a clock, a set's iteration order, or `uuid4()` outside
`workflow.uuid4()` fails here."* It records a real three-node epic in-process,
fetches the history, and replays it deterministically. A nondeterminism error
means the recording captured an activity-command order that the pure
re-derivation does not produce — the recorded interleaving put the epic-level
onboarding activity (`validate_target_repo`, scheduled from the workflow's
onboarding step) and a node-level `teardown_attempt` in an order the replay
cannot reconstruct. Slow, contended runners make the recording's event loop
interleave epic-level and node-level coroutines in orders a fast host never
exhibits; the code, not the test, owns that variance.

Why this is worse than a flaky check: `EpicWorkflow` replays its own history
in production every time the worker restarts with an epic in flight — the
2026-08-06 Temporal outage recovery did exactly that, successfully, on the
code of that day. A command sequence that depends on scheduling pressure is a
wedged epic waiting for the wrong restart. CI is the canary, not the patient.

## Why this spec can land through the check it fixes

A PR's required check runs the PR's own tree. This spec's branch carries the
fix, so its check exercises the fixed code — green by construction *if the fix
is right*, which US1's fail-first harness proves locally before the landing is
ever attempted. Nothing else in the corpus can land first: every other branch
re-rolls the 3-in-4 red.

## User Scenarios & Testing

### User Story 1 - Find the racy construct and make the command order a pure function (Priority: P1)

Locate the construct in `factory/workgraph/workflow.py` whose activity-command
order can vary with scheduling pressure — the mismatch pair brackets the
neighborhood: the onboarding step that schedules `validate_target_repo` and
the node/task machinery that schedules `teardown_attempt` — and change it so
the command sequence is identical under any event-loop interleaving. The
diagnosis must be demonstrated, not asserted: a harness that forces adverse
interleavings must reproduce the CI failure on the worker host **before** the
fix and fail to reproduce it **after**, under the same forcing.

**Goal**: the sequence of activity commands an `EpicWorkflow` issues is a pure
function of its inputs and its history — never of host speed, load, or task
wakeup order.

**Independent Test**: under the adversarial-interleaving harness (US1 builds
it as its fail-first instrument), the recorded epic's replay fails against the
pre-fix tree and passes 15 consecutive runs against the fixed tree; an
unmodified `test_replay_dispatches_nothing_twice` stays green throughout.

**Acceptance Scenarios**:

1. **Given** the pre-fix tree and a harness that injects scheduling adversity
   into the recording (delays or reordered wakeups at the epic/node coroutine
   boundary), **When** the recorded history is replayed, **Then** the replay
   fails with the incident's nondeterminism signature — the defect is
   reproduced on the worker host, fail-first, before any fix is written.
2. **Given** the fixed tree under the same adversarial harness, **When** the
   record-and-replay cycle runs 15 consecutive times, **Then** every replay
   succeeds and the commands match history exactly.
3. **Given** the fixed tree, **When** the full unmodified suite runs in a
   clean environment, **Then** it is green — the fix changes command
   *ordering determinism*, never which activities run, their inputs, or any
   node outcome, gate result, judge verdict, or queue interaction.
4. **Given** the diff of this story, **When** it is inspected, **Then**
   `test_replay_dispatches_nothing_twice` is not weakened, not deleted, not
   retried, and not marked — the test that caught the defect survives intact,
   and the fix is in the workflow code the test judges.

### User Story 2 - A worker restart cannot wedge the epics that recorded under the old order (Priority: P1)

The fix changes what commands the workflow issues, and Temporal replays live
epics through the *current* code at every worker restart. An epic whose
history was recorded under the old interleaving must still replay after the
fix deploys — otherwise the cure wedges the patients: any epic paused or
running across the deploy (018 is parked-open at drafting time) hits the same
nondeterminism error from the other side at its next worker restart.

**Goal**: histories recorded by the pre-fix code replay cleanly through the
fixed code, proven with a captured pre-fix history, so deploying this spec
requires no drain-the-floor ceremony and cannot strand 018.

**Independent Test**: a history recorded by the pre-fix workflow (captured as
a test fixture during US1's fail-first phase) replays green through the fixed
workflow; the suite carries that fixture as a standing regression.

**Acceptance Scenarios**:

1. **Given** a history file recorded by the pre-fix workflow under benign
   scheduling (the order every production epic to date actually recorded),
   **When** it is replayed through the fixed code, **Then** the replay
   succeeds — deploy compatibility is proven, not hoped.
2. **Given** the same pre-fix recording made under *adverse* scheduling (the
   CI-shaped order, if the fix's mechanism permits its capture), **When** it
   is replayed through the fixed code and the replay cannot succeed, **Then**
   the spec's landing notes say so explicitly and name the operator rule: no
   worker restart while an epic that recorded under adverse scheduling is in
   flight. Impossibility is acceptable; silence about it is not.
3. **Given** the fixture and its replay test, **When** a future hand changes
   the workflow's command order again, **Then** the fixture replay goes red —
   the compatibility proof is a standing guard, not a one-time check.

## Functional Requirements

- **FR-001**: The activity-command sequence `EpicWorkflow` issues MUST be
  invariant under event-loop scheduling order: same inputs, same history,
  same commands, on any host at any load.
- **FR-002**: The defect MUST be reproduced fail-first on the worker host via
  an adversarial-interleaving harness before the fix lands, and the same
  harness MUST pass 15 consecutive record-replay cycles after it.
- **FR-003**: The fix MUST NOT change which activities are executed, their
  inputs, their retry policies, or any observable epic outcome — ordering
  becomes deterministic; behavior does not otherwise change.
- **FR-004**: `test_replay_dispatches_nothing_twice` MUST survive unweakened:
  no deletion, no retry, no marker, no relaxation of its assertions.
- **FR-005**: A history recorded by the pre-fix code under benign scheduling
  MUST replay green through the fixed code, proven by a committed fixture
  history exercised in the suite.
- **FR-006**: The suite MUST carry the fixture replay as a standing
  regression so any future command-order change fails loudly at the gate
  instead of wedging a live epic at the next worker restart.
- **FR-007**: All new tests MUST build their stores under `tmp_path` and run
  green in a clean environment — the open store-isolation finding
  (`hardening/test-suite-writes-to-the-live-evidence-store`) applies to every
  test this spec adds.

## Success Criteria

- **SC-001**: The next three PR-event CI runs after this spec lands are green
  on the replay test — the 3-of-4 red rate goes to zero.
- **SC-002**: The adversarial harness reproduces the incident signature on
  the pre-fix tree and cannot reproduce it on the fixed tree, both on the
  worker host.
- **SC-003**: The committed pre-fix fixture history replays green through the
  fixed code, and its test is part of the default suite.
- **SC-004**: No new dependency; the full suite green; the diff confined to
  `factory/workgraph/workflow.py`, test files, and fixtures.

## Edge Cases

- **The fix's own epic runs on the pre-fix worker.** The worker driving this
  spec's epic imports the old workflow module; the story's worktree carries
  the new one. Gates and CI judge the worktree's code — the running epic's
  own history is recorded by the old code, which US2's fixture then proves
  replayable. The deploy order is: land, then restart the worker at the
  operator's convenience.
- **018 is parked-open across the deploy.** Its history was recorded under
  benign scheduling on the fast host (its every replay to date succeeded).
  US2-S1's fixture is the evidence class for exactly this epic; the landing
  notes name 018 as the live beneficiary.
- **The harness must not become load-bearing.** Adversarial interleaving is a
  test instrument; production code must not import, detect, or special-case
  it.
- **A retry of the recording inside the test** (Temporal activity retries
  during the record phase) is part of the recorded history, not noise — the
  harness must tolerate recordings whose activity attempt counts vary.

## Assumptions

- The nondeterministic construct is in `factory/workgraph/workflow.py` (or a
  module it imports into workflow scope), in the neighborhood the mismatch
  pair brackets: onboarding's `validate_target_repo` scheduling
  (`workflow.py:829`, invoked from the run boundary near `:644`) racing the
  node machinery that schedules `teardown_attempt` (node tasks are created at
  `:754`/`:758`). If diagnosis lands elsewhere, the spec's requirements are
  unchanged — FR-001 names the property, not the line.
- `WorkflowEnvironment.start_time_skipping()` plus `Replayer` (the shapes the
  test already uses) are sufficient instruments; no new dependency is needed
  for the adversarial harness — seeded delays in the scripted world's
  activity completions are enough to vary wakeup order.
- The 018 pause and the 031 kill/park (whichever state that epic holds at
  dispatch) leave no attempt in flight while this spec's stories run — the
  operator confirms the floor before dispatch (Phase 1).

## Out of Scope

- **Child workflows per node** (`temporal/node-child-workflows`, audit T1) —
  the structural redesign that would make node lifecycles independently
  replayable. This spec buys determinism for the current shape.
- **Worker versioning** (audit T7) — the general solution to deploying
  workflow-code changes across in-flight epics. US2 proves compatibility for
  this one change; it does not build the versioning machinery.
- **The CHECKS_FAILED blind-recovery ladder** that turned one red into a
  killed story chain twice today — that is 025's scope, unchanged.
- **Why GitHub runners exhibit the interleaving and fast hosts do not** —
  interesting, unactionable; the fix removes the sensitivity rather than
  chasing the trigger.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-007]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006]
```

US2 takes a merge-edge: its fixture is captured during US1's fail-first phase
and its replay-compatibility test runs against US1's fixed code, so its base
must contain US1's work.
