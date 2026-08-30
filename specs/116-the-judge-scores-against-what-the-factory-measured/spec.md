---
state: ready
fixes:
  - verify/the-judge-is-asked-to-predict-gate-outcomes-the-factory-already-measured
  - verify/a-judges-speculation-about-a-gate-overrides-that-gates-recorded-result
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# A new number rather than one of the 089-102 slots reserved on 2026-08-23:
# 102's reserved name is `a-spec-that-cannot-be-satisfied-fails-validate`, which
# is the *authoring-time* half of this defect and is its own epic. This is the
# runtime half.
#
# THE DEFECT, AND THE ONE LINE THAT PROVES IT. `judge_required(gate_results,
# output_check, criteria)` (`factory/verify/models.py`) is the guard the
# reference flow puts immediately in front of `run_judge`. It takes the gate
# results as its first argument, uses them to decide whether asking the judge can
# still change the outcome, and returns a bool. The caller then invokes
# `build_prompt(criteria, diff_text, prior_feedback=…)`
# (`factory/verify/judge.py:240`) — which has no parameter for them. The gate
# results are in the caller's hand on the line before, and are thrown away.
#
# WORSE THAN "THE JUDGE IS UNINFORMED": THE JUDGE IS ASKED TO GUESS SOMETHING
# THAT IS ALREADY TRUE BY CONSTRUCTION. `judge_required` returns True only when
# `gates_passed(gate_results)` — its docstring says so and gives the reason ("the
# gates and the output check have already decided a FAIL that no judge verdict
# could lift"). So on every code path where the judge runs at all, **every gate
# passed**. The judge is then handed a system prompt saying "if the evidence is
# not in the diff, the scenario does not pass" and asked to score scenarios whose
# Then-clauses are runtime outcomes. It reasons correctly from an information set
# that was deliberately narrowed, and the narrowing removed an answer the factory
# had already written down.
#
# MEASURED COST. One story deadlocked on exactly this, twice, for a combined
# fifteen attempts — six consecutive attempts with all four gates PASS and the
# judge failing the same scenario every time, on the grounds that a font file
# absent from the diff must be absent from the checkout. The files were in the
# base tree. `12 passed in 0.14s` was in the same record, one field away.
#
# AND ONE STEP WORSE. A separate attempt's verbatim judge reasoning asserted
# "The pytest gate would fail…" about a gate recorded PASS in the same row. That
# is unwinnable rather than merely wrong: the only way to satisfy the finding is
# to re-add or touch files already committed — padding the diff to satisfy the
# grader, the exact anti-pattern this repository teaches agents to refuse. The
# judge is inviting the behaviour the factory elsewhere forbids.
#
# WHY THIS DOES NOT WEAKEN PRINCIPLE VIII. The doctrine
# (`.specify/memory/constitution.md:63`, D-037 at `docs/decisions.md:963`) is
# that acceptance criteria must be provable from the diff, so the judge is given
# the diff and the criteria and nothing else. Adding the gate results does not
# hand the judge the code; it hands it the factory's own deterministic
# measurements of that code — facts the factory already committed to and already
# stores on the row being written. A judge that then disagrees with a green gate
# becomes a signal rather than a deadlock, which is US2.
#
# NOT IN SCOPE. This spec does not add a "cannot determine from the diff" judge
# outcome — a real want, with a different blast radius, touching `JudgeOutcome`,
# `_STRICTNESS` and `compose_result`. It does not hand the judge the base tree's
# file listing. It does not change `judge_required`'s guard, `prepare_diff`, or
# what the gates themselves measure. And it does not touch authoring-time
# refusal, which is 102.
---

# Feature Specification: the judge scores against what the factory measured

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

The verification loop runs gates, then the output check, then the judge. By the
time the judge is consulted, every gate has run and its exit code is in the row
being written. The judge is told none of it.

Two failures follow, and they are different:

1. **A scenario whose Then-clause is a runtime outcome is structurally
   unscoreable.** "Then the suite passes" cannot be demonstrated by a diff. The
   judge, correctly obeying its instruction to score only what the diff shows,
   fails it — forever, because no attempt can put a test result into a patch.
2. **A judge's speculation about a gate outrides that gate's recorded result.**
   Nothing compares the verdict's reasoning against the measurements sitting in
   the same record, so a judge asserting a gate would fail produces a node FAIL
   on a row where that gate is recorded PASS.

## The rule this spec is asking for

**The judge is shown what the factory already measured, and a verdict that
contradicts a recorded measurement is the judge's fault, not the node's.**

### What this spec is not

It is not a relaxation of Principle VIII. The judge still sees the diff and the
criteria — plus the factory's own deterministic results for that same attempt.
No source outside the diff is added.

It is not a new judge outcome. "The diff cannot show me this" deserves to be
first-class and is not this spec.

It is not a change to what makes the judge run. `judge_required` is correct, and
its guarantee — that gates have passed whenever the judge is consulted — is what
US1 exploits rather than alters.

## User Scenarios & Testing

### User Story 1 - The judge is shown the gate results (Priority: P1)

