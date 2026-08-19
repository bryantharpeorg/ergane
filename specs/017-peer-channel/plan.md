# Implementation Plan: Peer Channel

**Input**: [spec.md](spec.md) in this directory. Grounded in the 008
implementation as it landed (PRs #11/#12/#13, attested 2026-08-07), and
re-grounded on 2026-08-18 against 041-escalation-workflow, which moved the
mechanism this plan reuses.

## What 041 moved, and why it makes US1 smaller

This plan was written on 2026-08-08. Spec 041 landed afterwards and **took the
question lifecycle out of the epic workflow**. It was motivated by this very
spec: the peer-park deadlock is the recorded evidence that welding a park into
the epic workflow costs the next consumer. That next consumer is you.

What this changes, concretely:

- A question is now a **child workflow** — `QuestionWorkflow`
  (`factory/escalation/question.py:87`), a sibling of `EscalationWorkflow`. It
  owns its own signal, its own 8h window, its own ferry dedup and its own row.
- The epic workflow starts it and parks the node:
  `factory/workgraph/workflow.py:1320` (`start_child_workflow`), then sets
  `record.state = NodeState.WAITING_OPERATOR` and `record.pending_question_id`,
  then awaits at `workflow.py:1357`.

**So do not build peer messages as sibling buffers inside the epic workflow.**
That was this plan's original instruction and it is now the wrong shape — it
swims against the tree and re-commits the mistake 041 was written to undo.
Build a `MessageWorkflow` child in `factory/escalation/`, modelled on
`question.py`, and start it from the same seam.

**This is what makes FR-016 cheap.** Read `factory/workgraph/workflow.py:1344`.
It is one line:

```python
self._paused = True
```

That single line is the deadlock. It is what raises the scheduler's pause flag
(consumed at `workflow.py:691`, which drains and parks the whole scheduler until
the flag clears). FR-016 forbids exactly it for a peer park. **Mirror the
question block and omit that line** — plus give the park its own `NodeState`
member alongside `WAITING_OPERATOR` (`factory/workgraph/models.py:111`), because
FR-016 also requires a distinct node state.

Note the consequence for the drain: `_drain_in_flight` skips nodes in
`WAITING_OPERATOR` (`workflow.py:1027`) so a parked question is not treated as a
bracket to close. A new peer-park state must be added to that same exemption, or
the drain will wait forever on a node that is alive by design. That test is the
one worth writing first.

## Reuse inventory (re-verified against the tree 2026-08-18 — every anchor below was read)

The channel exists; this feature adds the address. Every mechanism below is
landed and live.

**Read the note "What 041 moved" before this list.** The 2026-08-08 edition of
this inventory pointed the question mechanism at `factory/workgraph/workflow.py`.
041-US3 moved it out. Every anchor below is the 2026-08-18 location; the old ones
resolve to unrelated code, not to nothing, so a stale anchor here reads as a real
answer.

- **Free-text answer signal + incurious buffering** — now a child workflow:
  `factory/escalation/question.py:87` (`QuestionWorkflow`), whose
  `question_answered` handler is at `question.py:98` and buffers into
  `self._replies` (`question.py:95`), read by a `wait_condition` at
  `question.py:142`. The wire name is `QUESTION_SIGNAL_NAME`
  (`factory/notify/service.py:95`). Peer messages get a sibling with the same
  discipline: signals only buffer; wait conditions read.
- **The in-flight ferry** — `factory/workgraph/adapter.py:148-217`
  (`FERRY_QUESTION_FILE`/`FERRY_ANSWER_FILE` at `adapter.py:148-149` in
  `$ATTEMPT_ARCHIVE`, `_FerryState` at `adapter.py:170`, the question write at
  `adapter.py:199`, `write_answer` at `adapter.py:206`), with the activity-side
  callbacks `ferry_send_question`/`ferry_read_answer` now in
  `factory/activities/notify_activities.py:918,942`, imported and wired in
  `factory/activities/agent_activities.py:74,230,476`. The addressee line is
  parsed from the same file; delivery down to a running peer reuses
  `write_answer`'s pattern with a distinct inbox file so a peer message is
  never confused with an operator answer.
- **Question store + guarded resolution** — `factory/verify/store.py:213`
  (questions DDL: 12-hex id as routing key, resolution states, expiry
  column, partial index on pending) and the guarded `resolve_question`
  first-wins arbiter (`store.py:1183`). Messages are a sibling table
  (`messages`: id, sender epic/node/attempt/persona, addressee, body,
  reply, resolution, expiry) in the same WAL/contract-DDL discipline.
- **Expiry** — no new clock: the question's window is owned by its child
  workflow (`factory/escalation/question.py:109` onward, anchored at the send
  rather than compared against the row's `expires_at` — two clocks, one bug).
  A message window is the same shape in its own child. The mailbox outbox
  sweep is the one genuinely new beat; hang it off the same activity cadence,
  never off a wall clock read inside workflow code (039's guard finds that).
- **Degradation target** — the whole 008 US1/US2 path
  (`send_question` at `factory/activities/notify_activities.py:763`,
  `question_message` at `factory/notify/messages.py:337`,
  `CallbackBridge.handle_reply` at `factory/notify/service.py:472` →
  `_answer_signal` at `service.py:644`): degrading a message = writing a
  question row from its content and shipping it through this path unchanged.
- **Prompt assembly's operator-answer section** — the dedicated section US2
  of 008 delivers answers through; the peer-message section is its sibling
  in the same assembly seam (`agent_activities.py`, prompt construction).
- **Telegram mirror** — the notify bridge's plain-notification path (no
  keyboard, no reply key), already used for lifecycle notices.

## Reuse inventory — US5 consults (the story that now lands second)

- **Ephemeral spawn machinery is every attempt**: `adapter_for`
  (`factory/workgraph/adapter.py:668`) + `run_attempt` (the protocol at
  `adapter.py:653`, the claude-CLI implementation at `adapter.py:816`)
  already dispatch,
  monitor, classify, and tear down a one-shot `claude -p`. A consult is
  `run_attempt` with no verification ladder behind it — the reply is the
  final message, classification is reply-or-not.
- **The judge is the persona precedent for one-request lifetimes — and for
  nothing else.** It was also read, on 2026-08-08, as the precedent for
  context-in-prompt over worktree access, and that half was **reversed by the
  operator on 2026-08-18**: a consult reads the asking node's worktree,
  read-only, live (FR-018). The judge is blinded to everything but a finished
  diff on purpose; a consult advises work in progress and needs to see it.
  Assembled context — message, spec, plan, asker identity — is still assembled;
  the worktree is added to it, not substituted for it.
- **The worktree the consult reads already has an address.** Node worktrees live
  at `.factory/worktrees/<epic>/<node>` (`factory/workgraph/worktree.py`, the
  same path the branch namespace mirrors), on this host, so the grant is a path
  and a mode — not a transport. Resolve it from the asker's node record rather
  than by string-building the path a second time.
- **`needs_worktree` in `personas.yaml` is not this.** It is a real field
  (`factory/config.py:103,203`, required at `:75`) meaning *provision this
  persona its own worktree from a base* — `architect` already carries
  `needs_worktree: true` with `write_scope: docs`. FR-018's grant is a
  read-only view of **someone else's** existing worktree. Reaching for the
  existing field because it has the right name is how this becomes a write.
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
- **Read-only is a grant, not an instruction** (FR-018). The finding
  `agent-edits-outside-its-worktree` stands at two occurrences of two, and both
  agents had been told to stay put — the cause is structural, since a node
  worktree is nested inside the operator's checkout and is therefore an ancestor
  of the agent's cwd. A consult pointed at another node's worktree is that same
  shape with a second agent in it. Enforce the bound where the process is
  configured, and test the refusal by observing a write that does not land, not
  by reading the prompt.
- **No consult recursion** (US5-S3): a consult's output is scanned for the
  marker only to refuse it — consults answer or decline, and a consult that
  wants help is a decline. Without this rule a consult chain is an unbounded
  spawn tree.
- **The memory bank is optional equipment** (FR-014): every consult test
  must pass with no bank configured — the factory must never require a
  Hindsight server to route a message.

## Structure

**Dispatch order is US1 → US5 → US2 → US3 → US4**, strictly serial, every edge a
merge-edge. The 2026-08-18 reorder moved consults from fourth to second; the
paragraphs below are written in that order and the story numbers are the spec's,
unchanged.

US1: grammar + routing + store + degradation + cap + sweep extension + threading
and the no-verdict guard (FR-003, FR-005, which moved here with the reorder) —
`workflow.py`, `store.py`, `agent_activities.py`, notify surfaces. US5:
`consult_activities.py` + the consult rung in routing + the worktree grant +
memory config. US2: the adapter's inbound direction and the prompt instructions
that go with it (`adapter.py`). US3: `peers.py` + mailbox transport + mirror +
registry refusals (`peer_activities.py`, one workflow seam for outbox sweep on
the expiry beat). US4: cross-epic signal + namespace completion + decision-log
and architecture-doc entries. No new dependency; no new store; no new clock.

US5 and US3 both insert a rung into the same routing ladder, which is why
nothing here runs beside anything else. At concurrency 1 that costs nothing.

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
plus a two-layer memory integration. The diff ceiling is 65,536 bytes, refused
deterministically — **raised from 61,440 on 2026-08-17**, so any 60 KiB figure
you have seen quoted for this repo is stale. Measure through `size_refusal`
(`factory/verify/diffbounds.py:113`), importing `DIFF_INPUT_LIMIT`
(`diffbounds.py:42`) rather than quoting it; that is exactly why the number
moved under this paragraph without breaking anything that imported it. **If a story does not fit whole, say where you would split it — do not trim
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

