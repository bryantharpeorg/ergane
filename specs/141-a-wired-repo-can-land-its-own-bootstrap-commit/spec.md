---
state: draft
fixes:
  - mergequeue/onboarding-couples-the-queue-to-the-default-branch-and-forbids-the-documented-two-branch-model
  - init/the-scaffolded-workflow-installs-no-toolchain
  - mergequeue/wiring-creates-the-ruleset-before-the-workflow-the-ruleset-requires
  - init/wire-creates-a-bootstrap-deadlock-against-the-commit-it-tells-you-to-make
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-wired-repo-can-land-its-own-bootstrap-commit"
# (lines 201-220), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n` and verified to
# resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N9, N10 and N12 of the `ergane-web` round-2 hand-over,
# plus C-16 and C-17 from the wolfenstein-container run — five sightings of one
# bootstrap that does not work. The triage verified the entry against 238b494 by
# a fan-out of one agent per claim, then handed every OPEN claim to a second
# agent instructed to refute it.
#
# WHAT IT COST, MEASURED. N9's reporter recovered by dropping the ruleset's
# enforcement, squash-merging the bootstrap commit, and restoring it — "four
# times over the run, because every operator commit during bootstrap needs it".
# C-17 is a third occurrence of the toolchain half, on a JavaScript target this
# time: "the shipped state of a freshly wired repo is two checks that fail for a
# reason unrelated to the code, with the merge queue armed against them". N10's
# reporter was shown `--wire`'s divergence warning, believed it, and abandoned
# the two-branch model the factory's own README describes.
#
# FOUR KEYS, AND TWO OF THEM ARE THE SAME DEFECT ON PURPOSE. N9 has two open
# ledger rows from two independent runs —
# `mergequeue/wiring-creates-the-ruleset-before-the-workflow-the-ruleset-requires`
# (ergane-web round 2) and
# `init/wire-creates-a-bootstrap-deadlock-against-the-commit-it-tells-you-to-make`
# (wolfenstein-container). Both are declared deliberately: declaring one closes
# one and leaves the other open forever, and a later audit that reads the
# duplication as a padded `fixes:` list would strip exactly the wrong half.
# US3 and US4 together fix that one defect whole. N12's other spelling,
# `ci/the-scaffolded-gates-workflow-cannot-derive-toolchain-setup-from-the-gate-commands-it-runs`,
# is NOT declared: it is already resolved as "duplicate identity: merged into
# init/the-scaffolded-workflow-installs-no-toolchain" — a merge, not a fix — and
# the canonical key is the open one, which is the one declared here.
#
# WHAT MOVED SINCE THE TRIAGE. Spec 057 landed four stories on 2026-09-03,
# between the triage's 238b494 and this refinement's 602a92c, and it added 92
# lines above `_wire`: the entry's factory/cli/init.py:1303 (the scaffold call)
# is now 1395 and its :1312 (the landing-policy call) is now 1404 — 1312 today
# is a bare `)`, which no anchor layer would have refused. The same landing moved
# `evaluate_repo` from the entry's onboard.py:150-158 to 162-171 and the third
# `onboard_target_repo` caller from init.py:1931 to `factory/cli/init.py:2289`.
# Every anchor in `wiring.py`, `merge_activities.py`, `github_forge.py` and
# `merge_queue_ruleset.json` was re-read and had not moved.
#
# ONE ANCHOR THE ENTRY GOT WRONG IN A WAY THAT WOULD HAVE REFUSED.
# The entry cites docs/decisions.md:1252-1266 for D-051 and line 1252 is blank, so
# that range is a refusal on its own. D-051's heading is at 1255 and the paragraph
# the entry meant ends at 1267; cited throughout this trio as
# `docs/decisions.md:1255-1267`.
#
# NOT IN SCOPE. This spec does not change what the queue requires (still exactly
# one check per declared gate), does not add a per-gate scope — spec 128 owns
# that and owns `_gate_check_finding` with it, which is why nothing here edits
# `factory/mergequeue/onboard.py` at all — does not touch `_landing_branch_finding`,
# and does not fix the node-side half of the browser problem, which
# `factory/verify/gate_annotation.py` already annotates.
#
# AND IT DOES NOT BUILD THE SECOND PHASE THE ENTRY OFFERED AS AN ALTERNATIVE.
# The entry's scope reads "created non-blocking (or with the wiring identity as a
# bypass actor) and activated only once a check named after every declared gate
# has been observed". The bypass actor is chosen and the observation phase is
# refused, for two measured reasons stated in plan.md traps 5 and 6: the
# non-blocking arm forces a module under `factory/` to spell a word
# `tests/test_final_sweep.py` refuses outright, and "has been observed" is a
# question no forge on the seam can answer without a twelfth seam operation the
# seam's own contract forbids. The bypass actor is what the working configuration
# on this repository already carries, which is why operator pushes succeed here
# and did not on two reported targets.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the bypass payload's shape pinned
# to a measured read-back instead of left to the implementer; its mode named and
# the critical ledger row that mode extends named with it; the narrowing to
# organization administrators stated instead of implied; FR-013 re-anchored from
# :611 to :589; the manifest-to-policy distance corrected from twelve lines to
# twenty-two; FR-015 and US4-S1 reworded off a "number equals position" property
# that is unsatisfiable over the list they govern; plan.md trap 9 given the
# schema v1/v2 split and trap 6 moved from :236 to :237.
#
# THE BYPASS ENTRY IS COPIED, NOT INVENTED.
# `gh api repos/bryantharpeorg/ergane/rulesets/20538625`, read 2026-09-04,
# returns `"bypass_actors": [{"actor_id": null, "actor_type":
# "OrganizationAdmin", "bypass_mode": "always"}]`. That array is quoted verbatim
# in plan.md § "What already exists, and where" and FR-011 now requires it
# field-for-field. The draft left the shape as an open question in a notes file,
# where it reached no implementer, and the offline model's create path
# (`tests/test_ergane_init_wiring.py:272` — `_create_ruleset`) echoes any posted
# JSON back — so every US3 scenario would have stayed green over a body GitHub
# refuses, and the failure would have surfaced only at the operator's live step 2,
# after landing, as `--wire` refusing on every repository.
#
# WHAT THE BYPASS COSTS, AND THAT IT IS NOT DECLARED FIXED.
# `verify/an-operator-push-to-the-landing-branch-bypasses-the-required-check-and-can-red-the-trunk-every-node-builds-on`
# is open and critical: mode `always` is what let `c9dea78` go straight to
# `ergane-buildout` with four failing tests and cost both 075 nodes a repair
# inside their own stories. This spec extends that configuration to every wired
# target on purpose, says so in § "What this spec is not", and argues the refusal
# of the narrower mode in plan.md trap 13. That row is NOT added to `fixes:` and
# is not closed here.
#
# AND THE FIX IS NARROWER THAN THE STORY'S TITLE. US3 closes both N9 rows on a
# bypass that admits organization administrators only. An operator holding
# repository-admin rights and not organization-owner rights wires successfully
# and is still refused the bootstrap push; `factory/mergequeue/wiring.py:356` —
# `repository_can_host_merge_queue` admits that operator's repository. The
# narrowing is stated in § "What this spec is not" so the two closed rows are
# read for what they are, and it reaches that operator through FR-016's report
# rather than through a refused push.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, answering the
# adversarial review. The dependency claim was false and is withdrawn: draft 128
# leaves `factory/mergequeue/onboard.py` to itself as this trio said, but its US2
# also binds its manifest key inside the same `try` block of
# `factory/activities/merge_activities.py:676-681` — `onboard_target_repo` that
# US1 binds the declared branch in, so the two diffs collide; **Depends on** now
# carries the region and the landing order, and plan.md trap 3 carries the
# reproduction. `manual_steps` is no longer presented as what a successful
# `--wire` prints — it is the by-hand list rendered only on refusal, and the
# instruction the reporters followed is the scaffold detail at
# `factory/mergequeue/wiring.py:241`; gap step 3, US4's narrative and FR-015 now
# say which path each requirement governs. Every claim about the body the offline
# model stores now cites the create path
# (`tests/test_ergane_init_wiring.py:272` — `_create_ruleset`) rather than the
# re-wire's PUT branch. FR-007 and FR-009 make the playwright roster entry imply
# its own node setup, so US2-S3's ordering holds for `npx playwright test`, which
# names no `npm`. FR-018 and US4-S4 name both controls rather than one: :763
# holds the auto-merge string and `tests/test_wiring_us2.py:129` holds the
# squash-title string. Declined: writing the two `factory_yaml.py` constants in
# the dash-symbol form the review asked for — they are module-level assignments
# and `factory/cli/nouns/spec.py:825` — `_symbol_spans` collects only functions
# and classes, so that form is a guaranteed refusal; plan.md trap 9 now says so.
---

