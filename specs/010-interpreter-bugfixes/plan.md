# Plan: Two silent losses in the interpreter

All line references below were read against `factory/workgraph/workflow.py` at
commit `6d08b3b` on 2026-08-09. They are cited so you can find the code, not so
you can trust the numbers — see trap 5.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The main loop's reap block | `:788-793` | US1 |
| `_drain_in_flight`'s reap block | `:1036-1041` | US1 |
| Node dispatch | `:750` (recovery), `:754` (fresh) | US1, context |
| `_lock_out_dependents` | `:927` | US1 — reused as-is, not modified |
| `_UNREACHABLE = {FAILED, KILLED}` | `:262` | US1 — the reason FR-002 says KILLED |
| `NodeRecord` | `factory/workgraph/models.py:231` | US1 — one new field |
| The judge's key bracket (the template) | `:1749` mint, `try:` `:1767`, `finally:` `:1775`, teardown `:1779` | US2 — **read this before writing anything** |
| The agent key mint | `:1184`, inside the `while True:` ladder at `:1153` | US2 |
| Its three explicit teardowns | `:1233`, `:1259`, `:1425` | US2 — these are removed, not supplemented |
| The recovery key mint | `:2263` | US2 |
| Its two explicit teardowns | `:2299`, `:2306` | US2 — same |
| `_teardown` | `:1603` | US2 — called, never changed |

## Traps

### Trap 1 — there are **two** reap sites, and fixing one leaves the bug

`_drain_in_flight` (`:1036-1041`) contains a byte-for-byte copy of the main
loop's reap block (`:788-793`). It is the reaper for the pause and kill paths. A
fix applied only to the main loop leaves every paused and every killed epic with
the original defect, and the suite will not notice, because the tests that
exercise the drain are about pausing rather than about crashing.

Write **one** helper — `_reap_finished(node_id, task, resolved)` or whatever you
call it — and have both sites call it. The duplication is how this bug will come
back otherwise. Do not change what the drain skips: a `WAITING_OPERATOR` node is
in flight by design (008-US2) and reaping it deadlocks the pause.

### Trap 2 — the plausible wrong fix is to make `_all_landings_terminal` stricter

When you trace the silent-success mode you will find that
`_all_landings_terminal()` (`:980`) returns `True` for the crashed node, because
a node that never verified has `landing is None` and the predicate reads that as
"owes nothing". It is tempting to tighten that predicate so a non-terminal node
blocks the exit.

Do not. That predicate is about *landings*, and its `landing is None` clause is
load-bearing for every node that was killed or failed before it ever verified —
tightening it turns a correctly-ended epic into one that never exits. The crashed
node's problem is that its **state** is wrong, not that the predicate is wrong.
Set the state to `KILLED` and the existing machinery is already correct.

### Trap 3 — `except Exception`, never `except BaseException`

`asyncio.CancelledError` derives from `BaseException`, so a bare
`except Exception` lets cancellation through — which is exactly what FR-006
wants, because the kill path deliberately does **not** cancel node tasks (see the
comment at `:795-799`: cancelling would interrupt `_run_node` at whatever `await`
it was parked on and skip teardown, violating constitution VI). Widening the
handler to `BaseException` would convert a cancellation into a recorded crash and
quietly defeat that design.

Write the reason in a comment above the handler. The correctness here is an
accident of the exception hierarchy, and the next hand to touch it deserves to
know it is load-bearing.

### Trap 4 — US2's bracket goes around the **iteration**, and the old teardowns come out

The agent key is minted at `:1184`, **inside** the `while True:` ladder loop that
starts at `:1153`. One mint per iteration, one attempt per iteration. So the
`try:` opens immediately after the mint and the `finally:` closes at the end of
that iteration's body — not around the whole loop, which would mint N keys and
tear down one.

Then the part that costs money: the three existing `await self._teardown(...)`
calls at `:1233`, `:1259` and `:1425` must be **deleted** as you add the
`finally`. Left in place they run first, and the `finally` runs again — two
teardown activities for one lease, two ledger rows for one attempt, and an
attribution error in the opposite direction from the one this spec is fixing.
FR-008 and its scenario 3 exist for this exact edit.

