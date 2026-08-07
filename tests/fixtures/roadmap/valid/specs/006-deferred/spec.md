---
state: deferred
---

# Feature Specification: Deferred

`state: deferred` — never dispatchable, regardless of edges.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deferred parks (Priority: P3)

As the operator, I see deferred specs parked.

**Acceptance Scenarios**:

1. **Given** a deferred spec, **When** the roadmap is read, **Then** it is not dispatchable.

- **FR-001**: Deferred MUST never dispatch.