# Feature Specification: a wired repo can land its own bootstrap commit

**Created**: 2026-09-04
**Depends on**: nothing landed. One draft on this floor overlaps, and the overlap
is not where it looks. Spec 128 (`a boundary-only gate is a declaration, not a
refusal`) owns `factory/mergequeue/onboard.py`, which this spec never opens — but
128's US2 also derives its manifest key at
`factory/activities/merge_activities.py:677` — `onboard_target_repo`, "beside
where `declared_gates` and `gate_commands` already come off the same config", and
passes it at `factory/activities/merge_activities.py:708` — `onboard_target_repo`.
US1 of this spec binds the declared landing branch into those same three lines and
changes the argument at `factory/activities/merge_activities.py:698` —
`onboard_target_repo`, ten lines above 128's. The `try` block at
`factory/activities/merge_activities.py:676-681` — `onboard_target_repo` is one
contiguous region both drafts insert into, so the two diffs cannot both apply
cleanly and the order is a decision rather than a coincidence. **Land US1 of this
spec first**: it is one binding and one argument, and it is the half that unparks
a repository already past bootstrap. An operator who would rather flip 128 first
must add `depends_on_landed:
[128-a-boundary-only-gate-is-a-declaration-not-a-refusal]` to this spec's
frontmatter before flipping this one, so the roadmap holds it instead of
dispatching both into the same six lines. plan.md trap 3 is the reproduction.

