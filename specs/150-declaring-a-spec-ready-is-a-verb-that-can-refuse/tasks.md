# Tasks: declaring a spec ready is a verb that can refuse

Read `plan.md` before starting. Five of its traps decide whether this spec is
worth landing at all. Trap 1 is the one no gate can catch: a frontmatter writer
that round-trips the block through `yaml.safe_load` — or that rebuilds the file
from `_split_frontmatter`'s two joined halves — produces a file that parses,
validates clean, and has deleted every provenance comment or the trailing
newline; edit the one line in the original text, never re-render the block.
Trap 2 is why the write is `os.replace` and not `Path.write_text`: the roadmap
re-reads the whole corpus every tick and a corpus that does not parse stops every
spec, not this one. Trap 4 is the story-killer in US4: there are already three
readings of readiness in this tree and a fourth is how this verb comes to permit
a flip the roadmap then refuses — inject the resolver US2 relocated, do not
write one. Trap 14 is the one that makes the whole spec hollow if missed:
`validate`'s `--target-repo` default is a path that does not exist on this host,
three of the twelve layers then skip, and the run prints "all pass" and exits 0 —
so the ready verb defaults that flag to the repository holding the specs root and
refuses at layer `validate_skipped` on any skipped layer. And trap 9 governs
every test here: a test that writes `state: ready` into a real directory under
`specs/` dispatches an epic within one tick, and no gate catches it. Build every
corpus under `tmp_path`.

The phases run in landing order — User Story 1, User Story 2, User Story 4, User
Story 3 — so the phase number and the story number do not match after Phase 2.
The story number in each heading is the one that matters: it is what cuts this
document into the slice a node is dispatched with. User Story 4 is the half of
the original User Story 2 that was split off when the pair was measured against
the diff bound; the numbers were not shuffled to make them sequential, because a
story number is never re-used for different work.

Traps 7 and 8 are the two reds a correct diff collects for reasons this spec is
not about: 133's fixture trios are frozen byte for byte against golden captures,
so copy one into `tmp_path` rather than editing it; and moving `ReadinessBasis`
out of `factory/cli/status.py` without re-binding the name there turns two landed
tests red. Trap 13 is the opposite — a red that is the point: US3-S5's test is red
on today's tree before this story adds a verb, because
`factory/cli/nouns/spec.py:114` — `_add_spec_parser` has omitted `new` since it
shipped. Trap 4 is the inverse of it, and Phase 2 is split so the difference is
impossible to miss: T011 is the red — the six names have one definition site and
it is the new one, false before the move and true after — while T012 sits under
its own **non-regression control** heading and is green throughout, because
`factory/roadmap/models.py:53` already imports `find_cycle` from
`factory.workgraph.models` and an assertion widened to "no import from
`factory.workgraph`" to force a first failure is red on arrival and stays red
after the story is correct. Assert on the two git-reading modules by name, and
leave the control green.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The change is bytes, computed before anything is written

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-003, trap 1) Build a `tmp_path`
      spec directory whose `spec.md` frontmatter carries `state: draft`, at least
      three `#` comment lines, a `depends_on_landed:` list and a `fixes:` list,
      and whose file ends in a trailing newline. Plan a change to `ready` and
      assert the returned value carries that path, `draft`, `ready`, and a text
      that is equal to the text read once the single `state:` line is removed
      from each. A diff that re-rendered the block from the parsed mapping fails
      on the comment lines and one that rebuilt the file from the splitter's two
      halves fails on the trailing newline, which is the whole purpose of writing
      the assertion this way rather than asserting a substring.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Hash the fixture's bytes, plan one
      change that is permitted and one that is refused, and assert the hash is
      unchanged after both. Planning is a read.
