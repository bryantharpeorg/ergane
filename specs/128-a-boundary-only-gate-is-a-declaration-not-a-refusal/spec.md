---
state: landed
fixes:
  - feedback/pr-9-a-boundary-only-gate-is-a-choice-onboarding-cannot-be-told-about
# Attested landed 2026-09-07. US1 12d878a94f2c (#433), US2 8c235c63cdc8 (#434) —
# both observed on ergane-buildout by content, both on the first attempt, both
# PASS with no retry, no judge failure and no escalation. The epic ran twice
# (2026-09-06 16:45Z and 17:42Z); that was a relaunch between stories, not a
# rework — each node records attempt 1.
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. PR-9 of the `ergane-web` consolidated hand-over
# (`ergane-findings-ergane-web-2026-09-03.md`), filed 2026-08-27 from a live
# outage. It is the only item in that entire corpus that stopped a consumer's
# whole line, and it blocks on nothing.
#
# WHAT IT COST, MEASURED BY THE CONSUMER. The line was stopped 11h40m. The
# operator was offered a one-API-call workaround — add the gate to the branch
# ruleset — and DECLINED IT, choosing to leave their own line stopped rather than
# reverse a written decision. That decision is the argument for this spec: the
# configuration ergane refuses is one a careful operator chose, wrote down in
# `docs/decisions.md`, and would rather wait for than abandon.
#
# THE DECISION ERGANE CANNOT SEE. The consumer put an `audit` gate in the manifest
# and in the workflow but deliberately NOT in the ruleset, because an audit gate
# stops the line on a HIGH advisory — or on an advisory database it merely could
# not reach — and if the same gate also blocks the merge queue then nobody can
# hand-land the fix, including the fix for the network. They amended their own
# `CLAUDE.md` to record the asymmetry rather than let the file quietly disagree
# with the ruleset.
#
# THE ARGUMENT IS ALREADY IN THIS TREE, MADE ABOUT A DIFFERENT NOUN.
# `_noop_gate_finding` is the one finding in that module that warns instead of
# failing, and the verdict comment beside `passed=` says why: a verdict that read
# it as a refusal "would fail every repository that had deliberately turned its
# gates off (061 FR-009)". Every word of that reasoning applies here. This spec
# does not invent a policy; it extends one the module already holds.
#
# NOT IN SCOPE. This spec does not change what the boundary gate runs, does not
# touch the merge queue, the ruleset writer or `init --wire`, does not alter the
# `unknown_check:` or `noop_gate:` findings, and does not make any currently
# non-blocking finding blocking. A manifest that does not declare the new key
# behaves byte-identically to today.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04-smoke);
# every anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c.
#
# WHAT CHANGED. Spec 057 landed four stories between 238b494 and 602a92c and one
# of them added 97 lines to `factory/mergequeue/onboard.py`, so all seven anchors
# into that file had moved — `evaluate_repo` 150→162, the gate loop 203→215, the
# verdict comment 219→231 (validate refused: 219 is now blank), the conjunction
# 223→235, `_noop_gate_finding` 334→340, and the two `Finding` constructions
# 374/378→386/390. All are re-anchored in the symbol-tier form so the next drift
# is machine-caught. The fourteen anchors outside that file were re-read and had
# not moved.
#
# THE PLAN WAS WRONG ABOUT WHERE US2 LIVES, AND THAT WAS THE EXPENSIVE FIND. It
# said US2 touches `factory/mergequeue/onboard.py` "and no other production file",
# but `evaluate_repo` has exactly one caller — `onboard_target_repo` — and it is
# where the manifest is read. An implementer obeying that sentence would add the
# parameter, test it by passing the list directly, pass every gate and the judge,
# and ship a manifest key that never reaches production. FR-010 and US2-S5 now
# require the seam; the sizing paragraph names the second file.
#
# TWO HAZARDS ADDED FROM THE NEIGHBOUR LANDING. 057 put a *blocking* `standards`
# finding into `evaluate_init_facts`, so a US2 fixture that builds `InitFacts`
# without `standards_path`/`standards_exists` now gets a failing profile for a
# reason this spec is not about (trap 8). And `_read_writes` is the exact
# cross-check precedent for FR-002 — including the comment making Trap 5's
# argument — but `writes` is legal in v1, so copying it wholesale breaks FR-004
# (folded into trap 4).
#
# US1-S4 WAS PASSABLE BY A DO-NOTHING DIFF. "A v1 manifest refuses the key" is
# true today, before any change. It is now differential: the same manifest body
# must parse under v2 and refuse under v1.
#
# THE KEY IS KEPT, WHOLE. One key, nine — now ten — FRs, and the truth table in
# the ledger row matches this spec's row for row. Nothing was removed. The row
# still sits at severity `info` despite the measured 11h40m outage; re-grading it
# is a ledger act for the operator, not this refinement.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-smoke, cross-batch): a completeness
# critic read this trio against the rest of the batch and named four gaps. Three
# are closed in plan.md and tasks.md and nothing in this file's requirements,
# stories or Work Graph changed. The fourth is an operator act, recorded below
# because it must happen before dispatch and no gate will catch it.
#
# THE COMPILED ARTIFACT BESIDE THIS FILE IS STALE, AND MUST BE CLEARED BEFORE
# DISPATCH. `workgraph.json` in this directory was derived at 238b494 — before
# the 2026-09-04 refinement added FR-010 — and its `us2.requirement_keys` stop at
# FR-009. `ergane build start` reads a compiled graph off disk at
# `factory/cli/nouns/build.py:808` — `start_command`, and those requirement keys
# travel through `factory/workgraph/workflow.py:1740` — `_run_node` and
# `factory/activities/verify_activities.py:187` — `snapshot_criteria` into
# `factory/verify/criteria.py:450` — `load_criteria`, which is what selects the
# criteria the judge scores against, and through
# `factory/workgraph/prompt.py:606` — `_requirement_sections` into the prompt the
# node is handed. Dispatching from that file would hand the US2 node a prompt and
# a judged criteria set that never name the seam requirement — the precise
# failure trap 9 exists to prevent, landed with a green judge.
# `ergane spec validate` re-reads spec.md and cannot see it. This refinement is
# not permitted to write or delete that artifact: the operator deletes it (it is
# untracked, and `build start` is fed a freshly derived graph) or re-derives it
# and confirms `us2.requirement_keys` ends in FR-010.
#
# WHAT THE OTHER THREE ADDED, ALL OF IT IN plan.md AND tasks.md. The seam
# paragraph now names the two places the tree already drives `onboard_target_repo`
# offline — `tests/test_114_us2_fixtures_onboard.py:252` — `onboarding_findings`
# and `tests/test_114_us1_smoke_onboards.py:317` — so US2-S5's test copies a
# working shape instead of inventing a third forge fake or giving up and calling
# `evaluate_repo` directly; T014 repeats the citation where the implementer meets
# it. (Both citations were WRONG for this purpose and are replaced below.) Trap 4
# now names the consequence of registering the key outside
# `_V2_TOP_LEVEL_KEYS`: `_KNOWN_KEYS` (`factory/cli/init.py:511`) is that tuple,
# and `factory/cli/init.py:759` — `_carried_forward` refuses every manifest
# declaring a key outside it, so the wrong tuple breaks `ergane init` outright
# while the right one makes init carry and rewrite the key with no init edit —
# 120's defect from the other side. And the operator sequence's step 4 now runs
# the third door, `ergane repo onboard`, which FR-010 names and no scenario, task
# or step drove; it is the door that calls the seam with no `init_facts`.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. All fifty-seven unique citations — the forty-six inherited and the
# eleven this pass adds — resolve, every symbol-form one sits inside the span it
# names, and none had moved again since the pass above. The
# neighbour log over every file this plan touches, taken from the drafting date,
# holds nothing but 057's four landings, which that pass already absorbed.
#
# US2-S4 WAS PASSABLE BY A DIFF THAT TOUCHED NO PRODUCTION FILE, AND THAT IS THIS
# PASS'S FIND. Both refusal sites are already driven, green, on today's tree by a
# profile a test wrote by hand:
# `tests/test_interpreter.py:1045` — `ScriptedWorld.__init__` defaults
# `onboard_profile` to a passing `TargetRepoProfile`, and
# `tests/test_interpreter.py:2458` — `test_a_passing_onboarding_profile_proceeds_to_normal_dispatch`
# asserts the epic proceeds on it; `tests/test_roadmap_scheduler.py:251` —
# `_passing_profile`, injected at
# `tests/test_roadmap_scheduler.py:299` — `RoadmapWorld.__init__`, is
# the same thing for the roadmap. An implementer copying either satisfied the old
# scenario without writing a line of production code. US2-S4 and FR-009 now
# require both verdicts to be DERIVED from two manifests differing only in the
# declaration; plan.md carries the reproduction as trap 10 and T013 rewrites the
# task around it.
#
# ONE CITATION IN THE REPAIR BLOCK ABOVE WAS WRONG AND IS CORRECTED IN PLACE.
# `factory/activities/merge_activities.py:376` is the PR body's requirement list,
# not the criteria path; requirement keys reach the judge through `_run_node` and
# `snapshot_criteria`, and the prompt through `_requirement_sections`. That
# paragraph's substance is untouched and still an operator act: the stale
# `workgraph.json` beside this file must be deleted or re-derived before dispatch.
#
# NOTHING ELSE MOVED. The one key is kept whole, its ledger row's truth table
# still matches this spec's row for row, and it still sits at severity `info`
# despite the measured 11h40m outage — re-grading it remains a ledger act for the
# operator. plan.md also gains the dispatch door's own anchor
# (`factory/activities/merge_activities.py:777` — `validate_target_repo`) and a
# sizing paragraph that names the two workflow suites T013 must touch, which
# "`tests/test_onboard.py` and one new module" did not. state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): an adversarial review refuted the
# trio on one root cause wearing two faces, and it was rot kind 1 — an
# instruction gone wrong, not an anchor that moved. Every offline route the plan
# named for US2-S4 and US2-S5 goes through the REAL forge
# (`factory/activities/merge_activities.py:338` — `_forge`) over a remote-less
# repository, which refuses before `evaluate_repo` is ever called: US2-S5's Then
# ("the profile still passes") was unreachable by the mandated route, and trap
# 10's derived pair collapsed to two identical `repo_read` failures, killing the
# differential US2-S4 rests on. Re-derived here and confirmed:
# `factory/activities/merge_activities.py:719` — `_profile_from_forge_failure`
# hardcodes `passed=False` and never calls `evaluate_repo`, and
# `tests/test_114_us1_smoke_onboards.py:346` asserts exactly that about the very
# call the plan told the implementer to copy.
#
# WHAT THE REPAIR CHANGED, ALL OF IT IN plan.md AND tasks.md. The seam paragraph,
# trap 9, trap 10 and the sizing paragraph now name the MODELLED forge instead —
# `tests/fake_forge.py:160` — `FakeForge` over `tests/target_repo.py:102` —
# `build_target_repo`, the route `tests/test_forge_readiness.py:68` already drives
# to `passed is True` with `init_facts` unset — and T013 and T014 are rewritten
# around it, each carrying the prohibition on the route that looks identical. A
# new trap 11 records the last step of that route: both fixture families write
# **v1** manifests while this key is v2-only, so the test must rewrite the
# manifest as `version: 2` or collect a `factory_yaml` refusal instead. plan.md
# and tasks.md now also cite `tests/test_ergane_init_check.py:490` —
# `test_both_doors_render_identical_parity_findings`, the committed two-door
# assertion FR-010 should extend rather than leave entirely to a by-hand step, and
# the interpreter citation above is written on one line so the symbol tier
# actually checks it. Requirements, stories, scenarios, the Work Graph, the one
# `fixes:` key and every hold and NOT IN SCOPE paragraph above are unchanged, the
# stale `workgraph.json` is still an operator act, the `info` grade is still a
# ledger act, and state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): US2-S5 was green before the
# production change, and that was the whole refutation. The route T014 mandated
# copies `_ready_model` (`tests/test_forge_readiness.py:57`), whose landing
# branch requires EVERY declared gate, so `factory/mergequeue/onboard.py:385` —
# `_gate_check_finding` takes its passing branch for all of them and the profile
# passes with or without the seam FR-010 asks for. US2-S5's Given and FR-010 now
# require the listed gate to be declared and NOT required on the landing branch —
# the single arrangement in which the declaration decides the verdict — and T014
# is rebuilt on trap 10's model, carrying the red-before line T013 already had
# and a door-parity extension that asserts the finding's mark rather than parity
# alone (the two doors render identical triples before this story and after it).
# plan.md's worked-example paragraph, its door-parity paragraph and trap 9 carry
# the same condition, and the sizing paragraph's "four places" is corrected to
# the five files it then lists. Stories, the Work Graph, the one `fixes:` key and
# every hold and NOT IN SCOPE paragraph are unchanged. The `workgraph.json`
# beside this file was re-read this pass and its `us2.requirement_keys` still
# stop at FR-009: deleting or re-deriving it remains an operator act, as
# re-grading the `info` row remains a ledger act. state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): two instruction defects, both rot
# kind 1 — instructions gone wrong, not anchors that moved — and both fixed in
# plan.md and tasks.md. Nothing in this file's requirements, stories, scenarios,
# Work Graph or `fixes:` key changed.
#
# US1'S CORRECT DIFF WAS GATE-RED AND THE TRIO DID NOT SAY SO. `_KNOWN_KEYS`
# (`factory/cli/init.py:511`) *is* `_V2_TOP_LEVEL_KEYS`, the same object — verified
# by derivation, not by reading — and 120's landed
# `tests/test_120_rewrite_carries_forward.py:310` pins the carried-key list at
# `["ladder", "verify"]`. Registering `boundary_only_gates` where FR-004 requires
# makes that list three entries long, so the declared gate
# (`test: "uv run pytest -q"`, which is the whole suite) is red until that
# assertion is updated — and the one move that clears it without touching the
# test is putting the key in `_TOP_LEVEL_KEYS`, which trap 4 and FR-004 forbid and
# which breaks `ergane init` outright. New trap 13 and a clause in T005 name the
# file, the line and the update, and say the red is confirmation rather than a
# signal to move the key; US1's sizing paragraph names that test beside the two
# production files.
#
# THE US2 MODEL RECIPE COULD NOT PRODUCE A PASSING PROFILE. Trap 10, T013 and T014
# localised the difference from `_ready_model` to the gate tuple alone, but
# `tests/fake_forge.py:90` — `gate_on` reports a title source only when the caller
# passes one, and `factory/mergequeue/onboard.py:290` — `_landing_title_finding`
# appends a blocking finding when it does not. A model built to the recipe as
# written failed `landing_title` in both halves: US2-S5's Then unreachable and
# US2-S4's differential collapsed — the same failure this spec has now been
# refuted on three times, wearing a third face. The call is spelled with
# `title_source=NEUTRAL_TITLE_SOURCE` in the plan's worked example, in trap 10 and
# in both tasks; new trap 12 records the red as the third member of trap 8's
# series; and T014 now asserts the pair rather than the passing half alone.
#
# PROVENANCE IS APPENDED TO, NOT EDITED. The pass above corrected a citation
# inside an earlier entry in place; this one changes no earlier line, and every
# hold and NOT IN SCOPE paragraph stands as written. The stale `workgraph.json`
# beside this file is still an operator act — re-read this pass, its
# `us2.requirement_keys` still stop at FR-009 — and re-grading the `info` row
# against a measured 11h40m outage is still a ledger act. state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, re-run of the repair step): both
# blocking defects were re-derived from the tree before anything was written —
# `_KNOWN_KEYS` (`factory/cli/init.py:511`) is `_V2_TOP_LEVEL_KEYS`, and
# `tests/test_120_rewrite_carries_forward.py:310` pins the carried list at
# `["ladder", "verify"]`; `tests/fake_forge.py:103` sets
# `landing_title_from_proposal=title_source is not None`, and
# `factory/mergequeue/onboard.py:208` — `evaluate_repo` calls
# `factory/mergequeue/onboard.py:290` — `_landing_title_finding` unconditionally,
# so a model without `title_source` blocks. Both repairs were already on disk —
# traps 12 and 13, T005, T013 and T014 — and every anchor they rest on was
# re-read line by line this pass and resolves. Nothing in the requirements,
# stories, scenarios, Work Graph, traps, tasks, holds or NOT IN SCOPE paragraphs
# changed; this entry is the only line added. The stale `workgraph.json` beside
# this file remains an operator act and re-grading the `info` row remains a
# ledger act. state stays draft.
---

