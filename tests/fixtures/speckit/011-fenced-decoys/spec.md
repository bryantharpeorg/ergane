# Feature Specification: Fenced Decoys

**Feature Branch**: `011-fenced-decoys`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Fixture isolating fence masking. Every requirement-shaped line inside a
fenced block is inert; the real requirements sit after the fences, proving fences both
open and close.

## User Scenarios & Testing *(mandatory)*

The section opens with the template excerpt the factory hands to agents. None of it is
a requirement:

```markdown
### User Story 7 - Decoy in a markdown fence (Priority: P1)

[Describe this user journey in plain language]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

### Functional Requirements

- **FR-777**: System MUST [specific capability]
```

Some tooling emits the same shapes in a fence with no info string:

```
### User Story 6 - Decoy in a bare fence (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a bare fence, **When** it is masked, **Then** nothing leaks out of it.

- **FR-666**: This bullet MUST stay masked.
```

...and in a fence tagged with a language:

```text
### User Story 5 - Decoy in a text fence (Priority: P3)

- **FR-555**: This bullet MUST stay masked too.
```

### User Story 1 - Parse what is outside the fences (Priority: P1)

As the factory, I parse only the requirements that live outside fenced blocks, so that
quoted templates never become acceptance criteria.

**Why this priority**: Fence leakage would fabricate criteria the node was never
dispatched against.

**Independent Test**: Parse this file and assert exactly one story and one functional
requirement come back.

**Acceptance Scenarios**:

1. **Given** a spec whose fenced blocks contain story headers and FR bullets, **When** the criteria are parsed, **Then** only the requirements outside the fences are returned.

---

### Edge Cases

- What happens when a fence is opened and never closed? (Out of scope for this fixture.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST mask fenced code blocks before scanning for headers and requirement bullets.
