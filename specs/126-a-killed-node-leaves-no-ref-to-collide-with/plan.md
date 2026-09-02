# Implementation Plan: a killed node leaves no ref to collide with

Every `file:line` below was read from `ergane-buildout` at `bc3c464` on
2026-09-01 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing. Three of 072's six anchors had rotted in
twelve days and `ergane spec validate` passed the spec clean every time — that is
the spec that landed today, and this one is written under its lesson.

## What already exists, and where

**The preflight seam is built, and it takes exactly two checks today.**
`landing_readiness_preflight` (`factory/workgraph/preflight.py:702`) is four lines:

```python
return worktree_ownership_findings(graph, factory_root) + landing_branch_findings(
    graph
)
```

Its docstring states the contract US1 must not break: "One entry point so
`ergane build start` and the roadmap's pre-dispatch activity cannot drift in
*which* checks they run", and "Collected rather than short-circuited... an
operator fixing one refusal per run is the failure mode". The two check names are
constants at `:553` and `:554`:

```python
WORKTREE_OWNERSHIP_CHECK = "node-worktree-ownership"
LANDING_BRANCH_CHECK = "landing-branch-declared"
```

US1 adds a third constant, a third `*_findings` function beside
`worktree_ownership_findings` (`:557`) and `landing_branch_findings` (`:620`), and
one more term to that sum. It adds nothing else to this module.

**Both surfaces already call the single entry point.** The roadmap's
pre-dispatch activity is `preflight_spec`
(`factory/activities/roadmap_activities.py:626`), which calls it at `:661`:

```python
findings += landing_readiness_preflight(request.graph, _preflight_factory_root())
```

`ergane build start`'s arm is `_run_preflight` (`factory/workgraph/cli.py:128`).
The parity test that holds them together is
`tests/test_predispatch_landing_preflight.py::test_both_dispatch_surfaces_return_the_same_findings`,
and its module docstring names the discipline US1 inherits: "**Silence costs one
git call per *existing* directory.** A graph of sixteen nodes on a host that has
never built it must not shell out sixteen times, and the assertion is on the call
count, not on the wall clock."

**The finding shape is `PreflightFinding`** (`factory/workgraph/preflight.py:126`).
US1 introduces no new result type.

**The reachability-gated clearing is already written and landed.**
`_clear_remote_branch` (`factory/workgraph/worktree.py:1763`) is the whole of
US2's git work, and it already satisfies FR-008, FR-009 and FR-010 by
construction. Its own docstring: "every outcome here — no remote, no remote
branch, a tip nothing archived, a remote that cannot be reached — is a normal
answer that the local teardown must survive, so nothing on this path raises."

It refuses when nothing archived the tip (`:1796-1802`), it puts the archive on
the remote *before* removing the head (`:1811`), and it deletes rather than forces
(`:1822`). The safety predicate it consults is `_archive_holding` (`:1831`), whose
docstring draws the distinction US2 must not blur: "'teardown ran, so an archive
exists' and 'an archive ref holds this commit' are different claims, and only the
second one makes deleting the remote ref safe."

**The local archive that authorises that deletion is `_archive_node`**
(`factory/workgraph/worktree.py:1711`). It renames `factory/<epic>/<node>` to
`archive/factory/<epic>/<node>/<tip12>` and raises rather than overwrite an
existing archive ref at a different commit (`:1749-1755`).

**`reset()` (`factory/workgraph/worktree.py:1558`) is the one caller that runs
both**, in the order that matters — local archive first, remote clear second,
with the comment at `:1618` stating why: "After the local archive, never before:
the ref that authorises the remote deletion is the one `_archive_node` has just
written." US2 reuses this pair. It does not call `reset()`; see trap 10.

**Salvage refs are not archive refs.** `SALVAGE_REF_ROOT = "refs/salvage"`
(`factory/workgraph/worktree.py:742`), while `_archive_holding` looks under
`refs/heads/archive/factory/<epic>/<node>/`. The kill path runs `salvage_worktree`
and therefore has **no** archive ref, which is precisely why `_clear_remote_branch`
alone would correctly decline to delete anything today. US2 must archive first.

**The node-ending seam is `_close_out`** (`factory/workgraph/workflow.py:3083`):
salvage, then sweep, then set state. It already executes git activities with
`**_GIT` at `:3115` and `:3130`, which is the precedent US2's new activity follows.
Its PASS path returns early at `:3117` on `state is None`.

**The contract this spec reconciles** is recorded at
`factory/workgraph/workflow.py:3584` — "1h silence or `KILL` ends the node KILLED,
branch preserved (FR-008)" — pointing at `specs/003-merge-queue/spec.md:153`.
Read spec.md's frontmatter before touching US2: the requirement is about
reachability, and archiving satisfies it.

**The refusal marker already exists** for US3: `_NON_FAST_FORWARD =
"(non-fast-forward)"` (`factory/workgraph/worktree.py:679`), and the push error is
composed at `:638` and `:655`.

## Traps

**Trap 1 — The discriminator is `state`, not `termination`.** The `PAUSE_EPIC`
park calls `_close_out(graph, node, record, Termination.KILLED, state=_PARKED)`
(`factory/workgraph/workflow.py:3287`, and the same pair at
`factory/workgraph/workflow.py:4228`). A parked node
is the one node that is going to want its live name back. Branching US2's clearing
on `termination == Termination.KILLED` clears exactly the wrong node and will pass
a naive test, because the termination genuinely *is* KILLED on both paths. Branch
on the terminal `state`.

