---
state: draft
depends_on_landed:
  - 073-the-ledger-triages-what-it-can-prove
  - 107-a-landing-refuses-before-the-build-not-after
  - 114-the-live-smoke-runs-or-the-suite-says-why
fixes:
  - hardening/repo-cli-open-client-has-no-pytest-refusal
  - hardening/a-story-created-five-live-roadmap-schedules-that-paged-the-operator
  - hardening/reset-commits-the-operator-checkout
  - notify/live-telegram-smoke-pages-the-operator-from-every-agent-suite-run
  - hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix
# Drafted 2026-08-20 10:30 AM CT by an operator session, from a triage pass over
# the 143 findings that survived the 2026-08-20 sweep. Six of them — five
# critical — are one mechanism wearing five faces, and that mechanism has already
# emptied this repository's runtime root once, created five live schedules on the
# production namespace, committed 33 files of operator scratch to a branch, and
# paged the operator from a test.
#
# This spec is the declared fix for:
#   hardening/repo-cli-open-client-has-no-pytest-refusal                   (critical)
#   hardening/mutating-a-production-safety-guard-escapes-the-sandbox       (critical)
#   hardening/a-story-created-five-live-roadmap-schedules-that-paged-the-operator (critical)
#   hardening/reset-commits-the-operator-checkout                          (critical)
#   notify/live-telegram-smoke-pages-the-operator-from-every-agent-suite-run (critical)
#   hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix (critical)
#
# Those six lines become a `fixes:` frontmatter key once 073/US1 lands and widens
# the grammar. Until then the frontmatter grammar is closed to `state` and
# `depends_on_landed`, and a `fixes:` key here would be refused by
# `ergane spec validate` — so this comment is the declaration, exactly as 072
# does it.
#
# DO NOT FLIP READY without a pre-dispatch review.
#
# WHERE THIS CAME FROM. Five incidents in eight days, all one mechanism: a test
# process reaching the operator's production floor. The runtime root emptied
# (2026-08-14), the operator's checkout committed by a salvage aimed at a husk
# (2026-08-15), five unpaused schedules created on the production namespace by a
# mutation battery (2026-08-16), the repo CLI dialling real Temporal from a unit
# test and passing for the wrong reason (M8, 2026-08-16), and a live Telegram
# smoke paging the operator's phone from every suite run (2026-08-17).
#
# WHAT IT COST, MEASURED. One live runtime root emptied and restored from restic.
# Thirty-three files of operator scratch committed as `396611b`. Five schedules
# on a 5-minute cadence whose four failed runs wrote a failure count against the
# real roadmap's id and paged the operator. One leaked probe workflow,
# `epic-capacity-can-3d2bb231`, still counted as an open epic by the capacity
# read. One landed test (M8) that passed with its subject deleted.
#
# NOT IN SCOPE. The second-order damage in the schedules finding — `ergane
# roadmap status specs` resolving to a test's failed run — is a `_locate` defect
# filed as `cli/roadmap-status-resolves-to-a-failed-run`; it survives independently
# of how the corpse got there and folding it in would give US1 a second subject.
# The five leaked schedules were deleted by an operator on 2026-08-16 and are not
# this spec's to clean up. This spec does not delete any live tier, does not
# change what a gate runs, and does not touch the merge queue.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at 602a92c.
# DO NOT FLIP READY without a pre-dispatch review — the hold above still stands.
#
# ANCHORS. Drafted against `a58ec93`; thirty-six unique anchors re-read, and only
# the five into `factory/roadmap/schedule.py` had not moved. Twelve were refusals.
# The dangerous ones were not the moved lines but the moved *meaning*: every
# `factory/cli/repo.py` citation in the gap statement now lands inside
# `_override_disagreement` rather than `_refuse_unsafe_removal`, and the seven
# sibling `is_dir()` gates the plan told US4 to enumerate do not exist at those
# lines any more.
#
# THE TABLE WAS SHORT BY ONE, AND THAT WAS THE EXPENSIVE FIND. 082-US2 landed
# `factory/supervision/deploy.py:749` — `asked` on 2026-08-22, an eleventh
# `Client.connect`. Ten sites are unguarded now, not nine. FR-003's tree-walking
# test cannot pass until the tenth is migrated, so an implementer working the old
# list would have failed its own test with no idea why. FR-023 names it.
#
# TWO STORIES CHANGED SHAPE UNDER LANDED NEIGHBOURS. 107 wrote
# `_worktree_ownership` — the check US4 was told to invent — and wired it into
# `ensure`, `push_branch`, `sync_with_target` and preflight, but NOT into
# `salvage` or `_archive_node`, which are the two routes this finding names. US4
# survives whole; its instruction is now "reuse `_repo_identity`", not "write a
# new helper". And 114 moved the Telegram credential out of `os.environ` into a
# session stash the smoke still consumes, so the defect is alive with a new
# mechanism — while 114's own suite now asserts that every live marker keeps the
# literal `auto-skips unless `, which the old US3 was going to delete. FR-025.
#
# US1 IS SPLIT. Ten call sites, ten per-caller tests, a tree-walking test and
# pasted evidence in one node is over the 64 KiB diff refusal at the rate landed
# stories run (057-US2 was 52.8 KiB for less). US1 keeps the choke point and the
# four CLI callers; the new US6 takes the six remaining callers, FR-003 and
# FR-006. Nothing was renumbered; no story of this spec has landed.
#
# THE KEYS. Five of the six declared, back-filled into `fixes:` now that 073 has
# widened the grammar. The sixth,
# `hardening/mutating-a-production-safety-guard-escapes-the-sandbox`, is
# `resolved` in the ledger (2026-08-22, `050-init-preconditions`) and is NOT
# declared here; it stays in the argument because it is the reason US2 exists at
# all, not because this spec closes it. `factory/workgraph/adapter.py:104` also
# no longer passes `TELEGRAM_BOT_TOKEN` to an agent, so the notify finding's
# agent half is already gone and US3 closes the operator-suite half that remains.
#
# THE COMPILED ARTIFACT BESIDE THIS FILE IS STALE. `workgraph.json` here was
# derived at the 2026-08-20 five-story shape and knows nothing of US6 or of
# FR-022 through FR-025. `ergane build start` reads a compiled graph off disk, so
# dispatching from it would hand every node a criteria set from before this
# refinement. The operator deletes or re-derives it; this refinement is not
# permitted to write it.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against the same sha 602a92c,
# after an adversarial review refuted the draft above on five counts, none of
# them an anchor. The eleventh `Client.connect` — `factory/roadmap/schedule.py`,
# guarded but still a construction site — belonged to no story while FR-003
# demanded that it belong to none, so FR-023 now migrates seven callers and keeps
# that module's own refusal and `_refuse_live_client` exactly where they stand.
# FR-020's only instruction was a constant substitution that changes nothing
# (`EPIC_ID_PREFIX` is the same literal it replaces), so the exclusion is now by
# workflow *type*, using the `WorkflowType` clause the escalation reader already
# pins and documents. The landed live test
# `test_capacity_read_finds_open_epic_workflows_and_excludes_others` asserts the
# inverse of FR-019/FR-020 and carries `live_capacity`, so the declared `test`
# gate skips it and nothing would have caught it breaking: FR-026 rewrites that
# tier inside US5. US2's pass edge on US1 became a merge edge, because its whole
# slice edits the module US1 creates; US5 gained one on US3, because both write
# `tests/test_live_capacity.py`. Minor: FR-003's walk must decide on code, since
# `factory/controlplane/verify.py:732` carries the literal inside a comment, and
# FR-023's list and the site table are now in the symbol-anchor form.
# DO NOT FLIP READY without a pre-dispatch review — the hold above still stands.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, same sha 602a92c,
# after two lenses refuted the block above on six counts — none of them an
# anchor, all of them a landed contract or a seam. THE LANDED AST GUARD: 048-US4
# left `tests/test_declared_temporal.py:423` —
# `test_every_connect_site_reaches_the_one_resolver`, which walks ten named
# modules and asserts each imports a resolver from `factory.controlplane.resolve`;
# in every one of them that import serves only the connect site US1 and US6
# migrate, so the migration as written deleted the import and reddened the
# declared `test` gate on a contract no FR named. FR-002 and FR-023 now require
# each caller to keep its own resolver call, US1-S6 and US6-S5 assert it, and
# trap 19 reproduces it. THE CHOKE POINT'S SHAPE: it now takes an
# already-resolved target and resolves nothing, because
# `factory/controlplane/verify.py:193` — `_temporal_client_factory` must keep
# `temporal_target_for(config, …)` (048's config-first precedence, pinned by a
# landed test) and `factory/supervision/deploy.py:749` — `asked` connects to its
# own `self._address`; a parameterless resolver would have forced US6 to edit the
# module Sizing forbids it to touch. FR-001 is now the choke point's existence
# and shape only; exclusivity is FR-002, FR-023 and FR-003. THE FR-010 OPT-IN IS
# PINNED: it must be readable from `factory/` at connect time, in the shape
# `factory/verify/store.py:378-381` — `connect` already uses, because US3 is
# shown neither FR-009 nor US2's story and the idiomatic pytest answer would be
# invisible to the code FR-009 wires. US3-S7 asserts it; FR-009 now forbids a
# bare *boolean* environment variable rather than the mechanism FR-010 needs.
# US5-S2 WAS VACUOUS: T051 bound `_open_epics_provider`, which replaces the
# reader whose new filter is the whole of FR-020, so a test-only diff passed it;
# it now drives the real reader through `ActivityEnvironment`, the way
# `tests/test_live_capacity.py:202` — `_running_ids` already does. Minor: FR-005
# is now owned by US4 as well as US1, so T048's citation resolves inside US4's
# slice; T044 no longer tells `salvage` to reuse a refusal whose every branch
# names a repository `salvage` is not given; `tests/test_114_us3_live_tier_summary.py:175`
# — `scratch_session` is named as US3's harness. PROVENANCE CORRECTION: the block
# above credits `factory/workgraph/adapter.py:104` (the tuple `PASSTHROUGH_ENV`)
# with
# closing the notify finding's agent-suite half. The ledger row records that
# tuple as already `("PATH", "LANG", "TERM")` on 2026-08-17 when the leak was
# measured, so it is the allow-list, not the fix; the mechanism is `--clearenv`
# at `factory/workgraph/adapter.py:491` — `_build_argv`, launched with no `env=`
# at `factory/workgraph/adapter.py:694` — `launch`. The conclusion stands — the
# agent half is closed and US3 closes the operator-suite half — only the line an
# operator would re-read was wrong. `workgraph.json` beside this file is still
# the stale 2026-08-20 five-story artefact; this run is not permitted to write or
# delete it, and plan.md step 10 and T072 remain the operator's instruction.
# DO NOT FLIP READY without a pre-dispatch review — the hold above still stands.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, same sha 602a92c,
# after an adversarial review refuted the block above on five counts — again not
# one of them an anchor, all of them a landed test contract or an address nobody
# pinned. THE FAKES ARE INSTALLED AT `Client.connect`, NOT AT A FACTORY SEAM.
# Seven landed test modules monkeypatch `temporalio.client.Client.connect` and
# then drive the very callers this spec migrates; once those callers take their
# client from a choke point that refuses under `PYTEST_CURRENT_TEST`, the refusal
# fires before the fake is consulted and roughly a hundred landed tests go red on
# the declared `test` gate, on a contract no requirement named. FR-027 makes
# rebinding each fake part of the story that migrates the caller it drives and
# names all seven with their story; trap 23 reproduces the class. THE
# IMPOSSIBILITY: FR-023 migrates `factory/controlplane/verify.py:193` —
# `_temporal_client_factory` while FR-023, T013, T070 and plan step 9 all
# demanded an empty diff on `tests/test_declared_temporal.py`, whose `dialed`
# fixture and two dial tests need a real dial through that function under pytest.
# There was no legal implementation. FR-028 takes the decision here: the fixture
# and those two tests are carried forward onto the choke point's seam, both AST
# guards and both module tuples stay untouchable, and the empty-diff evidence
# becomes a scoped-diff evidence in US6 only. THE SECOND LANDED AST GUARD:
# `tests/test_ergane_status.py:1516` pins every migrated CLI function's `except`
# clauses and derives its module set from `factory/cli/**`, so a choke point
# placed under `factory/cli/` — a plausible home for a module whose first four
# callers are CLI entry points — reddens a contract the trio never named. FR-029
# fixes the home at `factory/controlplane/`, beside `resolve.py`. THE SANCTIONED
# DOOR HAD NO ADDRESS: US2-S4 stood both defences down and connected without
# pinning `TEMPORAL_ADDRESS`, which resolves to `factory/notify/service.py:129`,
# this host's own floor — the one test proving the door would have been the
# incident. FR-030 pins a closed port for every stand-down test, in the words the
# ledger row itself uses. Minor: FR-014's enumerating test may no longer pass on
# an empty walk; the plan's `git add -A` list said two where the tree holds three;
# trap 19's module list is corrected in both directions; T070's pre-migration
# grep returns eight in US6's base, not eleven. `workgraph.json` beside this file
# is still the stale 2026-08-20 five-story artefact, this run is still not
# permitted to write or delete it, and plan.md step 10 and T072 now name the
# command and the six-node check the operator must see before any flip.
# DO NOT FLIP READY without a pre-dispatch review — the hold above still stands.
---

