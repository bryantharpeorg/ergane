# Tasks: Peer Channel

Read `plan.md` before starting, and read its § "Read this before anything else"
first: this spec is held for a runtime failure no scripted test observes, and
several of the traps below exist because the obvious implementation passes the
whole suite while the feature is dead. Read § "The worktree grant already half
exists" before writing anything for US5, and Trap 4 before writing anything for
US7 — both name a check that is green before you start.

**Phases are numbered in story order; dispatch order is US1 → US6 → US9 → US7 →
US5 → US8 → US2 → US3 → US4**, every edge a merge-edge. The Work Graph in
`spec.md` is the dispatch truth. Phase numbers are stable identifiers here, not a
running order — US8's phase is 9 and US9's is 10, at the end of this file.

**No verification task pastes a whole assembled prompt.** `prompt.py` carries the
whole of `plan.md` into every prompt verbatim — over 45 KiB of it — and the
refusal threshold over the assembled diff is 65,536
(`factory/verify/diffbounds.py:66`), so one pasted prompt is larger than any
story's headroom here. Paste the section under discussion and the lines around
it. That is plan.md trap 22.

Tests are written first and must fail before the implementation that satisfies
them. A task that finds its test already passing has found a defect in the test,
not a task it may skip. Every acceptance scenario is provable from the diff,
which is all the judge sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm all six of 008, 009, 041, 079, 101 and 126 are
      landed on the target's default branch — that list is this spec's
      `depends_on_landed` in full, and an earlier edition of this task omitted
      009 — and re-verify
      the plan's anchors before deriving — Trap 4's grep in particular, since its
      output is a fact about one sha. Decide the mailbox root for the homelab
      peer: outside every repository working tree, and inside the tree
      `tests/test_workgraph_sweep.py:410` —
      `test_no_byte_a_real_attempt_persists_carries_either_credential` walks, or
      FR-020 is unassertable. Decide whether the factory-owned Hindsight bank
      exists — provision it and verify a recall round trip, or record that the
      memory layer starts absent, which FR-014 permits. **The sizing decision is
      already taken and is not yours to defer**: the earlier edition of this task
      asked for a measurement of code that does not exist yet, which nobody can
      perform, so 2026-09-04 took the only measurement available — the killed
      attempt `3c04efd`, a floor rather than a size — and split twice on it. US9
      carries FR-005 and FR-006 out of US6; US8 carries FR-018 out of US5. Read
      plan.md § Sizing for what each story now touches, and re-open the question
      only if a *landed* story here comes back larger than its paragraph says.

## Phase 2: User Story 1 — A question names its recipient, and every message is on the record

**Goal**: the addressee grammar over 008's two doors, and the `messages` table.
No interpreter file is touched by this story.

**Independent Test**: parse one transcript body twice, with and without the
addressee line; write a message row and a reply row and read them back.

### Tests for this story (write FIRST, must fail)

- [ ] T002 [P] [US1] (spec US1-S1, FR-001, trap 6) Given a final message whose
      `## OPERATOR QUESTION` body opens with an addressee line, assert
      `detect_operator_question` (`factory/verify/question.py:85`) returns a
      marker carrying the addressee and a body with the addressee line removed.
- [ ] T003 [P] [US1] (spec US1-S2, FR-001) Given a ferry question file whose body
      opens with the same addressee line, assert the ferry read yields the same
      addressee and the same body — one grammar, one parser, two call sites.
- [ ] T004 [P] [US1] (spec US1-S3, FR-001, trap 6) **The control, and it is
      differential.** Given one transcript body used twice inside a single test —
      once with the addressee line, once without — assert the addressed read
      yields an addressee and the unaddressed read yields a marker byte-identical
      to today's, checked against the 008 fixtures with no edit to them. A diff
      that only added a field cannot pass this pair.
- [ ] T005 [P] [US1] (spec US1-S4, FR-001) Given an addressee line that is present
      but empty, or malformed, assert no addressee is returned, the body is left
      whole, and the body still contains the line so the operator can see what the
      agent meant.
- [ ] T006 [P] [US1] (spec US1-S5, FR-008) Given a message row and a reply row
      written through the store, assert the row carries sender epic, node, attempt
      and persona, the addressee, the body, the reply, the resolution and the
      expiry; then resolve the same message id twice and assert the second call
      returns false, the first-wins arbiter
      `factory/verify/store.py:1808` — `resolve_question` applies to questions.
