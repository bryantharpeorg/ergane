# Feature Specification: Parallel Node Dispatch

**Feature Branch**: `007-parallel-dispatch`

**Created**: 2026-08-06

**Status**: Drafted. This is the widening the interpreter was built to accept —
`workflow.py`'s main loop already says so: *"Sequential by design: one node at a time,
the first ready one in declaration order... Parallel execution is deferred, and this
loop is where it would widen — the ready set is already computed, only the picker is
narrow."* The ready set is computed correctly today and thrown away down to one entry.

**Input**: Dispatch every ready node concurrently up to an operator-set cap, without
weakening the dependency guarantee, the verdict's independence from load, or the
kill/pause semantics that a sequential loop made easy.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Independent nodes run at the same time (Priority: P1)

As the factory operator, I can have an epic work every node whose dependencies are
satisfied at once, up to a cap I set, so that a graph's wall-clock is bounded by its
critical path rather than by the sum of everything in it.

003's own graph is the motivating case: `us1 ← us2`, with `us3` independent. Today
`us3` waits behind `us1` and `us2` for no reason the graph expresses — the DAG says it
is free, and the scheduler serialises it anyway. On a three-node epic that is an hour
or two; on a wider graph it is the difference between a working day and a week.

The cap is **`max_concurrent_nodes`**, and it belongs to the epic's dispatch rather
than to the target repo. `factory.yaml` describes what "green" means for the repo being
built and travels with the clone; how many agents a machine can host is a fact about
the machine. The same epic against the same repo warrants a different cap on a laptop
and on the DGX, so the value is supplied at `factory-epic start`.

The name is deliberately not `max_workers`: "worker" already names the Temporal worker
process (`python -m factory.worker`), and a knob called `max_workers` that does not
change the number of workers would mislead every reader of this codebase exactly once.

**Why this priority**: It is the feature. Everything else here defends it.

**Independent Test**: Run a graph of N independent nodes with the cap at N under time
skipping; assert all N are in flight simultaneously and the epic's elapsed time tracks
the slowest node rather than the sum.

**Acceptance Scenarios**:

1. **Given** a graph with several ready nodes and a cap of N, **When** the scheduler
   runs, **Then** up to N nodes are in flight at once and a slot is refilled as soon as
   any node reaches a terminal state.
2. **Given** a cap of 1, **When** any epic runs, **Then** behaviour is identical to
   today's sequential loop in dispatch order and observable state.
3. **Given** any interleaving of node completions, **When** the scheduler dispatches,
   **Then** no node is ever dispatched with an unmet dependency (005 SC-002 holds
   unchanged).
4. **Given** a worker restart with several nodes in flight, **When** the workflow
   replays, **Then** nothing is dispatched twice (005 US1-S4, extended to fan-out).

---

### User Story 2 - A node's verdict does not depend on its neighbours (Priority: P2)

As the factory operator, I can trust that a node passed or failed on its own merits,
so that concurrency changes how fast the epic runs and never what it concludes.

This is the hazard fan-out introduces that sequential execution hid. Gates are
subprocesses bounded by wall-clock timeouts, and for this repo the gate is
`uv run pytest -q` over ~1,339 tests. Three of those on one host contend for CPU, so
the same suite takes longer purely because neighbours exist. A fixed wall-clock timeout
then converts host load into a FAIL — a verdict that is not a fact about the node's
code. 002's whole discipline is that a gate result is mechanical evidence; evidence
that moves with unrelated load is not evidence.

**Why this priority**: Without it, fan-out makes the factory *less* trustworthy as it
gets faster, which is the worst possible trade.

**Independent Test**: Run one node's gates alone and again alongside `cap - 1` busy
neighbours; assert identical verdicts.

**Acceptance Scenarios**:

1. **Given** a node whose gates pass when run alone, **When** the same node runs at
   full concurrency, **Then** the verdict is still PASS.
2. **Given** a gate that genuinely hangs, **When** its bound elapses, **Then** it is
   still detected and failed — the protection loosens contention sensitivity, it does
   not remove timeouts.
3. **Given** the chosen mechanism, **When** an operator reads the epic's evidence,
   **Then** it is visible whether a gate ran contended, so a slow verdict is auditable.

---

### User Story 3 - Concurrent landings settle (Priority: P2)

