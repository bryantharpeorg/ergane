# Quickstart: validating Per-Node Usage Tracking

Proves the component end-to-end. Implementation detail lives in tasks.md; this is the
run/validation guide only.

## Prerequisites

- Python 3.11+, `uv` installed
- (Live-proxy smoke only, §2) `LITELLM_PROXY_URL` + `LITELLM_MASTER_KEY` exported; proxy
  running with its database (spend-log persistence on — default when virtual keys work)
- (Topology check only, §4) Temporal CLI:
  `temporal server start-dev --db-filename .temporal/dev.db`

The test suite needs neither: activity tests run in-process on
`temporalio.testing.ActivityEnvironment` against a fake proxy, so §1 is green with no
Temporal server and no LiteLLM reachable.

## 1. Unit + activity tests (no external services)

```bash
uv sync
uv run pytest -q
```

Expected: all green. The suite covers, per spec success criteria:
- exactly-one-ledger-row on every terminal path incl. fallback (SC-001, FR-002/005)
- aggregation correctness incl. cache-absent → NULL (FR-004, via FakeLiteLLM)
- attribution completeness — no row with null node/persona/epic/spec_ref (SC-003)
- master key never in payloads/errors/ledger (SC-004)
- zero enforcement side effects at any usage level (SC-005)
- rollup queries incl. retry-cost by attempt ordinal (SC-006, FR-006)
- CLI `--json` shape and structural read-only-ness (FR-012)

## 2. Live-proxy smoke test (optional, hits your LiteLLM)

```bash
uv run pytest -q -m live_proxy
```

Issues a real throwaway key (no budget), makes one tiny completion through it on a
cheap/local model, tears down, and asserts the ledger row's tokens match the proxy's
spend logs (SC-002). Skipped automatically when env vars are absent.

## 3. Inspect rollups

```bash
uv run factory-usage --db .factory/ledger.db --by persona --json
uv run factory-usage --by attempt --epic <epic-id>     # the cost of retries
sqlite3 ".factory/ledger.db" ".schema usage_records"   # documented direct-SQL surface
```

Expected: outputs per [contracts/cli.md](contracts/cli.md); schema per
[contracts/ledger-schema.sql](contracts/ledger-schema.sql).

## 4. Verify the single-writer topology (deploy-time check)

The `teardown_attempt` activity must be registered ONLY by the worker on the host
that owns the ledger file, on task queue `usage-ledger`
([contracts/activities.md](contracts/activities.md)). Validation: start a second
worker elsewhere without that queue and confirm teardowns still route to the ledger
host.
