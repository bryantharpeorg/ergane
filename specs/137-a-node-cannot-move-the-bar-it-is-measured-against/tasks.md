# Tasks: a node cannot move the bar it is measured against

Read `plan.md` before starting. Four of its traps decide whether this story is
worth anything. Trap 2: refuse `spec.md`, `plan.md` and `tasks.md` by name and
nothing else in the dispatched directory — fifty files under `specs/*/evidence/`
and fifteen `specs/<dir>/attempt-report-<story>.md` files across twelve
directories already arrived on their own nodes' pull requests, and the attempt
reports sit *beside* `evidence/`, so a directory-wide refusal with an `evidence/`
carve-out still makes twelve directories unlandable, this spec's own evidence
included. Trap 4: the worktree copy of the spec is compared against the node's own
BASE REF, never against the dispatch snapshot — the snapshot is hashed from the
operator's working tree and the worktree is cut from origin's landing head, so
comparing them flags ordinary dispatches where nobody edited anything. Trap 5: a
node cannot lower its own bar for its own verdict, so any criterion written about
what the judge sees is already true today and proves nothing. Trap 1: the ledger
row this spec declares says drift already fires; it does not, and reading that
sentence is how US2 gets skipped.

**Do not tick the checkboxes in this file** (trap 13). Six landed node PRs ticked
their own dispatched `tasks.md`, and the rule US1 builds refuses exactly that —
so a node of this spec that ticks its own boxes fails its own output check.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a file or a test function an earlier task in the same phase is
already editing.

## Phase 1: User Story 1 — A diff that moves the node's own bar is refused before it can land

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-002) In `tests/test_diff_hygiene.py`,
      build a diff-scope worktree whose changed paths include a production file,
      `specs/<feature>/spec.md` and `specs/<feature>/tasks.md`, run the output
      check with `specs/<feature>` declared as the dispatched spec directory, and
      assert `passed is False` and that the recorded evidence carries **both**
      paths, each with a rule naming the directory. Model the rule assertion on
      `tests/test_diff_hygiene.py:207` —
      `test_the_refusal_names_the_rule_that_refused_each_path`. An implementation
      that refuses only `spec.md` must fail this.
- [ ] T002 [US1] (spec US1-S2, FR-003, trap 2) **Both exempt classes, in the same
      test function as T001 over the same fixture.** Add
      `specs/<feature>/evidence/us1-report.txt` **and**
      `specs/<feature>/attempt-report-us1.md` to the diff and assert neither is
      refused nor recorded as a violation. Both are required: the first is
      FR-003's `evidence/` class, the second is FR-003's attempt-report class,
      which sits beside `evidence/` rather than under it, so a rule that refuses
      the directory with an `evidence/` carve-out passes on the first path and
      fails on the second. Not `[P]`: it edits T001's test. Without the second
      path this scenario has no discriminating power and the corpus-breaking rule
      ships green — fifteen committed attempt reports across twelve directories,
      and T012 and T022 below, are what it would refuse.
- [ ] T003 [US1] (spec US1-S3, FR-004) **The other-spec control, in the same test
      function.** Add `specs/<other>/spec.md` — a spec this node was not
      dispatched against — and assert it is not refused. Not `[P]`. Paired with
      T001, this is what a check that refuses nothing cannot satisfy.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005, trap 6) **The no-declaration control.**
      Over a worktree whose diff includes `specs/<feature>/spec.md`, run the
      output check with **no** dispatched spec directory and assert the returned
      record equals a literally constructed `OutputCheck`, the way
      `tests/test_diff_hygiene.py:381` —
      `test_an_ordinary_diff_produces_todays_output_check_exactly` already does.
      Every existing caller and every stored row must be unaffected.
- [ ] T005 [P] [US1] (spec US1-S5, FR-006, traps 9 and 11) In
      `tests/test_interpreter.py`, run an epic whose graph has `specs_root`
      **inside** `target_repo` and assert the recorded `CheckOutputInput` names
      `specs/<feature>`. The default graph will not do: `tests/test_interpreter.py:425`
      — `make_graph` fills `specs_root` from `tests/test_interpreter.py:240` (the
      relative `"specs"`) and `target_repo` from `tests/test_interpreter.py:241`
      (an absolute path elsewhere), so the correct derivation yields nothing
      there. Pass the override — `make_graph` takes `**overrides` — and build the
      graph with `specs_root` under `TARGET_REPO`. The recorder already exists:
      `tests/test_interpreter.py:1477` — `check_output` appends the whole input to
      `script.output_requests`, and `tests/test_interpreter.py:4305`, inside
      `tests/test_interpreter.py:4282` —
      `test_the_diff_the_judge_scores_is_read_by_an_activity`, is the assertion to
      copy. Handing the directory to the library seam by hand cannot satisfy this
      scenario; that is what it is for.
