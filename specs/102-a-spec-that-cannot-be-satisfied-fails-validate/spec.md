---
state: landed
fixes:
# ATTESTED 2026-08-30 11:52 PM CT by the operator session, in away mode.
# All three stories are on ergane-buildout, each on its first attempt: US1
# af13ebd (#399), US3 6f7347e (#400), US2 25820d3 (#401). epic-102 COMPLETED at
# 2026-08-31T00:53:09Z with every landing MERGED. Confirmed by `ergane spec
# landed <this dir> --default-branch ergane-buildout`, which observes all three.
# Caught by an away-tick sweep, not by the epic's own completion — nothing
# announces that a finished epic is still unattested, and `ergane status` kept
# listing 102 as `ready dispatchable` for the four hours between its epic
# completing (00:53:09Z) and this sweep finding it.
  - verify/the-judge-can-invite-a-node-to-rewrite-its-own-acceptance-criterion-without-firing-criteria-drift
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# Slot reserved — empty and untracked — by the spec-routing session 2026-08-23.
#
# THE AUTHORING-TIME HALF. Spec 116 puts the gate results in the judge's prompt,
# which is the runtime fix for a scenario whose Then-clause names a runtime
# outcome. This spec is the other half of the same defect: a criterion that
# *nothing* can prove — no diff, no gate — should be refused when it is written,
# not discovered at attempt six.
#
# THE MEASURED COST OF NOT DOING THIS. One story deadlocked for a combined
# fifteen attempts on a single scenario. The reporter's own analysis is worth
# quoting because it assigns the blame accurately: "Half of this was the
# operator's — the scenario was phrased as a runtime outcome, the only one across
# three specs phrased that way and the only one that deadlocked." An authoring
# check would have cost one refusal at `spec validate` time.
#
# THE INTERACTION WITH 116 IS LOAD-BEARING AND MUST NOT BE GOT WRONG. Once the
# judge is shown the gate results, a Then-clause naming a *gate* outcome becomes
# scoreable and must NOT be refused here. What stays unprovable is a runtime
# outcome no declared gate measures. So this spec's refusal is not "the Then
# clause mentions running something" — it is "nothing in this repository's
# declared verification can produce evidence for this clause". A check written
# without that distinction refuses exactly the scenarios 116 just made
# answerable, and the two specs cancel out.
#
# THE SECOND FINDING: THE JUDGE OFFERS TO LOWER THE BAR. A criterion was
# unsatisfiable as drafted — an operator defect. The attempt implemented the
# correct geometry, hedged the proof, and named the deviation in its own diff
# header. The judge refused it, correctly, and its feedback offered two
# remediation paths, the second being "reconcile the scenario text with…". The
# outcome in that instance was right, which is exactly why it is worth filing:
# the mechanism that produced a good result there is the one that produces a
# silently lowered bar elsewhere, and `criteria_drift` did not fire because
# nothing had drifted — the judge had merely proposed that it should. The judge's
# independence is the factory's only defence against a node weakening its own
# bar, and a judge that suggests the bar move is not independent of it.
#
# NOT IN SCOPE. This spec does not add a judge outcome, does not change what the
# judge is shown (116 owns that), does not change `criteria_drift`'s hashing, and
# does not refuse a spec for any reason other than an unprovable criterion.
---

# Feature Specification: a spec that cannot be satisfied fails validate

**Created**: 2026-08-28
**Depends on**: nothing outside this spec. The interaction with 116 is a
correctness constraint on US1 rather than a dependency: US1 must consult the
declared gates, which exist whether or not 116 has landed.

## The gap, stated precisely

An acceptance criterion is a contract between an operator and a judge, and
nothing checks that the contract is satisfiable before it is dispatched. Two
consequences:

1. **An unprovable criterion is discovered by exhaustion.** The scenario is
   scored, fails, is scored again, fails identically, and the ladder empties. The
   information that it could never have passed is available the moment it is
   written.
2. **The judge is allowed to propose moving the bar.** Its remediation feedback
   can suggest reconciling the scenario text with the implementation, which is
   the one remedy a judge must never offer, because the judge is the only thing
   standing between a node and its own acceptance criteria.

## The rule this spec is asking for

**A criterion nothing can prove is refused when the spec is validated, and the
judge may report that a criterion is unsatisfiable but never propose changing
it.**

### What this spec is not

It is not a restriction on what a Then-clause may say. A clause naming a gate
outcome is legitimate and, with the gate results in the judge's prompt, provable.
The refusal is for clauses nothing declared can evidence.

It is not a judge outcome. "The diff cannot show me this" as a first-class
verdict is a real want and belongs elsewhere.

It is not a change to `criteria_drift`. Its hashing is correct; it did not fire
because nothing drifted.

## User Scenarios & Testing

### User Story 1 - An unprovable criterion is refused at validate time (Priority: P1)

As an operator, a scenario nothing can evidence is refused when I validate the
spec, naming the clause and the reason.

