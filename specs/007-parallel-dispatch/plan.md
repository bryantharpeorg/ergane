# Implementation Plan: Parallel Node Dispatch

**Branch**: `007-parallel-dispatch` | **Date**: 2026-08-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-parallel-dispatch/spec.md`

## Summary

The widening the interpreter was built to accept. `workflow.py`'s main loop already
computes the whole ready set and then throws it away down to one entry — its own
docstring says *"Parallel execution is deferred, and this loop is where it would widen —
the ready set is already computed, only the picker is narrow."* US1 widens the picker
behind an operator-set cap, `max_concurrent_nodes`, supplied per epic at
`factory-epic start` because how many agents a host can carry is a fact about the host,
not about the target repo.

The other four stories exist because concurrency breaks assumptions a sequential loop
made free. The important one is **US2**: gates are wall-clock-bounded subprocesses
(`uv run pytest -q` over ~1,339 tests for this repo), so N of them on one host contend
for CPU and a fixed timeout converts neighbour load into a FAIL. That is a verdict which
is not a fact about the node's code, and 002's whole premise is that a gate result is
mechanical evidence. Without US2, fan-out makes the factory less trustworthy the faster
it gets. US3 carries landings into the merge queue concurrently — which is precisely the
condition 003 US2's rejection recovery was written for, at a rate sequential execution
never produced. US4 keeps `pause_epic`/`kill_epic` meaning what they meant when exactly
one node was in flight. US5 keeps the operator able to see a wide epic.

This plan is deliberately self-contained: the prompt assembler ships spec/plan/tasks
only, so every contract an implementer node needs is inlined below.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio` only. **No dependency is added.**

**Storage**: No new store. The dispatch slot is workflow state; the contention record
rides the existing verification evidence.

**Determinism — the constraint that shapes US1.** Temporal replays workflow code, so
concurrency must be expressed in the SDK's deterministic event loop, never in wall-clock
or OS threads:

- `asyncio.create_task` / `workflow.wait_condition` are safe and are the intended tools.
- `asyncio.wait(..., return_when=FIRST_COMPLETED)` is safe; *acting on which one finished
  first* is only safe because the SDK replays completion order from history.
- `asyncio.as_completed`, `time.monotonic`, `random`, and thread pools are **not** safe
  here and must not appear in the scheduler.
- The existing per-node work already lives in `_run_node`; making N of those concurrent
  tasks is the whole of the mechanism. Nothing about a single node's ladder changes.

**Testing**: `WorkflowEnvironment.start_time_skipping()` with scripted activity fakes.
Randomised completion interleavings (SC-003) are driven by scripting the fakes to
complete in different orders — not by real timing, which would make the suite flaky and
prove nothing about replay.

**Project Type**: single Python package (`factory/`).

**Constraints**: SC-002 — with the cap at 1, behaviour is identical to today and the
existing suite is green. Fan-out is opt-in.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with its implementation.
- **III (no unapproved dependencies)**: none added.
- **V (credentials)**: unchanged; each concurrent attempt still gets its own scoped key,
  and D-026's alias already carries `epic:node:attempt:persona`, so N concurrent keys
  cannot collide by construction. FR-011 asserts it rather than assuming it.
- **VI (salvage)**: FR-008 extends salvage-always to N in-flight nodes.
- **VII (persona routing)**: untouched.

## Project Structure

### Documentation (this feature)

```
specs/007-parallel-dispatch/
├── spec.md
├── plan.md      # this file
└── tasks.md
```

### Source Code (repository root)

```
factory/
├── workgraph/
│   ├── workflow.py   # US1 scheduler; US3 landing concurrency; US4 pause/kill/lock-out
│   ├── models.py     # US1 EpicInput.max_concurrent_nodes
│   └── cli.py        # US1 flag + validation; US5 fleet rendering
├── verify/
│   ├── gates.py      # US2 bounded gate concurrency + contention record
│   └── models.py     # US2 contention field on the gate result
tests/
├── test_interpreter.py   # US1, US3, US4
├── test_gates.py         # US2
└── test_epic_cli.py      # US1 flag validation, US5
```

## Data Model (inline)

**`EpicInput.max_concurrent_nodes: int = 1`** — defaulting to 1 is what makes SC-002 true
by construction: an epic that does not ask for fan-out gets today's behaviour exactly.
Validated at the CLI (positive integer; 0 and negatives rejected, never coerced) and
again in the workflow, because `EpicInput` can be constructed without the CLI.

**Dispatch slot** — not a type; the count of in-flight `_run_node` tasks. Held for a
node's whole ladder and released on its terminal state.

**`GateResult`** gains a contention marker — enough to answer "did this gate run alongside
others?" after the fact (FR-005). A boolean is sufficient; a count is better if it costs
nothing. This is what makes a slow verdict auditable rather than mysterious.

