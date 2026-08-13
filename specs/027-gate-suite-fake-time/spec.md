---
state: landed
# US2 COMPLETED BY THE OPERATOR 2026-08-13, on Bryan's explicit instruction
# ("correct the spec to reflect reality, then complete it yourself"). This is
# the fail-out path, used deliberately and counted — not a precedent to reach
# for. What happened: the relaunched node produced correct, complete work and
# was rejected five times by the judge on S4 alone, because the scenario
# carried "~2m40s" as if it were a threshold when the spec's own wording said
# "toward" (verify/approximate-targets-are-read-as-hard-thresholds). The
# refiner's defect, not the agent's. S4 and SC-001/SC-002 now state the two
# real thresholds — no test at 15s or more, and at least 40% off the before
# total — and say plainly that no other figure decides anything.
# The landed diff IS the agent's work, captured from its worktree before
# teardown (six commits, 46db521 back to 74c5519) and re-verified by the
# operator rather than trusted: sweep test 60.79s -> 1.81s, full clean-env
# suite green. It still faced the gates and the merge queue like any other
# landing. Measured result: suite 342.71s -> 172.82s (-50%), no test >= 15s.
# US1 LANDED 2026-08-13 at a564b8c (PR #51, first attempt) — measured by the
# operator: the two heartbeat tests went 60.26s/60.18s -> 12.14s/12.09s.
# US2 was KILLED the same day after FOUR attempts, gates green every time
# (191-192s, exit 0), on criteria no diff could satisfy: S1 named the commit
# message, S3 required a mutation that must be reverted before commit. Bryan
# authorized handling the escalation; resolved KILL 14:57Z. US2's scenarios,
# FR-005, FR-008, SC-001 and SC-003 were rewritten to Constitution VIII
# (D-037) — evidence pasted into one comment block above the test, the only
# home FR-004's tests-only scope allows — and plan.md trap 9 now states that
# path outright. Relaunched the same morning; US1 is landed and derives out.
# Flipped ready 2026-08-11 PM CT on the operator's word ("flip all 6"); the
# paused roadmap dispatches serially (max_concurrent_epics=1) in dir order
# once unpaused.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `ci/gate-suite-waits-out-real-clocks` (critical), then refined against the
# tree at 9594787 on 2026-08-11. Every ref below was re-read at that commit.
---

# Feature Specification: The gate suite stops waiting out real clocks

Three tests are ~53% of every gate run, measured 2026-08-11 in a clean env
(scratch `FACTORY_ROOT`, Telegram vars unset): 60.81s + 60.20s + 60.19s of a
~5m45s suite — 181.2s of a 182.58s three-test run. The gate is `uv run pytest
-q` (`factory.yaml:23`), paid on every attempt and every recovery of every
node, and a slow gate courts the 600s gate TIMEOUT that burned 006/us4's
first attempt (verification store, 2026-08-09: gate `TIMEOUT` at 600.0s,
verdict FAIL; the node passed on attempt 3).

The mechanism, re-verified against the tree: both files already run Temporal
time-skipping (`tests/test_interpreter.py:1659`,
`tests/test_workgraph_sweep.py:366`), but time-skipping advances **workflow
timers only** — an activity that is executing runs on the real clock. For the
two `tests/test_interpreter.py` tests the arithmetic closes exactly:
`heartbeat_then_block=True` makes the scripted agent heartbeat once and block
(`tests/test_interpreter.py:1291-1298`), each of three independent nodes
carries `timeout_override_s=20` so the derived heartbeat bound is
`max(20/2, 5×1s) = 10s` (`factory/workgraph/workflow.py:386-391`), the epic
dispatches them sequentially (`max_concurrent_nodes` defaults to 1,
`workflow.py:418`), and `_AGENT_RETRIES` carries `maximum_attempts=2`
(`workflow.py:302-305`) so each node's activity times out, is retried by
Temporal, blocks again, and times out a second time before the failure reaches
the workflow: 3 nodes × 2 activity attempts × 10s ≈ 60s per test, twice.

The third test is different, and this spec says so plainly: the received
explanation is **wrong** for `test_no_epic_ever_dispatches_a_node_with_an_unmet_dependency`
(`tests/test_workgraph_sweep.py:1476`). None of its five scripted epics sets
`heartbeat_then_block` (`tests/test_workgraph_sweep.py:1416-1473`), so its
~60s cannot come from the derived heartbeat bound. Static reading accounts for
at most ~5-10s of it (the kill epic's cancellation riding a 5s-throttled
heartbeat batch). Its composition must be measured before it is fixed — a fix
aimed at the wrong mechanism ships the minute intact.

