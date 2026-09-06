# Tasks: the findings store knows which repository it is about

Read `plan.md` before starting. Seven of its traps are the ones that make a green
story worthless. Trap 1: a migration keyed off `SCHEMA_VERSION` never fires,
because `factory/doctor/store.py:127` — `_bootstrap_schema` stamps the version
only into a store that has none, and every test store is created fresh so nothing
goes red. Trap 12: the fixture that proves the migration must be a frozen literal
in the test module, because the contract file the obvious fixture reads is a file
this same story rewrites. Trap 13: the migration can only run through
`factory/doctor/store.py:86` — `connect`, so a SELECT list that names the new
column unconditionally crashes `ergane spec validate`'s own fixes layer. Trap 2:
`ergane doctor` runs `factory/cli/doctor.py:177` — `doctor_command`, not the
identically named handler in `factory/doctor/cli.py` that the source triage entry
cited — and it must learn its repository from the working directory, not from a
new flag (trap 6, FR-017). Trap 10: the detector's repository must be threaded at
`factory/workgraph/detector.py:598` — `compare_and_report`, not merely accepted by
`factory/workgraph/detector.py:440` — `_build_finding`, and `compare_and_report`
files a **second** finding inline at
`factory/workgraph/detector.py:556-578` that never goes near `_build_finding` —
and for both of those findings the assertion is on the repository **column** read
back through `factory/doctor/store.py:478` — `get_finding`, never on the summary,
which 130 already fills in. Trap 9: `factory/doctor/models.py:81` —
`parse_findings_batch` **refuses** a batch holding one key twice
(`factory/doctor/models.py:138` — `parse_findings_batch`), a landed test and a
committed fixture hold that rule, and T015 will die on it long before it reaches
the dedupe it came to change. Re-qualify the rule on the (key, repository) pair;
deleting it is the regression T017a exists to catch.

Trap 15 is the one that decides whether US3 tests anything at all: two working
directories are two *ledgers* unless both runs are pinned to one store, because
`factory/cli/doctor.py:65` — `_store_path` falls through to
`factory/workgraph/worktree.py:191` — `resolve_factory_root` and its default
`factory/workgraph/worktree.py:93` is a relative path. Unpinned, T026 and T027
pass against the unmodified tree. Keep the session fixture's pin at
`tests/conftest.py:545`, or pass both runs the same `--db`, and change only the
cwd — never copy `tests/test_runtime_root_findings.py:65` — `_chdir_tmp`, which
deletes those variables on purpose.

Read trap 14 too before touching `factory/workgraph/detector.py`: draft spec
`specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote` owns
the same seam, this spec's frontmatter waits on it as landed, and what remains
here depends on what 130 actually landed.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The ledger has a repository column, and an existing store gains it without losing a row

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002, trap 3) Assert that a store
      created fresh by `connect` has a nullable repository column on `findings`
      and both a repository column and a refs column on `finding_events`, by
      reading `PRAGMA table_info` for each table. Assert nullability explicitly:
      trap 3 explains why `NOT NULL` cannot be used here.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003, trap 12) Build a database from a
      **frozen literal** copy of the version-1 DDL, written out as a constant in
      the test module the way `tests/test_escalation_record.py:156`
      (`_PRE_041_ESCALATIONS_DDL`) is, with the same comment saying why. The
      fixture MUST NOT read `specs/015-factory-doctor/contracts/doctor-store.sql`
      and MUST NOT use `tests/test_doctor_store.py:130` — `contract_db`: T007
      rewrites that contract in this same story, so a fixture built from it is a
      post-migration store and every assertion below passes for free. Populate it
      with findings and events, open it with `connect`, and assert every prior
      `findings` row survives with all **fourteen** of its previous column values
      unchanged and every prior `finding_events` row with all **six** of its own
      (the two tables are not the same width), the new columns exist, and the
      pre-existing rows read as no repository stated. Compare one row of each
      table before and after, not just the row counts.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, traps 1 and 12) Open that same
      frozen-literal store a second and third time and assert the row count and
      column list are equal across all three opens. An unconditional
      `ALTER TABLE` raises `duplicate column name` on the second connect, and
      `connect` runs on every report.