- [ ] T007 [P] [US1] (spec US1-S6, FR-007, trap 21) Extend the driven run inside
      `tests/test_verification_sweep.py:418` —
      `test_no_byte_this_component_persists_carries_either_credential` so that
      run writes a message body and resolves a message row carrying the canary
      credential, and assert the sweep fails on an unscrubbed store. There is no
      surface list to append to: the sweep walks
      `component.workspace.rglob("*")`, so a message the run never wrote is a
      surface it never searches, and that is what makes this test unable to pass
      on a sweep that was left alone.

### Implementation for this story

- [ ] T008 [US1] Implement the optional addressee line in the marker and ferry
      grammar and the `messages` table until T002–T007 pass. Parse the addressee
      as an optional first line and short-circuit to the existing code path when
      it is absent (trap 6) — do not route the absent case through a new function
      that handles it as one of several branches. Model the table on the questions
      DDL at `factory/verify/store.py:310` and reuse the guarded-resolution shape
      rather than forking it. Add the table to **both** copies of the schema:
      `_SCHEMA_DDL` (`factory/verify/store.py:201` says it is verbatim from the
      contract) and
      `specs/002-verification-gating/contracts/verification-store.sql`, which
      `tests/test_verify_store.py:92` loads and compares column by column — 126-US3
      edited both in one commit and so does this.

### Verification for this story

- [ ] T009 [US1] Paste, as committed evidence, the two parses of the same
      transcript body from T004 side by side — addressed and unaddressed — and the
      sweep output from T007 failing before the message write was driven and
      passing after.

## Phase 3: User Story 2 — A message reaches an attempt that is already running

**Goal**: the adapter's inbound direction — a push beside the existing pull — and
the prompt instructions that go with it.

**Independent Test**: two scripted agents whose attempts overlap in the test's own
timeline exchange an unsolicited message and a reply without either ending.

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1, FR-019, trap 8, trap 9) Given an addressee with
      an attempt in flight that has asked nothing — `state.question_id` unset —
      assert one ferry beat surfaces the routed message into the file the agent
      polls. This must fail today: the answer poll is guarded at
      `factory/workgraph/adapter.py:1440`. Do not relax that guard to make it
      pass; add a second, independent inbound path beside it.
- [ ] T011 [P] [US2] (spec US2-S2, FR-019) Given a running addressee handed a
      message, when it writes a reply into the ferry, assert the reply threads to
      the asker by message id **and that both attempt records are still live
      afterwards** — assert on the records, not on the absence of an exception.
- [ ] T012 [P] [US2] (spec US2-S3, FR-004, FR-019) Given an agent that never reads
      its inbox, when its attempt ends normally, assert the undelivered message
      degrades exactly as an expired one does and the node's attempt ceiling is
      unmoved.
- [ ] T013 [P] [US2] (spec US2-S4, FR-019) Given an attempt with an inbox and one
      without, assert the inbox instruction text is present in the first assembled
      prompt and absent from the second — the instruction is a fact about the
      attempt, not a paragraph pasted into every prompt.
- [ ] T014 [P] [US2] (FR-019, trap 8) Assert the existing ferry tests still pass
      unchanged and that an attempt which asks nothing and receives nothing polls
      no inbound file — the pull path is being joined, not replaced.

### Implementation for this story

- [ ] T015 [US2] Add the inbound direction to
      `factory/workgraph/adapter.py:222` — `_FerryState` and
      `factory/workgraph/adapter.py:1400` — `_ferry_once`, with its own file name
      beside `factory/workgraph/adapter.py:187`, its own state flag, and its own
      activity-side callback wired the way
      `factory/activities/notify_activities.py:958` — `ferry_send_question` is
      wired at `factory/activities/agent_activities.py:537`. Add the prompt
      instructions. Implement until T010–T014 pass.

### Verification for this story

- [ ] T016 [US2] Paste, as committed evidence, the two attempts' lifecycle
      timestamps from the overlapping-attempt test showing the message was
      delivered while both were running, and — from T013 — the inbox-instruction
      paragraph with the twenty lines around it from the prompt that has one,
      beside the same span from the prompt that does not. Not the two prompts
      whole: each carries the entire `plan.md` verbatim (trap 22).

