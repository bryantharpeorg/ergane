# Tasks: a test cannot reach the operator's floor

**Spec**: `specs/074-a-test-cannot-reach-the-operators-floor/spec.md`
**Plan**: `specs/074-a-test-cannot-reach-the-operators-floor/plan.md`

Read plan.md before the first task; its anchors were re-read from
`ergane-buildout` at `602a92c` on 2026-09-04 and the 2026-08-20 set had rotted.
Tests come first in every phase and must fail before the implementation lands.
`[P]` marks tasks with no ordering constraint between them. Every acceptance
criterion must be provable from the diff alone (Constitution VIII, D-037): where
a task says "paste", it means committed tool output, not a description of it.

Fifteen traps decide whether an attempt lands: trap 1 and trap 2 (the husk check
already exists as `_repo_identity`, and `salvage` has no repository to hand it),
trap 4 (the epic exclusion is by workflow type; swapping the bare literal for the
constant changes nothing), trap 5 (US2's independence is per mutation site, not per
signal), trap 8 (the marker phrase `auto-skips unless ` is load-bearing for two
landed readers), trap 10 (a landed test enters the unguarded client on purpose and
must be carried forward, not deleted), trap 17 (the capacity tier asserts the
inverse of US5 and the gate skips it), trap 18 (the eleventh client site is
guarded, and both of its guards stay), **trap 19** (a landed AST guard asserts a
resolver import in every module this spec migrates, and deleting the resolver call
with the connect reddens the declared gate), **trap 20** (the choke point takes an
already-resolved target and resolves nothing, because two callers cannot use a
parameterless resolver), **trap 21** (the FR-010 opt-in has to be readable from
`factory/`, not only from pytest), **trap 22** (binding `_open_epics_provider`
to prove FR-020 replaces the reader under test and passes on a test-only diff),
**trap 23** (seven landed test modules bind the floor at
`temporalio.client.Client.connect` and drive the callers this spec migrates, so
the choke point's refusal fires before the fake is consulted and about a hundred
landed tests go red unless the same story rebinds them), **trap 24** (a second
landed AST guard derives its module set from `factory/cli/**` and pins every
migrated function's `except` clauses, so the choke point may not live there),
**trap 25** (the one sanctioned door is proven against a dead port, never against
a resolved default) and **trap 26** (an enumerating test that resolves nothing
passes forever).

## Phase 1: User Story 1 — One place builds a real client

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-004) In
      `tests/test_one_client_chokepoint.py`, assert that with
      `PYTEST_CURRENT_TEST` set the choke point refuses, and that the message
      contains the address, the namespace and the name of the seam to bind. Model
      the message on `factory/roadmap/schedule.py:156` —
      `_default_schedule_client`, the only refusal in the tree that names all
      three.

- [ ] T002 [P] [US1] (spec US1-S2, FR-005) **The control for trap 7.** Assert the
      choke point's refusal and one unrelated precondition refusal reachable from
      the same call path are distinguishable: each contains a substring the other
      does not, and the test asserts on the unique one. Assert the negative too —
      that neither unique substring occurs in the other message.

- [ ] T003 [P] [US1] (spec US1-S4, FR-001) Assert the seam declared beside the
      choke point is bindable by exactly the name the refusal of T001 prints.

- [ ] T005 [US1] (spec US1-S3, FR-022) **Trap 10.** In
      `tests/test_runtime_root.py`, rewrite
      `tests/test_runtime_root.py:124` —
      `test_running_epic_ids_default_factory_raises_transport_not_nameerror` so it
      still enters the default client factory without rebinding it and now asserts
      the choke point's refusal. Do not delete it and do not convert it to a skip;
      US2-S3 is where the transport branch is proven afterwards.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-029, FR-004, trap 20, trap 24) Create the choke
      point module **in `factory/controlplane/`** — beside
      `factory/controlplane/resolve.py:232` — `resolve_temporal_target`,
      `factory/controlplane/client.py` being the obvious name — and **not** under
      `factory/cli/`, where `tests/test_ergane_status.py:1600` —
      `_cli_python_modules` would discover it and redden
      `tests/test_ergane_status.py:1716` —
      `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal`
      (trap 24). Do not re-export it from `factory/controlplane/__init__.py`,
      which is zero bytes on purpose. One
      function that takes an **already-resolved** target — an address and a
      namespace, passed in by its caller — resolves nothing for itself, refuses
      under `PYTEST_CURRENT_TEST` naming that address, that namespace and the
      seam, then connects. Copy the refusal shape from
      `factory/roadmap/schedule.py:156` — `_default_schedule_client`, whose own
      resolution stays in that module. **Do not give it a parameterless
      resolver**: `factory/controlplane/verify.py:193` —
      `_temporal_client_factory` must keep `temporal_target_for(config,
      source=_DECLARED_SOURCE)` and its config-first precedence, and
      `factory/supervision/deploy.py:749` — `asked` connects to `self._address`
      and `self._namespace` set at
      `factory/supervision/deploy.py:720`. US6 imports this module and may not
      widen it.

- [ ] T007 [US1] (FR-001) Declare the seam beside it, in the idiom of
      `factory/cli/repo.py:93-94`. Keep the property
      `factory/cli/nouns/__init__.py:54` — `_open_client` documents: noun modules
      are `exec_module`-d into fresh module objects, so the seam must live where
      discovery never reloads it.

