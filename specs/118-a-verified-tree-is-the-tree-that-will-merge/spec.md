---
state: landed
fixes:
# ALL THREE STORIES ARE ON ergane-buildout, each on its first attempt, gate and
# judge green: US1 dd84c70 (#378), US3 a169063 (#379), and US2 a8ca884 (#384),
# which landed 2026-08-30 and closed the last gap. Confirmed by `ergane spec
# landed <this dir> --default-branch ergane-buildout`, which observes all three.
# ATTESTED 2026-08-30 11:30 PM CT by the operator session, on Bryan's answer.
# The branch was complete first and the attestation followed it, which is the
# only correct order -- attesting ahead of the branch is what makes `ergane
# status` believe an epic is finished when it is not.
  - verify/a-stale-worktree-makes-gates-and-judge-score-against-a-base-that-no-longer-merges
  - verify/an-operator-cannot-correct-a-running-epics-context-because-the-worktree-is-pinned-at-dispatch
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# A new number: none of the 089-102 slots reserved on 2026-08-23 names this.
#
# NAMING, CORRECTED 2026-08-29 BEFORE DISPATCH: the function this spec changes is
# `ensure` (`factory/workgraph/worktree.py`). `prepare_worktree` is the
# ACTIVITY at `factory/activities/agent_activities.py:394` that calls it. An
# earlier draft used the activity's name for the function's body, which would send
# an implementer to open `worktree.py`, fail to find `prepare_worktree`, and either
# hunt or edit the activity instead. Line numbers below were always correct; only
# the name was wrong.
#
# READ THIS BEFORE DECIDING THE GUARD IS MISSING — IT IS NOT, AND IT CHECKS THE
# WRONG PROPERTY. `ensure` (`factory/workgraph/worktree.py`)
# already refuses a stale pin: "A recorded pin is reused only when it is still an
# ancestor of the target's current landing-branch head (US1 FR-001); otherwise
# the worktree is rebuilt and the old branch is archived, never deleted." The
# implementation is `if _is_ancestor(repo, recorded.base_ref)` (`:365`).
#
# THAT GUARD CATCHES DIVERGENCE. IT CANNOT CATCH STALENESS. A base three landings
# behind the landing branch **is** an ancestor of it — that is precisely what
# "behind" means. So the check passes, the worktree is reused, and the node is
# verified against a tree that is valid history and unmergeable in practice. The
# guard answers "is this pin still real?" when the question that decides a
# landing is "is this pin still current?".
#
# MEASURED. A story passed everything — four gates, the judge, 7/7 scenarios —
# and then failed immediately when pushed to a PR against the real landing
# branch. Its merge-base was three landings stale and had never seen a test file
# a sibling story introduced. Both halves of the loop scored it correct, because
# both read the worktree and the worktree was internally consistent. Neither has
# any notion of how old the base is.
#
# THE FIX BELONGS AT DISPATCH, AND THE MODULE ALREADY SAYS SO. The docstring at
# `:1-9` is emphatic that a worktree is "created once, reused across attempts"
# and that "rebuilding or rebasing between attempts would move the goalposts
# mid-node, which is the failure 002's criteria snapshot exists to prevent (R5)."
# This spec does not touch that. It adds a currency test at exactly the place the
# module already rebuilds for a failed validity test — `ensure`, at
# dispatch — so the two checks sit side by side and the between-attempts
# continuity is untouched.
#
# AND A PASS CANNOT BE AUDITED AGAINST WHAT IT MEASURED. `PreparedWorktree`
# knows its `base_ref`; the verification row does not carry it. So a PASS records
# that the node passed, not what it passed against, and the stale-base case is
# invisible in the record even after the fact.
#
# THE SECOND FINDING IS THE OTHER SIDE OF THE SAME PIN. Having diagnosed a
# missing environment fact, the natural operator move is to write it into the
# standards document and let the next attempt pick it up. That does not work: the
# retry reuses the pinned tree, and the prompt tells the agent to read the
# standards path "in this worktree" (`factory/workgraph/prompt.py:224`).
# Measured: after the documentation commit landed, the live worktree still had
# zero occurrences of the new text, and attempts 4, 5 and 6 each re-read the same
# stale document lacking the one fact they needed. The standards document is by
# construction not the node's work product, which is what makes it safe to
# resolve per attempt without moving any goalpost.
#
# NOT IN SCOPE. This spec does not rebase or rebuild a worktree between attempts,
# does not change the criteria snapshot, does not add an `ergane build refresh`
# verb, and does not change what `_is_ancestor` decides for the validity test.
---

# Feature Specification: a verified tree is the tree that will merge

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

The factory verifies a node against its worktree, and nothing in the loop knows
how old that worktree's base is. Two consequences:

1. **A PASS can be unmergeable by construction.** Gates and judge both read the
   worktree, the worktree is internally consistent, and neither has a notion of
   currency. The existing pin guard tests whether the base is still *in* the
   landing branch's history — a test a stale base passes trivially.
2. **The record cannot say what was measured.** The base SHA is known at
   preparation and absent from the verification row, so a PASS that could never
   have landed looks identical to one that could.

And the same pin makes an operator's correction unreachable: a standards fix
landed on the landing branch does not exist in a tree branched before it, so the
next attempt reads the old document.

## The rule this spec is asking for

**A node is verified against a base current enough to merge, the record says
which base that was, and the standards document an attempt reads is the one on
the landing branch now.**

