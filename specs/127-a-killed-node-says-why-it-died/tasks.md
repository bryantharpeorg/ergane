# Tasks: a killed node says why it died

Read `plan.md` before starting. Six traps are the difference between a fix that
works and a fix that passes: there are two overwrite sites and the finding names
one (trap 1); the interpreter suite cannot reach either of them because a stub
returns `[]` (trap 2); a committed test asserts the defect as intended behaviour
and is currently green (trap 3); `ergane status` already prints the cause and
adding a renderer to it is the wrong move (trap 5); `exhausted_bound` cannot
name the landing dial, so calling it on that path returns `None` and a test
written the same way passes anyway (trap 7); and US3 and US5 are one verb cut in
half for size, so each one's boundary is a hazard the other pays for (trap 16).

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The housekeeping report stops overwriting the cause

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-003) Given a node whose push was
      refused non-fast-forward and whose remote branch is then archived and
      cleared, assert `terminal_reason` still carries git's diagnosis, the archive
      report is readable from the new field on the same record, and the
      `epic_status` answer carries both — the record half and the query half of
      FR-001 are separate assertions.
- [ ] T002 [P] [US1] (spec US1-S4, FR-002, trap 1) **The control that matters
      most.** Drive the kill path inside `_escalate_ref_conflict`
      (`factory/workgraph/workflow.py:3216` — `_escalate_ref_conflict`), which at
      `factory/workgraph/workflow.py:3330` reaches
      `_archive_and_clear_remote_branch` and never `_close_out`, and assert the
      same separation holds. A fix applied only to `_close_out` — the site the
      finding names — passes T001 and fails this. The finding calls the method
      `_handle_push_refusal`; that name is not in the tree.
- [ ] T003 [P] [US1] (spec US1-S2, FR-003, trap 4) **The control.** Given a node
      ended with an empty housekeeping report, assert `terminal_reason` is
      unchanged from today's value and the new field is empty. Most nodes are this
      node; a regression here is wider than the defect.
- [ ] T004 [P] [US1] (spec US1-S3, FR-004) Given a node with a housekeeping report
      and no terminal reason, assert `terminal_reason` stays `None` and the report
      is in the new field. A report is not a cause and must never be promoted into
      one.
- [ ] T005 [US1] (FR-005, trap 2) In `tests/test_interpreter.py`, make the
      `archive_and_clear_remote_branch` stub at
      `tests/test_interpreter.py:1560-1565` able to return a **non-empty** report,
      and add a test that drives one through. Today it returns `[]`
      unconditionally, so `if report:` has never been true in this suite and
      neither overwrite site has ever executed under it. Not `[P]`: it edits the
      shared interpreter script fixture.
- [ ] T006 [US1] (FR-005, trap 3) In
      `tests/test_126_us2_kill_archives_remote.py`, repoint the assertions at
      `tests/test_126_us2_kill_archives_remote.py:260-262` (`BRANCH in …
      terminal_reason`, `pushed[:12] in … terminal_reason`) and at
      `tests/test_126_us2_kill_archives_remote.py:285-286` (`"origin" in …
      terminal_reason`) at the new field, and **EXTEND** the comment at
      `tests/test_126_us2_kill_archives_remote.py:318-319` to name the new field's
      empty value in the case it already describes. That comment is about the
      EMPTY-report path and stays TRUE after this change (trap 3): do not set out
      to falsify it, because the only way to succeed is to change the empty-report
      path, which US1-S2 forbids. **The two assertions above, by contrast, encode
      the defect and are green.** If they are still green and unedited when this
      story ends, the fix did not land and nothing else will say so.

### Implementation for this story

- [ ] T007 [US1] (FR-001) In `factory/workgraph/models.py`, add the housekeeping
      field to `NodeRecord` (`factory/workgraph/models.py:324` — `NodeRecord`)
      beside `terminal_reason` (`factory/workgraph/models.py:387`), with a
      docstring in the style of the sibling `attempt_note`
      (`factory/workgraph/models.py:390-398`) — which exists precisely to record
      why it is not `terminal_reason`. The docstring is the deliverable, not a
      nicety: it is what stops the next story re-merging the two fields.
- [ ] T008 [US1] (FR-001) In `factory/workgraph/workflow.py`, carry the same field
      on the query answer `NodeStatus` (`factory/workgraph/workflow.py:599` —
      `NodeStatus`) beside its `terminal_reason`
      (`factory/workgraph/workflow.py:641`), and populate it from the record where
      `terminal_reason` is populated (`factory/workgraph/workflow.py:882`). A field
      that stops at `NodeRecord` reaches no renderer, which is the defect in a new
      slot.