- [ ] T012 [US1] (FR-005) Grep the tree for the substring each new refusal's test
      asserts on, change any that collides, and record what you grepped in the
      commit body.

### Verification for this story

- [ ] T013 [US1] (spec US1-S1, spec US1-S4, FR-004, FR-022) Paste, as committed
      evidence in the test module's docstring, the red-then-green transcript for
      T001 and T005 — the failing run before the choke point exists and the
      passing run after — so the refusal is shown to be load-bearing rather than
      asserted to be. Paste beside it the output of
      `git diff --stat -- tests/test_declared_temporal.py`, which must be empty
      (trap 19).

**Checkpoint**: the four CLI callers reach Temporal through one function, and a
test process cannot get a client from it.

## Phase 2: User Story 7 — The four callers reach the choke point

Split out of US1 on 2026-09-08 for size. Merges after US1; everything that
waited for the whole of US1 now waits for this story.

### Tests for this story (write FIRST, must fail)

- [ ] T076 [P] [US7] (spec US7-S2, FR-002, trap 19) **The landed guard.** Assert
      that each of the four migrated modules still contains an import of
      `resolve_temporal_target` from `factory.controlplane.resolve` and still
      calls it before asking the choke point — walk the AST of each file the way
      `tests/test_declared_temporal.py:423` —
      `test_every_connect_site_reaches_the_one_resolver` does, so this story
      carries the contract in its own diff rather than discovering it as a red
      suite. Assert in the same module that
      `tests/test_declared_temporal.py:392` (the tuple `_RESOLVER_SITES`) still
      lists all four, and do not edit `tests/test_declared_temporal.py`.

- [ ] T079 [US7] (spec US7-S3, FR-027, trap 23) **The landed floor-fakes.**
      Rebind, to the seam the choke point declares, every fake this story's four
      callers are driven through: `tests/test_ergane_status.py:485` —
      `fake_temporal`, `tests/test_roadmap_schedule_discovery.py:311` —
      `fake_temporal`, `tests/test_roadmap_wedge_visibility.py:219` —
      `fake_temporal`, `tests/test_teardown_owns_the_ordering.py:213` — `_host`,
      `tests/test_teardown_owns_the_ordering.py:600` —
      `test_roadmap_pause_command_still_pauses_the_schedule`, and
      `tests/test_ergane_spec.py:448` — `test_validate_opens_no_socket`, whose
      fake raises rather than returns and would otherwise stop meaning "opens no
      socket". Each is one line in a fixture. **Delete nothing and skip
      nothing** — a green run cannot show you a test that is no longer there.
      Carry `tests/test_teardown_owns_the_ordering.py:631` —
      `test_roadmap_py_is_not_edited_by_this_story` forward in the same edit: it
      requires the literal `Client.connect` to occur exactly once in
      `factory/cli/roadmap.py`, which T010 removes, so make it assert that module
      reaches the choke point instead and leave its `_pause_command_factory`
      clause alone.

- [ ] T080 [P] [US7] (spec US7-S4, FR-029, trap 24) **The CLI guard sweep.** In
      this story's own test module, assert the three clause tuples
      `tests/test_ergane_status.py:1516` pins for the migrated callers —
      `('RPCError', 'RuntimeError', 'OSError')` for
      `factory/cli/nouns/__init__.py:54` — `_open_client` and
      `factory/cli/roadmap.py:205` — `_connect`, `('Exception',)` for
      `factory/cli/repo.py:85` — `_open_client` — and that each of those three
      functions still awaits. Do not edit `tests/test_ergane_status.py`'s table
      or its sweep at `tests/test_ergane_status.py:1716` —
      `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal`;
      this task states the contract in this story's diff so it is met as scope
      rather than as a red gate.

- [ ] T004 [US7] (spec US7-S1, FR-002) One case per migrated caller, four small
      cases rather than one loop — a loop that skips a caller looks identical to a
      loop that covers it. With the choke point's seam bound to a fake, assert
      each of `factory/workgraph/cli.py:977` — `_connect`,
      `factory/cli/nouns/__init__.py:54` — `_open_client`,
      `factory/cli/roadmap.py:205` — `_connect` and `factory/cli/repo.py:85` —
      `_open_client` behaves as it does today, including its own exit code.

### Implementation for this story

- [ ] T008 [P] [US7] (FR-002, trap 19) Migrate
      `factory/workgraph/cli.py:977` — `_connect`, keeping its `EXIT_TRANSPORT`
      translation and its address-in-the-message behaviour. **Keep the
      `resolve_temporal_target()` call at `factory/workgraph/cli.py:966` and its
      import at `factory/workgraph/cli.py:32`**, and pass the resolved target
      into the choke point: that import is the only one in this module and
      `tests/test_declared_temporal.py:423` —
      `test_every_connect_site_reaches_the_one_resolver` asserts it is there.

- [ ] T009 [P] [US7] (FR-002, trap 19) Migrate
      `factory/cli/nouns/__init__.py:54` — `_open_client`, keeping the
      `resolve_temporal_target()` call at `factory/cli/nouns/__init__.py:51` and
      its import at `factory/cli/nouns/__init__.py:19`.

- [ ] T010 [P] [US7] (FR-002, trap 19) Migrate
      `factory/cli/roadmap.py:205` — `_connect`, keeping the
      `resolve_temporal_target()` call at `factory/cli/roadmap.py:202` and its
      import at `factory/cli/roadmap.py:50`.

