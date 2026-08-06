# Feature Specification: Duplicate Story Key

**Feature Branch**: `016-duplicate-story-key`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Invalid fixture. Two headers declare User Story 2, so the requirement key
`US2` is ambiguous and a node could not be dispatched against it unambiguously. The
parser must reject the file and name `US2`. Every story here is otherwise well-formed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First story (Priority: P1)

As the corpus, I hold the key US1, which appears exactly once.

**Why this priority**: Isolates the failure to the duplicated key.

**Independent Test**: Parse the file and assert the error names US2, not US1.

**Acceptance Scenarios**:

1. **Given** a spec with a unique story key, **When** it is parsed, **Then** that key is not reported as duplicated.

---

### User Story 2 - Second story (Priority: P2)

As the corpus, I hold the key US2 first.

**Why this priority**: The first of the two claimants to US2.

**Independent Test**: Parse the file and assert the error names US2.

**Acceptance Scenarios**:

1. **Given** two stories numbered 2, **When** the spec is parsed, **Then** the duplicate key is rejected.

---

### User Story 2 - Second story, declared again (Priority: P3)

As the corpus, I claim the key US2 a second time, with a different title and priority.

**Why this priority**: The second claimant, proving the collision is on the key rather
than the title.

**Independent Test**: Parse the file and assert the error names US2.

**Acceptance Scenarios**:

1. **Given** a duplicated story number, **When** the spec is parsed, **Then** neither claimant silently wins.

---

### Edge Cases

- What happens when stories are renumbered by hand? (The collision is rejected rather
  than resolved by position.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST reject a spec that declares the same requirement key twice, naming the duplicated key.
