---
state: landed
# Landed 2026-08-10 10:33 PM CT. Two stories, PRs #35 and #36, 4h46m end to end.
# Neither story passed on its first attempt and both passed on their second, so
# the honest headline is 0-for-2 — the worst first-attempt rate of any epic so
# far. Both first attempts died at the `test` gate before reaching the judge;
# both second attempts were judged PASS on the judge's first try, all nine
# scenarios. No escalation, no question, no queue ejection.
#
# The verified fixes: `_reap_finished` retrieves `task.result()` at both reap
# sites, so a node coroutine that raises ends KILLED with its exception in
# `terminal_reason` instead of vanishing while the epic reads it as owing
# nothing. Both key mints — the agent ladder and `_recovery_attempt` — are
# bracketed `try/finally`.
#
# us2's implementer beat the plan on trap 4. The plan asked it to remove the
# five hand-written teardowns so a `finally` could not double-fire; it removed
# them AND added a `teardown_done` flag, so the bracket is idempotent even if a
# future edit reintroduces one. That is the stronger answer and it should be the
# precedent.
#
# THE FINDING THIS EPIC EXISTS TO RECORD, and it is not in the diff: us2's first
# attempt edited the operator's checkout instead of its own worktree. Census
# from its transcript — 58 Read and 4 Edit against /home/admin/code/ergane, 2
# Read against .factory/worktrees/010-interpreter-bugfixes/us2, 0 Edit there. It
# left `factory/workgraph/workflow.py` and `tests/test_interpreter.py` modified
# in the operator's tree. That is the sufficient explanation for the attempt's
# failure: the implementation landed in the wrong repository, so the worktree
# the gate ran against held the tests and none of the code, and it failed on its
# own two fail-first tests. The adapter sets cwd correctly; nothing makes an
# agent stay there. Filed as
# hardening/agent-edits-the-operator-checkout-not-its-worktree (critical). 018
# would not have prevented a single one of those writes — this is agent-sandbox.
#
# A 166k auto-compact also fired inside that attempt, against the 200k window
# Claude Code assumes because it does not recognise `ollama-cloud/kimi-k2.7-code`.
# Real, and evidence for 018/US4, but not the cause of the failure. Recorded
# because the first diagnosis blamed it and was wrong.
#
# us1's first attempt spent its budget on a genuinely hard harness — making
# `EpicWorkflow._run_node` raise inside Temporal's sandbox — and left 41 scratch
# files it later cleaned up. It also introduced a contract break, passing
# `drainable` where `_drain_in_flight` needed `in_flight` deleted, which no test
# covered and the judge never saw. Its second attempt found and fixed that
# unprompted.
#
# Cost: $111.82 across four attempts (us1 $43.03 + $8.63, us2 $21.31 + $38.85).
# No token counts are quoted and none can be: every ledger row for this epic
# carries `prompt_tokens = 0` and `request_count = 0` beside real spend, which
# is `interpreter/ledger-records-dollars-without-tokens`, now promoted to spec
# 024. The dollars are also the wrong signal — the models run on a flat-rate
# subscription — so this epic's effort is, for now, unmeasured.
# specs_root: specs
# target_repo: /home/admin/code/ergane-010-target
---

# Feature Specification: Two silent losses in the interpreter

Scaffolded by `factory-doctor promote` from two critical findings, then refined
against the tree at `6d08b3b` on 2026-08-09. Both findings are about the same
thing said two ways: the interpreter opens something — a task, a key — and has no
construct that guarantees it is closed when the code between raises. Neither is a
new capability. Both are brackets the code forgot to close.

## Why these two, together

They share one file (`factory/workgraph/workflow.py`) and one shape (a resource
opened on the happy path and released only on the paths the author enumerated).
Splitting them across epics would put two agents in the same 2,400-line module at
the same time for no benefit. Splitting them across *stories within* one epic,
with a merge edge, is what keeps the diffs readable and the conflicts impossible.