# Feature Specification: a test cannot reach the operator's floor

**Created**: 2026-08-20
**Depends on**: 073 (the `fixes:` grammar), 107 (`_worktree_ownership`, which US4
reuses) and 114 (the live-tier report and credential stash, which US3 rewires) —
all landed.

## The gap, stated precisely

This repository already knows the shape of the answer. It is written down, in
prose, at `factory/cli/repo.py:560` — `_refuse_unsafe_removal`:

> A convention is not a boundary for an act that deletes.

That sentence was paid for on 2026-08-14, when a process satisfying a test
emptied the live runtime root. D-045 turned it into a boundary at the one choke
point every deletion goes through, and the class has not recurred.

**The same sentence is true of an act that reaches production, and there it is
still only a convention.** The binding is a seam in `tests/`; the enforcement is
one `PYTEST_CURRENT_TEST` check on one module out of eleven. The chain is four
steps, and each one is a line in this tree:

1. Eleven call sites in `factory/` construct a real Temporal client, and exactly
   one of them refuses first: `factory/roadmap/schedule.py:156` —
   `_default_schedule_client` raises before the connect at
   `factory/roadmap/schedule.py:165` — `_default_schedule_client`. Guarded is not
   the same as centralised: that module still builds its own client, so it is one
   of the eleven sites FR-023 migrates, keeping its refusal where it is.
2. `PYTEST_CURRENT_TEST` appears in three modules only —
   `factory/roadmap/schedule.py:156` — `_default_schedule_client`,
   `factory/verify/store.py:378` — `connect` and `factory/cli/repo.py:570` —
   `_refuse_unsafe_removal`. Ten client constructions are outside all three.
3. The sharpest evidence that this is a convention and not a boundary is that two
   of those ten are in a file that *has* the guard: `factory/cli/repo.py` guards
   its deletion path at `factory/cli/repo.py:553-579` and leaves its client
   constructor open at `factory/cli/repo.py:80-90` — `_open_client`.
