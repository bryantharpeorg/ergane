# Ergane — Agentic Software Factory

Ergane turns OpenSpec change proposals into merged, verified code by dispatching headless
coding agents through a Temporal-orchestrated DAG, with hard per-node budgets, mechanical
acceptance-criteria verification, and GitHub's native merge queue for landing.

This document describes the target architecture. The decision log with rationale is in
[decisions.md](decisions.md). Build order is strict: **budgets → verification → merge**
(D-017). No components exist in code yet: each is specified first under `specs/`
(GitHub Spec Kit, D-020) — [001-per-node-budgets](../specs/001-per-node-budgets/spec.md),
[002-verification-gating](../specs/002-verification-gating/spec.md),
[003-merge-queue](../specs/003-merge-queue/spec.md).

## 1. System overview

```mermaid
flowchart TB
    subgraph intent [Intent layer — OpenSpec]
        OS["openspec/changes/&lt;name&gt;/<br/>proposal.md · tasks.md · design.md<br/>specs/&lt;cap&gt;/spec.md (delta)"]
        WG["workgraph.json<br/>(DAG: nodes + edges)"]
        OS --> WG
    end

    subgraph temporal [Temporal — namespace 'factory']
        INT["WorkGraph interpreter workflow<br/>(one per epic, generic)"]
        NQ[[task queue 'workgraph']]
        INT --- NQ
    end

    subgraph worker [Worker host]
        BM["budget middleware<br/>(key lease / poll / teardown)"]
        AA["agent activity<br/>(adapter: Claude Code, ...)"]
        VF["verifier activity<br/>(gates + judge)"]
        WT[("git worktree<br/>per node")]
        BM --> AA --> WT
        WT --> VF
    end

    subgraph llm [LiteLLM proxy (deployed)]
        VK["virtual key per node<br/>max_budget · metadata.node_id"]
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
{PASSED → PR_OPEN → ENQUEUED → MERGED} | {FAILED → retry/escalate} | {BUDGET_BREACH →
per-persona policy}`. Every terminal state tears down the key and writes the ledger.

## 2. Intent layer: OpenSpec (vanilla)

The system of record is a stock OpenSpec workspace (D-001). The factory consumes:

- `openspec/changes/<name>/specs/<capability>/spec.md` — **delta specs**, the source of
  acceptance criteria.
- `tasks.md` / `design.md` — context handed to agent prompts.
- Later: a forked schema adds `workgraph.json` making tasks + design required.

Criteria parsing is mechanical (no LLM). Grammar the parser keys on:

| token | meaning |
|---|---|
| `## ADDED\|MODIFIED\|REMOVED\|RENAMED Requirements` | delta operation bucket (level-2, case-insensitive) |
| `### Requirement: <name>` | requirement; trimmed header text is the identity key; body MUST contain `SHALL` or `MUST` |
| `#### Scenario: <desc>` | one acceptance criterion; body captured to next same/higher header |
| `- **GIVEN\|WHEN\|THEN\|AND** ...` | scenario steps |
| `- FROM:`/`- TO:` backticked headers | RENAMED mapping |

Headers match `/^(#{1,6})\s+(.+)$/` with code fences masked. `openspec change show <id>
--json` provides the same as structured JSON (Zod-validated upstream) if markdown parsing
ever gets brittle.

## 3. Orchestration: the WorkGraph interpreter

One **generic** Temporal workflow interprets a JSON DAG per epic (D-002). No codegen:
the workflow's logic is fixed; graph *data* varies. This keeps Temporal replay
deterministic and sidesteps per-epic versioning.

A node carries: `id`, `persona`, `spec_ref` (change + capability + requirement),
`acceptance` (parsed scenarios), `budget_usd` (optional override of the persona default),
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
  budget_usd: 5.00
  breach_policy: escalate       # escalate | hard-kill
  needs_worktree: true
