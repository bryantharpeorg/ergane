---
state: building
---

# Feature Specification: Unknown State

Declares `state: building` — not one of `draft | ready | deferred | landed`.
Only the system may say `building`; the author's vocabulary is the four intent
states, and an unknown value is rejected rather than coerced.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - X works (Priority: P1)

As anyone, I use X.

**Acceptance Scenarios**:

1. **Given** X, **When** I use it, **Then** it works.

- **FR-001**: X MUST work.