---
state: landed
# Attested landed 2026-08-29 by the away-mode loop. US1 3c8fef805fed (#368),
# US2 0190ab010fee (#369), US3 b5bffad16d4d (#370) — all three observed on
# ergane-buildout, merged 2026-08-27 11:02 PM through 2026-08-28 12:36 AM CT.
#
# THE STORIES LANDED. THE LIVE TIER IS NOT GREEN, AND THIS ATTESTATION SAYS SO
# RATHER THAN IMPLYING OTHERWISE. A gate run on 2026-08-29 from a shell with
# `scripts/ergane-env.sh` eval'd still produced 12 live-tier failures — 7 setup
# errors across `tests/test_live_judge.py` and 5 failures in
# `tests/test_live_epic.py` — reproduced at the parent commit, so they predate
# anything this morning did. Against the 19 setup errors this spec was written
# from, that is a real reduction and not a fix.
#
# The remainder is tracked, not lost: `ci/live-tier-fails-on-missing-spend-log-rows`
# (warning, open, 3 occurrences — the judge half, "no spend-log row appeared for
# the judge's key within 90s") and
# `live-tier/epic-smoke-cannot-onboard-its-own-fixture` (critical, open). Neither
# was re-verified by running the tier during this loop, because
# `tests/test_live_epic.py` dispatches a real epic and epic-089 was landing.
#
# Attesting is therefore a claim about the three stories, not about the tier.
# Anyone reading this to answer "is the live smoke green" should run it, not
# read this line.
#
# DRAFTED 2026-08-27 by the operator session, against ergane-buildout at ba9be75.
# Every file:line below was read from that commit, and every claim about what
# onboarding does was reproduced offline before drafting rather than inferred.
#
# WHY THIS EXISTS, WITH THE RECEIPT. On 2026-08-27 a full gate of ba9be75, run
# from a shell with `scripts/ergane-env.sh` eval'd, produced 19 errors:
#
#   1 failed, 5068 passed, 9 skipped, 19 errors in 584.83s
#
# All 19 were setup errors in the live tier. Twelve of them — every test in
# `tests/test_live_epic.py` — died on one message:
#
#   temporalio.exceptions.ApplicationError: GRAPH_INVALID: target repo
#   /tmp/.../target-repo failed onboarding; nothing dispatches against an
#   unvalidated repo:
#     [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED):
#            no git remotes found
#     [FAIL] factory_yaml: manifest failed to load: .../factory.yaml:
#            [runtime] declares `runtime: 'python:3.11-bookworm'`; the
#            supported backend is `bwrap`
#
# The same commit, gated from a shell WITHOUT that environment, is green:
# 5047 passed, 50 skipped, exit 0. Neither run is wrong. The live tier simply
# does not exist in the cheaper one, and the cheaper one is what CI runs.
#
# THE TWO BLOCKERS ARE INDEPENDENT AND BOTH ARE OLD.
#   - `manifest_source` (tests/test_live_epic.py:300-312) has emitted
#     `runtime: python:3.11-bookworm` unchanged since the repository's first
#     commit e915296 (2026-08-06). `_read_runtime`
#     (factory/verify/factory_yaml.py:294-300) began refusing anything outside
#     `SUPPORTED_BACKENDS` in 8b768e6, "011-agent-sandbox/us2" (2026-08-15).
#     329 commits have landed since.
#   - `build_scratch_repo` (tests/test_live_epic.py:506-530) creates the target
#     repo with `git init` and no remote, so the forge read refuses GH_REFUSED
#     before the manifest is reached. The onboarding gate that makes that fatal
#     landed in cc3a5e2, "003 us3 T042-T043" (2026-08-06) — the day after the
#     last recorded green live-epic run.
#
# THE REMEDY IS PROVEN, NOT PROPOSED. Both halves were reproduced and then
# cleared offline on 2026-08-27, in about two seconds, with no proxy, no agent
# and no Temporal server — by importing the smoke's own `build_scratch_repo`
# and calling the real `onboard_target_repo`. Rewriting the manifest's runtime
# to `bwrap` cleared `factory_yaml`; filtering the remainder through the real
# `_is_landing_only_check` (factory/workgraph/workflow.py:373-377) cleared
# `repo_read`, because a forge read is a landing check and this smoke never
# lands. Zero failures remained. `plan.md` carries the transcript.
#
# THAT OFFLINE REPRODUCTION IS ALSO THE SECOND STORY. It cost nothing, it needs
# nothing the default suite does not already have, and it would have gone red on
# 2026-08-15 the moment the backend list tightened. Its absence is why twelve
# days passed.
#
# WHAT THE OTHER SEVEN ERRORS WERE, AND WHY THEY ARE NOT IN SCOPE. The seven
# `tests/test_live_judge.py` errors have a different cause: a real judge call
# completes, and then no spend-log row appears for its key within 90s
# (tests/test_live_judge.py:348). That is a property of the operator's LiteLLM
# deployment, not of this repository — the test is behaving correctly by
# refusing to pass without attribution. It is tracked as
# `ci/live-tier-fails-on-missing-spend-log-rows` and belongs to the operator.
# A story here that "fixed" it would be a story that weakened an assertion.
#
# NOT IN SCOPE. This spec does not run a live epic in CI, does not add a live
# tier to the merge-group build, does not change what any live test asserts, and
# does not touch the judge's spend-log requirement. It makes the live epic smoke
# able to start, makes the cheap tier notice when it stops being able to, and
# makes a tier that did not run say so.
---

