# Tasks: the ledger takes what is not yet a defect

Read `plan.md` before starting. Three of its traps describe work that looks done
and is not: trap 4 (the completion assertion must read the emitted script, not
the parser's alias table), trap 7 (`.specify/templates/` no longer describes the
contract and FR-011 does **not** point there), and trap 12 (FR-007 cannot be
proved by looking at today's probes — the obvious test passes against an empty
production diff). Four more would fail the story they belong to outright. Trap 9:
the prose sweep is nine lines in six files, not the three the 2026-08-28 draft
named. Trap 10: the fragmentation class this spec once asked to change cannot be
exercised by any row in this ledger, so FR-008 leaves it alone and US2-S4 is
about the heading. Trap 13: hiding the verb from shell completion does **not**
hide it from `ergane findings --help`, one argparse shape does, and its metavar
must be *derived* rather than typed out or US3's own `draft` breaks every page
guard in the repository — read the second and third transcripts in § *The alias
trap, measured* before writing T006. Trap 14: the live ledger does not fit in a
story's evidence — `ergane findings list` alone is 56,899 bytes against a
65,536-byte refusal (`factory/verify/diffbounds.py:66`,
`DIFF_REFUSAL_THRESHOLD`) — so T021 and T029 paste excerpts and counts, never a
document. Traps 15 and 16 are two-line hazards inside single tests: a clock that
must be frozen, and the word `reporter`.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase because they
touch independent test functions. No `[P]` spans stories — all three edit
`factory/cli/doctor.py:251` — `add_findings_parser` and are serialised for that
reason.

## Phase 1: User Story 1 — The write verb says it writes

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, trap 15) Identical-row test, in a new
      `tests/test_115_us1_record_verb.py`: file the same finding through `record`
      into one scratch store and through `report` into a second, then assert
      every column of the resulting row matches, including `occurrences`,
      `first_seen` and the `finding_events` trail. Freeze the clock first —
      `factory/cli/doctor.py:61` — `_utcnow` has second resolution and stamps
      `first_seen`, `last_seen` and the event row, so two invocations either side
      of a tick differ in three columns for a reason the rename did not cause.
      The in-tree pattern is `tests/test_ergane_findings.py:106` —
      `_freeze_doctor_utcnow`, an autouse fixture monkeypatching
      `factory.cli.doctor._utcnow`; it is module-local and a new module does not
      inherit it. Assert against the store, not the parser: the claim FR-002
      makes is that behaviour did not change, and only the row can prove that.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Stream-separation test: run
      `findings report`, assert its exit status equals `record`'s, assert its
      stdout is byte-identical to `record`'s, and assert the deprecation line
      naming `record` appears on **stderr** and nowhere else. Stdout for this
      noun is parsed — `findings list --json` and `findings triage --json` both
      exist — so a notice there is a breaking change wearing a helpful face.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 4) Completion-output test: run
      `ergane completion bash` and `ergane completion zsh` and assert `record` is
      offered for the `findings` noun and `report` is not. Assert on the emitted
      script, never on whether the parser has an alias — the alias exists, and
      that is exactly why the naive assertion passes while
      `factory/cli/completion.py:53` advertises the dead name.
- [ ] T004 [P] [US1] (spec US1-S3, FR-003, trap 13, trap 16) Help-text test,
      three assertions. First: the string `report` appears nowhere in
      `ergane findings --help` — not in the usage line, not in the verb listing,
      not in the noun description. All three are separate surfaces: argparse
      renders every registered name into the usage metavar unless an explicit
      `metavar` overrides it, `aliases=` with `help=` prints `record (report)` in
      the listing regardless of the metavar, and `factory/cli/doctor.py:262` is a
      hand-written description string reading `Report, list, resolve, or promote
      findings.` that no parser change touches. Second: the brace set the usage
      metavar renders equals the set of registered verbs minus the one carrying
      the deprecated-name declaration — read the metavar the same way
      `tests/page_holds_true.py:346` — `verbs_of` reads it, so this assertion
      fails the day a verb is registered and left out, which is US3. Third: on
      `ergane findings record --help`, the only occurrence of the substring
      `report` is `--source`'s help string `reporter source`
      (`factory/cli/doctor.py:287`) — exempt that line explicitly rather than
      loosening the match, because FR-001 pins that string and a match loosened
      to a word boundary would also pass a usage line that still said `report`.
      The first assertion fails against every shape the 2026-08-28 draft
      permitted; trap 13 names the one that passes both it and the second.
