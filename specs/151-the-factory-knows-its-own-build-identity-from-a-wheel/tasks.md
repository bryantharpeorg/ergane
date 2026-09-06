# Tasks: the factory knows its own build identity from a wheel

Read `plan.md` before starting. Eight of its traps will each waste a whole story
if you meet them as a failure instead of as declared scope. Trap 1: the source
document names a **dead** call site — `factory/doctor/cli.py:242` — `_run_probe`
is reached by nothing the CLI runs, and editing it changes no behaviour. Trap 2:
anchoring the probe's git read on the package directory without moving the
pathspec turns one silent failure into a different silent failure. Trap 6:
changing what `factory/worker.py:220` — `_worker_revision` returns converts
082's deliberate refusal into a bad build id, and nothing here would catch it.
Trap 10: FR-006 forbids a second `importlib.metadata.version` call and **blesses**
the one `importlib.metadata.distribution` call FR-003's stamp needs — the two are
not the same lookup, and treating them as one is how a clock-based stamp gets
written. Trap 12: the host's own installed `ergane-cli` distribution answers
from inside US1's fixture, so the fixture must write a synthetic one under
`tmp_path` — otherwise US1-S1 passes for an ambient reason and US1-S2's control
rewrites a metadata file inside the gate's own virtual environment. Trap 13: eight
landed tests in **two** modules drive the skew path end to end — seven in
`tests/test_ergane_build_status_refusal.py` and one in
`tests/test_ergane_build.py` — and three assertions across them encode the exact
sentence FR-018 deletes; they go red when US4 lands and the cheapest green
un-does the story. Trap 14: renaming the snapshot's fields does not rename the
sentence the operator reads, and a finding that still says `commit None` is the
same lie one layer out. Trap 15: a worker running the code that was there before
this story sends a bare revision and no identity — every call until it is
restarted — and reading that as "resolved nothing" reprints the permanent
warning this spec exists to end.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — One resolver answers "what code is this"

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, US1-S2, FR-001, FR-003, FR-004, traps 4, 9, 11
      and 12) Build the installed-layout fixture: copy the `factory` package
      into `tmp_path/site-packages/factory` with
      `ignore=shutil.ignore_patterns("__pycache__")`, which places it outside
      every git work tree, **and write a synthetic
      `tmp_path/site-packages/ergane_cli-<version>.dist-info/METADATA`** beside
      it, then run a probe script in a subprocess with `PYTHONPATH` naming that
      directory. The synthetic dist-info is not optional decoration: the
      subprocess still has the interpreter's own `site-packages` on `sys.path`,
      where the host's real `ergane_cli-0.5.0.dist-info` lives, and
      `importlib.metadata` returns the first match on `sys.path` — `PYTHONPATH`
      precedes `site-packages`, so the synthetic one wins (trap 12, measured).
      Copy the shape of `tests/test_installed_layout.py:72` — `_installed_layout` and
      `tests/test_installed_layout.py:93` — `_run_probe`,
      including its discipline of asserting *which* `factory` was imported
      before asserting anything else. Assert **first** that the resolved
      distribution's own location lies under `tmp_path`; without that, a
      resolver that never looks at the package directory and simply calls
      `importlib.metadata` satisfies this test. Then assert the resolved
      identity names the distribution as its source and carries
      `cli_version()`'s version; and in the **same** test assert the identity
      resolved from the checkout names git and carries the checkout's short
      revision. Then assert what the stamp actually is (US1-S2): it equals the
      modification time of the resolved distribution's own metadata file, and
      the control proves the property FR-003 asks for — rewriting **the
      synthetic** metadata file moves the stamp, while touching a file inside
      the copied package leaves it where it was. Set the rewritten file's
      modification time explicitly (`os.utime` with a time at least one second
      later) rather than relying on the write's own clock: the consumer compares
      whole seconds (`factory/doctor/probes.py:99`), so a rewrite inside one
      wall-clock second leaves the stamp equal and the control goes red for a
      reason that has nothing to do with FR-003 — and the cheapest green for
      that is to weaken the assertion to "non-null stamp", which is the very
      assertion trap 11 says passes for `datetime.now()`. Rewrite nothing until the
      location assertion has passed: the file the control edits must be the one
      under `tmp_path` and never the installed distribution the gate itself runs
      from. A "non-null stamp" assertion alone passes for `datetime.now()` and
      for the module's own mtime, which are the two wrong moves trap 11 names.
      Not `[P]`: every other test in this phase builds on this fixture.
