# Tasks: a spec answers to its number

**Spec**: `specs/076-a-spec-answers-to-its-number/spec.md`
**Plan**: `specs/076-a-spec-answers-to-its-number/plan.md`

Read `plan.md` before the first task. Trap 1 comes first and is not optional:
this spec declares `depends_on_landed: [133-…]`, and 133 moves ten validation
layer bodies out of `factory/cli/nouns/spec.py`, so every line number in the
plan is stale by the time you read it — re-read each anchor by symbol before you
edit the line it names. Trap 2 is the one that decides US1: a number is an
integer, never a prefix, and the draft of this spec taught the opposite. Trap 6
is the one that quietly breaks a landed fix — resolution must not rebind
`args.specs_root` — and it is only visible in the demo-container shape, which is
why T009 extends an existing suite rather than writing a fresh pair. Trap 10 is
US2's most expensive: `show` is a reporting caller, so its landed read passes
`fetch=False`, and a `tmp_path` fixture cannot tell you whether you obeyed that.
Trap 8 is the one that reads like a licence to delete landed code:
`factory/cli/nouns/build.py` **already** imports `factory/cli/nouns/spec.py`,
deferred inside `ship_command`, three lines above the line T013 edits — that
import stays. Trap 13 is US3's: the corpus pass holds no landing data at all.
Trap 18 governs every evidence task — two of the four verbs write and one of
them dispatches.

Tests are written first and must fail before the implementation that satisfies
them — except the tasks marked **The control**, which assert non-regression and
are green from the first commit; do not manufacture a failure for those. Every
acceptance scenario is provable from the diff, which is all the judge sees;
runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — Every spec verb takes a number

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 15, trap 17) In
      `tests/test_spec_number_resolution.py`, build a fixture corpus under
      `tmp_path` holding `075-a-stronger-rung-runs-a-stronger-model` with a
      trio, and assert each of the four spec-taking verbs given `075` operates
      on that directory. Copy the `build ship` harness shape from
      `tests/test_ergane_build_ship.py` rather than inventing a third. Never
      read this repository's own `specs/`, which has 141 directories at
      `602a92c` and changes under the test.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert `75` resolves to the same
      directory as `075`, so a leading zero is optional.
- [ ] T003 [P] [US1] (spec US1-S3, FR-005, trap 4) **The control.** Assert the
      full-path form behaves exactly as today, including an absolute path whose
      parent is not the specs root, and that no resolution is attempted for it
      (assert the resolver is not called, or that a corpus with no matching
      number still succeeds on the path).
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, trap 3) Build a corpus holding both
      `070-alpha` and `70-beta` — by hand, because `_pick_spec_number`
      (`factory/cli/nouns/spec.py:302` — `_pick_spec_number`) refuses to mint
      into it — and assert `70` is refused naming both candidates and choosing
      neither.
- [ ] T005 [P] [US1] (spec US1-S5, FR-002, FR-004, trap 2) **The no-prefix
      differential.** Build a corpus holding `070-…` and `071-…` and nothing
      numbered 7, and assert `07` is refused with a message that names **both**
      the value `07` and the specs root it searched, and that mentions neither
      `070-…` nor `071-…`. Both halves are load-bearing: today's do-nothing
      failure already prints `cannot read 07/spec.md` and already names neither
      neighbour, so a test asserting only the absences is green before you write
      a line of production code. A prefix matcher passes every other test in
      this phase and fails this one.
- [ ] T006 [P] [US1] (spec US1-S6, FR-004) Assert an unmatched number is refused
      naming the value and the specs root searched.
- [ ] T007 [P] [US1] (spec US1-S7, FR-006, trap 5) Assert a number resolves
      against a non-default `--specs-root` for `spec validate`, `spec derive`
      and `build ship`; and assert `ergane spec landed 075`, whose parser
      registers no such flag (`factory/cli/nouns/spec.py:219` —
      `_add_spec_parser`), resolves against the default root instead of raising
      `AttributeError`.
