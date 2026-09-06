# Tasks: a gate refusal names what refused

Read `plan.md` before starting. Four traps decide whether this spec works at all
and none of them fails a test you would write by default. Trap 1: the candidate
parser path is the one every Ergane node takes and it carries only the fields it
names, so a manifest key that stops at `FactoryConfig` — or one lifted off the
acceptance and never handed to the runner — is parsed, stored, emitted and never
read. Trap 6: a new import in `factory/workgraph/workflow.py` outside the
`workflow.unsafe.imports_passed_through()` block leaves a green suite and a dead
worker. Trap 7: there are four places an `AttemptRecord` is appended, the commit
you will read as the pattern populated two of them, and the fourth must stay empty
on purpose. Trap 12: this repository's own `ergane.yaml` must not declare the new
key — the worker parses a node's manifest with its own installed parser, and the
last story that tried died four times at `CONFIG_ERROR` in 0.0s.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The gate result records the checks that refused it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002, trap 5) Commit a fixture of
      real failure output from the recognised runner — pasted, not paraphrased —
      and assert that a non-zero-exit outcome carrying it becomes a `GateResult`
      whose recorded names are exactly the checks that summary printed, in the
      order printed.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 5) **The control that keeps the
      recogniser honest.** Assert that an outcome whose output matches no
      signature produces no names and an `output_tail` unchanged from the
      command's own output. Include at least one line containing the word
      "failed" in prose, so a diff that started guessing fails here.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) Assert a gate that exited zero and
      passed records no names, even when its output quotes a failure summary — a
      green suite that printed the word refused nothing.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, trap 3) Given output long enough that
      the recorded tail dropped its earlier lines, assert every recorded name
      appears literally in that result's own `output_tail`. Assert containment per
      name, not a count: the point is that the operator can find each name in the
      evidence the row carries.
- [ ] T005 [P] [US1] (spec US1-S5, FR-005) Assert the names round-trip through
      `factory/verify/store.py:1091` — `_gate_to_dict` and
      `factory/verify/store.py:1105` — `_gate_from_dict`, and that a stored row
      lacking the field reads back as empty with no other field moved.
- [ ] T006 [US1] (spec US1-S6, FR-003, traps 4 and 13) Drive the shipped
      `SubprocessGateExecutor` and one second backend through the same
      `factory/verify/gates.py:1511` — `_run_watched` seam over one failing fixture
      command, and assert both results carry the same names. **Neither half may
      carry `@pytest.mark.skipif(not BWRAP_PRESENT, ...)`**: sixteen bwrap-guarded
      tests already skip on the host this gate runs on
      (`tests/test_sandbox_mount_set.py:156`), so a guarded assertion is a claim
      that never executes. A bwrap-driven assertion may be added beside this pair
      but may not replace it, and a test that calls the recogniser directly cannot
      satisfy this scenario — the claim is about where the derivation is applied.

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002, trap 5) Add the recogniser module beside
      `factory/verify/gate_annotation.py`, modelled on
      `factory/verify/gate_annotation.py:113` — `matched_install_signature`: named
      runners and the exact shape each prints, returning an empty result where
      nothing matched. Do not add a runner you cannot paste real output for.
- [ ] T008 [US1] (FR-001, FR-005) Add the defaulted field to
      `factory/verify/models.py:362` — `GateResult` beside `worktree_writes`, with
      the docstring paragraph the neighbouring fields each carry.
- [ ] T009 [US1] (FR-003, traps 3 and 4) Call the recogniser from
      `factory/verify/gates.py:1583` — `_to_result`, over the **final** tail —
      after `factory/verify/gates.py:1652` — `_to_result` folds in the install
      annotation — and only for a non-PASS status. Not in any executor: three of
      them reach this one function.
- [ ] T010 [US1] (FR-005) Add the field to both store codecs with `data.get`
      reading absence as empty, and document that reading the way the codec
      documents `worktree_writes`. No schema migration: this is a JSON codec pair.

### Verification for this story

- [ ] T011 [US1] Paste, as committed evidence, one failing gate's recorded output
      and the names parsed from it, and one failing gate whose output matched no
      signature together with its empty name list and unchanged tail.