- [ ] T003 [P] [US1] (spec US1-S5, FR-004, FR-005, traps 11 and 12) Over one
      test, assert three refusals and their layers: a `spec.md` with no leading
      fence pair is refused at layer `frontmatter` naming the path; a `spec.md`
      declaring `state: landed` is refused at layer `transition` naming both
      states; and a request equal to the state already declared is refused at
      layer `transition` too. Assert no file was written in any of the three.
- [ ] T004 [US1] (spec US1-S3, FR-006, trap 3) Plan a change, rewrite `spec.md`
      underneath it, then apply. Assert the apply wrote nothing, returned a
      refusal naming the path and both digests, and that the file still holds the
      rewritten bytes. Not `[P]`: it drives plan and apply over one fixture the
      earlier tasks also build.
- [ ] T005 [US1] (spec US1-S4, FR-007, trap 2) Plan a change over an unmoved
      file, patch `os.replace` to raise, apply, and assert the spec file still
      holds its original bytes. A direct write onto the target path cannot pass
      this. Not `[P]`: same fixture.

### Implementation for this story

- [ ] T006 [US1] (FR-001) In a new module under `factory/spec/`, define the three
      frozen dataclasses: `SpecStateChange` (spec directory, path, declared state,
      requested state, the complete text the file would hold, the SHA-256 hex
      digest of the bytes it was computed against), `StateRefusal` (layer,
      message), and `SpecStatePlan` (spec directory, declared state, requested
      state, optional change, tuple of refusals, permitted exactly when there is a
      change and no refusal). Do not cite `factory/spec/` by line anywhere: the
      package is created by this spec's `depends_on_landed` edge and an anchor
      into it is stale today.
- [ ] T007 [US1] (FR-002, FR-003, FR-004, FR-005, traps 1, 11 and 12) Write the
      planning function. Use
      `factory/roadmap/models.py:240` — `_split_frontmatter` to establish that a
      fence pair exists and where the block ends, then find the `state:` line
      **in the original text** and replace that one line. Do not rebuild the file
      from that function's two return values: it returns `"\n".join(...)` halves,
      so a reconstruction drops the trailing newline and normalises CRLF. Never
      rebuild the block from the mapping
      `factory/roadmap/models.py:260` — `_parse_frontmatter` loads, which holds
      only the three keys of `factory/roadmap/models.py:117` and no comments.
      Implement the transition table row for row, including the catch-all: a
      requested state other than `ready` or `deferred` is refused at layer
      `transition`, so this function cannot become the attestation verb the spec
      was told not to build.
- [ ] T008 [US1] (FR-006, FR-007, traps 2 and 3) Write the apply function.
      Re-read, hash with `hashlib.sha256(...).hexdigest()` and treat an unreadable
      file as moved, following
      `factory/activities/verify_activities.py:621` — `_has_drifted` and its digest
      line at `factory/activities/verify_activities.py:628` — `_has_drifted`. On a
      match, write through a temporary file **inside the spec's own directory**
      followed by `os.replace`, copying
      `factory/registry.py:353` — `_write_document` and its `os.replace` at
      `factory/registry.py:359` — `_write_document`. A `Path.write_text` onto the
      target leaves a window in which
      `factory/roadmap/workflow.py:494` — `read_corpus_activity` reads a truncated
      file and stops the whole line.

### Verification for this story

- [ ] T009 [US1] Paste, as committed evidence, the `git diff` of one scratch spec
      before and after an applied change — it must show exactly one changed line —
      together with the refusal text an apply produces when the file moved between
      the plan and the apply.

## Phase 2: User Story 2 — The readiness resolver moves once, and both readers hold the same object

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1, FR-011, traps 4 and 8) Import each of the six
      relocated names — `_observed_landed_resolver`, `ReadinessBasis`,
      `_readiness_basis`, `_observed_landing`, `_repo_holding` and
      `_declared_story_keys` — from `factory.cli.status` and from its new home
      under `factory/spec/`, and assert the two are the same object for every one
      of the six. A copy rather than a move passes an equality assertion and fails
      this one. Assert in the same test that the story's diff edits neither
      `tests/test_both_verbs_agree_about_the_schedule.py` nor
      `tests/test_ergane_status.py`, both of which read those names today
      (`tests/test_both_verbs_agree_about_the_schedule.py:54`,
      `tests/test_ergane_status.py:1211`).
