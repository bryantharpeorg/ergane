# Tasks: a message is a decision, not a log line

Read `plan.md` before starting. Seven traps decide whether this lands. Trap 3
names **seven** landed sites that assert the behaviour US1 reverses, all in the
two test files US1 already edits — meeting them by surprise ends in either
shipping nothing or deleting a guarantee this spec keeps, and an earlier draft of
that trap named only three. Trap 5 is the reason US1 exists at all: the composer
receives a bare string, so the cause must be named where the failure is reported,
and a diff that pattern-matches on exception text repeats a mistake this tree has
already refused once. Trap 9 is the one that passes green and breaks the
operator: a column added to a `CREATE TABLE IF NOT EXISTS` never reaches a
database that already exists. Trap 14 is the one that would eat US2's whole diff:
the 113 command sweep reads markdown code spans and a notice is plain text, so
`extract_commands` finds nothing in one and making it find something puts
backticks on the operator's phone. Trap 15 is the one that ends with a silent
phone: record per spec while sending one notice and the cause-keyed count reaches
63 in a single pass, which the geometric throttle answers by sending nothing at
all. Trap 17 is the one that goes green and is still unrunnable: a specs-root
positional rendered as `<specs-root>` parses. Trap 18 is the one that lands in
US1 and is only paid for in US2: the reporting site is not the cause, because
one site raises both a fault that clears itself and one that never did, so a
cause vocabulary minted per site makes FR-010 unsatisfiable honestly.

The spec's rule section carries the only enumeration of message kinds. Two are
**changed** — `roadmap_failure_notice` and `roadmap_recovery_notice`. Two are
**controls** and must come out of the diff byte-identical — `escalation_message`
and `question_message`. Three are **out of scope** — `resolution_notice`, the
stack heartbeat, and `manual_intervention_notice`, which has no production caller
at all (plan § "`manual_intervention_notice` is dead code"). Where a task below
says "every notice", it means the two changed ones.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence — notice counts, before-and-after message text — is
committed as pasted output, never described.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A failure notice says what stopped and what it blocks

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 1) Compose a roadmap failure
      notice for a pass that failed with `'NoneType' object has no attribute
      'epic_state'` and assert the text names the stage that stopped in factory
      vocabulary, still names the consecutive-failure count, and does **not**
      contain that string. Use that exact input; it is the string that failed a
      human twice.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert the same notice states what
      will not happen until the failure is resolved, and that a notice built for
      a cause that affected several specs in one pass names how many.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 4) Assert a cause the composer
      has no specific wording for still yields impact and options plus a pointer
      to where the verbatim text is recorded, and that the failure text is not
      the body.
- [ ] T004 [P] [US1] (spec US1-S4, FR-004, trap 2) **The pair.** In one test,
      report a failure, assert the composed notice omits the exception repr,
      and read the `roadmap_failures` row that same report wrote to assert
      `last_failure_text` still holds the repr verbatim. The record half passes
      today, so only the pair can fail a diff that cleaned the page by dropping
      the evidence.
- [ ] T005 [P] [US1] (spec US1-S5, FR-005, trap 4) Split a composed failure
      notice into lines and assert all three of the impact line, the options
      block and the pointer to the `roadmap_failures` record are present, and
      that their indices are in that order. Assert all three: once FR-001 lands
      there is no failure detail in the notice, so an ordering claim written
      against "any line carrying failure detail" compares against an empty set
      and passes on a notice that dropped one of the three.
- [ ] T006 [P] [US1] (spec US1-S6, FR-006, trap 2) **The second pair.** Report a
      failure whose text is a shell stderr tail carrying a value matching
      `_SECRET_PATTERNS`; assert neither the tail nor the value appears in the
      composed notice, **and** that the `roadmap_failures` row that same report
      wrote still holds both. Import the patterns from
      `factory/controlplane/config.py:80` (`_SECRET_PATTERNS`) the way
      `tests/test_readme.py:24` does rather than restating them. The notice half
      fails today; the row half passes today; only the pair refuses a diff that
      protected the credential by dropping the record.
- [ ] T007 [P] [US1] (spec US1-S7, FR-007, trap 5) Assert two different failure
      texts reported under one named cause share an impact statement, and one
      failure text reported under two different named causes does not. Both
      directions in one test: a composer that classified by matching the failure
      text passes neither.