- [ ] T002 [P] [US1] (spec US1-S3, FR-002, trap 2) Initialise two throwaway git
      repositories under `tmp_path`, one of them holding a copy of the package.
      Resolve the identity with the process working directory set to the
      **other** repository, and assert the returned revision and stamp are the
      package's repository's and not the working directory's — asserting first
      that the two repositories report different values, so the test cannot pass
      by both being equal.
- [ ] T003 [P] [US1] (spec US1-S4, FR-005) Using the T001 fixture with the
      distribution lookup made to fail, assert the identity reports the unknown
      source and that its reason string names **both** attempts — the git read
      and the distribution lookup — and why each failed. Assert on the substrings
      for each attempt, not on the whole sentence.
- [ ] T004 [P] [US1] (spec US1-S5, FR-006, trap 10) Assert the resolver's version
      equals `factory/supervision/engine_identity.py:38` — `cli_version`'s
      return, and assert that exactly one call site in
      `factory/supervision/engine_identity.py` resolves to `importlib.metadata`'s
      `version`. Count it over the module's parsed syntax tree (`ast`), following
      the `from importlib.metadata import version` binding at
      `factory/supervision/engine_identity.py:45` to the call at
      `factory/supervision/engine_identity.py:47`. Do **not** count occurrences
      of the literal text `importlib.metadata.version`: that string appears
      **zero** times in this module, a text count therefore returns zero, and the
      cheapest way to make it return one is to add the dotted call FR-006 forbids
      — which would make this test the cause of the defect it exists to prevent.
      The count is scoped to this module: the single
      `importlib.metadata.distribution` call FR-003 requires for the stamp is
      expected here and is not a version lookup, and
      `factory/supervision/container_project.py:157` binds the same lookup for
      the engine image, is pre-existing, and is out of scope — do not touch it
      and do not widen the assertion to the tree. The version half is what stops
      a second implementation of the question this spec exists to collapse.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-004) Add the frozen identity dataclass to
      `factory/supervision/engine_identity.py` beside
      `factory/supervision/engine_identity.py:38` — `cli_version`: a version, a
      stamp timestamp, an optional revision, a source name and an optional
      reason. Keep the module standard-library-only in spirit — its docstring
      says it is imported on the `build start` path and must not grow heavier
      dependencies.
- [ ] T006 [US1] (FR-002, FR-006, traps 2 and 10) Add the resolver. Anchor the
      git read on the imported package's own directory with an explicit `cwd=`,
      and move the pathspec with it — `-- factory/` relative to the package
      directory matches nothing, which is the failure trap 2 describes. Take the
      version from `cli_version()`, never from a second
      `importlib.metadata.version` call.
- [ ] T007 [US1] (FR-003, traps 10 and 11) Add the distribution arm: resolve the
      installed distribution with **one** `importlib.metadata.distribution` call
      — the call trap 10 blesses, because `cli_version()` returns a string and
      cannot reach the distribution's files — and take the stamp from that
      distribution's own on-disk metadata, so a reinstall of the same version
      moves it. Not the clock, and not the imported module's mtime — both make
      every worker look fresh and disable `ops/stale-worker` a second way.
- [ ] T008 [US1] (FR-005) Add the unknown arm: when neither source answers,
      report the unknown source with a reason naming both attempts and why each
      failed. This is the only row of the spec's truth table in which anything is
      still lost, and the message is what changes there.

### Verification for this story

- [ ] T009 [US1] Paste, as committed evidence, the resolved identity from all
      three rows of the truth table — the checkout, the copied package outside
      every work tree, and the copy with no resolvable distribution — each as the
      literal output of the probe script, with the command that produced it. Add
      one further pasted pair for US1-S2: the stamp before and after the
      distribution's metadata file is rewritten, with the command that rewrote
      it.

## Phase 2: User Story 2 — The stale-worker probe returns a verdict instead of a permanent skip

### Tests for this story (write FIRST, must fail)

- [ ] T010 [US2] (spec US2-S1, FR-007, traps 7 and 9) Drive
      `factory/doctor/probes.py:328` — `StaleWorkerProbe.gather` in the
      installed-layout fixture from T001 and assert it returns a snapshot
      carrying a stamp. **This is the test that matters**: every existing test in
      `tests/test_doctor_probes.py:86` — `TestStaleWorkerProbe` constructs a
      snapshot by hand and calls `evaluate`, and all four pass today on a host
      where the probe skips permanently. Include the control that the fixture is
      an honest no-git layout: run `git log -1 --format=%ct %H -- factory/` in it
      and assert it yields no usable line, so the gather cannot be answering for
      an ambient reason. Do **not** write the control as a call on
      `_newest_factory_commit`: T015 removes that function, so such a control
      either forces a dead helper to be kept alive or cannot be read in the diff.
