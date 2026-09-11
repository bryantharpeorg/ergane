---
state: landed
# Attested landed 2026-09-11. US1 556803eaa89e (#506) on attempt 1 — observed
# on ergane-buildout by content.
fixes:
  - tests/unpark-order-race-is-hidden-by-a-set-assertion
---
# Feature Specification: the unpark test observes its held child before it wakes the roadmap

## User Stories *(mandatory)*

### User Story 1 - the unpark scenario has one deterministic order (Priority: P1)

As the operator, I want the roadmap-unpark regression to establish that its
held child is running before it sends the signal that advances the roadmap, so
the gate tests the declared operator sequence instead of racing a
continue-as-new boundary.

**Why this priority**: This test has now failed two independent factory gates.
The second occurrence was the only failure in PR500's native merge group after
6,218 tests passed, so it blocks unrelated spec changes from landing.

**Independent Test**: Run
`tests/test_roadmap_prompt_assembly.py::test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it`
repeatedly against the committed change and inspect its exact dispatch-order
assertion. Moving the new wait back below `unpark_spec` is the negative control:
the already-recorded reproduction intermittently completes the original run
before the query observes `002-bravo`.

**Acceptance Scenarios**:

1. **Given** `001-runtime-root` is parked and `002-bravo` is configured as the
   held child, **When** the test reaches its operator edit and `unpark_spec`
   signal, **Then** its code has already awaited `_await_running(handle,
   "002-bravo")` on that same handle.
2. **Given** the held child is observed before the roadmap is woken, **When**
   the test completes, **Then** it asserts the exact dispatch sequence
   `['002-bravo', '001-runtime-root']`, preserving order and multiplicity.
3. **Given** this repair, **When** the implementation diff is inspected,
   **Then** it changes only the roadmap-prompt test and focused evidence; it
   does not change `RoadmapWorkflow`, the scripted child's hold semantics, a
   timeout, or any production module.
4. **Given** the historical failure mechanism, **When** the test waits for
   `002-bravo`, **Then** the wait remains the existing state-based
   `_await_running` query rather than a sleep or a longer timeout.

## Functional Requirements *(mandatory)*

- **FR-001**: The unpark test MUST observe `002-bravo` in `status.running`
  before editing the parked spec or sending `unpark_spec`.
- **FR-002**: The final dispatch assertion MUST compare the ordered list to
  `['002-bravo', '001-runtime-root']`; set conversion or other multiplicity
  loss is forbidden.
- **FR-003**: The repair MUST reuse `_await_running` and MUST NOT add sleeps,
  increase the 30-second bound, or weaken any assertion.
- **FR-004**: The story MUST NOT change production behavior. Its implementation
  scope is `tests/test_roadmap_prompt_assembly.py` plus one bounded evidence
  artifact if runtime proof is committed.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
```

## Assumptions

- The production roadmap behavior is not implicated. The failure is in test
  steering: `unpark_spec` can cause `001-runtime-root` to dispatch and complete
  before the test has established that `002-bravo` is the in-flight child.
- `workflow.start_child_workflow` plus the roadmap's quiescent
  continue-as-new is correct and out of scope.
