---
state: landed
# Attested landed 2026-08-17. US1 a5d1c8501e5f (#172), US2 664ac8ab7149 (#175),
# US3 eaed6e1a127b (#177) — all three observed on ergane-buildout, checked by
# commit ancestry and by content, not by a PR's merged flag.
#
# Two of the three needed an operator hand to land, and neither for a reason the
# agent or the judge got wrong:
#   US1 reached PASS only after DIFF_INPUT_LIMIT rose 60→64 KiB; four earlier
#     attempts died at admission control on a fully green diff of 61,725 bytes.
#   US3 reached verified:true, then was killed by DEQUEUED_BY_HUMAN decided from
#     one unconfirmed poll three seconds after its PR opened, while that PR was
#     open and healthy. GitHub then reported PR #176 merged and never moved the
#     branch — its merge commit 3cedbbe7 sat on a speculative line that forked
#     before #173 landed. Recovered by cherry-pick as #177.
# `ergane spec landed` reports only US2 and US3: #172's title carries a
# parenthetical that `_LANDING_RE` cannot parse. The work is present; the reader
# cannot see it. Filed, not fixed.
#
# Requested by Bryan 2026-08-12, mid-032: "a way to 'fail out' of ergane for a
# spec that repeatedly fails. allows the running claude process to complete the
# work on the agent's behalf, note it was built by something else but otherwise
# check it in with all of the same data attributes the pipeline expects to
# proceed." Design agreed same day, with three conditions stated by him and
# treated here as binding: the attestation must clearly state it was done
# externally; the count must be kept, because the long-term goal is for it to
# be zero; and it must be an explicit operator act, never automatic.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Drafted by the operator session against the tree at 8ac64fd on 2026-08-12,
# the day 032 was killed after four attempts at a story no agent could satisfy.
---

# Feature Specification: An operator may finish what an agent could not — visibly, and counted

## Why this exists, and the thing it must not become

On 2026-08-11 a single story took four attempts, roughly nine hours and 128M
input tokens, and landed nothing. The story was unsatisfiable as written; no
agent could have completed it. The floor was blocked the whole time, because
that story is the unblock for a required check every other branch waits behind.

The operator could have finished it in minutes. There was no way to hand that
work back. The only exits from a stuck node are **kill** — lose the work,
re-dispatch, hope — and **escalate**, which parks the node and offers the
operator a button but no way to supply the answer in code.

This spec adds the third exit: the operator does the work, and the workflow
accepts it as a completed node, with the pipeline's own data attributes, so
everything downstream proceeds normally.

**And this is the dangerous feature in this corpus.** Ergane's claim — the first
line of its own `CLAUDE.md`, and D-024 — is that no production code in this
repository is written by a human. This is the exception. If it is cheap and
quiet, it becomes the path of least resistance, the factory quietly stops being
a factory, and nobody notices because nothing records that it happened.

So the design is shaped by one rule stated three ways:

1. **Explicit.** It is an operator act. Nothing automatic may ever invoke it —
   not ladder exhaustion, not a recovery cycle, not a timeout. A node that runs
   out of attempts still fails or escalates exactly as it does today.
2. **Visible.** A node completed this way says so everywhere a human or a
   program might look: the verification record, the commit, the pull request,
   `ergane build status`, and the landed attestation.
3. **Counted.** The number of times this has been used is a queryable fact, not
   a recollection — because the target for that number is zero, and a target
   you cannot measure is a wish.

What it does **not** bypass is verification. The operator supplies *authorship*,
not a *verdict*. The work still faces the gates, the judge and the merge queue,
and it fails there like anything else.

## User Scenarios & Testing

### User Story 1 - The operator hands finished work back, and it is recorded as theirs (Priority: P1)

An operator, faced with a node that has exhausted its ladder, does the work
themselves — in the node's worktree, on the node's branch — and signals the
epic that the node is complete. The workflow accepts the branch as that node's
result and runs it through the **normal** verification and landing path:
gates, judge, PR, merge queue. The provenance travels with it from the first
moment, so there is no window in which an externally-completed node is
indistinguishable from an agent-built one.

**This story must ship the provenance with the mechanism.** A completion path
that lands work without recording who wrote it is the bad version of this
feature, and shipping it "for now" is how the guarantee is lost.

**Goal**: a stuck node has a third exit that costs the floor minutes instead of
hours, and the record of what happened is complete at the moment it happens.