- [ ] T011 [P] [US2] (spec US2-S2, FR-008, trap 14) Assert `evaluate` still
      files `ops/stale-worker` for a worker whose start time precedes the stamp,
      and that its **key**, its **category** and its `Severity.CRITICAL` are
      today's. Those three are what must not drift while the fields around them
      are renamed; do **not** pin the summary or the refs field-for-field. FR-011
      has to change both of those, and a test that freezes today's
      "before newest factory/ commit …" sentence or its `git/` ref prefixes is
      a test that forbids the fix T014 is written to prove.
- [ ] T012 [P] [US2] (spec US2-S3, FR-009, traps 3 and 9) Run the probe driver
      over a registry containing the stale-worker probe **in the T001
      installed-layout fixture** — not merely with the working directory changed
      — and assert it returns the success exit code. Carry the same honest-layout
      control T010 carries: `git log -1 --format=%ct %H -- factory/` run in that
      layout yields no usable line. Both are load-bearing. A node worktree is
      itself a git checkout, so once FR-002 anchors the read on the package
      directory a test that only changes directory goes green with FR-003's
      distribution fallback entirely unimplemented, and neither the gate nor the
      judge can tell that from the diff. That exit-code assertion is
      the whole of the committed test. The other half of US2-S3 — that
      `factory/cli/doctor.py` is untouched — is discharged by the diff's own file
      list, which is what the scenario asks the judge to read; do **not** write a
      test that shells `git diff` to check it, because a node worktree has no
      stable base to diff against. The exit code clears because nothing skipped,
      not because the arm at
      `factory/cli/doctor.py:206` — `_run_all_probes` learned about this spec.
- [ ] T013 [P] [US2] (spec US2-S4, FR-010) With neither a git answer nor
      resolvable distribution metadata, assert the probe still skips and that the
      skip's message names **both** attempts rather than naming git alone.
      `factory/doctor/probes.py:34` — `ServiceNotAnswering` renders the service
      token and the reason, and
      `factory/cli/doctor.py:215` — `_run_one_probe` prints both, so assert on
      the line the operator would read.
- [ ] T014 [P] [US2] (spec US2-S5, FR-011, trap 14) Construct the snapshot from
      distribution-sourced values — a stamp, no revision — and assert two
      things. First, that no field whose name claims a git commit is used:
      today's names on `factory/doctor/probes.py:94` — `WorkerSnapshot` are
      `newest_factory_commit_timestamp` and `newest_factory_commit_sha`, and a
      distribution stamp carried under either of those is a lie the next reader
      will believe. Second, call `evaluate` on that snapshot and assert the
      `ops/stale-worker` finding it returns claims no commit either: its summary
      names the build stamp and the source it came from and contains no
      `factory/` commit claim, and none of its refs begins `git/`. Without the
      second half the rename is cosmetic — today's summary at
      `factory/doctor/probes.py:366` and refs at
      `factory/doctor/probes.py:374` and `factory/doctor/probes.py:376` would
      render `commit None` and `git/commit:None` on the one install shape this
      spec exists to serve, in the CRITICAL finding the operator reads at step 3
      of the plan's verification sequence.

### Implementation for this story

- [ ] T015 [US2] (FR-007, FR-011, trap 2) Replace
      `factory/doctor/probes.py:161` — `_newest_factory_commit` with a call on
      US1's resolver, and rename the two snapshot fields on
      `factory/doctor/probes.py:94` — `WorkerSnapshot` to name a stamp of the
      code this process imported. It has exactly one consumer — `gather` — so
      nothing outside this module moves.
- [ ] T016 [US2] (FR-008) Follow the renamed fields through
      `factory/doctor/probes.py:345` — `StaleWorkerProbe.evaluate`, keeping the
      key `ops/stale-worker`, the `Severity.CRITICAL`, and the incident-class
      note at `factory/doctor/probes.py:378` — `StaleWorkerProbe.evaluate` as
      they are. The comparison stays what it is.
