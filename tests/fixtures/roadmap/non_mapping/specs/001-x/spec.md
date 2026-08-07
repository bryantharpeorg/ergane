---
- a sequence
- not a mapping
---

# Feature Specification: Non-Mapping

Frontmatter that is a YAML sequence rather than a mapping of keys. A spec
whose intent block is not a mapping has no `state` to read, and is rejected
rather than guessed at.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - X works (Priority: P1)

As anyone, I use X.

**Acceptance Scenarios**:

1. **Given** X, **When** I use it, **Then** it works.

- **FR-001**: X MUST work.