# Tasks: a pressed button does what it says

**Spec**: `specs/079-a-pressed-button-does-what-it-says/spec.md`
**Plan**: `specs/079-a-pressed-button-does-what-it-says/plan.md`

Read the plan's traps before the first task. Trap 2 (**both escalation sites**),
trap 3 (removing `RETRY` everywhere destroys the feature) and trap 6
(**reproduce the question park before touching the question branch**) are the
three that decide whether an attempt lands.

## Phase 1: User Story 1 — An escalation offers only what this node can execute

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-002) In
      `tests/test_escalation_offers_only_what_it_can_do.py`, assert `RETRY` is
      absent from the choices handed to a verification-ladder escalation raised
      on a node with no attempt left. Assert on the choice list, not on the enum.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert `RETRY` is absent from a
      landing escalation raised when `recovery_cycles >= max_recovery_cycles`.
      This is 075/us1's exact configuration at 03:18Z on 2026-08-21.
- [ ] T003 [P] [US1] (spec US1-S3) **The control.** Assert a node with an attempt
      left is offered `RETRY` and that pressing it issues an attempt key. A change
      that never offers `RETRY` passes T001 and T002 and has deleted the feature
      (trap 3).
- [ ] T004 [P] [US1] (spec US1-S4, FR-003) Assert every escalation offers at
      least one executable choice. An empty keyboard is a park with no exit.
- [ ] T005 [P] [US1] (spec US1-S5, FR-004) Assert a resolution naming an
      unoffered choice is refused by name and recorded, rather than falling
      through the kill branch at `factory/workgraph/workflow.py:3324`. Keep
      `EXPIRED` ending the node — separate the two cases explicitly (trap 4).
- [ ] T006 [P] [US1] (spec US1-S6, FR-005) Assert an answered `KILL` leaves
      exactly one escalation for that node. On 2026-08-19 three answered kills
      produced three fresh escalations.

### Implementation for this story

- [ ] T007 [US1] (FR-001) Replace the constant offer with a computed one at
      **both** sites: `factory/workgraph/workflow.py:2442` and `:3280` (trap 2).
      The budgets are already in scope at `:2813`, `:2850-2851` and `:484`.
- [ ] T008 [US1] (FR-001) Decide what happens to
      `factory/activities/notify_activities.py:117`'s `DEFAULT_CHOICES` and to
      the request dataclass default at `:168`. A default that still offers all
      four is a way for the next caller to reintroduce this. Say what you chose.
- [ ] T009 [US1] (FR-004) Add the named refusal for an unoffered resolution.

### Verification for this story

- [ ] T010 [US1] (SC-001) Paste the choice list for a node with nothing left and
      for a node with an attempt left, side by side.
- [ ] T011 [US1] (SC-002) Paste a `RETRY` press on a node with budget and the
      attempt key issued after it.
- [ ] T012 [US1] (SC-003) Paste an answered `KILL` and the escalation count for
      that node afterwards.

## Phase 2: User Story 2 — A pressed button lands, or the operator is told why

Independent of the workflow chain: this story edits `factory/notify/service.py`
and its own test file.

### Tests for this story (write FIRST, must fail)

- [ ] T013 [P] [US2] (spec US2-S1, FR-006) In
      `tests/test_pressed_button_reaches_the_store.py`, assert a press on a live
      escalation sends the signal and resolves the row.
- [ ] T014 [P] [US2] (spec US2-S2, FR-006) **Enumerate the bridge's
      press-handling branches from the code** — `BridgeOutcome`
      (`factory/notify/service.py:165`) is the enumeration that already exists —
      and assert each one either signals-and-resolves or returns a named refusal
      to the operator. Hand-listing the branches is how one of them came to
      swallow a press (trap 8).
- [ ] T015 [P] [US2] (spec US2-S3, FR-007) Assert every handled press is recorded
      where an operator can read it, naming the escalation id. The 03:16Z press
      left no signal, no row change and no line naming `f54b3a73c3b9`.
- [ ] T016 [P] [US2] (spec US2-S4, FR-008) **The control.** Assert a genuinely
      stale press is still refused and is told it is stale. Do not remove the
      staleness guard to make presses land (trap 9).

### Implementation for this story

- [ ] T017 [US2] (FR-006) Close the branch or branches that can return without
      signalling and without telling the operator. Preserve the
      signal-before-resolve ordering (`factory/notify/service.py:16-26`).
- [ ] T018 [US2] (FR-007) Record the handling of every press.
- [ ] T019 [US2] Cover the second entry point: `relay` at
      `factory/notify/service.py:287` reads `callback_query` at `:301` too.

### Verification for this story

- [ ] T020 [US2] (SC-004) Paste the branch enumeration and the outcome each
      produces.
