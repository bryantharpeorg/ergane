# Quickstart: Minimal WorkGraph Interpreter

Validation guide — every command runs from the repo root. Contracts referenced:
[workgraph-schema](contracts/workgraph-schema.md), [adapter](contracts/adapter.md),
[workflow](contracts/workflow.md), [prompt-assembly](contracts/prompt-assembly.md),
[cli](contracts/cli.md); entities in [data-model.md](data-model.md).

## 1. Full suite (no external services)

```bash
uv run pytest -q
```

Expected: green. Everything through the interpreter runs on fakes — the adapter
against `tests/stub_agent.py`, the workflow under
`WorkflowEnvironment.start_time_skipping()` with scripted activity fakes, worktrees
against `tmp_path` git repos. Live markers (`live_proxy`, `live_telegram`,
`live_epic`) auto-skip without their env vars.

## 2. Derive a WorkGraph from a fixture spec

```bash
uv run factory-epic derive tests/fixtures/workgraph/valid_epic \
    --target-repo /tmp/anywhere -o /tmp/workgraph.json
cat /tmp/workgraph.json
```

Expected: one node per user story, `depends_on` edges and `requirement_keys`
exactly as the fixture's `## Work Graph` block declares (SC-006). Then prove the
loud-failure half — each of these prints the offending story and writes nothing
(exit 1):

```bash
uv run factory-epic derive tests/fixtures/workgraph/missing_story --target-repo /tmp/x
uv run factory-epic derive tests/fixtures/workgraph/unknown_fr    --target-repo /tmp/x
uv run factory-epic derive tests/fixtures/workgraph/cycle         --target-repo /tmp/x
```

Deriving Ergane's own 005 spec (this directory gains no `## Work Graph`; 003's
spec does, as the crossover prerequisite) is the real-world check once 003's
declaration lands:

```bash
uv run factory-epic derive specs/003-merge-queue --target-repo <clone-path>
```

## 3. Interpreter behavior under time skipping

```bash
uv run pytest -q tests/test_interpreter.py
```

What the suite proves (US1/US3 independent tests): the scripted 3-node graph
(chain + independent leaf) completes with exact transition, unlock, and attempt
scripts (SC-001); zero dispatches with unmet dependencies on every path including
failure and kill (SC-002); RETRY re-dispatches with evidence in the prompt;
ESCALATE → KILL terminates with salvage ordering intact; `pause_epic` blocks
dispatch while the in-flight node finishes; replay after simulated worker restart
double-dispatches nothing (US1-S4); every attempt has its issue/teardown +
verification pair (SC-003) and terminal salvage commit + transcript (SC-004).

## 4. Live Tier 1 smoke (optional, env-gated)

Prerequisites: LiteLLM proxy + Postgres, Temporal dev server
(`temporal server start-dev --db-filename .temporal/dev.db`), Telegram bot,
`claude` CLI on this host; `personas.yaml` aliases set to real proxy aliases.

```bash
export LITELLM_PROXY_URL=... LITELLM_MASTER_KEY=...          # activities only
export TEMPORAL_ADDRESS=localhost:7233 TEMPORAL_NAMESPACE=factory
python -m factory.worker &                                    # workflow + all activities, queue `workgraph`
python -m factory.notify.service &                            # escalation bridge (optional for the smoke)
uv run pytest -q -m live_epic                                 # one-node epic against a scratch target repo
```

Expected: `factory-epic start` prints `epic-<id>`; `factory-epic status <id>`
tracks PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED; the scratch repo gains
a `factory/<epic>/us1` branch with real commits. This is the SC-005 rehearsal; the
003 crossover is the same commands pointed at `specs/003-merge-queue/`.

## 5. Inspect what an epic left behind

```bash
uv run factory-usage --by node --epic <epic-id>               # 001 ledger: every attempt's spend
sqlite3 .factory/verification.db \
  "SELECT node_id, attempt, verdict FROM verification_results WHERE epic_id='<epic-id>' ORDER BY node_id, attempt;"
ls .factory/transcripts/<epic-id>/                            # FR-007: per-attempt archives
git -C <target-repo> branch --list 'factory/<epic-id>/*'      # FR-013: one branch per node, salvage commits on each
```

Expected: the three records agree attempt-for-attempt — no attempt exists that the
ledger, the evidence store, and the transcript directory don't all know about
(SC-003, SC-004).