# Feature Specification: a boundary-only gate is a declaration, not a refusal

**Created**: 2026-09-03
**Depends on**: nothing.

## The gap, stated precisely

A gate declared in the manifest with no required check of the same name on the
landing branch is a **blocking** onboarding finding, and a blocking onboarding
finding parks **every spec in the repository** — not the spec that touches the
gate. Every spec.

The chain is four short steps:

1. `factory/mergequeue/onboard.py:390` — `_gate_check_finding` constructs
   `Finding(f"gate_check:{gate}", False, ...)` with **no** `severity` argument, so
   it takes the dataclass default at `factory/mergequeue/models.py:351` —
   `Finding`, which is `Severity.ERROR`.
2. `factory/mergequeue/models.py:363` — `blocking` is
   `not self.passed and self.severity == Severity.ERROR` — so that finding blocks.
3. The verdict is a conjunction over every gate:
   `passed=not any(f.blocking for f in findings)` at
   `factory/mergequeue/onboard.py:235` — `evaluate_repo`. One gate fails the whole
   profile.
4. A failed profile refuses at **two** places: the roadmap parks the spec
   (`factory/roadmap/workflow.py:1262` — `_dispatch`) and a child epic
   re-evaluating the same profile raises `GRAPH_INVALID`
   (`factory/workgraph/workflow.py:1225` — `_onboard_target`), so a manual
   `ergane build start` cannot route around it either.

