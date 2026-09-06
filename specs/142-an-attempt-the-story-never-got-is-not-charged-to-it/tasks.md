# Tasks: an attempt the story never got is not charged to it

Read `plan.md` before starting. Two of its traps decide whether this spec is
worth anything. Trap 1: the accounting function is **not** called
`charged_attempts` — that name appears in the ledger rows and in no source file;
it is `factory/verify/ladder.py:368` — `_attempts_spent`, and reusing its
`pre_agent` flag would page the operator about a credential that is fine. Trap 2:
both boundary refusals exit 127, and so does a gate command whose own binary is
missing — a branch on the exit code excuses the failure this factory most needs
to keep charging. Two more decide whether it works at all. Trap 13: **removing
`bwrap` does not reproduce this defect** — `factory/verify/gates.py:1346` —
`_resolve_gate_executor` falls back to `SubprocessGateExecutor`, so build the
refusal by constructing `BwrapGateExecutor` directly, and drive the toolchain arm
rather than the missing-binary one. Trap 14: **there are three sites that append a
verification-derived `AttemptRecord`**, not one. Trap 5 is why US2 is one story and
not two.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A boundary that never started is not a gate that failed

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, traps 2 and 13) Given a gate boundary
      that refused before running the command, assert the executor's outcome
      carries a field of its own saying the command never started. **Construct
      `factory/verify/gates.py:543` — `BwrapGateExecutor` directly.** Do not go
      through `resolve_gate_executor`: with the binary pointed at nothing it
      returns a `SubprocessGateExecutor` (`factory/verify/gates.py:1364`), which is
      what `tests/test_101_declared_caches.py:366` does and why that route proves
      nothing here. Drive both arms — the missing binary
      (`factory/verify/gates.py:583`) with `monkeypatch.setattr(gates_module,
      "BWRAP_BACKEND_BINARY", ...)` pointed at a path that does not exist, and the
      toolchain refusal (`factory/verify/gates.py:605`) the way
      `tests/test_toolchain_discovery.py:287` —
      `test_a_missing_tool_is_absent_rather_than_guessed` drives it, by emptying
      `_SYSTEM_FALLBACK_DIRS` on a planted host. `PlantedHost` is a module-local
      helper class rather than a pytest fixture
      (`tests/test_toolchain_discovery.py:131` — `PlantedHost`), so import it
      from that module. The second
      is the arm production reaches. No existing test asserts either; the only
      place the missing-binary form is written down is a hand-run recipe in a
      docstring (`tests/test_sandbox_mount_set.py:133`). Assert the field, never
      the exit code.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 3) Given an outcome flagged as
      never started, assert `factory/verify/gates.py:1583` — `_to_result` returns a
      status distinct from `FAIL`, `TIMEOUT`, `CONFIG_ERROR` and
      `DIRTIED_WORKTREE`, and that the result keeps the boundary's refusal text and
      exit code 127.
- [ ] T003 [P] [US1] (spec US1-S3, FR-001, trap 2) **The control that matters
      most.** Given a gate command that ran and exited 127 of its own accord,
      assert the result is `FAIL`, byte-identical to today. Put it in the same test
      as T002's never-started case so the pair, and only the pair, fails a diff
      that branched on `outcome.exit_code == 127`.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, trap 4) Given a result list holding only
      the never-started status, assert `factory/verify/models.py:950` —
      `gates_passed` is False and the composed verdict is FAIL. Also assert `PASS`,
      `FAIL`, `TIMEOUT`, `CONFIG_ERROR` and `DIRTIED_WORKTREE` still produce exactly
      the verdicts they produce today, so this story cannot move a verdict it is
      not about.
- [ ] T005 [P] [US1] (spec US1-S5, FR-004, trap 3) Given result lists holding, in
      turn, the never-started status, a `FAIL`, a `CONFIG_ERROR` and **no gate
      results at all**, assert the new predicate answers "the boundary never ran"
      for the first only. Two of the four decide the predicate's shape. The
      `CONFIG_ERROR`: an unusable manifest is a fact about the worktree the agent
      has just been editing. The empty list: a predicate shaped `all(result never
      started)` answers "never ran" over zero results and hands that attempt a
      free rung, where `factory/verify/gates.py:1620` says this module fails
      closed wherever the evidence is missing.