- [ ] T005 [P] [US1] (spec US1-S4, FR-004, trap 9) Prose-guard test: enumerate
      tracked markdown with `git ls-files '*.md'`, exclude `specs/`, and assert
      the string `findings report` appears in none of it. Both exclusions are
      load-bearing: `specs/` carries this spec's own citation of the old verb,
      `specs/089-a-spec-that-fixes-a-finding-declares-it/plan.md:130`, and the
      whole prose of the sibling draft
      `specs/152-the-findings-channel-accepts-an-honest-report/`; and a
      filesystem walk instead of `git ls-files` goes red on the operator's
      checkout for untracked documents a node's worktree never sees. Prove the
      guard is not vacuous by asserting it turns red against a fixture string.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, FR-003, trap 13) At
      `factory/cli/doctor.py:276`: register `record` as the write verb with
      today's arguments and runner — the sixteen lines at
      `factory/cli/doctor.py:277-292` move verbatim, `--source`'s `reporter
      source` help string included — and register `report` as a **second
      `add_parser` carrying no `help=`**, sharing the same `parents=` parent and
      running the same command function with a deprecation line on stderr.
      Declare *which* name is deprecated exactly once — one `set_defaults`
      marker on that second parser, or one constant — because T007 and the
      metavar both read it. Then, **after every verb is registered**, set the
      `metavar` on the `add_subparsers` call at `factory/cli/doctor.py:264` from
      the subparsers' own `_name_parser_map` minus that declaration; do not type
      the brace list out. A hand-written list parses fine and fails silently:
      `metavar` never touches `choices`, and `tests/page_holds_true.py:346` —
      `verbs_of` reads the braces as the verb set, so US3's `draft` would be
      rejected as non-existent by `tests/test_claude_md.py:81` and its two
      siblings. Rewrite the noun description at `factory/cli/doctor.py:262` so it
      says `record`. Not `aliases=`: measured, `aliases=` with `help=` prints
      `record (report)` in the verb listing whatever the metavar says, and
      without an explicit metavar every registered name lands in the usage line.
- [ ] T007 [US1] (FR-003, trap 4, trap 13) In `factory/cli/completion.py:32` —
      `_noun_and_verb_map`: at `factory/cli/completion.py:53`, drop the
      deprecated name before emitting, reading the same declaration T006 wrote
      rather than a second list of names. Grouping by `id(parser)` is **not**
      sufficient here and would land a no-op: it works only for `aliases=`, where
      both names map to one object, and T006 registers a second `add_parser`, so
      `record` and `report` are distinct objects and both survive the grouping.
      The transcript in `plan.md` § *The alias trap, measured* shows the leak, the
      `id(parser)` result and why the mechanism decides which fix works.
- [ ] T008 [US1] (FR-004, trap 8, trap 9) Rewrite the nine tracked lines that
      name the old verb: `CLAUDE.md:106`, `docs/architecture.md:558`,
      `docs/cli/findings.md:11`, `docs/cli/findings.md:12`,
      `docs/cli/findings.md:56`, `.claude/skills/away-mode/SKILL.md:158`,
      `.claude/skills/findings-ingest/SKILL.md:186`,
      `.claude/skills/findings-ingest/SKILL.md:249` and
      `.claude/skills/findings-ingest/SKILL.md:250`; then update the verb tuple
      at `tests/test_ergane_env_completion.py:120`, which spells the verb as a
      bare `"report"` and is the one call site a grep for `findings report` does
      not surface.

### Verification for this story

- [ ] T009 [US1] (spec US1-S1, spec US1-S2, spec US1-S3, spec US1-S4) Paste, as
      committed evidence, into the story's PR body and an artifact under the
      spec directory: the two rows produced by `record` and by `report` shown
      identical; the deprecation line taken from stderr with stdout shown
      clean beside it; the usage line of `ergane findings --help` with its brace
      list; the `findings)` line of `ergane completion bash` before
      and after, against the recorded baseline
      `list promote report resolve triage`; the output of
      `git grep -n 'findings report' -- '*.md' | grep -v '^specs/'` showing no
      lines; and the full-suite before-and-after counts.

## Phase 2: User Story 2 — A want is not a defect, and the ledger can tell

### Tests for this story (write FIRST, must fail)

- [ ] T010 [US2] (spec US2-S1, FR-006, trap 5) Withheld-count test, in a new
      `tests/test_115_us2_feedback_lane.py`: with a scratch store holding both
      defect rows and `feedback/` rows, run `findings list` with no flags and
      assert the feedback rows are absent **and** that the output states how many
      were withheld and names the flag that shows them. Read the expected count
      from the store, and give the fixture a row count that appears nowhere in
      the source, so a hardcoded number cannot pass.
- [ ] T011 [P] [US2] (spec US2-S2, FR-005) Composed-filter test: assert
      `--category` filters on the `category` column and composes with
      `--severity` and `--status` rather than replacing either. Put the
      `--category feedback` and `--all` cases in the same matrix so the three
      views are pinned together.
- [ ] T012 [P] [US2] (spec US2-S2, FR-006, trap 11) JSON-shape test: assert
      `findings list --json` still emits a bare array under every flag
      combination, and that the withheld notice reaches stderr rather than
      stdout on that path.
      Three in-tree consumers parse that array:
      `.claude/skills/findings-ingest/SKILL.md:77` is the corpus dump that decides
      whether a key already exists — the one
      `.claude/skills/findings-ingest/SKILL.md:73` calls mandatory before minting
      anything — and it already selects `open` and `regressed`, which is every
      feedback row in the ledger;
      `.claude/skills/findings-ingest/SKILL.md:136` runs
      `jq -r '.[].key' | cut -d/ -f1 | sort -u` to list the categories already in
      use; and `.claude/skills/findings-ingest/SKILL.md:187` runs `jq length` over
      the rehearsal store. Wrapping the array in an object to carry the count
      breaks all three, and a corpus dump that sees fewer keys mints duplicates.
      Assert each of those three lines carries `--all` after T020, read out of
      the skill file rather than restated here.
- [ ] T013 [P] [US2] (spec US2-S2, FR-006) Synopsis-guard test: read the
      `ergane findings list` synopsis line at `docs/cli/findings.md:10` and
      assert every flag it names is present in `ergane findings list --help`.
      This is the only thing holding that page to the CLI — nothing else in the
      suite does — and it is what stops the docs half of FR-006 from being a
      prose edit nobody checks: it stays red until `--category` and `--all`
      exist, so a documentation-only diff cannot satisfy it. Point it at the
      synopsis line by its content, not by its line number, so US1's edits to
      `docs/cli/findings.md:11` and `:12` cannot move it silently.
- [ ] T014 [P] [US2] (spec US2-S3, FR-007, trap 12) Reserved-lane refusal test,
      two halves. First: drive a synthetic probe whose `evaluate` returns a
      `factory/doctor/probes.py:43` — `FindingReport` in the reserved category
      through the probe path at `factory/cli/doctor.py:194-204`, and assert it is
      skipped with a message naming the probe and the lane and that no row was
      written. Second: **replace** `REGISTRY` (`factory/doctor/probes.py:628`) —
      `monkeypatch.setattr(_probes, "REGISTRY", [feedback_probe, defect_probe])` —
      and assert the refusal fires through the real loop **and** that the ordinary
      probe after it still files its row, which is what pins FR-007 to
      skip-and-continue rather than raise. Replace, never append: appending leaves
      the five real entries in the list, so
      `factory/cli/doctor.py:188` — `_run_all_probes` reaches Temporal and the
      resolved runtime root from a unit test. Only the pair proves the guard is
      not vacuous — asserting that today's five probes are clean passes against an
      empty production diff.
- [ ] T015 [P] [US2] (spec US2-S4, FR-008, trap 10) Triage-heading test:
      classify a store holding one `feedback/` row and three defect rows, and
      assert the feedback row is listed under its own heading in **both**
      `factory/doctor/triage.py:710` — `render` and
      `factory/doctor/triage.py:675` — `to_document`, under no other class's
      heading in either, and still counted in `total` and `classified`
      (`factory/doctor/triage.py:204` — `Triage`). Assert the cold rule and the
      closed-by-a-landed-spec rule still reach a feedback row: FR-008 changes
      where a row is *printed*, not which class it lands in. Do **not** write a
      fragmentation assertion here: `factory/doctor/triage.py:444` —
      `_fragmented_groups` reads only keys of three or more segments
      (`factory/doctor/triage.py:455-456`) and no open or regressed row in this
      ledger has more than two, so any such assertion is green before the story
      starts — trap 10 has the measurement.
- [ ] T016 [P] [US2] (FR-006, FR-007, FR-008, trap 1) One-constant test, written
      as a **substitution** and not as an identity check. Build one scratch store
      holding a `feedback/` row and a `zzz-not-a-lane/` row, monkeypatch the
      single reserved-category constant on its own module —
      `monkeypatch.setattr(_lane, "RESERVED_CATEGORY", "zzz-not-a-lane")`, the
      module T018 creates — and assert all three surfaces move to the sentinel
      together: `findings list` with no flags withholds the `zzz-not-a-lane/`
      rows and lists the `feedback/` rows normally, with the withheld count
      naming the sentinel rows; a probe report in the sentinel category is
      skipped at `factory/cli/doctor.py:240` — `_report_if_new` while a
      `feedback/` one is written; and `ergane findings triage` gives the sentinel
      its own heading in both faces while the `feedback/` row falls under its
      ordinary class. A surface that still spells the literal stays behind on
      `feedback` and the assertion for that surface goes red, naming it. Do
      **not** assert instead that the three resolve the name "by identity rather
      than by string equality": measured on this box, CPython 3.12.3 interns
      identifier-shaped literals, so two modules each holding only
      `X = "feedback"` give `m1.X is m2.X` → `True` and that assertion is green
      against exactly the three private literals trap 1 forbids. Trap 1 carries
      the measurement and the reason the sentinel is not identifier-shaped.

### Implementation for this story

- [ ] T017 [US2] (FR-005, FR-006, trap 5, trap 11) In
      `factory/cli/doctor.py:368` — `findings_list_command`: add `--category` and
      `--all` beside the two filters already applied there, and emit the
      withheld-count line — to stderr, so the `--json` early return at
      `factory/cli/doctor.py:378-380` keeps printing a bare array. Filter in the
      command, not in `factory/doctor/store.py:454` — `list_findings`, which
      takes no arguments today and whose signature is not this story's job.
- [ ] T018 [US2] (FR-007, trap 1, trap 12) Declare the reserved-category constant
      exactly once, in a new leaf module `factory/doctor/lane.py` holding
      `RESERVED_CATEGORY = "feedback"` and importing nothing, so neither
      `factory/cli/doctor.py` nor `factory/doctor/triage.py` can cycle on it. Then
      have **every** consumer read it as a module attribute at the point of use —
      `import factory.doctor.lane as _lane`, then `_lane.RESERVED_CATEGORY`, the
      shape `factory/cli/doctor.py:27` already uses for `_probes` and the reason
      T014 can replace `REGISTRY`. Do not write
      `from factory.doctor.lane import RESERVED_CATEGORY`: it binds the value at
      import time, T016's monkeypatch then reaches nothing, and the test that is
      supposed to hold FR-006, FR-007 and FR-008 to one name goes green whatever
      the consumers spell. Refuse a reserved-category `FindingReport` at
      `factory/cli/doctor.py:240` — `_report_if_new`, the one *wired* path every
      probe finding takes into the store, with a message naming the probe and the
      lane, skipping that report and continuing the loop rather than raising —
      `factory/cli/doctor.py:230-236` is the grammar already there. Edit
      `factory/cli/doctor.py` only: `factory/doctor/cli.py:257` —
      `_report_if_new` is an identically-named twin that no parser reaches, so a
      grep returns two definitions and a patch on the wrong one reads correct in
      the diff and changes nothing.
- [ ] T019 [US2] (FR-008, trap 10) In `factory/doctor/triage.py`: add the
      separate heading to `factory/doctor/triage.py:710` — `render` **and**
      `factory/doctor/triage.py:675` — `to_document`, so a reserved-lane row is
      printed under it and under nothing else. Do not remove those rows from the
      pool built in `factory/doctor/triage.py:470` — `classify`; that breaks the
      `total`/`classified` invariant the report prints. Do not touch
      `factory/doctor/triage.py:444` — `_fragmented_groups`: FR-008 puts it out
      of scope because no key in this ledger reaches its three-segment guard at
      `factory/doctor/triage.py:455-456`.
- [ ] T020 [US2] (FR-006, trap 11) Bring the prose with the interface. Add
      `--all` to all **three** call sites in the ingest skill:
      `.claude/skills/findings-ingest/SKILL.md:77` (the corpus
      dump that decides whether a key already exists — mandated at
      `.claude/skills/findings-ingest/SKILL.md:73`, and its
      `select(.status=="open" or .status=="regressed")` filter already matches
      every feedback row there is),
      `.claude/skills/findings-ingest/SKILL.md:136` (the category-reuse list) and
      `.claude/skills/findings-ingest/SKILL.md:187` (the rehearsal row count).
      All three read every row on purpose and all three
      go wrong quietly the moment the default hides a lane; the first one failing
      quietly is how an ingest agent mints a duplicate key for a want that already
      has one. Then update the reference page: the synopsis at
      `docs/cli/findings.md:10` gains `[--category NAME] [--all]`, and the
      `## ergane findings list` section at `docs/cli/findings.md:22` — whose flag
      sentence is `docs/cli/findings.md:39` — states the reserved lane, the
      withheld notice and which flag shows the rows. T013 is the guard that keeps
      the synopsis honest. Re-run
      `git grep -n 'findings list' -- '.claude' 'docs' '*.md'`
      before editing and reconcile the result with this list — it was two lines at
      drafting and three at refinement.