## The gap, stated precisely

`ergane init --wire` is supposed to leave a repository the factory can build in.
It leaves one that cannot land its own first commit, cannot go green if it did,
and is then judged against a branch nobody wired. Three defects, one victim, and
none of them is landable alone.

The chain is seven steps.

1. `--wire` writes the gates workflow into the operator's tree and never commits
   it — `factory/cli/init.py:1395` — `_wire` — and then applies the landing
   policy at `factory/cli/init.py:1404` — `_wire`.
2. That call reaches `factory/mergequeue/github_forge.py:252` —
   `apply_landing_policy`, then `factory/mergequeue/wiring.py:535` —
   `_queue_step`, which POSTs the body built at
   `factory/mergequeue/wiring.py:566` — `_ruleset_payload` from
   `factory/mergequeue/merge_queue_ruleset.json:4`. That file arms the ruleset on
   creation and names no bypass actor at all; `grep -rn 'bypass_actor' factory/`
   returns nothing.
3. So the landing branch is locked before the commit that would satisfy it
   exists — and the operator is told to make it anyway. A `--wire` that succeeds
   prints `WiringStep` details and nothing else
   (`factory/cli/init.py:1395` — `_wire` for the scaffold step, then
   `factory/cli/init.py:1422` — `_wire` for the ones the forge returned), so the
   instruction the reporters actually followed is the applied detail at
   `factory/mergequeue/wiring.py:241` — `scaffold_gates_workflow` ("commit it —
   the queue cannot require a check nothing produces"). The numbered list at
   `factory/mergequeue/wiring.py:120` — `manual_steps` — whose *fifth* entry is
   the commit and whose *third* is the ruleset — says the same thing in the wrong
   order, but it reaches an operator only when the wiring **refuses**: every call
   site passes it as `manual=` into `WiringRefused`, rendered by
   `factory/mergequeue/forge.py:143` — `WiringRefused.render` and printed at
   `factory/cli/init.py:1407` — `_wire`, and its own docstring
   (`factory/mergequeue/wiring.py:110-111`) calls it "the by-hand equivalent of
   `wire_repo`". Both paths give the same wrong order. The push is refused by the
   rule the same command just created; the pull request cannot enter the queue
   either, because its required checks come from the commit it is carrying.
4. Suppose the operator gets that commit in anyway. The checks still cannot pass:
   the rendered job is a bare `actions/checkout@v4` and the gate command
   (`factory/mergequeue/wiring.py:162` — `render_gates_workflow`) with no
   toolchain between them, and the only thing the file says about it is a
   `TODO(operator)` at `factory/mergequeue/wiring.py:131-132`. A repository whose
   gate is `uv run pytest -q` gets a required check that fails forever.
5. Suppose it lands even so. The profile that gates every epic then reads the
   wrong branch. `factory/activities/merge_activities.py:698` —
   `onboard_target_repo` asks for the policy of `repository.default_branch`,
   although the manifest was loaded twenty-two lines earlier at
   `factory/activities/merge_activities.py:676` — `onboard_target_repo` and
   declares the landing branch (`factory/verify/models.py:319` — `FactoryConfig`).
6. The branch name then travels into the findings' own words:
   `factory/mergequeue/github_forge.py:137` — `landing_policy` sets `branch=branch`
   and `factory/mergequeue/onboard.py:246` — `_gated_landing_finding` interpolates
   it, while `factory/mergequeue/onboard.py:394` — `_gate_check_finding` calls it
   "the landing branch". A repository wired on `release` is judged on `main` and
   told so in a sentence that says `main` is its landing branch.
7. A failed profile refuses at both sites: the roadmap parks the spec
   (`factory/roadmap/workflow.py:1262` — `_dispatch`) and a child epic
   re-evaluating the same profile raises `GRAPH_INVALID`
   (`factory/workgraph/workflow.py:1225` — `_onboard_target`), so a manual
   `ergane build start` cannot route around it either.

**The wiring already knows.** `factory/mergequeue/wiring.py:41-47` states the
disagreement in the module's own docstring — "the spec says enable the merge
queue on the declared landing branch; `evaluate_repo` reads the queue for
GitHub's *default* branch" — and `factory/mergequeue/wiring.py:559` —
`_divergence_step` reports it to the operator with two remedies, both of which
abandon the declaration. One live test asserts the defect as intended behaviour:
`tests/test_ergane_init_wiring.py:609` —
`test_a_landing_branch_that_is_not_the_default_is_wired_and_the_divergence_reported`
proves at `tests/test_ergane_init_wiring.py:640-642` that the profile fails, and
calls that proof "the warning is true".

**And this is a promoted rule already violated.** D-051 and Principle IX
(`docs/decisions.md:1255-1267`) say a governing value is declared, never ambient,
and rule out `gh repo view` as the source of the landing base by name. The
promotion swept the landing path and did not sweep this one.

## The rule this spec is asking for

**A repository the factory wired can land the commit the wiring told it to make,
with checks that can go green, judged against the branch its manifest declares.**

The branch half, complete. "Reads" is the branch the landing policy is fetched
for; every finding's text follows it, because the branch travels on
`LandingPolicy.branch`.

| manifest | forge default | reads today | reads after |
|---|---|---|---|
| declares `release` | `main` | `main` — every epic parks | `release` |
| declares `main` | `main` | `main` | `main`, unchanged |
| silent (schema default `main`) | `main` | `main` | `main`, unchanged |
| silent (schema default `main`) | `dev` | `dev` | **`main`** — a new refusal, and the correct one |
| refused or absent | `dev` | `dev` | `dev`, unchanged — no declaration to obey |

The fourth row is deliberate new strictness. A silent manifest still declares
`main` (`factory/verify/factory_yaml.py:514` — `_read_landing_branch` returns it),
and the landing side already opens every pull request against that declared value
through `factory/workgraph/worktree.py:1442` — `resolve_landing_base`. Today
onboarding is the one reader that disagrees with the lander; after this spec they
agree, and a repository configured so that they disagreed is told so instead of
building against a branch it will never land on.

The queue half, complete. The bypass entry is a single value with a single
meaning, so the table names it rather than gesturing at "a bypass".

| ruleset on the landing branch | who pushes the bootstrap commit | result |
|---|---|---|
| today: armed, no bypass entry at all | an organization administrator | refused by the rule the wiring just created |
| today: armed, no bypass entry at all | a repository admin who is not an organization administrator | refused, identically |
| after: armed, one entry — actor type `OrganizationAdmin`, mode `always`, `actor_id` null | an organization administrator | accepted |
| after: the same entry | a repository admin who is not an organization administrator | **still refused** — stated below, not fixed here |

### What this spec is not

It does not change what the queue *requires*. Exactly one required check per
declared gate, and no others, is unchanged — that property is what keeps the LLM
judge out of the forge's checks and it is untouched here.

It does relax whom that requirement binds, and denying that would be the lie this
spec exists to stop telling. A bypass entry in mode `always` is an ungated direct
push to the landing branch, for every organization administrator, for as long as
the ruleset lives. The ledger already carries the harm:
`verify/an-operator-push-to-the-landing-branch-bypasses-the-required-check-and-can-red-the-trunk-every-node-builds-on`
is open and critical because on this repository `c9dea78` went straight to
`ergane-buildout` carrying four failing tests, and both 075 nodes had to detect
and repair someone else's red trunk inside their own stories. That row's own
remedy (a) — route operator changes through the same proposal-and-queue path
every node uses — is the opposite of what FR-011 ships. This spec ships it
anyway, because the printed steps this spec is fixing instruct a direct push and
because `always` is the only mode any source in this tree has been measured to
accept; plan.md trap 13 writes out the refusal of the narrower mode and what it
would cost to take it instead. That key is not declared in `fixes:` and is not
closed here.

The bypass admits organization administrators and nobody else.
`factory/mergequeue/wiring.py:356` — `repository_can_host_merge_queue` accepts
any public repository owned by an organization, and creating a ruleset needs
repository-admin rights rather than organization-owner rights, so an operator who
is a repository admin and not an organization administrator runs `--wire`
successfully and is still refused the bootstrap push. That operator is not fixed
here: the repository-role actor is a magic integer no source in this tree
records, and inventing one is exactly the failure plan.md trap 13 names. What
that operator gets instead is FR-016 — the wiring report names both the actor
class and the mode the ruleset carries, so the narrowing is read off the report
rather than discovered by a refused push.

It is not a per-gate scope and it does not edit
`factory/mergequeue/onboard.py`. Spec 128 owns that module and owns
`_gate_check_finding`; every finding's text becomes true here without any finding
being edited, because the branch reaches them through `LandingPolicy.branch`.

It is not a guess at every toolchain. Three derivations, each a named marker with
a roster entry, and an explicit statement naming any gate for which nothing was
derived — silence is stated, never blanket.

It is not a fix for the boundary half of the browser problem. A workflow may
install a browser because a runner's `HOME` persists; the gate boundary replaces
`HOME` with a tmpfs (`factory/verify/gates.py:728`) and the existing annotation
at `factory/verify/gates.py:1652` already says so to the agent. This spec records
that asymmetry in the file it renders and changes nothing about the boundary.

## User Scenarios & Testing

### User Story 1 - The profile is read for the branch the manifest declares (Priority: P1)

As an operator running the two-branch model this factory's own README describes,
my repository passes onboarding instead of parking every spec I own.

**Why this priority**: P1 and it depends on nothing. It is the only one of the
three defects that stops work on a repository that is *already* bootstrapped, so
it is the one costing money today, and it is the one D-051 already decided.

**Independent Test**: Evaluate a repository whose manifest declares a landing
branch that is not the forge's default and whose queue is wired on the declared
one, and read the profile's verdict and the branch its findings name.

**Acceptance Scenarios**:

1. **Given** a repository whose manifest declares `landing_branch: release`, whose
   forge default branch is `main`, and whose queue is wired on `release`, **When**
   onboarding evaluates it, **Then** the profile passes — proven by a committed
   test that is today's
   `tests/test_ergane_init_wiring.py:609` —
   `test_a_landing_branch_that_is_not_the_default_is_wired_and_the_divergence_reported`
   with the same fixture and the verdict inverted, so the diff shows an assertion
   changing from `not profile.passed` to `profile.passed`.
2. **Given** that same repository, **When** the profile's findings are read,
   **Then** every finding that names a branch names `release` — `gated_landing`
   and `autonomous_landing` among them — and the diff contains no edit to
   `factory/mergequeue/onboard.py`, proving the branch arrived through
   `LandingPolicy.branch` rather than through a finding taught to name one.
3. **Given** a repository whose manifest cannot be loaded at all — absent, or
   refused by the schema — **When** onboarding evaluates it, **Then** the branch
   the policy is fetched for is the forge's default branch exactly as today and
   the manifest finding still fails, asserted by a committed test, so an
   unreadable manifest never becomes a branch decision.
4. **Given** a repository whose manifest declares no `landing_branch` and whose
   forge default branch is `dev`, **When** onboarding evaluates it, **Then** the
   policy is fetched for `main`, the value the schema declares on its behalf, and
   a committed test asserts that branch name — the deliberate new refusal, and the
   same value `factory/workgraph/worktree.py:1442` — `resolve_landing_base`
   already hands the lander.
5. **Given** a repository wired on a branch that is not the forge default, **When**
   the wiring report is rendered, **Then** the divergence step no longer states
   that every epic start will keep failing and no longer offers
   `gh repo edit --default-branch`, asserted by a committed test over the report
   text; the same diff corrects the module docstring at
   `factory/mergequeue/wiring.py:41-47` and the sentence at
   `docs/architecture.md:668-673`, both of which state the behaviour this story
   removes.

### User Story 2 - The scaffolded workflow installs what its own gate commands need (Priority: P1)

As an operator who has just been handed a workflow file to commit, the checks it
produces can go green without me guessing what the factory already knows.

**Why this priority**: P1. It is the third recorded occurrence of one defect and
the reason a freshly wired repository ships with required checks that fail for a
reason unrelated to its code. It depends on nothing, and it lands second only
because it shares a file with US1.

**Independent Test**: Render the workflow for a manifest declaring a `uv` gate, an
`npm` gate, a browser gate and an unrecognised gate, and read the four jobs.

**Acceptance Scenarios**:

1. **Given** `gates:` declaring `test: uv run pytest -q`, **When** the workflow is
   rendered, **Then** that job's steps are checkout, a pinned `astral-sh/setup-uv`
   step, `uv sync`, then the gate command, in that order — asserted by a committed
   test that reads the rendered text.
2. **Given** `gates:` declaring `lint: npm --prefix web run lint`, **When** the
   workflow is rendered, **Then** that job carries a pinned `actions/setup-node`
   step and `npm ci --prefix web` before the gate command, with the prefix taken
   from the command rather than assumed, asserted by a committed test.
3. **Given** a gate command that names playwright and does not name `npm`, such
   as `npx playwright test`, **When** the workflow is rendered, **Then** that job
   carries a pinned node setup step and then `playwright install --with-deps`
   after it — the playwright roster entry implies the node setup its own install
   needs, so the ordering has something to be ordered after even though FR-006's
   `npm` marker did not match — and the rendered file carries a comment stating
   that the same install cannot satisfy the gate inside the verification boundary
   because `HOME` there is a tmpfs; asserted by a committed test over the rendered
   text.
4. **Given** a gate command none of the declared markers matches, such as
   `make check`, **When** the workflow is rendered, **Then** that job is checkout
   and the command alone, and the rendered file states, naming that gate, that no
   setup was derived for it; a committed test asserts both, and asserts that the
   blanket `TODO(operator)` string at `factory/mergequeue/wiring.py:131-132` is
   gone from the module.
5. **Given** the exact workflow text this repository rendered before this story,
   committed into a target repository as a fixture, **When** `--wire` runs against
   it, **Then** the step reports that the file exists and differs and was not
   overwritten, and the file is byte-unchanged — a committed test that fails
   against a diff which changed nothing, because an unchanged renderer would
   report the file already satisfied instead.
6. **Given** a command that merely mentions a marker inside a quoted argument,
   such as `pytest -k "uv run"`, **When** the workflow is rendered, **Then** no
   setup step is derived for it, asserted by a committed test — the roster matches
   the command a gate runs, never a substring of anything.

### User Story 3 - The queue does not lock out the identity that wired it (Priority: P1)

As an operator who just ran `--wire`, I can push the bootstrap commit the wiring
told me to make.

**Why this priority**: P1 and it is the defect with two open ledger rows. It
lands third because it shares `factory/mergequeue/wiring.py` with US1 and US2 and
because the workflow it unblocks the push of is only worth pushing once US2 has
made it capable of passing.

**Independent Test**: Wire a fresh repository through the offline forge model and
read the body actually posted to the rulesets endpoint; then re-wire it and read
what was posted the second time.

**Acceptance Scenarios**:

1. **Given** a repository being wired for the first time, **When** the ruleset is
   created, **Then** the posted body carries exactly one bypass entry, equal
   field-for-field to the array plan.md § "What already exists, and where" quotes
   from this repository's live ruleset — actor type `OrganizationAdmin`, mode
   `always`, `actor_id` null — read from
   `factory/mergequeue/merge_queue_ruleset.json` and asserted literally by a
   committed test over the body the client received, so neither the actor class
   nor the mode can later move without that test moving with it.
2. **Given** that same change, **When** the diff is read, **Then** the bypass
   declaration is added to the JSON data file only and no module under `factory/`
   gains an identifier or a string constant spelling the word
   `tests/test_final_sweep.py:484` reserves, proven by
   `tests/test_final_sweep.py:614` —
   `test_the_component_cannot_even_spell_a_cap` staying green over the changed
   module.
3. **Given** a repository already carrying the ruleset this wiring writes, **When**
   `--wire` runs again, **Then** it reports the ruleset already satisfied and
   issues no mutating call —
   `tests/test_ergane_init_wiring.py:489` —
   `test_rewiring_reports_already_satisfied_and_changes_nothing` stays green
   unmodified.
4. **Given** the body this wiring builds — asserted in the same test to carry the
   bypass entry, so the case cannot hold vacuously over a payload that declares
   nothing — and a stored ruleset shaped the way a forge returns one, its bypass
   entries in a different order and each carrying the per-entry keys the forge
   fills in, **When** the comparison runs, **Then** it still reports satisfied,
   asserted by a committed test that hands both shapes to the comparison directly,
   because the offline model stores the posted body verbatim on both of its
   paths — `tests/test_ergane_init_wiring.py:272` — `_create_ruleset` on the POST
   and the PUT branch at `tests/test_ergane_init_wiring.py:248-251` on a re-wire —
   and so can never produce that shape itself.
5. **Given** a stored ruleset whose bypass differs in meaning from the declared
   one — the same actor type in a different mode, and a second case with a
   different actor type — **When** `--wire` runs, **Then** each is reported not
   satisfied and updated to carry the declared entry, asserted by a committed
   test — a bypass somebody else chose is not silently accepted as this factory's.

### User Story 4 - The printed order is the order that works (Priority: P2)

As an operator reading what `--wire` tells me — the step details a successful run
prints and the by-hand list a refused one prints — the step that unlocks the push
comes before the step that locks the branch, on both paths. The two paths are
governed separately: FR-015 owns the by-hand list at
`factory/mergequeue/wiring.py:104` — `manual_steps`, which is rendered only on
refusal, and FR-016 and FR-017 own the two details a successful run prints.

**Why this priority**: P2. Once US3 has landed, the deadlock is gone whether or
not the text is right; this story is what stops the next operator being told an
order that only works because of a bypass they were never told about.

**Independent Test**: Render the printed step list and the wiring report for a
first-time wiring and for a re-wiring, and read the order and the two details.

**Acceptance Scenarios**:

1. **Given** the printed step list, **When** it is rendered, **Then** the step that
   commits and pushes the workflow appears before the step that adds the ruleset,
   and the entries that carry a number carry `1` to `N` in order of appearance
   with no gap and no repeat, the unnumbered continuation lines skipped — asserted
   by a committed test over the returned list, on the numbers the entries carry
   and not on their prose, so a reordering that forgot to renumber fails.
2. **Given** a first-time wiring, **When** the queue step reports, **Then** its
   detail states that the workflow must be pushed before any proposal can satisfy
   the required checks and names both the actor class and the mode of the bypass
   the ruleset carries; **and** given a re-wiring of the same repository, the
   already-satisfied detail does not carry that sentence — both asserted in one
   committed test, so the sentence cannot be added unconditionally.
3. **Given** the scaffold step that has just written the file, **When** its detail
   is read, **Then** it tells the operator to commit *and push* it and gives the
   bootstrap order as the reason, replacing the text at
   `factory/mergequeue/wiring.py:241` — `scaffold_gates_workflow`, asserted by a
   committed test.
4. **Given** the two `gh api` commands the by-hand list has always carried,
   **When** the list is rendered after the reordering, **Then** both strings are
   unchanged, proven by two committed tests staying green and unmodified — the
   auto-merge string by `tests/test_ergane_init_wiring.py:763` —
   `test_manual_steps_renders_the_auto_merge_command`, which asserts on
   `allow_auto_merge=true` in a resolved and a placeholder form and on nothing
   else, and the squash-title string by `tests/test_wiring_us2.py:129` —
   `test_refusal_carries_complete_manual_steps`, the only assertion in the tree on
   `squash_merge_commit_title=PR_TITLE`. Neither is the control on its own.

## Functional Requirements

- **FR-001**: Onboarding MUST fetch the landing policy for the branch the target
  repository's manifest declares, not for the branch the forge reports as its
  default.
- **FR-002**: When the manifest cannot be loaded, onboarding MUST fetch the policy
  for the forge's default branch exactly as it does today, and the manifest
  finding MUST still fail.
- **FR-003**: The branch MUST reach every finding through `LandingPolicy.branch`;
  no finding may be edited to name a branch, and the diff MUST NOT touch
  `factory/mergequeue/onboard.py`.
- **FR-004**: `factory/mergequeue/wiring.py:559` — `_divergence_step` MUST stop
  asserting that onboarding reads the default branch and MUST stop offering the
  two remedies that abandon the declaration, and the two other places in the tree
  that state the removed behaviour — the module docstring at
  `factory/mergequeue/wiring.py:41-47` and `docs/architecture.md:668-673` — MUST be
  corrected in the same diff.
- **FR-005**: A rendered job whose gate command runs under `uv` MUST carry a pinned
  uv setup step and a dependency sync step before the gate command.
- **FR-006**: A rendered job whose gate command runs `npm` MUST carry a pinned node
  setup step and a clean install before the gate command, taking any `--prefix`
  from the command itself.
- **FR-007**: A rendered job whose gate command names playwright MUST carry a
  browser install with system dependencies after its node setup, and the
  playwright roster entry MUST itself imply that node setup, so a command naming
  playwright without naming `npm` — `npx playwright test` — still renders the step
  the install is ordered after.
- **FR-008**: A gate command matching no declared marker MUST render as checkout
  plus the command, and the rendered file MUST state, naming that gate, that no
  setup was derived for it; the blanket `TODO(operator)` MUST be gone.
- **FR-009**: The derivations MUST be a roster of named markers modelled on
  `factory/verify/gate_annotation.py:86-95`, each matched on a word-boundary
  phrase against the command a gate runs. A roster entry MAY declare that it
  implies another entry's steps — that is how FR-007's playwright entry obtains
  the node setup its install is ordered after — and every roster entry MUST be
  exercised by a committed test together with one command that matches none.
- **FR-010**: The rendered file MUST record that a browser install works in the
  generated workflow because a runner's `HOME` persists and cannot satisfy the
  same gate inside the verification boundary, whose `HOME` is a tmpfs
  (`factory/verify/gates.py:728`).
- **FR-011**: The ruleset body the wiring posts MUST carry exactly one bypass
  entry, declared in `factory/mergequeue/merge_queue_ruleset.json` and not
  composed in Python, equal field-for-field to the array plan.md § "What already
  exists, and where" quotes from this repository's live ruleset: actor type
  `OrganizationAdmin`, mode `always`, `actor_id` null. The shape is copied from
  that read-back and MUST NOT be invented (trap 13).
- **FR-012**: No module under `factory/` may gain an identifier or a string
  constant spelling the word `tests/test_final_sweep.py:484` reserves; the reason
  the bypass arm was taken rather than the non-blocking arm MUST be recorded as a
  comment where the body is built.
- **FR-013**: The comparison at `factory/mergequeue/wiring.py:589` —
  `_ruleset_satisfies` MUST decide the bypass declaration by meaning rather than
  by the bare inequality at `factory/mergequeue/wiring.py:592`, so a stored
  ruleset carrying the same declaration with its entries in a different order, or
  with per-entry keys the forge filled in, still reports satisfied and provokes no
  write.
- **FR-014**: A stored ruleset whose bypass differs in meaning from the declared
  one — a different actor type, a different mode, or a different number of
  entries — MUST be reported not satisfied and updated to the declared one.
- **FR-015**: `factory/mergequeue/wiring.py:104` — `manual_steps` — the by-hand
  list, rendered only when the wiring refuses — MUST place committing and pushing
  the workflow before the step that adds the ruleset, and
  the entries that carry a number MUST carry `1` to `N` in order of appearance
  with no gap and no repeat. The list's unnumbered continuation lines
  (`factory/mergequeue/wiring.py:117` and `factory/mergequeue/wiring.py:119`) are
  not entries and are skipped by that reading; a requirement that a number equal
  a list index is unsatisfiable over this list and MUST NOT be written.
- **FR-016**: The queue step's creation path — one of the two details a
  successful `--wire` prints — MUST state that the first push precedes the queue
  being satisfiable and MUST name both the actor class and the
  mode of the bypass the ruleset carries, so an operator the bypass does not admit
  reads that from the report; the already-satisfied path MUST NOT carry that
  sentence.
- **FR-017**: The applied detail of `factory/mergequeue/wiring.py:241` —
  `scaffold_gates_workflow` MUST tell the operator to commit *and push* the file
  and MUST give the bootstrap order as the reason.
- **FR-018**: The two `gh api` command strings in the by-hand step list MUST keep
  their current text, and both of the existing controls MUST stay green and
  unmodified: `tests/test_ergane_init_wiring.py:763` —
  `test_manual_steps_renders_the_auto_merge_command` for `allow_auto_merge=true`,
  and `tests/test_wiring_us2.py:129` —
  `test_refusal_carries_complete_manual_steps` for
  `squash_merge_commit_title=PR_TITLE`. Neither test covers both strings, so
  neither alone satisfies this requirement.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-011, FR-012, FR-013, FR-014]
US4:
  depends_on: []
  depends_on_merged: [US1, US2, US3]
  implements: [FR-015, FR-016, FR-017, FR-018]
```

No story reads a symbol another story writes, so there is no pass-edge anywhere:
every edge here is a merge edge and every merge edge is a file collision, stated
rather than left to be inferred (069-US2 FR-008). All four stories edit
`factory/mergequeue/wiring.py` and all four add cases to
`tests/test_ergane_init_wiring.py`, so each story declares a merge edge to every
story ahead of it rather than only to the one immediately ahead — the inference
that would otherwise add them reads pairs, not chains, and a chain would leave
US1 and US3 undeclared to each other.

The order within that chain is chosen, not arbitrary. US1 is first because it is
the only defect of the three that stops a repository already past bootstrap, so
it is the one costing money while the rest of this spec is being built. US2 is
second because US3 unlocks a push of a file that is worth pushing only once it
can go green. US4 is last because it is the text describing what US2 and US3 did,
and text written ahead of the behaviour it describes is the defect this whole
spec is about.
