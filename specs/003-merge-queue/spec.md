# Feature Specification: Merge Discipline via GitHub Merge Queue

**Feature Branch**: `003-merge-queue`

**Created**: 2026-07-24

**Status**: Draft

**Input**: Component 3 of the Ergane factory (D-007, D-008, D-010, D-017, D-018):
branch-per-node landing through GitHub's native merge queue with rebase-and-retest;
the factory enqueues, awaits the outcome, and routes conflicts/failures to the debugger
persona or the operator. Built last — most environment-dependent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verified work lands through the queue (Priority: P1)

As the WorkGraph interpreter, when a node passes inner-loop verification, its branch
becomes a PR that is enqueued for auto-merge; GitHub's merge queue rebases it onto the
current queue head, re-runs the deterministic required checks against the rebased
result, and merges on green — serialized, so parallel nodes never race into the target
branch.

**Why this priority**: This is the component's core value: verified work reaching main
safely without human shepherding.

**Independent Test**: On a sample public repo with merge queue enabled, drive one
node branch through PR → enqueue → merged, and assert the factory observed the final
state correctly.

**Acceptance Scenarios**:

1. **Given** a node with verdict PASS on branch `factory/<epic>/<node>`, **When** the
   landing step runs, **Then** a PR is opened (ready, not draft) with the node's spec
   reference and verification summary in the body, and auto-merge into the queue is
   requested.
2. **Given** an enqueued PR, **When** the merge queue processes it, **Then** the
   factory takes no further action while checks run — required checks are the target
   repo's deterministic gates only (never the LLM judge).
3. **Given** the queue merges the PR, **When** the factory observes completion,
   **Then** the node is marked MERGED, its worktree is cleaned up, and dependents that
   gate on landing (not just verification) unlock.
4. **Given** two sibling nodes passing verification near-simultaneously, **When** both
   enqueue, **Then** both land (or fail) strictly serialized by the queue with the
   second retested on top of the first — never a broken interleaving on the target
   branch.

---

### User Story 2 - Queue rejection recovery (Priority: P2)

As the factory operator, when the queue rejects a PR — rebase conflict or checks red on
the rebased tree — the factory doesn't silently stall: it re-syncs the branch, hands
real conflicts or regressions to the debugger persona, and only escalates to me when
that fails.

**Why this priority**: Rebase-and-retest failures are the normal cost of parallel
agents; unhandled, they'd strand verified work.

**Independent Test**: Manufacture a conflicting pair of PRs on the sample repo; assert
the loser is detected, re-driven, and either lands after repair or escalates.

**Acceptance Scenarios**:

1. **Given** a PR removed from the queue because required checks failed on the rebased
   tree, **When** the factory observes the rejection, **Then** the node re-enters the
   inner loop: branch updated onto the new target-branch head, verification (component
   2) re-run, and the PR re-enqueued on pass.
2. **Given** a PR that cannot be rebased (merge conflict), **When** detected, **Then**
   the `debugger` persona gets one bounded cycle in the node's worktree to resolve the
   conflict (fresh attribution key, conflict context in prompt), after which the branch is
   re-verified and re-enqueued.
3. **Given** the recovery cycle fails again, **When** that outcome lands, **Then** a
   Telegram escalation fires with the queue history and choices [retry | kill node |
   pause epic]; 1 hour of silence → kill, with the branch preserved (never deleted).
4. **Given** any rejected or killed node, **When** cleanup runs, **Then** the node's
   commits remain reachable on its branch (no work lost, constitution VI).

---

### User Story 3 - Target repo onboarding (Priority: P3)

As the factory operator, I can point the factory at a new public target repo and get a
checklist-verified setup: merge queue enabled on the default branch, required checks
matching `factory.yaml` gates, and branch protection consistent with factory
assumptions — before any node runs against it.

**Why this priority**: Prevents an entire class of "queue silently unavailable"
failures; operational hygiene rather than core flow.

**Independent Test**: Run onboarding validation against a repo with and without merge
queue configured; assert pass/fail with actionable findings.

**Acceptance Scenarios**:

1. **Given** a candidate target repo, **When** onboarding validation runs, **Then** it
   verifies: repo is public (queue available on any plan), merge queue enabled on the
   default branch, required checks exist and correspond to the repo's `factory.yaml`
   gates, and reports each finding.
2. **Given** a repo failing any check, **When** validation concludes, **Then** the repo
   is rejected for dispatch with instructions for the operator; nothing is dispatched
   against an unvalidated repo.

---

### Edge Cases

- Merge queue disabled mid-flight (settings change) → enqueue fails; treated as queue
  rejection with escalation, not a crash.
