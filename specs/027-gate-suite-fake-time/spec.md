---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 027-gate-suite-fake-time

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - Three tests wait out real 60-second clocks and are ~53% of every gate run: the suite's time-skipping Temporal env skips workflow timers but cannot skip an in-flight activity, and ScriptedWorld's heartbeat_then_block leaves the activity running so real heartbeat timeouts must elapse. The gate pays ~3 idle minutes on every attempt, several times per node. (Priority: P2)

Three tests wait out real 60-second clocks and are ~53% of every gate run: the suite's time-skipping Temporal env skips workflow timers but cannot skip an in-flight activity, and ScriptedWorld's heartbeat_then_block leaves the activity running so real heartbeat timeouts must elapse. The gate pays ~3 idle minutes on every attempt, several times per node.

**Acceptance Scenarios**:

1. **Given** the finding `ci/gate-suite-waits-out-real-clocks`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `tests/test_interpreter.py:2613`
- `tests/test_interpreter.py:3468`
- `tests/test_workgraph_sweep.py:1476`
- `tests/test_interpreter.py:1659`
- Measured 2026-08-11 in a clean env (scratch FACTORY_ROOT, Telegram vars unset, per hardening/test-suite-writes-to-the-live-evidence-store): test_no_epic_ever_dispatches_a_node_with_an_unmet_dependency 60.81s, test_a_dead_agent_is_still_detected_under_a_derived_heartbeat_timeout 60.20s, test_a_heartbeat_timeout_delivers_its_snapshot_to_teardown 60.19s — 181.2s of a 182.58s three-test run. Full suite is ~5m45s, so these three are ~53%; converting them to fake time yields ~2m40s. MECHANISM. Both files already use WorkflowEnvironment.start_time_skipping() (test_interpreter.py:1659, test_workgraph_sweep.py:366), but time-skipping advances workflow timers only — an activity still executing runs on the real clock. heartbeat_then_block=True makes the scripted attempt heartbeat once then block forever, so Temporal's real heartbeat timeout must elapse; all three scripted nodes (us1-us3, timeout_override_s=20, derived ~10s heartbeat bound) pay it, which is where ~60s per test comes from. The sweep test's 60s should be re-verified per-shape before restructuring — it runs five epics and its real-time source may differ. FIX DIRECTIONS. (1) End the activity and simulate the timeout - deliver last_heartbeat_details to teardown without real waiting; (2) shrink the real bounds to <=2s while keeping what each test proves (dead-agent detection under a DERIVED bound incl. the history assertion, snapshot delivery, the SC-002 mid-flight sweep); (3) last resort, move them out of the gate tier - but a tier split must be enforced in the gate command itself, because markers are decorative (nothing passes -m in the gate or CI; see interpreter/ci-failure-never-reaches-an-agent BLAST RADIUS). COST COUPLING. Gate wall clock is paid on every attempt and every recovery, and slow gates court gate TIMEOUT - 006/us4 died to one. CONSTRAINT. Never run the suite with the operator env exported; measure with pytest --durations=30 in a clean env.

## Functional Requirements

- **FR-001**: The factory MUST address `ci/gate-suite-waits-out-real-clocks`: Three tests wait out real 60-second clocks and are ~53% of every gate run: the suite's time-skipping Temporal env skips workflow timers but cannot skip an in-flight activity, and ScriptedWorld's heartbeat_then_block leaves the activity running so real heartbeat timeouts must elapse. The gate pays ~3 idle minutes on every attempt, several times per node.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
