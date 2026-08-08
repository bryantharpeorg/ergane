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

## D-028 · The landing's outcome lives in workflow state; reconciliation is polling-only (decided)

2026-08-06, settling US1 of the merge-queue epic (spec `specs/003-merge-queue/`). Four
decisions landed together because they are one posture — GitHub's queue is the source of
truth, and the factory only reads it:

1. **No landing store.** A landing's history (`outcomes`, `enqueued_at`, `recovery_cycles`,
   PR identity) is workflow state on its `Landing`, read back through the workflow's query
   surface. Rationale: the poll already reads GitHub; a SQLite landing table would duplicate
   that read with its own consistency problem, and unlike the verification evidence store
   (§6.1) there is no evidence to preserve — the queue history is GitHub's, not ours. A
   store becomes worth it only if US3's preflight or a future operations UI needs offline
   facts, and that is a new requirement, not this one.
2. **`depends_on_merged` grammar extension (FR-009).** A node can now declare it waits for
   a sibling to *merge* (not merely pass) via a second dependency edge set, so verified-but-
   unlanded work never unlocks a dependent. The existing `depends_on` (pass-based) set stays
   valid; the two sets are checked for overlap, and cycles run through their union. Existing
   graphs without the new field parse unchanged.
3. **Polling-only outcome observation.** No webhook, no `check_suite` event subscription
   (the D-011 no-public-endpoint posture again). The poll/classify loop is a pure function
   of the PR's current state, so a late landing reconciles as `MERGED` rather than being
   re-read as closed or dequeued, and classification is replay-identical under Temporal
   (SC-001).
4. **`LandingConfig` knobs.** The operator's landing surface is one config field on
   `EpicInput`: `merge_method` (passed verbatim to `gh pr merge --auto --<method>`),
   `poll_interval_s`, `stall_after_s` (SC-002's bound), `max_recovery_cycles` (FR-006).
   None of these is a constant buried in the workflow.

The interpreter's landing phase, the classifier, and the four landing activities are
exercised under time skipping and against a `FakeGh`; a `@pytest.mark.live_merge` smoke
drives one real branch through the sample repo's queue behind `FACTORY_SAMPLE_REPO` so a
broken queue assumption surfaces at run time, not at 3am.

## D-029 · Usage observation rides the agent heartbeat; visibility moves to the CLI (decided)

Decided 2026-08-06/07 (Bryan), recorded at landing per 006's T001. The interpreter's
per-30s `wait_condition` timeout + `poll_usage` loop cost ~11 history events per
interval (~1,320/hour/attempt) to keep a spend figure whose only consumer was the
teardown fallback. The trade was whether to keep any figure between polls at all.

1. **The heartbeat carries observation.** The adapter's monitor loop already beats
   every second for liveness; it gains a bounded usage read on the old `poll_interval_s`
   cadence and carries the newest `UsageSnapshot` as heartbeat *details* — mutable
   server state, zero history events. A failed read leaves the previous snapshot and
   never kills the beat: liveness and spend share a channel, and spend must not be able
   to kill liveness.
2. **Three delivery paths to teardown, each tested for a non-NULL spend.** Normal
   completion on `AdapterResult.last_snapshot`; timeout via
   `TimeoutError.last_heartbeat_details` off the caught `ActivityError`; kill by
   **return-on-cancel** (operator decision 2026-08-06, superseding the plan's first
   draft): the adapter catches cancellation and *returns* a KILLED `AdapterResult`
   carrying the snapshot, because reading heartbeat details off a cancelled activity's
   error is unverified in the installed SDK. A NULL spend row now means "never
   measured", a strictly stronger claim than the polling loop could make.
3. **Mid-attempt visibility moves to the CLI (decided 2026-08-07, after the judge
   failed a green-gated attempt on exactly this).** Deleting the poll deleted the only
   mid-attempt spend surface; the replacement must not reintroduce history events, and
   the workflow cannot read its own activity's heartbeat (`workflow.info()` has no
   pending-activity accessor in the installed SDK). `factory-epic status` reads
   `describe()`'s pending-activity heartbeat details — a client-side RPC, no history
   event — and renders live spend as a sibling of the query document, never merged
   into it.