## Phase 4: User Story 3 — A message reaches a named external agent

**Goal**: the operator-owned peer registry, the mailbox transport, the mirror,
the outbox sweep, and the attributed-advisory framing an outside reply arrives in.

**Independent Test**: a registry-named mailbox peer round trip — inbox file,
mirror, reply file to the next prompt; expiry degrades to the operator.

### Tests for this story (write FIRST, must fail)

- [ ] T017 [P] [US3] (spec US3-S1, FR-009, FR-010, trap 15) Given a message to a
      registered mailbox peer, assert exactly one file appears in the inbox
      carrying id, sender epic/node/persona, body and reply instructions, written
      by atomic rename, and that one mirror notification was sent with no reply
      key on it.
- [ ] T018 [P] [US3] (spec US3-S2, FR-009) Given a reply file in the outbox naming
      an open message id, assert the sweep beat delivers it to the asking node by
      US6's paths and records the exchange in the store.
- [ ] T019 [P] [US3] (spec US3-S3, FR-017, trap 15) Given an external reply
      reaching an asking agent, assert the prompt section names the registry entry
      it came from and frames it as an outside opinion, **and** that the reply
      bytes inside that frame are unchanged. Assert both halves in one test so
      neither can be dropped for the other.
- [ ] T020 [P] [US3] (spec US3-S4, FR-004) Given an external message unanswered at
      its registry expiry, assert it degrades to the operator question path, then
      write a late reply and assert it is stored and never read from the asker's
      next prompt.
- [ ] T021 [P] [US3] (spec US3-S5, FR-004, FR-009, trap 15) Given a name in no
      registry, and separately a registry entry whose mailbox path cannot be
      written, assert each is refused to the asker as undeliverable — named and
      immediate — with the attempt ceiling unmoved and no retry inside routing.
- [ ] T022 [P] [US3] (spec US3-S6, FR-009) Given a malformed registry entry, and
      separately one whose peer name collides with a node id or a persona name,
      assert loading refuses with a named finding in the style
      `factory/config.py:314-315` uses for `personas.yaml` — the guard and the
      `raise fail(...)` that names the offending field.
- [ ] T023 [P] [US3] (spec US3-S7, FR-020, trap 15, trap 21) Extend the driven run
      inside `tests/test_workgraph_sweep.py:410` —
      `test_no_byte_a_real_attempt_persists_carries_either_credential` so the
      attempt it runs sends one external message, and assert the sweep fails on a
      mailbox file or a mirror notification carrying the canary credential. Assert
      the mailbox root the test configures is inside the tree that sweep walks: a
      mailbox written outside it is a surface the sweep cannot see, and the
      assertion would then be about nothing.

### Implementation for this story

- [ ] T024 [US3] Implement `factory/notify/peers.py` — the registry parse, its
      closed transport vocabulary and its named findings — until T022 passes.
- [ ] T025 [US3] Implement the mailbox transport, the mirror and the outbox sweep
      in `factory/activities/peer_activities.py`, hanging the sweep off the
      existing expiry cadence rather than a wall clock read inside workflow code,
      and the attributed-advisory prompt section, until T017–T021 and T023 pass.

### Verification for this story

- [ ] T026 [US3] Paste, as committed evidence, one inbox file exactly as written,
      the mirror notification text, and the external-reply section of the asker's
      next assembled prompt — that section and its surrounding lines, not the
      prompt whole (trap 22) — showing the reply framed and attributed with its
      bytes unchanged.

## Phase 5: User Story 4 — A message crosses epics, and the channel is documented

**Goal**: cross-epic delivery by external workflow signal; one addressee
namespace across nodes, personas, registry names and epics; the decision log and
the architecture document.

**Independent Test**: two workflow instances with scripted children complete a
cross-epic round trip; an absent sibling degrades; the documents name the channel.

### Tests for this story (write FIRST, must fail)

- [ ] T027 [P] [US4] (spec US4-S1, FR-011, trap 7) Given a message addressed to a
      node in a named sibling epic, assert the sibling workflow receives it as a
      signal, buffers it without validating against state it may not have written
      yet, and delivers it to the target node by US6's rules.
