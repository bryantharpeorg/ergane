# Feature Specification: Functional Requirement Missing Its Modal

**Feature Branch**: `014-fr-missing-modal`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Invalid fixture. `FR-002` states a behaviour without MUST or SHALL, so it is
not a requirement the judge can score against — the parser must reject the file and
name `FR-002`. FR-001 (MUST), FR-003 (SHALL) and the story are well-formed, so FR-002
is the only defect.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Well-formed story (Priority: P1)

As the corpus, I carry one valid story so the file's only defect is FR-002.

**Why this priority**: Isolates the failure under test.

**Independent Test**: Parse the file and assert the error names FR-002 and no other
requirement.

**Acceptance Scenarios**:

1. **Given** a spec whose second functional requirement states no obligation, **When** it is parsed, **Then** the error names that requirement.

---

### Edge Cases

- What happens when a requirement is phrased as an aspiration? (Rejected — an
  unfalsifiable requirement cannot gate a node.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST reject a functional requirement whose body carries no obligation keyword, naming that requirement.
- **FR-002**: The system records a receipt for every refund it processes.
- **FR-003**: The parser SHALL accept SHALL as an obligation keyword alongside MUST.