What must survive is exactly what each test proves today: dead-agent detection
under a **derived** (not fixed) heartbeat bound including the history
assertion on the scheduled `heartbeat_timeout`; delivery of the
last-heartbeat snapshot to teardown; and the SC-002 mid-flight dependency
sweep across all five epic shapes. This spec removes the waiting, never the
proof.

## User Scenarios & Testing

### User Story 1 - The two heartbeat-timeout tests stop paying the bound they assert (Priority: P1)

`test_a_dead_agent_is_still_detected_under_a_derived_heartbeat_timeout`
(`tests/test_interpreter.py:2613`, 60.20s) and
`test_a_heartbeat_timeout_delivers_its_snapshot_to_teardown`
(`tests/test_interpreter.py:3468`, 60.19s) each wait out six real
heartbeat-timeout firings. The fix ends the real waiting — by advancing the
test server's clock past the pending activity's heartbeat deadline, or,
failing that, by shrinking the composition per plan.md's fallback — while
every assertion each test makes today survives verbatim, still exercised
through a **server-fired** heartbeat timeout carrying
`last_heartbeat_details`, never through a scripted raise.

**Goal**: both tests keep proving dead-agent detection under a derived bound
and heartbeat-snapshot delivery to teardown, at seconds instead of a minute
each.

**Independent Test**: in a clean env, run
`tests/test_interpreter.py -k "dead_agent_is_still_detected or heartbeat_timeout_delivers_its_snapshot" --durations=10`;
both pass, each far below its 60s baseline, and temporarily mutating the
production derivation or the payload delivery turns the matching test red.

**Acceptance Scenarios**:

1. **Given** a clean env (scratch `FACTORY_ROOT`, `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_CHAT_ID` unset, `scripts/ergane-env.sh` never sourced), **When**
   the restructured dead-agent test runs, **Then** it passes while still
   asserting all of: us1's attempt-1 teardown carries
   `termination == Termination.TIMEOUT` and `last_snapshot == SNAPSHOT`;
   `"run_gates"` appears in us1's sequence; us1 ends `MERGED`; and the
   scheduled `run_agent_attempt`'s `heartbeat_timeout` read from history
   equals the **derived** bound — half the attempt timeout, strictly greater
   than the 5s floor so it stays distinguishable from the old fixed constant —
   and `--durations` reports the test at 15s or less (target ≤3s), down from
   a recorded 60.20s baseline.
2. **Given** the same clean env, **When** the restructured snapshot-delivery
   test runs, **Then** it passes while still asserting that `SNAPSHOT` reached
   `teardown_for("us1", 1).last_snapshot` off the heartbeat-timeout path, with
   `termination == Termination.TIMEOUT`, `"run_gates"` in us1's sequence and
   us1 `MERGED` — and `--durations` reports it at 15s or less (target ≤3s),
   down from a recorded 60.19s baseline.
3. **Given** `_agent_heartbeat_timeout` temporarily mutated in the worktree to
   return a fixed `timedelta(seconds=5)` (the old constant; mutation never
   committed), **When** the restructured dead-agent test runs, **Then** it
   FAILS on its history assertion — the test still distinguishes a derived
   bound from a fixed one — and passes again once the mutation is reverted.
4. **Given** `_attempt_timeout` temporarily mutated in the worktree to discard
   `last_heartbeat_details` and record `None` (mutation never committed),
   **When** the restructured snapshot-delivery test runs, **Then** it FAILS on
   its `last_snapshot` assertion — the delivery path is still what is proven —
   and passes again once the mutation is reverted.

### User Story 2 - The dependency sweep's minute is measured, then removed (Priority: P2)

`test_no_epic_ever_dispatches_a_node_with_an_unmet_dependency`
(`tests/test_workgraph_sweep.py:1476`, 60.81s) runs five epics through the
harness it imports from `tests/test_interpreter.py` (the import block at
`tests/test_workgraph_sweep.py:108-124`) and pays a minute
no mechanism in this spec's finding explains. This story diagnoses where the
real time goes — per-epic wall-clock attribution, in the tree, before any
restructuring — and then removes the identified waits while keeping all five
epic shapes and both assertion loops (the mid-flight `verified` check and the
converse final check) intact and non-vacuous.

