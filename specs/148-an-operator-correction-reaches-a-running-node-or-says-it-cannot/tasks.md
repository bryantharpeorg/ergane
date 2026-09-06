# Tasks: an operator correction reaches a running node or says it cannot

Read `plan.md` before starting. Four of its traps decide whether this spec is
cheap or wasted. Trap 1: the ledger row this spec closes is **wrong about which
half survived** — the per-attempt standards read already ships at
`factory/activities/agent_activities.py:1022` — `resolve_standards`, and nothing
here touches that file. Trap 2: `sync_with_target` is a plain function and
calling it from the new command is the obvious move and the wrong one — the
worktree is on the worker host and may have an agent writing in it. Trap 4: a
sync that moves the pin on the record but not on the local
`factory/workgraph/workflow.py:1715` — `_run_node` hands to
`factory/workgraph/workflow.py:2559` — `_verify` hands the judge every landed
sibling's work; move all three fields. Trap 10: a conflicted re-sync leaves the
markers in the tree, so the outcome the operator reads has to say the remaining
attempts will run against them.

One property of the scripted test world decides how T003 is written: it never
reaches `read_worktree_diff`, because its criteria carry no scenarios, so an
assertion over the judge's diff base would pass over zero calls. The pin is
proved from the verification row and from the `epic_status` query instead —
`plan.md` § "The offline way to drive the attempt loop" has the mechanism, and
the same section names the second stub that world has been missing since 126-US2
landed `archive_and_clear_remote_branch` on every terminal path. T001 adds both.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — One verb re-syncs a running node's tree, or says why it could not

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (trap 2) Stand up the scripted activity world this phase runs
      in: a new module that **imports and subclasses**
      `tests/test_external_completion.py:198` — `ConfigurableScript` rather than
      copying it — `tests/test_095_pre_agent_failure.py:42` is the house move,
      importing another suite's Temporal wiring instead of standing up a second
      one — and whose subclass appends to `super().activities()` **two** stubs.
      First a `sync_landing_branch` stub with a test-controlled outcome: clean,
      conflicted, refused. Model it on the `resolve_standards`
      stub at `tests/test_external_completion.py:299` and the `prepare_worktree`
      stub at `tests/test_external_completion.py:309`, both inside
      `tests/test_external_completion.py:258` — `ConfigurableScript.activities`,
      whose returned registry is `tests/test_external_completion.py:437-445`.
      Second an `archive_and_clear_remote_branch` stub returning an empty report
      list, which nothing in this story calls: 126-US2 (`8d5102e`, 2026-09-02)
      put that activity on every terminal non-parked path
      (`factory/workgraph/workflow.py:3087` — `_close_out`, the activity at
      `factory/workgraph/workflow.py:3143`;
      `factory/workgraph/workflow.py:3594` — `_archive_and_clear_remote_branch`
      from three more sites) and stubbed it in the interpreter suite
      (`tests/test_interpreter.py:1560-1561`) rather than in this world, whose
      last commit predates it — so every test below whose node reaches a
      terminal state, T004, T005 and T006 included, dies on an unregistered
      activity without it. Without either stub the tests fail on registration
      rather than on the behaviour under test; and copying the harness instead
      of importing it adds 19,628 bytes to this story's diff for nothing, which
      is how a story this shape reaches the refusal (`plan.md` § Sizing). Not
      `[P]`: every other test in this phase builds on it.
- [ ] T002 [P] [US1] (spec US1-S1, FR-003, FR-004) Buffer a re-sync request for
      a node whose first attempt has failed, then assert the attempt loop
      executed `factory/activities/merge_activities.py:580` —
      `sync_landing_branch` exactly once for that node, **before** the agent was
      dispatched for the next attempt.
