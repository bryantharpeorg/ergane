---
state: ready
# FLIPPED draft -> ready 2026-08-21 8:25 AM CT at the operator's instruction,
# after he read the rendered page. What the pre-dispatch review did:
#
#   - ANCHORS: 50, all resolving against `origin/ergane-buildout` at 669006d.
#   - **THE FIRST PASS WAS AGAINST THE WRONG TREE.** `class LandingConfig:` was
#     cited at `factory/mergequeue/models.py:326`, which is a BLANK LINE in the
#     origin tree — the class is at `:377`. Every anchor in this spec was
#     re-derived by exact line-text match against origin. See 078's frontmatter
#     for the full account of how a five-commit-behind checkout produced 36 bad
#     citations across this batch.
#   - THE DEFAULTS WERE READ OUT OF THE TREE, not remembered: `merge_method`
#     "squash", `poll_interval_s` 60, `stall_after_s` 7200, `max_recovery_cycles`
#     1, at `factory/mergequeue/models.py:388-391`. US1-S2 pins all four.
#
# Drafted 2026-08-21 ~8:40 AM CT by an operator session, at the operator's
# instruction, before the first PyPI release since v0.1.0.
#
# WHAT THIS IS, IN ONE SENTENCE THE OPERATOR SAID HIMSELF. On 2026-08-19 at
# ~21:45 CT he asked to lower `stall_after_s` before leaving epic 070 running at
# `--max-concurrent-nodes 3` overnight, and **there is nowhere to lower it.**
#
# THE MEASUREMENT, verified line by line on 2026-08-21:
#   - `factory/mergequeue/models.py:377` `class LandingConfig:` declares four
#     fields -- `merge_method` (:337), `poll_interval_s` (:338), `stall_after_s`
#     (:339), `max_recovery_cycles` (:340).
#   - All three construction sites build it bare:
#       `factory/cli/roadmap.py:247`        `landing_config=LandingConfig(),`
#       `factory/workgraph/workflow.py:429` `landing_config: LandingConfig = LandingConfig()`
#       `factory/roadmap/workflow.py:263`   `landing_config: LandingConfig = LandingConfig()`
#   - And the hand-start path does not pass one at all:
#     `factory/cli/nouns/build.py:592` constructs `EpicInput(` with `graph`,
#     `proxy_url`, `config`, `verify_order` and `max_concurrent_nodes` -- no
#     `landing_config`. So a hand-started epic always runs the defaults, and the
#     roadmap path runs the defaults it was handed at `factory/cli/roadmap.py:247`.
#   Four dials, three construction sites, zero operator surface.
#
# WHY IT IS NOT COSMETIC, and this is the half that matters for the release.
# `max_recovery_cycles` defaults to **1**, and it is the bound that actually ends
# a node whose landing keeps being rejected --
# `factory/workgraph/workflow.py:2813` and `:2851` both compare against it. 069
# landed the correct pricing: a rejection caused by a sibling landing classifies
# as `BASE_MOVED` and is charged to neither budget. **But the recovery-cycle cap
# still bounds it.** So a fan-out of N stories sharing one file -- which is
# exactly what the tharpebox field report's spec 001 was, and exactly what its
# us4 died of with ZERO code defects -- is still unsupported out of the box, and
# no operator can raise the bound that ends it.
#
# THE ADJACENT DECISION THIS SPEC DELIBERATELY DOES NOT MAKE. Whether the default
# should be higher than 1 is a judgement about cost, not a defect. This spec
# makes the dial reachable and leaves today's defaults exactly where they are;
# an operator who wants a different default can then set one and measure it.
#
# Filed as, both critical and both open:
#   mergequeue/no-landing-dial-is-operator-settable-landingconfig-is-constructed-
#     empty-everywhere
#   mergequeue/max-recovery-cycles-bounds-every-raced-node-and-no-operator-can-
#     raise-it
---

# Feature Specification: the landing dials belong to the operator

## The gap, stated precisely

