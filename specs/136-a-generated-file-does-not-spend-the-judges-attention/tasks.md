# Tasks: a generated file does not spend the judge's attention

Read `plan.md` before starting. Four traps decide whether this spec is worth
dispatching. Trap 2: `092-the-diff-ceiling-and-the-evidence-doctrine-agree`
landed a requirement that **forbids** what FR-007 and FR-011 ask for, and this
spec supersedes it in writing — do not obey it and do not report it as a
conflict. Trap 3: `factory/verify/diffbounds.py:140-145` requires the refusal,
the abridgement record and `prepare_diff` to weigh the same assembly, so the
elision must be the same rule over the same sections in both modules, must not
be conditional on the diff being over the limit, and must weigh the stub on both
sides. Trap 15 is where that one rule has to live: the stub renderer goes in
`factory/verify/diffbounds.py`, because `diffbounds` may not import `judge`
(`factory/verify/diffbounds.py:9-14`, enforced as an exact set by
`tests/test_verification_sweep.py:879` — `test_exactly_one_module_imports_the_judge`)
and the reverse edge is a cycle besides. Trap 11 is the opposite hazard and the
one that would waste two whole stories: the patterns must reach production
through the activity inputs, or every test passes while the manifest key is read
by nobody. Trap 10 is the same hazard one hop earlier and it hides in a route
description: the pin forks at the activity result into the roadmap's child start
(`factory/roadmap/workflow.py:1303`) and the CLI's
(`factory/cli/nouns/build.py:951`), and the roadmap's is the one the schedule
fires unattended, so wiring only the CLI leaves every scheduled epic measuring
exactly as it does today with a green gate above it. Trap 5, trap 14 and trap 16 are the three places this work reaches
outside the function you are editing — a landed enumeration in
`tests/test_120_rewrite_carries_forward.py`, the store's hand-written serialiser,
and the refusal record's `largest_files` — and all three are declared scope, not
collateral.

Tests are written first and must fail before the implementation that satisfies
them. Six tasks are exceptions and are labelled **guard** where they appear:
they pass against today's tree by design, they are the controls that make the
other tests mean something, and each carries its own mutation in the test the
way `tests/test_forge_manifest.py:330-331` does. Do not hunt for a red run from
a guard; make the mutation clause true instead.

Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A repository declares which of its committed paths are generated

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) Given a v2 manifest declaring
      `generated_paths: ["package-lock.json", "**/*.lock"]`, assert it parses and
      the parsed configuration carries both patterns in declaration order.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001, trap 5) Given **one** manifest body
      declaring the key, assert the `version: 2` load parses and carries the
      patterns **and** the `version: 1` load is refused as an unknown top-level
      key naming `generated_paths`. Both halves in one test: the v1 half alone
      passes today, before any change, so only the pair can fail a diff that
      registered the key in `_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:109`) instead of `_V2_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:134`).
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) Given `generated_paths: [""]`,
      `generated_paths: [7]` and `generated_paths: "package-lock.json"`, assert
      each is refused with a message naming the offending value and the rule.
      Model the refusal shape on
      `factory/verify/factory_yaml.py:699` — `_read_diff_refusal_bytes` and the
      list handling on `factory/verify/factory_yaml.py:760` — `_read_caches`.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, FR-005, trap 4) Given a diff with one
      section matching a declared pattern and one matching none, assert the
      matching section is classified generated, its listing line carries its
      **real** added and removed counts plus an explicit marker, and the other
      line is byte-identical to today's. **And** assert that with no pattern
      declared the whole listing is byte-identical to today's string. The counts
      must come from `factory/verify/diffbounds.py:112` — `count_changes` over
      the full section text; a fixture whose generated section has known hunk
      counts is what makes a `+0 -0` regression fail here.
