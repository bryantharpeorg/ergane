---
state: ready
fixes:
  - roadmap/a-killed-nodes-branch-survives-and-loops-every-redispatch
  - relaunch/a-killed-epics-pushed-node-branch-survives-on-origin-and-fails-the-relaunch-after-verification
# DRAFTED 2026-09-01 9:15 PM CT by the operator session, against ergane-buildout at
# bc3c464, hours after the loop below ran for four and a half of them. Every
# file:line cited in spec.md and plan.md was read from that commit and verified,
# not recalled — which is 072's whole lesson, and 072 landed today.
#
# THE LOOP, MEASURED. On 2026-09-01 the roadmap dispatched
# 072-a-stale-anchor-fails-validate-not-the-attempt five times to land three
# stories. Run 1 (12:29Z-14:23Z) landed US2 and US1; its US3 reached
# verified=true and died in the landing path, and the operator answered KILL at
# 14:24Z. That kill left `refs/heads/factory/072-.../us3` on origin at 032c946d.
#
# Runs 2, 3 and 4 (14:34Z, 16:04Z, 17:34Z) then each re-dispatched US3, built it
# clean on kimi attempt 1, passed the gates, passed the judge, reached
# verified=true — and died at the push:
#
#     WorktreeError: push of 'factory/072-.../us3' to origin failed
#     ! [rejected] ... (non-fast-forward)
#
# Each failure opened an EscalationWorkflow (355a037212f8, f97b8e0eedaa,
# 706ec5e682ab); all three expired unanswered at the 3600s window; each expiry
# killed the node again and re-armed the roadmap's next scan. The loop was
# self-sustaining and was stopped by pausing the schedule, not by anything the
# factory did. Once the ref was cleared by hand, run 5 landed US3 on attempt 1.
#
# COST: three complete builds producing nothing, three of the operator's
# escalation windows consumed by a cause no button on the menu could address,
# and PR #422 left open and DIRTY against the stale ref for five hours.
#
# WHY IT IS EXPENSIVE RATHER THAN MERELY WRONG. The precondition that fails is
# knowable offline, before a key is issued — and it is checked at the LAST step,
# after the agent, the gates and the judge are all paid for. Every cycle pays
# full price to discover a fact one `git ls-remote` would have told it for free.
#
# THE REQUIREMENT THAT ARMS IT, AND WHY IT IS NOT ACTUALLY IN THE WAY.
# `factory/workgraph/workflow.py:3584` records the contract in one line: "1h
# silence or `KILL` ends the node KILLED, branch preserved (FR-008)". That is
# 003-merge-queue FR-008 (`specs/003-merge-queue/spec.md:153`): "Node branches
# MUST never be deleted by failure paths; killed or rejected work remains
# reachable on its branch."
#
# Read as a rule about NAMES, that requirement mandates the loop. Read as a rule
# about REACHABILITY — which is what it says — it is already satisfied by the
# archive bargain 100-US1 built and landed: rename the branch to
# `archive/factory/<epic>/<node>/`, put that archive on the remote under its own
# name, and only then remove the head. Nothing becomes unreachable; the live
# name is freed. `factory/workgraph/worktree.py:1558` does exactly this on the
# operator's `reset` path and argues the bargain in its own docstring.
#
# So this spec adds no new licence to destroy work. It extends a reconciliation
# the tree already contains to the one path that never got it.
#
# THIS DEFECT CLASS HAS NOW BITTEN THREE TIMES: 070-US1 (2026-08-19, a verified
# story lost after a relaunch), the ergane-web hand-over's [N30] (2026-08-28),
# and 072-US3 (2026-09-01, four cycles). It is a candidate for promotion into
# `.specify/memory/constitution.md` with a `docs/decisions.md` entry, and that
# promotion is an operator act this spec does not perform.
#
# NOT IN SCOPE. This spec does not add a button to the escalation menu, does not
# change what `KILL` means, does not touch the merge queue or the landing poller,
# does not change `max_recovery_cycles` or any ladder dial, and does not force-push
# or delete an archive ref under any circumstance.
---

# Feature Specification: a killed node leaves no ref to collide with

**Created**: 2026-09-01
**Depends on**: nothing outside this spec.

## The gap, stated precisely

A node killed inside the workflow leaves the branch it pushed sitting in the live
`factory/<epic>/<node>` namespace on origin. Nothing clears it, and nothing looks
for it before the next dispatch of the same node.

That next dispatch branches fresh from the current landing head, so its history
shares no ancestor with the survivor of the same name. Git refuses the push
non-fast-forward, and it refuses it *after* the agent has run, the gates have
passed and the judge has scored — the whole cost of the story, spent to discover
a fact that was true before dispatch.

