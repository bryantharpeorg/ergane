# Tasks: a wired repo can land its own bootstrap commit

Read `plan.md` before starting. Three of its traps are the difference between a
green story and a wasted one. Trap 3: spec 128 is queued against
`factory/mergequeue/onboard.py` and this spec must not open that file — the
branch reaches every finding on its own — **and** 128's US2 inserts into the same
`try` block of `factory/activities/merge_activities.py:676-681` —
`onboard_target_repo` that T006 edits, so that block, not `onboard.py`, is where
a merge conflict will actually arrive; US1 of this spec lands first.
Trap 5: the arm of the fix that reads
"create the ruleset non-blocking" is refused by `tests/test_final_sweep.py`,
which parses every module under `factory/` and rejects the arming field's name as
an identifier *or* as a string constant; the bypass declaration goes in the JSON
data file. Trap 6: there is no "wait until a check has been observed" phase in
this spec, and the two ways to build one are a forge-seam operation a test
forbids and a disk read that reproduces the deadlock. Trap 13: the bypass entry
US3 writes is a transcription of a live read-back quoted in plan.md, not a shape
to design — the offline forge model echoes any JSON back, so an invented payload
lands green and fails for the first time on a real `--wire`. Trap 14: the mode
that entry carries is the configuration a critical open ledger row already blames
for one red trunk; it is shipped deliberately and stated out loud, and that key
is not in `fixes:`.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The profile is read for the branch the manifest declares

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, trap 4) Invert
      `tests/test_ergane_init_wiring.py:609` —
      `test_a_landing_branch_that_is_not_the_default_is_wired_and_the_divergence_reported`:
      keep the fixture that wires `release` over a default of `main`, and change
      the assertions at `tests/test_ergane_init_wiring.py:640-642` from
      `not profile.passed` with a failing `gated_landing` to a passing profile.
      Rewrite the two comments that call the old verdict "true". **Do not delete
      the test** — it is the only fixture in the tree that wires a non-default
      landing branch.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003) Assert that every finding in that
      profile which names a branch names `release` — `gated_landing` and
      `autonomous_landing` at least — so the branch is proven to have arrived
      through `LandingPolicy.branch` rather than through a finding taught to name
      one.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) **The control.** Given a repository
      whose manifest is absent, and one whose manifest the schema refuses, assert
      the policy is fetched for the forge's default branch exactly as today and
      that the manifest finding still fails. Drive it through
      `tests/test_ergane_init_wiring.py:368` — `onboarding_profile`.
- [ ] T004 [P] [US1] (spec US1-S4, FR-001, trap 2) Given a manifest declaring no
      `landing_branch` and a forge default of `dev`, assert the policy is fetched
      for `main`. **The deliberate new refusal**: a silent manifest still declares
      `main` (`factory/verify/factory_yaml.py:514` — `_read_landing_branch`), and
      this is the assertion that fails a fallback shaped like "use the default
      when the declared value is `main`".
- [ ] T005 [P] [US1] (spec US1-S5, FR-004) Assert over
      `tests/test_ergane_init_wiring.py:376` — `wiring_report` that the divergence
      report no longer contains `gh repo edit --default-branch` and no longer
      claims every epic start will keep failing, while still naming both branches.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, traps 1 and 2) In
      `factory/activities/merge_activities.py:676` — `onboard_target_repo`, bind
      the declared landing branch beside `declared_gates` and `gate_commands`, and
      bind an empty value in the `except FactoryConfigError` arm at
      `factory/activities/merge_activities.py:683` — `onboard_target_repo`. Pass
      `declared or repository.default_branch` at
      `factory/activities/merge_activities.py:698` — `onboard_target_repo`. That
      is the entire production change for FR-001: do **not** add a parameter to
      `factory/mergequeue/onboard.py:162` — `evaluate_repo`, and do **not** open
      `factory/mergequeue/onboard.py` at all. Expect company in that block: draft
      spec 128's US2 threads `boundary_only_gates` in at
      `factory/activities/merge_activities.py:677` — `onboard_target_repo` and
      passes it at `factory/activities/merge_activities.py:708` —
      `onboard_target_repo` (trap 3). If it has already landed, add your binding
      beside it and rebase; do not move or revert it.
- [ ] T007 [US1] (FR-004) Rewrite the remedy text in
      `factory/mergequeue/wiring.py:559` — `_divergence_step`: keep the step and
      keep naming both branches — its docstring says silence is the trap — and
      remove the claim that onboarding reads the default branch together with the
      two remedies that abandon the declaration.