- PR merged manually by a human while enqueued → factory reconciles: observes merged
  state, marks node MERGED, proceeds.
- PR closed manually without merge → treated as operator kill; branch preserved;
  escalation notes the manual intervention.
- Queue outcome events lost (webhook/notification gap) → factory reconciles by polling
  PR state on a timer before declaring the node stalled.
- Target branch advanced by non-factory commits between verification and merge → the
  queue's rebase-and-retest covers it by design; no special handling.
- Two epics targeting the same repo → both use the same queue; serialization is
  repo-level, cross-epic ordering is whatever the queue decides.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every node MUST land through a PR from its own branch
  (`factory/<epic>/<node>`, the 005 FR-013 worktree branch); direct pushes to the
  target branch are prohibited.
- **FR-002**: PRs MUST be opened ready-for-review with the node's spec reference and a
  verification summary, and enqueued via the platform's auto-merge/merge-queue
  mechanism — the factory MUST NOT implement its own serialization of landings.
- **FR-003**: Merge-queue required checks MUST be the deterministic gates only; the
  LLM judge MUST never be a required check (D-008).
- **FR-004**: The factory MUST await and correctly classify queue outcomes: merged,
  checks-failed-on-rebase, conflict/unmergeable, dequeued-by-human — including by
  reconciliation polling when event delivery is unreliable.
- **FR-005**: On checks-failed-on-rebase, the node MUST re-enter the inner
  verification loop on an updated branch and re-enqueue on pass.
- **FR-006**: On conflict, the `debugger` persona MUST get one bounded
  resolve-verify-re-enqueue cycle before human escalation.
- **FR-007**: Escalations MUST offer [retry | kill node | pause epic] via Telegram
  inline buttons mapped to orchestration signals; 1 hour of silence defaults to kill.
- **FR-008**: Node branches MUST never be deleted by failure paths; killed or rejected
  work remains reachable on its branch.
- **FR-009**: Nodes MUST distinguish "verified" from "merged" states so downstream
  edges can declare which they gate on; default gating is on verified (merge is
  asynchronous), with merge-gating available per edge.
- **FR-010**: Target repo onboarding validation MUST block dispatch against repos
  whose queue/branch-protection/required-check configuration does not match the
  factory's assumptions, with actionable findings.

### Key Entities

- **Landing**: the lifecycle record of one node's journey from PASS to
  MERGED/REJECTED/KILLED — PR reference, enqueue time, queue outcomes, recovery
  attempts.
- **QueueOutcome**: classified result of one enqueue — merged | checks_failed |
  conflict | dequeued_by_human | stalled.
- **TargetRepoProfile**: onboarding validation result for a repo — queue availability,
  required-check mapping to `factory.yaml` gates, protection settings, pass/fail
  findings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero broken target-branch states caused by factory merges across
  concurrent-node test runs (the queue's rebase-and-retest guarantee, observed).
- **SC-002**: 100% of queue rejections result in exactly one of: successful re-land,
  bounded debugger recovery, or operator escalation — never a silent stall (stall
  detection bounded by the reconciliation timer).
- **SC-003**: Zero LLM-judge executions attributable to merge-queue activity.
- **SC-004**: Zero node branches deleted on any failure path.
- **SC-005**: 100% of dispatches occur against onboarding-validated repos.

## Work Graph

One node per story, compiled by `factory-epic derive` into the DAG the interpreter
runs (005 FR-011). Recovery waits on landing because it re-drives the PR the landing
path opens — there is nothing to recover before a branch can be enqueued. Onboarding
validation waits on neither: it inspects a repo's queue and branch-protection
configuration and blocks dispatch, which is a pre-flight check rather than a step in
the landing path, so it is a leaf the scheduler may take at any point.

Every functional requirement this spec declares is claimed by exactly one node — an
unclaimed one would be a requirement the factory builds nothing for and verifies
against nothing. Attempt timeouts resolve from the persona registry; no story here
argues for an override.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-009]
US2:
  depends_on: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
US3:
  depends_on: []
  implements: [FR-010]
```

## Assumptions

- Target repos are public GitHub repos, so the native merge queue is available on any
  plan (D-007); private-on-Free targets are out of scope (would reopen the
  custom-queue decision).
- The `gh` CLI is present on worker hosts and authenticated for the target repos.
- Components 1 and 2 are complete: usage tracking attributes the debugger cycles; verification
  produces the PASS verdicts and re-runs during recovery.
- The first target is the dedicated sample repo (D-010), created and
  onboarding-validated before this component's E2E tests.
- Exact GitHub event/polling mechanics (webhooks vs. polling cadence) are plan-level
  detail; this spec only requires reliable outcome classification (FR-004).