- [ ] T011 [P] [US7] (FR-002, trap 19) Migrate `factory/cli/repo.py:85` —
      `_open_client`, inside `factory/cli/repo.py:80-90` — `_open_client`. Keep
      the existing seam at `factory/cli/repo.py:93-94` working; tests bind it by
      that name. Keep the `resolve_temporal_target()` call at
      `factory/cli/repo.py:82` and its import at `factory/cli/repo.py:58`.
      **Trap 24**: leave `factory/cli/repo.py:48` alone — that unrelated
      `ActivityEnvironment` import is the only `temporalio` mention this module
      keeps once its `Client` import goes, and without it the module drops out of
      the discovered set and the sweep goes red.

## Phase 3: User Story 2 — Disabling one guard is not enough

### Tests for this story (write FIRST, must fail)

- [ ] T014 [P] [US2] (spec US2-S1, FR-007) In
      `tests/test_two_independent_guards.py`, neutralise the
      `PYTEST_CURRENT_TEST` refusal the way a mutation would — patch its condition
      to a constant — and assert the second defence still refuses, naming itself.

- [ ] T015 [P] [US2] (spec US2-S2, FR-008) The mirror: neutralise the second
      defence and assert the `PYTEST_CURRENT_TEST` refusal still fires.

- [ ] T016 [US2] (spec US2-S3, FR-008) **The control for trap 5.** Neutralise both
      and assert a connection is attempted. Point `TEMPORAL_ADDRESS` at 127.0.0.1
      port 1 and assert on the error text, not on an exception type — `temporalio`
      raises a bare `RuntimeError` on a dead port. A pair that cannot both be
      removed is one guard wearing a disguise, and this is the only test that can
      tell.

- [ ] T017 [P] [US2] (spec US2-S4, FR-009, FR-030, trap 25) Assert that with the
      named opt-in of FR-010 present, both defences stand down and a connection
      is attempted — **against `TEMPORAL_ADDRESS` pointed at 127.0.0.1 port 1**,
      exactly as T016 does it, asserting on an error text that names that
      address. This is the only test in the spec that walks through the
      sanctioned door and connects; unpinned, the target resolves to
      `factory/notify/service.py:129` and `factory/notify/service.py:144` —
      localhost port 7233, namespace `ergane` — which on the operator's host is
      the live control plane, and the test proving the door would be the
      incident.

- [ ] T018 [P] [US2] (spec US2-S5, FR-007) Assert the two defences share no `if`,
      no helper and no early return, by exercising each with the other patched
      out.

### Implementation for this story

- [ ] T019 [US2] (FR-007) Add the second defence at a different mutation site
      from the first — a different function, refusing a different subject.
      **Trap 5**: read `factory/roadmap/schedule.py:255` — `_refuse_live_client`
      first. It reads the same environment variable as guard one and the pair is
      still independent, because one refuses to *connect* and the other refuses to
      *act through* a real client it was handed.

- [ ] T020 [US2] (FR-008) Verify independence by construction: the two checks may
      not share an `if`, a helper, or an early return.

- [ ] T021 [US2] (FR-009) Wire the single stand-down to the FR-010 opt-in.
      **Trap 6**: `factory/verify/store.py:378-381` — `connect` has an
      acknowledgment variable and `factory/cli/repo.py:563-565` deliberately does
      not, and says why. Read both and state your choice in the commit body.

### Verification for this story

- [ ] T022 [US2] (spec US2-S3, FR-008) Paste, as committed evidence in the test
      module's docstring, the three-way transcript: guard one removed and the
      suite still refusing, guard two removed and the suite still refusing, both
      removed and the connection attempt reaching 127.0.0.1 port 1. This is the
      2026-08-16 incident re-run with the escape closed.

**Checkpoint**: mutation-testing either guard no longer reaches production.

## Phase 4: User Story 3 — A live tier is opted into, never armed by a credential

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1, FR-011) In
      `tests/test_live_tiers_are_opted_into.py`, set both Telegram credentials
      before the session starts, name no tier, and assert the live Telegram test
      is skipped and the bot constructor was never called. **Setting the variables
      is not enough to reach the stash**: `tests/conftest.py:525` —
      `_isolated_test_store` captures them into `tests/conftest.py:521` before
      deleting them, and `tests/test_live_notify.py:196` — `live_config` reads the
      stash. **Reuse the landed harness rather than inventing one**:
      `tests/test_114_us3_live_tier_summary.py:175` — `scratch_session` runs one
      throwaway pytest session in a subprocess with an environment it builds
      itself, which is the only place "before the session starts" can be arranged
      — an in-process test runs after `_isolated_test_store` has already fired.

- [ ] T024 [P] [US3] (spec US3-S2, FR-012) Name a tier with its credentials absent
      and assert a **failure** naming the missing credential, not a skip. Same
      harness: `tests/test_114_us3_live_tier_summary.py:175` — `scratch_session`,
      whose environment filter at `tests/test_114_us3_live_tier_summary.py:132`
      (the tuple `LIVE_ENV_FRAGMENTS`) already strips every live credential, so
      "absent" is the harness's default rather than something to arrange.

- [ ] T077 [P] [US3] (spec US3-S5, FR-010, trap 21) **Where the opt-in lives.**
      Assert that a module in `factory/` can read the opt-in with no pytest
      plugin loaded and no conftest imported, and that it yields the tier names
      that were set — read it the way `factory/verify/store.py:378-381` —
      `connect` reads its own acknowledgment through `resolve_env_flag`. This is
      the interface US2 wires FR-009's stand-down to; a `-m` expression or a
      pytest command-line option would satisfy every other US3 scenario and be
      invisible to production code.