- [ ] T005 [US1] (spec US1-S5, FR-004, trap 10) Given a target repository whose
      committed manifest declares one set of patterns and whose node worktree
      carries a manifest declaring a different set, assert the patterns on the
      `EpicInput` the epic is actually started with are the committed clone's —
      on **both** dispatch paths, the roadmap's child start and the hand-started
      CLI's. Copy
      `tests/test_023_us2_dispatch_pin.py:756` — `test_roadmap_dispatch_reads_config_per_child`
      for the first and
      `tests/test_023_us2_dispatch_pin.py:389` — `test_cli_dispatch_v2_manifest_pins_declared_caps_and_order`
      for the second; both capture the epic input rather than the read that fed
      it. Asserting over
      `factory/verify/factory_yaml.py:1134` — `load_loop_config`'s return or over
      `factory/activities/roadmap_activities.py:822` — `ReadLoopConfigResult`
      does **not** satisfy US1-S5: both sit upstream of the fork, and the fork is
      where T012 can be half-done. Not `[P]`: it builds two manifests and drives
      dispatch over both.
- [ ] T006 [P] [US1] (spec US1-S6, FR-006, trap 6) **Guard — passes before this
      diff too, and says so in its own docstring.** Assert this repository's own
      `ergane.yaml` declares no `generated_paths` and resolves to the empty
      declaration. Mirror
      `tests/test_forge_manifest.py:339` — `test_this_repositorys_own_manifest_does_not_spend_the_key`,
      whose docstring at `tests/test_forge_manifest.py:340` labels itself the
      same way, and copy its reason into the assertion message: the config gate
      parses a node's manifest with the worker's installed parser, so a diff that
      teaches the key **and** spends it is refused at `CONFIG_ERROR` in 0.0s on
      every attempt. State the mutation in the docstring — declare the key in
      `ergane.yaml` and this test fails — so a reader can tell a control from a
      vacuous assertion.
- [ ] T007 [P] [US1] (spec US1-S7, FR-005) **Guard — passes before this diff
      too.** Assert that a grep of the three modules that classify, render and
      measure a section — `factory/verify/diffbounds.py`,
      `factory/verify/judge.py` and `factory/verify/diffcheck.py` — finds no
      lockfile filename and no package-manager name, so the declaration is the
      only source of the answer. Scope it to those three files and say why in the
      test: a grep of all of `factory/` **fails today**, before any change — `npm`
      is written fifteen times elsewhere, counted at 602a92c across four files,
      at `factory/verify/factory_yaml.py:804` (a cache example),
      `factory/stack_packs.py:45` (the stack packs) and
      `factory/verify/gates.py:834` (gate prose) among them, and none of those is
      a classification rule. Keep the search list short and named in the test, not
      derived, and state the mutation in the docstring the way
      `tests/test_forge_manifest.py:330-331` does: hard-code `package-lock.json`
      in the matcher and this test fails.

### Implementation for this story

- [ ] T008 [US1] (FR-001, trap 5) Add `generated_paths` to `_V2_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:134`) — **not** to `_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:109`), where `diff_refusal_bytes` sits at
      `factory/verify/factory_yaml.py:120` and which
      `tests/test_forge_manifest.py:333` pins to `ergane init`'s interview
      prompts. `factory/verify/factory_yaml.py:280` — `_reject_unknown_keys`
      picks its known-set by version at `factory/verify/factory_yaml.py:270` and
      needs no edit; neither does `factory/cli/init.py`, which carries the key
      forward off `_KNOWN_KEYS` (`factory/cli/init.py:511`). **One landed test
      does need an edit and it is declared scope**: the enumeration at
      `tests/test_120_rewrite_carries_forward.py:308` asserts
      `carried == ["ladder", "verify"]` at
      `tests/test_120_rewrite_carries_forward.py:310`, which is a list of the
      v2-only keys rather than a guard on this spec, so it gains
      `"generated_paths"` **last**, after `"verify"`, because
      `_V2_TOP_LEVEL_KEYS` is built by concatenation and the assertion compares
      lists. Wrong moves, both visible from the failure and both forbidden:
      do not weaken that assertion to a set comparison (it is 120 FR-006's
      invariant), and do not retreat to `_TOP_LEVEL_KEYS` (trap 5's first half,
      which fails `tests/test_forge_manifest.py:333` instead). Change nothing
      else in that file; `tests/test_120_rewrite_carries_forward.py:311` stays
      true untouched because this spec adds no interview prompt.
