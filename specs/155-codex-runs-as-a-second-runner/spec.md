---
state: draft
depends_on:
  - 154-an-agent-names-its-cli-and-its-route-separately
# DRAFTED 2026-09-06 by an operator session from docs/codex-adapter-plan.md
# (§6 Spec B), against ergane-buildout at 8e8b3a1, with the 154 seam spec as
# its premise. Anchors re-read from the working tree on 2026-09-06.
#
# WHERE THIS CAME FROM. The Codex adapter brief. Spec 154 made the seam real —
# a persona names its CLI (`agent:`) and its credential route (`route:`)
# separately, the load refuses an agent with no registered adapter, and the
# dispatch path selects the adapter the persona names. This spec puts a second
# CLI behind that seam: Codex. Without 154 this spec is a hardcoded fork of
# Claude Code; with it, Codex is a class, a lookup, and a `config.toml`.
#
# WHAT WAS PROBED, AND WHAT WAS NOT. P1 RAN 2026-09-06 and PASSED: LiteLLM
# bridges `/v1/responses` to an `ollama-cloud/*` alias and returns real usage
# (`{"input_tokens":17,"output_tokens":83}`) with an HTTP 200 — so the gateway
# route is viable and the redesign risk in the brief's §9 is closed. One
# consequence surfaces as trap 1 below: the ollama upstream returns the
# reasoning model's chain-of-thought IN CLEARTEXT in both
# `output[].summary[].text` and `output[].encrypted_content`, so a Codex node
# on a reasoning model will emit reasoning text a downstream classifier could
# misread. P4 — whether Codex's Landlock/seccomp sandbox nests inside the
# factory's bwrap jail — was DELIBERATELY DEFERRED by the operator, who is
# weighing moving away from bwrap (recorded 2026-09-06). The remaining CLI
# probes (P2 `wire_api = "chat"` acceptance, P3 refusal text, P6 auth.json
# location, P8 session identity) were NOT run because the Codex binary is not
# installed on this host; each is named a trap the implementer measures, never
# assumes.
#
# NOT IN SCOPE. No bwrap mount-set or sandbox work — that boundary's future is
# an open operator decision, and the brief's story 4 is therefore CONDITIONAL
# here, not a commitment. No new provider key, and no per-persona LLM config
# blocks (D-048). No `--json` in v1 (decided in the brief §3.1: the two stdout
# refusal markers and the `## OPERATOR QUESTION` scan assume plain text, and
# token accounting already comes from the gateway on the attempt's virtual
# key). This spec does NOT decide the Chat Completions vs Responses wire
# question — it probes it and lets the answer pick the `wire_api`.
#
# THE PRIORITY. Codex is the first second runner by the operator's settled
# order (Codex, then pi.dev, then OpenCode, Copilot last), chosen on credential
# shape: Codex, pi.dev and OpenCode are all file-based-credential shaped, which
# spec 070 already designed for; Copilot's GitHub-token shape is the outlier.

---

# Feature Specification: codex runs as a second runner


## User Stories *(mandatory)*

### User Story 1 - A Codex node runs on the gateway, driving an ollama-cloud alias (Priority: P1)

As the operator, a persona can name `agent: codex` and `route: gateway`, and the
attempt runs Codex against the same LiteLLM aliases the ladder already uses,
spend attributed to the attempt's virtual key exactly as Claude's is.

**Why this priority**: P1 and the reason the pair of specs exists. It depends
on 154 having made `agent: codex` / `route: gateway` expressible and
selectable. P1 already proved the gateway serves `/v1/responses` for the
aliases, so this story is wiring, not discovery — except where the unprobed CLI
facts (the traps) turn out to bite.

**Independent Test**: Dispatch a single-story spec on a Codex persona through
the gateway and read the landed diff and the ledger row.

**Acceptance Scenarios**:

1. **Given** a persona declaring `agent: codex` and `route: gateway` and a
   registered `CodexAdapter`, **When** an attempt runs, **Then** the launched
   process is `codex exec` with the prompt on stdin, and the gateway env and
   generated `config.toml` point at the attempt's virtual key — the same
   per-attempt key the Claude route mints.
2. **Given** that attempt, **When** it spends, **Then** the spend is read from
   the proxy on the attempt's virtual key (`factory/activities/agent_activities.py:200-227`
   region), exactly as a Claude gateway attempt — token accounting is NOT a
   reason to add `--json`.
3. **Given** the per-node `CODEX_HOME`, **When** the adapter seeds it, **Then**
   it writes a `config.toml` declaring the gateway as a custom provider
   (`model_provider`, `[model_providers.ergane-gateway]` with `base_url`,
   `env_key`, `wire_api`) parameterised by the attempt's proxy URL and virtual
   key — the analogue of `_seed_node_home` (`factory/workgraph/adapter.py:896`), not a copy.
4. **Given** a Codex gateway attempt on an `ollama-cloud/*` alias backed by a
   reasoning model, **When** the response carries chain-of-thought in cleartext
   (P1 measured this), **Then** the adapter does NOT misclassify the run on the
   strength of that reasoning text appearing near the output.

