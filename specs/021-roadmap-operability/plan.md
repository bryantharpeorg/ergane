# Implementation Plan: Roadmap Operability

**Branch**: `021-roadmap-operability` | **Date**: 2026-08-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-roadmap-operability/spec.md`

## Summary

One string, two input fields, one wait, and one notification path. Small in
diff, large in consequence: the scheduler has never completed a pass, cannot
express the parallelism 007 built, cannot idle, and cannot say when it is
broken. Everything here is inside `factory/roadmap/`, `factory/activities/
roadmap_activities.py`, and the tests — no new component, no new dependency, no
new workflow type.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined, each
verified against the tree on 2026-08-09 — and T001 re-verifies them against the
tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+; the worker host runs 3.13.

**Primary Dependencies**: none added. `temporalio` is already the roster's.

**Verified reuse inventory** (`file:line` as of 2026-08-09; T001 re-checks):

*The defect*

- `factory/activities/roadmap_activities.py:443-445` —
  `client.list_workflows('ExecutionStatus = "RUNNING"')`. Verified live against
  the `factory` namespace: this spelling raises
  `RPCError: invalid query: invalid expression: invalid ExecutionStatus value
  'RUNNING'`; `'ExecutionStatus = "Running"'` returns cleanly. Temporal's
  visibility grammar wants the title-case enum name.
- `factory/activities/roadmap_activities.py:440-442` — the comment stating the
  production query is not exercised by tests. Read it before changing anything;
  it is the reason FR-002 exists.
- `_open_epics_provider` at `:454` — the seam. **Keep it.** FR-003.
- `count_open_epics` at `:458` — the activity the workflow calls, once per pass,
  from `factory/roadmap/workflow.py:622`.

*The node bound*

- `RoadmapInput` (`factory/roadmap/workflow.py:144-173`) — carries
  `specs_root`, `target_repo`, `proxy_url`, `max_concurrent_epics: int = 1`,
  `landing_config`, `config`, `poll_interval_s`, `carry_over`. **No node bound.**
- `_dispatch` (`:784`), the child start at `:870` — builds `EpicInput(graph,
  proxy_url, config, poll_interval_s, landing_config)`. Adding one keyword is
  the whole of FR-004.
- `EpicInput.max_concurrent_nodes: int = 1` (`factory/workgraph/workflow.py:393`)
  — the field already exists and the epic already validates it at `:606-613`.
  That validation is the shape FR-005 mirrors, and `max_concurrent_epics`'s own
  check at `factory/roadmap/workflow.py:546-553` is the closer precedent.
- `RoadmapStatus` / `roadmap_status` (`:456`) — where FR-005's reporting goes.

*The idle wait*

- `factory/roadmap/workflow.py:672-686` — the tail of the loop. `break` at
  `:686` is drain-and-exit; `:684` is the continue-as-new-if-work-was-done gate.
  US3 replaces the `break` path, and **must not** disturb `:656-657`, the
  quiescence CAN that fires after a child concludes.
- `_continue_as_new` (`:692`) and `RoadmapCarryOver` — the carry-over already
  holds parked findings, promotions, pause flag and the epic bound. Both new
  inputs must ride it, or a CAN silently resets them.
- Signals live at `:424-455` (`pause_roadmap`, `resume_roadmap`,
  `promote_spec`); `rescan` joins them with the same shape — set a flag, let the
  loop observe it. `workflow.wait_condition(..., timeout=...)` is the SDK call
  for signal-or-timeout.

*The notification*

- `factory/notify/service.py` — the Telegram bridge. `SIGNAL_NAME` (`:64`) and
  `QUESTION_SIGNAL_NAME` (`:73`) are the inbound paths; the outbound send is
  where a roadmap failure notice attaches.
- `factory/verify/store.py` — durable rows before the send (`insert_escalation`
  at `:439`, `insert_question` at `:663`). FR-010's "recorded regardless of
  delivery" is that same write-before-send discipline, and the doctor's ledger
  (`factory-doctor report`) is the other candidate home — pick one in T001 and
  say which.

**Storage**: none added.

**Testing**: `pytest`, `WorkflowEnvironment.start_time_skipping()`.
`tests/test_roadmap_workflow.py` (or whatever 009's suite is named — T001
confirms) holds the scripted-seam tests that must keep passing.
`tests/test_live_judge.py` is the live-tier precedent for FR-002: it reads
credentials from the environment and skips with a named reason when they are
absent.

**Project Type**: single Python package; no new module directory.

## Constitution Check

- **I (build order)**: four slices, each usable; US1 alone makes the scheduler
  work at all.
- **II (test-first)**: every task pairs a failing test with implementation.
  FR-002 is the story where this bites hardest — the test must be written so it
  fails against the shipped string.
- **III (dependencies)**: none added.
- **IV (determinism at the core)**: workflow code shells nothing; the capacity
  read stays an activity, and the idle wait uses `workflow.wait_condition`, not
  `asyncio.sleep`.
- **V (credentials)**: the live test reads the environment the operator already
  exports; no key reaches a workflow input, a signal payload, or a notification
  body.
- **VI (salvage)**: untouched.
- **VII (persona routing)**: untouched.

## Approach by story

### US1 — the capacity read and its proof (FR-001…FR-003)

Change the query to the title-case spelling. Then the part that matters: add a
live-tier test that calls the production read against a real Temporal and
asserts it returns known-open ids.

**The test must be able to fail.** Asserting "no exception raised" against an
empty namespace passes under a broken filter too (spec § Edge Cases). Start a
throwaway workflow with an `epic-`-prefixed id, assert the read finds it, and
assert a non-`epic-` workflow is excluded. Skip with a named reason when no
server answers.

Consider deriving the query from the SDK's own enum rather than a literal, if a
spelling the client exposes round-trips — that removes the class of defect
rather than this instance. Verify empirically before committing to it; if no
such symbol exists, a module-level constant with the live test pinned to it is
the honest second best.

### US2 — the node bound (FR-004, FR-005)

Add the field to `RoadmapInput` with default 1, validate it at run start beside
`max_concurrent_epics` (`:546-553` is the pattern, including the `bool`
exclusion — `isinstance(True, int)` is `True` and a `True` bound is a wiring
error), pass it in `_dispatch`'s `EpicInput`, carry it through
`RoadmapCarryOver`, and report both bounds in `roadmap_status`.

Naming: `max_concurrent_nodes`, matching `EpicInput`'s field exactly. Do not
invent a roadmap-local synonym — one concept, one word, and the D-021 sweep bans
the alternatives anyway.

### US3 — the idle wait (FR-006…FR-008)

Add `idle_rescan_s: int | None = None` to `RoadmapInput` and a `rescan` signal
setting a flag. At the loop tail, where `break` is today:

```python
if completed_this_run:
    return await self._continue_as_new(request)
