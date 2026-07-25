# Feature Specification: Per-Node Usage Tracking

**Feature Branch**: `001-usage-tracking`

**Created**: 2026-07-24

**Status**: Draft

**Input**: Component 1 of the Ergane factory (D-014 attribution mechanics, D-021 pivot):
attribute every LLM token and dollar to the WorkGraph node that spent it — token
breakdown (input, output, cache read, cache write) per node, rolled up by persona and
epic, tied to the piece of work (the node's OpenSpec requirement ref). **No budget
enforcement**: caps, breach policy, and escalation are deferred to spec
`004-budget-enforcement`.

## Clarifications

### Session 2026-07-24

- Q: Ledger storage medium given concurrent teardown writers? → A: SQLite database file (stdlib `sqlite3`, no new dependency); JSONL export as a convenience.
- Q: Enforce per-node budgets in this component? → A: No — track spend only. Token detail (input/output/cache) per persona and total, attributable to a piece of work. Enforcement (caps, breach policy, escalation) deferred to spec 004.
- Q: Final usage when the proxy is unreadable at teardown? → A: Record the last-known heartbeat snapshot with an explicit unconfirmed flag; NULL only if no snapshot was ever taken. Never fabricate zeros. (Resolved as low-stakes under tracking-only scope.)
- Q: Usage granularity when a node retries (component 2 loop)? → A: One key + one ledger row per attempt, with an `attempt` number on the row; node-level totals via rollup.
- Q: Rely on LiteLLM's own storage/reporting instead of a factory ledger? → A: No — keep the factory-owned SQLite ledger (insulation from LiteLLM schema/upgrades/licensing). LiteLLM spend logs remain the upstream source aggregated at teardown; only genuinely OSS-tier LiteLLM features may be used (key_alias, /spend/logs/v2, daily-activity endpoints) — enterprise-labeled features (per-key tags, spend_logs_metadata) are prohibited even where upstream license checks are currently missing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Attributed usage per node (Priority: P1)

As the factory operator, every LLM-consuming node's usage — input tokens, output
tokens, cache-read and cache-write tokens, request count, and dollar cost where the
model is priced — is captured and attributed to exactly one node, with its persona,
epic, and the OpenSpec requirement it was working on, without relying on the agent to
self-report.

**Why this priority**: Attribution is the whole component; rollups and visibility are
derivatives. Attribution must not depend on agent cooperation (agents crash, get
killed, misreport).

**Independent Test**: Run a node against a (fake or real) LiteLLM proxy, make several
model calls on its key, tear down, and assert the ledger row carries the correct token
breakdown and work reference.

**Acceptance Scenarios**:

1. **Given** a node `n1` in epic `e1` with persona `implementer` working on requirement
   `auth/Requirement: Session refresh`, **When** the node is dispatched, **Then** a
   dedicated virtual key is minted with alias `e1:n1`, metadata `{node_id, epic_id,
   persona, spec_ref}`, the persona's allowed model list, a TTL backstop — and **no
   spend cap**.
2. **Given** the agent makes requests on that key, **When** the node reaches any
   terminal state, **Then** teardown revokes the key and writes exactly one ledger row
   with the node's token breakdown (input, output, cache read, cache write), request
   count, and USD cost where priced.
3. **Given** a key already gone at teardown (TTL expiry), **When** teardown runs,
   **Then** it still succeeds (idempotent) and ledgers the last-known usage snapshot
   flagged as unconfirmed.
4. **Given** the proxy is unreachable at teardown, **When** the final usage read fails,
   **Then** the row records the last heartbeat snapshot with `final_usage_confirmed =
   false` — never a fabricated zero — and NULL only if no snapshot was ever taken.
5. **Given** a node running a local model with no registered pricing, **When** its row
   is written, **Then** token counts are complete even though USD cost is zero/absent.

---

### User Story 2 - Rollups by persona, epic, and piece of work (Priority: P2)

As the factory operator, I can ask: what did each persona spend (tokens and dollars)
this epic? What did this specific requirement cost across all the nodes that touched
it? What's the grand total? — so I can see where the factory's inference spend actually
goes and tune persona/model assignments from data.

**Why this priority**: The analytical payoff of US1; needs only query logic on top of
the ledger.

**Independent Test**: Ledger rows for multiple nodes across two epics and three
personas; assert per-persona, per-epic, per-spec-ref, and grand-total aggregations.

**Acceptance Scenarios**:

1. **Given** completed teardowns across epics, **When** I query by persona, **Then** I
   get token breakdown and USD totals per persona, within an epic and across all
   epics.
2. **Given** several attempts and nodes that worked on the same requirement (retries,
   debugger handoffs), **When** I query by spec ref, **Then** I get the combined cost
   of that piece of work across all its attempts and nodes — and by attempt ordinal,
   the cost of retries specifically.
3. **Given** an epic, **When** I query its total, **Then** I get tokens + USD summed
   over all its nodes, with unconfirmed rows included but flagged in the result.

---

### User Story 3 - Live usage visibility (Priority: P3)

As the factory operator, I can see what a running node has consumed so far (tokens,
dollars) — observability only, no enforcement action of any kind.

**Why this priority**: Nice-to-have while nodes run; everything material lands in the
ledger at teardown regardless.

**Independent Test**: Poll a running node's usage mid-flight and assert the snapshot
reflects proxy state; assert no side effects on the node.

**Acceptance Scenarios**:

1. **Given** a running node, **When** its usage is polled on the activity heartbeat
   (~30s cadence), **Then** a current snapshot (spend, tokens where available) is
   retained as the latest-known state for teardown fallback and live inspection.
2. **Given** any snapshot value, however large, **When** polling observes it, **Then**
   no warning, kill, or escalation is triggered (tracking-only guarantee).

---

### Edge Cases

- Node killed or timed out mid-request → teardown still writes a row; in-flight
  request's tokens appear if the proxy logged them, else the unconfirmed snapshot
  stands.
- Zero-usage node (agent crashed before any call) → row exists with zero requests,
  distinguishing "spent nothing" (confirmed) from "unknown" (unconfirmed NULL).
- Deterministic `verifier` persona (no agent, no model) → no key, no ledger row; its
  cost is not LLM cost.
- Same requirement touched by nodes in different epics → spec-ref rollup crosses
  epics; per-epic filter still available.
- Proxy returns 401 (bad master key) → error surfaces with status; master key never
  echoed in any message or log.
- Concurrent teardowns → SQLite ledger remains consistent (no lost or interleaved
  rows).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST mint one dedicated LiteLLM virtual key per **node
  attempt** at dispatch — the attribution primitive — carrying alias
  `<epic_id>:<node_id>:<attempt>`, metadata `{node_id, epic_id, persona, spec_ref,
  attempt}`, the persona's allowed model list, and an expiry TTL backstop. The key
  MUST NOT carry a spend cap (`max_budget` unset). Each retry of a node is a new
  attempt with its own key.
- **FR-002**: The system MUST revoke the node's key and write exactly one ledger row on
  every terminal path; teardown MUST be idempotent and MUST NOT fail when the key is
  already gone or the proxy is unreachable.
- **FR-003**: Each ledger row MUST record: epic, node, **attempt number**, persona,
  spec ref, key alias, input tokens, output tokens, cache-read tokens, cache-write
  tokens, request count, USD cost where priced, termination class, issue/teardown
  timestamps, and a `final_usage_confirmed` flag. One row per attempt teardown.
- **FR-004**: Token-level detail MUST come from the proxy's per-request spend logs for
  the attempt's key (not from agent self-reporting), aggregated at teardown; where the
  backend omits a cache metric, the row records it as absent, not zero. Only
  genuinely OSS-tier proxy features may be used for this (key alias, spend-log query
  endpoints); enterprise-labeled features MUST NOT be relied on, including where
  upstream license enforcement is currently missing.
- **FR-005**: When the final read fails, the row MUST carry the last heartbeat snapshot
  flagged unconfirmed; NULL only if no snapshot was ever taken. Fabricated zeros are
  prohibited.
- **FR-006**: The ledger MUST support rollups: by node (attempts aggregated), by
  persona (per-epic and global), by epic, by spec ref (across epics), by attempt
  ordinal (e.g. cost of attempt ≥2 = the price of retries), and grand totals — token
  breakdown and USD in each, with unconfirmed rows included and flagged.
- **FR-007**: The system MUST poll usage during node execution (heartbeat cadence,
  ~30s) for live visibility and snapshot retention only; polling MUST trigger no
  enforcement action. Polling MUST NOT require reconfiguring the deployed proxy.
- **FR-008**: The system MUST classify every agent termination into exactly one of:
  COMPLETED, AGENT_ERROR, TIMEOUT, KILLED (budget-breach classification belongs to
  deferred spec 004), recorded on the ledger row.
- **FR-009**: The master key MUST be read from the worker host environment inside
  activities only, and MUST never appear in workflow state, activity inputs/results,
  logs, or error messages. The per-node virtual key MAY travel in orchestration
  payloads (it is model-constrained, TTL'd, and revoked at teardown).
- **FR-010**: Ledger storage is a SQLite database file (Python stdlib `sqlite3` — no
  new dependency), append-only (one row per teardown), and MUST remain correct under
  concurrent teardown writers; a JSONL export MAY be provided as a convenience.
- **FR-011**: Token counts MUST be recorded for all models regardless of pricing; USD
  is recorded when the proxy prices the model (registering synthetic pricing for local
  models is optional operator setup, not a requirement of this component).

### Key Entities

- **Persona registry** (`personas.yaml`): operator-editable mapping persona → {agent,
  model, fallback, skills, write scope, needs_worktree}. Six personas: architect,
  implementer, verifier, judge, debugger, researcher; verifier is deterministic (no
  agent, no model, no key). Model values are operator-supplied LiteLLM aliases.
  (Budget-default and breach-policy attributes belong to deferred spec 004.)
- **KeyLease**: the live binding of one virtual key to one node attempt — key, alias,
  node, epic, attempt, persona, spec ref, issue time.
- **UsageSnapshot**: point-in-time usage for a key — spend USD and token counts as
  available — retained per heartbeat as latest-known state.
- **Termination**: enum COMPLETED | AGENT_ERROR | TIMEOUT | KILLED.
- **UsageRecord** (ledger row): see FR-003.
- **Spec ref**: the work-attribution key — change name + capability + requirement
  header, as parsed from OpenSpec (component 2 owns the parser; here it is an opaque
  string carried on the node).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of LLM-node teardowns produce exactly one ledger row, on every
  terminal path including kill and timeout.
- **SC-002**: Ledger token totals reconcile with the proxy's own spend logs for the
  same keys (exact match when final read succeeded; flagged when unconfirmed).
- **SC-003**: Every ledger row is attributable: node, persona, epic, and spec ref are
  non-null for 100% of rows.
- **SC-004**: Zero occurrences of the master key in any persisted artifact (payloads,
  ledger, logs, error strings) under test.
- **SC-005**: Zero enforcement side effects: no node is ever warned, throttled, or
  killed by this component under any usage level in test.
- **SC-006**: Per-spec-ref rollup answers "what did this requirement cost?" across
  retries and epics in a single query.

## Assumptions

- The LiteLLM proxy is already deployed and reachable; the operator provides a master
  key and proxy URL via worker-host environment variables. The operator already routes
  Claude Code through this proxy in daily use.
- Key management uses the proxy's documented endpoints (`/key/generate`, `/key/info`,
  `/key/delete`); per-request token detail comes from the proxy's spend-log records
  keyed by the attempt's virtual key (exact endpoint/fields are plan-level detail).
- The proxy runs with its database and spend-log persistence enabled (default when
  virtual keys are in use, as they are in the operator's daily setup); target-repo-
  independent setup validation verifies this before first dispatch.
- The SQLite ledger file lives on a single designated worker host; ledger-writing
  activities are pinned to that host via a dedicated task queue so the single-writer
  constraint is enforced by topology, not convention. (Multi-host ledger access is out
  of scope; the ledger can be rebuilt from proxy spend logs if ever needed.)
- Cache-read/cache-write token metrics are available for Anthropic-backed calls; other
  backends may omit them (FR-004 covers absence).
- Node budgets, caps, soft warnings, breach classification, and escalation are all out
  of scope — designed and parked in `specs/004-budget-enforcement/` (Status: Deferred).
- Nodes carry their spec ref from WorkGraph data; this component treats it as opaque.