- [ ] T009 [US1] (FR-002, FR-003) Add the reader, called from the reader list in
      `factory/verify/factory_yaml.py:208` — `parse_factory_config` beside
      `factory/verify/factory_yaml.py:224`. Absent means `()`; a non-list, a
      non-string entry and an empty-string entry are each refused naming the
      value and the rule.
- [ ] T010 [US1] (FR-003) Add the field to `FactoryConfig` beside
      `diff_refusal_bytes` (`factory/verify/models.py:349`), defaulting to the
      empty tuple so FR-003 holds by construction. Do not reach for
      `factory/verify/models.py:275` — `_default_diff_refusal_bytes`'s deferred
      import: an empty tuple needs no module to own it.
- [ ] T011 [US1] (FR-005, trap 4) Add the classification to
      `factory/verify/diffbounds.py:80` — `DiffSection` and set it in
      `factory/verify/diffbounds.py:93` — `split_sections` from a matcher over
      the declared patterns, **after**
      `factory/verify/diffbounds.py:112` — `count_changes` has read the full
      text. Then mark the generated line in
      `factory/verify/diffbounds.py:125` — `file_listing`, keeping its real
      counts. Default the pattern list to empty everywhere so an unclassified
      call renders today's string byte for byte.
- [ ] T012 [US1] (FR-004, trap 10) Carry the patterns on
      `factory/verify/factory_yaml.py:1134` — `load_loop_config`'s return
      (`factory/verify/factory_yaml.py:1086`, and the signature at
      `factory/verify/factory_yaml.py:1070`), then along the route
      `diff_refusal_bytes` already takes:
      `factory/activities/roadmap_activities.py:822` — `ReadLoopConfigResult`
      (field beside `factory/activities/roadmap_activities.py:833`, filled at
      `factory/activities/roadmap_activities.py:858` and
      `factory/activities/roadmap_activities.py:866`), and then **both** forks of
      the route, not one: the roadmap's own child start —
      `factory/roadmap/workflow.py:1247` — `_dispatch` builds the child
      `EpicInput` at `factory/roadmap/workflow.py:1296` and names the pinned
      value at `factory/roadmap/workflow.py:1303` — **and** the hand-started
      CLI's — `factory/cli/nouns/build.py:826`,
      `factory/cli/nouns/build.py:845`, the helper signature at
      `factory/cli/nouns/build.py:890`, and
      `factory/cli/nouns/build.py:951` on the `EpicInput` at
      `factory/cli/nouns/build.py:931`. Both land on
      `factory/workgraph/workflow.py:537` — `EpicInput` beside
      `factory/workgraph/workflow.py:595`. Eleven lines across five files, and
      the roadmap fork is the one the schedule fires, so leaving it out ships a
      manifest key that only hand-started epics honour. `factory/workgraph/cli.py:675` is a third
      `EpicInput` site and is **not** on this route — it is the legacy entry
      point and carries no 092 pin either. Default every hop to empty so a
      payload written before this story still constructs. The return is a 3-tuple
      today: widening it breaks five unpackings, and the three in landed tests
      are declared scope — `tests/test_092_manifest_threshold.py:186`,
      `tests/test_092_manifest_threshold.py:233` and
      `tests/test_023_us2_dispatch_pin.py:848`. Widen each unpacking; do not
      change what those tests assert.

### Verification for this story

- [ ] T013 [US1] Paste, as committed evidence, the refusal text for each of the
      three malformed declarations in T003, the v1 refusal from T002, and the
      rendered file listing for one diff with a pattern declared and the same
      diff without — the pair being the proof that FR-003 holds.