4. So a test that forgets to bind a seam does not fail and does not error. It
   consults the operator's production control plane and its verdict depends on
   what the floor happens to be doing.

### Measured against `602a92c`

| site | guarded under pytest |
| --- | --- |
| `factory/roadmap/schedule.py:165` — `_default_schedule_client` | **yes** — `factory/roadmap/schedule.py:156-162` |
| `factory/workgraph/cli.py:969` — `_connect` | no |
| `factory/cli/nouns/__init__.py:54` — `_open_client` | no |
| `factory/cli/roadmap.py:205` — `_connect` | no |
| `factory/cli/repo.py:85` — `_open_client` | no |
| `factory/doctor/probes.py:491` — `_gather_async` | no |
| `factory/doctor/probes.py:603` — `_closed_epics_from_temporal` | no |
| `factory/controlplane/verify.py:193` — `_temporal_client_factory` | no |
| `factory/notify/service.py:1048` — `main` | no |
| `factory/worker.py:342` — `main` | no |
| `factory/supervision/deploy.py:749` — `asked` | no |

The last row landed on 2026-08-22, after this spec was drafted, in a file the
original table did not name. That is the whole argument for FR-003 in one line: a
list of call sites rots, and a test that walks the tree does not.

Eleven rows, not ten: the guarded row is still a module that constructs a client,
and FR-001 is a claim about construction rather than about guarding. A twelfth
occurrence of the literal is not a call at all — `factory/controlplane/verify.py:732`
— `gather` carries `Client.connect` inside a comment, which is why FR-003's walk
has to decide on code rather than on text.

And what stands in for a boundary is not one seam: it is seven modules' worth of
monkeypatch, every one of them installed at the constructor rather than at a
factory seam. `tests/test_ergane_status.py:485` — `fake_temporal`,
`tests/test_roadmap_schedule_discovery.py:311` — `fake_temporal`,
`tests/test_roadmap_wedge_visibility.py:219` — `fake_temporal`,
`tests/test_teardown_owns_the_ordering.py:213` — `_host`,
`tests/test_ergane_spec.py:448` — `test_validate_opens_no_socket`,
`tests/test_doctor_probes.py:295` — `fake_temporal` and
`tests/test_declared_temporal.py:269` — `dialed` each replace
`temporalio.client.Client.connect` and then drive one of the eleven rows above.
That is the convention in its purest form — and it is also what the replacement
breaks. A choke point that refuses before `Client.connect` is reached makes every
one of those fakes unreachable, so roughly a hundred landed tests go red unless
the story that moves a caller also moves the fake that drives it. FR-027 and
FR-028 are that instruction, taken here rather than met as a red suite.

### What that costs, in incidents rather than in theory

- **`hardening/repo-cli-open-client-has-no-pytest-refusal`.** Mutation M8 deleted
  the destination check from "export refuses a destination inside the runtime
  root" and **the test still passed** — it had dialled the operator's real
  Temporal, found a genuinely open epic, and refused for that reason instead.
  Exit 1 either way, and the asserted substring "runtime root" appears in both
  messages. The finding names its own blocker:
  `tests/test_runtime_root.py:124` —
  `test_running_epic_ids_default_factory_raises_transport_not_nameerror`
  deliberately enters the real client factory and asserts a transport error, so
  adding the refusal breaks a landed contract unless the story carries it forward
  on purpose. FR-022 is that decision, taken here rather than left to an
  implementer.
- **`hardening/a-story-created-five-live-roadmap-schedules-that-paged-the-operator`.**
  Five unpaused schedules on the production namespace, 5-minute cadence, pointed
  at pytest temporary directories. Four `RoadmapWorkflow` runs failed, the failure
  counter was written against the *real* roadmap's id, and 031's notifier paged
  the operator's phone.
- **`notify/live-telegram-smoke-pages-the-operator-from-every-agent-suite-run`.**
  The live Telegram smoke skips only on *absent* credentials. 114 moved the
  credentials out of the environment into `tests/conftest.py:521` and the smoke
  now consumes that stash at `tests/test_live_notify.py:196` — `live_config`, so
  an operator with a token in their shell still arms it by existing.

### The part that makes a third guard necessary rather than tidy

`hardening/mutating-a-production-safety-guard-escapes-the-sandbox` is resolved in
the ledger and is not declared by this spec, but its argument is why US2 exists.
This repository requires mutation proof that a behaviour is not vacuous. **The
strongest mutation against a safety guard is disabling the guard.** Mutation M12
replaced the `PYTEST_CURRENT_TEST` check inside `_default_schedule_client` with
`if False:` — the correct thing to do when proving that check is load-bearing —
and the suite then created the five live schedules above.

So the practice this factory depends on for test honesty is, for one class of
code, an operation that reaches production. A single env-var guard is therefore
not merely thin; it is *guaranteed to be disabled at least once per proof*.

`factory/roadmap/schedule.py:22-26` already states the answer and already
implements it for one module:

> two independent guards are the enforcement — `_default_schedule_client` will
> not connect under `PYTEST_CURRENT_TEST`, and `_refuse_live_client` will not
> mutate through a real client under it. Removing either alone still refuses.

`factory/roadmap/schedule.py:255` — `_refuse_live_client` is the second half, and
reading it settles what "independent" means here: it reads the *same* environment
variable, in a *different function*, against a *different subject* — the client it
was handed rather than the connection it is about to open. Independence is per
mutation site, not per signal. This spec generalises that sentence to every
module. It invents nothing.

### Two neighbours in the same class

- **`hardening/reset-commits-the-operator-checkout`** (2 occurrences). A git
  operation pointed at a *husk* node path — a worktree directory whose `.git`
  file is gone — walks up and resolves to the operator's checkout. It arrived
  twice by two routes, and both routes still exist: `salvage` refuses only on
  `factory/workgraph/worktree.py:531` — `salvage` before running `git add -A` at
  `factory/workgraph/worktree.py:538` — `salvage`, and the teardown route reaches
  `factory/workgraph/worktree.py:1766` — `_archive_node`, which stages at
  `factory/workgraph/worktree.py:1768` — `_archive_node` behind the same
  `is_dir()`. 107 closed this class on four other paths and not on these two.
- **`hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix`**
  (2 occurrences). A leaked probe workflow was named `epic-capacity-can-3d2bb231`,
  minted by `tests/test_live_capacity.py:176` — `_probe_id`. The production worker
  fails its tasks — the class is not registered — and
  `factory/activities/roadmap_activities.py:774` — `_list_open_epics` counts it as
  an open epic, so a leaked test artefact silently consumes a concurrency slot the
  operator cannot see. A second reader of the same grammar landed since:
  `factory/supervision/units.py:1302` — `listed`.

## The rule this spec is asking for

**A process running under pytest cannot reach the operator's control plane, cannot
write to a directory no repository owns, and cannot select a live tier by holding
a credential — and each of those refusals survives the removal of any one guard.**

The four cases a client construction can be in, complete:

| under pytest | sanctioned tier opted into | both defences present | result |
|---|---|---|---|
| no | — | — | connects, byte-identical to today |
| yes | no | yes | **refused twice**, either refusal alone sufficient |
| yes | no | one removed by mutation | **still refused**, by the survivor |
| yes | **yes** | yes | connects — the one door, named in FR-009 |

### What this spec is not

It is not a ban on live tiers. Every tier stays runnable; US3 changes only what
selects one, and a tier that can no longer be run at all fails US3-S3.

It is not a second `PYTEST_CURRENT_TEST` check in the same function. Two reads of
one signal inside one `if` is one guard with two names, and the mutation that
found this class would have removed both at once.

It is not a fix for `ergane roadmap status specs`. That is a `_locate` defect
filed separately; it survives independently of how a failed run got onto the
namespace.