- [ ] T025 [P] [US3] (spec US3-S3, FR-010) Name a tier with credentials present
      and assert selection. Assert on selection only — do not run the live tier
      from a unit test.

- [ ] T026 [P] [US3] (spec US3-S4, FR-013) Name one tier and assert the other five
      registered `live_*` markers still skip.

### Implementation for this story

- [ ] T029 [US3] (FR-010, trap 21) Add the named opt-in and its parser. One name
      arms one tier; the value is a list of tier names. **The value must be an
      environment variable a module in `factory/` can read at the moment it is
      about to connect**, in the shape `factory/verify/store.py:378-381` —
      `connect` uses through `resolve_env_flag` — not a `-m` marker expression and
      not a pytest command-line option consumed inside `tests/conftest.py`.
      Selecting inside pytest *on top of* that value is fine; the requirement is
      that the value itself is where production code can see it, because FR-009
      wires the choke point's stand-down to this name and the choke point is not
      a pytest plugin.

### Verification for this story

- [ ] T038 [US3] (spec US3-S1, spec US3-S2, FR-011, FR-012) Paste, as committed
      evidence in the new test module's docstring, two scratch-session
      transcripts: credentials exported with no tier named (the Telegram test
      skipping, no send) and the tier named with credentials unset (a failure
      naming the credential). Both are pytest output, not a live send, and both
      come from `tests/test_114_us3_live_tier_summary.py:175` — `scratch_session`,
      which is what makes "exported before the session starts" reproducible.

**Checkpoint**: exporting a credential no longer arms anything.

## Phase 5: User Story 8 — Every live tier moves onto the opt-in

Split out of US3 on 2026-09-08 for size. Merges after US3.

### Tests for this story (write FIRST, must fail)

- [ ] T027 [US8] (spec US8-S1, FR-014) **The enumerating test.** Walk every
      live-tier test module in `tests/` and fail, naming the module, if its skip
      condition reads a credential rather than the opt-in. **Trap 8**: read the
      skip expression, and remember that after 114 the Telegram module reads
      `tests/conftest.py:521` rather than `os.environ`, so a check that only greps
      for `os.environ` reports the one module that pages as clean. **Trap 26**:
      assert the enumerated set is non-empty and contains at least
      `tests/test_live_notify.py` and `tests/test_live_capacity.py` by name — a
      marker-to-module walk that resolves nothing passes forever. Plan trap 26
      names the landed precedent this repository already carries for its own
      sweeps; read it there rather than here, because the module that carries it
      is US1's to edit and this story must not touch it.

- [ ] T028 [P] [US8] (spec US8-S2, FR-025) Assert every `live_*` registration at
      `pyproject.toml:89-96` still contains the literal `auto-skips unless ` after
      the rewrite, mirroring what
      `tests/test_114_us3_live_tier_summary.py:165` — `registered_live_tiers`
      already asserts, so the coupling is stated in this story rather than
      discovered by a red suite.

### Implementation for this story

- [ ] T030 [US8] (FR-011, FR-012) Convert `tests/test_live_notify.py` — change
      `tests/test_live_notify.py:196` — `live_config` to consult the opt-in and to
      fail on a named-but-uncredentialed tier. Leave the stash in
      `tests/conftest.py:525` — `_isolated_test_store` alone: it is 114's
      isolation and removing it re-opens a different hole.

- [ ] T031 [P] [US8] (FR-011, FR-012) Convert the `live_proxy` tier, including
      `tests/test_live_judge.py`, which carries that marker rather than one of its
      own.

- [ ] T032 [P] [US8] (FR-011, FR-012) Convert the `live_epic` tier.

- [ ] T033 [P] [US8] (FR-011, FR-012) Convert the `live_merge` tier.

- [ ] T034 [P] [US8] (FR-011, FR-012) Convert the `live_capacity` tier in
      `tests/test_live_capacity.py`. **Trap 13**: US5 rewrites two tests in this
      same file under FR-026, which is why US5 waits for this story to merge.
      Convert the tier's selection and leave the assertions alone.

- [ ] T035 [P] [US8] (FR-011, FR-012) Convert the `live_onramp` tier — the sixth
      tier, which landed after this spec was drafted and is absent from the
      2026-08-20 task list.

- [ ] T036 [US8] (FR-010, FR-025) Rewrite the six marker registrations at
      `pyproject.toml:89-96` so what follows `auto-skips unless ` names the opt-in
      instead of a credential. **Trap 8**: keep the phrase itself —
      `tests/conftest.py:766` — `_registered_live_tiers` splits on it and
      `tests/test_114_us3_live_tier_summary.py:147` — `registered_live_tiers`
      asserts it is present.

- [ ] T037 [US8] (FR-014) Make T027 pass. **Trap 15**: every tier must still be
      runnable; a tier that can no longer run at all fails T025.

## Phase 6: User Story 4 — A git operation on a husk refuses

### Tests for this story (write FIRST, must fail)

- [ ] T039 [P] [US4] (spec US4-S1, FR-017) In
      `tests/test_husk_never_reaches_the_operator.py`, build a real worktree under
      `tmp_path` and assert both salvage and the teardown archive proceed against
      it.