## D-030 · The fan-out cap is `max_concurrent_nodes` on `EpicInput`, supplied at `factory-epic start` (decided)

Decided 2026-08-07 (Bryan), recorded at epic 007's US5 landing. The scheduler
widens from one node at a time to N behind an operator-set cap, and two naming
questions had to be settled before the field landed.

1. **`max_concurrent_nodes`, not `max_workers`.** "Worker" already names the
   Temporal worker *process* — the host process that polls a task queue and runs
   activities — so a `max_workers` knob would collide with that established
   meaning and read as "how many worker processes." The thing being bounded is
   the count of in-flight `_run_node` tasks inside one workflow execution, which
   are nodes of the work graph, so the name says what it counts. The cap sits
   above the worker process, not beside it: one worker runs N concurrent node
   tasks through the SDK's deterministic event loop.
2. **On `EpicInput`, not in `factory.yaml`.** `factory.yaml` is a property of the
   *target repo* — its runtime image, its gates, its standards file — and the
   number of agents a host can carry is a property of the *host*, not of the repo
   being built. Putting host capacity in `factory.yaml` would make the same repo
   dispatch differently from two hosts, and would couple a deployment fact to a
   file the target repo owns. `EpicInput` is the epic's dispatch argument, supplied
   per `factory-epic start`, so the operator who knows the host sets the cap when
   they start the epic — and an epic moved to a bigger host is restarted with a
   bigger cap, not re-derived.

The cap defaults to `1`, which is what makes fan-out opt-in (SC-002): an epic that
does not name the flag runs exactly as the sequential loop did, and the existing
suite is green against the default. It is validated in the CLI (positive integer;
`0` and negatives rejected, never coerced) and again in the workflow, because
`EpicInput` can be constructed without the CLI. The fleet-visibility story (US5)
is a consequence, not a separate mechanism: `epic_status` was already a per-node
document, so the renderer's only widening was attributing each pending
`run_agent_attempt`'s heartbeat to the node its `activity_id` names rather than to
"the" running node — the cap is what makes several of those pending at once.

## D-031 · 009 supersedes D-002's "one workflow" — the roadmap scheduler is the factory's second workflow type (decided)

Decided 2026-08-07 (Bryan), recorded at epic 009's US3 landing. D-002 named a
single generic WorkGraph interpreter the factory's one workflow; 009 adds the
roadmap scheduler, so the factory now has two workflow types and D-002's "one"
no longer holds. The decision to record is the supersession itself, and the
two naming questions it settles.

1. **D-002 is superseded on the count, not the architecture.** The epic remains
   the unit of work and `EpicWorkflow` remains the generic interpreter D-002
   specified — `RoadmapWorkflow` dispatches dispatchable specs *as* child
   `EpicWorkflow` runs, ABANDON on parent close (SC-004), so the roadmap is a
   scheduler one level above the interpreter, not a replacement for it. D-002's
   "one generic WorkGraph interpreter" is still true of the epic; what changed is
   that it is no longer the only workflow type. The worker registers both names
   (`WORKFLOWS = [EpicWorkflow, RoadmapWorkflow]`) because Temporal dispatches by
   name over the one queue.
