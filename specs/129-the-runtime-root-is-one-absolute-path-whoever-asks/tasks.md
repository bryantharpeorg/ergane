# Tasks: the runtime root is one absolute path, whoever asks

Read `plan.md` before starting. Trap 1 is the reason this defect has survived two
full rounds of fixes: two subsystems already hand-rolled repo-anchored resolvers
rather than correct the shared one, and a third local workaround would make the
tree worse. Trap 3 and trap 5 are the two wrong fixes that go green: anchoring
inside `resolve_env_path` (`factory/env.py:47` — `resolve_env_path`) re-anchors
twelve unrelated paths and breaks `runtime_root_prefixes`
(`factory/verify/diffcheck.py:287` — `runtime_root_prefixes`), and
`git rev-parse --show-toplevel` from inside a node worktree answers the worktree.
Trap 4 warns that the committed tests `chdir` **in order to** exercise the
behaviour this spec removes — they are the defect, written down and green — and
that the same two files also hold nine assertions 043 landed which must survive
untouched. Trap 13 is the enumeration that decides whether this spec fixes the
operator finding or half-fixes it, and it is split across two stories: US2 owns
the worker's three derivations, US5 owns the operator's seven, and US5's four
verification derivations are the reproduction the finding was filed on. Traps 17
and 18 are US4's: the dispatch half and the salvage half of one node must resolve
the same root, and the field that makes that possible has to be optional or every
in-flight epic fails on replay. Trap 20 is US1's and is the one that decides
whether US1 merges green: FR-009's refusal reaches seven operator verbs the
moment the resolver starts refusing, and three of them are held by 043's own
committed tests. Trap 21 is US4's and is the reason this spec is not a half fix:
the 4.2 GB the declared finding measured comes from a path no runtime-root read
touches, and the fix does not go in the workflow.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — The root is absolute and anchored on its repository

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 14) With no runtime-root override
      set — the session fixture `_isolated_test_store` (`tests/conftest.py:525` —
      `_isolated_test_store`) sets both names for every test, so the delenv is an
      obligation — and the repository named by the caller, assert the root
      resolves to the same absolute repository-anchored path from the repository
      root, from a subdirectory of it, and from a directory outside it, changing
      the working directory between the three calls.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 3) Given a **relative** override
      such as `ERGANE_ROOT=.ergane` and a named repository, assert the resolved
      root equals that repository's `.ergane` — assert the whole path, from a
      working directory that is not the repository — **and** assert
      `runtime_root_prefixes` (`factory/verify/diffcheck.py:287` —
      `runtime_root_prefixes`) still returns that override's first path segment,
      which it cannot if the anchoring was added inside `resolve_env_path`
      (`factory/env.py:47` — `resolve_env_path`). The first assertion fails a
      `.resolve()` fix; the second fails a correct fix put in the wrong function.
      This arm never fires in local development because `scripts/ergane-env.sh`
      supplies an absolute path.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) **The control.** Given an absolute
      override, assert it is returned unchanged and still wins over the
      repository-anchored default. This story removes no operator control.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, trap 2) Given a repository whose runtime
      root does not exist, assert that *reading* it leaves the repository's
      directory listing unchanged, and that the explicit ensure path still creates
      it. Deleting the mkdir at `factory/workgraph/worktree.py:239` outright makes
      the suite green and the factory unable to bootstrap.
- [ ] T005 [P] [US1] (spec US1-S5, FR-009) Given no override, no repository named
      by the caller, and a working directory inside no git repository, assert the
      resolver refuses with a message naming what it was asked, and that the
      temporary directory still contains no `.ergane`.
- [ ] T006 [P] [US1] (spec US1-S6, FR-001, trap 5) Given a working directory inside
      a **real linked git worktree** of the repository, assert the resolved root is
      the owning clone's, not the worktree's. A `tmp_path` with a hand-written
      `.git` file does not reproduce this; create the worktree with git.
- [ ] T007 [P] [US1] (spec US1-S7, FR-016, traps 1 and 8) Assert the new
      environment-blind name choice answers a **child of the repository it is
      handed**, with `ERGANE_ROOT` set to a directory outside that repository, and
      creates nothing — across all three precedence arms: `.ergane/` wins when both
      exist, a lone `.factory/` is honoured, neither means `.ergane/`. This is the
      entry point US3 calls and `--clean-runtime` acts on, so a version that
      consults the environment is the 2026-08-14 deletion waiting to happen.
