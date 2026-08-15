# Tasks: Escalation is a workflow, and its transport is an adapter

Four stories. US1 → US2 is a merge chain; US3 and US4 both chain on US2 merged
and are independent of each other. Work test-first within a story and commit
once per task.

## Format: `[ID] [P?] [Story] Description`

Read `plan.md` first. Trap 1 is the one that decides whether US3 lands: the 008
behavior suite is the guard and you may not edit it. Trap 2 says the race you
are asked to make deterministic is already deterministic. Trap 3 says where the
correlation id comes from.

## Phase 1: User Story 1 — The transport is an adapter (Priority: P1) 🎯 MVP

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [US1] Write the interface-shape assertion FIRST (spec US1-S2,
      FR-001): the adapter protocol declares exactly two operations — outbound
      deliver of a rendered message plus correlation id, inbound relay of
      correlation id, reply text and sender identity — and no adapter code path
      can acknowledge, answer, or expire. Assert the last part by scanning the
      adapter modules' source, in the style of
      `tests/test_gh_client.py`'s `test_no_code_path_passes_delete_branch`.

- [ ] T002 [US1] Write the no-Temporal case FIRST (spec US1-S3, FR-002): the
      adapter delivers when called from a plain process with no Temporal client
      and no workflow context. 042's supervision probe is that caller and it
      runs when Temporal is dead, so this test is the contract, not a nicety.

- [ ] T003 [US1] Write the fake-adapter round trip FIRST (spec US1-S4): the
      full 008 question round trip — ask, deliver, answer, resume — behaves over
      a fake adapter as it does over Telegram.

### Implementation for User Story 1

- [ ] T004 [US1] Define the protocol and the registry, keyed by the names 033's
      config declares (an unknown name was already refused at parse time).

- [ ] T005 [US1] Move today's Telegram send and the bridge's ferry
      (`factory/notify/service.py:126`, `:365`) behind the interface. Rendering
      stays in `factory/notify/messages.py` — the adapter receives an
      already-rendered message.

- [ ] T006 [US1] Run the existing operator-channel suite unmodified (spec
      US1-S1) and paste the transcript. If `TELEGRAM_BOT_TOKEN` /
      `TELEGRAM_CHAT_ID` are present in your environment, run
      `tests/test_live_notify.py` too and paste that; if they are not, say so
      plainly in the commit rather than claiming a byte-compatibility you did
      not observe (plan trap 7).

- [ ] T007 [US1] Full suite green: `uv run pytest -q`.

## Phase 2: User Story 2 — Escalation is a workflow type (Priority: P1)

Chains on US1 merged. **This story does not touch the epic workflow's park —
that is US3.** Read plan traps 2, 3, 4, 9 and 12 before writing.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T008 [US2] Write the standalone lifecycle FIRST (spec US2-S1): started
      with no parent, the workflow delivers, awaits, and resolves to `answered`
      on a signal and to `expired` at its deadline, writing a store row at each
      transition.

- [ ] T009 [US2] Write the child case FIRST (spec US2-S2): a *test* parent
      starts it as a child and awaits it; answer and expiry both arrive as the
      child's result, and the parent holds no timer and no signal handler.

- [ ] T010 [US2] Write the race case FIRST (spec US2-S3, FR-007): an answer
      signal and the expiry timer both firing resolve to exactly one outcome,
      the loser is recorded as late evidence, and no error escapes. Drive it
      through the existing `expire_escalation` activity — plan trap 2 explains
      why adding a second arbiter beside the store's guarded UPDATE is how a
      press that beat the timer starts losing sometimes.

- [ ] T010a [US2] Write the settlement case FIRST (spec US2-S6, FR-013): one
      lifecycle per channel — signal, expiry — and after each, no pending row
      remains; settlement is the workflow's transition, never the channel's.
      Seed plan trap 9's abandoned-row shape too, not only well-formed rows —
      fourteen live rows prove the well-formed assumption is the bug.

