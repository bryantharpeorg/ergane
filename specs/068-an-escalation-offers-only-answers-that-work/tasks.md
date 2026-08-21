# Tasks: an escalation offers only answers that work

**Spec**: `specs/068-an-escalation-offers-only-answers-that-work/spec.md`
**Plan**: `specs/068-an-escalation-offers-only-answers-that-work/plan.md`

Read the plan's traps before the first task. Trap 1 (do not widen the cap —
distinguish), trap 3 (the reporter's stated remedy is already implemented at
`ladder.py:94`; implementing it again double-grants) and trap 6 (the red test is
pure and nearly free — get it first) are the three that decide whether an attempt
lands.

## Phase 1: User Story 1 — RETRY produces an attempt

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In
      `tests/test_escalation_grant_survives_the_judge_cap.py`, build a history of
      **three** non-debugger `AttemptRecord`s that **each** carry
      `JudgeOutcome.RETRY`, **plus one record with `persona=DEBUGGER_PERSONA`**
      (the debugger rung must already be spent), a `VerificationConfig` at
      defaults, and `escalations=[EscalationChoice.RETRY]`. Assert `next_action`
      returns a retry. It returns `ESCALATE` today — that is the reproduction,
      and it needs no Temporal (trap 6). A history where only the latest record
      carries `JudgeOutcome.RETRY` returns `RETRY` today and proves nothing.
- [ ] T002 [P] [US1] (spec US1-S4) **The control.** Same history, no grant, but
      under `VerificationConfig(max_attempts=5)` — at the defaults the attempt
      budget short-circuits first and the cap does no work, so a control at
      defaults passes even if you delete the cap outright
      (`factory/verify/ladder.py:17-22` states this). With `max_attempts=5` the
      history returns `ESCALATE` at `max_judge_retries=2` and a retry at
      `max_judge_retries=99`, so the assertion can actually fail. Both halves in
      this one file (trap 1).
- [ ] T003 [P] [US1] (spec US1-S2) Assert the granted retry actually dispatches —
      the node leaves the escalated state — not merely that a function returned a
      value.
- [ ] T004 [P] [US1] (spec US1-S3) Assert a second ESCALATE arising from anything
      other than an operator grant still becomes KILLED, preserving
      `factory/workgraph/workflow.py:1460-1465` (trap 2).
- [ ] T005 [P] [US1] (spec US1-S5) Assert two grants buy exactly two attempts, not
      more. Guards against trap 3's double-grant.
- [ ] T006 [P] [US1] (spec US1-S6) Enumerate the options
      `factory/notify/messages.py:99-101` offers against the action each produces,
      and assert none is a no-op.

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002) Change the condition at
      `factory/verify/ladder.py:96` so an operator-granted attempt is not
      suppressed by `_judge_rewrites_spent`, while judge-driven retries remain
      bounded. Keep `next_action` a pure function of its three arguments
      (trap 5).
- [ ] T008 [US1] (FR-003) Ensure the existing grant at `ladder.py:94` remains the
      only grant. Do not add a second (trap 3).
- [ ] T009 [US1] (FR-004) Leave `factory/workgraph/workflow.py:1460-1465` intact.
- [ ] T010 [US1] (FR-005) If any offered option remains incapable of changing the
      node's state, stop offering it.

## Phase 2: User Story 2 — KILL leaves the epic in a state the CLI can recover

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) In
      `tests/test_killed_node_leaves_a_resettable_epic.py`, assert an epic whose
      node was killed by an escalation resolution holds no living escalation
      child.
- [ ] T012 [P] [US2] (spec US2-S2) Assert `ergane build reset` succeeds against
      that epic — exit status and reset effect, not merely no exception.
- [ ] T013 [P] [US2] (spec US2-S3) Assert `reset` succeeds against an epic whose
      only living child is a stalled escalation. This is the deadlock's own
      shape.
- [ ] T014 [P] [US2] (spec US2-S4) **The control.** Assert `reset` still refuses an
      epic with a genuinely running node, naming what is running (trap 7).
- [ ] T015 [P] [US2] (spec US2-S5) Assert ending the node and ending the epic are
      distinguishable choices, and that PAUSE_EPIC collapses into neither
      (`factory/workgraph/workflow.py:1449-1455`).

