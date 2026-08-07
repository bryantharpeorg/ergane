---
state: ready
depends_on_landed: [001-a]
---

# Feature Specification: B

Cycle member B; depends on A. A ⇄ B is the cycle; the third spec `003-c` is
outside it and must not appear in the finding.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - B works (Priority: P1)

As anyone, I use B.

**Acceptance Scenarios**:

1. **Given** B, **When** I use it, **Then** it works.

- **FR-001**: B MUST work.