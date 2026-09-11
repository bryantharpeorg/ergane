# Tasks: a judge cannot waive a concrete counterexample

## Phase 1: User Story 1 — A concrete scenario counterexample is blocking

- [ ] T001 [US1] Add a realistic prompt fixture with an unqualified public CLI
      completion scenario, a green deterministic gate, an explicit-option test
      and a visibly crashing omitted-option branch. Covers US1-S1.
- [ ] T002 [US1] Tighten the fixed system prompt so tests are sampled evidence,
      an unqualified public scenario includes reachable defaults, and a concrete
      contradiction must fail the closest scenario instead of appearing only in
      PASS feedback. Covers FR-001, FR-002 and FR-003.
- [ ] T003 [US1] Add the branch-and-field rule for universal safety language,
      with a synthetic persisted sibling field that bypasses a nested sanitizer.
      Covers US1-S2 and FR-004.
- [ ] T004 [US1] Preserve the criteria boundary for unrelated defects and add a
      focused advisory control. Do not add holistic review authority or prose
      keyword parsing. Covers US1-S3 and FR-005.
- [ ] T005 [US1] Update `specs/002-verification-gating/contracts/judge.md` to
      match the shipped fixed template; keep wording vendor-neutral and free of
      incident-specific paths or aliases. Covers FR-007.
- [ ] T006 [US1] Run focused prompt assembly, verdict parser, gate contradiction,
      diff-bound and contract tests. Confirm no parser, JSON schema, registry,
      routing or retry behavior changed, then run the full declared gate. Covers
      US1-S4 and FR-006.
