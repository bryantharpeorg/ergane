---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 031-scheduler-failure-notify

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - A RoadmapWorkflow that dies before dispatching anything reports to no one: 24 consecutive failed scheduled executions over 6 hours produced no Telegram message, no ledger row, and no finding — the operator learned of it by looking (Priority: P2)

A RoadmapWorkflow that dies before dispatching anything reports to no one: 24 consecutive failed scheduled executions over 6 hours produced no Telegram message, no ledger row, and no finding — the operator learned of it by looking

**Acceptance Scenarios**:

1. **Given** the finding `roadmap/scheduler-failures-reach-nobody`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `factory/roadmap/workflow.py:741`
- `factory/notify/service.py`
- Filed 2026-08-10, splitting out the half of roadmap/capacity-query-rejects-every-pass that 021 did not fix. That finding's own note says 'Second finding, filed separately in spirit' — it never was, so it resolved with the typo and the real hazard would have gone with it. Mechanism: the operator channel (008) carries agent questions and escalations, which are things a RUNNING node raises. A scheduling pass that fails inside count_open_epics dies before any node exists, so there is nothing to raise a question about and no attempt to write a ledger row for; the failure is visible only in Temporal's own UI. Evidence: 24 scheduled executions FAILED between 2026-08-09 06:00Z and 12:05Z with 'invalid ExecutionStatus value RUNNING', and the operator discovered it by inspection, not by being told. Why it stays critical after the typo is fixed: the blind spot is not specific to that bug. Any exception in a pre-dispatch activity — capacity, corpus read, onboarding — has the same silence, and the roadmap is the one workflow that is supposed to run unattended. Related: hardening/stack-supervision covers the stack being dead; this covers the stack being alive and failing. Second-order evidence from the same episode: the schedule was paused 2026-08-09 12:05Z with a note naming the bug, 021/us1 landed the fix later that day, and as of 2026-08-10 the schedule is still paused — nothing closes that loop either.

## Functional Requirements

- **FR-001**: The factory MUST address `roadmap/scheduler-failures-reach-nobody`: A RoadmapWorkflow that dies before dispatching anything reports to no one: 24 consecutive failed scheduled executions over 6 hours produced no Telegram message, no ledger row, and no finding — the operator learned of it by looking.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