- [ ] T008 [US1] (FR-003, FR-009, trap 4) **Retarget, do not rewrite.** In
      `tests/test_runtime_root.py` and `tests/test_runtime_root_findings.py`,
      change only the cwd-relative *setup* so each test names its repository —
      extend `_unset_factory_root` (`tests/test_runtime_root.py:43` —
      `_unset_factory_root`) rather than replacing the files. Three bodies change:
      `test_resolve_no_root_creates_ergane` (`tests/test_runtime_root.py:60` —
      `test_resolve_no_root_creates_ergane`) becomes an assertion about the
      explicit ensure, and
      `test_resolve_legacy_only_uses_it_and_names_migration`
      (`tests/test_runtime_root.py:71` —
      `test_resolve_legacy_only_uses_it_and_names_migration`) and
      `test_resolve_new_wins_when_both_exist` (`tests/test_runtime_root.py:90` —
      `test_resolve_new_wins_when_both_exist`) keep their assertions and change
      only how the repository is named. **Nine assertions must not change**: the
      four contract tests at `tests/test_runtime_root_findings.py:153`,
      `tests/test_runtime_root_findings.py:179`,
      `tests/test_runtime_root_findings.py:199` and
      `tests/test_runtime_root_findings.py:222`, and 043's five migrate-verb tests
      spanning `tests/test_runtime_root.py:253-378`. Not `[P]`: this is the shared
      fixture every other task in this phase reads. A wholesale rewrite of these
      two files is ~46 KB of diff on its own — see plan.md § Sizing — and deletes
      the one guarantee that would have caught FR-013's split-state hazard.
- [ ] T009 [US1] (FR-003, FR-009, trap 4) Re-point the named control
      `test_the_resolver_would_have_created_the_runtime_root`
      (`tests/test_ergane_status.py:1047` —
      `test_the_resolver_would_have_created_the_runtime_root`) at the new explicit
      ensure rather than deleting it — it delenvs both root variables, chdirs to a
      non-repo tmp dir and asserts the resolver *creates*, so FR-003 and FR-009
      kill it twice over, and the "nothing was created" test above it loses its
      control if it goes. Then correct the two stale docstrings that state the
      create-and-cwd behaviour as fact:
      `test_check_does_not_create_the_runtime_root_it_is_judging`
      (`tests/test_ergane_init_check.py:637` —
      `test_check_does_not_create_the_runtime_root_it_is_judging`) and the comment
      block at `tests/test_clean_runtime_names_the_root_it_did_not_clean.py:444`.
- [ ] T060 [P] [US1] (spec US1-S8, FR-019, trap 20) From a working directory
      inside no git repository, with both root variables deleted, assert each of
      the seven operator reads answers the process-relative name choice and
      creates nothing rather than raising FR-009's refusal: `_store_path`
      (`factory/cli/doctor.py:65` — `_store_path`), `_store_path`
      (`factory/doctor/cli.py:50` — `_store_path`), `_check_fixes`
      (`factory/cli/nouns/spec.py:1231` — `_check_fixes`), `_evidence_stores`
      (`factory/doctor/probes.py:147` — `_evidence_stores`), the two
      `_gather_async` reads at `factory/doctor/probes.py:285` and
      `factory/doctor/probes.py:393`, and `migrate_runtime_root_command`
      (`factory/cli/repo.py:613` — `migrate_runtime_root_command`). Then run
      043's own tests unchanged as the second half of the proof:
      `tests/test_runtime_root_findings.py:135`,
      `tests/test_runtime_root_findings.py:153`,
      `tests/test_runtime_root_findings.py:179`, the five migrate-verb tests at
      `tests/test_runtime_root.py:253-378`, and
      `test_stale_worktree_gather_from_sync_context`
      (`tests/test_doctor_probes.py:390` —
      `test_stale_worktree_gather_from_sync_context`) — all five of those files
      construct exactly this state, three of them through the **autouse**
      `_chdir_tmp` (`tests/test_runtime_root_findings.py:65` — `_chdir_tmp`).

### Implementation for this story

- [ ] T010 [US1] (FR-016, traps 1 and 8) In `factory/workgraph/worktree.py`, lift
      the name choice at `factory/workgraph/worktree.py:218-240` into an
      **environment-blind** function of one argument — the repository — that
      returns a child of it and creates nothing. `.ergane/` wins, a lone
      `.factory/` is honoured, neither means `.ergane/`. `chosen_runtime_root` is
      a serviceable name; the blindness and the absent mkdir are the requirement.
      Leave the one-time legacy `DeprecationWarning` in `resolve_factory_root`
      (`factory/workgraph/worktree.py:191` — `resolve_factory_root`), which
      `test_resolve_legacy_only_uses_it_and_names_migration`
      (`tests/test_runtime_root.py:71` —
      `test_resolve_legacy_only_uses_it_and_names_migration`) asserts on and which
      `runtime_root_for` (`factory/cli/repo.py:418` — `runtime_root_for`) has
      never emitted. Without this function US3 has nothing to consolidate onto
      that is safe for `--clean-runtime` to act on.
