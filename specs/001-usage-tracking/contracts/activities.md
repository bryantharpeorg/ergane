# Contract: Temporal Activities (usage middleware)

Task queue: `usage-ledger` for `teardown_attempt` (pinned to the ledger host — the
single-writer topology from the spec assumption); `workgraph` for the rest.
All activities read `LITELLM_PROXY_URL` + `LITELLM_MASTER_KEY` from process env; the
master key never appears in inputs, outputs, heartbeats, or raised errors (FR-009).

## issue_attempt_key

Mints the attempt's attribution key (FR-001, R1).

- **Input** `IssueKeyInput`: `node_id: str`, `epic_id: str`, `attempt: int`,
  `persona: str`, `spec_ref: str`, `models: list[str]`, `ttl: str = "24h"` (R5)
- **Output**: `KeyLease` (see data-model.md)
- **Proxy calls**: `POST /key/generate` — `max_budget` OMITTED; alias
  `{epic}:{node}:{attempt}`; metadata mirrors input dims
- **Retry policy** (workflow-side, R4): initial 2s, ×2 backoff, max 60s interval,
  10min max elapsed; then `KEY_ISSUANCE_FAILED` (non-retryable application error)
- **Idempotency**: re-execution after a partial success may mint a duplicate key with
  the same alias — teardown revokes by key, and ledger upserts by alias, so
  duplicates are harmless; the proxy's alias-uniqueness error (if enabled) is
  treated as success-with-lookup.

## poll_usage

Heartbeat-cadence observability read (FR-007, R9). Enforcement-free by contract.

- **Input**: `KeyLease`
- **Output**: `UsageSnapshot {spend_usd, captured_at}`
- **Proxy calls**: `GET /key/info?key=...`
- **Failure mode**: raises; CALLER treats failure as skippable (a missed poll never
  fails the attempt — SC-005). Never triggers any action based on the value.

## teardown_attempt

The exactly-once ledger write + key revocation (FR-002/003/005, R2, R3).

- **Input** `TeardownInput`: `lease: KeyLease`, `termination: Termination`,
  `last_snapshot: UsageSnapshot | None`
- **Output**: `UsageRecord` (as persisted)
- **Proxy calls, strictly ordered** (R3):
  1. `GET /key/info` (final spend; on failure → fallback path)
  2. `GET /spend/logs/v2?...` paged by the attempt's key (token detail; on failure →
     fallback path)
  3. SQLite upsert by `key_alias` (WAL, read-write connection)
  4. `POST /key/delete` (LAST; 404/400 = already gone = success)
- **Fallback path**: `final_usage_confirmed = 0`; `spend_usd` from `last_snapshot`
  (NULL if None); token fields NULL. Zeros are never fabricated (FR-005).
- **Idempotency**: upsert by unique `key_alias`; key deletion tolerant of absence.
  Safe under Temporal at-least-once execution.

## Workflow-side call pattern (informative)

```
lease = await execute_activity(issue_attempt_key, input, retry_policy=R4)
try:
    result = await execute_activity(run_agent, ..., heartbeat→poll_usage snapshots)
finally:
    await execute_activity(teardown_attempt,
                           TeardownInput(lease, classify(result), last_snapshot),
                           task_queue="usage-ledger")
```

`run_agent` and `classify` belong to the agent-adapter surface (D-018), not this
component; the contract here is only that teardown runs on every terminal path.
