# Implementation Plan: Per-Node Usage Tracking

**Branch**: `001-usage-tracking` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-usage-tracking/spec.md`

## Summary

Attribute every LLM token and dollar to the WorkGraph node attempt that spent it, with
no enforcement. Mechanism: one LiteLLM virtual key per node attempt (alias
`epic:node:attempt`, no `max_budget`) issued/revoked by Temporal activities; usage
polled on the activity heartbeat as observability + teardown fallback; at teardown,
per-request token detail (input/output/cache-read/cache-write) aggregated from the
proxy's spend logs into a factory-owned SQLite ledger (one row per attempt); rollups
by node/persona/epic/spec-ref/attempt via a read-only CLI and documented schema.

## Technical Context

**Language/Version**: Python 3.11+ (D-003)

**Primary Dependencies**: `temporalio` (activities/workflow surface), `httpx` (LiteLLM
admin API client), `pyyaml` (persona registry) — all pre-approved (constitution III).
Ledger: stdlib `sqlite3`. CLI: stdlib `argparse`. No new dependencies.

**Storage**: SQLite database file, WAL mode, single designated worker host (dedicated
task queue enforces single-writer topology; spec assumption). Upstream source of
truth: LiteLLM proxy Postgres (`LiteLLM_SpendLogs`) — read via OSS HTTP endpoints
only, never written.

**Testing**: `pytest` + `pytest-asyncio`; `temporalio.testing.ActivityEnvironment` for
activities; `httpx.MockTransport` fake of the LiteLLM key/spend API (validated
approach in this repo's earlier scaffold); `tmp_path` SQLite databases.

**Target Platform**: Linux worker host(s) alongside the Temporal dev server
(`temporal server start-dev --db-filename .temporal/dev.db`, namespace `factory`).

**Project Type**: Library package (`factory/`) + Temporal activity surface + read-only
CLI. No service, no UI.

**Performance Goals**: Modest by design — tens of concurrent attempts; heartbeat
polling ~1 request/30s per running attempt; teardown aggregation bounded by an
attempt's request count (typically < 10³ spend-log rows).

**Constraints**: Master key only in worker-host env, read inside activities, never in
payloads/logs/errors (FR-009). Only genuinely OSS-tier LiteLLM features (FR-004).
No enforcement side effects of any kind (SC-005). Never fabricate zeros (FR-005).

**Scale/Scope**: Single operator, one proxy, low-thousands of ledger rows per epic.
SQLite is comfortably sufficient; multi-host ledger out of scope (spec assumption).

## Constitution Check

*GATE: evaluated against constitution v2.1.0 before Phase 0; re-checked after Phase 1.*

| Principle | Status | Evidence |
|---|---|---|
| I. Build order, vertical slices | PASS | This is component 1; no other component depends on unbuilt work. Ships with tests before component 2 starts. |
| II. Test-first | PASS | Every deliverable has a test strategy (see Testing above; tasks will order tests first). |
| III. Ask before dependencies | PASS | Uses only the approved roster + stdlib (`sqlite3`, `argparse`). Zero new dependencies requested. |
| IV. Determinism core, LLMs edges | PASS | No LLM calls anywhere in this component. Side effects (HTTP, SQLite) live in activities; classification/rollup logic is pure functions. |
| V. Spend attributed, never anonymous | PASS | This component *is* Principle V's implementation: key-per-attempt, ledger row per teardown, unknown-flagged-not-zeroed. |
| VI. No work lost | PASS (n/a) | Worktree salvage belongs to components 2/4; this component's analogue — ledger row on every terminal path, teardown idempotent — is FR-002/FR-005. |
| VII. Personas over model tiers | PASS | Persona registry (`personas.yaml`) resolves models; no model names in code; verifier persona keyless. |

**Post-Phase-1 re-check**: PASS — no design element introduced a violation; Complexity
Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-usage-tracking/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── activities.md    # Temporal activity contracts (inputs/outputs/idempotency)
│   ├── cli.md           # Read-only usage CLI contract
│   └── ledger-schema.sql# SQLite DDL (the documented direct-SQL surface, FR-012)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
factory/
├── __init__.py
├── config.py                    # persona registry loader/validation (personas.yaml)
├── usage/
│   ├── __init__.py
│   ├── models.py                # KeyLease, UsageSnapshot, UsageRecord, Termination
│   ├── litellm_client.py        # async admin client: /key/generate|info|delete, spend logs
│   ├── aggregate.py             # pure: spend-log rows -> token totals (cache handling)
│   ├── ledger.py                # SQLite ledger: schema, insert, rollup queries
│   └── cli.py                   # read-only `factory-usage` CLI (argparse, --json)
└── activities/
    ├── __init__.py
    └── usage_activities.py      # issue_attempt_key / poll_usage / teardown_attempt

personas.yaml                    # registry (restored; no budget/breach fields, D-021)
pyproject.toml                   # uv project; deps per approved roster

tests/
├── conftest.py                  # FakeLiteLLM (httpx.MockTransport, stateful)
├── test_config.py               # registry validation
├── test_litellm_client.py       # client contract vs fake proxy
├── test_aggregate.py            # token aggregation incl. cache-absent cases
├── test_ledger.py               # DDL, inserts, rollups, concurrency (threads)
├── test_cli.py                  # CLI output, --json shape, read-only guarantee
└── test_usage_activities.py     # ActivityEnvironment end-to-end vs fake proxy
```

**Structure Decision**: single `factory` package per D-004 (monorepo, one importable
package). `usage/` replaces the earlier `budgets/` naming (D-021). The WorkGraph
interpreter itself is NOT in scope — this component exposes activities + a thin
in-workflow call pattern documented in contracts/activities.md.

## Complexity Tracking

No constitution violations; table intentionally empty.