- [ ] T011 [P] [US2] (spec US2-S2, FR-011, FR-019, trap 4) Assert that the six
      names have exactly one definition site and that it is the new one. Read
      `factory/cli/status.py` with `ast` and assert its module body carries no
      `def` and no `class` statement for `ReadinessBasis`, `_readiness_basis`,
      `_observed_landed_resolver`, `_observed_landing`, `_repo_holding` or
      `_declared_story_keys` — only the import that re-binds them — and assert
      that `_readiness_basis.__module__` and
      `_observed_landed_resolver.__module__` each name the new module under
      `factory.spec`, which is the module FR-019 sends the ready planner to, so
      the resolver `factory/cli/status.py:292` injects into
      `factory/roadmap/models.py:570` — `compute_readiness` and the one the ready
      verb will inject are traced to one definition. Both halves are false
      against the tree this story starts from — `factory/cli/status.py:378` and
      `factory/cli/status.py:441` are `def` statements in that file today and
      both names report `factory.cli.status` — and true once the definitions have
      moved, which is the red this phase asks for.

### Non-regression control for this story

- [ ] T012 [P] [US2] (spec US2-S2, FR-011, trap 4) **This test is green on
      arrival, green after this story is correct, and that is exactly what it is
      for.** It is the control on trap 4's wrong move — a git read pushed down
      into the readiness computation — and its worth is that it never goes red
      for any other reason, so do not manufacture a failure out of it and do not
      move it into the phase above. Assert that
      `factory/roadmap/models.py:570` — `compute_readiness` still takes
      `landed_for` and `drifted_for` as parameters, by reading its signature with
      `inspect.signature`; and that no git read was added to
      `factory/roadmap/models.py`: no `subprocess` import, no import of
      `factory.workgraph.landed` and none of `factory.workgraph.worktree`, and no
      `["git", ...]` argv literal in its source. Read the imports with `ast`, not
      with a substring scan: `factory/roadmap/models.py:53` already carries
      `from factory.workgraph.models import find_cycle` — the corpus cycle
      detector `factory/roadmap/models.py:374` — `_cross_validate` calls at
      `factory/roadmap/models.py:400` — so widening this assertion to "no import
      from `factory.workgraph`" to make it fail first is red on arrival, is still
      red when this story is correct, and is only made green by deleting an
      import three other draft specs depend on. That import is out of scope and
      must survive. For the same reason do not assert on the substring "git":
      this module's docstrings say the word four times today.

### Implementation for this story

- [ ] T013 [US2] (FR-011, traps 4 and 8) Move
      `factory/cli/status.py:247` — `ReadinessBasis`,
      `factory/cli/status.py:378` — `_readiness_basis`,
      `factory/cli/status.py:441` — `_observed_landed_resolver`,
      `factory/cli/status.py:469` — `_observed_landing` and the two helpers they
      read — `factory/cli/status.py:425` — `_repo_holding` and
      `factory/cli/status.py:491` — `_declared_story_keys` — into
      `factory/spec/`. Carry with them the two module-level imports those bodies
      read, as imports rather than as definitions: `landing_branch` at
      `factory/cli/status.py:110` and `_landing_head` at
      `factory/cli/status.py:106`, which is an alias of
      `factory.workgraph.landed._resolve_default_head` — there is no local
      `def _landing_head` to find, and moving exactly the six named symbols
      without it is a `NameError` and a hunt. Then import every moved name back
      into `factory/cli/status.py` **under the name it has now**, so
      `factory/cli/status.py:264` and the call at `factory/cli/status.py:292`
      change not at all. `tests/test_both_verbs_agree_about_the_schedule.py:54`
      imports `ReadinessBasis` from the status module and
      `tests/test_ergane_status.py:1211` —
      `test_the_queue_header_names_the_readiness_basis` asserts the header that
      carries it; both must pass unedited.

