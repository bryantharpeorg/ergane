# Tasks: an operator's decision outlives the tick that missed it

Read `plan.md` before starting. Five of its traps decide whether these stories are
worth anything. Trap 3: the fake workflow handle at
`tests/test_roadmap_schedule_discovery.py:214` — `signal` never raises, so the
defect cannot be reproduced until you give it a way to; a test copied from the
existing floor passes today and proves nothing. Trap 4: that module's
`SPECS_ROOT` is a path that does not exist, so the first test that makes
`promote` write a file must move to a `tmp_path / "specs"` root — named `specs`,
because the fakes are keyed on the id derived from the root's name — and must
never be pointed at this repository's own `specs/`. That naming rule stops at
the tests that reach the fake floor: T006 needs no floor, and a root named
`specs` there resolves to this host's live `roadmap-specs` during the mandatory
red run. Trap 7: the roadmap is
declared `AUTO_UPGRADE`, so the new activity call belongs behind
`workflow.patched(...)` or a run in flight fails replay. Trap 8: registering that
activity is nine places, not two, and forgetting one of the six test workers
presents as a hang, not a failure. Trap 12: one existing test in a module these
stories do not otherwise touch patches the `_get_handle` seam US2 deletes, and its
specs root resolves to this floor's live roadmap.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A promotion is written down before it is signalled

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S2, FR-001) Assert that the record path derived
      from a relative spelling of a specs root and from its absolute spelling are
      the same file: write through one, read back through the other, and compare
      the two resolved paths. This is the anchor of the whole design — the CLI is
      given whatever the operator typed and the activity is given whatever the
      schedule recorded, and they must agree.
- [ ] T002 [P] [US1] (spec US1-S1, FR-002, FR-003, FR-007, trap 4) Over a
      `tmp_path / "specs"` root and `scheduled_floor`
      (`tests/test_roadmap_schedule_discovery.py:334` — `scheduled_floor`), assert
      that `ergane roadmap promote` exits 0, that the record names the spec dir,
      that a `.gitignore` sits beside it ignoring the directory's contents, that
      stdout carries the absolute path, and that `client.signals` is empty. The
      root must be named `specs`: the fakes are keyed on `BARE_ID` and
      `RUN_PREFIX` at `tests/test_roadmap_schedule_discovery.py:104` and
      `tests/test_roadmap_schedule_discovery.py:105`, and a bare `tmp_path` gets a
      location refusal instead of ever reaching the write. Never point this test
      at the repository's own `specs/`.
- [ ] T003 [P] [US1] (spec US1-S6, FR-003) **The control.** Assert that
      `factory/roadmap/models.py:440` — `read_roadmap` returns the same roadmap for
      a specs root with the record directory present as for one without it, and
      that `factory/doctor/triage.py:254` — `read_spec_records` likewise reports no
      extra spec. The record must be invisible to the corpus by name.
- [ ] T004 [US1] (spec US1-S4, FR-008, traps 2 and 3) Give the fake workflow
      handle a way to raise the refusal a completed run raises — the module already
      builds one at `tests/test_roadmap_schedule_discovery.py:207` — then assert
      that `promote` exits 0, that the record was written, that stdout says the
      promotion was recorded and no live run could be told, and that stderr
      contains no `unexpected error`. Not `[P]`: it edits the shared fake.
- [ ] T005 [US1] (spec US1-S3, FR-007, FR-008, trap 5) **The control that matters
      most.** Over `bare_floor` (`tests/test_roadmap_schedule_discovery.py:516` —
      `bare_floor`) with a live run, assert that `promote` both writes the record
      **and** signals `promote_spec`. Amend
      `tests/test_roadmap_schedule_discovery.py:593` — `test_bare_workflow_promote_signals_the_workflow`
      for the printed path, and leave
      `tests/test_roadmap_schedule_discovery.py:575` — `test_bare_workflow_pause_and_resume_signal_the_workflow_silently`
      exactly as it stands.
- [ ] T006 [P] [US1] (spec US1-S5, FR-009, trap 4) Assert that `promote` against a
      specs root that does not exist refuses in one line naming that path, that the
      path is still absent afterwards, and that stderr does not carry the
      `unexpected error` text of `factory/cli/errors.py:69` — `run_cli`. Prove
      FR-009's *ordering* with a stub rather than with a connection that is hoped
      to fail: monkeypatch `factory/cli/roadmap.py:201` — `_connect` with a
      callable that raises if it is ever reached, and assert both the refusal and
      that the stub was never called. Two things this test must not do, and trap 4
      says why: do not name its absent root `specs` — T002's naming rule is for
      the tests the fakes answer, and here it derives this host's live
      `roadmap-specs` — and do not leave `_connect` unpatched, because
      `tests/conftest.py` blocks no real connection and the red run of this test
      would otherwise signal the operator's own floor.
