---
state: draft
# HELD ready -> draft 2026-08-19 5:45 PM CT, BEFORE ANY DISPATCH, by the same
# operator session that wrote this spec ninety minutes earlier. A twelve-agent
# adversarial pre-dispatch review found 68 defects across 067/068/069 rated
# would-cost-an-attempt. Dispatching as written would have burned most of nine
# nodes. This returns to `ready` only after the findings are applied AND a
# re-review comes back clean.
#
# The classes found, so the rework is checkable rather than a matter of taste:
#
#   - LINE ANCHORS SYSTEMATICALLY OFF BY ONE OR TWO. Cited from grep context
#     rather than from opened files. `ladder.py:88` is a comment line and the
#     assignment is at :89; `:122` is `_debugger_cycles_spent`, while
#     `_attempts_spent` is at :111; `:100-106` is a def plus docstring, not the
#     comparison; `workflow.py:1459` is a closing paren and the conversion is at
#     :1460-1463; `escalation/workflow.py:395-399` is the EXPIRY fail-safe
#     branch, not the operator-KILL path the task sends an implementer to.
#   - CENTRAL FACTUAL CLAIMS FALSE. 068 asserts `reset` is the ONLY build verb
#     keyed by a compiled-artifact path. `start` and `salvage` are too, which
#     makes FR-010 unachievable as written and its family test unpassable.
#   - A PRESCRIBED RED TEST THAT DOES NOT REPRODUCE. A reviewer executed 068's
#     trap-6 recipe against the real tree and got a different result than the
#     trap asserts.
#   - A CONTROL TEST STRUCTURALLY UNABLE TO FAIL, proved by mutation.
#   - STORIES DECLARED INDEPENDENT THAT SHARE A FILE, in all three specs.
#
# The lesson, recorded where the next drafter meets it: A SPEC DRAFTED FROM GREP
# OUTPUT RATHER THAN FROM OPENED FILES READS AS AUTHORITATIVE AND IS NOT. Every
# anchor above was produced by reading `grep -n -A` context and miscounting the
# offset, which is invisible to the drafter and fatal to the implementer. The
# review cost fifteen minutes and caught what would have cost a night.
# Drafted 2026-08-19 5:40 PM CT by an operator session, from the same
# build-session report that produced 067 and 068. Flipped straight to `ready` at
# the operator's instruction; 063 and 064 were held to draft to let the P0 set
# through.
#
# WHY THIS MATTERS MORE HERE THAN THE REPORT MAKES IT LOOK. The reporter hit this
# on a five-story spec with a three-way fan-out and lost an entire node's ladder
# to it -- us4 exhausted with ZERO code defects, purely because us3 and us5 kept
# landing first. This factory has not felt it because it has run at
# `max_concurrent_epics: 1` with a node cap of 1 for most of its life, so
# siblings rarely race. The moment the cap goes up -- which is the entire point of
# the factory -- every fan-out that shares a file meets this.
#
# Verified against the tree before drafting, 2026-08-19:
#
#   - `factory/verify/models.py:645-647` -- max_attempts: 3, max_judge_retries: 2,
#     debugger_cycles: 1. The SHIPPED DEFAULT survives zero sibling landings for a
#     node that also needs its debugger rung for anything else.
#   - `factory/verify/ladder.py:111-119` -- `_attempts_spent` counts every record
#     whose persona is not the debugger. A rejection-driven recovery is such a
#     record, so a landing rejection costs an attempt AND a debugger cycle.
#   - `factory/workgraph/workflow.py:2163`, `:2254`, `:2539-2565`, `:2629` -- the
#     rejection path. `:2539-2565` already reasons about a recovery being futile
#     when the tree is identical to the one the queue rejected, and carries
#     `rejected_tip`. So the code ALREADY distinguishes "the base moved" from
#     "the tree is unchanged" in one place; it just does not price them
#     differently.
#   - `ergane build reset` (`factory/cli/nouns/build.py:878-900`) reads and
#     archives LOCAL state only. Nothing in it touches the forge.
#
# Filed as findings before drafting:
#   verify/a-landing-rejection-caused-by-a-sibling-landing-is-priced-as-a-code-defect
#   mergequeue/a-reset-epic-is-blocked-by-its-own-stale-pr-and-remote-branch
#
# RELATED AND ALREADY OPEN, same family, deliberately not folded in:
#   ci/ci-failure-never-reaches-an-agent
#   process/concurrent-epics-defeat-the-whichever-lands-second-reuse
---

# Feature Specification: the world moving is not the code being wrong

**Created**: 2026-08-19

## The gap, stated precisely

The ladder is the factory's budget for **code that is wrong**. It gives a
struggling agent more attempts, then a debugger, then a person. That is the right
shape for a wrong diff.

It is charged for something else entirely: **a correct diff whose base moved.**

When a sibling node lands while this node's pull request is enqueued, the
rejection is not evidence about the code. Nothing was learned. The remedy is a
rebase, which the conflict debugger performs well — the reporter singles it out
as one of the system's best parts. But performing it costs a debugger cycle *and*
an attempt, and at the shipped default (`debugger_cycles: 1`) a node survives
essentially no sibling landings.