### What this spec is not

It is not a rebase between attempts. That continuity is deliberate, argued in the
module's own docstring, and this spec preserves it. Every change here happens at
dispatch, beside the validity check that already rebuilds there.

It is not a change to the criteria snapshot. What a node is scored against stays
pinned; where its base sits does not.

It is not a refresh verb. Giving the operator a way to rebase a running node is a
reasonable want and a different spec.

## User Scenarios & Testing

### User Story 1 - A worktree too far behind is rebuilt at dispatch (Priority: P1)

As an operator, a node is not verified against a base that cannot merge.

**Why this priority**: P1 and it depends on nothing. It is the defect, and the
place to fix it already exists.

**Acceptance Scenarios**:

1. **Given** a recorded pin that is an ancestor of the landing-branch head but
   behind it by more than the configured tolerance, **When** the worktree is
   prepared, **Then** it is rebuilt and the old branch is archived — proven by a
   committed test.
2. **Given** a recorded pin at or within the tolerance of the landing-branch
   head, **When** the worktree is prepared, **Then** it is returned untouched —
   proven by a committed test. Reuse is the rule and this story narrows it, not
   replaces it.
3. **Given** a recorded pin that is not an ancestor at all, **When** the worktree
   is prepared, **Then** it is rebuilt exactly as it is today — proven by a
   committed test. The validity check keeps its current behaviour.
4. **Given** an existing worktree, **When** a second attempt of the same node
   opens it, **Then** it is returned untouched regardless of what the landing
   branch has done since — proven by a committed test. The currency test runs at
   dispatch, never between attempts.
5. **Given** an explicit `base_ref` supplied by a caller, **When** the worktree is
   prepared, **Then** the caller's instruction is honoured without a currency
   test — proven by a committed test. An explicit pin is already documented as
   the caller's authority.

### User Story 2 - The record says what the verdict was measured against (Priority: P1)

As an operator, a PASS names the base it was measured on, so a verdict can be
audited after the fact.

**Why this priority**: P1. Without it US1 prevents the next occurrence and leaves
every past and future verdict unauditable.

**Acceptance Scenarios**:

1. **Given** a verified attempt, **When** its row is written, **Then** the row
   carries the base the worktree was pinned to — proven by a committed test.
2. **Given** that attempt, **When** the operator reads the node's status,
   **Then** the base and the landing branch's current head are both shown —
   proven by a committed test. One line makes the stale-base case visible in
   seconds.
3. **Given** rows written before this change, **When** they are read, **Then**
   the base reads as unknown rather than as a wrong value — proven by a
   committed test.

### User Story 3 - An attempt reads the standards on the landing branch (Priority: P2)

As an operator, a correction I land reaches the next attempt of a running node.

**Why this priority**: P2 — it changes no verdict — but it is the difference
between a documented fix arriving and three further attempts re-reading a
document that lacks it.

**Acceptance Scenarios**:

1. **Given** a standards document updated on the landing branch after a node was
   dispatched, **When** the node's next attempt is prepared, **Then** the
   standards text the prompt refers to is the updated one — proven by a committed
   test.
2. **Given** a landing branch whose standards document cannot be read, **When**
   the attempt is prepared, **Then** the pinned tree's copy is used and the
   fallback is reported — proven by a committed test. A node must not fail to
   start because a document could not be fetched.
3. **Given** an attempt prepared this way, **When** the archived prompt is read,
   **Then** it records which source the standards came from — proven by a
   committed test.
4. **Given** a target repository declaring no standards path, **When** an attempt
   is prepared, **Then** behaviour is unchanged from today — proven by a
   committed test.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
```

US1 and US2 both change `factory/workgraph/worktree.py` — US1 the currency test,
US2 the base carried onto the record — and are serialised on file ownership
rather than on logic. US3 changes the prompt assembly and is independent of both.

## Requirements

- **FR-001**: `ensure` (`factory/workgraph/worktree.py`) MUST rebuild a worktree whose recorded pin is
  behind the landing-branch head by more than a configured tolerance.
- **FR-002**: A pin within the tolerance MUST be reused untouched.
- **FR-003**: The existing validity check MUST keep its current behaviour for a
  pin that is not an ancestor.
- **FR-004**: The currency test MUST run only when a worktree is prepared for
  dispatch, never between attempts of a prepared node.
- **FR-005**: An explicit caller-supplied `base_ref` MUST be honoured without a
  currency test.
- **FR-006**: The verification row MUST carry the base the worktree was pinned
  to, and rows predating this MUST read as unknown.
- **FR-007**: The operator's status view MUST show that base beside the landing
  branch's current head.
- **FR-008**: An attempt's standards text MUST be resolved from the landing
  branch, falling back to the pinned tree's copy and reporting the fallback when
  the landing branch cannot be read.
- **FR-009**: The archived prompt MUST record which source the standards came
  from.
- **FR-010**: Every story MUST leave the criteria snapshot and the
  reuse-across-attempts rule (`factory/workgraph/worktree.py:1-9`) unchanged.

## Success Criteria (summary)

- A node cannot pass four gates and a judge on a tree that its own landing branch
  would reject on the first push.
- A verdict names the base it was measured on, so "verified against `<sha>`,
  landing branch is at `<sha>`" is a line rather than an investigation.
- A standards correction landed during a running epic reaches that epic's next
  attempt.