- [ ] T006 [P] [US1] (spec US1-S6, FR-004, trap 3) Given a list holding one
      never-started result **and** one `FAIL` from a gate that ran, assert the
      predicate answers "it ran". Put it in the same test as T005: a predicate
      written `any(status is never-started)` passes T005 and fails only this, and
      that mutation hands a genuine gate failure a free, uncharged retry.

### Implementation for this story

- [ ] T007 [US1] (FR-001, trap 2) Add the field to `factory/verify/gates.py:273` —
      `ExecutionOutcome`, defaulting to "the command started" so every existing
      construction keeps today's meaning, and set it at the two boundary refusals:
      `factory/verify/gates.py:583` (sandbox binary missing) and
      `factory/verify/gates.py:605` (`ToolchainError` out of `_build_argv`).
- [ ] T008 [US1] (FR-002, trap 3) Add the new member to
      `factory/verify/models.py:73` — `GateStatus`, beside the five at
      `factory/verify/models.py:93-97`, and document in its docstring why
      `CONFIG_ERROR` (`factory/verify/models.py:76`,
      `factory/verify/factory_yaml.py:1103`) is not this and must stay charged.
- [ ] T009 [US1] (FR-002, trap 2) Branch in `factory/verify/gates.py:1583` —
      `_to_result` on the outcome's new field, **above** the non-zero-exit arm at
      `factory/verify/gates.py:1625`, keeping the exit code and the output tail. Do
      not touch any executor: the module's own comment at
      `factory/verify/gates.py:1645` says this is the single line every backend's
      outcome passes through.
- [ ] T010 [US1] (FR-003, FR-004, trap 4) Add the predicate beside
      `factory/verify/models.py:950` — `gates_passed`, comparing status **by
      value** as `factory/verify/models.py:958` requires, and leave `gates_passed`
      itself unedited. Confirm by reading that no consumer needed a branch:
      `factory/notify/messages.py:536`, `factory/verify/judge.py:441` and
      `factory/workgraph/prompt.py:868` all key off `PASS`.

### Verification for this story

- [ ] T011 [US1] Paste, as committed evidence, the composed gate result for a
      boundary that never started and for a command that ran and exited 127, side
      by side, showing the two different statuses and the identical exit code.

## Phase 2: User Story 2 — The ladder does not spend a rung on a verdict that measured nothing

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-005, FR-006, trap 1) Given an attempt whose
      gate results say the boundary never ran, assert the appended
      `factory/verify/models.py:1245` — `AttemptRecord` carries the new reason field
      naming the boundary, that `pre_agent` is still False, and that
      `factory/verify/ladder.py:393` — `pre_agent_failures_spent` reads zero over
      that history. Assert the last one rather than a termination:
      `factory/verify/models.py:1245` — `AttemptRecord` carries no termination
      field, and the pre-agent counter is what actually fires the credential
      escalation trap 1 is guarding against.
- [ ] T013 [P] [US2] (spec US2-S2, FR-005, trap 6) Given three such records and an
      ordinary allowance of three, assert `factory/verify/ladder.py:368` —
      `_attempts_spent` still reads zero and `factory/verify/ladder.py:270` —
      `exhausted_bound` returns `None`. Assert through `exhausted_bound`, not
      through `next_action`'s return value: `next_action` returns the same
      `ESCALATE` whichever bound fired, so only `exhausted_bound` can prove the
      ordinary allowance was not what stopped the node. This is also the test that
      fails if the new dial was defaulted at or below `max_attempts`.
- [ ] T014 [P] [US2] (spec US2-S3, FR-005) Given a history of one boundary refusal,
      one ordinary FAIL and one more boundary refusal, assert `_attempts_spent`
      counts exactly one — the exclusion is a property of each record, the way
      `factory/verify/ladder.py:380` says it is for `pre_agent`.
