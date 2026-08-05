# Decision Log

Format: one entry per decision, newest last. Entries are immutable — supersede, don't edit.
Status: `given` = pre-decided constraint from the project brief; `decided` = settled in the design interview (2026-07-24).

---

## D-001 · Intent layer: OpenSpec, vanilla grammar (given + decided)

OpenSpec is the system of record for intent. We will eventually fork its schema to add a
`workgraph.json` artifact that requires tasks + design, but **v1 parses vanilla OpenSpec** —
the user runs stock OpenSpec today, no customizations. Criteria parsing is fully mechanical
(no LLM): the parser keys on `## ADDED|MODIFIED|REMOVED|RENAMED Requirements` →
`### Requirement: <name>` (body must contain `SHALL`/`MUST`) → `#### Scenario: <desc>` →
`- **GIVEN|WHEN|THEN|AND**` bullets. `openspec change show <id> --json` is available as a
structured alternative.

## D-002 · Orchestration: Temporal, one generic WorkGraph interpreter (given)

Self-hosted Temporal. A single generic interpreter workflow executes a JSON DAG per epic.
Nodes carry spec refs, acceptance criteria, persona, budget, and dependency edges. No
codegen'd workflows — the interpreter reads graph data, keeping us on the right side of
Temporal determinism/versioning.

## D-003 · SDK language: Python (decided)

Interpreter, activities, criteria parser, and judge are Python. Rationale: the work is
overwhelmingly LLM-glue and text parsing; Temporal's Python SDK has a determinism-enforcing
workflow sandbox; activities shell out to `claude`/`git` anyway so worker performance is
not a differentiator. Alternatives considered: Go (best-tested SDK, worse LLM ergonomics),
TypeScript (one JS toolchain, weaker LLM tooling).

## D-004 · Repo layout: single Python monorepo, one `factory` package (decided)

This repo (`ergane`) **is the factory**. Layout: a single importable package `factory/`
with subpackages `workgraph/`, `activities/`, `budgets/`, `verify/`, `mergequeue/`,
`worker/`; plus `docs/`, `tests/`, and `personas.yaml` at the root. (The interview specced
flat top-level dirs; they live under one package so imports are `factory.budgets` rather
than a top-level `budgets` squatting on generic names.)

## D-005 · Package manager: uv (decided)

`uv` with a committed lockfile. Approved dependencies for component 1: `temporalio`,
`httpx`, `pyyaml`; dev: `pytest` (+ `pytest-asyncio` as part of the pytest stack for async
tests). Any further dependency requires explicit approval first.

## D-006 · Temporal deployment: local dev server, durable (decided)

Local: `temporal server start-dev --db-filename .temporal/dev.db` (SQLite persistence —
default start-dev is in-memory, a footgun). Namespace `factory`, task queue `workgraph`.
Docker-compose (server + postgres + UI) reserved for a later prod deployment.

## D-007 · Git host + merge mechanics: GitHub native merge queue (decided)

GitHub is the source-control and merge system. Target repos are **public**, which makes
GitHub's native merge queue available on any plan. Flow: on inner-loop pass, open PR →
`gh pr merge --auto` to enqueue → GitHub serializes, rebases (`gh-readonly-queue/...`),
re-runs required checks against the rebased tree, merges on green. Temporal's merge role
shrinks to: enqueue → await outcome → escalate (or route to `debugger`) on conflict/red.
Supersedes the earlier lean toward a custom Temporal-driven queue; a custom queue is only
revisited if a private-repo-on-Free target ever appears.

## D-008 · Judge placement: inner loop, pre-CI (decided)

The LLM-as-judge is part of the agent's inner verification loop, running in our sandbox
**before** any PR exists — alongside the deterministic gates (test/lint/typecheck).
Merge-queue required checks are **deterministic only**. Consequence: judge cost is bounded
to inner-loop attempts and never multiplied by merge-queue requeues/batch-bisection.

## D-009 · CI discovery: committed `factory.yaml` per target repo (decided)

Each target repo declares `runtime` (container image) and explicit `test` / `lint` /
`typecheck` commands in a committed `factory.yaml`. Deterministic beats auto-detection for
verifier gates.

## D-010 · First target: separate sample repo, never the factory itself (decided)

First E2E target is a separate, trivial, public sample coding repo (created when we reach
E2E; needs adding to session GitHub scope then). `ergane` stores the factory and stays out
of its own blast radius — no dogfooding until the loop is stable.

## D-011 · Escalation surface: Telegram with inline-button approvals (decided)

