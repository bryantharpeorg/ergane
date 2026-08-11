---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 025-ci-red-recovery

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - A red required check is treated as a stale base: the interpreter syncs and re-enqueues without routing the CI log to any agent, so the recovery cycle re-runs identical code and the node is KILLED with its dependents (Priority: P2)

A red required check is treated as a stale base: the interpreter syncs and re-enqueues without routing the CI log to any agent, so the recovery cycle re-runs identical code and the node is KILLED with its dependents

**Acceptance Scenarios**:

1. **Given** the finding `interpreter/ci-failure-never-reaches-an-agent`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `factory/workgraph/workflow.py:2084`
- `factory/workgraph/workflow.py:2126`
- `factory/mergequeue/models.py:203`
- `factory/workgraph/workflow.py:2093`
- Observed 2026-08-09 on epic-021-roadmap-operability/us1, which produced a correct fix, passed gate 'test' (exit 0), passed the judge on all three scenarios, then failed the required CI check twice and was KILLED, taking us2/us3/us4 down at attempt 0 without them ever running.

MECHANISM. CHECKS_FAILED is in _RECOVERY_OUTCOMES (workflow.py:2084), whose recovery cycle syncs the node branch onto the new target head and re-enqueues (:2126) on the assumption that a failing check means a stale base. Nothing carries the failing check's log, job url or output back to an implementer attempt. The recovery therefore re-ran byte-identical code: git diff between the attempt-1 code commit and the attempt-2 tip is EMPTY, the only new objects being two salvage commits. max_recovery_cycles defaults to 1 (mergequeue/models.py:203), so one no-op cycle exhausted the bound and the landing went KILLED (:2093), which makes dependents unreachable.

WHY THE GATE DID NOT CATCH IT. factory.yaml declares gate test = 'uv run pytest -q' and .github/workflows/test.yml runs the identical command. The commands do not differ; the MACHINES do. The worker host has Temporal on 127.0.0.1:7233, CI does not. The node added a live test whose skip guard caught OSError and RPCError, but temporalio's Client.connect raises RuntimeError against a refused port, so the guard never fired in CI and the test errored instead of skipping. Green locally, red in CI, by construction and not by flake.

WHY THE JUDGE DID NOT CATCH IT. The judge quoted the guard accurately -- 'catches OSError and RPCError and calls pytest.skip with a descriptive named reason' -- and passed it. The judge reads a diff; it does not execute one against an environment lacking the service.

BLAST RADIUS. Any story adding a test that depends on a service present on the worker host and absent in CI. Ergane's own suite has four such tiers (live_proxy, live_telegram, live_epic, live_merge). Markers do not mitigate: nothing passes -m in either CI or the gate, and live_capacity was not even registered in pyproject markers, so every live test in this repo skips by guard alone.

COST OF THE ONE OBSERVED INSTANCE. 28.8M input tokens, 394 API calls, two 5-minute CI runs, roughly 2.5 hours wall clock, and zero landed output.

CANDIDATE FIXES, IN INCREASING ORDER OF AMBITION. (1) Route the failing check's log tail into a fresh implementer attempt so a recovery is a retry with evidence rather than a blind re-enqueue. (2) Distinguish a check that fails identically before and after the sync from one that could plausibly be staleness, and do not spend a recovery cycle on the former. (3) Run the declared gate in an environment that matches CI, so a host-only dependency cannot pass the gate at all. (4) Require live-tier tests to prove their own skip with the dependency unreachable -- written into 021 plan.md trap 0 and tasks.md T003a as a per-spec mitigation, which is not a factory-level fix.

### User Story 2 - test_kill_with_n_in_flight_salvages_every_one_before_terminating asserts a timing coincidence -- that a sampled in-flight set was observed at size 3 -- so under CI load it fails on a diff that never touched it. Because it is inside the single required check, a flake spends a node's only recovery cycle, and two flakes in a row kill the node and every dependent. (Priority: P2)

test_kill_with_n_in_flight_salvages_every_one_before_terminating asserts a timing coincidence -- that a sampled in-flight set was observed at size 3 -- so under CI load it fails on a diff that never touched it. Because it is inside the single required check, a flake spends a node's only recovery cycle, and two flakes in a row kill the node and every dependent.

**Acceptance Scenarios**:

1. **Given** the finding `ci/flaky-concurrency-test-is-a-random-epic-killer`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `tests/test_interpreter.py:4822`
- `factory/workgraph/workflow.py:2084`
- Fired 2026-08-09 17:54Z against 021-roadmap-operability/us3, whose diff touches only factory/roadmap/workflow.py. Failure: 'AssertionError: never saw all three in flight; running_sets=[{us1, us2}, {us1, us2}]' -- the third node had not been dispatched yet when the kill signal landed, so the sampler never caught the overlap. Nothing about the node's change is implicated. Re-run on the recovery head (31328267468) passed in 5m20s, which is the definition of a flake. Cost profile: a red required check is CHECKS_FAILED, which is recovery-eligible, and max_recovery_cycles is 1 -- so the first flake consumes the entire recovery budget silently and the second kills the node plus its dependents. 021 lost four stories to a CI red this morning by exactly this route (see interpreter/ci-failure-never-reaches-an-agent); that one was a real defect, this one would have been luck. Fix direction: assert the durable fact the test already has -- three salvage commits, three KILLED states -- rather than the sampled coincidence, or make the script await all three dispatches before signalling the kill. Do not paper over it with a retry on the required check: that hides real regressions in the one gate the merge queue trusts.

## Functional Requirements

- **FR-001**: The factory MUST address `interpreter/ci-failure-never-reaches-an-agent`: A red required check is treated as a stale base: the interpreter syncs and re-enqueues without routing the CI log to any agent, so the recovery cycle re-runs identical code and the node is KILLED with its dependents.
- **FR-002**: The factory MUST address `ci/flaky-concurrency-test-is-a-random-epic-killer`: test_kill_with_n_in_flight_salvages_every_one_before_terminating asserts a timing coincidence -- that a sampled in-flight set was observed at size 3 -- so under CI load it fails on a diff that never touched it. Because it is inside the single required check, a flake spends a node's only recovery cycle, and two flakes in a row kill the node and every dependent.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: []
  implements: [FR-002]
```
