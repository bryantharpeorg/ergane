# Codex as Ergane's primary working environment: audit and handoff plan

**Audit date:** 2026-09-09 UTC (2026-09-08 evening in Dallas).
**Checkout:** `/home/admin/code/ergane`, branch `ergane-buildout`, HEAD `18b83474c6fa`.
**Mandate:** read-only audit while other agents code; this new Markdown document is the sole requested write.
**Status:** implementation plan, not an implemented migration or a production-readiness attestation.

**Latest operator steering — 2026-09-09:** Codex CLI is the immediate operator
client and desired builder runner, with builder inference remaining on the
existing LiteLLM gateway to Ollama Cloud (`agent: codex`, `route: gateway`).
The subscription-first priorities below describe the earlier audit brief and
are superseded for near-term work. First promotions recommended: 157, 087, 158.
The automatic subscription upper rung is now agreed as the final implementation
phase, using the approved factory-login design and the current deployment.
Its target/governance proposal remains to reconcile. See section 10 and the consolidated review for current
scope; landed acceptance histories remain intact.

## 1. Assessment

**The runner integration is real and substantially complete. Codex is not yet ready to become the unattended factory default. The operator workflow can move first, after a small, deliberate instruction and skill migration.**

Keep the adapter architecture that landed in specs 154 and 155. Finish the credential lifecycle, attempt evidence, deployment, and operator interfaces around it. Do not repeat the original adapter implementation project.

The intended destination is:

- The operator uses Codex for refinement, review, status, findings analysis, and management of buildout.
- Factory coding personas primarily use `agent: codex`, `route: subscription`, with an explicitly verified ChatGPT model. This preserves the operator ruling recorded in 155's plan on 2026-09-08.
- Claude Code remains an explicitly selectable runner, using the same project instructions and portable skills.
- The existing gateway judge continues independently during this migration. Its implementation is an HTTP completion, not a coding-agent CLI invocation.
- Shared project knowledge remains in Ergane's existing documents, specs, and findings system. There is no second Codex-specific roadmap or standards document.

### What was actually inspected

Source, tests, manifests, recent commits, the existing adapter brief, spec 154/155 records, all six project skills and their scripts, the 20 distinct user-installed custom skills, duplicate installations, instruction files, Spec Kit metadata, and selected configuration structure. Enabled Claude plugin skills were assessed for purpose and portability; their complete dependencies were not runtime-certified. Current official Codex documentation was checked for discovery, execution, and authentication contracts.

No tests, agent CLI turns, authentication probes, live-store commands, fetches, builds, dispatches, service changes, commits, or pushes were performed. No credential contents were read. A read-only systemd status query failed with `Failed to connect to bus: Operation not permitted`; the deployed worker identity, effective environment, and running image therefore remain unverified. Stub tests were read, not run.

This is a source audit of a moving workspace, not a frozen deployment inspection. The starting and pre-write Git status agreed. During final verification, other agents changed spec trios 074, 131, 136, and 147; the fingerprinted integration sources, registry, and instruction file remained unchanged. Existing documents and workgraphs were left alone. In particular:

- `specs/155-codex-runs-as-a-second-runner/spec.md` already had an uncommitted change from `ready` to `landed`, with extensive operator attestation.
- `docs/codex-adapter-plan.md` already existed untracked. It describes the earlier design baseline and must not be read as the current implementation inventory.
- Source anchors below were verified during this audit; the implementing agent must recheck them against its chosen base.

## 2. What has landed and should be retained

| Capability | Evidence | Assessment |
| --- | --- | --- |
| Separate runner and credential route | `factory/config.py:154`, `derive_agent_and_route`, `effective_route`, `Persona` | Correct foundational abstraction; legacy persona forms remain readable. |
| Unknown-runner refusal | `factory/config.py:346`, adapter registry | Configuration checks the actual registered adapters rather than silently launching Claude. |
| Dispatch chooses the persona's runner | `factory/activities/agent_activities.py:519` | The former hardcoded Claude dispatch has been removed. |
| Shared execution policy | `factory/workgraph/adapter.py:1165` | Both adapters reuse launch monitoring, timeout, process cleanup, archival, and question-ferry policy. Preserve this. |
| Codex gateway invocation | `CodexAdapter`, `_seed_codex_config` at `adapter.py:2081` | `codex exec`, stdin prompt, generated Responses provider, per-attempt gateway key in the environment. |
| Codex subscription invocation | `discover_codex_credential` at `adapter.py:943`; `_credential` and `_seed_home` | Discovers and copies a Codex credential into the node home; subscription key issuance skips the gateway. Lifecycle gaps follow below. |
| Measured refusal marker | `adapter.py:1847`; `agent_activities.py:586` | The known 401 shape reaches a named auth failure. Other classification weaknesses remain. |
| Packaged binary support | `factory/verify/toolchain.py:126`, `Dockerfile:44`, bwrap toolchain binds | Codex 0.153.4 is pinned in the image; npm payload mounting is handled. Host standalone packaging differs. |
| Honest absent subscription spend | `factory/activities/usage_activities.py:535` | Subscription rows retain unknown tokens/spend rather than pretending the run cost zero. |
| Standards delivered explicitly | `factory/workgraph/prompt.py`, `resolve_standards` in `agent_activities.py` | Implementer authority does not depend on a vendor instruction filename being auto-loaded. |

