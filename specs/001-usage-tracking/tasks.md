# Tasks: Per-Node Usage Tracking

**Input**: Design documents from `/specs/001-usage-tracking/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — constitution II (test-first) is non-negotiable; each story's
tests are written first and must fail before implementation.

**Organization**: Grouped by user story; each story is independently implementable
and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1 (attributed usage), US2 (rollups + CLI), US3 (live visibility)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: uv project + package skeleton per plan.md Project Structure

- [X] T001 Create `pyproject.toml` (uv project; deps: temporalio, httpx, pyyaml; dev: pytest, pytest-asyncio; `factory-usage` console-script entry point; hatchling build with `factory` package; pytest `asyncio_mode=auto` and `live_proxy` marker)
- [X] T002 [P] Create package skeleton: `factory/__init__.py`, `factory/usage/__init__.py`, `factory/activities/__init__.py`, empty `tests/__init__.py` placeholder files
- [X] T003 [P] Restore `personas.yaml` at repo root per research R8 (six personas; `{agent, model, fallback, skills, write_scope, needs_worktree}`; CHANGEME model placeholders; NO budget/breach fields)
- [X] T004 [P] Extend `.gitignore` for `.factory/` ledger artifacts and `.venv/`, `__pycache__/`, `.pytest_cache/`, `.temporal/` (keep existing entries)
- [ ] T005 Run `uv sync` and verify `uv run pytest -q` collects zero tests successfully (toolchain sanity)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared types, config, fake proxy, LiteLLM client, ledger schema — every
story consumes these

**⚠️ CRITICAL**: No user story work until this phase completes

- [ ] T006 [P] Write `tests/test_config.py` FIRST: shipped registry parses with six personas; verifier is `agent: none`/`model: null`/keyless; write_scope enum enforced; agent/model consistency rules; missing-field and bad-enum rejection (per data-model.md Persona rules) — tests must fail (no config.py yet)
- [ ] T007 [P] Write `tests/conftest.py`: stateful `FakeLiteLLM` on `httpx.MockTransport` — `/key/generate` (no max_budget expected), `/key/info`, `/key/delete` (404 on missing), paginated `/spend/logs/v2` returning rows with `prompt_tokens`, `completion_tokens`, `spend`, and `metadata.additional_usage_values` cache fields (rows configurable per key, cache fields omittable); records all requests; rejects wrong master key with 401
- [ ] T008 [P] Implement `factory/usage/models.py`: frozen dataclasses `KeyLease` (incl. `attempt`, `spec_ref`), `UsageSnapshot`, `AggregatedUsage`, `UsageRecord`, enum `Termination` (COMPLETED|AGENT_ERROR|TIMEOUT|KILLED) — exactly per data-model.md field tables
- [ ] T009 Implement `factory/config.py` (persona registry loader/validation) until T006 passes
- [ ] T010 Write `tests/test_litellm_client.py` FIRST: issue key sends alias `epic:node:attempt`, metadata dims, models list, ttl, and NO `max_budget`; get_spend parses info; revoke idempotent on 404; spend-log pagination drains all pages; 401 error carries status but never the master key string — must fail (no client yet)
- [ ] T011 Implement `factory/usage/litellm_client.py` (async httpx client: `issue_key`, `get_spend`, `fetch_spend_log_rows` with pagination, `revoke_key`; credential-free `LiteLLMError`) until T010 passes
- [ ] T012 Write `tests/test_ledger_schema.py` FIRST: creating a ledger applies `contracts/ledger-schema.sql` DDL (WAL mode on, `usage_records` table + indexes + CHECK constraints present, `schema_version` = 1); upsert-by-`key_alias` uniqueness holds — must fail
- [ ] T013 Implement `factory/usage/ledger.py` (connection factory with WAL + busy_timeout per research R6, schema bootstrap from embedded DDL matching `contracts/ledger-schema.sql`, `upsert_record(UsageRecord)`) until T012 passes

**Checkpoint**: foundation ready — user stories can proceed (in parallel if desired)

---

## Phase 3: User Story 1 — Attributed usage per node attempt (Priority: P1) 🎯 MVP

**Goal**: every attempt's tokens (incl. cache), requests, and USD land in exactly one
ledger row, attributed to node/attempt/persona/epic/spec_ref, on every terminal path.

**Independent Test** (spec US1): run an attempt against the fake proxy, make calls on
its key, tear down, assert the row's token breakdown and work reference; repeat for
fallback paths.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T014 [P] [US1] Write `tests/test_aggregate.py`: spend-log rows → `AggregatedUsage` (sums, request count); cache fields absent from ALL rows → None (never 0); cache fields present on some rows → sum of present values; empty row set → zero-request aggregate (per research R2 / FR-004)
- [ ] T015 [P] [US1] Write `tests/test_usage_activities.py` (ActivityEnvironment + FakeLiteLLM + tmp ledger): issue→key exists with correct shape and no cap; teardown happy path follows R3 order (info → spend logs → ledger row → delete LAST, assert via request log) and row matches proxy data with `final_usage_confirmed=1`; teardown with key already gone → snapshot-fallback row `final_usage_confirmed=0`, spend from snapshot, tokens NULL; teardown with no snapshot ever → NULLs, never zeros; re-run teardown → still exactly one row (upsert); master key never in lease/record/error strings (SC-004); `KEY_ISSUANCE_FAILED` application error surfaces when proxy 500s persist (R4)

### Implementation for User Story 1

- [ ] T016 [P] [US1] Implement `factory/usage/aggregate.py` (pure function `aggregate_rows(rows) -> AggregatedUsage` incl. cache-absence rule) until T014 passes
- [ ] T017 [US1] Implement `factory/activities/usage_activities.py`: `issue_attempt_key` (raises typed `KEY_ISSUANCE_FAILED` per R4), `teardown_attempt` (strict R3 ordering, snapshot fallback, upsert, tolerant deletion) per `contracts/activities.md`, env-only credentials, until T015 passes
- [ ] T018 [US1] Add attribution-completeness guard in `teardown_attempt` + test case in `tests/test_usage_activities.py`: reject (raise, don't write) a `UsageRecord` with empty node/epic/persona/spec_ref (SC-003)

**Checkpoint**: MVP — attempts produce correct, attributed ledger rows on all paths

---

## Phase 4: User Story 2 — Rollups by persona/epic/spec-ref/attempt (Priority: P2)

**Goal**: answer "what did each persona / this requirement / retries cost?" via
ledger queries and the read-only `factory-usage` CLI.

**Independent Test** (spec US2): seed rows across two epics/three personas; assert
per-dimension aggregations, retry-ordinal view, unconfirmed flagging, and CLI `--json`
shape; prove CLI cannot write.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T019 [P] [US2] Write `tests/test_rollups.py`: seeded rows → rollups by persona (per-epic + global), by epic, by spec_ref across epics, by attempt ordinal (attempt ≥ 2 = retry cost), by node (attempts aggregated), grand totals; group with all-NULL cache metric reports None; `unconfirmed_rows` counts flagged rows (FR-006, SC-006)
- [ ] T020 [P] [US2] Write `tests/test_cli.py`: `--by` each dimension over a seeded tmp ledger; `--json` output matches `contracts/cli.md` shape exactly (incl. nulls, totals, filters echo); `--epic`/`--since` filters; exit codes 0/2/3; read-only proof — CLI runs against a read-only-mode connection and a mutation attempt via the CLI path raises (US2 scenario 4)

### Implementation for User Story 2

- [ ] T021 [US2] Implement rollup queries in `factory/usage/ledger.py` (`rollup(by=..., epic=None, since=None)` returning group metric dicts per the canonical SQL in `contracts/ledger-schema.sql`) until T019 passes
- [ ] T022 [US2] Implement `factory/usage/cli.py` (argparse, `mode=ro` URI open, table + `--json` renderers, exit codes) + wire `factory-usage` entry point in `pyproject.toml`, until T020 passes

**Checkpoint**: US1 + US2 independently green

---

## Phase 5: User Story 3 — Live usage visibility (Priority: P3)

**Goal**: heartbeat-cadence snapshots of a running attempt, observability-only.

**Independent Test** (spec US3): poll against the fake proxy mid-"run", assert
snapshot reflects proxy state and that no action of any kind is triggered at any
usage level.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T023 [P] [US3] Write `tests/test_poll_usage.py` (ActivityEnvironment): poll returns `UsageSnapshot` matching FakeLiteLLM state with `captured_at`; enormous spend values produce a snapshot and NOTHING else — no exception, no side-effect calls on the fake (assert request log contains only `/key/info`) (SC-005); poll failure raises but is documented-skippable (caller contract)

### Implementation for User Story 3

- [ ] T024 [US3] Implement `poll_usage` activity in `factory/activities/usage_activities.py` per `contracts/activities.md` until T023 passes; snapshot feeds `teardown_attempt`'s fallback input (already exercised by T015)

**Checkpoint**: all three stories independently functional

---

## Phase 6: Polish & Cross-Cutting

- [ ] T025 [P] Add `tests/test_live_proxy.py` with `@pytest.mark.live_proxy`: real-proxy smoke per quickstart §2 (issue uncapped key → one tiny completion via a cheap/local model → teardown → ledger row reconciles with proxy spend logs, SC-002); auto-skip when `LITELLM_PROXY_URL`/`LITELLM_MASTER_KEY` unset
- [ ] T026 [P] Update `docs/architecture.md` §5 target-shape note to "implemented" state and confirm module names match the shipped layout
- [ ] T027 Run full quickstart.md validation (§1 suite green; §3 CLI + sqlite3 schema inspection outputs match contracts) and fix any drift
- [ ] T028 Final sweep: grep tests assert no `LITELLM_MASTER_KEY` value appears in any persisted artifact or error path (SC-004); confirm no enforcement branch exists anywhere in `factory/usage/` (SC-005)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2 → (Phases 3, 4, 5) → Phase 6**
- Phase 2 blocks all stories (models, config, fake proxy, client, ledger schema)
- US2 (Phase 4) reads rows shaped by US1's writer but is testable with seeded rows —
  independent of Phase 3 completion
- US3 (Phase 5) depends only on Phase 2 (client + models)

### Within stories

- Test tasks strictly before their implementation tasks (constitution II)
- T016 ∥ T017 start after T014/T015 exist and fail; T018 after T017
- T021 after T019; T022 after T020 and T021 (CLI calls rollups)

### Parallel Opportunities

- Phase 1: T002, T003, T004 in parallel after T001
- Phase 2: T006, T007, T008 in parallel; T010 ∥ T012 after T007/T008
- Stories 3/4/5 can proceed in parallel once Phase 2 is done
- Within stories: all [P]-marked test authoring in parallel

## Parallel Example: after Phase 2 checkpoint

```bash
# Three independent story tracks:
Track A (US1): T014, T015 → T016, T017, T018
Track B (US2): T019, T020 → T021, T022
Track C (US3): T023 → T024
```

## Implementation Strategy

**MVP first**: Phases 1–3 only → validate US1 independently (the attributed ledger is
the component's reason to exist) → then US2 (rollups/CLI), then US3 (live polling),
then Polish. Commit after each task or logical group; every checkpoint is a valid
stopping point.