**Trap 2 — Do not insert the clearing above `_close_out`'s early return.** A node
whose `state` is `None` has PASSED and is about to open a pull request from that
branch (`:3117-3122`). Putting the clear before that return retires the head of a
node that is landing. Following trap 1 makes this free; ignoring trap 1 makes it
fatal.

**Trap 3 — `ls-remote` matches the *tail* of a ref name.**
`_clear_remote_branch` carries the lesson in a comment at `:1778-1781`: the short
name also matches `refs/heads/anything/<branch>`, "and here it would decide a
deletion rather than a report". US1 batches one `ls-remote` for the whole graph,
so it queries a *pattern* rather than a single full ref, which makes this hazard
sharper rather than softer. Filter the returned listing on exact, full
`refs/heads/factory/<epic>/<node>` names in Python. Never let the pattern decide
which node a returned line belongs to.

**Trap 4 — The predicate is ancestry against the landing head, not existence.**
Every node of every completed epic still has its branch on origin; there are
hundreds of them, `factory/006-interpreter-hardening/us3` onward, and
`factory/072-a-stale-anchor-fails-validate-not-the-attempt/us3` is there right
now, merged. Refusing on existence refuses every re-derivation of a finished epic
and makes the check worthless within a day. The finding fires only when the remote
tip is **not** an ancestor of the head the node would branch from (FR-003,
US1-S2).

**Trap 5 — Reachability decides the deletion, never the fact that a kill ran.**
100 FR-002. Reuse `_archive_holding`; do not add a second answer to "is this safe
to delete". Two answers that can disagree about data loss is a worse defect than
the loop this spec closes.

**Trap 6 — Never force, and never touch an existing archive ref.** 100 FR-010.
`_archive_node` raises rather than overwrite (`:1749-1755`) and
`_clear_remote_branch` deletes rather than forces (`:1819-1822`). Both behaviours
are load-bearing; neither may be relaxed to make a retry path quieter.

**Trap 7 — Workflow code cannot shell out.** `_close_out` is workflow code and is
replayed deterministically. The clearing goes in a Temporal activity, following
`salvage_worktree` / `remove_worktree` and their `**_GIT` options at `:3115` and
`:3130`. Calling `worktree` helpers inline from the workflow will pass a unit test
and break replay.

**Trap 8 — A kill must complete when origin is unreachable.**
`_clear_remote_branch` returns report lines and never raises, deliberately. An
activity that turns "could not reach origin" into a retryable failure converts a
kill into a node that never terminates — strictly worse than the ref it was
cleaning up. FR-009. This is 100 FR-003's call, made again.

**Trap 9 — One remote call per graph, asserted on the count.** 107's test module
already pins this discipline for the ownership check. US1-S3 is the same
assertion for the same reason: sixteen nodes, one `ls-remote`, and the test counts
calls rather than measuring time.

**Trap 10 — Reuse the archive+clear *pair*, not `reset()`.** `reset()`
(`:1558`) also commits dirty worktree state, removes the worktree directory and
deletes the sidecar — all of which `_close_out` has already done via
`salvage_worktree` and `remove_worktree` by the time US2's activity runs. Calling
`reset()` from the kill path makes the kill fight the sweep it just performed.
Factor a small public helper in `worktree.py` that runs `_archive_node` then
`_clear_remote_branch`, and have `reset()` and the new activity both call it, so
the ordering comment at `:1618` has exactly one home.

**Trap 11 — The preflight is a report over a moving target, and the push stays
the enforcement.** The landing head can advance between preflight and dispatch,
and `capture_base_ref` fetches before reading precisely because of that. Do not
try to make US1 authoritative, do not pin a base in the preflight, and do not
weaken `push_branch` (`:554`) because a check now runs earlier. US1 makes reaching
the enforcement rare; it does not replace it. This mirrors 107's own split — US1
was the per-node enforcement, the preflight was the epic-wide report.

**Trap 12 — US3 may not alter escalations it is not about.** FR-012. Branch on the
terminal cause using the existing `_NON_FAST_FORWARD` marker
(`factory/workgraph/worktree.py:679`), and add a test that an escalation for an
unrelated cause is byte-identical to today's.

## Sizing

US1 is one constant, one `*_findings` function, one added term in a four-line
sum, and tests. It touches `factory/workgraph/preflight.py` and its test module
and nothing else — neither dispatch surface needs an edit, because both already
call the entry point.

US2 is one small public helper in `factory/workgraph/worktree.py`, one activity
beside `remove_worktree`, one guarded `execute_activity` call in `_close_out`, and
tests. The git logic is entirely reuse.

US3 is a branch on the terminal cause in the escalation message composition, plus
tests. No new data reaches the operator that the node record does not already
hold.

The three stories name no file in common except the test tree, and none depends on
another.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that, the operator
will run this, and it is the falsifiable test of the whole spec:

1. On a scratch clone, push a `factory/<epic>/<node>` branch whose tip is
   unrelated to the landing head.
2. Run `ergane build start` against a graph naming that node. It must refuse,
   name the ref, and dispatch nothing — no key issued, no agent started.
3. Delete the ref, dispatch for real, and let a node reach KILLED.
4. Read origin: the live `factory/<epic>/<node>` name is gone, and an
   `archive/factory/<epic>/<node>/<sha>` ref carries its tip.
5. Re-dispatch the same node. It must build and push without a non-fast-forward
   refusal.

Step 5 is the one that matters, because it is the exact sequence that ran four
times on 2026-09-01 and failed four times.