- [ ] T011 [US1] (FR-001, FR-003, FR-009, traps 2 and 5) In the same module, give
      `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
      `resolve_factory_root`) an optional repository parameter, make it return an
      absolute path anchored on the **owning clone** by calling T010's function
      with that repository, and split "answer the question" from "ensure the
      directory exists" so the mkdir at `factory/workgraph/worktree.py:239` moves
      to the explicit ensure. Reuse `_repo_identity`
      (`factory/workgraph/worktree.py:1037` — `_repo_identity`) and `_owning_clone`
      (`factory/workgraph/worktree.py:1072` — `_owning_clone`) for discovery rather
      than shelling out again; refuse when neither a named repository nor an
      owning clone is available. `DEFAULT_RUNTIME_ROOT`
      (`factory/workgraph/worktree.py:93`) stays the name; only its resolution
      changes. The legacy-name precedence at
      `factory/workgraph/worktree.py:224-230` is unchanged.
- [ ] T012 [US1] (FR-002, trap 3) Anchor a **relative** override inside
      `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
      `resolve_factory_root`), applied to the value `resolve_env_path` returned at
      `factory/workgraph/worktree.py:211`. An absolute value is returned untouched.
      **Do not edit `factory/env.py:79` or `factory/env.py:88`**: that helper is
      handed no repository, serves fifteen call sites of which twelve are not
      runtime-root reads, and `runtime_root_prefixes`
      (`factory/verify/diffcheck.py:287` — `runtime_root_prefixes`) skips an
      absolute override and reads `override.parts[0]` at
      `factory/verify/diffcheck.py:305-306` only while the override is still
      relative. T002's second assertion is what fails that version. The third
      runtime-root read through that helper, `factory/cli/nouns/build.py:1888`, is
      US4's and is fixed by naming the repository, not here.
- [ ] T061 [US1] (FR-019, trap 20) Give the seven operator reads T060 names their
      refusal opt-out — one line each in `factory/cli/doctor.py`,
      `factory/doctor/cli.py`, `factory/doctor/probes.py`,
      `factory/cli/nouns/spec.py` and `factory/cli/repo.py`, calling T010's name
      choice with the working directory. **Do not** write the fallback as a
      literal `Path(".factory")` in the first three:
      `test_doctor_modules_do_not_carry_factory_literal_defaults`
      (`tests/test_runtime_root_findings.py:222` —
      `test_doctor_modules_do_not_carry_factory_literal_defaults`) refuses that
      shape by AST in exactly those three modules. Change nothing these verbs
      *derive* — trap 13 owns the store derivations and they are US2's and US5's.
      `_override_disagreement` (`factory/cli/repo.py:455` —
      `_override_disagreement`) needs nothing: it returns at
      `factory/cli/repo.py:471` unless an override is set. Not `[P]`: it shares
      `factory/cli/repo.py` with nothing else in this phase but is the task T060
      is written against.

### Verification for this story

- [ ] T013 [US1] Paste, as committed evidence, the resolved root printed from three
      different working directories **with no runtime-root variable set**, showing
      one identical absolute path, plus the refusal text printed from a directory
      inside no git repository, plus the output of `ergane findings list`,
      `ergane doctor` and `ergane --help` run from that same directory, showing
      that FR-019's seven verbs still answer and that no runtime root was created
      there.

## Phase 2: User Story 2 — The worker's store default is derived once, and follows the data

### Tests for this story (write FIRST, must fail)

- [ ] T014 [P] [US2] (spec US2-S1, FR-004, traps 13 and 14) With
      `ERGANE_VERIFICATION_DB_PATH` and `FACTORY_VERIFICATION_DB_PATH` deleted,
      assert the verification store path derived through **each of the three
      worker-side callables** — `_store_path`
      (`factory/activities/verify_activities.py:634` — `_store_path`),
      `_store_path` (`factory/activities/notify_activities.py:770` —
      `_store_path`) and the shared helper T021 creates, which is what the bridge
      reaches after this story — is the same absolute file beneath the resolved
      runtime root from the repository and from a directory inside a node
      worktree, and that no answer contains the worktree's own directory. **Do
      not try to call the bridge's own line.** `factory/notify/service.py:1049`
      sits inside `main` (`factory/notify/service.py:1029` — `main`), which
      connects to Temporal and polls; T019 holds that line by asserting on the
      module's source, which is the only way to hold a process entry point. The
      operator's four derivations are US5's; do not reach into them here.
- [ ] T015 [P] [US2] (spec US2-S2, FR-005, traps 9 and 14) With both store
      variables deleted, write a verification row from a process standing in the
      repository, change the working directory to a worktree, and assert **the rows
      come back** *and* that the file both processes opened is the one beneath the
      resolved runtime root, asserted by path. The failure mode is an empty result,
      not an exception, and the row assertion alone passes under the session
      fixture's absolute override.
- [ ] T016 [P] [US2] (spec US2-S3, FR-004, traps 6 and 19) **The control.** From a
      directory inside no git repository, assert importing `factory/stores.py` and
      the three modules that call it succeeds and resolves no runtime root. This is
      the test that fails an implementation deriving the constants at import time,
      which would break `ergane --help` outside a clone.
- [ ] T017 [P] [US2] (spec US2-S4, FR-013, trap 15) Seed a repository holding
      **both** runtime-root names where the store under `.ergane/` is 0 bytes and
      the store under `.factory/` holds rows, stand a process **inside a node
      worktree of that repository** — an owning clone must be discoverable or
      FR-014's fallback fires first and FR-013 is never reached — and assert the
      reader opens the populated `.factory/` file and its rows come back. Assert on
      row *contents*: an existence test passes on the 0-byte file, which is exactly
      why 043's `_resolve_store_path` (`factory/doctor/cli.py:58` —
      `_resolve_store_path`) is copied as a pattern rather than called.
- [ ] T018 [P] [US2] (spec US2-S5, FR-014, trap 16) From a working directory inside
      no git repository and with no repository named, assert a store reader falls
      back to today's process-relative default and returns a path rather than
      propagating FR-009's refusal. `RecordVerificationInput`
      (`factory/activities/verify_activities.py:467` — `RecordVerificationInput`)
      carries no repository, so a refusal here stops a wheel-installed worker
      recording any verification at all.