### Implementation for this story

- [ ] T008 [US1] (FR-007, trap 5) Give a reported failure a named cause that
      travels as a value, and name it at each of the three reporting sites:
      `factory/roadmap/workflow.py:1082` — `_report_run_failure`, the
      unreadable-child-result path at `factory/roadmap/workflow.py:909` —
      `_run_inner`, and the drift degrade path at
      `factory/roadmap/workflow.py:1387` — `_drift_resolver`. Thread it through
      `factory/roadmap/workflow.py:1044` — `_report_roadmap_failure`. One cause
      per site is too coarse and US2 cannot recover from it: `_drift_resolver`
      raises both a fault that clears itself and one that does not, so decide the
      cause from the exception's type and its `FailureError` chain the way
      `factory/roadmap/workflow.py:1438` — `_derivation_detail` already does, and
      never from its text (traps 5 and 18).
- [ ] T009 [US1] (FR-001, FR-002, FR-005, trap 16) Give the notice a structure —
      impact, options, pointer to the record — and compose it in that order in
      `factory/notify/messages.py:329` — `roadmap_failure_notice`, including a
      field for how many specs one cause affected in the pass (US3 fills it;
      this story only has to carry it). Decide where those three lines sit:
      `factory/notify/messages.py:656` — `_compose` clips the *body* from the
      front at `factory/notify/messages.py:663-666`, so either put them in the
      footer the way 079-US4 put the blast radius there, or keep the body
      bounded by construction — a count, never a rendered list of affected spec
      names. Rewrite the docstring: its promise to carry the failure text
      verbatim is the decision being reversed.
- [ ] T010 [US1] (FR-003, trap 4) Give the unknown-cause path the same
      structure, with a pointer to the `roadmap_failures` record — never the raw
      text as the body.
- [ ] T011 [US1] (FR-006, trap 4) Make the pointer name the record rather than
      quote it: no span of the failure text may be rendered into the notice on
      any path, known cause or unknown. A filter that strips
      secret-shaped values out of a rendered failure text is the wrong shape —
      it leaves every other failure text on the phone and makes FR-001 depend on
      a regex; removing the text is what satisfies both.
- [ ] T012 [US1] (FR-004, trap 2) Leave `_report_roadmap_failure`'s
      record-before-send ordering intact and keep `failure_text` on
      `RecordRoadmapFailureInput`. The notice stops printing it; the row does
      not stop holding it.
- [ ] T013 [US1] (FR-001, FR-006, trap 3) Update **all seven** landed sites that
      assert the reversed behaviour, deliberately and in this diff. There are
      seven, not three, and they are all in the two files this story already
      edits:
      (1) `tests/test_roadmap_failure_notifications.py:406` — `test_a_failed_run_notifies_once_with_the_failure_verbatim`,
      asserting at `tests/test_roadmap_failure_notifications.py:422`;
      (2) `tests/test_messages.py:282` — `test_roadmap_failure_notice_carries_failure_text_and_count`,
      asserting at `tests/test_messages.py:286`;
      (3) `tests/test_roadmap_failure_notifications.py:176` — `_failure_count_from`,
      whose four call sites at `:571`, `:654`, `:701` and `:702` must keep
      parsing the count out of the new phrasing;
      (4) `tests/test_roadmap_failure_notifications.py:547` — `test_schedule_churned_ids_accumulate_one_count_and_page_geometrically`,
      whose own verbatim assertion is at `:575`, below those count assertions;
      (5) `tests/test_roadmap_failure_notifications.py:835` — `test_clean_run_under_sandbox_with_prior_failure_reaches_completed`,
      asserting at `tests/test_roadmap_failure_notifications.py:862`;
      (6) `tests/test_roadmap_failure_notifications.py:892` — `test_failed_run_sends_notice_and_workflow_fails_with_original_exception`,
      asserting at `tests/test_roadmap_failure_notifications.py:913`. In (1),
      (2), (4), (5) and (6) the verbatim assertion goes and the delivery and
      count assertions beside it stay, and (3) is re-taught rather than deleted; in (6) leave the exception-chain assertion at
      `tests/test_roadmap_failure_notifications.py:907` alone, because the
      workflow must still raise what the notice stops printing. Rewrite their
      intent; do not delete the count guarantee with the repr. Leave
      `tests/test_roadmap_failure_notifications.py:495` — `test_failure_is_recorded_when_notifier_is_down`
      green as it stands: its assertion at
      `tests/test_roadmap_failure_notifications.py:532` reads the stored row,
      which FR-004 keeps. Site (7) is the one that needs a decision rather than a
      deletion:
      `tests/test_roadmap_failure_notifications.py:988` — `test_unreadable_child_result_records_failure_and_notifies`
      asserts `"001-alpha" in call.message and "could not read" in call.message`
      at `tests/test_roadmap_failure_notifications.py:1024`, and that is the text
      of the second reporting site T008 changes,
      `factory/roadmap/workflow.py:909` — `_run_inner`. `"could not read"` is a
      span of the failure text, which FR-006 keeps out of every notice, so assert
      the **named cause** that site now passes as a value instead. Keep
      the `"001-alpha"` half only if the reporting site passes the spec dir as a
      value alongside the cause; otherwise assert the affected-spec count FR-002
      gives the notice. Never assert a substring of the failure text.