- [ ] T004 [P] [US1] (spec US1-S4, FR-004, trap 4) Assert the committed contract
      at `specs/015-factory-doctor/contracts/doctor-store.sql` declares the new
      columns, so the module DDL and the contract cannot be edited apart. This is
      the half `tests/test_doctor_store.py:142` —
      `test_a_new_store_matches_the_published_contract_ddl` cannot state on its
      own: it only proves the two agree, not that either is right.
- [ ] T005 [P] [US1] (spec US1-S5, FR-016, trap 13) Open the frozen-literal
      version-1 store from T002 **without** letting `connect` touch it, using
      `factory/doctor/store.py:98` — `connect_readonly`, and assert that
      `factory/doctor/store.py:478` — `get_finding`,
      `factory/doctor/store.py:454` — `list_findings` and
      `factory/doctor/store.py:493` — `list_events` all return their rows with
      the repository reading as none rather than raising
      `sqlite3.OperationalError: no such column`. That connection sets
      `query_only = ON` and can never migrate, and the two consumers behind it are
      `factory/cli/nouns/spec.py:1231` — `_check_fixes` (no `except` around the
      call at `factory/cli/nouns/spec.py:1282` — `_check_fixes`, so validate
      crashes rather than
      skipping a layer) and `factory/cli/doctor.py:394` —
      `findings_triage_command`.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, traps 3 and 8) Add the nullable repository
      column to `findings` and the nullable repository and refs columns to
      `finding_events` in `_SCHEMA_DDL` (`factory/doctor/store.py:50-68` and
      `factory/doctor/store.py:70-79`). Two sentences elsewhere become false the
      moment this lands and are part of this task: the module docstring at
      `factory/cli/repo_export.py:7-8` ("No store here has a repo column") and the
      docstring of `tests/test_ergane_repo_forget.py:391` —
      `test_export_carries_only_the_departing_repos_rows`. Correct the prose;
      change nothing about what the export selects.
- [ ] T007 [US1] (FR-004, trap 4) Make the identical edit to
      `specs/015-factory-doctor/contracts/doctor-store.sql:23` and to the two
      expectation lists the suite holds it by,
      `tests/test_doctor_store.py:148` —
      `test_the_findings_columns_match_the_contract` and
      `tests/test_doctor_store.py:156` —
      `test_the_finding_events_columns_match_the_contract`. Do not loosen either
      assertion; that is the guarantee, not the obstacle.
- [ ] T008 [US1] (FR-003, trap 1) Raise `SCHEMA_VERSION`
      (`factory/doctor/store.py:20`) and add a migration called from
      `factory/doctor/store.py:123` — `_bootstrap_schema`, modelled on
      `factory/usage/ledger.py:142` — `_bootstrap_schema` calling
      `factory/usage/ledger.py:237` — `_migrate`. Key it off `PRAGMA
      table_info(findings)` — whether the column is there — and **not** off the
      recorded version, for the reason written at
      `factory/usage/ledger.py:167-170`, beside the constant at
      `factory/usage/ledger.py:171`: a version is a claim and the schema is
      the fact. `factory/doctor/store.py:127` — `_bootstrap_schema` is the line
      that makes a version-keyed migration a no-op forever.
