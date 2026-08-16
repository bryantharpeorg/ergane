---
state: draft
---

# Feature Specification: Peer channel (reconstructed)

**Input**: The worse half of the 2026-08-15 corpus sweep, reconstructed as a
fixture. A story was inserted at position two after `tasks.md` was written, so
every phase below the first carries the number of the story that used to sit
there. Three of the four nodes still assemble a prompt — and each is handed the
*next* story's task list, silently. Only the last story, which no heading names
at all, produces a refusal.

The table the sweep produced, reconstructed here exactly:

| node | phase it finds | whose tasks those are |
| --- | --- | --- |
| us1 | Phase 2 | US1 |
| us2 | Phase 3 | US3 |
| us3 | Phase 4 | US4 |
| us4 | none | — |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A question reaches a peer agent in the same epic (Priority: P1)

As a node, I can address a question to a sibling node of my own epic and read
its answer before I stop.

**Acceptance Scenarios**:

1. **Given** two nodes of one epic, **When** the first addresses the second, **Then** the answer reaches the first before it stops.

---

### User Story 2 - A message reaches an attempt that is already running (Priority: P1)

As a node whose sibling is mid-attempt, I can reach it without waiting for it to
finish, so a question does not cost a fresh dispatch.

**Acceptance Scenarios**:

1. **Given** a sibling attempt already running, **When** a message is addressed to it, **Then** the running attempt reads it without being re-dispatched.

---

### User Story 3 - A message reaches a named external agent (Priority: P2)

As a node, I can address an agent the operator's registry names, and its reply
reaches me the same way a sibling's does.

**Acceptance Scenarios**:

1. **Given** a registry-named external peer, **When** a message is addressed to it, **Then** the reply reaches the sender.

---

### User Story 4 - A message crosses epics (Priority: P3)

As a node, I can address a node of another epic, so one addressee namespace
spans the whole floor.

**Acceptance Scenarios**:

1. **Given** two live epics, **When** a node of one addresses a node of the other, **Then** the message is delivered.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A node MUST be able to address a sibling node of its own epic and receive the reply before it stops.
- **FR-002**: A message addressed to an attempt already running MUST reach that attempt without re-dispatching it.
- **FR-003**: A message addressed to a registry-named external peer MUST be delivered and its reply returned to the sender.
- **FR-004**: A message addressed to a node of another epic MUST be delivered across the epic boundary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of addressed messages are delivered or degrade to the operator path.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: [US1]
  implements: [FR-002]
US3:
  depends_on: [US1]
  implements: [FR-003]
US4:
  depends_on: [US3]
  implements: [FR-004]
```