**The stated reason for the refusal is true of the forge and false of the
factory.** "A declared gate with no matching check would land a PR that never runs
that gate" holds for what GitHub enforces. It does not hold for what ergane runs:
the boundary gate iterates every declared gate before a node opens a pull request,
looping over `config.gates.items()` at `factory/verify/gates.py:1491` —
`_run_gate_list_from_config`. A declared gate with no required check is not an
ungated gate. It is a gate that binds nodes and does not bind humans, and that is
a coherent thing to want.

**And the remedy text argues for reversing a decision it cannot see.** "Add it to
the branch's required checks" is right for someone who made a mistake and wrong for
someone who made a choice. The defect is not strictness; it is strictness about
something the manifest has no way to express.

## The rule this spec is asking for

**A repository may declare that a gate binds the boundary alone, and onboarding
reports that declaration instead of refusing it — while the typo case the check
exists for keeps refusing exactly as it does today.**

The four cases, complete:

| declared as a gate | listed boundary-only | required on branch | result |
|---|---|---|---|
| yes | yes | no | **pass**, reported every run |
| yes | yes | yes | non-blocking "declaration is stale" |
| yes | **no** | **no** | **today's blocking failure, unchanged** — the typo case |
| **no** | yes | — | **blocking** — the list names a gate that does not exist |

