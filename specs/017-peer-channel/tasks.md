# Tasks: Peer Channel

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm 008 is landed on the target's default branch
      (this spec's frontmatter edge); re-verify plan.md's reuse inventory.
      **Done 2026-08-18** — every anchor was stale and is now corrected in
      plan.md, because 041 moved the question lifecycle out of the epic
      workflow into a child `QuestionWorkflow`. Current anchors: the
      `question_answered` signal and its buffer
      (`factory/escalation/question.py:87,95,98`), the child start and park
      (`factory/workgraph/workflow.py:1320,1344`), the ferry constants
      (`factory/workgraph/adapter.py:148-217`) and callbacks
      (`factory/activities/notify_activities.py:918,942`, wired at
      `factory/activities/agent_activities.py:74,230,476`), the questions DDL
      and guarded resolution (`factory/verify/store.py:213,1183`), and
      the bridge reply path (`factory/notify/service.py:472,644`). Decide
      the mailbox root for the homelab peer (outside every repo working
      tree) and record it in the registry entry. For US4: provision the
      factory-owned Hindsight bank, verify a recall round trip against it,
      and record its endpoint in factory config — or record that the memory
      layer starts absent (FR-014 permits it). Correct the plan before
      deriving, not the nodes after.

---

## Phase 2: User Story 1 — A question reaches a peer agent in the same epic (Priority: P1) 🎯 MVP

**Goal**: addressee grammar over the 008 channel; workflow-routed peer
delivery both directions; degradation floor; message cap; store rows.

**Independent Test**: two scripted agents in one epic complete a
question/reply round trip with no Telegram send and no ladder cost.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; the plan's reuse-inventory refs exist — constitution I gate;
      STOP and report blocked if not satisfied.
- [ ] T003 [P] [US1] (spec US1-S1, US1-S2) Write addressee-grammar cases FIRST: addressee parsed
      from marker and ferry bodies; absent addressee routes the existing
      008 path with existing tests' meaning unchanged (assert against the
      008 fixtures, unedited); unknown addressee refuses to the asker;
      self-address refuses — must fail.
- [ ] T004 [P] [US1] (spec US1-S3, US1-S4) Write routing cases FIRST with scripted children: peer
      with attempt in flight receives via ferry inbox within one poll
      interval; peer without an attempt receives via the dedicated prompt
      section on next dispatch verbatim; reply threads back by message id
      on both paths; terminal-target and expiry cases degrade to an
      operator question carrying the message body — must fail.