A `break` or `return` inside a `try` runs the `finally` on its way out. That is
what makes this restructuring safe: you are not changing control flow, you are
moving the teardown from five hand-written call sites to two structural ones.

Same shape at the recovery site: mint `:2263`, teardowns `:2299` and `:2306`, and
the `await self._verify(...)` at `:2303` sitting between them with nothing
catching it — that await is literally the "verify raise" in the finding's key.

### Trap 5 — these line numbers rot faster than you think

The two findings this spec was promoted from carried refs from an audit run
roughly a day earlier. By 2026-08-09 **every one of them was wrong**: B1's were
stale by about 100 lines and pointed at `_onboard_target` and a blank line; B2's
were stale by about 700 and its written note had gone from stale to *inverted* —
it named the agent-key path as the good example when the agent-key path is the
gap and the judge path is the good example.

`006-interpreter-hardening` landing is what moved them. Something else may have
landed between this plan and your worktree. Grep for the construct, not the
number: `create_task`, `in_flight.items()`, `issue_attempt_key`, `_teardown(`.
If a citation here does not match what you find, the code wins and you say so in
your commit message.

### Trap 6 — you are editing the module that is running you

`factory/workgraph/workflow.py` is the interpreter dispatching your own attempt.
This is safe, and here is why, so you do not go looking for a problem: the
Temporal worker imports `factory/` from **its own checkout**, never from your
worktree. Your edits cannot affect the epic building you.

What follows from that is the constraint: **do not restart the worker, do not
touch the operator's checkout, and do not assume your change is live anywhere.**
It goes live when an operator restarts the worker after this lands. Your evidence
is the test suite and nothing else.

## Approach

### US1 — one reaper, and a node that ends when its coroutine ends

1. Add `terminal_reason: str | None = None` to `NodeRecord`
   (`factory/workgraph/models.py:231`), documented as "set only when a node ended
   for a reason the ladder did not produce" — today that means one thing, a
   crashed coroutine.
2. Extract the shared reap helper. Its body is the current five lines plus a
   `try: task.result() / except Exception as exc:` around the outcome retrieval.
   On exception: set `record.state = NodeState.KILLED`, set
   `record.terminal_reason` to the exception's text, and call
   `workflow.logger.exception(...)` so it reaches the Temporal history where an
   operator can actually find it.
3. Point both `:788-793` and `:1036-1041` at it.
4. The existing `if state != PASSED: _lock_out_dependents(resolved)` line stays
   exactly where it is and now does the right thing, because the crashed node is
   `KILLED` and therefore in `_UNREACHABLE`.

Note the ordering that makes this work: the state must be set to `KILLED`
**before** the lock-out call, not after. That is the whole fix in one sentence.

### US2 — three mints, one shape

Read `_score_diff` `:1749-1779` first and copy its shape. Bracket the agent mint
per trap 4, bracket the recovery mint the same way, delete the five explicit
teardown calls those brackets replace, and leave the judge site alone.

Testing this needs the raise to be forced from outside, since neither site raises
on its own: patch the activity the site awaits between mint and teardown so it
raises, then assert on the recorded `teardown_attempt` executions. `_verify` is
the natural seam for recovery; `_attempt` for the agent path.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A new `NodeRecord` field | The alternative is reusing `escalations: list[str]`, which is the escalation log; putting crash text there makes two unrelated things one list and the status renderer would have to guess. |
| A shared reap helper instead of two edits | Two edits is how the bug got two homes in the first place (trap 1). |
| Removing five teardown calls to add two | Not removing them is the double-teardown defect FR-008 names in advance (trap 4). |

## Verification

`uv run pytest -q` green. Beyond that, the two tests that did not exist before
are the point of the epic: a node whose coroutine raises, and a forced raise
between each mint and its teardown. If either passes before you write the
implementation, the test is wrong — read constitution II.