## Phase 2: User Story 2 — The operator reads what refused without re-running the suite

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-006) Given a verification result whose gate
      refused with two named checks, assert the attempt record's refusal line is
      the exact expected string, naming the gate, its status and both names, and
      that `factory/cli/nouns/build.py:1188` — `_query_status`'s JSON document
      carries it unchanged.
- [ ] T013 [P] [US2] (spec US2-S2, FR-008) Given a gate that refused with no
      recognised names, assert the refusal line still names the gate and its
      status and states that the check names were not recognised. Assert it is not
      empty and not `None`: an empty string reads as "nothing refused".
- [ ] T014 [P] [US2] (spec US2-S3, FR-008) **The control.** Given an attempt whose
      gates passed, assert the record carries no refusal line, so the field marks
      a refusal rather than annotating every row.
- [ ] T015 [US2] (spec US2-S4, FR-007, trap 7) Exercise all three append sites
      that hold a verification result — `factory/workgraph/workflow.py:2096` —
      `_run_node`, `factory/workgraph/workflow.py:2886` —
      `_apply_external_completion_if_present` and
      `factory/workgraph/workflow.py:4018` — `_recovery_attempt` — and assert each
      populates the refusal line, per attempt, on its own record. Not `[P]`: it
      drives three surfaces over one shared fixture.
- [ ] T016 [P] [US2] (spec US2-S5, FR-009, trap 7) Assert a node history recorded
      without the field replays and the status query answers with the refusal line
      absent, raising nothing. `AttemptRecord` is workflow state; an undefaulted
      field presents as a degraded `ergane build status`, not as a red test.
- [ ] T017 [P] [US2] (spec US2-S6, FR-010) Assert the escalation gate line carries
      the named checks as a marker beside the contention and writes markers at
      `factory/notify/messages.py:581` — `_gate_line`, and that a gate with no
      names gains no marker.
- [ ] T018 [P] [US2] (spec US2-S7, FR-007, trap 7) **The site that must stay
      empty.** Assert the unanswered-question FAIL appended at
      `factory/workgraph/workflow.py:2041` — `_run_node` carries no refusal line:
      no gate produced a result there, and a line invented for it would name a
      refusal that did not happen.

### Implementation for this story

- [ ] T019 [US2] (FR-006, FR-008) Add the shared derivation to the module T007
      created: given the attempt's gate results, return the refusal line or
      nothing. One function, spelled once, so the three call sites cannot drift.
- [ ] T020 [US2] (FR-006, FR-009, trap 7) Add the defaulted field to
      `factory/verify/models.py:1245` — `AttemptRecord`, following `model_alias`'s
      own docstring on why a history that predates a field must not be made to
      guess. Do **not** route the refusal through `attempt_note`
      (`factory/cli/nouns/build.py:738` — `_attempt_note_lines`): that is the
      latest attempt's single sentence, not a per-attempt record, and a refusal
      written there is overwritten by the next attempt.
- [ ] T021 [US2] (FR-007, traps 6 and 7) Call the derivation at the three append
      sites that hold a result, and **add its import inside**
      `factory/workgraph/workflow.py:119`'s
      `workflow.unsafe.imports_passed_through()` block. An import at the top of
      that file passes every test and kills the worker at boot. Leave
      `factory/workgraph/workflow.py:2041` — `_run_node` alone.
- [ ] T022 [US2] (FR-010) Append the names marker in
      `factory/notify/messages.py:581` — `_gate_line`, following the two markers
      already there, and keep it bounded the way the writes marker is bounded.

### Verification for this story

- [ ] T023 [US2] Paste, as committed evidence, the `history` entry a refused
      attempt now produces beside the one the ledger row recorded on 2026-08-25
      (`{'attempt': 1, 'judge_outcome': None, ..., 'verdict': 'FAIL'}`), and the
      rendered escalation gate line carrying the marker.

## Phase 3: User Story 3 — A gate can be executed more than once, and a disagreement is recorded

### Tests for this story (write FIRST, must fail)

- [ ] T024 [P] [US3] (spec US3-S1, FR-011) With an executor scripted to return
      PASS every time and a repetition view declaring three executions for one
      gate, assert the executor was invoked three times for that gate, the gate
      contributed exactly one result, and the declaration order of results is
      unchanged.