- [ ] T008 [P] [US1] (spec US1-S8, FR-013, trap 7, trap 17) Assert the epic id
      computed after resolving `075` is
      `075-a-stronger-rung-runs-a-stronger-model` and not `075`, at
      `spec derive` (`factory/workgraph/cli.py:314` — `derive_command`) and at
      `build ship` (`factory/cli/nouns/build.py:1035` — `ship_command`). This
      committed test is how `build ship`'s resolution is proven; it is kept out
      of the pasted evidence because `ship` dispatches (trap 18).
- [ ] T009 [P] [US1] (spec US1-S9, FR-014, trap 6, trap 17) **The control** —
      green from the first commit, like T003; do not manufacture a failure for
      it. It goes red only against an implementation that writes the joined root
      back onto `args.specs_root`, and **it only fires in the demo-container
      shape.** Extend
      `tests/test_derive_specs_root_default.py`, which already builds the
      fixture: a repo under `tmp_path/repo` whose specs live at
      `tmp_path/repo/specs`, a decoy `specs/` under `tmp_path/image-root`, and
      `monkeypatch.chdir` to the decoy. Derive the **absolute** spec directory
      with no `--specs-root` and assert two things: the compiled graph's
      `specs_root` is `str(repo / "specs")` and not the decoy, and the parsed
      `--specs-root` value is still the literal `DEFAULT_SPECS_ROOT` string
      after resolution has run. Do **not** write the differential as "derive the
      same spec by number and by path under the default root and compare the two
      graphs": there the rebound root and the spec's own parent are the same
      absolute path, so a conforming and a non-conforming implementation both
      pass. An implementation that writes the joined root back onto
      `args.specs_root` flips the comparison at
      `factory/workgraph/cli.py:332` — `derive_command` and fails both
      assertions here.

### Implementation for this story

- [ ] T010 [US1] (FR-002, FR-013, trap 2, trap 7, trap 8) Write one resolver in
      `factory/workgraph/cli.py`, beside
      `factory/workgraph/cli.py:282` — `_resolve_identity_path`, under a public
      name both noun modules can import. It matches the leading numeric segment
      of each direct child of the specs root with the same `^(\d+)-` rule the
      writer half uses
      (assigned at `factory/cli/nouns/spec.py:299`, under its doc comment at
      `factory/cli/nouns/spec.py:298`), compares by **integer value** so
      leading zeros are optional and no prefix matches, and returns the real
      directory path so `epic_id = spec_dir.resolve().name` still yields the
      full slug. Import the existing `SPEC_NAME`
      (`factory/workgraph/cli.py:61`, or `factory/roadmap/models.py:57`); do not
      add a third.
- [ ] T011 [US1] (FR-005, trap 4) Try the path form first — the value is used
      as-is when it already names a directory — and fall back to number
      resolution only then, so no existing caller changes behaviour and an
      absolute path outside the specs root still works.
- [ ] T012 [US1] (FR-003, FR-004, trap 3) Refuse a value matching more than one
      directory by naming every candidate, following the message shape at
      `factory/cli/nouns/spec.py:302` — `_pick_spec_number`; refuse a miss by
      naming the value **and** the root searched, which is the assertion T005
      turns on.
- [ ] T013 [US1] (FR-006, FR-014, trap 5, trap 6) Apply the resolver at the five
      handler sites — `factory/cli/nouns/spec.py:491` — `_validate_command`,
      `factory/cli/nouns/spec.py:256` — `_derive_command`,
      `factory/workgraph/cli.py:175` — `landed_command`,
      `factory/workgraph/cli.py:307` — `derive_command` and
      `factory/cli/nouns/build.py:1034` — `ship_command`. In `ship_command`,
      leave the deferred
      `from factory.cli.nouns.spec import derive_spec_command,
      validate_spec_command` at `factory/cli/nouns/build.py:1031` exactly where
      it is — it is landed (106-US4), it sits three lines above the line you are
      editing, and hoisting or deleting it breaks `ergane build ship` (trap 8).
      Read the specs root
      with `getattr(args, "specs_root", DEFAULT_SPECS_ROOT)` because `landed`
      registers no such flag, and resolve into a local: do **not** assign back
      to `args.specs_root`, which
      `factory/workgraph/cli.py:332` — `derive_command` compares against the
      default string.