### What this spec is not

It is not a relaxation of the gate contract. Every declared gate still runs in the
boundary gate before a node opens a pull request; that is the fact the whole
argument rests on and it is unchanged.

It is not a change to `noop_gate:` or `unknown_check:`. Their severities and their
text stay exactly as they are.

It is not a way to make a repository greener. A manifest without the new key is
evaluated byte-identically to today, and a list that names an undeclared gate is
blocking — stricter than today, because today such a name cannot be written at all.

## User Scenarios & Testing

### User Story 1 - The manifest can say a gate binds the boundary alone (Priority: P1)

As an operator with a gate I deliberately do not want blocking the merge queue, I
can write that down where ergane will read it.

**Why this priority**: P1 and it depends on nothing. Without a key to declare, US2
has nothing to consult. The schema half is also where the strictest new behaviour
lives — a list naming an undeclared gate is a refusal that cannot exist today.

**Independent Test**: Load a manifest declaring the key and read the parsed config;
load one whose list names an undeclared gate and read the refusal.

**Acceptance Scenarios**:

1. **Given** a v2 manifest declaring `boundary_only_gates: [audit]` beside a
   `gates:` block that declares `audit`, **When** the manifest is loaded, **Then**
   it parses and the parsed configuration carries that list.
2. **Given** a v2 manifest declaring `boundary_only_gates: [typecheck]` where
   `typecheck` is **not** among the declared gates, **When** the manifest is
   loaded, **Then** it is refused with a message naming `typecheck` and stating
   that the list may only name gates the manifest declares.