- [ ] T009 [US1] (FR-002, FR-003, FR-004, traps 1 and 4) Change **both**
      assignments — `factory/workgraph/workflow.py:3151-3152` in `_close_out` and
      `factory/workgraph/workflow.py:3612-3613` in
      `_archive_and_clear_remote_branch` — to write the new field. Keep the
      `if report:` guard on both; the empty-report path must not change. Leave
      `factory/workgraph/workflow.py:3253`, where git's diagnosis is stored, alone.

### Verification for this story

- [ ] T010 [US1] Paste, as committed evidence, a terminal node record from a real
      kill on a scratch remote showing git's refusal in `terminal_reason` and the
      archive report in the new field. The judge sees the diff only, so the record
      must be in it.

## Phase 2: User Story 2 — Both surfaces print the cause and the housekeeping as two things

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1, FR-007) Given an epic with a terminal node
      carrying both a cause and a housekeeping report, assert `ergane build
      status`'s node line carries the two as distinct labelled tokens and shows
      neither as the other.
- [ ] T012 [P] [US2] (spec US2-S2, FR-006, trap 5) **The control that keeps the
      surfaces from drifting.** Assert that `ergane status`'s node lines for one
      document are identical to `render_status`'s
      (`factory/cli/nouns/build.py:464` — `render_status`) for the same document,
      and therefore carry both tokens. `ergane status` renders no node lines of its
      own: `factory/cli/status.py:788` imports that renderer at
      `factory/cli/status.py:796`. This test fails the moment anyone adds a second
      renderer to `factory/cli/status.py`.
- [ ] T013 [P] [US2] (spec US2-S3, FR-007) **The control.** Given a node with a
      housekeeping report and no terminal reason, assert neither verb claims a
      cause for it and only the housekeeping token appears.
- [ ] T014 [P] [US2] (spec US2-S4, trap 14) **The control.** Given an epic whose
      nodes are all non-terminal, assert both verbs' output is byte-identical to
      today's. `ergane status` is watched continuously; a diff in its steady-state
      output is a change to the thing everyone reads.

### Implementation for this story

- [ ] T015 [US2] (FR-007, FR-008, traps 5 and 6) In `factory/cli/nouns/build.py`,
      add a housekeeping token function beside `_reason_token`
      (`factory/cli/nouns/build.py:718` — `_reason_token`), flattening whitespace
      the way it does and the way `_attempt_note_lines`
      (`factory/cli/nouns/build.py:738` — `_attempt_note_lines`) does, and
      interpolate it into the node line assembled at
      `factory/cli/nouns/build.py:501-506`. Leave the cause reaching both surfaces
      through `_reason_token` itself.
- [ ] T016 [US2] (FR-006) Change no line of `factory/cli/status.py`. This task is
      the deliberate absence: the delegation at `factory/cli/status.py:796` is what
      gives `ergane status` the new token, and the comment at
      `factory/cli/status.py:794-795` says why a second renderer there is a defect.
      If the diff touches that file, T012 is the test that should have stopped it.

### Verification for this story

- [ ] T017 [US2] Paste both verbs' output for one real epic with a killed node
      that had a remote branch, as committed evidence, with the two node lines
      beside each other so their agreement is readable in the diff.

## Phase 3: User Story 3 — One verb assembles the causal chain

### Tests for this story (write FIRST, must fail)

- [ ] T018 [P] [US3] (spec US3-S1, FR-009, traps 10, 11 and 15) Given an epic with
      a node that failed verification and was killed after its landing was
      rejected, assert `ergane build why <epic-id> <node-id>` prints the last
      verdict, the failing gate with its output tail, the judge feedback where one
      exists, the queue outcomes and rejection cause from the landing, the
      transcript directory of the latest attempt, and the terminal reason. Assert
      the transcript directory is printed as a path and never opened, and assert
      the gate output is CLIPPED — the last `EVIDENCE_TAIL_LINES` lines
      (`factory/notify/messages.py:79`) with the drop named — not the whole
      `GateResult.output_tail` (`factory/verify/models.py:362` — `GateResult`),
      which is up to 32 KiB against a 64 KiB story bound (trap 15).