- [ ] T017 [US2] (FR-010) Raise `ServiceNotAnswering` only when the identity is
      unknown, with a reason naming both attempts. The service token should stop
      saying `git` when git is one of two things that were tried.
- [ ] T018 [US2] (FR-009, traps 1 and 3) Confirm by reading that neither
      `factory/cli/doctor.py` nor `factory/doctor/cli.py` needed an edit. **If
      either did, the design is wrong**: the first arm at
      `factory/cli/doctor.py:206` — `_run_all_probes` clears because nothing
      skipped, and `factory/doctor/cli.py:242` — `_run_probe` is on no live path
      at all.

### Verification for this story

- [ ] T019 [US2] Paste, as committed evidence, the exit code and stderr of the
      probe driver run in the installed layout before and after the change — the
      first skipping and returning the transport code, the second returning the
      success code with no skip line — captured with the command that produced
      each.

## Phase 3: User Story 3 — `ergane --version` names a build instead of printing `(unknown)`

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S1, FR-013) Given an identity whose source is git
      and which carries a revision, assert the first line rendered by
      `factory/cli/main.py:132` — `_version_text` is byte-identical to today's
      for the same version and revision, against a literal expected string. A
      checkout must not notice this story.
- [ ] T021 [P] [US3] (spec US3-S2, FR-012) Given an identity whose source is the
      installed distribution, assert the first line names the version and the
      build stamp and contains no `(unknown)` parenthetical. Assert the absence
      of the literal `(unknown)`, not merely the presence of the version.
- [ ] T022 [P] [US3] (spec US3-S3, FR-014) Given an identity that could not be
      resolved, assert `_version_text` still returns its three lines without
      raising, with no control plane supplied. 048-US4's comment above the
      endpoint block says why: this is the command run to find out what you have,
      so a broken host must still get an answer. Then assert US3-S3's second
      clause, which is FR-014's second half and which nothing else in this phase
      decides: the rendered path resolves exactly the endpoints it resolves
      today and no more. Count the calls — `resolve_temporal_target` at
      `factory/cli/main.py:152` and `resolve_proxy_url` at
      `factory/cli/main.py:158`, one each — with counting stand-ins, and assert
      the resolver added no third resolution. A criterion no task produces
      evidence for is decided by nobody.

### Implementation for this story

- [ ] T023 [US3] (FR-012, FR-013, FR-014) Replace the git block at
      `factory/cli/main.py:136-144` with a call on US1's resolver and render the
      parenthetical at `factory/cli/main.py:165` — `_version_text` from the
      identity: the revision when there is one, the build stamp and its source
      when there is not. The range is `136-144`, not `136-143`: line 143 is
      `except Exception:` and 144 is the `revision = "unknown"` fallback, and
      replacing only through 143 leaves that assignment orphaned. The resolver
      must not raise into this function.

### Verification for this story

- [ ] T024 [US3] Paste, as committed evidence, the full output of
      `ergane --version` from the checkout and from a package copy outside every
      git work tree, side by side, with the command that produced each.

## Phase 4: User Story 4 — The skew check compares what both sides can actually report

### Tests for this story (write FIRST, must fail)

- [ ] T025 [P] [US4] (spec US4-S1, US4-S6, FR-016, FR-019, trap 8) Given a worker
      and a CLI that both report no revision and the same version, assert
      `factory/cli/nouns/build.py:986` — `_skew_notice` returns nothing. This is
      the case that fires on **every** call today — the operator-facing key in
      the `fixes:` block is exactly this sentence, printed on every reading of
      061's node states. In the same module assert US4-S6: parsing
      `factory/cli/nouns/build.py` finds no subprocess call carrying a
      `git rev-parse` argument list. Assert on the **invocation**, not on the
      literal text: the seam comment at `factory/cli/nouns/build.py:969` also
      contains that string, so a text search fails an otherwise correct
      implementation — if T033 leaves the comment in place, rewrite the comment
      with the code it describes. Also assert the package-level seam at
      `factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests` still
      overrides what the status command reads for the CLI side.
- [ ] T026 [P] [US4] (spec US4-S2, FR-017) Given both sides reporting no revision
      and **different** versions, assert the notice warns and names both
      versions.
- [ ] T027 [P] [US4] (spec US4-S3, FR-017) Given two revisions that differ,
      assert the warning is byte-identical to today's, against a literal expected
      string. That is the case the check was built for and operators read it in
      runbooks.
