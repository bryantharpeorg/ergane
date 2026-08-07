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
[002-verification-gating](../specs/002-verification-gating/spec.md) (**implemented**,
§6 and §9),
[005-workgraph-interpreter](../specs/005-workgraph-interpreter/spec.md)
(**implemented**, §3 and §8),
[003-merge-queue](../specs/003-merge-queue/spec.md), plus the deferred
[004-budget-enforcement](../specs/004-budget-enforcement/spec.md). The merge
component (§7) does not exist in code yet — it is the first epic the factory
dispatches against itself (D-024).

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
        VF["verifier activities<br/>(gates + output check + judge)"]
        WT[("git worktree<br/>per node")]
        FDB[(".factory/<br/>ledger.db · verification.db")]
        BM --> AA --> WT
        WT --> VF
        BM --> FDB
        VF --> FDB
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

    TG["Telegram notifier<br/>send activity + callback bridge<br/>(inline-button approvals → signals)"]

    WG --> INT
    NQ --> BM
    AA -- "ANTHROPIC_BASE_URL + virtual key" --> VK
    VF -- pass --> PR
    INT <--> TG
    TG <--> FDB
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

## 3. Orchestration: the WorkGraph interpreter (spec: `specs/005-workgraph-interpreter/`)

**Implemented** as the bootstrap kernel's third component (D-024). One **generic**
Temporal workflow — `EpicWorkflow`, namespace `factory`, task queue `workgraph` —
interprets a JSON DAG per epic (D-002). No codegen: the workflow's logic is fixed;
graph *data* varies. This keeps Temporal replay deterministic and sidesteps per-epic
versioning.

Layout, all under the single `factory` package (D-004):

| module | role |
|---|---|
| `factory/workgraph/models.py` | `WorkGraph` / `WorkNode` / `NodeState` / `EpicState` / `AttemptContext` / `AdapterResult`, plus pure start-time graph validation |
| `factory/workgraph/derive.py` | pure: epic spec text → `WorkGraph` via the `## Work Graph` section (D-025) |
| `factory/workgraph/prompt.py` | pure two-loop attempt-prompt assembly (inner ralph contract advisory, outer 002 ladder authoritative) |
| `factory/workgraph/worktree.py` | one worktree per node: ensure / salvage / remove / diff |
| `factory/workgraph/adapter.py` | the D-018 seam — `AgentAdapter` + `ClaudeCodeAdapter` (§8) |
| `factory/workgraph/workflow.py` | `EpicWorkflow`: the interpreter itself, pure decisions only |
| `factory/workgraph/cli.py` | `factory-epic derive \| start \| status` (§3.2) |
| `factory/activities/agent_activities.py` | `resolve_graph` / `resolve_persona` / `prepare_worktree` / `run_agent_attempt` / `read_worktree_diff` / `salvage_worktree` / `remove_worktree` |
| `factory/worker.py` | runnable `python -m factory.worker` — registers `EpicWorkflow` plus all three components' activities |

A node carries: `id`, `persona`, `spec_ref` (feature + requirement keys — also
the work-attribution key for usage tracking), `requirement_keys` (the acceptance
criteria 002 snapshots), `depends_on` edges, and an optional `timeout` override.
The graph is validated in full before anything dispatches — duplicate ids, dangling
edges, cycles, unresolvable personas, and producing nodes whose persona resolves no
timeout are all start-time rejections.

**Scheduling is sequential.** The interpreter walks ready nodes in declaration order
and runs them one at a time; a node is ready only when every dependency reports
`PASSED`. Parallel node execution, verifier nodes, and multi-epic scheduling are
deferred — the bootstrap runs single-digit node counts, and sequencing keeps
workflow history small and the one-epic-at-a-time `.factory/` SQLite constraint
honest.