- [ ] T021 [US2] (SC-005, spec US2-S5) Paste a real press on a real escalation on
      this host, with the resulting store row and the signal. If no live
      escalation exists when you get here, say so and paste the closest
      constructed equivalent — do not invent a transcript (trap 12).

## Phase 3: User Story 3 — An answered question un-parks the node

**Depends on US1 having merged** (`depends_on_merged`). Shares
`factory/workgraph/workflow.py` with US1 and US4 (trap 10).

### Tests for this story (write FIRST, must fail)

- [ ] T022 [P] [US3] (spec US3-S5) **Reproduce first.** Build the park —
      node asks a question, answer arrives, child completes — and capture what
      the node's state is afterwards, against the tree as it stands. **Do not
      edit the answered branch until this reproduction exists** (trap 6).
- [ ] T023 [P] [US3] (spec US3-S1, FR-009) In
      `tests/test_answered_question_unparks_the_node.py`, assert the node leaves
      `WAITING_OPERATOR` and a new attempt is dispatched.
- [ ] T024 [P] [US3] (spec US3-S2, FR-010) Assert the assembled prompt string
      carries the question and the answer verbatim.
- [ ] T025 [P] [US3] (spec US3-S3, FR-011) Assert a sibling that was `PENDING`
      behind the park is dispatched once the node resumes. Two of 073's stories
      waited behind one park.
- [ ] T026 [P] [US3] (spec US3-S4, FR-012) **The control.** Assert an expired
      question still re-enters the ladder as a FAIL, unchanged.
- [ ] T027 [P] [US3] (spec US3-S6) Assert a store whose `usage_records` DDL
      predates the `question` termination either accepts the teardown or fails by
      name. The tree's DDL lists it (`factory/usage/ledger.py:76-78`); an
      installed store from before it does not, and the symptom is identical
      (trap 7).

### Implementation for this story

- [ ] T028 [US3] (FR-009, FR-011) Fix what the reproduction named. Two candidates
      to eliminate early, neither confirmed: whether the `continue` at
      `factory/workgraph/workflow.py:1728` reaches the state assignment at
      `:1549`, and whether `self._paused = False` at `:1727` wakes the
      scheduler's wait at `:819-822`.
- [ ] T029 [US3] (FR-010) Ensure the exchange reaches the prompt.
- [ ] T030 [US3] If the cause turns out to be the store constraint rather than
      the workflow branch, fix that and say so plainly in the diff. Follow the
      migration precedent at `factory/verify/store.py:347-348`.

### Verification for this story

- [ ] T031 [US3] (SC-006) Paste the reproduction before the fix (parked) and
      after (resumed), including the sibling that was waiting.
- [ ] T032 [US3] (SC-007) Paste the assembled prompt carrying the question and
      the answer.

## Phase 4: User Story 4 — A pause parks; it does not kill what is left

**Depends on US3 having merged** (`depends_on_merged`). Same file (trap 10).

### Tests for this story (write FIRST, must fail)

- [ ] T033 [P] [US4] (spec US4-S1, FR-013) In `tests/test_pause_is_not_a_kill.py`,
      assert a PAUSE_EPIC press on a node with dependents does not kill them.
- [ ] T034 [P] [US4] (spec US4-S2, FR-014) Assert the undispatched nodes dispatch
      after a resume. A park whose work cannot be resumed is a kill with a longer
      name.
- [ ] T035 [P] [US4] (spec US4-S3, FR-015) Assert the rendered escalation message
      names what each offered choice does to the node and to the epic.
- [ ] T036 [P] [US4] (spec US4-S4) **The control.** Assert a KILL press still
      locks out dependents exactly as today. `_lock_out_dependents`
      (`factory/workgraph/workflow.py:1219`) is correct for a killed node and must
      not be weakened (trap 5).
- [ ] T037 [P] [US4] (spec US4-S5) Assert `ergane build reset` can act on the
      state a PAUSE_EPIC press leaves behind.

### Implementation for this story

- [ ] T038 [US4] (FR-013) Stop routing PAUSE_EPIC through `NodeState.FAILED` at
      `factory/workgraph/workflow.py:3322`. `factory/workgraph/models.py:93`
      records the precedent: `WAITING_OPERATOR` is deliberately outside
      `_UNREACHABLE` for exactly this reason.
- [ ] T039 [US4] (FR-013) Check the ladder's PAUSE_EPIC path too
      (`factory/workgraph/workflow.py:1781-1787`); it does not go through `:3322`
      and may already be correct. Say which it was.
- [ ] T040 [US4] (FR-015) Name the blast radius in the message.

### Verification for this story

- [ ] T041 [US4] (SC-008) Paste a PAUSE_EPIC press with dependents, their states
      after, and the same epic dispatching them after a resume.
- [ ] T042 [US4] (SC-009) Paste the rendered escalation message showing what each
      offered choice will do.
</content>