# Feature Specification: the live smoke runs, or the suite says why

**Created**: 2026-08-27
**Depends on**: nothing. US1 → US2 are sequential because US2 asserts on the
manifest US1 corrects; US3 is independent of both.

## The gap, stated precisely

This repository's most expensive claim is that a spec goes in and merged,
verified code comes out. Exactly one test proves the whole of it against the
real world — `tests/test_live_epic.py`, whose module docstring names four
beliefs that "have no other test": that the agent invocation is real, that the
session transcript still lands where the adapter archives it from, that a
registered worker serves every activity, and that the ledger row, verification
row and salvage commit agree attempt for attempt when the numbers come from a
proxy rather than a fake.

That test has been unable to start since **2026-08-15** at the latest, and
plausibly since 2026-08-06. Nothing reported it, for two compounding reasons:

1. The tier is invisible unless the operator's environment is loaded.
   `live_config` (`tests/test_live_epic.py:366-372`) skips when `LITELLM_PROXY_URL`
   and `LITELLM_MASTER_KEY` are absent, and `scripts/gate-commit` inherits the
   caller's shell. The same tree gates green or red depending on which terminal
   you typed in.
2. Nothing cheap checks the expensive test's own inputs. Whether the smoke's
   scratch repository still satisfies onboarding is decidable offline in
   seconds, and nothing decided it.

A skip is reported identically to a pass. `50 skipped` says nothing about
*which* fifty, and the operator reading it has no way to tell a suite that
exercised the factory end to end from one that did not try.

## The rule this spec is asking for

**The end-to-end smoke can start; the cheap tier proves it can still start; and
a run that did not exercise a live tier says which one and what would have run
it.**

### What this spec is not

It is not an attempt to run live tests in CI — they cost model time and need
credentials CI does not hold, and that is the right arrangement. It does not
weaken a single live assertion; the judge's insistence on a spend-log row stays
exactly as strict as it is today. And it adds no new live test: the subject is
the ones that already exist.

## User Scenarios & Testing

### User Story 1 - The smoke's own repository onboards (Priority: P1)

As the live-epic smoke, I dispatch against a scratch repository the factory is
willing to accept, so my twelve assertions run instead of erroring at setup.

**Why this priority**: P1 and first. Until this is true nothing else in the tier
executes, and the other stories are about keeping a thing working that does not
currently work.

**Independent Test**: build the smoke's scratch repository, run the real
onboarding over it, and read back the findings — no proxy, no agent, no server.

**Acceptance Scenarios**:

1. **Given** the smoke's scratch repository, **When** onboarding runs over it,
   **Then** the `factory_yaml` finding passes — proven by a committed test that
   builds the repository and calls the real manifest loader, so the check that
   the manifest is loadable is itself pinned rather than assumed.
2. **Given** the manifest, **When** it names its sandbox backend, **Then** the
   name is taken from `SUPPORTED_BACKENDS` (`factory/verify/factory_yaml.py:90`)
   rather than restated as a literal, so the next tightening of that tuple fails
   where it is made instead of twelve days later at dispatch.
3. **Given** a scratch repository with no git remote, **When** the smoke
   dispatches, **Then** the forge-dependent `repo_read` finding does not
   disqualify it, because the smoke never opens a proposal and never lands —
   and a committed test asserts the epic is dispatched in the halting mode that
   makes that true, rather than asserting it indirectly through a green run.
4. **Given** the smoke dispatched that way, **When** its node reaches PASSED,
   **Then** every assertion the module already makes still holds — the attempt's
   salvage commit is on the branch, the branch outlives the worktree, and the
   worktree is swept — so this story changes what the smoke can start, never
   what it proves.