- [ ] T006 [P] [US1] (spec US1-S6, FR-006, trap 8) In
      `tests/test_verify_activities.py` — the suite for the module T007 adds the
      helper to — drive the new derivation helper directly with a `specs_root`
      that is **not** under `target_repo`, using paths that do not exist on disk,
      and assert it yields nothing; the harness default of trap 11 is exactly this
      case. Then drive the same call again with `Path.exists` and `Path.stat`
      patched to raise and assert the answer is unchanged, so an implementation
      that reads the filesystem fails this test rather than passing it. `[P]` with
      T005: different module, different fixture.

### Implementation for this story

- [ ] T007 [US1] (FR-006, trap 8) Add the repository-relative derivation beside
      `factory/activities/verify_activities.py:208` — `spec_path`, as its sibling:
      `specs_root`, `target_repo` and `feature` in, the worktree-relative spec
      directory or nothing out, path arithmetic only.
      `Path(specs_root).relative_to(target_repo)` raising `ValueError` **is** the
      "the spec lives outside this repository" answer — return nothing there, and
      do not widen the `except` to swallow anything else.
- [ ] T008 [US1] (FR-001, FR-002, FR-003, traps 2, 6 and 7) Add a pure function
      beside `factory/verify/diffcheck.py:311` — `hygiene_violations` that returns
      one entry per changed path that is `spec.md`, `plan.md` or `tasks.md`
      **directly inside** the dispatched spec directory; give the library
      `factory/verify/diffcheck.py:172` — `check_output` the new optional
      parameter that carries that directory, defaulting to nothing; and append the
      function's result to the list built at
      `factory/verify/diffcheck.py:239` — `check_output`. Decide by path only —
      never by reading the file's content, so a checkbox tick and a rewritten
      SHALL clause are refused alike (trap 13). Every other path inside that
      directory is untouched — anything under `evidence/`, any
      `attempt-report-<story>.md`, anything else — because fifty evidence files
      and fifteen attempt reports across twelve directories already landed on
      their own nodes' PRs (trap 2). Do **not** refuse the directory and carve
      `evidence/` back out: that rule passes T001 and fails T002 on the attempt
      report. Do **not** add a name to
      `factory/verify/diffcheck.py:287` — `runtime_root_prefixes`, which would
      refuse every path under `specs/` in every repository, and do **not** touch
      `factory/verify/diffcheck.py:166` — `decide_passed`, which already refuses on
      a non-empty list. Amend the "Two shapes occur" paragraph in
      `factory/verify/models.py:413` — `HygieneViolation` to enumerate the new rule
      shape.
- [ ] T009 [US1] (FR-005) Add the optional dispatched-spec-directory field to
      `factory/activities/verify_activities.py:294` — `CheckOutputInput`,
      defaulting to nothing, and pass it through the activity at
      `factory/activities/verify_activities.py:327` — `check_output` to T008's new
      library parameter. The default is what makes every payload written before
      this story behave exactly as it did — copy the wording of the field already
      carrying that contract there.
- [ ] T010 [US1] (FR-006, trap 8) Derive the directory from `request.graph` and
      pass it at `factory/workgraph/workflow.py:2609` — `_verify`, the site that
      already reads `prepared.path` on the next line. Without this line the
      refusal is a library parameter nobody sets, every test above still passes,
      and the defect is intact behind a landed story.
- [ ] T011 [US1] (FR-004) Confirm by reading that
      `factory/verify/diffcheck.py:166` — `decide_passed`,
      `factory/verify/diffcheck.py:311` — `hygiene_violations`,
      `factory/verify/diffcheck.py:287` — `runtime_root_prefixes` and the diff
      size refusal are byte-unchanged. **If any of them needed an edit, the design
      is wrong**: the verdict already refuses on a non-empty violation list.

### Verification for this story