2. **The bound is `max_concurrent_epics`, not `max_workers` or `max_requests`.**
   "Worker" names the Temporal worker *process* (D-030's precedent one level
   down), so a `max_workers` knob collides with that meaning. "Request" is the
   D-021 trap — children are *dispatches*/*children*, never *requests* — and the
   knob never branches on `cost` or `tokens`. The thing bounded is the count of
   in-flight child epics, so the name says what it counts. It defaults to `1`
   (fan-out is opt-in), is validated in the workflow (a positive integer; `0`,
   negatives, and bools rejected, never coerced), and rides the carry-over across
   continue-as-new.

Continue-as-new (FR-007) fires at quiescence — zero children open, after a child
concluded this run — carrying the run's state in an explicit `RoadmapCarryOver`
input (landed, parked, promotions, paused, the bound). The boundary is safe only
at that moment: no completion event can be lost across it because no child is in
flight, and the new run restores the carry-over and re-reads everything else —
which is what makes "a restart re-reads the world and does not double-dispatch"
true for free. The operator surface (FR-008) models the epic's one level up:
`pause_roadmap` parks dispatch between epics (the in-flight child finishes),
`resume_roadmap` releases it, `promote_spec` treats a named draft as ready on the
next pass (the file remains the authority of record; the signal covers the gap
until its next edit), and `roadmap_status` reports every spec's state, the
running child, parked findings, the pause flag, attested-vs-observed landings
(`landed_kind`/`satisfied_as`, FR-003's two kinds), and the bound in force.
Terminating the roadmap never terminates a child in flight (`parent_close_policy`
ABANDON, SC-004) — the child survives and finishes under its own contract.

## D-032 · The operator-question channel: a free-text sibling to the button escalation (decided)

Decided 2026-08-06 (Bryan), recorded at epic 008's US2 landing. Escalations
(§9) are button presses — a small fixed enum (`RETRY`/`KILL`/`PAUSE_EPIC`)
that cannot carry free text. When an agent's final message ends in a
`## OPERATOR QUESTION` marker it is asking something a button cannot answer,
so a **sibling channel** carries the question out and the free-text reply back.
The two were the two live shapes: send the question as a Telegram message and
answer into the *next* attempt's prompt (v0 — US1+US2), or keep the asking
attempt alive and ferry the answer back into the same process (v1 — US3).

1. **v0 first; v1 explicitly deferred behind it.** The bridge, the expiry
   semantics, and the retry-feedback prompt slot all exist, so v0 is nearly pure
   reuse; the ferry adds adapter machinery whose value depends on how often
   questions actually occur — a frequency nobody has measured yet, one live
   occurrence in. A fresh dispatch carrying the answer recovers everything
   except warm process context, and warm context is worth paying for only if
   questions turn out to be common. US3 is the optional v1 optimization,
   sequenced behind 006-US1's monitor-loop changes so the two features edit the
   adapter's loop sequentially.
2. **A sibling `questions` table, not the `escalations` table.** The
   escalations `resolution` is CHECK-pinned to `RETRY`/`KILL`/`PAUSE_EPIC`/
   `EXPIRED`; a free-text answer has nowhere to live in a pinned enum, which is
   the whole reason the sibling table exists. The two channels share the
   bridge's discipline (row-before-send, signal-before-resolve, expire as the
   backstop) and never touch each other's table.
3. **Routing by message id, never by recency (FR-008).** A free-text reply threads
   back to the question by the Telegram `reply_to_message_id` the send returned,
   not to the most recent open question. With two questions open, recency would
   route a reply to the wrong one regardless of the thread; the message id is
   the one fact about a question that can only be known after Telegram accepts
   it, and it is the reply-routing key.

The answer reaches the next attempt verbatim under a dedicated `## Operator
answer` prompt section, distinct from the `## Prior attempt evidence` the marker
rode in on, and an answered question costs **no ladder slot**: the QUESTION
attempt breaks the ladder loop before appending to `record.history`, so
`_attempts_spent` excludes it — the next attempt is the same attempt number,
now carrying the answer. An unanswered question expires (default 8h) and is
reclassified as a burned FAIL that *does* consume a slot, so the node un-parks
and the epic finishes without operator action (SC-003).

## D-033 · One hole in FR-012 — the QUESTION marker parks, never grades (decided)

Decided 2026-08-07 (Bryan), recorded at epic 008's US2 landing (FR-010). D-018
keeps `AdapterResult` narrow and FR-012 forbids any agent-reported signal from
reaching node state — the rule that stops an agent from grading itself, and the
reason `transcript_path` is documented as "evidence, never an input to a
decision." A question marker read out of the agent's final message **is** an
agent-authored signal reaching state, and this decision does not pretend
otherwise: it amends the rule with the narrowest possible hole rather than
routing around it.

1. **Exactly one signal exists, with exactly one effect.** The `## OPERATOR
   QUESTION` marker is the one agent-authored signal that may reach node state,
   and its only possible effect is to park the node `WAITING_OPERATOR` and page
   the operator. It can never produce, influence, or substitute for a verdict:
   gates and judge are not consulted for a QUESTION attempt because there is
   nothing to grade, and a marker on an attempt that *also* claims completion
   changes nothing about how that completion is judged.
2. **The distinction that keeps the rule's purpose intact.** FR-012 exists to
   stop agents from awarding themselves outcomes, and "I cannot proceed without
   the operator" awards nothing — it is the one statement whose truth the
   speaker is the sole authority on. The hole is scoped to that statement and
   nothing wider: park-only, never a verdict.

See spec 008 § "Decision: one hole in FR-012" for the surfaced reasoning; this
entry claims the D-number at landing, as 008's spec said it would ("this spec
claims two entries at landing: the channel itself, and the FR-012 amendment").

## D-034 · The roadmap reconciles instead of ignoring: delta derivation supersedes hand-authored remainder graphs (decided)

Decided 2026-08-08, recorded at epic 016-delta-derivation US4 landing. The
007 and 009 splits were continued by hand-trimming remainder `workgraph.json`
files (2026-08-07), twice violating D-025's rule that a workgraph is never
hand-authored. US2's `derive_delta` already computed the remainder from git
facts and pinned fingerprints; US4 closes the loop by making the roadmap use it
universally. The decision to record is the supersession itself.

1. **Hand-trimmed remainder graphs are retired from the runbook.** The two
   2026-08-07 remainder files remain banked as fixtures (`tests/fixtures/remainders/`,
   commit `8d57b86`) so SC-002 can replay them as ground truth, but no operator
   step ever trims a remainder again. The roadmap and the `factory-epic` CLI both
   derive through the same delta path; a re-readied partially-landed spec
   dispatches its computed remainder, and an amended landed spec dispatches only
   its delta.

2. **Attribution is a two-ended contract.** The landing squash subject is
   rendered by `factory.mergequeue.messages.pr_title` as
   `<epic_id>/<node_id>: <story title>`; GitHub appends `(#<pr>)`, and
   `factory.workgraph.landed._LANDING_RE` parses the same shape. The renderer
   and the reader are the two ends of one contract — a change to either side
   must change both, and the regex anchors on `epic_id` so commits from other
   epics do not leak into a spec's baseline.

3. **No store and no new dependency.** Landed facts, pinned fingerprints, and
   deltas are computed from git and the corpus on demand, every time. Drift is
   a read-only signal (`amended`) rendered by `compute_readiness`; the workflow
   reads it through the `drift_for_spec` activity because workflow code never
   shells git (constitution IV). The existing `DeriveInput` already carried
   `target_repo`, so `derive_spec` needed no new argument — only a new baseline
   read inside the activity.

---

## D-035 · Detection is durable, remediation is work: the factory-doctor ledger (decided)

Decided 2026-08-07 (Bryan), recorded at epic 015-factory-doctor landing. The
2026-08-07 audit produced 27 findings on a review page that scrolls out of
memory; the doctor gives them a durable home and a mechanical path into the
factory's own build order. The decision is the five calls from spec 015 §
"Decision: detection is durable, remediation is work".

1. **The ledger is the durable home of triage.** Findings live in
   `.factory/doctor.db` with identity, recurrence, and status, not in chat
   artifacts or runbook memory.

2. **The doctor is CLI verbs, not a workflow type.** A scheduled `check` may
   arrive later, but the core surface (`report`, `list`, `resolve`, `check`,
   `promote`) needs no long-lived process to be useful.

3. **Probes detect; they never remediate.** An orphaned key is deleted by an
   operator or by an epic the finding becomes — a diagnostic tool that mutates
   the system under diagnosis becomes a disease. This is enforced structurally:
   the `factory/doctor/` package imports no key-revocation, worktree-removal,
   or process-control surfaces.

4. **Promotion writes `draft` and stops.** The deriver guarantees the scaffold's
   structure before anything is renamed into place; a human owns the prose and
   the readiness flip. The loop closes through the roadmap grammar: a promoted
   finding whose spec attests `state: landed` resolves automatically on the
   next doctor invocation, and a re-report afterward files as `regressed`.

5. **Severity and status are closed sets; category is open.** Recurrence
   arithmetic and exit codes compute over severity and status, so they are
   grammar. Categories are open taxonomy; refusing a new taxonomy word would
   make the ledger resist exactly the findings it exists to collect.
