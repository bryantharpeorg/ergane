# Tasks: a test cannot reach the operator's floor

**Spec**: `specs/074-a-test-cannot-reach-the-operators-floor/spec.md`
**Plan**: `specs/074-a-test-cannot-reach-the-operators-floor/plan.md`

Read the plan's traps before the first task. Four of them decide whether an
attempt lands: trap 1 (the husk defect is the *wrong* check, not a missing one),
trap 2 (do not put the worktree check inside `_git`), trap 5 (US2 is not a second
environment variable) and trap 7 (a substring two refusals share is how a test
passes for the wrong reason).

## Phase 1: User Story 1 — One place builds a real client

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_one_client_chokepoint.py`, walk
      `factory/**/*.py` and assert exactly one module contains `Client.connect`,
      failing with the name of any other file that does. Read the tree from the
      package root, not from a hardcoded list — the point is that it stays true
      as the tree grows.
- [ ] T002 [P] [US1] (spec US1-S3) Assert that with `PYTEST_CURRENT_TEST` set the
      choke point refuses, and that the message contains the address, the
      namespace and the name of the seam to bind. Model the message on
      `factory/roadmap/schedule.py:153-162`.
- [ ] T003 [P] [US1] (spec US1-S4) **The control for trap 7.** Assert the choke
      point's refusal and one unrelated precondition refusal are distinguishable:
      each must contain a substring the other does not, and the test asserts on
      the unique one.
- [ ] T004 [P] [US1] (spec US1-S5) Assert `factory/worker.py`'s start-up path
      obtains its client through the choke point and is not refused when
      `PYTEST_CURRENT_TEST` is unset. Bind the seam; do not connect.
- [ ] T005 [US1] (spec US1-S2) One assertion per migrated caller: with the seam
      bound to a fake, each of the nine behaves as it does today. Nine small
      cases, not one loop — a loop that skips a caller looks identical to a loop
      that covers it.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-004) Create the choke point module. One function
      that resolves the target, refuses under `PYTEST_CURRENT_TEST` naming
      address, namespace and seam, then connects. Copy the refusal shape from
      `factory/roadmap/schedule.py:153-162` — it is the only message in the tree
      that names all three.
- [ ] T007 [US1] (FR-001) Declare the seam beside it, in the idiom of
      `factory/cli/repo.py:92-93`.
- [ ] T008 [P] [US1] (FR-002) Migrate `factory/workgraph/cli.py:817`.
- [ ] T009 [P] [US1] (FR-002) Migrate `factory/cli/nouns/__init__.py:54`. This is
      the `_connect()` behind `factory/cli/nouns/build.py:896 _reset_epic`, so
      check US4 has not moved it first.
- [ ] T010 [P] [US1] (FR-002) Migrate `factory/cli/roadmap.py:188`.
- [ ] T011 [P] [US1] (FR-002) Migrate `factory/cli/repo.py:84`, inside
      `_open_client` at `factory/cli/repo.py:79-89`. Keep the existing seam at
      `factory/cli/repo.py:92-93` working; tests bind it.
- [ ] T012 [P] [US1] (FR-002) Migrate `factory/doctor/probes.py:491`.
- [ ] T013 [P] [US1] (FR-002) Migrate `factory/doctor/probes.py:603`.
- [ ] T014 [P] [US1] (FR-002) Migrate `factory/controlplane/verify.py:185`.
- [ ] T015 [P] [US1] (FR-002) Migrate `factory/notify/service.py:801`.
- [ ] T016 [US1] (FR-002, FR-006) Migrate `factory/worker.py:283` inside
      `async def main()` at `factory/worker.py:274`. **Trap 9**: the worker is
      allowed to reach production; a test that imports it is not. The guard keys
      on the test process, never on the caller.
- [ ] T017 [US1] (FR-005) Grep the tree for the substring each new refusal's test
      asserts on, and change any that collides. Record what you grepped in the
      commit body.
- [ ] T018 [US1] (FR-003) Make T001 pass by leaving no other `Client.connect`.
      Re-enumerate; the plan's list of nine was taken at `a58ec93`.

**Checkpoint**: `Client.connect` appears in exactly one file, and a test process
cannot get a client from it.

## Phase 2: User Story 2 — Disabling one guard is not enough

Depends on Phase 1.

### Tests for this story (write FIRST, must fail)

- [ ] T019 [P] [US2] (spec US2-S1) In `tests/test_two_independent_guards.py`,
      neutralise the `PYTEST_CURRENT_TEST` refusal the way a mutation would —
      patch its condition to a constant false — and assert the second defence
      still refuses, naming itself.
- [ ] T020 [P] [US2] (spec US2-S2) The mirror: neutralise the second defence and
      assert the `PYTEST_CURRENT_TEST` refusal still fires.
- [ ] T021 [US2] (spec US2-S3) **The control for trap 5.** Neutralise both and
      assert a connection is attempted. Point it at `127.0.0.1:1` and assert on
      the connection error — `temporalio` raises `RuntimeError` on a dead port
      (plan trap 8), so do not assert on a typed transport exception. A pair that
      cannot both be removed is one guard wearing a disguise, and this is the only
      test that can tell.
- [ ] T022 [P] [US2] (spec US2-S4) Assert that with the named opt-in of FR-010
      present, both defences stand down and a connection is attempted.

### Implementation for this story

- [ ] T023 [US2] (FR-007) Add the second defence. It must not read the same
      signal as the first: trap 5. Read `factory/roadmap/schedule.py:22-26` for
      the worked pair — refuse to *connect*, and separately refuse to *act
      through* a real client.
- [ ] T024 [US2] (FR-008) Verify independence by construction: the two checks may
      not share an `if`, a helper, or an early return.
- [ ] T025 [US2] (FR-009) Wire the single stand-down to the FR-010 opt-in.
      **Trap 6**: `factory/verify/store.py:279-281` has an acknowledgment
      variable and `factory/cli/repo.py:468-470` deliberately does not, and says
      why. Read both and state your choice in the commit body.

**Checkpoint**: mutation-testing either guard no longer reaches production.

## Phase 3: User Story 3 — A live tier is opted into, never armed by a credential

Independent of Phases 1, 2, 4 and 5.

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US3] (spec US3-S1) In `tests/test_live_tiers_are_opted_into.py`,
      set both Telegram credentials with no tier opted in and assert the live
      Telegram test is skipped and nothing is sent.
- [ ] T027 [P] [US3] (spec US3-S2) Opt into a tier with its credentials absent
      and assert a **failure** naming the missing credential, not a skip.
- [ ] T028 [P] [US3] (spec US3-S3) Opt in with credentials present and assert
      selection. Assert on selection only — do not run the live tier from a unit
      test.
- [ ] T029 [P] [US3] (spec US3-S4) Opt into one tier and assert the other four
      still skip.
- [ ] T030 [US3] (spec US3-S5) **The enumerating test.** Walk every live-tier
      test module in `tests/` and fail, naming the module, if its skip condition
      reads a credential rather than the opt-in. **Trap 8**: read the skip
      expression, not the marker — nothing passes `-m`, so markers prove nothing.

### Implementation for this story

- [ ] T031 [US3] (FR-010) Add the named opt-in and its parser. One name arms one
      tier; the value is a list of tier names.
- [ ] T032 [P] [US3] (FR-011, FR-012) Convert `tests/test_live_notify.py` to skip
      on the opt-in and fail on a named-but-uncredentialed tier. Its module
      docstring claims `-m live_telegram` selects it — make that true or delete
      the claim (plan trap 8).
- [ ] T033 [P] [US3] (FR-011, FR-012) Convert the `live_proxy` tier.
- [ ] T034 [P] [US3] (FR-011, FR-012) Convert the `live_epic` tier.
- [ ] T035 [P] [US3] (FR-011, FR-012) Convert the `live_merge` tier.
- [ ] T036 [P] [US3] (FR-011, FR-012) Convert the `live_capacity` tier, including
      `tests/test_live_capacity.py:169`.
- [ ] T037 [US3] (FR-010) Correct the five marker descriptions at
      `pyproject.toml:72-78`. Each currently says "auto-skips unless
      *`<credential>`* is set", which is the defect written into the manifest.
- [ ] T038 [US3] (FR-014) Make T030 pass. **Trap 14**: every tier must still be
      runnable; a tier that can no longer run at all fails T028.

**Checkpoint**: exporting a credential no longer arms anything.

## Phase 4: User Story 4 — A git operation on a husk refuses

Independent of Phases 1, 2, 3 and 5.

### Tests for this story (write FIRST, must fail)

- [ ] T039 [P] [US4] (spec US4-S1) In `tests/test_husk_never_reaches_the_operator.py`,
      build a real worktree under `tmp_path` and assert a git operation aimed at
      it proceeds.
- [ ] T040 [P] [US4] (spec US4-S2) **The test that matters (trap 1).** Delete
      *only* `path/.git`, leaving the directory populated, and assert the refusal
      names the path and says it is not a worktree. Assert the enclosing
      repository's `HEAD` and porcelain status are byte-identical before and
      after. Deleting the whole directory instead proves nothing —
      `factory/workgraph/worktree.py:401-402` already catches that.
- [ ] T041 [P] [US4] (spec US4-S3) Assert a path that does not exist refuses the
      same way.
- [ ] T042 [P] [US4] (spec US4-S4) Assert both routes refuse: the salvage path at
      `factory/workgraph/worktree.py:381` and the reset path reached from
      `factory/cli/nouns/build.py:886`.
- [ ] T043 [US4] (spec US4-S5) **The control for trap 3.** Build a node worktree
      nested inside an enclosing repository — which is where they live — and
      assert it is recognised as a worktree. An implementation that used
      `git -C <path> rev-parse --show-toplevel` passes T040 by accident and fails
      here.

### Implementation for this story

- [ ] T044 [US4] (FR-015, FR-017) Write `require_live_worktree(path)` in
      `factory/workgraph/worktree.py`: `path/.git` must exist and resolve into
      this repository's gitdir. **Trap 3**: do not ask git to find a repository
      from `path` — from inside a husk it finds the operator's checkout and
      returns success.
- [ ] T045 [US4] (FR-015, FR-016) Replace the `is_dir()` gate at
      `factory/workgraph/worktree.py:401-402` with it, before
      `factory/workgraph/worktree.py:408`'s `git add -A`.
- [ ] T046 [US4] (FR-018) Apply it on the reset route. Enumerate the node-path
      `is_dir()` gates — `factory/workgraph/worktree.py:460`, `:912`, `:1018` and
      the siblings at `:329`, `:1082`, `:1121`, `:1198` — and convert the ones
      that precede a git invocation. FR-015 is not about all nine.
- [ ] T047 [US4] (FR-015) **Trap 2**: do not touch
      `factory/workgraph/worktree.py:1234-1245`. `_git` runs against target-repo
      clones too, and `:1286`, `:1305`, `:1316` run against paths that are
      legitimately not worktrees.
- [ ] T048 [US4] (FR-005) Grep for the substring T040 asserts on before you settle
      the message.

**Checkpoint**: a husk refuses, and the operator's checkout is untouched.

## Phase 5: User Story 5 — A probe workflow cannot be counted as an epic

Independent of Phases 1–4.

### Tests for this story (write FIRST, must fail)

- [ ] T049 [P] [US5] (spec US5-S1) In `tests/test_probe_is_not_an_epic.py`,
      assert a probe-created workflow id does not match the grammar
      `_list_open_epics` recognises.
- [ ] T050 [P] [US5] (spec US5-S2) Supply a listing containing
      `epic-capacity-can-3d2bb231` and assert the open-epic count excludes it.
      Bind `factory/activities/roadmap_activities.py:510 _open_epics_provider`.
- [ ] T051 [US5] (spec US5-S3) **The control for trap 4.** Assert a real epic id
      built by `factory/roadmap/workflow.py:194` is still counted. This failing
      open would make the roadmap over-dispatch.

### Implementation for this story

- [ ] T052 [US5] (FR-019) Rename the probe's workflow id so it cannot wear the
      epic prefix. Change what probes are *named*; **trap 4** — do not tighten
      what an epic id is.
- [ ] T053 [US5] (FR-020) Exclude non-epic ids at
      `factory/activities/roadmap_activities.py:496`, replacing the bare literal
      with the constant that already exists twice
      (`factory/cli/status.py:107`, `factory/cli/nouns/build.py:125`). Note in the
      commit body which one you imported and why the other stays.
- [ ] T054 [US5] (FR-021) Make T051 pass.

**Checkpoint**: the leaked probe stops consuming a slot without anyone deleting
it first.

## Verification — operator-run, not part of any story

These are the spec's Success Criteria. They are the operator's, not the judge's,
and no agent should attempt them: SC-003 re-runs the incident that put five live
schedules on the production namespace, and SC-006 aims a destructive verb at a
husk.

- [ ] T055 (SC-001) Ten refusals, none reaching the network.
- [ ] T056 (SC-002) `grep -rn "Client.connect" factory/ --include=*.py` — one file.
- [ ] T057 (SC-003) The M12 re-run, with `temporal schedule list` and
      `temporal workflow list` before and after.
- [ ] T058 (SC-004) Credentials exported, no tier named, no message sent.
- [ ] T059 (SC-005) Tier named, credentials absent, failure names the credential.
- [ ] T060 (SC-006) Husk refusal for both routes, with `git status --porcelain`
      and `git rev-parse HEAD` unchanged.
- [ ] T061 (SC-007) A listing containing `epic-capacity-can-3d2bb231` and a count
      that excludes it.
