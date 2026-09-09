# Codex-primary operator migration runbook

**Status:** implementation authorized; first three specs promoted
**Source date:** 2026-09-09
**Repository:** `/home/admin/code/ergane` at the source fingerprint recorded in the audit

## Purpose and authority boundary

This runbook turns the Codex-primary audit into an ordered, reversible migration.
The operator authorized execution on 2026-09-09. Each stage authorizes only the
normal actions needed to implement and qualify that stage; credential entry,
trust grants, and target-policy expansion still require their declared gates.
The roadmap remains paused while this sequence uses deliberate per-spec
dispatch. Specs 125, 154, 155, and 156 are landed records and are not rewritten
by this batch.

The operator promoted **157, 087, and 158** to `ready`, in dependency order; the
remaining six trios stay draft until their phase gates are reached. On
2026-09-09 the operator approved a separately created factory Codex login session and credential
directory, used through one host-global serialized credential-owner stream
across all local targets and deployment shapes. This is design approval; setup
and real account qualification have not been performed.

The operator then clarified the immediate target: Codex CLI for the operator,
and Codex CLI builders routed through the existing LiteLLM gateway to Ollama
Cloud. Builder declarations use `agent: codex`, `route: gateway`, and the
operator-selected `ollama-cloud/...` alias. Operator-session inference is
configured independently; this does not change the operator's provider.

The first three promotions are **157, 087, and 158**, in that dependency order.
157 now contains only the operator contract; its former
subscription governance story is preserved in the deferred proposal. 160's
gateway-relevant evidence work no longer depends on future credential ownership
in 159. Subscription setup (159/112), the private pilot, and subscription-specific
governance were initially deferred. The operator subsequently included the
automatic Codex subscription upper rung as the final implementation phase,
scoped to the deployment actually in use. Subscription-only onboarding in 112
and unused deployment layouts remain outside that phase. No private target or
GitHub plan change is required by the gateway migration; existing gateway
target eligibility continues to apply.

For later subscription use, the operator selected automatic ladder routing:
the configured upper-rung persona uses Codex with `route: subscription`, just
as the prior Claude upper rung used subscription auth. Configured ladder order,
attempt caps, and frozen persona routing govern the transition; no per-use
confirmation or new human escalation choice is required. A model-only fallback
does not change the route. The normal gateway builders and independent judge
retain their declared routing.

## The nine-trio change set

| Spec | Job | Depends on | Release hold |
| --- | --- | --- | --- |
| 157 | Canonical `AGENTS.md`, Claude compatibility, workflow/capability map | none | Fresh two-client discovery is implementation-completion evidence |
| 087 | One collision-safe operator-skill source with two client bindings | 157 | Do not install during specification work |
| 158 | Pure status/triage/metrics/render jobs selected by declared intent | 087, 157 | No live-state mutation during qualification |
| 159 | Authentic managed-account validation and one host-global durable credential owner | none | Owner design approved; real account use waits for governance and private-pilot qualification |
| 112 | `llm.mode = none`, honest readiness, split runner/route install | 159 | Must retain gateway judge and spec-125 Claude behavior |
| 160 | Current-attempt Codex JSONL evidence and neutral classification for both routes | none beyond landed adapter | Real event fixtures only after controlled qualification |
| 161 | Narrow deployed credential/toolchain path, private-queue eligibility, and confined real smoke proof | Current broad draft: 112, 159, 160; narrow before final-phase dispatch | Final phase uses the current deployment; target/governance proposal remains to reconcile |
| 139 | Target-context unit, protected-path checker, client hook bindings/trust evidence | 157 | Fresh-client trust/enforcement qualification |
| 162 | One away-mode owner, explicit monitor/action policy, client bindings | 157, 158, 161 | Stable supervised-pilot evidence and measured scheduling/notification bindings |

## Migration sequence

### Stage 0 — Preserve the baseline

- Record the effective target, landing branch, registry snapshot, engine image,
  Codex/Claude binary versions, runner, route, model, runtime root, and rollback
  values without changing them.
- Confirm all active attempts are quiescent before any later installed-skill,
  registry, image, or client-definition change.
- Retain Claude routes and the existing independent gateway judge as rollback
  choices. Do not interpret `agent` as the route; use the explicit/effective
  `route` field.

### Stage 1 — Establish the shared operator contract

