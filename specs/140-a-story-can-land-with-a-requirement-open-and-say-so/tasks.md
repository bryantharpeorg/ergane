# Tasks: a story can land with a requirement open and say so

Read `plan.md` before starting. Six of its traps are the ones that turn a green
story into a landed non-fix. Trap 7: `_RESULT_COLUMNS`
(`factory/verify/store.py:711`) is read positionally, so a column added in the
wrong place passes every fresh-database test and mangles every migrated store.
Trap 8: a marker the prompt never teaches is a mechanism that cannot fire, and
every test still passes. Trap 9: the question path detects its marker and then
*skips grading* — copying that control flow would turn a confession into a free
pass. Traps 10 and 13 are the two that decide *where* US3's refusals go, and both
name a cheaper-looking site that passes a resolver-free unit test while doing
nothing on the surfaces this spec exists to change: read them before writing a
line of Phase 3, because the tasks below deliberately forbid those two sites.
Trap 15 is the sixth: the report prints its paste-ready frontmatter entry **once
per epic**, never once per attempt, because two entries pasted into one block are
one YAML key written twice and the last one silently wins.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The attempt record can name a requirement the story left open

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-015) **The control.** Compose a
      result for an attempt that recorded no open requirement and assert the new
      field is empty and every other field, `verdict` included, equals what
      today's composition produces for the same inputs. Every attempt already in
      the store is this attempt.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001, trap 4) Compose the same gate results,
      output check and judge verdict twice — once naming an open requirement, once
      not — and assert the two results differ in that one field alone and share a
      `verdict`. Compare field by field rather than by equality of the whole
      object, so the assertion names which field moved.
- [ ] T003 [P] [US1] (spec US1-S5, FR-002) **The invariant control.** Assert the
      members of `OverallVerdict` are exactly two and name them. This test exists
      so that a later reader who wants a third verdict has to delete an assertion
      rather than add an enum member (`factory/verify/models.py:16-19`).
- [ ] T004 [US1] (spec US1-S3, FR-004) Write a result carrying two named open
      requirements to a real store file, read it back, and assert the same two
      names in the same order. Not `[P]`: it shares a store fixture with T005.
- [ ] T005 [US1] (spec US1-S4, FR-003, FR-004, trap 7) Open a store created before
      the column, assert the migration adds it, that the recorded schema version is
      the new one, that a pre-existing row reads back as empty, and — the half that
      catches the real defect — that the migrated store's column list equals a
      freshly created store's **in order**, not merely in membership.

### Implementation for this story

- [ ] T006 [US1] (FR-001, trap 4) Add the field to
      `factory/verify/models.py:860` — `VerificationResult`, last, defaulting to
      an empty tuple, modelled on `gate_contradictions`; document in the class
      docstring that empty means "the attempt named none", never "not checked".
- [ ] T007 [US1] (FR-001, FR-002) Thread it through
      `factory/verify/models.py:998` — `compose_result` as a keyword argument with
      an empty default, carried onto the row and consulted nowhere in the verdict
      derivation. Say so in the docstring, in the voice of the four paragraphs
      already there explaining why such a fact is passed in rather than derived.
- [ ] T008 [US1] (FR-003, trap 7) Add the column **last** in the DDL, after
      `route` and before the `UNIQUE` clause, in both copies of the same table:
      the contract at
      `specs/002-verification-gating/contracts/verification-store.sql:65-67`, and
      the module-level DDL string in `factory/verify/store.py`, whose
      `CREATE TABLE` opens at `factory/verify/store.py:208` and whose `route`
      column sits at `factory/verify/store.py:259`, immediately above the
      `UNIQUE` clause at `factory/verify/store.py:260`. This edit is the fresh
      schema only — the migration of an existing store is T010's, inside
      `factory/verify/store.py:556` — `_migrate` — and the two must agree on
      order. Edit only the `.sql` contract in that spec directory — never that
      spec's `spec.md`, `plan.md` or `tasks.md`. Precedent: 126-US3 (`94c8cd8`).
- [ ] T009 [US1] (FR-003, trap 7) Bump `SCHEMA_VERSION`
      (`factory/verify/store.py:175`) to 14 and write its comment paragraph in the
      same voice as the thirteen above it, stating that the column is additive and
      that NULL reads back as empty rather than being backfilled.