**Why this priority**: P1 and it depends on nothing. It converts a fifteen
attempt deadlock into one refusal.

**Acceptance Scenarios**:

1. **Given** a spec whose Then-clause asserts a runtime outcome that no declared
   gate measures, **When** `ergane spec validate` runs, **Then** it refuses,
   quoting the clause and naming why nothing can evidence it — proven by a
   committed test.
2. **Given** a spec whose Then-clause asserts an outcome a declared gate does
   measure, **When** validate runs, **Then** it passes — proven by a committed
   test. **This is the scenario that keeps this spec and 116 from cancelling
   out**, and it must be written even though 116 may not have landed.
3. **Given** a spec whose Then-clauses are all provable from a diff, **When**
   validate runs, **Then** its verdict is unchanged from today — proven by a
   committed test over the existing corpus.
4. **Given** a target repository declaring no gates, **When** validate runs on a
   spec asserting a runtime outcome, **Then** the refusal says that no gate is
   declared — proven by a committed test. A repository with nothing to measure
   with is a different conversation from one whose gates do not cover the claim.
5. **Given** a refused clause, **When** the operator reads the refusal, **Then**
   it suggests how to make the criterion provable — proven by a committed test.
   A refusal that only forbids teaches nothing.

### User Story 2 - Validate says what the judge will see (Priority: P2)

As an operator, I can ask a spec what evidence its judge will have, before I
spend an epic finding out.

**Why this priority**: P2. US1 refuses the worst case; this makes the rule
learnable rather than a wall an author meets repeatedly.

**Acceptance Scenarios**:

1. **Given** any spec, **When** validate runs, **Then** it reports what the judge
   will be shown for it — the diff, the criteria, and the declared gates whose
   results will accompany them — proven by a committed test.
2. **Given** a spec whose scenarios are all provable, **When** validate runs,
   **Then** the report states that and adds no refusal — proven by a committed
   test.
3. **Given** a spec with one borderline clause, **When** validate runs, **Then**
   the report names that clause without refusing it — proven by a committed test.
   Not every hard-to-prove clause is an unprovable one, and an author is better
   served by a warning than by a false refusal.

### User Story 3 - The judge may not propose moving the bar (Priority: P1)

As an operator, a judge tells me a criterion cannot be satisfied; it does not
offer to change it.

**Why this priority**: P1. The judge's independence is the only defence against a
node weakening its own acceptance criteria, and a judge that suggests the
criterion move has already compromised it — even when, as in the measured case,
the immediate outcome was correct.

**Acceptance Scenarios**:

1. **Given** the judge's instructions, **When** they are read, **Then** they
   forbid proposing a change to the acceptance criteria as a remediation —
   proven by a committed test.
2. **Given** a verdict whose feedback proposes changing a criterion, **When** it
   is composed, **Then** the proposal is recorded and does not reach the next
   attempt's prompt — proven by a committed test. A remediation an agent is told
   to follow is a remediation an agent will follow.
3. **Given** a verdict reporting that a criterion appears unsatisfiable, **When**
   it is composed, **Then** that report is preserved and surfaced to the operator
   — proven by a committed test. Saying a criterion cannot be met is exactly what
   the judge should do; proposing the edit is not.
4. **Given** a verdict whose feedback proposes no criterion change, **When** it is
   composed, **Then** it reaches the next attempt unchanged — proven by a
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

US1 and US2 both change the `spec validate` composition in
`factory/cli/nouns/spec.py` and are serialised on file ownership. US3 changes the
judge's instructions and its verdict handling in `factory/verify/judge.py`, and is
independent of both.

## Requirements

- **FR-001**: `ergane spec validate` MUST refuse a Then-clause asserting a runtime
  outcome that no declared gate measures, quoting the clause.
- **FR-002**: A Then-clause asserting an outcome a declared gate measures MUST
  NOT be refused.
- **FR-003**: A spec whose clauses are all provable from a diff MUST validate
  exactly as it does today.
- **FR-004**: A refusal in a repository declaring no gates MUST say so
  specifically.
- **FR-005**: A refusal MUST suggest how to make the criterion provable.
- **FR-006**: Validate MUST report what evidence the judge will be shown for the
  spec.
- **FR-007**: A borderline clause MUST be named without being refused.
- **FR-008**: The judge's instructions MUST forbid proposing a change to the
  acceptance criteria.
- **FR-009**: A proposal to change a criterion MUST be recorded and MUST NOT
  reach the next attempt's prompt.
- **FR-010**: A judge's report that a criterion appears unsatisfiable MUST be
  preserved and surfaced to the operator.
- **FR-011**: Every story MUST leave `criteria_drift`'s hashing unchanged.

## Success Criteria (summary)

- The scenario that deadlocked a story for fifteen attempts is refused by
  `spec validate` in one run, with a suggestion for how to phrase it provably.
- A clause naming a gate outcome — the case 116 makes answerable — validates
  cleanly, so the two specs compose instead of cancelling.
- A judge can say a criterion cannot be met, and cannot tell an agent to change
  it.