A single lightweight notifier service (long-polling, so no public webhook needed) sends
escalations as Telegram messages with `InlineKeyboardButton`s (`callback_data` e.g.
`bump:node-42`). Button presses arrive as `callback_query` updates and are translated into
Temporal signals that unblock the waiting node. Temporal Web UI is the operational
dashboard for now; a custom dashboard is deferred. Note: LiteLLM's native alerting speaks
Slack/webhook only — Telegram traffic always flows through our notifier.
(`python-telegram-bot` will be proposed as a dependency when the notifier is built —
not part of component 1.)

## D-012 · Routing: persona-first, model is an attribute (decided)

Nodes carry a `persona`, not a model tier. A registry (`personas.yaml`) resolves each
persona to `{agent, model, fallback, skill, permission scope, budget default, breach
policy, needs_worktree}`. `model_tier` survives only as a derived hint for cost-aware
fallback. Catalog v1 — six personas:

| persona | role | backing skill(s) | write scope |
|---|---|---|---|
| `architect` | design.md, interfaces, domain model | codebase-design, design-an-interface, domain-modeling | docs only |
| `implementer` | code from spec delta + tasks | implement, tdd | full worktree |
| `verifier` | run deterministic gates, parse criteria | none (deterministic) | read + run |
| `judge` | LLM-as-judge vs acceptance criteria | code-review | read-only |
| `debugger` | diagnose verify failures, drive retry | diagnosing-bugs | full worktree |
| `researcher` | gather docs/context | research, grill-with-docs | read + web |

"Reviewer" is folded into `judge`; no `spec-author` persona yet (specs are human-authored).
Model names in `personas.yaml` are placeholders the operator edits to their real LiteLLM
aliases — code never hardcodes a model.

## D-013 · Budget denomination: uniform dollars (decided)

All budgets are USD. LiteLLM only computes `spend` for priced models — Anthropic is priced
out of the box; local vLLM/Ollama report $0 unless priced. Therefore synthetic
`input_cost_per_token` / `output_cost_per_token` are registered in the proxy's
`model_list` for every local model, so one `max_budget` per key enforces uniformly.
Budget defaults live on the persona; overridable per node at dispatch.

## D-014 · Key lifecycle: one LiteLLM virtual key per node (given + decided)

Dispatch → `POST /key/generate` with `max_budget`, `key_alias = "<epic>:<node>"`,
`metadata = {node_id, epic_id, persona}`, `models` = persona's allowed models, `duration`
as a TTL backstop. Spend read via `GET /key/info`. Teardown → `POST /key/delete` +
ledger write. The LiteLLM **master key** is provided by the operator, lives only in the
worker host's env (`LITELLM_MASTER_KEY`), is read only inside activities, and never
appears in workflow state, activity payloads, or logs (Temporal persists those).
Validated assumption: the operator already routes Claude Code through this LiteLLM proxy
to Ollama and Anthropic in daily use (`ANTHROPIC_BASE_URL` + virtual key).

## D-015 · Breach policy: soft-warn 80% / salvage-always / per-persona kill-or-escalate (decided)

- **Soft-warn** (all personas): activity polls `/key/info` on its heartbeat (~30s); at 80%
  of `max_budget`, one Telegram warning; node continues.
- **Hard floor** (LiteLLM-enforced): at 100%, the proxy 400-blocks further spend
  (`ExceededTokenBudget`). The wrapper detects this in agent output, classifies the
  termination `BUDGET_BREACH` (distinct from `AGENT_ERROR`), SIGTERMs with 30s grace, and
  **always salvages** — commits whatever exists in the worktree to the node branch so no
  work is lost (Bernstein graveyard pattern).
- **Then per-persona policy:** `hard-kill` (verifier, judge, researcher — cheap work):
  node fails, notify only. `escalate` (implementer, debugger, architect — expensive work):
  Telegram buttons **[Bump +50% & resume] [Reroute cheaper] [Kill]** → Temporal signal;
  bump = `POST /key/update` with raised `max_budget`, resume in the same worktree.
  No response within 1h → kill (worktree already salvaged).

## D-016 · Budget alerts: poll, don't reconfigure the proxy (decided)

v1 relies purely on spend-polling via `/key/info`. No changes to the already-deployed
LiteLLM proxy's `general_settings` (webhook/Slack alerting) — fewer moving parts.
Proxy-side alerting may be revisited later.

## D-017 · Build order (given)

1. **Per-node budgets** — key issuance/teardown as Temporal activity middleware, breach
   policy, ledger. 2. **Verification gating** — verifier node type, criteria parser, judge
   rubric, retry-with-feedback, escalation. 3. **Merge queue** — last, most
   environment-dependent. Small vertical slices; every component gets tests before moving on.

## D-018 · Agent adapter: narrow, swappable, Bernstein-informed (given + decided)

