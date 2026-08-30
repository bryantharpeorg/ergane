---
state: landed
# Attested landed 2026-08-30. US1 c06a55635c17 (#390), US2 1a9efff7f3e9 (#391),
# US3 03451a9277cb (#392) — all three observed on ergane-buildout, all three on
# the first attempt, all three on `implementer` resolving to claude-opus-5 via
# the operator's subscription.
#
# The first epic dispatched after Opus became the DEFAULT implementer rather
# than a promotion rung, and the first the roadmap dispatched by itself after a
# 22-hour pause. us1 took 31 minutes dispatch-to-merged, us2 about 64, us3 about
# 89 including a merge queue wait.
#
# WHAT IT COST THE QUEUE, recorded because it is the measurable half of a defect
# class this spec did not cause. us1 changed factory/verify/models.py and us2
# changed 21 files; between them they invalidated line anchors in specs 116 and
# 120 that had been correct when this epic started. See
# refinement/a-landing-silently-invalidates-every-spec-anchor-below-it.
fixes:
  - verify/the-judges-attention-budget-and-the-refusal-threshold-are-the-same-constant
  - verify/the-diff-size-refusal-counts-generated-lockfiles-and-has-no-manifest-key
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# The directory was reserved — empty and untracked — by the spec-routing session
# on 2026-08-23 at 14:04, alongside 089-102.
#
# THE DEFECT IN ONE SENTENCE. `DIFF_INPUT_LIMIT` is documented as "an attention
# budget, not a context limit" (`factory/verify/diffbounds.py:36-42`) and is
# then used as two different things: the size the judge's prompt is abridged to,
# and the size above which a story is refused before the judge ever runs. One
# constant, two jobs, and the second job silently inherits a number chosen for
# the first.
#
# THE CONSEQUENCE IS A STRUCTURALLY UNBUILDABLE STORY. Over 64 KiB, no attempt
# can pass: all four gates green, judge never reached, every ladder rung failing
# identically on `size_refusal`. Measured twice — once at 185,682 bytes where
# 161 KB was two generated lockfiles a story requiring `npm ci` could not omit,
# and once at 74,465 bytes of hand-written UI with no lockfiles at all. The
# second is the one that matters: exempting lockfiles fixes the instance and
# hides the general problem.
#
# THREE THINGS THAT FOLLOW, WORTH SEPARATING. (1) The only remedy available to
# an agent is to delete content, and the cheapest content to delete is prose —
# a size check whose cheapest remedy is deleting prose will always be paid in
# prose, and the factory has no instrument that can see the bill. (2) By every
# signal the factory records, the smaller attempt is strictly better, and it is
# not. (3) A story can be too large to build but not too large to split, and the
# factory's only vocabulary for that condition is FAIL — so an operator learns
# about a decomposition problem as a byte count.
#
# THE GENTLER MECHANISM ALREADY EXISTS AND IS PREEMPTED. `prepare_diff`
# (`factory/verify/judge.py:315`) handles an oversize diff properly: an
# always-complete file listing, then each file a share of the budget in
# proportion to its size with a floor so small files are carried whole, spent on
# its head and its tail because a half-finished implementation is usually at the
# end of a file. Truncation is disclosed to the judge. That is the mechanism
# designed for exactly this case, and `size_refusal` fires first.
#
# WHY THE REFUSAL EXISTS AT ALL, AND WHY THIS SPEC KEEPS IT. Principle VIII
# (`.specify/memory/constitution.md:63`) and D-037 (`docs/decisions.md:963`) are
# non-negotiable: the judge sees the diff and the criteria and nothing else, so
# acceptance criteria must be provable from the diff. A diff abridged past the
# point where a criterion is provable makes a PASS meaningless. The refusal is
# that doctrine defended with a blunt instrument. This spec does not remove the
# defence; it separates the threshold from the judge's attention budget, puts
# the threshold in the operator's hands, and makes an abridged PASS auditable —
# so the ceiling and the doctrine agree instead of the ceiling standing in for
# it.
#
# THE SEAM IS ALREADY CUT AND NOTHING IS WIRED TO IT. `check_output` takes
# `diff_size_limit: int | None = DIFF_INPUT_LIMIT`
# (`factory/verify/diffcheck.py:162`), documented at `:178-184` as "the size
# check's seam ... `None` disables the check". No caller passes it. The default
# is the judge's cap "read from `factory.verify.diffbounds` rather than restated
# here — a second copy of that number would let tuning it silently do nothing",
# which is right and is exactly why the two roles must become two names rather
# than two copies.
#
# NOT IN SCOPE. This spec does not exempt lockfiles or any generated path — that
# is the instance fix that hid the general problem, and the round-2 report is
# explicit that it must not be repeated. It does not make `diff_check` optional;
# the manifest requires it (`factory/verify/factory_yaml.py:748-751`) and that
# stays. It does not add a "cannot determine from the diff" judge outcome, which
# is a real want with its own key and a different blast radius. It does not
# change `prepare_diff`'s abridgement algorithm.
---