- [ ] T028 [P] [US4] (spec US4-S2, FR-004, FR-011, trap 16) Given a sibling epic
      that is not running or never answers, assert US6's degradation applies
      unchanged and that the client signal's failure was caught in the activity
      rather than raised into the workflow.
- [ ] T029 [P] [US4] (FR-009, FR-011) Assert the one addressee namespace refuses a
      collision between an epic id, a node id, a persona name and a registry name
      at load, whichever pair collides.

### Implementation for this story

- [ ] T030 [US4] Implement cross-epic routing in
      `factory/activities/peer_activities.py` and the namespace completion until
      T027–T029 pass.
- [ ] T031 [US4] (spec US4-S3, FR-012) Claim the decision-log numbers in
      `docs/decisions.md` — the transport decision and the FR-012-amendment
      extension to "park and route" — and extend `docs/architecture.md` with the
      peer channel, its registry and the consult runner. US4 lands last in this
      spec and no other story here claims a decision-log number, so take the next
      free ones at landing time, per the 006/008 precedent the spec cites.

### Verification for this story

- [ ] T032 [US4] Paste, as committed evidence, the signal and reply events from
      the cross-epic round trip's two workflow histories — the events, not the
      whole histories — showing the signal buffered and the reply returned, and
      the refusal produced when the sibling epic is gone.

## Phase 6: User Story 5 — A message with no live recipient spawns its answerer

**Goal**: the consult rung — an ephemeral persona spawn, reply-or-degrade, spend
metered under its own alias, spawns limited; the two-layer memory split wired and
optional. **No sandbox grant** — the invocation is built here and typed in US8.

**Independent Test**: a scripted-adapter consult round trip with ledger
attribution; failure, decline, recursion and limit cases all end at the operator
path or a refusal; an asker with no readable worktree still gets an answer.

### Tests for this story (write FIRST, must fail)

- [ ] T033 [P] [US5] (spec US5-S1, FR-013) Given a message addressed to a persona
      with no live attempt, and separately to a node whose attempts are terminal,
      assert exactly one consult spawns with that persona's registry model, its
      reply threads back by message id, and its process, key and assembled context
      are discarded after the reply.
- [ ] T034 [P] [US5] (spec US5-S2, FR-004, FR-013) Given a consult that fails,
      one that times out and one that declines, assert all three degrade to the
      008 operator question path — the rung sits above the floor, never replaces
      it.
- [ ] T035 [P] [US5] (spec US5-S3, FR-013, trap 17) Given a consult whose output
      carries a peer-addressed marker, assert the marker is refused and the
      message is treated as a decline.
- [ ] T036 [P] [US5] (spec US5-S4, FR-014, FR-021, trap 18, trap 21) Four parts,
      one test. Given a factory bank named in operator-owned configuration, assert
      the written config names that bank. Given operator configuration naming a
      second endpoint, assert the writer refuses and **no config file is written
      at all** — that refusal is what makes "no other endpoint can appear in it"
      an assertion rather than a hope, since a test that reads back the one config
      it just wrote leaves the negative unasserted. Given no bank configured,
      assert no config file is written and the consult still answers from
      assembled context. And extend the driven run inside
      `tests/test_workgraph_sweep.py:410` so the attempt it runs writes a consult
      config, asserting the sweep fails on a credential in it.
- [ ] T037 [P] [US5] (spec US5-S5, FR-015, trap 13) Given consult spawns standing
      at the configured limit, assert one more is refused, the message degrades to
      the operator, and the refusal names the configuration field and its value.
      Name the field the way `max_concurrent_nodes` is named — `cap`, `budget` and
      `quota` are refused under `factory/` by
      `tests/test_final_sweep.py:471`.
- [ ] T039 [P] [US5] (spec US5-S7, FR-013) Given an asker with no readable
      worktree — terminal node, swept tree, or a bare persona address — assert the
      consult still answers from assembled context and that its reply names which
      context it had. This is the no-grant path and it belongs here rather than in
      US8: a consult must answer without a worktree at all.
- [ ] T040 [P] [US5] (spec US5-S6, FR-015, trap 12) Given two consults answering
      two messages from the same node, attempt and persona, assert the ledger
      holds two rows with two distinct key aliases and that the asker's own
      attempt row is intact. The alias column at `factory/usage/ledger.py:69` is
      `UNIQUE`, so an alias built the way an attempt's is built collapses them.