## Phase 2: User Story 2 — The judge's attention is not spent on a generated file

### Tests for this story (write FIRST, must fail)

- [ ] T014 [P] [US2] (spec US2-S1, FR-007, traps 3 and 17) Given twenty
      5,120-byte source sections plus one 102,400-byte generated section and an
      allowance of 65,036, assert only the twenty source sizes reach
      `factory/verify/judge.py:515` — `_allocate`, that the twenty grants divide
      the whole 65,036-byte allowance — 3,251 or 3,252 bytes each, measured at
      602a92c — and that the generated section is replaced by a stub. Assert the
      grants, not just the total: today the generated section takes 24,076 of
      65,036 (37.0%) and every source section is cut to `SMALL_FILE_FLOOR`
      (`factory/verify/judge.py:121`) = 2,048, so the source bytes shown go from
      40,960 to 65,036. Do **not** assert the sections are carried whole and do
      not "fix" the code until they are: 20 x 5,120 = 102,400 still exceeds the
      allowance, so `factory/verify/judge.py:542` — `_render_section` still cuts
      every one of them and `PreparedDiff.truncated` is still true here. Trap 17
      names the two contortions that Then would otherwise buy.
- [ ] T015 [P] [US2] (spec US2-S2, FR-008, trap 3) **The scenario a partial fix
      fails.** Given a diff comfortably **under** the attention limit containing a
      generated section, assert the body is still elided and the stub still names
      the path, its real counts and its real byte size.
      `factory/verify/judge.py:473` — `prepare_diff` returns `whole` untouched on
      that path today (`factory/verify/judge.py:493`), which is exactly where an
      over-limit-only fix would leave the two measurements disagreeing.
- [ ] T016 [P] [US2] (spec US2-S3, FR-009) Given a diff whose only elision is a
      declared generated file, assert **both** halves in one test: the prepared
      text carries the stub in place of the generated body, **and**
      `PreparedDiff.truncated` (`factory/verify/judge.py:265`) is false and the
      prompt's `truncated_input` (`factory/verify/judge.py:286`) is false. The
      second half alone is true today on any under-limit diff — `prepare_diff`
      returns `whole` untouched at `factory/verify/judge.py:493` with
      `truncated=False` — so only the pair asserts that an elision *happened* and
      was not called a truncation. A disclosed elision of a declared generated
      file is not "the judge could not see what it needed", and conflating the two
      would mark every future lockfile-bearing PASS as made on an abridgement.
- [ ] T017 [US2] (spec US2-S4, FR-010, trap 11) Drive
      `factory/activities/verify_activities.py:430` — `run_judge` with an
      activity input that names the patterns, and assert the assembled prompt
      carries the stub. The test may **not** hand patterns to `prepare_diff`,
      `build_prompt` or `judge.run_judge` directly — that is the shortcut this
      scenario exists to refuse. Not `[P]`: it drives the activity seam the
      implementation task edits.
- [ ] T018 [P] [US2] (spec US2-S5, FR-003, FR-008) **Guard — the control, and it
      passes before this diff too.** Given a manifest declaring no patterns,
      assert the assembled prompt over a fixture diff is byte-identical to
      today's. Capture today's bytes from the tree before the implementation
      lands, not after, and state the mutation in the docstring: elide by suffix
      rather than by declaration and this test fails.

### Implementation for this story

