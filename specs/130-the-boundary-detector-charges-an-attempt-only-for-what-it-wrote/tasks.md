# Tasks: the boundary detector charges an attempt only for what it wrote

Read `plan.md` before starting. Six of its traps are unusual and none may be
skipped.

Trap 1 and trap 9 are the same shape twice: a **committed spec** requires the
behaviour this spec removes, and says so in its own text. 073-US4 scenario 2 (and
011-US1 scenario 5, and the landed 011 FR-012 behind them at
`specs/011-agent-sandbox/spec.md:358`) require that a removed sibling worktree
files a finding; 011-US1 scenario 3 requires that an operator's own edit is
reported. Neither must survive — the factory itself removes sibling worktrees as
ordinary housekeeping, and the operator edit case is the one that made a
`critical` channel unreadable. Override those scenarios and invert their committed
tests openly, saying in the diff which scenario is overridden and why; do not
delete anything quietly. **Five committed tests carry edits, not two**: two in
`tests/test_detector_reports_removals_only.py` — the control inverted at
`tests/test_detector_reports_removals_only.py:176` and the sibling-naming
assertion at `tests/test_detector_reports_removals_only.py:158` — and three in
`tests/test_us1_detector.py`: the sibling assertion at
`tests/test_us1_detector.py:460-462` (US2), the operator-work control at
`tests/test_us1_detector.py:322` and the pre-attempt write at
`tests/test_us1_detector.py:386` (US4). Each is green today and each goes red on
the story that must edit it; T009, T020 and their bodies name all five.

Trap 15 bounds how that override may be written. Both overridden specs are
`state: landed`, and a landed story's identity digest is built from its title, its
acceptance-scenario text, its work-graph declaration and the bodies of the FRs it
implements — `factory/workgraph/landed.py:438` — `_story_parts`. Change any of
those four and `factory/workgraph/delta.py:142` — `derive_delta` stops subtracting
the story and **reopens it as a node to dispatch**. So the override is written in
a `#` provenance line inside the landed spec's frontmatter fence, in the inverted
test's docstring and in the commit message — and the scenario text stays
byte-identical. Editing the scenario "to record the override" spends a future
attempt rebuilding a story that landed weeks ago.

Trap 14 is the opposite hazard: US1's obvious fixture is **green before any
production change**, because the derive write is deterministic. A test that cannot
fail proves nothing, and it is the phase's "must fail first" rule that catches it.

Trap 3 is the one that would ship broken: the guard for FR-001 must not deny the
write to `ergane build ship --json`, which reaches the same handler with
`as_json=True` and no output path, and which no committed test exercises.

Trap 10 runs the other way: US2 must **leave** `EXCLUDED_DIR_NAMES`,
`EXCLUDED_SUFFIXES` and `_snapshot_paths` in place even after they stop being
reached. Removing them is US3's entire production diff.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output — and it must be output a
node in a worktree can produce, which means a pytest transcript, never a live
two-epic run (trap 13).

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A read-only-looking verb does not write

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 14) Given a spec directory whose
      committed work-graph artifact **differs from what this invocation would
      derive** — seed its `target_repo` with another path, which is the harm the
      ledger row records — assert `ergane spec derive --json` with no output path
      leaves those seeded bytes on disk. The seeding is the point: derive-then-
      re-derive compares one deterministic output against itself and passes today,
      so run this test before writing T006 and confirm it fails.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) **The control.** Given an explicit
      output path, assert `--json` writes to it. An explicit path is a request to
      persist.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) **The control that matters.** Assert
      `spec derive` **without** `--json` still writes the artifact. 97 committed
      artifacts exist in this tree and the dispatch path reads one off disk.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, traps 4 and 14) Assert the `--json`
      document emitted with no output path carries **no** artifact path — the key
      is absent or null. Parse the printed document and assert on the key; do not
      grep the text. Asserted as "it does not name a file that was not written"
      the check passes today, because today the file is always written.