**Independent Test**: signalling `complete_node_externally` for a node whose
ladder is exhausted drives that node through VERIFYING to its normal terminal
state, and the stored verification record carries the provenance string; the
same signal against a healthy node is refused and changes nothing.

**Acceptance Scenarios**:

1. **Given** a node whose ladder is exhausted and a branch carrying the
   operator's work, **When** `complete_node_externally` is signalled naming the
   node, the branch and a provenance string, **Then** the node re-enters
   verification and proceeds through gates, judge, PR and queue exactly as an
   agent-completed node does.
2. **Given** that node, **When** the verification record is written, **Then** it
   carries the provenance — who completed it and that it was external — and
   that field is not nullable for an externally-completed node.
3. **Given** a node that is RUNNING, PENDING, or has attempts remaining,
   **When** the signal is sent, **Then** it is **refused**: the node is
   untouched, the refusal is recorded, and the epic continues. The hatch opens
   only for a node that has genuinely run out of road.
4. **Given** externally-supplied work that fails the gates or the judge,
   **When** verification runs, **Then** it fails exactly as agent work would —
   the operator supplied authorship, not a verdict, and nothing about this path
   grants a pass.
5. **Given** the whole of this spec's code, **When** it is inspected, **Then**
   no automatic path — ladder exhaustion, recovery cycle, timeout, escalation
   expiry — can reach the signal. It is reachable only from an explicit
   operator command.

### User Story 2 - Every surface says it was built externally (Priority: P1)

The provenance US1 records must be legible at every place a person or a program
asks "where did this come from" — not merely present in a database column.
`ergane build status` shows it; the landing commit carries it in a trailer; the
pull request body states it; and the spec's landed attestation says the spec
contains externally-completed work rather than implying an unbroken chain of
agent authorship.

**Goal**: nobody — reviewer, auditor, or a future operator reading the ledger —
can mistake an externally-completed story for an agent-built one, and nobody
has to know to go looking.

**Independent Test**: for an externally-completed node, the status output, the
commit trailer, the PR body and the spec attestation each state it, and for an
agent-completed node none of them do.

**Acceptance Scenarios**:

1. **Given** an externally-completed node, **When** `ergane build status` is
   read, **Then** the node's row states it was completed externally, beside its
   state, without the reader having to pass a flag.
2. **Given** the landing commit for that node, **When** it is inspected, **Then**
   it carries a provenance trailer naming the external author, so `git log` and
   any tool reading trailers sees it without consulting the factory's stores.
3. **Given** the pull request that lands it, **When** the body is read, **Then**
   it states plainly that the work was completed externally and why the node
   was eligible — the exhausted ladder is part of the record.
4. **Given** a spec whose stories include at least one externally-completed
   node, **When** its `state: landed` attestation is written, **Then** the
   attestation states that the spec contains externally-completed work. An
   attestation that reads as fully agent-built when it is not is the failure
   this story exists to prevent.
5. **Given** an agent-completed node, **When** all four surfaces are read,
   **Then** none of them mention external completion — the marking is a signal,
   and a signal that fires on everything carries nothing.

### User Story 3 - The count is a fact, and the target is zero (Priority: P2)

Every use of the hatch increments a durable count, queryable per spec and in
total, so "how often did we bail out" is answered by the system rather than by
memory. The number is expected to be small and is meant to fall; a rising count
is the signal that specs are being written that agents cannot build, which is a
refinement problem, not a tooling problem.

**Goal**: the escape hatch measures itself, so its own overuse is visible before
it becomes normal.

**Independent Test**: completing two nodes externally across two specs yields a
total of 2 and per-spec counts of 1 each; a corpus that has never used the
hatch reports 0 rather than an absence.

**Acceptance Scenarios**:

1. **Given** any externally-completed node, **When** it reaches its terminal
   state, **Then** a durable counter is incremented, recording the spec, the
   node, the provenance and the time.
2. **Given** a corpus with recorded external completions, **When** the count is
   queried, **Then** it reports the total and the per-spec breakdown.
3. **Given** a corpus that has never used the hatch, **When** the count is
   queried, **Then** it reports **0** explicitly — a zero that is measured, not
   a table that happens to be empty and might equally mean the counting is
   broken.
4. **Given** the count, **When** it is read, **Then** the surface states the
   target is zero, so the number is interpretable by someone encountering it
   for the first time.

