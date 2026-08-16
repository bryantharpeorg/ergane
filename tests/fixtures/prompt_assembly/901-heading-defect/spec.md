---
state: draft
---

# Feature Specification: Runtime root integrity (reconstructed)

**Input**: The 2026-08-15 incident, reconstructed as a fixture. The roadmap
dispatched an epic with four stories and one tick later every node was dead,
killed before any agent ran, each with the same refusal:

```
node 'us1': tasks.md declares no phase naming user story US1, so this node has
no task slice to work (FR-006)
```

Nothing is wrong with this file. The defect lives in `tasks.md`, whose phase
headings name each story's title and never the story key the assembler looks
for — which is why every existing validate layer passes this trio.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The leak detector stops requiring the live store's absence (Priority: P1)

As the operator, I want the leak detector to pass on a host that has a live
store, so that satisfying it never means deleting production data.

**Acceptance Scenarios**:

1. **Given** a host carrying a live store, **When** the leak detector runs, **Then** it passes, **And** the live store is still on disk.

---

### User Story 2 - The findings ledger is addressed through the resolver (Priority: P1)

As the operator, I want every reader of the findings ledger to resolve its path
the same way, so that two components cannot disagree about where it lives.

**Acceptance Scenarios**:

1. **Given** a relocated runtime root, **When** the ledger is read, **Then** it is read from the relocated root.

---

### User Story 3 - The runtime root can be migrated (Priority: P2)

As the operator, I want a command that moves an existing runtime root, so that
renaming it is not a hand-run sequence of moves.

**Acceptance Scenarios**:

1. **Given** an existing runtime root, **When** the migration runs, **Then** every store is present under the new root.

---

### User Story 4 - The migration refusal names the variable the operator set (Priority: P3)

As the operator, I want a refused migration to name the environment variable
that caused it, so that the fix is one edit rather than a search.

**Acceptance Scenarios**:

1. **Given** an overriding environment variable, **When** the migration refuses, **Then** the refusal names that variable.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The leak detector MUST pass on a host carrying a live store, and MUST NOT require its absence.
- **FR-002**: Every reader of the findings ledger MUST resolve its path through the runtime-root resolver.
- **FR-003**: The system MUST provide a command that migrates an existing runtime root to a new location.
- **FR-004**: A refused migration MUST name the environment variable that caused the refusal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The leak detector passes on a host with a live store.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: []
  implements: [FR-002]
US3:
  depends_on: [US2]
  implements: [FR-003]
US4:
  depends_on: [US3]
  implements: [FR-004]
```