Three failures follow, in the order they cost a story:

1. **Nothing refuses at dispatch.** `landing_readiness_preflight`
   (`factory/workgraph/preflight.py:702`) already collects the landing
   preconditions offline, epic-wide, on both dispatch surfaces. "A remote branch
   this node's push would have to fast-forward over" is not among its checks,
   though it is knowable with one `git ls-remote` for the whole graph.
2. **The kill abandons the ref rather than archiving it.** `_close_out`
   (`factory/workgraph/workflow.py:3083`) ends the node and leaves the remote
   branch untouched. The archive bargain that would free the name while keeping
   the work reachable exists at `factory/workgraph/worktree.py:1558` and is
   reachable only from the operator's `reset`, never from the kill.
3. **The escalation cannot name the cause.** A node dying non-fast-forward
   escalates with a menu of `RETRY | KILL | PAUSE_EPIC | KILL_EPIC`. `RETRY`
   re-runs the identical failure, `KILL` re-arms the loop, and neither
   `PAUSE_EPIC` nor `KILL_EPIC` clears the ref. The operator is asked to choose
   on a one-hour clock among four options, none of which addresses the cause,
   and the message does not say which ref is in the way or what would be safe.

## The rule this spec is asking for

**A node that would collide with a surviving ref is refused before an agent is
paid, a node the factory ends leaves its work archived rather than abandoned in
the live namespace, and an operator asked to decide is told which ref is in the
way and what would be safe to do about it.**

### What this spec is not

It is not a new licence to delete work. 003 FR-008 stands unchanged: every commit
reachable from a killed node's branch stays reachable. What changes is that it
stays reachable under an archive name instead of under the live one, which is the
bargain 100-US1 already struck and this spec extends.

It is not a new escalation button. The menu keeps its four choices. US3 changes
what the message *says*, not what the operator may press, because widening the
choice set is a change to the operator channel's contract and deserves its own
decision.

It is not a change to the push itself. `push_branch`
(`factory/workgraph/worktree.py:554`) keeps its behaviour and its error text; the
non-fast-forward refusal stays the enforcement. US1 is the *report* that makes
reaching that enforcement rare.

It is not a fix for `temporal workflow terminate`, which bypasses the kill
sequence entirely and is deliberately left alone (`interpreter/cancel-bypasses-
kill-sequence`).

## User Scenarios & Testing

### User Story 1 - A dispatch refuses on a ref it would collide with (Priority: P1)

As an operator, when a node's remote branch would refuse that node's push, I am
told before anything is dispatched and nothing is spent.

**Why this priority**: P1 and it depends on nothing. It is the complete fix for
the *loop* on its own: even with the ref never cleared, an epic that refuses
before it spends cannot spin. US2 stops the ref being created; US1 stops it
costing anything, and does so for refs that arrive by routes US2 does not cover —
a salvage push, an operator's own push, a `temporal workflow terminate`.

**Independent Test**: Point a graph at a target repo whose origin carries a node
branch unrelated to the landing head, run the preflight, and read the finding.

**Acceptance Scenarios**:

1. **Given** a graph whose node `us1` has a branch on origin whose tip is not an
   ancestor of the landing head, **When** `landing_readiness_preflight` runs,
   **Then** it returns a failing `PreflightFinding` naming `us1`, the full ref,
   the ref's short sha, and the landing head it was compared against, and the
   detail ends with a sentence stating that nothing was dispatched.
2. **Given** a graph whose node `us1` has a branch on origin whose tip **is** an
   ancestor of the landing head — the ordinary state of every node of a completed
   epic — **When** the preflight runs, **Then** it returns no finding for `us1`,
   because that push fast-forwards.
3. **Given** a graph of sixteen nodes on a target repo whose origin carries no
   `factory/<epic>/*` refs at all, **When** the preflight runs, **Then** it
   consults the remote exactly once, asserted on the call count and not on
   elapsed time.
4. **Given** a target repo whose origin cannot be reached, **When** the preflight
   runs, **Then** it returns an informational finding naming the unreachable
   remote and does not fail the dispatch, because a preflight that starts
   refusing on a network hiccup is a worse defect than the ref it checks for.
5. **Given** one fixture graph, **When** the roadmap's pre-dispatch activity
   (`factory/activities/roadmap_activities.py:626`) and `ergane build start`'s
   preflight (`factory/workgraph/cli.py:128`) each run over it, **Then** the two
   finding lists are equal, so a second copy of this check cannot be added
   without a red test.

### User Story 2 - A node the factory ends leaves an archive, not an obstacle (Priority: P2)

As an operator, when the factory kills a node, the work it built stays reachable
and the name it occupied is free for the next attempt.