Implement 157, then 087, then 158. Qualify canonical instruction and skill
discovery in fresh Codex and Claude root, nested-directory, and worktree
sessions. Reporting invocations must produce no tracked-file, runtime-store,
finding, ref, queue, or service mutation. Memory, scheduling, notification,
delegation, and publication gaps are reported as unavailable capabilities, not
papered over with invented tool names.

Implement 139 after the instruction boundary is stable. Its target-safety
context is not the operator contract. Installation may report a hook definition
written and trust required; only separately authorized real-client evidence can
report active enforcement. Official Codex guidance binds trust to the exact
non-managed hook definition and requires project trust
(https://learn.chatgpt.com/docs/hooks).

### Stage 2 — Qualify the existing Codex gateway path

The landed `CodexAdapter` and `_seed_codex_config` already select the existing
proxy as a custom Responses provider using the attempt's gateway key. Official
Codex configuration supports custom providers with a base URL and environment
key (https://learn.chatgpt.com/docs/config-file/config-advanced). This source
contract is not current deployed end-to-end evidence.

Implement 160 independently of 159 to harden current-attempt capture,
classification, and gateway usage attribution. Before a later builder switch,
qualify one opt-in Codex/gateway persona against the declared Ollama Cloud alias
through the actual pinned deployment: tool use, edit, gate, commit, judge,
archive, gateway ledger, cancellation, and normal queue landing. Keep the
selected model/route and judge explicit. Check generated home/config isolation
and actual toolchain/confinement; these deployment concerns apply to gateway
use before the subscription-specific final phase.

This is later cutover work. A failed gateway qualification should produce a
narrow implementation finding/spec rather than importing the private-account
pilot as a prerequisite. Do not infer successful streaming/tool calls from a
model-list or one-response probe.

### Stage 3 — Final phase: automatic Codex subscription upper rung

Implement 159's credential lifecycle. Use file-backed managed-account fixtures to prove
`auth_mode: chatgpt`, reject API-key and malformed shapes, choose one host-global
effective-rung owner across targets/deployments, stage narrowly, finalize
validated refresh state, and
publish only non-secret status. OpenAI describes managed ChatGPT automation as
an advanced trusted-private pattern and says the changed auth file must be
persisted after refresh (https://learn.chatgpt.com/docs/auth/ci-cd-auth).

Reuse 160's route-neutral JSONL decoder. Non-interactive Codex emits JSONL thread, turn,
item, error, and usage events; the archive and neutral message projection must
belong to the current invocation only
(https://learn.chatgpt.com/docs/non-interactive-mode).

#### Current-deployment qualification

Narrow the broad 161 trio and its 112 dependency before dispatch so this phase
qualifies the deployment actually in use. Full subscription-only onboarding and
additional host/container layouts are separate later scope. Qualify narrow
credential delivery, launch/mount confinement, process-group cleanup, and
current-attempt archival with synthetic children. A version command or stub is
insufficient even for those claims. Reconcile the existing private-pilot and
governance proposal for the chosen target before the real qualification; that
proposal is not a claim of CLI-enforced repository visibility. Synthetic
children are not Codex search/edit/gate/commit evidence.

#### Automatic ladder pilot and rollback decision

- Configure the declared upper-rung persona as Codex/subscription, retaining
  ordinary gateway builders and Claude alternatives. The ladder invokes the
  rung automatically within its configured bounds; no per-use approval is added.
- Keep the judge on its independently selected gateway model.
- Verify organization ownership, private visibility, and GitHub Enterprise
  Cloud merge-queue capability; refuse before dispatch if any is absent.
- Prove one small story end to end, then controlled ordinary retry, pre-agent
  failure, auth failure, question, timeout/cancel, and route-transition cases.
- Prove ordinary gateway failures trigger the configured subscription rung
  automatically, with absent/disabled/exhausted controls and no changed judge
  or landing path.
- Observe 5–10 representative supervised stories before changing future
  defaults. Compare first-pass acceptance, landing time, interventions, diff
  quality, evidence completeness, and usage availability; a small sample is a
  pilot, not a universal quality claim.
- On refresh interference, unintended API-key use, wrong attempt attribution,
  repeated unexplained startup failure, or materially worse intervention/landing
  behavior, stop new Codex dispatches, preserve evidence, restore future Claude
  defaults from the snapshot, and diagnose on isolated infrastructure. Do not
  kill unrelated live nodes or delete their homes.

### Outside this implementation sequence — Optional away-mode assistance

Implement 162 only after the supervised pilot is stable. Start monitor-only with
one durable owner/lease. Scheduled desktop tasks require the app and machine to
be running and are project-scoped; CLI/IDE do not manage those schedules, and
web tasks cannot use a local project folder
(https://learn.chatgpt.com/docs/automations). Add action authority narrowly and
explicitly. Idle observations remain quiet; completion, failure, meaningful
change, or required human action may notify. Temporal remains the factory
scheduler.

## Complete skill inventory and disposition

The inventory describes the 2026-09-09 installation. “Keep” is a product
disposition, not authorization to install or change anything now.

### Six project skills

| Skill | Disposition | Owning work |
| --- | --- | --- |
| `floor-status` | Keep; remove implicit fetch/re-arm/merge, use effective route and frozen attempt data, resolve paths, replace dated figures | 087 packaging; 158 behavior |
| `escalation-triage` | Keep; evidence gathering is read-only, read actual options/recovery, remove fixed paths/process scans/mandatory notification | 087; 158 |
| `findings-ingest` | Keep after correction; distinguish historical evidence from current recurrence, preserve provenance/dedup/severity, separate analysis from authorized apply | 087; 158 |
| `away-mode` | Redesign; monitor-only first, one owner/lease, explicit action scope, classified retry, quiet unchanged ticks | 087; 162 |
| `build-metrics` | Keep; preserve dispatch identity, runner/route/model and unknown dimensions, resolve roots, pin dependencies, use unique scratch output | 087; 158 |
| `spec-html` | Keep presentation; consume Ergane validation/graph results, preserve skipped/refusal/advisory states, resolve paths, publication explicit | 087; 158 |

### Fifteen shared user skills

| Skill | Disposition for Ergane |
| --- | --- |
| `grill-me` | Keep explicit for genuinely uncertain design; never interpose on an already concrete request. |
| `grill-with-docs` | Keep/adapt to `CONTEXT.md` and append-only `docs/decisions.md`; no parallel ADR convention or read-only mutation. |
| `diagnose` | Keep for authorized isolated reproduce/instrument/fix work; not a read-only audit recipe. |
| `tdd` | Keep within dispatched scope; approved spec scenarios are the contract, without redundant generic approval pauses. |
| `improve-codebase-architecture` | Keep on demand; use available delegation, preserve decisions/read-only scope, avoid broad rollout refactors. |
| `zoom-out` | Keep explicit; orient through current architecture and domain vocabulary. |
| `handoff` | Keep; allow a named durable path and preserve unresolved evidence and authority. |
| `prototype` | Keep on demand in scratch or isolated checkout, never beside live imported factory modules. |
| `setup-matt-pocock-skills` | Replace/adapt local setup assumptions with canonical shared guide, Ergane trios/findings, and existing domain docs. |
| `triage` | Keep for other repositories; disable/reroute generic GitHub-label trigger in Ergane. |
| `to-prd` | Adapt to a draft trio/brief; no automatic GitHub publication or ready state. |
| `to-issues` | Adapt vertical slices to stories/work-graph edges; external issue tracker only by explicit request. |
| `caveman` | Keep explicit/reversible; narrow generic brevity trigger and preserve evidence quality. |
| `find-skills` | Keep explicit for capability extension; no popularity-driven install or ordinary-work trigger. |
| `write-a-skill` | Consolidate its quality checklist with Codex `skill-creator`; retain one source plus native packaging guidance. |

### Five Claude-only user skills

| Skill | Disposition for Ergane |
| --- | --- |
| `forge` | Optional port; replace hard-coded question tools; never replace Ergane's trio for factory work. |
| `grind` | Not in the default kit; reconsider only after narrowing direct implementation/commit, live-checkout, loop, and delegation authority. |
| `teach` | Personal-only learning workspace outside this repository. |
| `photo-critique` | Personal-only; no factory role. |
| `airbnb-search` | Personal-only; migrate its MCP dependency separately if desired. |

### Plugin families and bundled capabilities

| Skill or group | Disposition |
| --- | --- |
| `understand` | Optional, separately audited architecture-map generator; never required for orientation and never redirect output into the live checkout during read-only/concurrent work. |
| `understand-dashboard` | Optional viewer; not an authoritative factory status surface. |
| `understand-chat` | Optional graph questions; live source overrides stale graph data. |
| `understand-explain` | Retain only if it measurably improves over `zoom-out` and source inspection. |
| `understand-onboard` | Episodic only; do not create a second durable architecture authority. |
| `understand-diff` | Optional PR aid; treat its overlay write as mutation requiring intent. |
| `understand-domain` | Optional visualization; `CONTEXT.md` remains vocabulary authority. |
| `understand-knowledge` | No current factory role; separate knowledge-workspace concern. |
| `impeccable` | Low relevance to this backend integration; audit packaging/scripts before any later frontend use. |
| Codex `openai-docs`, creator/installer, image generation, research, Sites, visualization | Platform capabilities used only for their jobs; not node defaults or migration dependencies. |
| Claude Stop/SessionEnd hooks and telemetry | Inventory by purpose; do not copy syntax or install automatic repository mutation/continual graph rebuilds. |

### Adjacent non-skill surfaces

| Surface | Disposition |
| --- | --- |
| `ralph/ralph.sh` | Retire/document as a default factory execution path because it invokes `claude -p` outside `AgentAdapter` and competes with Temporal policy. If later retained for a distinct operator job, give it a separate spec with explicit runner selection, isolation, and authority; do not silently port it. |
| Absent Spec Kit command shims | Inventory historical use and reconcile source/version before restoration; project metadata alone is not a Codex installation. |

### Thirty-two unavailable lockfile names

These names have lock entries but no same-name installed body in the inspected
custom-skill directories. Treat every row as **reconcile source, version, name,
and intended scope; neither restore nor delete from its name alone**.

| Names |
| --- |
| `ask-matt`, `batch-grill-me`, `claude-handoff`, `code-review` |
| `codebase-design`, `design-an-interface`, `diagnosing-bugs`, `domain-modeling` |
| `edit-article`, `git-guardrails-claude-code`, `grilling`, `implement` |
| `loop-me`, `migrate-to-shoehorn`, `obsidian-vault`, `qa` |
| `request-refactor-plan`, `research`, `resolving-merge-conflicts`, `scaffold-exercises` |
| `setup-pre-commit`, `setup-ts-deep-modules`, `to-questionnaire`, `to-spec` |
| `to-tickets`, `ubiquitous-language`, `wayfinder`, `wizard` |
| `writing-beats`, `writing-fragments`, `writing-great-skills`, `writing-shape` |

Also reconcile the historically used but currently absent Spec Kit commands.
Do not bulk-install any marketplace catalog to make the counts match.

## Qualification evidence and stop gates

| Gate | Minimum evidence | Stop condition |
| --- | --- | --- |
| Shared discovery | Redacted fresh Codex/Claude root, nested, worktree observations | Either client loads divergent policy or a node gains a second standards source |
| Reporting purity | Equivalent facts and zero file/store/ref/queue/service changes | Any read intent mutates state |
| Auth authenticity | Managed-account fixture accepted; API-key/malformed/unsupported rejected before launch | Auth mode or owner is ambiguous |
| Lifecycle | One serialized owner across two epics/targets/deployments with refresh/restart/cancel recovery and persisted validated state | Operator login interference, duplicate roots, or concurrent owners |
| Attempt evidence | Current invocation only; event classes, question/auth/timeout/cancel, honest usage | Old/error-only output fabricates a turn or usage |
| Deployment | Every declared supported layout is exercised; unsupported standalone refuses before dispatch; host-side policy sees the owner while the child sees only its staged copy; real search/edit/test/commit is pilot-only | Only version/stub proof, credential absent, child sees owner state, or confinement lost |
| Hooks | Exact definition/hash, normal trust, real allow/refuse for supported tools | File installed but untrusted, unsupported payload, or bypass required |
| Pilot | Landed diff, gates, judge, attestation, archive, runner/route/model | Wrong route, evidence gap, refresh contamination, poor recovery |
| Away mode | Durable owner/lease and stop, quiet idle ticks, explicit actions | Duplicate owner, authority drift, or scheduler ambiguity |

## Handoff checklist

- [ ] Operator selects draft-only versus promotion-to-ready endpoint.
- [x] Operator approves the separate factory Codex login and host-global serialized owner (2026-09-09).
- [ ] For later subscription rollout, operator names an eligible private pilot target.
- [ ] For later subscription rollout, the deferred governance proposal is separately scoped and approved before application.
- [x] Nine trios validate and derive with their expected story/FR coverage.
- [x] Independent reviewers' blocking objections are resolved or recorded as holds.
- [x] No runtime store, credential, client trust store, service, registry, spec state, commit, or remote changed during this documentation pass.