- [ ] T015 [P] [US2] (spec US2-S4, FR-007, trap 5) Given consecutive boundary
      refusals reaching the declared limit, assert `next_action` returns ESCALATE
      rather than RETRY **and** that `factory/verify/ladder.py:270` —
      `exhausted_bound` names the new dial rather than `max_attempts`. Without this
      the exclusion is a starvation defect —
      `factory/verify/ladder.py:220-229` makes the same argument for the pre-agent
      limit.
- [ ] T016 [US2] (spec US2-S5, FR-008, trap 1) Given that escalation, assert over
      the composed string that `factory/verify/ladder.py:270` — `exhausted_bound`
      names the new dial and the boundary and mentions neither the credential nor
      `max_pre_agent_failures`. Assert the fail-safe default separately, over the
      call rather than the string: `factory/workgraph/workflow.py:2146-2152`
      passes `default_choice` to `_escalate`, so it appears in no composed
      sentence and a test that looked for it there would push the implementer to
      write it into the note text. Not `[P]`: it reads the same composed record
      two tasks build.
- [ ] T017 [P] [US2] (spec US2-S6, FR-007, trap 6) Given one manifest declaring the
      new ladder dial and one declaring none, assert the first parses and carries
      the declared value while the second parses to the shipped default. Both halves
      in one test: the default half passes today, before any change, so only the
      pair can fail a diff that added the dial to the dataclass and to no
      registration. The default half also pins the shipped value: FR-007 fixes it
      above the default `max_attempts` of 3, for the reason
      `factory/verify/models.py:1206` gives for `max_pre_agent_failures`.
- [ ] T018 [US2] (spec US2-S7, FR-013, trap 14) Given a node driven to a **clean
      re-sync recovery** whose scripted gate results say the boundary never ran,
      assert the record appended at `factory/workgraph/workflow.py:4017` — inside
      `factory/workgraph/workflow.py:3879` — `_recovery_attempt` — carries the same
      reason field the ladder loop's record carries, and that the ordinary
      allowance does not move. Copy the fixture at
      `tests/test_rung_resolves_its_own_model.py:183` —
      `test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model`, whose
      scripted world already drives that path; `tests/test_interpreter.py:688` —
      `scored` takes the `gates=` list this needs. Not `[P]`: it drives a
      `WorkflowEnvironment` rather than calling the ladder. This is the test a
      one-site fix fails.
- [ ] T018b [US2] (spec US2-S8, FR-013, trap 14) Given a node the ladder has
      already exhausted whose branch the operator hands back, and whose scripted
      gate results for that hand-back say the boundary never ran, assert the
      record appended at `factory/workgraph/workflow.py:2885` — inside
      `factory/workgraph/workflow.py:2837` —
      `_apply_external_completion_if_present` — carries the same reason field the
      ladder loop's record carries, and that the ordinary allowance counts only
      the genuine attempts before it. Copy
      `tests/test_external_completion.py:705` —
      `test_external_completion_fails_when_work_breaks_gates`: its
      `tests/test_external_completion.py:198` — `ConfigurableScript` already
      scripts gate results per attempt (`tests/test_external_completion.py:252` —
      `_fail_gate` is the entry to swap), the node is exhausted at
      `max_attempts=1` (`tests/test_external_completion.py:487`) so the hand-back
      is accepted, and the settled status carries the history
      (`factory/workgraph/workflow.py:895`). Not `[P]`: it drives a
      `WorkflowEnvironment`. T018 fails a diff wired to 2095 and 2885; this one
      fails a diff wired to 2095 and 4017. Nothing else here does.

### Implementation for this story

- [ ] T019 [US2] (FR-006, trap 9) Add **one** reason field to
      `factory/verify/models.py:1245` — `AttemptRecord` — empty meaning "charged" —
      with a named constant per reason, rather than a second boolean beside
      `factory/verify/models.py:1273`. US3 reuses this field; a flag per trigger
      would make five ways to ask one question.