- [ ] T005 [P] [US1] (spec US1-S5) Write cap and discipline cases FIRST: outstanding
      messages beyond the configured cap refuse with the cap named
      (SC-004's ping-pong terminates); message text is unreadable by gates
      and judge (extend 008's FR-010 guard test); the credential sweep
      asserts message bodies and stored rows; ledger rows unchanged by an
      exchange — must fail.
- [ ] T006 [P] [US1] (spec US1-S6) Write store cases FIRST: `messages` table rows carry
      sender, addressee, body, reply, resolution, expiry; guarded
      resolution is first-wins against expiry (the `resolve_question`
      pattern); late replies stored and never read — must fail.

### Implementation for User Story 1

- [ ] T007 [US1] Implement the grammar, workflow buffers and routing, ferry
      inbox delivery, prompt section, degradation, cap, and store table
      until T003, T004, T005, T006 pass.

---

## Phase 2b: User Story 2 — A message reaches an attempt that is already running (Priority: P1)

Added 2026-08-16. The 2026-08-08 refinement split the original US1 into US1
(routing, no adapter change) and US2 (live delivery, which needs a new adapter
direction the original story never named) — and renumbered the spec's stories
without giving US2 a phase here. `ergane spec validate` refused the whole spec
for it: *"node 'us2': tasks.md declares no phase naming user story US2, so this
node has no task slice to work"*. A node with no slice cannot be dispatched at
all, so this was a hard blocker, not a tidiness point.

**This is the story with the protocol change in it.** Today's ferry is a *pull*:
the adapter's answer poll only begins once the agent has itself written a
question file, so there is no path by which an unsolicited message reaches a
running attempt. US1 needs none of that — it lands the message in the target's
next assembled prompt. Do not let US1's shape mislead you into thinking this one
is more of the same.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007a [P] [US2] (spec US2-S1) Write the unsolicited-inbound case FIRST:
      with a scripted agent whose attempt is already in flight and which has
      asked nothing, a routed peer message is surfaced within one poll
      interval — must fail, because the pull-only ferry cannot do this today.
- [ ] T007b [P] [US2] (spec US2-S2) Write the reply-threading case FIRST: a
      running addressee writes a reply, it threads to the asker by message id,
      and **neither attempt terminates** — assert both attempts are still live
      after the exchange, not merely that the reply arrived.
- [ ] T007c [P] [US2] (spec US2-S3, FR-017) Write the attributed-advisory case
      FIRST: an external peer's reply surfaced mid attempt is presented as
      attributed advisory text naming its registry entry, verbatim in content
      and framed as an outside opinion — must fail.
- [ ] T007d [P] [US2] (spec US2-S4) Write the ignored-inbox case FIRST: an agent
      that never reads its inbox ends its attempt normally and the undelivered
      message degrades exactly as an expired one does. **Assert the node's
      attempt ceiling did not move** — a peer that ignores its inbox costs a
      message, never a node.

### Implementation for User Story 2

- [ ] T007e [US2] Add the inbound direction to the adapter: a way to deliver an
      unsolicited message to a live attempt and to read what it writes back,
      plus the prompt instructions that tell an agent to watch its inbox while
      it works. Implement until T007a–T007d pass and the existing ferry tests
      are unchanged — the pull path is not being replaced, it is being joined.

## Phase 3: User Story 3 — A message reaches a named external agent (Priority: P2)

**Goal**: operator-owned peer registry; mailbox transport; Telegram mirror;
outbox sweep on the existing expiry beat.

**Independent Test**: registry-named mailbox peer round trip — inbox file,
mirror, reply file to next prompt; expiry degrades to operator.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T008 [P] [US3] (spec US3-S1, US3-S2) Write registry cases FIRST: `peers.yaml` parse with
      named findings (personas-loader style); transport values closed
      (`mailbox` today); namespace collision with node ids refused at
      load; unregistered addressee refuses as undeliverable — must fail.
- [ ] T009 [P] [US3] (spec US3-S3, US3-S4) Write mailbox cases FIRST: one JSON file per message,
      atomic write, documented schema (id, sender, body, reply
      instructions); unwritable path refuses immediately to the asker;
      outbox reply reaches the asker by US1's paths; reply after expiry
      stored, never read; expiry degrades to operator question; every
      external send mirrors one Telegram notification with no reply key;
      sweep asserts mailbox files carry no credential values — must fail.

### Implementation for User Story 3

- [ ] T010 [US3] Implement `factory/notify/peers.py` and the mailbox
      transport + mirror in `factory/activities/peer_activities.py`, wire
      the outbox sweep into the expiry beat, until T008, T009 pass.

---

## Phase 4: User Story 4 — A message crosses epics, and the channel is documented (Priority: P3)

**Goal**: cross-epic delivery by external workflow signal; one addressee
namespace across nodes, registry names, and epics; decision log and docs.

**Independent Test**: two workflow instances with scripted children complete
a cross-epic round trip; absent sibling degrades; docs name the channel.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T011 [P] [US4] (spec US4-S1, US4-S2, US4-S3) Write cross-epic cases FIRST: an epic-addressed message
      delivers as a signal to the sibling workflow, buffers incuriously,
      and reaches the target node by US1's rules; reply crosses back; a
      finished or absent sibling epic degrades to the operator (the client
      signal's failure caught in the activity, never the workflow) — must
      fail.

### Implementation for User Story 4

- [ ] T012 [US4] Implement cross-epic routing in
      `factory/activities/peer_activities.py` and the namespace completion
      until T011 passes.
- [ ] T013 [US4] Final sweep + docs: claim the decision-log numbers in
      `docs/decisions.md` (transport decision; FR-012-amendment extension —
      "park and route"); extend `docs/architecture.md` with the peer
      channel and registry; cross-reference the mailbox schema where the
      operator will look for it; confirm no new dependency and no new
      store.

---

## Phase 5: User Story 5 — A message with no live recipient spawns its answerer (Priority: P1)

**This phase dispatches SECOND, immediately after US1** (reordered 2026-08-18).
Phase numbers are stable identifiers here, not a running order; the work graph
in spec.md is the dispatch truth and it reads US1 → US5 → US2 → US3 → US4.

**Goal**: the consult rung — ephemeral persona spawn, reply-or-degrade,
spend attributed, bounded; a read-only view of the asking node's worktree; the
two-layer memory split wired and optional.

**Independent Test**: scripted-adapter consult round trip with ledger
attribution; the consult reads uncommitted work in the asker's worktree and
cannot write to it; failure, decline, recursion, and bound cases all end at the
operator path or a refusal.

### Tests for User Story 5 (write FIRST, must fail)

- [ ] T014 [P] [US5] (spec US5-S1, US5-S2, US5-S3) Write consult-spawn cases FIRST with a scripted
      adapter: a persona-addressed message with no live attempt spawns
      exactly one consult with that persona's registry model and the
      assembled context (message, spec, plan, asker identity) in its
      prompt; the reply threads back by message id; a terminal-node
      addressee consults with the node's persona; failure, timeout, and
      decline each degrade to the operator question path; a consult output
      carrying a peer-addressed marker is refused; spawns beyond the
      configured bound refuse into the operator path; the consult's key is
      issued and torn down inside the spawn bracket and its spend lands in
      the ledger attributed to the asking node — must fail.
- [ ] T015 [P] [US5] (spec US5-S4, US5-S5) Write memory-layer cases FIRST: with a bank endpoint
      configured, the consult's written MCP config names only the
      factory-owned bank (assert no other endpoint can appear — sweep
      style); with no endpoint configured, no MCP config is written and the
      consult runs and answers; the credential sweep covers the config
      file; consult behavior is identical under both except for the tool's
      presence — must fail.

- [ ] T015a [P] [US5] (spec US5-S6, US5-S7, FR-018, SC-008) Write worktree-grant
      cases FIRST: with the asking node's worktree holding a file that is
      present in the working tree and absent from its branch, the consult's
      assembled context contains that file's content — proving the read could
      have come from nowhere else; a write attempted from the consult to that
      worktree and to a path above it both fail, and the worktree is
      byte-identical afterwards; the bound is enforced where the process is
      configured, so the refusal holds with the instruction removed from the
      prompt; an asker with no readable worktree (terminal node, swept tree,
      bare persona address) still gets an answer, and the reply says which
      context it had — must fail.

### Implementation for User Story 5

- [ ] T016 [US5] Implement `factory/activities/consult_activities.py` and
      the consult rung in routing until T014, T015 pass.
- [ ] T016a [US5] (FR-018) Implement the worktree grant until T015a passes:
      resolve the asker's worktree from its node record rather than
      re-deriving the path, mount it read-only for the consult, and refuse
      anything outside it. Do **not** reuse `personas.yaml`'s
      `needs_worktree` (`factory/config.py:103`) — that field provisions a
      persona its *own* worktree from a base and is a different capability
      with a larger blast radius (plan trap).
- [ ] T017 [US5] Docs: record the consult decision and the two-layer memory
      split (§ Decision) alongside US3's claimed entries — coordinate the
      decision-log numbers with whichever of US3/US4 lands second — and add
      the consult runner to `docs/architecture.md`'s module table.

---

## Closed gap: the already-running-attempt story now has a phase

**Resolved — kept because the failure mode is worth recognising again.** For
eight days this file's phases were numbered against the story list from *before*
the already-running-attempt story was inserted into the spec, so every phase
below Phase 2 carried the wrong story's number: the second node would have been
handed the third story's tasks, the third the fourth story's, the fourth the
fifth story's, and the fifth would have found no phase at all.

Three of those four fail **silently** — assembly succeeds and the agent works
the wrong slice, which is worse than a refusal because nothing reports it. Only
the missing phase produced an honest `ergane spec validate` refusal, and that
refusal is the only reason the other three were ever found. Phase 2b now exists
and the numbers are correct.

The same drift had reached the two narrative sections at the foot of this file,
which were still describing US2 as the homelab peer and consults as US4; both
were rewritten on 2026-08-18. **When a story is inserted, renumbered or
reordered, the prose is where the stale mapping hides** — the work graph and the
phase headings get checked, and paragraphs do not.

## Dependencies & Execution Order

Rewritten 2026-08-18 with the reorder. The list below had drifted a story out of
step with the phases — it described US2's work under Phase 3 and consults under
Phase 5 as "US4" — which is the same silent failure the note above this section
was written about. Every edge is a merge-edge.

- **Phase 1** is operator work and gates everything — including the mailbox
  root decision the registry entry needs and the memory-bank decision the
  consult runner reads.
- **Phase 2 (US1)** is the MVP seam: the address, the routing, the store, the
  floor, threading, and the no-verdict guard. Dispatches first.
- **Phase 5 (US5)** dispatches second: consults, the worktree grant, memory.
  Imports US1's routing and store — merged, not passed. This is the story that
  makes the channel useful at a concurrency of 1.
- **Phase 2b (US2)** dispatches third: the adapter's inbound direction.
- **Phase 3 (US3)** dispatches fourth: the registry and mailbox transport. It
  inserts a rung into the same routing ladder US5 touched, which is why it
  waits rather than running beside it.
- **Phase 4 (US4)** dispatches last: cross-epic routing and the closing docs.

## Implementation Strategy

Rewritten 2026-08-18: the previous version named the wrong stories throughout,
crediting the homelab peer to US2 and consults to US4.

US1 lands the address, the routing and the floor. On its own it self-answers
the question class that burned 006-us1 — but slowly, because at a concurrency
of 1 the peer being asked is almost never running, so each exchange costs a
dispatch. **US5 is what makes that fast**, and it is the escalation vision
itself: "ask the architect" works with no architect running, the architect can
read what the implementer has actually written rather than what the plan said,
and the machine is always tried before the human. US2 makes the conversation
live rather than turn-based. US3 is the operator's named want, the homelab
peer. US4 completes the topology when concurrency makes it real.

The operator path is the floor under every story: nothing in this spec can make
a question die unheard, because every failure branch lands on the channel
008 proved in production.
