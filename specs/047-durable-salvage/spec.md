---
state: ready
# Flipped to ready 2026-08-16 by the operator session on Bryan's instruction,
# after an operator read of all three documents: every criterion is decidable
# from a diff, the two seam-disabled controls (SC-002, SC-004) are what make the
# checks non-vacuous, and the eleven traps include the one the drafting session
# found by tripping over it — a gc control built in a repo with a remote cannot
# prune, because US1's push pins the object behind refs/remotes/origin/<branch>.
# The three orphaned salvage commits the spec was drafted from were rescued by
# hand the same morning and pushed under refs/salvage/*, so the evidence US2
# exists to make automatic is off-machine already; that is recorded in the
# Out of Scope section rather than left as a pending chore.
# Drafted 2026-08-16 by an operator session, from one open critical finding,
# `hardening/salvage-is-lost-when-a-node-never-reaches-a-pr` (filed 2026-08-13,
# 1 occurrence), whose stated mechanism this spec **corrects rather than
# repeats** — see plan.md § "Where this spec disagrees with the finding".
# The correction matters: the finding says every killed node in the factory's
# history has lost its work. It has not. What is true, and measured at
# 5e38c19 on 2026-08-16, is narrower and still critical: no salvage is ever
# off-machine, and a superseded per-attempt salvage sha becomes unreachable and
# is eventually pruned.
# This is the spec that defends constitution principle VI ("No Work Is Ever
# Lost"). Every acceptance scenario is decidable from the story's diff alone
# (principle VIII / D-037): the durability claims are exercised against a bare
# fixture remote inside `tmp_path`, never against a real remote, and the
# pruning claim is proven by a committed control.
---

# Feature Specification: 047-durable-salvage

## Context

Constitution VI says agent output is salvaged on every termination path by
committing the worktree to the node's branch before cleanup. The factory does
exactly that: `salvage()` (`factory/workgraph/worktree.py:372`) runs `git add
-A`, commits with `--allow-empty` and the per-attempt subject from
`salvage_message()` (`:243`), and returns the new head (`:413`). It does not
push, and it writes no ref other than the branch it is already on.

Pushing is a separate function, `push_branch()` (`:416`), and a repo-wide grep
finds exactly **one** caller: `factory/activities/merge_activities.py:371`,
inside `open_landing_pr`. No other code in the tree pushes a node branch. So
the asymmetry is precise: **the merge surface pushes; the salvage path does
not.** A node that never passes verification never opens a PR, never reaches
`open_landing_pr`, and therefore never leaves the machine it was built on.

Two consequences, both measured on this host at `5e38c19` on 2026-08-16.

**First: salvaged work is one disk away from gone.** Of 28 local `factory/**`
branches in the operator checkout, 8 have no counterpart on `origin`. Four of
those are epics in flight. The other four are terminated nodes whose only copy
of their salvaged work is this one machine:

```
factory/006-interpreter-hardening/us1  91ef108  salvage(…/us1): completed attempt 3
factory/006-interpreter-hardening/us2  473c1d2  salvage(…/us2): completed attempt 1
factory/006-interpreter-hardening/us5  768c65f  salvage(…/us5): completed attempt 1
factory/027-gate-suite-fake-time/us2   b60337d  salvage(…/us2): completed attempt 5
```

This is not theoretical. On 2026-08-14 an agent ran `rm -rf` against the live
runtime root and destroyed all three stores, all transcripts and both node
worktrees (`hardening/agent-deleted-the-live-runtime-root`, resolved by 043).
Recovery came from an off-machine restic snapshot. The `.git` directory
survived that particular blast radius by luck of where the deletion pointed;
had it not, those four branches would have been gone permanently and the
factory would hold no record it ever built that work.