```

Six personas ship in v1: `architect`, `implementer`, `verifier`, `judge`, `debugger`,
`researcher` (full table in D-012). Model names are **placeholders the operator edits** —
code never hardcodes a model, and `models` on the issued key constrains what the agent can
actually call, making the persona's model binding enforceable, not advisory.

## 5. Component 1 — per-node budgets (spec: `specs/001-per-node-budgets/`)

First in build order. Target shape: package `factory/budgets/` + Temporal activity
surface in `factory/activities/budget_activities.py`.

### 5.1 Key lifecycle (middleware around every agent node)

```
issue_node_key ─▶ [agent runs, polling spend on heartbeat] ─▶ teardown_node_key
     │                                                              │
     └─ POST /key/generate                                          └─ GET /key/info (final spend)
        max_budget, duration,                                          POST /key/delete
        key_alias="epic:node",                                         append ledger entry
        metadata={node_id,epic_id,persona},
        models=[persona's allowed]
```

- The generated key is handed to the agent as its API credential
  (`ANTHROPIC_BASE_URL=<proxy>`, auth = virtual key) — already the operator's proven daily
  setup (D-014).
- `LITELLM_MASTER_KEY` is read from env **inside activities only**; it never enters
  workflow state, payloads, or logs.
- Teardown is idempotent and runs on every terminal state (pass, fail, breach, kill).

### 5.2 Spend polling & soft warn

The agent activity heartbeats ~every 30s; each heartbeat may call `check_node_spend`
(`GET /key/info` → `spend`, `max_budget`). At ≥80% a single soft-warn fires (Telegram,
once per node). No proxy-side alerting is configured (D-016).

### 5.3 Breach detection & policy

LiteLLM enforces the hard floor itself: past `max_budget`, requests fail with HTTP 400
`ExceededTokenBudget` (surfaced as an auth-style error, not 429). The wrapper:

1. detects breach markers in agent output / final spend snapshot,
2. classifies termination: `COMPLETED | AGENT_ERROR | BUDGET_BREACH | TIMEOUT | KILLED`
   — breach and error take different escalation paths,
3. SIGTERM (30s grace) → SIGKILL,
4. **salvages always**: commits the worktree to the node branch (no work is ever lost),
5. applies the persona's policy (D-015): `hard-kill` → node fails, notify;
   `escalate` → Telegram **[Bump +50% & resume] [Reroute cheaper] [Kill]**, each a
   Temporal signal; bump uses `POST /key/update`; 1h no-response → kill.

### 5.4 Ledger

Append-only JSONL, one entry per node teardown: `{epic_id, node_id, persona, key_alias,
max_budget_usd, final_spend_usd, termination, issued_at, torn_down_at}`. Queryable
per-epic totals. LiteLLM's `LiteLLM_SpendLogs` table (keyed by `metadata.node_id`) holds
per-request detail when forensics are needed.

### 5.5 Uniform dollars

All budgets are USD (D-013). Local models get synthetic `input_cost_per_token` /
`output_cost_per_token` registered in the proxy `model_list`; without that they'd report
$0 and never trip a budget.

## 6. Component 2 — verification gating (NEXT)

Two-tier, inner-loop, pre-CI (D-008, D-019):

1. **Deterministic gates** — `test` / `lint` / `typecheck` commands from the target repo's
   committed `factory.yaml` (D-009), exit-code semantics, run in the node's sandbox.
2. **LLM judge** — `judge` persona (cheap tier, own budget key, read-only), scoring the
   diff against the parsed `#### Scenario:` criteria. Bounded: truncated diff input,
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
workflow. Used by: budget breach (§5.3), verify-fail-after-retries (§6), merge
conflict/red (§7). Built alongside component 2; until then, escalations log + fail safe
(kill path).

## 10. Security notes

- Master key: worker-host env only; activities redact it from errors; never in Temporal
  payloads (D-014).
- Per-node virtual keys are least-privilege: model-constrained, budget-capped, TTL'd
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
- **OpenSpec**: parser grammar and Zod schemas from `Fission-AI/OpenSpec` source
  (`change-parser.ts`, `markdown-parser.ts`, `base.schema.ts`); `--json` CLI output.
- **Bernstein** (`chernistry/bernstein`): narrow adapter with process-only outputs;
  two-tier verify (deterministic signals + bounded opt-in judge, cap 2, verbatim
  feedback); anti-rubber-stamp diff attribution; worktree-per-task with graveyard refs;
  plan-then-apply merges; LLM out of the coordination loop.