### Verification for this story

- [ ] T014 [US1] Paste, as committed evidence, the before-and-after text of all
      four messages quoted in the spec's frontmatter, composed by the old and
      new code, as pasted tool output in the diff (traps 1, 13).
- [ ] T015 [US1] Paste, as committed evidence, the `roadmap_failures` row read
      back for the run whose notice omits the repr, showing `last_failure_text`
      unchanged (trap 2).

## Phase 2: User Story 2 — Every notice states the options and what silence does

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US2] (spec US2-S1, FR-008) Compose the two changed notice kinds
      by name — `roadmap_failure_notice` and `roadmap_recovery_notice` — and
      assert each names its options as actions an operator can take, or says in
      one line that there is nothing to decide. Do not write the test as a loop
      over every public composer in the module: `question_message` and
      `escalation_message` are controls, and `resolution_notice` and
      `factory/notify/messages.py:313` — `manual_intervention_notice` are out of
      scope, so a loop drags all four in — and the last of those is a composer
      nothing in production calls, so a line added to it reaches no operator.
- [ ] T017 [P] [US2] (spec US2-S2, FR-009) Assert the roadmap failure notice
      states what happens if the operator does nothing, and that the recovery
      notice carries exactly one nothing-to-decide line and no second sentence
      about silence — its cause has already cleared, so there is nothing for
      silence to cost.
- [ ] T018 [P] [US2] (spec US2-S3, FR-010, trap 18) Assert a notice for a cause
      that will not clear itself says so, and a notice for a cause the next
      scheduled pass retries names that mechanism rather than a wall-clock time.
      Drive both causes out of the same reporting site — the hook refusal that
      arrives as a non-retryable `ApplicationError` and the timeout on the same
      `drift_for_spec` call — because a test that took one cause per site would
      pass on a vocabulary in which trap 18 says the answers collide.
- [ ] T019 [P] [US2] (spec US2-S4, FR-011, traps 12, 14, 17) In a new test
      module, collect the `ergane` invocations the two changed composers declare
      as values, assert the collected set is not empty, parse every one with
      `tests/page_holds_true.py:180` — `parse_argv`, assert each one's rendered
      form appears verbatim in the notice that declared it, and assert no
      rendered form contains an angle-bracket placeholder — `<specs-root>` is
      absent from `tests/page_holds_true.py:163` (`_PLACEHOLDER_VALUES`) and
      argparse accepts any string for a positional, so the placeholder passes the
      parse check and cannot be typed. Copy the
      parse half of `tests/test_claude_md.py:57` (`COMMANDS`) and **not** the
      extraction half: `tests/page_holds_true.py:301` — `extract_commands` and
      `tests/page_holds_true.py:292` — `assert_commands_not_dropped` read
      markdown code spans and return nothing over plain notice text. Never a
      second CLI parser, and never `--help` subprocesses.