- [ ] T005 [US1] (spec US1-S5, FR-011, trap 3) **The control that would have been
      missed.** Assert `ergane build ship --json` still finds the artifact and
      reaches its summary. Build the namespace the way ship's own parser does —
      `--json` is `dest="as_json"` at
      `factory/cli/nouns/build.py:2134` — `add_parser` — and check the test fails
      against a guard keyed on `--json` alone. Not `[P]`: it constrains the shape
      T006 may take.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, FR-011, traps 3 and 4) In
      `factory/workgraph/cli.py`, stop the unconditional write at
      `factory/workgraph/cli.py:384` — `derive_command` from happening when the
      caller asked to print and nothing more, without denying it to a caller that
      requires the artifact on disk —
      `factory/cli/nouns/build.py:1045` — `ship_command`, which then demands it at
      `factory/cli/nouns/build.py:1051` — `ship_command`. FR-002 already makes an
      explicit output path a request to persist, which is the cheapest seam. Then
      fix the `"artifact"` key emitted at
      `factory/workgraph/cli.py:391` — `derive_command`, which otherwise names a
      file that was not written.

### Verification for this story

- [ ] T007 [US1] Paste, as committed evidence, the pytest transcript of this
      phase's tests, and **two pairs** of `sha256sum` output for a work-graph
      artifact seeded with a different `target_repo`, taken before and after a real
      `ergane spec derive --json` run: one pair from before T006 (the sums must
      **differ**, which is the defect) and one from after (the sums must match).
      A single matching pair proves nothing — it is what today's tree already
      produces when the artifact equals the derivation (trap 14). Copy the spec
      directory into a temporary path rather than deriving in place, so the
      evidence does not commit a rederived artifact.

## Phase 2: User Story 2 — The detector watches the attempt's own worktree

### Tests for this story (write FIRST, must fail)

- [ ] T008 [P] [US2] (spec US2-S1, FR-004) **The control.** Given an attempt
      running while a **sibling** node's worktree is written to, assert no finding
      is filed against the running attempt. This is already true through the
      loss-only rule at `factory/workgraph/detector.py:134` — `_is_loss`, so this
      test is green before the story and must stay green after it — do not try to
      make it fail first.
      `tests/test_detector_reports_removals_only.py:58` — `sibling` is the fixture
      to copy.
- [ ] T009 [US2] (spec US2-S2, FR-005, traps 1 and 15) Given an attempt running
      while a sibling worktree is **removed**, assert no finding is filed — and
      **override 073-US4 scenario 2 without editing it**. Invert its committed
      test, `tests/test_detector_reports_removals_only.py:176` — `test_sibling_worktree_removed_files_a_finding_naming_it`,
      and name the overridden scenario
      (`specs/073-the-ledger-triages-what-it-can-prove/spec.md:282`) and the reason
      in its docstring. Record the override itself as a `#` provenance line inside
      the frontmatter fence of
      `specs/073-the-ledger-triages-what-it-can-prove/spec.md`, naming this spec
      and FR-005; do the same in `specs/011-agent-sandbox/spec.md` for the
      sibling-worktree half of its US1 scenario 5 and for FR-012 at
      `specs/011-agent-sandbox/spec.md:358`. **Leave both specs' scenario text,
      story titles, `## Work Graph` blocks and FR bodies byte-identical** — those
      four are the delta fingerprint
      (`factory/workgraph/landed.py:461` — `_story_parts`), and a moved digest
      reopens a landed story as a node to dispatch
      (`factory/workgraph/delta.py:142` — `derive_delta`, trap 15).
      **Three tests need edits here, not one.** Edit
      `tests/test_detector_reports_removals_only.py:144` — `test_sibling_worktree_gaining_files_files_no_finding`
      in the same pass: exactly one of its two snapshot assertions goes red, the
      one naming `sibling.py` at
      `tests/test_detector_reports_removals_only.py:158`. Its neighbour at
      `tests/test_detector_reports_removals_only.py:157` — the bare
      `assert entries` — stays true and must be kept, because the three store files
      recorded at `factory/workgraph/detector.py:323` — `_runtime_root_state`
      survive this story and are what keeps the snapshot non-empty; update that
      line's message string, not its assertion. Its final no-finding assertion
      stays. And edit
      `tests/test_us1_detector.py:429` — `test_agent_truncating_runtime_root_store_files_finding`:
      it truncates the sibling worktree at `tests/test_us1_detector.py:449` and
      asserts at `tests/test_us1_detector.py:460-462` that the finding names it, so
      exactly that assertion goes red under T013. Remove it; keep the `doctor.db`
      and `ledger.db` assertions and the read-only assertion at
      `tests/test_us1_detector.py:468`. State in the diff that this spec
      deliberately overrides three committed scenarios — 073-US4-S2, 011-US1-S5 and
      011's FR-012 at `specs/011-agent-sandbox/spec.md:358` — and why:
      `factory/workgraph/workflow.py:3582` — `_remove_worktree` is called from four
      sites in the workflow, so 073's control fires on the factory's own
      housekeeping. Not `[P]`: it touches two other specs' files and two test files
      other tasks in this phase read.
