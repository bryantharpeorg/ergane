# Tasks: the live smoke runs, or the suite says why

**Input**: `spec.md` and `plan.md` in this directory, both drafted 2026-08-27
against ergane-buildout at ba9be75.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch independent test functions. No `[P]` spans stories.

## Phase 1: User Story 1 — The smoke's own repository onboards

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001) Manifest-loads test, in a new
  `tests/test_114_us1_smoke_onboards.py`: build the smoke's scratch repository
  through `build_scratch_repo` (`tests/test_live_epic.py:506`) and load its
  manifest with the real `load_factory_config`. Assert it loads. This is the
  two-second version of the ten-minute test, and its absence is why the defect
  survived from 2026-08-15 to 2026-08-27.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001) Derived-backend test: assert the
  manifest's declared runtime is `SUPPORTED_BACKENDS[0]`
  (`factory/verify/factory_yaml.py:90`) read from the tuple at assertion time,
  not compared against the literal `"bwrap"`. A test that hardcodes the string
  passes for the same coincidental reason the fixture did (plan T2).
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) Halting-dispatch test: assert the
  `EpicInput` the smoke constructs (`tests/test_live_epic.py:606`) carries
  `halt_after_pass=True`. Assert on the constructed input, not on a run — the
  point is a check that costs nothing and therefore actually runs.
- [ ] T004 [P] [US1] (spec US1-S3, FR-002) Onboarding-clears test: run the real
  `onboard_target_repo` over the corrected scratch repository, filter through
  the real `_is_landing_only_check` (`factory/workgraph/workflow.py:374-378`),
  and assert no failure survives. The expected transcript is in `plan.md`
  § *The remedy, measured*; this task commits it as an assertion.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002) In `tests/test_live_epic.py`: interpolate
  `SUPPORTED_BACKENDS[0]` into `manifest_source` (`:298-312`) in place of
  `python:3.11-bookworm`, importing the tuple; add `halt_after_pass=True` to the
  `EpicInput` in `start` (`:599-618`).

### Verification for this story

- [ ] T006 [US1] (spec US1-S4, FR-003, SC-001) Paste into the PR: the offline
  onboarding transcript before and after, showing both findings and then none;
  the list of the twelve `tests/test_live_epic.py` test names, unmodified, with
  a statement that none of their assertions changed; and the full-suite
  before-and-after counts.

## Phase 2: User Story 2 — The cheap tier notices when the expensive one breaks

### Tests for this story (write FIRST, must fail)

- [ ] T007 [US2] (spec US2-S1, FR-004) Runs-without-credentials test, in a new
  `tests/test_114_us2_fixtures_onboard.py`: with `LITELLM_PROXY_URL`,
  `LITELLM_MASTER_KEY`, `TEMPORAL_ADDRESS` and `TEMPORAL_NAMESPACE` all removed
  from the environment, assert the new check executes and does not skip. A check
  that skips under the same conditions as the test it guards is not a guard
  (plan T4).
- [ ] T008 [P] [US2] (spec US2-S2, FR-005) Imported-predicate test: assert the
  new module resolves `_is_landing_only_check` by identity from
  `factory.workgraph.workflow` rather than restating the check names. Copying
  the four names and three prefixes is faster and is the thing this assertion
  exists to prevent (plan T3).
- [ ] T009 [P] [US2] (spec US2-S2, FR-006) Named-survivors test: drive the check
  against a scratch repository whose manifest is deliberately broken and assert
  the failure message contains the check name `factory_yaml` and the detail
  naming both the declared runtime and the supported backend. `assert
  profile.passed` would not have told anyone which of two blockers to fix.
- [ ] T010 [P] [US2] (spec US2-S4, FR-006) Reverted-runtime test: copy the
  corrected scratch repository, put `python:3.11-bookworm` back, and assert the
  check fails. This is the only task in the file that observes the guard failing
  on the defect it was written for.
