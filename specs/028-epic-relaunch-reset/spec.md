---
state: ready
# Flipped ready 2026-08-11 PM CT on the operator's word ("flip all 6"); the
# paused roadmap dispatches serially (max_concurrent_epics=1) in dir order
# once unpaused.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `interpreter/relaunched-epic-resumes-the-dead-runs-tree` (critical, source
# operator-2026-08-09), then refined against the tree at 9594787 on 2026-08-11.
# Related open finding, named but NOT fixed here:
# `interpreter/cancel-bypasses-kill-sequence`.
---

# Feature Specification: A relaunch that does not resume the dead run

## The defect in one sentence

Three artifacts outlive a dead epic — the worktree directory (survives
`temporal workflow terminate` entirely), the `<node>.json` base-ref sidecar
(survives even a clean `kill_epic`), and the node branch (survives by explicit,
documented design) — and `ensure()` trusts all three unconditionally, so a
relaunched epic silently resumes the dead run's tree at the dead run's base pin.

## The mechanism, story by story

`factory/workgraph/worktree.py`'s `ensure()` has three reuse decisions and not
one of them asks a question first. A present directory returns the recorded
`PreparedWorktree` verbatim. An absent directory with a surviving sidecar reuses
the recorded pin. An absent directory with a surviving branch checks the dead
branch back out. Each of those is *correct* inside a live epic — reuse across
attempts is FR-013's contract and the debugger persona depends on it — and each
is *wrong* across the boundary of a dead one, because nothing marks the boundary.

Proved 2026-08-09: `020-landing-attribution` died four times at `CONFIG_ERROR`
because its us1 wrote a `landing_branch` line into `factory.yaml` that the
then-running worker's parser rejected — the very key us1 was in the middle of
teaching it; today's parser accepts `landing_branch`, which changes nothing
about the reuse defect. The operator fixed the spec, terminated the parked run,
re-derived and restarted — and it failed a **fifth** time, identically, because
`terminate` runs none of the workflow's cleanup, `ensure()` found the directory
present, and handed the new agent the dead agent's tree, poison line included.
The new agent's transcript truthfully says it never edited `factory.yaml`. It
did not need to.

Today a clean relaunch needs three undocumented hand steps: `rm` the sidecar,
rename the node branch in the target clone, and reset the clone. This spec
replaces them with three small stories:

- **US1** makes `ensure()` trust-but-verify: a recorded pin is reused only after
  proving it is still an ancestor of the target's current landing-branch head;
  anything that fails the proof is rebuilt fresh, with what was there archived —
  renamed, never deleted. This is the mechanical backstop, and it subsumes the
  finding's "refuse to dispatch" candidate fix (see Out of Scope).
- **US2** makes the sweep complete: `remove()` takes the sidecar with the
  directory, so a cleanly killed epic stops leaving a stale pin on disk.
- **US3** gives the operator the supported path: `ergane build reset`, which
  archives node branches, clears sidecars, removes surviving worktrees, and
  reports what it did. This — not US1 — is what would have prevented 020's fifth
  failure, because that tree's pin was merely *behind* the landing head, not
  divergent from it: ancestry cannot flag a poisoned tree on a fast-forwarded
  target, and an operator verb can.

One boundary named up front: `temporal workflow terminate` bypassing the kill
sequence is the related open finding `interpreter/cancel-bypasses-kill-sequence`.
This spec makes the survivors of a terminate harmless and cleanable; it does not
try to make terminate run cleanup.

## User Scenarios & Testing

### User Story 1 - ensure() verifies the pin before reusing it (Priority: P1)

**Goal**: `ensure()` reuses a recorded worktree, pin, or surviving branch only
after verifying the base it is about to trust still belongs to the target's
history — the recorded `base_ref` is an ancestor of the current landing-branch
head — and otherwise rebuilds fresh, archiving what was there so no history is
lost. In-epic reuse across attempts, where the landing branch only ever moves
forward, is byte-for-byte unchanged.

**Independent Test**: prepare a node against a scratch origin, leave its
worktree, sidecar and branch in place as a terminate would, reset the origin's
landing branch so the pin is no longer an ancestor, and call `ensure()` again:
it hands back a fresh tree at the new head with the old branch reachable under
an archive ref. Repeat with the origin merely advanced: the old tree comes back
untouched.

