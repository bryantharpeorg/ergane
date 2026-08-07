---
state: ready
depends_on_landed: [002-nowhere]
---

# Feature Specification: Dangling Dep

`depends_on_landed` names `002-nowhere`, a spec directory this corpus does
not hold. An edge to nothing can never be satisfied, and silently ignoring
it would let a typo pass as "blocked" forever — the deriver's discipline,
applied one level up: the entry is rejected naming the offender and the file.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - X works (Priority: P1)

As anyone, I use X.

**Acceptance Scenarios**:

1. **Given** X, **When** I use it, **Then** it works.

- **FR-001**: X MUST work.