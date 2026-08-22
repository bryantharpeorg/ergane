# US3 — the park, reproduced before the fix and after it

Committed evidence for SC-006 (T031) and SC-007 (T032). Every block below is
pasted tool output, not a description of one (constitution VIII).

Reproduction: `tests/test_answered_question_unparks_the_node.py`.
Command: `uv run pytest tests/test_answered_question_unparks_the_node.py -q -p no:randomly -rA`.

---

## What the reproduction found, and what it did not

The plan (trap 6) said the answered branch reads correctly and told this node not
to guess which line was wrong. It was right to: **the answered branch is
correct, and the reproduction proves it.**

The 008-US2 fixtures deliver the operator's reply from inside `send_question` —
so the child settles while the parent is still in the teardown that precedes its
`wait_condition`, and the parked wait is never actually waited on. That timing is
not an operator's. `test_an_answer_that_arrives_long_after_the_park_un_parks_the_node`
signals the `QuestionWorkflow` child only after the park is observable through
`epic_status` (node `WAITING_OPERATOR`, epic `PAUSED`, question shipped) — the
live shape — and **it passed against the unfixed tree**, together with US3-S1,
US3-S2 and US3-S3.

The wedge is the teardown *at* the park, and its cause is the ledger.

---

## The cause: `usage_records` has never had a migration

`'question'` entered the `termination` CHECK in 008 (`e652c1c`, 2026-08-07) and
`'auth_failure'` in 070 (`357d227`). Both arrived inside `_SCHEMA_DDL`, where
every statement is `CREATE TABLE IF NOT EXISTS` — a no-op on a table that already
exists — and `factory/usage/ledger.py` carried no `_migrate` at all. Every ledger
created before 2026-08-07 still refuses the one row a parked question owes:

```
$ git log --oneline -S"'question'" -- factory/usage/ledger.py
e652c1c 008-operator-channel/us1: US1 (#11)

$ git log --oneline -S"auth_failure" -- factory/usage/ledger.py
357d227 070-a-story-can-choose-who-builds-it/us3: US3 (#239)
```

Against a ledger written before 008, `teardown_attempt`'s upsert:

```
factory/usage/ledger.py:161: sqlite3.IntegrityError: CHECK constraint failed:
termination IN
                               ('completed', 'agent_error', 'timeout', 'killed')
```

Trap 7 predicted exactly this, including that the symptom would be identical to a
bug in the question branch. It is.

> **The operator's own check, which this node could not run.** The plan's
> independent verification asks for the *installed* store's `usage_records` DDL
> against the tree's. There is no installed ledger reachable from this worktree —
> `/home/admin/code/ergane/.ergane/ledger.db` exists and is 0 bytes, and a
> filesystem search for any `ledger.db` over 1 KiB returns nothing — so the
> comparison here is against the pre-008 DDL read out of git
> (`git show e915296:factory/usage/ledger.py`), which is what SQLite recorded in
> `sqlite_master` on any ledger of that vintage. If the operator's real ledger
> predates 2026-08-07, one `connect` now migrates it; if it does not, the
> migration is a no-op. Worth confirming on the real file either way.

---

## Before the fix — the epic wedges (T031)

Source reverted to the tree as it stood (`git checkout -- factory/`), tests as
committed in `f6e4151`:

```
FAILED test_connecting_a_pre_008_ledger_widens_it_so_a_question_teardown_lands
FAILED test_the_widening_keeps_the_rows_the_ledger_already_had
FAILED test_every_termination_the_factory_can_write_is_admitted_after_a_migration
FAILED test_a_teardown_the_ledger_refuses_at_the_park_does_not_wedge_the_epic
4 failed, 11 passed in 32.50s
```

The fourth failure is 073's morning. After 30 real seconds with the question
answered and nothing left to run:

```
tests/test_interpreter.py:1890: AssertionError: timed out after 30.0s waiting for
us1 to stop being parked on a question its teardown cannot close; last status:

  epic_state = PAUSED
  us1: state=WAITING_OPERATOR attempt=1 awaiting_operator=True  terminal_reason=None
  us2: state=PENDING          attempt=0 awaiting_operator=False terminal_reason=None
  us3: state=PENDING          attempt=0 awaiting_operator=False terminal_reason=None
```

**Two stories behind one park**, and nothing pending to explain it. The
mechanism, from the same run:

```
Task exception was never retrieved
future: <Task finished name='Task-41 (workflow: EpicWorkflow, id: epic-demo-loans,
        run: da4fa2a1-...)' coro=<EpicWorkflow._run_node() done,
        defined at factory/workgraph/workflow.py:1437>
        exception=ActivityError('Activity task failed')>
temporalio.exceptions.ApplicationError: IntegrityError: CHECK constraint failed: usage_records

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "factory/workgraph/workflow.py", line 1950, in _run_node
    await self._teardown(lease, termination, record.last_snapshot)
  ...
temporalio.exceptions.ActivityError: Activity task failed
```

`_run_node` raised **holding the park**. `self._paused` stays `True` with nobody
alive to clear it, and `_drain_in_flight` never reaps the corpse, because the
record still says `WAITING_OPERATOR` — a state it deliberately does not wait on,
since a parked node is alive by design. Zero pending activities, deterministic on
replay: the finding's description of the live failure, line for line.

---

## After the fix — the node ends and the sibling runs (T031)