3. **Given** a manifest that does not declare the key at all, **When** it is
   loaded, **Then** the parsed configuration is byte-identical to today's, because
   every existing manifest is this manifest.
4. **Given** one manifest body declaring the key, loaded twice — once under
   `version: 2` and once under `version: 1` — **When** each is loaded, **Then** the
   v2 load parses and carries the list while the v1 load is refused as an unknown
   top-level key, so the key is real in v2 and the version boundary is not quietly
   widened. A committed test asserts both halves, and only the pair can fail a diff
   that added the key to the wrong tuple.

### User Story 2 - Onboarding reports the declaration instead of refusing it (Priority: P2)

As an operator, a gate I declared boundary-only does not park every spec in my
repository.

**Why this priority**: P2 and it depends on US1 having a key to read. This is the
story that ends the outage: it turns one blocking finding into a reported one, and
both refusal sites clear as a consequence rather than by being edited.

**Independent Test**: Evaluate a repository whose manifest lists a gate
boundary-only and whose landing branch requires no such check, and read the
profile's verdict and findings.

**Acceptance Scenarios**:

1. **Given** a gate declared, listed boundary-only, and **not** required on the
   landing branch, **When** the repository is evaluated, **Then** the profile
   passes and still carries a non-blocking finding naming that gate, so the choice
   stays visible every run rather than becoming silent.