# Feature Specification: the diff ceiling and the evidence doctrine agree

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

One constant answers two questions that have different right answers:

| Question | Who asks | What the answer depends on |
| --- | --- | --- |
| How much diff may the judge's prompt carry? | `prepare_diff` | the model's context and attention |
| Above what size is a story refused unjudged? | `size_refusal` | whether the criteria are still provable |

The first is a property of the model. The second is a property of the work and
of the operator's tolerance. Today both read `DIFF_INPUT_LIMIT = 64 * 1024`, so
raising the judge's budget to fit a bigger model also raises the size at which
work is refused, and lowering the refusal to be strict also blinds the judge.
They cannot be tuned independently because they are the same name.

And the refusal is not reachable from the manifest. `diff_check` is mandatory
(`factory/verify/factory_yaml.py:748-751`), the limit has no manifest key and no
CLI flag, and the one seam that exists — `check_output`'s `diff_size_limit` — has
no production caller. So the only way an operator can change the size at which
their repository refuses to build is to edit the tool's source.

## The rule this spec is asking for

**The size the judge is shown and the size at which work is refused are two
settings with two names, the refusal is the operator's to set, and a verdict
reached on an abridged diff says so in the record.**

### What this spec is not

It is not the removal of the ceiling. A diff abridged past the point where a
criterion is provable makes a PASS meaningless, and Principle VIII is
non-negotiable. The ceiling stays; it stops being a constant chosen for a
different purpose.

It is not a generated-path exemption. Exempting lockfiles fixed one instance and
concealed the general defect, which then reappeared on a story with no lockfiles
at all. Any attempt that reaches for a filename pattern has solved the wrong
problem.

It is not a judge outcome. "The diff cannot show me this" deserves to be a first
class verdict rather than a scenario failure, and it is not this spec.

## User Scenarios & Testing

### User Story 1 - The two limits have two names (Priority: P1)

As an operator, the size the judge's prompt is abridged to and the size at which
a story is refused are separate settings, so tuning one cannot silently move the
other.

**Why this priority**: P1 and it depends on nothing. Every other story needs two
names to talk about.

**Acceptance Scenarios**:

1. **Given** the two limits set to different values with the refusal above the
   attention budget, **When** a diff larger than the attention budget but smaller
   than the refusal threshold is checked, **Then** no size refusal is recorded —
   proven by a committed test.
2. **Given** the same configuration, **When** that diff is prepared for the
   judge, **Then** it is abridged to the attention budget and its truncation is
   disclosed — proven by a committed test.
3. **Given** a diff larger than the refusal threshold, **When** it is checked,
   **Then** a size refusal is recorded naming the total and the biggest files,
   exactly as it is today — proven by a committed test.
4. **Given** default configuration, **When** any diff is checked, **Then** the
   outcome is identical to today's for every size — proven by a committed test
   over sizes either side of the current constant. This story is a rename and a
   split, not a behaviour change.

### User Story 2 - The refusal threshold belongs to the operator (Priority: P1)