- [ ] T012 [US1] Paste, as committed evidence, the output check's record for one
      worktree in four states — the dispatched `spec.md` changed, the same bytes
      written under `evidence/` instead, the same bytes written to
      `attempt-report-us1.md` beside it, and another spec's `spec.md` changed —
      showing `passed` and the recorded rule in each. The third state is the one
      that separates this rule from the directory-minus-`evidence/` rule trap 2
      refuses; do not omit it. Commit the file under this spec's own `evidence/`
      directory, which FR-003 is what permits.

## Phase 2: User Story 2 — Drift is measured against the bytes the node started from

### Tests for this story (write FIRST, must fail)

- [ ] T013 [US2] (spec US2-S1, FR-007, traps 1, 3 and 4) In
      `tests/test_verify_activities.py`, build a **real** repository and node
      worktree — `tests/target_repo.py:102` — `build_target_repo` then
      `tests/target_repo.py:131` — `add_worktree`, with `specs/<feature>/spec.md`
      committed before the worktree is attached — edit only the worktree's copy,
      compose a result whose `base_ref` is the repository's head, write an
      operator-side `spec.md` that still hashes to the dispatch snapshot, record
      through `tests/test_verify_activities.py:448` — `record`, and assert
      `criteria_drift` is true and the stored row's `criteria_sha256` is still the
      snapshot's. Build the operator-side file from
      `tests/test_verify_activities.py:465` — `write_criteria_source`. Do not copy
      `tests/test_verify_activities.py:1236` —
      `test_a_spec_edited_under_the_node_is_flagged_as_drift`: despite its name it
      edits the operator-side file and passes today. A bare directory with a file
      in it is not a worktree and has no base ref to compare against.
- [ ] T014 [US2] (spec US2-S2, FR-007, trap 4) **The discriminating control, and
      the reason this story was rebuilt.** Over the same real worktree, leave the
      worktree copy byte-identical to its base ref and make the operator-side copy
      — the one the dispatch snapshot was taken from — different from it, then
      assert `criteria_drift` is false. This is the ordinary dispatch where the
      operator's working tree is ahead of origin's landing head and no node has
      touched anything. An implementation that compares the worktree copy against
      the snapshot flags it and fails here. Not `[P]`: it shares T013's repository
      fixture.
- [ ] T015 [US2] (spec US2-S3, FR-008, trap 12) **The absence control, three
      halves in one test.** With no `specs/<feature>/spec.md` at the base ref and
      none in the worktree, assert `criteria_drift` is false; with the file at the
      base ref and deleted from the worktree, assert it is true; with the
      operator-side copy deleted, assert it is still true. Not `[P]`: it shares
      T013's fixture. A change that reuses
      `factory/activities/verify_activities.py:630` — `_has_drifted`'s
      unreadable-is-drift rule for the worktree comparison passes the first half of
      the suite and fails here, and would flag every dispatch of a spec that is not
      committed to the landing branch.
- [ ] T016 [P] [US2] (spec US2-S4, FR-009, trap 12) With a result that already
      carries drift and both copies matching their baselines, assert
      `criteria_drift` stays true, the way
      `tests/test_verify_activities.py:1274` —
      `test_drift_the_caller_already_detected_is_never_cleared` already does for
      the single-path case. In the same test, record a result whose `base_ref` is
      the `factory/verify/models.py:798` sentinel and assert no worktree read is
      attempted — patch the git wrapper to raise if it is called.
- [ ] T017 [US2] (spec US2-S5, FR-010, trap 9) In `tests/test_interpreter.py`,
      assert the `RecordVerificationInput` the workflow constructed carries the
      prepared worktree's path and the repository-relative spec directory T007
      derives. The existing fake at
      `tests/test_interpreter.py:1513` — `record_verification` appends only
      `request.result`, so add a **NEW** recorder list —
      `record_requests: list[RecordVerificationInput]`, declared beside
      `tests/test_interpreter.py:971` and appended at
      `tests/test_interpreter.py:1517` — and assert against that. Do **not** widen
      `script.records`: it is a `list[VerificationResult]` at
      `tests/test_interpreter.py:974` and sixteen sites in the same module read
      `r.node_id`, `r.attempt`, `r.verdict` and `r.criteria_sha256` off its
      members, so changing its element type breaks the suite. Asserting against
      `script.records` cannot satisfy this scenario, and calling the activity
      directly is the shortcut it exists to refuse.
