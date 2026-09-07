# 130-US3 — the detector carries no language-shaped list

Committed evidence for epic 130's T019. Every line below is pasted tool output
from a run in this worktree; nothing is described that was not printed. A live
multi-language target is an operator step (plan trap 13); this node's evidence
is the transcript of tests it wrote and ran, plus the grep T019 names.

## What this story changed

`factory/workgraph/detector.py` no longer defines `EXCLUDED_DIR_NAMES`,
`EXCLUDED_SUFFIXES` or `_snapshot_paths` (US3-S1, FR-006). Epic 130 US2 stopped
the runtime-root walk from visiting node worktrees at all, which left
`_snapshot_paths` — the only consumer of the two constants — unreferenced;
plan trap 10 kept all three in place for this story. After US2 the detector
looks in exactly two places: the three named evidence stores at the runtime
root, and the target repository, where `_tracked_state` reads untracked files
with git's `--exclude-standard` in the target. There is nothing left for a list
to prune, so the diff deletes rather than replaces: no `.gitignore` parser, no
`git check-ignore` call, no new dependency (trap 8). What to leave out of a
snapshot in someone else's repository is that repository's statement, made
through git's own ignore machinery, read in the target.

The `Iterator` import goes with `_snapshot_paths`, its last user. The module
docstring and the two comments that named the constant — in
`factory/activities/roadmap_activities.py` and `tests/test_090_refusal_parks_the_spec.py`
— are updated in the same diff (trap 12). Nothing else in `factory/` referenced
any of the three names.

## T015 observed red, before T018

The removal has to earn its test. With the pre-T018 `factory/workgraph/detector.py`
checked out (commit `61c40db`, the test-first commit), the T015 test fails on
the first name it checks:

Command: `uv run pytest
tests/test_us3_no_language_shaped_list.py::test_detector_defines_no_generated_path_exclusion_list -q`
against `61c40db`'s detector:

```text
F                                                                        [100%]
=================================== FAILURES ===================================
____________ test_detector_defines_no_generated_path_exclusion_list ____________

    def test_detector_defines_no_generated_path_exclusion_list() -> None:
        """US3-S1 / FR-006: the names are gone from the module, and nothing replaced them.

        Written first and observed red against the pre-story module, which still
        defined all three names — US2 left them unreferenced on purpose (plan
        trap 10), and this is the test the removal has to earn.
        """
        import factory.workgraph.detector as detector

        defined = set(vars(detector))
        for name in ("EXCLUDED_DIR_NAMES", "EXCLUDED_SUFFIXES", "_snapshot_paths"):
>           assert name not in defined, (
                f"{name} is a language-shaped list in the detector; FR-006 removed it "
                "and it must not come back"
            )
E           AssertionError: EXCLUDED_DIR_NAMES is a language-shaped list in the detector; FR-006 removed it and it must not come back
E           assert 'EXCLUDED_DIR_NAMES' not in {'Any', 'AttemptContext', 'CATEGORY', 'DetectorError', 'EXCLUDED_DIR_NAMES', 'EXCLUDED_SUFFIXES', ...}

tests/test_us3_no_language_shaped_list.py:194: AssertionError
================================== live tiers ==================================
live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
live_epic       did not run — runs when Tier 1 env is set
live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
=========================== short test summary info ============================
FAILED tests/test_us3_no_language_shaped_list.py::test_detector_defines_no_generated_path_exclusion_list
1 failed in 0.11s
```

T016 and T017, by contrast, are the controls and were **green before the
story** — the task says so, and trying to make them fail first would have been
the shortest path to the ignore-rule parser trap 8 forbids. Their pre-story
green state is part of the record: run at `61c40db` (tests present, detector
unchanged), `tests/test_us3_no_language_shaped_list.py` read `1 failed, 3
passed` — the failure being T015, and the two controls passing against the
module that still carried the list.

## T015 earned green through the removal; the controls stayed green

After T018 — the two constants, `_snapshot_paths` and the `Iterator` import
removed, the module docstring and the two naming comments updated:

Command: `uv run pytest tests/test_us3_no_language_shaped_list.py
tests/test_detector_reports_removals_only.py tests/test_us2_own_worktree_only.py
tests/test_detector_keys_on_the_class.py tests/test_us1_detector.py
tests/test_090_refusal_parks_the_spec.py -q`

```text
............................                                             [100%]
================================== live tiers ==================================
live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
live_epic       did not run — runs when Tier 1 env is set
live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
28 passed in 72.33s (0:01:12)
```

Per-test, from the same four detector files:

Command: `uv run pytest tests/test_us3_no_language_shaped_list.py
tests/test_detector_reports_removals_only.py tests/test_us2_own_worktree_only.py
tests/test_detector_keys_on_the_class.py -v`