Neither is theoretical. B1's silent-success mode was reachable all day
2026-08-09; B2's leak is what makes a 24-hour virtual key outlive the attempt
that minted it, and it drops that attempt's row from the usage ledger — the
ledger is already known to be unreliable for tokens, and this is a second way it
under-reports.

## User Scenarios & Testing

### User Story 1 - A node whose coroutine raises ends the node, not the epic's honesty (Priority: P1)

Today the scheduler dispatches each node with `asyncio.create_task` and reaps
finished tasks by deleting them from `in_flight`. It never calls `task.result()`.
An exception raised inside `_run_node` or `_run_recovery` — anything the ladder
does not catch — is therefore discarded by the event loop, and the node's slot
frees exactly as if the node had finished normally.

The consequence is not a crash. It is worse: the crashed node's `state` is left
at whatever it was when the exception flew (`RUNNING`, `VERIFYING`), which is in
neither `_UNREACHABLE` nor the terminal set. Its dependents are not locked out,
because `_lock_out_dependents` only kills a `PENDING` node whose dependency is
`FAILED`/`KILLED`. And `_all_landings_terminal()` reads the crashed node as owing
nothing, because a node that never verified has `landing is None`. So the main
loop can break, `EpicState.COMPLETED` can be written, and the epic reports itself
finished with one node frozen mid-flight and its dependents never dispatched.

**Goal**: a node coroutine that raises ends that node terminally, with the
exception recorded, and its dependents locked out — while every other in-flight
node runs on.

**Independent Test**: a graph of three nodes where `a`'s coroutine raises and `b`
depends on `a`; the epic ends with `a` KILLED carrying the exception's text, `b`
KILLED by lock-out, and `c` (independent) MERGED.

**Acceptance Scenarios**:

1. **Given** a dispatched node whose coroutine raises `RuntimeError("boom")`,
   **When** the reaper picks it up, **Then** that node's state is `KILLED`, its
   record carries the exception's text, and the epic's outcome map shows it.
2. **Given** that same node with a `depends_on` dependent, **When** the reaper
   runs, **Then** the dependent is `KILLED` by lock-out rather than left
   `PENDING` — the crashed node is now in `_UNREACHABLE`, which is the whole
   mechanism by which lock-out reaches it.
3. **Given** a second, independent node in flight at the same time, **When** the
   first node's coroutine raises, **Then** the second node completes normally:
   one node's crash does not propagate out of the reaper.
4. **Given** a node whose coroutine raises **while the epic is paused or being
   killed** — so the drain, not the main loop, is the reaper — **Then** scenarios
   1 and 2 hold identically. There are two reap sites and they must not diverge.
5. **Given** a node coroutine that completes normally, **When** it is reaped,
   **Then** nothing about its handling changes: no new state, no new record
   field set, no extra activity call.

### User Story 2 - Every key that is minted is torn down, including when the code between raises (Priority: P1)

Three sites mint an attempt key. One of them — the judge's, in `_score_diff` —
brackets its mint with `try:` / `finally:` and tears the key down whatever
happens. The other two do not: they call `_teardown` once on each exit path the
author enumerated, which means any raise on a path the author did not enumerate
leaves the key alive for its full 24-hour TTL and skips the ledger row that
teardown is what writes.

The recovery site is the one the finding is named for. Between its mint and its
teardown it awaits `self._verify(...)` — the judge, the gates, the diff. A
`JudgeUnavailableError` or any gate-layer raise there leaks the key by
construction.

**Goal**: all three mints are bracketed the same way, and the shape is uniform
enough that a fourth mint added later is obviously wrong if it is not bracketed.

**Independent Test**: for each of the two unbracketed sites, force a raise
between mint and the code's own teardown call and assert `teardown_attempt` was
still executed exactly once with the right lease.

**Acceptance Scenarios**:

1. **Given** the agent-key site, **When** an exception is raised after the key is
   issued and before any existing `_teardown` call is reached, **Then**
   `teardown_attempt` runs exactly once for that lease and the exception still
   propagates unchanged.
