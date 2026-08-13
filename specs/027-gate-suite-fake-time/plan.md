# Plan: The gate suite stops waiting out real clocks

All line references were read at commit `9594787` on 2026-08-11. They are cited
so you can find the code, not so you can trust the numbers — landings move them
(010's plan watched every one of its finding's refs go stale in a day). Beside
each anchor is the construct to grep for; if a citation does not match the
tree, the tree wins and you say so in your commit message.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The dead-agent test | `tests/test_interpreter.py:2613` (`def test_a_dead_agent_is_still_detected`) | US1 — restructured |
| The snapshot-delivery test | `tests/test_interpreter.py:3468` (`def test_a_heartbeat_timeout_delivers`) | US1 — restructured |
| The derivation-shape test | `tests/test_interpreter.py:2552` (`test_heartbeat_timeout_is_derived_from_attempt_timeout_and_floored`) | US1 — **untouched**; it proves the bound's shape without blocking, and is the boundary of this story |
| `ScriptedWorld.heartbeat_then_block` and its block | `tests/test_interpreter.py:863`, `:1291-1298` (`heartbeat_then_block`) | US1 — the comment here is stale, see trap 3 |
| The time-skipping `env` fixture | `tests/test_interpreter.py:1656-1663` (`start_time_skipping`) | US1 |
| `start_epic` and its worker throttle caps | `tests/test_interpreter.py:1666-1711`, caps at `:1699-1702` (`max_heartbeat_throttle_interval`) | US1 drive loop; US2 lead 1 |
| `run_epic` / `wait_for` / `WAIT_TIMEOUT_S = 10.0` | `tests/test_interpreter.py:1714`, `:1751`, `:250` | both stories |
| The sweep test | `tests/test_workgraph_sweep.py:1476` (`def test_no_epic_ever_dispatches`) | US2 — diagnosed, then restructured |
| Its five epic shapes | `tests/test_workgraph_sweep.py:1416-1473` (`def _epics`) | US2 — all five survive |
| The sweep's harness import | `tests/test_workgraph_sweep.py:108-124` (`from tests.test_interpreter import`) | US2 — why the merge-edge exists |
| The sweep's own `temporal` fixture | `tests/test_workgraph_sweep.py:363-370` | US2 |
| `_agent_heartbeat_timeout` — derived, floored | `factory/workgraph/workflow.py:383-391` (`_AGENT_HEARTBEAT_TIMEOUT_FLOOR`) | read-only; US1 mutation target (S3) |
| `_AGENT_RETRIES`, `maximum_attempts=2` | `factory/workgraph/workflow.py:302-305` | read-only — why every bound is paid twice |
| Agent activity scheduling | `factory/workgraph/workflow.py:1569-1585` (`heartbeat_timeout=_agent_heartbeat_timeout`) | read-only, context |
| `_attempt_timeout` and `last_heartbeat_details` | `factory/workgraph/workflow.py:1609-1640` | read-only; US1 mutation target (S4) |
| `_edges_satisfied` — the two edge conjuncts | `factory/workgraph/workflow.py:915-927` | read-only; US2 mutation target (S3) |
| `max_concurrent_nodes: int = 1` | `factory/workgraph/workflow.py:418` | why the three nodes pay sequentially |
| `HEARTBEAT_INTERVAL_S = 1.0` | `factory/workgraph/adapter.py:98` via `factory/activities/agent_activities.py:141` | why the floor is 5s |
| The gate command, no `-m` anywhere | `factory.yaml:23`, `.github/workflows/test.yml:20` | why markers are decorative (FR-007) |

## Traps

### Trap 1 — the env is already time-skipping; adding more of it fixes nothing

Both files use `start_time_skipping()` and have for their whole lives. The 60s
is not a workflow timer anyone forgot to skip — it is the real clock an
*executing activity* runs on, which time-skipping never touches. The plausible
wrong fix is to hunt for an unskipped timer or to shrink workflow-side
timeouts (`escalation_timeout_s`, `poll_interval_s`): those are already free.
The only clocks that cost anything here are the ones an activity is holding
open.

### Trap 2 — simulating the timeout with a raise breaks the very path the tests prove

It is tempting to have the blocked activity raise instead of block, so the
workflow "sees a failure" immediately. Wrong fix, named in advance (FR-003):
a raise surfaces as an `ActivityError` whose cause is an `ApplicationError`,
`_attempt_timeout` (`workflow.py:1623-1635`) only reads
`last_heartbeat_details` off an `ActivityTimeoutError`, so the snapshot
assertion loses its subject — teardown would record `None` and US1-S2 fails.
The heartbeat timeout must genuinely fire at the server: either the clock is
advanced past its deadline, or a real (short, floored-above) bound elapses.

### Trap 3 — the comment beside the block is wrong twice, and sizing a fix to it under-fixes

`tests/test_interpreter.py:1291-1298` says the blocked attempt "pays one
heartbeat timeout (5s) and no more". Both halves are stale: the bound is
*derived* (10s at `timeout_override_s=20`, not 5s), and `_AGENT_RETRIES`
carries `maximum_attempts=2`, so Temporal retries the timed-out activity once
— the fake blocks again and the bound is paid **twice per node** before the
workflow hears anything. Six firings per test, not three. A fix that budgets
for the comment's arithmetic will report success while half the wait remains.
Correct the comment in the same edit.