### Verification for this story

- [ ] T014 [US2] Paste, as committed evidence, two artifacts: `git diff --stat`
      for this story, which must show `factory/cli/status.py` losing about a
      hundred and thirty lines and no file under `tests/` that this story did not
      create being edited; and the transcript of a Python session importing each
      of the six names from `factory.cli.status` and from its new home and
      printing the identity comparison for each pair.

## Phase 3: User Story 4 — Readying refuses exactly what the roadmap would refuse

### Tests for this story (write FIRST, must fail)

- [ ] T015 [P] [US4] (spec US4-S1, FR-008, FR-019, traps 7 and 14) Copy 133's
      **clean** fixture trio into a `tmp_path` corpus — do not edit the committed
      one, whose bytes 133's golden captures freeze — beside a second spec
      directory declaring `state: landed` that the first names in
      `depends_on_landed`. Drive the plan against a target repository under which
      the copy's citations resolve, so **no layer skips**: a run in which one did
      is refused by FR-017 and this test would be asserting the wrong thing.
      Assert the plan is permitted, carries a change to `ready`, and carries the
      readiness basis the relocated resolver reported.
- [ ] T016 [P] [US4] (spec US4-S2, FR-009, traps 6, 7 and 10) Copy 133's
      **defective** trio into a `tmp_path` corpus. Plan a ready change; separately
      call the validation library form over the same directory; assert the plan
      carries no change and that its refusals at layer `validate` are, in the
      report's order, one per refusal in that report, each message equal to that
      refusal's own layer name, `": "`, and that refusal's own message. Build the
      expected sequence by rendering the report's refusals, never by restating
      them. A hand-written summary string cannot pass this, and neither can a
      group-by-layer collapse, which is why the comparison is element by element
      rather than a count.
- [ ] T017 [P] [US4] (spec US4-S3, FR-010, traps 4 and 7) Build a `tmp_path`
      corpus of two specs where the first declares `depends_on_landed` on the
      second and the second declares `state: draft`. Assert the plan carries no
      change and a refusal at layer `depends_on_landed` naming the second
      directory and the state it declares — and, in the same test, assert the set
      of directories those refusals name equals the blockers
      `factory/roadmap/models.py:570` — `compute_readiness` reports for that spec
      over the same corpus. A second implementation of the edge rule cannot pass
      both halves.
- [ ] T018 [P] [US4] (spec US4-S4, FR-012) Over **one** spec directory that fails
      both preconditions — a trio the validation report refuses and an edge onto a
      spec declaring `draft` — plan ready and plan defer, and assert ready is
      refused while defer is permitted and carries a change to `deferred`. This is
      the test that fails if the preconditions were wired into the shared planning
      function of T007 instead of into the ready planner.
- [ ] T019 [P] [US4] (spec US4-S5, FR-017, trap 14) Over the same corpus T015
      builds, compute two ready plans: one against the readable target repository
      and one against a path that is not a readable directory. Assert the first is
      permitted and the second carries no change and one refusal at layer
      `validate_skipped` for each of `anchor_resolution`, `symbol_anchors` and
      `evidence`, each message equal to that layer's own name, `": "`, and the
      reason the validation report gives for not running it. Read the skipped set
      from the report's own skipped member; a planner that inspects only
      `report.refusals` passes the first half and fails the second.