- [ ] T019 [P] [US2] (spec US2-S6, FR-004, trap 13) Assert the bridge module
      carries no direct read of the legacy variable beside the relative literal —
      `factory/notify/service.py:1049` inside `main`
      (`factory/notify/service.py:1029` — `main`) reads
      `os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH`
      today and so honours `FACTORY_VERIFICATION_DB_PATH`
      (`factory/activities/verify_activities.py:130`) alone. Copy the shape of
      `test_doctor_modules_do_not_carry_factory_literal_defaults`
      (`tests/test_runtime_root_findings.py:222` —
      `test_doctor_modules_do_not_carry_factory_literal_defaults`): a process entry
      point nobody calls from a test is held by asserting on its source.
- [ ] T020 [P] [US2] (spec US2-S7, FR-013, trap 12) **The control.** Assert 043's
      four contract tests are unchanged by this story — the assertions at
      `tests/test_runtime_root_findings.py:153`,
      `tests/test_runtime_root_findings.py:179`,
      `tests/test_runtime_root_findings.py:199` and
      `tests/test_runtime_root_findings.py:222` — by running them and by not
      editing `factory/doctor/cli.py`. `ergane findings` keeps 043's existence
      rule; this story's content rule lives only in the new helper.

### Implementation for this story

- [ ] T021 [US2] (FR-004, FR-005, traps 6, 13 and 19) Create **`factory/stores.py`**
      and put the one shared derivation in it: given a store file name, return the
      absolute path beneath the resolved runtime root. `factory/workgraph/worktree.py`
      is US1's file and `factory/env.py` cannot import the resolver (the resolver
      imports it at `factory/workgraph/worktree.py:84`), so this new leaf module is
      the declared home and the import direction is one-way — `factory/stores.py`
      imports the resolver; its callers import `factory/stores.py`; nothing under
      `factory/workgraph/` imports `factory/stores.py`. Do not name the helper
      `_resolve_store_path`: 043 owns that name at `factory/doctor/cli.py:58` and
      keeps it.
- [ ] T022 [US2] (FR-013, traps 12 and 15) In that helper, follow the *pattern* of
      the rule 043 landed as `_resolve_store_path` (`factory/doctor/cli.py:58` —
      `_resolve_store_path`) and strengthen it from *existence* to *content*: when
      the file under the resolved root is absent or 0 bytes and the file under the
      other runtime-root name holds content, open the populated one. Nothing is
      copied and nothing is moved, and `factory/doctor/cli.py` is not edited — on
      this floor its existence rule answers a stale 28,672 B `.ergane/doctor.db`
      beside a live 126,267,392 B `.factory/doctor.db`, and that stays true after
      this story by design.
- [ ] T023 [US2] (FR-014, trap 16) In the same helper, catch FR-009's refusal and
      fall back to today's process-relative default rather than propagating it.
      Getting this wrong in the raising direction makes a wheel-installed worker
      refuse every `store.connect(_store_path())` —
      `factory/activities/verify_activities.py:509`,
      `factory/activities/verify_activities.py:576` and eleven sites in
      `factory/activities/notify_activities.py`. Trap 14 guarantees no test in the
      suite would show you.
- [ ] T024 [US2] (FR-004, traps 6 and 13) Point the three worker-side derivations
      at that helper, **inside the functions** rather than at import: `_store_path`
      (`factory/activities/verify_activities.py:634` — `_store_path`), `_store_path`
      (`factory/activities/notify_activities.py:770` — `_store_path`) and
      `factory/notify/service.py:1049`. Leave `DEFAULT_VERIFICATION_DB_PATH`
      (`factory/activities/verify_activities.py:128`) as a file name. Do not touch
      the roughly fifteen call sites that take the raw answer
      (`factory/doctor/probes.py`, `factory/cli/doctor.py` and the rest); if the
      diff touches fifteen files, the fix went in at the wrong layer.

### Verification for this story

- [ ] T025 [US2] Paste, as committed evidence, a verification store written from
      the repository root and read from inside a worktree showing the same rows,
      beside `stat -c '%n %s'` on both runtime-root names' copies of that file
      taken before and after, proving the opened file is the populated one and
      that no size dropped.

## Phase 3: User Story 3 — One resolver, and the readiness check reports it

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US3] (spec US3-S1, FR-006, trap 10) With `ERGANE_ROOT` naming a
      directory inside the repository under **neither** runtime-root name — the arm
      where the check's own name choice and the engine's answer diverge — assert
      the value the readiness check reports equals the shared resolver's answer.
      Read trap 10 first: `factory/cli/init.py:2249` — `gather_init_facts` already
      asks git about the resolved *name*, so the no-override arm passes on an
      unchanged tree and proves nothing; the override arm is the live half.
- [ ] T027 [P] [US3] (spec US3-S2, FR-007, traps 1 and 8) Assert all three call
      sites — the shared resolver, `resolve_repo_runtime_root`
      (`factory/cli/init.py:2088` — `resolve_repo_runtime_root`) and
      `runtime_root_for` (`factory/cli/repo.py:418` — `runtime_root_for`) — return
      the same value for one repository with no override set, and that the two
      hand-rolled name choices now call US1's environment-blind entry point rather
      than deriving the precedence themselves.
