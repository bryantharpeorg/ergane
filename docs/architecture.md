# Ergane — Agentic Software Factory

Ergane turns Spec Kit feature specs into merged, verified code by dispatching headless
coding agents through a Temporal-orchestrated DAG, with per-node usage attribution,
mechanical acceptance-criteria verification, and GitHub's native merge queue for landing.

This document describes the target architecture. The decision log with rationale is in
[decisions.md](decisions.md). Build order is strict: **usage tracking → verification →
minimal interpreter (005) → merge, built by the factory itself** (D-017 as amended by
D-024), with component 1 pivoted from budget enforcement to usage tracking (D-021).
Each component is specified first under `specs/` (GitHub Spec Kit, D-020) —
[001-usage-tracking](../specs/001-usage-tracking/spec.md) (**implemented**, §5),
[002-verification-gating](../specs/002-verification-gating/spec.md),
[003-merge-queue](../specs/003-merge-queue/spec.md), plus the deferred
[004-budget-enforcement](../specs/004-budget-enforcement/spec.md). Components 2 and 3
do not exist in code yet.

## 1. System overview

```mermaid
flowchart TB
    subgraph intent [Intent layer — Spec Kit]
        OS["specs/&lt;feature&gt;/<br/>spec.md · plan.md · tasks.md"]
        WG["workgraph.json<br/>(DAG: nodes + edges)"]
        OS --> WG
    end

    subgraph temporal [Temporal — namespace 'factory']
        INT["WorkGraph interpreter workflow<br/>(one per epic, generic)"]
        NQ[[task queue 'workgraph']]
        INT --- NQ
    end

    subgraph worker [Worker host]
        BM["usage middleware<br/>(key lease / poll / teardown)"]
        AA["agent activity<br/>(adapter: Claude Code, ...)"]
        VF["verifier activity<br/>(gates + judge)"]
        WT[("git worktree<br/>per node")]
        BM --> AA --> WT
        WT --> VF
    end

    subgraph llm [LiteLLM proxy (deployed)]
        VK["virtual key per node<br/>no cap · metadata.node_id"]
        MODELS["vLLM (DGX Spark) · Ollama Cloud · Anthropic"]
        VK --> MODELS
    end

    subgraph gh [GitHub]
        PR["PR per node branch"]
        MQ["native merge queue<br/>(rebase + required checks)"]
        PR --> MQ
    end

    TG["Telegram notifier<br/>(inline-button approvals → signals)"]

    WG --> INT
    NQ --> BM
    AA -- "ANTHROPIC_BASE_URL + virtual key" --> VK
    VF -- pass --> PR
    INT <--> TG
```

**Node lifecycle:** `PENDING → (deps met) → KEY_ISSUED → RUNNING → VERIFYING →
{PASSED → PR_OPEN → ENQUEUED → MERGED} | {FAILED → retry/escalate}`. Every terminal
state tears down the key and writes the usage ledger. (A `BUDGET_BREACH` state joins
the lifecycle only if deferred spec 004 is reactivated.)

## 2. Intent layer: Spec Kit feature specs (D-023)

The system of record is the target repo's `specs/` directory of Spec Kit feature specs
(D-023 — the intent-layer *role* of D-001 survives; the grammar is now Spec Kit,
superseding vanilla OpenSpec deltas). The factory consumes:

- `specs/<feature>/spec.md` — **feature specs**, the source of acceptance criteria.
- `specs/<feature>/plan.md` / `tasks.md` — context handed to agent prompts.
- Later: an optional `workgraph.json` making the DAG explicit.

Criteria parsing is mechanical (no LLM). Grammar the parser keys on (the Spec Kit
template):

| token | meaning |
|---|---|
| `### User Story <n> - <title> (Priority: P<m>)` | story requirement (level-3); key = `US<n>`; title and priority captured |
| `**Acceptance Scenarios**:` | introduces the story's numbered scenario list |
| `<k>. **Given** … **When** … **Then** …` | one acceptance criterion; scenario id `US<n>-S<k>`; the bold **Given/When/Then/And** segments are the steps, captured verbatim in order |
| `- **FR-###**: <body>` | functional requirement (bullets under `### Functional Requirements`); key = `FR-###`; body must contain `MUST` or `SHALL` |

Headers match `/^(#{1,6})\s+(.+)$/` with code fences masked. Validation errors name the
exact offender: a user story with zero acceptance scenarios, an FR without MUST/SHALL, a
scenario item with no bold keyword steps, duplicate requirement keys, or a requested
requirement key absent from the spec. Spec Kit has no CLI/JSON emitter — the markdown
parser is the sole mechanical path — and Ergane's own `specs/` corpus doubles as
real-world fixture material (D-024).

## 3. Orchestration: the WorkGraph interpreter

One **generic** Temporal workflow interprets a JSON DAG per epic (D-002). No codegen:
the workflow's logic is fixed; graph *data* varies. This keeps Temporal replay
deterministic and sidesteps per-epic versioning.