Activity wrapper is agent-agnostic: inputs `(prompt, worktree, model config via env,
session id)`; immediate output is process outcome + termination classification only.
The **diff is read from the worktree** and **usage from the LiteLLM ledger** — never from
the adapter — so Claude Code can be swapped for pi.dev/OpenCode without touching
orchestration. Termination classes are a shared enum; exit-code/stream parsing is
per-adapter. One isolated git worktree per node; sandboxed containers.

## D-019 · Verification shape (for component 2; direction settled in interview)

Two-tier, per Bernstein: always-on deterministic gates first (exit-code-based, from
`factory.yaml`), bounded LLM judge second (verbatim retry feedback, hard retry cap,
cheap-tier model via `judge` persona). Anti-rubber-stamp: a non-no-op node whose diff is
empty fails verification regardless of gate output. Downstream edges unlock only on pass.

## D-020 · Factory development is spec-first via GitHub Spec Kit (decided)

The factory's own development uses GitHub Spec Kit: constitution in
`.specify/memory/constitution.md`, one spec per build-order component under
`specs/###-component-name/` (spec → plan → tasks → implement). The component-1
implementation scaffolded during the design session was reverted in favor of specs —
no implementation code exists until its spec's plan/tasks are approved. This does
**not** touch D-001: OpenSpec remains the runtime intent layer the factory consumes;
Spec Kit governs how the factory itself gets built.

## D-021 · Component 1 pivots to usage tracking; budget enforcement deferred (decided)

Supersedes the enforcement scope of D-013/D-015/D-016 (their design is preserved, not
discarded). The operator wants spend **tracked, not enforced**: per-node token detail
(input, output, cache read, cache write), rolled up by persona and epic, and
attributable to a piece of work (the node's OpenSpec requirement ref). Component 1 is
now `specs/001-usage-tracking/` — per-node virtual keys survive as the attribution
primitive but are minted **without** `max_budget`; polling is observability-only; the
SQLite ledger records token breakdowns and USD-when-priced. Caps, breach policy
(soft-warn / hard-kill / escalate), and the bump/reroute/kill escalation flow are
parked fully-designed in `specs/004-budget-enforcement/` (Status: Deferred,
unscheduled) with a reactivation checklist. Synthetic local-model pricing (D-013)
becomes optional until enforcement is reactivated. Constitution amended accordingly
(v2.0.0).

## D-022 · `python-telegram-bot` approved for the notifier (decided)

Approved during spec 002 clarification (2026-07-24) per constitution III. The Telegram
notifier (long-polling, inline-button escalations → Temporal signals, built with
component 2) uses `python-telegram-bot` rather than a hand-rolled Bot API client on
`httpx`. Constitution roster updated (v2.1.0).

## D-023 · Input grammar: Spec Kit feature specs replace OpenSpec deltas (decided)

Supersedes D-001's choice of intent format (the intent-layer *role* survives; the
grammar changes). The factory consumes Spec Kit feature specs
(`specs/<feature>/spec.md`) instead of vanilla OpenSpec change deltas. Rationale:
the factory's own development already speaks Spec Kit (D-020); one grammar for both
the factory and its targets removes a format boundary, and — decisive for D-024 —
makes Ergane's own `specs/` backlog directly parseable as factory input. The parser
keys on the Spec Kit template grammar (user stories with priorities, numbered
**Given/When/Then** acceptance scenarios, `FR-###` functional requirements); there
is no upstream CLI/JSON emitter, so the in-factory markdown parser is the sole
mechanical path, and Ergane's own specs double as real-world fixtures. Blast
radius: 002 US1 (parser, fixture corpus, `DeltaOperation`/rename machinery
removed), architecture §2, judge rubric's REMOVED-by-absence rule. Everything
downstream of the `CriteriaSet` normalization seam is untouched.

## D-024 · Self-hosting: Ergane builds itself after a minimal bootstrap (decided)

The end goal is stated: after a small hand-built kernel, Ergane is its own factory.
The bootstrap kernel — 001 usage tracking, 002 verification gating (amended per
D-023), and a minimal 005 WorkGraph interpreter — is built by a ralph loop (fresh
headless session per task, tasks.md checkboxes + git as the only durable state),
which is the hand-cranked prototype of the node loop the factory industrializes.
First self-hosted epic: `specs/003-merge-queue/`, dispatched by the factory against
this repository, with the human operator acting as the merge queue until 003 itself
lands. Crossover milestone: a verified 003 branch with zero human-written code.
Supersedes the "factory never operates on its own repository" constraint and the
D-017 build order: (1) 001 ✅ → (2) 002 → (3) minimal 005 → (4) 003 via the factory.
Constitution amended (v2.2.0).

## D-025 · The DAG is compiled from the spec: `## Work Graph`, plus two config fields (decided)

