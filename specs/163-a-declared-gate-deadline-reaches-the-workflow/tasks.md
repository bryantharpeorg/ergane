# Tasks: a declared gate deadline reaches the workflow

## Phase 1: User Story 1 - The declared deadline reaches verification

- [ ] T001 [US1-S1] Write a failing regression carrying a real temporary 900-second manifest through the CLI configuration/dispatch seam and observing the verification activity's 960-second heartbeat option; include the unchanged 600/660 control.
- [ ] T002 [US1-S2] Write a failing roadmap regression through `read_loop_config` and child-input construction, retaining the promotion-persona override and unrelated ladder fields, then observing the same verification scheduling option.
- [ ] T003 [US1-S3] Write the deadline matrix: mixed explicit deadlines, sparse deadlines, all-explicit shorter deadlines, no gates, and both manifest versions.
- [ ] T004 [US1-S4] Prove that later manifest edits do not change a pinned input, old inputs keep their defaults, invalid declarations retain refusal, and existing gate-timeout/termination tests still exercise the executor.
- [ ] T005 [US1-S1] [US1-S2] [US1-S3] Connect the existing manifest deadlines to the existing dispatch configuration in the smallest shared seam, without new settings, serialized fields, or dependencies.
- [ ] T006 [US1-S4] Run focused regression tests and the declared full gate; commit compact actual red/green evidence, identify skipped live paths, and check the complete diff remains below 64 KiB.
