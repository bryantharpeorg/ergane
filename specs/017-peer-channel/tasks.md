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
      (this spec's frontmatter edge); re-verify plan.md's reuse inventory —
      the `question_answered` signal and buffers
      (`factory/workgraph/workflow.py:472-566`), the ferry constants and
      callbacks (`factory/workgraph/adapter.py:108-203`,
      `factory/activities/agent_activities.py:73,453`), the questions DDL
      and guarded resolution (`factory/verify/store.py:136-163,609+`), and
      the bridge reply path (`factory/notify/service.py:198-297`). Decide
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
- [ ] T003 [P] [US1] Write addressee-grammar cases FIRST: addressee parsed
      from marker and ferry bodies; absent addressee routes the existing
      008 path with existing tests' meaning unchanged (assert against the
      008 fixtures, unedited); unknown addressee refuses to the asker;
      self-address refuses — must fail.
- [ ] T004 [P] [US1] Write routing cases FIRST with scripted children: peer
      with attempt in flight receives via ferry inbox within one poll
      interval; peer without an attempt receives via the dedicated prompt
      section on next dispatch verbatim; reply threads back by message id
      on both paths; terminal-target and expiry cases degrade to an
      operator question carrying the message body — must fail.
- [ ] T005 [P] [US1] Write cap and discipline cases FIRST: outstanding
      messages beyond the configured cap refuse with the cap named
      (SC-004's ping-pong terminates); message text is unreadable by gates
      and judge (extend 008's FR-010 guard test); the credential sweep
      asserts message bodies and stored rows; ledger rows unchanged by an
      exchange — must fail.
- [ ] T006 [P] [US1] Write store cases FIRST: `messages` table rows carry
      sender, addressee, body, reply, resolution, expiry; guarded
      resolution is first-wins against expiry (the `resolve_question`
      pattern); late replies stored and never read — must fail.

### Implementation for User Story 1

- [ ] T007 [US1] Implement the grammar, workflow buffers and routing, ferry
      inbox delivery, prompt section, degradation, cap, and store table
      until T003, T004, T005, T006 pass.

---

## Phase 3: User Story 2 — A message reaches a named external agent (Priority: P2)

**Goal**: operator-owned peer registry; mailbox transport; Telegram mirror;
outbox sweep on the existing expiry beat.

**Independent Test**: registry-named mailbox peer round trip — inbox file,
mirror, reply file to next prompt; expiry degrades to operator.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T008 [P] [US2] Write registry cases FIRST: `peers.yaml` parse with
      named findings (personas-loader style); transport values closed
      (`mailbox` today); namespace collision with node ids refused at
      load; unregistered addressee refuses as undeliverable — must fail.
- [ ] T009 [P] [US2] Write mailbox cases FIRST: one JSON file per message,
      atomic write, documented schema (id, sender, body, reply
      instructions); unwritable path refuses immediately to the asker;
      outbox reply reaches the asker by US1's paths; reply after expiry
      stored, never read; expiry degrades to operator question; every
      external send mirrors one Telegram notification with no reply key;
      sweep asserts mailbox files carry no credential values — must fail.

### Implementation for User Story 2

- [ ] T010 [US2] Implement `factory/notify/peers.py` and the mailbox
      transport + mirror in `factory/activities/peer_activities.py`, wire
      the outbox sweep into the expiry beat, until T008, T009 pass.

---

## Phase 4: User Story 3 — A message crosses epics, and the channel is documented (Priority: P3)

**Goal**: cross-epic delivery by external workflow signal; one addressee
namespace across nodes, registry names, and epics; decision log and docs.

**Independent Test**: two workflow instances with scripted children complete
a cross-epic round trip; absent sibling degrades; docs name the channel.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T011 [P] [US3] Write cross-epic cases FIRST: an epic-addressed message
      delivers as a signal to the sibling workflow, buffers incuriously,
      and reaches the target node by US1's rules; reply crosses back; a
      finished or absent sibling epic degrades to the operator (the client
      signal's failure caught in the activity, never the workflow) — must
      fail.

### Implementation for User Story 3

- [ ] T012 [US3] Implement cross-epic routing in
      `factory/activities/peer_activities.py` and the namespace completion
      until T011 passes.
- [ ] T013 [US3] Final sweep + docs: claim the decision-log numbers in
      `docs/decisions.md` (transport decision; FR-012-amendment extension —
      "park and route"); extend `docs/architecture.md` with the peer
      channel and registry; cross-reference the mailbox schema where the
      operator will look for it; confirm no new dependency and no new
      store.

---

## Phase 5: User Story 4 — A message with no live recipient spawns its answerer (Priority: P2)

**Goal**: the consult rung — ephemeral persona spawn, reply-or-degrade,
spend attributed, bounded; the two-layer memory split wired and optional.

**Independent Test**: scripted-adapter consult round trip with ledger
attribution; failure, decline, recursion, and bound cases all end at the
operator path or a refusal.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T014 [P] [US4] Write consult-spawn cases FIRST with a scripted
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
- [ ] T015 [P] [US4] Write memory-layer cases FIRST: with a bank endpoint
      configured, the consult's written MCP config names only the
      factory-owned bank (assert no other endpoint can appear — sweep
      style); with no endpoint configured, no MCP config is written and the
      consult runs and answers; the credential sweep covers the config
      file; consult behavior is identical under both except for the tool's
      presence — must fail.

### Implementation for User Story 4

- [ ] T016 [US4] Implement `factory/activities/consult_activities.py` and
      the consult rung in routing until T014, T015 pass.
- [ ] T017 [US4] Docs: record the consult decision and the two-layer memory
      split (§ Decision) alongside US3's claimed entries — coordinate the
      decision-log numbers with whichever of US3/US4 lands second — and add
      the consult runner to `docs/architecture.md`'s module table.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — including the mailbox
  root decision the registry entry needs and the memory-bank decision the
  consult runner reads.
- Phase 2 (US1) is the MVP seam: the address, the routing, and the floor.
- Phase 3 (US2) imports US1's routing and store — merged, not passed.
- Phase 4 (US3) imports both and completes the namespace — merged,
  sequential, carries the docs with Phase 5.
- Phase 5 (US4) imports only US1 — merged after it, parallel to Phases 3–4.

## Implementation Strategy

US1 alone already self-answers the question class that burned 006-us1: an
implementer can ask its architect instead of the operator's phone. US2 is
the operator's named want — the homelab peer — and rides entirely on US1's
semantics. US4 is the escalation vision completed: "ask the architect"
works with no architect running, the machine is always tried before the
human, and what the consults learn accrues in the factory's own memory
bank. US3 completes the topology when concurrency makes it real. The
operator path is the floor under every story: nothing in this spec can make
a question die unheard, because every failure branch lands on the channel
008 proved in production.
