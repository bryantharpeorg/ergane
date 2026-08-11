---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 028-epic-relaunch-reset

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - Relaunching a killed or terminated epic silently resumes the dead run's worktree at the dead run's base pin, because three artifacts outlive the workflow: the worktree directory (survives 'temporal workflow terminate' entirely), the <node>.json base-ref sidecar (survives even a clean kill_epic), and the node branch (survives by explicit design). There is no operator command that clears them. (Priority: P2)

Relaunching a killed or terminated epic silently resumes the dead run's worktree at the dead run's base pin, because three artifacts outlive the workflow: the worktree directory (survives 'temporal workflow terminate' entirely), the <node>.json base-ref sidecar (survives even a clean kill_epic), and the node branch (survives by explicit design). There is no operator command that clears them.

**Acceptance Scenarios**:

1. **Given** the finding `interpreter/relaunched-epic-resumes-the-dead-runs-tree`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `factory/workgraph/worktree.py:200-213`
- `factory/workgraph/worktree.py:216-224`
- `factory/workgraph/worktree.py:507`
- Proved 2026-08-09. 020-landing-attribution died four times at CONFIG_ERROR because its us1 declared 'landing_branch' in factory.yaml, which the worker's parser rejects. The operator fixed the spec, terminated the parked run, reset the target clone to the fixed head, re-derived and restarted -- and it failed a FIFTH time, identically. Cause: 'temporal workflow terminate' runs none of the workflow's cleanup, so ensure() at :202 found the directory present, returned the recorded PreparedWorktree verbatim (base_ref 9d41928, three commits stale) and handed the new agent the dead agent's tree, factory.yaml poison line included. The new agent's own transcript correctly states it did not edit factory.yaml -- it did not need to, the line was already there. Escalating: a clean kill_epic DOES sweep the directory, but :507's sidecar and the node branch both survive, and :216-224 documents the branch survival as intentional ('its salvaged history is the node's record and must stay reachable'), so _branch_exists is true and ensure checks the dead branch back out. A clean relaunch today needs three undocumented hand steps: rm the sidecar, rename or delete the node branch in the target clone, and reset the clone. Candidate fixes, ranked: (1) a 'factory-epic reset <spec-dir>' verb that archives the node branches and clears sidecars, so the operator has a supported path instead of three greps; (2) have derive/start refuse to dispatch a node whose branch already exists at a commit not reachable from the pinned base, naming what to do; (3) make the reuse rule at :202 verify the recorded base_ref is still an ancestor of the target's current landing branch head and rebuild if not; (4) sweep the sidecar in the same place the kill path sweeps the directory, which is the smallest change and fixes only the base-pin half.

## Functional Requirements

- **FR-001**: The factory MUST address `interpreter/relaunched-epic-resumes-the-dead-runs-tree`: Relaunching a killed or terminated epic silently resumes the dead run's worktree at the dead run's base pin, because three artifacts outlive the workflow: the worktree directory (survives 'temporal workflow terminate' entirely), the <node>.json base-ref sidecar (survives even a clean kill_epic), and the node branch (survives by explicit design). There is no operator command that clears them.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