- [ ] T010 [US1] (FR-003, FR-004, trap 7) Add the `ALTER TABLE` branch in
      `factory/verify/store.py:556` — `_migrate` **after** the persona loop at
      `factory/verify/store.py:650`, never beside `gate_contradictions` where the
      block reads more naturally. Add the column name to the end of
      `_RESULT_COLUMNS` (`factory/verify/store.py:711`) and read it back in
      `factory/verify/store.py:1031` — `_result_from_row`, defaulting NULL to the
      empty tuple.

### Verification for this story

- [ ] T011 [US1] Paste, as committed evidence, the `PRAGMA table_info` output for
      a store migrated from the previous schema and for a freshly created one,
      side by side, showing identical column order.

## Phase 2: User Story 2 — A node can say which requirement it left open, and the record receives it

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-006) Given an archived final message whose
      last line-anchored `## OPEN REQUIREMENT` heading names `FR-007`, assert the
      detector returns `FR-007` and nothing else.
- [ ] T013 [P] [US2] (spec US2-S2, FR-006) Assert the heading quoted inside prose,
      inside a fenced block, and at a different heading level each yield no
      requirement. Reuse the fence-masking and heading grammar
      `factory/verify/question.py:152` — `_last_marker` already applies; do not
      write a second scanner.
- [ ] T014 [P] [US2] (spec US2-S3, FR-007) Assert a marker whose body matches no
      requirement key records nothing and the attempt grades as one with no marker
      at all — the same line `factory/verify/question.py:85` —
      `detect_operator_question` draws for an empty body.
- [ ] T015 [US2] (spec US2-S4, FR-008, trap 9) **The control that matters most.**
      Verify two attempts with identical gate results, output check and judge
      verdict, one whose transcript carries the marker and one whose does not, and
      assert both compose the same `verdict` **and** the same termination, with
      only the recorded field differing. Not `[P]`: it drives the verification path
      over one shared fixture.
- [ ] T016 [P] [US2] (spec US2-S5, FR-005, trap 8) Assert the assembled implementer
      prompt contains the heading the detector matches, reading the detector's own
      constant rather than a second copy of the string. Without this test a story
      that ships a detector and no prompt section is green and inert.
- [ ] T017 [P] [US2] (spec US2-S6, FR-009, trap 15) Assert the attempt report
      text for one epic whose attempts are: one declaring `FR-003`, one declaring
      `FR-007`, and one declaring none, names each declaring attempt's requirement
      under its own line, adds no line under the third, and carries **exactly one**
      paste-ready `open_requirements:` frontmatter entry naming both requirements —
      count the occurrences of the key in the rendered text and assert it is one,
      because one entry per attempt is the build this assertion exists to fail.
      Assert too that an epic whose attempts declare none renders neither the lines
      nor the entry.
- [ ] T018 [US2] (spec US2-S7, FR-009, trap 14) **The line the operator is told to
      paste must be a line the grammar accepts.** Take the single aggregated
      paste-ready entry the report builder produced in T017 — that value, not a
      hand-typed copy of it —
      write it into a scratch corpus as the frontmatter of a `state: landed` spec,
      read that corpus through `factory/roadmap/models.py:411` — `read_roadmap`,
      and assert the read succeeds and the entry carries the requirement. Not
      `[P]`: it consumes T017's builder output. This test is what earns the merge
      edge this story declares on the frontmatter-grammar story — before that
      grammar lands, this same line makes `read_roadmap` refuse the whole corpus
      (trap 14).

### Implementation for this story

- [ ] T019 [US2] (FR-006, FR-007) Add the detector beside
      `factory/verify/question.py:85` — `detect_operator_question`, reusing
      `factory/verify/question.py:119` — `_read_stdout` and
      `factory/verify/question.py:152` — `_last_marker`, and define its heading
      constant beside `QUESTION_HEADING` (`factory/verify/question.py:51`). Return
      the requirement keys the body names; a body naming none returns nothing, the
      same as no marker.