Two changes: `factory/usage/ledger.py` migrates the constraint (the cause), and
`factory/workgraph/workflow.py` releases the park on the raising path as well as
the returning one (the blast radius — *any* raise between the park and the
un-park costs the whole epic, not just this one).

Same scenario, same refused teardown, fixed tree:

```
--- at the park ---
  epic_state = PAUSED
  us1: state=WAITING_OPERATOR attempt=1 awaiting_operator=True  terminal_reason=None
  us2: state=PENDING          attempt=0 awaiting_operator=False terminal_reason=None
  us3: state=PENDING          attempt=0 awaiting_operator=False terminal_reason=None

--- after the teardown failed (fixed tree) ---
  epic_state = RUNNING
  us1: state=KILLED           attempt=1 awaiting_operator=False terminal_reason='Activity task failed'
  us2: state=KILLED           attempt=0 awaiting_operator=False terminal_reason=None
  us3: state=VERIFYING        attempt=1 awaiting_operator=False terminal_reason=None
  dispatched = ['us1', 'us3']
```

The refused teardown still refuses — the fix does not pretend a broken ledger
works — but it now costs one node instead of the epic. `us1` ends terminal, `us2`
is locked out behind a dependency whose edge is dead, and **`us3`, which was
`PENDING` behind the park, dispatches**. That is FR-011.

One observation worth an operator's attention rather than a change here:
`terminal_reason` reads `'Activity task failed'`, which is `_reap_finished`'s
`str(exc)` on a Temporal `ActivityError` and does not name the ledger. The cause
is in the workflow's logs and in the activity's own error; the status line is
thinner than it could be. Out of this story's scope, and noted rather than
silently tolerated.

And with the migration in place, the ledger accepts the row a parked question
owes, so the ordinary path never reaches any of this:

```
CREATE TABLE "usage_records" (
    ...
    termination            TEXT    NOT NULL CHECK (termination IN
                               ('completed', 'agent_error', 'timeout', 'killed', 'question', 'auth_failure')),
    ...
)
```

— the pre-008 table after one `ledger.connect()`, with its rows, its `id`s, its
UNIQUE guard and its four indexes intact.

---

## The full run, green (T031)

```
PASSED test_a_pre_008_ledger_refuses_the_row_a_parked_question_owes
PASSED test_connecting_a_pre_008_ledger_widens_it_so_a_question_teardown_lands
PASSED test_the_widening_keeps_the_rows_the_ledger_already_had
PASSED test_every_termination_the_factory_can_write_is_admitted_after_a_migration
PASSED test_a_current_ledger_is_left_exactly_as_it_is
PASSED test_a_teardown_the_ledger_refuses_at_the_park_does_not_wedge_the_epic
PASSED test_an_answer_that_arrives_long_after_the_park_un_parks_the_node
PASSED test_the_answer_attempts_prompt_carries_the_exchange_verbatim
PASSED test_the_assembled_prompt_renders_the_exchange_without_a_workflow
PASSED test_a_sibling_pending_behind_the_park_dispatches_once_the_node_resumes
PASSED test_an_answered_park_lets_the_whole_epic_finish
PASSED test_an_expired_question_still_re_enters_the_ladder_as_a_fail
PASSED test_an_expired_question_leaves_no_node_parked_and_no_epic_paused
PASSED test_a_kill_while_parked_still_leaves_the_node_parked
PASSED test_the_reproduction_graph_really_does_stand_a_sibling_behind_the_park
15 passed in 9.04s
```

The repository's declared gate (`ergane.yaml`: `uv run pytest -q`), whole:

```
4164 passed, 52 skipped, 7 warnings in 333.57s (0:05:33)
```

The two controls are in that list and passed before and after. US3-S4: an
expired question still burns its slot and re-enters the ladder as a FAIL
(`[1, 2, 3, 4]` attempts against the answered case's `[1, 2, 3, 4, 5]` — the
difference *is* the slot). And a kill landing on a parked node still leaves it
parked with its row pending, which is the path the new `except Exception` clause
must not reach, because it `break`s rather than raises.

---

## The assembled prompt, carrying the exchange (T032, SC-007)

Verbatim from `build_attempt_prompt(..., operator_answer=OperatorAnswer(...))` —
the same pure function `_run_node` calls at `factory/workgraph/workflow.py:1541`
to build the attempt that follows an answer, and the section of its output that
the answer produces:

````text
## Operator answer

You asked the operator a question on your previous attempt, and the operator answered. Both are reproduced verbatim — the question you asked, then the answer the operator gave. Read the answer as the operator's decision and proceed on it.

Question:

```text
I hit a fork on how the questions table should key its rows.

Option A: a 12-hex id like escalations. Option B: the (epic, node, attempt) tuple. I lean A for reply-routing parity.

Which?
```

Answer:

```text
Go with Option A: a 12-hex id like escalations, for reply-routing parity.
The (epic, node, attempt) tuple collides across re-runs.
```
````

Both halves of the exchange, unparaphrased, under a heading distinct from
`## Prior attempt evidence` (the ladder's verdict) and from the agent's own
`## OPERATOR QUESTION` marker. `test_the_answer_attempts_prompt_carries_the_exchange_verbatim`
makes the same assertion against `AttemptContext.prompt` — the bytes the workflow
actually handed the adapter on the attempt that followed a live answer — so the
claim is about a dispatched prompt and not only about the assembler.