As the factory operator, I can have several verified nodes land at once without the
epic deadlocking or corrupting the target's history, so that fan-out reaches the merge
queue rather than stopping just short of it.

003 gives every node its own branch, PR and queue entry, and GitHub serialises the
queue. Fan-out therefore produces exactly the condition 003 US2 was written for —
several PRs racing one queue, some rejected as CONFLICT and routed to recovery — but at
a rate sequential execution never generated. `depends_on_merged` must still hold when
its dependency is one of several landings in flight.

**Why this priority**: Landing is where concurrency turns from a scheduling question
into a correctness one against a repo we do not control.

**Independent Test**: Drive several nodes to PASS simultaneously against a scripted
queue that merges some and rejects others; assert every landing reaches a terminal
state and the epic completes.

**Acceptance Scenarios**:

1. **Given** several nodes reaching PASS together, **When** they land, **Then** each
   opens exactly one PR and enqueues, and the epic completes only when every landing is
   terminal.
2. **Given** a node declaring `depends_on_merged`, **When** its dependency is enqueued
   but not yet merged, **Then** it does not dispatch — regardless of how many other
   landings are in flight.
3. **Given** concurrent landings where one is rejected, **When** recovery runs, **Then**
   the rejected node recovers without stalling the others.

---

### User Story 4 - Pause and kill still mean what they meant (Priority: P3)

As the factory operator, `pause_epic` and `kill_epic` behave predictably when several
nodes are in flight, so that the controls I have do not degrade as the epic widens.

Today's semantics lean on there being exactly one node running: pause "stops dispatch
and nothing else: the node already in flight keeps its whole ladder." With N in flight
that sentence has to become N-safe rather than be quietly reinterpreted. Likewise
`_lock_out_dependents`, which runs after a node ends non-PASSED, must lock out that
node's dependents without disturbing unrelated nodes mid-ladder.

**Why this priority**: Correctness of the operator's emergency controls; it matters at
the moment something has already gone wrong.

**Independent Test**: Pause and kill an epic with several nodes in flight; assert
in-flight nodes finish (pause) or are all salvaged (kill).

**Acceptance Scenarios**:

1. **Given** several nodes in flight, **When** `pause_epic` is signalled, **Then** no
   new node dispatches and every in-flight node completes its ladder.
2. **Given** several nodes in flight, **When** `kill_epic` is signalled, **Then** every
   one is cancelled and salvaged, and each branch remains reachable.
3. **Given** a node ending non-PASSED while others run, **When** lock-out applies,
   **Then** only its dependents are locked out and unrelated in-flight nodes are untouched.

---

### User Story 5 - The operator can see the whole fleet (Priority: P3)

As the factory operator, `factory-epic status` shows me every node currently running
and what each is costing, so that a wide epic is as legible as a narrow one.

**Why this priority**: Small, but a fan-out epic whose status shows one node is worse
than no status at all.

**Independent Test**: Query status with several nodes in flight; assert each appears
with its own state, attempt and spend.

**Acceptance Scenarios**:

1. **Given** several nodes in flight, **When** status runs, **Then** every one is
   listed with its state and attempt, in both human and `--json` output.