- [ ] T025 [P] [US3] (spec US3-S2, FR-012, FR-013) With an executor scripted PASS
      then FAIL, assert the reported row is the failing execution's own status,
      exit code, duration and tail — none of them blended — and that it records two
      executions and a disagreement.
- [ ] T026 [P] [US3] (spec US3-S3, FR-013) With an executor scripted FAIL then
      FAIL at the same status, assert the row records two executions and **no**
      disagreement: both executions agreed about the verdict.
- [ ] T027 [P] [US3] (spec US3-S4, FR-014, trap 11) **The control that matters
      most.** With no repetition view at all, in **both**
      `factory/verify/gates.py:1416` — `_run_gate_list` and
      `factory/verify/gates.py:1467` — `_run_gate_list_from_config`, assert every
      gate was invoked exactly once, every row records one execution and no
      disagreement, and no other recorded field moved. A diff that made repetition
      a default cannot pass this.
- [ ] T028 [P] [US3] (spec US3-S5, FR-015, trap 9) **The control.** Enumerate
      `factory/verify/models.py:73` — `GateStatus` and
      `factory/verify/models.py:114` — `OverallVerdict` and assert each declares
      the same members it declares today, and that
      `factory/verify/models.py:950` — `gates_passed` is decided by the reported
      status alone.
- [ ] T029 [P] [US3] (spec US3-S6, FR-013) Assert the execution count and the
      disagreement round-trip through
      `factory/verify/store.py:1091` — `_gate_to_dict` and
      `factory/verify/store.py:1105` — `_gate_from_dict`, and that a stored row
      lacking both reads back as one execution and no disagreement with no other
      field moved.

### Implementation for this story

- [ ] T030 [US3] (FR-011, FR-014, trap 10) Add the repetition loop inside the
      single manifest entry, called from both
      `factory/verify/gates.py:1447` — `_run_gate_list` and
      `factory/verify/gates.py:1491` — `_run_gate_list_from_config`, threading the
      snapshot each execution returns into the next as
      `factory/verify/gates.py:1511` — `_run_watched` requires. Take the view as an
      optional gate-keyed parameter on `_run_gate_list`, shaped like `writes_view`
      at `factory/verify/gates.py:1421` — `_run_gate_list`, and read it in
      `_run_gate_list_from_config` with the defensive `getattr` its neighbour at
      `factory/verify/gates.py:1480` — `_run_gate_list_from_config` already uses,
      so a config shape that predates US4 declares nothing rather than raising.
      One result per declared gate; declaration order unchanged; absent view means
      one execution.
- [ ] T031 [US3] (FR-012, FR-013, FR-015, traps 8 and 9) Select the reported row —
      first non-PASS execution if any, otherwise the last — and record the
      execution count and the disagreement on two defaulted fields of
      `factory/verify/models.py:362` — `GateResult`. Not the `gate_contradictions`
      column at `factory/verify/store.py:241`: that is 116-US3's judge-versus-
      measurement fact and must stay distinguishable from this one. Do **not**
      touch `factory/verify/models.py:950` — `gates_passed`, add a
      `factory/verify/models.py:73` — `GateStatus` member, or add a
      `factory/verify/models.py:114` — `OverallVerdict` member: a disagreement
      already reports a non-PASS row, so the edit buys nothing and changes what
      PASS means for rows this story is not about.
- [ ] T032 [US3] (FR-013) Round-trip both fields through
      `factory/verify/store.py:1091` — `_gate_to_dict` and
      `factory/verify/store.py:1105` — `_gate_from_dict`, absence reading as one
      execution and no disagreement.

### Verification for this story

- [ ] T033 [US3] Paste, as committed evidence, the scripted executor's recorded
      invocation counts for a gate given three executions and for the same run with
      the view removed, beside the single reported row each produced.

## Phase 4: User Story 4 — A repository declares which gate is executed more than once

### Tests for this story (write FIRST, must fail)

- [ ] T034 [P] [US4] (spec US4-S1, FR-016, trap 12) Assert a v2 manifest declaring
      `runs:` for a declared gate parses and the parsed configuration carries the
      mapping. Write it as a fixture under `tmp_path`: this repository's own
      `ergane.yaml` must not declare the key, because the worker parses a node's
      manifest with its own installed parser (`ergane.yaml:49-53`).