- [ ] T010 [P] [US2] (spec US2-S3, FR-009) **The control.** Given an attempt that
      genuinely writes outside its own worktree — a tracked path modified in the
      target repository, or an evidence store truncated — assert a `critical`
      finding is filed with its evidence unchanged from today's, and that
      `tests/test_us1_detector.py:249` — `test_agent_modifying_tracked_file_in_target_repo_files_finding`
      passes **unedited**. The store half of
      `tests/test_us1_detector.py:429` — `test_agent_truncating_runtime_root_store_files_finding`
      must also pass, but that test is **not** unedited: T009 removes its
      sibling-worktree assertion. Assert on what survives — the `doctor.db` and
      `ledger.db` halves and the read-only assertion — not on the file being
      untouched.
- [ ] T011 [P] [US2] (spec US2-S4, FR-010, trap 2) **The control.** Assert
      `compare_and_report`'s return value still gates nothing at
      `factory/workgraph/adapter.py:1177` — `run_attempt` and
      `factory/workgraph/adapter.py:1185` — `run_attempt`. An accurate detector
      must not become an enforcing one in the same change.
- [ ] T012 [P] [US2] (spec US2-S5, FR-009) **The control for the worst case.**
      Assert that deleting the runtime root outright during the attempt still files
      a finding naming the evidence stores, and that
      `tests/test_us1_detector.py:476` — `test_detector_reports_even_when_runtime_root_is_deleted`
      passes unedited.
      This is the 2026-08-14 destruction, and it must survive US2.

### Implementation for this story

- [ ] T013 [US2] (FR-004, FR-005, traps 10 and 12) In
      `factory/workgraph/detector.py:311` — `_runtime_root_state`, stop
      snapshotting node worktrees. Today it walks every node directory under
      `<root>/worktrees/<epic>/<node>` and skips exactly one, at
      `factory/workgraph/detector.py:336` — `_runtime_root_state`; after this
      story it visits none of them, and the three named store files it records
      before that loop are what the runtime-root half compares. Leave
      `factory/workgraph/detector.py:349` — `_snapshot_paths` and the two exclusion
      constants where they are — US3 removes them (trap 10). Correct the module
      docstring at `factory/workgraph/detector.py:1` and the docstring at
      `factory/workgraph/detector.py:314` — `_runtime_root_state`, both of which
      state the behaviour this task removes.

### Verification for this story

- [ ] T014 [US2] Paste, as committed evidence, the pytest transcript of this
      phase's tests — including the unedited controls named in T010 and T012, and
      the edited `tests/test_us1_detector.py:429` — `test_agent_truncating_runtime_root_store_files_finding`
      passing on its surviving halves — from a run over
      `tests/test_detector_reports_removals_only.py` and
      `tests/test_us1_detector.py`. Paste also
      `git diff specs/073-the-ledger-triages-what-it-can-prove/spec.md` and
      `git diff specs/011-agent-sandbox/spec.md`, showing that every changed line is
      a `#` comment inside the frontmatter fence and that no scenario, story title,
      work-graph line or FR body moved (trap 15). A live two-epic run is the
      operator's step, not this node's (trap 13).