- [ ] T028 [P] [US3] (spec US3-S3, FR-003) **The control.** Assert none of the
      three call sites creates the root when it does not exist, asserting on the
      directory listing, preserving the property both hand-rolled copies were
      written to obtain.
- [ ] T029 [P] [US3] (spec US3-S4, FR-011, trap 8) **The control that prevents a
      repeat of 2026-08-14.** With `ERGANE_ROOT` naming a directory outside the
      repository, assert `runtime_root_for` (`factory/cli/repo.py:418` —
      `runtime_root_for`) still returns a child of that repository and consults no
      environment variable, because `--clean-runtime` deletes what it returns. This
      is why FR-007 routes it through the environment-blind entry point and not
      through `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
      `resolve_factory_root`), whose first act is to return the override
      (`factory/workgraph/worktree.py:211-216`).
- [ ] T030 [P] [US3] (spec US3-S5, FR-006, trap 11) With `ERGANE_ROOT` naming a
      directory outside the repository, assert the readiness check names that root
      and reports that it lies outside the repository, rather than reporting the
      repository's `.gitignore` as failing.
- [ ] T031 [P] [US3] (spec US3-S6, FR-012) Assert the `.gitignore` `init` writes
      carries ignore entries for **both** runtime-root names. Today
      `factory/cli/init.py:1831` — `_write_scaffold` writes exactly one line from
      `RUNTIME_ROOT` (`factory/cli/init.py:135`).
- [ ] T032 [P] [US3] (spec US3-S7, FR-008) **The control.** In a repository holding
      only a legacy `.factory/`, assert the shared resolver, the readiness check
      and `runtime_root_for` all still choose `.factory/`, and assert the file
      listing is unchanged so nothing was relocated.

### Implementation for this story

- [ ] T033 [US3] (FR-007, FR-011, traps 1 and 8) Route the name choice in
      `resolve_repo_runtime_root` (`factory/cli/init.py:2088` —
      `resolve_repo_runtime_root`) and `runtime_root_for`
      (`factory/cli/repo.py:418` — `runtime_root_for`) through the
      **environment-blind entry point US1 landed for FR-016** — not through
      `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
      `resolve_factory_root`), which returns the override first and would hand
      `--clean-runtime` a root outside the repository. **Read both docstrings
      first**: they name the mkdir side effect and the cwd dependence as their
      reasons for existing, and US1 is what removes those reasons.
      `runtime_root_for` keeps its environment blindness — consolidate the name
      choice and nothing else, and leave `_override_disagreement`
      (`factory/cli/repo.py:455` — `_override_disagreement`) as the only reader of
      the override on that path. This story must not edit
      `factory/workgraph/worktree.py`; if the entry point it needs is missing, US1
      was incomplete and that is an escalation, not a licence.
- [ ] T034 [US3] (FR-006, traps 10 and 11) Point the readiness check at the
      engine's resolver so the reported root and the used root are the same value
      by construction, and give it an answer for a root that lies outside the
      repository rather than reporting it as un-ignored. **Move only the reported
      root.** `resolve_repo_runtime_root` (`factory/cli/init.py:2088` —
      `resolve_repo_runtime_root`) returns a repository-relative *name* and an
      `is_legacy` flag, and its one caller — `factory/cli/init.py:2222` inside
      `gather_init_facts` (`factory/cli/init.py:2200` — `gather_init_facts`) —
      spends it three times. `runtime_root=` becomes the shared resolver's answer;
      `runtime_root_is_legacy=` and
      `runtime_root_ignored=_git_ignores(repo_root, f"{root_name}/")`
      (`factory/cli/init.py:2249`) keep taking the name from
      `resolve_repo_runtime_root`, which T033 re-points at the blind entry point.
      `git check-ignore` can only be asked about a repository-relative path, so
      feeding it an absolute override answers nothing; replacing the whole
      function with the resolver breaks that line for every override, and leaving
      the reported root alone fails T026.
- [ ] T035 [US3] (FR-012) Make `_write_scaffold` (`factory/cli/init.py:1831` —
      `_write_scaffold`) write ignore entries for both runtime-root names, since
      `init` cannot know which name the engine will resolve.
- [ ] T036 [US3] (FR-008, trap 12) Update `docs/architecture.md:199`, which states
      the cwd-relative default as design — a documentation change under FR-008's
      no-behaviour-change umbrella. Leaving it is how the next operator re-derives
      this defect from the documentation. `docs/architecture.md:203` stays as
      written.

### Verification for this story

- [ ] T037 [US3] Paste the readiness check's reported root beside the engine's
      resolved root for one repository, as committed evidence that they agree, and
      paste the same pair with `ERGANE_ROOT` pointing outside the repository.

## Phase 4: User Story 4 — Every read on a node's lifecycle resolves one root

### Tests for this story (write FIRST, must fail)

