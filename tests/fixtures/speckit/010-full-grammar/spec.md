# Feature Specification: Book Loans

**Feature Branch**: `010-full-grammar`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Fixture exercising every production of the Spec Kit grammar the mechanical
criteria parser keys on (architecture §2): story headers with title and priority,
numbered acceptance scenarios with bold **Given**/**When**/**Then**/**And** steps
(including multi-**And** items and items wrapped across lines), functional requirement
bullets carrying MUST or SHALL, fenced code blocks whose header-like and FR-like lines
must be masked, and bold bullets in other sections that are not requirements.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Borrow a book (Priority: P1)

As a library member, I can borrow an available copy so that I can read it at home.

**Why this priority**: Borrowing is the core transaction; every other story is a
variation on it.

**Independent Test**: Borrow an available copy as a member in good standing and assert
the loan record and its due date.

**Acceptance Scenarios**:

1. **Given** an available copy of a book, **When** a member in good standing borrows it, **Then** a loan is recorded with a 21-day due date.
2. **Given** a member already holding the maximum number of loans, **When** they try to borrow another copy, **Then** the request is refused, **And** the refusal states how many loans they currently hold, **And** the copy stays available.
3. **Given** a copy already on loan, **When** another member requests it, **Then** the
   member is offered a hold, **And** the hold is queued behind any hold already
   standing against that copy.

---

### User Story 2 - Return a book (Priority: P2)

As a library member, I can return a borrowed copy and see my loan closed.

**Why this priority**: Returns close the loop US1 opens, but a loan desk is
demonstrable for a single cycle without them.

**Independent Test**: Return an open loan and assert the loan closes and the copy
becomes available to the next hold.

The return desk hands agents this template excerpt verbatim, so the parser sees a
story header, a scenario list, and an FR bullet that are all inert:

```markdown
### User Story 8 - Decoy story inside a fence (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a fenced decoy, **When** the parser masks fences, **Then** this scenario never exists.

- **FR-900**: This decoy MUST never appear in the parsed requirement set.
```

**Acceptance Scenarios**:

1. **Given** an open loan, **When** the copy is returned before its due date, **Then** the loan is closed, **And** the copy is offered to the next hold in its queue.
2. **Given** an overdue loan, **When** the copy is returned, **Then** the loan is
   closed, **And** a fine is recorded for each day past the due date.

---

### User Story 3 - Renew a loan (Priority: P3)

As a library member, I can renew a loan that nobody else is waiting for.

**Why this priority**: Convenience layered on US1 and US2; the desk works without it.

**Independent Test**: Renew a loan with no holds queued against its copy and assert the
extended due date.

**Acceptance Scenarios**:

1. **Given** an open loan with no holds queued against its copy, **When** the member renews it, **Then** the due date extends by 21 days.

---

### Edge Cases

- What happens when a member's card expires mid-loan?
- How does the system handle a copy reported lost while holds are queued against it?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record one loan per borrowed copy, carrying member, copy, borrowed-at timestamp, and due date.
- **FR-002**: The system SHALL refuse a borrow request from a member already holding the maximum number of loans, and SHALL state the current count in the refusal.
- **FR-003**: The system MUST NOT close a loan that is already closed; a second return of the same copy is a no-op.
- **FR-004**: The system MUST queue holds per copy in request order, and MUST offer a
  returned copy to the first hold in that queue before making it generally
  available.

The bare fence below is inert for the same reason the markdown fence above is:

```
### Functional Requirements

- **FR-901**: This decoy MUST also stay out of the parsed requirement set.
```

### Key Entities *(include if feature involves data)*

- **Loan**: the binding of one copy to one member — member, copy, borrowed-at, due-at, closed-at.
- **Hold**: a member's queued claim on a copy — copy, member, requested-at, queue position.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of borrow requests produce either a loan or an explained refusal.
- **SC-002**: Zero copies are ever on two open loans at once.

## Assumptions

- Membership status is authoritative at the moment of the request.
- Fines are recorded, not collected; collection is out of scope.
