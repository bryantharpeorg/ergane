# Tasks: The gate suite stops waiting out real clocks

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

This spec refactors tests, so constitution II's "write FIRST, must fail" maps
onto it precisely, in two halves: the **baseline measurement is the red** — the
recorded 60s figures are the failing state every later task is judged against —
and the **mutation checks are the must-fail** — a restructured test that stays
green while the production code under it is broken has lost its subject, and
each one must be observed red before its story is done. A task that finds its
baseline already fast, or its mutation already caught, has found a defect in
this plan and reports it rather than skipping ahead.

Every measurement runs in the clean env its task spells out, verbatim —
plan.md trap 6: a suite run with the operator env exported writes rows into
the live evidence store and pages the operator. Never source
`scripts/ergane-env.sh`.

No task is marked `[P]`: within each story every task touches
`tests/test_interpreter.py`, `tests/test_workgraph_sweep.py`, or a temporary
mutation of `factory/workgraph/workflow.py`, and they are sequential by
design.

## Format: `[ID] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, grepping constructs rather than trusting line numbers
      (plan.md trap 8). Five claims, because each is load-bearing:
      `heartbeat_then_block=True` still appears in exactly two tests
      (`grep -n "heartbeat_then_block=True" tests/`); `_AGENT_RETRIES` still
      carries `maximum_attempts=2` (trap 3's ×2 arithmetic turns on it);
      `_agent_heartbeat_timeout` is still half-the-timeout floored at
      `5 × HEARTBEAT_INTERVAL_S` (trap 7 turns on the floor's value); the
      sweep's five epics still set no `heartbeat_then_block`
      (trap 4's whole premise); and `factory.yaml`'s gate is still
      `uv run pytest -q` with no `-m` anywhere (FR-007's premise). If any
      claim fails, the corresponding trap changes shape — fix the plan before
      dispatch.

---

## Phase 2: User Story 1 — The two heartbeat-timeout tests stop paying the bound they assert (Priority: P1) 🎯 MVP

**Goal**: dead-agent detection under a derived bound, and heartbeat-snapshot
delivery to teardown, proven at seconds instead of ~60s each — through a
genuine server-fired heartbeat timeout, never a scripted raise.

**Independent Test**: the two tests pass in a clean env far below their
baselines, and mutating the derivation or the delivery path turns the matching
test red.

### Baseline and probe for User Story 1 (measure FIRST — the baseline is the red)

- [ ] T002 [US1] Verify prerequisites in this worktree: plan.md's inventory
      claims hold here (grep the trap-8 constructs), and the full suite is
      green once via the clean-env invocation in T012's task body before any
      edit — constitution II gate; STOP and report blocked if not satisfied.
- [ ] T003 [US1] Record the baseline FIRST: run
      `env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID FACTORY_ROOT="$(mktemp -d)" uv run pytest tests/test_interpreter.py -k "dead_agent_is_still_detected or heartbeat_timeout_delivers_its_snapshot" -q --durations=10`
      — a scratch `FACTORY_ROOT` and no Telegram vars because the suite run
      with the operator env writes to the live evidence store (plan.md
      trap 6). Expect ~60s per test (60.20s / 60.19s at refinement); record
      the exact figures for the "down from" halves of the acceptance evidence
      (spec US1-S1, US1-S2). If either test is already fast, this spec's
      premise has moved — STOP and report.
- [ ] T004 [US1] Probe the primary mechanism before building on it (plan.md
      § US1): a throwaway one-node `heartbeat_then_block` epic driven by
      `await env.sleep(11)` pulses. If the epic completes in wall-clock
      seconds with `termination == Termination.TIMEOUT` and a delivered
      snapshot, the clock-advance path is real; if not, take the fallback
      (single-node graph, `timeout_override_s=12` — never 10 or below,
      plan.md trap 7). Delete the probe before committing; the commit message
      states which path was taken and why (spec US1-S1).

### Implementation for User Story 1

- [ ] T005 [US1] Restructure both tests on the path T004 proved, keeping every
      existing assertion byte-identical: the dead-agent test keeps TIMEOUT
      termination, `last_snapshot == SNAPSHOT`, `"run_gates"` in us1's
      sequence, us1 `MERGED`, and the history assertion that the scheduled
      `heartbeat_timeout` equals the derived bound with derived-half strictly
      above the 5s floor (spec US1-S1, FR-001); the snapshot test keeps the
      same set with the snapshot arriving via `last_heartbeat_details`
      (spec US1-S2, FR-002, FR-003 — plan.md trap 2: the timeout fires at the
      server, never as a scripted raise). Fix the stale comment at the
      `heartbeat_then_block` block while editing it (plan.md trap 3). Leave
      the derivation-shape test at `test_heartbeat_timeout_is_derived_from_attempt_timeout_and_floored`
      untouched.

### Bite-checks and evidence for User Story 1 (must fail under mutation)

- [ ] T006 [US1] Prove both tests still bite, one mutation at a time, neither
      ever committed: (a) change `_agent_heartbeat_timeout` to return a fixed
      `timedelta(seconds=5)` and observe the restructured dead-agent test FAIL
      on its history assertion, then revert (spec US1-S3); (b) change
      `_attempt_timeout` to record `None` instead of reading
      `last_heartbeat_details` and observe the restructured snapshot test FAIL
      on its `last_snapshot` assertion, then revert (spec US1-S4). Record both
      red runs in the commit message. A mutation that stays green means the
      restructuring lost the test's subject — go back to T005.
- [ ] T007 [US1] Re-run T003's exact invocation plus the whole file
      (`tests/test_interpreter.py`) with `--durations=10` in the clean env:
      both tests at 15s or less (target ≤3s), no other test in the file at
      15s or more — the wait must be gone, not moved (spec US1-S1, US1-S2).
      Confirm `git diff` touches only `tests/` (FR-004). Record before/after
      figures in the commit message.

---

## Phase 3: User Story 2 — The dependency sweep's minute is measured, then removed (Priority: P2)

**Goal**: the SC-002 sweep keeps all five epic shapes and both assertion loops
at seconds instead of 60.81s, with the minute's composition recorded as
measurement — because the received explanation is provably wrong for this test
(plan.md trap 4) and a fix aimed at the wrong mechanism ships the minute
intact.

**Independent Test**: the instrumented run attributes ≥90% of the test's wall
clock by epic and mechanism; the restructured run keeps every assertion and
lands far below baseline.

**Chains on US1 merged** (`depends_on_merged`): both stories edit
`tests/test_interpreter.py` — US1 the tests and the `ScriptedWorld` comment,
US2 the shared harness for instrumentation — and dispatched as siblings they
would meet in the merge queue.

### Baseline and diagnosis for User Story 2 (measure FIRST — the attribution is the deliverable)

- [ ] T008 [US2] Verify prerequisites (US1's restructuring is in this
      worktree's base; plan.md inventory claims hold), then record the sweep
      baseline FIRST:
      `env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID FACTORY_ROOT="$(mktemp -d)" uv run pytest tests/test_workgraph_sweep.py -k "no_epic_ever_dispatches" -q --durations=5`
      (clean env, plan.md trap 6). Expect ~60s (60.81s at refinement); record
      the exact figure (spec US2-S1, US2-S2).
- [ ] T009 [US2] Diagnose before restructuring (FR-005): wall-clock each of
      the five `_epics` labels around their `run_epic` calls; if one epic
      dominates, add a monotonic timestamp beside `ScriptedWorld`'s activity
      log in `tests/test_interpreter.py` and attribute within it. Run the
      single test with `-s` in the clean env. The attribution must account
      for ≥90% of measured wall clock, name epic(s) and mechanism(s), and go
      into both the commit message and a comment above the test. Check
      plan.md trap 4's leads in order, and where the measurement contradicts
      them, say so explicitly — the tree wins (spec US2-S1).

### Implementation for User Story 2

- [ ] T010 [US2] Remove what the measurement named, and nothing it did not:
      all five epic shapes, each epic's expected end-state map,
      `script.observed` non-empty per epic, both dependency-assertion loops,
      and the `overrun`/`unscripted` guards survive verbatim (spec US2-S2,
      FR-006). If lead 1 is confirmed, prefer asserting cancellation delivery
      over silently spinning `WAIT_TIMEOUT_S`; the worker throttle caps in
      `start_epic` are test-side levers (plan.md § US2). Then re-run T008's
      exact invocation: the restructured sweep at 15s or less (target ≤5s),
      the figure recorded beside T008's baseline in the commit message — this
      is US2-S2's `--durations` evidence, produced here rather than inferred
      from T012's suite-wide bound (spec US2-S2). If a wait proves
      irreducible without changing what the gate runs, STOP and park a
      question — never a marker, never a tier edit (FR-007, plan.md trap 5).

### Bite-check and evidence for User Story 2 (must fail under mutation)

- [ ] T011 [US2] Prove the sweep still bites: temporarily mutate
      `_edges_satisfied` so the pass-edge conjunct treats an unverified
      dependency as satisfied, observe the restructured sweep FAIL, revert;
      never committed, red run recorded in the commit message (spec US2-S3).
      A sweep that stays green under that mutation has gone vacuous — go back
      to T010.
- [ ] T012 [US2] Close the books (FR-008): run the full suite as
      `env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID FACTORY_ROOT="$(mktemp -d)" uv run pytest -q --durations=30`
      (clean env — scratch `FACTORY_ROOT`, no Telegram vars, `ergane-env.sh`
      never sourced; plan.md trap 6). Evidence to record in the commit
      message: none of this spec's three tests at 15s or more, no test in the
      suite at 15s or more, and the before/after wall-clock totals against
      the ~5m45s baseline and ~2m40s target (spec US2-S4, SC-001, SC-002).
- [ ] T013 [US2] Final sweep: confirm the combined diff of both stories
      touches only `tests/` (SC-004 — `factory/` clean, `factory.yaml`
      untouched, no dependency added). This spec changes no rule the factory
      previously held, so no `docs/decisions.md` entry is expected; claim one
      at landing ONLY if an operator-answered question from T010 authorized a
      change to what the gate runs, in which case the entry records that
      decision and its rationale as a numbered, immutable addition.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything: trap 4's premise (no
  `heartbeat_then_block` in the sweep) and trap 7's floor value are the two
  claims whose failure would reshape the stories.
- Phase 2 (US1) has no dependency and is the MVP: two-thirds of the measured
  181s, one file, one mechanism, and T004 fails fast if the primary mechanism
  is not real.
- Phase 3 (US2) chains on US1 **merged** — shared harness file, plain
  conflict avoidance — and closes with the suite-wide numbers because it is
  the story that lands last.

## Implementation Strategy

US1 alone is worth landing: it removes ~120s from every gate run on every
attempt and every recovery, and its restructuring is mechanical once T004
answers the one open question. US2 is deliberately measurement-first: its
minute has no verified explanation, and the diagnosis is as much the
deliverable as the speed — the attribution comment it leaves above the test
is what stops the next hand from guessing. Neither story changes what any
agent is asked to do, what the judge scores, what the gate runs, or a single
line under `factory/`.