- [ ] T011 [US2] Write the operator-surface case FIRST (spec US2-S4, FR-008):
      `ergane escalations list` shows every unanswered escalation with its
      question and deadline, sourced from running workflows, and drains as they
      resolve. The workflow-listing precedent is
      `factory/activities/roadmap_activities.py:448` (grep `list_workflows`).

- [ ] T012 [US2] Confirm 039's guard covers the new module (spec US2-S5,
      FR-012). It discovers workflow modules by scanning for the decorator
      (`tests/test_workflow_env_guard.py:184`), so it needs no edit — assert
      that it *found* your module rather than merely that it passed, or a
      discovery bug would read as compliance.

- [ ] T012a [US2] Write the round-trip case FIRST (spec US2-S7, FR-014, plan
      trap 12): a stored `EscalationRecord` carrying `check_evidence` reads
      back with it intact, and `typing.get_type_hints(EscalationRecord)`
      resolves. Both halves fail today — the store has no column
      (`factory/verify/store.py:451`, `:624`) and the annotation
      (`factory/verify/models.py:498`) names a module the file never imports.

### Implementation for User Story 2

- [ ] T013 [US2] Mint the correlation id in the **starter**, use it as the
      workflow ID, and pass it through the optional `escalation_id` field
      `SendEscalationInput` already carries
      (`factory/activities/notify_activities.py:150`). Keep the 12-hex-digit
      width — it is why Telegram's `callback_data` fits in 64 bytes (plan
      trap 3).

- [ ] T014 [US2] Implement `run()`: delivery activity, then a durable timer set
      from the row's own instant raced against the answer signal; on timeout,
      call `expire_escalation` and take its answer. Preserve the undelivered
      fail-safe — today an undelivered escalation returns the kill default
      *without waiting* (`factory/workgraph/workflow.py:1968`). Settlement
      happens here, on every terminal transition, whatever the channel
      (FR-013).

- [ ] T014a [US2] Close the record's round-trip gap (FR-014): persist
      `check_evidence` through a `schema_version` migration or delete the
      field's pretense — state which and why in the commit — and make the
      annotation resolve either way.

- [ ] T015 [US2] Add `ergane escalations list`.

- [ ] T016 [US2] Full suite green: `uv run pytest -q`.

## Phase 3: User Story 3 — The epic park becomes parent-awaits-child (Priority: P2)

Chains on US2 merged. Independent of US4. **The riskiest story in this spec:
it refactors the escalation path the operator uses daily. Read plan traps 1,
10 and 11 first — the guard is a suite you may not edit, the operator's verbs
signal handlers you are deleting, and a known defect must be carried, not
fixed.**

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T017 [US3] Before changing anything, run the five behavior-suite files
      unchanged and record the baseline: `tests/test_notify.py`,
      `tests/test_notify_activities.py`, `tests/test_operator_question.py`,
      `tests/test_question_delivery.py`, `tests/test_question_reply.py`
      (spec US3-S1, SC-004). They must pass identically after the migration,
      and **the diff must show them unedited**. An assertion you changed to
      accommodate the refactor is a behavior change wearing a refactor's
      clothes; if one is genuinely wrong, report a finding, do not edit it here.

- [ ] T018 [US3] Write the no-timer-no-handler assertion FIRST (spec US3-S2,
      FR-010): after migration the epic workflow holds no escalation expiry
      timer and no escalation signal handler of its own. Pause, resume and kill
      stay.

- [ ] T019 [US3] Write the expiry-parity case FIRST (spec US3-S3): a parked
      node whose escalation expires reaches the same terminal state and writes
      the same store rows it does today.

- [ ] T020 [US3] Write the **two concurrent escalations** case FIRST (spec
      US3-S4, FR-010, SC-005): the second is not blocked by the first and
      neither pauses the epic's scheduler
      (`factory/workgraph/workflow.py:1050`). This is the 017 deadlock made
      structurally impossible, and inspection cannot show it — plan trap 6.

