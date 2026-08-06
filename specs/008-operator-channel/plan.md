# Implementation Plan: Operator Channel

**Branch**: `008-operator-channel` | **Date**: 2026-08-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-operator-channel/spec.md`

## Summary

A blocking design question from an implementer currently dies in a one-shot
stdout and is charged as a failed attempt (found live: 006-us1 attempt 1,
2026-08-06 — $2.57 and 23 minutes to ask a good question nobody could hear).
This feature gives the question a channel built almost entirely from parts the
factory already runs: the final-message capture the output check already reads,
the escalation store and Telegram bridge that ladder escalations already use,
and the retry prompt that already carries verification feedback. New surface is
deliberately thin: a marker convention, a QUESTION termination class with
park-don't-burn ladder routing, free-text reply handling in the bridge, and an
operator-answer section in the prompt assembler.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so contracts an implementer node needs are inlined here.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio`, `httpx`, `pyyaml`, `python-telegram-bot`
— all roster items, all already in use. **This feature adds no dependency.**
If a task believes it needs one, that is an operator-approval conversation
(constitution III), not a quiet `uv add`.

**Existing parts this feature reuses — verify each against the code before
building on it; the first task of each story is that verification**:

- The agent's final message is captured per attempt and is already an input to
  verification (`check_output` reads attempt output today). The question marker
  rides that channel; no new artifact, no worktree pollution.
- The escalation store lives in the verification DB (`escalations` table,
  `factory/activities/verify_activities.py`) with expiry semantics
  (`expire_escalation`) and a resolution signal (`escalation_resolved`, carried
  by `SIGNAL_NAME`, signature `(escalation_id, choice: str)` — `choice` is a
  string and can carry free text; reuse it, do not add a second signal).
- The Telegram bridge (`factory/notify/service.py`, `CallbackBridge`) handles
  **callback queries only** (inline buttons). Free-text replies need a
  `MessageHandler` registered alongside the existing `CallbackQueryHandler`,
  routing by reply-to message id → escalation id. This is the one genuinely new
  bridge behaviour; everything else is reuse.
- Retry attempts already carry verification feedback into the next prompt. The
  operator answer is a **separate, clearly labelled section**, not an addendum
  to failure feedback — an answer is a decision, not a diagnosis.

**Storage**: No new store. Questions and answers are rows in the existing
escalation store with a distinguishing kind; the ledger schema is unchanged
(FR-006 is satisfied by the existing teardown path).

**Testing**: `pytest`, `WorkflowEnvironment.start_time_skipping()`,
`ActivityEnvironment`, and the existing fake bridge/store patterns in the
notify and verify test suites. Every behaviour here is provable without a live
Telegram bot; one optional `live_telegram` case may round-trip a real message.

**Project Type**: single Python package (`factory/`).

**Constraints**: No behaviour change that any existing escalation test asserts
(SC-005). Repo gotcha that will bite here if forgotten:
`tests/test_final_sweep.py` forbids certain enforcement words in component
string literals outside docstrings (D-021) — check its list before naming
anything in user-facing strings.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with its implementation.
- **III (no unapproved dependencies)**: none added.
- **V (credentials)**: FR-007. Question and answer text transit Telegram —
  outside the machine. The existing escalation sweep is the precedent; extend
  its assertion to question payloads and stored answers. No key value, ever.
- **VI (salvage)**: FR-005 — a question attempt's committed work is preserved
  identically to any salvaged attempt. The QUESTION path must reuse the salvage
  activity, not approximate it.
- **VII (persona routing)**: untouched.

## Approach by story

### US1 — question detection, classification, delivery (FR-001/002/005/006/007)

The marker is a fixed heading the agent writes in its final message:

```
## OPERATOR QUESTION
<the fork, the options considered, the agent's lean>
```

Detection happens in verification, next to where the output check already reads
attempt output: marker present → the attempt's termination is QUESTION and the
verification short-circuits (no judge — there is nothing to score; gates may
still be recorded if they ran). The ladder routes QUESTION to a new parked
state (`WAITING_OPERATOR`) instead of consuming a retry. Salvage and teardown
run exactly as for any terminal attempt (FR-005/006).

Delivery reuses the escalation send: a new kind (question) with epic/node/
attempt attribution and the marker body as text. The credential sweep extends
to this payload (FR-007).

**The trap**: QUESTION must not be reachable by accident. The marker is chosen
to be improbable in ordinary output (a level-2 heading with a fixed phrase),
and detection requires it at line start in the final message — not in code
blocks quoted from specs, not in the transcript body. A task must assert the
false-positive case: an attempt whose final message merely *discusses* operator
questions is not classified QUESTION.

### US2 — the answer round trip and the no-burn accounting (FR-003/004/008)

The bridge gains a `MessageHandler`: a reply to a question message resolves the
escalation with the reply text as `choice`, through the same
`escalation_resolved` signal ladder escalations use. Routing is by reply-to
message id, mapped to escalation id at send time (FR-008) — never "the newest
open question".

On resolution the node un-parks and dispatches its next attempt. The prompt
assembler adds an operator-answer section carrying the stored question and the
answer verbatim (FR-003) — the next agent sees both what was asked and what was
decided. Attempt accounting: the ladder's ceiling counts only burn-class
terminations; a task must assert a node's remaining attempts are identical
before the question attempt dispatched and after its answer arrived.

Expiry (FR-004) reuses `expire_escalation`: an expired question resolves as if
the attempt had FAILed, and the ladder proceeds. The expiry window is the
existing escalation default unless the registry overrides it; no new knob
unless a test proves the default wrong.

### US3 — the in-attempt ferry (FR-009), deferred behind live evidence

Ferry files in the attempt's archive directory (not the worktree — nothing the
salvage would commit): the agent writes `question`, polls for `answer`; the
adapter's monitor loop ships the question up (same delivery as US1) and the
answer down. The window is bounded; on expiry the agent proceeds to the US1
path (final-message marker), so the ferry can only ever improve the round trip,
never hang it (FR-009). Sequenced behind 006-US1's adapter changes by the work
graph, for the same reason 006 sequenced US4 behind US1: one loop, one editor
at a time.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| Marker false positives | Classification by string match on model output | Line-anchored fixed heading; explicit false-positive test |
| Answer routed to wrong question | Two nodes parked concurrently | Reply-to threading asserted with two open questions |
| Question parks a node forever | Operator asleep; epic hostage | FR-004 expiry reuses proven escalation expiry |
| Burn-free questions get farmed | Agents learn asking is free | Prompt contract: a question must name its fork and options; the judge never sees QUESTION attempts, so there is no verdict to game — only operator patience, which is the natural rate limiter |
| Credential leak via Telegram | Question text leaves the machine | Sweep assertion extended to question/answer payloads (FR-007) |