- [ ] T020 [US2] (FR-005, trap 1) Exclude records carrying that reason in
      `factory/verify/ladder.py:389`, inside `factory/verify/ladder.py:368` —
      `_attempts_spent`, keeping the exclusion a property of the record so it holds
      where `config` is None. Do **not** set `pre_agent`
      (`factory/workgraph/workflow.py:2109`) for this case.
- [ ] T021 [US2] (FR-007, trap 5) Add the consecutive-tail counter and its limit
      predicate beside `factory/verify/ladder.py:393` — `pre_agent_failures_spent`
      and `factory/verify/ladder.py:410` — `pre_agent_bound_spent`, and consult the
      limit in `factory/verify/ladder.py:188` — `next_action` beside
      `factory/verify/ladder.py:228`.
- [ ] T022 [US2] (FR-007, trap 6) Register the dial in all three places:
      `_LADDER_KEYS` (`factory/verify/factory_yaml.py:144-151`), `_LADDER_BOUNDS`
      (`factory/verify/factory_yaml.py:157-164`) and the construction at
      `factory/verify/factory_yaml.py:888`, plus the field on
      `factory/verify/models.py:1181` — `VerificationConfig` beside
      `factory/verify/models.py:1215`. A dataclass default alone is refused as an
      unknown key the first time an operator writes it.
- [ ] T023 [US2] (FR-008) Add the branch to `factory/verify/ladder.py:270` —
      `exhausted_bound` beside the pre-agent branch at
      `factory/verify/ladder.py:311-321`, in the order `next_action` reaches them,
      naming the new dial and a remedy that is about the host's sandbox and not
      about a credential.
- [ ] T024 [US2] (FR-005, FR-008, FR-013, trap 14) Derive the reason **once**,
      from the composed result's `gate_results` through the predicate US1 added —
      never from an exit code and never from message text — and set it at **all
      three** sites that append a verification-derived `AttemptRecord`:
      `factory/workgraph/workflow.py:2095` (the ladder loop, beside the `pre_agent`
      flag at `factory/workgraph/workflow.py:2109`),
      `factory/workgraph/workflow.py:2885` (inside
      `factory/workgraph/workflow.py:2837` —
      `_apply_external_completion_if_present`) and
      `factory/workgraph/workflow.py:4017` (inside
      `factory/workgraph/workflow.py:3879` — `_recovery_attempt`). All three run
      the same gates through the same activity on the same host and all three write
      a persona `_attempts_spent` counts. Then extend the fail-safe default at
      `factory/workgraph/workflow.py:2146-2152` to the new limit.

### Verification for this story

- [ ] T025 [US2] Paste, as committed evidence, the ladder's decision over a history
      of consecutive boundary refusals — one line per record showing the reason
      field, the running ordinary-allowance count staying at zero, and the final
      ESCALATE — together with the exact `exhausted_bound` sentence it composed.

## Phase 3: User Story 3 — An answered question leaves a record, not a hole

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US3] (spec US3-S1, FR-009, trap 7) Given a node parked on an
      operator question that the operator answered, assert the history holds a
      record for the parked attempt whose reason field names the pause and whose
      verdict is `OverallVerdict.FAIL`. Today the history holds nothing for that
      attempt while `factory/workgraph/workflow.py:1815` has already advanced its
      number. Assert the verdict too: `AttemptRecord.verdict`
      (`factory/verify/models.py:1264`) has no default, and
      `factory/verify/ladder.py:209` reads a `PASS` as a landing.
- [ ] T027 [P] [US3] (spec US3-S2, FR-009) Given that history, assert
      `factory/verify/ladder.py:368` — `_attempts_spent` reads exactly what it read
      before the question, so obeying a stop-and-ask still costs no rung.
- [ ] T028 [US3] (spec US3-S3, FR-010, trap 8) **The control.** Given a node whose
      question expired unanswered, assert the FAIL record appended at
      `factory/workgraph/workflow.py:2040` is unchanged and still counted. Pin it in
      the same test as T026's answered path: the two branches sit four lines apart
      and 008-US2 charges the expiry on purpose. Not `[P]`: it drives both branches
      over one fixture.

