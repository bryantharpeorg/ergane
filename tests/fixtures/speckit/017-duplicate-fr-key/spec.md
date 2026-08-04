# Feature Specification: Duplicate Functional Requirement Key

**Feature Branch**: `017-duplicate-fr-key`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Invalid fixture. `FR-002` is declared twice with different bodies, so the
requirement key is ambiguous. The parser must reject the file and name `FR-002`. The
story, FR-001 and FR-003 are well-formed, so the duplicate is the only defect.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Well-formed story (Priority: P1)

As the corpus, I carry one valid story so the file's only defect is the duplicated
functional requirement key.

**Why this priority**: Isolates the failure under test.

**Independent Test**: Parse the file and assert the error names FR-002.

**Acceptance Scenarios**:

1. **Given** a spec declaring one FR key twice, **When** it is parsed, **Then** the error names the duplicated key.

---

### Edge Cases

- What happens when two authors append requirements to the same section? (The key
  collision is rejected rather than last-write-wins.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST reject a spec that declares the same functional requirement key twice, naming the duplicated key.
- **FR-002**: The system MUST record a receipt for every refund it processes.
- **FR-003**: The system SHALL retain receipts for seven years.
- **FR-002**: The system MUST email a receipt for every refund it processes.