## Phase 3: User Story 3 — The detector carries no language-shaped list

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US3] (spec US3-S1, FR-006, trap 8) Assert the detector module
      defines no generated-path exclusion list: import it and assert
      `EXCLUDED_DIR_NAMES`, `EXCLUDED_SUFFIXES` and `_snapshot_paths` are absent,
      and that no ignore-rule parser or new dependency replaced them.
- [ ] T016 [P] [US3] (spec US3-S2, FR-006) **The control.** Given a **target**
      repository whose own `.gitignore` covers a generated directory, assert writes
      into it file no finding — because
      `factory/workgraph/detector.py:265` — `_tracked_state` reads untracked files
      with `--exclude-standard` in the target repository. That mechanism is already
      there, so this test is green before the story: its job is to stay green
      through the removal, and trying to make it fail first is the shortest path to
      the ignore-rule parser trap 8 forbids.
      The rules must come from the target, not from this repository: a fix that
      reads ergane's own `.gitignore` works on this floor and fails on every
      consumer.
- [ ] T017 [P] [US3] (spec US3-S3, FR-006) **The control.** The same fixture with
      the `.gitignore` line removed: assert a write outside the worktree still
      files a finding. Ignoring is the target's statement, not the detector's
      guess.

### Implementation for this story

- [ ] T018 [US3] (FR-006, trap 8) Remove `EXCLUDED_DIR_NAMES`
      (`factory/workgraph/detector.py:70`), `EXCLUDED_SUFFIXES`
      (`factory/workgraph/detector.py:73`) and
      `factory/workgraph/detector.py:349` — `_snapshot_paths`, which US2 left
      unreferenced. Do not replace them with a `.gitignore` parser, a new
      dependency or a `git check-ignore` call — the surviving rule is the one the
      target repository already applies. Update the two comments that name the
      constant, at `factory/activities/roadmap_activities.py:190` and
      `tests/test_090_refusal_parks_the_spec.py:35`, and nothing else in those two
      files.

### Verification for this story

- [ ] T019 [US3] Paste, as committed evidence, the pytest transcript of this
      phase's tests, and the output of `grep -rn "EXCLUDED_DIR_NAMES\|EXCLUDED_SUFFIXES" factory/`
      showing no definition remains.

## Phase 4: User Story 4 — A finding names the repository, and the operator's own work is not it

### Tests for this story (write FIRST, must fail)

- [ ] T020 [US4] (spec US4-S1, FR-007, traps 9 and 15) Given a change already
      present in the target repository's working tree when the attempt begins,
      assert no finding is filed for that path — and **override 011-US1 scenario 3
      (`specs/011-agent-sandbox/spec.md:191`) without editing it, while editing
      BOTH of its committed controls**, which require the opposite. Record the
      override as a `#` provenance line inside `specs/011-agent-sandbox/spec.md`'s
      frontmatter fence and in each edited test's docstring; leave that spec's
      scenario text, story titles, `## Work Graph` block and FR bodies
      byte-identical, because those four are the delta fingerprint
      (`factory/workgraph/landed.py:461` — `_story_parts`) and a moved digest
      reopens landed 011-US1 as a node to dispatch
      (`factory/workgraph/delta.py:142` — `derive_delta`, trap 15). The first
      control is
      `tests/test_us1_detector.py:322` — `test_operator_work_is_reported_and_untouched`.
      The second is not obvious and is the one that will otherwise be met red at the
      gate:
      `tests/test_us1_detector.py:357` — `test_detector_runs_on_completed_agent_error_timeout_and_killed`
      writes its tracked change at `tests/test_us1_detector.py:386`, before each of
      its four attempts — and `capture_start` runs inside
      `factory/workgraph/adapter.py:1129` — `run_attempt` before the agent launches,
      so under FR-007 all four iterations record it at start and report nothing.
      Do not weaken its closing assertions: move each iteration's write to *during*
      the attempt, as
      `tests/test_us1_detector.py:249` — `test_agent_modifying_tracked_file_in_target_repo_files_finding`
      already does. Re-read the whole file for that shape before you start. Say in
      the diff which scenario is overridden and why. Not `[P]`: it touches another
      spec's file and a test file other tasks in this phase read.