### Implementation for this story

- [ ] T029 [US3] (FR-009, FR-010, traps 7 and 8) In the answered branch at
      `factory/workgraph/workflow.py:2058`, append an `AttemptRecord` carrying
      `OverallVerdict.FAIL` — the verdict the expiry branch four lines above
      already uses, and the one `factory/verify/ladder.py:209` forbids writing as
      `PASS` — together with the reason constant US2 added, and update the comment
      at
      `factory/workgraph/workflow.py:2053` which currently states the opposite. Do
      **not** touch the expiry branch above it and do **not** stop
      `factory/workgraph/workflow.py:1815` from incrementing the attempt number —
      that number is part of the evidence store's upsert key at
      `factory/verify/store.py:260`.

### Verification for this story

- [ ] T030 [US3] Paste, as committed evidence, one node's history across a question
      it answered and a question that expired — the first record uncharged and
      naming the pause, the second a charged FAIL — with the ordinary-allowance
      count printed beside each, in the shape `ergane build status --json` carries
      it (`factory/workgraph/workflow.py:895`), which is the only operator reading
      of this history (trap 12).

## Phase 4: User Story 4 — The escalation says how long each attempt took

### Tests for this story (write FIRST, must fail)

- [ ] T031 [P] [US4] (spec US4-S1, FR-011, trap 10) Given a verification result
      whose `factory/verify/models.py:937` and `factory/verify/models.py:938` differ
      by a known amount, assert `factory/notify/messages.py:529` —
      `_render_attempt` renders exactly that difference. Assert the rendered string,
      not a substring: any implementation that consults a wall clock produces a
      different number and fails this.
- [ ] T032 [P] [US4] (spec US4-S2, FR-012) Given four results whose first start and
      last finish are seven seconds apart, assert
      `factory/notify/messages.py:270` — `render_history` carries one further line
      stating that span.
- [ ] T033 [US4] (spec US4-S3, FR-012, trap 10) Given one result whose stored
      timestamps cannot be parsed **and** one whose can, assert the first renders
      with no elapsed clause and raises nothing while the second states its
      elapsed time. Put both in the same test as T031, the way T003 and T028 pin
      their controls: the omission asserted on its own passes a diff that renders
      no elapsed time anywhere. Not `[P]`: it reads the rendered history T031
      builds. This renderer is on the paging path; an exception here is a page
      that never arrives.

### Implementation for this story

- [ ] T034 [US4] (FR-011, trap 10) Render the per-attempt elapsed in
      `factory/notify/messages.py:531`, computed from the result's two stored
      timestamps and from no clock read. They are whole seconds with a `Z` suffix
      (`factory/workgraph/workflow.py:4371` — `_iso`), so parse defensively and
      return no line rather than raise.
- [ ] T035 [US4] (FR-012) Add the span line to `factory/notify/messages.py:270` —
      `render_history` when it holds more than one attempt, computed the same way.
      Keep it out of the single-attempt case, where it says nothing the attempt line
      does not.

### Verification for this story

- [ ] T036 [US4] Paste, as committed evidence, the rendered escalation history for
      four attempts spanning seven seconds and for four attempts spanning forty
      minutes, so the two pages read differently in the committed artifact.

## Verification

- [ ] T037 The full gate command passes green.
- [ ] T038 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Steps 1 and 4 read `ergane build status <epic>
      --json`, never `ergane build attempts` and never the rendered line, whose
      `attempt N` is the dispatch counter (trap 12). Step 1 is the one that must be
      run first and must be believed: with `bwrap` moved aside,
      `resolve_gate_executor` returns a `SubprocessGateExecutor` and nothing
      refuses, so that is not this defect (trap 13) — step 2 drives the toolchain
      arm instead. Step 3 is the falsifiable
      test of the whole spec:
      with `bwrap` present and a gate command pointed at a binary that does not
      exist, the node must still spend its rungs and still escalate on
      `max_attempts`. An implementation that branched on exit code 127 passes every
      other step and fails that one.