- [ ] T008 [P] [US1] (FR-004) Correct the two remaining statements of the removed
      behaviour: the module docstring paragraph at
      `factory/mergequeue/wiring.py:41-47`, and the sentence at
      `docs/architecture.md:668-673` that says the merge-queue rule is read on the
      default branch. Cite D-051 (`docs/decisions.md:1255-1267`) in the docstring:
      the declaration owns the value.
- [ ] T009 [US1] (FR-003, trap 3) Confirm by reading the diff that
      `factory/mergequeue/onboard.py`, `factory/roadmap/workflow.py` and
      `factory/workgraph/workflow.py` are untouched. **If any of them needed an
      edit, the design is wrong**: both refusal sites consult `profile.passed`,
      and the verdict is what this story changes.

### Verification for this story

- [ ] T010 [US1] Paste, as committed evidence, the onboarding report for one
      repository declaring `landing_branch: release` over a default of `main` —
      before and after — the first failing on `gated_landing` for `main`, the
      second passing and naming `release`, both produced through
      `onboard_target_repo` rather than by calling `evaluate_repo` directly.

## Phase 2: User Story 2 — The scaffolded workflow installs what its own gate commands need

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1, FR-005) Given `test: uv run pytest -q`, assert
      the rendered job's steps are checkout, a pinned uv setup action, a
      dependency sync, then the gate command, **in that order** — assert on order,
      not on presence.
- [ ] T012 [P] [US2] (spec US2-S2, FR-006) Given `lint: npm --prefix web run
      lint`, assert the job carries a pinned node setup action and a clean install
      carrying the prefix `web`, taken from the command rather than assumed.
- [ ] T013 [P] [US2] (spec US2-S3, FR-007, FR-010) Given a gate command naming
      playwright **and not naming `npm`** — `npx playwright test`, the shape
      `factory/verify/gate_annotation.py:86-95` itself quotes — assert the job
      carries a pinned node setup step and then a browser install with system
      dependencies after it, and that the rendered file states that the same
      install cannot satisfy the gate inside the verification boundary, whose
      `HOME` is a tmpfs (`factory/verify/gates.py:728`). The playwright roster
      entry has to imply that node setup (FR-007, FR-009): FR-006's marker is
      `npm`, which this command does not name, so without the implication the
      ordering assertion has nothing to be ordered after.
- [ ] T014 [P] [US2] (spec US2-S4, FR-008, trap 9) Given `typecheck: make check`,
      assert the job is checkout plus the command alone, that the rendered file
      names that gate as one nothing was derived for, and that the string
      `TODO(operator)` no longer appears in `factory/mergequeue/wiring.py`. The
      gate **name** must be v1-legal (`test`/`lint`/`typecheck`) whenever the case
      is driven through the `wired` fixture — schema v1 refuses `check:` at
      manifest load, before the renderer runs; a case that calls
      `factory/mergequeue/wiring.py:143` — `render_gates_workflow` directly takes
      a plain mapping and is unconstrained.
- [ ] T015 [P] [US2] (spec US2-S6, FR-009, trap 9) Given `test: pytest -k "uv
      run"`, assert **no** setup step is derived. The roster matches the command a
      gate runs on a word-boundary phrase, never a substring of anything — the
      argument is already written at `factory/verify/gate_annotation.py:28-33`.
- [ ] T016 [US2] (spec US2-S5, FR-005, trap 8) Commit the workflow text this
      repository renders **today** as a fixture, place it at the managed path in a
      target repository, run the wiring, and assert the step reports "exists and
      differs; it was NOT overwritten" and that the file is byte-unchanged. Not
      `[P]`: it needs the new renderer's output to differ from the fixture, so it
      is written against both. This is the scenario a diff that changed nothing
      cannot pass — an unchanged renderer reports the file already satisfied.

### Implementation for this story

- [ ] T017 [US2] (FR-009, trap 9) Add the roster to
      `factory/mergequeue/wiring.py`, modelled on
      `factory/verify/gate_annotation.py:86-95` — one frozen entry per tool
      carrying its word-boundary phrase and the steps it implies, with the
      docstring stating that growing it is deliberate. Keyed on the gate's
      command, never on the gate's name.
- [ ] T018 [US2] (FR-005, FR-006, FR-007, trap 10) In
      `factory/mergequeue/wiring.py:143` — `render_gates_workflow`, emit the
      derived steps **inside each gate's own job**, between the checkout at
      `factory/mergequeue/wiring.py:162` — `render_gates_workflow` and the run
      step. Do not add a shared setup job: the job id is the check name, and a
      check no gate declares fails the repository through
      `factory/mergequeue/onboard.py:402` — `_unknown_check_finding`. Keep
      `tests/test_ergane_init_wiring.py:460` —
      `test_the_generated_jobs_produce_no_unknown_check_finding` green.