- [ ] T040 [P] [US4] (spec US4-S2, FR-015, FR-016) **The test that matters
      (trap 1).** Delete *only* `path/.git`, leaving the directory populated, and
      assert the refusal names the path and says it is not a worktree. Assert the
      enclosing repository's `HEAD` and porcelain status are byte-identical before
      and after. Deleting the whole directory instead proves nothing:
      `factory/workgraph/worktree.py:531` — `salvage` already catches that.

- [ ] T041 [P] [US4] (spec US4-S3, FR-015) Assert a path that does not exist
      refuses the same way.

- [ ] T042 [P] [US4] (spec US4-S4, FR-018) Assert both routes refuse: the salvage
      path through `factory/workgraph/worktree.py:511` — `salvage`, and the reset
      path reached from `factory/cli/nouns/build.py:2332` — `_reset_epic` through
      `factory/workgraph/worktree.py:1750` — `_archive_node`.

- [ ] T043 [US4] (spec US4-S5, FR-017) **The control for trap 3.** Build a node
      worktree nested inside an enclosing repository — which is where they live —
      and assert it is recognised as a worktree and the operation proceeds. An
      implementation that asked git to find *a* repository from the path passes
      T040 by accident and fails here.

### Implementation for this story

- [ ] T044 [US4] (FR-015, FR-017) **Trap 1 and trap 2.** Do not write a new
      helper. `factory/workgraph/worktree.py:1037` — `_repo_identity` already
      answers the question, and `factory/workgraph/worktree.py:1020` —
      `_worktree_ownership` shows which half matters: the resolved top level must
      equal `path.resolve()`. Use the repo-free half, because
      `factory/workgraph/worktree.py:511` — `salvage` is handed no `target_repo`
      and `factory/activities/agent_activities.py:783` — `salvage_worktree` has
      none to give it. **The refusal wording splits with the routes.** On the
      `_archive_node` route, which does take a `repo`, reuse
      `factory/workgraph/worktree.py:1088` — `_ownership_refusal` unchanged. On
      the salvage route there is no repository to name, and *both* branches of
      that helper say "the dispatched target repo {repo.resolve()}", so either
      make `repo` optional and drop that clause when it is absent — keeping every
      existing caller's message byte-identical, because they all still pass one —
      or write the salvage wording deliberately, in the same order and with the
      same remedy. Whichever you pick,
      `tests/test_worktree_ownership.py:243` —
      `test_the_refusal_reads_exactly_as_the_operator_will_meet_it` pins the
      dispatch-time text verbatim and must stay green.

- [ ] T045 [US4] (FR-015, FR-016) Gate `factory/workgraph/worktree.py:531` —
      `salvage` with it, before `factory/workgraph/worktree.py:538` — `salvage`
      runs `git add -A`.

- [ ] T046 [US4] (FR-016, FR-018) Gate `factory/workgraph/worktree.py:1766` —
      `_archive_node` with it, before `factory/workgraph/worktree.py:1768` —
      `_archive_node` runs `git add -A`. That is the `build reset` route; leave
      `factory/workgraph/worktree.py:597` and
      `factory/workgraph/worktree.py:1345` alone, since 107 already put its
      ownership check immediately after both.

- [ ] T047 [US4] (FR-015) **Trap 3**: do not touch
      `factory/workgraph/worktree.py:1940` — `_git`. It runs against target-repo
      clones too, and `factory/workgraph/worktree.py:2014` — `_is_ancestor`,
      `factory/workgraph/worktree.py:2060` — `_branch_exists` and
      `factory/workgraph/worktree.py:2071` — `_has_remote` run against paths that
      are legitimately not worktrees.

- [ ] T048 [US4] (FR-005) Grep for the substring T040 asserts on before you settle
      the message.

### Verification for this story

- [ ] T049 [US4] (spec US4-S2, FR-016) Paste, as committed evidence in the test
      module's docstring, the before-and-after `git status --porcelain` and
      `git rev-parse HEAD` of the enclosing repository from the T040 run, showing
      both unchanged. `396611b` is what this evidence exists to make impossible.

**Checkpoint**: a husk refuses on both routes, and the enclosing checkout is
untouched.

## Phase 7: User Story 5 — A probe workflow cannot be counted as an epic

### Tests for this story (write FIRST, must fail)

- [ ] T050 [P] [US5] (spec US5-S1, FR-019) In `tests/test_probe_is_not_an_epic.py`,
      assert that every id the live capacity tier mints through
      `tests/test_live_capacity.py:176` — `_probe_id` wears no `epic-` prefix.

- [ ] T073 [P] [US5] (spec US5-S3, FR-020) Capture the visibility query
      `factory/activities/roadmap_activities.py:772-773` — `_list_open_epics` sends,
      from a fake client that records it, and assert it carries
      `WorkflowType = "EpicWorkflow"` beside its `ExecutionStatus` clause. Assert in
      the same test that the pinned type name equals the type Temporal registers for
      `factory/workgraph/workflow.py:763` — `EpicWorkflow`, so the pin cannot drift
      from the class. Model the query on `factory/escalation/client.py:52-59`.

