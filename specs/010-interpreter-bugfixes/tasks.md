# Tasks: Two silent losses in the interpreter

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Four things, because each one
      has already been wrong once: that the reap block at `:788-793` and the one
      in `_drain_in_flight` at `:1036-1041` are still byte-identical (if they
      have diverged, trap 1 changes shape); that `_UNREACHABLE` is still
      `{FAILED, KILLED}`; that the agent mint is still inside the `while True:`
      ladder rather than above it, because trap 4's whole instruction turns on
      that; and that the judge's `try`/`finally` at `:1767`/`:1775` is still
      intact, because it is the template US2 copies and this spec claims it is
      already correct.

---

## Phase 2: User Story 1 — A crashed node coroutine ends the node (Priority: P1) 🎯 MVP

**Goal**: an exception inside a node's coroutine ends that node `KILLED` with the
exception recorded, locks out its dependents, and leaves every other in-flight
node alone.

**Independent Test**: a three-node graph where `a` raises and `b` depends on `a`
ends with `a` KILLED carrying the exception text, `b` KILLED, and independent `c`
MERGED.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` green;
      `factory/workgraph/workflow.py` and `factory/workgraph/models.py` exist and
      plan.md's inventory claims hold — constitution II gate; STOP and report
      blocked if not satisfied.
- [ ] T003 [US1] Write the crash case FIRST: a node whose coroutine raises
      `RuntimeError` ends `KILLED`, and `NodeRecord.terminal_reason` carries the
      exception's text. This is the test the whole story exists for — must fail.
- [ ] T004 [P] [US1] Write the lock-out case FIRST: that crashed node's
      `depends_on` dependent ends `KILLED` rather than sitting `PENDING`. Assert
      on the dependent, not on `_lock_out_dependents` being called — the fix is
      that the crashed node lands in `_UNREACHABLE`, and asserting on the call
      would pass even if the state were still wrong — must fail.
- [ ] T005 [P] [US1] Write the containment case FIRST: a second, independent node
      in flight at the same moment completes normally. FR-005 is that one node's
      crash ends one node; a reaper that re-raised would take the epic and this
      is the test that catches it — must fail.
- [ ] T006 [US1] Write the **drain** case FIRST — trap 1, the site a partial fix
      forgets: the same crash, reaped by `_drain_in_flight` on the pause or kill
      path rather than by the main loop, produces the same `KILLED` state, the
      same `terminal_reason` and the same lock-out. Then assert the drain still
      skips a `WAITING_OPERATOR` node, because reaping it deadlocks the pause
      (008-US2) and this story must not regress it — must fail.
- [ ] T007 [P] [US1] Write the no-op case FIRST, the negative half: a node
      coroutine that returns normally is reaped exactly as it is today —
      `terminal_reason` stays `None`, its state is untouched by the reaper, and
      no extra activity is executed. This is the test that catches an
      implementation which marks every reaped node — must fail only if the
      implementation over-reaches, so say that in the test's docstring.

### Implementation for User Story 1

- [ ] T008 [US1] Add `terminal_reason: str | None = None` to `NodeRecord`
      (`factory/workgraph/models.py:231`) with the comment plan.md § US1 asks
      for — until T003 passes.
- [ ] T009 [US1] Extract the shared reap helper and point **both** `:788-793` and
      `:1036-1041` at it. `except Exception`, never `BaseException` — trap 3 —
      and carry that trap's reason into a comment above the handler. Set
      `record.state = NodeState.KILLED` **before** the existing
      `_lock_out_dependents` call, which is the ordering the whole fix turns on.
      Do not touch `_all_landings_terminal` — trap 2. Until T003–T007 pass.

---

## Phase 3: User Story 2 — Every minted key is torn down (Priority: P1)

**Goal**: the agent and recovery key mints are bracketed the way the judge's mint
already is, and teardown runs exactly once per lease on every path.

**Independent Test**: forcing a raise between each mint and its teardown leaves
`teardown_attempt` executed exactly once for that lease, with the exception
still propagating.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Write the **double-teardown** case FIRST, before the leak cases,
      because it is the one that costs money if wrong (trap 4): an ordinary happy
      path through each of the two sites executes `teardown_attempt` **exactly
      once** per lease. Today this passes; it is written first so that the moment
      T014 adds a `finally` on top of a surviving explicit call, this goes red
      instead of shipping a second ledger row per attempt. State that in the
      test's docstring — must fail only if the implementation over-reaches.
- [ ] T011 [P] [US2] Write the recovery-leak case FIRST — the failure the finding
      is named for: with `_verify` patched to raise, the recovery site at `:2263`
      still executes `teardown_attempt` once for its lease, and the exception
      still propagates unchanged — must fail.
- [ ] T012 [P] [US2] Write the agent-leak case FIRST: with `_attempt` patched to
      raise, the agent site at `:1184` still executes `teardown_attempt` once for
      its lease, and the exception still propagates unchanged — must fail.
- [ ] T013 [P] [US2] Write the judge-unchanged case FIRST: the already-correct
      bracket in `_score_diff` mints and tears down exactly as it does today.
      US2's fourth acceptance scenario is the boundary — this story does not
      refactor working code into a shared helper nobody asked for — must fail
      only if the implementation over-reaches.

### Implementation for User Story 2

- [ ] T014 [US2] Bracket the agent mint per trap 4: `try:` immediately after the
      mint at `:1184`, `finally:` closing that **iteration** of the `while True:`
      ladder at `:1153` — not the loop — and **delete** the three explicit
      `await self._teardown(...)` calls at `:1233`, `:1259` and `:1425` as you
      go. Until T010 and T012 pass.
- [ ] T015 [US2] Bracket the recovery mint the same way: `try:` after `:2263`,
      `finally:` around the body, and delete the explicit teardowns at `:2299`
      and `:2306`. Leave `_score_diff` alone. Until T010, T011 and T013 pass.
- [ ] T016 [US2] Final sweep + docs: `docs/decisions.md` gains a numbered entry
      claimed at landing — a node's coroutine failure is a node terminal rather
      than a silence, and every key mint is bracketed — and
      `docs/architecture.md`'s node-lifecycle section records the new terminal
      reason. State the boundary: this is the cheap correctness fix, and the
      structural one (a child workflow per node) remains
      `temporal/node-child-workflows`'s to make. Confirm no new dependency, no
      new activity, no new store.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything; T001's fourth check in
  particular, because if the judge's bracket has been removed since this plan was
  written, US2's template is gone and the spec's own claim is false.
- Phase 2 (US1) has no dependency and is the MVP: an epic stops being able to
  report success while holding a frozen node.
- Phase 3 (US2) chains on US1 **merged**. The two stories touch the same file,
  and this is the one case where the merge edge is plain conflict avoidance
  rather than a semantic gate — US2 rewrites control flow inside `_run_node`
  while US1 rewrites the loop that calls it. Dispatched as siblings they would
  meet in the merge queue, and one of them would lose a two-hour attempt to a
  rebase.

## Implementation Strategy

US1 alone is worth landing: it converts the worst failure mode either finding
describes — an epic that reports itself complete while a node is frozen and its
dependents were never dispatched — into an ordinary node death that the existing
lock-out already handles correctly.

US2 is smaller than it reads. It is two `try`/`finally` brackets copied from a
site three hundred lines away that already has them, and five line deletions. The
risk in it is entirely in the deletions, which is why T010 is written first.

Neither story changes what any agent is asked to do, what the judge scores, or
what the merge queue writes.