The reported instance is clean: us3, us4 and us5 all legitimately edit one
frontend file, the spec fans them out concurrently after us2, and **us4 exhausted
its entire ladder with zero code defects.** Raising `debugger_cycles` to 3
mid-build was mandatory, not tuning.

This factory has not felt it because it has run one node at a time. That is a
property of this operator's caution, not of the product.

## The second half: a dead run's forge state blocks its own rebuild

After kill + reset + redispatch, the rebuilt node's push was rejected
non-fast-forward: the previous run's `origin/factory/<epic>/<node>` still existed
and its pull request was still open. The consumer agent closed the PR and deleted
the branch by hand, twice.

`ergane build reset` archives local branches and never touches the forge. That is
consistent with its documented job — a terminated epic's *survivors* — but the
factory owns the `factory/<epic>/<node>` namespace by construction, so there is
no ambiguity about whether it may clean it.

Grouped with the pricing defect because both are what stands between a killed or
raced epic and a working relaunch.

## User Scenarios & Testing

### User Story 1 - A moved base costs a rebase, not an attempt (Priority: P1)

As an operator, a node whose landing was rejected only because a sibling landed
first rebases and requeues without spending the budget that exists for wrong
code.

**Why this priority**: P1. It is what exhausted a defect-free node, and it is the
thing that makes concurrent fan-out unusable at the shipped default.

**Independent Test**: reject a node's landing for a moved base, and assert the
ladder's spent counts are unchanged.

**Acceptance Scenarios**:

1. **Given** an enqueued landing rejected because the base moved, **When** the
   node recovers, **Then** **all three** of the ladder's attempt count, the
   debugger-cycle count and the landing's `recovery_cycles` are unchanged —
   proven by a committed test asserting all three directly. There are two
   budgets on this path and today a moved base spends one of each: a recovery
   increments `recovery_cycles` (`factory/workgraph/workflow.py:2325`) **and**
   appends an `AttemptRecord` the ladder counts (`:2502-2508`). A fix that
   frees only one leaves the node dying at the other.
2. **Given** the same, **When** the node recovers, **Then** it rebases and
   requeues — proven by a committed test asserting the requeue happened, not
   merely that no budget was spent. A node that stops cheaply is not a fix.
3. **Given** a landing rejected because the node's own tree is wrong — a failing
   required check on unchanged code — **When** it recovers, **Then** it IS
   charged exactly as today, on **both** budgets: `recovery_cycles` increments
   and the ladder records the attempt — proven by a committed test asserting
   both. This is the control, and without it the story could be satisfied by
   never charging anything. Assert both, or the control only covers the budget
   the implementer happened to think about.
4. **Given** a rejection whose recovery would produce a tree identical to the one
   the queue already rejected, **When** the node decides, **Then** it does not
   requeue the same tree — proven by a committed test. The existing reasoning at
   `factory/workgraph/workflow.py:2539-2565` already covers this and must
   survive.
5. **Given** repeated moved-base rejections, **When** they recur, **Then** the
   free rebase path is bounded — proven by a committed test asserting a limit.
   An unbudgeted path with no bound converts a bounded failure into an unbounded
   one, and a node whose siblings land forever must eventually stop.
6. **Given** the diff, **When** the classification is inspected, **Then** it
   distinguishes rejections by their cause rather than by a retry count or a
   string match on a message — proven by a committed test over at least two
   distinct moved-base causes and one code-fault cause.

---

### User Story 2 - Siblings that will collide are not raced (Priority: P2)

As an operator, two stories whose task slices name the same file are not
dispatched concurrently, so the collision that would cost a ladder never happens.

**Why this priority**: P2. US1 makes the collision survivable; this makes it
rarer. Doing only this would leave every undeclared collision still fatal, which
is why it is second.

**Independent Test**: derive a graph whose two independent stories name a common
file and assert an ordering edge is inferred.

**Acceptance Scenarios**:

1. **Given** two stories with no declared edge whose task slices name at least one
   file in common, **When** the graph is derived, **Then** an ordering edge is
   inferred between them — proven by a committed test asserting the derived
   graph.
2. **Given** two stories whose slices share no file, **When** the graph is
   derived, **Then** no edge is inferred — proven by a committed test. A deriver
   that serialises everything has removed concurrency rather than made it safe.
3. **Given** an inferred edge, **When** the graph is read by an operator, **Then**
   the edge is distinguishable from one the spec declared, and states why it was
   inferred — proven by a committed test. An operator who cannot tell which edges
   they wrote cannot debug their own spec.
4. **Given** a spec that declares stories disjoint while their slices overlap,
   **When** it is validated, **Then** the disagreement is reported — proven by a
   committed test. 060 asserted file-disjointness its diffs contradicted and only
   landing order saved it; this is that check.
5. **Given** the inference, **When** it is applied, **Then** it can be overridden
   by an explicit declaration in the spec — proven by a committed test. An
   operator who knows two stories touch one file safely must be able to say so.