`LandingConfig` is the merge queue's control panel: how a passing node lands, how
often its pull request is polled, how long a silent queue counts as stalled, and
how many times a rejected landing may be recovered. Every field has a default,
every default is reachable only by editing source, and every construction site
takes the default.

The consequence is that two of the operator's most common decisions cannot be
expressed at all:

- **"This epic fans out across a shared file — let a raced node recover more than
  once."** `max_recovery_cycles` is 1 and cannot be raised.
- **"I am leaving this running unattended — do not let a node sit for two hours
  before anyone notices."** `stall_after_s` is 7200 and cannot be lowered.

## The rule this spec is asking for

**A dial that exists is a dial the operator can set, and a dial the operator has
set is one they can read back.** Not one of the three is true today.

## What this spec does not change

- The default values. `merge_method="squash"`, `poll_interval_s=60`,
  `stall_after_s=7200`, `max_recovery_cycles=1` all stay exactly as they are.
  Whether 1 is the right recovery bound is a cost judgement, and this spec is
  what makes it possible to measure rather than argue.
- 069's pricing. A `BASE_MOVED` rejection is charged to neither budget and stays
  that way.
- The verification ladder's caps, which already travel on `EpicInput.config`.
- The classifier, the poller, or anything about how a landing is decided.

## User Scenarios & Testing

### User Story 1 - A hand-started epic runs the dials its operator set (Priority: P1)

As an operator starting an epic by hand, I can set any of the landing dials at
dispatch and the epic runs with what I set.

**Why this priority**: P1 and it is the spine. Every other story here depends on
the value reaching the workflow.

**Independent Test**: start an epic with a raised recovery bound and assert the
running epic's landing config carries it.

**Acceptance Scenarios**:

1. **Given** an operator setting a landing dial at dispatch, **When** the epic
   starts, **Then** the workflow's landing config carries that value — proven by
   a committed test asserting the constructed `EpicInput`.
2. **Given** an operator setting none of them, **When** the epic starts, **Then**
   every dial holds today's default — proven by a committed test naming all four
   values. **This is the control**: the whole point of this spec is that
   unattended behaviour does not change.
3. **Given** a raised `max_recovery_cycles`, **When** a node's landing is
   rejected more than once for a recoverable cause, **Then** it recovers more
   than once — proven by a committed test that drives the recovery path, not by
   asserting the value was stored. **A dial that is parsed and never read is the
   defect class this repository has now filed five times**
   (`verify/readiness-proves-a-thing-is-declared-not-that-it-works`).
4. **Given** a lowered `stall_after_s`, **When** a landing sits unanswered past
   it, **Then** it classifies as stalled at the operator's threshold rather than
   at 7200 — proven by a committed test driving the classifier.
5. **Given** a dial set to a value that cannot work — a negative interval, a zero
   poll, an unknown merge method — **When** the epic is started, **Then** it is
   refused by name before dispatch — proven by a committed test. A bad dial must
   fail at the command, not four hours later inside a workflow.
6. **Given** the three `EpicInput` construction sites
   (`factory/cli/nouns/build.py:592`, `factory/workgraph/cli.py:571`,
   `factory/roadmap/workflow.py:1258`), **When** this story lands, **Then** none
   of them silently drops an operator-set landing config — proven by a committed
   test covering each. One forgotten site is how this defect reads as "set but
   ignored", which is worse than "cannot be set".

---

### User Story 2 - A scheduled epic runs the dials its operator set (Priority: P1)

As an operator running the roadmap unattended, the dials I chose apply to the
epics the scheduler starts, not only to the ones I start by hand.

**Why this priority**: P1. Unattended is the case the dials exist for — the
2026-08-19 request that produced this spec was about an overnight run.

**Independent Test**: configure a landing dial for the roadmap, let it dispatch a
child epic, and assert the child carries the value.

**Acceptance Scenarios**:

1. **Given** an operator-set landing dial on the roadmap, **When** it dispatches
   a child epic, **Then** the child's `EpicInput` carries the value — proven by a
   committed test.
