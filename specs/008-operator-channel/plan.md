# Implementation Plan: Operator Channel

**Branch**: `008-operator-channel` | **Date**: 2026-08-06 (verified against the tree 2026-08-07) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-operator-channel/spec.md`

## Summary

A blocking design question from an implementer currently dies in a one-shot
stdout and is charged as a failed attempt (found live: 006-us1 attempt 1,
2026-08-06 — $2.57 and 23 minutes to ask a good question nobody could hear).
This feature gives the question a channel built from parts the factory already
runs — the streamed transcript the adapter already archives, the escalation
send/expiry patterns, the Telegram bridge, the retry-prompt evidence assembly —
plus three genuinely new pieces this plan names honestly: a `questions` store
table (the escalations table's CHECK constraints make it unusable for free-text
answers), a free-text reply path in the bridge (it is callback-only today), and
a **scoped amendment to D-018/FR-012**, which currently forbids any
agent-reported signal from reaching node state. Every claim below was verified
against the tree on 2026-08-07; T002 re-verifies against the tree that hosts
the work.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so contracts an implementer node needs are inlined here.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio`, `httpx`, `pyyaml`, `python-telegram-bot`
— all roster items, all already in use. **This feature adds no dependency.**

**Verified reuse inventory** (file:line as of 2026-08-07):

- **The final message's real home**: the adapter streams the agent's combined
  stdout/stderr live into the attempt archive (`factory/workgraph/adapter.py:36`,
  `STDOUT_LOG_NAME = "stdout.log"` at `:67`), and `AdapterResult.transcript_path`
  points at that directory (`factory/workgraph/models.py:249-261`). The output
  check does NOT read it — `check_output` is a diff/artifact check only
  (`factory/activities/verify_activities.py:270-310`). Marker detection is
  therefore a new, read-only verification-side reader over the archived
  `stdout.log`, keyed off `transcript_path`.
- **The rule this feature must amend, not evade**: `AdapterResult` is narrow by
  design — "No diff, no usage numbers, no parsed verdict … FR-012 forbids any
  agent-reported signal from reaching node state. `transcript_path` is
  evidence, never an input to a decision" (`models.py:250-258`, D-018). A
  question marker that produces a QUESTION classification is an agent-authored
  signal reaching state. The spec records the scoped amendment (spec
  § Decision): exactly one signal, park-only, never a verdict.
- **Escalation store — pattern yes, table no**: the `escalations` schema
  (`factory/verify/store.py:116-133`) hard-CHECKs
  `resolution IN ('RETRY','KILL','PAUSE_EPIC','EXPIRED')` and
  `resolved_via IN ('BUTTON','TIMEOUT')`, stores `choices` as a JSON list of
  `EscalationChoice` (StrEnum `RETRY|KILL|PAUSE_EPIC`,
  `factory/verify/models.py:112-121`), and has **no** kind, attempt, answer, or
  Telegram message-id column. Free text cannot ride it. **Decision: a sibling
  `questions` table in the same verification DB** — `question_id` (12-hex, the
  escalation keying convention), workflow/epic/node/attempt, `question_text`,
  `message_id` (Telegram, for reply routing), `sent_at`, `expires_at`,
  `resolution IN ('ANSWERED','EXPIRED')`, `answer_text`, `resolved_at` — reusing
  the store's idempotent `_transition` shape and expiry discipline
  (`store.py:482-527`: "True if this call is what resolved it"), not the
  constrained table.
- **Bridge**: `CallbackBridge.handle` (`factory/notify/service.py:118-148`) is
  callback-query-only and validates a press against the record's offered
  choices before signalling. Free-text replies are a new `MessageHandler`
  registered beside the existing `CallbackQueryHandler` (`service.py:230-231`),
  routing reply-to `message_id` → `question_id` via the new table.
- **Signal**: `SIGNAL_NAME = "escalation_resolved"` (`service.py:56`) resolves
  through the enum-validated escalation path — overloading it with free text
  was this plan's first idea and the store's CHECK constraints falsify it.
  **New signal `question_answered(question_id, answer_text)`** on
  `EpicWorkflow`, mirroring the `escalation_resolved` shape (`workflow.py:414-423`).
- **Send path template**: `send_escalation`
  (`factory/activities/notify_activities.py:158`) with `SendEscalationInput`
  (workflow_id/epic_id/node_id/history_summary; deliberately no credential —
  `:109-121`) and `SentEscalation` (escalation_id, delivered, expires_at,
  `:127-135`). `send_question` mirrors it, with two deltas: no keyboard (a
  question wants a typed reply, not buttons), and the Telegram `message_id`
  from the send **is captured into the questions table** — the escalation path
  never stores it, and reply routing needs it.