- [ ] T051 [P] [US5] (spec US5-S2, FR-020, trap 22) Script a listing containing
      `epic-capacity-can-3d2bb231` carrying a probe's workflow type, hand it to the
      **real** reader, and assert the open-epic count excludes it — on the type,
      not on the id, since nobody can rename a workflow already on the namespace.
      Build the executions with `.id` and `.workflow_type`, return them from a fake
      client's `list_workflows`, and run
      `factory/activities/roadmap_activities.py:755` — `_list_open_epics` through
      `ActivityEnvironment(client=fake)`, the way
      `tests/test_live_capacity.py:202` — `_running_ids` already does. **Do not
      bind `factory/activities/roadmap_activities.py:786-789`**: that seam
      defaults to `_list_open_epics` and is read only by
      `factory/activities/roadmap_activities.py:801` — `count_open_epics`, so
      binding it replaces the function whose new filter is the whole of this
      requirement and the test then asserts on the set it supplied itself — a
      test-only diff would pass.

- [ ] T052 [P] [US5] (spec US5-S5, FR-024) The same listing through the second
      reader, `factory/supervision/units.py:1302` — `listed`, and assert it
      excludes the leaked execution too and sends the same clause. One counter
      fixed and one left alone is a half fix (plan trap 4).

- [ ] T053 [US5] (spec US5-S4, FR-021) **The control for trap 4.** Assert a real
      epic id built by `factory/roadmap/workflow.py:195` — `_epic_id_for`, on an
      execution whose workflow type is `EpicWorkflow`, is still counted by both
      readers. This failing open would make the roadmap over-dispatch.

### Implementation for this story

- [ ] T054 [US5] (FR-019) Rename the ids minted at `tests/test_live_capacity.py:176`
      — `_probe_id` so no probe in `tests/test_live_capacity.py` can wear the epic
      prefix. Change what probes are *named*; **trap 4** — do not tighten what an
      epic id is.

- [ ] T055 [US5] (FR-020) The mechanism, in
      `factory/activities/roadmap_activities.py:755` — `_list_open_epics`: add the
      `WorkflowType = "EpicWorkflow"` clause to the query at
      `factory/activities/roadmap_activities.py:772-773` — `_list_open_epics`, pin
      the type name beside the status pinned at
      `factory/activities/roadmap_activities.py:783`, and drop any listed execution
      whose `workflow_type` is not that one, so a supplied listing decides the
      exclusion without a server. **Trap 4**: replacing the bare literal at
      `factory/activities/roadmap_activities.py:775` — `_list_open_epics` with
      `EPIC_ID_PREFIX` (`factory/cli/status.py:114`,
      `factory/cli/nouns/build.py:196`) is a tidy-up worth doing and is *not* the
      fix — both spellings are `"epic-"`. Import the constant; do not edit either
      module, and note in the commit body which one you imported and why the other
      stays.

- [ ] T056 [US5] (FR-024) Apply the same clause and the same type check at
      `factory/supervision/units.py:1302` — `listed`, which already imports
      `EPIC_ID_PREFIX` at `factory/supervision/units.py:1292` — `_open_epics`.

- [ ] T074 [US5] (spec US5-S6, FR-026) **Trap 17.** Rewrite the two live tests that
      assert the inverse of this story: `tests/test_live_capacity.py:260` —
      `test_capacity_read_finds_open_epic_workflows_and_excludes_others` and
      `tests/test_live_capacity.py:331` —
      `test_capacity_read_excludes_continued_as_new_chain`. Keep the probes, flip
      the assertions: the narrowed read counts none of them, while a direct
      `client.list_workflows('ExecutionStatus = "Running"')` still finds the same
      ids, so the tier keeps proving the status grammar it was written for. Do not
      register a probe under the production workflow type to save the old positive
      case — `tests/test_live_capacity.py:168` — `_probe_worker` polls the
      production task queue. Leave `tests/test_live_capacity.py:377` —
      `test_capacity_read_fails_under_shipped_uppercase_spelling` alone; it patches
      the provider with its own query.

- [ ] T057 [US5] (FR-021) Make T053 pass.

### Verification for this story

- [ ] T058 [US5] (spec US5-S2, spec US5-S5, FR-020, FR-024) Paste, as committed
      evidence in the test module's docstring, the two counts computed from one
      supplied listing that contains `epic-capacity-can-3d2bb231` under a probe's
      workflow type and a real epic id under `EpicWorkflow` — one count per reader —
      showing the probe excluded and the epic kept, and beside them the query string
      each reader sent.

**Checkpoint**: the leaked probe stops consuming a slot in both readers, without
anyone deleting it first, and the live tier asserts that rather than its opposite.

## Phase 8: User Story 6 — The last seven callers, and the test that keeps them there

### Tests for this story (write FIRST, must fail)

- [ ] T060 [US6] (spec US6-S1, FR-023) One case per migrated caller, seven small
      cases: with the choke point's seam bound, assert each of
      `factory/doctor/probes.py:491` — `_gather_async`,
      `factory/doctor/probes.py:603` — `_closed_epics_from_temporal`,
      `factory/controlplane/verify.py:193` — `_temporal_client_factory`,
      `factory/notify/service.py:1048` — `main`, `factory/worker.py:351` — `main`,
      `factory/supervision/deploy.py:749` — `asked` and
      `factory/roadmap/schedule.py:165` — `_default_schedule_client` obtains its
      client from the choke point **and still resolves its own target first**
      (trap 19). Add the eighth case **trap 18** asks for: with
      `PYTEST_CURRENT_TEST` set, `factory/roadmap/schedule.py:144` —
      `_default_schedule_client` still raises `ScheduleUnavailable` with its own
      message, before the choke point is asked at all.

