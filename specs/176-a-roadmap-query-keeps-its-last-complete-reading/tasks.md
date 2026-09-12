# Tasks: a roadmap query keeps its last complete reading

## Phase 1: User Story 1 — truthful status across continue-as-new

- [ ] T001 [US1] Add a deterministic regression that blocks only the continued
  run's first `read_corpus_activity`, queries during the block, and expects both
  prior spec rows plus current controls and no running child.  Covers US1-S1,
  US1-S2 and FR-008.
- [ ] T002 [US1] Add a defaulted, typed carry-over field for the last complete
  query snapshot and cover decoding of a historical payload that omits it.
  Covers US1-S6 and FR-001, FR-002, FR-006.
- [ ] T003 [US1] Capture the complete quiescent status immediately before
  continue-as-new and restore it before the new run's first await without
  assigning it to any scheduling input.  Covers FR-001, FR-002 and FR-004.
- [ ] T004 [US1] Make `roadmap_status` use the carried snapshot only while the
  fresh corpus is unavailable, overlaying current pause, bounds, promotions and
  parked state.  Covers US1-S1 through US1-S3 and FR-003, FR-007.
- [ ] T005 [US1] Prove the first completed fresh read replaces the snapshot and
  that a corpus edit between runs controls subsequent readiness and dispatch.
  Covers US1-S4 and FR-004, FR-005.
- [ ] T006 [US1] Preserve the fresh-first-run behavior and assert that no spec
  row is fabricated when there is no prior complete snapshot.  Covers US1-S5.
- [ ] T007 [US1] Run the unchanged pause/operator test repeatedly, then the
  roadmap scheduler, durability, operator-surface, query and Temporal payload
  suites.  Do not increase timeouts, add sleeps or weaken assertions.  Covers
  FR-008 and FR-009.
- [ ] T008 [US1] Inspect the final diff for scheduling, service, agent, Ollama,
  route, credential, timeout, registry and release side effects; none are in
  scope.  Covers US1-S7 and FR-010.