As an operator, I raise or lower the size at which my repository refuses to build
a story by editing my manifest, not the tool's source.

**Why this priority**: P1. Without it US1 splits a constant an operator still
cannot reach, and the measured cost of not reaching it was three fully-green
attempts thrown away one rung from escalation.

**Acceptance Scenarios**:

1. **Given** a manifest declaring a diff refusal threshold, **When** a node is
   verified, **Then** the check refuses at the declared value rather than the
   default — proven by a committed test.
2. **Given** a manifest declaring no threshold, **When** a node is verified,
   **Then** the default applies and the manifest validates exactly as it does
   today — proven by a committed test over the existing manifest corpus.
3. **Given** a manifest declaring a threshold below the judge's attention
   budget, **When** the manifest is loaded, **Then** it is refused naming both
   values — proven by a committed test. A refusal stricter than the judge's own
   input limit means every abridged diff is also a refused one, which is the
   configuration that reintroduces this defect under a new name.
4. **Given** a manifest declaring a non-integer or negative threshold, **When**
   it is loaded, **Then** it is refused in the shape the other numeric manifest
   keys are refused — proven by a committed test.

### User Story 3 - An abridged verdict is auditable (Priority: P2)

As an operator, when a story passed on a diff the judge saw only part of, the
record says so, so a PASS on a large story can be told apart from a PASS on one
the judge read whole.

**Why this priority**: P2, and it is what makes US1 and US2 safe against
Principle VIII. Widening the gap between the two limits means more verdicts are
reached on abridged evidence; a verdict that does not disclose that is exactly
the rubber stamp the doctrine exists to prevent.

**Acceptance Scenarios**:

1. **Given** a diff abridged for the judge, **When** the verification row is
   written, **Then** it records that the judge's input was abridged and by how
   much — proven by a committed test.
2. **Given** a diff the judge saw whole, **When** the row is written, **Then** it
   records that no abridgement occurred — proven by a committed test. The absence
   of a flag must be a statement, not a silence.
3. **Given** an abridged PASS, **When** the operator reads the attempt through
   the CLI, **Then** the abridgement is visible without reading the store —
   proven by a committed test.

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

US1 splits the constant in `factory/verify/diffbounds.py` and threads the second
name through `factory/verify/diffcheck.py`. US2 adds the manifest key and its
loader, and reaches the same `diffcheck` seam. US3 records the abridgement, which
touches `diffcheck` again and the verification store. All three therefore share
`factory/verify/diffcheck.py` and are serialised on file ownership rather than
on logic.

## Requirements

- **FR-001**: The judge's attention budget and the diff refusal threshold MUST be
  two separately named settings, and the refusal threshold MUST default to a
  value that preserves today's behaviour.
- **FR-002**: `prepare_diff` MUST abridge to the attention budget, and the size
  refusal MUST fire only above the refusal threshold.
- **FR-003**: A diff between the two values MUST be judged on an abridged prompt
  rather than refused.
- **FR-004**: The manifest MUST accept a diff refusal threshold, and a manifest
  omitting it MUST behave exactly as it does today.
- **FR-005**: The manifest loader MUST refuse a threshold below the judge's
  attention budget, naming both values.
- **FR-006**: The manifest loader MUST refuse a non-integer or negative
  threshold in the shape the other numeric manifest keys are refused.
- **FR-007**: The verification record MUST state whether the judge's input was
  abridged, and by how much, on every attempt that reached the judge.
- **FR-008**: Every story MUST leave `prepare_diff`'s abridgement algorithm
  (`factory/verify/judge.py:315`) unchanged, and MUST NOT exempt any path by name
  or pattern from the measured size.

## Success Criteria (summary)

- A story whose honest diff is larger than the judge's attention budget can be
  built, judged and landed, on an abridged prompt whose abridgement is recorded.
- An operator changes the size at which their repository refuses to build by
  editing the manifest, and a threshold that would recreate this defect is
  refused at load time.
- A PASS reached on a partially-shown diff is distinguishable, in the record and
  in the CLI, from a PASS reached on a diff the judge read whole.
