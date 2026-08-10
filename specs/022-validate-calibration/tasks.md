# Tasks: 022 — `spec validate` calibration

One story, one file. Work test-first and commit once per task. Read `plan.md`'s
traps before the first edit; trap 1 and trap 2 are the two ways this goes wrong.

## Tests first

- [ ] **T001** [US1-S1] In `tests/test_ergane_spec.py`, change
  `test_validate_reports_uncovered_scenario_ids` (currently at `:445`) to
  assert `result.code == 0` while keeping its existing assertion that `US1-S2`
  appears in the output. This is a landed test asserting the contract this
  spec replaces — see trap 2. It fails until T006.

- [ ] **T002** [US1-S3] Confirm `test_validate_reports_missing_tasks_file`
  (currently at `:500`) still asserts exit 1, and add a comment naming why it
  is exempt: a spec with no task list is a structural defect, not a convention
  gap. Do not change its assertions. See trap 1.

- [ ] **T003** [US1-S5] Strengthen
  `test_validate_scenario_coverage_passes_when_all_referenced` (currently at
  `:473`) so it cannot pass against a deleted check: assert that a fixture with
  a deliberate gap still prints its uncovered ids, alongside the existing
  all-referenced case that exits 0 and prints the success line. See trap 3.

- [ ] **T004** [US1-S4] Add a test for a spec carrying a frontmatter defect and
  uncovered scenarios at once: both findings printed, exit 1. This is the test
  that proves severity decides the verdict rather than finding count.

- [ ] **T005** [US1-S2] Add a test asserting the `--json` document carries a
  severity for each finding, that `spec_dir`, `checked` and the `layer` and
  `message` keys are unchanged, and that finding order is preserved. See trap 4.

## Implementation

- [ ] **T006** [US1-S1] Give `_ValidateFinding` (`factory/cli/nouns/spec.py:216`)
  a severity attribute with a default that keeps all eight existing
  construction sites as refusals, then pass the advisory severity from the
  uncovered-ids site at `spec.py:410` only — not from the missing-file site at
  `spec.py:398`. Satisfies FR-001, FR-003, FR-004, FR-005.

- [ ] **T007** [US1-S4] Replace the exit rule at `spec.py:288` so it returns
  `EXIT_USER` when any refusal finding is present and `EXIT_OK` otherwise.
  Satisfies FR-002.

- [ ] **T008** [US1-S1] Make an advisory read differently from a refusal in the
  human output at `spec.py:279-282`, keeping both on stderr. Satisfies FR-006,
  and trap 5 says why the stream does not change.

- [ ] **T009** [US1-S5] Resolve what prints when the command exits 0 with
  advisories present — the if/elif at `spec.py:279-286` cannot currently reach
  both branches. A reader must be able to tell that the command found something
  and passed anyway. See trap 6.

- [ ] **T010** [US1-S2] Add the severity to each finding dict at
  `spec.py:271-274`, changing nothing else about the document. Satisfies FR-007.

## Verification

- [ ] **T011** [US1-S6] Run the corpus proof from `plan.md` over every
  directory in `specs/`. Every spec whose only findings are uncovered scenarios
  must exit 0 with its ids still printed on stderr; any spec with a
  frontmatter, derivation or persona defect must still exit 1. Record the
  before and after counts in your notes — seventeen specs exit 1 today.

- [ ] **T012** Confirm `ergane spec validate specs/022-validate-calibration`
  reports no uncovered scenarios, because every scenario id this spec declares
  is referenced by a task above. Satisfies FR-008 and makes this spec the first
  in the corpus to pass its own check.

- [ ] **T013** Final gate command passes green: `uv run pytest -q`.
