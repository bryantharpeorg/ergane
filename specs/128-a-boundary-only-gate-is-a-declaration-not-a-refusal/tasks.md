# Tasks: a boundary-only gate is a declaration, not a refusal

Read `plan.md` before starting. Trap 1 describes reasoning that is **already in
this tree** — `_LANDING_ONLY_CHECK_PREFIXES` at
`factory/workgraph/workflow.py:391` — wired to the demo path and nowhere else.
Widening its use is the obvious move and it exempts the typo case this check
exists for. Trap 2 describes a second refusal site that a roadmap-only test cannot
see. Trap 9 is the opposite hazard and the one that would waste the whole story:
the manifest key must be threaded through the seam in
`factory/activities/merge_activities.py`, or every test passes while production
reads nothing. Trap 10 is that same waste from the other end: both refusal sites
already proceed on a passing `TargetRepoProfile` a test wrote by hand, and they do
so on today's tree, so US2-S4's verdicts must be derived from two manifests rather
than constructed — through the **modelled** forge, because the real forge over a
remote-less repository never reaches `evaluate_repo` at all. Trap 11 is the last
step of that route: the fixture manifests are v1 and this key is v2-only. Trap 12
is the third red a US2 fixture collects for a reason this spec is not about — a
model built without `title_source` fails `landing_title`, both halves of the pair
come back failing, and the differential dies a third way. Trap 13 is US1's: the
tuple FR-004 names is also the one `ergane init` carries by, so the correct
registration turns a landed 120 test red by construction — that red is the proof
the key went into the right tuple, not a reason to move it.

Tests are written first and must fail before the implementation that satisfies
them — except the tasks marked **The control**, which assert non-regression and
are green from the first commit; do not manufacture a failure for those. Every
acceptance scenario is provable from the diff, which is all the judge sees;
runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The manifest can say a gate binds the boundary alone

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) Given a v2 manifest declaring
      `boundary_only_gates: [audit]` beside a `gates:` block that declares `audit`,
      assert it parses and the parsed configuration carries the list.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 5) Given a v2 manifest whose
      `boundary_only_gates` names a gate the manifest does not declare, assert the
      load is refused with a message naming the entry and the rule. **New
      strictness, deliberately**: a misspelled entry exempts nothing while reading
      as though it exempts something.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) **The control.** Given a manifest that
      does not declare the key, assert the parsed configuration is identical to
      today's. Every existing manifest is this manifest.
- [ ] T004 [P] [US1] (spec US1-S4, FR-004, trap 4) Given **one** manifest body
      declaring the key, assert the `version: 2` load parses and carries the list
      **and** the `version: 1` load is refused as an unknown top-level key. Both
      halves in one test: the v1 half alone passes today, before any change, so
      only the pair can fail a diff that registered the key in the wrong tuple.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-004, traps 4 and 13) Add the key to
      `_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:134`) — **not** to
      `_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:118`), where `writes`
      lives and which is the v1 list. `factory/verify/factory_yaml.py:269` —
      `_reject_unknown_keys` picks its known-set by version at
      `factory/verify/factory_yaml.py:270` — `_reject_unknown_keys` and needs no
      edit. That same tuple is `_KNOWN_KEYS` (`factory/cli/init.py:511`) — the
      same object — so this one line turns a **landed** test red:
      `tests/test_120_rewrite_carries_forward.py:310` asserts the carried-key
      list is exactly `["ladder", "verify"]`. Update that assertion in this
      commit to `["ladder", "verify", "boundary_only_gates"]`; the key is
      carried-not-interviewed by construction, so the same test's second
      assertion (`tests/test_120_rewrite_carries_forward.py:311`) still holds and
      no interview prompt is added. The red is confirmation the key landed in the
      right tuple, **not** a signal to move it: moving it to `_TOP_LEVEL_KEYS`
      breaks FR-004 and fails `tests/test_forge_manifest.py:333` instead (trap
      13).
- [ ] T006 [US1] (FR-001) Add the field to `FactoryConfig` beside `gates`
      (`factory/verify/models.py:310` — `FactoryConfig`), defaulting to empty so
      FR-003 holds by construction.
- [ ] T007 [US1] (FR-002, trap 5) Add the reader that cross-checks every entry
      against the declared gates, modelled on `factory/verify/factory_yaml.py:431` —
      `_read_writes` and its refusal at `factory/verify/factory_yaml.py:459` —
      `_read_writes`, and call it from the reader list beside `_read_writes` at
      `factory/verify/factory_yaml.py:217`. Reuse that refusal's wording — the tree
      already argues this case.

### Verification for this story

- [ ] T008 [US1] Paste, as committed evidence, the refusal text for a manifest
      whose list names an undeclared gate, and the successful parse of one whose
      list is correct.

## Phase 2: User Story 2 — Onboarding reports the declaration instead of refusing it

### Tests for this story (write FIRST, must fail)