**Acceptance Scenarios**:

1. **Given** a node's worktree, sidecar and branch all surviving a terminate,
   and a target whose landing branch has been reset so the recorded `base_ref`
   is no longer an ancestor of its current head, **When** `ensure()` runs,
   **Then** it returns a fresh worktree created from a freshly captured pin, and
   the sidecar records the new pin — not the dead run's.
2. **Given** a prepared node whose recorded `base_ref` is still an ancestor of
   the landing branch's current head (the target only advanced), and a dirty
   worktree from the previous attempt, **When** `ensure()` runs, **Then** it
   returns the recorded `PreparedWorktree` verbatim and the tree's contents are
   untouched — no fetch result, rebase or reset ever modifies it.
3. **Given** the rebuild in scenario 1, **When** it completes, **Then** every
   commit that was reachable from the old branch tip — plus a commit capturing
   any uncommitted state the abandoned tree held — is reachable from a ref in
   the archive namespace, and no ref was deleted.
4. **Given** no directory and no sidecar but a surviving node branch whose tip
   does not descend from the freshly captured pin, **When** `ensure()` runs,
   **Then** the branch is archived and a fresh branch and worktree are created
   at the fresh pin, rather than the dead branch being checked back out.
5. **Given** no directory and no sidecar but a surviving node branch whose tip
   does descend from the freshly captured pin (nothing has landed since),
   **When** `ensure()` runs, **Then** the branch is checked out exactly as
   today — the documented continuity of salvaged history is preserved.

### User Story 2 - The sweep takes the sidecar with the directory (Priority: P2)

**Goal**: `remove()` deletes the node's base-ref sidecar in the same operation
that deletes the worktree directory, so every existing sweep path — close-out,
landing terminals, the kill sequence — stops leaving a stale pin behind. The
branch and its salvage history still survive removal, exactly as documented.

**Independent Test**: prepare a node, then call `remove()`: the directory and
`<node>.json` are both gone, the branch survives, and a second `remove()` — or
one for a node never prepared — still succeeds.

**Acceptance Scenarios**:

1. **Given** a prepared node with its sidecar on disk, **When** `remove()` runs,
   **Then** the worktree directory and the `<node>.json` sidecar are both gone
   and the node branch with its history is untouched.
2. **Given** a node already removed, or one that was never prepared, **When**
   `remove()` runs, **Then** it succeeds — the sweep stays idempotent for
   activity retries.
3. **Given** an epic whose node reaches a terminal that sweeps the worktree
   through the `remove_worktree` activity, **When** the sweep completes,
   **Then** no sidecar for that node remains under the factory root — the
   workflow inherits the fix by calling the same function, with no workflow
   edit.
4. **Given** a cleanly killed epic swept by US2 and then relaunched, **When**
   `ensure()` runs for one of its nodes, **Then** it finds no sidecar to trust
   and captures a fresh pin, with the surviving branch handled by US1's rule.

### User Story 3 - ergane build reset, the supported relaunch path (Priority: P2)

**Goal**: one operator command replaces the three undocumented hand steps: it
archives every node branch the graph names (rename, never delete), removes
surviving worktree directories after committing any uncommitted state, clears
sidecars, and reports per node what it did. It refuses to touch an epic whose
workflow is still running.

**Independent Test**: against a scratch target carrying a dead run's leavings —
dirty worktrees, sidecars, branches — run `ergane build reset <graph>` and
verify every action in its report happened, every pre-reset tip is still
reachable, a second run reports nothing to do, and a subsequent `ensure()`
yields a fresh tree at the current landing head.

**Acceptance Scenarios**:

1. **Given** a terminated epic's survivors — worktree directories holding
   uncommitted work, sidecars, node branches — **When** `ergane build reset`
   runs against the epic's compiled graph, **Then** for each node it commits the
   dirty state to the node branch, renames the branch into the archive
   namespace, removes the worktree directory, deletes the sidecar, and prints a
   per-node report naming each action, exiting 0.
2. **Given** a reset that already ran, **When** it runs again, **Then** it
   reports nothing to do for every node and exits 0.
