---
state: landed
# Attested landed 2026-08-16 by an operator session, after `ergane spec landed
# specs/049-forge-seam --default-branch ergane-buildout` observed every
# story in git: US1 fde4309d, US2 784c03ba, US3 6ca72111, US4 0f8f6b36, US5 63760c17, US6 1bfc8c8b.
# Every story passed the real bwrap boundary gate and an LLM judge on a diff
# that fit whole, each with truncated_input=False.
#
# The work graph was rewritten mid-epic (#125) to cut depth from six to four,
# which let US2, US3 and US5 build concurrently -- and cost an ejection from
# the merge queue when US3 landed under US5. `depends_on_merged` models what a
# story needs to EXIST, not what it will TOUCH, and all three extended
# `factory/mergequeue/forge.py`.
#
# SC-001 was repaired before US6 was dispatched: it demanded the onboarding
# profile be unchanged "finding for finding" while US2-S4 mandates a distinct
# new finding, so no correct implementation could satisfy both. The US2
# implementer reported it rather than picking a reading quietly.
# Flipped to ready 2026-08-16 by the operator session after reading the three
# documents. What decided it: the spec does the design act rather than the
# renaming act. It derives six forge-neutral questions from what the factory
# actually does with a forge — propose a change, have it gated on evidence it
# can name, land it without a human — and FR-006 forbids the shared judgment
# from naming a merge queue, a repository visibility or a squash-title setting,
# proven by a test that reads the module's source so a later edit cannot quietly
# reintroduce them. That is the difference between a seam and a rename.
#
# Two of its best moves were self-correction. It found that US4-S2, its own
# idempotence scenario, could have been satisfied through `tests/fake_gh.py` and
# proved nothing — because that fake never consumes an expectation, so "we
# called it once" is unfalsifiable — and fenced the scenario to assert against a
# repository model instead. And it disproved the operator's claim that
# `workgraph/worktree.py` carries GitHub coupling: its two mentions are docstring
# prose, and the git layer is already forge-neutral because ADO speaks git too.
#
# Drafted 2026-08-16 by an operator session, implementing D-046 ("The forge is an
# adapter, and GitHub is the reference implementation"), decided the same day on
# the operator's observation that clients will run Ergane against Azure DevOps and
# other forges, not only GitHub.
#
# Refined against the tree at 4ce493d. Every anchor in plan.md was read by hand at
# that commit; 034-ergane-init/US3 (`init --wire`, 4ce493d) is in the base and is
# NOT reverted — US4 draws the seam around it. D-046 lands as PR #110 and will be
# on the branch before any story here dispatches.
#
# Six stories, chained rather than fanned out, and both halves of that are
# deliberate.
#
# Chained, on evidence from this same day rather than on caution. 034/US3 and
# US4 were correctly modelled as independent and ran concurrently; each
# introduced a module-level `_gh_client_factory` in `factory/cli/init.py` with a
# different signature. Different regions of the file, so there was no textual
# conflict, so the rebase kept both — the second shadowed the first and nine
# tests died. It cost a rework cycle, and it produced an assertion that had
# become unfalsifiable by merge. US1 of this spec edits that exact seam, and
# US2/US3 both edit `mergequeue/models.py`. Wall time is cheap here; a silent
# collision on code no agent has a second reading of is not.
#
# Six, because the coupling is concentrated in four modules but they are large
# (gh.py 484, wiring.py 505, merge_activities.py 798, onboard.py 473), and this
# repo refuses any diff over 61,440 bytes deterministically
# (`factory/verify/diffbounds.py:38`). A single "introduce the seam" story would
# be refused before a judge ever read it.
#
# Every acceptance scenario is decidable from the story's diff alone (constitution
# principle VIII / D-037). "Works against Azure DevOps" appears nowhere as a
# criterion; the seam's honesty is proven by a conformance suite that enrols every
# registered forge and by a fake forge that is a model of a repository rather than
# a call recorder.
---

# Feature Specification: 049-forge-seam

## Context

GitHub is not a dependency of this factory. It is an *assumption*, and the
assumption is load-bearing at the earliest possible moment: `EpicWorkflow`
calls `_onboard_target` (`factory/workgraph/workflow.py:833`) before
`resolve_graph`, before a key is issued, before a worktree exists. A failing
profile fails the epic there. The judgment behind that gate,
`factory/mergequeue/onboard.py::evaluate_repo:95`, is written in GitHub's own
vocabulary: the repository must be **public** (D-007,
`onboard.py:174`), a **merge queue** must be enabled on the default branch
(`:190`), `squash_merge_commit_title` must be `PR_TITLE` (`:225`, D-041), and
every declared gate must appear as a **required status check** (`:255`). A
target on Azure DevOps fails that gate not because it is unready but because
the questions do not apply to it.