- [ ] T009 [P] [US2] (spec US2-S1, FR-005, trap 8) Given a gate declared, listed
      boundary-only, and not required on the landing branch, assert the profile
      **passes** and still carries a non-blocking finding naming that gate. The
      choice must stay visible every run rather than becoming silent. Build the
      fixture with `tests/test_onboard.py:280` — `_init_facts` or with
      `init_facts=None`: 057 added a blocking `standards` finding, so a hand-built
      `InitFacts` fails the profile for a reason this story is not about.
- [ ] T010 [P] [US2] (spec US2-S2, FR-006, trap 7) Given a gate declared, listed
      boundary-only, and **required** on the landing branch, assert the profile
      passes with a non-blocking "declaration is stale" finding. A drifted manifest
      is not a broken repository.
- [ ] T011 [P] [US2] (spec US2-S3, FR-007, trap 6) **The control that matters
      most.** Given a gate declared, **not** listed, and not required, assert the
      profile fails with today's blocking `gate_check:<gate>` finding and that its
      detail text is **byte-identical** to today's. This is the typo case the check
      exists for, and operators have that string in their runbooks.
- [ ] T012 [P] [US2] (FR-008, trap 3) **The control.** Assert `noop_gate:` and
      `unknown_check:` findings keep their current severities and blocking
      behaviour, so this story cannot soften findings it is not about.
- [ ] T013 [US2] (spec US2-S4, FR-009, traps 2, 10, 11 and 12) Given **two**
      manifests differing only in the `boundary_only_gates` line, derive a profile
      from each through the real judgment, then assert that the listed one neither
      parks at the roadmap's dispatch path (`factory/roadmap/workflow.py:1262` —
      `_dispatch`) nor raises at a child epic's re-evaluation
      (`factory/workgraph/workflow.py:1225` — `_onboard_target`), while the unlisted
      one still parks and still raises. Derive each profile the way
      `tests/test_forge_readiness.py:68` —
      `test_a_forge_reporting_no_visibility_passes_and_fails_when_gating_goes`
      derives its own pair at `tests/test_forge_readiness.py:90`: one repository
      from `tests/target_repo.py:102` — `build_target_repo` whose `ergane.yaml` is
      overwritten with a `version: 2` body (trap 11), one
      `tests/fake_forge.py:58` — `RepositoryModel` built the way
      `tests/test_forge_readiness.py:57` — `_ready_model` builds one with its gate
      tuple narrowed and **nothing else changed** —
      `model.gate_on("main", tuple(g for g in FIXTURE_GATES if g != "lint"),
      title_source=NEUTRAL_TITLE_SOURCE)`, over `FIXTURE_GATES`
      (`tests/test_forge_readiness.py:33`) and `NEUTRAL_TITLE_SOURCE`
      (`tests/test_forge_readiness.py:36`) — so the gate under test is declared
      and not required, and `onboard_target_repo(FakeForge(model), str(repo))`
      run once per manifest. Dropping `title_source` is not a simplification: it
      fails `landing_title` in **both** halves, so the pair stops differing and
      the differential dies for a third reason this spec is not about (trap
      12).
      Then feed the two derived profiles through the seams the suite already
      scripts: `tests/test_roadmap_scheduler.py:299` — `RoadmapWorld.__init__`,
      beside `tests/test_roadmap_scheduler.py:965` —
      `test_an_onboarding_failure_parks_the_spec`; and
      `tests/test_interpreter.py:1045` — `ScriptedWorld.__init__`, beside
      `tests/test_interpreter.py:2458` — `test_a_passing_onboarding_profile_proceeds_to_normal_dispatch`.
      **Do not inject a `TargetRepoProfile` the test constructed with
      `passed=True`**: both surfaces already proceed on one today, so that test is
      green on a diff that changes no production file. **And do not derive the
      pair through `onboard_target_repo(_forge(...), ...)`**: that route refuses
      before `evaluate_repo` runs, so both halves come back `passed=False` on a
      `repo_read` finding and the difference between them disappears. Not `[P]`:
      it drives both surfaces over one shared fixture.
