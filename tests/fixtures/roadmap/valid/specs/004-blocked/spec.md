---
state: ready
depends_on_landed: [002-bravo]
---

# Feature Specification: Blocked

`state: ready` but its one dependency names `002-bravo`, which is `draft`
(not landed), so the edge is unsatisfied and the spec is blocked with that
edge named (acceptance scenario 5) — a legitimate waiting state, not a
grammar rejection.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Blocked waits (Priority: P2)

As the operator, I see a blocked spec name its blocker.

**Acceptance Scenarios**:

1. **Given** a ready spec with an unsatisfied edge, **When** the roadmap is read, **Then** it is blocked naming the unsatisfied edge.

- **FR-001**: Blocked MUST name its unsatisfied dependencies.