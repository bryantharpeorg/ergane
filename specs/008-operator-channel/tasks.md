# Tasks: Operator Channel

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm the reuse inventory in plan.md § Technical Context
      still matches the code this epic will build on (escalation store shape,
      `SIGNAL_NAME` signature, bridge handler registration, final-message capture
      path) — these were drafted from the 2026-08-06 tree and 006's landings may
      have moved them. Correct the plan before deriving, not the nodes after.

---

## Phase 2: User Story 1 — A blocking question reaches the operator's phone (Priority: P1) 🎯 MVP

**Goal**: a marked question in an attempt's final message becomes a QUESTION
termination, a parked node, and a Telegram message — never a burned attempt.

**Independent Test**: complete an attempt whose final message carries the
marker; assert QUESTION classification, one bridge send with the question text,
and no FAIL recorded.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q` is
      green and the plan's verified inventory still holds — in particular the
      `escalations` CHECK constraints (`factory/verify/store.py`), the
      narrowness of `AdapterResult` and its `transcript_path` (D-018,
      `factory/workgraph/models.py`), and the streamed `stdout.log` in the
      attempt archive (`factory/workgraph/adapter.py`) — constitution I gate;
      if the inventory is wrong, STOP and write the discrepancy under the
      operator-question marker (this epic's own mechanism, used manually until
      it exists).
- [ ] T003 [P] [US1] Write marker-detection cases FIRST against archived
      transcripts (the reader's input is the `stdout.log` under
      `AdapterResult.transcript_path` — plan § US1): a final message with the
      line-anchored `## OPERATOR QUESTION` heading classifies QUESTION with the
      body extracted; a message that merely discusses the marker mid-text or
      quotes it in a fenced block does not; an empty body under the marker is a
      malformed question and classifies as today's FAIL (a question with no
      content is not a question); a missing or unreadable transcript is an
      infrastructure failure, never a QUESTION and never a silent FAIL — must
      fail.
- [ ] T004 [P] [US1] Write ladder-routing cases FIRST in the interpreter tests:
      QUESTION termination parks the node WAITING_OPERATOR; salvage runs and
      committed work survives on the branch (FR-005); teardown writes the ledger
      row with real usage (FR-006); the judge is never invoked for a QUESTION
      attempt; **the amendment's guard (FR-010)**: a marker can never produce,
      influence, or substitute for a verdict — an attempt with a marker AND a
      substantive diff still gets no PASS from the marker's presence — must
      fail.
- [ ] T005 [US1] Write delivery cases FIRST against the fake bridge and store:
      the question ships once, attributed epic/node/attempt, body verbatim; a
      `questions` row is written with the Telegram message id captured at send
      (plan § Technical Context — the sibling-table decision; the constrained
      `escalations` table is never touched); the credential sweep assertion
      extends to the question payload and the new table (FR-007) — must fail.

### Implementation for User Story 1

- [ ] T006 [US1] Implement marker detection where verification reads attempt
      output, and the QUESTION termination class, until T003 passes.
- [ ] T007 [US1] Implement WAITING_OPERATOR parking and the QUESTION path through
      salvage/teardown in the interpreter, until T004 passes.
- [ ] T008 [US1] Implement `send_question` (mirror of `send_escalation`: no
      keyboard, message id captured into the `questions` table) until T005
      passes. Extend the prompt contract text (the assembler's standing agent
      instructions) to state the marker and the bar: a question names its fork
      and the options considered, and is for genuinely blocking forks only.

---

## Phase 3: User Story 2 — The answer reaches the next attempt at zero ladder cost (Priority: P1)

**Goal**: a Telegram reply becomes the next attempt's operator-answer section,
and an answered question never counted against the ceiling.

**Independent Test**: answer a parked question; the next prompt carries Q and A
verbatim; the node's remaining attempts equal the pre-question count.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T009 [P] [US2] Write bridge reply-routing cases FIRST: a Telegram reply to
      a question message resolves that question with the reply text as
      `answer_text` (first answer wins, the store's idempotent-transition
      contract); with two questions open, each reply routes by reply-to
      `message_id` → `question_id`, never by recency (FR-008); a non-reply
      message, a reply to a non-question message, and a reply to an
      already-resolved question are ignored or answered-as-settled — must fail.
- [ ] T010 [P] [US2] Write round-trip cases FIRST in the interpreter tests: on
      resolution the node un-parks and the next attempt's assembled prompt
      carries the question and answer verbatim in a dedicated section, distinct
      from verification feedback (FR-003); attempt accounting is unchanged by
      an answered question (a node with N attempts before the question has N
      after the answer); an expired question resolves as FAIL and consumes a
      slot, and the question default is 8 h — 28,800 s, not the escalation
      hour (FR-004, reusing the existing expiry mechanism) — must fail.

### Implementation for User Story 2

- [ ] T011 [US2] Add the `MessageHandler` reply path to
      `factory/notify/service.py`, routing by the `questions` table's stored
      message id, until T009 passes. This story adds the **new signal
      `question_answered(question_id, answer_text)`** to `EpicWorkflow` —
      the escalation signal cannot carry free text: the store CHECK-constrains
      resolutions to the choice enum, verified against the tree (plan
      § Technical Context).
- [ ] T012 [US2] Implement un-park dispatch, the operator-answer prompt section,
      no-burn accounting, and expiry-as-FAIL in the interpreter and prompt
      assembler, until T010 passes.
- [ ] T013 [US2] Final sweep + docs: extend the credential sweep to answers and
      stored records (SC-004); update `docs/architecture.md`'s escalation section
      (questions are a first-class sibling of escalations) and note the marker
      contract where agent prompt contracts are documented; record BOTH
      decision-log entries at the next free numbers — the channel itself and
      the scoped D-018/FR-012 amendment (FR-010, spec § Decision).

---

## Phase 4: User Story 3 — The attempt survives its own question (Priority: P3, deferred behind live evidence)

**Goal**: an in-flight agent's question round-trips without a re-dispatch; the
ferry degrades to the US1 path, never to a hang.

**Independent Test**: with a scripted answer arriving mid-attempt, the same
process resumes and commits; with no answer, the attempt exits via the US1
marker path.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T014 [US3] Write ferry cases FIRST against the adapter: question file in
      the archive directory (never the worktree) ships upward once; an answer
      file is delivered to the polling agent; an unanswered ferry window ends
      with the agent proceeding to the US1 final-message path (FR-009); the
      ferry read never blocks or fails the liveness beat (the same isolation
      006-US1 requires of the usage read) — must fail.

### Implementation for User Story 3

- [ ] T015 [US3] Implement the ferry in the adapter's monitor loop and the agent
      prompt contract's ferry instructions, until T014 passes.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates derivation.
- Phase 2 (US1) has no dependency and is the MVP.
- Phase 3 (US2) depends on US1: store rows, termination class, and parked state
  all land there.
- Phase 4 (US3) depends on US2, and additionally waits for 006-US1's adapter
  changes to land — one monitor loop, one editor at a time (the 006 US4-after-US1
  argument). Do not derive US3 into a graph until 006-US1 is merged.

## Implementation Strategy

US1+US2 are the feature; US3 is an optimization with its own explicit go/no-go:
derive it only after the v0 channel has been exercised by real questions and
their frequency argues for keeping process context warm. If this epic must be
cut to one story, US1 alone still converts a silent burn into a message the
operator can act on by editing specs — tonight's manual path, minus the
archaeology.