- [ ] T019 [US2] (FR-008, FR-010) Replace the `TODO(operator)` lines at
      `factory/mergequeue/wiring.py:131-132` with text the renderer computes: what
      was derived, which gates nothing was derived for, by name, and the
      `HOME`-persistence asymmetry beside the browser install. The header constant
      is shared by every job, so the per-gate sentences are rendered, not
      hard-coded into `factory/mergequeue/wiring.py:124-140`.

### Verification for this story

- [ ] T020 [US2] Paste, as committed evidence, the complete rendered
      `ergane-gates.yml` covering all four gate shapes — a `uv` gate, an
      `npm --prefix` gate, a playwright gate and one nothing matches — so a reader
      can see the four jobs and the four verdicts side by side. Produce it by
      calling `factory/mergequeue/wiring.py:143` — `render_gates_workflow`
      directly with a plain four-entry mapping, **not** through a manifest: schema
      v1 fixes gate names to the three in `KNOWN_GATES`
      (`factory/verify/factory_yaml.py:92`) and refuses a fourth at load
      (`factory/verify/factory_yaml.py:357-366`), so a four-gate manifest never
      reaches the renderer (trap 9). The renderer takes an unconstrained mapping,
      which is why the evidence goes through it.

## Phase 3: User Story 3 — The queue does not lock out the identity that wired it

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1, FR-011, trap 13) Wire a fresh repository
      through `tests/test_ergane_init_wiring.py:115` — `FakeGitHub` and assert the
      body posted to the rulesets endpoint carries exactly one bypass entry,
      equal field-for-field to the array plan.md § "What already exists, and
      where" quotes — `actor_id` null, `actor_type` `OrganizationAdmin`,
      `bypass_mode` `always`. Assert the three fields **literally**, not the
      presence of a list: the fake's create path
      (`tests/test_ergane_init_wiring.py:272` — `_create_ruleset`) stores whatever
      was posted and hands it back, so a shape-tolerant assertion passes over a
      payload GitHub refuses.
- [ ] T022 [P] [US3] (spec US3-S2, FR-012, trap 5) Assert the declaration is
      present in `factory/mergequeue/merge_queue_ruleset.json` and that no module
      under `factory/` gained an identifier or a string constant naming the arming
      field. `tests/test_final_sweep.py:614` —
      `test_the_component_cannot_even_spell_a_cap` is the test that proves it;
      note in the new test which module it covers and why the JSON file is exempt.
- [ ] T023 [US3] (spec US3-S4, FR-013, trap 7) Assert first that the body
      `factory/mergequeue/wiring.py:566` — `_ruleset_payload` builds carries the
      bypass declaration — **without that half the rest of this test passes over a
      payload that declares nothing** — then hand
      `factory/mergequeue/wiring.py:589` — `_ruleset_satisfies` a stored ruleset
      shaped the way a forge returns one, its bypass entries in a different order
      and carrying keys the request never sent, and assert it still reports
      satisfied. Not `[P]`: it is written against the same comparison T027
      changes. The offline model stores the posted body verbatim on both paths —
      `tests/test_ergane_init_wiring.py:272` — `_create_ruleset` on the POST, the
      branch at `tests/test_ergane_init_wiring.py:248-251` on a re-wire's PUT — so
      it can never produce this shape and a test that went through it would prove
      nothing.
- [ ] T024 [P] [US3] (spec US3-S5, FR-014) Given a stored ruleset whose bypass
      differs in meaning from the declared one — one case with the same actor type
      in a different mode, one with a different actor type — assert the wiring
      reports each not satisfied and updates it to the declared entry.
- [ ] T025 [P] [US3] (spec US3-S3, FR-013) **The control.**
      `tests/test_ergane_init_wiring.py:489` —
      `test_rewiring_reports_already_satisfied_and_changes_nothing` must stay green
      **unmodified**: a re-run reports already satisfied, issues no mutating call,
      and leaves the model's state byte-identical
      (`tests/test_ergane_init_wiring.py:512-513`).

### Implementation for this story

- [ ] T026 [US3] (FR-011, FR-012, traps 5, 13 and 14) Add the bypass declaration
      to `factory/mergequeue/merge_queue_ruleset.json`, beside the arming field at
      `factory/mergequeue/merge_queue_ruleset.json:4`, **transcribed** from the
      array plan.md § "What already exists, and where" quotes: one entry, all
      three fields, values unchanged. Do not paraphrase it, do not drop
      `actor_id`, do not substitute an actor type that plan does not quote — no
      test in this repository can refuse a payload the offline model will happily
      echo. Add **no** Python naming either field. Record beside
      `factory/mergequeue/wiring.py:566` — `_ruleset_payload`, as a comment, both
      halves: why the bypass arm was taken rather than the non-blocking one (the
      sweep refuses the other word, and this is the working configuration on this
      repository), and that the mode is the one a critical open ledger row blames
      for an ungated push that redded this trunk — shipped deliberately, argued in
      plan.md trap 14, and not declared fixed.
