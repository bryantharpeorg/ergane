# 130-US2 — the detector stops watching sibling worktrees

Committed evidence for epic 130's T014. Every line below is pasted tool output
from a run in this worktree; nothing is described that was not printed. A live
two-epic run is the operator's step (plan trap 13); this node's evidence is the
transcript of tests it wrote and ran, plus the spec diffs proving the override
touched only frontmatter comments.

## What this story changed

`factory/workgraph/detector.py` `_runtime_root_state` no longer walks
`<root>/worktrees/<epic>/<node>` at all — own or sibling. It snapshots the
three named evidence stores at the root (`doctor.db`, `ledger.db`,
`verification.db`) and nothing else under `worktrees/`. `_snapshot_paths` and
the two exclusion constants are left in place for US3 (plan trap 10); the
`own_worktree` parameter stays in the signature for US4, which shares the file.

Three committed scenarios are deliberately overridden by this story — 073-US4
scenario 2, the sibling-worktree half of 011-US1 scenario 5, and 011's FR-012
— because the factory itself removes sibling worktrees as ordinary
housekeeping (`factory/workgraph/workflow.py` `_remove_worktree`, called from
four workflow sites). The override is recorded in `#` provenance lines inside
each spec's frontmatter fence, in the inverting tests' docstrings, and in the
T009 commit message. Neither spec's scenario text, story titles, work-graph
block or FR bodies moved.

## Test transcript — the phase's files, T014

Command: `uv run pytest tests/test_detector_reports_removals_only.py
tests/test_us1_detector.py -q`

```text
================================== live tiers ==================================
live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
live_epic       did not run — runs when Tier 1 env is set
live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
11 passed in 72.37s (0:01:12)
```

Per-test outcomes from the same two files
(`uv run pytest <files> -v`, PASSED lines only):

```text
tests/test_detector_reports_removals_only.py::test_sibling_worktree_gaining_files_files_no_finding PASSED [  9%]
tests/test_detector_reports_removals_only.py::test_sibling_worktree_removed_files_no_finding PASSED [ 18%]
tests/test_detector_reports_removals_only.py::test_truncated_evidence_store_files_a_finding_naming_it PASSED [ 27%]
tests/test_detector_reports_removals_only.py::test_growing_evidence_store_files_no_finding PASSED [ 36%]
tests/test_detector_reports_removals_only.py::test_modified_tracked_path_still_files_a_finding PASSED [ 45%]
tests/test_us1_detector.py::test_agent_modifying_tracked_file_in_target_repo_files_finding PASSED [ 54%]
tests/test_us1_detector.py::test_agent_writing_only_inside_worktree_files_nothing PASSED [ 63%]
tests/test_us1_detector.py::test_operator_work_is_reported_and_untouched PASSED [ 72%]
tests/test_us1_detector.py::test_detector_runs_on_completed_agent_error_timeout_and_killed PASSED [ 81%]
tests/test_us1_detector.py::test_agent_truncating_runtime_root_store_files_finding PASSED [ 90%]
tests/test_us1_detector.py::test_detector_reports_even_when_runtime_root_is_deleted PASSED [100%]
```

Reading of that list against the tasks:

- **T009's inversion** — `test_sibling_worktree_removed_files_no_finding` —
  passes after T013; it was observed-red before it (its failure output is pasted
  under "Observed-red" below).
- **T010's unedited control** —
  `test_agent_modifying_tracked_file_in_target_repo_files_finding`
  (`tests/test_us1_detector.py:249`) — passes unedited.
- **T010's store half** — `test_agent_truncating_runtime_root_store_files_finding`
  (`tests/test_us1_detector.py:429`) — passes on its surviving halves
  (`doctor.db`, `ledger.db`, the read-only assertion); the sibling-worktree
  naming assertion was removed by T009 as the task directs.
- **T012's unedited control** —
  `test_detector_reports_even_when_runtime_root_is_deleted`
  (`tests/test_us1_detector.py:476`) — passes unedited.

This story's own new file, plus the other detector file
(`uv run pytest tests/test_us2_own_worktree_only.py
tests/test_detector_keys_on_the_class.py -q`):

```text
================================== live tiers ==================================
live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
live_epic       did not run — runs when Tier 1 env is set
live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
9 passed in 0.32s
```

Per-test outcomes from that same run:

```text
tests/test_us2_own_worktree_only.py::test_sibling_worktree_written_to_files_no_finding PASSED [ 11%]
tests/test_us2_own_worktree_only.py::test_genuine_escape_files_critical_and_names_no_sibling PASSED [ 22%]
tests/test_us2_own_worktree_only.py::test_genuine_escape_store_truncation_files_critical PASSED [ 33%]
tests/test_us2_own_worktree_only.py::test_compare_and_report_return_gates_nothing_at_both_call_sites PASSED [ 44%]
tests/test_us2_own_worktree_only.py::test_deleted_runtime_root_still_files_naming_the_stores PASSED [ 55%]
tests/test_detector_keys_on_the_class.py::test_two_nodes_violating_the_boundary_file_one_row_with_two_occurrences PASSED [ 66%]
tests/test_detector_keys_on_the_class.py::test_the_row_names_the_epic_and_node_of_the_attempt_that_filed_it PASSED [ 77%]
tests/test_detector_keys_on_the_class.py::test_an_attempt_over_the_bound_is_truncated_with_a_remainder_count PASSED [ 88%]
tests/test_detector_keys_on_the_class.py::test_an_attempt_under_the_bound_names_every_path_and_says_nothing_more PASSED [100%]
```

