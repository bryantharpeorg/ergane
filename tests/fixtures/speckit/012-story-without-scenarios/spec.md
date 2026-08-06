# Feature Specification: Story Without Scenarios

**Feature Branch**: `012-story-without-scenarios`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Invalid fixture. User Story 2 carries no `**Acceptance Scenarios**:` section
at all — the parser must reject the file and name `US2` as the offender. US1 and the
functional requirement are well-formed, so US2 is the only defect.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Well-formed story (Priority: P1)

As the corpus, I carry one valid story so the file's only defect is the story below.

**Why this priority**: Isolates the failure under test.

**Independent Test**: Parse the file and assert the error names US2, not US1.

**Acceptance Scenarios**:

1. **Given** a spec with one valid and one scenario-less story, **When** it is parsed, **Then** the error names the scenario-less story.

---

### User Story 2 - Story with no acceptance scenarios (Priority: P2)

As the corpus, I describe a journey but never state how to accept it.

**Why this priority**: A story with no acceptance scenarios cannot be verified, so the
parser refuses to dispatch against it.

**Independent Test**: None — that is the point.

---

### Edge Cases

- What happens when a story is still being drafted? (It is rejected until it states its
  acceptance scenarios.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST reject a user story that declares no acceptance scenarios, naming that story.
