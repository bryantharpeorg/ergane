# Tasks: 050-init-preconditions

Tests are written first and committed **red**, then made green. A test that has
never been observed to fail is not evidence — nine such tests were found in this
repository on 2026-08-16, five of them by the agents' own mutation batteries.

Every story ends with a mutation battery pasted verbatim into
`specs/050-init-preconditions/evidence/us<n>-mutations.md`. Before running a
battery, `git add -A`: a battery run against untracked files survives
`git checkout -- .` and silently contaminates every later run, which happened
here on 2026-08-16.

---

## Phase 1: User Story 1 — A schedule is never created into a control plane that is not there

### Tests for this story (write FIRST, must fail)

- **T001** A test that runs the full init path against a fake schedule backend
  and an unreadable control-plane config, and asserts **the backend holds no
  schedule**. Assert against the backend's state, never against a call log
  (US1-S1, plan trap 3).
- **T002** A test asserting the reported schedule line for that run names the
  control plane as the cause and `ergane install` as the remedy, in the same
  vocabulary `run_check` already uses (US1-S1, FR-003).
- **T003** A test asserting that in the same refused run, `ergane.yaml`, the
  `.gitignore` entry, `.ergane/` and the registry row are all written exactly as
  today (US1-S2, FR-004).
- **T004** A test asserting that with a readable control plane the schedule is
  created and its reported line is byte-identical to today's for identical
  inputs (US1-S3, FR-005). This is the test that stops the story being satisfied
  by removing scheduling — plan trap 2.
- **T005** A test driving a control plane that is configured but **unreachable**,
  asserting the step reports a failure and raises nothing (US1-S5, FR-002).
  Distinct from T001: not-configured and unreachable are different cases.
- **T006** A test asserting no test in this phase requires `TEMPORAL_ADDRESS` or
  reaches a real Temporal — the anti-vacuity guard for plan trap 4.

### Implementation for this story

- **T007** Compute the control-plane readability fact before the schedule step
  in `factory/cli/init.py`.
- **T008** Add the precondition branch to `_schedule` (`init.py:529`), returning
  a `ScheduleStep(FAILED, schedule_id_for(slug), <reason>)` — the shape the
  manifest-load failure at `:539-545` already uses. Do not raise (FR-002).
- **T009** Introduce the fake schedule backend seam if one does not already
  exist, so T001–T006 can run without a Temporal.
- **T010** Confirm no flag was added that disables scheduling (FR-010).

### Evidence for this story

- **T011** Run the `env -i` reproduction from the spec's Context against the
  built wheel and commit the transcript to
  `specs/050-init-preconditions/evidence/us1-reproduction.md` (SC-001).
- **T012** Mutation battery, including the mandatory one: delete the
  precondition and record which tests go red (US1-S4, SC-002).

---

## Phase 2: User Story 2 — Readiness is reported before the act that depends on it

### Tests for this story (write FIRST, must fail)

- **T013** A test capturing init's output for a run whose control plane cannot
  be read, asserting the control-plane verdict's **index** precedes the schedule
  line's index (US2-S1). Assert on position, not presence — plan trap 5.
- **T014** A test asserting that on a fully passing run the output still ends
  with the readiness report and still prints the `next, run:` guidance naming
  the paths to commit (US2-S2).
- **T015** A test asserting the control-plane probe is evaluated once per init
  run (US2-S3, FR-006).

### Implementation for this story

- **T016** Reorder so the control-plane verdict is emitted before the schedule
  step's line (FR-007).
- **T017** Share the single computed control-plane fact between the precondition
  and the readiness report (FR-006).

### Evidence for this story

- **T018** Mutation battery: restore the original ordering and confirm T013 goes
  red.

---

## Phase 3: User Story 3 — A schedule identity cannot collide with a stranger's

### Tests for this story (write FIRST, must fail)

- **T019** A test where a schedule already exists under the derived id, recorded
  against a **different** repository root: assert init refuses that step, names
  both roots, and leaves the existing schedule's state unchanged (US3-S1,
  FR-008).
- **T020** A test where the existing schedule's recorded root is the **same**
  repository: assert it reconciles exactly as today (US3-S2, plan trap 8).
- **T021** A test asserting the comparison reads a fact recorded on the schedule
  rather than local filesystem state (US3-S3, FR-009) — the anti-vacuity guard
  for this phase.

### Implementation for this story

- **T022** Record the repository root on the schedule in `desired_for_repo`, or
  read the equivalent fact it already carries.
- **T023** Add the identity comparison and its refusal to the schedule step.

### Evidence for this story

- **T024** Mutation battery: make the comparison read local state instead and
  confirm T021 goes red.

---

## Verification

- **T025** Full suite green in the worktree, final line pasted verbatim into the
  last commit. 44 skips is the expected baseline; a new skip is a finding.
- **T026** Diff measured the way `diffcheck` measures — scratch index,
  `git add -A`, `git diff --cached $(git merge-base HEAD origin/<landing>)` —
  against the merge-base, not the moving tip, and compared against
  `DIFF_INPUT_LIMIT` imported from `factory/verify/diffbounds.py` rather than a
  quoted number.
