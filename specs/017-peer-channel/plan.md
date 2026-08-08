# Implementation Plan: Peer Channel

**Input**: [spec.md](spec.md) in this directory. Grounded in the 008
implementation as it landed (PRs #11/#12/#13, attested 2026-08-07).

## Reuse inventory (verified against the tree 2026-08-08)

The channel exists; this feature adds the address. Every mechanism below is
landed and live:

- **Free-text answer signal + incurious buffering** —
  `factory/workgraph/workflow.py:541-566` (`question_answered`, buffered in
  `_answers` keyed by id, `_questions` stashed at park time,
  `workflow.py:472-487`). Peer messages get sibling buffers with the same
  discipline: signals only buffer; wait conditions read.
- **The in-flight ferry** — `factory/workgraph/adapter.py:108-203`
  (`FERRY_QUESTION_FILE`/`FERRY_ANSWER_FILE` in `$ATTEMPT_ARCHIVE`,
  `_FerryState`, poll cadence constants), with the activity-side callbacks
  `ferry_send_question`/`ferry_read_answer` wired at
  `factory/activities/agent_activities.py:73,453`. The addressee line is
  parsed from the same file; delivery down to a running peer reuses
  `write_answer`'s pattern with a distinct inbox file so a peer message is
  never confused with an operator answer.
- **Question store + guarded resolution** — `factory/verify/store.py:136-163`
  (questions DDL: 12-hex id as routing key, resolution states, expiry
  column, partial index on pending) and the guarded `resolve_question`
  first-wins arbiter (`store.py:609+`). Messages are a sibling table
  (`messages`: id, sender epic/node/attempt/persona, addressee, body,
  reply, resolution, expiry) in the same WAL/contract-DDL discipline.
- **Expiry loop** — the workflow's timer-driven park/expiry evaluation
  (`workflow.py:682-691` region): the same beat evaluates message expiry
  and sweeps mailbox outboxes via activity, so no new clock exists.
- **Degradation target** — the whole 008 US1/US2 path
  (`notify_activities.py:169+`, `question_message` in
  `factory/notify/messages.py`, `CallbackBridge.handle_reply` →
  `_answer_signal` in `factory/notify/service.py:198,279`): degrading a
  message = writing a question row from its content and shipping it through
  this path unchanged.
- **Prompt assembly's operator-answer section** — the dedicated section US2
  of 008 delivers answers through; the peer-message section is its sibling
  in the same assembly seam (`agent_activities.py`, prompt construction).
- **Telegram mirror** — the notify bridge's plain-notification path (no
  keyboard, no reply key), already used for lifecycle notices.

## New modules

- `factory/notify/peers.py` — registry load/validate (`peers.yaml`, sibling
  of `personas.yaml`): name, transport (`mailbox` today; the A2A seam),
  address, expiry seconds. Pure parse + named findings, personas-loader
  style.
- `factory/activities/peer_activities.py` — routing: same-epic delivery
  (workflow-internal, no activity needed beyond store writes), mailbox write
  (one JSON file, atomic rename), outbox sweep (returns reply rows for the
  workflow to buffer), cross-epic client signal (US3; the activity holds the
  Temporal client, the workflow never does).
- Workflow additions — `message_delivered`/`message_replied` signal(s)
  sibling to `question_answered`; per-node outstanding-message counters for
  the FR-006 cap; addressee resolution table (node ids + registry names +
  epic ids, one namespace, collisions refused at load).

## Traps (named so the implementer does not rediscover them)

- **Addressee-less compatibility is the contract** (FR-001, SC-006): the 008
  tests must keep their meaning without edits. Parse the addressee as an
  optional prefix line in the marker/ferry body; absence short-circuits to
  the existing code path before any new branch runs.
- **Signals only buffer** — the 008 hard rule: a signal handler that routes
  or acts runs inside whatever workflow task delivered it. All delivery
  decisions live in the scheduler/wait-condition side.
- **The FR-012 hole stays narrow** (FR-005): message text enters prompts and
  parks nodes; it must be unreadable by gates and judge. The 008 FR-010
  guard test is the template — extend it, do not fork it.
- **Mailbox writes are cross-trust-boundary**: atomic rename into the inbox,
  no partial files; unwritable path = immediate refusal to the asker, never
  a retry loop inside routing (US2-S4, edge case list).
- **Cross-epic signal to a finished workflow**: the client signal raises;
  catch and degrade (FR-004) — the sibling epic being gone is the same fact
  as a terminal peer.
- **Ledger discipline**: message exchanges change no accounting — QUESTION's
  no-burn rule already covers the park; a ferried in-flight exchange costs
  nothing but tokens, which the usage read already meters.

## Structure

US1: grammar + routing + store + degradation + cap + sweep extension
(workflow.py, adapter.py, store.py, agent_activities.py, notify surfaces).
US2: `peers.py` + mailbox transport + mirror + registry refusals
(`peer_activities.py`, one workflow seam for outbox sweep on the expiry
beat). US3: cross-epic signal + namespace completion + decision-log and
architecture-doc entries. No new dependency; no new store; no new clock.