**Goal**: the SC-002 sweep keeps every proof over every epic shape it runs
today, at seconds instead of a minute, with the minute's composition recorded
as measurement rather than assumption.

**Independent Test**: in a clean env, run the sweep test alone with the
diagnosis instrumentation and read the per-epic attribution; then run the
restructured test and confirm every per-epic expected end-state map, the
non-empty `script.observed`, and both assertion loops still execute, far
below the 60.81s baseline.

**Evidence rule for every scenario below**: each is decided from the diff alone
(Constitution VIII). The evidence lives in **one comment block directly above
the sweep test** in `tests/test_workgraph_sweep.py` — FR-004 keeps this story
inside `tests/`, so that block is the only legal home for it. Paste tool output
verbatim, command line included; a described measurement is not a recorded one.

**Acceptance Scenarios**:

1. **Given** the un-restructured sweep test instrumented with per-epic
   wall-clock timing, **When** it runs once in a clean env, **Then** the diff's
   comment block carries a per-epic attribution table accounting for at least
   90% of the test's wall clock, naming which of the five epics pay real time
   and through which mechanism — and where the measurement contradicts
   plan.md's leads, the block says so: the tree wins.
2. **Given** the restructured sweep test, **When** the diff is read, **Then**
   all five epic shapes still run; each epic still ends in its expected
   per-node state map; `script.observed` is non-empty for every epic; the
   mid-flight loop still asserts every dispatched node's dependencies were
   `verified` at dispatch and the converse final loop still runs; `"overrun"`
   and `"unscripted"` still never appear — and the comment block carries the
   **pasted `--durations` line** for this test showing 15s or less (target
   ≤5s) beside its recorded 60.81s baseline.
3. **Given** `_edges_satisfied` temporarily mutated in the worktree so the
   pass-edge conjunct treats an unverified dependency as satisfied (mutation
   never committed), **When** the restructured sweep test runs, **Then** the
   comment block carries the **pasted failure output** of that run — assertion
   text and test id — followed by the **pasted passing line** after revert.
   The mutation stays uncommitted; its transcript is the artifact, and the
   transcript is what this scenario is decided on.
4. **Given** US1 landed and US2 applied, **When** the full suite runs in a
   clean env as `uv run pytest -q --durations=30`, **Then** the comment block
   carries the **pasted summary line** (total wall clock) before and after,
   plus the pasted `--durations=30` head, and both thresholds hold: **no test
   at 15s or more**, and the after total is **at least 40% below the pasted
   before total**. Those two numbers decide this scenario; no other figure in
   this spec is a threshold.

## Functional Requirements

- **FR-001**: The dead-agent test MUST retain its full present assertion set —
  TIMEOUT classification, snapshot at teardown, `run_gates` in sequence,
  `MERGED` end state, and the history assertion that the scheduled
  `heartbeat_timeout` equals the derived bound — and the asserted bound MUST
  remain strictly greater than the 5s floor, so a regression to a fixed
  constant stays detectable.
- **FR-002**: The snapshot-delivery test MUST retain its full present
  assertion set, with the snapshot still arriving via
  `TimeoutError.last_heartbeat_details` into `_attempt_timeout` and out to
  teardown.
- **FR-003**: The TIMEOUT both tests exercise MUST be a genuine server-fired
  heartbeat timeout. Simulating it by making the blocked activity raise is
  named in advance as a wrong fix: an `ActivityError` whose cause is an
  `ApplicationError` bypasses the `ActivityTimeoutError` branch of
  `_attempt_timeout` and the snapshot path loses its subject.
- **FR-004**: Every change in this spec MUST be confined to `tests/`. No file
  under `factory/` changes, `factory.yaml` does not change, and no dependency
  is added.
- **FR-005**: The sweep story MUST produce a measured per-epic attribution of
  the test's real time before restructuring it, and MUST record it in the
  comment block above the test. No requirement of this spec may name the
  commit message: the judge is given the diff and never reads one
  (Constitution VIII / D-037).
- **FR-006**: The restructured sweep test MUST keep all five epic shapes, the
  per-epic expected end-state assertions, the non-vacuity assertion on
  `script.observed`, and both dependency-assertion loops.
- **FR-007**: No requirement of this spec may be satisfied by pytest markers
  or by moving a test out of the gate tier. Nothing passes `-m` in the gate
  (`factory.yaml:23`) or CI (`.github/workflows/test.yml:20`), so a marker is
  decoration. If a wait proves irreducible without changing what the gate
  runs, the node MUST park a question for the operator rather than ship a
  tier split.