- **The answer's road into the next prompt — verified real**: the ladder
  threads `prior_feedback` between attempts (`factory/workgraph/workflow.py:643`,
  `:729-732` — "if verdict is not None and verdict.feedback: prior_feedback =
  verdict.feedback") and the prompt assembler renders verification evidence
  sections (`factory/workgraph/prompt.py:147-152`, judge feedback quoted at
  `:392-393`). The operator answer becomes a **sibling section** in that same
  assembly — a decision, rendered distinctly from a diagnosis.

**Storage**: the new `questions` table above; the ledger is untouched (FR-006
is satisfied by the existing teardown path — QUESTION is a termination class,
not an accounting exemption).

**Testing**: `pytest`, `WorkflowEnvironment.start_time_skipping()`,
`ActivityEnvironment`, the fake-bridge and scripted-world patterns already in
the notify/interpreter suites. Everything provable without a live bot; one
optional `live_telegram` case may round-trip a real reply.

**Project Type**: single Python package (`factory/`).

**Constraints**: No behaviour change any existing escalation test asserts
(SC-005). Repo gotcha: `tests/test_final_sweep.py` bans 18 enforcement words in
component identifiers/strings and forbids branching on values named
`requests`/`cost`/`tokens` — check its lists before naming anything here.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with its implementation.
- **III (no unapproved dependencies)**: none added.
- **V (credentials)**: FR-007. Question and answer text transit Telegram —
  outside the machine. Extend the escalation sweep's assertion to question
  payloads, stored answers, and the new table. No key value, ever.
- **VI (salvage)**: FR-005 — a question attempt's committed work is preserved
  via the same salvage path as any terminal attempt.
- **VII (persona routing)**: untouched.
- **D-018/FR-012**: amended, not violated — the amendment is scoped in spec
  § Decision and recorded in the decision log at landing (FR-010).

## Approach by story

### US1 — question detection, classification, delivery (FR-001/002/005/006/007)

The marker is a fixed heading the agent writes in its final message:

```
## OPERATOR QUESTION
<the fork, the options considered, the agent's lean>
```

Detection: a new read-only verification activity reads the archived
`stdout.log` under `AdapterResult.transcript_path` (the adapter streams it
live, so it exists on every termination path) and extracts a line-anchored
marker section from the **final** assistant message. Marker present → the
attempt's termination is QUESTION; verification records the fact and never
consults gates or judge for a verdict — there is nothing to grade, and the
amendment's guard is exactly that a marker can *park* a node and can never
*pass* one. The ladder routes QUESTION to `WAITING_OPERATOR`; salvage and
teardown run exactly as for any terminal attempt (FR-005/006).

Delivery: `send_question` (mirror of `send_escalation`, no keyboard), row into
the `questions` table with the Telegram `message_id` captured at send.

**The trap**: QUESTION must not be reachable by accident. Line-anchored fixed
heading, final message only, not inside fenced blocks; a task must assert the
false-positive case — an attempt whose final message merely *discusses* the
marker is not classified QUESTION.

### US2 — the answer round trip and the no-burn accounting (FR-003/004/008)

The bridge gains a `MessageHandler`: a Telegram **reply** to a question message
looks up `message_id` → `question_id`, records the reply text as `answer_text`
via the idempotent transition (first answer wins), and signals the workflow
with the new `question_answered(question_id, answer_text)` signal. Routing is
by reply-to threading only (FR-008) — never "the newest open question"; a
non-reply message, a reply to a non-question message, and a reply to an
already-resolved question are all ignored or answered-as-settled, mirroring
the bridge's existing outcomes.

On the signal the node un-parks and dispatches its next attempt; the prompt
assembler renders the stored question and answer verbatim in a dedicated
operator-answer section, distinct from verification feedback. Attempt
accounting: the ladder's ceiling counts only burn-class terminations; a task
asserts a node's remaining attempts are identical before the question attempt
dispatched and after its answer arrived.

Expiry (FR-004) reuses the escalation expiry *pattern* — the workflow timer
plus an idempotent expire transition on the questions table ("True if this
call is what expired it") — an expired question resolves as if the attempt had
FAILed, and the ladder proceeds. Expiry window: the escalation default, no new
knob unless a test proves it wrong.

### US3 — the in-attempt ferry (FR-009), deferred behind live evidence

Ferry files in the attempt's **archive directory** (never the worktree —
nothing salvage would commit): the agent writes `question`, polls for
`answer`; the adapter's monitor loop ships the question up (same `questions`
row + send) and the answer down. Bounded window; on expiry the agent proceeds
to the US1 final-message path, so the ferry can only improve the round trip,
never hang it (FR-009). Sequenced behind 006-US1's adapter changes: one
monitor loop, one editor at a time.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| Agent-signal creep past the amendment | D-018/FR-012 exists to stop self-grading; the marker is a hole in it | Amendment scoped in spec § Decision: one marker, park-only, never a verdict; guard asserted in tests |
| Marker false positives | Classification by string match on model output | Line-anchored fixed heading, final message only; explicit false-positive test |
| Answer routed to wrong question | Two nodes parked concurrently | `message_id` reply-to threading via the questions table; asserted with two open questions |
| Question parks a node forever | Operator asleep; epic hostage | Expiry reuses the escalation timer + idempotent-transition pattern (FR-004) |
| Free text corrupts escalation semantics | escalations table CHECKs are load-bearing for the fail-safe ladder | Sibling `questions` table; the constrained table is never touched |
| Credential leak via Telegram | Question/answer text leaves the machine | Sweep assertion extended to payloads, answers, and the new table (FR-007) |
| Burn-free questions get farmed | Agents learn asking is free | Prompt contract: a question names its fork and options; no verdict exists to game — operator patience is the rate limiter |