- [ ] T007 [US1] (FR-012, trap 6) Update the `roadmap_promote_command` row at
      `tests/test_ergane_status.py:1549` to name exactly the classes the verb now
      catches, and — only if that guard names a transport class — add the verb to
      the sorted anti-vacuity list asserted at `tests/test_ergane_status.py:1841` —
      `test_no_temporal_call_site_catches_the_transport_failure_alone`, in sort
      order. Not `[P]`: T019 edits the same table.

### Implementation for this story

- [ ] T008 [US1] (FR-001, FR-003, FR-009, trap 9) Add `factory/roadmap/promotions.py`:
      the path derivation from a specs root (resolved absolutely, one function used
      by both sides), the read, and the write. The directory name starts with a
      dot so `factory/roadmap/models.py:440` — `read_roadmap` and
      `factory/doctor/triage.py:254` — `read_spec_records` skip it by name rather
      than by luck. Creating it writes the `.gitignore` in the same act. A specs
      root that does not exist, or a record that cannot be written, raises
      `OperatorError` naming the path and creates nothing.
- [ ] T009 [US1] (FR-002, FR-007, FR-008, FR-009) Rewrite
      `factory/cli/roadmap.py:397` — `roadmap_promote_command` in this order:
      refuse first if the specs root does not exist (before `_locate`, so no client
      is opened for a typo); resolve the location; write the record; print the
      absolute path and the spec; and only then decide about a signal — no signal
      when `location.owner is RoadmapOwner.SCHEDULE`, following
      `factory/cli/roadmap.py:355` — `roadmap_pause_command`; otherwise
      `promote_spec` as today, with a refusal caused by a completed run reported as
      recorded-but-not-signalled at exit 0 and any other `RPCError` still refusing
      as a transport error. The write comes before the signal so a decision is
      never lost to a run that cannot receive it. Leave `_get_handle` in place: it
      still has one caller after this story.

### Verification for this story

- [ ] T010 [US1] Paste, as committed evidence, two captures: `ergane roadmap
      promote` against a schedule between ticks — its stdout and the record's
      contents — and `git status --short` in the repository holding that corpus,
      showing the promotions directory does not appear.

## Phase 2: User Story 2 — `unpark` answers for the tick that already re-checked the spec

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1, FR-010, traps 2 and 3) Using the raising fake
      handle from T004, assert that `unpark` against a scheduled floor whose newest
      run has completed exits 0, that stdout names the owning schedule, states a
      fresh run starts with no parks and states the next tick re-checks the spec,
      and that stderr carries no `unexpected error`.
- [ ] T012 [P] [US2] (spec US2-S6, FR-010, trap 13) **The second owner.** Over a
      bare floor whose run has completed, assert that the sentence names the run as
      ended and names `ergane roadmap start`, and that it is **not** the same
      string as the schedule-owned sentence T011 asserts. One f-string for both
      owners promises a tick nothing will start.
- [ ] T013 [P] [US2] (spec US2-S2, FR-011) **The control.** Over `bare_floor` with
      a live run, assert `unpark` still signals `unpark_spec` and stays silent at
      exit 0 — the signal list, the empty stdout and the empty stderr, all three.
      This story changes the missing-run path and nothing else.
- [ ] T014 [US2] (FR-011, trap 12) Convert
      `tests/test_roadmap_prompt_assembly.py:572` — `test_the_unpark_verb_carries_the_spec_the_operator_named`
      in the same commit as T018. It patches `_get_handle` and installs no fake
      client, so once `unpark` calls `_locate` it would connect for real against
      `roadmap-specs` — this floor's live roadmap. Keep its own `_Handle`, which is
      the only place the signal's *argument* is asserted, and patch at the new seam
      (`roadmap_cli._locate`, returning a fake client whose `get_workflow_handle`
      returns that handle); or move it onto `fake_temporal`/`bare_floor` only if the
      argument assertion survives the move. Not `[P]`: it must land with T018.
