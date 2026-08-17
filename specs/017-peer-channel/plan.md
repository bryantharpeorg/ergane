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

## Reuse inventory — US4 consults

- **Ephemeral spawn machinery is every attempt**: `adapter_for` +
  `run_attempt` (`factory/workgraph/adapter.py:219-249`) already dispatch,
  monitor, classify, and tear down a one-shot `claude -p`. A consult is
  `run_attempt` with no verification ladder behind it — the reply is the
  final message, classification is reply-or-not.
- **The judge is the persona precedent** for one-request lifetimes and for
  context-in-prompt over worktree access: v0 consults get no worktree —
  message, spec, plan, and asker identity are assembled into the prompt
  (the registry can grant a worktree later without touching the seam).
- **Key issuance bracket**: consults get their own scoped virtual key,
  issued and torn down inside the spawn bracket (constitution V — no key
  outlives its work), and the usage read meters them exactly as attempts,
  attributed to the asking node (FR-015, D-013).
- **Memory layer**: an MCP config file written per consult pointing at the
  factory-owned Hindsight bank (FR-014) — endpoint from operator-owned
  factory config, absent means no MCP config is written and the consult
  runs bare. The credential sweep covers the written config file. Retain,
  if used, verifies extraction (`memory_unit_count > 0`), never the ack —
  the bank's own outage history is the reason.

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
  epic ids + persona names, one namespace, collisions refused at load).
- `factory/activities/consult_activities.py` (US4) — the consult runner:
  context assembly, MCP config write, spawn bracket (key + adapter +
  teardown), reply extraction, spawn-bound enforcement. No verdict types
  imported: a consult cannot reach the ladder by construction.

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
  nothing but tokens, which the usage read already meters. Consults are the
  exception that proves it: they DO spend, so they are metered and
  attributed like attempts (FR-015) while consuming no ladder slot.
- **No consult recursion** (US4-S3): a consult's output is scanned for the
  marker only to refuse it — consults answer or decline, and a consult that
  wants help is a decline. Without this rule a consult chain is an unbounded
  spawn tree.
- **The memory bank is optional equipment** (FR-014): every consult test
  must pass with no bank configured — the factory must never require a
  Hindsight server to route a message.

## Structure

US1: grammar + routing + store + degradation + cap + sweep extension
(workflow.py, adapter.py, store.py, agent_activities.py, notify surfaces).
US2: `peers.py` + mailbox transport + mirror + registry refusals
(`peer_activities.py`, one workflow seam for outbox sweep on the expiry
beat). US3: cross-epic signal + namespace completion + decision-log and
architecture-doc entries. US4: `consult_activities.py` + the consult rung
in routing + memory config — parallel to US2/US3, merged after US1. No new
dependency; no new store; no new clock.

## Added at the 2026-08-16 re-verification, and read this part first

**This spec was held for a reason, and the reason has not expired — it has been
converted into a dispatch condition.**

The 2026-08-08 verification pass found that a peer-addressed park would have
reused 008's operator park, which raises the scheduler's pause flag. The node
that must answer a peer question is a node of the *same epic*, so the pause
prevents the very dispatch that would answer it. Every peer question would have
dead-waited the 8-hour window and then paged the operator — making SC-001's
headline claim ("zero operator messages") false in production **while every
scripted test passed**. FR-016 now forbids that pause.

**A defect of that shape is exactly what a judge reading a diff cannot catch.**
So this epic gets a **watched run**: the operator watches the first peer exchange
happen for real, rather than accepting a PASS and moving on. That is a condition
on dispatch, not on readiness, and it is why this spec sat at `draft` for eight
days.

**What blocked validation, now fixed.** `ergane spec validate` refused this spec
outright: the 08-08 split of US1 into US1 + US2 renumbered the spec's stories and
never gave US2 a phase in `tasks.md`, so node `us2` had no task slice and could
not be dispatched at all. Phase 2b now exists. A repair on 2026-08-16 (#92) had
addressed part of the renumbering and missed this half.

**Sizing risk, stated plainly.** Five stories, and US5 alone spans consult-spawn
plus a two-layer memory integration. The diff ceiling is 61,440 bytes, refused
deterministically. Measure through `size_refusal` from
`factory/verify/diffbounds.py`, importing `DIFF_INPUT_LIMIT` rather than quoting
it. **If a story does not fit whole, say where you would split it — do not trim
checks.** On 2026-08-16 six stories landed on evidence the judge only partly saw,
one at 2.1x the ceiling; a seventh refused to fit, reported it, and was split
instead. The refusal was the right answer and cost nothing.

## Instrument traps carried forward from 2026-08-16

**Purge `__pycache__` between mutants**, or run under `PYTHONDONTWRITEBYTECODE=1`.
CPython validates a cached `.pyc` on `(mtime-in-whole-seconds, size)` only, so
two same-size mutants written inside one wall-clock second make the second run
execute the *first* mutant's bytecode. It fails toward green and reproduces
stably.

**Quote `passed` and `skipped`, never the warning count** — a warm cache
suppresses compile-time warnings. Baseline skips are 44; a new skip is a hidden
test you must declare.

**A mutation can be indistinguishable from correct** when every test observes the
two states at a moment they coincide. This spec is unusually exposed: a message
that arrives at the *next* attempt and one that arrives *mid* attempt look
identical to any test whose two attempts do not actually overlap in time. US2's
Independent Test says "attempts overlap" for that reason — honour it, or US2's
whole protocol change is unfalsifiable.

**Assert against the world, not a call log.** "We routed the message" is a claim
about your own code; "the addressee's assembled prompt contains it" and "neither
attempt terminated" are claims about the world. Only the second kind would have
caught the park deadlock this spec was held for.