- [ ] T009 [US1] (FR-001, FR-002, FR-016, trap 13) Add **three** fields across the
      two frozen carriers — `repository` on `factory/doctor/models.py:30` —
      `Finding`, and `repository` **and** that observation's own `refs` on
      `factory/doctor/models.py:48` — `FindingEvent` (one field on the first
      carrier, two on the second, matching T006's columns) — each defaulting to
      none so FR-005 holds by construction. One field per carrier is the misreading
      to avoid: it leaves `FindingEvent.refs` for US2, in a story that no longer
      owns the migration. Then make the read path serve a store that has not
      been migrated yet: `factory/doctor/store.py:454` — `list_findings`,
      `factory/doctor/store.py:478` — `get_finding` and — the third explicit
      SELECT list, and the one no requirement reached before this repair —
      `factory/doctor/store.py:493` — `list_events` (FR-002, FR-016) must read the
      columns the store actually has (`PRAGMA table_info`), or select the known
      columns and fill the new ones from a guarded read. `list_events` must also
      return the two new event fields, or US2-S1's trail can only be read with raw
      SQL. Adding the new names to those SELECT lists and stopping is the wrong
      move: the migration only ever
      runs through `factory/doctor/store.py:86` — `connect`, and the read-only
      door `factory/doctor/store.py:98` — `connect_readonly` is what
      `ergane spec validate` and `ergane findings triage` use.
- [ ] T010 [US1] (FR-005, FR-006, trap 11) Confirm by reading that neither
      `factory/workgraph/worktree.py:191` — `resolve_factory_root` nor
      `factory/doctor/cli.py:58` — `_resolve_store_path` needed an edit. **If
      either did, the design is wrong**: the repository is a column, not a path.

### Verification for this story

- [ ] T011 [US1] Paste, as committed evidence, a `sqlite3` transcript over a copy
      of a real version-1 store: the row and event counts and `PRAGMA
      table_info(findings)` **before** the migration — it must read fourteen
      columns, which is what proves the fixture is a pre-143 store and not the new
      contract — and the same three readings after it, plus the same readings
      after a second `connect`. Paste beside it the output of
      `ergane spec validate` run against a second, deliberately un-migrated copy,
      showing the fixes layer answering rather than raising `no such column`.

## Phase 2: User Story 2 — Every report names the repository it is about, and the trail keeps its own evidence

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-008) Report one key twice with different
      refs, the first naming one repository and the second another, and assert the
      trail holds two events, each with its own repository and its own refs, and
      that the first event's refs are still what the first report supplied. Read
      the trail through `factory/doctor/store.py:493` — `list_events`, which T009
      already taught to return the two new fields, not through raw SQL against
      `finding_events`: a test that reaches around the product proves nothing
      about the product. This is the provenance half; the upsert at
      `factory/doctor/store.py:165-171` — `report` is what destroys it today.
- [ ] T013 [P] [US2] (spec US2-S2, FR-009, trap 6) Assert that
      `ergane findings report` with the repository named records it, **and** that
      the same command with no repository named records none. Both halves in one
      test: defaulting the resolver in would pass the first half alone while
      writing an unstated fact into the ledger.
- [ ] T014 [US2] (spec US2-S3, FR-010, traps 10 and 14) Drive
      `factory/workgraph/detector.py:538` — `compare_and_report` with a real
      `target_repo` and a start snapshot on disk, and assert the row read back
      through `factory/doctor/store.py:478` — `get_finding` carries that
      repository **on the repository field**, as that field's value. Assert the
      **field, not the summary text**: 130 lands before this spec by the
      frontmatter's `depends_on_landed` edge and its US4-S3 already puts the
      repository into the finding's summary and refs, so a text assertion passes
      with a zero-line diff in `factory/workgraph/detector.py`. The test may not
      call `_build_finding` directly and may not construct the `Finding` itself —
      that shortcut is exactly what leaves production filing findings about no
      repository. Not `[P]`: it drives the same detector surface as T015 and T017.
- [ ] T015 [US2] (spec US2-S4, FR-011, trap 9) Fire the detector for two different
      target repositories against one runtime root and assert
      `<runtime-root>-detector/findings.json` holds two entries, one per
      repository, and that re-ingesting that file through
      `factory/doctor/models.py:81` — `parse_findings_batch` still carries each
      entry's repository, asserted on each parsed `Finding`'s repository field
      rather than on its summary or refs. The dedupe to change is
      `factory/workgraph/detector.py:621` — `_persist_finding`. Expect this test
      to fail **first** on the parser, not on the dedupe: both entries carry the
      one class key `factory/workgraph/detector.py:419` — `_finding_key` returns,
      and `factory/doctor/models.py:138` — `parse_findings_batch` rejects a
      repeated key outright with `duplicate_key`. That is T022's work, and T017a
      is the control that stops the rejection being deleted instead of
      re-qualified. A repository added to the JSON but not to the constructor's
      field list is dropped silently at
      `factory/doctor/models.py:145-163` — `parse_findings_batch`.
- [ ] T016 [P] [US2] (spec US2-S5, FR-007, trap 5) Report a finding against a
      repository's top level and another against a subdirectory inside the same
      work tree, and assert both rows record the identical repository string.
      Without one resolver a repository has as many identities as it has
      spellings.