Related decoy: the worker's `max_heartbeat_throttle_interval=5s`
(`:1699-1702`) throttles how often heartbeats are *sent*; lowering it does not
shrink the heartbeat *timeout*. It is a US2 lever (cancellation delivery), not
a US1 one.

### Trap 4 — the sweep's minute is NOT US1's mechanism; copying US1's fix ships the minute intact

None of the sweep's five epics sets `heartbeat_then_block`
(`tests/test_workgraph_sweep.py:1416-1473` — verified at `9594787`), so the
finding's mechanism cannot explain its 60.81s. Static reading closes at most
~5-10s of it. Leads to check, as hypotheses and not conclusions — the
measurement is the deliverable, and the tree wins over every one of them:

1. The kill epic (`await_cancel=True`, `signal_during={"us1": "kill_epic"}`):
   cancellation is delivered in a heartbeat *response*, heartbeats are
   throttled to one RPC per 5s (`:1699-1702`), and the `await_cancel` loop is
   bounded at `WAIT_TIMEOUT_S = 10s` (`:1300-1313`). Note the sweep, unlike
   the interpreter's kill test, never asserts `script.cancellations` — a
   cancellation that silently never lands spins the full 10s and still
   passes.
2. Worker shutdown at each `start_epic` exit awaiting an activity coroutine
   the server has already abandoned.
3. Server-side retry backoff on any scripted activity failure.
4. Anything else the instrumentation names — five epics run in one test, so
   attribute per epic label first, then per activity within the guilty
   epic(s).

The wrong fix is restructuring the sweep to "not block on heartbeats" — it
never did — and declaring the minute fixed because the interpreter tests got
faster. US2-S1 (diagnosis first, recorded attribution) exists to make that
impossible.

### Trap 5 — markers are decorative, and a tier split is not this spec's to make

Nothing passes `-m` in the gate (`factory.yaml:23` — `uv run pytest -q`) or in
CI (`.github/workflows/test.yml:20`). A `@pytest.mark.slow` therefore excludes
nothing anywhere; it is documentation wearing a mechanism's clothes. And a
real tier split means editing the gate command — changing what green means —
which is an operator decision with a decisions-log entry, out of scope by
FR-007 and Out of Scope. If a wait proves irreducible, park a question. Do not
ship a marker, and do not touch `factory.yaml`.

### Trap 6 — never measure with the operator env exported

`hardening/test-suite-writes-to-the-live-evidence-store`: a suite run with the
operator's env writes real rows into the live evidence store and pages the
operator's phone. Every measurement in this spec runs with a scratch
`FACTORY_ROOT`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` unset, and
`scripts/ergane-env.sh` never sourced. The tasks spell the exact invocation
inline; use it verbatim.

### Trap 7 — shrinking into the floor erases the assertion's meaning

The fallback shrinks `timeout_override_s`, and the floor is
`5 × HEARTBEAT_INTERVAL_S = 5s`. The old defect this test guards against was a
*fixed 5-second bound* — so a shrunken timeout whose derived half lands ON the
floor (any `timeout_override_s ≤ 10`) makes the history assertion expect 5s,
indistinguishable from the defect, and US1-S3's mutation check stops failing.
Keep `timeout/2` strictly above 5s: `timeout_override_s=12` (6s bound) is the
smallest comfortable choice. FR-001 states this; the mutation check enforces
it.

### Trap 8 — these line numbers rot before dispatch

Read at `9594787`; an epic is running on this host and landings move files.
Grep for the construct, never the number: `heartbeat_then_block`,
`start_time_skipping`, `_agent_heartbeat_timeout`, `_AGENT_RETRIES`,
`last_heartbeat_details`, `_edges_satisfied`,
`def test_no_epic_ever_dispatches`, `max_heartbeat_throttle_interval`.

### Trap 9 — US2 already died four times here: the judge sees the diff and nothing else

This story was dispatched once before (2026-08-13) and its node was killed after
**four attempts, gates green every time** (191–192s, exit 0). Every attempt
failed the same four judge findings, and every finding said a variant of "this
evidence is not in the diff." The judge is handed the diff and the criteria
snapshot — not the base tree, not your commit message, not your terminal
(Constitution VIII / D-037).

What that means for you, concretely:

- **Paste, never describe.** "Measured 12.1s in a clean env" is a claim the
  judge must take on faith and will not. The pasted `--durations` line, with
  the command that produced it, is evidence.
- **One home for all of it.** FR-004 confines this story to `tests/`, so the
  evidence cannot go in a `MEASUREMENTS.md` under `specs/` — that would be
  out of scope. Put every measurement in **one comment block directly above
  the sweep test** in `tests/test_workgraph_sweep.py`. Three previous attempts
  failed to find this path; it is now stated rather than left to inference.
- **The mutation transcript is the deliverable, not the mutation.** Scenario 3
  wants `_edges_satisfied` broken, the test observed red, then reverted. The
  revert erases the proof, so the *pasted red output* (assertion text and test
  id) followed by the *pasted green line* after revert is what the diff must
  carry.
- **Four things must appear in that block**: the per-epic attribution table,
  this test's before/after `--durations` lines, the mutation's red-then-green
  transcript, and the full-suite before/after totals with the
  `--durations=30` head.

## Approach

### US1 — advance the clock the activity is holding, or shrink around the floor

**Primary path.** The time-skipping server accepts manual advancement:
`WorkflowEnvironment.sleep(duration)` on the env object. Whether a manual
advance fires the heartbeat timeout of a *pending activity* is the one
unverified fact this story turns on, so prove it first (T004) with a throwaway
probe in the worktree — a one-node `heartbeat_then_block` epic driven by
`env.sleep(11)` pulses; if the epic completes in wall-time seconds with
`termination == TIMEOUT`, the mechanism is real. Then restructure both tests
from `run_epic(env, script, graph=graph)` to a drive loop of the shape:

```python
async with start_epic(env, script, graph=graph) as handle:
    result = asyncio.create_task(handle.result())
    for _ in range(MAX_PULSES):          # bounded: a broken drive fails, not hangs
        if result.done():
            break
        await env.sleep(11)              # one derived bound (10s) + grace
    status = result.result()
