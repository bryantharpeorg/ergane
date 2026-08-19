# Tasks: a message is a decision, not a log line

**Spec**: `specs/066-a-message-is-a-decision-not-a-log-line/spec.md`
**Plan**: `specs/066-a-message-is-a-decision-not-a-log-line/plan.md`

Read the plan's traps first. Trap 1 (the screenshot is the acceptance test),
trap 3 (a raw-text fallback has changed nothing) and trap 5 (options are
actions) are the three that decide whether this lands.

## Phase 1: User Story 1 — A failure message says what stopped and what it blocks

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) Assert a notice rendered from the failure text
      `'NoneType' object has no attribute 'epic_state'` states what has stopped
      in factory vocabulary and does **not** contain that string. Use that exact
      input: it is the one that actually failed a human, twice.
- [ ] T002 [P] [US1] (spec US1-S2) Assert the notice states the blast radius — what
      will not happen until it is resolved.
- [ ] T003 [P] [US1] (spec US1-S3) Assert an unrecognised internal failure still
      produces an impact-and-options notice carrying a pointer to the verbatim
      text, rather than degrading to the raw text (trap 3).
- [ ] T004 [P] [US1] (spec US1-S4) Assert the verbatim text is still recorded in
      `roadmap_failures` and is retrievable (trap 2).
- [ ] T005 [P] [US1] (spec US1-S5) Assert the impact and options appear before any
      detail in the rendered string.
- [ ] T006 [P] [US1] (spec Edge Cases) Assert a failure text containing a
      secret-shaped value is not rendered into the notice, reusing
      `_SECRET_PATTERNS` from `factory/controlplane/config.py`.

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002, FR-005) Give a notice a structure — impact,
      options, detail — and render it in that order. `roadmap_failure_notice`
      (`factory/notify/messages.py:273`) is the composer that produced every
      message in the operator's screenshot; its docstring's promise to carry the
      failure text verbatim is the decision being reversed, so update the
      docstring too.
- [ ] T008 [US1] (FR-003) Give the unrecognised-failure path the same structure,
      with a pointer to where the verbatim text can be read (trap 3).
- [ ] T009 [US1] (FR-004) Leave `_report_roadmap_failure`'s record-before-send
      ordering (`factory/roadmap/workflow.py:955`) intact (trap 2).

## Phase 2: User Story 2 — Every message states the options and what silence does

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) Assert every operator-facing notice kind names its
      options as actions an operator can take (trap 5).
- [ ] T011 [P] [US2] (spec US2-S2) Assert every notice kind states what happens on
      silence. `escalation_message` (`:302`) already does; this generalises it
      and must not regress it (trap 4).
- [ ] T012 [P] [US2] (spec US2-S3) Assert a notice for a condition that will not clear
      itself says so explicitly.
- [ ] T013 [P] [US2] (spec US2-S4) Assert a notice for a retrying condition states when
      it will retry.
- [ ] T014 [P] [US2] (spec US2-S5) Assert every command any notice names resolves,
      reusing `tests/page_holds_true.py`'s helpers — never a second sweep
      (trap 6).

### Implementation for this story

- [ ] T015 [US2] (FR-006, FR-007) Add options and silence-default to every composer
      in `factory/notify/messages.py`: `manual_intervention_notice` (:257),
      `roadmap_failure_notice` (:273), `roadmap_recovery_notice` (:288),
      `question_message` (:337), `resolution_notice` (:355).
- [ ] T016 [US2] (FR-008) State self-clearing and retry timing where they apply.
- [ ] T017 [US2] (FR-009) Ensure every command named is one the CLI resolves
      (trap 6).

## Phase 3: User Story 3 — One cause is one message

### Tests for this story (write FIRST, must fail)

- [ ] T018 [P] [US3] (spec US3-S1) In `tests/test_roadmap_failure_notifications.py`,
      drive one fault across a full corpus pass with texts differing only by
      spec name and assert the operator receives **one** notice naming the
      affected count. The 2026-08-19 fetch fault is the fixture: 63 messages in
      six minutes.
- [ ] T019 [P] [US3] (spec US3-S2) Assert repetition across consecutive passes is
      throttled — that `_should_notify_failure`'s count now rises instead of
      resetting to one on every spec (trap 7).
- [ ] T020 [P] [US3] (spec US3-S3) Assert two genuinely different faults in one pass are
      both reported (trap 8).
- [ ] T021 [P] [US3] (spec US3-S4) Assert a recovery notice states what resumed, not
      only that recovery happened.

### Implementation for this story

- [ ] T022 [US3] (FR-010, FR-011) Key the consecutive-failure count on the cause
      rather than the rendered text, and fold one pass's identical causes into a
      single notice at the call site (`factory/roadmap/workflow.py:1281`). Leave
      the geometric throttle at `:139` alone — it was never the defect (trap 7).
- [ ] T023 [US3] (FR-012) Keep distinct causes distinct (trap 8).
- [ ] T024 [US3] (FR-013) Make `roadmap_recovery_notice` (:288) say what resumed.

## Verification

- [ ] T025 (SC-001) Re-render all four messages from the 2026-08-19 screenshot,
      quoted verbatim in the spec's frontmatter, and **paste the before-and-after
      of each into the diff** (traps 1, 11).
- [ ] T026 (SC-002) Hand one rendered notice to someone who does not maintain
      Ergane and confirm they can say what stopped and what their choices are.
- [ ] T027 (SC-003) Replay the fetch fault across a full corpus pass and count the
      notices. 63 before; the target is one.
- [ ] T028 (SC-004) Confirm no notice names a command that does not resolve.
- [ ] T029 Count total message volume over a normal day, before and after. If it
      rose, the spec failed regardless of the suite (trap 10).