- [ ] T041 [P] [US5] (FR-015, trap 12) Assert a consult's `Termination` value is
      admitted by the live ledger, exercising a store created before this story's
      DDL change so `factory/usage/ledger.py:188` — `_widen_terminations` is the
      thing that makes it pass.

### Implementation for this story

- [ ] T042 [US5] Implement `factory/activities/consult_activities.py` — context
      assembly, spawn bracket, reply extraction, recursion refusal and the spawn
      limit — plus the consult rung in the routing ladder US6 landed, until T033,
      T034, T035, T037 and T039 pass. Leave the invocation's read grant to US8:
      this story builds the invocation, US8 types what it carries.
- [ ] T044 [US5] (FR-014, FR-015, FR-021) Implement the per-consult MCP config
      write, its second-endpoint refusal and the ledger metering until T036, T040
      and T041 pass, extending the DDL's termination vocabulary in `_SCHEMA_DDL`
      rather than only the enum.

### Verification for this story

- [ ] T045 [US5] Paste, as committed evidence: the two ledger rows from T040 with
      their distinct key aliases beside the asker's own attempt row, and the
      refusal produced when operator configuration names a second memory endpoint
      (T036), showing that no configuration file was written.

## Phase 7: User Story 6 — A message reaches a peer that is not running, and the reply comes back

**Goal**: the `MessageWorkflow` child, workflow-state routing and buffers, the
next-prompt delivery section, reply threading and the degradation floor. **No
park** — that is US7 — and **no limit and no guard**, which are US9.

**Independent Test**: two scripted nodes in one epic — one addresses the other,
the addressee's next assembled prompt carries the message under its own section,
the reply reaches the asker's next assembled prompt verbatim, no operator
notification is sent, and both attempt ceilings are unmoved.

### Tests for this story (write FIRST, must fail)

- [ ] T046 [P] [US6] (spec US6-S1, FR-002, FR-003) Given a peer message addressed
      to a node with no attempt in flight and attempts remaining, assert that
      node's next assembled prompt carries the message verbatim under a section
      distinct from the one `factory/workgraph/prompt.py:814` — `_answer_section`
      writes, and that the reply threads back to the asker by message id.
- [ ] T051 [P] [US6] (spec US6-S2, FR-004) Given a message addressed to a terminal
      node, to the sender itself, to a name in no namespace, and one unanswered at
      its expiry — with no consult available — assert each degrades to the operator
      question path carrying the message body and that the asker's attempt ceiling
      is unmoved.
- [ ] T054 [P] [US6] (FR-002, trap 7) Assert the message signal handler only
      buffers — no routing, no state mutation beyond the append — the discipline
      `factory/escalation/question.py:101` — `question_answered` holds.

### Implementation for this story

- [ ] T055 [US6] Add `factory/escalation/message.py` — a `MessageWorkflow` child
      modelled on `factory/escalation/question.py:90` — `QuestionWorkflow`, owning
      one message's signal, window and row (trap 5) — and register it in
      `factory/worker.py` beside the existing children. Do **not** build per-node
      buffers, timers or expiry loops inside the epic workflow: 041-US3 took that
      shape out for this spec's own reason.
- [ ] T057 [US6] (FR-002, FR-003, FR-004, trap 20) Add workflow-state routing and
      buffers, the peer-message prompt section beside
      `factory/workgraph/prompt.py:146` — `OperatorAnswer`, reply threading and
      the degradation floor through
      `factory/activities/notify_activities.py:803` — `send_question`, until T046,
      T051 and T054 pass. Do **not** add a park: `factory/workgraph/workflow.py:2006`
      is US7's block. Do **not** add the outstanding-message limit or the
      no-verdict guard: they are US9's, and taking either here undoes the split
      this story's size depends on.

### Verification for this story

- [ ] T059 [US6] Paste, as committed evidence, the peer-message section of the
      addressee's assembled prompt — that section and the twenty lines around it,
      never the prompt whole (trap 22) — beside the message as the asker wrote it,
      so the verbatim claim is checkable byte for byte, and the asker's own next
      prompt showing the threaded reply.

## Phase 8: User Story 7 — An asker waits for its reply without stopping the epic