## Functional Requirements

- **FR-001**: The workflow MUST accept a `complete_node_externally` signal
  naming the node, the branch carrying the work, and a provenance string, and
  MUST drive that node through its normal verification and landing path.
- **FR-002**: The signal MUST be refused for any node that has not exhausted its
  ladder, and the refusal MUST be recorded rather than silently dropped.
- **FR-003**: No automatic path may invoke the completion signal. Ladder
  exhaustion, recovery cycles, timeouts and escalation expiry MUST continue to
  fail or escalate as they do today.
- **FR-004**: Externally-supplied work MUST face the same gates, judge and merge
  queue as agent work; this path grants authorship, never a verdict.
- **FR-005**: The verification record for an externally-completed node MUST
  carry its provenance, and that field MUST NOT be nullable on this path.
- **FR-006**: `ergane build status`, the landing commit trailer, the pull
  request body and the spec's landed attestation MUST each state that the work
  was completed externally; agent-completed nodes MUST carry none of these
  markings.
- **FR-007**: Every external completion MUST increment a durable count carrying
  spec, node, provenance and timestamp, queryable in total and per spec.
- **FR-008**: The count surface MUST report an explicit `0` for a corpus that
  has never used the hatch, distinguishable from a broken or absent counter, and
  MUST state that zero is the target.
- **FR-009**: All new tests MUST build their stores under `tmp_path` — the open
  `hardening/test-suite-writes-to-the-live-evidence-store` finding applies here
  as everywhere.

## Success Criteria

- **SC-001**: A node that has exhausted its ladder can be completed by the
  operator and landed without killing the epic or re-dispatching it.
- **SC-002**: For an externally-completed story, all four surfaces in FR-006
  state it; for an agent-built story, none do.
- **SC-003**: Grepping the tree finds no call path from ladder exhaustion,
  recovery, timeout or escalation expiry to the completion signal.
- **SC-004**: `ergane` reports the external-completion count, including an
  explicit zero on a corpus that has never used it.
- **SC-005**: Externally-supplied work that fails its gates fails the node —
  demonstrated by a test, not asserted.
- **SC-006**: No new dependency; the full suite green in a clean environment.

## Edge Cases

- **The branch does not exist, or carries no commits.** The signal is refused
  with a message naming what was looked for. An empty completion is a mistake,
  not a valid hand-back.
- **The epic is paused when the signal arrives.** The signal is buffered like
  every other operator signal; the node completes when the epic resumes. Signals
  are durable and arrive without a worker — the pause is not a race.
- **The signal names a node this epic does not have.** Recorded and never read,
  matching `escalation_resolved`'s deliberate incuriosity: validating against
  state the workflow may not have written yet drops the presses that arrive
  fastest.
- **Two completions for the same node.** First wins; the second is refused and
  recorded. The node has one result.
- **The operator completes a node, and its dependents then fail.** Nothing
  special: dependents see a normally-completed dependency, because that is the
  entire point of using the pipeline's own attributes.
- **The count is asked for before the feature is ever used.** Answers 0. See
  FR-008 — an empty table and a broken counter must not look alike.

## Assumptions

- The operator does the work in the node's existing worktree and branch, which
  a killed or exhausted node still has; this spec does not create worktrees.
- Provenance is a free-text string supplied by the operator, not a detected
  identity. The factory records what it is told, and D-009's
  declared-never-detected rule is the precedent.
- "Ladder exhausted" is the condition the existing ladder already computes; this
  spec reads it and does not redefine when a node is out of road.

## Out of Scope

- **Automatic fallback.** Explicitly forbidden by FR-003, and the reason is not
  caution: an automatic hatch would have fired on 032 and hidden that the
  *story* was contradictory. The four failed attempts are what surfaced the
  defect; a silent rescue would have shipped the symptom and left the trap in
  place for the next spec.
- **Operator-supplied verdicts.** Nothing here lets a human declare a gate
  passed or a judge satisfied.
- **Re-writing history for past external work.** The count starts when this
  lands; earlier hand-completions are not backfilled.
- **A UI.** The signal and the CLI verb are the surface.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-009]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008]
```

US1 carries the mechanism **and** its provenance record together, because a
completion path that does not record authorship is the version of this feature
that must never exist — not even for one merge. US2 (the visible surfaces) and
US3 (the count) both take merge-edges on US1 and are independent of each other.
