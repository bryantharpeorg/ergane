---
state: draft
# RETURNED TO DRAFT 2026-08-18 5:30 PM CT on Bryan's decision: "if we don't
# think it'll fix anything, let's just not implement it until we're sure it'll
# fix it. i don't want unintended consequences."
#
# This restores the 2026-08-16 park below, whose argument was never answered.
# The unintended consequence he is guarding against is concrete and named in
# plan.md trap 1: US1 changes the activity-command order in the module every
# in-flight epic replays through at worker restart, so a wrong fix does not
# merely fail -- it can wedge epics that recorded under the old order.
#
# What unblocks this is a MEASUREMENT, not a builder: a history captured from a
# pull_request MERGE-COMMIT CI run, which is the only configuration that has
# ever failed. Until that capture exists, there is no fourth diagnosis to build
# against. Flip ready when it does.
#
# --- the 2026-08-17 flip this reverses, kept for the chain ---
# FLIPPED READY 2026-08-17 3:20 PM CT on Bryan's explicit instruction, over the
# standing "DO NOT FLIP READY" below. That note is left intact because its
# argument has not been answered: the merge-group capture it asks for has still
# never been obtained, and the finding
# interpreter/replay-test-nondeterminism-under-load survived the fix that was
# supposed to close it. Anyone dispatching this should expect an implementer to
# be building against a premise nobody has confirmed, and should watch the first
# attempt rather than trust a PASS.
#
# --- the 2026-08-16 park this overrides, kept for the chain ---
# STILL PARKED 2026-08-16 — re-read tonight when the operator asked for every
# draft to be made ready. This is the one that could not be, and the reason is
# not staleness: the spec's own premise has now been disproven TWICE, and the
# evidence for what replaced it is incomplete in a way no refinement can close.
#
#   1. The original US1 blamed command-emission order in
#      factory/workgraph/workflow.py. The 08-12 audit showed the workflow emits
#      validate_target_repo exactly once and is clean on every nondeterminism
#      axis. Premise dead.
#   2. The 08-12 replacement blamed a corrupted recorded history (a phantom
#      second schedule). The 08-13 capture night killed that too: ten captured
#      histories each held exactly one validate_target_repo, well-formed, 356
#      events, and every one replays CLEAN locally.
#   3. The 08-13 diagnosis -- eviction-path CancelledError swallow plus command
#      emission in finally blocks -- WAS drafted, as 038-replay-eviction-leak,
#      and 038 LANDED on 2026-08-13 (US1 at 867930e0d533, state: landed).
#
# And the flake is still here. The finding
# interpreter/replay-test-nondeterminism-under-load was last seen
# 2026-08-16T17:45:48Z -- three days after 038 landed -- at occurrence 8, first
# seen 2026-08-11. So 038 fixed a real defect and did not fix this one.
#
# What the finding now says is missing, verbatim in shape: every observed
# failure was a pull_request MERGE-COMMIT CI run, while 24 push-event samples
# stayed green. The capture that would settle it must run IN THE MERGE GROUP,
# not on a branch -- and the apparatus built for it (PR #41) was dirty with
# potentialMergeCommit=none, so it could never produce the one configuration
# that fails. #41 is now CLOSED. That capture has never been obtained.
#
# DO NOT FLIP READY. There is no story here that an implementer could satisfy:
# the third diagnosis shipped, the symptom survived it, and nobody knows what
# the fourth is. Dispatching against this would repeat the 4-attempt kill that
# produced the first re-scope. What it needs is a measurement, not a builder.
#
# --- the 2026-08-12 note this supersedes, kept for the chain ---
# PARKED pending re-scope 2026-08-12 ~7:52 PM CT (operator, on Bryan's word):
# the operator diagnosis (finding interpreter/replay-test-nondeterminism-
# under-load, recurrence 5, evidence chain in its notes) shows the incident's
# error can only arise from a CORRUPTED recorded history — a phantom second
# validate_target_repo schedule — with the Java time-skipping test server
# under load as prime suspect. EpicWorkflow audited clean on every
# nondeterminism axis. US1 as written mandates a production fix in
# factory/workgraph/workflow.py (T006/T007), which the evidence says does not
# exist there; US2/US3 chain on it. DO NOT flip ready without re-scoping —
# see RESCOPE-2026-08-12.md in this directory for the replacement story shape
# and the confirmation still pending (one discriminator-armed CI capture).
# Re-split into three stories 2026-08-12 after the epic was killed at attempt 4
# (see the note above US1 — the old story was unsatisfiable, not merely hard).
# spec.md, plan.md and tasks.md were all brought forward together and agree;
# workgraph.json re-derived to three nodes (us1, plus us2/us3 both on a
# merge-edge to us1). Flipped ready by the operator 2026-08-12 ~6:30 AM CT.
# Dispatch condition unchanged: the floor must be otherwise quiet — us1 edits
# the workflow module every other epic runs on (plan.md trap 6).
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
is right*, which US2's 15-cycle run against US1's harness proves locally before
the landing is ever attempted. Nothing else in the corpus can land first: every
other branch re-rolls the 3-in-4 red.