- [ ] T019 [P] [US3] (spec US3-S2, FR-009) Given no node argument, assert the verb
      reports every terminal node of the epic in the same shape.
- [ ] T020 [P] [US3] (spec US3-S3, FR-009) **The control.** Given a node that
      passed and landed, assert the verb says it has no failure to explain rather
      than printing an empty chain.

### Implementation for this story

- [ ] T021 [US3] (FR-009, traps 10, 11, 12, 15 and 16) Add the `why` subcommand in
      `factory/cli/nouns/build.py`: register it beside the `attempts` parser
      (`factory/cli/nouns/build.py:2280`), read the attempts through `node_history`
      (`factory/verify/store.py:873` — `node_history`) as `attempts_command`
      (`factory/cli/nouns/build.py:1284` — `attempts_command`) reads the store, and
      read the ending through the `epic_status` query the way `_query_status`
      (`factory/cli/nouns/build.py:1119` — `_query_status`) does at
      `factory/cli/nouns/build.py:1125`. Compose the transcript path with
      `transcript_dir` (`factory/workgraph/adapter.py:771` — `transcript_dir`) and
      do not read it — and resolve its first argument, `factory_root`, with the
      call this module already makes at `factory/cli/nouns/build.py:1888-1890`
      (`resolve_env_path(ERGANE_ROOT_ENV, FACTORY_ROOT_ENV,
      DEFAULT_FACTORY_ROOT_PATH)`), not a bare relative default, which prints a
      path correct only from the worker's cwd (trap 11). Clip the gate output
      rather than printing `output_tail` whole: promote the clipper at
      `factory/notify/messages.py:641` — `_tail` — to a public name in that module,
      behaviour and bound unchanged, updating its four call sites there
      (`factory/notify/messages.py:539`, `factory/notify/messages.py:547`,
      `factory/notify/messages.py:571`, `factory/notify/messages.py:576`), and
      import the public name — this module imports `factory.notify.service` at
      `factory/cli/nouns/build.py:94`, not `factory.notify.messages`, so the import
      is new and no production module imports a private name from it (trap 15).
      Add no store, no query column and no directory walk. Call the module-level
      `_verification_store_path`; it is already defined twice
      (`factory/cli/nouns/build.py:1484` and `factory/cli/nouns/build.py:1534`) and
      a third copy is not the fix. **Stop at the present execution:** on
      `RPCStatusCode.NOT_FOUND` refuse in the shape
      `factory/cli/nouns/build.py:1135-1138` already refuses in, and leave the
      two-way discriminator to US5 — building it here puts back the bytes this
      story was split to shed (trap 16).

### Verification for this story

- [ ] T022 [US3] Paste, as committed evidence, ONE run and no more: the verb's
      output for a real failed node beside the `journalctl` line that was
      previously the only place that answer existed. Code and pasted evidence share
      this story's diff bound (D-050, `DIFF_INPUT_LIMIT` at
      `factory/verify/diffbounds.py:47`, and `DIFF_REFUSAL_THRESHOLD` at
      `factory/verify/diffbounds.py:66`, above which a story is refused unjudged),
      so trim that run to the lines that carry the answer — a single unclipped gate
      tail is up to 32 KiB (`factory/verify/models.py:362` — `GateResult`), half
      the bound, on its own (trap 15).

## Phase 4: User Story 4 — A landing-recovery escalation names its exhausted bound

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US4] (spec US4-S1, FR-011, traps 7 and 8) Given a node escalating
      from the landing-recovery path with its recovery cycles spent, assert the
      composed message names `max_recovery_cycles` and its configured value, in the
      sentence shape `factory/verify/ladder.py:265-267` produces and
      `factory/notify/messages.py:450` prints. Assert the dial name literally: a
      test that only asserts "some bound is named" passes against the wrong bound,
      which is what calling `exhausted_bound` on this path would produce.
- [ ] T024 [P] [US4] (spec US4-S2, FR-012) **The control.** Given the same path
      with a cycle remaining, assert no exhausted bound is named. A dial that has
      not been reached must not be reported as spent — and this branch also passes
      when the bound is never computed at all, so it is only meaningful beside
      T023.
- [ ] T025 [P] [US4] (spec US4-S3, FR-012, trap 9) **The control.** Given a
      verification escalation, assert the message is byte-identical to today's, so
      this story cannot alter the path 095 already built or re-word
      `ExhaustedBound.describe` (`factory/verify/ladder.py:265-267`).

### Implementation for this story

