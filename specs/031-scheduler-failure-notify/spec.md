---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `roadmap/scheduler-failures-reach-nobody` (critical, filed 2026-08-10), then
# refined against the tree at 9594787 on 2026-08-11.
---

# Feature Specification: A pass failure is a fact told once, not a choice asked forever

## The delta this spec is scoped to

The finding's headline — 24 failed scheduled executions, six hours, no message —
was observed against code that predates 021/us4, which landed later the same day
and closed most of it. The tree at `9594787` already has: a failure boundary
around the whole scheduler body (`RoadmapWorkflow.run` wraps `_run_inner` in
`try/except`, reports, then re-raises), a durable consecutive-failure count
written to the store *before* any send is attempted (`record_roadmap_failure`),
a throttle (`_should_notify_failure`), recovery reporting on the next green pass
(`_report_run_success`), and four tests
(`tests/test_roadmap_failure_notifications.py`). None of that is re-specified
here. What remains is two precise defects in how that machinery behaves under
the production topology, and they are this spec's whole scope.

**Defect 1 — the count is keyed by an identity the schedule churns.** Both
reporters key the store row by `workflow.info().workflow_id`. A Temporal
schedule starts every action's workflow under a distinct id — the configured id
with the scheduled time appended — so each scheduled failure finds no prior row,
records count 1, and pages. The landed test that proves counting across runs
does so by restarting *under the same workflow id* (its own comment says so),
which is exactly what the schedule never does. Under the schedule, the incident's
24 identical failures would today produce 24 pages, and the recovery pass —
under yet another fresh id — would find count 0 and report nothing. Silence
became spam, and recovery reporting silently never engages. The stable identity
already exists and is derivable from the workflow's own input:
`roadmap_workflow_id(request.specs_root)`.

**Defect 2 — the failure is dressed as an escalation, and an escalation is the
wrong grammar.** `record_roadmap_failure` writes a pending escalation row with
RETRY/KILL choices and a one-hour deadline, and the page renders buttons plus
"No answer by … applies the default: KILL the node." But the workflow re-raises
and is already FAILED: nothing waits on the resolution, nothing ever calls
`expire_escalation` for the row (its would-be caller is dead), and a button
press has the bridge signal a closed workflow — which fails, leaves the row
pending, and toasts the operator "Could not reach the orchestrator — nothing
recorded, press again." A choice nobody can honor, an hour that never ends, a
row pending forever in the evidence store. The recovery message holds the same
defect in miniature: `_report_run_success` sends through `send_escalation`
with no pre-written row, so the send itself inserts a fresh pending RETRY/KILL
row — for a message that announces recovery. A pass failure is a *fact*: the
corpus already distinguishes an escalation (asks for a choice) from a notice
(`manual_intervention_notice`: "a fact to be told, not a decision to be asked").
This spec moves roadmap failure reporting to the notice grammar — fire and
forget, then re-raise, with Temporal's UI staying the source of truth.

## User Scenarios & Testing

### User Story 1 - The failure count survives the schedule's identity churn (Priority: P1)

Key the durable roadmap-failure record by the roadmap's stable identity —
derived from the run's `specs_root` input — instead of the per-execution
workflow id, and bound repeat paging geometrically so a six-hour incident is a
handful of pages, not one per failure.

**Goal**: consecutive identical failures arriving as separate scheduled
executions accumulate one count, page on a geometric schedule (counts 1, 3, 9,
27, …), and reset with one recovery page on the next green pass — exactly the
behavior the landed tests already prove for restarts under a single workflow id,
now true under the ids the schedule actually mints.