- [ ] T027 [US3] (FR-013, FR-014, trap 7) Teach
      `factory/mergequeue/wiring.py:589` — `_ruleset_satisfies` to decide the
      bypass declaration by meaning rather than by the bare inequality at
      `factory/mergequeue/wiring.py:592` — `_ruleset_satisfies`, the way it already
      compares the required contexts by meaning further down. Order-insensitive,
      tolerant of keys the forge added, and still false when the declaration
      differs.

### Verification for this story

- [ ] T028 [US3] Paste, as committed evidence, the ruleset body this wiring posts
      on a first run and the report line a second run produces, showing the bypass
      entry with all three of its fields in the first and "already satisfied" with
      no write in the second. Paste the body whole rather than summarising it: the
      three field values are the story's only checkable claim about a shape no
      offline test can refuse (trap 13).

## Phase 4: User Story 4 — The printed order is the order that works

### Tests for this story (write FIRST, must fail)

- [ ] T029 [P] [US4] (spec US4-S1, FR-015, trap 11) Assert over the list
      `factory/mergequeue/wiring.py:104` — `manual_steps` returns that the
      commit-and-push entry precedes the ruleset entry, **and** that the entries
      carrying a leading number carry `1` to `N` in order of appearance with no
      gap and no repeat. Skip the unnumbered continuation lines
      (`factory/mergequeue/wiring.py:117` and `factory/mergequeue/wiring.py:119`)
      rather than asserting number equals list index: the returned list has seven
      elements and only five numbers, so an index assertion fails on an untouched
      list and proves nothing about the reorder. The number half is what catches a
      reorder that forgot to renumber; nothing in the suite catches it today.
- [ ] T030 [P] [US4] (spec US4-S2, FR-016, trap 14) In one test, assert the queue
      step's creation path states that the workflow must be pushed before any
      proposal can satisfy the required checks and names **both** the actor class
      and the mode of the bypass the ruleset carries — an operator the bypass does
      not admit has to be able to read that off the report — **and** that the
      already-satisfied path does not carry that sentence. Both halves together,
      so the sentence cannot be added unconditionally.
- [ ] T031 [P] [US4] (spec US4-S3, FR-017) Assert the applied detail of
      `factory/mergequeue/wiring.py:241` — `scaffold_gates_workflow` tells the
      operator to commit *and push* the file and gives the bootstrap order as the
      reason.
- [ ] T032 [P] [US4] (spec US4-S4, FR-018, trap 11) **The controls, both of
      them.** `tests/test_ergane_init_wiring.py:763` —
      `test_manual_steps_renders_the_auto_merge_command` must stay green
      **unmodified** — it holds `allow_auto_merge=true` and nothing else — and
      `tests/test_wiring_us2.py:129` —
      `test_refusal_carries_complete_manual_steps` must too, because it holds the
      tree's only assertion on `squash_merge_commit_title=PR_TITLE`. Neither
      covers both strings: a renumbering may not reword either of the two
      `gh api` commands operators have in their runbooks, and :763 alone would not
      notice.

### Implementation for this story

- [ ] T033 [US4] (FR-015, FR-018, trap 11) Reorder
      `factory/mergequeue/wiring.py:113-121` — `manual_steps` so committing and
      pushing the workflow precedes the ruleset entries, and retype every number
      so it matches its new position. Leave the two `gh api` command strings
      byte-identical.
- [ ] T034 [US4] (FR-016, trap 14) Add the bootstrap sentence to the creation
      path of `factory/mergequeue/wiring.py:535` — `_queue_step` only, naming the
      bypass by its actor class *and* its mode; leave the already-satisfied and
      updated details as they are.
- [ ] T035 [US4] (FR-017) Rewrite the applied detail at
      `factory/mergequeue/wiring.py:241` — `scaffold_gates_workflow` to say commit
      **and push**, with the bootstrap order as the reason rather than "the queue
      cannot require a check nothing produces".

### Verification for this story

- [ ] T036 [US4] Paste, as committed evidence, the full printed step list and the
      full `--wire` report for a first-time wiring, so the two orders can be read
      against each other in one place.

## Verification

- [ ] T037 The full gate command passes green.
- [ ] T038 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. Step 2 — pushing the bootstrap commit directly
      into a freshly wired repository — is the falsifiable test of US3 and US4,
      because it is the push two reported targets refused four times over one run;
      step 5 — dispatching through the roadmap and starting one epic with
      `ergane build start` — is the falsifiable test of US1, because it is the
      epic start N10's reporter abandoned the two-branch model to get past.
