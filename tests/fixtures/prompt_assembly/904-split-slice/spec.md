---
state: draft
---

# Feature Specification: The agent sandbox (reconstructed)

**Input**: The 2026-08-15 near-miss, reconstructed as a fixture. This spec is
sound and so is the graph it compiles to. The defect lives in `tasks.md`, whose
Tests and Implementation groups are both written at phase level, so each story's
slice stops at its own implementation heading and every implementation task
falls outside the slice of the story that names it.

Nothing refuses this trio. Every node assembles a complete prompt, and the
prompt each node is handed is silently missing half its work — which is the
whole reason the slice-coverage lint exists rather than assembly alone.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Writes outside the worktree are detected (Priority: P1)

As the operator, I want an attempt that writes outside its own worktree to be
detected, so that the isolation the factory claims is a fact rather than a
convention.

**Acceptance Scenarios**:

1. **Given** an attempt that edits a file outside its worktree, **When** the attempt ends, **Then** the escape is detected and recorded.

---

### User Story 2 - The agent runs inside a boundary (Priority: P1)

As the operator, I want the agent launched inside a containment boundary, so
that a write outside the worktree is refused rather than merely noticed.

**Acceptance Scenarios**:

1. **Given** an agent that writes an absolute path outside its worktree, **When** the write is attempted, **Then** the boundary refuses it.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect a write made outside an attempt's own worktree and record it.
- **FR-002**: The system MUST launch the agent inside a boundary that refuses a write outside the worktree.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of attempts that write outside their worktree are detected.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: [US1]
  implements: [FR-002]
```
