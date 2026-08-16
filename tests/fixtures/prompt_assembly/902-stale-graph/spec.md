---
state: draft
---

# Feature Specification: Stale compiled graph

**Input**: The spec.md half of assembly. This spec once declared two stories; the
second was cut. The compiled `workgraph.json` beside it was never re-derived, so
the artifact still carries a `us2` node — and that artifact is what
`ergane build start` loads and dispatches, not this file.

A node whose story the specification no longer declares cannot be told what to
implement, and the assembler refuses it naming `spec.md`. This file itself is
sound: its frontmatter parses, its `## Work Graph` compiles, and its one story
has a task slice.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Save a link (Priority: P1)

As a reader, I can save a long URL and get a short code back.

**Acceptance Scenarios**:

1. **Given** a well-formed URL, **When** a reader saves it, **Then** a link is stored with a short code no other link holds.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store one link per saved URL, carrying the URL and its short code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of saved URLs are reachable through their short code.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