A node carries: `id`, `persona`, `spec_ref` (feature + requirement keys — also
the work-attribution key for usage tracking), `acceptance` (parsed scenarios), and
`depends_on` edges. The interpreter releases a node when all its dependency edges report
`PASSED`, runs it through the pipeline in §5–§7, and signals/awaits Telegram on
escalations.

All side effects live in activities. Workflow code makes pure decisions over graph state —
the plan-then-apply split (decide in workflow, mutate in activity) mirrors Bernstein's
`dry_run_merge → should_attempt_merge → build_merge_command` pattern and is what Temporal's
sandbox wants anyway.

## 4. Personas (`personas.yaml`)

Routing is persona-first (D-012). A node names a persona; the registry resolves everything
else:

```yaml
implementer:
  agent: claude-code            # adapter name, D-018
  model: anthropic/CHANGEME     # operator's real LiteLLM alias
  fallback: local/CHANGEME
  skills: [implement, tdd]
  write_scope: worktree         # worktree | docs | read
  needs_worktree: true
  # budget_usd / breach_policy attributes return with deferred spec 004
```

Six personas ship in v1: `architect`, `implementer`, `verifier`, `judge`, `debugger`,
`researcher` (full table in D-012). Model names are **placeholders the operator edits** —
code never hardcodes a model, and `models` on the issued key constrains what the agent can
actually call, making the persona's model binding enforceable, not advisory.

## 5. Component 1 — per-node usage tracking (spec: `specs/001-usage-tracking/`)

First in build order. Pivoted by D-021 from budget *enforcement* to usage *attribution*:
track every token and dollar per node attempt, enforce nothing. **Implemented** — the
shipped layout is:

```text
factory/
├── config.py                    # persona registry loader/validation (personas.yaml)
├── usage/
│   ├── models.py                # KeyLease, UsageSnapshot, AggregatedUsage, UsageRecord, Termination
│   ├── litellm_client.py        # async admin client: /key/generate|info|delete, spend logs
│   ├── aggregate.py             # pure: spend-log rows -> AggregatedUsage (cache handling)
│   ├── ledger.py                # SQLite ledger: schema bootstrap, upsert, rollup queries
│   └── cli.py                   # read-only `factory-usage` CLI (argparse, --json)
└── activities/
    └── usage_activities.py      # issue_attempt_key / poll_usage / teardown_attempt
```

Env inputs: `LITELLM_PROXY_URL` + `LITELLM_MASTER_KEY` (activities only),
`FACTORY_LEDGER_PATH` (ledger location, shared by the activities and the CLI).

### 5.1 Key lifecycle (attribution middleware around every agent node attempt)

```
issue_attempt_key ─▶ [agent runs, poll_usage on heartbeat] ─▶ teardown_attempt
     │                                                            │
     └─ POST /key/generate                                        └─ read final usage + spend logs
        NO max_budget, duration=TTL,                                 write ledger row
        key_alias="epic:node:attempt",                               POST /key/delete LAST
        metadata={node_id,epic_id,attempt,persona,spec_ref},
        models=[persona's allowed]
```

- The per-node virtual key exists purely so spend is **attributable without agent
  cooperation** — it is handed to the agent as its API credential
  (`ANTHROPIC_BASE_URL=<proxy>`, auth = virtual key), the operator's proven daily setup.
- `metadata.spec_ref` ties the key — and therefore every token spent on it — to the
  piece of work (Spec Kit feature + requirement keys) the node was dispatched for.
- `LITELLM_MASTER_KEY` is read from env **inside activities only**; it never enters
  workflow state, payloads, or logs.
- Teardown is idempotent and runs on every terminal state (pass, fail, kill, timeout).

### 5.2 Usage polling (observability only)

The agent activity heartbeats ~every 30s and snapshots current usage (`GET /key/info`).
Snapshots are retained as latest-known state — the teardown fallback when the final
read fails — and power live inspection. **No threshold triggers anything** (D-021):
no warnings, no kills. No proxy-side config changes (D-016).

### 5.3 Ledger (SQLite)

One row per attempt teardown in a SQLite database (stdlib `sqlite3`, WAL mode,
concurrent-writer safe; clarified 2026-07-24): epic, node, attempt, persona, spec ref,
key alias, **input / output / cache-read / cache-write tokens**, request count, USD
where the model is priced, termination class (`COMPLETED | AGENT_ERROR | TIMEOUT |
KILLED`), issue/teardown timestamps, and a `final_usage_confirmed` flag (last-known
snapshot is recorded when the proxy is unreadable — never a fabricated zero; unknown
metrics stay NULL). Token detail is aggregated from the proxy's per-request spend logs
for the key, not agent self-reporting. Teardown upserts on `key_alias`, so re-running it
never duplicates a row.