### Implementation for this story

- [ ] T016 [US2] (FR-006) The escalation child is **awaited**
      (`factory/workgraph/workflow.py:2023` `execute_child_workflow`), so a killed
      node's own escalation is already complete when its resolution is read —
      FR-006 is already true for that case. What is **not** true is the stalled
      case: `kill_epic` (`factory/workgraph/workflow.py:561-573`) only sets
      `self._kill_requested`, and neither `_escalate` (`:2023`) nor
      `_escalate_landing` (`:2673`) observes it, so an epic holding an open
      escalation ignores `ergane build kill` for up to `escalation_timeout_s`
      (default 3600). Copy the question park's shape at
      `factory/workgraph/workflow.py:1357-1368` — `wait_condition(child.done() or
      self._kill_requested)`, then cancel the child and leave the store row
      PENDING; a stopped epic is neither a press nor a burn.
      **`factory/escalation/workflow.py:373-402` is `_settle_unanswered`'s expiry
      fail-safe and is OUT OF SCOPE per this spec's own Edge Case on expiry — do
      not touch it.**
- [ ] T017 [US2] (FR-007) Widen `_reset_epic`'s precondition
      (`factory/cli/nouns/build.py:879-915`) by what kind of child is alive, not
      by loosening the status test (trap 7).
- [ ] T018 [US2] (FR-008) Make ending the node and ending the epic distinct
      operator choices.

## Phase 3: User Story 3 — Every build verb is keyed by the epic id

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US3] (spec US3-S1) In `tests/test_build_verbs_take_an_epic_id.py`,
      assert `ergane build reset <epic-id>` resolves the graph from
      `<specs_root>/<epic_id>/workgraph.json` **without requiring Temporal
      history** and resets the right nodes, with the epic's workflow absent from
      Temporal (trap 11).
- [ ] T020 [P] [US3] (spec US3-S2) Assert an unknown epic id fails naming the id
      and where it looked.
- [ ] T021 [P] [US3] (spec US3-S3) Enumerate every `build` subcommand's first
      positional argument (`factory/cli/nouns/build.py:1067-1219`) and assert each
      **live-epic verb** takes `epic_id`, with `start`, `salvage` and
      `external-completion-count` declared as exclusions **in the test, with the
      reason stated** — `salvage` keeps its graph path deliberately
      (`build.py:918-935`) and `external-completion-count` has no positional. The
      test must fail if a new subcommand appears outside both lists.
- [ ] T022 [P] [US3] (spec US3-S4) Assert a supplied graph path is **still
      accepted** — `tests/test_ergane_build.py:1284, 1297, 1342, 1363, 1378, 1422`
      all pass one. Never silently reinterpreted (trap 8).
- [ ] T022b [P] [US3] (spec US3-S5) Assert `reset` still archives the survivors when
      the epic's workflow is gone from Temporal.
      `factory/cli/nouns/build.py:882-891` proceeds on `NOT_FOUND` today and
      `tests/test_ergane_build.py:1363` pins it; that must survive the argument
      change (trap 11).

### Implementation for this story

- [ ] T023 [US3] (FR-009) Change `factory/cli/nouns/build.py:1158` to accept an
      epic id and resolve `<specs_root>/<epic_id>/workgraph.json` itself, saying
      what happens when it is absent. **Keep the positional graph path
      accepted** — `tests/test_ergane_build.py:1284, 1297, 1342, 1363, 1378,
      1422` all pass one. `_reset_epic` needs `graph.nodes` and
      `graph.target_repo`, not only the id (trap 11).
- [ ] T024 [US3] (FR-010) Bring the family into line and keep it that way.

## Verification

- [ ] T025 (SC-001) Construct the frontmatter's exact history, apply RETRY, and
      paste the decided action before and after the fix.
- [ ] T026 (SC-002) Paste the control run: the cap still bounds judge-driven
      retries with no grant present.
- [ ] T027 (SC-003) Kill a node from an escalation, run `ergane build reset`
      against the epic with no Temporal surgery, and paste the output.
- [ ] T028 (SC-004) Run `ergane build reset <epic-id>` and paste the output.
- [ ] T029 (SC-005) Paste the enumeration of every `build` subcommand's first
      positional argument.