- [ ] T026 [US4] (FR-011, FR-012, traps 7, 8 and 9) Give `_escalate_landing`
      (`factory/workgraph/workflow.py:4178` — `_escalate_landing`) an
      `exhausted_bound` parameter as `_escalate` has at
      `factory/workgraph/workflow.py:2964`, pass it into the `EscalationRequest`
      built at `factory/workgraph/workflow.py:4215-4223`, and compute it at the two
      exhaustion callers — `factory/workgraph/workflow.py:3817` and
      `factory/workgraph/workflow.py:3866` — from the same predicate they already
      evaluate for `retry_grants_work` (`factory/workgraph/workflow.py:3825-3827`
      and `factory/workgraph/workflow.py:3862-3865`). Build an `ExhaustedBound`
      (`factory/verify/ladder.py:244` — `ExhaustedBound`) naming
      `max_recovery_cycles` (`factory/mergequeue/models.py:393`) and render it with
      `_bound_sentence` (`factory/workgraph/workflow.py:4351` — `_bound_sentence`).
      Do **not** call `exhausted_bound` (`factory/verify/ladder.py:270` —
      `exhausted_bound`): it takes a `VerificationConfig` and can only ever name
      one of four verification dials. Do **not** pass a bound from
      `factory/workgraph/workflow.py:4079`, the futile re-enqueue, which is not an
      exhaustion. Do **not** edit `describe`.

### Verification for this story

- [ ] T027 [US4] Paste the rendered message for both branches — recovery cycles
      spent and a cycle remaining — as committed evidence.

## Phase 5: User Story 5 — The verb tells "no such epic" from "the execution aged out"

### Tests for this story (write FIRST, must fail)

- [ ] T028 [P] [US5] (spec US5-S1, FR-010, trap 10) Given an epic id nothing is
      running under — `NOT_FOUND` from `epic_status` and **no** rows from
      `epic_history` (`factory/verify/store.py:899` — `epic_history`) — assert the
      verb names the epic id, the workflow id it looked for and the store path it
      read, exits non-zero, and prints no traceback — the shape
      `factory/cli/nouns/build.py:1135-1138` already refuses in. The store, not the
      status code, is what tells this case from T029's: both are `NOT_FOUND`.
- [ ] T029 [P] [US5] (spec US5-S2, FR-010, trap 10) **The degradation control.**
      Given verification rows for an epic whose execution has aged out of the
      server — the same `NOT_FOUND` as T028, but **with** rows from `epic_history`
      (`factory/verify/store.py:899` — `epic_history`) — assert the verb prints the
      store half of the chain and reports the ending as unavailable, rather than
      refusing the whole reading. `terminal_reason` is in no store — `grep -rn
      terminal_reason factory/verify/` returns nothing — so this branch is the
      difference between a verb that answers late and one that only answers early.

### Implementation for this story

- [ ] T030 [US5] (FR-010, traps 10, 12 and 16) In `factory/cli/nouns/build.py`,
      **replace** the `NOT_FOUND` refusal US3 shipped rather than adding a second
      absence path beside it (trap 16): read `epic_history`
      (`factory/verify/store.py:899` — `epic_history`) for the epic's rows and
      branch on rows-present, not on the status code — no rows refuse (US5-S1),
      rows degrade (US5-S2). Both absences arrive as `RPCStatusCode.NOT_FOUND` on
      the `epic_status` query `_query_status` (`factory/cli/nouns/build.py:1119` —
      `_query_status`) issues at `factory/cli/nouns/build.py:1125`, which
      `factory/cli/nouns/build.py:1135-1138` collapses into one refusal today, so
      the store is the only fact that separates them. Reach the store through the
      module-level `_verification_store_path` — it is already defined twice
      (`factory/cli/nouns/build.py:1484` and `factory/cli/nouns/build.py:1534`) and
      a third copy is not the fix (trap 12). Add no store and no query column.

### Verification for this story

- [ ] T031 [US5] Paste, as committed evidence, the verb's two answers for the two
      absences: the refusal for an epic id nothing is running under, naming the
      store path it read, and the half-chain-plus-named-absence for an epic whose
      rows outlived its execution. Trim both to the lines that carry the answer.

## Verification

- [ ] T032 The full gate command passes green.
- [ ] T033 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 2 is the falsifiable test of this whole
      spec: it is the surface that read `Activity task failed` for every node death
      in the `ergane-web` run, and the one line that would have saved four hours.