- [ ] T038 [P] [US4] (spec US4-S1, FR-010) From a working directory outside the
      target repository and with no override set, assert the dispatch path resolves
      its runtime root under `request.target_repo`. `prepare_worktree`
      (`factory/activities/agent_activities.py:398` — `prepare_worktree`) already
      holds it: `request.target_repo` is passed at
      `factory/activities/agent_activities.py:417`, three lines above the
      `factory_root=factory_root()` at
      `factory/activities/agent_activities.py:420`.
- [ ] T039 [P] [US4] (spec US4-S2, FR-010) Assert both preflight readers —
      `_preflight_factory_root` (`factory/cli/nouns/build.py:367` —
      `_preflight_factory_root`) and `_preflight_factory_root`
      (`factory/activities/roadmap_activities.py:670` — `_preflight_factory_root`)
      — read the runtime root for the repository the dispatch names rather than
      from the process's working directory.
- [ ] T040 [P] [US4] (spec US4-S3, FR-010) **The control.** With an absolute
      `ERGANE_ROOT` set, assert the override still wins over the repository the
      epic names. The anchor does not overrule an explicit operator choice.
- [ ] T041 [P] [US4] (spec US4-S4, FR-010) From a working directory outside the
      target repository with no override set, assert `_reset_epic`
      (`factory/cli/nouns/build.py:1826` — `_reset_epic`) resolves its runtime root
      under the graph's `target_repo`, by asserting the archived worktree path lies
      inside that repository. Today `factory/cli/nouns/build.py:1888` reads the
      root blind while `graph.target_repo` is in scope five lines below at
      `factory/cli/nouns/build.py:1893`, so a reset from the wrong directory
      archives nothing and reports success.
- [ ] T042 [P] [US4] (spec US4-S5, FR-010) From a working directory outside the
      target repository with no override, assert `open_landing_pr`
      (`factory/activities/merge_activities.py:425` — `open_landing_pr`) and
      `sync_landing_branch` (`factory/activities/merge_activities.py:580` —
      `sync_landing_branch`) each resolve the root of `request.target_repo`. Today
      `factory/activities/merge_activities.py:464` and
      `factory/activities/merge_activities.py:602` compute a blind
      `worktrees.resolve_factory_root(FACTORY_ROOT_ENV)[0]` on the line after the
      `request.target_repo` the same call already passes
      (`factory/activities/merge_activities.py:461`,
      `factory/activities/merge_activities.py:599`) — the most blatant instance in
      the tree, and the one that stops landing entirely once FR-009 refuses.
- [ ] T043 [P] [US4] (spec US4-S6, FR-018, trap 17) Create a node's worktree
      through the dispatch path with `request.target_repo` named and the process
      standing outside that repository, then assert the path the salvage reads
      compute is **that same directory**: `salvage`
      (`factory/workgraph/worktree.py:511` — `salvage`), `record_salvage_ref`
      (`factory/workgraph/worktree.py:778` — `record_salvage_ref`) and
      `mirror_node_branch` (`factory/workgraph/worktree.py:855` —
      `mirror_node_branch`), reached from
      `factory/activities/agent_activities.py:796`,
      `factory/activities/agent_activities.py:807` and
      `factory/activities/agent_activities.py:822`. A disagreement is not a wrong
      store, it is `[Errno 2] No such file or directory:
      /opt/ergane/.ergane/worktrees/...` — one of the three failures recorded in
      the `worktree_path` finding's own notes.
- [ ] T044 [P] [US4] (spec US4-S7, FR-018, trap 18) **The control.** Construct
      `SalvageWorktreeInput` (`factory/activities/agent_activities.py:745` —
      `SalvageWorktreeInput`) **without** the repository — the payload shape an
      epic already in flight replays — and assert the activity resolves a path and
      does not raise FR-009's refusal. Any new field on that input or on
      `PrepareLandingPrInput` (`factory/activities/merge_activities.py:112` —
      `PrepareLandingPrInput`) must be optional with a default, the way
      `AttemptContext.target_repo` is (`factory/workgraph/models.py:463`,
      `str = ""`). The sentence naming the reason belongs to the *next* field:
      `factory/workgraph/models.py:466` says the default exists "for legacy
      payloads that predate this field" about `agent`
      (`factory/workgraph/models.py:467`), not about `target_repo`.
- [ ] T045 [P] [US4] (spec US4-S8, FR-010) **The control.** Given an absolute
      runtime root, assert `worktree_path` (`factory/workgraph/worktree.py:289` —
      `worktree_path`) returns an absolute path naming the same directory from two
      different working directories. All ten call sites take the root as an
      argument — `factory/workgraph/preflight.py:598` and nine inside
      `factory/workgraph/worktree.py` — so this is a regression guard, and the
      audit the `worktree_path` finding asks for by name is T038 through T044.
      Read only; that file is US1's. The call site outside
      `factory/workgraph/worktree.py` is inside `worktree_ownership_findings`
      (`factory/workgraph/preflight.py:563` — `worktree_ownership_findings`), not
      inside `landing_readiness_preflight` (`factory/workgraph/preflight.py:797` —
      `landing_readiness_preflight`).
