---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 029-salvage-landing-grammar

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - When an agent commits nothing itself, the salvage commit is the PR's only commit, and GitHub's COMMIT_OR_PR_TITLE squash rule uses that single commit's message as the merge subject -- so the merge lands as 'salvage(<epic>/<node>): completed attempt N' instead of the landing grammar. The story is in the tree but invisible to landed_facts, and a delta derivation would re-dispatch work that already landed. (Priority: P2)

When an agent commits nothing itself, the salvage commit is the PR's only commit, and GitHub's COMMIT_OR_PR_TITLE squash rule uses that single commit's message as the merge subject -- so the merge lands as 'salvage(<epic>/<node>): completed attempt N' instead of the landing grammar. The story is in the tree but invisible to landed_facts, and a delta derivation would re-dispatch work that already landed.

**Acceptance Scenarios**:

1. **Given** the finding `targets/salvage-only-pr-lands-invisible`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `factory/workgraph/landed.py:110`
- `factory/workgraph/worktree.py:24`
- Observed 2026-08-09 on 021-roadmap-operability/us4, PR #28. The PR title was correct ('021-roadmap-operability/us4: US4') but the PR held exactly ONE commit -- the salvage commit -- so GitHub used the commit message and the merge landed as 'salvage(021-roadmap-operability/us4): completed attempt 1 (#28)'. The work is fully present (e4e90c3: roadmap/workflow.py +155, notify_activities.py +156, a 374-line test file, docs) and 'factory-epic landed specs/021-roadmap-operability' reports only US1, US2, US3. It CANNOT report US4 and must not: 020-US2's own negative test requires salvage subjects to be refused as landings, because they appear in every branch's history. Contrast PRs #26 (5 commits), #27 (2), #29 (3) -- all used the PR title and all read correctly. So the bug fires exactly when an attempt commits nothing and salvage sweeps everything. Repo setting today: squash_merge_commit_title=COMMIT_OR_PR_TITLE. Fix, one call: gh api -X PATCH repos/bryantharpeorg/ergane -f squash_merge_commit_title=PR_TITLE. Deterministic, repo-wide, and it makes the merge subject depend on the thing the factory controls (the PR title it writes) rather than on how many commits an agent happened to make. Until then any delta derivation over 021 will re-emit US4 at full price -- which is the exact failure 016 and 020 were built to prevent.

## Functional Requirements

- **FR-001**: The factory MUST address `targets/salvage-only-pr-lands-invisible`: When an agent commits nothing itself, the salvage commit is the PR's only commit, and GitHub's COMMIT_OR_PR_TITLE squash rule uses that single commit's message as the merge subject -- so the merge lands as 'salvage(<epic>/<node>): completed attempt N' instead of the landing grammar. The story is in the tree but invisible to landed_facts, and a delta derivation would re-dispatch work that already landed.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
