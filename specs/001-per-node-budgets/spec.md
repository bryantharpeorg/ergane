# Feature Specification: Per-Node Budgets

**Feature Branch**: `001-per-node-budgets`

**Created**: 2026-07-24

**Status**: Draft

**Input**: Component 1 of the Ergane factory (D-013, D-014, D-015, D-016, D-017): LiteLLM
virtual-key issuance/teardown as Temporal activity middleware around every LLM-consuming
WorkGraph node, breach policy (soft-warn / hard-kill / escalate), and an append-only
spend ledger.

## Clarifications

### Session 2026-07-24

- Q: Ledger storage medium given concurrent teardown writers? → A: SQLite database file (stdlib `sqlite3`, no new dependency); JSONL export as a convenience.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Key lifecycle around a node (Priority: P1)

As the WorkGraph interpreter, when I dispatch an LLM-consuming node, a dedicated virtual
key is minted with the node's budget, handed to the agent as its only credential, and
revoked when the node reaches any terminal state — so a runaway node can never spend
beyond its cap and spend is always attributable to exactly one node.

**Why this priority**: This is the enforcement core; nothing else in the component means
anything without the key lifecycle. It is independently valuable even with no breach
policy (LiteLLM's own hard block still applies).

**Independent Test**: Issue a key against a (fake or real) LiteLLM proxy, observe the
key exists with correct `max_budget`/alias/metadata/models, tear down, observe the key
is gone and a ledger row exists.

**Acceptance Scenarios**:

1. **Given** a node `n1` in epic `e1` with persona `implementer` (budget $5), **When**
   the node is dispatched, **Then** a virtual key is created with `max_budget` 5.0, alias
   `e1:n1`, metadata `{node_id, epic_id, persona}`, the persona's allowed model list, and
   a TTL backstop.
2. **Given** a node with a per-node budget override in the graph, **When** dispatched,
   **Then** the override — not the persona default — is applied to the key.
3. **Given** a node that reaches any terminal state (completed, failed, breached,
   killed, timed out), **When** teardown runs, **Then** the key is revoked and exactly
   one ledger row is written with final spend and termination class.
4. **Given** a key that was already deleted (TTL expiry, prior teardown), **When**
   teardown runs again, **Then** teardown still succeeds (idempotent) and a ledger row
   is still written.
5. **Given** the proxy is unreachable when final spend is read, **When** teardown runs,
   **Then** the key revocation is still attempted and the ledger row records spend as
   unknown/zero rather than the teardown failing.

---

### User Story 2 - Breach detection and policy (Priority: P2)

As the factory operator, when a node hits its budget, the system tells me exactly what
happened (breach, not a generic agent error), never loses the partial work, and applies
the persona's policy: cheap personas just fail; expensive personas escalate to me with
actionable choices.

**Why this priority**: Turns the raw hard-block into operational behavior. Depends on
US1's lifecycle.

**Independent Test**: Simulate an agent process ending with a LiteLLM budget-400 in its
output; assert classification, salvage, and the per-persona action without any real
proxy.

**Acceptance Scenarios**:

1. **Given** a running node whose spend crosses 80% of budget, **When** the next spend
   poll observes it, **Then** exactly one soft warning is emitted for that node (never
   repeated) and the node continues.
2. **Given** an agent process that exits non-zero with a budget-exceeded marker in its
   output (e.g. `ExceededTokenBudget`), **When** the wrapper classifies the termination,
   **Then** the class is BUDGET_BREACH — distinct from AGENT_ERROR.
3. **Given** an agent that exits cleanly (code 0) even though spend grazed the cap,
   **When** classified, **Then** the class is COMPLETED (the work exists).
4. **Given** any breach, **When** the process is stopped (graceful signal, then force
   after a grace period), **Then** the worktree contents are committed to the node's
   branch before cleanup (salvage-always).
5. **Given** a breached node whose persona policy is `hard-kill` (verifier, judge,
   researcher), **When** policy is applied, **Then** the node fails, downstream edges
   stay locked, and a notification is sent.
6. **Given** a breached node whose persona policy is `escalate` (implementer, debugger,
   architect), **When** policy is applied, **Then** the operator receives an escalation
   with three choices — bump +50% and resume, reroute cheaper, kill — and the chosen
   action is executed; bump raises `max_budget` on the same key and resumes in the same
   worktree.
7. **Given** an escalation with no operator response for 1 hour, **When** the timeout
   fires, **Then** the node is killed (work already salvaged).

---

### User Story 3 - Spend ledger (Priority: P3)

As the factory operator, I can see what every node actually spent, per epic, after the
fact — even for nodes that breached or were killed — so I can tune persona budget
defaults from data.

**Why this priority**: Observability on top of US1/US2; valuable but not enforcement.

**Independent Test**: Append entries for several nodes across two epics; query per-epic
entries and totals.

**Acceptance Scenarios**:

1. **Given** completed teardowns, **When** I query the ledger for an epic, **Then** I
   get one row per node with persona, budget, final spend, termination class, and
   issue/teardown timestamps, plus a per-epic total.
2. **Given** a ledger row, **When** it is read back, **Then** the termination class
   round-trips as a typed value, not a bare string.

---

### Edge Cases

- Agent output contains a breach marker but exit code is 0 → COMPLETED wins (work
  exists; spend is still capped by the proxy).
- Timeout and breach markers both present → TIMEOUT wins (markers may be incidental to
  a hang).
- Breach detected on a node we ourselves signaled to stop → BUDGET_BREACH, not KILLED
  (must not misfile self-inflicted stops).
- Zero-budget persona (deterministic `verifier`) → no key is issued at all; no ledger
  row for LLM spend.
- Proxy returns 401 (bad master key) → error surfaces with status but must never echo
  the master key in any message or log.
- Escalation "bump" chosen after the key's TTL expired → bump fails; escalation
  re-presented with kill/reroute only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST mint one dedicated LiteLLM virtual key per LLM-consuming
  node at dispatch, carrying: the node's budget as a hard cap (`max_budget`), alias
  `<epic_id>:<node_id>`, metadata `{node_id, epic_id, persona}`, the persona's allowed
  model list, and an expiry TTL as a backstop against teardown failure.
- **FR-002**: The budget applied MUST be the node's explicit override when present,
  otherwise the persona's default from the registry.
- **FR-003**: The system MUST revoke the node's key and write exactly one ledger row on
  every terminal path; teardown MUST be idempotent and MUST NOT fail when the key is
  already gone or final spend cannot be read.
- **FR-004**: The system MUST poll spend during node execution (heartbeat cadence,
  ~30s) and emit exactly one soft warning per node at ≥80% of budget. Polling MUST NOT
  require reconfiguring the deployed proxy (no proxy-side alerting in v1).
- **FR-005**: The system MUST classify every agent termination into exactly one of:
  COMPLETED, AGENT_ERROR, BUDGET_BREACH, TIMEOUT, KILLED — using exit code, output
  markers (`ExceededTokenBudget`, `budget_exceeded`, `ExceededBudget`), and the last
  spend snapshot, with precedence: clean exit → COMPLETED; timeout → TIMEOUT; breach
  evidence → BUDGET_BREACH; operator/self kill → KILLED; else AGENT_ERROR.
- **FR-006**: On breach, the system MUST salvage the worktree (commit to the node
  branch) before any cleanup, on every path, without exception.
- **FR-007**: The system MUST apply the persona's breach policy: `hard-kill` → fail
  node + notify; `escalate` → operator prompt with [bump +50% & resume | reroute
  cheaper | kill], defaulting to kill after 1 hour of silence. Bump MUST raise
  `max_budget` on the existing key and resume in the same worktree.
- **FR-008**: All budgets MUST be denominated in USD. Local models MUST have synthetic
  per-token pricing registered in the proxy so their spend is non-zero and enforceable
  (operator setup step, documented).
- **FR-009**: The master key MUST be read from the worker host environment inside
  activities only, and MUST never appear in workflow state, activity inputs/results,
  logs, or error messages. The per-node virtual key MAY travel in orchestration
  payloads (it is capped, constrained, TTL'd, and revoked).
- **FR-010**: The ledger MUST be append-only, one row per node teardown, recording
  epic, node, persona, alias, budget, final spend, termination class, and timestamps;
  it MUST support per-epic filtering and totals. Storage is a SQLite database file
  (Python stdlib `sqlite3` — no new dependency) and MUST remain correct under
  concurrent teardown writers; a JSONL export MAY be provided as a convenience.

### Key Entities

- **Persona registry** (`personas.yaml`): operator-editable mapping persona → {agent,
  model, fallback, skills, write scope, budget default USD, breach policy,
  needs_worktree}. Six personas: architect, implementer, verifier, judge, debugger,
  researcher. Escalate: implementer/debugger/architect; hard-kill:
  verifier/judge/researcher. Verifier is deterministic (no agent, no model, no key).
  Model values are operator-supplied LiteLLM aliases; shipped file contains CHANGEME
  placeholders.
- **KeyLease**: the live binding of one virtual key to one node — key, alias, node,
  epic, persona, budget, issue time.
- **SpendSnapshot**: point-in-time spend vs budget for a key; derives fraction-used and
  exhausted.
- **Termination**: enum COMPLETED | AGENT_ERROR | BUDGET_BREACH | TIMEOUT | KILLED.
- **LedgerEntry**: one teardown record (see FR-010).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: No node can spend more than its budget plus one in-flight request — the
  cap is enforced by the proxy, not by agent cooperation.
- **SC-002**: 100% of node teardowns produce exactly one ledger row, including breach,
  kill, and timeout paths.
- **SC-003**: 100% of budget breaches are classified BUDGET_BREACH (never AGENT_ERROR)
  in the test matrix of termination scenarios.
- **SC-004**: Zero occurrences of the master key in any persisted artifact (payloads,
  ledger, logs, error strings) under test.
- **SC-005**: A breached escalate-persona node whose operator picks "bump" resumes in
  the same worktree with the raised cap, with no work lost.

## Assumptions

- The LiteLLM proxy is already deployed and reachable; the operator provides a master
  key and proxy URL via worker-host environment variables.
- The operator already routes Claude Code through this proxy (base-URL + key) in daily
  use; the same mechanism carries the per-node virtual key.
- Key management uses the proxy's documented endpoints: `/key/generate`, `/key/info`,
  `/key/update`, `/key/delete`; breach manifests as HTTP 400 with an
  `ExceededTokenBudget`-style detail.
- Telegram delivery of warnings/escalations is specified separately (component 2's
  notifier); until it exists, this component emits notifications through a stub
  interface and escalations default to the kill path.
- Node budgets never reset mid-node (no `budget_duration`); the TTL is expiry, not
  reset.
