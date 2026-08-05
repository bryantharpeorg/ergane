# Feature Specification: Short Links

**Feature Branch**: `valid_epic`

**Created**: 2026-08-05

**Status**: Draft

**Input**: Deriver fixture — the accepting case. Three stories in spec order, one
dependency edge, one independent leaf, one per-story `timeout` override, and prose
inside the `## Work Graph` section that the fence-masked scan must read past.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Save a link (Priority: P1)

As a reader, I can save a long URL and get a short code back, so that I can share it
anywhere a long URL will not fit.

**Why this priority**: Nothing else in the feature is reachable until a link exists.

**Independent Test**: Save one URL and assert a stored link carrying a unique short
code.

**Acceptance Scenarios**:

1. **Given** a well-formed URL, **When** a reader saves it, **Then** a link is stored with a short code no other link holds.
2. **Given** a URL the same reader already saved, **When** they save it again, **Then** the existing short code is returned, **And** no second link is stored.

---

### User Story 2 - Follow a short link (Priority: P1)

As anyone holding a short code, I can follow it and land on the original URL.

**Why this priority**: A saved link nobody can follow is not yet a feature. It ties
with US1 and is scheduled after it because it reads what US1 writes.

**Independent Test**: Follow the short code of a stored link and assert the redirect
target.

**Acceptance Scenarios**:

1. **Given** a stored link, **When** its short code is followed, **Then** the caller is redirected to the original URL.
2. **Given** a short code no link holds, **When** it is followed, **Then** the caller is told the code is unknown, **And** no redirect is issued.

---

### User Story 3 - List my links (Priority: P2)

As a reader, I can list the links I have saved, so that I can find a code I have
forgotten.

**Why this priority**: Convenience layered on the two stories above; the feature is
demonstrable without it, and it waits on neither.

**Independent Test**: Save two links, list them, and assert both come back newest
first.

**Acceptance Scenarios**:

1. **Given** a reader with saved links, **When** they list their links, **Then** every link they saved is returned newest first, **And** links saved by other readers are not returned.

---

### Edge Cases

- What happens when a short code is followed while its link is being deleted?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store one link per saved URL, carrying the URL, its short code, the saving reader, and the saved-at timestamp.
- **FR-002**: The system SHALL assign every stored link a short code unique across all links.
- **FR-003**: The system MUST redirect a followed short code to the URL of the link holding it, and MUST refuse a code no link holds.
- **FR-004**: The system MUST list a reader's own links newest first, and MUST NOT include links saved by another reader.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of saved URLs are reachable through their short code.

## Work Graph

Prose in this section is welcome and read past — only the fenced block below declares
the graph.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: [US1]
  implements: [FR-003]
  timeout: 7200        # the redirect path is the slow one; give it two hours
US3:
  depends_on: []
  implements: [FR-004]
```

## Assumptions

- Short codes are opaque; guessability is out of scope for this fixture.