- [ ] T035 [P] [US4] (spec US4-S2, FR-017) Assert an entry naming an undeclared
      gate is refused naming the entry and listing the declared gates, and that a
      value which is not a whole number greater than zero is refused naming that
      value. Include `true` among the refused values: `isinstance(True, int)` is
      true and YAML spells booleans that way.
- [ ] T036 [P] [US4] (spec US4-S3, FR-018, trap 2) Given **one** manifest body
      declaring `runs:`, assert the `version: 2` load parses and carries it **and**
      the `version: 1` load is refused as an unknown top-level key. Both halves in
      one test: the v1 half alone passes today, so only the pair can fail a diff
      that registered the key in `_TOP_LEVEL_KEYS`.
- [ ] T037 [US4] (spec US4-S4, FR-019, traps 1 and 12) Drive the candidate-parser
      path with a scripted candidate result declaring `runs:` and assert the gate
      was invoked the declared number of times. Not `[P]`: it shares the scripted
      executor with T034's fixture manifest. A test that only drives the in-process
      configuration cannot satisfy this scenario, and neither can one that asserts
      the accepted shape carries the field without asserting the runner was given
      it — deleting the argument at
      `factory/verify/gates.py:1298` — `run_gates` is 084's own SC-011 mutation and
      left eleven of twelve tests green.
- [ ] T038 [P] [US4] (spec US4-S5, FR-020) Assert the retry prompt's attempt block
      (`factory/workgraph/prompt.py:843` — `_attempt_block`) and the escalation
      gate line (`factory/notify/messages.py:581` — `_gate_line`) each name the
      disagreement and the number of executions, so the next attempt is not sent to
      rewrite working code.

### Implementation for this story

- [ ] T039 [US4] (FR-016, FR-018, traps 2 and 12) Add `runs` to
      `_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:134`) and **not** to
      `_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:109`), where `timeouts` —
      the reader you are about to copy — lives.
      `factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` picks its set
      by version and needs no edit, and `_KNOWN_KEYS` (`factory/cli/init.py:511`)
      is that same tuple, so `ergane init` carries the key with no edit to
      `factory/cli/init.py`. Do not add the key to this repository's `ergane.yaml`.
- [ ] T040 [US4] (FR-016, FR-017) Add the reader modelled on
      `factory/verify/factory_yaml.py:397` — `_read_timeouts`, cross-checking each
      entry against the declared gates and refusing a value that is not a whole
      number greater than zero with `type(x) is not int`. Call it from the reader
      list at `factory/verify/factory_yaml.py:216`, and add the field to
      `factory/verify/models.py:291` — `FactoryConfig` beside
      `factory/verify/models.py:310` — `FactoryConfig`.
- [ ] T041 [US4] (FR-019, trap 1) Carry the declaration through the candidate
      protocol and all the way into the runner: add it to
      `factory/verify/gates.py:205` — `_AcceptedConfig`, read it by name in
      `factory/verify/gates.py:1045` — `_interpret_candidate` beside the three keys
      read at `factory/verify/gates.py:1076` — `_interpret_candidate`, validating
      its shape the way the neighbours are validated, and **hand it to the runner**
      at `factory/verify/gates.py:1292` — `run_gates` and
      `factory/verify/gates.py:1298` — `run_gates` the way `writes_view` is handed
      over. The emitter at `factory/verify/factory_yaml.py:1152` — `_main` needs no
      edit; the reader and the hand-off do, and without either every Ergane node
      ignores the key.
- [ ] T042 [US4] (FR-020) Name the disagreement and its execution count in
      `factory/workgraph/prompt.py:843` — `_attempt_block` and in
      `factory/notify/messages.py:581` — `_gate_line`, following the markers US2
      left there.

### Verification for this story

- [ ] T043 [US4] Paste, as committed evidence, one rendered attempt block and one
      rendered escalation gate line for a row that recorded a disagreement, beside
      the parsed configuration a v2 manifest declaring `runs:` produced.

## Verification

- [ ] T044 The full gate command passes green.
- [ ] T045 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 1 — reading `ergane build status --json`
      for a node the gates refused — is the falsifiable test of this whole spec,
      because it is the 2026-08-25 reading run forwards; step 3 runs against a
      scratch repository on a worker restarted after landing, per trap 12; and step
      5 is the control that no gate started running twice by default.