- [ ] T014 [US1] (FR-001) Update the four `spec_dir` help strings to say a
      directory **or a spec number** —
      `factory/cli/nouns/spec.py:137` — `_add_spec_parser`,
      `factory/cli/nouns/spec.py:159` — `_add_spec_parser`,
      `factory/cli/nouns/spec.py:219` — `_add_spec_parser` and
      `factory/cli/nouns/build.py:2111` — `add_parser`.

### Verification for this story

- [ ] T015 [US1] (trap 18) Paste, as committed evidence, the **diff** of the two
      read-shaped verbs run once with `076` and once with
      `specs/076-a-spec-answers-to-its-number` — `ergane spec validate
      --target-repo .` and `ergane spec landed --default-branch
      ergane-buildout`, two `diff` invocations, each of which must be empty —
      plus two runs against this repository's corpus, into
      `specs/076-a-spec-answers-to-its-number/evidence/us1-agreement.md`: the
      refusal text from `ergane spec validate 999 --target-repo .`, which must
      name `999` **and** the specs root searched — today that command prints
      `cannot read 999/spec.md` and names no root, and the root is the half that
      proves production code ran — and the single summary line from
      `ergane spec validate 07 --target-repo .` naming
      `specs/007-parallel-dispatch/spec.md`, not that report's body. Do **not**
      demand a refusal for `07` here: `specs/007-parallel-dispatch` exists at
      `602a92c`, so under FR-002 `07` is the number seven and resolving it is
      the correct answer — a refusal would contradict FR-002 and US1-S2, and
      making `07` refuse to satisfy an evidence line is how prefix reasoning
      gets back in. The no-prefix refusal is proven on T005's fixture corpus,
      never on this repository's. Do
      **not** run `ergane spec derive` or `ergane build ship` for this evidence:
      derive writes `<spec-dir>/workgraph.json`, which is a tracked artifact this
      spec directory does not have at `602a92c` and which `build start` reads off
      disk (open finding `cli/spec-derive-json-rewrites-the-committed-artifact`),
      and `ship` derives and then dispatches. Their resolution is proven by T008.
      `specs/076-a-spec-answers-to-its-number/workgraph.json` MUST NOT exist in
      this story's diff. Paste the diffs and the two short excerpts, never the
      full outputs: `spec validate`'s report alone is tens of lines and this
      story's diff shares one 65,536-byte allowance with its tests (plan.md,
      Sizing).

## Phase 2: User Story 2 — One spec's whole picture, in one command

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US2] (spec US2-S1, FR-007) In `tests/test_spec_show.py`, build a
      fixture corpus whose state, story count, landed count and task count are
      four known and mutually distinct values, and assert `show` reports all
      four. Distinct values are the point: three equal counts cannot tell a
      correct report from a report that prints one number three times.
- [ ] T017 [P] [US2] (spec US2-S2, FR-008, trap 10) Over a fixture repository
      whose manifest declares a landing branch that is not `main` and whose two
      branches hold different landings, assert the landed count `show` reports
      is the one read against the declared branch — a `main` default returns the
      other number and fails — **and** assert the read did not fetch: spy on
      `factory/workgraph/landed.py:130` — `landed_facts` and assert it was
      called with `fetch=False`, or assert no `git fetch` was invoked. The
      second assertion cannot be skipped: a `tmp_path` repo has no `origin`, so
      `factory/workgraph/landed.py:273` — `_resolve_default_head` never fetches
      there and the first assertion passes either way.
- [ ] T018 [P] [US2] (spec US2-S3, FR-007) Assert a blocked spec's blockers are
      named, and that they equal the values
      `factory/roadmap/models.py:570` — `compute_readiness` gives `spec list`
      for the same spec.