This is why US1 carries the fix and cannot be split away from it: **US1's PR is
the one that turns the check green**, and every other PR in the corpus — this
spec's US2 and US3 included — waits behind it. A story of this spec that does
not contain the fix cannot merge, because its own required check is the very
check the fix repairs.

## User Scenarios & Testing

> **SPLIT 2026-08-12 after four failed attempts. Read this before implementing.**
>
> The original US1 asked one story to reproduce the defect *fail-first* and to
> fix it, in one diff. That is not buildable under this factory's own
> verification model, and no agent could have satisfied it:
>
> - The deterministic gate runs `pytest` over the story's diff. A test that
>   genuinely reproduces the nondeterminism must **fail** — which turns the
>   gate red and fails the attempt.
> - The judge reads the same diff and asks for the fail-first reproduction the
>   story demands.
>
> The only diff satisfying both would have to show the harness failing *before*
> a fix and passing *after* — two tree states, one snapshot. It cannot exist.
>
> Four attempts (three implementer, one debugger, ~9h, 128M input tokens)
> resolved the bind the only way that keeps the gate green: a harness asserting
> success. The judge then correctly rejected it as "not a fail-first
> reproduction" — the same objection all four times. **Neither the agent nor
> the judge was wrong; the story was.**
>
> **Two constraints shape the rewrite, and the second kills the obvious fix.**
>
> 1. The reproduction must be an **artifact**, not a live failing test — a
>    committed account of the pre-fix run, so "demonstrated, not asserted" is
>    satisfied by evidence rather than by a red suite.
> 2. **The first story to land MUST contain the fix.** The required check is
>    the full suite, and it is red until the defect is fixed, so *no* PR from
>    this spec can merge before the fix does. A split that puts the harness in
>    a story of its own deadlocks: that story cannot merge, and the fix story
>    waits on it. (This was the first draft of this split, on 2026-08-12; it
>    was wrong and is recorded here so it is not re-proposed.)
>
> So US1 keeps harness **and** fix together — that pairing is irreducible — and
> sheds everything that does not have to land with it. The heavy standing-proof
> burden moves to US2, which lands afterwards through a green check.

### User Story 1 - Make the command order a pure function, diagnosis evidenced (Priority: P1)

Locate the construct in `factory/workgraph/workflow.py` whose activity-command
order varies with scheduling pressure — the mismatch pair brackets the
neighborhood: the onboarding step that schedules `validate_target_repo` and the
node/task machinery that schedules `teardown_attempt` — and change it so the
command sequence is identical under any event-loop interleaving.

**This story MUST change production code.** A diff touching only `tests/` is a
failed attempt by definition: that is exactly how the unsplit story failed four
times running, and it is the single most important thing to get right here.

The diagnosis must be **demonstrated, not asserted** — but the demonstration is
a *committed artifact*, not a failing test. Build the seeded
adversarial-interleaving harness, run it against the tree **before** applying
the fix, and commit the captured output of that reproducing run as evidence
under `specs/032-replay-determinism/evidence/`. Then apply the fix and show the
same harness, at the same seed, going green. The before/after proof is the
evidence file plus the passing harness — never a red suite.

**Goal**: the sequence of activity commands an `EpicWorkflow` issues is a pure
function of its inputs and its history — never of host speed, load, or task
wakeup order. This is the story whose PR turns the required check green, and
nothing else in the corpus can land before it.

**Independent Test**: the full suite is green including
`test_replay_dispatches_nothing_twice`; the harness passes 3 consecutive
record-replay cycles at a fixed seed; and the committed evidence file shows the
same harness reproducing the signature before the fix.

**Acceptance Scenarios**:

1. **Given** this story's diff, **When** it is inspected, **Then** it contains a
   substantive change under `factory/` — `factory/workgraph/workflow.py` at the
   named construct. A tests-only diff fails this scenario outright.
2. **Given** the harness at a fixed seed on the fixed tree, **When** the
   record-and-replay cycle runs 3 consecutive times, **Then** every replay
   succeeds and the commands match history exactly.
3. **Given** the committed evidence file, **When** it is read, **Then** it shows
   the harness reproducing the incident's signature against the pre-fix tree —
   the diagnosis demonstrated, without requiring a failing test to survive in
   the diff.