- [ ] T014 [US2] (spec US2-S5, FR-010, traps 9, 10, 11 and 12) Given a repository
      whose manifest declares the list for a gate the landing branch does **not**
      require, drive onboarding through
      `factory/activities/merge_activities.py:639` — `onboard_target_repo` with a
      caller that names **no** list of its own, and assert the profile passes —
      **and** assert the other half: the same repository with the
      `boundary_only_gates` line removed from its `version: 2` manifest still
      fails with the blocking `gate_check:<gate>` finding. One repository, one
      manifest line, two verdicts, the shape `tests/test_forge_readiness.py:68`
      already uses. Red before, green after: on today's tree with US1 merged,
      T015 and T016 written and T017 unwritten, the listed half's profile still
      carries that blocking finding too, because nothing has read the manifest's
      list. Build the model the way trap 10 does and **not** the way
      `tests/test_forge_readiness.py:57` — `_ready_model` does — narrow its gate
      tuple and change nothing else:
      `model.gate_on("main", tuple(g for g in FIXTURE_GATES if g != "lint"),
      title_source=NEUTRAL_TITLE_SOURCE)`, over `FIXTURE_GATES`
      (`tests/test_forge_readiness.py:33`) and `NEUTRAL_TITLE_SOURCE`
      (`tests/test_forge_readiness.py:36`), so the listed gate is declared and
      not required. Keeping `title_source` is mandatory, not cosmetic: without it
      `tests/fake_forge.py:90` — `gate_on` leaves
      `landing_title_from_proposal=False` and the profile fails `landing_title`,
      so it never passes at all and this scenario's Then is unreachable (trap
      12). Hand the model to `tests/fake_forge.py:160` — `FakeForge` over a
      repository from `tests/target_repo.py:102` — `build_target_repo` whose
      `ergane.yaml` you rewrite as a `version: 2` body (trap 11), with
      `init_facts` left unset (trap 8). Copy the *call* at
      `tests/test_forge_readiness.py:90` —
      `onboard_target_repo(FakeForge(model), str(repo))`, the shape
      `tests/test_forge_readiness.py:68` —
      `test_a_forge_reporting_no_visibility_passes_and_fails_when_gating_goes`
      drives to `profile.passed is True` at `tests/test_forge_readiness.py:92` —
      but not its model: `_ready_model` requires every declared gate
      (`tests/test_forge_readiness.py:61`), so
      `factory/mergequeue/onboard.py:385` — `_gate_check_finding` takes its
      passing branch, the profile passes before T017 exists, and the test is green
      on a diff that threads nothing. The test may not pass the list to
      `evaluate_repo` by hand either — that is the other shortcut this scenario
      exists to refuse. Do **not** copy
      `tests/test_114_us2_fixtures_onboard.py:252` — `onboarding_findings` or
      `tests/test_114_us1_smoke_onboards.py:317`: they hand the **real** forge a
      repository with no remote, so
      `factory/activities/merge_activities.py:719` —
      `_profile_from_forge_failure` returns `passed=False` without ever calling
      `evaluate_repo`, which is why
      `tests/test_114_us1_smoke_onboards.py:346` —
      `test_the_filter_is_what_clears_the_repository` asserts exactly that. Do not
      write a new forge fake either. Then extend FR-010's existing door-parity
      assertion, `tests/test_ergane_init_check.py:490` —
      `test_both_doors_render_identical_parity_findings`, with a case whose
      manifest lists a declared gate the branch does not require — its wiring at
      `tests/test_ergane_init_check.py:502` already requires `test` and
      `typecheck` over a manifest declaring `test` and `lint`, so `lint` is that
      gate — and assert through **both** doors that the `gate_check:lint` finding
      is non-blocking. Equality of the triples alone holds before this story and
      after it; the mark is the half that can fail.

### Implementation for this story

- [ ] T015 [US2] (FR-005, FR-006, FR-007, FR-008, traps 1 and 3) In
      `factory/mergequeue/onboard.py:390` — `_gate_check_finding`, branch on
      whether the gate is listed boundary-only and pass `Severity.WARNING`
      **explicitly** for the two non-blocking cases, following
      `factory/mergequeue/onboard.py:340` — `_noop_gate_finding`. Do **not** widen
      `factory/mergequeue/models.py:363` — `blocking` and do **not** touch the
      verdict conjunction at `factory/mergequeue/onboard.py:235` — `evaluate_repo`;
      both are shared with findings this story is not about. Do **not** reach for
      `factory/workgraph/workflow.py:394` — `_is_landing_only_check` — it is wired
      to the demo path and exempting `gate_check:` through it would exempt the typo
      case too.
- [ ] T016 [US2] (FR-005, FR-006) Thread the declared list into
      `factory/mergequeue/onboard.py:162` — `evaluate_repo` so the gate loop at
      `factory/mergequeue/onboard.py:215` — `evaluate_repo` can consult it,
      following how `gate_commands` already reaches `_gate_check_finding`. Additive
      with an empty default, so a caller that says nothing reports exactly what it
      reports today.
- [ ] T017 [US2] (FR-010, trap 9) Derive the list from the loaded manifest in
      `factory/activities/merge_activities.py:677` — `onboard_target_repo`, beside
      where `declared_gates` and `gate_commands` already come off the same config,
      and pass it at `factory/activities/merge_activities.py:708` —
      `onboard_target_repo`. This is what makes the key real; without it every test
      above can pass while production reads nothing.
- [ ] T018 [US2] (FR-009, trap 2) Confirm by reading that neither
      `factory/roadmap/workflow.py` nor `factory/workgraph/workflow.py` needed an
      edit. **If either did, the design is wrong**: both sites consult
      `profile.passed`, and the verdict is what this story changes.

### Verification for this story

- [ ] T019 [US2] Paste, as committed evidence, the onboarding report for the same
      repository before and after the gate is listed boundary-only — the first
      blocking and parking, the second passing and still naming the gate — with both
      reports produced through `onboard_target_repo`, not by calling
      `evaluate_repo` directly.

## Verification

- [ ] T020 The full gate command passes green.
- [ ] T021 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end, including step 4's third door
      (`ergane repo onboard`, which calls the seam with no `init_facts`). Step 5 —
      dispatching through the roadmap **and** by hand with `ergane build start` —
      is the falsifiable test of this whole spec, because it is the pair of refusal
      sites that stopped a consumer's line for 11h40m.
