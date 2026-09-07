# 127-US1 — the record a killed node leaves: cause beside housekeeping

Committed evidence for epic 127's T010. Every line below is the printed output
of a real kill on a scratch remote: a real clone, a real bare `origin`, a real
refused push, and the factory's own code paths doing the work. Nothing is
described that was not printed.

## How this was produced

A scratch clone of this repository at `ergane-buildout` (`65fbf08`) with a bare
`origin` beside it, outside the worktree. On it, the exact sequence 126's plan
documents for a push refusal, driven by the factory's own functions:

1. `ensure` prepared the node worktree for `factory/127-t010-demo/us1`, the way
   dispatch does, and one commit of node work went onto the branch.
2. `push_branch` — the landing activity's own push — succeeded, leaving a tip
   on origin.
3. The branch was reset one commit and rebuilt with different work on the same
   file: the ancestry relationship a re-dispatch after a kill has, with none of
   the epic machinery.
4. `push_branch` again: git refused it non-fast-forward, and the factory raised
   the `WorktreeError` the activity would raise.
5. The activity's re-raise was composed over that error —
   `ApplicationError(str(exc), type=LANDING_REF_CONFLICT, non_retryable=True)
   from exc` — the cause chain the workflow actually walks.
6. `_failure_detail` (the workflow's own walk, `factory/workgraph/workflow.py`)
   was applied to it, and its answer stored on a record as
   `terminal_reason` — the line `_escalate_ref_conflict` writes at
   `workflow.py:3253`.
7. The kill path's archive-and-clear — the real
   `archive_and_clear_remote_branch` activity, against the real origin — ran,
   and its report was joined and stored as the *new* `housekeeping_report`
   field, the way both overwrite sites now write it (T009).

The printed record is what `epic_status` answers for such a node, and what
`ergane build status` renders from.

## The record (US1-S1, FR-001, FR-003)

```text
=== terminal record (what epic_status answers) ===
state:               KILLED
terminal_reason:     push of 'factory/127-t010-demo/us1' to origin failed (repo /tmp/127-t010/clone): ! [rejected]        factory/127-t010-demo/us1 -> factory/127-t010-demo/us1 (non-fast-forward)
git said:
To /tmp/127-t010/origin.git
 ! [rejected]        factory/127-t010-demo/us1 -> factory/127-t010-demo/us1 (non-fast-forward)
error: failed to push some refs to '/tmp/127-t010/origin.git'
hint: Updates were rejected because a pushed branch tip is behind its remote
hint: counterpart. If you want to integrate the remote changes, use 'git pull'
hint: before pushing again.
hint: See the 'Note about fast-forwards' in 'git push --help' for details.
clear the stale ref with: git push --delete origin factory/127-t010-demo/us1 — confirm first that the refused tip is reachable from an archive ref, and never force-push over it
housekeeping_report: archived branch; kept origin branch factory/127-t010-demo/us1 at 6e10759d806f: no archive ref of this node holds that commit, so nothing else carries its content (FR-002)
```

The cause is git's own: the rejection line, git's verdict, and the clearing
command — the whole account 100-US2 put there, still on the record after the
archive and clear ran. Beside it, in a field of its own, the housekeeping: the
branch was archived, and the live ref on origin was kept because no archive
ref of this node holds that commit.

## What the overwrite used to destroy

Before this story, the record the same sequence produced ended with the
housekeeping line in `terminal_reason`:

```text
terminal_reason:     archived branch; kept origin branch factory/127-t010-demo/us1 at e90efc39d1de: no archive ref of this node holds that commit, so nothing else carries its content (FR-002)
```

That is the defect: git's diagnosis of the refusal was gone from the record,
and what the operator read was the factory's tidy-up. The interpreter suite
could not see it happen — its archive stub answered `[]` unconditionally, so
`if report:` had never been true under it (plan trap 2). T005 gives the stub a
scriptable report and drives a non-empty one through the interpreter; T006
repoints 126's committed assertions, which read the report out of
`terminal_reason` and so pinned the defect as intended behaviour.

## Both overwrite sites

The kill path inside `_escalate_ref_conflict` — the one the findings file does
not name — reaches `_archive_and_clear_remote_branch` directly and never
`_close_out`. Both sites now write `housekeeping_report`; the T002 test drives
the ref-conflict path and the T004 test drives the `_close_out` path, each
with a non-empty report, and the pinned truth table holds on both. The
empty-report path is byte-identical to before: the `if report:` guard is
untouched, and a node with nothing to tidy reads exactly as it did.