## The full gate (factory.yaml `test`)

Command: `uv run pytest -q`

```text
5732 passed, 58 skipped, 12 warnings in 509.11s (0:08:29)
```

## Observed-red: the override is real, not a deletion

Before T013, the two tests this story turns were failing against the unchanged
walk — the sibling was being charged (`runtime:worktrees/<epic>/us4` refs).
Pasted from the run at commit `47aa24d` (T010–T012 committed, T013 not yet):

```text
E       AssertionError: assert not ['runtime:worktrees/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote/us4', 'runtime:worktrees/130-t...e/us4/src', 'runtime:worktrees/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote/us4/src/sibling.py']
```

and the inverted 073 control, before T013:

```text
FAILED tests/test_detector_reports_removals_only.py::test_sibling_worktree_removed_files_no_finding
1 failed, 4 passed in 0.20s
```

## Spec diffs — the override lives in frontmatter comments only (trap 15)

`git diff b891e753cec0f590a9bca3831adf266ec1a5eae6 HEAD --
specs/073-the-ledger-triages-what-it-can-prove/spec.md`
(`b891e75` is the merge base with `ergane-buildout`):

```diff
diff --git a/specs/073-the-ledger-triages-what-it-can-prove/spec.md b/specs/073-the-ledger-triages-what-it-can-prove/spec.md
index 47f2e0b..52fef63 100644
--- a/specs/073-the-ledger-triages-what-it-can-prove/spec.md
+++ b/specs/073-the-ledger-triages-what-it-can-prove/spec.md
@@ -56,6 +56,20 @@ fixes:
 # (critical), filed the same morning from the same read.
 #
 # DO NOT FLIP READY without a pre-dispatch review.
+#
+# --- OVERRIDE, 2026-09-07, by epic 130 US2 (FR-005) ---
+# specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote
+# deliberately reverses US4 scenario 2 — "a sibling worktree is removed during
+# the attempt ... a finding is filed naming it ... the behaviour that must
+# survive". 073 did not know that the factory itself removes sibling worktrees
+# as ordinary housekeeping: `factory/workgraph/workflow.py` `_remove_worktree`
+# is called from four sites in the workflow, so this scenario's committed
+# control (`tests/test_detector_reports_removals_only.py`, now
+# `test_sibling_worktree_removed_files_no_finding`) fired on the factory's own
+# normal operation and charged it to whichever attempt happened to be tearing
+# down. The inversion lives in that test's docstring; the scenario text, story
+# titles, work-graph block and FR bodies here are fingerprint input and are
+# untouched by the override.
 ---
 
 # Feature Specification: the ledger triages what it can prove
```

`git diff b891e753cec0f590a9bca3831adf266ec1a5eae6 HEAD --
specs/011-agent-sandbox/spec.md`:

```diff
diff --git a/specs/011-agent-sandbox/spec.md b/specs/011-agent-sandbox/spec.md
index 00de9f9..53123cc 100644
--- a/specs/011-agent-sandbox/spec.md
+++ b/specs/011-agent-sandbox/spec.md
@@ -26,6 +26,21 @@ depends_on_landed: [043-runtime-root-integrity]
 #
 # Numbered 011 because F1 is an audit-triage finding and 011-014 are reserved
 # for those. 010 took the B-series; this takes the first F.
+#
+# --- OVERRIDE, 2026-09-07, by epic 130 US2 (FR-005) ---
+# specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote
+# deliberately reverses the sibling-worktree half of US1 scenario 5 (a removed
+# or truncated "sibling's worktree" files a critical) and the part of FR-012
+# that requires coverage of "every node worktree other than the attempt's own".
+# The factory itself removes sibling worktrees as ordinary housekeeping —
+# `factory/workgraph/workflow.py` `_remove_worktree`, called from four workflow
+# sites — so a sibling worktree is not evidence of an escape, and watching one
+# charged ordinary housekeeping to whichever attempt happened to be tearing
+# down. The evidence-store and ledger halves of scenario 5 and of FR-012 stand
+# exactly as written. The inversion lives in the docstring of
+# `tests/test_us1_detector.py::test_agent_truncating_runtime_root_store_files_finding`;
+# the scenario text, story titles, work-graph block and FR bodies here are
+# fingerprint input and are untouched by the override.
 ---
 
 # Feature Specification: The worktree is where the agent starts, not where it is kept
```

Every changed line in both diffs is an added `#` comment inside the frontmatter
fence; nothing is removed and no scenario, story title, work-graph line or FR
body moved.

## Scope notes

- No story here wires the detector's return into a verdict; T011's structural
  assertion (`test_compare_and_report_return_gates_nothing_at_both_call_sites`)
  pins both call sites as bare expression statements and stays green through
  the walk change (FR-010).
- `EXCLUDED_DIR_NAMES`, `EXCLUDED_SUFFIXES` and `_snapshot_paths` are left in
  `factory/workgraph/detector.py` untouched — they are US3's entire production
  diff (plan trap 10).
- The compiled `workgraph.json` in this spec directory is not in this diff; the
  operator's step 0 handles it before dispatch.