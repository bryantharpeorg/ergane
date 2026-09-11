# Tasks: counterexample fixtures prove the defect they name

Read the complete trio and all plan traps.  Keep one executable source for each
fixture and derive the prompt diff from that same source.  The tests must fail on
the integrated PR 509 fixtures for the reproduced behavioral reasons before any
repair.  PR 509 stays parked and untouched.

## User Story 1 — Counterexample evidence survives a negative control

- [ ] T001 [US1] (US1-S1, FR-001, FR-002, FR-004) Integrate authored commits
      `a154f1b` through `192fd78` in order, excluding salvage `3e9e2ea`.  Add
      focused controls that execute both existing fixture bodies.  Capture the
      specific red: omission sees `"explicit"` without a crash, and both
      persisted fields equal the sanitized value.
- [ ] T002 [US1] (US1-S2, FR-003) Replace the completion fixture with a unified
      diff generated from executable before/after source.  Assert an explicit
      call completes, an omitted call raises the visible exception, and the
      generated diff contains that exact branch.
- [ ] T003 [US1] (US1-S3, FR-005) Replace the universal-safety fixture with a
      unified diff generated from executable source that sanitizes one field but
      persists a distinct raw caller-controlled sibling.  Assert the captured
      persisted values prove the bypass.
- [ ] T004 [US1] (US1-S4, FR-006, FR-007) Assemble the production judge prompt
      with the exact generated diffs, scenarios and sampled green gate.  Assert
      section order and retain the PR 509 default-path, universal-claim,
      advisory-boundary and 64 KiB contract wording.
- [ ] T005 [US1] (US1-S5, FR-008, FR-009) Run focused judge prompt, verdict
      parser, gate contradiction, diff-bound and contract controls.  Confirm no
      dependency, parser, schema, retry, registry, routing, credential, doctor or
      live-model change; record compact red/green evidence and run the full
      declared gate before normal judge and native merge-queue handling.