It is not a narrowing of what an epic id is. FR-019 changes what a *probe* is
named, and FR-020 excludes on the workflow **type** an execution was started as —
a fact about what a workflow is rather than about what somebody called it.
Tightening the id grammar instead would fail open: a real epic would stop being
counted and the roadmap would over-dispatch.

## User Scenarios & Testing

### User Story 1 - One place builds a real client (Priority: P1)

As an operator, every real Temporal client in the factory is constructed at one
choke point, so there is one place to guard and a new caller cannot miss it.

**Why this priority**: P1 and it depends on nothing. US2 has nothing to harden
until the choke point exists, and the unguarded sites are the surface every other
story's incident came through.

**Independent Test**: Ask the choke point for a client with `PYTEST_CURRENT_TEST`
set and read the refusal; drive each of the four migrated CLI callers with the
choke point's seam bound to a fake and read what they do.

**Acceptance Scenarios**:

1. **Given** `PYTEST_CURRENT_TEST` is set, **When** any caller asks the choke
   point for a client, **Then** it refuses, and the refusal names the address, the
   namespace and the seam the test should bind instead — proven by a committed
   test asserting all three strings, modelled on
   `factory/roadmap/schedule.py:156-162`.
2. **Given** the four callers `factory/workgraph/cli.py:969` — `_connect`,
   `factory/cli/nouns/__init__.py:54` — `_open_client`,
   `factory/cli/roadmap.py:205` — `_connect` and `factory/cli/repo.py:85` —
   `_open_client`, **When** each needs a client, **Then** each obtains it from the
   choke point and none of the four contains `Client.connect` — proven by a
   committed test per caller that binds the choke point's seam to a fake and
   asserts the caller's own error translation is unchanged.
3. **Given** a refusal from the choke point and a refusal from an unrelated
   precondition on the same call path, **When** a test asserts on the refusal
   text, **Then** the two messages are distinguishable by a substring unique to
   each — proven by a committed test asserting both messages and asserting that
   neither unique substring occurs in the other. This is FR-005 and it exists
   because M8 passed against "runtime root", a substring two different refusals
   shared.
4. **Given** the landed test `tests/test_runtime_root.py:124` —
   `test_running_epic_ids_default_factory_raises_transport_not_nameerror`, which
   enters the real client factory on purpose, **When** the choke point starts
   refusing under pytest, **Then** that test is carried forward rather than
   deleted: the diff shows it still entering the default seam and now asserting
   the choke point's refusal, and the diff contains no deletion of a test
   function — proven by the committed test file itself.
5. **Given** the choke point's module, **When** the diff is read, **Then** the
   seam a test binds is declared beside it and named in the refusal of scenario 1
   — proven by a committed test that binds the seam by the name the refusal
   prints.
6. **Given** the landed guard `tests/test_declared_temporal.py:423` —
   `test_every_connect_site_reaches_the_one_resolver`, which walks ten named
   modules and requires each to import `resolve_temporal_target` or
   `temporal_target_for` from `factory.controlplane.resolve`, **When** the four
   callers are migrated, **Then** each still calls its own resolver and hands the
   resolved address and namespace to the choke point, and
   `tests/test_declared_temporal.py` is unchanged — proven by the committed diff,
   in which every migrated caller keeps its resolver import and its resolver call
   and that file carries no edit. In all four, the resolver's only caller is the
   connect site being moved, so deleting the call along with the connect deletes
   the import the guard asserts on and reddens the declared `test` gate.
7. **Given** the five landed test modules that bind the Temporal floor at
   `temporalio.client.Client.connect` and then drive one of this story's four
   callers — `tests/test_ergane_status.py:485` — `fake_temporal`,
   `tests/test_roadmap_schedule_discovery.py:311` — `fake_temporal`,
   `tests/test_roadmap_wedge_visibility.py:219` — `fake_temporal`,
   `tests/test_teardown_owns_the_ordering.py:213` — `_host` (with its sibling at
   `tests/test_teardown_owns_the_ordering.py:600` —
   `test_roadmap_pause_command_still_pauses_the_schedule`) and
   `tests/test_ergane_spec.py:448` — `test_validate_opens_no_socket`, **When**
   the four callers are migrated, **Then** every one of those fakes is rebound to
   the seam the choke point declares, no test function in those modules is
   deleted or turned into a skip, and
   `tests/test_teardown_owns_the_ordering.py:631` —
   `test_roadmap_py_is_not_edited_by_this_story` — which today requires
   `factory/cli/roadmap.py` to contain the literal `Client.connect` exactly once
   — asserts instead that the module reaches the choke point — proven by the
   committed diff to those four files together with the test module of scenario
   2, in which each rebound caller returns the fake it was given. The refusal of
   scenario 1 fires before `Client.connect` is reached, so a fake left there is
   never consulted and its test goes red rather than loose.
8. **Given** the landed CLI guard sweep `tests/test_ergane_status.py:1702` —
   `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal`, which
   derives its module set from every file under `factory/cli/` that awaits and
   mentions Temporal (`tests/test_ergane_status.py:1586` —
   `_cli_python_modules`) and then compares it, function by function and `except`
   clause by `except` clause, against the table at
   `tests/test_ergane_status.py:1516`, **When** the choke point is written and
   the four callers are migrated, **Then** the choke point's module is not under
   `factory/cli/`, each migrated function still awaits and still carries exactly
   the clause tuple that table pins for it, and neither the table nor the sweep
   carries an edit — proven by the committed diff, in which the new module's path
   is outside `factory/cli/` and each migrated `try`/`except` is unchanged, and
   by a committed test in this story's own module asserting the pinned tuples for
   `factory/cli/nouns/__init__.py:54` — `_open_client`,
   `factory/cli/repo.py:85` — `_open_client` and
   `factory/cli/roadmap.py:205` — `_connect`.

---

### User Story 2 - Disabling one guard is not enough (Priority: P1)

As an operator, a test process cannot reach the production control plane even
when the `PYTEST_CURRENT_TEST` refusal has been removed, so proving that refusal
is load-bearing does not itself reach production.

**Why this priority**: P1, depends on US1 for the choke point and on US3 having
merged for the opt-in name FR-009 wires to. Without it, every mutation battery
run against the choke point is an incident waiting for its turn, and US1's single
guard would concentrate that risk rather than reduce it.

**Independent Test**: Neutralise each defence in turn the way a mutation would and
read what the choke point does; then neutralise both and read that a connection
is attempted.

**Acceptance Scenarios**:

1. **Given** the `PYTEST_CURRENT_TEST` refusal is neutralised in-process the way
   mutation M12 did it, **When** a test asks the choke point for a client,
   **Then** it still refuses and the refusal names the second defence — proven by
   a committed test that patches the first defence's condition to a constant.
2. **Given** the second defence is neutralised in-process instead, **When** a test
   asks for a client, **Then** the `PYTEST_CURRENT_TEST` refusal still fires —
   proven by a committed test. Either alone suffices; that is what
   `factory/roadmap/schedule.py:22-26` means by independent.
3. **Given** both defences are neutralised, **When** a test asks for a client
   with `TEMPORAL_ADDRESS` pointed at a closed port, **Then** a connection is
   attempted and the resulting error names that address — proven by a committed
   test asserting on the error text rather than on an exception type, because
   `temporalio` raises a bare `RuntimeError` on a dead port. Two guards that
   cannot both be removed would be one guard wearing a disguise, and this is the
   only test that can tell.
