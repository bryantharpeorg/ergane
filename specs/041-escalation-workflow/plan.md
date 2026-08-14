# Plan: Escalation is a workflow, and its transport is an adapter

All line references were read against the tree at `ace6229` on 2026-08-13. Grep
the construct beside each anchor rather than trusting the number — see trap 8.

This epic touches code the operator uses every day. US3 in particular refactors
the live escalation path while the channel is in use. Read trap 1 before you
touch anything under `tests/`.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| **The caller-supplies-the-id seam, already built** | `factory/activities/notify_activities.py:150` — `SendEscalationInput.escalation_id` is optional and reused when given; `_pending_record` at `:355` honours it | US2 — this is how the correlation id becomes the workflow ID without inventing a mechanism; trap 3 |
| The delivery activity | `notify_activities.py:272` — grep `async def send_escalation` | US2 — the workflow's delivery step |
| The expiry activity, **which already settles the race** | `notify_activities.py:318` — grep `async def expire_escalation` | US2 — FR-007 is mostly already satisfied here; trap 2 |
| The store's guarded UPDATE | `factory/verify/store.py:469` — grep `UPDATE escalations SET resolution` | US2 — press arbitration, unchanged |
| The two tables and why there are two | `store.py:131` (`escalations`), `:159` (`questions`) | US2, US4 — trap 5 |
| The two signals | `factory/workgraph/workflow.py:571` (`escalation_resolved(id, choice)`), `:582` (`question_answered(id, text)`) | US2, US3 — trap 5 |
| **The escalation park being extracted** | `workflow.py:1950`–`:1990` — grep `send_escalation` then `wait_condition` | US3 — read the whole block, including the undelivered branch |
| The question park being extracted | `workflow.py:1362`–`:1460` — grep `send_question` | US3 |
| The scheduler's own park | `workflow.py:1050` — grep `wait_condition(not self._paused)` | US3 — FR-010's hazard; trap 6 |
| The bridge that ferries replies today | `factory/notify/service.py:126` (`CallbackBridge`), `:365` (`run_bridge`) | US1 — the inbound half of the seam |
| Message rendering, which does not change | `factory/notify/messages.py` | US1 — the adapter receives an *already-rendered* message |
| **039's workflow-scope env guard, which discovers new modules by construction** | `tests/test_workflow_env_guard.py:184` — grep `_discover_workflow_modules` | US2 — trap 4 |
| The legitimate activity-scope store read | `notify_activities.py:650` — grep `def _store_path` | US2 — activity scope is fine; workflow scope is not |
| The 008 behavior suite US3 may not edit | `tests/test_notify.py`, `tests/test_notify_activities.py`, `tests/test_operator_question.py`, `tests/test_question_delivery.py`, `tests/test_question_reply.py` | US3 — trap 1 |
| The Telegram live suite | `tests/test_live_notify.py`; marker at `pyproject.toml:34` | US1 — trap 7 |
| 033's typed config | `escalation.adapter`, `escalation.authorized_responders` | US1, US4 |

## Traps

### Trap 1 — US3's criterion is a suite that does not change, so do not change it

The five behavior-suite files listed above are the guard. If your diff edits an
assertion in any of them to accommodate the refactor, the refactor changed
behavior and the guard stopped guarding. FR-009 and SC-004 both say this, and
SC-004 says how it is checked: **the diff shows those files unchanged.** If you
believe an assertion is genuinely wrong, that is a finding to report, not an
edit to make inside this story.

### Trap 2 — the race is already settled; do not settle it twice

FR-007 asks that an answer racing expiry resolve to exactly one deterministic
outcome. That is already true, in code, at two levels:
`store.expire_escalation` (`store.py:469`) is a guarded UPDATE that permits
exactly one terminal transition, and the `expire_escalation` activity
(`notify_activities.py:318`) reads the row back when the guard matches nothing
and hands the workflow the operator's answer *instead of* the kill — the R12
case, documented in its docstring. Its other documented promise matters too: it
never raises on an unknown id or an unreadable store, because "the caller's
fail-safe kill must not be blocked by the same failure that lost the row."

So the EscalationWorkflow's job is to *call* this, not to add arbitration
beside it. Two arbiters is how a press that beat the timer starts losing
sometimes.

### Trap 3 — the correlation id must be minted before the workflow starts

FR-004 makes the workflow ID the correlation id. A workflow ID must exist
before `start_workflow`, and `secrets.token_hex` cannot be called from workflow
scope (non-deterministic). Today the id is minted inside the activity
(`_pending_record`, `notify_activities.py:355`).

The seam for this is already there and already used: `SendEscalationInput`
carries an optional `escalation_id` that the activity reuses rather than
minting, added for the roadmap failure path that writes its row before
attempting delivery. So the *starter* mints the id, uses it as the workflow ID,
and passes it in. Do not add a second id, and do not mint inside the workflow.

Two consequences worth knowing. The 12-hex-digit width exists so Telegram's
`callback_data` fits in 64 bytes without carrying a workflow id (R11) — keep
the width. And `SentEscalation.expires_at` exists so the row's deadline and the
workflow's timer agree; the extracted workflow must still set its timer from
the same instant, or the bridge and the workflow will disagree about whether a
press was in time.

### Trap 4 — 039's guard will find your new workflow module without being told

`tests/test_workflow_env_guard.py` discovers workflow-defining modules by
scanning for the decorator (`:184`), which is exactly why it was built that
way. Your new `@workflow.defn` module is covered the moment it exists, and an
`os.environ` read at workflow scope in it fails a test you did not write. This
is the defect that wedged the roadmap for eleven hours on 2026-08-13; FR-012
keeps it closed. Note the distinction the guard already makes correctly:
`notify_activities._store_path()` (`:650`) is an *activity*-scope read and is
legitimate. Keep store-path resolution on that side of the line.