---

### User Story 3 - A reset epic can be rebuilt without hand-cleaning the forge (Priority: P2)

As an operator, resetting an epic clears the forge state that would otherwise
reject its own rebuild.

**Why this priority**: P2. Two interventions in the reported session, and the
manual remedy is known — but it is silent until a push fails, and it makes
relaunch unreliable in exactly the situation where an operator is already
recovering from something.

**Independent Test**: reset an epic with an open node PR and a remote node
branch, and assert a rebuilt node can push.

**Acceptance Scenarios**:

1. **Given** a reset epic whose node left an open pull request, **When** reset
   runs, **Then** that pull request is closed with a comment naming the reset —
   proven by a committed test asserting the forge calls made.
2. **Given** the same, **When** reset runs, **Then** the remote
   `factory/<epic>/<node>` branch is deleted or archive-renamed — proven by a
   committed test.
3. **Given** a rebuilt node after a reset, **When** it pushes, **Then** the push
   succeeds — proven by a committed test asserting the non-fast-forward rejection
   does not occur.
4. **Given** a pull request outside the `factory/<epic>/<node>` namespace, **When**
   reset runs, **Then** it is untouched — proven by a committed test. The factory
   owns its own namespace and nothing else, and a cleanup verb that reaches
   outside it is a much worse defect than the one being fixed.
5. **Given** a forge that is unreachable, **When** reset runs, **Then** the local
   reset still completes and the forge work is reported as not done — proven by a
   committed test. A cleanup verb that fails entirely because a network call
   failed leaves the operator worse off than before.

---

### Edge Cases

- **A rejection with two causes at once.** The base moved *and* a required check
  failed on the node's own code. It must be priced as a code fault: the expensive
  classification is the safe default, and US1-S6's cause-based test should
  include it.
- **A sibling that lands between the rebase and the requeue.** The free path is
  re-entered; US1-S5's bound is what stops that becoming infinite.
- **An inferred edge that creates a cycle.** Two stories each naming a file the
  other creates. The derivation must refuse naming both stories rather than
  emitting an uncompilable graph.
- **A reset run twice.** The second finds the pull request already closed and the
  branch already gone. It must succeed.

## Requirements

### Functional Requirements

- **FR-001**: A landing rejection whose only cause is a moved base MUST NOT
  consume an attempt, a debugger cycle, or a recovery cycle. All three, because
  the recovery path spends from two independent budgets and freeing one leaves
  the node exhausted by the other.
- **FR-002**: Such a rejection MUST route to a rebase-and-requeue path.
- **FR-003**: A rejection caused by the node's own code MUST continue to be
  charged as today.
- **FR-004**: The free path MUST be bounded.
- **FR-005**: Rejections MUST be classified by cause, not by retry count or by a
  message match.
- **FR-006**: The existing refusal to requeue a tree identical to one already
  rejected MUST survive.
- **FR-007**: Derivation MUST infer an ordering edge between stories whose task
  slices name a common file, and MUST NOT infer one between stories that share
  none.
- **FR-008**: An inferred edge MUST be distinguishable from a declared one and
  MUST state why it was inferred, and MUST be overridable by an explicit
  declaration.
- **FR-009**: Validation MUST report a spec that declares stories disjoint while
  their slices overlap.
- **FR-010**: `ergane build reset` MUST close the node's open pull request and
  delete or archive-rename the remote node branch, within the
  `factory/<epic>/<node>` namespace and nowhere else.
- **FR-011**: If the forge is unreachable, the local reset MUST still complete and
  the undone forge work MUST be reported.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  implements: [FR-007, FR-008, FR-009]
US3:
  depends_on: []
  implements: [FR-010, FR-011]
```

## Success Criteria

### Measurable Outcomes

- **SC-001**: Reject a landing for a moved base and paste the attempt count, the
  debugger-cycle count **and** `recovery_cycles` before and after. None of the
  three may move.
- **SC-002**: Paste the control — a code-fault rejection, still charged. Without
  it SC-001 is satisfiable by charging nothing.
- **SC-003**: Land a three-way fan-out sharing one file at the shipped default
  `debugger_cycles: 1` and paste the result. This is the reported failure,
  reproduced and survived.
- **SC-004**: Derive a graph whose two independent stories name one common file
  and paste the inferred edge, then paste a derivation over disjoint stories
  showing no edge.
- **SC-005**: Reset an epic with an open node PR and a remote node branch, paste
  the forge calls, and push a rebuilt node.

## Assumptions

- The conflict debugger's rebase behaviour is good and is not in scope. The
  reporter: "given landing-rejection evidence naming the conflicted file, the
  recovery attempt genuinely rebased onto `origin/main`, took the right side, and
  re-verified. When it had cycles available, it needed no help at all." This spec
  changes what that recovery *costs*, not what it does.
- The merge queue remains the gate. Nothing here proposes landing outside it.
- `depends_on_merged` remains the edge type for contention. US2 infers edges of
  that kind rather than inventing a third.