- [ ] T078 [P] [US6] (spec US6-S2, FR-023, trap 19) **The landed guard.** Walk the
      AST of each of the seven migrated modules and assert each still imports a
      resolver entry point from `factory.controlplane.resolve` and still calls it
      before asking the choke point — the same walk
      `tests/test_declared_temporal.py:423` —
      `test_every_connect_site_reaches_the_one_resolver` performs over
      `tests/test_declared_temporal.py:392` (the tuple `_RESOLVER_SITES`). Assert
      specifically that `factory/controlplane/verify.py:193` —
      `_temporal_client_factory` still calls `temporal_target_for` and that
      `factory/supervision/deploy.py:749` — `asked` still reads `self._address`
      and `self._namespace`. Do not edit `tests/test_declared_temporal.py`.

- [ ] T081 [US6] (spec US6-S3, FR-027, FR-028, trap 23) **The landed
      floor-fakes, US6's two.** Rebind
      `tests/test_doctor_probes.py:295` — `fake_temporal` to the seam the choke
      point declares — one line, and it serves both probe sites. Then carry
      `tests/test_declared_temporal.py:264` — `dialed` forward the same way, and
      with it the only two tests in this repository that need a **real dial**
      through `factory/controlplane/verify.py:193` — `_temporal_client_factory`
      under pytest: `tests/test_declared_temporal.py:274` —
      `test_the_verify_probe_dials_the_address_the_worker_would_use` and
      `tests/test_declared_temporal.py:303` —
      `test_the_probe_snapshot_names_the_server_it_actually_dialed`. Each must
      still enter that function and still assert the address and namespace that
      were dialed; only what they bind changes. **This is the one edit permitted
      anywhere in that file** (FR-028): `tests/test_declared_temporal.py:332`
      (the tuple `_CONNECT_SITES`), `tests/test_declared_temporal.py:392` (the
      tuple `_RESOLVER_SITES`), `tests/test_declared_temporal.py:395` —
      `test_no_connect_site_keeps_its_own_copy_of_the_temporal_contract` and
      `tests/test_declared_temporal.py:423` —
      `test_every_connect_site_reaches_the_one_resolver` stay exactly as they
      are, and no test function is removed. The earlier draft of this plan asked
      for an empty diff on this file *and* for T065's migration; that pair had no
      legal implementation, which is why the exemption is legislated here rather
      than discovered by a node.

### Implementation for this story

- [ ] T063 [P] [US6] (FR-023, trap 19) Migrate `factory/doctor/probes.py:491` —
      `_gather_async`, keeping its `resolve_temporal_target()` call at
      `factory/doctor/probes.py:487` and the lazy import at
      `factory/doctor/probes.py:483` that serves it.

- [ ] T064 [P] [US6] (FR-023, trap 19) Migrate `factory/doctor/probes.py:603` —
      `_closed_epics_from_temporal`, keeping its `resolve_temporal_target()` call
      at `factory/doctor/probes.py:599` and the lazy import at
      `factory/doctor/probes.py:597`. Both of this module's resolver imports serve
      a connect site, so dropping either takes the module out of the guard's
      reach.

- [ ] T065 [P] [US6] (FR-023, trap 19, trap 20) Migrate
      `factory/controlplane/verify.py:193` — `_temporal_client_factory`: replace
      only the `Client.connect` call, and pass in the target this function already
      resolved. It **must** keep `temporal_target_for(config,
      source=_DECLARED_SOURCE)` at `factory/controlplane/verify.py:192` and the
      import at `factory/controlplane/verify.py:32` — that is 048-US4's
      config-first precedence, recorded in its own docstring and pinned by
      `tests/test_declared_temporal.py:274` —
      `test_the_verify_probe_dials_the_address_the_worker_would_use`, which calls
      `_temporal_client_factory(config.temporal)` and asserts which address was
      dialed. **That test dials for real, under pytest, through a fake installed
      at `Client.connect`** — after this migration the choke point refuses before
      the fake is reached, so T081 rebinds it and its sibling in the same story
      (FR-028, trap 23). Do not attempt this migration without doing T081 as
      well; and do not touch anything else in that file. Preserve the seam its
      landed tests bind by name, and leave
      `factory/controlplane/verify.py:724` — `gather` alone.

- [ ] T066 [P] [US6] (FR-023, trap 19) Migrate
      `factory/notify/service.py:1048` — `main`, keeping the lazy import its
      comment explains: this module *defines* the two constants the resolver
      reads, so a module-scope import would be circular. Keep the
      `resolve_temporal_target()` call at `factory/notify/service.py:1047` and its
      import at `factory/notify/service.py:1045`; this module is the tenth entry
      in `tests/test_declared_temporal.py:392` (the tuple `_RESOLVER_SITES`).

- [ ] T068 [US6] (FR-023, trap 20) Migrate
      `factory/supervision/deploy.py:749` — `asked`. This site is absent from the
      2026-08-20 table; it is nested inside `_call` behind a lazy import, which is
      why only a tree walk finds it. It resolves nothing at the connect: it
      reads `self._address` and `self._namespace`, set once at
      `factory/supervision/deploy.py:720` from `resolve_temporal_target()`, so
      hand those two values to the choke point and change nothing else. Its
      `except (RPCError, RuntimeError, OSError)` branch exists because temporalio
      raises a bare `RuntimeError` on a dead port — keep that translation.
      **Trap 19**: this module is *not* in `tests/test_declared_temporal.py:392`
      (the tuple `_RESOLVER_SITES`) — six of the seven callers here are, and this
      one is not — so keep its lazy resolver import at
      `factory/supervision/deploy.py:716` because FR-023 requires it, not because
      the landed guard would catch you.