```

Every existing assertion stays byte-identical — the point of the drive is that
nothing downstream of the timeout changes. Fix the stale comment (trap 3)
while editing the block. Delete the probe before committing; record in the
commit message which path was taken and the measured before/after durations.

**Fallback, if the probe disproves the mechanism.** Shrink the composition
instead: both tests assert only on `us1` (verified — every `teardown_for`,
`sequence`, and `states` assertion names us1 alone), so a single-node graph
with `timeout_override_s=12` keeps every assertion meaningful (6s derived
bound, strictly above the floor per trap 7) and costs 2 activity attempts ×
6s ≈ 12-13s per test — within the ≤15s acceptance bound, 120s → ~26s for the
pair. State in the test docstring why the timeout is 12 and why it must not
drop to 10 or below.

Either path: the derivation-shape test at `:2552` is untouched, `factory/` is
untouched, and the two restructured tests still reach `MERGED` through gates
and landing exactly as today.

### US2 — measure the minute, then take it apart

1. **Instrument before touching anything** (T009): wall-clock each of the five
   `run_epic` calls by epic label; if one epic dominates, timestamp the
   guilty epic's `ScriptedWorld` activity log (a monotonic time beside each
   `calls` entry — this edits shared infra in `tests/test_interpreter.py`,
   which is why US2 rides a merge-edge on US1). Run the single test with `-s`
   in the clean env. The attribution must cover ≥90% of the measured wall
   clock and it goes in the commit message and a comment above the test.
2. **Fix what the measurement names** (T010). If it is lead 1, the levers are
   test-side: assert (and if needed, accelerate) cancellation delivery rather
   than silently spinning `WAIT_TIMEOUT_S`; the worker throttle caps at
   `:1699-1702` are test infrastructure. If it is something else, fix that,
   and the recorded attribution explains the delta from this plan.
3. **Do not weaken the sweep to speed it**: all five shapes, both assertion
   loops, the `script.observed` non-vacuity check, and the
   `overrun`/`unscripted` guards survive verbatim (FR-006).
4. **Close the books** (T012): full-suite `--durations=30` in the clean env,
   before/after totals recorded, no test ≥15s anywhere.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A manual clock-drive loop instead of just lowering the timeouts | The floor (5s) and the retry (×2) put a hard ~10s-per-test under any real-elapsing approach, and a timeout at the floor is indistinguishable from the fixed-bound defect the test exists to catch (trap 7). Driving the clock removes the wait without touching what is asserted. |
| A probe task before the restructuring | The primary mechanism (`env.sleep` firing a pending activity's heartbeat timeout) is unverified in this tree; building both tests on it unproven risks a full attempt discovering it at the end instead of at the start. |
| A diagnosis task before the sweep fix | The received mechanism is provably absent from the sweep's five epics (trap 4); this factory has already paid twice for scenarios "declared, never demonstrated", and an unmeasured fix here would be a third. |
| Two stories with a merge-edge instead of one story | Different files, different mechanisms, different evidence — and both may edit `tests/test_interpreter.py` (US1 the tests and `ScriptedWorld` comment, US2 the shared log for instrumentation), which is exactly the collision `depends_on_merged` exists to prevent. |
| Mutation bite-checks instead of trusting the refactor | A restructured test can keep its assertion text and lose its subject (trap 2's failure mode passes every green run). Red-under-mutation is the only cheap proof the tests still catch the defects they were written for. |

## Verification

The gate is `uv run pytest -q`, green in the worktree, run only as the tasks
spell it (clean env, trap 6). Beyond green, this spec's evidence is numeric
and recorded: the `--durations` baselines before (T003/T008), the same
commands after (T007/T012), and the three mutation reds (T006/T011) — each
observed, then reverted, then noted in the landing commits. A green suite that
skipped the numbers has not verified this spec; the numbers are the spec.
