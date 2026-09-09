---
state: ready
---

# Feature Specification: a declared gate deadline reaches the workflow

## Incident and scope

The approved 600-to-900-second test deadline exposed a disconnected timer.
The manifest reaches the gate subprocess, but dispatch pins the default
`VerificationConfig.gate_timeout_s=600`; `_verify` consequently gives the
activity a 660-second heartbeat deadline. The activity heartbeats before each
gate, not periodically during a gate. A valid 900-second gate can therefore
lose its activity before its declared time expires.

This is the narrow prerequisite to restarting the Codex-primary migration.
Keep `timeouts` as the sole declaration. Do not introduce another ladder dial,
change defaults globally, bypass gates, or alter already-running epic inputs.
The existing two-hour total activity ceiling is unchanged: this story repairs
the heartbeat watchdog, not support for arbitrarily long complete suites. The
requested single 900-second gate fits within that independent ceiling.

### User Story 1 - Both dispatch paths pin the manifest-derived watchdog (Priority: P1)

As an operator, declaring a gate deadline gives that gate its full execution
window, whether I start an epic directly or through the roadmap.

**Acceptance Scenarios**:

1. **Given** a manifest with a test gate declared for 900 seconds, **When** the CLI constructs the epic input, **Then** the pinned gate watchdog basis is 900 and the verification activity receives its existing 60-second grace beyond that basis — proven by committed tests exercising the dispatch and activity-scheduling seams, not a source-string assertion.
2. **Given** the same manifest and a roadmap promotion-persona override, **When** a child epic is constructed, **Then** it carries the same 900-second watchdog basis, preserves the promotion override and every unrelated ladder field, and schedules verification with the same grace — proven by committed tests through the roadmap configuration read and child-input construction.
3. **Given** mixed gate deadlines, undeclared deadlines, both supported manifest versions, or no gates, **When** dispatch resolves its configuration, **Then** its watchdog basis is the largest effective deadline among declared gates, an omitted gate deadline uses the existing default, no gates retains the existing default, and a complete set of shorter explicit deadlines is not silently raised to the default — proven by table-driven committed tests.
4. **Given** an epic input already pinned at dispatch and a later manifest edit, **When** verification is scheduled, **Then** its pinned watchdog remains unchanged, old inputs retain their original defaults, malformed timeout declarations retain their existing refusal, and gate execution still uses the existing timeout resolution and termination behavior — proven by committed integration and regression tests.

**Independent Test**: Carry one temporary manifest through the production
dispatch readers into an `EpicInput`, then observe the options supplied to
the actual verification activity scheduling seam. Assert both 900/960 and
the unchanged default 600/660 pair without a fifteen-minute sleep.

## Functional Requirements

- **FR-001**: Dispatch MUST derive the gate watchdog basis from the effective deadlines of the gates the target manifest declares.
- **FR-002**: Direct CLI and roadmap dispatch MUST share that derivation and MUST preserve unrelated verification and promotion configuration.
- **FR-003**: The existing per-gate `timeouts` declaration and default MUST remain the only governing sources; no new user setting or dependency may be introduced.
- **FR-004**: Verification MUST retain the existing watchdog grace, bounded subprocess termination, and pinned-input semantics; running epics and historical inputs MUST NOT be silently migrated.
- **FR-005**: Regression tests MUST exercise the configuration-to-dispatch-to-verification connection that the incident exposed, including its default and negative controls.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
```