**Second: a superseded per-attempt salvage sha stops resolving.** The workflow
runs `salvage_worktree` at three sites (`factory/workgraph/workflow.py:1319`,
`:2019`, `:2534`) and **discards the returned sha at all three** — it is never
written to a store, never put on `NodeStatus` (`workflow.py:429`), and exists
only as an `ActivityTaskCompleted` payload in Temporal history. Meanwhile the
commit it names is reachable from exactly one place: the node branch's tip, at
that instant. Anything that later moves that branch — an agent's `git commit
--amend`, an operator deleting the branch before a relaunch — orphans it, and
`git gc` prunes it on its own schedule.

Three orphaned salvage commits are sitting in this clone's object database
right now, each reachable from **zero** refs:

```
7c818d8  salvage(028-epic-relaunch-reset/us3): completed attempt 2  (2026-08-13)
c840683  salvage(028-epic-relaunch-reset/us3): completed attempt 1  (2026-08-13)
53bdbb4  salvage(003-merge-queue/us3): completed attempt 1          (2026-08-06)
```

And one that was already collected: the finding records
`salvage_worktree(attempt=4, node_id=us2, termination=completed) ->
81905eb1f8bb…` for `027-gate-suite-fake-time/us2`; `git cat-file -t` on that
sha answers `fatal: could not get object info` in the operator checkout and in
all three sibling target clones on this host. The record survives; the thing it
records does not.

Three stories. The first makes a salvage survive the machine that made it. The
second makes every recorded per-attempt sha stay resolvable no matter what
later happens to the branch. The third lets an operator ask what a terminated
node left behind without knowing git plumbing.

---

### User Story 1 - A salvage commit leaves the machine that made it (Priority: P1)

Salvage already produces the durable artifact; what it does not do is put a
copy anywhere else. The push that makes a node branch exist off-machine is
today a side effect of opening a PR, which is precisely the path a killed,
timed-out or failed node never takes. Salvage must mirror the node branch to
the target's remote itself, at salvage time.

The hard constraint is that mirroring may never turn a salvage into a failure.
Constitution VI says salvage happens on every termination path; a target repo
with no remote, an unreachable remote, or a remote that refuses the push must
each leave the salvage commit made and the call returning normally, reporting
what happened rather than raising it.

**Why this priority**: it is the half of "no work is ever lost" that is not
implemented at all. Four terminated nodes' work exists on exactly one disk
today, and the machine holding it has already had an agent run `rm -rf` at it
once.

**Independent Test**: Salvage a node in a target clone whose `origin` is a bare
repository inside `tmp_path`, and confirm the node branch arrives there at the
salvage commit; then repeat with no remote, with a broken remote, and with the
landing branch's own name, and confirm the salvage commit is made every time
and nothing raises.

**Acceptance Scenarios**:

1. **Given** a node worktree in a target clone whose `origin` is a bare
   repository created in `tmp_path`, **When** salvage runs for a terminal
   attempt, **Then** the node branch exists on that bare remote pointing at the
   sha salvage returned — proven by a committed test.

2. **Given** a target clone with no remote configured at all, **When** salvage
   runs, **Then** the salvage commit is made on the node branch, the call
   returns the sha, nothing raises, and the reported mirror outcome names the
   absent remote as the reason — proven by a committed test.

3. **Given** a target clone whose `origin` points at a path that does not
   exist, **When** salvage runs, **Then** the salvage commit is still made, the
   call still returns the sha, nothing raises, and the reported mirror outcome
   carries git's own refusal text rather than a paraphrase of it — proven by a
   committed test.

4. **Given** an attempt whose salvage already mirrored, **When** the same
   attempt's salvage runs again against a clean tree (the activity-retry path
   `salvage`'s existing idempotency covers), **Then** the branch gains no second
   commit, the remote is unchanged, and the second mirror reports success —
   proven by a committed test.

5. **Given** a node whose branch name is the target repository's declared
   landing branch, **When** salvage runs, **Then** the salvage commit is made
   and nothing is pushed, with the refusal naming that branch — proven by a
   committed test that asserts the bare remote's landing branch is byte-for-byte
   where it was.

6. **Given** the mirror disabled through its seam, **When** the scenario-1
   worktree is salvaged, **Then** the branch does **not** appear on the bare
   remote — the control proving the mirror changed an outcome (SC-004) — proven
   by a committed test.

7. **Given** the diff, **When** the salvage activity is exercised, **Then**
   `salvage_worktree` still returns the salvage commit sha as a plain `str`, so
   the workflow's payload contract is untouched — proven by a committed test.

---

### User Story 2 - Every recorded per-attempt salvage sha still resolves (Priority: P1)

A salvage commit is reachable from one place: the node branch's tip, at the
moment it is made. The next attempt commits on top, and the branch tip is still
an ancestor chain — but a rewrite is not. `factory/028-epic-relaunch-reset/us3`
shows the whole failure in one reflog: four `commit (amend)` entries, and two
salvage commits (`c840683`, `7c818d8`) left reachable from nothing. Once `git
gc` runs, the sha the workflow recorded resolves to nothing, which is what
`81905eb1f8bb…` already is.

Salvage must therefore write its own ref: an immutable, per-attempt ref in the
target repository naming epic, node and attempt at that salvage commit. A ref
is what `git gc` reads; a commit a ref names is not collectable, whatever the
branch does afterwards.

**Why this priority**: US1 makes the *branch tip* durable. This story makes the
*record* durable — without it, the factory keeps writing down shas that stop
meaning anything, and there is no way to tell a lost attempt from a superseded
one after the fact.

**Independent Test**: Salvage attempt 1, rewrite the branch with `git commit
--amend` (the rewrite observed on 028/us3), expire every reflog and run `git gc
--prune=now`, then resolve attempt 1's sha; it must still resolve. With the ref
seam disabled, the same sequence must prune it.

**Acceptance Scenarios**:

1. **Given** a node whose attempt 1 has been salvaged, **When** the target
   repository's refs are read, **Then** a per-attempt ref names epic, node and
   attempt 1, and resolves to exactly the sha salvage returned — proven by a
   committed test.

2. **Given** attempt 1 salvaged, **When** the node branch is rewritten in its
   worktree with `git commit --amend` and the repository then has every reflog
   expired and `git gc --prune=now` run against it, **Then** attempt 1's sha
   still resolves — proven by a committed test.

3. **Given** the per-attempt ref suppressed through its seam, **When** the
   identical amend-then-gc sequence from scenario 2 runs, **Then** attempt 1's
   sha does **not** resolve — the control proving the ref is what saved it, not
   the sequence being impossible (SC-002) — proven by a committed test.

4. **Given** an attempt salvaged twice against a clean tree, **When** the refs
   are read, **Then** exactly one ref names that attempt and it is unmoved —
   proven by a committed test.

5. **Given** an attempt salvaged twice with the worktree dirtied in between —
   the path `salvage` deliberately allows, because a duplicate commit is a
   better error than discarded work — **When** the refs are read, **Then**
   both salvage commits are named by refs and neither is reachable from zero
   refs — proven by a committed test.

6. **Given** an attempt salvaged against a target clone whose `origin` is a
   bare repository in `tmp_path`, **When** the mirror US1 built runs, **Then**
   the per-attempt refs are present on that bare remote too — proven by a
   committed test.

7. **Given** a remote that refuses the per-attempt ref namespace, **When**
   salvage runs, **Then** the salvage commit is made, the local per-attempt ref
   is written, nothing raises, and the refusal is reported — proven by a
   committed test whose fixture remote refuses that namespace.

8. **Given** an attempt that produced nothing, **When** its `--allow-empty`
   salvage runs, **Then** it gets a per-attempt ref exactly as a dirty one does
   — proven by a committed test.

---

### User Story 3 - An operator can ask what a terminated node left behind (Priority: P2)

The answer to "the node was killed — is its work anywhere?" is currently four
git plumbing commands against a clone the operator has to know the path of, and
a ref-naming convention that is documented only in `worktree.py`'s docstring.
There is no verb. `ergane status` (`factory/cli/status.py:199`) reads the live
floor and needs Temporal; a terminated epic's workflow may be gone, which is
exactly when the question is asked. `ergane spec landed`
(`factory/workgraph/cli.py:154`) reports landed stories and is silent about
everything else — and must stay silent, because 020-US2's negative test
requires salvage subjects to be refused as landings
(`factory/workgraph/landed.py:45`).

So this is a new verb on the existing `build` noun, shaped like `build reset`
(`factory/cli/nouns/build.py:590`): it takes a compiled work graph, reads git,
and prints one block per node. It reads and never writes.

**Why this priority**: P2 because US1 and US2 make the work survive whether or
not anyone can see it, and a durability fix that nobody can confirm is still a
durability fix. But an operator who cannot check has to trust, and this
repository's standing rule is to verify what the factory believes rather than
what it reports.

**Independent Test**: Build a target clone holding one terminated node's branch
and per-attempt refs, one node that never dispatched, and a bare fixture
remote; run the verb against the compiled graph and read each node's answer;
then assert the repository is unchanged.

**Acceptance Scenarios**:

1. **Given** a compiled work graph and a target clone holding a terminated
   node's branch and two per-attempt salvage refs, **When** the verb runs,
   **Then** its output names that node's branch, its tip sha and subject, and
   one line per per-attempt ref with that attempt's sha and subject — proven by
   a committed test.

2. **Given** a node in the graph that never dispatched, so it has no branch and
   no refs, **When** the verb runs, **Then** it says so for that node and exits
   0 — proven by a committed test.

3. **Given** one node's branch present on the target's bare fixture remote and
   another node's branch present only in the local clone, **When** the verb
   runs, **Then** each node is labelled with which of the two it is — proven by
   a committed test.

4. **Given** a target clone with no remote at all, **When** the verb runs,
   **Then** it reports the off-machine question as unanswered rather than
   failing, and exits 0 — proven by a committed test.

5. **Given** the verb has run, **When** the target repository's full ref list
   and worktree list are compared against what they were before, **Then** they
   are identical — proven by a committed test that captures both before and
   after.

6. **Given** no Temporal server is reachable, **When** the verb runs, **Then**
   it answers normally — proven by a committed test that makes no Temporal
   connection and asserts the code path opens none.

---

## Functional Requirements

- **FR-001**: After committing, `salvage` MUST attempt to mirror the node
  branch to the target repository's remote, and MUST return the salvage commit
  sha whether or not that mirror succeeded.
- **FR-002**: A mirror failure of any kind — no remote configured, a remote
  that cannot be reached, a remote that refuses — MUST NOT raise, MUST NOT
  alter or skip the salvage commit, and MUST be reported as a structured
  outcome carrying git's own message rather than a paraphrase. Constitution VI
  is unconditional: salvage always happens.
- **FR-003**: Mirroring MUST refuse to push a branch whose name is the target
  repository's declared landing branch, reusing the existing guard in
  `push_branch` (`factory/workgraph/worktree.py:444-449`) rather than restating
  the rule in a second place.
- **FR-004**: Mirroring MUST be idempotent and MUST never use `--force`. A
  second mirror of an unchanged branch is a success, not an error.
- **FR-005**: The `salvage_worktree` activity MUST keep returning the salvage
  commit sha as a plain `str`, and this spec MUST add no new activity call to
  `EpicWorkflow` — the workflow's command sequence is unchanged, so no in-flight
  or replayed history is affected.
- **FR-006**: Every salvage MUST write an immutable ref in the target
  repository naming the epic, the node and the attempt, pointing at that
  attempt's salvage commit, so the recorded sha is reachable from a ref and
  therefore not collectable.
- **FR-007**: No salvage commit that a per-attempt ref has ever named may
  become unreachable. Where one attempt legitimately produces two salvage
  commits (the dirty-tree re-salvage `salvage`'s docstring permits at
  `factory/workgraph/worktree.py:386-389`), both MUST end up named.
- **FR-008**: The per-attempt refs MUST travel by the same mirror path FR-001
  builds, and MUST degrade exactly as FR-002 requires when the remote refuses
  the namespace.
- **FR-009**: An operator verb MUST report, for every node of a compiled work
  graph, the node's branch, its tip, each per-attempt salvage ref, and whether
  that branch exists off this machine. It MUST be read-only: no ref, worktree,
  branch or file may be created, moved or deleted by it.
- **FR-010**: That verb MUST answer for nodes that left nothing, MUST answer
  when the target has no remote, and MUST NOT require a Temporal connection.
- **FR-011**: An empty salvage MUST stay a first-class salvage: `--allow-empty`
  behaviour is unchanged, and an attempt that produced nothing MUST still
  commit, MUST still mirror, and MUST still get a per-attempt ref.
- **FR-012**: For a target repository that already had a working remote and a
  node that already reached a PR, every observable outcome MUST be unchanged —
  the landing path's own push stays exactly where it is.

## Success Criteria

- **SC-001**: The four terminated-node branches that exist only on this disk
  today cannot recur: each of the termination paths that produced them,
  reconstructed as a fixture, leaves the node branch on the fixture remote.
- **SC-002**: **Control.** With the per-attempt ref seam disabled, the
  reconstructed 028/us3 amend-then-gc sequence prunes the recorded sha; with it
  enabled, the same sha resolves. The check is proven to be what changed the
  outcome.
- **SC-003**: A target repository with no remote runs every termination path
  with salvage succeeding and nothing raising — the portability floor: no
  remote is a normal target, not a broken one.
- **SC-004**: **Control.** With the mirror seam disabled, the node branch does
  not reach the fixture remote.
- **SC-005**: `ergane build salvage` answers for a terminated node with no
  Temporal server running anywhere.
- **SC-006**: The full suite passes with every existing `tests/test_worktree.py`
  salvage and push fixture unchanged — the parity half, FR-012.

## Out of Scope

- Recovering the salvage commits already orphaned in the operator checkout
  (`7c818d8`, `c840683`, `53bdbb4`) or the one already pruned
  (`81905eb1f8bb…`). Backfilling history is an operator action against one
  clone, not behaviour the factory should carry. **Done by hand on 2026-08-16,
  before drafting closed**: the three orphans were each given a
  `refs/salvage/<epic>/<node>/attempt-<n>` ref and pushed, so they are now off
  this disk and safe from the next `git gc`. That rescue is the evidence this
  spec's US2 exists to make automatic; it is not a substitute for it, and the
  fourth commit was already unrecoverable when it was looked for.
- Adding a remote to a target repository that does not declare one, or
  configuring where a target pushes. The factory mirrors to what the target
  already says; it never invents a destination.
- A `--json` view of the new verb. `build reset` has none either; add one when
  something needs to consume it.
- Any change to what `ergane spec landed` reports, or to the landing grammar
  in `factory/workgraph/landed.py`.
- Any change to the landing path's own push (`open_landing_pr`,
  `factory/activities/merge_activities.py:371`). It already works and the
  merge queue depends on its exact shape.
- Persisting the salvage sha into the verification store or onto `NodeStatus`.
  US2 makes the sha resolvable, which is what the record needed; a second copy
  of it is a different spec.
- Changing the target clone's `gc` configuration. Relying on a `gc` setting
  would be a fix that one `git config` undoes silently.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-012]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010]
```