4. **Given** the sanctioned opt-in of FR-010 names the tier and
   `TEMPORAL_ADDRESS` is pointed at a closed port, 127.0.0.1 port 1, **When** it
   asks for a client, **Then** both defences stand down and the connection is
   attempted against *that* address — proven by a committed test asserting the
   error text names 127.0.0.1:1. A door with no user is only a way in, so this
   door has exactly one, and it is explicit; and it is proven against a dead port
   and never against a resolved default, because with nothing exported
   `resolve_temporal_target()` yields `factory/notify/service.py:129` — the
   operator's own floor — so the one test that proves the door would otherwise be
   the incident this spec exists to close. FR-030.
5. **Given** the diff, **When** the two defences are read, **Then** they share no
   `if`, no helper and no early return, and each is reachable with the other
   removed — proven by a committed test that exercises each defence with the other
   patched out.

---

### User Story 3 - A live tier is opted into, never armed by a credential (Priority: P1)

As an operator, a live-tier test runs because someone named that tier, not
because a credential happened to be in the environment or in the session stash
114 put it in.

**Why this priority**: P1 and it depends on nothing. It is the whole of the
Telegram paging incident and half of the namespace leak, and it is independent of
the client work.

**Independent Test**: Run a scratch session with both Telegram credentials present
and no tier named, and read the skip; name a tier with its credentials absent and
read the failure.

**Acceptance Scenarios**:

1. **Given** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are both set before the
   session starts and no tier has been opted into, **When** the suite runs,
   **Then** the live Telegram test skips and no send is attempted — proven by a
   committed test that asserts the skip and asserts the bot constructor was never
   called. Setting the credentials is not enough to reach the stash at
   `tests/conftest.py:521`.
2. **Given** a tier is opted into by name but its credentials are absent, **When**
   the suite runs, **Then** the test **fails** naming the missing credential
   rather than skipping — proven by a committed test asserting a failure outcome
   and the credential's name in its message. Asking for a live run and silently
   not getting one is how a tier rots unnoticed.
3. **Given** a tier is opted into by name with its credentials present, **When**
   the suite runs, **Then** that tier's tests are selected — proven by a committed
   test that asserts selection, not by running the live tier itself.
4. **Given** the opt-in names one tier, **When** the suite runs, **Then** the other
   five tiers still skip — proven by a committed test enumerating all six
   registered `live_*` markers. One name arms one tier.
5. **Given** every live-tier test module in `tests/`, **When** the suite is
   searched, **Then** each one's skip condition is the opt-in and not the presence
   of a credential — proven by a committed test that enumerates them from the
   registered markers, asserts the enumerated set is not empty and contains at
   least `tests/test_live_notify.py` and `tests/test_live_capacity.py` by name,
   and fails naming any module that decides on a credential alone. Without the
   non-empty assertion a marker-to-module walk that resolves nothing passes
   forever — the vacuity `tests/test_ergane_status.py:1733` —
   `test_the_discovered_module_set_contains_status_and_build` exists to close for
   the sweep beside it.
6. **Given** the six marker registrations at `pyproject.toml:89-96`, **When** they
   are rewritten to describe the opt-in, **Then** each still contains the literal
   `auto-skips unless ` and what follows it names the opt-in rather than a
   credential — proven by the committed diff keeping
   `tests/test_114_us3_live_tier_summary.py:165` — `registered_live_tiers` green,
   which asserts that phrase is present in every `live_*` registration.
7. **Given** the opt-in of FR-010, **When** a module in `factory/` reads it with
   no pytest plugin loaded and no conftest imported, **Then** it yields the tiers
   that were named — proven by a committed test that reads the opt-in through the
   same shape `factory/verify/store.py:378-381` — `connect` uses for its own
   acknowledgment, so US2's stand-down has something production code can consult.
   A selection that exists only as a `-m` marker expression or a pytest
   command-line option fails this scenario, because FR-009 wires the choke point
   to this name and the choke point is not a pytest plugin.

---

### User Story 4 - A git operation on a husk refuses (Priority: P1)

As an operator, a git operation aimed at a node path that is not a live worktree
refuses by name instead of resolving to the operator's checkout.

**Why this priority**: P1 and it depends on nothing. It is the only story here
whose incident wrote to the operator's git history, and the class has already
recurred once by a second route.

**Independent Test**: Build a real worktree under a temporary directory, delete
only its `.git` file, aim salvage and teardown at it, and read what each does to
the enclosing repository.

**Acceptance Scenarios**:

1. **Given** a node path that is a live worktree, **When** salvage and teardown are
   aimed at it, **Then** both proceed exactly as today — proven by a committed test
   over a real worktree built in a temporary directory.
2. **Given** a node path whose `.git` file has been removed — a husk, the
   directory still populated — **When** a git operation is aimed at it, **Then** it
   refuses, naming the path and the fact that it is not a worktree, and no
   repository is touched — proven by a committed test asserting the enclosing
   repository's `HEAD` and porcelain status are byte-identical before and after.
   Deleting the whole directory instead proves nothing: `is_dir()` already catches
   that.
3. **Given** a node path that does not exist at all, **When** a git operation is
   aimed at it, **Then** it refuses the same way — proven by a committed test.
   A missing directory resolves upward exactly as a husk does.
4. **Given** the husk refusal, **When** it is reached through
   `factory/workgraph/worktree.py:511` — `salvage` and through
   `factory/workgraph/worktree.py:1750` — `_archive_node`, **Then** both refuse —
   proven by committed tests for each route. The finding records both; one fix
   that covers one route leaves the class open.
5. **Given** a node worktree nested inside an enclosing repository — which is where
   they live — **When** the check runs, **Then** it is recognised as a worktree and
   the operation proceeds — proven by a committed test. An implementation that
   asked git to find *a* repository from the path passes scenario 2 by accident
   and fails here.

---

### User Story 5 - A probe workflow cannot be counted as an epic (Priority: P2)

As an operator, a workflow created by a probe or a test cannot be mistaken for a
running epic, so a leaked artefact never consumes a concurrency slot.

**Why this priority**: P2, and it waits only for US3 to merge, because both
stories write `tests/test_live_capacity.py`. US1 through US3 should stop new
leaks; this story bounds the damage of the one already on the namespace and of
any that get through.

**Independent Test**: Hand a scripted listing containing `epic-capacity-can-3d2bb231`
— an execution whose workflow type is a probe's, not an epic's — to both open-epic
readers and read the counts, then read the query each reader sent.

**Acceptance Scenarios**:

1. **Given** the ids minted by `tests/test_live_capacity.py:176` — `_probe_id`,
   **When** the live capacity tier constructs them, **Then** none of them wears the
   `epic-` prefix — proven by a committed test asserting the shape of every id that
   tier mints.
2. **Given** a scripted listing holding the leaked workflow
   `epic-capacity-can-3d2bb231` under a probe's workflow type, **When** open epics
   are listed, **Then** it is not counted — proven by a committed test that runs
   the real reader over a listing handed to it through a fake client, never by
   binding the provider seam, which would replace the very function this
   requirement changes and pass on a test-only diff. The decision is the
   execution's workflow type, never its id alone: the leaked id predates any
   renaming and has to stop counting without being deleted first.
3. **Given** the visibility query the reader sends, **When** it is captured from a
   fake client, **Then** it carries a `WorkflowType = "EpicWorkflow"` clause beside
   the existing `ExecutionStatus` clause, and the pinned type name equals the type
   Temporal registers for `factory/workgraph/workflow.py:752` — `EpicWorkflow` —
   proven by a committed test that asserts the query string and compares the pinned
   name against the registered definition, so a second grammar cannot drift from
   the first. The precedent is `factory/escalation/client.py:52-59`, whose comment
   states what the clause is for.
4. **Given** an execution carrying a real epic id built by
   `factory/roadmap/workflow.py:195` — `_epic_id_for` and the `EpicWorkflow` type,
   **When** open epics are listed, **Then** it is counted exactly as today — proven
   by a committed test. Every epic starts as `EpicWorkflow.run`, at
   `factory/cli/nouns/build.py:930` — `_start_epic`,
   `factory/workgraph/cli.py:674` — `_start_epic` and
   `factory/roadmap/workflow.py:1295` — `_dispatch`, and this scenario is what says
   the narrowing did not lose one.