```text
tests/test_us3_no_language_shaped_list.py::test_detector_defines_no_generated_path_exclusion_list PASSED [  5%]
tests/test_us3_no_language_shaped_list.py::test_no_ignore_rule_parser_dependency_was_added PASSED [ 11%]
tests/test_us3_no_language_shaped_list.py::test_target_ignoring_generated_dir_keeps_writes_silent PASSED [ 16%]
tests/test_us3_no_language_shaped_list.py::test_target_not_ignoring_generated_dir_files_a_finding PASSED [ 22%]
tests/test_detector_reports_removals_only.py::test_sibling_worktree_gaining_files_files_no_finding PASSED [ 27%]
tests/test_detector_reports_removals_only.py::test_sibling_worktree_removed_files_no_finding PASSED [ 33%]
tests/test_detector_reports_removals_only.py::test_truncated_evidence_store_files_a_finding_naming_it PASSED [ 38%]
tests/test_detector_reports_removals_only.py::test_growing_evidence_store_files_no_finding PASSED [ 44%]
tests/test_detector_reports_removals_only.py::test_modified_tracked_path_still_files_a_finding PASSED [ 50%]
tests/test_us2_own_worktree_only.py::test_sibling_worktree_written_to_files_no_finding PASSED [ 55%]
tests/test_us2_own_worktree_only.py::test_genuine_escape_files_critical_and_names_no_sibling PASSED [ 61%]
tests/test_us2_own_worktree_only.py::test_genuine_escape_store_truncation_files_critical PASSED [ 66%]
tests/test_us2_own_worktree_only.py::test_compare_and_report_return_gates_nothing_at_both_call_sites PASSED [ 72%]
tests/test_us2_own_worktree_only.py::test_deleted_runtime_root_still_files_naming_the_stores PASSED [ 77%]
tests/test_detector_keys_on_the_class.py::test_two_nodes_violating_the_boundary_file_one_row_with_two_occurrences PASSED [ 83%]
tests/test_detector_keys_on_the_class.py::test_the_row_names_the_epic_and_node_of_the_attempt_that_filed_it PASSED [ 88%]
tests/test_detector_keys_on_the_class.py::test_an_attempt_over_the_bound_is_truncated_with_a_remainder_count PASSED [ 94%]
tests/test_detector_keys_on_the_class.py::test_an_attempt_under_the_bound_names_every_path_and_says_nothing_more PASSED [100%]
============================== 18 passed in 0.51s ==============================
```

`test_detector_reports_removals_only.py` and `test_us2_own_worktree_only.py`
are the controls this story must not take with it (US3-S2: the surviving
mechanism is green before the story and must stay green through the removal),
and `test_detector_keys_on_the_class.py` pins 073-US5's bounded evidence. All
stayed green.

## The full gate

Command: `uv run pytest -q`

```text
5736 passed, 58 skipped, 11 warnings in 503.19s (0:08:23)
```

One earlier full-gate run showed a single failure in
`tests/test_roadmap_prompt_assembly.py::test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it`,
which passes 3/3 in isolation and in a rerun of its whole file plus
`test_roadmap_scheduler.py` (41 passed), which drives a Temporal
`WorkflowEnvironment` and printed a gRPC `ConnectionRefused` retry to an
ephemeral port on the flaked run. None of that test's inputs are touched by
this story's diff, which is three removed names and two prose comments. The
rerun above is green.

## T019's grep — no definition remains

Command: `grep -rn "EXCLUDED_DIR_NAMES\|EXCLUDED_SUFFIXES" factory/`

```text
factory/workgraph/detector.py:24:  here: 073's ``EXCLUDED_DIR_NAMES``/``EXCLUDED_SUFFIXES`` pair was a
factory/activities/roadmap_activities.py:191:       boundary detector carried `EXCLUDED_DIR_NAMES` once and removed it
```

Both remaining hits are prose — the docstring sentence that records why the
list was removed (trap 12) and the comment in the roadmap activities that cites
it as the standing reminder of what a hand-written list costs, updated by T018
to say it was carried once and removed. There is no assignment or definition
left: `grep -rn "_snapshot_paths" factory/` returns nothing, and importing the
module shows `hasattr` false for all three names.

## What this story did not do

- It did not replace the list with an ignore-rule parser, a `git check-ignore`
  call, or a new dependency (FR-006, trap 8). The only surviving rule is git's
  `--exclude-standard`, applied by `_tracked_state` in the target repository.
- It did not read ergane's own `.gitignore`. The US3-S2 fixture's ignored
  directory is `node_modules/`, which this floor's own `.gitignore` does not
  cover — so a detector that read the host's rules would fail the control here
  rather than on a consumer's floor.
- It did not touch the other 130 stories' files beyond the two naming comments
  T018 assigns to it, and left every landed spec byte-identical.