- [ ] T020 [P] [US4] (spec US4-S6, FR-018, trap 15) Build a `tmp_path` corpus
      holding the draft spec being readied beside one sibling whose frontmatter
      carries a key outside the closed set at
      `factory/roadmap/models.py:117`. Assert the ready planner **returns** a plan
      refused at layer `corpus` carrying each fault
      `factory/roadmap/models.py:411` — `read_roadmap` names, and that no
      exception escapes; assert in the same test that a defer plan over the same
      spec is still permitted. A planner that lets `RoadmapError` through fails
      with an error, not an assertion.

### Implementation for this story

- [ ] T021 [US4] (FR-008, FR-009, FR-017, traps 6, 10 and 14) Add the ready
      planner and the defer planner as the two exported entry points, each
      delegating the transition table to T007's function. In the ready planner,
      obtain the validation report by calling the library form 133 exports over
      the same spec directory, target repo and specs root, then build **one
      `StateRefusal` per refusal in that report** at layer `validate`, whose
      message is that refusal's own layer name, `": "`, and its message — not one
      per refusing layer — and one `StateRefusal` per **skipped** layer at layer
      `validate_skipped`, rendered the same way from the layer's name and the
      reason the report gives. One rendering function for both, so the operator's
      line and a program's field cannot drift. Do **not** build an argv list the
      way `factory/cli/install.py:1078` — `_spec_validate_argv` does, and do not
      re-compose the layers.
- [ ] T022 [US4] (FR-010, FR-018, FR-019, traps 4 and 15) Read the corpus with
      `factory/roadmap/models.py:411` — `read_roadmap` inside a guard that turns
      each fault it names into a `StateRefusal` at layer `corpus` and returns a
      refused plan rather than propagating the exception. On a corpus that parses,
      call the relocated `_readiness_basis` for the basis and the resolver it
      chose, pass that resolver to
      `factory/roadmap/models.py:570` — `compute_readiness` as `landed_for`, and
      turn each blocker into a `StateRefusal` at layer `depends_on_landed` naming
      the directory and the state that spec's own frontmatter declares. Carry the
      basis on the plan. Write no resolver of your own, and add no git read inside
      `compute_readiness`, whose docstring at
      `factory/roadmap/models.py:587` — `compute_readiness` says why.
- [ ] T023 [US4] (FR-012) Make the defer planner consult neither precondition, nor
      the skipped layers, nor the corpus — one call into T007's function and
      nothing else. Parking a spec is always safe; a defer that could be refused
      by a broken trio, an unreadable target repo or a broken sibling is a defer
      that cannot park a broken spec.

### Verification for this story

- [ ] T024 [US4] Paste, as committed evidence, three refusal reports for one
      scratch spec — the edge refusal naming the unmet directory and the state it
      declares, the validate refusal carrying a layer's own name and message, and
      the `validate_skipped` refusal naming the three layers an unreadable target
      repository leaves unrun — beside the `ergane spec validate` output for the
      same directory run with the same `--target-repo` and `--specs-root`, so the
      two texts can be read against each other.

## Phase 4: User Story 3 — The operator reaches it through a verb that shows before it writes

### Tests for this story (write FIRST, must fail)

- [ ] T025 [P] [US3] (spec US3-S1, FR-014, trap 9) Over a `tmp_path` corpus —
      never `specs/` — invoke the ready verb with `--dry-run` on a spec the
      library form permits. Assert exit 0, that the output carries the `state:`
      line it would write and the digest the change was computed against, and that
      the file's hash is unchanged.
- [ ] T026 [P] [US3] (spec US3-S2, FR-013, trap 1) Invoke the ready verb without
      `--dry-run` on the same spec. Assert the frontmatter declares `ready`, that
      every comment line and both list keys are byte-identical to before, and that
      the output names the transition.
- [ ] T027 [P] [US3] (spec US3-S3, FR-016) Invoke the ready verb on a spec the
      library form refuses. Assert the user-error exit code, one output line per
      refusal carrying that refusal's layer and its message, and an unchanged
      file.