- [ ] T020 [P] [US2] (spec US2-S5, FR-009, FR-011, FR-012, traps 6, 7) **The
      controls ride with the change.** In one test assert the escalation still
      carries its blast-radius block and its "No answer by …" sentence unchanged,
      that `question_message` still carries "Reply to this message with your
      answer" and "No answer by … lets the node proceed as a FAIL" unchanged,
      **and** that the roadmap failure notice now carries the silence sentence
      T023 adds and at least one command line rendered from a declared
      invocation (T024), while still naming no button, no offered choice and no
      deadline. Check what each half proves before writing it: the two control
      halves are satisfied on this story's base, and so are the options block
      US1 landed under FR-003 and FR-005 and the no-keyboard half that
      `tests/test_messages.py:290` — `test_roadmap_failure_notice_offers_nothing_and_names_no_deadline`
      has asserted since 031. Only the silence sentence and the rendered command
      are US2's own, so an assertion set without them is green the moment it is
      written and this task's heading is a lie.
- [ ] T021 [P] [US2] (spec US2-S6, FR-013) Assert a recovery notice names what
      resumed, not only that recovery happened.

### Implementation for this story

- [ ] T022 [US2] (FR-008) Add an options block to the one changed composer that
      does not have one — `factory/notify/messages.py:344` —
      `roadmap_recovery_notice` — as commands the operator runs, or one line
      saying there is nothing to decide. `factory/notify/messages.py:329` —
      `roadmap_failure_notice` arrives with an options block already: US1 built
      it under FR-003 and FR-005, as literal text. Do not add a second one —
      T024 re-renders those same lines from the declared invocations it
      introduces and T023 adds the silence sentence beneath them, so the three
      tasks are one change to one block, not three blocks.
      Touch no other composer, and in particular not
      `factory/notify/messages.py:313` — `manual_intervention_notice`: nothing in
      production calls it, so every line added to it is diff spent on a message
      no operator receives.
- [ ] T023 [US2] (FR-009, FR-010, trap 7) Add the silence sentence to
      `roadmap_failure_notice`, keyed on the cause US1 landed: whether it clears
      itself, and what retries it if it does. Phrase it without the escalation's
      deadline words, which `tests/test_messages.py:290` refuses in a roadmap
      notice for a reason. `roadmap_recovery_notice` gets no silence sentence —
      its nothing-to-decide line is the answer. Do **not** apply the phrasing to
      `factory/notify/messages.py:484` — `question_message`: its sentence landed
      with 008-US1, FR-012 holds it byte-identical, and T020 fails if it moves.
- [ ] T024 [US2] (FR-011, traps 14, 17) Hold each `ergane` invocation a changed
      notice names as an argv value on the composer and render the notice line
      from it, so the text an operator reads and the argv the test parses cannot
      drift. Derive the `specs_root` positional every roadmap verb takes from the
      `roadmap_id` the composer already has, by stripping `ROADMAP_ID_PREFIX`
      from it: plan trap 17 carries both anchors and the arithmetic, and the
      basename that falls out is the spelling an operator types from the
      repository root. Not a placeholder, which parses and cannot be typed, and
      **not** a new composer parameter — trap 17 names what a new parameter
      drags into this story's diff, and this story reads no file outside
      `factory/notify/messages.py`. No markup either: the notice ships as plain
      text and Telegram renders it literally, so a backticked command shows the
      operator backticks.
- [ ] T025 [US2] (FR-013) Make `roadmap_recovery_notice` say what resumed.
- [ ] T026 [US2] (FR-012, trap 6) Leave both controls untouched:
      `factory/notify/messages.py:414` — `escalation_message`,
      `factory/notify/messages.py:358` — `render_blast_radius`, the effects table
      at `factory/notify/messages.py:134` (`_CHOICE_EFFECTS`), and
      `factory/notify/messages.py:484` — `question_message`. Leave
      `factory/notify/messages.py:502` — `resolution_notice` and
      `factory/notify/messages.py:313` — `manual_intervention_notice` alone as
      well; both are out of scope. If a shared helper is extracted, both
      controls' rendered text must be byte-identical.

### Verification for this story

- [ ] T027 [US2] Paste, as committed evidence, every composed notice kind in
      full — the two changed and the two controls — so the options block and
      the silence sentence can be read rather than inferred from assertions, and
      so the controls can be compared against the pre-change text by eye.
- [ ] T028 [US2] Paste, as committed evidence, the list of `ergane` invocations
      the two changed composers declared and the notice line each was rendered
      into, proving the check is not vacuous, that every rendered form is
      typeable rather than a `<specs-root>` placeholder (trap 17), and that no
      backtick reaches the operator (trap 14).