- [ ] T062 [P] [US4] (spec US4-S9, FR-020, trap 21) Construct an `AttemptContext`
      carrying the **relative** `home_path` the workflow computes today —
      `home_path(DEFAULT_FACTORY_ROOT, ...)` at
      `factory/workgraph/workflow.py:1893` and
      `factory/workgraph/workflow.py:3985` — run the attempt from a temporary
      directory outside the target repository with no override set, and assert the
      per-node HOME created at `factory/workgraph/adapter.py:1060` and exported at
      `factory/workgraph/adapter.py:971` lies beneath the target repository's
      resolved runtime root, and that the temporary directory gains no `.ergane`.
      This is the 4.2 GB the C-32 row measured; T038 through T045 do not cover it,
      because no `resolve_factory_root` read builds this path.
- [ ] T063 [P] [US4] (spec US4-S10, FR-010, trap 18) **The control.** Construct an
      `AttemptContext` leaving `target_repo` at its empty default
      (`factory/workgraph/models.py:463`) — the value a payload predating the
      field replays with — and assert `run_agent_attempt`
      (`factory/activities/agent_activities.py:482` — `run_agent_attempt`)
      resolves a path at `factory/activities/agent_activities.py:498` rather than
      raising FR-009's refusal or anchoring on `Path("")`.

### Implementation for this story

- [ ] T046 [US4] (FR-010) Give `factory_root`
      (`factory/activities/agent_activities.py:188` — `factory_root`) the
      repository its callers already hold and pass it at every call site that has
      one: `factory/activities/agent_activities.py:420` (`prepare_worktree`),
      `factory/activities/agent_activities.py:498` inside `run_agent_attempt`
      (`factory/activities/agent_activities.py:482` — `run_agent_attempt`), which
      reaches it through `AttemptContext.target_repo`
      (`factory/workgraph/models.py:463`), `factory/activities/agent_activities.py:861`
      (`remove_worktree`, `factory/activities/agent_activities.py:847` —
      `remove_worktree`) and `factory/activities/agent_activities.py:893`
      (`archive_and_clear_remote_branch`,
      `factory/activities/agent_activities.py:877` —
      `archive_and_clear_remote_branch`), whose inputs already carry `target_repo`.
      `factory_root`'s docstring still says "Relative by default"; that sentence
      goes with the change.
- [ ] T047 [US4] (FR-010) Do the same for the landing reads at
      `factory/activities/merge_activities.py:464` and
      `factory/activities/merge_activities.py:602`, for the two preflight readers
      (`factory/cli/nouns/build.py:367` — `_preflight_factory_root` and
      `factory/activities/roadmap_activities.py:670` — `_preflight_factory_root`),
      and for `_reset_epic` (`factory/cli/nouns/build.py:1826` — `_reset_epic`) at
      `factory/cli/nouns/build.py:1888`, which holds `graph.target_repo` five lines
      below at `factory/cli/nouns/build.py:1893`.
- [ ] T048 [US4] (FR-018, traps 17 and 18) Make the four reads that hold no
      repository resolve the same root the dispatch did:
      `factory/activities/agent_activities.py:796`,
      `factory/activities/agent_activities.py:807`,
      `factory/activities/agent_activities.py:822` and `_landing_body_dir`
      (`factory/activities/merge_activities.py:342` — `_landing_body_dir`) at
      `factory/activities/merge_activities.py:349`. Carrying `target_repo` on
      `SalvageWorktreeInput` (`factory/activities/agent_activities.py:745` —
      `SalvageWorktreeInput`) and `PrepareLandingPrInput`
      (`factory/activities/merge_activities.py:112` — `PrepareLandingPrInput`) is
      the obvious route and `RemoveWorktreeInput`
      (`factory/activities/agent_activities.py:838` — `RemoveWorktreeInput`) is the
      precedent — **but the field must be optional with a default** (trap 18), and
      the refusal must never propagate from these four.
- [ ] T064 [US4] (FR-020, trap 21) Derive the per-node agent HOME from the
      resolved absolute root in `run_agent_attempt`
      (`factory/activities/agent_activities.py:482` — `run_agent_attempt`), which
      already holds it from `factory/activities/agent_activities.py:498`, and
      replace the frozen context once — the precedent is one line away,
      `context = replace(context, session_id=derived)`
      (`factory/activities/agent_activities.py:513`), whose comment block above it
      states the replay reasoning this change reuses. **Do not edit
      `factory/workgraph/workflow.py:1893` or `factory/workgraph/workflow.py:3985`**:
      a workflow may not touch the filesystem, so it cannot ask which runtime-root
      name this repository uses, and joining the `graph.target_repo` sitting seven
      lines below (`factory/workgraph/workflow.py:1900`,
      `factory/workgraph/workflow.py:3992`) to a hard-coded `.ergane` answers
      wrongly for a repository holding only `.factory/` — and moves the HOME of an
      epic already in flight. Leave both sites computing a value so an older
      payload still deserialises. Then check the one other consumer: `_build_argv`
      (`factory/workgraph/adapter.py:464` — `_build_argv`) walks up from the home
      to choose the runtime root it read-only-binds
      (`factory/workgraph/adapter.py:529-534`), so a home that is no longer three
      levels under the root changes the sandbox's bind set.

### Verification for this story