Settled during spec 005 clarification. Three additive surfaces, no forks and no new
dependencies.

**`## Work Graph` — an additive grammar extension, not a template fork.** D-002's
`workgraph.json` is never hand-authored and never inferred: the epic's own spec
carries an optional `## Work Graph` section whose first fenced YAML block declares,
per user story, `depends_on` (story ids), `implements` (FR keys), and an optional
`timeout` override. `factory-epic derive` compiles that section into
`workgraph.json` — one node per story (D-023's granularity), node id = lowercased
story key, `requirement_keys` = the story key plus its `implements` FRs, edges from
`depends_on`. Derivation is a pure function (spec text in, `WorkGraph` out) and
cross-validates against the same `load_criteria` parser the verifier uses: every
story needs a declaration and vice versa, every `implements` key must be an FR the
spec declares, every `depends_on` must be a declared story, and the graph must be
acyclic — any violation names the offending story and emits nothing. Rationale:
dependency order between stories is authoring knowledge that only the spec's author
holds; it is *not* mechanically recoverable from prose, and guessing it is exactly
the LLM-in-the-orchestrator that principle IV forbids. Forking
`.specify/templates/` to add the section was explicitly refused — the operator stays
on the upstream Spec Kit upgrade path, and a spec missing the section fails
validation rather than the template enforcing it. The compiled artifact stays
inspectable and diffable next to the spec it came from; specs without the section
remain valid Spec Kit specs that simply cannot be dispatched yet.

**Persona `timeout` (`personas.yaml`).** An attempt's wall-clock bound is an
operator-editable registry value (principle VII), not a constant in code: an
optional positive integer of seconds, forbidden on `agent: none` personas the same
way `model` is. Resolution is persona-first at dispatch — a node's `## Work Graph`
override wins when declared, else the registry — and a producing node whose persona
resolves no timeout fails WorkGraph validation at epic start, before any key is
issued. Deliberately *not* resolved at derive time, which would bake registry values
into a compiled artifact that goes stale the moment the operator edits the registry.

**`factory.yaml` `standards` (schema stays v1).** A target repo may name one
committed standards document (Ergane's own points at
`.specify/memory/constitution.md`); prompt assembly then carries a read-and-obey
directive naming the path, and `prepare_worktree` fails the dispatch loudly if a
declared file is absent from the worktree. It lives in `factory.yaml` because
standards are a property of the *repo*, not of who works on it, and because a
committed file is adapter-agnostic — no reliance on `CLAUDE.md` auto-loading. The
path is referenced rather than inlined: the agent reads it in-worktree, and the
prompt never drifts from the document the gates see.

## D-026 · `key_alias` carries the persona; one judge key per scoring job (decided)

2026-08-05, from the operator-side review of ralph run 3. Component 1's alias
becomes `{epic}:{node}:{attempt}:{persona}` — persona is key *identity*, not
metadata. The defect was live-only: 005 mints the judge's key inside the
implementer's still-open bracket (the implementer's termination isn't known until
verification ends), LiteLLM refuses a duplicate alias while its key lives, and
the ledger upserts on the alias. A persona-blind alias therefore failed the mint
on every scored node — and had the ordering differed, the judge's teardown would
have silently overwritten the implementer's ledger row (SC-003 corrupted rather
than broken). Same decision, same unit: the judge's parse re-asks are retries of
one scoring job, so `_judge` mints one key for the whole job instead of one per
re-ask — one bracket, one ledger row per scoring. The interpreter suite's fake
proxy now enforces live-alias uniqueness so the guarantee is structural rather
than scripted; the ledger schema is unchanged (the alias is opaque TEXT).

## D-027 · "The attempt's work" is worktree-vs-base-ref, not worktree-vs-HEAD (decided)

2026-08-05, from the first live epic smoke. 002's R7 defined the diff the judge
scores — and the output check's "did the node do work" — as worktree-vs-HEAD,
deliberately: the design assumed the agent leaves its work uncommitted and the
salvage commit lands after verification. 005's FR-012 prompt then handed the
agent the inner ralph contract, which says commit as you go — and Claude Code
does. Live consequence: the committed implementation vanished from the judge's
diff (HEAD had moved with it), the only visible "work" was the gate run's
`__pycache__`, and the judge — correctly, on what it was shown — failed a node
whose gate was green. The same HEAD definition also let a fully-committed
attempt read as "no work" and let committed out-of-scope changes evade the
write-scope check. `worktree.diff` and `diffcheck.check_output` now take the
prepared worktree's `base_ref` (the node's branch point) and measure everything
since it: committed, staged and untracked alike. Ignored files still stay out —
a target repo's `.gitignore` is what keeps generated noise from the judge, and
the smoke's scratch repo now carries one like any real repo.