- [ ] T075 [US6] (FR-023, trap 18, trap 19) **Trap 18.** Migrate
      `factory/roadmap/schedule.py:165` — `_default_schedule_client` and the lazy
      `temporalio` import at `factory/roadmap/schedule.py:146` —
      `_default_schedule_client` that serves it. Keep the
      `resolve_temporal_target()` call at `factory/roadmap/schedule.py:153` —
      `_default_schedule_client` and its import at
      `factory/roadmap/schedule.py:151` — `_default_schedule_client`: this module
      is one of the ten the landed guard walks, and that is its only resolver
      import. Take the connect and nothing else: `factory/roadmap/schedule.py:156-162` keeps
      refusing under `PYTEST_CURRENT_TEST` with its own message, and
      `factory/roadmap/schedule.py:255` — `_refuse_live_client` is not touched. Keep
      the `except Exception` translation at `factory/roadmap/schedule.py:166-169` —
      `_default_schedule_client` around the call: `tests/test_ergane_init_schedule.py:218`
      — `test_the_default_client_refuses_to_connect_from_a_test` and
      `tests/test_init_schedule_precondition.py:397` —
      `test_nothing_in_this_phase_can_reach_a_real_temporal` are landed contracts
      that assert on it.

## Phase 9: User Story 9 — The worker's own entry, and the door that is now the only door

Split out of US6 on 2026-09-08 for size. Merges after US6, last of the client
work, because its closing assertion is only true once every migration lands.

### Tests for this story (write FIRST, must fail)

- [ ] T059 [P] [US9] (spec US9-S1, FR-003) In
      `tests/test_no_second_client_constructor.py`, walk `factory/**/*.py` from
      the package root and assert exactly one module *constructs* a client, failing
      with the name of any other file. Decide on parsed code, not on raw text:
      `factory/controlplane/verify.py:732` — `gather` carries the literal inside a
      comment that must survive, so a substring walk flags a file that has already
      been migrated. Read the tree, never a list — this spec was drafted naming nine
      sites and the tree already held eleven.

- [ ] T061 [P] [US9] (spec US9-S2, FR-006) Assert `factory/worker.py:351` — `main`
      is not refused with `PYTEST_CURRENT_TEST` unset. Bind the seam; do not
      connect.

- [ ] T062 [P] [US9] (spec US9-S3, FR-006) Assert that merely importing
      `factory/worker.py` attempts no connection — the choke point's seam is never
      called on import. **Trap 9**: the guard keys on the test process, never on
      the caller.

### Implementation for this story

- [ ] T067 [US9] (FR-023, FR-006, trap 19) Migrate `factory/worker.py:351` —
      `main`, keeping the `resolve_temporal_target()` call at
      `factory/worker.py:339` and the module-scope import at
      `factory/worker.py:80`. **Trap 9**: the worker is allowed to reach
      production; a test that imports it is not.

- [ ] T069 [US9] (FR-003) Make T059 pass by leaving no module but the choke point
      constructing a client. Re-enumerate from the tree; do not trust this list
      either, and do not reflow the comment at
      `factory/controlplane/verify.py:732` — `gather` to get past a test that should
      have parsed the code.

### Verification for this story

- [ ] T070 [US9] (spec US9-S1, FR-003) Paste, as committed evidence in the test
      module's docstring, the output of
      `grep -rn "Client.connect" factory/ --include=*.py` over the finished tree —
      two lines, the choke point's call and the surviving comment at
      `factory/controlplane/verify.py:732` — `gather` — beside the same grep taken
      **on this story's own base before its migration**, which returns *eight*
      calls and that comment: the seven this story migrates plus the choke
      point's own, US1 having already merged its four. Eleven was the count
      before US1; pasting it here means you pasted a transcript you did not run.
      Paste beside them `git diff -- tests/test_declared_temporal.py`, which must
      touch `tests/test_declared_temporal.py:264` — `dialed` and the two dial
      tests T081 carries forward and **nothing else** — never the two tuples and
      never either AST guard (trap 19, FR-028).

**Checkpoint**: exactly one module constructs a client, the only other occurrence
of the literal is a comment, and the test that says so parses the tree.


## Verification

The declared `test` gate must be green for every story before it is opened. Then
the operator runs plan.md's numbered list, which nothing here may attempt: step 3
re-runs the incident that put five live schedules on the production namespace,
and step 6 aims a destructive verb at a husk.

- [ ] T071 The declared `test` gate green on each story's branch.
- [ ] T072 The operator's sequence, plan.md steps 1 through 11, in order — the
      capacity tier run at step 8, which the declared gate skips, the landed
      resolver guard at step 9 with its scoped diff, the seven floor-fake modules
      at step 10 with their collected count, and ending at step 11 with `rm
      specs/074-a-test-cannot-reach-the-operators-floor/workgraph.json` or a
      re-derivation, confirming six nodes, **before** any flip to `ready` — the
      roadmap dispatches a ready spec itself and `ergane build start` reads the
      compiled graph off disk. No refinement run has been permitted to write or
      delete that file.