- [ ] T020a [US3] Write the operator-verbs case FIRST (spec US3-S5, plan
      trap 10): after migration, `ergane build answer` and
      `ergane build resolve` (`factory/cli/nouns/build.py:457`, `:527`) still
      work, and a resolution sent through either settles its store row exactly
      as a button press does — the channel asymmetry the finding measured
      becomes impossible.

- [ ] T020b [US3] Write the RETRY characterization FIRST (plan trap 11): the
      migrated response mapping reproduces today's behavior at the
      recovery-exhausted stage bit for bit — including the defect where RETRY
      tears the node down. The test documents it and cites
      `interpreter/escalation-retry-kills-the-node`; it pins the behavior on
      purpose so the separate fix spec has a baseline. Do NOT fix it here.

### Implementation for User Story 3

- [ ] T021 [US3] Replace the escalation park
      (`factory/workgraph/workflow.py:1950`–`:1990`) with start-child-and-await,
      including its undelivered branch.

- [ ] T022 [US3] Replace the question park (`workflow.py:1362`–`:1460`) the same
      way. Keep both signals and both tables — plan trap 5 explains why the
      second of each exists and why unifying them belongs in a different spec.

- [ ] T022a [US3] Re-point the operator verbs at the child workflow (plan
      trap 10). Do not teach the CLI to write store rows — that is a third
      writer; FR-013 already made settlement the workflow's, which is what
      T020a proves.

- [ ] T023 [US3] Full suite green: `uv run pytest -q`, and paste the
      behavior-suite result verbatim.

## Phase 4: User Story 4 — Any messenger, and only authorized answers (Priority: P2)

Chains on US2 merged. Independent of US3.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T024 [US4] Write the webhook round trip FIRST (spec US4-S1, FR-003):
      against a local HTTP listener, a question POSTs the rendered message and
      correlation id, and `ergane answer <id> "ship it"` resumes the waiting
      workflow with that text.

- [ ] T025 [US4] Write the unauthorized-reply case FIRST (spec US4-S2, FR-011):
      a relay whose sender identity is absent from
      `escalation.authorized_responders` does not resume the workflow, is
      recorded with its identity, and leaves the expiry clock untouched.

- [ ] T026 [US4] Write the not-poisoned case FIRST (spec US4-S3, SC-002): after
      the unauthorized reply, an authorized one is accepted normally.

- [ ] T027 [US4] Write the no-adapter-may-expire case FIRST (spec US4-S4): with
      either adapter, expiry fires from the workflow's own durable timer and is
      recorded by a factory activity.

### Implementation for User Story 4

- [ ] T027a [US4] Add `authorized_responders` to the typed config's
      `Escalation` block (`factory/controlplane/config.py:165-172`) with the
      parser's existing refusal conventions — the landed 033 parser does not
      have the field; the spec's Assumptions section corrects the original
      claim that it would.

- [ ] T028 [US4] Implement the webhook adapter — outbound POST only; it decides
      nothing.

- [ ] T029 [US4] Add `ergane answer <correlation-id> <text>`, signalling the
      workflow named by that id. For an id with no running workflow, report
      which of the three cases it was — answered, expired, or never existed —
      not a generic failure.

- [ ] T030 [US4] Implement the authorized-responders check **factory-side**,
      applied to every adapter's relay rather than per adapter (FR-001 forbids
      an adapter deciding anything, and answer-or-not is a decision).

- [ ] T031 [US4] Full suite green: `uv run pytest -q`.

## Verification

- [ ] Final gate command passes green.
- [ ] The five 008 behavior-suite files are unedited in the diff.
- [ ] Two concurrent escalations, neither blocking the other, is a passing test.
- [ ] 039's env guard found the new workflow module and passed.
- [ ] No arbitration was added beside the store's guarded UPDATE.
- [ ] No lifecycle leaves a pending row, whichever channel answered (FR-013).
- [ ] `ergane build answer` and `ergane build resolve` work post-migration and
      settle their rows (T020a).
- [ ] The RETRY defect is characterized with the finding key, not fixed (T020b).
