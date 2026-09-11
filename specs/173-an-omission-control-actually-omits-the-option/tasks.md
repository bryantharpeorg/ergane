# Tasks: an omission control actually omits the option

Read the complete trio and every plan trap.  The call expression is part of the
evidence: omission contains no option keyword.  PR 512 remains parked and
untouched; integrate only its authored commits into a new factory branch.

## User Story 1 — Prove true omission

- [ ] T001 [US1] (US1-S4, FR-001, FR-005, FR-007) Integrate authored commits
      `8b80967` through `3eab623` in order, excluding salvage `376ea73`.  Confirm
      the effective three-file payload and preserve the prompt/contract wording.
- [ ] T002 [US1] (US1-S1, US1-S2, FR-002, FR-003) Run the parked completion
      source through a recorder that raises only for `"omitted"`.  Call once as
      `complete("target")` and once with explicit `option=None`; assert the first
      succeeds, the second raises, and the ordered capture is exact.  Record the
      old test's explicit-`None` substitution before changing it.
- [ ] T003 [US1] (US1-S1, US1-S2, FR-002, FR-003) Replace the misleading
      negative control with the two literal call shapes and a value-recording
      callee.  A constant-return lambda or prose-only assertion is insufficient.
- [ ] T004 [US1] (US1-S3, FR-004, FR-005) Execute the repaired completion and
      universal-safety after-sources and compare their generated diffs exactly
      with the production prompt after criteria and sampled gate evidence.
- [ ] T005 [US1] (US1-S5, FR-006, FR-007) Commit compact synthetic red/green
      evidence; run focused judge/parser/gate/contradiction/diff-bound controls,
      check the four-file scope and 64 KiB ceiling, then run the full declared
      gate before normal judge and native merge-queue handling.