### Trap 5 — there are two signals and two tables, and the second of each exists for a reason

`escalation_resolved(escalation_id, choice)` carries a choice pinned to a closed
enum by the `escalations` table's CHECK constraints. `question_answered(
question_id, answer_text)` exists as a sibling because free text cannot pass
through that enum — the `questions` table (`store.py:159`) is a sibling of
`escalations` (`:131`) for the same reason. The tempting simplification is one
signal and one table. It may even be right — but it is a behavior change to
the operator channel, and this epic's whole discipline is that behavior does
not change. Carry both; if you want to unify them, that is a finding and a
later spec.

### Trap 6 — prove the 017 hazard is gone, do not assert it

FR-010 says awaiting an escalation child must not pause the epic's scheduler.
The scheduler parks on `wait_condition(not self._paused)` (`workflow.py:1050`),
and 017's recorded hazard is that a peer park reusing the operator park pauses
that scheduler and deadlocks the answering peer — which is why 017 is held at
draft. Inspection cannot show this is fixed. **Two concurrent escalations, the
second not blocked by the first**, is what shows it, and SC-005 asks for exactly
that test.

### Trap 7 — "byte-compatible" is a claim about the live channel

FR-003 says the telegram adapter is byte-compatible and the existing suite
passes unmodified. A refactor proven only against a fake adapter has proven
only that the fake agrees with the new code — which is the same
fake-agrees-with-client failure `tests/test_live_proxy.py`'s docstring was
written about. `tests/test_live_notify.py` auto-skips without
`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`. If those are present in your
environment, run it and paste the transcript. If they are not, say so plainly
in the commit rather than claiming a compatibility you did not observe.

### Trap 8 — anchors rot, and this tree is moving fast

Nineteen stories landed on 2026-08-13 alone. Grep for the construct —
`send_escalation`, `expire_escalation`, `escalation_resolved`,
`_discover_workflow_modules`, `CallbackBridge` — and if a citation here
disagrees with the tree, the tree wins and you say so in the commit message.

## Approach

### US1 — the interface, and Telegram behind it

1. Define the adapter protocol with exactly two operations (FR-001). It takes
   an *already-rendered* message; rendering stays in `factory/notify/messages.py`.
2. Move today's Telegram send and the bridge's ferry behind it, changing no
   message and no assertion.
3. Make it a plain library (FR-002): no Temporal import on the adapter's own
   path, and a test that calls it from a process with no client and no workflow
   context — 042's supervision probe is that caller, and it runs when Temporal
   is dead.
4. Register adapters by the name 033's config declares, so an unknown name was
   already refused at parse time.

### US2 — the workflow type, standalone first

1. The starter mints the correlation id and uses it as the workflow ID (trap 3).
2. `run()`: execute the delivery activity, then race a signal against a durable
   timer set from the row's own instant. On timeout, call `expire_escalation`
   and take its answer (trap 2). Result is `answered(text, identity)` or
   `expired`.
3. Preserve the undelivered fail-safe: today an undelivered escalation returns
   the kill default *without waiting* (`workflow.py:1968`). Keep that shape.
4. `ergane escalations list` queries running EscalationWorkflows (FR-008) —
   the capacity read at `factory/activities/roadmap_activities.py:432` is the
   precedent for listing workflows by id prefix.
5. Prove standalone and as a child of a *test* parent. The real parent is US3.

### US3 — the migration, behind an unedited suite

1. Replace the escalation park (`workflow.py:1950`–`:1990`) and the question
   park (`:1362`–`:1460`) with start-child-and-await.
2. Remove the epic's own escalation timer and signal handlers (FR-010) — and
   only those; the pause, resume and kill signals stay.
3. Run the five behavior-suite files unchanged (trap 1) and paste the result.
4. Add the two-concurrent-escalations test for FR-010 (trap 6).

### US4 — webhook, identity, and `ergane answer`

1. The webhook adapter POSTs rendered message plus correlation id; the test
   double is a local HTTP listener.
2. `ergane answer <correlation-id> <text>` signals the EscalationWorkflow named
   by that id. For an id with no running workflow, report which of the three
   cases it was — answered, expired, or never existed — rather than a generic
   failure.
3. The authorized-responders check is **factory-side**, applied to every
   adapter's relay, not implemented per adapter (FR-011). An unauthorized reply
   is recorded with its identity and touches neither state nor the expiry clock,
   and a later authorized reply is still accepted (SC-002).

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| Four stories | US2 must be provable before US3 migrates a live consumer onto it — that separation is 032's lesson, where one story requiring two things in one diff burned four attempts and 128M tokens. US1 is the interface both need; US4 is additive and rides beside US3. |
| A workflow type rather than a shared helper | A helper would still need a timer and a signal target, which means a workflow — and the caller without an epic has nowhere to put either. 017 is the standing evidence: the second consumer of the welded park deadlocks. |
| Keeping two signals and two tables | Unifying them is a behavior change to the channel the operator uses daily, inside an epic whose criterion is that behavior does not change (trap 5). |
| Factory-side identity checking rather than per adapter | FR-001 forbids an adapter deciding anything. An adapter that filtered replies would be making an answer-or-not decision, which is the one thing the seam exists to keep factory-side. |

## Verification

`uv run pytest -q` green in the worktree before and after each story.

Green is necessary and not sufficient, three times:

- **US3** is verified by *what the diff does not contain*: the five behavior
  files unchanged (SC-004). A green suite you edited proves nothing.
- **FR-010** is verified by a second concurrent escalation, not by reading the
  code (trap 6).
- **FR-003's byte-compatibility** is verified against the live channel when its
  credentials are present, and honestly disclaimed when they are not (trap 7).
