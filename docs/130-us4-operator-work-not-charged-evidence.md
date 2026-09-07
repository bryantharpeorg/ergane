# 130-US4 — a finding names the repository, and the operator's own work is not it

Committed evidence for epic 130's T026. Every line below is pasted tool output
from a run in this worktree; nothing is described that was not printed. A live
operator commit in a target repository mid-attempt is the operator's step (plan
trap 13); this node's evidence is the transcript of tests it wrote and ran,
plus the spec diff proving the override touched only frontmatter comments.

## What this story changed

`factory/workgraph/detector.py` no longer takes different kinds of snapshot at
start and teardown. `capture_start` now records the *working tree* — the same
kind `compare_and_report` always took — so content present when the attempt
begins is recorded as seen and files nothing (US4-S1, FR-007). The snapshot
also records the target's HEAD, so a commit that moved HEAD during the attempt
is distinguished from a write: teardown content is compared against the tree
the new HEAD names, commit-carried paths file nothing, and a path the attempt
changed on top of the commit still files (US4-S2). A filed finding carries
`repo:<path>` in its refs and names the repository in its summary, from the
value the start snapshot already captured and the comparison used to drop
(US4-S3, FR-008).

The modified-tracked-path overlay in `_tracked_state` reads content with
`git hash-object` (read-only, no `-w`): `git diff-index --raw` prints an
all-zero sha for an unstaged modification, so two working-tree snapshots could
not otherwise agree on an untouched dirty tree — the operator's pre-existing
edit would have reappeared as a difference between two reads of the same
content.

011-US1 scenario 3's reporting half is reversed deliberately. The override is
recorded as `#` provenance lines inside that spec's frontmatter fence, in the
docstrings of both its committed controls (edited openly in this diff), and in
the commit message. Its scenario text, story titles, work-graph block and FR
bodies are byte-identical.

## Test transcript — the two edited controls and the escape control, in one run

T026 names three runs that must share one run: both edited 011 controls and the
escape control. Command: `uv run pytest tests/test_us4_operator_work_not_charged.py
tests/test_us1_detector.py::test_operator_work_is_reported_and_untouched
tests/test_us1_detector.py::test_detector_runs_on_completed_agent_error_timeout_and_killed -v`

```text
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 8 items

tests/test_us4_operator_work_not_charged.py::test_pre_existing_working_tree_content_files_no_finding PASSED [ 12%]
tests/test_us4_operator_work_not_charged.py::test_attempt_writing_on_top_of_pre_existing_dirt_still_files PASSED [ 25%]
tests/test_us4_operator_work_not_charged.py::test_operator_commit_is_silent_but_attempt_write_on_top_files PASSED [ 37%]
tests/test_us4_operator_work_not_charged.py::test_finding_names_the_target_repository PASSED [ 50%]
tests/test_us4_operator_work_not_charged.py::test_genuine_escape_files_with_evidence_intact PASSED [ 62%]
tests/test_us4_operator_work_not_charged.py::test_detector_leaves_the_operators_tree_byte_identical PASSED [ 75%]
tests/test_us1_detector.py::test_operator_work_is_reported_and_untouched PASSED [ 87%]
tests/test_us1_detector.py::test_detector_runs_on_completed_agent_error_timeout_and_killed PASSED [100%]
================================== live tiers ==================================

live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
live_epic       did not run — runs when Tier 1 env is set
live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
========================= 8 passed in 61.52s (0:01:01) =========================
```

## Both edited 011 controls and the full story's files, in one run

Command: `uv run pytest tests/test_us4_operator_work_not_charged.py
tests/test_us1_detector.py -v` (per-test lines; quiet tail below):