5. **Given** the same listing, **When** it is read by the second counter at
   `factory/supervision/units.py:1302` — `listed`, **Then** that reader excludes
   what FR-020 excludes and sends the same clause — proven by a committed test. One
   counter fixed and one left alone is a half fix: the supervision teardown refusal
   would still see a slot in use that nothing is using.
6. **Given** the two landed live-tier tests `tests/test_live_capacity.py:260` —
   `test_capacity_read_finds_open_epic_workflows_and_excludes_others` and
   `tests/test_live_capacity.py:331` —
   `test_capacity_read_excludes_continued_as_new_chain`, whose probes register as
   the workflow types `CapacityProbeWorkflow` and
   `CapacityContinueAsNewProbeWorkflow` and which today assert that an
   epic-prefixed probe **is** counted, **When** the reader narrows to the
   epic workflow type, **Then** both are rewritten so that no assertion needs a
   probe to be counted and no probe is registered under the production workflow
   type — proven by the committed diff to that file, in which each rewritten test
   asserts the narrowed read counts none of its own probes while a direct
   `ExecutionStatus = "Running"` listing still finds the same ids, so the tier keeps
   proving the status grammar it was written for. Both carry `live_capacity`, so
   the declared `test` gate skips them: this scenario is the only thing that
   notices them break.

---

### User Story 6 - The last seven callers, and the test that keeps them there (Priority: P1)

As an operator, no module outside the choke point constructs a Temporal client,
and a test proves it against the tree rather than against a list somebody wrote
down.

**Why this priority**: P1, and it waits only for US1 to merge. FR-003's test
cannot pass until the last site is migrated, so it lands with the last site. It
is a separate node because US1 plus eleven migrations plus their tests is over
the 64 KiB diff refusal.

**Independent Test**: Run the tree-walking test against the tree; drive the worker
entrypoint with the choke point's seam bound and read that it is not refused
outside pytest.

**Acceptance Scenarios**:

1. **Given** the factory package, **When** it is walked, **Then** exactly one
   module constructs a client — proven by a committed test that walks
   `factory/**/*.py` from the package root, decides on parsed code rather than on
   raw text so that the literal inside the comment at
   `factory/controlplane/verify.py:732` — `gather` survives and is not counted, and
   fails naming any other file. Read the tree, never a hardcoded list: this spec
   was drafted with a list of nine and the tree already held eleven.
2. **Given** the seven callers `factory/doctor/probes.py:491` — `_gather_async`,
   `factory/doctor/probes.py:603` — `_closed_epics_from_temporal`,
   `factory/controlplane/verify.py:193` — `_temporal_client_factory`,
   `factory/notify/service.py:1048` — `main`, `factory/worker.py:342` — `main`,
   `factory/supervision/deploy.py:749` — `asked` and
   `factory/roadmap/schedule.py:165` — `_default_schedule_client`, **When** each
   needs a client, **Then** each obtains it from the choke point — proven by a
   committed test per caller that binds the choke point's seam. The last of those
   is the module US2 is modelled on: its own refusal at
   `factory/roadmap/schedule.py:156-162` and `factory/roadmap/schedule.py:255` —
   `_refuse_live_client` stay exactly as they are, so the choke point is reached
   from there only once a mutation has removed the first — proven by a committed
   test asserting that module still refuses under `PYTEST_CURRENT_TEST` with its
   own message.
3. **Given** the worker entrypoint `factory/worker.py:333` — `main`, **When** it
   runs with `PYTEST_CURRENT_TEST` unset, **Then** it connects exactly as it does
   today — proven by a committed test that binds the seam and asserts the
   entrypoint is not refused. The worker is production; the guard is about the
   test process, not about this caller.
4. **Given** a test that merely imports `factory/worker.py`, **When** it runs,
   **Then** no connection is attempted — proven by a committed test asserting the
   choke point's seam was never called on import.
5. **Given** the landed guard `tests/test_declared_temporal.py:423` —
   `test_every_connect_site_reaches_the_one_resolver` and the module list it
   walks at `tests/test_declared_temporal.py:392` (the tuple `_RESOLVER_SITES`,
   built from `tests/test_declared_temporal.py:332`), **When** the seven callers
   are migrated, **Then** each still resolves its own target and hands it to the
   choke point — `factory/controlplane/verify.py:193` —
   `_temporal_client_factory` keeping `temporal_target_for(config, …)` and the
   config-first precedence its docstring records, and
   `factory/supervision/deploy.py:749` — `asked` keeping the `self._address` and
   `self._namespace` it was constructed with — and
   `tests/test_declared_temporal.py:423` —
   `test_every_connect_site_reaches_the_one_resolver` itself carries no edit —
   proven by the committed diff, in which each caller's resolver call survives
   beside the migrated connect and that test is untouched.
6. **Given** the two landed test modules that bind the floor at
   `temporalio.client.Client.connect` and drive a caller this story migrates —
   `tests/test_doctor_probes.py:295` — `fake_temporal`, which drives both probe
   sites, and `tests/test_declared_temporal.py:269` — `dialed`, which serves
   `tests/test_declared_temporal.py:274` —
   `test_the_verify_probe_dials_the_address_the_worker_would_use` and
   `tests/test_declared_temporal.py:303` —
   `test_the_probe_snapshot_names_the_server_it_actually_dialed`, both of which
   require a real dial through `factory/controlplane/verify.py:193` —
   `_temporal_client_factory` under pytest — **When** the seven callers are
   migrated, **Then** both fakes are rebound to the choke point's seam, both dial
   tests still assert the address and namespace that were dialed, and the rest of
   that module carries no edit: `tests/test_declared_temporal.py:332` (the tuple
   `_CONNECT_SITES`), `tests/test_declared_temporal.py:392` (the tuple
   `_RESOLVER_SITES`), `tests/test_declared_temporal.py:395` —
   `test_no_connect_site_keeps_its_own_copy_of_the_temporal_contract` and
   `tests/test_declared_temporal.py:423` —
   `test_every_connect_site_reaches_the_one_resolver` are unchanged and no test
   function is removed — proven by the committed diff to that file, which touches
   the fixture and those two tests and nothing else.

## Functional Requirements

- **FR-001**: One module in `factory/` MUST be the choke point through which
  every real Temporal client is constructed. It MUST accept an **already
  resolved** target — an address and a namespace handed to it by its caller — and
  MUST resolve nothing for itself, so that each caller keeps the one precedence
  048-US4 pinned and no site restates the contract. It MUST declare, beside
  itself, the seam a test binds. It MUST live outside `factory/cli/`; FR-029
  fixes where, and says which landed contract decides it. Exclusivity is not this
  requirement: FR-002 and FR-023 migrate the callers and FR-003 is the test that
  proves no second constructor survives.
- **FR-002**: The four CLI callers — `factory/workgraph/cli.py:969` — `_connect`,
  `factory/cli/nouns/__init__.py:54` — `_open_client`,
  `factory/cli/roadmap.py:205` — `_connect` and `factory/cli/repo.py:85` —
  `_open_client` — MUST be migrated to that choke point, and each MUST keep its
  own error translation and exit code. Each MUST also keep its own
  `resolve_temporal_target()` call and hand the resolved target to the choke
  point: the landed guard `tests/test_declared_temporal.py:423` —
  `test_every_connect_site_reaches_the_one_resolver` requires every one of these
  modules to import a resolver entry point from `factory.controlplane.resolve`,
  and in each of them that import serves the connect site being migrated and
  nothing else. No migrated caller MAY restate the address or namespace contract
  for itself, and `tests/test_declared_temporal.py` MUST NOT be edited by this
  story — none of the four modules is driven by that file's two dial tests, so
  its diff here is empty and FR-028's exemption is US6's alone.
