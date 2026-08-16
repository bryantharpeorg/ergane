---
state: draft
---

# Feature Specification: Well-formed trio

**Input**: The control. Two stories, two functional requirements, one edge, and
a `tasks.md` whose phase headings name the stories by key. Every node of the
graph this compiles assembles a complete prompt, so the `prompt_assembly` layer
must report nothing at all against it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Save a link (Priority: P1)

As a reader, I can save a long URL and get a short code back.

**Acceptance Scenarios**:

1. **Given** a well-formed URL, **When** a reader saves it, **Then** a link is stored with a short code no other link holds.

---

### User Story 2 - Follow a short link (Priority: P2)

As anyone holding a short code, I can follow it and land on the original URL.

**Acceptance Scenarios**:

1. **Given** a stored link, **When** its short code is followed, **Then** the caller is redirected to the original URL.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store one link per saved URL, carrying the URL and its short code.
- **FR-002**: The system MUST redirect a followed short code to the URL of the link holding it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of saved URLs are reachable through their short code.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: [US1]
  implements: [FR-002]
```