**`EpicStatus`** — unchanged shape. It is already a per-node document, so N running nodes
render without a schema change; US5 is about the *renderer* not collapsing them, plus
tests that would have caught a renderer assuming one.

## Approach by story

### US1 — the widened scheduler (FR-001, 002, 003, 004)

`_next_ready` gains a sibling returning the **whole** ready set rather than its first
element; `_next_ready` itself may then be expressed in terms of it or retired.

The main loop becomes: while any node is non-terminal or any task is in flight, start
tasks for ready nodes while a slot is free, then `wait_condition` on "a task finished or
a kill/pause arrived". A finished task releases its slot, applies its lock-out, and the
loop re-evaluates the ready set.

**The dependency guarantee is the thing most easily lost here.** Today "no dispatch with
an unmet dependency" is nearly free because only one node runs. With N in flight, the
ready set must be recomputed against *current* state every time a slot frees — never
cached across a completion — or a node whose dependency just failed can slip through the
gap. FR-003 and SC-003 exist for exactly this, and the randomised-interleaving test is
the one that would catch it.

**Replay**: nothing is stored outside workflow state, so FR-004 follows from using the
SDK's event loop rather than from any bookkeeping. The test must still exist — a
regression here would be silent and expensive.

### US2 — verdicts independent of load (FR-005)

Two mechanisms, and the plan deliberately does not pick between them; the implementing
node must choose from evidence and record why:

1. **Bound gate concurrency below node concurrency.** Nodes fan out, gates queue. A
   process-level bound in `factory/verify/gates.py` — gates already run through the
   worker's thread path — so a node's *agent* runs in parallel while its *gates* take a
   turn. Simple, and it makes the verdict genuinely load-independent rather than
   load-tolerant.
2. **Make the bound tolerant instead**, deriving the gate's wall-clock allowance from
   observed contention.

Option 1 is preferred: it makes the property true rather than approximately true, and the
agent phase — which is where the wall-clock actually goes — stays fully parallel. Option 2
trades a real guarantee for throughput the epic mostly does not need.

Either way the contention marker is recorded (FR-005 acceptance 3): a verdict an operator
cannot audit is the failure mode this story is about.

### US3 — concurrent landings (FR-006)

003 gives each node its own branch, PR and queue entry, and GitHub serialises the queue,
so the factory's job is not to serialise but to **not deadlock while several landings are
open**. Concretely: the landing poll loops are already per-node background work; N of them
must not starve each other, and the epic's completion condition — every node terminal AND
every landing terminal — must hold with N landings rather than one.

`depends_on_merged` must keep gating while its dependency is merely enqueued (acceptance
2), which is the case fan-out makes easy to get wrong: a dependent becomes *ready* the
moment its dependency is verified, and only the merge-gate stops it.

**Note for the implementer**: 003's own landing phase was where an unbounded
`wait_condition` on "all landings terminal" hung every CLI test whose fixtures did not
script merge activities. That is a live lesson from this codebase — any wait added here
must be paired with fixtures updated in the same task, not left for a later one.

### US4 — pause, kill, lock-out under fan-out (FR-007, 008, 009)

- **Pause** — stop starting tasks; let in-flight tasks finish. The existing docstring
  ("stops dispatch and nothing else: the node already in flight keeps its whole ladder")
  becomes true of N nodes rather than one, which is a widening of its meaning, not a change.
- **Kill** — cancel every in-flight task and salvage each. Salvage-always (constitution VI)
  is per node, so N kills must all complete before the epic terminates; a kill that
  salvages three of four nodes is a lost-work bug.
- **Lock-out** — `_lock_out_dependents` currently runs after *the* node. It must be scoped
  to the finishing node's dependents and must not touch unrelated in-flight nodes
  (FR-009). This is the subtlest change in the epic and deserves a test naming an
  unrelated in-flight node explicitly.

### US5 — fleet visibility (FR-010, 011)

`epic_status` already answers per node, so this is renderer work plus the tests that
would have caught a renderer assuming a single running node. FR-011 is an assertion, not
a change: D-026's alias already carries node and attempt, so concurrent attempts cannot
be charged to each other — prove it with concurrent attempts in the ledger.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| Node dispatched with an unmet dependency | Ready set cached across a completion | Recompute every time a slot frees; randomised-interleaving test (SC-003) |
| Non-determinism in the scheduler | `as_completed`, wall-clock, threads all break replay | Named as forbidden in Technical Context; replay test (SC-005) |
| Kill salvages some nodes but not all | Salvage is per node; N cancellations | Kill test asserting all N branches reachable (SC-006) |
| Lock-out disturbs unrelated in-flight nodes | Currently scoped to "the" node | Explicit test naming an unrelated running node |
| Gate contention silently changes verdicts | Verdict looks normal; only timing differs | Bound gate concurrency (preferred) + contention record |
| A wait added for landings hangs the suite | Exactly what happened in 003's T020 | Fixtures updated in the same task as any new wait |
