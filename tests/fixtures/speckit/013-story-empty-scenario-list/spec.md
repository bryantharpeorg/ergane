# Feature Specification: Story With An Empty Scenario List

**Feature Branch**: `013-story-empty-scenario-list`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Invalid fixture, second shape of "zero acceptance scenarios": User Story 2
declares `**Acceptance Scenarios**:` but lists no numbered items under it. The parser
must reject the file and name `US2`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Well-formed story (Priority: P1)

As the corpus, I carry one valid story so the file's only defect is the empty list
below.

**Why this priority**: Isolates the failure under test.

**Independent Test**: Parse the file and assert the error names US2, not US1.

**Acceptance Scenarios**:

1. **Given** a spec whose second story declares an empty scenario list, **When** it is parsed, **Then** the error names that story.

---

### User Story 2 - Story whose scenario list is empty (Priority: P2)

As the corpus, I declare the acceptance-scenarios heading and then say nothing under
it — the shape a half-filled template leaves behind.

**Why this priority**: An unfilled template section is indistinguishable from an
unverifiable story, so it is rejected the same way.

**Independent Test**: None — that is the point.

**Acceptance Scenarios**:

---

### Edge Cases

- What happens when the template heading survives but its items were never written?
  (Rejected, naming the story.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST reject a user story whose acceptance-scenario list is empty, naming that story.