### Verification for this story

- [ ] T021 [US2] (spec US2-S1, spec US2-S2, spec US2-S3, spec US2-S4, trap 14)
      Paste, as committed evidence, **under 16 KiB total** — measured
      2026-09-04, `ergane findings list` alone is 56,899 bytes,
      `ergane findings triage` 43,538, `ergane findings triage --json` 87,193 and
      `ergane findings list --json` 119 MB, against the 65,536-byte refusal that
      counts pasted evidence (`factory/verify/diffbounds.py:66`,
      `DIFF_REFUSAL_THRESHOLD`), so a whole
      document may never be pasted and the `--json` document may never be pasted
      at all. Paste instead: (a) the three views — no flags, `--category
      feedback`, `--all` — taken in full **from the fixture store this story's
      own tests build**, which holds a handful of rows; (b) from the live ledger,
      the withheld-count line alone, the two `findings list --json | jq length`
      numbers with and without `--all`, and their difference shown equal to that
      count; (c) the refusal message the synthetic reserved-category probe
      produces, and the row the ordinary probe behind it still filed; (d) from
      live `findings triage`, the feedback heading with its rows and the
      `total`/`classified` footer line, excerpted — plus the `jq` path and value
      showing the same heading present in `triage --json`, not the document; (e)
      the diff of `docs/cli/findings.md:10`; and (f) the full-suite
      before-and-after counts. State the byte size of the
      pasted block in the task's own output so the next reader can check it.