- [ ] T019 [P] [US2] (spec US2-S4, FR-009, trap 9) **The control that must be
      able to fail.** Drive `show` with no reachable control plane and assert
      every disk fact is present and the epic state reads unknown. Assert the
      guard is the declared one — `factory/cli/status.py:147`'s transport tuple,
      `factory/cli/status.py:154`'s query-refusal tuple, or the `OperatorError`
      the client opener raises — and prove the test can fail by making the
      connection unconditional in a scratch edit before writing the fix.
- [ ] T020 [P] [US2] (spec US2-S5, FR-015) Assert a dispatched epic's state is
      reported when a control plane is reachable, against a fake client: the
      state reported is the one the fake returned, the query asked for is
      `epic_status`, and the handle id is `epic-<directory name>` — the value
      `factory/workgraph/cli.py:160` — `workflow_id` produces from the resolved
      directory.
- [ ] T021 [P] [US2] (spec US2-S6, FR-010) Assert `--json` carries six facts
      under stable keys — state, story count, landed count, task count,
      blockers, and the epic state — and that the human render is produced from
      that same object, field by field. Run the assertion on both paths: with a
      reachable fake client, and with none, where the epic-state field must be
      present and read `unknown` rather than be missing.
- [ ] T021a [P] [US2] (spec US2-S7, FR-007, FR-010, trap 2) Assert `show` takes
      a **number**: run it over the US2-S1 fixture corpus once with the spec's
      number and once with that spec's directory path, and assert the two
      `--json` documents are equal. Without this, every other US2 assertion is
      satisfied by a `show` that accepts only a path — the argument form is the
      premise of the story and no other scenario names it.

### Implementation for this story

- [ ] T022 [US2] (FR-007, FR-008, trap 10) Register the `show` verb in
      `factory/cli/nouns/spec.py:113` — `_add_spec_parser`, taking a number or a
      path through US1's resolver, plus `--json` **and `--default-branch` with
      `default=None`**. That flag is not optional decoration: T023 copies
      `landed_command`'s branch order, whose first arm is `args.default_branch`,
      so a parser without it makes every `ergane spec show` run an
      `AttributeError` — trap 5's shape, reappearing in code this story writes.
      The `None` default is what lets the manifest declaration still win.
- [ ] T023 [US2] (FR-008, FR-011, trap 10) Read landed facts through **one
      named, per-spec-cached reader you define here** — the one-spec analogue of
      `factory/cli/status.py:441` — `_observed_landed_resolver`, taking a spec
      directory and returning its landed facts — not an inline call in `show`'s
      body. FR-011 makes US3 import this same object and forbids a second landed
      implementation, so if `show` calls the scanner inline there is nothing for
      T033 to reuse and US3 ships the duplicate FR-011 refuses. Inside it, call
      `factory/workgraph/landed.py:130` — `landed_facts` directly with
      `fetch=False`, the way `factory/cli/status.py:483` — `_observed_landing`
      does, and resolve the branch in `landed_command`'s declared order — the
      explicit flag, then `factory/workgraph/worktree.py:1471` —
      `landing_branch`, then `main` (`factory/workgraph/cli.py:186` —
      `landed_command`). Do **not** route the read through
      `factory/workgraph/cli.py:168` — `landed_command`: it is a printing
      command and it keeps the fetching default, so `show` would write a
      remote-tracking ref on every run and die on an offline box. Take the
      repository from `factory/cli/status.py:425` — `_repo_holding`, whose
      docstring says it tests `.git` for existence on purpose because in a git
      worktree `.git` is a file — not
      `factory/workgraph/cli.py:474` — `_target_repo_for_spec`, which requires a
      directory and otherwise falls back to `spec_dir.parent.parent.parent`.
      Every node runs in a worktree. Say on the output that the answer was read
      without fetching.
- [ ] T024 [US2] (FR-009, trap 9) Read the corpus from disk first, then reach
      for the control plane and catch the declared failures, reporting the epic
      state as unknown — the shape at `factory/cli/status.py:284` —
      `collect_floor`. No blanket `except Exception`.