As an operator, the judge scores a scenario whose Then-clause is a runtime
outcome using the factory's own measurement of that outcome, instead of guessing
from a patch that cannot contain it.

**Why this priority**: P1 and it depends on nothing. It is the defect, and the
data is already in the caller's hand at the call site.

**Acceptance Scenarios**:

1. **Given** a set of gate results and a criteria set, **When** the judge prompt
   is assembled, **Then** the prompt carries each gate's name, status and exit
   code — proven by a committed test.
2. **Given** a gate that failed, **When** the prompt is assembled, **Then** that
   gate's recorded output tail is carried too, bounded to a stated length —
   proven by a committed test. A failing gate cannot occur on the judged path
   today, but the assembler must not depend on that guarantee holding.
3. **Given** no gate results supplied, **When** the prompt is assembled, **Then**
   it is byte-identical to today's prompt — proven by a committed test. The
   section is additive and its absence is the current behaviour.
4. **Given** a prompt carrying gate results, **When** its size is measured,
   **Then** the gate section is counted against the judge's input budget the same
   way every other section is — proven by a committed test. A section that
   escapes the budget would reintroduce a truncation nobody disclosed.
5. **Given** the assembled prompt, **When** its section order is inspected,
   **Then** the gate results appear before the diff and after the scenarios —
   proven by a committed test. The existing order is documented as
   non-cosmetic: the standard is established before the evidence measured
   against it.

### User Story 2 - A verdict that contradicts a recorded gate is a judge fault (Priority: P1)

As an operator, when the judge's reasoning asserts a gate would fail and that
gate is recorded PASS in the same row, the node is not charged for it.

**Why this priority**: P1. Without it US1 improves the odds and leaves the
unwinnable case intact — an attempt whose only remedy is to pad the diff.

**Acceptance Scenarios**:

1. **Given** a verdict whose finding names a gate recorded PASS on this attempt
   and asserts it would fail, **When** the verdict is composed, **Then** the
   contradiction is recorded and the finding does not produce a node FAIL —
   proven by a committed test.
2. **Given** the same verdict, **When** the judge retry budget is unspent,
   **Then** the judge is retried rather than the node failed — proven by a
   committed test. A judge fault is the one failure a judge retry is actually
   for.
3. **Given** the same verdict with the judge retry budget spent, **Then** the
   contradiction is recorded and the attempt does not fail the node on that
   finding alone — proven by a committed test.
4. **Given** a verdict whose findings name no gate, **When** it is composed,
   **Then** the outcome is unchanged from today — proven by a committed test.
5. **Given** a verdict naming a gate that genuinely failed, **When** it is
   composed, **Then** it is honoured — proven by a committed test. The check is
   for contradiction, not for gate mentions.

### User Story 3 - The record says what the judge was shown (Priority: P2)

As an operator, I can tell from the stored attempt whether the judge scored it
with the gate results in hand.

**Why this priority**: P2. It is what makes a historical verdict readable after
this change lands, and what lets a regression be spotted if the section is ever
dropped.

**Acceptance Scenarios**:

1. **Given** an attempt judged with gate results in the prompt, **When** its row
   is written, **Then** the row records that they were included — proven by a
   committed test.
2. **Given** an attempt judged without them, **When** its row is written,
   **Then** the row records their absence rather than being silent — proven by a
   committed test.
3. **Given** a recorded contradiction from US2, **When** the operator reads the
   attempt through the CLI, **Then** the contradiction is visible without
   reading the store — proven by a committed test.

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

US1 and US2 both change `factory/verify/judge.py`; US2 and US3 both change the
verdict's composition and its record. All three are serialised on file ownership
rather than on logic.

## Requirements

- **FR-001**: The judge prompt MUST carry each gate's name, status and exit code
  for the attempt being scored.
- **FR-002**: The prompt MUST carry a bounded output tail for any gate whose
  status is not PASS.
- **FR-003**: With no gate results supplied, the assembled prompt MUST be
  byte-identical to the prompt assembled today.
- **FR-004**: The gate section MUST be counted against the judge's input budget
  by the same measurement every other section uses.
- **FR-005**: The gate section MUST appear after the scenarios and before the
  diff.
- **FR-006**: A judge finding that asserts a gate would fail, naming a gate
  recorded PASS on the same attempt, MUST NOT by itself produce a node FAIL, and
  MUST be recorded as a contradiction.
- **FR-007**: A contradiction MUST cause a judge retry while the judge retry
  budget is unspent.
- **FR-008**: The attempt record MUST state whether the judge was shown the gate
  results.
- **FR-009**: Every story MUST leave `judge_required`
  (`factory/verify/models.py`), `prepare_diff` and the gate implementations
  unchanged.

## Success Criteria (summary)

- A scenario whose Then-clause is a runtime outcome can pass, because the
  factory's measurement of that outcome is in the judge's prompt.
- The fifteen-attempt deadlock is not reachable: six consecutive all-green
  attempts cannot fail on the same unscoreable scenario, because the judge is no
  longer guessing at it.
- A judge that contradicts a green gate produces a retry and a recorded
  contradiction, not a killed node and an agent invited to pad its diff.