- [ ] T019 [US2] (FR-007, FR-008, traps 3, 4 and 15) Write the stub renderer as
      **one** function in `factory/verify/diffbounds.py`, beside
      `factory/verify/diffbounds.py:125` — `file_listing`, where the section
      vocabulary both modules share already lives; give it the section and have
      it name the path, the real added and removed counts and the real byte size.
      Reach it from `factory/verify/judge.py:473` — `prepare_diff` by adding one
      more name to the private-alias import at `factory/verify/judge.py:63`, the
      route `_file_listing`, `_split_sections` and `_count_changes` already take.
      **Do not put it beside `factory/verify/judge.py:542` — `_render_section`**,
      however natural that looks: US3 has to weigh the identical bytes from
      `factory/verify/diffbounds.py:137` — `assembled`, and `diffbounds` may not
      import `judge` — `factory/verify/diffbounds.py:9-14` states the fence and
      `tests/test_verification_sweep.py:879` — `test_exactly_one_module_imports_the_judge`
      asserts it as an exact set over every file under `factory/verify/`, so that
      placement turns the declared gate red and cycles at import time. Then, in
      `prepare_diff`, replace every generated section with that stub on **both**
      paths — the untouched return at `factory/verify/judge.py:493` and the
      abridged one — and pass only the non-generated sizes to `_allocate` at
      `factory/verify/judge.py:501`. The stub's bytes count toward `whole`; US3
      weighs the same bytes by calling the same function, because there is one
      assembly.
- [ ] T020 [US2] (FR-009) Leave `PreparedDiff.truncated`
      (`factory/verify/judge.py:265`) meaning what it means today: set by the
      abridger cutting a section it would otherwise have shown, never by the
      elision. If the natural implementation compares rendered text against
      section text, the generated sections must be excluded from that
      comparison.
- [ ] T021 [US2] (FR-010, trap 11) Thread the patterns from the pinned epic input
      to `prepare_diff`: a field on
      `factory/activities/verify_activities.py:399` — `RunJudgeInput`, passed at
      `factory/activities/verify_activities.py:444` into
      `factory/verify/judge.py:752` — `run_judge`, on through
      `factory/verify/judge.py:307` — `build_prompt` at
      `factory/verify/judge.py:352`, and named once in the workflow at
      `factory/workgraph/workflow.py:2923` — which is inside
      `factory/workgraph/workflow.py:2942` — `_score`, **not** inside
      `factory/workgraph/workflow.py:2749` — `_judge`, which reaches it only
      through `self._score(...)` at `factory/workgraph/workflow.py:2771`. Empty
      default at every hop. Without this task every test above can pass while
      production reads nothing.

### Verification for this story

- [ ] T022 [US2] Paste, as committed evidence, the `_allocate` grants for the
      T014 fixture before and after — the before being the four measured lines
      quoted in `plan.md` § "What already exists, and where", the after being the
      twenty grants of 3,251/3,252 summing to 65,036 that the same section
      records — and the stub line as rendered, so a reader can see the path, the
      counts and the byte size the judge was told about. The pasted after-grants
      and the US2-S1 Then must say the same thing; if they disagree, the Then is
      wrong and trap 17 says why.

## Phase 3: User Story 3 — The refusal stops counting bytes the judge will never read

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1, FR-011) Given a diff of 70,652 assembled bytes
      of which 53,176 belong to a declared generated path, and a threshold of
      65,536, assert no size refusal is recorded and that the measured total
      **equals** the assembly `factory/verify/judge.py:473` — `prepare_diff`
      builds from the same patch and the same patterns — compare against that
      value directly, never against a literal. `70,652 - 53,176 = 17,476` is the
      pre-marker measurement and is **not** the expected number: the total also
      carries the stub and the listing's generated marker, and an expectation
      written as `17476 + len(stub)` is off by the marker. **And** assert the
      identical diff with no pattern declared is still refused with today's
      message. Only the pair can fail a diff that changed nothing in production.