- **FR-003**: A committed test MUST walk `factory/**/*.py` and MUST fail, naming
  the file, if any module other than the choke point constructs a client
  directly. It MUST read the tree, not a list, and it MUST decide on parsed code
  rather than on raw text: the literal occurs inside a comment at
  `factory/controlplane/verify.py:732` — `gather`, and that comment MUST survive.
- **FR-004**: The choke point MUST refuse to connect when `PYTEST_CURRENT_TEST`
  is set, and the refusal MUST name the address and the namespace of the target
  it was handed, and the seam a test should bind.
- **FR-005**: Every refusal this spec introduces MUST carry a substring unique to
  it, and no two refusals reachable from one call path MAY share the substring a
  test asserts on.
- **FR-006**: `factory/worker.py`'s production start-up path MUST be unchanged
  outside pytest, and importing that module MUST attempt no connection.
- **FR-007**: A second defence MUST refuse a production connection from a test
  process, and it MUST live at a different mutation site from the first — a
  different function, guarding a different subject, in the shape
  `factory/roadmap/schedule.py:255` — `_refuse_live_client` already uses.
- **FR-008**: Either defence alone MUST refuse, and a test process MUST be able
  to connect only when both have been neutralised.
- **FR-009**: There MUST be exactly one sanctioned way to stand both defences
  down, and it MUST be the named opt-in of FR-010 — not a bare *boolean*
  environment variable, not a file's presence, and not a credential. FR-010 fixes
  the shape that name takes; this requirement fixes that there is only one of
  them.
- **FR-010**: A live tier MUST run only when it is named in an explicit opt-in,
  and that opt-in MUST be a value a module in `factory/` can read at the moment
  it is about to connect — an environment variable naming the tiers, in the shape
  `factory/verify/store.py:378-381` — `connect` already reads through
  `resolve_env_flag`. A mechanism that lives only inside pytest — a `-m` marker
  expression, or a pytest command-line option consumed in `tests/conftest.py` —
  does NOT satisfy this requirement: FR-009 wires the choke point's stand-down to
  this name, and production code cannot read a pytest option.
- **FR-011**: The presence of a tier's credentials MUST NOT select that tier,
  whether they are read from the environment or from the session stash at
  `tests/conftest.py:521`.
- **FR-012**: A tier that is named but whose credentials are absent MUST fail,
  naming the missing credential, and MUST NOT skip.
- **FR-013**: Naming one tier MUST arm that tier only.
- **FR-014**: A committed test MUST enumerate every live-tier test in `tests/`
  from the registered `live_*` markers and MUST fail, naming the module, if any of
  them decides on a credential rather than on the opt-in. It MUST also assert
  that the enumerated set is not empty and that it contains at least
  `tests/test_live_notify.py` and `tests/test_live_capacity.py` by name, so a
  walk that resolves no module cannot pass.
- **FR-015**: A git operation aimed at a node path MUST verify that the path is a
  live worktree before running, and MUST refuse naming the path otherwise.
- **FR-016**: That refusal MUST fire before any repository is touched.
- **FR-017**: A node worktree nested inside an enclosing repository MUST be
  recognised as a worktree.
- **FR-018**: Both `factory/workgraph/worktree.py:511` — `salvage` and
  `factory/workgraph/worktree.py:1750` — `_archive_node` MUST go through the check
  of FR-015.
- **FR-019**: A workflow id created by a probe or a test MUST NOT match the
  grammar that identifies an epic.
- **FR-020**: Listing open epics MUST decide on the workflow **type** an execution
  was started as, not on its id alone, so that a workflow already on a namespace
  under the old prefix stops counting without being deleted. The visibility query
  MUST carry a `WorkflowType = "EpicWorkflow"` clause beside its `ExecutionStatus`
  clause — the shape `factory/escalation/client.py:52-59` already pins for the same
  reason — and the reader MUST also drop any listed execution whose workflow type
  is not that one, so a supplied listing decides the exclusion without a server.
  The pinned type name MUST be proven equal to the type Temporal registers for
  `factory/workgraph/workflow.py:752` — `EpicWorkflow`. The epic id grammar MUST
  NOT be narrowed.
- **FR-021**: Listing open epics MUST count real epic ids exactly as it does
  today.
- **FR-022**: `tests/test_runtime_root.py:124` —
  `test_running_epic_ids_default_factory_raises_transport_not_nameerror` MUST be
  carried forward rather than deleted: it MUST still enter the default client
  factory and MUST assert the choke point's refusal, and no test function may be
  removed from that module.
- **FR-023**: The seven remaining callers — `factory/doctor/probes.py:491` —
  `_gather_async`, `factory/doctor/probes.py:603` — `_closed_epics_from_temporal`,
  `factory/controlplane/verify.py:193` — `_temporal_client_factory`,
  `factory/notify/service.py:1048` — `main`, `factory/worker.py:342` — `main`,
  `factory/supervision/deploy.py:749` — `asked` and
  `factory/roadmap/schedule.py:165` — `_default_schedule_client` — MUST be migrated
  to the choke point. `factory/supervision/deploy.py:749` — `asked` is not in the
  2026-08-20 table and MUST be found by walking the tree.
  `factory/roadmap/schedule.py:156-162`, that module's own `PYTEST_CURRENT_TEST`
  refusal, and `factory/roadmap/schedule.py:255` — `_refuse_live_client` MUST both
  be left exactly as they are: they are the pair FR-007 is modelled on, and after
  the migration they compose with the choke point instead of duplicating it. Each
  of the seven MUST keep its own target resolution and hand the resolved target to
  the choke point — `factory/controlplane/verify.py:193` —
  `_temporal_client_factory` keeping `temporal_target_for(config, …)` and its
  config-first precedence, `factory/supervision/deploy.py:749` — `asked` keeping
  the `self._address` and `self._namespace` it was constructed with, and the rest
  keeping `resolve_temporal_target()` — because the landed guard
  `tests/test_declared_temporal.py:423` —
  `test_every_connect_site_reaches_the_one_resolver` asserts that import in every
  one of these modules, and that test, its sibling and both module tuples MUST
  NOT be edited — the only change permitted anywhere in
  `tests/test_declared_temporal.py` is the carry-forward FR-028 requires.
- **FR-024**: `factory/supervision/units.py:1302` — `listed`, the second reader of
  the epic grammar, MUST exclude exactly what FR-020 excludes and MUST send the
  same `WorkflowType` clause.
- **FR-025**: Every `live_*` marker registration at `pyproject.toml:89-96` MUST
  keep the literal `auto-skips unless ` and MUST change only what follows it, so
  `tests/conftest.py:766` — `_registered_live_tiers` and
  `tests/test_114_us3_live_tier_summary.py:147` — `registered_live_tiers` keep
  parsing the condition out of the registration.
- **FR-026**: The two live-tier tests that today require an epic-prefixed probe to
  be counted — `tests/test_live_capacity.py:260` —
  `test_capacity_read_finds_open_epic_workflows_and_excludes_others` and
  `tests/test_live_capacity.py:331` —
  `test_capacity_read_excludes_continued_as_new_chain` — MUST be rewritten in the
  same story that narrows the reader, and no probe workflow MAY be registered under
  the production workflow type in order to keep an assertion alive.