2. **Given** the recovery site, **When** `_verify` raises, **Then**
   `teardown_attempt` runs exactly once for that lease and the exception still
   propagates unchanged.
3. **Given** either site on its ordinary happy path, **When** the attempt
   finishes, **Then** `teardown_attempt` runs **exactly once** — not twice. This
   is the scenario that fails if a `finally` is added on top of the existing
   explicit calls without removing them, and it is the one that costs money,
   because a double teardown is a second ledger row for one attempt.
4. **Given** the judge site, which is already correct, **When** the suite runs,
   **Then** its behaviour is unchanged: this story does not refactor working code
   into a shared helper it did not ask for.

## Functional Requirements

- **FR-001**: The reaper MUST retrieve each finished task's outcome rather than
  discarding it, at **both** reap sites — the main loop's and
  `_drain_in_flight`'s.
- **FR-002**: A node whose coroutine raises MUST end `KILLED`. `KILLED` and not
  `FAILED`: `FAILED` is documented as the park a `PAUSE_EPIC` resolution
  produces, and a crash is not an operator decision. `KILLED` is also the state
  that puts the node in `_UNREACHABLE`, which is what makes FR-003 work at all.
- **FR-003**: A crashed node's dependents MUST be locked out on the same pass, by
  the existing `_lock_out_dependents` — no second lock-out mechanism.
- **FR-004**: The exception MUST be recorded where an operator reading
  `factory-epic status` can see it, in a new `NodeRecord` field. Discarding the
  exception a second time — this time deliberately — would fix the state machine
  and keep the silence.
- **FR-005**: A crashed node MUST NOT propagate its exception out of the reaper.
  One node's crash ends one node.
- **FR-006**: Cancellation MUST remain distinguishable from failure. The kill
  path deliberately never cancels node tasks so that each closes its own
  bracket; the reaper's handler must not convert a cancellation into a recorded
  crash.
- **FR-007**: Every site that issues an attempt key MUST tear it down on every
  exit, raise included.
- **FR-008**: Teardown MUST run exactly once per lease. Adding a bracket around
  code that already calls teardown explicitly, without removing those calls, is
  a defect this spec names in advance.
- **FR-009**: The exception a bracketed site was carrying MUST still propagate
  after teardown. The bracket closes the key; it does not swallow the failure.

## Success Criteria

- **SC-001**: An epic containing a node whose coroutine raises never reports
  `COMPLETED` with that node in a non-terminal state.
- **SC-002**: For every mint site in `factory/workgraph/workflow.py`, a test
  exists that forces a raise between mint and teardown and asserts teardown ran.
- **SC-003**: Ordinary runs issue exactly as many `teardown_attempt` calls as
  before this spec: the fix is about the paths that were missing, not about
  adding calls to the paths that worked.
- **SC-004**: Both stories land as separate merges, US2 on top of US1.

## Edge Cases

- A node parked `WAITING_OPERATOR` is in flight but not done, and the drain
  deliberately skips it. That skip must survive: it is not a crash, and reaping
  it would deadlock the pause (008-US2).
- `asyncio.CancelledError` derives from `BaseException`, so a bare
  `except Exception` already lets it through. That is the correct behaviour and
  it should be stated in a comment rather than left as an accident of the
  hierarchy — a later hand widening it to `BaseException` would break FR-006
  silently.
- A raise inside `_teardown` itself is out of scope. The activity has its own
  retry policy, and a bracket cannot protect the thing it calls.

## Assumptions

- The two reap sites are the only two. A third added later inherits the defect;
  US1 answers this by giving both sites one shared helper rather than two edits.
- The judge's existing bracket is correct and is the template.
- No new dependency, no new activity, no new store.

## Out of Scope

- The structural fix for node dispatch — child workflows per node — which is
  `temporal/node-child-workflows`'s epic, not this one. This spec buys the cheap
  correctness now; it does not pre-empt that design.
- The ledger's token columns (`interpreter/ledger-records-dollars-without-tokens`).
  A leaked key drops a row entirely; that finding is about rows that exist and
  are wrong. Different defect, different spec.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009]
```