4. **Given** the harness, **When** it is inspected, **Then** its forcing is
   deterministic and seeded — the same seed reproduces the same interleaving —
   and production code neither imports it nor special-cases it.
5. **Given** the fixed tree, **When** the full unmodified suite runs in a clean
   environment, **Then** it is green — the fix changes command *ordering
   determinism*, never which activities run, their inputs, or any node outcome,
   gate result, judge verdict, or queue interaction.
6. **Given** the diff of this story, **When** it is inspected, **Then**
   `test_replay_dispatches_nothing_twice` is not weakened, not deleted, not
   retried, and not marked — the test that caught the defect survives intact,
   and the fix is in the workflow code the test judges.

### User Story 2 - The harness becomes a standing regression (Priority: P2)

US1 proves the fix once, at one seed, over 3 cycles — enough to land, and
deliberately no more, because everything US1 carries has to clear a red check
on the way in. This story turns that one-off proof into a permanent guard:
the adversarial harness runs **15 consecutive record-replay cycles** in the
suite, and a committed pre-fix fixture history rides alongside it so any future
change to command ordering fails loudly at the gate.

By the time this story dispatches the required check is green (US1 landed), so
it can carry the heavier, slower proof without gambling the unblock on it.

**Goal**: the determinism US1 established cannot silently regress — the next
ordering change fails at the gate, not at 3 a.m. in a live epic.

**Independent Test**: the suite carries a 15-cycle record-replay run at a fixed
seed and a committed fixture history, and is green in a clean environment.

**Acceptance Scenarios**:

1. **Given** US1's harness in the base, **When** the suite runs, **Then** it
   executes 15 consecutive record-replay cycles at a fixed seed and every one
   succeeds.
2. **Given** a history recorded by the pre-fix code and committed as a fixture,
   **When** the suite replays it through the fixed workflow, **Then** it is
   green — and this test stands permanently as the regression guard.
3. **Given** this story's diff, **When** the store-isolation rule is applied,
   **Then** every new test builds its stores under `tmp_path` (FR-007) and the
   15-cycle run does not extend suite wall-clock beyond the gate's budget —
   if it would, the cycle count is the thing that gives, not the isolation.

### User Story 3 - A worker restart cannot wedge the epics that recorded under the old order (Priority: P1)

The fix changes what commands the workflow issues, and Temporal replays live
epics through the *current* code at every worker restart. An epic whose
history was recorded under the old interleaving must still replay after the
fix deploys — otherwise the cure wedges the patients: any epic paused or
running across the deploy (018 is parked-open at drafting time) hits the same
nondeterminism error from the other side at its next worker restart.

This story is unchanged by the 2026-08-12 split except for its number and its
edge: it waits on **US1**, the story that carries the fix, not on US2. It has no
dependency on US2's standing-regression work, so the two can proceed in either
order once US1 lands.

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
- **FR-002**: The defect MUST be reproduced on the worker host via a
  deterministic, seeded adversarial-interleaving harness, and that reproduction
  MUST be committed as a **captured account of the pre-fix run** under
  `specs/032-replay-determinism/evidence/` — evidence, not a failing test. The
  suite that ships with the fix is green; the demonstration lives in the
  artifact. After the fix the same harness MUST pass **3** consecutive
  record-replay cycles at the same seed. (Split from the original FR-002 on
  2026-08-12: requiring one diff to be both fail-first and fixed is
  unsatisfiable under a gate that runs the suite over that same diff, and the
  four attempts that failed were failing an impossible requirement. See the
  note above US1.)
- **FR-008**: Once the check is green, the harness MUST become a standing
  regression: **15** consecutive record-replay cycles at a fixed seed in the
  suite, plus a committed pre-fix fixture history replayed as a permanent
  guard. This is deliberately *not* required of the story that carries the fix —
  it is proof that can afford to wait, and loading it onto the unblock is what
  made the original story unbuildable.
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
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006]
```

US1 is the unblock and takes no edge: it carries the fix, and its PR is the one
that turns the required check green. US2 and US3 both take **merge**-edges on
US1 rather than on each other — neither needs the other's work, so once US1
lands they are independent and may run in either order or concurrently.

The 2026-08-12 split deliberately keeps harness and fix together in US1 and
moves only the *heavy standing proof* (15 cycles, committed fixture regression)
to US2. Everything US1 carries must clear a red check on the way in, so US1
holds the minimum that proves the fix — 3 cycles and an evidence file — and not
one requirement more.

Story numbers were reassigned rather than appended: nothing from 032 has ever
landed — all four attempts were killed and only an unmerged salvage branch
exists — so no landed number is being reused, and the immutability rule is not
engaged.
