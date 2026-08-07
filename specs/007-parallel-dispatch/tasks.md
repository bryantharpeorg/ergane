# Tasks: Parallel Node Dispatch

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must fail**
before its implementation task runs.

Tasks marked `[P]` touch disjoint files within their story. Tasks without it are
sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm 003 and 006-US1 have both landed. 003 supplies the landing
      path US3 tests against; 006-US1 supplies the heartbeat change without which fan-out
      multiplies workflow history by the number of concurrent attempts — at the pre-006
      rate of ~1,320 events/hour/attempt, three concurrent nodes produce ~4,000/hour
      against Temporal's 10,240 warning and 51,200 hard limit, making history the binding
      constraint on epic width. 006's us3/us4 are explicitly NOT required (decided
      2026-08-07) and may land before or after this epic. This is a sequencing
      requirement, not a preference.

---

## Phase 2: User Story 1 — Independent nodes run at the same time (Priority: P1) 🎯 MVP

**Goal**: the scheduler dispatches every ready node concurrently up to
`max_concurrent_nodes`, without weakening the dependency guarantee or replay safety.

**Independent Test**: a graph of N independent nodes with the cap at N has all N in
flight at once, and the epic's elapsed time tracks its slowest node rather than the sum.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` is green,
      `factory/workgraph/workflow.py` exists, and the landing phase from 003 and the
      heartbeat change from 006 are both present — constitution I gate; STOP and report
      blocked if not satisfied.
- [ ] T003 [P] [US1] Write `tests/test_epic_cli.py` cases FIRST: `factory-epic start`
      accepts the cap, rejects `0`, negatives and non-integers with a usage error rather
      than coercing them, and defaults to `1` when the flag is absent — must fail.
- [ ] T004 [US1] Write `tests/test_interpreter.py` concurrency cases FIRST under time
      skipping with scripted fakes: with a cap of N and N independent ready nodes, all N
      are in flight simultaneously; a slot is refilled the moment any node reaches a
      terminal state; the epic's simulated elapsed time tracks the slowest node, not the
      sum (SC-001) — must fail.
- [ ] T005 [US1] Write the **cap-of-1 equivalence** case FIRST: with the cap at 1, dispatch
      order and observable state are identical to today's sequential loop (SC-002). This is
      the test that makes fan-out opt-in rather than a behaviour change, and it must be
      written before the loop is touched so it captures today's behaviour honestly — must fail.
- [ ] T006 [US1] Write the **dependency-guarantee** case FIRST (FR-003/SC-003): across
      several scripted completion interleavings, zero nodes are dispatched with an unmet
      dependency — including the case where a node's dependency fails while other nodes are
      mid-ladder. Interleavings are produced by scripting fake completion order, never by
      real timing, which would be flaky and would prove nothing about replay — must fail.
- [ ] T007 [US1] Write the **replay** case FIRST (FR-004/SC-005): a simulated worker
      restart with several nodes in flight re-derives the epic and dispatches nothing
      twice — must fail.

### Implementation for User Story 1

- [ ] T008 [US1] Add `EpicInput.max_concurrent_nodes` (default 1) in
      `factory/workgraph/models.py`, validated in the workflow as well as the CLI —
      `EpicInput` can be constructed without the CLI, so CLI-only validation is not validation.
- [ ] T009 [US1] Add the CLI flag and its validation in `factory/workgraph/cli.py` until
      T003 passes.
- [ ] T010 [US1] Widen the scheduler in `factory/workgraph/workflow.py` until T004–T007
      pass: a whole-ready-set accessor alongside `_next_ready`; start `_run_node` tasks
      while a slot is free; `wait_condition` on a task finishing or a kill/pause arriving;
      release the slot and apply lock-out on completion. **Recompute the ready set against
      current state every time a slot frees — never cache it across a completion**, which
      is how a node whose dependency just failed slips through. Use only
      `asyncio.create_task` / `workflow.wait_condition` / `asyncio.wait`; `as_completed`,
      wall-clock reads, `random` and thread pools break replay and must not appear.

---

## Phase 3: User Story 2 — A node's verdict does not depend on its neighbours (Priority: P2)

**Goal**: concurrency changes how fast the epic runs, never what it concludes.

**Independent Test**: a node's gates pass alone and still pass alongside `cap - 1` busy
neighbours.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T011 [P] [US2] Write `tests/test_gates.py` cases FIRST: a gate whose wall-clock
      duration would exceed its bound only because of concurrent load still returns its
      true verdict; a gate that genuinely hangs is still detected and failed once its bound
      elapses — the protection reduces contention sensitivity, it does not remove timeouts;
      whether a gate ran contended is recorded on its result and is readable afterwards
      (FR-005 acceptance 3) — must fail.

### Implementation for User Story 2

- [ ] T012 [US2] Add the contention marker to the gate result in
      `factory/verify/models.py`.