## Phase 3: User Story 3 — Getting it out again hands over the evidence

### Tests for this story (write FIRST, must fail)

- [ ] T022 [US3] (spec US3-S1, FR-009) Read-only and idempotent test, in a new
      `tests/test_115_us3_draft_brief.py`: snapshot every `findings` and
      `finding_events` row, run `findings draft`, assert the snapshot is
      unchanged, then run it a second time and assert the brief is
      byte-identical. A queue-reading verb that mutates the queue cannot be run
      twice to see what it says.
- [ ] T023 [P] [US3] (spec US3-S1, FR-009, trap 2) Not-wrapped test: assert
      `draft` does not go through `factory/cli/doctor.py:353` — `_with_store`,
      which runs `_resolve_promoted_findings` — a write — before every verb it
      wraps. Assert by driving a store holding a promoted finding whose spec has
      landed and proving `draft` did not close it. `triage` faced the same
      decision and left its reasoning at `factory/cli/doctor.py:340-347`.
- [ ] T024 [P] [US3] (spec US3-S2, FR-010) Full-evidence test: file a finding,
      record it twice more across two distinct `seen_at` values, then assert the
      brief carries every stored column and every event returned by
      `factory/doctor/store.py:493` — `list_events`, asserting on
      `occurrences == 3` and on both dates. Those are what separate a passing
      thought from a standing complaint.