2. **Given** a gate declared, listed boundary-only, and **required** on the landing
   branch, **When** the repository is evaluated, **Then** the profile passes and
   carries a non-blocking finding stating the declaration is stale, because the
   list now describes something that is not true.
3. **Given** a gate declared and **not** listed boundary-only and not required on
   the landing branch, **When** the repository is evaluated, **Then** the profile
   fails with today's blocking `gate_check:<gate>` finding, byte-identical in text,
   because that is the typo case the check exists for.
4. **Given** two manifests differing only in the `boundary_only_gates` line, each
   turned into a profile by the real judgment rather than written by the test,
   **When** the roadmap's dispatch path and a child epic's re-evaluation each
   consult the pair, **Then** the listed one neither parks nor raises while the
   unlisted one still parks and still raises — proving both refusal sites were
   cleared by the verdict rather than by a second edit. A `TargetRepoProfile` a
   test constructed with `passed=True` cannot satisfy this scenario: both surfaces
   already proceed on one today, so a diff touching no production file would pass
   it.
5. **Given** a repository whose manifest declares the list for a gate that is
   declared and **not** required on the landing branch — the one arrangement in
   which the declaration is what decides the verdict — evaluated through
   `onboard_target_repo`, the one seam the dispatch activity, `ergane init
   --check` and `ergane repo onboard` all share, **When** the caller names no
   list of its own, **Then** the profile passes where the same repository without
   that line fails, because the diff shows that seam reading the list off the
   loaded manifest and handing it to `evaluate_repo`. A test that passes the list
   to `evaluate_repo` by hand cannot satisfy this scenario, and neither can one
   whose landing branch requires every declared gate: such a profile passes
   before the seam exists, so the scenario would be green on a diff that threaded
   nothing. A key that never leaves the schema fixes nothing.