- [ ] T024 [P] [US3] (spec US3-S2, FR-012, traps 9 and 14) Assert the record
      names the excluded path and the bytes it carried **after a store round
      trip** — write it with `upsert_result` and read it back with
      `node_history`, the way `tests/test_092_abridged_is_recorded.py:148`
      asserts the abridgement record survives, and assert the serialised document
      the way `tests/test_092_abridged_is_recorded.py:274` does. An in-memory
      assertion alone is satisfied by a field that is dropped on write. The
      record types are `factory/verify/models.py:456` — `DiffSizeRefusal`,
      `factory/verify/models.py:479` — `DiffAbridgement` and
      `factory/verify/models.py:521` — `OutputCheck`; a measurement that left
      something out and did not say so is the omission Principle VIII refuses,
      and the loaded row is the only thing an operator ever reads
      (`factory/cli/nouns/build.py:1625`).
- [ ] T025 [P] [US3] (spec US3-S3, FR-014, trap 12) **Guard — the control that
      matters most, and it passes before this diff too.** Given a diff of 70,652
      bytes with no generated file in it at all, assert it is still refused at the
      same threshold, with today's message and today's `largest_files` list. Copy
      the expected strings from the current behaviour rather than writing new
      ones, and state the mutation in the docstring: exclude by suffix rather than
      by declaration and this refusal disappears.
- [ ] T026 [P] [US3] (spec US3-S4, FR-014, trap 12) **Guard — passes before this
      diff too.** Given a v2 manifest declaring `verify: [gates, judge]`, assert
      it is still refused by `factory/verify/factory_yaml.py:958-963` with its
      message unchanged. Write the manifest that way rather than as "a manifest
      with no `diff_check`": a manifest with **no** `verify:` block is not refused
      at all — it takes the default order at
      `factory/verify/factory_yaml.py:923-924`, which already contains the step —
      so a test written from those words fails against today's tree before any
      change. State the mutation in the docstring: make `diff_check` optional to
      get a story's bytes under the threshold and this test fails.
- [ ] T027 [US3] (spec US3-S5, FR-013, trap 11) Drive the output-check activity
      with an input that names the patterns and assert the exclusion happened;
      **and** assert an input naming none measures byte-identically to today.
      The test may not hand patterns to
      `factory/verify/diffbounds.py:137` — `assembled` or
      `factory/verify/diffcheck.py:172` — `check_output` around
      the activity. Not `[P]`: it drives the seam T032 edits.
- [ ] T028 [P] [US3] (spec US3-S6, FR-011, trap 3) Given a diff that exceeds
      `DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`) only because of a
      declared generated body, assert
      `factory/verify/diffbounds.py:159` — `abridgement` and
      `factory/verify/judge.py:473` — `prepare_diff`, given the
      same patch and the same patterns, agree: the record's `abridged` equals
      `PreparedDiff.truncated`. This is
      `tests/test_092_abridged_is_recorded.py:141` held at the margin the
      patterns move, and it is what fails if `assembled` drops the stub the
      prompt still carries.
- [ ] T029 [P] [US3] (spec US3-S7, FR-011, FR-012, trap 16) Given a diff whose
      **non-generated** bytes alone exceed the threshold and which also carries a
      declared generated section of 53,176 bytes, assert the refusal fires and
      that no entry in its `largest_files` **names** the generated path, while
      the excluded path and its real byte count are on the FR-012 field. Assert
      the rendered brief too, not only the record:
      `factory/workgraph/prompt.py:956` quotes
      `factory/workgraph/prompt.py:975` — `_size_listing` into the next attempt's
      prompt, and a listing that names an uncounted body is the wrong ruler this
      spec must not hand the agent. State the mutation in the docstring: rank
      `largest_files` over the section bodies the way
      `factory/verify/diffbounds.py:220-223` does today and the generated path is
      named as what spent a total that never counted it. Do **not** write "states
      more bytes than its own `total_bytes`" into the assertion or the docstring:
      the refusal only fires above the threshold, so for this fixture 53,176 is
      necessarily below the recorded total and that clause would be vacuous
      (trap 16).

### Implementation for this story