```text
tests/test_us4_operator_work_not_charged.py::test_pre_existing_working_tree_content_files_no_finding PASSED [  8%]
tests/test_us4_operator_work_not_charged.py::test_attempt_writing_on_top_of_pre_existing_dirt_still_files PASSED [ 16%]
tests/test_us4_operator_work_not_charged.py::test_operator_commit_is_silent_but_attempt_write_on_top_files PASSED [ 25%]
tests/test_us4_operator_work_not_charged.py::test_finding_names_the_target_repository PASSED [ 33%]
tests/test_us4_operator_work_not_charged.py::test_genuine_escape_files_with_evidence_intact PASSED [ 41%]
tests/test_us4_operator_work_not_charged.py::test_detector_leaves_the_operators_tree_byte_identical PASSED [ 50%]
tests/test_us1_detector.py::test_agent_modifying_tracked_file_in_target_repo_files_finding PASSED [ 58%]
tests/test_us1_detector.py::test_agent_writing_only_inside_worktree_files_nothing PASSED [ 66%]
tests/test_us1_detector.py::test_operator_work_is_reported_and_untouched PASSED [ 75%]
tests/test_us1_detector.py::test_detector_runs_on_completed_agent_error_timeout_and_killed PASSED [ 83%]
tests/test_us1_detector.py::test_agent_truncating_runtime_root_store_files_finding PASSED [ 91%]
tests/test_us1_detector.py::test_detector_reports_even_when_runtime_root_is_deleted PASSED [100%]
======================== 12 passed in 72.77s (0:01:12) =========================
```

## Written first, observed red

The three tests that earn their production change, observed red against the
pre-story module (fe24a5f's `factory/workgraph/detector.py`), each failing on
the exact clause it exists to enforce:

```text
>       assert finding is None, (
E       AssertionError: working-tree content present before capture_start must not be filed as this attempt's escape (FR-007)
E       assert Finding(key='hardening/agent-worktree-boundary', category='hardening', severity=<Severity.CRITICAL: 'critical'>, statu...t_seen='2026-09-07T11:01:49Z', last_seen='2026-09-07T11:01:49Z', promoted_spec=None, resolved_at=None, resolution=None) is None
tests/test_us4_operator_work_not_charged.py:142: AssertionError
        assert finding is not None, "the write on top of the commit must still file"
        assert finding.severity is Severity.CRITICAL
>       assert not named(finding, "operator_notes.md"), finding.summary
E       AssertionError: attempt 1 of 130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote/us4 modified 3 tracked path(s) and removed or truncated 0 runtime-root path(s): README.md, operator_notes.md, src/calc.py
E       assert not True
tests/test_us4_operator_work_not_charged.py:213: AssertionError
        assert finding is not None
>       assert f"repo:{repo}" in finding.refs, finding.refs
E       AssertionError: ['epic:130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote', 'node:us4', 'target:src/calc.py']
E       assert 'repo:/tmp/pytest-of-unknown/pytest-10/test_finding_names_the_target_0/passing' in ['epic:130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote', 'node:us4', 'target:src/calc.py']
tests/test_us4_operator_work_not_charged.py:246: AssertionError
FAILED tests/test_us4_operator_work_not_charged.py::test_pre_existing_working_tree_content_files_no_finding
FAILED tests/test_us4_operator_work_not_charged.py::test_operator_commit_is_silent_but_attempt_write_on_top_files
FAILED tests/test_us4_operator_work_not_charged.py::test_finding_names_the_target_repository
3 failed in 0.18s
```

The three controls (`test_attempt_writing_on_top_of_pre_existing_dirt_still_files`,
`test_genuine_escape_files_with_evidence_intact`,
`test_detector_leaves_the_operators_tree_byte_identical`) passed against the
pre-story module and pass against this one — they are the proof the exclusion
is a baseline and not a hole.

## The override did not reopen the landed story

`ergane spec derive specs/011-agent-sandbox --delta --target-repo $PWD -o
$(mktemp)` — the same check operator step 6 runs:

```text
nothing to build: all stories are already landed and unchanged
```

## The spec diff touched only frontmatter comments

`git diff specs/011-agent-sandbox/spec.md --stat`:

```text
 specs/011-agent-sandbox/spec.md | 20 ++++++++++++++++++++
 1 file changed, 20 insertions(+)
```

Every inserted line is a `#` comment inside the frontmatter fence (the full diff
is in the T026 commit and above in this file's history); nothing else moved —
the summary line `20 insertions(+)` with no deletions is the fingerprint
argument in one line.

## Sibling stories' suites, unbroken

The detector tests the three earlier stories added, run against this story's
detector:

```text
30 passed in 73.31s (0:01:13)
```

(`uv run pytest tests/test_us4_operator_work_not_charged.py
tests/test_us2_own_worktree_only.py tests/test_us3_no_language_shaped_list.py
tests/test_detector_reports_removals_only.py
tests/test_detector_keys_on_the_class.py tests/test_us1_detector.py -q`.)