- **FR-008**: Every duration measurement this spec calls for MUST be taken in
  a clean env — scratch `FACTORY_ROOT`, `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` unset, `scripts/ergane-env.sh` never sourced — because a
  suite run with the operator env exported writes rows into the live evidence
  store and pages the operator
  (`hardening/test-suite-writes-to-the-live-evidence-store`). Before/after
  numbers MUST appear in the comment block as **pasted tool output including
  the command line** — a prose claim is not a record, and the pasted command
  line is what evidences the clean env.

## Success Criteria

- **SC-001**: Full-suite wall clock in a clean env drops at least 40% below the
  recorded baseline, with the actual before and after figures pasted into the
  comment block above the sweep test. (The ~2m40s figure this spec carried
  before 2026-08-13 was an estimate made before the minute's composition was
  measured; it was never a threshold, and stating it as one cost five attempts
  on work that had already cut the suite in half. See
  `verify/approximate-targets-are-read-as-hard-thresholds`.)
- **SC-002**: `uv run pytest -q --durations=30` in a clean env reports no test
  at 15s or more; the three tests this spec names each run at 15s or less
  (targets: ≤3s, ≤3s, ≤5s — targets, not thresholds; the 15s bar decides).
- **SC-003**: Each of the three tests demonstrably still bites: every mutation
  scenario (US1 scenarios 3-4, US2 scenario 3) was observed red and then
  reverted, with the red runs pasted into the comment block above the test
  they exercise.
- **SC-004**: The combined diff of both stories touches only files under
  `tests/`.

## Edge Cases

- **The manual-clock mechanism may not exist in practice.** Whether
  `WorkflowEnvironment.sleep` advances the time-skipping server past a
  *pending activity's* heartbeat deadline is unverified in this tree; the
  plan's first US1 task proves or disproves it before anything is
  restructured, and the fallback (plan.md § US1 fallback) is specified for
  the disproven case.
- **The 5s floor collides with "shrink the bounds".** The derived bound is
  floored at `5 × HEARTBEAT_INTERVAL_S = 5s`, and the old defect the
  dead-agent test guards against was a *fixed 5s bound* — so a shrunken
  composition whose derived half equals the floor asserts a number
  indistinguishable from the defect. Any shrunken timeout must keep
  `timeout/2 > 5s` (e.g. `timeout_override_s=12` → 6s).
- **The retry policy doubles every wait.** `_AGENT_RETRIES` carries
  `maximum_attempts=2`, so each blocked node pays its bound twice before the
  workflow hears about it. Duration arithmetic that forgets the retry
  under-predicts by half.
- **No committed duration assertions.** A test that asserts its own wall
  clock flakes on a loaded runner. The thresholds in this spec are acceptance
  evidence read from `--durations` output by the implementer and the
  operator, never `assert elapsed < N` in the suite.
- **Abandoned activity coroutines at worker exit.** A heartbeat-timed-out
  activity's coroutine keeps running on the worker until shutdown cancels it;
  a restructuring must not leave the `Worker` context waiting on one.

## Assumptions

- The three tests' current assertions are the correct contract; nothing
  depends on their real elapsed time.
- `WorkflowEnvironment.sleep` is part of the already-approved `temporalio`
  dependency; no new dependency is implied by either direction.
- The 2026-08-11 baseline (60.81s / 60.20s / 60.19s, ~5m45s suite) was
  measured in a clean env and is the comparison point for every "down from"
  in this spec.
- The finding's refs were re-verified at `9594787` and are accurate today;
  plan.md carries the grep anchors for when they rot.

## Out of Scope

- **Moving any test out of the gate tier**, or any edit to `factory.yaml`'s
  gate command. The finding names it a last resort enforced in the gate
  command itself; changing what green means is an operator decision that
  would need its own `docs/decisions.md` entry, not a side effect of a
  test-speed story (FR-007 routes the blocked case to a question instead).
- **Production changes** to the heartbeat derivation, `_AGENT_RETRIES`, the
  worker throttle configuration, or the adapter's heartbeat interval. The
  suite adapts to the factory, not the reverse.
- **Other slow tests.** Anything under the 15s bar (e.g. the `SETTLE_S`
  sleeps in `tests/test_interpreter.py`) is left alone; this spec removes the
  53%, not every second.
- **The CI-log delivery gap** (`interpreter/ci-failure-never-reaches-an-agent`)
  that the finding cites for why markers are decorative — separate finding,
  separate spec.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
```
