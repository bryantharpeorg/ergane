---
state: ready
depends_on_landed: [001-alpha]
---

# Feature Specification: Ready

`state: ready` with one dependency on an attested-landed spec, so it is
dispatchable (acceptance scenario 1).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ready dispatches (Priority: P1)

As the operator, I see a ready spec dispatch.

**Acceptance Scenarios**:

1. **Given** a ready spec with a satisfied edge, **When** the roadmap is read, **Then** it is dispatchable.

- **FR-001**: Ready MUST dispatch when its edges are satisfied.