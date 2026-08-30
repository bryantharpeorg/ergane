# Attempt report — US3: a deterministic ref conflict escalates instead of killing the epic

## What changed

- `factory/workgraph/worktree.py` — `is_non_fast_forward` (the classifier, anchored on
  git's own per-ref status line) and `ref_conflict_remedy` (the clearing command).
  `_push_refusal` appends the command to the refusal it already worded, for that one cause
  and no other.
- `factory/activities/merge_activities.py` — `LANDING_REF_CONFLICT`, raised non-retryably
  ahead of the retryable `PUSH_FAILED` catch-all, classified on `WorktreeError.stderr`.
- `factory/workgraph/workflow.py` — `_open_landing` (the one push both landing paths now
  make) and `_escalate_ref_conflict` (page, then act). One hand-granted re-push.

## T022 — the three confirmations this task asks for

**1. Every other push failure keeps today's retryable path (FR-009).** The carve-out is a
single `if` in front of the existing raise, so an unrecognised stderr falls through to
`ApplicationError(str(exc), type=PUSH_FAILED)` unchanged. Held by three tests that fail if
the class is widened: a real remote rejection that is *not* a non-fast-forward
(`pre-receive hook declined`) still crossing the activity as retryable `PUSH_FAILED`; the
classifier answering False for seven unclassifiable stderrs, including the phrase in prose
and the phrase inside a ref name; and a workflow-level control asserting a `PUSH_FAILED`
still spends its three attempts and pages nobody.

**2. No force push was added anywhere in this epic.**

```
$ git diff 8e77243..HEAD -- factory/ | grep -cE "^\+.*--force"
0
```

`tests/test_mergequeue_sweep.py::test_no_command_module_pushes_with_force` scans every
command module and is green. It caught this attempt once — an early docstring quoted the
forbidden flag by name while explaining why never to use it — and the docstring was
reworded rather than the guard scoped.

**3. No archive ref is deleted anywhere in this epic.** The only ref deletion the epic adds
is US1's `push --quiet <remote> --delete <node branch>`, guarded by `_archive_holding`'s
reachability check, and the only line the epic removes that mentions both "archive" and
"delete" is a docstring sentence about the *sidecar*:

```
$ git diff 8e77243..HEAD | grep -E "^-.*archive" | grep -E "delete|-d "
-    directory, archives the node branch, and deletes the sidecar.  Idempotent:
```

US3 itself deletes nothing: it classifies a failure, names a command for a human to run,
and routes the node to a question.

## T023 — the demonstration

**What I could not run, and why.** The plan's demonstration is `ergane build start` twice
around a kill. This attempt's sandbox has no LLM gateway, so no dispatched node could run
an agent:

```
$ uv run ergane doctor
ergane doctor: orphaned-key: skipped (proxy not answering) (proxy is not answering: no LLM
gateway endpoint is available: set LITELLM_PROXY_URL in the environment ...)
```

Beyond the credential, a live dispatch would run the worker against factory code this
attempt is editing and push node branches to the operator's real GitHub remote. That is an
operator's action, not a node's, so I did not attempt it. **The three observations the
demonstration turns on are reproduced below** against real git and a real remote, driven
through the same functions the epic dispatches (`ensure`, `push_branch`, `worktree.reset`),
with the pre-spec teardown emulated locally so the "before" half is real too. What this
does not exercise is Temporal, the agent, the judge and the merge queue.

```
=== 1. an epic was killed with its node branch already on origin ===

$ git ls-remote origin 'refs/heads/factory/*'
bf8d17a47bc2cffd04a33c84bf404e1483095fd4	refs/heads/factory/100-demo/us1

=== 2. BEFORE: the re-dispatch pushes, and git refuses it ===

$ what the operator now reads (US2 FR-005, US3 FR-008)
push of 'factory/100-demo/us1' to origin failed (repo /tmp/tmp2ywweh0i/clone): ! [rejected]        factory/100-demo/us1 -> factory/100-demo/us1 (non-fast-forward)
git said:
To /tmp/tmp2ywweh0i/origin.git
 ! [rejected]        factory/100-demo/us1 -> factory/100-demo/us1 (non-fast-forward)
error: failed to push some refs to '/tmp/tmp2ywweh0i/origin.git'
hint: Updates were rejected because a pushed branch tip is behind its remote
hint: counterpart. If you want to integrate the remote changes, use 'git pull'
hint: before pushing again.
hint: See the 'Note about fast-forwards' in 'git push --help' for details.
clear the stale ref with: git push --delete origin factory/100-demo/us1 — confirm first that the refused tip is reachable from an archive ref, and never force-push over it

is_non_fast_forward(stderr) -> True
activity error type      -> LANDING_REF_CONFLICT (was PUSH_FAILED)
non_retryable            -> True

=== 3. AFTER: the kill's teardown clears origin (US1) ===

$ ergane teardown (worktree.reset)
committed dirty state
removed worktree
archived branch
deleted origin branch factory/100-demo/us1 at bf8d17a47bc2 (kept as refs/heads/archive/factory/100-demo/us1/bf8d17a47bc2, here and on origin)

$ git ls-remote origin 'refs/heads/factory/*'   # expect: empty
(no output)

$ git ls-remote origin 'refs/heads/archive/*'   # expect: the salvage
bf8d17a47bc2cffd04a33c84bf404e1483095fd4	refs/heads/archive/factory/100-demo/us1/bf8d17a47bc2

=== 4. the second dispatch pushes, and lands ===

push_branch(...) -> 9e8bccb62e0b
$ git ls-remote origin 'refs/heads/factory/*'
9e8bccb62e0b4812b7d282b4877f1f3a6b329ae2	refs/heads/factory/100-demo/us1
```

The empty `ls-remote` in step 3 is the evidence, and step 4 is the claim: before this spec
that push is refused *after* the node has passed verification, which is what made the
defect expensive. US3's own half is step 2 — the same refusal now arrives named,
classified, non-retryable, and carrying the command that clears it.

## Trap 7 — the sibling cascade, verified rather than assumed

The plan says to check the cascade rather than assume escalation stops it. It does stop it,
and the mechanism is that `_lock_out_dependents` runs from `_reap_finished` only once a
node's coroutine has *ended*: a node parked on an open page has not ended, so no PENDING
dependent is touched while the operator decides. Asserted from inside `send_escalation` —
the merge-gated sibling is `PENDING` at the moment the page goes out — rather than from a
final status, which cannot tell a sibling that survived from one that was killed and
recreated. After a granted re-push the whole graph merges. No finding to report.

What is *not* claimed: an operator who answers `KILL` still locks out the dependents of the
node they killed. That is their decision arriving through a page, which is the whole
difference this story makes.

## Gate

```
$ uv run pytest tests/test_100_ref_conflict_escalates.py -v
tests/test_100_ref_conflict_escalates.py::test_a_non_fast_forward_push_fails_non_retryably PASSED
tests/test_100_ref_conflict_escalates.py::test_the_node_escalates_rather_than_terminating PASSED
tests/test_100_ref_conflict_escalates.py::test_the_escalation_names_the_ref_the_reason_and_the_command PASSED
tests/test_100_ref_conflict_escalates.py::test_a_push_refused_for_another_reason_stays_retryable PASSED
tests/test_100_ref_conflict_escalates.py::test_an_unclassifiable_stderr_falls_back_to_the_retryable_path PASSED
tests/test_100_ref_conflict_escalates.py::test_an_ordinary_push_failure_still_retries_and_pages_nobody PASSED
tests/test_100_ref_conflict_escalates.py::test_no_pending_sibling_is_killed_when_a_node_escalates PASSED
tests/test_100_ref_conflict_escalates.py::test_the_epic_is_not_stopped_by_one_nodes_ref_conflict PASSED
============================== 8 passed in 2.81s ===============================

$ uv run pytest -q
5288 passed, 58 skipped, 7 warnings in 377.95s (0:06:17)
```

Two guards owned by earlier stories moved with the code rather than being relaxed, and both
still fail on the edit they were written to catch: `test_both_landing_call_sites_leave_the_
base_to_the_one_resolution_path` now holds `_land` and `_reenqueue` to reaching the single
push path (107's claim, expressed over the shape US3 gave it), and the workflow imports pin
in `test_forge_landing.py` declares the error type the workflow routes on. The seam fence
those tests exist for — no forge module imported into workflow code — is untouched.
