# Tasks: Codex keeps its seeded home across the worktree boundary

## Phase 1: User Story 1 - The seeded home survives the launch boundary

- [ ] T001 [US1-S1] Add the strict-child regression through `CodexAdapter.run_attempt` with a production-shaped relative home and a distinct worktree; run it red and capture the missing-home/config failure before the fix.
- [ ] T002 [US1-S2] Cover production bubblewrap launch construction and actual strict-child execution where supported, preserving existing confinement and declaring unavailable execution as an explicit skip.
- [ ] T003 [US1-S3] Add relative/absolute and two-node controls that observe each child's seeded configuration, successful turn classification and archived synthetic rollout without ambient filesystem assertions.
- [ ] T004 [US1-S4] Add synthetic gateway/subscription relative-home isolation coverage and retain the existing absolute-home tests; assert key placement and route-specific files without touching real operator credentials.
- [ ] T005 [US1-S1] [US1-S2] [US1-S3] [US1-S4] Repair child-facing Codex home identity at the existing activity-side adapter seam, keeping seed location and all consumers consistent without workflow, root-policy, auth-routing or sandbox changes.
- [ ] T006 [US1-S1] [US1-S2] [US1-S3] [US1-S4] Run focused and full gates, commit compact actual red/green evidence and skip disclosures, and verify the complete story diff fits below 64 KiB.