**Independent Test**: run consecutive failing `RoadmapWorkflow` executions over
one specs root under *distinct* workflow ids (the schedule's shape) with a
recording notification seam; assert one accumulating count, pages only at the
geometric thresholds, and a recovery page naming the prior count from a green
run under yet another fresh id.

**Acceptance Scenarios**:

1. **Given** a corpus whose scheduling pass fails identically every run,
   **When** three consecutive executions run under three distinct workflow ids
   over the same specs root, **Then** one count accumulates to 3, the operator
   is paged at counts 1 and 3 only, and the count-3 page names the count.
2. **Given** prior consecutive failures recorded for a corpus, **When** a later
   execution under yet another distinct workflow id completes a green pass,
   **Then** exactly one recovery page names the prior count and the count
   resets.
3. **Given** nine consecutive identical failures over one corpus, each arriving
   as its own execution, **When** they are reported, **Then** pages go out at
   counts 1, 3 and 9 — three pages, not nine.
4. **Given** two corpora under different specs roots failing at the same time,
   **When** their executions interleave, **Then** each corpus keeps its own
   independent count and pages independently.

### User Story 2 - A pass failure is reported as a notice, and the workflow still fails (Priority: P2)

Replace the escalation grammar with the notice grammar for roadmap failure and
recovery reporting: no buttons, no deadline, no pending row — and the workflow
execution still ends FAILED in Temporal with its original exception.

**Goal**: the operator's page states what failed and how many times, offers
nothing, threatens nothing, and leaves nothing pending; the durable fact lives
in the roadmap-failure record the reporter already writes first; Temporal's UI
remains the source of truth because the exception re-raises unchanged.

**Independent Test**: script a failing pass with a recording send seam; assert
the message offers no choice and names no deadline, the workflow execution
fails with the original exception, no pending escalation row exists for the
roadmap, and — with the send seam raising — the failure record still holds the
fact.

**Acceptance Scenarios**:

1. **Given** a scheduling pass that fails, **When** the failure is reported,
   **Then** the message is a notice — it offers no choice, renders no keyboard,
   names no response deadline — and it carries the failure text verbatim with
   the consecutive count.
2. **Given** the failure was reported, **When** the report completes, **Then**
   the workflow execution still ends FAILED in Temporal carrying the pass's own
   exception — the notice precedes the re-raise and replaces nothing.
3. **Given** the notifier is down (the send raises or delivers nothing),
   **When** a pass fails, **Then** the durable roadmap-failure record still
   holds the failure text and count, and no pending escalation row exists for
   the roadmap — there is nothing a button press or an expiry sweep could act
   on.
4. **Given** the reporting path itself is broken (the recording activity
   raises), **When** a pass fails, **Then** the workflow's recorded failure is
   still the pass's own exception, not the reporter's.
5. **Given** prior failures and a green pass, **When** recovery is reported,
   **Then** the recovery message is likewise a notice — no choice, no deadline —
   naming the prior count.

## Functional Requirements

- **FR-001**: The durable roadmap-failure record MUST be keyed by the roadmap's
  stable identity derived from the run's `specs_root` input
  (`roadmap_workflow_id(request.specs_root)`), never by
  `workflow.info().workflow_id` — two executions over the same corpus share one
  count regardless of how each was started (operator start or schedule action).
- **FR-002**: Consecutive identical failures arriving as separate workflow
  executions MUST accumulate one count and reset on a green pass over the same
  corpus — the cross-run mechanism stays the existing store row; no second
  mechanism (time bucketing, a new table, search attributes) is added.
- **FR-003**: Repeated identical failures MUST page only when the count is a
  power of three (1, 3, 9, 27, …), so N consecutive failures produce a number
  of pages that grows with the logarithm of N. The incident's 24 failures
  produce exactly 3 failure pages.
- **FR-004**: Recovery after failures MUST page once naming the prior count and
  reset the count, including when the green execution runs under a different
  workflow id than the failed ones.
- **FR-005**: Roadmap failure and recovery reports MUST be notices: no inline
  keyboard, no offered choice, no response deadline in the text. The message
  carries the failure text verbatim and the consecutive count (or the prior
  count, for recovery), and never a credential.
- **FR-006**: Reporting a roadmap failure or recovery MUST NOT write a pending
  escalation row. For a failure, the durable fact is the roadmap-failure
  record, and it MUST still be written before any send is attempted — a
  notifier that is down loses the message, never the fact.
- **FR-007**: The workflow execution MUST still end FAILED in Temporal after a
  reported failure: the notice is sent, then the original exception re-raises
  unchanged. Swallowing the exception to report it is named in advance as a
  defect.
- **FR-008**: A failure inside the reporting path MUST NOT replace the pass's
  own failure: reporting at the boundary is best-effort, and the workflow's
  recorded failure remains the original exception.

## Success Criteria

- **SC-001**: Under per-execution workflow ids (the schedule's shape), 24
  consecutive identical failed passes over one corpus page the operator exactly
  3 times, and the next green pass pages exactly once, naming 24.
- **SC-002**: A roadmap failure page renders no buttons and names no deadline;
  the bridge can receive no press for it because nothing was offered.
- **SC-003**: Every failed pass remains visible as a FAILED workflow execution
  in Temporal's UI, carrying the pass's own exception.
- **SC-004**: After this spec lands, roadmap failure reporting writes no new
  escalation rows; rows written before it lands are untouched.
- **SC-005**: The full suite is green, the landed 021/us4 tests still prove
  their facts (re-pointed where this spec changes the mechanism they pinned),
  and no dependency is added.

## Edge Cases

- **Alternating distinct failure texts** reset the count on every flip (the
  store's exact-text match), so each alternation pages at count 1. Accepted:
  exact-text equality is the existing mechanism; fuzzier fingerprinting is out
  of scope.
- **An operator-started roadmap** runs under exactly
  `roadmap_workflow_id(specs_root)`, so the stable key equals today's key and
  its behavior is unchanged by US1.
- **The recording activity's store is unwritable**: the activity retries per
  the existing `_FAST` policy; if it still fails, FR-008 keeps the workflow's
  failure the original one. The page is lost; Temporal's UI still shows the
  failure.
- **A notice that fails to deliver** is data, not an error — the existing
  one-attempt `_NOTIFY` posture; the fact is already durable (FR-006).
- **Scheduled executions are invisible to `ergane roadmap status`** (it looks
  up the exact stable id, and scheduled runs carry suffixed ids). Real, but
  pre-existing and not a reporting defect; out of scope.

## Assumptions

- A Temporal schedule starts each action's workflow under a distinct id — the
  configured id with the scheduled time appended. This is the documented
  behavior the dedupe defect turns on; the operator preflight (T001) re-verifies
  it against one real scheduled execution from the 2026-08-09 incident in the
  Temporal UI before dispatch.
- The `ergane-roadmap` schedule itself (paused 2026-08-09 12:05Z with a note
  naming the then-live bug, still paused as of filing) is operator
  infrastructure. Its stale pause is evidence of the loop this spec closes;
  nothing in this spec creates, edits, or resumes it.
- `python-telegram-bot` is already on the approved roster (constitution III);
  no new dependency is needed for a buttonless send — `send_question` already
  sends without a keyboard.
- The landed 021/us4 test file may be edited where this spec changes the
  mechanism its assertions pinned (the escalation-row implementation detail);
  the facts those tests prove — record-before-send, no spam, recovery — must
  survive with re-pointed targets. Landed story numbers stay untouched; this
  spec's stories take new numbers in their own spec.

## Out of Scope

- **The stack being dead entirely** — worker down, Temporal down, a schedule
  action Temporal cannot start. That is `hardening/stack-supervision`, parked
  by the operator; this spec covers the stack being alive and failing.
- **Unpausing the `ergane-roadmap` schedule.** An operator act. The stale pause
  note may be cited as evidence; no task touches the schedule.
- **Cleaning or rewriting historical escalation rows.** History is evidence
  (the 024 discipline).
- **Fingerprinting "similar" failures** beyond the store's exact-text equality.
- **Epic- and node-level notification behavior.** The operator channel for
  running nodes (008) is untouched; so is the epic workflow's escalation
  ladder, including `send_escalation` itself for its epic-side callers.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
```