- [ ] T020 [US2] (FR-005, trap 8) Add the prompt section beside
      `_OPERATOR_QUESTION` (`factory/workgraph/prompt.py:258`), formatting the
      detector's constant into it rather than repeating the string, and append it
      to the unconditional assembly list at
      `factory/workgraph/prompt.py:571-572`. Say plainly in the section that the
      marker records a requirement left open, that it changes no verdict, and that
      it is not a way to skip work.
- [ ] T021 [US2] (FR-006) Add the activity modelled on
      `factory/activities/verify_activities.py:371` —
      `detect_operator_question_activity`, including its raise-rather-than-return
      treatment of an unreadable archive, and register it in `factory/worker.py:142`
      beside the existing one. An activity nothing registers is not callable, which
      is why `factory/worker.py` is one of this story's production files rather
      than an afterthought.
- [ ] T022 [US2] (FR-008, trap 9) Call the detector where the question detector is
      called, `factory/workgraph/workflow.py:1940-1946`, and **change no branch**:
      no new termination, no salvage, no park. Carry the keys to
      `factory/workgraph/workflow.py:2559` — `_verify` as a keyword-only argument
      with an empty default — the other two call sites,
      `factory/workgraph/workflow.py:2871` and `factory/workgraph/workflow.py:4005`,
      stay byte-identical — and pass them at
      `factory/workgraph/workflow.py:2653` beside `base_ref` and `dispatch`.
- [ ] T023 [US2] (FR-009, trap 15) Add the line-builder beside
      `factory/cli/nouns/build.py:1398` — `_contradiction_lines` and call it from
      `factory/cli/nouns/build.py:1352` — `render_attempts`. Print nothing for an
      attempt that recorded none, following that function's stated rule that
      silence is the record's own answer. The paste-ready entry is **not** one of
      those per-attempt lines: build it once from every result the renderer was
      handed, deduplicated and deterministically ordered, and print it once for the
      epic. Two entries in one frontmatter block are one key written twice, and
      `factory/roadmap/models.py:260` — `_parse_frontmatter` keeps the last with no
      error (trap 15). Build it as one value a test can read, so T018 can feed
      exactly what an operator would copy. The
      "print the exact line to paste" precedent is named in `plan.md` § "What
      already exists, and where" — read it there rather than citing that file here;
      US2 opens no file US3 also opens.

### Verification for this story

- [ ] T024 [US2] Paste, as committed evidence, the attempt-report text for one
      epic containing both an attempt that declared an open requirement and one
      that did not, showing the extra two lines under the first and nothing under
      the second, with the two attempts' verdicts identical.

## Phase 3: User Story 3 — A spec with an open requirement is not complete

### Tests for this story (write FIRST, must fail)

- [ ] T025 [P] [US3] (spec US3-S1, FR-010) Assert a spec declaring
      `open_requirements: [FR-007]` beside `state: landed` parses and that the
      entry carries the list.
- [ ] T026 [P] [US3] (spec US3-S2, FR-010) Assert a scalar value is refused with a
      message naming the key and the required shape, on the same path `fixes:` is
      refused at `factory/roadmap/models.py:296` — `_shape_entry`. A scalar read as
      a list is a list of characters, and this repository has already paid for that
      once.
- [ ] T027 [P] [US3] (spec US3-S3, FR-015) **The control.** Assert a corpus in
      which no spec declares the key parses and computes readiness identically to
      today. Every spec now in `specs/` is that spec.
- [ ] T028 [US3] (spec US3-S4, FR-011, FR-012, traps 10 and 12) Assert that spec B,
      whose `depends_on_landed` names an attested-landed spec A that declares one
      open requirement, lists A among its blockers when readiness is computed with
      no injected resolver; that A's rendered state is not `landed`; that the same
      corpus with A's key removed makes B dispatchable; and that when A is *also*
      drifted the incomplete rendering wins over `amended`. Not `[P]`: one corpus
      fixture, four readings. This test alone does **not** prove the refusal is in
      the right place — T029 is what does that.