- [ ] T003 [P] [US1] (spec US1-S2, FR-005, trap 4) On a clean sync, assert both
      of the pin's reachable halves in one test: the merged-in head is on
      `record.prepared` — read through the
      `factory/workgraph/workflow.py:860` — `epic_status` query, whose
      `NodeStatus.base_ref` is composed from `record.prepared.base_ref` at
      `factory/workgraph/workflow.py:890-894` — **and** it is the base written
      onto the following attempt's verification row — the value
      `factory/workgraph/workflow.py:2672` composes from the same `prepared`
      local `check_output` is measured with
      (`factory/workgraph/workflow.py:2614`). Read that row back from the store
      this world writes to for real through the `record_verification` stub at
      `tests/test_external_completion.py:356-367`, querying the `base_ref`
      column declared at `factory/verify/store.py:234` the way
      `tests/test_external_completion.py:511` — `_verification_row` queries its
      own columns. The third write, `record.base_ref`, has no reader outside the
      landing path's own pre-sync comparison at
      `factory/workgraph/workflow.py:3696`: put it in the diff, do not try to
      assert it, and do not mistake the query's `base_ref` for it — that value
      is `record.prepared`'s. A diff that writes the record fields and leaves
      `factory/workgraph/workflow.py:1715` — `_run_node`'s own local stale
      passes the query half and fails the row, and that failure is invisible
      to every other assertion in the file. Do **not** write this assertion
      against `read_worktree_diff`: this world stubs none
      (`tests/test_external_completion.py:437-445`) and cannot reach the
      activity anyway, because `factory/workgraph/workflow.py:2625` gates it on
      `factory/verify/models.py:977` — `judge_required` and
      `tests/test_external_completion.py:456` — `_criteria_for` declares no
      scenarios (`tests/test_external_completion.py:465`), so the assertion
      would pass over an empty set and hide the very half-fix this task exists
      to catch.
- [ ] T004 [P] [US1] (spec US1-S3, FR-004, FR-006, traps 6 and 10) On a
      conflicted sync, assert the recorded outcome carries the conflicted paths
      **and** states that the tree still holds unresolved conflict markers its
      remaining attempts will run against; assert the node keeps running its
      ladder and the request is **consumed** rather than re-applied on the
      following attempt. Assert too that the diff introduces no rebase, reset or
      force-push call and routes the merge through the existing
      `factory/activities/merge_activities.py:580` — `sync_landing_branch`
      activity. Branch reachability is landed behaviour of
      `factory/workgraph/worktree.py:1316` — `sync_with_target` that FR-004
      forbids touching and this world has no git to measure it in; it is proved
      in `plan.md` operator step 4 instead.
- [ ] T005 [P] [US1] (spec US1-S4, FR-006, FR-009, trap 5) On a refused sync,
      assert all four in one test: the reason is recorded on the node, no
      escalation is opened, no attempt is spent, and the next attempt opens the
      pinned tree. The landing path escalates and returns here
      (`factory/workgraph/workflow.py:3711`); this path must not.
- [ ] T006 [P] [US1] (spec US1-S5, FR-008, trap 3) **The control that matters
      most.** With no request buffered, run three attempts and assert no sync
      activity was executed and the recorded base pin is identical across all
      three. A diff that syncs every attempt passes every other test in this
      phase and fails this one.
- [ ] T007 [P] [US1] (spec US1-S6, FR-007) Buffer a request naming a node that
      is not at work and assert it is refused with a recorded reason rather than
      left buffered, and that the refusal is readable from the node record
      rather than from the external-completion audit log — assert nothing was
      written through
      `factory/verify/store.py:1882` — `record_external_completion_signal`.
- [ ] T008 [P] [US1] (spec US1-S7, FR-001, trap 2) Run `ergane build resync`
      against an epic id that names no running workflow and assert a non-zero
      exit with the `no epic '<id>' is running here` refusal, and assert the
      command opens no repository and calls no worktree helper.
- [ ] T009 [P] [US1] (FR-009, trap 5) **The control.** Assert a clean re-sync
      leaves `record.landing` untouched — recovery cycles and free rebases read
      exactly as they did before the sync — so an operator courtesy cannot spend
      the landing path's accounting.
- [ ] T009a [P] [US1] (spec US1-S8, FR-010, traps 8 and 10) **The readout the
      title is about.** A renderer test, no workflow environment: render
      `ergane build status` for one node whose last re-sync conflicted and one
      whose last re-sync was refused, and assert the first block carries the
      conflicted paths and the sentence naming the unresolved markers its
      remaining attempts will run against, and the second carries the refusal
      and its reason. Without this, a diff that adds the field to `NodeStatus`
      and renders only the clean case passes every other test in this phase.

### Implementation for this story

- [ ] T010 [US1] (FR-002) Add the buffering signal handler to the epic workflow,
      modelled on `factory/workgraph/workflow.py:853` —
      `complete_node_externally`: it appends the node id and returns. No
      activity, no await — `factory/workgraph/workflow.py:838` — `kill_epic`
      says why a handler that acted would race the lifecycle it is changing.
      Declare the signal name as a module constant beside
      `factory/notify/service.py:115`.