**Goal**: the peer park — a distinct node state that raises no pause, holds
neither concurrency slot, clears no pause it did not set, wakes the scheduler on
a message, and is classified deliberately at every site that reads the park.

**Independent Test**: two scripted nodes in one epic with `max_concurrent_nodes`
and `max_concurrent_subscription_nodes` both at 1 **and both nodes routed to a
subscription persona** — one addresses the other, the addressee is dispatched
**while the asker is parked**, the reply reaches the asker verbatim, no operator
notification is sent, and both attempt ceilings are unmoved.

### Tests for this story (write FIRST, must fail)

- [ ] T047 [US7] (spec US7-S1, FR-016, trap 1) **Set `max_concurrent_nodes` to 1,
      set `max_concurrent_subscription_nodes` to 1, and route both scripted nodes
      to a persona whose `agent` is `subscription`.** Given an asker parked
      awaiting a peer reply, assert the addressee is dispatched, the pause flag is
      unset and the epic state is still running. All three conditions are
      load-bearing. Above 1 on either limit the test passes whether or not the
      park released its slot; and with the nodes on the default persona the
      subscription branch is never entered at all —
      `factory/workgraph/workflow.py:1413` — `_is_subscription_node` reads the
      node's own persona and the shipped `implementer` is `agent: claude-code`
      (`personas.yaml:270`), so the assertion about
      `factory/workgraph/workflow.py:1102` would be about a branch that never
      runs. Install the registry the way
      `tests/test_subscription_accounting.py:242` — `test_subscription_concurrency_is_bounded_by_declared_limit`
      does: monkeypatch `load_personas` to return
      `tests/test_subscription_accounting.py:73`'s registry, whose persona is
      defined at `tests/test_subscription_accounting.py:63`, and build the nodes
      with `tests/test_subscription_accounting.py:79` — `_subscription_nodes`.
- [ ] T048 [US7] (spec US7-S2, FR-016, trap 2) Given an asker parked awaiting a
      peer reply and **no other node finishing**, assert the addressee is
      dispatched without waiting for an unrelated task to complete. A timeout on
      the scheduler's wait converts the deadlock into a delay and passes this test
      in a time-skipping environment — assert on the absence of a timer, or drive
      the test with no clock to skip.
- [ ] T049 [P] [US7] (spec US7-S3, FR-016, trap 3) Given an epic paused by an
      operator's press, when a peer-parked node in it un-parks, assert the pause is
      still set. `factory/workgraph/workflow.py:2072` is the unconditional clear
      this must not copy.
- [ ] T050 [P] [US7] (spec US7-S4, FR-016, trap 4) Given a node parked on a peer
      message, assert it is not reported as awaiting the operator (the derivation
      at `factory/workgraph/workflow.py:903`), its dependents are still PENDING
      rather than KILLED (`factory/workgraph/workflow.py:300` is the set that
      decides it), `factory/workgraph/workflow.py:1572` — `_drain_in_flight`
      does not wait on it, and a merge-gated dependent's edge is not read as dead
      by `factory/workgraph/workflow.py:1522` — `_dead_edge`, whose `continue` at
      `factory/workgraph/workflow.py:1534` is keyed on `_PARKED` and not on this
      state.
- [ ] T062 [P] [US7] (spec US7-S5, FR-016, trap 4) Given a kill arriving while a
      node is parked on a peer message, assert the peer park is matched by a
      branch of its own in
      `factory/workgraph/workflow.py:1715` — `_run_node`, that the node's record
      ends KILLED, and that its pending peer message is resolved as undelivered
      with no wait outstanding on it. Assert on the message's resolution, not only
      on the node's state: `factory/workgraph/workflow.py:2381` matches the
      question park and the `else` below it closes the node out KILLED, so the
      fall-through produces the right-looking state with a coroutine still parked
      behind it, and only the message row tells the two apart.
- [ ] T063 [P] [US7] (spec US7-S6, FR-016, trap 19) Given a peer-parked node whose
      close-out runs, assert its remote branch was **not** archived and cleared.
      `factory/workgraph/workflow.py:3087` — `_close_out` gates that destructive
      act on `factory/workgraph/workflow.py:3137`'s `if state is not _PARKED:`,
      an identity check against one state, so this test fails on any peer-park
      state the guard was not taught about.