- [ ] T029 [US3] (spec US3-S7, FR-011, trap 10) **The leg that catches the inert
      build.** Compute readiness over T028's corpus again, this time injecting a
      `landed_for` resolver that reports A observed-landed — the shape
      `factory/roadmap/workflow.py:1331` — `_observed_resolver` and
      `factory/cli/status.py:441` — `_observed_landed_resolver` supply on the two
      live paths — and assert B *still* names A among its blockers. A refusal
      written inside `factory/roadmap/models.py:504` — `_attested_resolver` passes
      T028 and fails here, which is exactly the failure mode: the observed resolver
      is asked first at `factory/roadmap/models.py:598-605`, and a spec that just
      landed with a requirement open is precisely the spec it answers landed for.
      Not `[P]`: it shares T028's corpus fixture.
- [ ] T030 [P] [US3] (spec US3-S5, FR-013, FR-015, trap 1) Assert
      `ergane spec landed` names the open requirement in its human output, carries
      it under its own field in the `--json` document, and that the document's
      `no_open_requirements` field is `False`; and that the same spec without the
      key yields that field `True` with `default_branch`, `facts` and `unlanded`
      exactly as today's document has them — the one additive field FR-015 declares
      as its only exception, and nothing else moved. The flag is named for what it
      measures, never `complete`: this document reports landings, and a boolean
      called complete would read true for a spec with no landed story at all
      (trap 1). Assert in the same test that the story list is unchanged — the
      `RequirementKind.STORY` filter at `factory/workgraph/cli.py:199-203` stays
      exactly as it is.
- [ ] T031 [P] [US3] (spec US3-S6, FR-014, trap 13) Assert a finding whose only
      declaring spec declares an open requirement is not classified fixed even when
      its `last_seen` predates that spec's landing commit; that its reason names
      the declaring spec and the open requirement; and — the two assertions that
      refuse the cheaper wrong build — that its class is **not** `CANDIDATE` on
      `factory/doctor/triage.py:115` — `TriageClass`, and that its reason does not
      contain the string "no 'fixes:' declares it". Dropping the spec from the
      declared index satisfies "not fixed" and fails all three of the others,
      because the row falls into the prose scan at
      `factory/doctor/triage.py:528-546` (trap 13). Assert last the leg that keeps
      today's rule intact: the same finding, declared *also* by a second landed
      spec that declares no open requirement, still classifies `FIXED` on that
      second spec's proof and names it in the reason. A build that sends any
      finding with one incomplete declarer to a human regresses triage for the
      complete spec, which FR-015 forbids.

### Implementation for this story

- [ ] T032 [US3] (FR-010, trap 3) Add the key to `_KNOWN_KEYS`
      (`factory/roadmap/models.py:117`) and its type-check to
      `factory/roadmap/models.py:296` — `_shape_entry`, copying the `fixes` block
      immediately below `depends_on_landed` including its comment. Add the field to
      `factory/roadmap/models.py:126` — `SpecEntry` with a `default_factory`, for
      the reason stated on `fixes` there. Do **not** add a fifth `SpecState` value.
- [ ] T033 [US3] (FR-010, trap 11) Expose one function in
      `factory/roadmap/models.py` that reads the key out of a frontmatter block,
      beside `factory/roadmap/models.py:240` — `_split_frontmatter`, and let the
      other two readers import it the way `factory/doctor/triage.py:80` already
      imports that one. No second parse of this key anywhere. The roadmap's own
      shape check stays the one place the *shape* is refused; this function is the
      one place the *value* is read.
- [ ] T034 [US3] (FR-011, trap 10) Put the refusal in
      `factory/roadmap/models.py:570` — `compute_readiness`'s dependency loop,
      **before** `observed(dependency)` is called at
      `factory/roadmap/models.py:598-605`: a dependency whose `SpecEntry` declares
      an open requirement is a blocker whatever either resolver would have said.
      Do **not** write it in `factory/roadmap/models.py:504` — `_attested_resolver`
      and do not reach it through the `attested` fall-through: the loop asks the
      injected observed resolver first, both live callers inject one
      (`factory/roadmap/workflow.py:689` and `factory/roadmap/workflow.py:853` for
      the roadmap, `factory/cli/status.py:292` for the status board), so an
      attested-only refusal is skipped for exactly the specs the roadmap just
      landed — inert in the dispatch loop and on the status board while a
      resolver-free unit test passes green (trap 10). T029 is the test that catches
      that build; run it before and after.
