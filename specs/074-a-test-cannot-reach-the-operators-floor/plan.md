# Implementation Plan: a test cannot reach the operator's floor

**Spec**: `specs/074-a-test-cannot-reach-the-operators-floor/spec.md`

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing. The 2026-08-20 draft of this plan was
read against `a58ec93`, and by 602a92c all but five of its anchors had moved —
some of them onto real, plausible, wrong code. That is what 072 exists for and
it is why every citation here is written in the `` `path.py:NN` — `symbol` ``
form the symbol tier can check.

Repaired the same day, in the same run, after an adversarial review refuted the
draft: the eleventh construction site is legislated below rather than left to a
node (trap 18), FR-020 has a named mechanism instead of a substitution that
changes nothing (trap 4), the live capacity tier's own inverted assertion is
trap 17, and the two edges the Work Graph was missing are declared in spec.md.

Repaired a second time, same run, same sha, after two lenses refuted that repair.
None of the six defects was an anchor; four were landed contracts or seams this
plan named without saying what they bind. The choke point now takes an
already-resolved target and resolves nothing (trap 20); every migrated caller
keeps its own resolver call, because a landed AST guard asserts that import in
exactly the ten modules this spec migrates (trap 19); the FR-010 opt-in has to be
readable from `factory/` rather than from pytest (trap 21); and the test of
FR-020 may not bind the provider seam, which would replace the reader whose new
filter is the whole requirement (trap 22).

Repaired a third time, same run, same sha, after an adversarial review refuted
that repair on five counts — again not one of them an anchor. The class it found
sits one layer under the anchors: seven landed test modules bind the Temporal
floor at `temporalio.client.Client.connect` and then drive the exact callers this
spec migrates, so the choke point's refusal fires before any of those fakes is
consulted (trap 23). Two of those fakes made the plan self-contradictory —
`tests/test_declared_temporal.py` had to be both migrated through and left
untouched — which FR-028 now settles. A second landed AST guard decides where the
choke point may live (trap 24), the sanctioned door needed an address (trap 25),
and the FR-014 enumerator needed an anti-vacuity floor (trap 26).

## What already exists, and where

### The doctrine, already written down twice

- `factory/roadmap/schedule.py:22-26` — the module docstring that states the
  two-independent-guards rule in one sentence and names both halves. **This is
  the design US2 generalises.** Read it before writing anything.

  ```
  Isolation follows D-045's shape because the convention failed here once: the
  seam binding in `tests/` is the convention, and two independent guards are the
  enforcement — `_default_schedule_client` will not connect under
  `PYTEST_CURRENT_TEST`, and `_refuse_live_client` will not mutate through a real
  client under it.  Removing either alone still refuses.
  ```