- [ ] T049 [US4] Paste, as committed evidence, the runtime root a dispatch-path
      read, a landing-path read, a salvage-path read and a reset-path read each
      return when the process's working directory is a temporary directory outside
      the target repository, showing one path under the target repository in all
      four — the dispatch and salvage lines must be byte-identical, because that is
      trap 17. Beside it paste `du -sh` of the installed package directory taken
      before and after that dispatch, and the absolute path of the per-node HOME
      the attempt created, showing it under the target repository and the package
      directory unchanged — that pair is the only evidence that reaches what the
      C-32 row measured.

## Phase 5: User Story 5 — The operator's read verbs open the same store, and say which

### Tests for this story (write FIRST, must fail)

- [ ] T050 [P] [US5] (spec US5-S1, FR-017, traps 13 and 14) With
      `ERGANE_VERIFICATION_DB_PATH` and `FACTORY_VERIFICATION_DB_PATH` deleted,
      assert the verification store path derived through the winning
      `_verification_store_path` (`factory/cli/nouns/build.py:1534` —
      `_verification_store_path`), `_verification_store_path`
      (`factory/cli/status.py:690` — `_verification_store_path`) and `_store_path`
      (`factory/cli/nouns/answer.py:96` — `_store_path`) is the same absolute file
      beneath the resolved runtime root from the repository and from a directory
      inside a node worktree, and that no answer contains the worktree's own
      directory. These three are what `ergane build answer` and `ergane status`
      reach, and they are the reproduction the operator finding was filed on.
- [ ] T051 [P] [US5] (spec US5-S2, FR-017, trap 7) **The control that catches the
      half-edit.** Import and call **each** definition of
      `_verification_store_path` individually — `factory/cli/nouns/build.py:1484` —
      `_verification_store_path` and `factory/cli/nouns/build.py:1534` —
      `_verification_store_path` — and assert both return the same absolute path.
      They are byte-identical today and the second shadows the first, so a test
      that goes through the CLI passes while half the file is still wrong.
- [ ] T052 [P] [US5] (spec US5-S3, FR-017, trap 14) With `ERGANE_LEDGER_PATH` and
      `LEDGER_PATH` deleted, assert the ledger path resolved through each of the
      three modules defining `DEFAULT_LEDGER_PATH`
      (`factory/activities/usage_activities.py:99`, `factory/usage/cli.py:30`,
      `factory/cli/usage.py:26`) is the same absolute file beneath the resolved
      runtime root.
- [ ] T053 [P] [US5] (spec US5-S4, FR-015) Assert the empty-result line names the
      absolute store file it opened alongside the count. Today
      `factory/cli/nouns/build.py:1554`, inside `_answer`
      (`factory/cli/nouns/build.py:1547` — `_answer`), prints only
      `no pending questions for epic '<id>'`, which is indistinguishable from a
      quiet floor. This is the second half of the operator finding's stated remedy
      shape and the half nothing else reaches.
- [ ] T054 [P] [US5] (spec US5-S5, FR-017, trap 6) **The control.** From a
      directory inside no git repository, assert the CLI's help path runs and these
      six modules import without resolving a runtime root or raising FR-009's
      refusal. These modules are on `ergane --help`'s import path, so an
      import-time derivation breaks the CLI outside a clone.

### Implementation for this story

- [ ] T055 [US5] (FR-017, traps 6, 7 and 13) Point the operator-side derivations at
      US2's helper in `factory/stores.py`, **inside the functions** rather than at
      import: **both** definitions of `_verification_store_path`
      (`factory/cli/nouns/build.py:1484` and `factory/cli/nouns/build.py:1534`; the
      second shadows the first, so editing one changes nothing — collapse them to
      one if that is cleaner), `_verification_store_path`
      (`factory/cli/status.py:690` — `_verification_store_path`), `_store_path`
      (`factory/cli/nouns/answer.py:96` — `_store_path`), and the three
      `DEFAULT_LEDGER_PATH` readers (`factory/activities/usage_activities.py:651`,
      `factory/usage/cli.py:145`, `factory/cli/usage.py:112`). Leave the constants
      as file names.
- [ ] T056 [US5] (FR-015) Make the empty-result report name the absolute store file
      it opened at `factory/cli/nouns/build.py:1554` inside `_answer`
      (`factory/cli/nouns/build.py:1547` — `_answer`).

### Verification for this story

- [ ] T057 [US5] Paste, as committed evidence, the store paths printed by
      `ergane status` and `ergane build answer` from the repository root and from
      inside a node worktree — the two verbs the operator finding was filed against
      — with `stat -c '%n %s'` on each, proving the opened file is the populated
      one and not a 0-byte sibling, and paste the empty-result line showing the
      path it now names.

## Verification

- [ ] T058 The full gate command passes green.
- [ ] T059 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. **Step 1 — unsetting every runtime-root
      variable rather than eval'ing `scripts/ergane-env.sh` — is the step everyone
      will skip, and skipping it makes every later step pass for the wrong
      reason.** Step 7 — `ergane build answer` and `ergane status` from inside a
      node worktree — is the one that distinguishes a fix from a half fix, steps 2
      and 10 are the pair that proves no store was orphaned, and step 12 is the one
      that proves the dispatch and salvage halves of one node found the same
      worktree.
