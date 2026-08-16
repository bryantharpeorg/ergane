---
state: draft
---

# Feature Specification: Orphan tasks and a quoted example

**Input**: The two things the lint must *not* refuse. Its `tasks.md` is sound —
every phase names its story by key and every tagged task sits in the slice its
tag names — but it carries two shapes that a miscalibrated lint would fail it
for.

The first is a `## Verification` phase carrying task ids and no story key. Those
ids reach no agent, deliberately: they are the operator's own closing pass. They
are worth *stating* and are not a defect, so they are information and the exit
code is unchanged by them.

The second is a task line quoted inside a fenced block. The tasks template
quotes its own grammar, so a lint that scans lines without the assembler's
fence masking would read an example as a task — and this one is deliberately
written to look like the worst kind: a task tagged for one story sitting inside
another story's slice. Masked, it is text about a task. Unmasked, it is a
finding that names a task nobody wrote.

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
