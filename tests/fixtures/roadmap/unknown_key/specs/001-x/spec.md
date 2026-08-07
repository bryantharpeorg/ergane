---
state: ready
priority: P1
---

# Feature Specification: Unknown Key

Carries an unknown frontmatter key `priority`. The closed key set
(`state`, `depends_on_landed`) is the deriver's discipline applied one level
up: silently dropping a key an author wrote is how a roadmap comes to mean
something other than it says.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - X works (Priority: P1)

As anyone, I use X.

**Acceptance Scenarios**:

1. **Given** X, **When** I use it, **Then** it works.

- **FR-001**: X MUST work.