3. **Given** the epic's workflow is currently running, **When** reset runs,
   **Then** it refuses before touching anything, names the workflow id in its
   error, and exits nonzero.
4. **Given** no workflow for this epic exists on the Temporal server (never
   started here, or history purged), **When** reset runs, **Then** it proceeds —
   absence of a workflow is not an error for a cleanup verb.
5. **Given** a completed reset, **When** the target's refs are inspected,
   **Then** every commit reachable from any pre-reset node branch tip is still
   reachable from an archive ref, and no ref of any kind was deleted.
6. **Given** a reset followed by a relaunch, **When** the new epic's first
   attempt for a node opens its worktree, **Then** the tree is freshly created
   at the target's current landing-branch head and contains nothing of the dead
   run's edits.

## Functional Requirements

- **FR-001**: `ensure()` MUST NOT reuse a recorded `base_ref` — whether to
  return an existing directory or to pin a rebuilt one — without verifying it is
  an ancestor of the target's current landing-branch head, read the same way
  `capture_base_ref` reads it: fetched from `origin`, the clone's own HEAD only
  when there is no `origin`, and a fetch failure raised rather than passed over.
- **FR-002**: When the verification passes, behaviour MUST be today's exactly:
  the same tree returned untouched, the same pin, the same branch — the check
  may fetch, but it MUST NOT modify the worktree, the branch, or the sidecar.
- **FR-003**: When the verification fails, `ensure()` MUST rebuild: archive what
  was there, capture a fresh pin, create a fresh worktree and branch, and write
  a fresh sidecar recording the new pin.
- **FR-004**: Archiving MUST be a rename, never a delete: any uncommitted state
  in an abandoned tree is committed to its branch first (constitution VI), the
  branch is renamed to an archive name that is unique per archived tip, and no
  existing ref is ever overwritten or deleted by any code path this spec adds.
- **FR-005**: A surviving node branch with no recorded pin MUST be checked out
  only when the freshly captured pin is an ancestor of (or equal to) the branch
  tip; otherwise the branch is archived and a fresh one is created. This is the
  finding's refuse-to-dispatch guard, subsumed: `ensure()` heals instead of
  refusing, and loses nothing because the archive keeps everything.
- **FR-006**: `remove()` MUST delete the node's base-ref sidecar in the same
  operation that removes the worktree directory, and MUST remain idempotent —
  a missing directory or missing sidecar is success.
- **FR-007**: The sidecar sweep MUST live only in `remove()`: every existing
  removal path (close-out, landing MERGED, landing KILLED, kill sequence)
  inherits it by already flowing through the `remove_worktree` activity, and no
  workflow code changes.
- **FR-008**: `ergane build reset <graph>` MUST exist as a `build` subcommand
  taking the compiled workgraph artifact (the same argument shape as
  `build start`), and for each node in the graph MUST: commit any dirty worktree
  state to the node branch, remove the worktree directory, archive the node
  branch under FR-004's rules, delete the sidecar, and print a per-node report
  of what it did — including "nothing to do".
- **FR-009**: Reset MUST be idempotent: a second run performs no action, reports
  so, and exits 0.
- **FR-010**: Reset MUST refuse to run while the epic's workflow reports RUNNING
  on the Temporal server, before touching anything. A NOT_FOUND workflow
  proceeds; an unreachable server is a transport error (exit 3), never a
  silently skipped check.
- **FR-011**: Reset MUST touch only the artifacts of nodes the graph names —
  their `factory/<epic>/<node>` branches, their sidecars, their worktree
  directories. It MUST NOT delete any ref, rewrite the landing branch, alter
  the clone's checked-out state, or touch any remote.

## Success Criteria

- **SC-001**: The 020 incident's shape is closed by test: terminate (nothing
  swept) → `ergane build reset` → relaunch hands the new run a fresh tree at the
  current landing head containing none of the dead run's edits.
- **SC-002**: In-epic reuse is provably unchanged: a node whose target has only
  advanced opens the identical, untouched tree on its next attempt.
- **SC-003**: No new code path deletes a ref; every archived tip remains
  reachable, asserted by test against the ref namespace, not by reading the
  report.