- [ ] T013 [US2] Implement load-independent gate execution in `factory/verify/gates.py`
      until T011 passes. plan.md § US2 sets out two mechanisms and **prefers bounding gate
      concurrency below node concurrency** — nodes fan out, gates queue — because it makes
      the property true rather than approximately true while leaving the agent phase, where
      the wall-clock actually goes, fully parallel. If the implementing node chooses the
      other mechanism, it must record why in the task's commit message.

---

## Phase 4: User Story 3 — Concurrent landings settle (Priority: P2)

**Goal**: several verified nodes land at once without deadlock.

**Independent Test**: several nodes reach PASS together against a scripted queue that
merges some and rejects others; every landing reaches a terminal state and the epic
completes.

### Tests for User Story 3 (write FIRST, must fail)

- [x] T014 [US3] Write `tests/test_interpreter.py` landing-concurrency cases FIRST: N
      nodes reaching PASS together each open exactly one PR and enqueue; the epic completes
      only when every landing is terminal; a rejected landing recovers without stalling the
      others; a `depends_on_merged` dependent does not dispatch while its dependency is
      merely enqueued, regardless of how many other landings are open — must fail.

### Implementation for User Story 3

- [ ] T015 [US3] Make the landing phase concurrency-safe in
      `factory/workgraph/workflow.py` until T014 passes. **Any wait condition added here
      must have its test fixtures updated in the same task.** 003's T020 added an unbounded
      `wait_condition` on "all landings terminal" and left the pre-landing `ScriptedEpic`
      fixtures unmigrated, which hung four CLI tests for 81s each and cost an attempt — the
      failure presented as `tcp connect error`, pointing away from its own cause.

---

## Phase 5: User Story 4 — Pause and kill still mean what they meant (Priority: P3)

**Goal**: the operator's emergency controls stay correct with N nodes in flight.

**Independent Test**: pause and kill an epic with several nodes in flight; in-flight nodes
finish (pause) or are all salvaged (kill).

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T016 [US4] Write `tests/test_interpreter.py` cases FIRST: `pause_epic` with N in
      flight starts nothing new and lets all N finish their ladders; `kill_epic` with N in
      flight cancels and **salvages every one** before the epic terminates, with all N
      branches reachable (SC-006) — a kill that salvages three of four is a lost-work bug;
      a node ending non-PASSED while others run locks out only its own dependents and
      leaves an unrelated in-flight node untouched (FR-009) — must fail.

### Implementation for User Story 4

- [ ] T017 [US4] Implement N-safe pause, kill and lock-out scoping in
      `factory/workgraph/workflow.py` until T016 passes. Lock-out scoping is the subtlest
      change in this epic: `_lock_out_dependents` runs today after *the* node, and must
      become a statement about the finishing node's dependents alone.

---

## Phase 6: User Story 5 — The operator can see the whole fleet (Priority: P3)

**Goal**: a wide epic is as legible as a narrow one.

**Independent Test**: query status with several nodes in flight; each appears with its own
state, attempt and spend.

### Tests for User Story 5 (write FIRST, must fail)

- [ ] T018 [P] [US5] Write `tests/test_epic_cli.py` cases FIRST: with N nodes in flight,
      status lists every one with its state and attempt in both human and `--json` output —
      the renderer must not assume a single running node; with concurrent attempts, each
      node's spend is attributed to it alone (FR-011, D-026's alias discipline under
      concurrency) — must fail.

### Implementation for User Story 5

- [ ] T019 [US5] Implement fleet rendering in `factory/workgraph/cli.py` until T018 passes.
- [ ] T020 [US5] Final sweep + docs: update `docs/architecture.md` §3 (the scheduler is no
      longer sequential; the cap and where it is supplied) and record a decision-log entry
      at the next free D-number covering the cap's naming and placement — `max_concurrent_nodes`
      rather than `max_workers` because "worker" already names the Temporal worker process,
      and on `EpicInput` rather than `factory.yaml` because host capacity is not a property
      of the target repo.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 is operator work and gates everything.
- Phase 2 (US1) has no dependency and is the MVP; everything else defends a property that
  only exists once it lands.
- Phases 3–6 (US2, US3, US4, US5) each depend on US1 and on nothing else.

### Within stories

Tests before implementation, always. T005 (cap-of-1 equivalence) must be written before
T010 touches the loop, so that it captures today's behaviour rather than tomorrow's.

### Parallel Opportunities

US2, US3, US4 and US5 form a four-wide ready set behind US1 — this epic is itself a
fan-out, and with the cap above 1 after US1 lands it becomes its own first beneficiary
and a live test of the feature.

## Implementation Strategy

US1 alone is worth landing: it is the feature, and the cap defaults to 1 so nothing
changes for anyone who does not ask. US2 is the one that must not be skipped — without
it fan-out makes the factory less trustworthy the faster it gets, which is a worse trade
than staying sequential. If the epic must be cut short, cut US5 first and US2 never.