- [ ] T021 [P] [US4] (spec US4-S2, FR-007) Given the target repository's HEAD moves
      during the attempt because the operator committed, assert no finding is filed
      for the paths that commit carried, **and** that a path the attempt changed on
      top of that commit is still filed. One test, both halves — the second half is
      what stops this becoming a hole.
- [ ] T022 [P] [US4] (spec US4-S3, FR-008) Given a finding that **is** filed,
      assert it names the target repository, using the value
      `factory/workgraph/detector.py:405` — `_write_snapshot` already captures and
      `factory/workgraph/detector.py:598` — `compare_and_report` today drops.
- [ ] T023 [P] [US4] (spec US4-S4, FR-007) **The control.** Given a genuine escape
      by the running attempt, assert the finding is filed exactly as today with its
      evidence intact.
- [ ] T024 [P] [US4] (spec US4-S5, FR-007, trap 9) **The half of 011-US1-S3 that
      survives.** Assert the detector still only reads the target repository: the
      operator's file is byte-identical after the attempt, and nothing was stashed,
      checked out or cleaned.

### Implementation for this story

- [ ] T025 [US4] (FR-007, FR-008, traps 9 and 12) In
      `factory/workgraph/detector.py`, make the start snapshot the same kind as the
      teardown snapshot so a change already present when the attempt began is not
      attributed to it —
      `factory/workgraph/detector.py:533` — `capture_start` takes the committed
      tree from
      `factory/workgraph/detector.py:279` — `_committed_state` while
      `factory/workgraph/detector.py:592` — `compare_and_report` takes the working
      tree. Record the target repository's HEAD in the start snapshot written at
      `factory/workgraph/detector.py:405` — `_write_snapshot` so a commit during
      the attempt is distinguishable from a write, and compare against the tree
      that HEAD names. Carry the captured `target_repo` through
      `factory/workgraph/detector.py:598` — `compare_and_report` into
      `factory/workgraph/detector.py:440` — `_build_finding` so the finding names
      its repository. Correct the docstrings at
      `factory/workgraph/detector.py:203` — `_tracked_state` and
      `factory/workgraph/detector.py:279` — `_committed_state`, which assert the
      behaviour this task reverses, and the comment in `tests/test_us3_boundary.py`
      that explains why its fixture commits first.

### Verification for this story

- [ ] T026 [US4] Paste, as committed evidence, the pytest transcript of this
      phase's tests, including **both** edited 011 controls —
      `tests/test_us1_detector.py:322` — `test_operator_work_is_reported_and_untouched`
      and
      `tests/test_us1_detector.py:357` — `test_detector_runs_on_completed_agent_error_timeout_and_killed`
      — and the escape control, all passing in the same run. Paste also
      `git diff specs/011-agent-sandbox/spec.md`, showing every changed line is a
      `#` comment inside the frontmatter fence and that no scenario, story title,
      work-graph line or FR body moved (trap 15).

## Verification

- [ ] T027 The full gate command passes green.
- [ ] T028 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 2 — raising `max_concurrent_epics` to 2 and
      running two overlapping epics — is the falsifiable test of this whole spec:
      that dial has been pinned at 1 for an entire build because of this detector,
      and raising it is the outcome that justifies the work. Step 5's ledger sweep
      is an operator act this spec does not perform, which is why
      `hardening/agent-worktree-boundary` is not in `fixes:` (trap 7). Step 6 is the
      proof that neither overridden landed story was reopened by the override
      (trap 15). Step 0 is not run here at all: it is the operator's act *before*
      dispatch, deleting the `workgraph.json` compiled in this spec directory
      before FR-011 existed, because a `build start` from that artifact never puts
      FR-011 in front of the judge.