- **FR-027**: Every landed test that binds the Temporal floor at
  `temporalio.client.Client.connect` and drives a caller this spec migrates MUST
  be rebound, in the same story that migrates that caller, to the seam FR-001
  declares beside the choke point. None of them MAY be deleted, skipped, or given
  a stand-down: FR-004's refusal fires before `Client.connect` is reached, so a
  fake left there is never consulted. US1 owns five modules —
  `tests/test_ergane_status.py:485` — `fake_temporal`, which reaches
  `factory/cli/nouns/__init__.py:54` — `_open_client` through
  `factory/cli/status.py:305` — `collect_floor`;
  `tests/test_roadmap_schedule_discovery.py:311` — `fake_temporal` and
  `tests/test_roadmap_wedge_visibility.py:219` — `fake_temporal`, both driving
  `factory/cli/roadmap.py:205` — `_connect` through `ergane roadmap`;
  `tests/test_teardown_owns_the_ordering.py:213` — `_host` and
  `tests/test_teardown_owns_the_ordering.py:600` —
  `test_roadmap_pause_command_still_pauses_the_schedule`, which reach
  `factory/cli/nouns/__init__.py:54` — `_open_client` through
  `factory/supervision/units.py:1291` — `_open_epics`; and
  `tests/test_ergane_spec.py:448` — `test_validate_opens_no_socket`, whose
  exploding fake asserts that `ergane spec validate` opens no socket and would
  otherwise stop meaning it. US6 owns two, named in FR-028. In the same story,
  `tests/test_teardown_owns_the_ordering.py:631` —
  `test_roadmap_py_is_not_edited_by_this_story`, which requires the literal
  `Client.connect` to occur exactly once in `factory/cli/roadmap.py`, MUST be
  carried forward to assert that module reaches the choke point instead.
- **FR-028**: `tests/test_declared_temporal.py` MUST be edited in exactly one way
  and no other. `tests/test_declared_temporal.py:264` — `dialed` and the two
  tests it serves — `tests/test_declared_temporal.py:274` —
  `test_the_verify_probe_dials_the_address_the_worker_would_use` and
  `tests/test_declared_temporal.py:303` —
  `test_the_probe_snapshot_names_the_server_it_actually_dialed` — MUST be carried
  forward onto the choke point's seam: each still enters
  `factory/controlplane/verify.py:193` — `_temporal_client_factory` under pytest
  and still asserts the address and the namespace that were dialed. Nothing else
  in that module MAY change: `tests/test_declared_temporal.py:332` (the tuple
  `_CONNECT_SITES`), `tests/test_declared_temporal.py:392` (the tuple
  `_RESOLVER_SITES`), `tests/test_declared_temporal.py:395` —
  `test_no_connect_site_keeps_its_own_copy_of_the_temporal_contract` and
  `tests/test_declared_temporal.py:423` —
  `test_every_connect_site_reaches_the_one_resolver` MUST be left exactly as they
  stand, and no test function MAY be removed from the module. Without this
  requirement FR-023 and FR-027 contradict each other and no legal implementation
  exists.
- **FR-029**: The choke point's module MUST NOT live under `factory/cli/`. It
  MUST live in `factory/controlplane/`, beside
  `factory/controlplane/resolve.py:232` — `resolve_temporal_target`, and MUST NOT
  be re-exported from `factory/controlplane/__init__.py`, which is zero bytes and
  whose emptiness is what keeps the worker's start-up imports acyclic. Every
  migrated CLI caller MUST keep awaiting and MUST keep the `except` clause tuple
  pinned for it at `tests/test_ergane_status.py:1516`, and neither that table nor
  `tests/test_ergane_status.py:1702` —
  `test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal` MAY be
  edited: that sweep derives its module set from every file under `factory/cli/`
  that awaits and mentions Temporal, so a choke point placed there is a new
  module in the discovered set and a red gate on a contract no other requirement
  here names.
- **FR-030**: Every committed test in this spec that stands a defence down and
  then attempts a connection MUST point `TEMPORAL_ADDRESS` at a closed port,
  127.0.0.1 port 1, and MUST assert on the error text naming that address. None
  of them MAY let the target resolve to the built-in default at
  `factory/notify/service.py:129`, which on the operator's host is the live
  control plane. This is the ledger's own fix direction for
  `hardening/mutating-a-production-safety-guard-escapes-the-sandbox`: briefs that
  ask for mutation of a production-safety guard must also say how to make the
  escape harmless — point the client at a dead port, use a scratch namespace, or
  unset the credential.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-004, FR-005, FR-022, FR-027, FR-029]
US2:
  depends_on: []
  depends_on_merged: [US1, US3]
  implements: [FR-007, FR-008, FR-009, FR-030]
US3:
  depends_on: []
  implements: [FR-010, FR-011, FR-012, FR-013, FR-014, FR-025]
US4:
  depends_on: []
  implements: [FR-005, FR-015, FR-016, FR-017, FR-018]
US5:
  depends_on: []
  depends_on_merged: [US3]
  concurrent_with: [US4]
  implements: [FR-019, FR-020, FR-021, FR-024, FR-026]
US6:
  depends_on: []
  depends_on_merged: [US1]
  concurrent_with: [US2]
  implements: [FR-003, FR-006, FR-023, FR-027, FR-028]
```

FR-027 is carried by US1 and US6 both, for the same reason and by the same
mechanism as FR-005 below: it is one rule about a class — a landed fake bound at
`Client.connect` is rebound by whoever moves the caller it drives — and both
stories move callers such fakes drive. A node is handed its own FRs and no
sibling's (`factory/workgraph/prompt.py:594` — `_requirement_sections`), so a
node that only saw the other story's copy would meet the class as roughly a
hundred red tests instead of as declared scope. Each story's half is named
inside the requirement.

FR-005 is carried by US1 and US4 both. It is the only spec-wide requirement
here — every refusal this spec introduces must be distinguishable from the
refusals it shares a call path with — and both stories introduce one, so a node
that is not handed its body would be measured on a rule it was never shown
(`factory/workgraph/prompt.py:594` — `_requirement_sections` gives a node its own
FRs and no sibling's).

US2 declares `depends_on_merged: [US1, US3]` rather than a pass edge on US1. Its
whole slice edits the module US1 creates, and a pass edge is ordering only — the
predecessor must reach a verdict and nothing about its code is guaranteed to be
present (`docs/architecture.md:698-700`, and CONTEXT.md's own definition). US2
dispatched while US1 sat in the merge queue would pin a base with no choke point
in it and spend the attempt on a module that is not there. The US3 half of that
edge is the older reason: FR-009 wires the stand-down to FR-010's opt-in and that
name is US3's to mint. US6 declares `depends_on_merged: [US1]` for the same reason
in its weaker form — it migrates callers into the choke point and so needs it
merged — and has nothing to wait for beyond that. US5 declares
`depends_on_merged: [US3]` because both stories write `tests/test_live_capacity.py`:
US3 converts that tier's skip fixture and US5 rewrites two of its tests (FR-026),
and two nodes editing one file from two worktrees costs whichever lands second a
merge-queue rejection. US6 declares `concurrent_with: [US2]` for the same
kind of reason: both slices name `factory/roadmap/schedule.py`, but US2 only reads
it — it is the exemplar FR-007 is modelled on — while US6 migrates its connect, so
serialising them would buy nothing. US5 also keeps `concurrent_with: [US4]` because
both slices name `factory/cli/nouns/build.py` and neither edits it — US4 reaches the teardown
route through `factory/cli/nouns/build.py:1897` — `_reset_epic` and US5 imports the
constant at `factory/cli/nouns/build.py:188` — so the inferred contention edge
would serialise two stories that share no production write. Beyond that shared test
file, US3, US4 and US5 touch nothing in common: US3 is `tests/` and
`pyproject.toml`, US4 is `factory/workgraph/worktree.py`, US5 is the two epic
readers in `factory/activities/roadmap_activities.py` and
`factory/supervision/units.py`.
