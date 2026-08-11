---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Auto-scaffolded by ergane findings promote; review before flipping to ready.
---

# Feature Specification: 026-manifest-self-extension

This spec was scaffolded from accepted findings in the ergane findings ledger. Each user story below carries the original finding's evidence verbatim; the operator or an architect session refines the prose before flipping `state` to `ready`.

### User Story 1 - The config gate parses the node's factory.yaml with the WORKER's installed parser, not the worktree's, so any story that adds a factory.yaml key fails CONFIG_ERROR on every attempt no matter how correct its code is (Priority: P2)

The config gate parses the node's factory.yaml with the WORKER's installed parser, not the worktree's, so any story that adds a factory.yaml key fails CONFIG_ERROR on every attempt no matter how correct its code is

**Acceptance Scenarios**:

1. **Given** the finding `interpreter/manifest-schema-cannot-be-extended-by-a-story`, **When** the work scoped here is implemented, **Then** the ledger records a resolution tied to this spec.

**Why this priority**: Promoted from the doctor ledger; the recurrence count motivates building the fix.

**Independent Test**: Verify the fix closes the finding and the scaffold compiles with zero rejections.

**Evidence**:
- `factory/verify/gates.py:47`
- `factory/verify/factory_yaml.py:138`
- `factory/verify/gates.py:406`
- Observed 2026-08-09 on epic-020-landing-attribution/us1, whose FR-001 requires factory.yaml to accept a new optional top-level key 'landing_branch'.

MECHANISM. run_gates imports parse_factory_config at module scope (gates.py:47) and calls it in-process before running any gate command. That process is the WORKER, which imports factory/ from the worker's own checkout. The node's worktree is where the candidate parser lives, and it is never consulted. So the manifest is validated by the very code the story is trying to change.

The node did everything right. Its worktree contains both halves of the change: 'landing_branch' added to the known-keys tuple (factory_yaml.py:67) with a _read_landing_branch reader (:300), AND the key declared in factory.yaml (:34). The worker's older parser sees an unknown top-level key, returns a single CONFIG_ERROR GateResult, and per gates.py:406 runs NOTHING else. Every attempt fails identically at 0.0s before a single test executes. Attempts 1 through 4 all produced the same result.

CONSEQUENCE, STATED GENERALLY. The factory cannot extend its own manifest schema in one story. Any FR of the form 'factory.yaml MUST accept <new key>' is unsatisfiable if the story also declares that key in the repository's own factory.yaml, because the gate that judges it is running last-landed code. This is a bootstrap deadlock, not a bug in the story.

WHY IT IS NOT THE SAME AS THE CI FINDING. interpreter/ci-failure-never-reaches-an-agent is about a red check after the gate passes. This one fires before any gate command runs at all, and no retry can clear it -- an escalation RETRY is guaranteed to reproduce it, which makes the operator's most natural button the wrong one.

WORKAROUND AVAILABLE TODAY. Split the concern: a story may teach the parser to ACCEPT an optional key, proven with fixtures, but must not declare that key in the repository's own factory.yaml. The live manifest gains the key only after the parser has landed and the worker has been restarted on it. 020's FR-001 is worded 'factory.yaml MUST accept an optional top-level landing_branch', which reads as an invitation to edit the live manifest, and the plan carries no trap warning against it.

CANDIDATE FIXES. (1) Parse the manifest with the worktree's own factory package so a story is judged by its candidate code -- matches how the gate COMMANDS already run, via uv run inside the worktree. (2) Treat an unknown top-level key as a warning rather than CONFIG_ERROR when the worktree's parser accepts it. (3) Failing both, make the deadlock explicit: a constitution rule that schema-extending stories never declare the new key in the repo's own manifest, so the trap is binding rather than remembered.

## Functional Requirements

- **FR-001**: The factory MUST address `interpreter/manifest-schema-cannot-be-extended-by-a-story`: The config gate parses the node's factory.yaml with the WORKER's installed parser, not the worktree's, so any story that adds a factory.yaml key fails CONFIG_ERROR on every attempt no matter how correct its code is.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