- **SC-004**: A cleanly killed epic leaves no sidecar on disk for any swept
  node.
- **SC-005**: The full suite stays green and no dependency is added.

## Edge Cases

- **An explicit `base_ref` argument bypasses the recorded pin entirely** (today
  only tests pass it; the production caller `prepare_worktree` never does). It
  remains the caller's authority and is not ancestry-checked — the check guards
  the *recorded* pin, not a deliberate instruction.
- **A clone with no `origin`** verifies ancestry against its own HEAD, mirroring
  `capture_base_ref`'s no-origin rule.
- **A fetch failure during verification raises** `WorktreeError`, for
  `capture_base_ref`'s stated reason: a quiet stale answer is the defect this
  exists to prevent. The activity's retry policy owns transient network failure.
- **A terminate survivor on a fast-forwarded target passes US1's check** — the
  pin is behind, not divergent, and the poisoned tree is reused. That is 020's
  exact fifth failure, it is why US3 exists, and the spec says so rather than
  pretending ancestry catches it.
- **The adopt path** (directory present, sidecar missing — today's
  worktree.py:207-216) becomes rare once US2 sweeps both together, and is left
  in place for hand-damaged state; the directory-present reuse it feeds is
  subject to no recorded pin, so it pins where the tree stands, as documented.
- **Archive-name collision**: the archive name is derived from the archived tip,
  so a retry after a partial rebuild finds the same name holding the same
  commit; that is "already archived", not an error. A collision at a *different*
  commit is refused — never overwritten.
- **A landing PR still open when reset runs**: reset renames local branches
  only; the remote branch and its PR are untouched and remain the operator's to
  close (FR-011).

## Assumptions

- `factory/workgraph/worktree.py` is the sidecar's only reader and writer
  (verified at 9594787: `_record_file`, `_record`, `_read_record` have no
  callers outside the module), so US1 and US2 change every consumer by changing
  one file.
- Node branch names are only ever consumed as exact strings (`branch_name`,
  `_branch_exists`, `push_branch`); nothing globs `factory/*`, so an
  `archive/factory/...` namespace collides with nothing (verified: no ref
  iteration over the prefix anywhere in `factory/`).
- The archive namespace ends in a per-tip suffix, so no plain
  `archive/factory/<epic>/<node>` branch is ever created and git's
  ref directory/file conflict cannot arise.
- Reset takes the compiled graph artifact because it is the one file that names
  the epic id, the target repo and every node id — the exact set of artifacts
  reset may touch (FR-011) — and because `build start` already established that
  argument shape.
- One fetch per `prepare_worktree` call is an accepted cost of FR-001; the
  alternative — checking ancestry against unfetched local refs — can silently
  pass on a stale view, which is the same defect one layer down.

## Out of Scope

- **Making `temporal workflow terminate` run cleanup.** That is the open finding
  `interpreter/cancel-bypasses-kill-sequence`; this spec makes the survivors
  safe, not the terminate polite. Name the relationship in code comments where
  relevant; do not fix it here.
- **A separate refuse-to-dispatch guard in `derive` or `build start`** (the
  finding's candidate fix 2). It falls out of US1: `ensure()` is the only place
  that holds the pin, the branch and a git checkout at the same moment, and
  healing with an archive loses nothing where refusing would cost the operator
  a round trip. A start-time guard would re-implement the same ancestry check
  against a clone `start` does not otherwise read.
- **Syncing the target clone's own checkout** (the third hand step). The pin is
  fetched from `origin`, never read from the clone's HEAD, so a stale checkout
  no longer poisons the pin. One residual read remains and is unchanged here:
  `landing_branch()` takes the branch *name* from the clone's checked-out
  `factory.yaml`, so a checkout stale across a landing-branch rename still
  matters — that is its documented rule, not this spec's. Bringing the clone
  forward is an ordinary `git pull` the operator may run or skip.
- **Remote-side cleanup** — closing dead PRs, deleting remote branches. Reset is
  local by contract (FR-011).
- **Backfilling or repairing any past epic's artifacts.** Reset is forward-
  looking; 020's archived leavings are evidence, not work items.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010, FR-011]
```