- [ ] T018 [P] [US2] (FR-011) **The control.** Assert the recorded
      `criteria_sha256` is the dispatch snapshot's in every case above, and that
      the criteria the judge is handed are still the snapshot's — neither read may
      become an input to what is scored.

### Implementation for this story

- [ ] T019 [US2] (FR-007, FR-008, traps 4 and 12) In
      `factory/activities/verify_activities.py:602` — `_with_drift`, add the
      worktree comparison as its own function: the worktree copy is drift when it
      differs from the same repository-relative path at the result's `base_ref`,
      and is not drift when neither side carries the file. Compare blob identities
      rather than text — `git -C <worktree> rev-parse <base_ref>:<relpath>` against
      `git -C <worktree> hash-object -- <relpath>` — through
      `factory/workgraph/worktree.py:1940` — `_git`, the way
      `factory/activities/agent_activities.py:1103` — `_git_show` already reads a
      blob from an activity. A `WorktreeError` from either read means "no bytes on
      that side"; when both sides report none, the answer is false, and it is never
      true because git failed. Attempt nothing when the worktree path, the derived
      directory or a real base ref is missing. Leave
      `factory/activities/verify_activities.py:621` — `_has_drifted` and its
      unreadable-is-drift rule exactly as they are; that rule is right for the
      operator-side copy and wrong for this one. Preserve both contracts already
      in `_with_drift`'s docstring: drift the caller found is never cleared, and
      the row keeps the snapshot's hash.
- [ ] T020 [US2] (FR-010) Add the optional worktree-path and spec-directory fields
      to `factory/activities/verify_activities.py:467` — `RecordVerificationInput`,
      defaulting to nothing so every older payload is unchanged, and fill them at
      `factory/workgraph/workflow.py:2699` — `_verify` from the prepared
      worktree's path (`factory/workgraph/worktree.py:264` — `PreparedWorktree`)
      and T007's derivation, read off `request.graph` in the same function. Reuse
      that helper; do not re-derive it here. Add **no** base-ref field: the pin is
      already on the composed result at
      `factory/workgraph/workflow.py:2672` — `_verify`, and taking it from there is
      what guarantees the drift read uses the same base the gates and the judge
      were measured against (`factory/verify/models.py:942` —
      `VerificationResult`).
- [ ] T021 [US2] (FR-011, trap 10) Record in a code comment that this supersedes
      `specs/102-a-spec-that-cannot-be-satisfied-fails-validate/spec.md:215`
      (FR-011, "leave `criteria_drift`'s hashing unchanged") **for the drift
      inputs only** — the hash function, the snapshot and the recorded value are
      untouched; what changed is which files are compared, and against what.
      Confirm by reading that `factory/verify/criteria.py:480` — `load_criteria`
      and `factory/workgraph/workflow.py:1736` — `_run_node` needed no edit.

### Verification for this story

- [ ] T022 [US2] Paste, as committed evidence, the recorded drift value for four
      recordings over one snapshot hash — worktree copy edited away from its base
      ref, worktree copy matching its base ref while the snapshot differs, worktree
      copy and base ref both absent, and a result carrying the unknown base-ref
      sentinel — each showing `criteria_drift` and the row's `criteria_sha256`.
      The second is the one that separates this rule from the
      compare-against-the-snapshot rule trap 4 refuses; do not omit it. This
      story's own evidence file lands under
      `specs/137-a-node-cannot-move-the-bar-it-is-measured-against/evidence/`,
      through the refusal US1 already merged; if it is refused, FR-003 was built
      wrong and that is the finding, not this task.

## Verification

- [ ] T023 The full gate command passes green.
- [ ] T024 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end — step 0 first, because filing the residue row
      before dispatch is what stops a triage sweep closing a critical row on a
      half-fix, and step 7 last, because the declared row's own notes are wrong.
      Step 1 paired with step 2 is the falsifiable test of US1: the first is
      `701be6e` — a node deleting a sentence from the spec it was dispatched
      against — run forwards and refused, the second is the fifty committed files
      under `specs/*/evidence/` and the fifteen `attempt-report-<story>.md` files
      still landing. Step 1 paired with step 5 is the falsifiable test of US2:
      drift on the edit a node made, silence on the divergence it did not.
