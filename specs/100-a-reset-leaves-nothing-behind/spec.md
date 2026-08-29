---
state: ready
fixes:
  - relaunch/a-killed-epics-pushed-node-branch-survives-on-origin-and-fails-the-relaunch-after-verification
  - landing/kill-and-redispatch-leaves-a-stale-remote-node-branch-that-kills-the-next-landing
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# Slot reserved — empty and untracked — by the spec-routing session 2026-08-23.
# Two ledger keys, one mechanism: the ledger split this identity before this
# session ingested a third report of it. Both are declared here.
#
# THE SHAPE THAT MAKES THIS THE FIRST-PRIORITY DEFECT: IT IS SELF-SEALING.
# The recovery path the factory recommends — answer KILL_EPIC, let the roadmap
# re-dispatch — is what arms the mine, and the mine fires on the next *success*.
# A node went RUNNING → VERIFYING → PASSED on attempt 1 in 6m51s, then died
# pushing its branch. Any target repository that has ever killed an epic is in
# this state permanently for that node.
#
# WHY THE PUSH IS REFUSED, AND WHY GIT IS RIGHT. Answering KILL_EPIC salvages the
# node's work and pushes the branch to origin. The new dispatch branches fresh
# from the landing branch, so its `factory/<epic>/<node>` has no ancestor
# relationship with the surviving remote branch of the same name, and a plain
# non-force push is correctly refused non-fast-forward. Nothing cleans the remote
# ref up between dispatches, and nothing checks for it at dispatch time.
#
# THE LOCAL HALF IS ALREADY RIGHT, AND THAT IS THE CLUE. Teardown
# (`factory/workgraph/worktree.py:1354`) removes the directory, archives the node
# branch and deletes the sidecar, and the docstring at `:1358` is explicit that
# "the node branch remains reachable from an archive ref" — archived, never
# deleted (`:336`, FR-004). The content is preserved. The design is sound and it
# stops at the edge of the local clone: `_archive_node` (`:1369`) never touches
# origin, so the ref that actually blocks the next landing is the one nothing
# archives.
#
# THREE SEPARATE DEFECTS, FIXABLE SEPARATELY, AND THIS SPEC IS ONE PER STORY.
# (1) The stale remote ref. (2) `push_branch` runs `git push --quiet`
# (`:509`), so the one word that ends the diagnosis — "non-fast-forward" — is
# discarded; the operator gets `terminal_reason: Activity task failed` and four
# hours. (3) `PUSH_FAILED` is retryable (`factory/activities/merge_activities.py:86`)
# and a ref conflict is deterministic, so the node spends three activity attempts
# arriving at the same refusal, and is then killed along with every node
# depending on it — three PENDING siblings in the measured case.
#
# THE PRECEDENT FOR STORY 3 IS IN THE SAME FILE. The comment at
# `factory/activities/merge_activities.py:90-95` explains why the ownership
# refusal was carved out of `PUSH_FAILED`: "two repositories ... behind
# `PUSH_FAILED` would spend its three attempts arriving at the same" answer, and
# it leaves "today's retryable `PUSH_FAILED` path, untouched". A ref conflict is
# the same argument with a different cause, and this spec makes it the second
# carve-out rather than inventing a new mechanism.
#
# NOT IN SCOPE. This spec does not change what a salvage preserves, does not
# delete any archive ref, does not force-push anything ever, and does not change
# the escalation buttons themselves. It also does not change `KILL_EPIC`'s
# behaviour — the recovery path stays; it stops leaving a mine behind.
---

# Feature Specification: a reset leaves nothing behind

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

Teardown is careful about the local clone and silent about origin. The result is
a remote ref that no verb owns: the salvage put it there, teardown does not
remove it, the next dispatch does not look for it, and the push that discovers it
is refused with the reason suppressed and then retried three times before killing
the epic.

Everything needed to fix it is already true. The salvaged content is preserved
under an archive ref, so the live remote ref carries nothing unique. Git states
the reason precisely, and `--quiet` throws it away. And a non-retryable carve-out
of `PUSH_FAILED` already exists in the same module, with its rationale written
down.

## The rule this spec is asking for

**A killed dispatch leaves no ref that can refuse the next one, and a refusal
that an operator can fix in one command says so and escalates instead of killing
the epic.**

### What this spec is not

It is not a force push. Nothing here overwrites a remote ref with divergent
history; the remote branch is removed only when its content is already reachable
from an archive ref, and otherwise the operator is asked.

It is not a change to salvage. What a kill preserves, and where, stays exactly as
it is.

It is not a redesign of the escalation contract. Story 3 changes which class a
failure falls into, not what the operator may press.

## User Scenarios & Testing

### User Story 1 - A killed node leaves no remote ref behind (Priority: P1)

As an operator, killing an epic does not arm a failure that fires on the next
dispatch's success.