Rollups (`factory.usage.ledger.rollup`, surfaced by the read-only `factory-usage` CLI
with `--by`, `--epic`, `--since`, `--json`): by **persona**, **epic**, **spec-ref**
across epics, **attempt** ordinal (attempt ≥ 2 is retry cost), and **node** (attempts
aggregated) — each with grand totals and an `unconfirmed_rows` count. The DDL is
documented in `specs/001-usage-tracking/contracts/ledger-schema.sql`; direct SQL against
the ledger is a supported read surface.

### 5.4 Dollars are optional, tokens are not

Token counts are recorded for every model. USD appears where the proxy prices the
model (Anthropic out of the box); registering synthetic pricing for local vLLM/Ollama
models is optional operator setup under tracking-only — it becomes mandatory only if
budget enforcement (spec 004) is reactivated.

### 5.5 Deferred: budget enforcement (spec `specs/004-budget-enforcement/`)

The fully-designed enforcement layer — per-persona caps, `BUDGET_BREACH`
classification, soft-warn at 80%, salvage-always kill, and the Telegram
bump/reroute/kill escalation — is parked in spec 004 with a reactivation checklist.
It layers onto this component's key lifecycle without restructuring.

## 6. Component 2 — verification gating (NEXT)

Two-tier, inner-loop, pre-CI (D-008, D-019):

1. **Deterministic gates** — `test` / `lint` / `typecheck` commands from the target repo's
   committed `factory.yaml` (D-009), exit-code semantics, run in the node's sandbox.
2. **LLM judge** — `judge` persona (cheap tier, own attribution key, read-only), scoring the
   diff against the parsed acceptance scenarios. Bounded: truncated diff input,
   capped response, **max 2 judge retries**; on `retry` verdict the judge's feedback is
   handed **verbatim** to the retry attempt (Bernstein's highest-value pattern).
3. **Anti-rubber-stamp**: a non-no-op node with an empty diff fails regardless of gates.
4. Fail → retry-with-feedback loop (bounded) → `debugger` persona → Telegram escalation.
5. Downstream DAG edges unlock only on `PASSED`.

The judge never runs in CI — merge-queue checks are deterministic only, so requeues and
batch bisection never multiply judge spend.

## 7. Component 3 — merge (LAST)

GitHub-native (D-007): branch-per-node → PR on verify-pass → `gh pr merge --auto` →
GitHub's merge queue serializes, rebases onto the current queue head
(`gh-readonly-queue/...`), re-runs **deterministic required checks** against the rebased
tree, merges on green. Temporal enqueues, awaits the outcome, and on conflict/red routes
to `debugger` or escalates. Unmerged work from failed/killed nodes is preserved on its
branch (salvage, §5.3) rather than deleted.

## 8. Agents: the adapter seam

Per D-018 and Bernstein's `CLIAdapter`: the adapter's only job is **launch, monitor,
terminate, classify termination**. Inputs: prompt, worktree path, env (proxy URL + virtual
key + model), session id. Output: exit classification + log path. Everything semantic is
read elsewhere — the **diff from the worktree**, **usage from the ledger**. That keeps
Claude Code swappable for pi.dev/OpenCode by writing a new adapter, nothing else.

## 9. Escalation: Telegram notifier

One long-polling service (no public webhook): sends escalation messages with inline
buttons; button `callback_query` → `answerCallbackQuery` → Temporal signal to the waiting
workflow. Used by: verify-fail-after-retries (§6), merge
conflict/red (§7). Built alongside component 2; until then, escalations log + fail safe
(kill path).

## 10. Security notes

- Master key: worker-host env only; activities redact it from errors; never in Temporal
  payloads (D-014).
- Per-node virtual keys are least-privilege: model-constrained, TTL'd
  (`duration`) as a backstop against teardown failures, deleted on teardown.
- Agents run in sandboxed containers with one isolated worktree; write scope is a persona
  attribute.
- Target repos are public (D-007/D-010) — nothing secret may be committed to them, and the
  factory repo's own config must not leak proxy URLs/keys into target-repo commits.

## 11. Research this design leans on

- **LiteLLM**: `/key/generate|info|update|delete`, breach = HTTP 400 `ExceededTokenBudget`
  (hard block), `soft_budget` alerts-only, cost computed only for priced models — synthetic
  pricing required for vLLM/Ollama. (docs.litellm.ai: virtual_keys, users, cost_tracking,
  custom_pricing)
- **OpenSpec** (historical): parser grammar and Zod schemas from `Fission-AI/OpenSpec`
  source (`change-parser.ts`, `markdown-parser.ts`, `base.schema.ts`). Superseded as
  the input grammar by Spec Kit (D-023); the fence-masked header-scan technique
  carries over.
- **Bernstein** (`chernistry/bernstein`): narrow adapter with process-only outputs;
  two-tier verify (deterministic signals + bounded opt-in judge, cap 2, verbatim
  feedback); anti-rubber-stamp diff attribution; worktree-per-task with graveyard refs;
  plan-then-apply merges; LLM out of the coordination loop.