- [ ] T011 [P] [US2] (spec US2-S3, FR-007) Coverage-guard test, two halves: add a
  throwaway module that hand-authors a manifest to the discovered set inside the
  test and assert the guard turns red for it; then assert the guard does **not**
  demand `tests/test_live_onramp.py`, whose manifest `ergane init` generates
  (`tests/test_live_onramp.py:687-694`) and which cannot be built offline at all.
  A guard that reports zero uncovered modules because its discovery found none is
  the vacuous sweep this repository has shipped before; a guard that demands the
  impossible gets relaxed within the hour (plan T5, FR-007).

### Implementation for this story

- [ ] T012 [US2] (FR-004, FR-005, FR-006, FR-007) Add
  `tests/test_114_us2_fixtures_onboard.py`: for each covered live module, build
  its scratch repository through that module's own builder, run the real
  `onboard_target_repo` (`factory/activities/merge_activities.py:612`), filter
  through the imported `_is_landing_only_check` when that module dispatches
  halting, assert no survivors and name any that remain; plus the coverage guard
  over `tests/test_live_*.py`.

### Verification for this story

- [ ] T013 [US2] (spec US2-S1, spec US2-S4, SC-002) Paste into the PR: the check
  passing with an emptied environment, the check failing on the reverted runtime
  with the backend named in its message, the coverage guard's covered and
  discovered sets, and the full-suite before-and-after counts.

## Phase 3: User Story 3 — A tier that did not run says so

### Tests for this story (write FIRST, must fail)

- [ ] T014 [US3] (spec US3-S1, FR-008) Absence-report test, in a new
  `tests/test_114_us3_live_tier_summary.py`: run a scratch session with no live
  environment and assert the summary names every live marker registered in
  `pyproject.toml:81-88` together with the condition that would have run it,
  with both strings derived from the registration rather than restated.
- [ ] T015 [P] [US3] (spec US3-S2, FR-008) Presence test: with a live-marked test
  made to run, assert the summary reports that tier as having run. A report that
  can only announce absence cannot distinguish the two cases.
- [ ] T016 [P] [US3] (spec US3-S3, FR-009) Always-emitted test: assert the report
  appears on a fully green run as well as on a red one. A notice that appears
  only on failure is a notice nobody reads on the day it matters.
- [ ] T017 [P] [US3] (spec US3-S4, FR-009) No-verdict test: assert the hook
  changes no exit status — a session that would exit 0 still exits 0 with every
  live tier absent. A describer that can fail a build has acquired a second job
  (plan T6).

### Implementation for this story

- [ ] T018 [US3] (FR-008, FR-009) Add a `pytest_terminal_summary` hook to
  `tests/conftest.py`, parsing marker name and condition out of the registered
  `markers` list at the `<name>: <description>` boundary, reading ran-or-not from
  the session's own reports, writing to the terminal reporter and returning
  without touching the exit status.

### Verification for this story

- [ ] T019 [US3] (spec US3-S1, spec US3-S2, SC-003) Paste into the PR: the
  summary block from a run with no live environment and from one with a live
  tier executing, and the full-suite before-and-after counts.

## What no task here can prove

Every task above runs offline, against scratch repositories and scripted
sessions. **None of them proves the live-epic smoke finishes**, because none of
them runs it — that needs a proxy, a `claude` on PATH, a Temporal server and
real model time, and the gate has none of those by design.

That proof is the operator verification in `plan.md`: with the environment
loaded, `uv run pytest -m live_epic -q`, and a real agent turning `check_greet`
green. Between 2026-08-15 and 2026-08-27 the gate was green every single day
while that test could not start. A spec that ends with another green gate and no
run would be the same evidence a third time.

One boundary this file will not blur: **the seven `tests/test_live_judge.py`
errors are not in scope.** Their cause is a missing spend-log row on the
operator's LiteLLM deployment (`tests/test_live_judge.py:348`), tracked as
`ci/live-tier-fails-on-missing-spend-log-rows`. The only way to turn them green
from inside this repository is to weaken an assertion that exists to prove
per-persona attribution, and no task here does that (plan T7).