- [ ] T017 [US2] (spec US2-S6, FR-010, trap 10) **The second construction site.**
      Drive `factory/workgraph/detector.py:538` — `compare_and_report` with **no**
      start snapshot on disk, so the branch at
      `factory/workgraph/detector.py:554` — `compare_and_report` fires, and assert
      the CRITICAL it builds inline at `factory/workgraph/detector.py:556-578` and
      persists at `factory/workgraph/detector.py:579` — `compare_and_report`
      carries the target repository on its repository field, read back through
      `factory/doctor/store.py:478` — `get_finding`. The **field, not the summary
      text**, for T014's reason. This test is the one a diff that threads only
      `_build_finding` fails while T014 still passes. Not `[P]`: same surface as
      T014.

- [ ] T017a [US2] (spec US2-S7, FR-011, trap 9) **The control on T015's fix.**
      Assert that a batch holding two entries under one key that name the **same**
      repository is still refused naming that key — and that the landed guard
      `tests/test_doctor_models.py:90` —
      `test_batch_duplicate_key_refuses_naming_key` still passes against
      `tests/fixtures/doctor/batch-duplicate-key/findings.json` **unedited**,
      whose two entries name no repository at all and are therefore still an equal
      pair. Without this task the cheapest way to make T015 green is deleting the
      `duplicate_key` rejection, which lets a genuinely repeated entry inside one
      repository upsert twice and inflate the `occurrences` total 073 FR-024
      exists to keep honest. Not `[P]`: it constrains the same edit as T022.

### Implementation for this story