The coupling is concentrated rather than diffuse, which is what makes this
tractable. Three modules carry the surface — `factory/mergequeue/gh.py` (the
only place `gh` is spawned), `factory/mergequeue/wiring.py` (034/US3's writes),
`factory/activities/merge_activities.py` (the landing activities) — and
`factory/mergequeue/onboard.py` holds the judgment. Two facts checked at
4ce493d make it cheaper than it looks:

- **`EpicWorkflow`'s code names no GitHub fact.** It consumes
  `TargetRepoProfile.passed` and its findings and nothing else; a search for
  GitHub vocabulary in `factory/workgraph/workflow.py` returns only prose (the
  comment at `:663` and the docstring at `:837`). No workflow change is implied,
  and workflow changes are where this repository's replay defects come from.
- **The client is already a parameter in three places.**
  `onboard_target_repo(client, target_repo)`
  (`factory/activities/merge_activities.py:589`) takes a client rather than
  constructing one, and three modules already hold a construction seam:
  `_client_factory` (`merge_activities.py:296`), `_onboard_client_factory`
  (`factory/workgraph/cli.py:70`), and `_gh_client_factory`
  (`factory/cli/init.py:80`). Some of the seam exists by accident — but all three
  name `GhClient` concretely, so what exists is a *client*-construction seam, not
  a forge seam.

**Renaming is not seaming.** A `Forge` protocol whose methods are
`merge_queue_enabled()` and `squash_merge_commit_title()` has moved the coupling,
not removed it. The central work of this spec is deciding what the forge-neutral
questions *are*, and the reasoning is part of the deliverable.

## What the factory actually needs from a forge

Three things, and everything else is one forge's spelling: it must **propose a
change**, have that change **gated on evidence it can name**, and **land it
without a human**. Six questions follow, five of them asked at readiness and one
asked at every poll.

**Q1 — Reachability and identity.** Can the factory reach this repository on its
forge, and by what name does the forge know it? A repository the factory cannot
read is never dispatchable, whatever else is true of it. (Today: `gh repo view`
→ `nameWithOwner`; an unreadable repo yields the `repo_read` finding at
`merge_activities.py:764`.)

**Q2 — Gated landing.** Will the forge refuse to land a change into the landing
branch until a set of *named* checks passes? The word carrying the weight is
**named**: the factory's verification contract is that the gates its manifest
declares are the gates the forge runs, and that claim is only checkable if the
checks are addressable by name.

**Q3 — Landing without a human.** Once those checks pass, will the forge
complete the merge on its own? The factory has no human in the loop by
construction (D-024); a forge that needs a click at the end is a forge it cannot
land through.

**Q4 — Check parity.** Is the set of checks the forge will require *exactly* the
set of gates the manifest declares — no declared gate left unrequired, and no
required check the factory does not control? This is the one question
`evaluate_repo` already asks neutrally, and it is the structural form of
"deterministic gates only" (D-008): a required check that is not a declared gate
is the door through which an LLM judge could become CI.

**Q5 — A readable landing.** Will the commit the forge writes when it lands
carry the proposal's title verbatim? This is what `squash_merge_commit_title:
PR_TITLE` was really asking. The delta reader parses `<epic>/<node>: US<n>` off
the landed subject (`factory/workgraph/landed.py:38`), and its `(?:\(#\d+\))?`
group already makes GitHub's PR-number suffix optional — **the reader is already
forge-tolerant; only the setting was GitHub-shaped.**

**Q6 — Is this proposal in conflict with its target?** Asked at every poll, not
at readiness. `classify` — "the only place a poll becomes a decision", pure by
constitution IV — reads `snapshot.merge_state_status == "DIRTY"`
(`factory/mergequeue/classify.py:74`), which is GitHub's `mergeStateStatus`
vocabulary sitting inside the deterministic core. The neutral fact is a boolean:
the forge reports conflict, the classifier decides what it means.

### Two things that are not forge questions, and must stop pretending to be

**Repository visibility belongs to GitHub.** "The repo must be public because
the merge queue is available on any plan only for public repos" (D-007) is a
GitHub *billing* constraint sitting inside a universal readiness check. It is
not wrong and it is not dropped — it is GitHub's own answer to Q2/Q3, and after
this spec it is authored by the GitHub implementation, where it is true, instead
of by the shared judgment, where it is parochial. A forge with no notion of
repository visibility is judged without it and can pass.

It moves, but it does not soften. It stays a **failing** finding carrying its
remedy verbatim, for two reasons. D-007 is not advice: private-on-Free *cannot
ever* enqueue, so the operator faces a real choice with two real answers — make
the repository public, or move to a plan whose queue covers private ones — and
the remedy is the actionable half of the finding. And an advisory finding is a
finding nobody acts on; downgrading it would convert a hard refusal into a line
of report text, which is how a repository comes to fail every epic start on a
check somebody once decided was informational.

**Manifest validity and 034's local facts are properties of a tree and a host.**
`factory_yaml`, `runtime_root_ignored`, `runtime_root_migration`,
`registry_entry`, `landing_branch` and `control_plane` (`onboard.py:209`,
`:310`, `:347`, `:383`, `:415`) are already forge-independent. The seam must not
drag them across it, and `tests/test_ergane_init_check.py:441` exists to notice
if something tries.

---

### User Story 1 - Onboarding reads the repository through a forge, not through `gh` (Priority: P1)

As the factory, I gather a target repository's readiness facts through a named
forge that I resolve, not by spawning `gh`. The `github` forge is today's
`GhClient` behind that interface with no behavioural change: a GitHub target
produces the same `TargetRepoProfile`, finding for finding, detail for detail.

**Scope fence**: this story moves *where the facts come from*. It does not
re-ask the questions — `evaluate_repo`'s findings stay byte-identical, which is
what makes the move checkable. Re-asking them is US2, deliberately separated so
that the design act arrives in a diff small enough to read.

**Why this priority**: every other story in this spec sits on this interface,
and it is the cheapest it will ever be — the facts `evaluate_repo` needs are
already gathered in one function (`merge_activities.py:589`) through an already
injectable client.

**Independent Test**: resolve the `github` forge against a scripted `gh` and
confirm the profile is unchanged from today's; resolve a fake forge backed by an
in-memory repository model and confirm the same `evaluate_repo` judges it.

**Evidence rule for every scenario in this spec**: the judge is given the diff
and these criteria — never a terminal, never the base tree (constitution VIII).
Any runtime claim is met by tool output pasted verbatim into a committed file.

**Acceptance Scenarios**:

1. **Given** the forge interface, **When** the diff is inspected, **Then** it
   declares exactly the operations this spec names and no others, and no
   operation on it classifies an outcome, decides a verdict, retries, or settles
   anything — proven by a committed test that reads the protocol's own members.
2. **Given** the `github` forge resolved against a scripted `gh`, **When** the
   existing onboarding suite runs, **Then** it passes with no assertion changed
   to accommodate the seam — the diff shows the expected findings untouched.
3. **Given** a fake forge that is a *model of a repository* — reads served from
   mutable state, writes changing it — configured as a repository that fails
   readiness, **When** `evaluate_repo` judges it, **Then** it fails; and when the
   model is changed to satisfy the questions, the same judgment passes it. The
   fake is never asserted on by call log alone, and it is not built on
   `tests/fake_gh.py`, whose defect is filed as
   `ci/the-scripted-gh-fake-never-consumes-an-expectation`.
4. **Given** a forge name nothing is registered under, **When** it is resolved,
   **Then** resolution raises rather than defaulting — a deployment that asked
   for one forge and silently got another would land somewhere nobody looked.
5. **Given** the diff, **When** `pyproject.toml` is read, **Then** it declares no
   new dependency (constitution III).

---

### User Story 2 - The readiness questions are forge-neutral, and D-007 belongs to GitHub (Priority: P1)

As the factory, I ask a repository the five readiness questions above in terms
no forge owns, and I let each forge answer in its own terms. GitHub's answer to
"can this repository gate and land automatically" still includes "it must be
public", and that finding is now authored by the GitHub implementation rather
than by the shared judgment.

**Why this priority**: this is the story that decides whether the seam is real.
Without it US1 has relocated GitHub's vocabulary behind an interface, which is
the failure mode D-046 §3 names explicitly.

**Independent Test**: judge a fake forge that models a repository with gated,
autonomous landing, exact check parity and a proposal-titled landing subject —
and *no concept of visibility at all* — and confirm it passes readiness; judge
today's GitHub facts and confirm today's verdicts.

**Acceptance Scenarios**:

1. **Given** a forge reporting a repository that gates landing on named checks,
   lands without a human, requires exactly the declared gates, and titles the
   landing commit from the proposal — and that reports no visibility fact
   whatsoever — **When** `evaluate_repo` judges it, **Then** the profile passes,
   proven by a committed test.
2. **Given** the GitHub forge and a private repository, **When** the profile is
   built, **Then** it still fails with a finding naming D-007 and the same
   remedy an operator reads today, and the diff shows that finding authored in
   the GitHub implementation rather than in the shared judgment.
3. **Given** the diff, **When** `factory/mergequeue/onboard.py` is read, **Then**
   the shared judgment names no merge queue, no repository visibility, and no
   `squash_merge_commit_title` — proven by a committed test that reads the
   module's source, so a later edit cannot quietly reintroduce them.
4. **Given** a forge that gates on named checks but will not complete the merge
   without a human, **When** the profile is built, **Then** it fails with a
   finding distinct from the gating finding — Q2 and Q3 are separately
   answerable and separately actionable.
5. **Given** the diff, **When** `tests/test_ergane_init_check.py`'s sole-author
   guard runs, **Then** it still passes: `gate_check:` / `unknown_check:` and
   034's local facts remain authored only by the shared judgment.

---

### User Story 3 - The landing path proposes, lands and observes through the forge (Priority: P1)

As the factory, I open a proposal, ask the forge to land it, poll it, withdraw
it and fetch its failing-check evidence through the forge — never by naming
`gh`. `EpicWorkflow` does not change.

**Why this priority**: this is the half of the coupling that runs on every
landing, and it is where a second forge's differences are loudest. It is also
where the pure classifier still speaks GitHub. It depends on US1's protocol and
on nothing else — the landing path and the readiness path are disjoint module
sets (`classify.py` and the landing activities versus `onboard.py`), so this
story and US2 move at the same time.

**Independent Test**: drive one landing's whole life — find, open, request
landing, observe merged, observe rejected, withdraw — against the fake forge,
and confirm the workflow-visible records are the ones the classifier already
consumes.

**Acceptance Scenarios**:

1. **Given** the landing activities, **When** the diff is inspected, **Then**
   none of them constructs a `GhClient` or names `gh`, and the existing landing
   suite passes with no assertion changed — proven by a committed test.
2. **Given** a proposal whose target has moved under it, **When** the forge
   reports it in conflict, **Then** `classify` returns `CONFLICT` from a
   forge-neutral fact and not from the string `"DIRTY"` — proven by a committed
   test, and by a second test asserting `factory/mergequeue/classify.py`'s source
   contains no forge-native status literal.
3. **Given** a `PrSnapshot` recorded before this spec, **When** it is
   deserialized, **Then** it loads unchanged and classifies as it did — every
   field this story adds carries a default, because these records cross the
   Temporal payload boundary and sit in workflow histories.
4. **Given** the diff, **When** `factory/workgraph/workflow.py` is read, **Then**
   no line of its code changed — proven by a committed test asserting the
   epic workflow imports and calls exactly what it does today.
5. **Given** the forge, **When** the merge-surface structural guards run,
   **Then** they still hold: no path requests branch deletion, no push is
   forced, and the only merge form in source is the automatic one.

---

### User Story 4 - Wiring a repository is a forge operation (Priority: P2)

As an operator running `ergane init --wire`, I wire whichever forge my
repository is on. 034/US3's GitHub rulesets work is not reverted: it becomes the
`github` forge's implementation of "make this repository satisfy the readiness
questions", and a forge that cannot wire refuses with manual steps rather than
half-applying a change.

**Why this priority**: it is the operator-facing half of the same seam, and it is
lower than US1–US3 because a target can always be wired by hand. It sits after
US2, not US3: scenario 1 judges the mutated model with the *same* `evaluate_repo`
that guards dispatch, and that assertion only means anything once US2 has made
that judgment forge-neutral. It has no dependency on the landing path, which is
the other half of the seam and moves in parallel.

**Independent Test**: run the wiring operation against the fake repository model
and confirm the factory's *own reader* then passes it — the same round trip
`tests/test_ergane_init_wiring.py:348` already performs.

**Acceptance Scenarios**:

1. **Given** a fake repository model that fails readiness, **When** the forge's
   wiring operation runs against it, **Then** the same `evaluate_repo` that
   guards dispatch judges the mutated model and passes it — the assertion is on
   the model's judged state, never on the call log.
2. **Given** a repository already wired, **When** the operation runs again,
   **Then** it reports every act as already satisfied and issues no mutating
   call — proven by a committed test asserting an empty mutation list *against
   the repository model*. It may not be proven through `tests/fake_gh.py`: that
   fake answers every call from the first matching expectation forever, so a
   second identical command is unreachable and an idempotence claim tested
   through it cannot fail
   (`ci/the-scripted-gh-fake-never-consumes-an-expectation`).
3. **Given** a forge whose credentials cannot change repository settings,
   **When** wiring runs, **Then** it refuses before any write, carrying the
   by-hand steps — proven by a committed test asserting nothing was mutated.
4. **Given** the diff, **When** `factory/cli/init.py` is read, **Then** `--wire`
   resolves a forge by name rather than constructing a `GhClient`, and the
   existing `--wire` suite passes with no assertion changed.

---

### User Story 5 - The forge is declared in the manifest, and an unknown forge is refused before dispatch (Priority: P2)

As an operator, I declare `forge: github` in my repository's manifest, because
which forge a repository is on is a property of that repository — the same kind
of fact as `landing_branch` and `gates`, which are manifest keys for exactly
that reason. Absent, the value is `github`, so every repository that exists
today is unaffected.

This is deliberately *not* where 041 put its transport choice, and the asymmetry
is the point. A messenger is a property of the operator's host: one operator,
one Telegram, many repositories — so it belongs in the control-plane file.
Forges run the other way: one host, many repositories, possibly on different
forges at once. A control-plane forge key would make the engine able to serve
only one forge at a time, which is the constraint this spec exists to remove.

**Scope fence, and it is the sharp one**: this story teaches the manifest loader
the key. It **must not** add the key to *this* repository's own `ergane.yaml`.
The config gate parses a node's manifest with the **worker's installed parser**,
not the worktree's, so a diff that both teaches the key and uses it is rejected
at `CONFIG_ERROR` in 0.0s before any gate command runs. 020/US1 died four times
proving this (`ergane.yaml:38-45`). The key becomes usable here only after this
story lands and an operator restarts the worker.

**Why this priority**: without it the forge is resolved by a default and the
seam has no selector, which is half a seam. It is P2 because the default is
correct for every target that exists.

**Independent Test**: load a fixture manifest declaring a known forge and
confirm it parses; load one declaring an unknown forge and confirm it is refused
with the registered names listed; load one declaring nothing and confirm the
value is `github`.

**Acceptance Scenarios**:

1. **Given** a fixture manifest declaring `forge: github`, **When** it is loaded,
   **Then** it parses and the resolved forge name is `github` — proven by a
   committed test.
2. **Given** a fixture manifest declaring a forge no builder is registered under,
   **When** it is loaded, **Then** it is refused with a message naming the
   registered forges — never a silent fallback to the default.
3. **Given** a fixture manifest declaring no forge, **When** it is loaded,
   **Then** the value is `github` and every existing manifest fixture in the
   suite parses unchanged — proven by a committed test.
4. **Given** the diff, **When** this repository's own `ergane.yaml` is read,
   **Then** it is untouched — the story that teaches the parser a key never also
   spends it.

---

### User Story 6 - The seam cannot silently re-leak (Priority: P3)

As a future implementer, I cannot reintroduce a forge-native concept outside the
forge's own implementation without a test telling me. A protocol with one
implementation and no guard erodes back into a direct call within a quarter.

**Why this priority**: it prevents regression rather than delivering behaviour,
and it can only be written once every consumer has moved. If it is never built
the seam still works — it just stops being true over time.

**Independent Test**: add a forge-native term to a module outside the forge
implementation and confirm the sweep fails; remove it and confirm it passes.

**Acceptance Scenarios**:

1. **Given** the sweep, **When** it runs over the shipped package, **Then**
   forge-native vocabulary appears only in the modules an explicit path
   allowlist names, and the allowlist is by path rather than by count — proven
   by a committed test.
2. **Given** the sweep, **When** its own coverage is checked, **Then** it asserts
   that the file list it read is non-empty and contains the forge implementation
   — the anti-vacuity guard, without which a sweep that read nothing passes
   forever (`tests/test_final_sweep.py:644` is the precedent).
3. **Given** the merge-surface structural guards, **When** the swept module set
   is read, **Then** every forge module is in it *without any path having been
   added to the swept set by this spec* — proven by a committed test asserting
   the guards' file list contains them, because the guards are scoped to
   `factory/mergequeue/` and anything outside it escapes them silently.
4. **Given** the diff, **When** the shipped package is swept for the vocabulary
   `tests/test_final_sweep.py:462` reserves, **Then** nothing this spec adds
   spells any of it — a forge operation named for what a forge *does to* a
   merge would fail that sweep on the word alone.

---

## Functional Requirements

- **FR-001**: A forge interface MUST express what the factory needs from a
  forge, and nothing else. No operation on it may classify an outcome, decide a
  verdict, retry, settle, or judge; every such decision stays factory-side, as
  `factory/notify/adapter.py:134` keeps them for the messenger seam.
- **FR-002**: Forges MUST be selectable by name through a registry, with
  `github` as the value when nothing names one, and an unregistered name MUST
  raise rather than fall back to the default.
- **FR-003**: The `github` forge MUST be the reference implementation and MUST
  keep this repository's own landing path working unchanged — same commands,
  same findings, same PR bodies. A seam that requires re-provisioning this
  repository is a failed seam.
- **FR-004**: The test-side fake forge MUST be a model of a repository — reads
  served from mutable state, changed only by writes the factory actually issued
  — and the factory's own reader MUST be what judges it. It MUST NOT be built on
  `tests/fake_gh.py`, and MUST NOT copy its shape: that fake is the open finding
  `ci/the-scripted-gh-fake-never-consumes-an-expectation`, and a fake that only
  records calls makes every test that uses it vacuous.
- **FR-005**: The conformance suite that asserts the interface's shape MUST be
  parametrized over *every registered forge*, so a forge added later is enrolled
  by existing rather than by remembering. It refuses to inherit 041's shape for
  a reason on the ledger: `ci/the-adapter-conformance-suite-is-a-hardcoded-list-
  of-one` records that the messenger seam's three conformance tests are
  parametrized over the literal `["telegram"]`, so a second adapter would ship
  having never been conformance-checked at all.
- **FR-006**: The shared readiness judgment MUST ask the forge-neutral questions
  Q1–Q5 above and MUST NOT name a merge queue, a repository visibility, or a
  squash-title setting.
- **FR-007**: A forge implementation MAY contribute additional findings of its
  own; the GitHub implementation MUST contribute the D-007 visibility finding,
  with the same remedy an operator reads today.
- **FR-008**: Checks that are properties of a repository's tree or the
  operator's host — manifest validity, runtime-root hygiene, registry entry,
  landing branch, control-plane readiness — MUST remain authored by the shared
  judgment and MUST NOT move behind the seam.
- **FR-009**: The landing activities MUST propose, request landing, observe,
  withdraw and fetch failing-check evidence through the forge, and MUST NOT
  construct a forge-native client.
- **FR-010**: The poll record MUST carry a forge-neutral conflict fact, and the
  classifier MUST decide `CONFLICT` from it rather than from a forge-native
  status string. Every field added to a record that crosses the Temporal payload
  boundary MUST carry a default so stored histories deserialize unchanged.
- **FR-011**: `factory/workgraph/workflow.py` MUST NOT change. If an
  implementer believes it must, that belief is a spec defect and must be raised
  rather than acted on.
- **FR-012**: Making a repository satisfy the readiness questions MUST be a
  forge operation; 034/US3's rulesets work becomes the GitHub implementation of
  it and MUST NOT be reverted or rewritten.
- **FR-013**: A forge that cannot apply a policy MUST refuse before any write,
  carrying the by-hand steps, so a repository is never left half-wired.
- **FR-014**: The repository manifest MUST accept an optional `forge` key whose
  absence means `github`; an unknown value MUST be refused by the loader with
  the registered names listed.
- **FR-015**: The story that teaches the manifest loader the `forge` key MUST
  NOT add that key to this repository's own manifest.
- **FR-016**: A sweep MUST hold forge-native vocabulary to an explicit path
  allowlist, and MUST assert its own coverage so a sweep that read nothing
  cannot pass.
- **FR-017**: The forge's modules MUST live inside `factory/mergequeue/`, so
  that the merge-surface structural guards cover them by construction rather
  than by an added entry — no path requests branch deletion, no push is forced,
  and the only merge form in source is the automatic one. Those guards were
  earned by incidents; a prettier package path is not worth trading three
  safety properties for, and "we will widen the sweep" is a promise the next
  implementer inherits rather than a property the tree holds.
- **FR-018**: This spec MUST NOT add a new dependency — package, service or
  tool (constitution III).

## Success Criteria

- **SC-001**: This repository's own epic start — `EpicWorkflow._onboard_target`
  against `bryantharpeorg/ergane` — reaches the same **verdict** after this spec
  as before it, asking every question it asked before, in the same reading
  order, with no question dropped and no new failure. Two renames and one split
  are expected and are not regressions: `merge_queue` → `gated_landing`,
  `squash_title` → `landing_title`, and Q2's "gates a landing" separated from
  Q3's "lands without a human" (US2-S4, FR-006). Measured:

  ```
  before: visibility, merge_queue, factory_yaml, squash_title, gate_check:test
  after:  visibility, gated_landing, autonomous_landing, factory_yaml,
          landing_title, gate_check:test
  ```

  This criterion previously read "finding for finding", which US2-S4 could not
  satisfy and no correct implementation could: US2-S4 mandates a finding that
  "finding for finding" forbids. Repaired 2026-08-16 before US6 was dispatched,
  because acceptance criteria snapshot into an attempt prompt at dispatch and a
  self-contradicting criterion is an argument an implementer cannot win. What
  SC-001 was defending — that a refactor must not silently change what this
  repository's own onboarding decides — is unchanged and is what the wording
  above now states.
- **SC-002**: A repository model with no concept of visibility, no merge queue
  and no squash-title setting, but which gates landing on named checks matching
  its declared gates and lands without a human, passes readiness.
- **SC-003**: **Control.** The same model with its gating removed fails
  readiness — establishing that the neutral question decides an outcome rather
  than the case having been impossible either way.
- **SC-004**: `factory/workgraph/workflow.py` is byte-identical across the epic.
- **SC-005**: The interface's conformance suite runs against every registered
  forge, and adding a registration enrols it with no test edit.
- **SC-006**: The full suite passes with the existing merge-queue, onboarding,
  landing, `init --check` and `init --wire` fixtures unchanged.

## Out of Scope

- **An Azure DevOps implementation.** This spec draws the seam and proves it
  with a fake; it does not ship a second forge. A thin second implementation was
  considered and rejected: written speculatively it would encode a guess about
  ADO's API that nobody can check, and its tests would fake ADO exactly as the
  fake forge already fakes a repository — the same evidence at twice the cost.
  What makes the seam honest here is FR-004 (the fake is a repository, not a
  recorder) and FR-005 (conformance enrols every registration). Build the ADO
  forge when a real ADO target exists to check it against.
- **Renaming the landed records.** `PrSnapshot`, `Landing`, `QueueOutcome` and
  `LandingState` keep their names. "Pull request" is shared vocabulary — Azure
  DevOps calls them pull requests too — and the landed-identifier rule in
  `CONTEXT.md` applies. The seam's hard edge is around *landing policy*, not
  around proposals.
- **Moving the stores, the registry, or anything 043 touched.**
- **Any change to what the judge is asked, or to the ladder.**
- **Retiring `factory/mergequeue/gh.py`.** It stays as the GitHub forge's
  subprocess layer; the seam sits above it, not through it.
- **Fixing `tests/fake_gh.py`.** Its non-consuming match loop is an open
  finding (`ci/the-scripted-gh-fake-never-consumes-an-expectation`) touching
  seven test modules, and repairing it would silently change what those
  modules assert — a large, unrelated blast radius inside an epic whose whole
  claim is that nothing observable changed. This spec must not *build on* it
  (FR-004) and must not *fix* it; it is its own piece of work.
- **A second home for the forge outside `factory/mergequeue/`.** Settled by
  FR-017: the merge-surface structural guards are scoped to that directory and
  were earned by incidents, so the forge lives where they already reach.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-018]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-009, FR-010, FR-011]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-012, FR-013]
US5:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-014, FR-015]
US6:
  depends_on: []
  depends_on_merged: [US2, US3, US4, US5]
  implements: [FR-016, FR-017]
```