### Implementation for this story

- [ ] T056 [US7] (FR-016, traps 1–4 and 19) Add the peer park. Start the child
      from the seam at `factory/workgraph/workflow.py:1980`, mirror the park block
      at `factory/workgraph/workflow.py:2006` and **omit**
      `factory/workgraph/workflow.py:2008`; add one `NodeState` member beside
      `factory/workgraph/models.py:155`; release **both** slots the parked task
      holds — the general fill limit at `factory/workgraph/workflow.py:1089` and
      the subscription limit at `factory/workgraph/workflow.py:1102`; give the
      wait predicate at `factory/workgraph/workflow.py:1137` a term that a
      buffered message sets; and classify the new state deliberately at every site
      Trap 4's grep returns, re-run at your own sha. At 602a92c the decisions are
      `factory/workgraph/workflow.py:300`, `factory/workgraph/workflow.py:313`,
      `factory/workgraph/workflow.py:903`, `factory/workgraph/workflow.py:1534`,
      `factory/workgraph/workflow.py:1606`, `factory/workgraph/workflow.py:2381`
      and `factory/workgraph/workflow.py:3137`. Show the grep's output accounted
      for in the diff. Implement until T047–T050, T062 and T063 pass.

### Verification for this story

- [ ] T058 [US7] Paste, as committed evidence, the epic's node-state timeline from
      the both-limits-at-1 test showing the asker parked and the addressee
      dispatched *while it was parked*, with the pause flag unset throughout.
- [ ] T064 [US7] Paste, as committed evidence, the remote branch listing before
      and after a peer-parked node's close-out, showing the node's ref still
      present — the 126 guard at `factory/workgraph/workflow.py:3137` proved to
      have been taught about this state rather than assumed to cover it.

## Phase 9: User Story 8 — The consult's read of the asker's worktree is declared, not inherited

**Goal**: a typed read grant on the invocation and one `--ro-bind` in the sandbox
argv, asserted against a control invocation that carries none. Split out of US5
on 2026-09-04: everything here is in `factory/workgraph/adapter.py` except the one
call site in US5's launcher that sets the field.

**Independent Test**: build the argv twice from the same launcher — granted and
ungranted — and compare; derive the granted path from the asker's node record;
then, on a host with the sandbox binary, watch a real write fail.

### Tests for this story (write FIRST, must fail)

- [ ] T038 [P] [US8] (spec US8-S1, FR-018, trap 10, trap 11) **The differential,
      and it is the whole story's evidence.** Build the sandbox argv from a
      consult invocation carrying the asker's worktree as its declared read grant
      and assert exactly one `--ro-bind` whose source and destination are that
      worktree path, no `--bind` naming it, and the ordering
      `factory/verify/gates.py:150` — `ordered_binds` imposes. Then build the argv
      again from an invocation with the grant field unset and assert **no** bind
      names that worktree. Read plan.md § "The worktree grant already half exists"
      first: `factory/workgraph/adapter.py:538` already binds the runtime root
      read-only above every worktree, so a test that merely reads the asker's
      files passes on a production diff that adds nothing, and only this pair
      fails on it.
- [ ] T066 [P] [US8] (spec US8-S2, FR-018) Assert the grant field holds exactly
      the path `factory/workgraph/worktree.py:289` — `worktree_path` derives for
      the asker's node record, by comparing against that function's own return
      value rather than against a literal — one derivation, one grant. A second
      string-built path is the defect this pins: it agrees with the first one
      until the layout changes, and then binds a directory that is not there.
- [ ] T065 [P] [US8] (spec US8-S3, FR-018, trap 10) Given a host that has the
      sandbox binary, launch a consult for real against the asker's worktree and
      assert a write into that worktree and into a path above it both fail with
      the tree's checksum unchanged, **with the don't-write instruction removed
      from the prompt**. Guard it the way `tests/test_us5_gates.py:44` guards its
      own — `BWRAP_PRESENT` — and declare the skip reason in the guard, because a
      host without the binary proves nothing here and T038 is the assertion that
      holds everywhere.

### Implementation for this story