- [ ] T028 [P] [US3] (spec US3-S4, FR-015) Invoke the same refused case with
      `--json`, load the printed document, and assert it carries the declared
      state, the requested state, each refusal with its layer and message, and a
      flag stating nothing was written.
- [ ] T029 [P] [US3] (spec US3-S5, FR-016, trap 13) Build the `spec` parser, read
      its registered subcommand names, and assert the set includes `ready` and
      `defer` **and** that the module docstring
      (`factory/cli/nouns/spec.py:1`), the parser help
      (`factory/cli/nouns/spec.py:114` — `_add_spec_parser`) and the summary
      (`factory/cli/nouns/spec.py:236`) each name every registered subcommand.
      Derive the expected set from the parser; do not restate it. This test is red
      on today's tree before a verb is added, because the help string omits `new`.
- [ ] T030 [P] [US3] (spec US3-S6, FR-013, trap 14) Over a `tmp_path` corpus whose
      specs root sits inside a git repository, invoke the ready verb with no
      `--target-repo`. Patch the ready planner, read the target repository it was
      called with, and assert it equals the repository holding the specs root —
      the relocated `_repo_holding`. Assert separately that the subparser's own
      default for the flag is not a literal path. A verb that copied `validate`'s
      `/srv/factory/targets/short-links` fails both halves.

### Implementation for this story

- [ ] T031 [US3] (FR-013, trap 14) Register two subparsers beside the five
      `factory/cli/nouns/spec.py:113` — `_add_spec_parser` already adds: after the
      `landed` block that begins at `factory/cli/nouns/spec.py:216` and before the
      `NOUN` registration at `factory/cli/nouns/spec.py:236`. Each takes
      `spec_dir`, `--dry-run` and `--json`; `ready` also takes `--specs-root` with
      the default `factory/cli/nouns/spec.py:134` gives `validate` and
      `--target-repo` defaulting to the repository holding that specs root
      (the relocated `_repo_holding`), **not** to the literal path `validate`
      carries. Resolve that default in the command function rather than in
      `add_argument`, since it is a function of `--specs-root`; when no repository
      holds the specs root and the flag was not given, refuse naming that. Each
      subparser ends in `set_defaults(run=...)`.
- [ ] T032 [US3] (FR-013, FR-014, FR-016) Write the two command functions as thin
      wrappers: call the planner, render the plan, and unless `--dry-run` call the
      apply function. No precondition logic may appear in either function — every
      decision they render was made in US4. A plan carrying refusals prints one
      line per refusal carrying its layer and its message and returns the
      user-error code, following how the other verbs in this module raise through
      `OperatorError`.
- [ ] T033 [US3] (FR-015) Serialise the plan, or the applied result, as one
      document behind `--json`, carrying the declared state, the requested state,
      the refusals with their layers and messages, and whether anything was
      written.
- [ ] T034 [US3] (FR-016, trap 13) Correct all three verb-list strings —
      `factory/cli/nouns/spec.py:1`,
      `factory/cli/nouns/spec.py:114` — `_add_spec_parser` and
      `factory/cli/nouns/spec.py:236` — so each names every registered
      subcommand. The help string is missing `new` before this story starts;
      adding the two new verbs and leaving that omission keeps T029 red.

### Verification for this story

- [ ] T035 [US3] Paste, as committed evidence, four terminal transcripts over a
      scratch corpus: the ready verb with `--dry-run` on a permitted spec, the
      same verb applying it, the same verb refusing a spec with an unmet edge, and
      the same verb refusing when `--target-repo` names a path that does not exist
      — with the file's `git diff` after the applied run showing one changed line.

## Verification

- [ ] T036 The full gate command passes green.
- [ ] T037 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end on a **scratch** specs root. Step 9 — pointing a
      roadmap at that corpus and confirming that a spec the verb refused is not
      dispatched while one it readied is — is the falsifiable test of this whole
      spec, because it is the act the spec exists to make refusable. It is also
      the step trap 9 forbids running against `specs/`.
