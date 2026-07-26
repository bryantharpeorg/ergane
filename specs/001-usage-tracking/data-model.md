# Data Model: Per-Node Usage Tracking

Entities from spec Key Entities, refined by research decisions R1–R8. All dataclasses
are frozen (immutable) and Temporal-payload-safe unless noted.

## Persona (config, not persisted)

Loaded from `personas.yaml` (R8).

| Field | Type | Rules |
|---|---|---|
| name | str | registry key |
| agent | str | adapter name; `"none"` = deterministic persona |
| model | str \| None | required iff agent ≠ "none"; None iff agent = "none" |
| fallback | str \| None | optional |
| skills | tuple[str, ...] | may be empty |
| write_scope | enum `worktree\|docs\|read` | drives component 2's diff-exemption rule |
| needs_worktree | bool | |

Derived: `is_llm = agent != "none"`. LLM personas get keys; `verifier` never does.

## KeyLease (Temporal payload)

The live binding of one virtual key to one node **attempt** (R1).

| Field | Type | Rules |
|---|---|---|
| key | str | the virtual key; capped-scope credential, allowed in payloads (FR-009) |
| key_alias | str | `"{epic_id}:{node_id}:{attempt}"` — unique per attempt |
| node_id | str | |
| epic_id | str | |
| attempt | int | ≥ 1 |
| persona | str | registry name |
| spec_ref | str | opaque work-attribution key (change/capability/requirement) |
| issued_at | str | ISO 8601 UTC |

Uniqueness: `(epic_id, node_id, attempt)` is the attempt identity everywhere.

## UsageSnapshot (Temporal payload)

Point-in-time `/key/info` read (R9); heartbeat state and teardown fallback.

| Field | Type | Rules |
|---|---|---|
| spend_usd | float | ≥ 0; proxy-computed (0 for unpriced models) |
| captured_at | str | ISO 8601 UTC |

## AggregatedUsage (internal, pure-function output)

Result of aggregating spend-log rows for one key (R2).

| Field | Type | Rules |
|---|---|---|
| prompt_tokens | int | summed row columns |
| completion_tokens | int | summed row columns |
| cache_read_tokens | int \| None | None = metric absent from all rows (never fabricated 0) |
| cache_write_tokens | int \| None | same rule |
| request_count | int | row count |
| spend_usd | float | summed row `spend` |

## Termination (enum)

`COMPLETED | AGENT_ERROR | TIMEOUT | KILLED` (FR-008). `BUDGET_BREACH` intentionally
absent (deferred, spec 004). Persisted as lowercase strings.

## UsageRecord (ledger row — the persisted entity)

One row per attempt teardown (FR-003). SQLite DDL in
[contracts/ledger-schema.sql](contracts/ledger-schema.sql).

| Column | Type | Rules |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| epic_id | TEXT NOT NULL | |
| node_id | TEXT NOT NULL | |
| attempt | INTEGER NOT NULL | ≥ 1 |
| persona | TEXT NOT NULL | |
| spec_ref | TEXT NOT NULL | SC-003: never null |
| key_alias | TEXT NOT NULL UNIQUE | idempotency guard: re-teardown upserts, never duplicates |
| prompt_tokens | INTEGER NULL | NULL only on unconfirmed-with-no-data path |
| completion_tokens | INTEGER NULL | same |
| cache_read_tokens | INTEGER NULL | NULL = absent metric (FR-004) |
| cache_write_tokens | INTEGER NULL | same |
| request_count | INTEGER NULL | |
| spend_usd | REAL NULL | NULL only if no snapshot ever taken (FR-005) |
| final_usage_confirmed | INTEGER NOT NULL (0/1) | 0 = last-snapshot fallback used |
| termination | TEXT NOT NULL | enum value |
| issued_at | TEXT NOT NULL | ISO 8601 |
| torn_down_at | TEXT NOT NULL | ISO 8601 |

Indexes: `(epic_id)`, `(persona)`, `(spec_ref)`, `(epic_id, node_id, attempt)`.

## State transitions (attempt lifecycle, this component's slice)

```
DISPATCH ──issue_attempt_key──▶ KEY_ISSUED ──agent runs──▶ (heartbeat: UsageSnapshot*)
    │ (retry policy R4 exhausted)                                │ terminal (any path)
    ▼                                                            ▼
KEY_ISSUANCE_FAILED                              teardown_attempt (idempotent)
(no key, no ledger row,                          order: info → spend logs → ledger → delete
 infra-failure notification)                                     │
                                                                 ▼
                                                     UsageRecord persisted (exactly one)
```

Invariants:
- Exactly one UsageRecord per issued key, on every terminal path (SC-001).
- No UsageRecord without an issued key (issuance failure ≠ usage).
- `final_usage_confirmed = 1` ⟺ teardown read proxy data successfully.
- Rollups (FR-006) are pure SQL over UsageRecord; unconfirmed rows included + flagged.