- [ ] T028 [P] [US4] (spec US4-S4, FR-018, trap 13) Given one side that resolved
      nothing at all, assert the notice names which side and the reason its
      identity carried, rather than today's fixed sentence about the worker
      predating the check or not being a git checkout. **Then rewrite the three
      landed assertions that encode that sentence, in two modules.** They are
      `assert "worker revision is unknown" in result.stderr.lower()` at
      `tests/test_ergane_build_status_refusal.py:474`, inside
      `tests/test_ergane_build_status_refusal.py:459` — `test_skew_degrades_when_worker_revision_is_unknown`;
      `assert "unknown" in notice.lower()` at
      `tests/test_ergane_build_status_refusal.py:497`, inside
      `tests/test_ergane_build_status_refusal.py:478` — `test_skew_degrades_in_json_when_worker_revision_is_unknown`; and
      `assert "unknown" in result.json["skew_notice"].lower()` at
      `tests/test_ergane_build.py:812`, inside
      `tests/test_ergane_build.py:790` — `test_status_json_is_the_query_result_verbatim`. The third one is in a
      module no earlier draft named: it drives the command through a live
      Temporal environment over a worker deliberately built without the revision
      interceptor (`tests/test_ergane_build.py:631` — `build_worker_for_test`),
      so `worker_revision` is `None` there
      (`tests/test_ergane_build.py:810`) and the new identity field is absent
      too — FR-018's row exactly. All three go red when T033 lands; making them
      green again by preserving today's sentence satisfies every new test in this
      phase and silently un-does FR-018. The five other landed skew tests —
      `tests/test_ergane_build_status_refusal.py:375` — `test_skew_is_visible_when_worker_revision_differs`,
      `tests/test_ergane_build_status_refusal.py:395` — `test_skew_is_visible_in_json_when_worker_revision_differs`,
      `tests/test_ergane_build_status_refusal.py:419` — `test_skew_is_silent_when_revisions_match`,
      `tests/test_ergane_build_status_refusal.py:440` — `test_skew_is_silent_in_json_when_revisions_match` and
      `tests/test_ergane_build_status_refusal.py:501` — `test_worker_revision_is_recorded_once_and_carried_not_recomputed`, whose
      `assert WORKER_REVISION_A in result.stderr` at
      `tests/test_ergane_build_status_refusal.py:540` reads the same warning
      through `_query_status` — are FR-017's own regression: their assertions
      stay byte-identical, and they stay that way only because FR-021 keeps a
      bare `worker_revision` a revision-only side. All eight move to whatever
      argument shape T033 gives `_skew_notice`, so read all eight before
      changing the signature.
- [ ] T029 [P] [US4] (spec US4-S7, US4-S8, FR-020, FR-021, trap 15) Given one
      side whose identity is git-sourced and carries a revision and one whose
      identity is
      distribution-sourced and carries a version and a stamp but no revision,
      both having resolved and both reporting the same version, assert the notice
      warns and names both sources and both values — for **both** orderings:
      worker git with CLI distribution, and the reverse. This is the mixed row of
      the comparison table in `spec.md` § "The rule this spec is asking for", it
      is neither FR-016's row (both sides without a revision and the same
      version) nor FR-018's (a side that resolved nothing), and nothing else in
      this phase constrains it. It is also the shape a CLI run from the checkout
      against a packaged worker actually has, which is what the operator checks
      at `plan.md` § "Verification the operator will run" step 4 — leave it
      undecided and that step and this story can disagree.
      Then assert US4-S8, the other row this task owns: build a status document
      with a `worker_revision` and **no** identity field — the shape
      `tests/test_ergane_build_status_refusal.py:309` — `_query_document`
      produces today, and the shape every worker sends until it is restarted —
      and assert all three sub-cases FR-021 decides. Equal revisions with a
      revision-carrying CLI side: no notice. Differing revisions: today's
      byte-identical warning. A CLI side carrying a version but no revision: no
      notice, **not** FR-018's unreadable-side sentence. This is the row that
      decides whether the five landed tests T028 leaves byte-identical stay
      green, and getting it wrong reprints the operator key's permanent warning
      on every un-restarted worker while every other test in this phase passes.
- [ ] T030 [US4] (spec US4-S5, FR-015, trap 6) Assert the value carried in
      `worker_revision` is unchanged and that
      `factory/versioning.py:94` — `resolve_deployment_version` still raises
      `factory/versioning.py:60` — `VersioningRefused` when the revision is
      `None` under engaged versioning. In the same test, assert an `EpicInput`
      built without the new field is accepted and reports the default. Not `[P]`:
      it drives the worker, the versioning module and the payload over one
      fixture.