**Why this priority**: P1 and it depends on nothing. It is the mine itself.

**Acceptance Scenarios**:

1. **Given** a node whose branch was pushed to origin and whose epic is then
   killed, **When** teardown runs, **Then** the remote branch is removed and the
   archive ref that carries its content still resolves — proven by a committed
   test.
2. **Given** the same node, **When** a fresh dispatch of it later pushes its
   branch, **Then** the push succeeds — proven by a committed test.
3. **Given** a remote branch whose tip is *not* reachable from any archive ref,
   **When** teardown runs, **Then** it leaves the ref alone and reports what it
   declined to remove — proven by a committed test. Content nothing else holds is
   not teardown's to discard.
4. **Given** a node whose branch was never pushed, **When** teardown runs,
   **Then** it completes unchanged and reports no remote work — proven by a
   committed test.
5. **Given** teardown run twice over the same node, **When** the second run
   completes, **Then** it succeeds — proven by a committed test. Teardown is
   documented as idempotent and stays so.

### User Story 2 - A refused push says why (Priority: P1)

As an operator, a failed push tells me it was refused non-fast-forward, instead
of telling me an activity task failed.

**Why this priority**: P1, and it is the cheapest fix in the epic. The reason
cost four hours and three wrong diagnoses while git had it in hand the whole
time.

**Acceptance Scenarios**:

1. **Given** a push refused by the remote, **When** the failure is recorded,
   **Then** git's own stderr is carried into the error — proven by a committed
   test.
2. **Given** that failure, **When** the operator reads the node's terminal
   reason, **Then** it names the refusal rather than reading `Activity task
   failed` — proven by a committed test.
3. **Given** a push that succeeds, **When** it completes, **Then** it emits no
   more output than it does today — proven by a committed test. The diagnosis
   belongs on the failure path, not on every landing.

### User Story 3 - A deterministic ref conflict escalates instead of killing the epic (Priority: P1)

As an operator, a state problem I can fix in one command pages me, rather than
killing a verified node and every node waiting behind it.

**Why this priority**: P1. Retrying a deterministic refusal three times and then
killing three PENDING siblings is disproportionate to a fix that is one `git
push --delete` away.

**Acceptance Scenarios**:

1. **Given** a push refused non-fast-forward, **When** the activity fails,
   **Then** it fails non-retryably — proven by a committed test.
2. **Given** that non-retryable failure, **When** the node's next action is
   decided, **Then** it escalates rather than terminating the node — proven by a
   committed test.
3. **Given** that escalation, **When** the operator reads it, **Then** it names
   the ref, the reason, and the command that clears it — proven by a committed
   test.
4. **Given** a push that fails for a transient reason, **When** the activity
   fails, **Then** it remains retryable exactly as today — proven by a committed
   test. This story carves out one deterministic cause; it does not make pushing
   non-retryable.
5. **Given** a node that escalates on a ref conflict, **When** its siblings are
   examined, **Then** no PENDING sibling has been killed — proven by a committed
   test.

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
  depends_on_merged: [US2]
```

US1 changes teardown and US2 changes `push_branch`, both in
`factory/workgraph/worktree.py`, so they are serialised on **file ownership
rather than on logic** — raced, whichever landed second would be rejected for the
other's change. US3 changes `factory/activities/merge_activities.py` and is
serialised behind US2 for a different reason: it classifies on the stderr US2
captures, so it is a genuine logical dependency.

## Requirements

- **FR-001**: Teardown MUST remove a node's remote branch when its tip is
  reachable from an archive ref.
- **FR-002**: Teardown MUST leave a remote branch in place, and report it, when
  its tip is not reachable from any archive ref.
- **FR-003**: Teardown MUST remain idempotent and MUST complete unchanged for a
  node whose branch was never pushed.
- **FR-004**: A refused push MUST carry git's own stderr into the raised error.
- **FR-005**: A node whose push was refused MUST report a terminal reason naming
  the refusal.
- **FR-006**: A successful push MUST emit no more output than it does today.
- **FR-007**: A push refused non-fast-forward MUST fail non-retryably, following
  the carve-out precedent at `factory/activities/merge_activities.py:90-95`.
- **FR-008**: A non-fast-forward refusal MUST escalate the node rather than
  terminate it, and the escalation MUST name the ref, the reason and the
  clearing command.
- **FR-009**: A push failing for any other reason MUST remain retryable.
- **FR-010**: Every story MUST leave archive refs intact and MUST NOT introduce a
  force push anywhere in the epic.

## Success Criteria (summary)

- Answering KILL_EPIC and letting the roadmap re-dispatch is a recovery that
  works twice.
- A refused push is diagnosed from the terminal reason alone.
- A ref conflict costs one escalation, not three activity attempts, one killed
  verified node and three killed siblings.
