# Tasks: Peer channel (reconstructed)

**This is the defect, and three quarters of it is silent.** The phases were
numbered against the story list from before the already-running-attempt story
was inserted into the spec, so every phase below Phase 2 carries the number of
the story that used to sit there. The tasks under each phase still carry the
key of the story they were written for, which is the only evidence left that
the heading above them names somebody else.

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm the notifier is landed on the target's default
      branch before any of this is dispatched.

## Phase 2: User Story 1 — A question reaches a peer agent in the same epic

- [ ] T002 [P] [US1] Write the routing cases FIRST with scripted children: a
      question addressed to a sibling is answered before the sender stops
      (spec US1-S1) — must fail.
- [ ] T003 [US1] Implement the addressee grammar and the workflow buffers.

## Phase 3: User Story 2 — A message reaches a named external agent

- [ ] T004 [P] [US3] Write the registry cases FIRST: `peers.yaml` parses with
      named findings and closed transport values (spec US3-S1) — must fail.
- [ ] T005 [US3] Implement the peer registry and the mailbox transport.

## Phase 4: User Story 3 — A message crosses epics

- [ ] T006 [P] [US4] Write the cross-epic cases FIRST: an epic-addressed
      message is delivered as a signal to the sibling workflow
      (spec US4-S1) — must fail.
- [ ] T007 [US4] Implement cross-epic routing and complete the namespace.

## Known gap: the already-running-attempt story has no phase yet

There is deliberately no phase heading naming it, so the assembler refuses that
node and the epic cannot be dispatched. Its acceptance scenario (US2-S1) is
named here rather than in a task, because a phase heading carrying a note would
assemble cleanly and hand the agent a paragraph where its task list belongs.

## Verification

- [ ] Final gate command passes green.