### Implementation for this story

- [ ] T031 [US4] (FR-015, trap 6) Capture the worker's build identity beside
      `factory/worker.py:240` and carry it into the dispatch payload on the
      **existing** `replace(...)` call at `factory/worker.py:327`, inside the
      guard at `factory/worker.py:326` — not on a second `replace` and not
      outside that guard, so the revision and the identity are written together
      or not at all. The CLI never sets `worker_revision`, so the guard is true
      on every dispatch. The new field on
      `factory/workgraph/workflow.py:583` — `EpicInput` is defaulted. Leave
      `factory/worker.py:220` — `_worker_revision` exactly as it is: 082 refuses
      a `None` revision on purpose.
- [ ] T032 [US4] (FR-015) Record it in
      `factory/workgraph/workflow.py:933` — `EpicWorkflow.run` and return it on
      `factory/workgraph/workflow.py:689` — `EpicStatus` from
      `factory/workgraph/workflow.py:910` — `EpicWorkflow.epic_status`, following
      how `worker_revision` already travels those four places. Defaulted, so a
      payload written before this story is accepted unchanged.
- [ ] T033 [US4] (FR-016, FR-017, FR-018, FR-020, FR-021, trap 15) Rewrite
      `factory/cli/nouns/build.py:986` — `_skew_notice` to take both sides'
      identities: silent when they agree, warning when they disagree by revision
      (text unchanged) or by version, warning and naming both sources when only
      one side carries a revision, and naming the unreadable side and its reason
      when a comparison cannot be made at all. Keep the worker's bare
      `worker_revision` as an input, not only the identity: a payload that
      carries a revision and no identity is a revision-only side and must be
      compared by revision or stay silent (FR-021). Treating a missing identity
      as "resolved nothing" is the one rewrite that passes every new test in this
      phase and prints a warning on every call until the worker restarts.
- [ ] T034 [US4] (FR-016, FR-019, trap 8) Feed it at
      `factory/cli/nouns/build.py:1171` and
      `factory/cli/nouns/build.py:1173`, inside
      `factory/cli/nouns/build.py:1119` — `_query_status`. The CLI's own side
      comes from US1's resolver, not from a `git rev-parse` of its own — that is
      FR-019, and it is why `factory/cli/nouns/build.py` must hold no such call
      when this story lands. Reach it through the package-level seam at
      `factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests` or one added
      beside it: `factory.cli.main` `exec_module`s each noun file into a fresh
      module object, so a patch on the imported `build` module never binds.

### Verification for this story

- [ ] T035 [US4] Paste, as committed evidence, the stderr line
      `factory/cli/nouns/build.py:1119` — `_query_status` prints for three
      stubbed status documents — both sides packaged and agreeing, both packaged
      and disagreeing by version, and two revisions that differ — before and
      after the change, with the command that produced each. Drive it through
      `_query_status` with a stubbed client and document, **not** by calling
      `_skew_notice` directly: the notice reaches the operator through that print
      and nowhere else. The shape to copy is
      `tests/test_ergane_build_status_refusal.py:353` — `fake_revision_client`,
      `tests/test_ergane_build_status_refusal.py:309` — `_query_document`,
      `tests/test_ergane_build_status_refusal.py:366` — `_set_cli_revision` and
      `tests/test_ergane_build_status_refusal.py:34` — `_invoke`, with
      `tests/test_status_shows_the_dials_in_force.py:137` — `as_json_document`
      for building a status document that survives the wire. Do **not** copy
      `tests/test_ergane_status.py`: it never drives `_query_status` — its only
      two mentions of the name are an AST guard-sweep table at
      `tests/test_ergane_status.py:1529` and that sweep's anti-vacuity list at
      `tests/test_ergane_status.py:1845`. Do not attempt a live `ergane build status`
      against a real epic from a packaged worker — a node worktree has neither;
      that run is the operator's, at `plan.md` § "Verification the operator will
      run" step 4.

## Verification

- [ ] T036 The full gate command passes green.
- [ ] T037 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 3 — start a worker in a packaged
      environment, reinstall the same version under it, and confirm
      `ops/stale-worker` fires — is the falsifiable test of the whole spec: it is
      the CRITICAL check running for the first time on the install shape this
      project recommends. Step 5 removes the wheel from the story entirely and
      still finds trap 2.
