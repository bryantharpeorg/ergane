# Implementation Plan: a reset leaves nothing behind

**Spec**: `specs/100-a-reset-leaves-nothing-behind/spec.md`

Teardown learns about origin, the push stops suppressing its own diagnosis, and
one deterministic refusal moves out of the retryable class.

## What already exists, and where

Anchors below are file-and-symbol, not file-and-line, deliberately. Every line
number this section previously carried was wrong by between 16 and 70 lines
when checked against `origin/ergane-buildout` on 2026-08-30 — `:1369` was a
bare `"""`, `:368` was a `path =` assignment and `:336` was a function
parameter. Landings move this file constantly. Grep the symbol.

- **Teardown**: `reset` (`factory/workgraph/worktree.py`) — removes the
  directory, archives the node branch, deletes the sidecar. Its docstring is
  where the idempotence contract lives, including "every commit reachable from
  the old node branch remains reachable from an archive ref". `reset` calls
  `_archive_node` once; the rebuild path in `ensure` calls it at four more
  points, not three.
- **The archive contract**: `_archive_node` (same file) is the only writer, and
  renames rather than deletes — "the old branch is archived, never deleted
  (FR-004)". `archive_message` formats the message as
  `archive(<epic>/<node>): superseded at <tip12>`. The archive ref namespace is
  described in the standalone comment beginning "Naming the ref after what it
  points at makes the write idempotent".
- **The push**: `push_branch` (same file). It already carries a *refusal before
  git runs* — a worktree-ownership check added by 107-US2, with the comment
  above it explaining the R3 reasoning. The push itself is the lone
  `_git(repo, "push", "--quiet", remote, branch)` inside that function; note
  the file contains a second, unrelated `"push", "--quiet"` call that pushes a
  whole ref namespace, so match on the surrounding function rather than the
  string.
- **The failure classes and the precedent for US3**:
  `factory/activities/merge_activities.py` defines `PUSH_FAILED`. The comment
  block immediately below it is the argument US3 reuses verbatim in shape: an
  ownership refusal was carved out of `PUSH_FAILED` because "two repositories
  ... behind `PUSH_FAILED` would spend its three attempts arriving at the same"
  answer, explicitly leaving "today's retryable `PUSH_FAILED` path, untouched".
  The landing activity's docstring states which error is retryable and which is
  not — it names `LANDING_PUSH_REFUSED` as non-retryable — and is what US3
  updates.

## Traps

**Trap 1 — reachability is the safety property, not the branch name.** US1 must
delete a remote ref only when its tip is an ancestor of, or equal to, something
an archive ref holds. Deleting on the strength of "teardown ran, so an archive
exists" is not the same claim: a salvage can push a tip and a later local
operation can archive a different one. Ask git whether the remote tip is
reachable from the archive namespace, and when it is not, keep the ref (FR-002).
This is the difference between a cleanup and a data-loss bug.

**Trap 2 — teardown runs where the network may not be.** Deleting a remote ref
needs origin, and teardown is also invoked in paths where a fetch would be
unwelcome or impossible. A network failure must not turn an idempotent local
teardown into a failed one: report what could not be reached and complete.
FR-003 is the constraint; US1-S5 is its proof.

**Trap 3 — never force-push, and never delete an archive ref.** FR-010 exists
because the tempting one-line fix for the whole epic is `push --force`, which
turns a recoverable ref conflict into unrecoverable data loss on a branch whose
content nothing else holds. Deleting a *remote branch* whose content is archived
is safe; overwriting it is not, and the two are one keystroke apart.

**Trap 4 — `--quiet` suppresses stderr on success too, and that is fine.**
US2 must capture the reason on the failure path without making every successful
landing noisier (FR-006). `_git` is the shared helper — check how it already
handles stderr before changing the call, and prefer carrying the captured text
into the raised `WorktreeError` over dropping `--quiet` wholesale.

**Trap 5 — classify on git's own words, anchored.** "non-fast-forward" is
git's phrase and appears in a predictable place, but a substring match against
arbitrary stderr is how a guard starts firing on unrelated failures. Match it
narrowly, and default to *retryable* when unsure — FR-009 says every other cause
keeps today's behaviour, so an ambiguous classification must fall back to the
existing path, not to the new one.

**Trap 6 — escalating is not the same as not failing.** US3-S2 says the node
escalates rather than terminating. The activity still fails; what changes is that
the failure is non-retryable and the node's next action is an escalation. Do not
swallow the error to keep the node alive — an escalation with no recorded failure
behind it is unreadable.

**Trap 7 — the sibling kill is the cost that justifies this.** US3-S5 asserts no
PENDING sibling is killed. Verify that assertion against the actual cascade
behaviour rather than assuming escalation stops it; if a sibling cascade still
fires, that is a finding to report, not a scenario to soften.

## Sizing

US1 is the largest: a reachability check, a remote deletion, a degraded path for
no-network, and idempotence. US2 is the smallest change in the epic and the one
that would have saved four hours. US3 is a classification and a routing change
following a precedent in the same file.

If an attempt adds `--force` anywhere, or deletes an archive ref, it has gone
outside the spec.

## Verification the operator will run, independent of the gate

The gate proves each piece. Only a real kill-and-redispatch proves the mine is
gone, and that is the whole claim:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. dispatch a one-story spec, let the node reach VERIFYING, then kill the epic
uv run ergane build start <spec-dir> --target-repo .
# ... answer KILL_EPIC on the escalation, or terminate and sweep ...
# 2. confirm the remote ref is gone and the archive still resolves
git ls-remote origin 'refs/heads/factory/<epic>/*'          # expect: empty
git ls-remote origin 'refs/heads/archive/*'                 # expect: the salvage
# 3. re-dispatch the same spec and let it land
uv run ergane build start <spec-dir> --target-repo .
```

The demonstration succeeds when step 3 lands. Before this spec it fails at
`PUSH_FAILED` *after* passing verification, which is what makes the defect
expensive: the work is done and thrown away. Paste all three outputs into the
attestation, including the empty `ls-remote` — the absence is the evidence.