- [ ] T015 [P] [US2] (spec US2-S3, FR-011, trap 11) **The absence control.** After
      an `unpark` on a scheduled floor, assert that no promotions record and no
      park record exist under the specs root. A reviewer cannot see an absence any
      other way, and the symmetric park record is the tempting wrong build.
- [ ] T016 [P] [US2] (spec US2-S4, FR-010) **The unchanged case.** Assert that a
      schedule owning dispatch that has started **no** run still gets today's
      refusal from `factory/cli/roadmap.py:334` — `_handle_for`, naming the
      schedule and the run prefix, word for word. That path was already honest and
      this story does not reword it.
- [ ] T017 [P] [US2] (spec US2-S5, FR-013, trap 6) Assert the guard sweep at
      `tests/test_ergane_status.py:1702` —
      `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal` still
      passes with the table updated, and that it fails if the
      `roadmap_unpark_command` row is left stale — the second half proves the
      assertion is load-bearing rather than decorative.

### Implementation for this story

- [ ] T018 [US2] (FR-010, FR-011, trap 13) Rewrite
      `factory/cli/roadmap.py:403` — `roadmap_unpark_command` to resolve the
      location, signal `unpark_spec` as today, and turn a refusal caused by a
      completed run into one printed sentence chosen by `location.owner`: for
      `RoadmapOwner.SCHEDULE`, the schedule, no parks in a fresh run, and the next
      tick; for a bare workflow or an unowned run, the run that ended and
      `ergane roadmap start` — exit 0 either way. Write nothing: no promotions
      record, no park record. Any other `RPCError` still refuses as a transport
      error.
- [ ] T019 [US2] (FR-013, trap 6) Update the `roadmap_unpark_command` row at
      `tests/test_ergane_status.py:1550` to name exactly the classes the verb now
      catches, and add the verb to the sorted anti-vacuity list at
      `tests/test_ergane_status.py:1841` —
      `test_no_temporal_call_site_catches_the_transport_failure_alone` only if that
      guard names a transport class. Do not widen to a bare `except Exception`:
      `tests/test_ergane_status.py:1901` — `test_no_temporal_call_site_is_guarded_by_a_blanket_except`
      forbids it. `_get_handle` loses its last caller in T018: remove the function
      and remove its row at `tests/test_ergane_status.py:1546` in the same commit,
      because the sweep compares the table against the module by set equality in
      both directions.
- [ ] T020 [US2] (FR-011, trap 11) Confirm by reading that
      `factory/roadmap/workflow.py` needed no edit for this story. **If it did, the
      design is wrong**: a park has never survived the tick that made it
      (`factory/roadmap/workflow.py:565` — `__init__`), and this story is a
      sentence, not a store.

### Verification for this story

- [ ] T021 [US2] Paste, as committed evidence, the terminal capture of
      `ergane roadmap unpark` against a schedule between ticks — exit code, stdout
      and stderr — beside the same command's output before the change, which is the
      `unexpected error (...)` line. Say in the same commit message what closing
      `roadmap/unpark-cannot-reach-a-scheduled-run` means, because the row's own
      words survive this story literally: the verb still does not reach a
      scheduled run and still writes nothing. It is closed by a refusal that
      explains, plus US2-S3's control that nothing durable was lost — not by
      making the verb reachable. A later triage that reads the row as "unpark now
      reaches a scheduled run" is the misreading the row itself warns against for
      its older sibling.

## Phase 3: User Story 3 — The roadmap reads the record on its next pass

### Tests for this story (write FIRST, must fail)

- [ ] T022 [P] [US3] (spec US3-S1, FR-004) Over `tests/test_roadmap_scheduler.py:474` —
      `run_roadmap`, with no signal sent and no carry-over supplied, assert that a
      run whose corpus carries a record naming a draft spec applies the promotion
      for that pass and that its `roadmap_status`
      (`factory/roadmap/workflow.py:731` — `roadmap_status`) reports `promoted`
      true for it.
- [ ] T023 [US3] (spec US3-S2, FR-004, trap 10) **The union.** Seed the record with
      one draft spec, then send `promote_spec` for a second through the handle
      `run_roadmap` yields, and assert both are applied. Use the signal rather than
      a carry-over: `run_roadmap`'s signature at
      `tests/test_roadmap_scheduler.py:474` — `run_roadmap` takes no `carry_over`
      argument, so the carry-over half would need the harness widened first. Not
      `[P]`: it shares the corpus fixture T022 introduces.