### User Story 2 - A Codex refusal is classified, not read as a silent success (Priority: P1)

As the operator, when Codex cannot authenticate, the attempt ends named as a
refusal, not as a clean run that produced nothing.

**Why this priority**: P1, shared with US1, because a Codex node that dies on a
bad credential and reads as a diffless success is the exact failure the factory
has already paid for once — spec 070's probe found `claude` exits 1 and prints
`Not logged in` on STDOUT, not stderr, which a stderr-watching caller reads as
silent success. Codex's refusal shape is UNMEASURED (P3 was not run); this
story is where it gets measured and classified.

**Independent Test**: Run Codex with no credential and record the exact refusal
text, its stream, and its exit code; then run it through the classifier.

**Acceptance Scenarios**:

1. **Given** Codex invoked with no valid credential, **When** it refuses,
   **Then** the attempt is classified as a refusal (the Codex analogue of
   `SUBSCRIPTION_REFUSAL_MARKER`, `factory/workgraph/adapter.py:193`) naming the auth failure —
   and the marker comes from the MEASURED text (trap 2), never an assumed one.
2. **Given** the measured refusal string, **When** a committed test replays it
   through the refusal classifier, **Then** the attempt is NOT a silent
   diffless success — the control half asserting the thing 070's probe taught.
3. **Given** the reasoning-model cleartext CoT (US1-S4), **When** the refusal
   classifier scans stdout, **Then** reasoning text alone does not satisfy nor
   defeat refusal detection.

### User Story 3 - A Codex node runs on a ChatGPT subscription (Priority: P2)

As the operator, a persona can name `agent: codex` and `route: subscription`,
and the attempt runs against the operator's own ChatGPT sign-in with no virtual
key minted and no metered spend — the same shape Claude's subscription route
has today.

**Why this priority**: P2 because it depends on US1 (the adapter and the
gateway route existing) and adds the second credential route. It inherits the
subscription route's known hole: usage is not metered off a virtual key, and
Claude's subscription route has the same hole today — this spec does not fix
that, it matches it.

**Independent Test**: Seed a node home with the measured `auth.json`, run a
turn, and read the credential source the adapter recorded.

**Acceptance Scenarios**:

1. **Given** a persona declaring `agent: codex` and `route: subscription`,
   **When** an attempt runs, **Then** no virtual key is minted and the node
   home is seeded from the discovered `auth.json` (whose location is MEASURED
   in P6, trap 3), the analogue of the three-path discovery at
   `factory/workgraph/adapter.py:840`.
2. **Given** the seeded subscription credential, **When** the attempt records
   its `credential_source`, **Then** it names the file it came from, so a
   subscription run is distinguishable from a gateway run in the evidence.
3. **Given** a subscription credential that rotates on use (the hazard
   documented as unmeasured for Claude at `factory/workgraph/adapter.py:840-852`), **When** it is
   inherited here, **Then** the spec names it as an inherited hazard rather
   than pretending it is measured for Codex.

### User Story 4 - The toolchain and image carry the Codex binary, confined by the standing boundary (Priority: P3)

As the factory, a Codex node can start at all — the binary is on the toolchain
and in the image — and it is confined by whatever sandbox boundary the operator
has in force when this story lands.

**Why this priority**: P3 and CONDITIONAL. The operator is weighing moving away
from bwrap (recorded 2026-09-06), so this spec deliberately does NOT probe or
commit to bwrap nesting (P4 deferred). The story is scoped to presence and
launch under the CURRENT boundary, and it names the nesting question as
explicitly open rather than answering it.

**Independent Test**: On a host with the toolchain applied, launch Codex under
the standing launch path and confirm it starts and writes its worktree.

**Acceptance Scenarios**:

1. **Given** the toolchain and image definitions, **When** they are applied,
   **Then** `codex` resolves on the node's PATH.
2. **Given** the standing launch path in force when this lands, **When** a
   Codex node starts, **Then** it launches and writes its worktree — with
   Codex's own sandbox disabled
   (`--dangerously-bypass-approvals-and-sandbox`) if the outer boundary already
   confines the node, since a Codex node launched under bwrap must not ALSO be
   told to enforce its own read-only default.
3. **Given** the open question of Codex's Landlock/seccomp sandbox nesting
   inside bwrap, **When** this story is drafted, **Then** the nesting is
   recorded as an UNANSWERED hazard tied to the operator's sandbox-boundary
   decision — not silently assumed to work, and not silently assumed to fail.

## Functional Requirements *(mandatory)*