## Phase 3: User Story 3 — One cause is one message

### Tests for this story (write FIRST, must fail)

- [ ] T029 [P] [US3] (spec US3-S1, FR-014, trap 10) In
      `tests/test_roadmap_failure_notifications.py`, drive a multi-spec corpus
      through one pass in which one cause fails every spec with texts differing
      only by spec name, and assert the operator received exactly **one** notice
      naming how many specs were affected. The 2026-08-19 fetch fault is the
      fixture: 63 notices in six minutes.
- [ ] T030 [P] [US3] (spec US3-S2, FR-015, traps 8, 9, 15) In one test assert
      both halves. First: after the single pass of T029, the `roadmap_failures`
      row's `consecutive_count` is exactly **1** — the guard against a record
      left inside the per-spec loop, which drives it to 63 and makes
      `_should_notify_failure` send nothing. Then: with the same cause persisting
      across two further passes whose failure texts differ, the count rises 1, 2,
      3 instead of resetting, and the notices fall to the geometric throttle's
      rate. Create the old `roadmap_failures` table first, then call the
      activity, so the test proves the migration path and not just a fresh store.
- [ ] T031 [P] [US3] (spec US3-S3, FR-016, trap 11) Drive one pass in which most
      specs fail on one cause and at least one fails on another, and assert
      exactly two notices were sent, one per cause. Today this pass sends one
      notice per spec, so the assertion fails before the change and a naive
      collapse fails it after.

### Implementation for this story

- [ ] T032 [US3] (FR-014, FR-016, trap 10) Accumulate the pass's causes in
      `factory/roadmap/workflow.py:1387` — `_drift_resolver` instead of
      reporting from inside the loop, and report once per distinct cause when
      the loop `factory/roadmap/workflow.py:1398` — `_compute_drift` drives ends,
      passing the affected spec count into the field US1 landed.
- [ ] T033 [US3] (FR-015, trap 8) Key the consecutive count on the named cause
      rather than the failure text in `factory/activities/notify_activities.py:680` — `record_roadmap_failure`.
      Leave `factory/roadmap/workflow.py:152` — `_should_notify_failure` alone;
      the geometric throttle was never the defect.
- [ ] T034 [US3] (FR-015, trap 9) Add the column the cause key needs with an
      additive migration — `PRAGMA table_info`, then `ALTER TABLE … ADD COLUMN`
      when it is missing — modelled on `factory/verify/store.py:556` — `_migrate`.
      Do **not** add it to `factory/activities/notify_activities.py:606`
      (`_ROADMAP_FAILURES_DDL`): `CREATE TABLE IF NOT EXISTS` is a no-op against a
      database that already exists.
- [ ] T035 [US3] (FR-014, FR-004, trap 15) Keep the record-before-send ordering
      on the folded report: each distinct cause writes its `roadmap_failures`
      update once per pass, before its notice is sent, so `last_failure_text` and
      the count keep being written exactly as FR-004 requires. Do **not** leave
      the record call inside the per-spec loop while folding only the send — the
      cause-keyed count then reaches 63 in one pass and the throttle answers with
      silence. A per-failure history table is out of scope: the store is
      `roadmap_id TEXT PRIMARY KEY`, one row per roadmap, and FR-015 permits only
      an additive `ADD COLUMN`.

### Verification for this story

- [ ] T036 [US3] Paste, as committed evidence, the notice count for a full
      corpus pass under one cause, before and after — the 63-to-1 measurement —
      together with the `roadmap_failures` row after that pass showing
      `consecutive_count` at 1 (trap 15).
- [ ] T037 [US3] Paste, as committed evidence, the `roadmap_failures` rows after
      three consecutive passes whose texts differ and whose cause does not,
      showing the count rising instead of resetting.

## Verification

- [ ] T038 The full gate command passes green.
- [ ] T039 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 3 (replay the flood) is the falsifiable
      test of US3 and step 4 (replay the wedge) of US1 and US2 together; they are
      the two outages of 2026-08-19 run forwards.
- [ ] T040 Count total operator-channel message volume over a normal day, before
      and after. If it rose, the spec failed regardless of what the suite says
      (spec § "What this spec is not").
