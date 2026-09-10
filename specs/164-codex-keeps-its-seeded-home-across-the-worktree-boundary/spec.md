---
state: ready
---

# Feature Specification: Codex keeps its seeded home across the worktree boundary

## Incident and scope

The first four Codex/Ollama launches for 131 and 147 failed before inference:
`CODEX_HOME points to ".ergane/homes/<epic>/<node>/.codex", but that path does not exist`.
The directory DID exist beneath the worker's frozen checkout. The workflow
passed a relative per-node home, the activity seeded it there, and the child
changed directory into the node worktree while retaining relative CODEX_HOME.
Tests and the earlier live smoke used absolute homes and missed this boundary.

A credential-free differential probe reproduced the refusal using installed
Codex `login status` on both host and bubblewrap. Changing only CODEX_HOME to
the absolute location already seeded made both reach `Not logged in`, without
an inference request, credential copy, new mount, or sandbox relaxation.

This is one focused adapter repair, not a runtime-root migration. Preserve the
existing declared per-node home and its seed location; make its identity survive
the child cwd change. Do not add filesystem reads or resolution to workflows,
alter pinned workflow payloads, change provider/auth routes, or edit launchers.
The operator-approved temporary Claude/Ollama lane builds this repair only;
restoring Codex and restarting 131/147 are operator deployment work, not this
story's implementation scope.

### User Story 1 - A Codex child reads the same home the activity seeded (Priority: P1)

As an operator, a Codex attempt launched from a workflow-produced relative
per-node home starts with its seeded configuration available, even though its
working directory is the node worktree.

**Acceptance Scenarios**:

1. **Given** a relative home generated with the production home-path helper and a different absolute node worktree, **When** the production Codex adapter runs a strict child through the host backend, **Then** the child receives an absolute CODEX_HOME naming the already-seeded directory, reads its generated gateway configuration without creating that directory, and completes; committed tests and compact actual red/green output show this scenario fails on the original implementation and passes after the repair.
2. **Given** that same relative-home attempt and the bubblewrap backend, **When** the production sandbox launch is constructed and, where available, executed with a credential-free strict child, **Then** CODEX_HOME names the same seeded location, the worktree remains the child cwd, and the existing per-node home bind and environment allowlist suffice without broader mounts; committed tests cover launch construction on all hosts and actual execution on supported hosts, with unavailable execution explicitly skipped and reported.
3. **Given** relative and already-absolute homes for two separate nodes, **When** their successful strict children emit distinct synthetic rollout files, **Then** production turn detection and transcript archiving find each node's own rollout, both homes remain distinct, and the already-absolute case retains its location; committed behavioral tests observe the child, classification and archived files rather than merely comparing helper strings.
4. **Given** gateway and subscription contexts, **When** the repaired adapter prepares their respective homes, **Then** gateway credentials still travel only through the constructed key environment and generated provider configuration names that variable without its value, while subscription credentials still use the existing isolated per-node copy without gateway credentials or provider configuration; committed tests using synthetic credentials prove these properties for relative homes and preserve the existing absolute-home contract.

**Independent Test**: Use an isolated temporary worker directory, the real
`home_path` helper with the existing relative runtime root, a distinct node
worktree, and the real `CodexAdapter.run_attempt` policy. A strict disposable
child refuses a missing CODEX_HOME/config rather than manufacturing one, reads
the seeded config, writes a synthetic rollout, and exits. No live credentials,
gateway service, model, or installed Codex is required for the regression suite.

## Functional Requirements

- **FR-001**: Codex's child-facing home MUST be absolute and identify the existing declared per-node seed location before launch changes cwd.
- **FR-002**: Host and bubblewrap launches MUST preserve that identity without widening confinement or inheriting operator credentials.
- **FR-003**: Seeding, child execution, turn detection and archiving MUST agree on the same node-local Codex home for relative and absolute inputs.
- **FR-004**: Gateway and subscription isolation MUST retain their existing route-specific behavior; no authentication, model, workflow-payload or runtime-root policy change is included.
- **FR-005**: Regression tests MUST exercise the production adapter's relative-home boundary with a strict child and meaningful absolute and node-isolation controls.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
```