- **FR-001**: A `CodexAdapter` MUST be registered in `_ADAPTERS`
  (`factory/workgraph/adapter.py:1512`) under the name `codex`, so a persona naming
  `agent: codex` resolves (154's US2 refusal must NOT fire for it) and the
  dispatch path (154's US3) selects it.
- **FR-002**: A Codex attempt on `route: gateway` MUST mint and use the
  per-attempt virtual key exactly as the Claude route does, reaching Codex via
  the `env_key` named in the generated `config.toml`; spend MUST be read from
  the proxy on that key.
- **FR-003**: The adapter MUST seed a per-node `CODEX_HOME` with a generated
  `config.toml` declaring the gateway as a custom provider, parameterised by
  the attempt's proxy URL and key. Provider routing belongs in that file, NOT
  in any `[[llm.persona]]`-style control-plane config (D-048).
- **FR-004**: Codex MUST be launched with the prompt on stdin (`codex exec -`),
  matching the existing prompt delivery (`factory/workgraph/adapter.py:1584`), and the two stdout
  refusal markers plus the `## OPERATOR QUESTION` scan MUST keep working on
  plain text — v1 does NOT pass `--json`.
- **FR-005**: A Codex auth failure MUST be classified as a refusal from the
  MEASURED refusal text, not read as a silent success. The marker value comes
  from the probe, not from assumption.
- **FR-006**: A Codex attempt on `route: subscription` MUST mint no virtual key
  and seed the node home from the discovered `auth.json`; the recorded
  `credential_source` MUST distinguish it from a gateway run.
- **FR-007**: Reasoning-model chain-of-thought returned in cleartext (P1
  finding) MUST NOT cause a misclassification of either a successful turn or a
  refusal.
- **FR-008**: The toolchain and image MUST place `codex` on the node's PATH;
  launch MUST disable Codex's own read-only default when an outer boundary
  already confines the node. The bwrap-nesting question stays explicitly open,
  tied to the operator's sandbox-boundary decision.

## Work Graph

```yaml
US1:
  depends_on: []
  depends_on_merged: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-007]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-006]
US4:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008]
```

Every edge is `depends_on_merged`, and the whole graph descends from spec 154,
which must land first (T001). US2 classifies the refusal from text measured in
US1's probe task, so it cannot land before the adapter it classifies exists —
and a refusal that could pass silently must never reach the floor, which is why
US1 and US2 land together. US3 adds the subscription route on top of the
gateway adapter and its measured credential facts. US4 is the conditional
presence story, dependent only on the adapter existing; it is deliberately
sequenced but scoped against the operator's open sandbox-boundary decision. The
stories largely share `factory/workgraph/adapter.py` (US1/US2/US3) and the
toolchain/image files (US4), so no `concurrent_with` override is added — a
story editing `adapter.py` must not run beside another editing `adapter.py`.

## Traps

- **Trap 1 — reasoning CoT comes back in cleartext.** P1 measured the ollama
  upstream returning full chain-of-thought in `output[].summary[].text` and
  `output[].encrypted_content`. A classifier or marker-scan that keys on output
  text can misread reasoning as content or as a failure. Do not match markers
  against reasoning blocks.
- **Trap 2 — Codex's refusal shape is UNMEASURED.** P3 was not run (binary not
  installed). Measure the exact refusal text, stream, and exit code before
  writing the marker; 070's lesson is that a refused run on the wrong stream
  reads as a silent diffless success.
- **Trap 3 — `auth.json` location and rotation are UNMEASURED.** P6 was not
  run. Measure where `codex login` writes it and whether it rotates on use; the
  rotation hazard is documented as unmeasured even for Claude
  (`factory/workgraph/adapter.py:840-852`) and is inherited, not solved.
- **Trap 4 — there is no documented flag to supply a session id up front**
  (unlike Claude's `--session-id`). Capture what `thread.started` reports so
  attempt identity stays recordable; do not assume a `--session-id` analogue
  exists.
- **Trap 5 — `wire_api = "chat"` acceptance is unresolved.** One secondary
  source says Chat Completions was removed and only `responses` remains; the
  official page neither confirms nor denies. P1 proved the proxy serves
  `responses`, so `wire_api = "responses"` is the default assumption — but if a
  model or wire decision needs `chat`, probe P2 before relying on it.
- **Trap 6 — do not over-invest in bwrap.** The operator is weighing moving
  away from it (2026-09-06). Land the minimal presence-and-launch change under
  the standing boundary; the nesting/allowlist hardening waits on that
  decision.
- **Trap 7 — a repeating 429 naming a `cooldown_list` is a dead upstream
  credential, not a rate limit.** Read up to the first 401;
  `/health/liveliness` reports healthy throughout.

## Constitution References *(mandatory)*

- **Principle VII** — a persona resolves to agent, route (added by 154), model
  + fallback, skills, write scope, budget default, breach policy. This spec
  adds the first non-Claude value the `agent` axis takes.
- **Environment Constraints** (constitution.md:127-128): the agent seam names
  "Claude Code first; pi.dev/OpenCode later." Codex is added to that sentence
  in the operator's settled priority order (Codex → pi.dev → OpenCode →
  Copilot) by the D-053 governance motion 154 requires and this spec depends
  on.
- **D-018 / its successor**: the CLI is swappable and a second agent must be a
  class and a lookup, not an orchestration change (D-018's promise; superseded
  not edited).

## Success Criteria *(mandatory)*

- A single-story spec dispatched on a Codex persona through the gateway lands,
  with the landed diff and the ledger row as evidence — a green suite and a
  PASS verdict are evidence, not proof; run the thing.
- A Codex refusal is classified from measured text, never read as a silent
  success.
- The adapter conformance suite sweeps `_ADAPTERS` and would notice if Codex
  broke the seam.
- `uv run pytest -q` green.
