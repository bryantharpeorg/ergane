---
state: landed
# Attested landed 2026-09-11. US1 0dcb761ca6d3 (#508) on attempt 2 — observed
# on ergane-buildout by content.
fixes:
  - findings-ingest/default-analysis-rehearsal-path-crashes
  - findings-ingest/historical-observation-identity-bypasses-sanitization
---

# Feature Specification: the historical ingest default is a real path

## Why this repair exists

The agent-authored 158/US4 candidate correctly added historical observation
identity, time, schema migration and idempotent application, but independent
qualification found two release blockers before PR504 landed. Analysis-only
ingestion without `--rehearsal-db` passes the integer file descriptor returned
by `tempfile.mkstemp` to `Path` and crashes. Its sanitization wrapper also copies
`observation_id` unchanged, so credential-shaped input survives in the
rehearsal database.

The original PR remains parked. This spec integrates that agent-authored work
from its preserved commit range and repairs the two proven defects through the
normal agent, gate, judge and native merge-queue path.

## User Stories *(mandatory)*

### User Story 1 - Historical ingestion is safe on every public analysis path (Priority: P1)

As an operator rehearsing an old report, I can omit optional output arguments
and still receive a usable sanitized database without touching the operational
ledger or leaking a file descriptor.

**Independent Test**: Invoke the production `findings ingest` command with a
temporary historical batch and no `--apply`, `--db`, or `--rehearsal-db`.
Capture its printed path, inspect the stored event, compare the operational
database before and after, and exercise credential-shaped values in both normal
finding text and `observation_id`.

**Acceptance Scenarios**:

1. **Given** a historical finding with a stable observation id and observation
   time, **When** it is parsed, rehearsed, applied and read back, **Then** those
   values remain distinct from ingestion time, duplicate application creates no
   recurrence, and a historical claim never changes a current finding row.
2. **Given** analysis-only ingestion with no `--rehearsal-db`, **When** the
   public command completes, **Then** it returns success, prints one existing
   readable rehearsal-database path, closes the temporary descriptor, and
   leaves the operational ledger byte-for-byte unchanged.
3. **Given** credential-shaped text in a persisted historical observation id,
   source, summary, reference or note, **When** analysis-only rehearsal writes
   its event, **Then** no original credential-shaped value appears in the
   database, stdout, stderr or exception text, while the sanitized observation
   identity stays stable for duplicate ingestion and distinct for distinct
   source observations.
4. **Given** an explicit existing rehearsal path, **When** analysis-only
   ingestion is requested, **Then** the command still refuses to overwrite it;
   explicit `--apply --db` remains the only route to the operational store.
5. **Given** a version-1 doctor database and the historical candidate's schema
   extension, **When** the database is opened and the same observation is
   applied twice, **Then** migration is idempotent, the observation-id uniqueness
   rule is present, and the finding row and event trail record one historical
   observation without manufacturing `last_seen` or occurrence changes.

## Functional Requirements *(mandatory)*

- **FR-001**: The complete 158/US4 historical-event behavior MUST be integrated
  from the preserved agent candidate; the salvage-only commit MUST NOT be used
  as an implementation shortcut or attributed as new authored work.
- **FR-002**: Analysis-only ingestion without an explicit rehearsal path MUST
  close the `mkstemp` descriptor and operate on the returned pathname.
- **FR-003**: Every externally controlled text field persisted by the historical
  rehearsal, including `observation_id`, MUST follow an explicit credential
  sanitization or refusal policy with no raw value in output or errors.
- **FR-004**: Sanitized observation identity MUST remain deterministic for
  duplicate detection and MUST NOT collapse two distinct source observations.
- **FR-005**: Analysis-only ingestion MUST NOT open the operational store for
  writing; application MUST still require `--apply` and an explicit target.
- **FR-006**: Historical application MUST preserve observation time,
  idempotency, current-row independence and the schema contract already proven
  by the 158/US4 candidate.
- **FR-007**: Tests MUST drive both the omitted-option public path and the
  explicit rehearsal path. Parser-default assertions alone do not satisfy the
  command-completion scenario.
- **FR-008**: The change MUST add no dependency, network call, live-ledger
  mutation, new authorization shortcut or change to current `findings report`
  recurrence semantics.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008]
```

## Assumptions

- PR504 and branch
  `factory/158-operator-skills-report-and-act-by-declared-intent/us4` remain
  unmerged evidence. Their candidate code is reusable because a factory agent,
  rather than the operator, authored it.
- This repair does not authorize applying any historical batch to the live
  doctor ledger.