- [ ] T043 [US8] (FR-018, trap 10) Implement the declared worktree grant until
      T038, T066 and T065 pass: add an extra-bind field to
      `factory/workgraph/adapter.py:293` — `AgentInvocation`, resolve the asker's
      worktree from its node record via
      `factory/workgraph/worktree.py:289` — `worktree_path` rather than
      re-deriving the path, emit one `--ro-bind` tuple in
      `factory/workgraph/adapter.py:464` — `_build_argv` beside the pair at
      `factory/workgraph/adapter.py:523`, and set the field at the consult call
      site US5 landed. Do **not** touch the runtime-root bind at
      `factory/workgraph/adapter.py:538`: it is on the path every attempt takes,
      narrowing it is a different spec, and FR-018 asks only that the declared
      grant add exactly one path. Do **not** reuse `personas.yaml`'s
      `needs_worktree` (`factory/config.py:188`) — it provisions a persona its
      *own* worktree from a base and is a different capability with a larger blast
      radius. Do not smuggle the path through `env`: a string convention is
      exactly what T038's control invocation cannot tell from a typed grant.

### Verification for this story

- [ ] T067 [US8] Paste, as committed evidence: both argv listings from T038 — the
      granted invocation showing exactly one `--ro-bind` naming the asker's
      worktree and no `--bind` naming it, and the control invocation showing none
      — and the failed write's error from T065 with the worktree's checksum before
      and after. Two argv listings and one error: no prompt, no transcript.

## Phase 10: User Story 9 — An exchange is bounded, and its text reaches no verdict

**Goal**: the outstanding-message limit with a refusal that names its
configuration field, and the no-verdict guard extended rather than forked. Split
out of US6 on 2026-09-04 because US6's only measurement is a killed attempt and
therefore a floor.

**Independent Test**: a two-node exchange that would not otherwise converge
terminates at the limit with both nodes proceeding; the workflow's read set off
an attempt still admits no message text.

### Tests for this story (write FIRST, must fail)

- [ ] T052 [P] [US9] (spec US9-S1, FR-006, trap 13) Given a node whose outstanding
      peer messages stand at the configured limit, assert the next send is refused
      to the asker with the refusal naming the configuration field and its value;
      then drive a two-node exchange that would not otherwise converge and assert
      it terminates at the limit with both nodes proceeding. Name the field the
      way `max_concurrent_nodes` is named — `cap`, `budget` and `quota` are
      refused under `factory/` by `tests/test_final_sweep.py:471`.
- [ ] T053 [P] [US9] (spec US9-S2, FR-005) Given a message and a reply carried
      through an exchange, assert neither the gates nor the judge can read the
      message text, extending 008's own guard rather than forking it. The guard is
      two committed tests and both are named:
      `tests/test_interpreter.py:3591` — `test_a_marker_never_produces_a_pass_from_its_presence`
      holds that an agent-authored marker parks and never grades, and
      `tests/test_workgraph_sweep.py:1168` — `test_the_workflow_reads_nothing_off_an_attempt_but_its_termination`
      pins the workflow's read set off an attempt result. Extend those; a new
      guard of your own leaves the old ones passing on a hole they were written to
      close.

### Implementation for this story

- [ ] T068 [US9] (FR-005, FR-006, trap 13) Implement the outstanding-message limit
      and the no-verdict guard on the routing seam US6 landed, until T052 and T053
      pass. Word the refusal the way the scheduler words its own at
      `factory/workgraph/workflow.py:970` — the field's name and the value it was
      given — but hand it back to the **asker**: that one raises
      `ApplicationError` and fails the epic, and a message over its limit must
      cost a message and never a node (FR-004). Message text reaches the store and
      the prompt and nothing else.

### Verification for this story

- [ ] T069 [US9] Paste, as committed evidence, the refusal text produced at the
      outstanding-message limit — naming the configuration field and its value —
      and the diff of the read-set assertion in
      `tests/test_workgraph_sweep.py:1168` showing which member was added and
      what it is for, or showing it unchanged because the message text never
      reaches an attempt result at all.

## Verification

- [ ] T060 The full gate command passes green.
- [ ] T061 The operator sequence in `plan.md` § "Verification the operator will
      run, independent of the gate" is executed end to end. Step 1 — watching the
      addressee dispatch while the asker is parked, at a concurrency of 1 — is the
      falsifiable test of this whole spec and the reason it was held at `draft`
      since 2026-08-08. A PASS verdict is not evidence for it.