- `factory/cli/repo.py:553` — `_refuse_unsafe_removal`, whose docstring states
  the thesis of this whole spec at `factory/cli/repo.py:560` —
  `_refuse_unsafe_removal` ("A convention is not a boundary for an act that
  deletes"), explains D-045's shape, and explains at `factory/cli/repo.py:563-565`
  why *this* guard deliberately has no acknowledgment variable:

  ```
      Unlike D-045 there is no acknowledgment variable.  D-045 has one because a
      sanctioned live smoke must open a real store; nothing needs to empty a real
      runtime root from inside a test, and a door with no user is only a way in.
  ```

- `factory/verify/store.py:363` — `connect`, and its guard at
  `factory/verify/store.py:378-381` — `connect`, which *does* carry an
  acknowledgment variable via `resolve_env_flag` because a sanctioned live smoke
  must open a real store. **FR-009 is the choice between these two shapes.** Read
  both. (The 2026-08-20 plan cited lines 266 and 279-281 for these; both were
  wrong by 602a92c and the symbol tier refused the first.)

### The one guarded client, and the second defence beside it

- `factory/roadmap/schedule.py:156` — `_default_schedule_client` — the refusal:
  resolves the target, then raises `ScheduleUnavailable` naming the address, the
  namespace and the seam to bind. Copy this message shape; it is the only one in
  the tree that names all three.
- `factory/roadmap/schedule.py:165` — `_default_schedule_client` — the
  `Client.connect` it guards.
- `factory/roadmap/schedule.py:255` — `_refuse_live_client` — guard two, and the
  thing US2 must copy structurally rather than literally. Note what it actually
  does: it reads the *same* environment variable as guard one, in a *different
  function*, and refuses on the *client it was handed* rather than on the
  connection it is about to open. See trap 5.

### The eleven construction sites (US1 takes four, US6 takes seven)

US1's four, all CLI or operator entry points:

- `factory/workgraph/cli.py:977` — `_connect`
- `factory/cli/nouns/__init__.py:54` — `_open_client`. Its docstring explains why
  the seam lives on the package rather than on `build`: noun modules are
  `exec_module`-d into fresh module objects, so a monkeypatch on an imported
  module does not reach the object the parser references. Preserve that property.
- `factory/cli/roadmap.py:205` — `_connect`
- `factory/cli/repo.py:85` — `_open_client`, inside `factory/cli/repo.py:80-90` —
  `_open_client`, whose seam is declared immediately below at
  `factory/cli/repo.py:93-94` (module level, not a definition).

US6's seven:

- `factory/doctor/probes.py:491` — `_gather_async`
- `factory/doctor/probes.py:603` — `_closed_epics_from_temporal`
- `factory/controlplane/verify.py:193` — `_temporal_client_factory`
- `factory/notify/service.py:1048` — `main`
- `factory/worker.py:351` — `main`, inside `factory/worker.py:351` — `main`.
  FR-006 is about this one.
- `factory/supervision/deploy.py:749` — `asked`. **This site is not in the
  2026-08-20 table.** 082-US2 landed it on 2026-08-22, nested inside
  `_call`, behind a lazy `from temporalio.client import Client`. It is why
  FR-003's test must walk the tree.
- `factory/roadmap/schedule.py:165` — `_default_schedule_client`. **Guarded, and
  still a construction site.** The eleventh. Migrate the connect and the lazy
  import at `factory/roadmap/schedule.py:146` — `_default_schedule_client` that
  serves it; leave everything else in that module exactly as it is. Trap 18 is the
  whole instruction.

One more occurrence of the literal is not a site at all:
`factory/controlplane/verify.py:732` — `gather` carries `Client.connect` inside a
comment about a timeout branch. It must survive the migration, which is why FR-003's
test parses code and the operator's grep in step 2 below expects two lines rather
than one.

### The landed floor-fakes, and the two AST guards over the migration

Neither of these is optional reading. They are what turns a correct migration
into a red gate, and no anchor tier can see either.

- Seven modules install a fake at `temporalio.client.Client.connect` itself,
  never at a factory seam. US1's five:
  `tests/test_ergane_status.py:485` — `fake_temporal` (57 uses across 39 test
  functions), which drives `main_module.main([...])` into
  `factory/cli/status.py:305` — `collect_floor` and so into
  `factory/cli/nouns/__init__.py:54` — `_open_client`;
  `tests/test_roadmap_schedule_discovery.py:311` — `fake_temporal` (32 uses) and
  `tests/test_roadmap_wedge_visibility.py:219` — `fake_temporal` (13 uses), both
  driving `ergane roadmap status/pause/resume` into
  `factory/cli/roadmap.py:205` — `_connect`;
  `tests/test_teardown_owns_the_ordering.py:213` — `_host` and
  `tests/test_teardown_owns_the_ordering.py:600` —
  `test_roadmap_pause_command_still_pauses_the_schedule`, which reach
  `factory/cli/nouns/__init__.py:54` — `_open_client` through
  `factory/supervision/units.py:1291` — `_open_epics`; and
  `tests/test_ergane_spec.py:448` — `test_validate_opens_no_socket`, whose fake
  raises rather than returns. US6's two:
  `tests/test_doctor_probes.py:295` — `fake_temporal` (17 uses), which drives
  both probe sites, and `tests/test_declared_temporal.py:269` — `dialed`.
- `tests/test_teardown_owns_the_ordering.py:631` —
  `test_roadmap_py_is_not_edited_by_this_story` is not a fake but the same class
  of collision: it asserts the literal `Client.connect` occurs exactly once in
  `factory/cli/roadmap.py`, which T010 removes. Carry it forward; FR-027.
- `tests/test_ergane_status.py:1516` `EXPECTED_GUARDS` and the sweep at
  `tests/test_ergane_status.py:1716` —
  `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal`. The
  module set is derived, at `tests/test_ergane_status.py:1600` —
  `_cli_python_modules`, from every file under `factory/cli/` containing
  `await ` and one of `temporalio` / `RPCError` / `WorkflowQuery` /
  `WorkflowAlreadyStartedError`; `tests/test_ergane_status.py:1699` —
  `_discovered_guard_modules` then reports each awaiting function's `except`
  clause tuples, and the sweep asserts the discovered module set equals the table
  *and*, per module, that the function set and each clause tuple match. Trap 24.
- `tests/test_declared_temporal.py:264` — `dialed` serves two tests that require
  a **real dial** through `factory/controlplane/verify.py:193` —
  `_temporal_client_factory` under pytest:
  `tests/test_declared_temporal.py:274` —
  `test_the_verify_probe_dials_the_address_the_worker_would_use` asserts
  `dialed.calls == [(OVERRIDE_ADDRESS, OVERRIDE_NAMESPACE)]`, and
  `tests/test_declared_temporal.py:303` —
  `test_the_probe_snapshot_names_the_server_it_actually_dialed` requires the
  same dial through `TemporalProbe().gather(config)`. FR-028.

### US3's surface, after 114 landed

- `pyproject.toml:89-96` — the marker registrations. There are **six** now, not
  five: `live_onramp` landed with 106. Every description reads "auto-skips unless
  *`<credential>`* is set". That sentence is the defect, stated in the manifest —
  and the phrase `auto-skips unless ` is now load-bearing for two landed readers.
  See trap 8.
- `tests/conftest.py:525` — `_isolated_test_store`, the session-scoped autouse
  fixture 114 added. It captures the two Telegram variables into
  `tests/conftest.py:521` and then deletes them from `os.environ` at
  `tests/conftest.py:563` — `_isolated_test_store`. Its own comment says why:
  "Capture first, delete second: the live smoke reads the stash to opt in."
- `tests/test_live_notify.py:196` — `live_config` consumes that stash and skips
  only when it is empty. **This is the live defect, in its post-114 shape**: the
  credential no longer arms the tier through the environment, it arms it through
  the stash.
- `tests/conftest.py:766` — `_registered_live_tiers` and
  `tests/test_114_us3_live_tier_summary.py:147` — `registered_live_tiers` both
  parse each marker registration at the `auto-skips unless ` boundary, and the
  second **asserts** the phrase is present in every `live_*` registration
  (`tests/test_114_us3_live_tier_summary.py:165` — `registered_live_tiers`).
- `tests/test_114_us3_live_tier_summary.py:175` — `scratch_session` — **the
  harness US3's scenarios need and must not re-invent.** It runs one throwaway
  pytest session in a subprocess against this repository's own `pyproject.toml`,
  with a caller-supplied conftest and body and an environment it builds itself,
  stripping every name matching `tests/test_114_us3_live_tier_summary.py:132` (the
  tuple `LIVE_ENV_FRAGMENTS`). That subprocess boundary is the only way US3-S1's
  "both credentials set **before the session starts**" can be arranged: by the
  time an in-process test runs, `tests/conftest.py:525` — `_isolated_test_store`
  has already captured and deleted them. T023, T024 and T038 all reach for it.
- The opt-in FR-010 mints has to be readable from `factory/`, not only from
  pytest — see trap 21. `factory/verify/store.py:378-381` — `connect` is the
  shape: an environment variable read through `resolve_env_flag` at the moment
  the guard decides.
- The six tier modules: `tests/test_live_proxy.py`, `tests/test_live_notify.py`,
  `tests/test_live_epic.py`, `tests/test_live_merge.py`,
  `tests/test_live_capacity.py`, `tests/test_live_onramp.py`.
  `tests/test_live_judge.py` carries a `live_proxy` marker rather than one of its
  own; count it when enumerating modules, not when enumerating tiers.

### US4's surface, after 107 landed

**107 already wrote the check this story was told to invent.** Read all four
pieces before writing a line:

- `factory/workgraph/worktree.py:989` — `_worktree_ownership`, whose docstring is
  trap 3 stated by the tree itself: git walks *up*, so a bare directory nested
  inside a clone answers `--show-toplevel` with exit 0, and "comparing common
  directories alone therefore calls a directory that is not a worktree at all
  *owned*". Its answer is a returned dataclass, never an exception.
- `factory/workgraph/worktree.py:1037` — `_repo_identity`, one `git rev-parse
  --path-format=absolute --show-toplevel --git-common-dir`, returning `None` when
  git finds no repository. **This is the whole of what `salvage` needs**, because
  the test that matters is `toplevel == path.resolve()` and that needs no
  `target_repo`.
- `factory/workgraph/worktree.py:1088` — `_ownership_refusal`, which already
  produces the "is not a git worktree of any repository" message naming the
  directory, what git resolved it to, and a remedy. **Read its signature before
  planning to reuse it**: `_ownership_refusal(repo, path, ownership, *,
  branch=None)`, and *both* returned strings name "the dispatched target repo
  {repo.resolve()}". `_archive_node` has a `repo` to pass; `salvage` does not
  (trap 2). Its exact wording is pinned by
  `tests/test_worktree_ownership.py:243` —
  `test_the_refusal_reads_exactly_as_the_operator_will_meet_it`, so widening the
  signature is a change to a landed contract and must keep the message its
  existing callers produce byte-identical. See T044.
- Where 107 wired it: `factory/workgraph/worktree.py:409` — `ensure`,
  `factory/workgraph/worktree.py:608` — `push_branch`,
  `factory/workgraph/worktree.py:1353` — `sync_with_target`, and
  `factory/workgraph/preflight.py:602`.

**Where it did not:**

- `factory/workgraph/worktree.py:531` — `salvage`, still `if not path.is_dir()`,
  then `factory/workgraph/worktree.py:538` — `salvage` runs `git add -A`. This is
  the route that produced `396611b`.
- `factory/workgraph/worktree.py:1766` — `_archive_node`, still `if path.is_dir()`
  then `factory/workgraph/worktree.py:1768` — `_archive_node` runs `git add -A`.
  This is the `build reset` route, reached from
  `factory/cli/nouns/build.py:2178` — `reset_command` through
  `factory/cli/nouns/build.py:2332` — `_reset_epic`, through
  `factory/workgraph/worktree.py:1607` — `reset` and
  `factory/workgraph/worktree.py:1660` — `archive_and_clear_remote_branch`.

The complete list of node-path `is_dir()` gates in that module today, so nobody
has to re-derive it: `factory/workgraph/worktree.py:401`,
`factory/workgraph/worktree.py:531`, `factory/workgraph/worktree.py:597`,
`factory/workgraph/worktree.py:1345`, `factory/workgraph/worktree.py:1518`,
`factory/workgraph/worktree.py:1607`, `factory/workgraph/worktree.py:1660`,
`factory/workgraph/worktree.py:1689` and `factory/workgraph/worktree.py:1766`.
`git add -A` runs at three places in this module, not two:
`factory/workgraph/worktree.py:538` — `salvage`,
`factory/workgraph/worktree.py:1526` — `diff` and
`factory/workgraph/worktree.py:1768` — `_archive_node`. FR-015 is about the two
that stage into the worktree's **own** index and then commit — `:538` and
`:1768`. `factory/workgraph/worktree.py:1526` — `diff` runs its add against a
scratch `GIT_INDEX_FILE` in a temporary directory
(`factory/workgraph/worktree.py:1525` — `diff`), so it stages nothing and commits
nothing; its docstring says so in the tree's own words. Do not treat that
three-versus-two as a technicality: one grep falsifies a two-item list, and an
implementer who catches this plan out on it will distrust the rest. It leaves one
residual that is **out of scope here**: from inside a husk,
`factory/workgraph/worktree.py:1526` — `diff` still walks up, so the judge would
be handed the operator's tree as the attempt's patch. That is non-mutating, it is
a different defect, and this spec does not fix it — do not widen US4 to chase it.
Nor is FR-015 about all nine `is_dir()` gates. The
gates at `factory/workgraph/worktree.py:597` and
`factory/workgraph/worktree.py:1345` already have 107's ownership check
immediately after them; the 2026-08-20 plan's list of seven sibling gates
(lines 460, 912, 1018, 329, 1082, 1121 and 1198) described a file that no longer
exists.

- `factory/workgraph/worktree.py:298` — `salvage_message` — the commit subject
  `396611b` carried on 2026-08-15.

### US5's surface

- `factory/activities/roadmap_activities.py:755` — `_list_open_epics`, and the
  grammar at `factory/activities/roadmap_activities.py:775` — `_list_open_epics`:
  `if execution.id.startswith("epic-")`. A bare literal, not the constant — and
  replacing it with the constant changes nothing, because the constant *is*
  `"epic-"` (`factory/cli/status.py:114`, `factory/cli/nouns/build.py:196`). The
  behaviour lives one line up, in the query at
  `factory/activities/roadmap_activities.py:772-773` — `_list_open_epics`, whose
  only clause today is the status pinned at
  `factory/activities/roadmap_activities.py:783`. FR-020 adds the second clause
  there and a type check beside the id test; trap 4.
- `execution.workflow_type` is a field the SDK's `WorkflowExecution` carries
  (beside `id`, `status` and `raw_info`, which `factory/versioning.py:171` —
  `open_epic_from` already reads), so the client-side half of FR-020 needs no new
  round trip and a scripted listing can decide it without a server.
- The precedent for the query half, in the tree and arguing for itself:
  `factory/escalation/client.py:52-59` pins
  `WorkflowType = "EscalationWorkflow" AND ExecutionStatus = "Running"` and its
  comment says why — "without it this enumerates every workflow in the namespace,
  epics included."
- What makes the type clause safe: every epic is started as `EpicWorkflow.run`, at
  `factory/cli/nouns/build.py:930` — `_start_epic`,
  `factory/workgraph/cli.py:674` — `_start_epic` and
  `factory/roadmap/workflow.py:1295` — `_dispatch`. The class is
  `factory/workgraph/workflow.py:763` — `EpicWorkflow`, registered under its own
  name, which is the value the pinned constant must be proven equal to.
- `factory/activities/roadmap_activities.py:786-789` — `_open_epics_provider`.
  Module-level, so it cannot be written in the symbol-tier form; the range covers
  its comment and its assignment. **It is `count_open_epics`'s seam, not a seam
  for exercising the reader.** It defaults to `_list_open_epics` itself and is
  read at exactly one place,
  `factory/activities/roadmap_activities.py:801` — `count_open_epics`, so binding
  it *replaces* the function whose new type filter is the whole of FR-020. No test
  of FR-020 may bind it — trap 22. The way to drive the real reader over a
  scripted listing is already in the tree:
  `tests/test_live_capacity.py:202` — `_running_ids` runs
  `roadmap_activities._list_open_epics` inside `ActivityEnvironment(client=…)`,
  so a fake client's `list_workflows` supplies the executions and the reader's own
  filter decides.
- `factory/supervision/units.py:1302` — `listed` — **the second reader**, added
  since this spec was drafted. It runs the same visibility query and filters on
  `EPIC_ID_PREFIX` imported at `factory/supervision/units.py:1292` — `_open_epics`.
  FR-024.
- The prefix, spelled at five sites: `factory/cli/status.py:114`
  `EPIC_ID_PREFIX = "epic-"`, `factory/cli/nouns/build.py:196` the same constant
  again, `factory/activities/roadmap_activities.py:775` — `_list_open_epics` the
  bare literal, `factory/workgraph/cli.py:162` — `workflow_id`, and
  `factory/roadmap/workflow.py:195` — `_epic_id_for`.
  `factory/escalation/client.py:59` documents why one such literal is pinned.
  **Trap 4.**
- `tests/test_live_capacity.py:176` — `_probe_id` mints the ids. The leak on the
  namespace came from `tests/test_live_capacity.py:342` —
  `test_capacity_read_excludes_continued_as_new_chain`, which asks for the prefix
  `epic-capacity-can`.
- The two live tests US5 must rewrite (FR-026): `tests/test_live_capacity.py:260` —
  `test_capacity_read_finds_open_epic_workflows_and_excludes_others`, which mints
  `epic-capacity-open` and `epic-capacity-closed` at
  `tests/test_live_capacity.py:271-273` and asserts they **are** counted, and
  `tests/test_live_capacity.py:331` —
  `test_capacity_read_excludes_continued_as_new_chain`, which asserts the same of
  `epic-capacity-can`. Both reach the production read through
  `tests/test_live_capacity.py:202` — `_running_ids`. Their probes are registered
  as `CapacityProbeWorkflow` (`tests/test_live_capacity.py:56` —
  `_CapacityProbeWorkflow`) and `CapacityContinueAsNewProbeWorkflow`
  (`tests/test_live_capacity.py:71` — `_ContinueAsNewProbeWorkflow`), so after
  FR-020 no probe is counted whatever it is called. Trap 17.
- `tests/test_live_capacity.py:377` —
  `test_capacity_read_fails_under_shipped_uppercase_spelling` is the tier's other
  half and is untouched by this story: it patches the provider with its own copy of
  the query, so it neither sees the new clause nor needs to.

## Traps

**1. The husk defect is not a missing check — it is the wrong check, and 107
already wrote the right one.** `factory/workgraph/worktree.py:531` — `salvage`
refuses on `is_dir()`, and a husk is a directory whose `.git` file is gone. An
implementer who reads "add a guard" will write a new helper and prove it with a
test that deletes the whole directory — which the existing line already catches.
The test that matters deletes **only `path/.git`** and leaves the directory
populated. And the helper already exists: `factory/workgraph/worktree.py:1037` —
`_repo_identity`. Writing a second one is the wrong move; FR-015 and US4-S2.

**2. `salvage` has no `target_repo`, so it cannot call `_worktree_ownership`.**
`factory/workgraph/worktree.py:511` — `salvage` takes `epic_id`, `node_id`,
`termination`, `attempt`, `factory_root` and nothing else, and
`factory/activities/agent_activities.py:783` — `salvage_worktree` hands it no
repository either. The tempting move is to reach for
`factory/workgraph/worktree.py:954` — `_main_worktree` to find one — which from
inside a husk returns the **operator's checkout**, exactly the failure being
fixed. Use the repo-free half: `_repo_identity(path)` is not `None` **and** its
top level equals `path.resolve()`. That is the same first assertion
`factory/workgraph/worktree.py:1020` — `_worktree_ownership` makes, and its
docstring says why it is the one that matters.

**3. Do not put the check inside `_git`.** `factory/workgraph/worktree.py:1940` —
`_git` runs against target-repo clones as well as node worktrees, and the direct
`subprocess.run` calls at `factory/workgraph/worktree.py:2014` — `_is_ancestor`,
`factory/workgraph/worktree.py:2060` — `_branch_exists` and
`factory/workgraph/worktree.py:2071` — `_has_remote` run against `repo` paths that
are legitimately not worktrees. A blanket "cwd must be a worktree" breaks the
merge-base, branch and remote reads. Gate the two node-path call sites, FR-018.

**4. Exclude by workflow type; never tighten the epic id grammar.** The `epic-`
prefix is spelled at the five sites listed above, two of which construct real epic
ids (`factory/workgraph/cli.py:162` — `workflow_id`,
`factory/roadmap/workflow.py:195` — `_epic_id_for`). Making the readers' *id* test
stricter risks a real epic stopping being counted, which fails *open* — the roadmap
would over-dispatch. So exactly two moves are sanctioned and no third is. FR-019
changes what probes are **named**. FR-020 adds the `WorkflowType = "EpicWorkflow"`
clause to the visibility query and the matching check on `execution.workflow_type`
beside the id test — and that pair, not the rename, is what makes the workflow
already on the namespace stop counting, because nobody can rename it now. The
precedent is `factory/escalation/client.py:52-59`, whose comment says what the
clause is for in the tree's own words. What is **not** the fix: replacing the bare
literal at `factory/activities/roadmap_activities.py:775` — `_list_open_epics` with
`EPIC_ID_PREFIX`. Both are `"epic-"`; the substitution is a tidy-up and changes no
behaviour whatever, and a story that does only that has done nothing. Prove FR-021
against a real id from `factory/roadmap/workflow.py:195` — `_epic_id_for` carried on
an execution whose type is `EpicWorkflow`. And there are **two** readers, not one:
fixing `_list_open_epics` and leaving `factory/supervision/units.py:1302` — `listed`
alone is a half fix that the supervision teardown refusal will find (FR-024).

**5. US2 is not solved by a second environment variable, and it is not solved by
avoiding one either.** The finding is that a guard readable from `os.environ` gets
disabled during the mutation proof this repository requires. A second
`os.environ.get(...)` **in the same function** is one guard with two names —
mutation M12 would have removed the `if` containing both. But read
`factory/roadmap/schedule.py:255` — `_refuse_live_client` before concluding the
second defence must not read the variable at all: it does read it, and the pair
is still independent, because the two `if`s live in two functions and refuse two
different things — one refuses to *connect*, the other refuses to *act through* a
real client it was handed. Independence here is per mutation site, not per signal.
US2-S3 is the test that distinguishes a real pair from a disguised single: with
both disabled, it must attempt the connection. FR-007, FR-008.

**6. FR-009 wants exactly one door, and the tree holds an argument about doors.**
`factory/verify/store.py:378-381` — `connect` has an acknowledgment variable;
`factory/cli/repo.py:563-565` deliberately refuses to have one and says why.
Choose deliberately and say which in the commit body. The spec's answer is the
named opt-in of FR-010 and nothing else — no bare boolean, no marker file.

**7. A substring two refusals share is how a test passes for the wrong reason.**
Mutation M8 deleted the destination check from "export refuses a destination
inside the runtime root" and the test still passed, because the CLI had reached
the operator's real Temporal, found an open epic, and refused for *that* reason —
and both messages contained "runtime root". FR-005 is that incident turned into a
rule. When you write a refusal, grep the tree for the substring your test will
assert on, and record what you grepped in the commit body.

**8. The live markers are not decorative any more — two landed readers parse
them, and one asserts on their wording.** In August nothing passed `-m`, so the
2026-08-20 plan told US3 to rewrite the marker descriptions freely. Since 114
landed, `tests/conftest.py:766` — `_registered_live_tiers` splits every
registration at the literal `auto-skips unless `, and
`tests/test_114_us3_live_tier_summary.py:165` — `registered_live_tiers`
**asserts** that literal is present in every `live_*` registration and fails the
suite naming the marker if it is not. Rewriting the descriptions to drop the
phrase breaks a landed story. Keep the phrase; change what follows it, from a
credential to the opt-in. FR-025. The thing that still decides at run time is the
skip expression *inside* each module, which is what FR-014's enumerating test must
read — and after 114, `tests/test_live_notify.py:196` — `live_config` reads the
session stash rather than `os.environ`, so an enumerating test that only greps for
`os.environ` will report that module clean while it is the one that pages.

**9. `factory/worker.py` must still start.** FR-006. The worker is the one caller
that is *supposed* to reach production, and it is also the process that imports
everything else here. A guard that keys on "am I in a test" is correct; a guard
that keys on "is this the worker" is not, because a test that imports
`factory/worker.py:351` — `main` must not connect either. US6-S3 and US6-S4.

**10. There is a landed test that deliberately enters the unguarded client, and
deleting it is the wrong move.** `tests/test_runtime_root.py:124` —
`test_running_epic_ids_default_factory_raises_transport_not_nameerror` points
`TEMPORAL_ADDRESS` at a closed port and asserts the *real* default seam raises
`OperatorError` with `EXIT_TRANSPORT`. The finding
`hardening/repo-cli-open-client-has-no-pytest-refusal` names this test as the
reason the obvious fix was declined once already: "the implementer declined to
change a landed contract from inside an unrelated story, which was the right
call." It is no longer an unrelated story, so the decision is taken here — FR-022:
carry it forward asserting the choke point's refusal, and let US2-S3 be what
proves the transport branch through the sanctioned door. Do not delete it, and do
not weaken it to a skip.

**11. This spec touches eleven modules the worker imports live.** Do not land any
of it while an epic is in flight — the worker re-imports workflow code from disk
while activity modules stay passthrough from the stale process, which is a known
finding in its own right (`hardening/self-landing-stales-the-running-worker`).

**12. Criteria are provable from the diff and nothing else.** The judge sees the
diff and the story's acceptance scenarios — no base tree, no terminal, no commit
message. Every scenario says "proven by a committed test" for that reason. Where a
scenario needs runtime evidence, the evidence must be *pasted into a committed
file*, and the operator verification below is the operator's, not the judge's — do
not treat it as your acceptance bar.

**13. One test file per story, and one file two stories share on purpose.** Six
stories, six new files. Do not append to an existing test module: concurrent nodes
in separate worktrees both editing `tests/test_worktree.py` is a merge conflict the
queue resolves by rejecting somebody. The exceptions are the files the FRs name
explicitly — `tests/test_runtime_root.py` (FR-022, US1) and the six tier modules
(US3). Each of those belongs to one story, with one that does not:
`tests/test_live_capacity.py` is written by **both** US3, which converts the tier,
and US5, which rewrites two of its tests under FR-026. That is why US5 declares
`depends_on_merged: [US3]` instead of being dispatchable beside it, and why neither
implementer may tidy the other's half of that file.

**14. Never write outside your worktree.** The node worktree is nested inside the
operator's checkout, so `../` reaches real files and nothing enforces the
boundary. This is the spec whose subject is exactly that class; do not become an
occurrence of it.

**15. Do not delete or disable a live tier.** US3 changes how they are selected. A
tier that can no longer be run at all fails US3-S3 and removes the only evidence
anyone has that the live path works.

**16. The 2026-08-20 anchors in the ledger are stale too.** The finding
`hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix`
stores, in its `refs`, line 494 of `factory/activities/roadmap_activities.py` and
line 169 of `tests/test_live_capacity.py`. Neither resolves any more: 494 is a
blank line two above `drift_for_spec`, and 169 is a `task_queue=` keyword — both
unrelated to this spec. (They are written here in prose rather than as anchors on
purpose: they are quotations of a stale record, and an anchor that resolves would
misrepresent them as current.) Work from this plan's anchors, not from the ledger
row's; correcting the row is an operator act.

**17. The capacity tier's own positive case is an epic-prefixed probe id, and the
gate cannot see it break.** `tests/test_live_capacity.py:260` —
`test_capacity_read_finds_open_epic_workflows_and_excludes_others` mints
`epic-capacity-open` and `epic-capacity-closed` at
`tests/test_live_capacity.py:271-273` and asserts the production read **finds**
them; `tests/test_live_capacity.py:331` —
`test_capacity_read_excludes_continued_as_new_chain` asserts the same of
`epic-capacity-can`. Every one of those assertions is the inverse of FR-019 and
FR-020, and both tests carry `live_capacity`, so the declared `test` gate skips
them: US5 can land green over a landed live tier that is silently broken — the
failure class US3 exists to close. FR-026 is the instruction. The rewrite that
works keeps the probes and flips the assertions: the narrowed read counts none of
them, while a direct `client.list_workflows('ExecutionStatus = "Running"')` still
finds the same ids, so the tier keeps proving the status grammar it was written
for. What does **not** work is registering a probe under the production workflow
type to keep the old positive case alive — `tests/test_live_capacity.py:168` —
`_probe_worker` polls the production task queue, so a fake `EpicWorkflow` there is
a worse leak than the one being fixed.

**18. The eleventh site is guarded, not centralised — and migrating it must not
disturb either guard.** `factory/roadmap/schedule.py:165` —
`_default_schedule_client` is the one client construction in the tree that already
refuses, which is exactly why the draft of this plan left it out of every story
while FR-003 demanded that no module but the choke point construct a client. FR-023
owns it now. Take the connect and its lazy import at
`factory/roadmap/schedule.py:146` — `_default_schedule_client`, and nothing else:
`factory/roadmap/schedule.py:156-162` keeps refusing under `PYTEST_CURRENT_TEST`
and keeps naming `factory.roadmap.schedule._schedule_client_factory` as the seam to
bind, and `factory/roadmap/schedule.py:255` — `_refuse_live_client` is not touched
at all. They are the pair FR-007 is modelled on and US2 reads them as its exemplar;
removing either to "avoid duplication" deletes the only worked example of the thing
this spec is generalising. After the migration the two compose: guard one still
fires first, and a mutation that removes it now meets the choke point's refusal,
which the `except Exception` at `factory/roadmap/schedule.py:166-169` —
`_default_schedule_client` re-raises as `ScheduleUnavailable`. Keep that
translation: `tests/test_ergane_init_schedule.py:218` —
`test_the_default_client_refuses_to_connect_from_a_test` and
`tests/test_init_schedule_precondition.py:397` —
`test_nothing_in_this_phase_can_reach_a_real_temporal` both assert on it and are
landed contracts.

**19. A landed AST guard pins the resolver import in ten modules, nine of them
modules this spec migrates, and in those nine the resolver's only caller is the
connect site you are moving.** 048-US4 left
`tests/test_declared_temporal.py:423` —
`test_every_connect_site_reaches_the_one_resolver`, which walks the module list
at `tests/test_declared_temporal.py:392` (the tuple `_RESOLVER_SITES`, built from
`tests/test_declared_temporal.py:332`) and asserts each file contains an
`ImportFrom factory.controlplane.resolve` naming `resolve_temporal_target` or
`temporal_target_for`. The list is `worker.py`, `cli/nouns/__init__.py`,
`cli/main.py`, `cli/roadmap.py`, `cli/repo.py`, `workgraph/cli.py`,
`doctor/probes.py`, `controlplane/verify.py`, `roadmap/schedule.py` and
`notify/service.py`. The correspondence is close but **not exact, in both
directions**, and reasoning from a contract that is not there costs an attempt:
`cli/main.py` is in the tuple and neither story touches it — it holds no
`Client.connect` at all — while `factory/supervision/deploy.py`, which T068
migrates, is absent from the tuple. Keep deploy.py's lazy resolver import at
`factory/supervision/deploy.py:716` and its call at
`factory/supervision/deploy.py:720` anyway: FR-023 requires every caller to
resolve for itself, which is why T078 can assert on all seven even though the
landed guard only covers six of them. Grep the nine and you will find
that outside `factory/controlplane/verify.py:724` — `gather` and the second
probe site,
the resolver is called at the connect line and nowhere else. **The wrong move an
implementer will make**: delete the `target = resolve_temporal_target()` line
along with the `Client.connect` it fed, delete the now-unused import, and go red
on `tests/test_declared_temporal.py` under the declared `test` gate, on a contract
nothing in their prompt named. The right move: keep the resolution where it is and
hand its result to the choke point. FR-002 for US1's four, FR-023 for US6's seven;
US1-S6 and US6-S5 assert it. Do not edit `tests/test_declared_temporal.py` to make
this go away — `tests/test_namespace_one_literal.py:343` calls that guard's sibling
"the test this change is most likely to break", which is the tree telling you this
class is known.

**20. The choke point takes a resolved target. It does not resolve one.** Two of
the eleven callers cannot use a parameterless resolver, and no amount of care in
US6 can work around it. `factory/controlplane/verify.py:193` —
`_temporal_client_factory` must keep `temporal_target_for(config,
source=_DECLARED_SOURCE)`: its docstring records that config-first precedence as
048-US4's FR-016/SC-006, and
`tests/test_declared_temporal.py:274` —
`test_the_verify_probe_dials_the_address_the_worker_would_use` calls
`_temporal_client_factory(config.temporal)` and asserts which address was dialed.
`factory/supervision/deploy.py:749` — `asked` connects to `self._address` and
`self._namespace`, its own fields, set once at construction from
`factory/supervision/deploy.py:720` — not from the environment at connect time.
So the choke point's signature is `(address, namespace)` plus whatever seam and
refusal it adds, and every caller resolves for itself. **The wrong move**: give the
choke point a parameterless resolver, discover in US6 that two callers cannot use
it, and either regress 048's precedence or widen the choke point's module — which
Sizing forbids US6 to write and which US2 is editing at the same time
(`concurrent_with: [US2]`). FR-001, FR-004, T006.

**21. The FR-010 opt-in must be readable from `factory/`, and the idiomatic
pytest answer is not.** US3's node is shown its own story, its own FRs and this
plan — never US2's story and never FR-009
(`factory/workgraph/prompt.py:594` — `_requirement_sections`). So the sentence
that has to reach US3 is this one: FR-009 wires the choke point's stand-down to
the name FR-010 mints, and the choke point is production code in `factory/`. A
`-m live_capacity` marker expression, or a `--live-tiers` pytest option consumed
inside `tests/conftest.py`, satisfies every one of US3-S1 through US3-S6 and is
invisible to `factory/`; US2 would then merge after US3 with a two-file slice and
be unable to satisfy FR-009 without editing `tests/conftest.py` outside its slice
or minting a second door, which FR-009 forbids in the same sentence. Use an
environment variable naming the tiers, read the way
`factory/verify/store.py:378-381` — `connect` reads its acknowledgment through
`resolve_env_flag`. Selecting *inside* pytest on top of that value is fine — the
requirement is that the value itself is where production can see it. FR-010,
US3-S7.

**22. Binding `_open_epics_provider` to prove FR-020 proves nothing.**
`factory/activities/roadmap_activities.py:786-789` — `_open_epics_provider`
defaults to `_list_open_epics` and is read only by
`factory/activities/roadmap_activities.py:801` — `count_open_epics`. A test that
binds it hands back its own scripted set and then asserts on the set it just
supplied: **a test-only diff passes it with the production filter unwritten**,
which is exactly the vacuity FR-020 exists to close. Drive the real reader
instead: build executions carrying `.id` and `.workflow_type`, hand them to a
fake client's `list_workflows`, and run `_list_open_epics` through
`ActivityEnvironment(client=fake)` — `tests/test_live_capacity.py:202` —
`_running_ids` is the worked example, already landed. The same test captures the
query string the fake was asked, which is US5-S3. T051, T073.

**23. The landed tests bind the floor at `Client.connect`, not at your seam —
and your refusal fires first.** This is the class that refuted two earlier
repairs of this plan, and it is invisible to every anchor tier because nothing
about it is a moved line. Seven modules monkeypatch
`temporalio.client.Client.connect` and then drive a caller this spec migrates;
the list, with the entry point each one drives, is in "The landed floor-fakes"
above. Once that caller takes its client from a choke point that refuses under
`PYTEST_CURRENT_TEST`, the refusal happens *before* `Client.connect` is reached,
so the fake is never consulted and the test fails on the declared `test` gate.
`tests/test_ergane_status.py:485` — `fake_temporal` alone is used 57 times across
39 test functions. **The wrong move an implementer will make**: migrate the four
callers, run the story's own new test file, see it green, and open a PR that
reddens roughly a hundred landed tests in modules their prompt never named. **The
right move**: in the same story, rebind each of those fakes to the seam the choke
point declares — a one-line change per fixture — and do not delete or skip a
single test function. FR-027; US1 owns five modules, US6 owns two; T079 and T081.
The trio names one landed carry-forward besides these,
`tests/test_runtime_root.py:124` (FR-022, trap 10); that one is not the whole
list, and treating it as the whole list is how this survived two repairs.

**24. A second landed AST guard decides where the choke point may live, and it
is not the one trap 19 is about.** `tests/test_ergane_status.py:1600` —
`_cli_python_modules` collects every file under `factory/cli/` that contains
`await ` and one of `temporalio` / `RPCError` / `WorkflowQuery` /
`WorkflowAlreadyStartedError`, and
`tests/test_ergane_status.py:1716` —
`test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal` asserts
that this discovered set **equals** the table at
`tests/test_ergane_status.py:1516` and that, per module, the function set and
every `except` clause tuple match. The tempting home for a module whose first
four callers are all CLI entry points is `factory/cli/`; putting it there adds a
module to the discovered set and reddens a contract nothing in the prompt names.
Put it in `factory/controlplane/`, beside
`factory/controlplane/resolve.py:232` — `resolve_temporal_target`, and do **not**
re-export it from `factory/controlplane/__init__.py`, which is zero bytes on
purpose — `factory/controlplane/resolve.py:44-49` records that a re-export there
closes an import cycle at worker start. Two smaller halves of the same guard: a
migrated caller must keep *awaiting* (a synchronous choke point drops
`_open_client` out of the discovered set), and it must keep its `except` clause
tuple exactly — `('RPCError', 'RuntimeError', 'OSError')` for
`factory/cli/nouns/__init__.py:54` — `_open_client` and
`factory/cli/roadmap.py:205` — `_connect`, `('Exception',)` for
`factory/cli/repo.py:85` — `_open_client`. `factory/cli/repo.py` stays in the
discovered set after its `Client` import goes only because of
`factory/cli/repo.py:48`, its unrelated `ActivityEnvironment` import; leave that
line alone. FR-029, US1-S8, T080.

**25. The one sanctioned door must be proven against a dead port, never against
a resolved default.** US2-S4 is the only scenario in this spec that stands both
defences down and then *connects*. With nothing exported,
`resolve_temporal_target()` falls through to `factory/notify/service.py:129` and
`factory/notify/service.py:144` — localhost port 7233, namespace `ergane` — which
on the operator's host is the live control plane, so a test proving the door would
itself be the incident this spec exists to close. Its sibling T016 already pins
`TEMPORAL_ADDRESS` at 127.0.0.1 port 1; the door must too. The ledger row for
`hardening/mutating-a-production-safety-guard-escapes-the-sandbox` names this
omission as the missing instruction in so many words: "Briefs that ask for
mutation of a production-safety guard must also say how to make the escape
harmless: point the client at a dead port, use a scratch namespace, or unset the
credential." FR-030, T017.

**26. An enumerating test that resolves nothing passes forever.** FR-014's walk
goes from a registered `live_*` marker to the module that carries it. A mapping
that misses, or a glob that collects nothing, yields an empty set and a green
test with the requirement unwritten — the same vacuity trap 22 closes for FR-020
and the same one the tree already closes for its own sweeps at
`tests/test_ergane_status.py:1747` —
`test_the_discovered_module_set_contains_status_and_build`. Assert the enumerated
set is non-empty and names at least `tests/test_live_notify.py` and
`tests/test_live_capacity.py`. FR-014, US3-S5, T027.

**27. The compiled work graph beside this file was stale for three weeks, and a
manual `build start` would have shipped five stories out of six.**
`specs/074-a-test-cannot-reach-the-operators-floor/workgraph.json` held five
nodes against a six-story spec, with a dependency chain (`us4←us1`, `us5←us4`)
that the live derivation does not produce. It was regenerated on 2026-09-08 and
now holds six nodes at chain depth 2 (`us2←us1,us3`; `us5←us3`; `us6←us1`), so
this spec is **two rounds of work, not six**. The trap generalises: the roadmap
derives its graph in-process and never writes it back, so the on-disk artefact
drifts silently, while `ergane build start` reads it off disk. If you regenerate
it again, diff the node count against `grep -c '^### User Story' spec.md` before
trusting it.

**28. A neighbouring defect was filed on 2026-09-07 and is deliberately NOT in
this spec's `fixes:`.** `tooling/gate-commit-inherits-the-callers-live-tier-environment`
(warning, one sighting) is the same *family* as this spec — a tool reaching the
operator's live floor because the ambient environment let it — but a different
*mechanism*: a shell script inheriting `TEMPORAL_*` and `LITELLM_*` from the
caller, not a Python process failing a pytest guard. It is named here so you
recognise it if you trip it, and it is absent from `fixes:` on purpose. A
`fixes:` list longer than the functional requirements justify is a claim, not a
fix — the standing lesson from 092 and 100 — and nothing in FR-001 to FR-020
changes how `scripts/gate-commit` builds its environment. If you believe US3's
work does close it, say so in the PR body and let an operator report the
occurrence; do not edit the frontmatter to claim it.


## Sizing

**Re-sliced 2026-09-08.** US1, US3 and US6 ran to sixteen, seventeen and fifteen
tasks. Thirty stories landed on `ergane-buildout` in the current window and every
one of them had **fewer than twelve**; the largest landed diff was 64,887 bytes
against a 65,536 refusal, clearing by 649. Three stories were therefore cut in
two — US1/US7, US3/US8, US6/US9 — and the largest story here is now eleven tasks.
The paragraphs below were written for the pre-split stories, so read each one
against the Work Graph rather than as a per-story budget: US1's paragraph now
covers US1 **and** US7 together, US3's covers US3 and US8, US6's covers US6 and
US9. The split does not reduce the total diff; it divides it, which is the point,
because a story refused for size is not retried smaller — it burns the attempt
and the epic re-slices around it anyway, at full price.


**US1** — one new module in `factory/controlplane/` (~80 lines with its
docstring), four call-site edits of roughly three lines each, one new test file,
the carry-forward edit to `tests/test_runtime_root.py`, and the five landed
modules trap 23 names: `tests/test_ergane_status.py`,
`tests/test_roadmap_schedule_discovery.py`,
`tests/test_roadmap_wedge_visibility.py`,
`tests/test_teardown_owns_the_ordering.py` and `tests/test_ergane_spec.py`.
Eleven files rather than six — but the five added ones are one fixture line each
plus the carry-forward of
`tests/test_teardown_owns_the_ordering.py:631` —
`test_roadmap_py_is_not_edited_by_this_story`, so perhaps thirty lines of diff
between them, not five files' worth of story. Comparable landed stories: 107-US1
at 37.6 KiB, 100-US1 at 28.9 KiB. Still comfortably inside the 64 KiB refusal —
and there is no way to make it smaller, because a fake that keeps binding
`Client.connect` after the migration is a red gate rather than a deferred edit.

**US6** — seven call-site edits (the six of the 2026-08-20 table plus
`factory/roadmap/schedule.py`, whose connect moves and whose two guards stay), one
new test file with a case per caller plus the tree-walking test, and the two
landed modules trap 23 names: `tests/test_doctor_probes.py` (one fixture line)
and `tests/test_declared_temporal.py` (the fixture plus the two dial tests
FR-028 carries forward, perhaps fifteen lines). Ten files, no new
module: US6 imports the choke point and does not write it — which is only possible
because trap 20 fixed its signature to take an already-resolved target. A choke
point that resolved for itself would have forced US6 to widen the module US2 is
editing in parallel. Comparable: 114-US3 at 22.2 KiB.

The old single US1 was the choke point *plus* all ten migrations *plus* ten
per-caller tests *plus* the tree-walking test *plus* pasted evidence in one node.
057-US2 reached 52.8 KiB for less, and the refusal is measured on the assembled
diff with evidence included (D-050). Split before dispatch, not during: a node is
one PR and an implementer cannot split itself.

**US2** — two defences and five tests, in the choke point module plus its test
file. Two files. Small and dense.

**US3** — six tier modules, `tests/conftest.py`, `pyproject.toml` and one new test
file. Nine files but small edits each; 114-US3 touched a comparable set at
22.2 KiB.

**US4** — `factory/workgraph/worktree.py` and one new test file. Two files.

**US5** — `factory/activities/roadmap_activities.py`,
`factory/supervision/units.py`, `tests/test_live_capacity.py` (the probe id, plus
FR-026's rewrite of the two live tests) and one new test file. Four files; each
production edit is one query clause and one type check.

Files shared between stories — stated as files, not as production files, because
the collision that costs an attempt does not care which kind it was. US1 writes the
choke point module; US6 only imports it, so `depends_on_merged: [US1]` there is
about the module existing in US6's base rather than about US6 editing it. US2 does
edit it — both defences live in it — which is why US2's edge on US1 is a merge edge
and not the pass edge the draft carried. US3 and US5 both write
`tests/test_live_capacity.py` (trap 13), hence `depends_on_merged: [US3]` on US5.
The landed test modules trap 23 adds do not create a new collision: US1's five
and US6's two are disjoint sets, and no other story names any of the seven.
US4 shares no file with anyone. US4 and US5 both *mention*
`factory/cli/nouns/build.py` in their task slices and neither edits it, which is
what `concurrent_with` on US5 declares. Apart from that one test file, US3's surface
— `tests/` and `pyproject.toml` — meets nobody else's.

## Verification the operator will run, independent of the gate

1. With `PYTEST_CURRENT_TEST` set and `TEMPORAL_ADDRESS` pointed at the operator's
   real control plane, call each of the eleven entry points and read eleven
   refusals — the worker's included, because FR-004 refuses on the test process and
   not on the caller. None may reach the network. Then unset `PYTEST_CURRENT_TEST`
   and repeat: the worker connects and every CLI caller behaves as it does today.
   That pair is what FR-004 and FR-006 assert between them; reading only the first
   half would reject a correct implementation.
2. Run `grep -rn "Client.connect" factory/ --include=*.py`. Two lines may come
   back: the choke point's own call, and the comment at
   `factory/controlplane/verify.py:732` — `gather`, which is prose and must
   survive. Anything else is a missed migration. This grep is not FR-003's test —
   the test parses code precisely because the grep cannot tell those two apart.
3. Neutralise the `PYTEST_CURRENT_TEST` refusal the way mutation M12 did —
   replace its condition with a constant false — run the full suite, and compare
   `temporal schedule list` and `temporal workflow list` taken before and after.
   No schedule and no workflow may appear that was not there before. This is the
   incident of `hardening/mutating-a-production-safety-guard-escapes-the-sandbox`,
   re-run, and it is the one step no agent may attempt.
4. With `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` exported and no tier named,
   run the full suite and read the skip line for the live Telegram test. Confirm
   the phone stayed quiet.
5. Name the Telegram tier with its credentials unset and read the failure naming
   the missing credential. Then name it with credentials present and confirm the
   tier runs — trap 15's control.
6. Build a husk — a node worktree whose `.git` file has been deleted — aim
   `ergane build reset` at it, and compare `git status --porcelain` and
   `git rev-parse HEAD` for the operator's checkout before and after. Both must be
   unchanged. Repeat by driving the salvage route.
7. Hand a listing containing `epic-capacity-can-3d2bb231` under a probe's workflow
   type to both open-epic readers and confirm both counts exclude it, and that a
   real epic id from `factory/roadmap/workflow.py:195` — `_epic_id_for` on an
   `EpicWorkflow` execution is still counted by both. Then read the query each
   reader sends and confirm both carry the `WorkflowType` clause.
8. Run the capacity tier against a real Temporal — a server up, the tier named —
   and read it green. The declared `test` gate skips that tier, so US5's rewrite of
   it is checked here or nowhere (trap 17).
9. Run `uv run pytest tests/test_declared_temporal.py -v` against the finished
   tree and read `test_every_connect_site_reaches_the_one_resolver` and
   `test_no_connect_site_keeps_its_own_copy_of_the_temporal_contract` green, with
   the collected count quoted — a mistyped node id collects nothing and reports
   success. Then read `git diff main -- tests/test_declared_temporal.py`: in
   US1's diff it must be empty, and in US6's it may touch only
   `tests/test_declared_temporal.py:264` — `dialed`,
   `tests/test_declared_temporal.py:274` —
   `test_the_verify_probe_dials_the_address_the_worker_would_use` and
   `tests/test_declared_temporal.py:303` —
   `test_the_probe_snapshot_names_the_server_it_actually_dialed` (FR-028) — never
   the two tuples and never the two AST guards. This is trap 19's control, and
   the declared gate runs it too, which is why an implementer that "fixed" a
   guard rather than a caller would still be green here; the *shape* of that diff
   is the part only the operator checks.
10. Run the seven landed floor-fake modules by name — `uv run pytest
   tests/test_ergane_status.py tests/test_roadmap_schedule_discovery.py
   tests/test_roadmap_wedge_visibility.py tests/test_teardown_owns_the_ordering.py
   tests/test_ergane_spec.py tests/test_doctor_probes.py
   tests/test_declared_temporal.py -q` — and read them green with the collected
   count quoted. This is trap 23's control. The declared gate covers it too, so
   what the operator is really checking is that the count did not *drop*: FR-027
   forbids deleting or skipping a test to make the migration green, and a deletion
   is invisible in a green run.
11. Before dispatch, and before any flip to `ready`: clear the compiled artefact
   beside this file. `rm specs/074-a-test-cannot-reach-the-operators-floor/workgraph.json`,
   or re-derive it against the refined spec.md, and confirm the graph that comes
   back has **six** nodes and knows FR-022 through FR-030. The one on disk was
   compiled on 2026-08-23 at the five-story shape, `ergane build start` resolves
   `<specs_root>/<epic_id>/workgraph.json` off disk
   (`factory/cli/nouns/build.py:2147` — `resolve_reset_graph`), and the roadmap
   dispatches a `ready` spec itself without waiting for an operator — so a flip
   with the stale file present hands every node a criteria set from before this
   refinement. This is an operator act: no refinement run has been permitted to
   write or delete that file.