- [ ] T035 [US3] (FR-012, trap 12) Add a field beside `drifted`
      (`factory/roadmap/models.py:541`) on `factory/roadmap/models.py:516` —
      `SpecReadiness`, and populate it from the entry in the construction at
      `factory/roadmap/models.py:609-618`; only then add the rendered value beside
      `RENDERED_AMENDED` (`factory/roadmap/models.py:91`) and its branch in
      `factory/roadmap/models.py:544` — `rendered_state`. The field is a
      precondition, not a nicety: `rendered_state` reads `self.drifted` and
      `self.state` and can see no `SpecEntry` at all, so the branch cannot be
      written without it. Guard the new branch the way `amended` is guarded at
      `factory/roadmap/models.py:546` — it replaces `landed` and applies only when
      `self.state is SpecState.LANDED`; written ungated it would change the
      rendered state of every draft or ready spec that declares the key, on the
      status board, and no test in this phase would fail. The declared requirement
      takes precedence over `amended` when both apply, asserted by T028's fourth
      reading rather than left to the order of an `if` chain (trap 12).
- [ ] T036 [US3] (FR-013, trap 1) In `factory/workgraph/cli.py:168` —
      `landed_command`, read the open requirements through T033's function, name
      them in the human output, and add them plus one boolean,
      `no_open_requirements`, to the `--json` document built at
      `factory/workgraph/cli.py:205-222`. Emit the boolean unconditionally — a
      field that appears only sometimes is a second shape of the same document —
      and add no other key: `default_branch`, `facts` and `unlanded` keep their
      shapes and contents, which is the whole of FR-015's one declared exception.
      Leave the story filter at
      `factory/workgraph/cli.py:199-203` and `factory/workgraph/landed.py:395` —
      `_story_keys` untouched: enumerating every FR there would print a rescue PR
      title for a requirement that is not a node.
- [ ] T037 [US3] (FR-014, trap 13) Carry the open requirements onto
      `factory/doctor/triage.py:140` — `SpecRecord` through
      `factory/doctor/triage.py:281` — `_declaration` and
      `factory/doctor/triage.py:233` — `read_spec_records`, reading them with
      T033's function. **Keep the spec in** `factory/doctor/triage.py:583` —
      `_declared_index`, and add the fourth outcome inside
      `factory/doctor/triage.py:613` — `_class_declared`, handing the requirements
      in the way `landing_date_for` already is. Discount the incomplete declarer,
      not the finding: drop that spec from the list the branch reasons over and let
      the remaining declarers classify it exactly as they do today, keeping the
      rule that function's own docstring states — a finding several specs declare
      is fixed when *any* of them proves it. Only when the list empties does the
      row go to `NEEDS_HUMAN`, which is annotated and never closed
      (`factory/doctor/triage.py:772`), with a reason naming the declaring spec and
      its open requirement. Dropping the spec from the index instead sends the row
      past the declared classes into the prose scan at
      `factory/doctor/triage.py:528-546`, which stamps it `CANDIDATE` with a reason
      that is false in every clause, names no requirement, and sits in a class
      `--apply` may never touch — and `_declared_index` returns
      `dict[str, list[str]]`, so it could carry no reason even if it were the right
      site (trap 13).

### Verification for this story

- [ ] T038 [US3] Paste, as committed evidence, the roadmap render, the
      `ergane spec landed --json` document and the `ergane findings triage` row for
      one scratch corpus, first with the key declared and then with the line
      deleted, showing all three surfaces changing together and returning to
      today's answer. Six short documents, not a transcript: trim each to the lines
      that move.

## Verification

- [ ] T039 The full gate command passes green.
- [ ] T040 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 1 is trap 7 run forwards and needs a store
      that predates the migration; step 2 begins with a worker restart on an empty
      floor, for the two open critical findings named there — one blocks every new
      epic until the restart, the other detonates every in-flight one because of
      it; steps 4 and 5 are the falsifiable test of the
      whole spec, because they are the three surfaces that called a half-finished
      spec complete, run forwards and then back — and step 5 is trap 10 run
      forwards, on the resolver the roadmap actually dispatches with.
