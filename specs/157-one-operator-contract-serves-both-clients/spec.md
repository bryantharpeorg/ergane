---
state: ready
---

# Feature Specification: one operator contract serves both clients

## Provenance and current scope

This spec is work package A from the 2026-09-09 Codex-primary audit. It corrects
the present split in which Ergane has a repository `CLAUDE.md` but no repository
`AGENTS.md`, while retaining the guard that a dispatched factory node follows its
assembled brief and the standards path named by `ergane.yaml`. It creates no
second standards channel and no second work queue.

The operator clarified on 2026-09-09 that the immediate builder path is Codex
CLI through the existing gateway to Ollama Cloud, alongside a Codex operator
session. Subscription governance is deferred to
`docs/codex-primary-governance-proposal-2026-09-09.md`; the former draft US3 and
its three governance requirements are removed and their identifiers are not reused.
This spec was promoted for implementation on 2026-09-09. Completion requires
the fresh-client discovery evidence below; no subscription login, private pilot,
or constitutional amendment is a prerequisite for this operator migration.

### User Story 1 - One canonical orientation has two verified entry points (Priority: P1)

As an operator using either supported client, I receive the same repository
orientation without maintaining two copied policies.

**Acceptance Scenarios**:

1. **Given** the repository root, **When** the canonical orientation is inspected, **Then** `AGENTS.md` contains the existing implementer guard, document-authority map, live-state commands, active-factory restriction, and the distinction between observation and authorized action, while `CLAUDE.md` is a compatibility entry point to those exact bytes — proven by committed tests over the tracked file type and resolved content.
2. **Given** a root, nested-directory, and worktree session for each supported client, **When** its effective instruction chain is recorded, **Then** all six observations name the same canonical repository instructions exactly once and give a dispatched node's assembled prompt and declared standards precedence — proven by a committed, redacted qualification artifact plus a parser test.
3. **Given** an operator asks only for status or diagnosis, **When** the orientation is followed, **Then** it authorizes no fetch, merge, dispatch, attestation, escalation answer, findings write, service change, commit, or push — proven by focused semantic tests over the instruction text.

**Why this priority**: Every later operator skill and runbook depends on an unambiguous instruction source.

**Independent Test**: Install neither skills nor services; resolve both entry points and assert the required sections and the six-client-context evidence.

### User Story 2 - The operator workflow names Ergane's authorities and degraded capabilities (Priority: P1)

As an operator, I can move from a finding through refinement and later dispatch
without a generic issue tracker, a vendor-specific tool name, or an unavailable
memory connection being presented as fact.

**Acceptance Scenarios**:

1. **Given** the shared workflow guide, **When** an operator follows it, **Then** it orders source verification, optional memory recall, finding-to-spec ownership, whole-trio refinement, validation, readiness, dispatch, landing, and attestation while stating which steps require explicit authority — proven by committed document-contract tests.
2. **Given** memory, scheduling, notification, delegation, or publication is unavailable in one client, **When** the capability guide is consulted, **Then** the job reports that capability unavailable and offers the narrow supported fallback without inventing a universal API name — proven by a table-driven test covering each capability row.
3. **Given** an ancestor instruction proposes Beads, GitHub issues, mandatory pushes, or checkout cleanup, **When** work is performed in Ergane, **Then** the repository guide identifies Spec Kit trios, the findings ledger, and immutable decisions as the governing local authorities and forbids a competing queue — proven by a committed semantic test.

**Why this priority**: Shared filenames are insufficient if the workflow behind them still forks by client.

**Independent Test**: Parse only `docs/agents/workflow.md` and `docs/agents/capabilities.md`; every lifecycle phase, authority boundary, and unavailable-capability fallback must be explicit.

## Functional Requirements

- **FR-001**: `AGENTS.md` MUST be the one canonical repository orientation and MUST begin with the dispatched-node guard.
- **FR-002**: `CLAUDE.md` MUST be a tested compatibility entry point to the canonical orientation, not a copied policy.
- **FR-003**: The orientation MUST preserve the normative role of `.specify/memory/constitution.md`, the descriptive role of `docs/architecture.md`, the immutable role of `docs/decisions.md`, and the vocabulary role of `CONTEXT.md`.
- **FR-004**: The orientation MUST name `ergane.yaml` as the active manifest and MUST treat legacy `factory.yaml` only as compatibility context where code still accepts it.
- **FR-005**: Observation requests MUST NOT authorize mutation, and every merge, dispatch, attestation, answer, findings application, service change, commit, push, or publication MUST require its own declared intent.
- **FR-006**: `docs/agents/workflow.md` MUST define one client-neutral findings-to-refinement-to-build workflow without adding an issue tracker or scheduler.
- **FR-007**: `docs/agents/capabilities.md` MUST separate shared intent from client bindings and MUST represent an absent binding explicitly.
- **FR-008**: Memory unavailability MUST be reported; neither nodes nor unattended runs may gain memory-write authority from this spec.
- **FR-009**: Instruction tests MUST exercise root, nested-directory, and worktree discovery on both clients using redacted committed evidence rather than filename assumptions.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-009]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008]
```