- [ ] T018 [US2] (FR-007, trap 5) Add the single repository resolver — git top
      level when the path is inside a work tree, otherwise the resolved absolute
      path, copying the `rev-parse --show-toplevel` call at
      `factory/cli/init.py:295` — `resolve_repo_root` — in the module every
      writer already imports from
      (`factory/doctor/models.py:30` — `Finding`'s module), and route all three
      writers through it. Write down in a comment why a dataclass-and-grammar
      module now shells out to git: the alternative is a second spelling rule.
- [ ] T019 [US2] (FR-008) Write the repository onto the row and append it, with
      that report's own refs, to the event in `factory/doctor/store.py:137` —
      `report`. The row keeps naming the latest observation, as it does today; the
      trail is what stops losing the earlier ones. The two event fields written
      here are the two `factory/doctor/store.py:493` — `list_events` was taught to
      return in T009; write them under the same names or the reader T012 drives
      returns nothing. That asymmetry is load-bearing for US3's filter — see
      T028.
- [ ] T020 [US2] (FR-009, trap 6) Register the repository option on
      `ergane findings report` (`factory/cli/doctor.py:276-288`) and pass it into
      the `Finding` built at `factory/cli/doctor.py:487` —
      `findings_report_command`. Do **not** fall back to the resolver when the
      flag is absent.
- [ ] T021 [US2] (FR-010, traps 10 and 14) Thread `target_repo` from
      `factory/workgraph/detector.py:538` — `compare_and_report` into the call at
      `factory/workgraph/detector.py:598` — `compare_and_report`, onto the
      `Finding` returned at `factory/workgraph/detector.py:503-518` —
      `_build_finding`, **and** onto the inline `Finding` built by
      `factory/workgraph/detector.py:554` — `compare_and_report` at
      `factory/workgraph/detector.py:556-578` for the missing-snapshot branch,
      where `target_repo` is already in scope and unused. The refs at
      `factory/workgraph/detector.py:467` — `_build_finding` are unchanged and the
      key at `factory/workgraph/detector.py:58` does not move (073 FR-024). The
      two callers at `factory/workgraph/adapter.py:1177` — `run_attempt` and
      `factory/workgraph/adapter.py:1185` — `run_attempt` already pass the
      repository, so `factory/workgraph/adapter.py` needs no edit. Read what 130
      landed first: if the value already reaches `_build_finding`, what remains
      here is the field and the second site.
- [ ] T022 [US2] (FR-011, trap 9) Key the batch dedupe at
      `factory/workgraph/detector.py:621` — `_persist_finding` on key **and**
      repository, and carry the repository through
      `factory/doctor/models.py:81` — `parse_findings_batch` as a **per-entry**
      field, not an envelope field. The reason is decided, not open: the parser's
      one-provenance rule scopes `source`, the reporter — and this file is one
      *runtime root* (`factory/workgraph/detector.py:388` — `_snapshot_dir`),
      which is exactly the thing that serves many repositories, so an envelope
      field cannot hold the two entries US2-S4 requires. Four edits, and the
      second is the one the trio exists to name:
      (a) add the per-entry `repository` to the entry field list at
      `factory/doctor/models.py:145-163` — `parse_findings_batch`, or it is read
      from the JSON and dropped;
      (b) **re-qualify, do not delete**, the uniqueness rejection at
      `factory/doctor/models.py:138` — `parse_findings_batch` and
      `factory/doctor/models.py:139` — `parse_findings_batch` so its identity is
      the (key, repository) pair — the `ValueError` it raises at
      `factory/doctor/models.py:142` — `parse_findings_batch` reaches the operator
      through `factory/cli/doctor.py:456` — `findings_report_command` as
      `batch refused:`;
      (c) leave `tests/test_doctor_models.py:90` —
      `test_batch_duplicate_key_refuses_naming_key` and
      `tests/fixtures/doctor/batch-duplicate-key/findings.json` **unedited**: both
      fixture entries name no repository, so they remain an equal pair and the
      landed guard must keep passing as written (T017a);
      (d) add a *new* fixture for the case that must now parse — two entries, one
      key, two repositories — and use it in T015.
      Editing the landed test or its fixture to accommodate the change is the
      tell that (b) was done wrong.

### Verification for this story

- [ ] T023 [US2] Paste, as committed evidence, the `finding_events` rows for one
      key reported twice from two repositories — showing two distinct repositories
      and two distinct refs arrays — beside the `findings` row showing
      `occurrences = 2` and one key. Produce them through `report`, not by writing
      SQL against the tables.

## Phase 3: User Story 3 — Reading is per repository, and a repository's own first sighting is news

### Tests for this story (write FIRST, must fail)

- [ ] T024 [P] [US3] (spec US3-S1, FR-012, trap 7) Assert that
      `ergane findings list` with the repository filter set to the repository that
      reported **first** lists that observation, and that the unfiltered listing
      still lists the key exactly once. Set the fixture up so the row's own
      repository column names the *later* repository: a filter applied to the row
      returns nothing here, which is the point of the test.
- [ ] T025 [P] [US3] (spec US3-S2, FR-013, trap 7) Record one key twice under one
      repository and once under another, and assert — reading
      `ergane findings list --json`, the surface T029 must actually change — that
      the per-repository counts read 2 and 1 **while the row's own `occurrences`
      still reads 3**. Assert all three numbers in one test: the pair alone would
      pass a diff that split the row, which is what FR-001 forbids, and reading
      them from a store function alone would pass a diff that never reaches the
      operator's output.
- [ ] T026 [US3] (spec US3-S3, FR-014, FR-017, traps 2, 6 and 15) With a critical
      probe finding already recorded under one repository, drive
      `factory/cli/doctor.py:177` — `doctor_command` with the process's **working
      directory** inside a second repository, and nothing else telling it where it
      is, and assert it returns the user exit code. **Pin the store for both runs**
      — keep the session fixture's `ERGANE_ROOT`/`FACTORY_ROOT` pin at
      `tests/conftest.py:545`, or pass both runs the same explicit `--db` — and
      change only the cwd, and say in the test why: `factory/workgraph/worktree.py:93`
      is a relative `DEFAULT_RUNTIME_ROOT`, which
      `factory/cli/doctor.py:65` — `_store_path` falls through to, so the
      `tests/test_runtime_root_findings.py:65` — `_chdir_tmp` pattern of
      chdir-with-no-`ERGANE_ROOT` hands each repository its own empty ledger and
      this assertion then passes on a zero-line production diff. Passing the
      repository in as an argument or an option does not satisfy this scenario
      either: the operator types `ergane doctor` bare, and a flag leaves the defect
      running. Driving `factory/doctor/cli.py:214` — `_check_command` instead does
      not satisfy it: that module is not what the `ergane doctor` verb runs. Not
      `[P]`: it shares its fixture with T027.
- [ ] T027 [US3] (spec US3-S4, FR-015, trap 15) **The control.** With that key now
      already observed under the second repository, assert a further run with the
      working directory in that same repository returns zero. It must read back the
      store T026 wrote — the same pin, the same `--db`, no second runtime root — or
      it is asserting a first sighting and not a repeat. Only the T026/T027 pair
      can fail a diff that deleted the newness rule instead of qualifying it, and
      only a pinned store makes the pair fail today.

### Implementation for this story

- [ ] T028 [US3] (FR-012, trap 7) Register the repository filter on
      `ergane findings list` (`factory/cli/doctor.py:266-273`) and apply it in
      `factory/cli/doctor.py:368` — `findings_list_command`. Derive it from
      `finding_events`, **not** from the row's own repository column: the severity
      and status filters at `factory/cli/doctor.py:372-376` are the wrong pattern
      to copy, because they filter row attributes and the row is a
      latest-observation summary (T019). A row filter answers "which repository
      reported this most recently", which is not the question FR-012 asks.
- [ ] T029 [US3] (FR-013, trap 7) Add the grouped query over `finding_events` that
      yields per-repository counts beside
      `factory/doctor/store.py:454` — `list_findings`, and carry them onto each
      record of `ergane findings list --json` — that JSON is the surface US3-S2
      asserts against and T032 pastes. Assemble the record where it is emitted,
      at `factory/cli/doctor.py:379` — `findings_list_command`, which today is
      `print(json.dumps([asdict(f) for f in findings], indent=2))`: `asdict` over
      the frozen carrier, so a derived count cannot ride on the dataclass without
      becoming a second store column, which FR-001 forbids. Build the emitted
      mapping from the `Finding` plus the counts rather than widening `Finding`.
      Leave the `occurrences` column and the ordering at
      `factory/doctor/store.py:461-474` — `list_findings` untouched.
- [ ] T030 [US3] (FR-014, FR-015, FR-017, traps 2 and 6) Resolve the repository in
      `factory/cli/doctor.py:177` — `doctor_command` from the process's working
      directory through T018's resolver — add no option to
      `factory/cli/doctor.py:162` — `add_doctor_parser`, whose only option stays
      `--db` — thread it through `factory/cli/doctor.py:188` — `_run_all_probes`,
      and make newness per key **and** repository in
      `factory/cli/doctor.py:240` — `_report_if_new`. The exit arithmetic at
      `factory/cli/doctor.py:206-212` — `_run_all_probes` keeps its shape,
      including the `EXIT_TRANSPORT` and unexpected-error branches that precede
      it: only the definition of "new" gains a dimension.
- [ ] T031 [US3] (FR-006, FR-015, traps 2 and 11) Confirm by reading that
      `factory/doctor/cli.py` was not made the home of this change and that
      `factory/workgraph/worktree.py` was not edited at all. If the second copy of
      the handler was also updated, state in the diff which one the tests drive.

### Verification for this story

- [ ] T032 [US3] Paste, as committed evidence, four **bare** `ergane doctor`
      invocations and their exit codes in order, each run from inside the named
      repository with no repository argument — first repository (1), second
      repository (1), second repository again (0), first repository again (0) —
      beside the `ergane findings list --json` output showing one row with its
      unchanged `occurrences` total and its two per-repository counts. The
      transcript MUST show the pinned `ERGANE_ROOT` (or the `--db` both runs were
      given) beside the four exit codes, so the pasted evidence carries its own
      falsifier: under two runtime roots those same four codes reproduce on
      unmodified code and prove nothing (trap 15). Note in it as well that every
      probe answered, since `EXIT_TRANSPORT` (3) precedes the new-criticals
      branch.

## Verification

- [ ] T033 The full gate command passes green.
- [ ] T034 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end, including step 1's migration over a copy of a
      real 520-row store, step 2's un-migrated copy read through
      `ergane spec validate`, and step 5's four bare exit codes. Step 5 is the
      falsifiable test of this whole spec: it is the green check that was never
      green, run forwards.