The four 155 story commits are on this branch: US1 `994dccc` (#453), US2 `1b84e3d` (#456), US4 `6c61d66` (#455), US3 `18b8347` (#462). Spec 154 is attested in commit `ca363b4`.

The current checked-in registry still uses Claude for every LLM persona: implementer at `personas.yaml:294`, closer at `:378`, debugger at `:499`, architect/researcher likewise, and legacy Claude subscription for `opus-closer` at `:541`. There is no checked-in Codex persona. This establishes the checkout's configuration, not the live worker's effective registry: environment overrides, XDG configuration, and installed package data also participate in registry resolution (`factory/config.py:114`).

## 3. Findings, ordered by migration consequence

Here, **P1** means resolve before relying on the affected primary workflow; **P2** means resolve during migration. “Confirmed” describes a source-level behavior, not a reproduced production incident.

### F1 — P1: subscription selection does not enforce subscription authentication

**Confirmed source behavior.** `discover_codex_credential` checks only that a candidate file exists. `CodexAdapter._credential` accepts it, and `_seed_home` copies it. No check enforces managed ChatGPT authentication or excludes an API-key login. The subscription test fixture explicitly supplies `{"auth_mode": "apikey", ...}` (`tests/test_155_us3_codex_subscription.py:81`).

Thus `route: subscription` can seed API credentials into Codex's default provider while Ergane records no gateway spend. The CLI, not the route declaration, would then determine the actual billing method. This contradicts the operator's subscription ruling.

**Required outcome:** validate credential mode and required structure before launch, refuse unsupported/API-key modes by name, and preserve a redacted credential-source/mode record. Generate the appropriate CLI login-method restriction where supported by the pinned version; verify its behavior rather than assuming it. Missing, malformed, wrong-mode, and inaccessible credentials must fail before consuming a coding attempt. Subscription must never silently fall back to gateway or API-key billing. OpenAI documents ChatGPT and API-key sign-in as different access paths, and provides a login-method restriction. [Authentication](https://learn.chatgpt.com/docs/auth).

### F2 — P1: copied subscription credentials have no refresh ownership or persistence policy

**Confirmed implementation; provider effects require qualification.** Each attempt copies the operator's credential again (`adapter.py:2042`), even though node homes persist. Refreshed node credentials are not reconciled into a durable credential owner. Copying files isolates filesystem writes; it does not establish independent OAuth sessions or prevent server-side refresh-token invalidation. The comments claiming that copies prevent concurrent nodes invalidating one another are stronger than the evidence supports.

Current OpenAI account-auth automation guidance requires a serialized stream for a credential, preserving refreshed credentials between runs, and avoiding repeated restoration of the original seed. It also explicitly scopes this pattern to trusted private automation and excludes public/open-source repositories. Ergane's constitution declares public targets. That mismatch must be resolved before claiming unattended copied-account execution is a supported operating arrangement; it does not prevent the operator using Codex interactively. Do not reinterpret the operator's subscription request as permission to choose paid API access. [Account-auth automation guidance](https://learn.chatgpt.com/docs/auth/ci-cd-auth).

**Required outcome:** qualify the intended deployment against that guidance; establish a worker-owned, durable credential lifecycle with explicit provenance, refresh persistence, and recovery. Preserve the operator's interactive session. Any future concurrency design must prove independent session ownership or safe serialization, not infer it from separate paths. Do not build a custom OAuth refresh client when Codex already owns refresh.

The existing `max_concurrent_subscription_nodes` is insufficient as an account-wide protection: it is per epic, and `_subscription_nodes_in_flight` counts original node personas (`workflow.py:1455`), not necessarily the current promoted/recovery runner. Multiple epics and an operator session can still contend. Start qualification with one factory subscription execution globally; raising concurrency is a separate acceptance condition.

### F3 — P1: a route change can inherit the previous route's Codex configuration

**Confirmed source behavior.** `home_path` is per node, explicitly shared across attempts (`adapter.py:882`). A gateway attempt writes `.codex/config.toml`; a later subscription attempt copies `auth.json` but does not remove or replace that gateway config (`adapter.py:2018`). The environment no longer provides `CODEX_GATEWAY_KEY`, while the retained provider still requires it. This makes a Codex gateway → Codex subscription ladder transition refuse rather than change route as requested. The reverse transition leaves a subscription credential present unnecessarily.

**Required outcome:** every attempt materializes an exact execution configuration for its resolved route. Test gateway → subscription → gateway in one node home, including activity retries and recovery. Separate durable authentication from disposable execution configuration; clearing the entire node home is not a substitute for designing the lifecycle.

### F4 — P1: evidence can come from an earlier attempt or from non-message output

**Confirmed source behavior.** `_turn_happened` accepts any rollout file anywhere in the persistent node home (`adapter.py:2057`, `_codex_rollouts` at `:2102`). After a previous successful attempt, a later launch failure that creates no rollout can still count as having taken a turn. `_archive_session` then copies all discovered rollouts into the current archive. The plan itself records that even a refused first run can create an error-only rollout (`specs/155.../plan.md:165`). Existence is not proof of a model response.

Separately, `_classify_auth_failure` scans the whole combined output for a substring (`agent_activities.py:607`). An ordinary nonzero exit with a quoted historical 401 in reasoning, tool output, or a test fixture will be classified as authentication failure. The reasoning-only control in `test_155_us2_codex_refusal.py:203` uses a successful exit, which bypasses the classifier and misses this case. The same combined output is also relevant to the existing operator-question scan.

**Required outcome:** capture the current Codex session and current-attempt events explicitly. Distinguish fatal authentication events, actual assistant messages, diagnostic/tool output, and reasoning. Keep raw evidence and existing question-ferry behavior. Prefer a small adapter-side event decoder with a stable neutral result contract, rather than adding Codex parsing throughout orchestration. Codex documents JSONL events, session IDs, usage events, and separate final-message output. [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

Add controls for a prior rollout plus a new startup failure, a fresh error-only rollout, a non-auth exit quoting a 401, an actual refusal with surrounding output, and an operator-question marker quoted in a tool response. Preserve `credential_source` and result metadata when reclassifying; the current reconstruction at `agent_activities.py:617` drops that field.

### F5 — P1 for container deployment: having the binary does not provide the credential

**Confirmed generated-project gap.** `factory/supervision/container_project.py:583` mounts state, supervision, config, and registered repositories. It has no explicit Codex credential source mount or `CODEX_HOME` forwarding. Mounting the config directory does not make the host's `~/.codex/auth.json` exist inside the engine. The discovery fallback therefore cannot be assumed to work in a generated engine deployment.

The actual host runner resolves to the standalone ARM64 0.153.4 release. The image installs npm Codex. The standalone leaf bind loses the installation layout used for bundled tools, a divergence already measured and recorded in 155's plan, trap 8. US4's executable-launch test uses a planted package and shell payload (`tests/test_155_us4_codex_toolchain.py:112`), not a real Codex model turn.

**Required outcome:** declare and reconcile the worker credential source using the lifecycle from F2; support an explicit, narrow credential/state path rather than mounting the operator's whole Codex home. Add a real packaged-runner smoke exercise for each supported host/image shape: launch, search, edit, test, commit, archive. Keep the external confinement boundary effective when the Codex bypass flag is used. Boundary replacement can remain a separate project.

### F6 — P1 for day-to-day operations: status and onboarding still speak Claude

**Confirmed.** `factory/workgraph/credential_status.py` only discovers Claude credentials and offers Claude remedies; `factory/cli/nouns/build.py:1178` exposes it without selecting a runner. The environment helper's subscription advice also names Claude (`scripts/ergane-env.sh:98`). No Codex profile is supplied in the example registry or operator instructions.

**Required outcome:** runner-aware credential diagnostics, explicit runner/route/model visibility for the actual attempt, configuration provenance, and an installation/cutover guide. Display subscription usage as unavailable until measured, not free. Gateway routing is not itself proof of marginal per-token billing either: the current gateway includes flat-rate upstream arrangements.

### F7 — P1 for portable operation: instruction discovery and knowledge access differ

**Confirmed filesystem/configuration state.** The repo has `CLAUDE.md` but no `AGENTS.md`; project `.agents` and `.codex` are empty. There is no global `~/.codex/AGENTS.md` and no configured instruction-filename fallback. Codex therefore has no configured equivalent of the project's Claude orientation.

The discovered ancestor `/home/admin/AGENTS.md` mandates Beads, mandatory push, and cleanup for every session. That is inappropriate as universal Ergane guidance: this project tracks findings and executable specs, and has an active-factory mutation boundary. Do not assume every Codex surface loads ancestor files above the Git root identically; test the actual instruction chain. The conflict is present on disk regardless.

Global Claude guidance also contains the operator's timestamp preference and Hindsight recall/retention rules. Claude configuration registers Hindsight, Airbnb, and Playwright MCP servers; the inspected Codex config has no `mcp_servers`. These tools were not exposed in this session. Port the relevant knowledge connection and policy deliberately; don't substitute fresh recollection for missing memory.

### F8 — P2: spec authoring, convenience scripts, and governance still assume Claude

- `.specify/integration.json` and `.specify/init-options.json` identify only Claude; no installed project Spec Kit skills were found. Authoring needs a tested Codex entry point, even though the resulting Markdown remains neutral.
- `ralph/ralph.sh:23` still launches `claude -p` directly. It is outside `AgentAdapter`. Replacing factory dispatch does not replace this script.
- `CLAUDE.md`, `CONTEXT.md`, architecture prose, and the constitution still contain `factory.yaml` or first-runner-era descriptions. The active manifest is `ergane.yaml`.
- Spec 155 expects a D-053 governance motion; the inspected decision log has D-052 followed by D-054, with no D-053 heading. The constitution still lists Claude first and pi.dev/OpenCode later. Reconcile the missing decision through the normal immutable-log process; don't fabricate an old decision or silently rewrite history.

### F9 — P2: skills contain stale facts, duplicate mechanisms, and incompatible workflow assumptions

See the complete disposition below. The most consequential defects are: a status skill that can trigger merges, route detection using the retired sentinel, metrics that merge separate dispatches, an HTML renderer with its own incomplete validator, and an ingestion skill giving contradictory instructions about historical sightings. Porting those unchanged would preserve their failure modes.

## 4. Shared instructions and skills: proposed architecture

### Project instructions

Use a single canonical project `AGENTS.md`. Make `CLAUDE.md` a compatibility symlink to it, subject to a loading check on both installed clients. If a deployment cannot preserve that symlink, use a tiny explicit loader and validate that it reads the canonical file. Do not maintain two copied policies.

Retain the existing operator/implementer distinction at the very beginning. A factory node follows its assembled brief and declared standards; the operator guide must not authorize wider work. Retain the standards/document authority map, immutable decisions, live-state commands, refinement discipline, landed-story identity, and escalation boundaries.

Add only the missing operational essentials:

1. Manifest is `ergane.yaml`, with legacy lookup documented only where relevant.
2. Locate the effective registry, runtime root, target checkout, and landing branch before reasoning from local defaults.
3. The repo's work authorities are findings and Spec Kit trios. Generic Beads/GitHub-issue skills must not create a competing queue.
4. A short skill index by job, with operator-only scope and links to the canonical skills.
5. Active-factory rule and a reviewable isolated-checkout procedure for authorized implementation. Never edit the live imported engine to make an inspection succeed.
6. Explicit distinction between read-only reporting and merge/dispatch/attestation/answer actions.
7. Vendor-specific capability references only when needed.

Keep this file approximately the size of the current orientation. Move incident narratives, host details, and CLI tutorials into linked references. Extend `tests/test_claude_md.py` to validate the canonical source and compatibility entry points, including semantic sources such as the active manifest—not merely whether cited paths exist.

Codex reads `AGENTS.md` through its instruction hierarchy and supports alternate filenames via configuration. A repo-owned canonical file is preferable here to making every operator configure a Claude fallback manually. [Instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

### Skill layout

```text
AGENTS.md                          # canonical operator orientation, node guard first
CLAUDE.md -> AGENTS.md              # compatibility, verified in both clients
.agents/skills/<name>/SKILL.md      # one canonical implementation per project skill
.agents/skills/<name>/scripts/      # deterministic helpers where useful
.agents/skills/<name>/references/   # incidents, schemas, harness details
.agents/skills/<name>/agents/openai.yaml
.claude/skills/<name> -> ../../.agents/skills/<name>
docs/agents/workflow.md             # findings -> refinement -> spec -> build -> attest
docs/agents/capabilities.md         # harness bindings and availability checks
```

Codex discovers project/user skills under `.agents/skills` and follows skill-directory symlinks. Its optional `agents/openai.yaml` can disable implicit invocation. Preserve the equivalent explicit-invocation policy on Claude; do not assume Claude's `disable-model-invocation` frontmatter controls Codex. [Skill discovery and metadata](https://learn.chatgpt.com/docs/build-skills).

Use skill-relative paths in scripts and examples. Project-local aliases must point within the tracked repo so isolated worktrees remain self-contained. For user skills, consolidate identical copies into `~/.agents/skills`, then expose them to Claude through aliases. Do not put operator credentials or home-specific connection settings into tracked skill directories.

**Persona `skills:` is currently reserved and unused** (`factory/config.py:234`, `tests/test_062_us3_skills.py`). Moving directories will not make that field execute skills. Do not wire it opportunistically. Operator skills should not become automatic instructions for implementer nodes; explicitly gate scope and invocation. If curated node skills are later needed, specify that dispatch contract separately and keep the declared standards authoritative.

### Capability bindings

| Shared intent | Portable behavior | Harness-specific implementation |
| --- | --- | --- |
| Ask about a real design choice | Ask one concise question; continue independent work | Native available question tool or text; no hardcoded `AskUserQuestion` requirement |
| Delegate bounded investigation | Define scope, inputs, output, and mutation restriction | Use the current harness's delegation facility only when available and authorized |
| Recall project lessons | Read relevant durable memory, then verify against code | Hindsight MCP configured per operator; explicit degraded state if unavailable |
| Resume a monitor | Persist scope, cursor, expiry, stop condition, and action permissions | Claude wakeup or Codex automation integration, discovered and qualified separately |
| Notify the operator | Notify on completion, actionable changes, or required decisions | Available authorized channel; no mandatory `PushNotification` tool name |
| Show a spec | Produce local self-contained HTML with validation provenance | Local link/preview by default; optional requested publication via available publisher |
| Stop monitoring | Cancel only this monitor and persist stopped state | Map both wakeup and background-task cancellation; no global task termination |

Skills should express these jobs directly, with small harness references. Avoid a general-purpose abstraction framework or a replacement workflow engine. Temporal remains responsible for durable factory scheduling.

## 5. Usefulness audit: all installed custom skills

Usage figures below come from local Claude `skillUsage` counters. They are cross-project, partial invocation telemetry—not a quality score, a complete history, or evidence that a skill with no entry was never used.

### Six project skills

| Skill | Value / observed usage | Disposition and concrete changes |
| --- | --- | --- |
| `floor-status` (270 lines) | Highest daily value; 163 recorded invocations | **Keep; migrate first.** Make reporting side-effect-free: no automatic fetch, re-arm, or merge. Read `route` directly, not `r.agent == "subscription"` (`SKILL.md:140`). Use resolved attempt/snapshot data, not a regex over a start payload joined to today's registry. Retire the claim that debugger promotion never resolves its model; current workflow freezes and selects rung personas. Replace dated pace figures with measured data or explicitly unavailable estimates. Discover target, branch, and runtime paths. |
| `escalation-triage` (164 lines) | High value at the moment human attention is needed; no counter entry | **Keep.** Preserve decision-brief scope and no unsolicited escalation answers. Replace fixed `.factory` paths, raw process scans, static button semantics, and mandatory push-notification calls. Read the escalation's actual options and current recovery behavior; several landing/kill changes postdate the skill. No mutation during evidence gathering. |
| `findings-ingest` (331 lines) | High value for consumer reports; 1 recorded invocation | **Keep; correct before reuse.** Section 2 says not to re-report historical sightings of already fixed defects, but section 7 and hard rules say never filter before ingestion. Resolve this with explicit observation time/provenance and a historical-evidence path that does not advance recurrence as if seen now. A historical document alone must not justify resolving a current live defect either. Preserve deduplication, severity provenance, scratch rehearsal, and honest classification. Refresh moved CLI anchors and recheck the partial-batch warning against current code. Separate analysis from authorized ledger application. |
| `away-mode` (220 lines) | Valuable operator function; 13 recorded invocations, plus 105 for generic `loop` | **Redesign, then enable explicitly.** It depends directly on `ScheduleWakeup`, `TaskStop`, and `PushNotification`. Its policy and persisted state should be shared; scheduling and notification are harness bindings. Use one owner/lease so two operator sessions cannot dispatch/attest the same floor. Begin with monitor-only mode; action mode must carry the operator's specific authority. Replace blanket one-hour handling of every 429 with classified, bounded behavior. Keep quiet while unchanged. |
| `build-metrics` (151 lines) | Useful for comparing the Codex rollout; 1 recorded invocation | **Keep; repair measurements.** `scripts/rework.py:44` hardcodes `.factory` stores and groups by epic/node/attempt without the `dispatch` dimension added in spec 117. Repeated dispatches can be collapsed. Resolve runtime paths, preserve dispatch identity, and compare runner/route/model where recorded. Treat missing historical dimensions as unknown. `loc.py` downloads and executes mutable upstream cloc code and uses fixed shared `/tmp` filenames; make dependencies explicit/pinned and scratch outputs unique. Move all old figures into dated reference material. |
| `spec-html` (84 lines, ~600-line renderer) | Useful refinement/review surface; 3 recorded invocations | **Keep the presentation; replace duplicate validation.** `render.py` implements its own graph/anchor checks; `factory.spec.validate_spec` now composes the real validation layers. Consume that report and existing graph/landing interfaces; preserve skipped/refusal/advisory distinctions. Stop swallowing landing lookup failures as empty data (`render.py:158`). Replace fixed checkout/branch paths and optional Claude `Artifact` publication with portable local output and explicit publication. |

There is no need to delete any of the six project jobs. Their domain knowledge is valuable. Their current wrappers and stale implementation assumptions are the problem.

### Fifteen shared user skills

All fifteen directories under `~/.agents/skills` have byte-identical counterparts under `~/.claude/skills`, including bundled support files. Fourteen are duplicate directory copies; `find-skills` is already symlinked. Codex can discover the shared copies; maintenance parity is currently accidental except for that symlink.

| Skill | Ergane usefulness | Disposition |
| --- | --- | --- |
| `grill-me` | Strong for resolving a genuinely uncertain design; 8 recorded uses | Keep, explicit use. Do not turn an already concrete implementation request into an interview. |
| `grill-with-docs` | Strong for refinement; 34 recorded uses | Keep and adapt to `CONTEXT.md` plus immutable `docs/decisions.md`. Do not create a parallel `docs/adr` convention or mutate docs during read-only work. |
| `diagnose` | Strong for actual bugs; 1 recorded use | Keep for authorized investigation/fix sessions in isolated environments. Its reproduce/instrument/fix loop is not a read-only audit recipe. |
| `tdd` | Strong for implementation behavior | Keep. Treat an approved spec's interfaces and acceptance scenarios as existing authorization; remove repeated generic approval checkpoints where they add no decision. Apply within the dispatched scope. |
| `improve-codebase-architecture` | Useful selectively | Keep on demand. Replace `Agent` / `subagent_type=Explore` dependency with an available capability; honor the existing decision log and read-only mode. Avoid broad refactoring during adapter qualification. |
| `zoom-out` | Useful, tiny orientation aid | Keep, explicit. Point to current architecture and domain terms. |
| `handoff` | Strong for operator continuity; 5 recorded uses | Keep. Allow a named durable document path rather than forcing `/tmp`; reference existing plans and preserve unresolved evidence/authority. |
| `prototype` | Useful for uncertain UI/state behavior | Keep on demand. Scratch or isolated checkout for Ergane; its instruction to put prototypes beside live modules is unsuitable while the worker imports that tree. |
| `setup-matt-pocock-skills` | Current defaults do not fit Ergane | Replace/adapt its local setup contract. It prefers `CLAUDE.md`, prohibits creating `AGENTS.md` beside it, assumes a conventional issue tracker and `docs/adr`, and asks several setup questions whose answers this repo already provides. Use the canonical shared guide and Ergane workflow mapping. |
| `triage` | Generic GitHub label workflow overlaps poorly with Ergane findings triage | Keep available for other repos; disable/reroute its generic trigger here. Ergane's seven findings classes are not the skill's five GitHub label states. |
| `to-prd` | Useful synthesis discipline, wrong default output/authority here | Adapt to draft a Spec Kit trio/brief; do not publish an extensive GitHub PRD and label it ready automatically. Preserve refinement and mechanical validation before readiness. |
| `to-issues` | Useful vertical-slice discipline, wrong dispatch artifact here | Adapt to Ergane stories and workgraph edges, or keep opt-in for an explicitly requested external tracker. Avoid duplicating specs as a competing issue queue. |
| `caveman` | Optional style preference; 5 recorded uses | Keep explicit and reversible. Narrow the generic “be brief” trigger; brevity should not silently become a persistent mode or reduce evidence quality in operational reports. |
| `find-skills` | Useful only when extending capabilities; 2 recorded uses | Keep explicit. Narrow broad “how do I” triggers and avoid installing by popularity alone. Do not invoke during ordinary code work or audits. |
| `write-a-skill` | Useful authoring checklist; 1 recorded use | Consolidate overlap with Codex's built-in `skill-creator`. Keep one portable quality checklist plus native packaging instructions, rather than multiple competing skill authors. |

### Five additional Claude-only user skills

| Skill | Ergane usefulness | Disposition |
| --- | --- | --- |
| `forge` | Useful for planning non-factory operator work; 4 recorded uses | Port as optional. Replace hardcoded question tools. Its one-file executable-plan format must not replace Ergane's spec/plan/tasks contract for factory work. |
| `grind` | Useful for explicitly authorized miscellaneous plan execution | Port only after narrowing scope. It implements and commits directly, refers to `~/.claude/skills/forge/STRUCTURE.md`, and relies on `/loop` and delegation. Do not run it against the live factory checkout or as a second scheduler beside Temporal. |
| `teach` | Optional learning aid | Keep personal, outside the Ergane default kit. It creates a teaching workspace and should not scatter lessons/state into this production repository. |
| `photo-critique` | No factory role | Keep personal; no need to migrate as part of this project. Script-based work is largely portable, but verify image/display capabilities separately when used. |
| `airbnb-search` | No factory role; 2 recorded uses | Keep personal. Its `claude mcp` diagnostics and Airbnb MCP dependency need a separate personal migration, not an Ergane integration dependency. |

### Enabled Claude plugin skills and bundled Codex capabilities

| Skill / group | Assessment |
| --- | --- |
| `understand` | Optional architecture map generator; substantial dependencies and writes. Do not require it for normal orientation. Its worktree-to-main-checkout output redirection is inappropriate for this read-only/concurrent-work situation. |
| `understand-dashboard` | Optional viewer for a generated graph; keep separate from the factory's authoritative status UI. |
| `understand-chat` | Optional graph-assisted questions; live source must override stale graph data. |
| `understand-explain` | Overlaps with `zoom-out` and direct source inspection; retain only if the graph demonstrably improves navigation. |
| `understand-onboard` | Useful episodically; avoid a second durable architecture document that immediately drifts. |
| `understand-diff` | Optional PR assistance; writes a dashboard overlay and is not intrinsically read-only. |
| `understand-domain` | Optional visualization; preserve `CONTEXT.md` as vocabulary authority, not generated domain output. |
| `understand-knowledge` | No current factory role; intended for a separate wiki/knowledge workspace. |
| `impeccable` | Useful for frontend projects, low relevance to this backend integration. Its sources already have some harness-aware path handling; audit plugin packaging/scripts before any separate migration. |

Claude's settings also have Stop and SessionEnd hooks plus telemetry configuration. Do not copy hook syntax or infer feature parity from plugin counters. Inventory each hook's actual purpose and migrate only a needed behavior. Do not hook operator sessions to automatic repository mutations or continual graph rebuilds by default.

The Codex session's bundled `openai-docs`, skill/plugin creators/installers, image generation, research, Sites, and visualization capabilities are platform tools, not missing Claude-to-Codex ports. Use them for their specific jobs; they should not be added as default dependencies of factory nodes. No marketplace catalog should be bulk-installed for this migration.

### Lockfile drift and unavailable skills

`skills-lock.json` has 41 entries, but no tracked `.agents/skills` files. Thirty-two lock entries have no same-name installation in the inspected custom-skill directories:

`ask-matt`, `batch-grill-me`, `claude-handoff`, `code-review`, `codebase-design`, `design-an-interface`, `diagnosing-bugs`, `domain-modeling`, `edit-article`, `git-guardrails-claude-code`, `grilling`, `implement`, `loop-me`, `migrate-to-shoehorn`, `obsidian-vault`, `qa`, `request-refactor-plan`, `research`, `resolving-merge-conflicts`, `scaffold-exercises`, `setup-pre-commit`, `setup-ts-deep-modules`, `to-questionnaire`, `to-spec`, `to-tickets`, `ubiquitous-language`, `wayfinder`, `wizard`, `writing-beats`, `writing-fragments`, `writing-great-skills`, `writing-shape`.

These are inventory discrepancies, not 32 installed capabilities. Their bodies were unavailable in the inspected installation and their usefulness cannot honestly be certified from names. Reconcile source/version/name and intended scope before restoring or removing lock entries. Also inventory the absent Spec Kit commands, whose historic use appears in Claude counters; the project metadata alone does not install them for Codex.

## 6. Implementation sequence

Use the following work packages to produce small Ergane spec trios when implementation is authorized. **Do not reserve numeric spec IDs from this audit:** other agents are active. Rebase the plan on their current work and allocate fresh IDs through the existing process. Do not edit landed story numbers or duplicate already-landed 154/155 work.

### A. Shared operator entry point and workflow mapping

**Dependencies:** none. **Scope:** project instruction files, `docs/agents`, instruction tests, descriptive documentation.

- Introduce canonical `AGENTS.md` and verified Claude compatibility entry point.
- Establish the local findings/spec/decision workflow for generic skills; correct active-manifest references.
- Carry over relevant personal preferences into shared operator guidance, while keeping host-specific connections outside the repo.
- Resolve the ancestor Beads policy's scope and the missing governance motion through appropriate separate changes. Do not rewrite old decisions.

**Acceptance:** fresh Codex and Claude sessions at root and nested directories identify the same authorities and workflow; a factory node's brief remains controlling; a read-only status request makes no repo/store/queue changes; instruction tests validate both entry points. Record actual loaded instructions instead of trusting filenames.

### B. Portable read-only operator toolkit

**Dependencies:** A. **Scope:** `floor-status`, `escalation-triage`, `build-metrics`, `spec-html`, their helpers and focused tests.

- Move canonical skills with repository-relative compatibility aliases.
- Remove implicit mutations from reporting, correct route/snapshot/dispatch handling, and consume existing validation APIs.
- Add capability/absence reporting and tested explicit-invocation metadata.

**Acceptance:** the same request on both clients yields equivalent facts from the same inputs; zero unintended writes; missing Temporal/ledger/CLI is reported accurately; HTML validation matches the CLI; two dispatches of the same node remain distinct in metrics. Static trigger tests must distinguish “report status” from “merge this PR.”

### C. Subscription authentication lifecycle

**Dependencies:** F2 deployment/auth arrangement settled; otherwise independent of B. **Scope:** credential discovery/staging, mode enforcement, durable refresh ownership, exact route seeding, diagnostic surface.

- Close F1–F3 using real managed-ChatGPT-shaped synthetic fixtures and a controlled real qualification run later.
- Record source and mode without tokens. Handle custom `CODEX_HOME`, missing file, wrong mode, malformed data, inaccessible storage, and unsupported keyring/external-token cases explicitly.
- Serialize by credential owner across epics/recovery, with crash recovery; preserve refreshed state without overwriting the operator's login or blindly trusting an agent-mutated file.
- Make credential diagnostics select/report the runner and effective route.

**Acceptance:** no API-key credential is accepted as subscription; refresh state survives subsequent attempts/restart; mixed routes cannot retain incompatible configuration; an auth failure spends no coding rung; operator and factory sessions have a documented, verified ownership relationship.

### D. Codex attempt evidence and neutral result handling

**Dependencies:** no dependency on operator skill work; coordinate edits with C in `adapter.py` and `agent_activities.py`.

- Capture actual current session identity and event classes; keep raw logs and produce the neutral message/result evidence existing consumers need.
- Correct pre-agent/auth classification and retain credential provenance on failure.
- Capture subscription token counts when supported, keeping dollars unavailable and gateway spend independently attributable. Do not invent dollar equivalents for subscription tokens.

**Acceptance:** F4's counterexamples pass; timeouts, cancellation, question ferry, normal completion, real auth failures, and later attempts are attributed to exactly the correct execution. Claude conformance remains unchanged. A JSON-output transition cannot leak raw events into existing plain-text question scanners.

### E. Deployment and confined execution qualification

**Dependencies:** C and D before subscription production use. **Scope:** engine project generation, installation/readiness, host and npm packaging contracts.

- Provide the worker's declared credential source in the actual chosen deployment; report inaccessible auth before dispatch.
- Verify installed binary version/layout and the boundary used by that worker. Keep 0.153.4 as the measured baseline unless a newer version is separately qualified.
- Exercise search, edits, gates, commit, cancellation, and archive under the real launch path. A `--version` success or shell stub is not enough.

**Acceptance:** real Codex works under each supported deployment shape; attempts remain confined; missing auth/payload/tools produce actionable startup refusals. Deployed worker identity matches the intended engine revision. Run this after current attempts finish or on isolated infrastructure, never by changing their imported checkout.

### F. Refinement and knowledge continuity

**Dependencies:** A and B. **Scope:** Spec Kit authoring entry points, Hindsight capability binding, `findings-ingest`, selected generic skills, lockfile reconciliation.

- Create one tested neutral refinement path: recall relevant lessons, inspect current code, draft/refine trio, validate, render, present for dispatch.
- Reconcile historical findings without manufacturing recurrence; preserve evidence dates and source identifiers.
- Port Hindsight recall and authorized human-session retention to the operator environment. Nodes and unattended monitors do not acquire memory-write authority.
- Resolve `ralph/ralph.sh`: prefer retiring/documenting it as legacy if Temporal supersedes its job. If still required, give the entry point an explicit tested runner selection and separate authorization scope; don't create another factory execution policy.

**Acceptance:** either client can refine the same input into an Ergane-valid trio, name active traps, resume from a handoff, and explain when memory is unavailable. No extra issue tracker, duplicate standards channel, or direct live-checkout coding loop appears.

### G. Supervised Codex-primary pilot

**Dependencies:** A–F for their affected surfaces. **Scope:** isolated canary registry and target first; then future dispatch defaults.

1. Snapshot the effective registry, worker/image/binary identity, route, model, branch, and rollback values. Do not use today's source tree as a substitute for that snapshot.
2. Add new opt-in Codex subscription personas; retain existing Claude entries. Set `fallback: null` unless a separately tested same-route fallback is deliberately declared. Gateway aliases do not belong in a subscription model slot.
3. Verify the exact CLI model is available to this account and pinned CLI. Local Codex config currently names `gpt-6-astra` with `xhigh`; this is a configuration observation, not entitlement or benchmark evidence. Factory isolated homes do not inherit that preference, and `context_window` is currently discarded by the Codex environment adapter.
4. Land one small real story end to end: subscription coding attempt, existing deterministic gates, existing independent judge, merge, correct attestation, correct evidence. Capture results against the landing branch, not `main` by default.
5. Exercise a forced ordinary retry, pre-agent failure, auth failure, question, timeout/cancel, and route transition using controlled fixtures/infrastructure. Include restart/refresh behavior; keep disruptions away from active production nodes.
6. Observe 5–10 representative supervised stories, including a multi-story dependency and a recovery. Compare first-pass acceptance, time to landing, operator interventions, diff quality, and usage availability with a comparable Claude sample. Small samples justify a pilot, not a universal quality claim.
7. Change default producing personas and promotion/debugger selections only for future epics after review of that evidence. Refresh the appropriate installed worker/registry at a quiescent boundary; running epics retain their frozen inputs.

**Acceptance:** actual landed code and attributed evidence support the switch; no silent billing-route change; no credential/old-rollout contamination; no unexplained attempt spending; Claude can still be selected and pass the same contract.

The judge stays on its independently selected gateway model. `factory/verify/judge.py:918` posts chat completions directly; changing its persona's `agent` field does not turn it into `codex exec`. Moving all judge/enrichment inference to subscription would be another product decision and execution contract, not a configuration flip.

### H. Optional unattended operator assistance

**Dependencies:** stable G; A/B/F for shared policies. **Scope:** `away-mode` capability bindings and durable monitor state.

- Begin with one monitor-only owner. Persist target, last observation, authorized actions, deadline, and stop state.
- Qualify Codex's actual automation/notification tools before replacing Claude wakeups. A skill file alone does not schedule anything.
- Add narrowly authorized actions after monitoring is dependable. Preserve escalation choices for the operator unless specifically authorized in that session.
- Stop on completion, expiry, or explicit off; notify only on meaningful change, failure, or a required decision.

**Acceptance:** stop survives restart; two clients cannot both own the same monitor; idle ticks remain quiet; only authorized actions execute; Temporal continues to own factory scheduling.

## 7. Validation and rollout gates

These checks are proposed work for the implementation session, not commands run in this audit.

| Gate | Required evidence |
| --- | --- |
| Shared discovery | Real fresh-session evidence from Codex and Claude, root/subdirectory/worktree; canonical instructions and intended skills visible once |
| Reporting purity | No changes to tracked files, runtime state, refs, findings, or merge queue from status/triage/metrics reads; scratch HTML only when explicitly requested |
| Subscription authenticity | Managed ChatGPT fixture accepted; API-key/malformed/unsupported fixtures refused before launch; actual selected auth mode recorded without secrets |
| Lifecycle | Refresh persistence, credential-owner serialization across two epics, restart/cancel recovery, and operator-session coexistence qualified |
| Route transition | Same-node gateway → subscription → gateway and Claude → Codex → Claude paths obey the newly resolved runner and route |
| Evidence | Current session only; old/error-only rollout does not fabricate a turn; quoted markers do not change failure class or ask an operator question |
| Deployment | Every declared supported layout is exercised; unsupported standalone refuses before dispatch; host-side policy can stage credentials while the child cannot read owner state; real search/edit/test/commit is reserved for the held pilot |
| Regression | Relevant 154/155, adapter, subscription, usage, prompt, question, toolchain/container, and instruction tests; then the repository's declared full gate in an isolated checkout |
| Pilot | Landed diff, gate/judge results, ledger and attempt archive, actual runner/route/model, and attestation for real Codex-produced work |
| Rollback | Future dispatch can return to the preserved Claude personas without changing running epic snapshots or losing evidence |

Rollback triggers include auth-refresh interference with the operator, unintended API-key use, incorrect attempt attribution, repeated unexplained startup failures, or a material increase in intervention/failed landings. Stop new Codex dispatches, preserve evidence, restore future defaults from the snapshot, and diagnose on isolated infrastructure. Do not mass-kill live nodes or delete their homes as a rollback strategy.

## 8. Handoff instructions

Start with A and B to make Codex useful for the operator immediately. Treat C–E as the factory cutover gate. Keep the existing gateway/Claude floor running while those changes are built and reviewed on isolated branches. Do not combine auth lifecycle, output decoding, skill migration, and an unattended monitor into one large story.

Before implementation, re-read this document against the current tree and active work. Verify the source and actual deployment separately. Avoid filing these observations as new live sightings without checking the existing findings ledger for matching identities and prior fixes. This audit did not report or resolve findings.

The work is complete when the operator can perform the normal refinement/status/review/handoff cycle through either client from one instruction/skill source, Codex subscription coding runs reliably through the real factory and its recovery paths, Claude remains selectable, and the evidence distinguishes every runner, route, attempt, and unmeasured quantity honestly.

### Source fingerprint reference

The audit read these SHA-256 prefixes before writing the plan. Use them to notice drift, not as a requirement to reset other agents' work:

| File | SHA-256 prefix |
| --- | --- |
| `factory/workgraph/adapter.py` | `2121171b55616e0b` |
| `factory/activities/agent_activities.py` | `c493378da3a2ab6a` |
| `factory/config.py` | `5cabf7a63483f285` |
| `factory/workgraph/workflow.py` | `82f51d3f1ba6400b` |
| `factory/verify/judge.py` | `b6f3ae0374f45599` |
| `CLAUDE.md` | `6c9d03708dcc62a7` |
| `personas.yaml` | `04478b775a89635a` |

## 9. Continuation checkpoint — specification authoring handed to Sol

**2026-09-09, HEAD `caf7c5ee8281b002ad9dbce1c2187ff684489e12`.** The user confirmed the workflow is paused, approved a specification-writing batch, and then requested a clean handoff to GPT-5.6 Sol. Read the [Sol specification handoff](/home/admin/code/ergane/docs/codex-sol-spec-handoff-2026-09-09.md) before continuing. It records the approved allocation, unanswered questions, current source findings, and exact continuation steps.

The batch refines existing drafts 087, 112, and 139 and adds six focused trios. Subscription-first rollout, full unattended-operation scope under the existing away policy, and independent read-only reviewers are confirmed. The original endpoint is reviewed drafts; the later question about promoting them to ready remains unanswered.

No existing trio or production file was changed. Six temporary teaching scaffolds were removed after exact-content verification; proposed numbers 157–162 are not reserved. Independent reviewers completed premise research only, not review of authored trios.

Two refinements matter: current Codex documentation includes hooks, so 139 must specify the actual input/trust contract; managed-account automation guidance adds credential-ownership and pilot-target questions that must be resolved before subscription rollout claims. These corrections and sources are detailed in the handoff. The earlier audit's runtime-evidence limitations remain in force.

## 10. Specification batch disposition

**2026-09-09 continuation.** Fresh IDs 157–162 were allocated through
`ergane spec new`; the audit's proposed-number caveat is now satisfied. Existing
drafts 087, 112, and 139 were refined in place. The nine trios remain draft.
The operator approved the separate factory-login design, then clarified that
the operator/gateway migration comes first and an automatic subscription upper
rung is the final implementation phase. 157/087/158 are
the current promotion recommendations; no state change has been authorized.
157 now has two operator stories, with its former governance story preserved
in the deferred proposal, and 160 no longer waits for 159.

The F8 statement that D-053 was absent is now known to be stale. D-053 exists and
records the runner/route split; no batch document edits or fabricates it. The
governance proposal appends the next available decision (`D-056` only at this
source fingerprint) after the then-current last entry if approved.

### Finding-to-spec coverage

| Audit finding | Owning acceptance surface | Residual hold |
| --- | --- | --- |
| F1 — subscription selection/auth authenticity | 159 US1 rejects non-managed shapes; 112 US3 writes runner and route separately | Real account-backed qualification |
| F2 — refresh ownership/persistence | 159 US2 owns one serialized effective-rung lifecycle; US3 fences route state; US5 finalizes/reconciles refresh state | Owner design approved; implement as the final phase |
| F3 — route transition contamination | 159 US3 derives exact effective route and clears incompatible config; 112 US3 preserves mixed gateway judge | Controlled transition qualification |
| F4 — stale/non-message attempt evidence | 160 US1–US3 binds JSONL, archive, projection, and classifications to the current invocation | Real supported-version event fixtures |
| F5 — deployed binary without credential/layout | 161 US1–US3 owns narrow delivery, actual toolchain layout, and synthetic confinement; US5 owns the newly exposed private-queue eligibility prerequisite | 161 US4 private account-backed pilot |
| F6 — Claude-shaped status/onboarding | 159 US4 publishes shared non-secret status; 112 consumes it and reports runner/route/model honestly | Client discovery evidence |
| F7 — instruction/knowledge portability | 157 owns canonical instructions/capabilities; 087 operator skills; 139 target context and supported hooks | Fresh two-client discovery/trust qualification |
| F8 — authoring/governance assumptions | 157 owns operator workflow; the separate deferred proposal preserves subscription governance; 112/139 remove Claude-only assumptions; the runbook disposes `ralph/ralph.sh` and records memory degradation | Future subscription governance needs its own scoped implementation; any retained `ralph` role needs its own runner/authority spec |
| F9 — stale/duplicate skill mechanisms | 087 owns collision-safe packaging; 158 owns pure declared-intent jobs; 162 owns away-mode policy/bindings | No skill install or unattended rollout yet |

### Audit-package-to-spec mapping

| Audit package | Trio(s) |
| --- | --- |
| A — shared operator entry/workflow | 157 |
| B — portable read-only toolkit | 087, 158 |
| C — subscription authentication lifecycle | 159, 112 |
| D — attempt evidence/result handling | 160 |
| E — deployment/confinement qualification | 161 |
| F — refinement/knowledge continuity | 157, 087, 158, plus runbook inventory |
| G — supervised Codex-primary pilot | Gateway path: landed 154–156 plus 160 and the runbook's deployment qualification; final subscription rung: 159, shared 160 evidence, focused current-deployment 161, and reconciled governance |
| H — optional unattended assistance | 162 |

The operator runbook is
`docs/codex-primary-operator-migration-runbook-2026-09-09.md`; the held amendment
text is `docs/codex-primary-governance-proposal-2026-09-09.md`; validation and
independent review outcomes are recorded in
`docs/codex-primary-spec-review-2026-09-09.md`.