- [ ] T025 [P] [US3] (spec US3-S3, FR-011, trap 7) Contract-derivation test:
      assert the brief's section skeleton matches what
      `factory/doctor/scaffold.py:153` — `_build_spec_md_from_slots` emits —
      `## Functional Requirements` at level 2 and a `## Work Graph` fence with
      `implements:` on every node (`factory/doctor/scaffold.py:203-226`) — and
      that the brief names `ergane spec validate` as its acceptance test. Prove
      the derivation by changing the generator in a fixture and asserting the
      brief changes with it. A test that only checks the words are present passes
      against a hardcoded copy. Assert also that
      `factory/doctor/scaffold.py:321` — `_build_spec_md`, the sibling branch
      `factory/doctor/scaffold.py:50-58` selects and the one `promote` actually
      compiles through `derive_workgraph` at `factory/cli/doctor.py:566-577`,
      emits the same section skeleton: the brief reads one branch while the proof
      runs over the other, and nothing else holds the two to each other. Assert
      also that the brief names no section from
      `.specify/templates/spec-template.md` that the generator does not emit:
      that file has no `## Work Graph` at all, puts requirements at
      `.specify/templates/spec-template.md:88` under
      `.specify/templates/spec-template.md:81`, and still teaches
      `.specify/templates/spec-template.md:71` and
      `.specify/templates/spec-template.md:106`.
