# Phase 0 Research: Per-Node Usage Tracking

All unknowns from Technical Context resolved. Primary source: LiteLLM source-code
research performed 2026-07-24 (BerriAI/litellm @ main c93c3f7, schema.prisma,
spend_tracking_utils.py, spend_management_endpoints.py; docs mirror
BerriAI/litellm-docs @ 02fe2aa) plus earlier proxy-API research (docs.litellm.ai
virtual_keys / cost_tracking pages, 2026-07-24 session).

## R1. Attribution mechanism

**Decision**: One virtual key per node attempt; alias `epic:node:attempt`; metadata
`{node_id, epic_id, persona, spec_ref, attempt}`; `models` = persona's allowed list;
`duration` (TTL) set; `max_budget` omitted.

**Rationale**: The key is the only attribution primitive that works without agent
cooperation — everything the agent spends flows through it. Alias encodes the
dimensions LiteLLM *will* reliably return; metadata is a best-effort mirror (LiteLLM
does NOT copy arbitrary key metadata into spend rows — verified). Persona/spec_ref
resolution therefore happens factory-side at teardown (the activity input carries
them), not from proxy data.

**Alternatives considered**: per-request tags (`metadata.tags`) — rejected:
enterprise-licensed (per-key tags gate is unenforced at `/key/generate` today, but
building on a licensing gap is prohibited by FR-004); `spend_logs_metadata` —
rejected for the same reason; one key per node spanning attempts — rejected by
clarification (per-attempt granularity chosen).

## R2. Token detail extraction

**Decision**: At teardown, page through the proxy's per-request spend logs filtered
to the attempt's key (`GET /spend/logs/v2`, OSS-verified; fallback `GET /spend/logs?api_key=`)
and aggregate in a pure function: `prompt_tokens`, `completion_tokens` summed from
row columns; cache tokens summed from each row's
`metadata.additional_usage_values.cache_read_input_tokens` /
`cache_creation_input_tokens`; request count = row count; USD = sum of row `spend`.
A cache metric absent from every row → stored as NULL (absent), not 0 (FR-004).

**Rationale**: SpendLogs columns carry prompt/completion/total tokens and spend;
cache detail is only in the metadata JSON (`additional_usage_values` — verified in
`get_logging_payload`). Aggregating factory-side keeps us on ungated endpoints and
off the enterprise daily-rollup UI paths.

**Alternatives considered**: `/user/daily/activity` per-key breakdown (has
first-class cache columns) — kept as a cross-check tool, not primary: day-granular
and keyed to the verification-token table, which the deleted key eventually leaves;
direct Postgres reads of `LiteLLM_SpendLogs` — documented escape hatch for ledger
rebuilds only (schema is Prisma-migrated, no compat guarantee; pin version if used).

## R3. Teardown ordering (correctness-critical)

**Decision**: `read /key/info` → `page spend logs` → `write ledger row` → `delete key`.
Key deletion is LAST. If any read step fails, fall back to the latest heartbeat
snapshot (`final_usage_confirmed = false`) and still delete + ledger.

**Rationale**: Spend-log *rows* survive key deletion (alias persisted per-row in
`metadata.user_api_key_alias` — verified), but the `/spend/logs/v2` `key_alias`/
`api_key` filters may resolve through the live token table; deleting last removes any
dependence on post-deletion filter behavior. Idempotency: a re-run teardown that
finds the key already gone uses the snapshot path (FR-002, FR-005).

**Alternatives considered**: delete-then-aggregate — rejected (risks unfiltered or
empty reads); aggregate continuously during run — rejected (heartbeat snapshot
already covers liveness; full pagination every 30s is wasteful).

## R4. Key-issuance failure at dispatch (carried from clarify session 1)

**Decision**: Temporal activity retry policy on `issue_attempt_key`: initial 2s,
backoff ×2, max interval 60s, max elapsed 10min. Exhaustion fails the attempt with a
distinct `KEY_ISSUANCE_FAILED` activity error; the interpreter records the attempt as
`AGENT_ERROR`-class infrastructure failure (no key row → no ledger row; the attempt
never ran) and notifies. No agent process is ever started without a key.

**Rationale**: Proxy blips are transient (restarts, deploys); 10 minutes absorbs
them without wedging the epic. Distinct error type keeps infra failures out of
agent-quality statistics.

**Alternatives considered**: fail-fast (brittle against routine proxy restarts);
infinite retry (wedges the node invisibly — violates "no silent stalls" ethos).

## R5. Key TTL default (carried from clarify session 1)

**Decision**: `duration: "24h"`, constant in config with per-dispatch override.

**Rationale**: An attempt outliving 24h is pathological (timeouts fire long before);
TTL is purely the backstop against teardown never running. Long enough to never
truncate a legitimate attempt, short enough that leaked keys die within a day.

**Alternatives considered**: 7d (needlessly long exposure for a credential); 1h
(could expire under a legitimately long implementer attempt + queued teardown).

## R6. SQLite concurrency & durability

**Decision**: `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, one connection per
activity invocation, single `INSERT` per teardown in an implicit transaction.
Schema versioned with a `schema_version` pragma table; rollup queries are plain SQL
(see contracts/ledger-schema.sql).

**Rationale**: WAL gives safe concurrent writers within one host — which is the
enforced topology (dedicated task queue pins ledger activities to the host that owns
the file). Per-invocation connections avoid cross-async-task sharing issues.

**Alternatives considered**: long-lived connection pool (needless statefulness in
activities); JSONL (rejected in clarification — interleaving risk); Postgres
(rejected in clarification — new infrastructure).

## R7. CLI implementation

**Decision**: stdlib `argparse` console script `factory-usage` (entry point in
pyproject): `factory-usage [--db PATH] [--epic E] [--since DATE] --by
persona|epic|spec-ref|attempt|node [--json]`. Human output = aligned table; `--json`
= stable machine shape (see contracts/cli.md). Opens SQLite read-only
(`mode=ro` URI) — the read-only guarantee is structural, not conventional.

**Rationale**: Zero new dependencies (constitution III); `mode=ro` makes US2's
"no CLI invocation ever writes" testable and enforced.

**Alternatives considered**: `click`/`typer` (nicer ergonomics, but a dependency ask
for a 5-flag CLI is not justified); rich TUI (out of scope).

## R8. Persona registry shape (restored from D-012, trimmed per D-021)

**Decision**: `personas.yaml` at repo root: per persona `{agent, model, fallback,
skills, write_scope, needs_worktree}` — no `budget_usd`, no `breach_policy` (those
return with spec 004). Verifier: `agent: none, model: null` → keyless. Loader
validates enums and the agent/model consistency rules; CHANGEME placeholders ship.

**Rationale**: This component needs the registry for the `models` list on key
issuance and the write-scope-derived rules component 2 will consume; enforcement
fields would be dead config until 004 reactivates.

## R9. Heartbeat polling mechanics

**Decision**: The agent-running activity heartbeats every ~30s; each heartbeat calls
`GET /key/info` and stores `{spend, ts}` as the latest snapshot in activity-local
state, surfaced to the workflow only at completion (not per-beat). Snapshot is
input to teardown as the fallback. Polling failures are logged and skipped — a
missed poll never fails the attempt (SC-005: zero enforcement side effects).

**Rationale**: `/key/info` is one cheap indexed read; 30s bounds staleness of the
unconfirmed-fallback path to one poll interval. Token-level detail is deliberately
NOT polled (R2 does that once, at teardown).