- [ ] T024 [P] [US3] (spec US3-S3, FR-005, trap 7) Assert the patch gate from the
      source: read the seeding block and fail if the new activity call is reachable
      outside a `workflow.patched(...)` branch, in the shape the guard sweep at
      `tests/test_ergane_status.py:1702` —
      `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal`
      already uses for source-derived assertions. Without this the story can pass
      with an unguarded call and break a run in flight on the operator's floor.
- [ ] T025 [US3] (spec US3-S4, FR-006, trap 8) Assert that the new read activity
      appears in the worker's activity list (`factory/worker.py:197`). The symptom
      of forgetting it is a roadmap that silently stops dispatching — and, in a test
      environment, a hang rather than a named failure — so the assertion is the only
      thing that fails loudly. Not `[P]`: it lands with T027's sweep.

### Implementation for this story

- [ ] T026 [US3] (FR-006, trap 8) Add the read activity beside
      `factory/roadmap/workflow.py:494` — `read_corpus_activity`, in its shape and
      in its module, and register it in **both** places in `factory/worker.py` —
      the import at `factory/worker.py:85` and the activity list at
      `factory/worker.py:197`. Registering it is what puts the activity's input
      record on the swept Temporal payload boundary
      (`tests/test_temporal_payload_shape.py:212` — `activity_boundary_types`
      walks every registered activity's types), so either give every field of that
      record a default or add its allowlist row beside
      `tests/test_temporal_payload_shape.py:477` with the kind of justification
      its neighbours carry — otherwise
      `tests/test_temporal_payload_shape.py:629` —
      `test_every_boundary_field_has_a_default_or_is_allowlisted` fails in a module
      this story would not otherwise open.
- [ ] T027 [US3] (FR-006, trap 8) Register the same activity in every test module
      that builds a roadmap worker from a hand-written list, import beside entry:
      `tests/test_ergane_roadmap.py:137` — `_worker`,
      `tests/test_scheduled_epics_carry_the_dials.py:124` — `_worker`,
      `tests/test_roadmap_first_tick_on_fresh_init.py:118` — `_run_roadmap`,
      `tests/test_roadmap_scheduler.py:530` — `run_roadmap`,
      `tests/test_roadmap_failure_notifications.py:238` — `run_roadmap_with_notifications`,
      `tests/test_roadmap_failure_notifications.py:333` — `run_roadmap_with_sandboxed_workflow`
      and `tests/test_023_us2_dispatch_pin.py:671` — `_run_roadmap`. Seven lists in six modules; the
      scheduler's is the shared `run_roadmap` harness that four other modules
      import. A worker that does not serve the activity does not raise — the
      workflow task parks and the test sits until its own wait expires — so a
      module left out of this sweep fails as a timeout with no name on it.
- [ ] T028 [US3] (FR-004, FR-005, traps 7 and 10) Seed the promotions in
      `factory/roadmap/workflow.py:832` — `_run_inner`, between the corpus read and
      `factory/roadmap/workflow.py:845` — `_run_inner`'s call to
      `_apply_promotions`. Union into `self._promotions`; do **not** assign over
      it, or the carry-over assigned at `factory/roadmap/workflow.py:815` —
      `_run_inner` and any promotion signalled mid-pass at
      `factory/roadmap/workflow.py:621` — `promote_spec` are lost. Gate the new
      activity call with `workflow.patched(...)`, in the shape
      `factory/workgraph/workflow.py:1826` — `_run_node` uses, because
      `factory/roadmap/workflow.py:528-530` declares this workflow `AUTO_UPGRADE`
      and a run in flight replays its history under the new code. Never consume the
      record: a promotion ends when the frontmatter leaves `draft`, which
      `factory/roadmap/workflow.py:1110` — `_apply_promotions` already handles.

### Verification for this story

- [ ] T029 [US3] Paste, as committed evidence, one capture of a roadmap pass over
      a corpus whose record names a draft spec: the record's contents and the
      `ergane roadmap status` output showing that spec `promoted=True`, with no
      signal sent in between.

## Verification

- [ ] T030 The full gate command passes green.
- [ ] T031 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 3 — promote a draft between ticks, wait one
      tick, and watch it dispatch — is the falsifiable test of this whole spec: it
      is the 2026-08-19 sitting run forwards, and it is the step a record that
      never reaches the workflow cannot pass.