- [ ] T025 [US2] (FR-015, trap 8) Read the one epic's state by composing it in
      place: `client.get_workflow_handle(workflow_id(epic_id))` with
      `factory/workgraph/cli.py:160` — `workflow_id`, then
      `await handle.query("epic_status")`, driven through `asyncio.run` the way
      `factory/cli/nouns/build.py:1005` — `status_command` drives
      `factory/cli/nouns/build.py:1119` — `_query_status`. Do not import
      `_query_status` itself: it prints and returns an exit code rather than
      returning data, so it hands `show` a printed line and a status code where
      `show` needs an epic state. That is the whole reason, and it is
      sufficient — importing across the two noun modules is **not** forbidden
      (`factory/cli/nouns/build.py:1031` already does it; see trap 8).
- [ ] T026 [US2] (FR-010) Build one document object carrying all six facts,
      serialise it for `--json`, and render the human view from the same object.

### Verification for this story

- [ ] T027 [US2] (trap 18) Paste, as committed evidence, `ergane spec show 076`
      beside `ergane spec landed specs/076-a-spec-answers-to-its-number
      --default-branch ergane-buildout`, and the same `show` run with the
      control plane unreachable, into
      `specs/076-a-spec-answers-to-its-number/evidence/us2-show.md`. Both verbs
      here only read; do not add `derive` or `ship` to this file.

## Phase 3: User Story 3 — The corpus view answers "what should I look at"

### Tests for this story (write FIRST, must fail)

- [ ] T028 [P] [US3] (spec US3-S1, FR-011, trap 13) In
      `tests/test_spec_list_filters.py`, over a fixture repository whose
      manifest declares a landing branch that is not `main`, holding one spec
      with landed stories and one with none, assert each row carries a
      landed-versus-total count, that the two rows differ, and that both counts
      are the ones read against the **declared branch** — build the two branches
      with different landings so a `main` default returns different numbers and
      fails. Assert the branch actually used, not the number of calls: a
      call-count assertion on `factory/roadmap/models.py:411` — `read_roadmap`
      is satisfied by any implementation, including one that then shells git
      once per row against `main`. Separately assert the frontmatter corpus is
      walked once, so the state column and the count column cannot come from two
      reads that disagree.
- [ ] T029 [P] [US3] (spec US3-S2, FR-012) Over a fixture corpus holding at
      least one `ready` spec and at least one `draft` spec, assert `--state
      ready` lists the ready spec's directory name, omits the draft spec's, and
      produces a spec-row count equal to the number of ready specs. All three,
      and the positive two are the load-bearing half: a filter that always emits
      no spec row satisfies the absence and satisfies US3-S3 and US3-S5 too, so
      the whole flag could ship as "always empty" and pass this story; and
      against a do-nothing production diff argparse refuses `--state` with
      `SystemExit(2)` and an empty stdout, so a test written to the absence alone
      is red for the wrong reason and green the moment the flag merely parses.
      This is the fix T005 already carries for US1-S5.
- [ ] T030 [P] [US3] (spec US3-S3, FR-012, trap 11) **The control.** Assert a
      filter matching nothing produces no spec row and one line saying the
      filter matched nothing — never the unfiltered list.
- [ ] T031 [P] [US3] (spec US3-S4, FR-011, trap 12) **The row invariant.** Over
      a fixture corpus holding one blocked spec, assert three things about the
      unflagged render: the line count equals the spec count, every row carries
      the new count column, and the blocked spec still names every one of its
      blockers on that same line. Do **not** assert the output equals a golden
      capture of today's render: FR-011 changes the unflagged output on purpose,
      so "unchanged" would either forbid the column US3-S1 requires or pin
      whatever this diff happened to produce. If a golden file helps, commit it
      as a BEFORE capture and assert the only difference is the added column.