Per node: `PENDING → KEY_ISSUED → RUNNING → VERIFYING → PASSED | FAILED`, with
`KILLED` reachable from any non-terminal state. Every attempt is bracketed by
component 1's key lifecycle (§5.1) and routed by component 2's ladder (§6) — retry,
debugger, escalate — with the agent's own self-report never touching node state
(the adapter yields process outcome and termination class only). When the gates and
the output check are green and the node's criteria carry acceptance scenarios, the
judge is consulted inside a key lifecycle of its own, minted for the `judge` persona
(resolved once at epic start, since no node names it) and constrained to that
persona's aliases — so scoring is spend attributed to the scorer. Worktree salvage
runs on every termination path before cleanup (principle VI). Epic states are
`RUNNING ⇄ PAUSED`, `→ KILLED`, `→ COMPLETED` (every node terminal — which does not
imply every node passed; the run's result carries the per-node outcomes).

**Signals and query.** `pause_epic` stops new dispatch while the in-flight node
finishes its full ladder; `resume_epic` continues; `kill_epic` cancels the in-flight
attempt, salvages, tears down keys, and marks every non-terminal node `KILLED`. The
notifier's `escalation_resolved` signal (§9) carries a human's answer back into the
ladder — a `PAUSE_EPIC` resolution parks the node `FAILED` and pauses the epic. The
`epic_status` query answers with the epic state plus per-node status keyed in
declaration order, so reading it top to bottom reads the epic in the order it was
authored to run.

**Transcript archiving.** Every attempt's evidence lands under
`.factory/transcripts/<epic>/<node>/attempt-<n>/` — the agent's `stdout.log` and its
session transcript, archived on every path including timeout and kill. Transcripts
live on the worker host beside the ledger; they are never written into a target
repo's worktree and never committed. The adapter's pid/pgid handles live alongside
under `.factory/run/`, so a crashed worker's orphaned process group is reaped before
the next attempt relaunches.

All side effects live in activities. Workflow code makes pure decisions over graph state —
the plan-then-apply split (decide in workflow, mutate in activity) mirrors Bernstein's
`dry_run_merge → should_attempt_merge → build_merge_command` pattern and is what Temporal's
sandbox wants anyway. The workflow reads worktree diffs, spec text, and usage through
activities; it parses nothing itself.

### 3.1 The graph is compiled from the spec (D-025)

`workgraph.json` is never hand-authored. The epic's spec carries an additive
`## Work Graph` section — a fenced YAML block declaring, per user story,
`depends_on`, `implements`, and an optional `timeout`:

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-009]
US2:
  depends_on: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
```

Derivation is pure and cross-validated against the same criteria parser the verifier
uses (§2): one node per story, id = lowercased story key, `requirement_keys` = the
story key plus its `implements` FRs. A story with no declaration, a declaration for
a story the spec lacks, an unknown FR, an unknown or self-referential dependency, a
cycle, or a malformed block each fail by name and emit nothing. The Spec Kit
templates under `.specify/templates/` are **not** forked — the convention is
enforced by validation, which keeps the operator on the upstream upgrade path.

### 3.2 Operator surface: `factory-epic`

- `derive <spec-dir>` — compile the spec's `## Work Graph` into `workgraph.json`
  next to the spec (or `-o`); on failure print every collected error and write
  nothing.
- `start <workgraph.json>` — start the epic as workflow id `epic-<epic_id>`, which
  is what makes a run findable without anyone writing down a run id; Temporal's id
  uniqueness *is* the one-epic-at-a-time rule.
- `status <epic-id>` — the `epic_status` query plus the execution's Temporal
  status, human-readable or `--json`. Because a query against a *closed* workflow
  still succeeds and returns its final internal state, the internal `epic_state`
  alone could read `RUNNING` for an execution Temporal has already `FAILED` — so
  the CLI reads the execution status from `describe()` and reports it alongside
  the internal state (FR-010): the epic line carries both, and `--json` adds it
  as a sibling `execution_status` key beside the query's document, never merged
  into it, so no `--json` consumer breaks. The execution status is the ground
  truth; the internal state is what the epic had in memory when the run last
  advanced.

`TEMPORAL_ADDRESS` / `TEMPORAL_NAMESPACE` are honored throughout. Temporal's Web UI
remains the dashboard for anything deeper.

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
  timeout: 14400                # attempt wall-clock bound, seconds (D-025)
  # budget_usd / breach_policy attributes return with deferred spec 004