2. **Given** no operator-set dial, **When** the roadmap dispatches, **Then** the
   child carries today's defaults — proven by a committed test. **The control.**
3. **Given** a running roadmap, **When** an operator changes a dial, **Then** the
   spec states plainly whether it applies to already-running epics or only to the
   next dispatch, and a committed test proves which. An epic compiled its
   dispatch at start; pretending otherwise is how an operator concludes a dial
   does not work.
4. **Given** the roadmap's construction site
   (`factory/cli/roadmap.py:247`), **When** this story lands, **Then** it no
   longer builds `LandingConfig()` bare — proven by a committed test.

---

### User Story 3 - The dials in force are readable (Priority: P2)

As an operator, I can read what landing dials a running epic is actually using,
so I know my flag took effect.

**Why this priority**: P2. Without it US1 and US2 are unfalsifiable from the
outside, which is the exact shape of the last five readiness defects.

**Independent Test**: start an epic with a non-default dial and read it back from
status output.

**Acceptance Scenarios**:

1. **Given** a running epic, **When** the operator asks for its status, **Then**
   the landing dials in force are shown — proven by a committed test asserting
   the rendered output.
2. **Given** an epic running defaults, **When** status is read, **Then** the
   defaults are shown as defaults — proven by a committed test. Distinguishing
   "set to 60" from "defaulted to 60" is the whole value of the line.
3. **Given** a degraded status query, **When** the dials cannot be read, **Then**
   status still renders the rest of the epic rather than failing — proven by a
   committed test. 052 landed that principle; do not regress it.

## Requirements

### Functional Requirements

- **FR-001**: Every field of `LandingConfig` MUST be settable by the operator at
  dispatch.
- **FR-002**: An unset dial MUST take today's default value, unchanged.
- **FR-003**: A set dial MUST change the behaviour it names, proven by driving
  that behaviour rather than by reading the stored value.
- **FR-004**: An invalid dial value MUST be refused by name before dispatch.
- **FR-005**: Every `EpicInput` construction site MUST carry the operator-set
  landing config rather than a default-constructed one.
- **FR-006**: The roadmap's dispatch MUST carry operator-set landing dials to its
  child epics.
- **FR-007**: The spec MUST state, and a test MUST prove, whether a dial change
  reaches an already-running epic.
- **FR-008**: A running epic's landing dials MUST be readable from operator
  status output.
- **FR-009**: Status MUST distinguish a set value from a defaulted one.
- **FR-010**: A status query that cannot read the dials MUST still render the
  rest of the epic.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010]
  persona: opus-closer
```

US1 and US3 both edit `factory/cli/nouns/build.py`; US1 and US2 both reach
`EpicInput`'s landing config. The chain is contention, not logic — US2 does not
need US1's behaviour, it needs US1's lines to have stopped moving.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste an epic started with a raised recovery bound and the running
  epic's landing config showing it.
- **SC-002**: Paste the control: an epic started with no dials, showing all four
  defaults.
- **SC-003**: Paste the recovery-path test driving a second recovery cycle under
  a raised bound, and failing to get one under the default.
- **SC-004**: Paste a stall classified at a lowered `stall_after_s`.
- **SC-005**: Paste an invalid dial refused by name at the command.
- **SC-006**: Paste a roadmap-dispatched child epic carrying an operator-set
  dial.
- **SC-007**: Paste status output showing the dials in force, once for a set
  value and once for a default.

## Assumptions

- `EpicInput.landing_config` (`factory/workgraph/workflow.py:429`) already
  reaches every consumer; the field is plumbed and only ever default-constructed.
  Verified 2026-08-21 by reading all three construction sites.
- `max_recovery_cycles` is read at `factory/workgraph/workflow.py:2813` and
  `:2851` and nowhere else. If an implementer finds a third reader, it is in
  scope and should be named in the diff.
- Changing a dial for a running epic is not required. FR-007 asks the
  implementer to *state and prove* which it is, not to build signal-based
  reconfiguration.
</content>