- [ ] T011 [US1] (FR-003, FR-004, FR-005, traps 3 and 4) Apply a buffered
      request in the attempt loop, immediately before the per-attempt standards
      resolution at `factory/workgraph/workflow.py:1826`, by executing
      `factory/activities/merge_activities.py:580` — `sync_landing_branch`. Take
      the request once, the way
      `factory/workgraph/workflow.py:2793` — `_pop_external_completion` does. On
      a clean sync move the pin on all three of the fields
      `factory/workgraph/workflow.py:3734-3736` moves — including the local
      `prepared` on its first line, which here is the one
      `factory/workgraph/workflow.py:1715` — `_run_node` passes to
      `factory/workgraph/workflow.py:2559` — `_verify` at
      `factory/workgraph/workflow.py:2076-2080`; a record-only write leaves the
      next attempt measured from the pre-merge base. The call must be reachable
      **only** from a buffered request: an unconditional sync un-pins the
      worktree against 118 FR-004/R5
      (`factory/workgraph/worktree.py:420-441`) and changes the activity
      sequence every recorded history was written with.
- [ ] T012 [US1] (FR-006, FR-009, traps 5 and 10) Handle the two non-clean
      outcomes without borrowing the landing path's behaviour: record the
      refusal reason, or the conflicted paths **together with the fact that the
      tree still holds unresolved markers the node's remaining attempts will run
      against**, and let the ladder continue. Do **not** call
      `_escalate_and_apply`, do **not** touch `record.landing`, do **not** count
      the attempt, and do **not** switch persona the way
      `factory/workgraph/workflow.py:3787-3794` does — there is no debugger on
      this path. Compare against `factory/workgraph/workflow.py:3711` and
      `factory/workgraph/workflow.py:3716` and copy neither.
- [ ] T013 [US1] (FR-007) Refuse a buffered request for a node that is not at
      work, recording the reason on the node record, in the shape of
      `factory/workgraph/workflow.py:2819` —
      `_refuse_buffered_external_completions` and its existing call site at
      `factory/workgraph/workflow.py:1762`. Copy the shape, not the sink: that
      helper writes through
      `factory/verify/store.py:1882` — `record_external_completion_signal`,
      which wants a branch and a provenance string a re-sync request does not
      have.
- [ ] T014 [US1] (FR-001, trap 2) Add `resync_command` and its parser entry to
      the build noun, modelled on
      `factory/cli/nouns/build.py:1247` — `complete_node_externally_command` and
      declared inside `factory/cli/nouns/build.py:2074` — `add_parser` beside
      the `complete-node-externally` parser at
      `factory/cli/nouns/build.py:2296`. It sends the signal through
      `factory/cli/nouns/build.py:1492` — `_send_signal_with_args` and does
      nothing else. It must not import
      `factory.workgraph.worktree`: `factory/cli/nouns/build.py:2115` records
      that `target_repo` is a worker-host path, and an attempt may be in flight
      in that tree.
- [ ] T015 [US1] (FR-010, traps 8 and 10) Carry the last re-sync outcome onto
      `NodeStatus` beside the `base_ref` 118-US2 added at
      `factory/workgraph/workflow.py:890-894`, and render **all three shapes** —
      clean with the new pin, conflicted with the paths and the unresolved-marker
      sentence, refused with the reason — as their own line in
      `ergane build status`, modelled on
      `factory/cli/nouns/build.py:738` — `_attempt_note_lines`. Do not change
      `factory/cli/nouns/build.py:524` — `_base_token`; that token is US2's
      neighbour and its text is asserted there.

### Verification for this story

- [ ] T016 [US1] Paste, as committed evidence, three `ergane build status`
      readings for one node: before and after a **clean** re-sync — showing the
      pin moving to the landing head — and after a **refused** re-sync, showing
      the refusal and its reason with the attempt number unchanged. Paste with
      them `git -C <worktree> log --oneline -3` for the clean case, showing the
      merge commit with the node's own commits still reachable beneath it.
      Those three blocks and that three-line log are the whole of it: no
      transcript, no full log, no repeated status. 118-US3's attempt report was
      15,361 bytes of a 59,174-byte story and D-050 counts every one of them
      (`plan.md` § Sizing).

## Phase 2: User Story 2 — Every surface that offers another attempt says the tree is pinned

### Tests for this story (write FIRST, must fail)

- [ ] T017 [P] [US2] (spec US2-S1, FR-011, trap 8) Render the blast-radius
      block for a choice set containing RETRY and assert two things about the
      RETRY line: it states that the tree the next attempt opens was branched
      from the landing branch when the node was dispatched, and it names both of
      the things that move that tree — a landing recovery and an operator
      re-sync. Assert also that the flat claim is absent, i.e. the line does not
      say the tree has not moved since: the same entry renders on the landing
      escalation (`factory/workgraph/workflow.py:4178` — `_escalate_landing`),
      where `factory/workgraph/workflow.py:3734-3736` has already moved the pin.