```

Six personas ship in v1: `architect`, `implementer`, `verifier`, `judge`, `debugger`,
`researcher` (full table in D-012). Model names are **placeholders the operator edits** —
code never hardcodes a model, and `models` on the issued key constrains what the agent can
actually call, making the persona's model binding enforceable, not advisory.

`timeout` (D-025) is the same shape of operator-owned default: a positive integer of
seconds bounding one agent attempt, optional on agent-backed personas and forbidden
on deterministic (`agent: none`) ones, exactly as `model` is. A node's
`## Work Graph` override wins when declared; otherwise the registry answers. Code
hardcodes no fallback — a producing node whose persona resolves no timeout fails
graph validation at epic start rather than silently inheriting a constant.

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

## 6. Component 2 — verification gating (spec: `specs/002-verification-gating/`)

Two-tier, inner-loop, pre-CI (D-008, D-019). **Implemented** — the shipped layout is:

```text
factory/
├── verify/
│   ├── models.py          # enums + frozen records (CriteriaSet … EscalationRecord), compose_result
│   ├── criteria.py        # pure: mechanical Spec Kit spec parser (fence masking, §2 grammar)
│   ├── factory_yaml.py    # pure: factory.yaml schema v1 load/validate → CONFIG_ERROR
│   ├── gates.py           # gate runner: bash -c in the worktree, timeouts, scrubbed env
│   ├── diffcheck.py       # anti-rubber-stamp: worktree diff / expected artifacts
│   ├── judge.py           # pure prompt assembly + truncation + strict verdict parse, proxy call
│   ├── ladder.py          # pure: next_action(history, config) retry-ladder decisions
│   └── store.py           # SQLite evidence store: schema, upserts, escalation lifecycle
├── notify/                # Telegram notifier — §9
└── activities/
    └── verify_activities.py  # snapshot_criteria / run_gates / check_output / run_judge / record_verification
```

The pipeline, cheapest signal first:

1. **Criteria snapshot** — `snapshot_criteria` parses the dispatch-time `spec.md` (§2
   grammar) down to the node's requested requirement keys and hashes the raw bytes.
   Verification scores against that snapshot; a later edit to the spec surfaces as a
   `criteria_drift` flag on the evidence row, never as moved goalposts (FR-010).
2. **Deterministic gates** — `test` / `lint` / `typecheck` commands from the target repo's
   committed `factory.yaml` (D-009), exit-code semantics, run in the node's worktree in
   declaration order: per-gate timeout (default 600s, SIGTERM then SIGKILL), 32 KiB output
   tail retained as evidence, environment scrubbed so no proxy or bot credential is visible
   to the command. A missing or malformed manifest is a single `CONFIG_ERROR` result —
   never a pass by default.
3. **Anti-rubber-stamp** — a write-scope node with an empty worktree diff fails regardless
   of gates; a read-scope node must instead produce every declared artifact, non-empty.