- [ ] T026 [P] [US3] (spec US3-S4, FR-012, trap 6) No-invocation test: with
      `LITELLM_PROXY_URL`, `LITELLM_MASTER_KEY`, `TEMPORAL_ADDRESS` and
      `TEMPORAL_NAMESPACE` unset and the socket constructor patched to raise, run
      `draft` and assert it exits 0, that nothing under `specs/` was created or
      modified, and that no subprocess was spawned. Assert on behaviour under a
      stripped environment, not on the absence of an import, which can be added
      back without failing it.

### Implementation for this story

- [ ] T027 [US3] (FR-009, FR-010, FR-011, FR-012, trap 2, trap 6, trap 7) Add the
      `draft` verb to `factory/cli/doctor.py:251` — `add_findings_parser` and its
      command function: read the named findings and their events, assemble one
      brief carrying every column and the full trail plus the trio contract
      derived from `factory/doctor/scaffold.py:27` — `scaffold_spec`, write it to
      a path resolved the way `factory/cli/doctor.py:65` — `_store_path` resolves
      the store, and print that path. Wire it outside `_with_store`. Register it
      before the metavar is computed, so US1's derived string picks it up with no
      second edit — if `draft` is missing from the usage line's brace list, T004's
      second assertion is what says so.
- [ ] T028 [US3] (FR-009) Add `ergane findings draft` to `docs/cli/findings.md` —
      one synopsis line beside the five at `docs/cli/findings.md:10-15` and one
      section, so the reference page US1 rewrote and US2 corrected stays true —
      and add it to the read-only verb list at `docs/cli/README.md:103`, because
      `draft` writes no row and that sentence is where a reader learns which
      verbs do not.

### Verification for this story

- [ ] T029 [US3] (spec US3-S1, spec US3-S2, spec US3-S3, spec US3-S4, trap 14)
      Paste, as committed evidence, **under 16 KiB total**, from the fixture
      finding T024 builds rather than from a live row — a `notes` field in this
      ledger runs to multiple KiB and FR-010 asks the brief to carry every column
      plus the whole trail, so a live brief is not a bounded document. Paste: the
      written brief for that fixture finding recorded three times, with its event
      trail visible; the store snapshot before and after showing no change; the
      `sha256` of the first and second invocations' briefs shown equal, rather
      than the second brief; the brief's section list beside the headings
      `factory/doctor/scaffold.py:153` — `_build_spec_md_from_slots` emits; the
      `docs/cli/README.md:103` line after the edit; and the full-suite
      before-and-after counts. State the byte size of the pasted block.

## Verification

- [ ] T030 The full gate command passes green.
- [ ] T031 The operator sequence in `plan.md` § *Verification the operator will
      run, independent of the gate* is executed end to end. Step 5 is the
      falsifiable test of this whole spec and no gate can run it: hand a real
      brief to a drafting session and read what comes back against what
      `ergane findings promote` alone would have produced. If the difference is
      small, the schedule this spec deferred stays deferred.

**One boundary no task here may blur**: no task invokes an agent, adds a Temporal
schedule, or migrates the store's schema. All three are named out of scope in
`spec.md`, and each has a specific cheaper-looking version that reintroduces what
the spec was written to avoid — a second node lifecycle (trap 6), an unattended
drafter writing specs nobody asked for, and a migration spent on a lane that has
not yet proved it is used (trap 3).