## Functional Requirements

- **FR-001**: The v2 manifest MUST accept a top-level `boundary_only_gates` list of
  gate names beside `gates:`.
- **FR-002**: A `boundary_only_gates` entry naming a gate the manifest does not
  declare MUST be refused, with a message naming the entry and the rule.
- **FR-003**: A manifest that does not declare `boundary_only_gates` MUST parse and
  evaluate exactly as it does today.
- **FR-004**: `boundary_only_gates` MUST be refused on a v1 manifest as an unknown
  top-level key, on the same path every other v2-only key is refused, while the
  same body under v2 parses.
- **FR-005**: A declared gate that is listed boundary-only and has no required
  check on the landing branch MUST produce a non-blocking finding naming the gate,
  and MUST NOT fail the profile.
- **FR-006**: A declared gate that is listed boundary-only and **does** have a
  required check MUST produce a non-blocking finding stating the declaration is
  stale.
- **FR-007**: A declared gate that is **not** listed boundary-only and has no
  required check MUST keep today's blocking finding with its text unchanged.
- **FR-008**: The new non-blocking findings MUST carry `Severity.WARNING`
  explicitly, following `factory/mergequeue/onboard.py:340` —
  `_noop_gate_finding`, and MUST NOT be produced by widening
  `factory/mergequeue/models.py:363` — `blocking` or by changing the verdict
  conjunction at `factory/mergequeue/onboard.py:235` — `evaluate_repo`.
- **FR-009**: Neither the roadmap's park site (`factory/roadmap/workflow.py:1262` —
  `_dispatch`) nor the child-epic refusal (`factory/workgraph/workflow.py:1225` —
  `_onboard_target`) may be edited to special-case this key; a test MUST assert
  both clear through the profile verdict alone, and the verdicts it asserts on
  MUST be derived by evaluating manifests that differ only in the declaration,
  never constructed by the test — both sites already proceed on a hand-built
  passing profile today.
- **FR-010**: The list MUST reach `evaluate_repo` from the loaded manifest through
  `factory/activities/merge_activities.py:639` — `onboard_target_repo`, the single
  seam the dispatch activity, `ergane init --check` and `ergane repo onboard` all
  share, so no door reports a verdict the others do not — and so the key is not a
  schema field that production never reads. The committed test proving it MUST be
  written against a landing branch that does **not** require the listed gate, so
  the seam is what decides the verdict; on a branch requiring every declared gate
  the profile passes before this requirement is implemented at all.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
```

One `depends_on_merged` edge, declared rather than left inferred (069-US2 FR-007).
US2 reads a configuration field US1 adds, and the two stories touch different
modules — `factory/verify/factory_yaml.py` and `factory/verify/models.py` for US1,
`factory/mergequeue/onboard.py` and `factory/activities/merge_activities.py` for
US2 — so the edge buys correctness of sequencing rather than freedom from
contention.