if request.idle_rescan_s:
    await workflow.wait_condition(
        lambda: self._rescan_requested or not self._paused_unchanged,
        timeout=timedelta(seconds=request.idle_rescan_s),
    )
    self._rescan_requested = False
    return await self._continue_as_new(request)
break
```

Three things this must get right:

- **`None` means today.** No idle config, no behaviour change, `break` as it
  stands (FR-006, acceptance 5).
- **Continue-as-new on every idle wake**, not a counter. Zero children are open
  at that point, so the boundary is trivially safe, and CAN-per-wake keeps
  history flat by construction rather than by arithmetic.
- **`wait_condition` with a timeout returns on either path** — signal or
  timeout — and the code must not care which. Do not branch on the return value
  to decide whether to re-read; always re-read.

`pause_roadmap` must win over `rescan`: the existing pause wait at `:664-666`
already parks, and idle must not route around it.

### US4 — the failure reaches someone (FR-009, FR-010)

The roadmap cannot notify about its own failure from inside itself — a run that
raises does not get to send a message afterwards. Two viable shapes; T001 picks
one and records which:

- **A supervising surface** reads recent `RoadmapWorkflow` executions and
  reports consecutive failures. Honest, and it works for failures that happen in
  continue-as-new rather than in the loop (spec § Edge Cases). Costs a component.
- **A try/except at the loop boundary** that records and notifies before
  re-raising. Cheaper, but blind to a failure outside the `try`.

Whichever is chosen, the durable write happens **before** the send (the
escalation precedent at `factory/verify/store.py:439`), so a notifier that is
down loses the message and not the fact — otherwise this story recreates the
blind spot one layer in.

Consecutive-count semantics: notify on the first failure and on count
thresholds, never once per failure; reset and report recovery on the first
success.

## Traps

1. **Do not delete the seam.** `_open_epics_provider` looks like the thing that
   caused this. It is not — the time-skipping server genuinely cannot answer the
   production query, and removing the seam turns 009's workflow suite red for no
   gain. The missing piece is coverage on the *far* side of the seam (FR-003).

2. **A live test that cannot fail is worse than none.** Against an empty
   namespace, a broken filter and a working one both return zero rows. Assert on
   known-open ids, and prove the test fails under the shipped spelling before
   claiming the story done.

3. **The live tier is currently red for an unrelated reason.** The proxy writes
   no `SpendLogs` rows since the v1.95.0 upgrade, so `tests/test_live_judge.py`
   errors with *"no spend-log row appeared for the judge's key within 90s"* —
   19 errors as of 2026-08-09, filed as
   `interpreter/ledger-records-dollars-without-tokens`. That is **not** this
   spec's tests failing. Do not "fix" it, and do not conclude the live tier is
   broken and skip building FR-002 into it.

4. **Carry-over resets what it does not carry.** Both new inputs must ride
   `RoadmapCarryOver`, or the first continue-as-new silently reverts the node
   bound to 1 and idle mode to off — and CAN fires after every epic, so the
   reversion would look like an intermittent bug rather than a missing field.

5. **`isinstance(True, int)` is `True`.** The existing bound validation
   explicitly excludes `bool` (`:546-548`). The new bound needs the same
   exclusion or `max_concurrent_nodes=True` becomes a bound of 1 by accident.

6. **The idle wait must consume no activity.** `workflow.wait_condition` is the
   call. Anything that re-reads the corpus on a beat is the interval polling
   009's FR-004 refused, and it would make an overnight idle cost thousands of
   git invocations — one `drift_for_spec` per landed spec, per wake.

7. **This spec's own epic runs under the scheduler it repairs.** If the roadmap
   dispatches 021, US1's node is editing the capacity read the parent is calling
   between passes. Prefer dispatching 021 by hand; if it must run scheduled,
   expect the parent to be mid-flight across its own fix and do not treat that
   as a defect in the story.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| The live test passes vacuously | Empty namespace ≠ working filter | Trap 2: assert known-open ids, prove it fails on the old string |
| Removing the seam to "fix it properly" | The seam looks like the culprit | Trap 1 and FR-003 keep it explicitly |
| Idle mode changes today's behaviour | Every current caller drains and exits | FR-006: `None` default, asserted by acceptance 5 |
| History grows overnight | An idle loop that re-reads on a beat | CAN on every idle wake; SC-005 measures an idle night |
| CAN reverts the new inputs | Carry-over is an explicit allowlist | Trap 4, asserted across a CAN boundary |
| US4 misses failures outside the loop | A CAN-time failure has no `try` around it | T001 picks the shape and records why; the supervising-surface option is the one that covers it |
| The scheduler repairs itself mid-run | 021 may be dispatched by the roadmap | Trap 7 — dispatch by hand |