**Why this priority**: P2 and it depends on nothing. US1 makes the collision
cheap; this makes it stop happening. Second because a refusal that costs nothing
is worth more than a cleanup that has to be right about reachability, and because
this story is the one that touches 003 FR-008.

**Independent Test**: Kill a node whose branch is on origin, then read origin's
refs: the live name is gone and an archive ref carries the same tip.

**Acceptance Scenarios**:

1. **Given** a node whose branch is on origin and whose tip is reachable from an
   archive ref of that node, **When** the workflow ends it KILLED, **Then** the
   live `factory/<epic>/<node>` ref is gone from origin, an
   `archive/factory/<epic>/<node>/<short-sha>` ref on origin carries that tip,
   and the node's terminal record names both.
2. **Given** a node whose remote tip is **not** reachable from any archive ref of
   that node, **When** the workflow ends it KILLED, **Then** the live ref is left
   in place and reported, because reachability decides the deletion and never the
   fact that a kill ran.
3. **Given** a node whose remote is unreachable at kill time, **When** the
   workflow ends it KILLED, **Then** the kill completes, the node reaches its
   terminal state, and the surviving ref is reported as an action the operator
   still owes.
4. **Given** the same node killed twice — the terminal path re-running on activity
   retry — **When** the second kill runs, **Then** it succeeds having found
   nothing to do, and no archive ref is overwritten or force-updated.

### User Story 3 - An escalation names the ref that is in the way (Priority: P3)

As an operator deciding on a one-hour clock, I am told which ref blocks this node
and whether removing it would lose anything.

**Why this priority**: P3 and it depends on nothing. With US1 and US2 landed this
escalation becomes rare, but it does not become impossible, and the hour the
operator spends on it is the most expensive hour in the system.

**Independent Test**: Compose the escalation message for a node whose terminal
reason is a non-fast-forward refusal and read what it says.

**Acceptance Scenarios**:

1. **Given** a node escalating on a push refused non-fast-forward, **When** the
   escalation message is composed, **Then** it names the full ref, its tip's short
   sha, and states whether that tip is reachable from an archive ref of the node.
2. **Given** that tip is reachable from an archive ref, **When** the message is
   composed, **Then** it carries the exact command that would clear the ref.
3. **Given** that tip is reachable from no archive ref, **When** the message is
   composed, **Then** it says so and carries no clearing command, because a
   command offered for an unarchived tip is an invitation to lose work.
4. **Given** a node escalating for any other cause, **When** the message is
   composed, **Then** it is unchanged from today's, so this story cannot alter
   escalations it is not about.

## Functional Requirements

- **FR-001**: `landing_readiness_preflight` MUST return a failing finding for
  every node whose remote branch exists and whose tip is not an ancestor of the
  landing head the node would branch from.
- **FR-002**: That finding MUST name the node, the full ref, the ref's short sha,
  and the landing head compared against, and MUST state that nothing was
  dispatched.
- **FR-003**: A remote branch whose tip IS an ancestor of the landing head MUST
  produce no finding.
- **FR-004**: The check MUST consult the remote at most once per graph, asserted
  on the call count.
- **FR-005**: An unreachable remote MUST produce an informational finding and MUST
  NOT refuse the dispatch.
- **FR-006**: Both dispatch surfaces MUST run this check through the single
  entry point, and a parity test MUST assert their finding lists are equal.
- **FR-007**: A node the workflow ends KILLED MUST archive and then clear its
  remote branch, reusing the reachability-gated clearing the reset path already
  implements rather than re-deriving it.
- **FR-008**: The clearing MUST leave the tip reachable from an archive ref on
  the remote before the live head is removed, and MUST leave the live ref in
  place and report it when no archive ref of that node makes the tip reachable.
- **FR-009**: The kill MUST complete, and the node MUST reach its terminal state,
  when the remote is unreachable; the surviving ref is reported.
- **FR-010**: Every story MUST leave archive refs intact, and MUST NOT force-push,
  delete an archive ref, or overwrite an archive ref that already exists at a
  different commit.
- **FR-011**: An escalation whose terminal cause is a non-fast-forward refusal
  MUST name the ref, its short sha, and whether the tip is archived, and MUST
  carry a clearing command only when it is.
- **FR-012**: Escalations for every other cause MUST be unchanged.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  implements: [FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012]
```

The one edge is `depends_on_merged`, and it is declared rather than left inferred
(069-US2 FR-007). US3 only *reads* `_NON_FAST_FORWARD` from
`factory/workgraph/worktree.py`, which US2 edits, so the slice they share is a
read against a write — the cheapest possible contention and also the easiest to
get silently wrong. Serialising the smallest story behind the one doing ref
surgery costs a merge cycle and removes the race entirely.