- [ ] T032 [P] [US3] (spec US3-S5, FR-016, trap 14) **The laptop control.** Over
      a fixture corpus in a directory no git repository holds, assert every row
      still renders, every row's count column is the literal `unknown` rather
      than a number, and the output carries one line saying landings could not
      be read. `0` is a different answer from `unknown` and this is the test
      that keeps them apart.

### Implementation for this story

- [ ] T033 [US3] (FR-011, trap 12, trap 13, trap 14) Add the landed-versus-total
      count to each row in `factory/roadmap/cli.py:92` — `_render_roadmap`,
      without pushing the `blocked by:` tail off the line. The total is the
      stories the spec declares, parsed the way
      `factory/cli/status.py:491` — `_declared_story_keys` parses them; the
      landed half comes from the reader US2 built for FR-008 —
      `factory/workgraph/landed.py:130` — `landed_facts` with `fetch=False`,
      against the branch `factory/cli/status.py:401` — `_readiness_basis`
      resolves through `factory/workgraph/worktree.py:1471` — `landing_branch`
      for the repository `factory/cli/status.py:425` — `_repo_holding` finds.
      Never `main` by default. Pass it into
      `factory/roadmap/cli.py:46` — `render_command` as an injected seam and
      cache one scan per spec, the way
      `factory/cli/status.py:441` — `_observed_landed_resolver` caches it; do
      not write a second landed implementation and do not rescan per row.
- [ ] T034 [US3] (FR-012, trap 11) Add the `--state` filter to the `list` parser
      (`factory/cli/nouns/spec.py:113` — `_add_spec_parser`) and to
      `factory/roadmap/cli.py:46` — `render_command`, producing no spec row and
      one explanatory line on an empty match. `factory/cli/status.py:364` —
      `_entries` is the precedent for narrowing a corpus to one state.
- [ ] T035 [US3] (FR-016, trap 14) When the seam answers nothing — no git
      repository holds the corpus, or the branch will not resolve — render every
      count as `unknown` and emit one line saying landings could not be read.
      Never `0`, never a traceback: `factory/roadmap/cli.py:78` —
      `_cli_drift_resolver` says the render must work on a laptop with no
      factory running, and `factory/cli/status.py:378` — `_readiness_basis` is
      the written precedent for degrading and labelling the degrade.

### Verification for this story

- [ ] T036 [US3] (trap 18) Paste, as committed evidence, into
      `specs/076-a-spec-answers-to-its-number/evidence/us3-filters.md`, four
      **excerpts** and not four transcripts: (a) `ergane spec list specs` — its
      first ten rows plus the blocked spec's row, and one line stating the total
      row count, which must equal the spec count; (b)
      `ergane spec list specs --state ready` in full, which is one row at
      `602a92c`; (c) a `--state` run matching nothing — the explanatory line and
      no spec row, run over a pruned copy, because at `602a92c` every state the
      enum accepts has a member in this corpus (plan.md, operator step 5); and
      (d) a `list` run over a copy of `specs/` in a directory no git repository
      holds — its first five rows showing `unknown` in the count column, the
      explanatory line, and the total row count. Excerpts are the point: one
      full render is a measured 144 rows and 11,965 bytes and FR-011's column
      adds about eight characters a row, so two of them would be some 27 KB of
      evidence against the 65,536-byte allowance this story already shares with
      `tests/test_spec_list_filters.py` and its two-branch git fixture (plan.md,
      Sizing).

## Verification

- [ ] T037 Run the declared gate and paste its output; it must be green.
- [ ] T038 Re-run
      `ergane spec validate specs/076-a-spec-answers-to-its-number
      --target-repo . --specs-root specs` against the tree 133 landed on, before
      any dispatch, and read every anchor refusal as trap 1 firing.
- [ ] T039 Run the operator sequence in plan.md's "Verification the operator will
      run, independent of the gate", steps 1 through 6, and paste each result.
      Step 3 must be run from a working directory outside this repository, and
      with `-o` pointing at a scratch path, or it proves nothing and writes a
      tracked artifact (trap 18).