- [ ] T030 [US3] (FR-011, traps 3, 15 and 16) In
      `factory/verify/diffbounds.py:137` — `assembled`, weigh a generated section
      as the stub instead of as its body at `factory/verify/diffbounds.py:155`,
      keeping `file_listing` complete and the stub's own bytes in the total. Call
      **the function T019 added to this module** — do not re-render the stub
      inline here and do not write a second formatter; two implementations of one
      rule that must agree to the byte is trap 3's second bullet and it lands
      green. Read `factory/verify/diffbounds.py:140-145` first and keep its
      promise. Give `factory/verify/diffbounds.py:159` — `abridgement` the same
      patterns, so the record and the prompt cannot disagree. Then narrow the
      record in the same pass: `factory/verify/diffbounds.py:182` — `size_refusal`
      ranks `largest_files` at `factory/verify/diffbounds.py:212` and builds it at
      `factory/verify/diffbounds.py:220-223` from `section.size`, the body's own
      length, so leave that unnarrowed and the record names 53,176 bytes beside a
      `total_bytes` that never counted them (trap 16). Build it from the same
      narrowed measurement.
- [ ] T031 [US3] (FR-012, trap 14) Record the exclusion on the output check:
      which paths were excluded and how many bytes they carried, filled where
      `factory/verify/diffcheck.py:172` — `check_output` already fills the
      refusal and the abridgement at `factory/verify/diffcheck.py:252-256` and
      `factory/verify/diffcheck.py:262` — **and serialised**, or no operator ever
      sees it: add it to
      `factory/verify/store.py:1129` — `_output_check_to_dict` and to
      `factory/verify/store.py:1214` — `_output_check_from_dict`, whose
      whitelists are hand-written field by field. Recorded on every attempt where
      any were excluded, and absent — never zero — when nothing was, so rows
      written before this story load unchanged.
- [ ] T032 [US3] (FR-013, trap 11) Thread the patterns from the pinned epic input
      to the measurement: a field on
      `factory/activities/verify_activities.py:294` — `CheckOutputInput`, passed
      at `factory/activities/verify_activities.py:344` into `check_output`, and
      from there to the two sites that measure — `factory/verify/diffcheck.py:253`
      (the refusal) and `factory/verify/diffcheck.py:262` (the abridgement
      record) — and named once in the workflow at
      `factory/workgraph/workflow.py:2619`, inside the activity call at
      `factory/workgraph/workflow.py:2607`. Empty default at every hop.
      `factory/verify/diffcheck.py:342` — `diff_size_refusal` is **not** on this
      route: it is a parallel public seam with no production caller, so update
      its signature for consistency if you touch it at all, and never mistake
      threading a value into it for wiring the check.
- [ ] T033 [US3] (FR-014, trap 12) Confirm by reading that
      `DIFF_REFUSAL_THRESHOLD` (`factory/verify/diffbounds.py:66`),
      `DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`) and the mandatory
      `diff_check` rule at `factory/verify/factory_yaml.py:958-963` are
      unchanged. **If any of them moved, the design is wrong**: this story
      narrows what is weighed, and nothing else.

### Verification for this story

- [ ] T034 [US3] Paste, as committed evidence, the output check's record for the
      same diff twice — once with the lockfile declared and once without — the
      first passing and naming the excluded path and its bytes **as read back
      from the store**, the second refused at 70,652 against 65,536 with
      `package-lock.json` at 53,176 named as the largest contributor. Then paste
      the T029 case: the refusal that fires in a pattern-declaring repository,
      with its `largest_files` and its `total_bytes` side by side, so a reader can
      check that no entry exceeds the total. All three produced through the
      activity input, not by calling `assembled` directly.

## Verification

- [ ] T035 The full gate command passes green.
- [ ] T036 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 4 — writing a different `generated_paths`
      list into the node's worktree copy of the manifest mid-attempt and
      confirming the pinned value did not move — is the one step no committed
      test stands in for, because it is about which file was read and when. Step
      2 is the falsifiable test of the whole spec: the container run's 70,652
      bytes against 65,536, run forwards.