2. **Given** concurrent attempts, **When** the ledger is read, **Then** each node's
   spend is attributed to it alone (D-026's alias discipline holds under concurrency).

---

### Edge Cases

- A cap larger than the graph's widest ready set: the cap is a ceiling, never a target,
  and must not cause spurious waiting.
- A cap of 0 or negative: rejected at `start`, not silently coerced.
- Every ready node failing at once: lock-out must converge, and "ran out of ready nodes"
  must stay distinguishable from "finished" (the loop's existing distinction).
- Host exhaustion below the cap — N agent processes, N worktrees, N pytest runs. The cap
  is the operator's instrument; the system must not deadlock if it is set too high, and
  the failure must be legible rather than a hang.
- A recovery attempt and a fresh node both ready with one slot free: 003 establishes
  that pending recovery outranks pending fresh work; fan-out must not lose that ordering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The scheduler MUST dispatch every ready node concurrently, up to
  `max_concurrent_nodes`, refilling a slot as soon as any node reaches a terminal state.
- **FR-002**: `max_concurrent_nodes` MUST be supplied per epic at `factory-epic start`,
  MUST be rejected if not a positive integer, and a value of 1 MUST reproduce today's
  sequential behaviour exactly.
- **FR-003**: The scheduler MUST NOT dispatch a node with an unmet dependency, under any
  interleaving of concurrent completions (005 SC-002 preserved).
- **FR-004**: A worker restart with any number of nodes in flight MUST re-derive the
  epic without dispatching any node twice.
- **FR-005**: A node's gate verdict MUST NOT depend on how many other nodes are
  executing concurrently, and whether a gate ran contended MUST be visible in its evidence.
- **FR-006**: Concurrent landings MUST each reach a terminal state without deadlock, and
  `depends_on_merged` MUST continue to gate dispatch on its dependency's merge.
- **FR-007**: `pause_epic` MUST stop new dispatch while every in-flight node completes
  its ladder.
- **FR-008**: `kill_epic` MUST cancel every in-flight node and salvage each before the
  epic terminates.
- **FR-009**: A node reaching a non-PASSED terminal state MUST lock out its own
  dependents without disturbing unrelated in-flight nodes.
- **FR-010**: `factory-epic status` MUST report every concurrently running node with its
  state and attempt, in human and `--json` output.
- **FR-011**: Per-node usage attribution MUST be unaffected by concurrency; no
  concurrent attempt may be charged to another node (D-026 alias discipline).

### Key Entities

- **Ready set** — the nodes whose dependencies are all satisfied; already computed
  today, currently truncated to its first element.
- **Dispatch slot** — one unit of the concurrency budget, held for a node's whole ladder
  and released on its terminal state.
- **Contention record** — whatever makes FR-005 auditable: evidence that a gate ran
  alongside others, so a slow verdict can be read honestly after the fact.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A graph of N independent nodes with the cap at N completes in wall-clock
  close to its slowest node, not the sum of all N.
- **SC-002**: With the cap at 1, the existing suite is green and dispatch order is
  unchanged — fan-out is opt-in, not a behaviour change.
- **SC-003**: Across randomized completion interleavings under time skipping, zero
  dispatches occur with unmet dependencies.
- **SC-004**: A node's gate verdict is identical run alone and run at full concurrency.
- **SC-005**: A simulated worker restart mid-fan-out double-dispatches nothing.
- **SC-006**: A kill with N nodes in flight leaves all N salvaged with reachable branches.

## Work Graph

One node per story. US1 builds the widened scheduler; everything else defends a property
that only exists once it does, so all four wait on it and nothing waits on each other.
The graph is therefore itself a fan-out — a four-wide ready set behind a single root,
which makes this epic its own first beneficiary if it is run with a cap above 1 after
US1 lands.

Every functional requirement is claimed by exactly one node. Attempt timeouts resolve
from the persona registry; no story here argues for an override.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: [US1]
  implements: [FR-005]
US3:
  depends_on: [US1]
  implements: [FR-006]
US4:
  depends_on: [US1]
  implements: [FR-007, FR-008, FR-009]
US5:
  depends_on: [US1]
  implements: [FR-010, FR-011]
```

## Assumptions

- **003 has landed.** US3 is meaningless without the landing path, and the epic assumes
  the merge queue exists rather than the D-024 interim manual dance.
- **006 has landed, and this matters more than it looks.** Fan-out multiplies whatever
  an attempt costs in workflow history by the number of concurrent attempts. At today's
  polling rate — 11 history events per 30 seconds per attempt, ~1,320/hour — three
  concurrent nodes would produce ~4,000 events/hour against Temporal's 10,240-event
  warning and 51,200 hard limit. Running this before 006's heartbeat change would make
  the history ceiling the binding constraint on how wide an epic can go. 006 first is a
  sequencing requirement, not a preference.
- 006 and 007 both modify `factory/workgraph/workflow.py` — 006 the attempt's inner
  loop, 007 the scheduler around it. They are run sequentially for that reason; running
  them concurrently would manufacture exactly the CONFLICT recovery 003 US2 handles, for
  no benefit.
- The host can genuinely support the caps an operator will set. Nothing here sizes the
  cap automatically; that is deliberate, and a cap set beyond the host's capacity is an
  operator error the system must fail legibly on rather than absorb.