- [ ] T018 [P] [US2] (spec US2-S2, FR-012) Assert the same line verbatim, and
      assert it names the standards document as the one channel re-read per
      attempt and makes no claim about the spec, plan or tasks, which
      `factory/workgraph/workflow.py:1013` reads once per epic. Asserting the
      line whole is the point: a later widening then shows up as a diff.
- [ ] T019 [P] [US2] (spec US2-S3, FR-013, trap 11) Assert the same line names
      both supported recoveries by name — `ergane build resync`, and ending the
      epic and starting the spec again from the landing branch as it then
      stands, said as the operator's own move for a hand-started epic and as a
      later roadmap run's for a spec the roadmap owns. Assert too that the line
      does **not** promise that ending the epic makes the roadmap rebuild it:
      `factory/roadmap/workflow.py:1416` — `_landed_status_for` files a child
      that completed with a FAILED or KILLED node into the map
      `factory/roadmap/workflow.py:864-871` excludes from `dispatchable`, and an
      epic started with `ergane build start` has no roadmap owner at all, so the
      flat claim strands the operator exactly as this finding measured.
- [ ] T020 [P] [US2] (spec US2-S4, FR-014, trap 7) **The control.** Render the
      block for a choice set that does **not** offer RETRY and assert none of
      that text appears.
      `factory/notify/messages.py:358` — `render_blast_radius` renders one line
      per *offered* choice (079-US1); a paragraph bolted onto the message body
      would describe a button that is not on the keyboard and this test is what
      catches it.
- [ ] T021 [P] [US2] (spec US2-S5, FR-015, trap 8) Render a status line for a
      node with a prepared worktree and assert two things: the new sentence
      naming the pin and both of its movers — a landing recovery, an operator
      re-sync — is present, and the existing
      `base <sha12> landing head <branch> <sha12>` token from
      `factory/cli/nouns/build.py:524` — `_base_token` is unchanged, character
      for character.

### Implementation for this story

- [ ] T022 [US2] (FR-011, FR-012, FR-013, FR-014, traps 7, 8 and 11) Extend
      RETRY entry of the `_CHOICE_EFFECTS` map at
      `factory/notify/messages.py:134` **in place** — currently
      `factory/notify/messages.py:135-138` — so it says the tree was branched
      from the landing branch at dispatch and moves only when a landing recovery
      syncs it (`factory/workgraph/workflow.py:3734-3736`) or an operator
      re-syncs it, names the standards document as the one per-attempt channel,
      and names both recoveries — the verb, and ending the epic and starting the
      spec again from the landing branch as it then stands, the operator's own
      move for a hand-started epic and a later roadmap run's for a spec the
      roadmap owns (trap 11: a flat "the roadmap rebuilds it" is false on both
      paths, `factory/roadmap/workflow.py:864-871`). The map is keyed by choice
      and not by escalation site, so this same line is what
      `factory/workgraph/workflow.py:4178` — `_escalate_landing` renders after a
      recovery has moved the pin; an unqualified "has not moved" is a false
      sentence there. One dictionary entry; no second block, no change to
      `factory/notify/messages.py:373` — `_effect_line`.
- [ ] T023 [US2] (FR-015, trap 8) Add the pin sentence to `ergane build status`
      beside the token `factory/cli/nouns/build.py:524` — `_base_token` renders,
      composed into the node block at `factory/cli/nouns/build.py:504`: the base
      is the pin taken at dispatch and moves between attempts only when a
      landing recovery syncs it or a re-sync is applied — the same two movers
      T022's sentence names, because a status line and a message that disagree
      about the tree are worse than either alone. Do not
      re-derive the base, do not reformat the token, and do not compute whether
      the pin is stale — that comparison belongs to
      `factory/workgraph/worktree.py:362` — `ensure`, it needs a fetch, and a
      renderer that fetches is a renderer that hangs.

### Verification for this story

- [ ] T024 [US2] Paste, as committed evidence, the rendered blast-radius block
      for an escalation offering RETRY and for one that does not, side by side,
      and the `ergane build status` output for a node with a prepared worktree
      showing the new sentence beside the unchanged base token.

## Verification

- [ ] T025 The full gate command passes green.
- [ ] T026 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Steps 4, 5 and 7 are the falsifiable test of
      the whole spec: a deliberate conflict must leave the node's work reachable
      with no reset and no rebase in the reflog **and** must be reported as a
      tree the remaining attempts will run against, a removed worktree must
      produce a reported refusal with no escalation and no attempt spent, and
      resolving the conflict by hand on the worker host must let the next rung
      go green.