### User Story 2 - The cheap tier notices when the expensive one breaks (Priority: P1)

As the default `uv run pytest -q`, I check that every live module's scratch
repository would still onboard, so a tightened rule fails on the day it lands.

**Why this priority**: P1. US1 fixes the instance; this is what stops the class.
The check costs no credentials, no network and no model time — the entire reason
the defect survived twelve days is that nobody had written the two-second
version of the ten-minute test.

**Independent Test**: run the new module on its own with no environment loaded
at all and watch it pass; then break a live module's manifest and watch it fail.

**Acceptance Scenarios**:

1. **Given** no `LITELLM_PROXY_URL`, no `LITELLM_MASTER_KEY`, no Temporal server
   and no network, **When** the new check runs, **Then** it executes rather than
   skipping — a check that skips under the same conditions as the test it
   guards is not a guard.
2. **Given** a live module's scratch repository, **When** the check runs
   onboarding over it and filters the findings the way that module's dispatch
   does, **Then** no failure remains — and the assertion reports the surviving
   findings by name, because "passed is False" would not have told anyone which
   of the two blockers to fix.
3. **Given** a `tests/test_live_*.py` module that hand-authors a repository
   manifest from a literal in its own source, **When** the check enumerates what
   it covers, **Then** that module is covered — proven by a guard that fails when
   such a module is not in the covered set. Enumerating by hand is how a fourth
   live module arrives uncovered while the suite stays green. A module whose
   manifest is *generated* by `ergane init` is outside the rule and must not be
   demanded by the guard: writer and reader are the same code there, so it cannot
   drift the way a literal can.
4. **Given** the corrected manifest from US1, **When** its runtime is reverted to
   the refused value in a scratch copy, **Then** the check fails and its message
   names the runtime and the supported backend. A guard never observed failing on
   the defect it was written for is a guard nobody has reason to trust.

### User Story 3 - A tier that did not run says so (Priority: P2)

As a suite run, I state which live tiers I did not exercise and what would have
exercised them, so a green line stops being ambiguous.

**Why this priority**: P2. It prevents nothing on its own — US2 is the check —
but it is what makes the absence legible to the person reading the output, and
this repository already has a name for that shape: a result that names its own
consequence rather than falling silent.

**Independent Test**: run the suite with no live environment and read the
summary; then run it with the environment loaded and read it again.

**Acceptance Scenarios**:

1. **Given** a run in which no live tier executed, **When** the suite finishes,
   **Then** the summary names each registered live marker that did not run and
   the condition that would have run it, drawn from the marker's own registration
   in `pyproject.toml:81-88` rather than from a second list that can drift.
2. **Given** a run in which a live tier did execute, **When** the suite finishes,
   **Then** that tier is reported as having run, so the report distinguishes the
   two cases rather than only announcing absence.
3. **Given** the report, **When** it is emitted, **Then** it appears on every
   run including a fully green one — a notice that appears only on failure is a
   notice nobody reads on the day it matters.
4. **Given** the report, **When** the suite is invoked in a way that captures
   output for a machine, **Then** the report does not change any exit status and
   does not fail a run. Its job is to describe, and a describer that can fail a
   build acquires a second job it was not designed for.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
```

US2 asserts on the manifest US1 corrects, so it waits for it. US3 touches
`tests/conftest.py` and nothing US1 or US2 owns, so it is concurrent with both.

## Requirements (summary — numbered at refinement)

The smoke's manifest names a supported backend, sourced from the code's own
tuple; the smoke dispatches in halting mode, because it has no forge and never
lands, and the forge-dependent onboarding finding is a landing check; the
smoke's existing assertions are unchanged; an offline check runs the real
onboarding over every live module's scratch repository, under the same finding
filter that module dispatches with, and fails naming the surviving findings; a
guard proves the covered set includes every manifest-writing live module; and a
terminal summary names every live marker that did or did not run, and what
would run it.

## Success Criteria (summary)

Pasted: the offline onboarding transcript before and after the fix, showing both
findings and then none; the new check failing on a reverted runtime with the
backend named; the summary block from a run with no live environment and from
one with it; and the full-suite before-and-after counts.

**Operator verification, which is the point of the spec**: with the environment
loaded, run `-m live_epic` and watch a real agent turn a red check green. The
gate can prove the smoke starts. Only a run can prove it still finishes, and the
whole reason this spec exists is that twelve days of green gates proved neither.