4. **LLM judge** — `judge` persona (cheap tier, own attribution key, read-only), scoring the
   diff strictly per scenario against the parsed acceptance criteria. Bounded: diff
   truncated to 60 KiB with explicit markers (criteria never truncated), response capped at
   2000 tokens, **max 2 judge retries**; on `retry` verdict the judge's feedback is
   handed **verbatim** to the retry attempt (Bernstein's highest-value pattern). Skipped
   entirely when a gate already failed — a two-second lint failure costs no completion.
5. **Composed verdict, recorded first** — any failing gate, a failed output check, or a
   judge `retry`/`fail` makes the attempt FAIL; an unreachable judge behind green gates
   passes with `judge_unavailable` recorded rather than fabricated. The row is written
   before any routing decision, and downstream DAG edges unlock only on `PASSED` (FR-005).
6. **Fail → ladder** — `ladder.next_action(history, config)` is a pure function of the
   recorded attempts: retry-with-feedback within `max_attempts` (default 3, with the 2
   judge retries bounded *inside* that total), then the `debugger` persona once, then
   Telegram escalation (§9). Escalation `RETRY` grants exactly one further attempt;
   `KILL`, `PAUSE_EPIC`, and the 1h timeout end the node.

### 6.1 Evidence store (SQLite)

`.factory/verification.db` (stdlib `sqlite3`, WAL + busy timeout, `schema_version` 1) —
the same single-designated-host topology as the 001 ledger, path overridable with
`FACTORY_VERIFICATION_DB_PATH`. Two tables:

- `verification_results` — one row per attempt per form, upserted on
  `(epic_id, node_id, attempt, form)` so a redelivered activity lands on the first run's
  row instead of duplicating evidence: verdict, gate results / output check / judge verdict
  as JSON evidence bundles, `judge_unavailable` and `criteria_drift` flags, criteria hash,
  spec ref, timestamps. `judge_verdict` is NULL when the judge never ran — a different fact
  from a judge that ran and returned FAIL.
- `escalations` — one row per operator decision, written *before* the message is sent and
  making exactly one terminal transition (a button resolution *xor* the timeout `EXPIRED`)
  under a guarded UPDATE, because the press and the workflow's timer race by design.

Evidence round-trips as the frozen records it was written from, because the retry prompt
quotes gate `output_tail` and judge feedback verbatim and the escalation message carries
the full failure history. The DDL is documented in
`specs/002-verification-gating/contracts/verification-store.sql`; direct SQL against the
store is a supported read surface, deliberately query-friendly for a future operations UI.

The judge never runs in CI — merge-queue checks are deterministic only, so requeues and
batch bisection never multiply judge spend. The production loop that drives the ladder
ships as the documented pattern in
`specs/002-verification-gating/contracts/verification-flow.md` (exercised by a test-only
reference workflow under time skipping); the WorkGraph interpreter owns running it.

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

No public webhook — the notifier ships (with component 2) as a **pair**: an activity that
sends, and a separate long-polling process that brings the answer back as a signal.

```text
factory/
├── notify/
│   ├── messages.py            # pure: escalation text + inline keyboard + callback_data
│   └── service.py             # runnable bridge: long-poll → store → Temporal signal
└── activities/
    └── notify_activities.py   # send_escalation / expire_escalation
```

- **Send activity** — `send_escalation` inserts the escalation row *before* it sends, so a
  crash in between leaves an expirable row rather than an untracked message, and reports
  delivery as data: a missing `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` or a failed send
  yields `delivered=false`, and the workflow applies the fail-safe kill immediately instead
  of waiting out the hour. `expire_escalation` makes the timeout transition and reports
  whichever terminal state the store actually holds. The bot token is read from the worker
  environment inside the activity only — never in inputs, results, rows, or logs (001's
  master-key discipline, extended per D-022).
- **Callback bridge** — `python -m factory.notify.service`, one long-polling process per
  deployment (`TELEGRAM_BOT_TOKEN`, `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`,
  `FACTORY_VERIFICATION_DB_PATH`), stateless across restarts because every fact it needs is
  in the escalation row. A press is parsed (`callback_data` = `esc:<12-hex>:<choice>`,
  within Telegram's 64-byte limit), looked up, validated against the choices that row
  actually offered, **signalled** to the waiting workflow as
  `escalation_resolved(escalation_id, choice)`, and only then resolved in the store and
  answered. Signal-before-resolve is deliberate: a row marked resolved on a signal that
  never landed strands the workflow for the full hour, whereas a pending row can simply be
  pressed again. Presses that lose the race with expiry, or arrive on an unknown or
  already-resolved id, are answered with a notice and change nothing.
- **Messages** — pure rendering: the full failure history across attempts plus one inline
  button per offered choice (`RETRY` / `KILL` / `PAUSE_EPIC`).

Escalations expire after 1h and **default to kill** — but only after salvage (principle VI),
which the node-lifecycle owner performs. Used by: verify-fail-after-retries (§6), and merge
conflict/red (§7) once component 3 lands.

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
