---
state: draft
fixes:
  - interpreter/an-unknown-agent-silently-runs-claude-code
# DRAFTED 2026-09-06 by an operator session from docs/codex-adapter-plan.md,
# against ergane-buildout at 8e8b3a1. Every `file:line` in spec.md and plan.md
# was read from the working tree with `sed -n`/`grep -n` on 2026-09-06 and
# verified to resolve to the symbol named, not recalled. The brief's own
# warning holds: anchors move, and a green `ergane spec validate` is not proof
# they are still good.
#
# WHERE THIS CAME FROM. The Codex adapter brief (docs/codex-adapter-plan.md),
# §6 Spec A. The brief is a brief and binds no implementer; this spec does.
# The operator's agent-runner priority — Codex, then pi.dev, then OpenCode,
# Copilot last — is settled and recorded in the brief's §1. This spec is the
# first of a pair; the Codex adapter itself is the next number.
#
# WHAT IT FIXES, AND WHY FIRST. There is no Codex in this spec. It is the
# seam-making half, and it lands on its own merit because it closes a live
# defect: `load_personas` validates `agent:` only as a non-empty string
# (factory/config.py:268-270 — the `not isinstance(agent, str) or not agent`
# guard), so a persona declaring `agent: codex` loads cleanly today, is treated
# as gateway-routed (config.py:203-208 treats anything that is not "none" or
# "subscription" as gateway), has a virtual key minted for it, and then runs
# Claude Code — because the single production call site passes a constant, not
# the persona's value (factory/activities/agent_activities.py:178 defines
# `DEFAULT_AGENT = ClaudeCodeAdapter.name` and :521 calls
# `adapter_for(DEFAULT_AGENT)`). An agent nobody chose, running under a model
# nobody chose, with success indistinguishable from the right thing. The
# finding key `interpreter/an-unknown-agent-silently-runs-claude-code` is
# minted alongside this spec, at `error`.
#
# THE STALE COMMENT THAT HID IT. The comment above `DEFAULT_AGENT`
# (agent_activities.py:175-177) still reads "`AttemptContext` carries no
# `agent` field, so the seam is exercised here rather than per attempt."
# Spec 070 landed the field: `agent: str = ""` sits at
# factory/workgraph/models.py:320, documented at :308-314. The comment
# describes a codebase that no longer exists and is the reason the sever
# stayed invisible. This spec corrects the call site AND the comment; fixing
# one without the other is how it survived.
#
# NOT IN SCOPE. No Codex binary, no CODEX_HOME, no `config.toml` generation,
# no Responses-vs-Chat wire decision — all of that is the next spec, and the
# brief's probe phase (§5) is its input, not this one's. No change to the
# bwrap `--setenv` allowlist (adapter.py:596-618) beyond what the hoist
# requires, and none is required — the operator is weighing moving away from
# bwrap (recorded 2026-09-06), so this spec deliberately does not deepen
# investment in that boundary. No new provider key, and no reintroduction of
# per-persona LLM config blocks: `[[llm.persona]]` apparatus was deleted and
# an AST-walking test fails if it returns (D-048), and route selection is a
# registry field, not a provider config. No change to what the ladder runs.
#
# NEIGHBOURS CHECKED. The personas this derives for are the four live ladder
# personas — implementer, closer, debugger, judge — every one declaring
# `agent: claude-code` and deriving to `route: gateway` per §4.2 of the brief.
# The ladder change landed 2026-09-06 (8e8b3a1); this spec and that change are
# in flight in the same window, and the derivation must leave every one of
# those personas routing exactly as it does today.

## User Stories *(mandatory)*

### User Story 1 - A persona names its CLI and its route separately (Priority: P1)

As the operator, the registry says which CLI runs and how it is authenticated as
two independent facts, so adding a second CLI does not force me to invent
credential-route sentinels.

**Why this priority**: P1 and it depends on nothing. Every other story reads a
`route` field that must exist first. Today `agent:` carries both meanings at
once — `claude-code` names a CLI, `subscription` names a credential route,
`none` names neither — and every predicate that reads it tests a superset of
what it means. The split is the smallest change that lets a second CLI exist
without widening the sentinel grammar.

**Independent Test**: Load a registry declaring `route:` explicitly, load one
omitting it, and read the derived route in each.

**Acceptance Scenarios**:

1. **Given** a persona declaring `agent: claude-code` and `route: gateway`,
   **When** the registry is loaded, **Then** it parses and the persona carries
   both fields, and `routes_through_gateway` (config.py:203) reads `route` and
   answers true.
2. **Given** a persona declaring `agent: subscription` and no `route:` key,
   **When** the registry is loaded, **Then** the load derives `agent:
   claude-code` and `route: subscription` — a legacy value refactored into the
   new pair, not an error — and a committed test asserts the derivation is the
   one the table in plan.md names, entry for entry.
3. **Given** a persona declaring both an explicit `route:` and a legacy
   `agent:` value that would derive a different route, **When** it is loaded,
   **Then** the explicit `route:` wins, because the derivation is a default,
   not an override.
4. **Given** a manifest with no `route:` anywhere — `personas.example.yaml`,
   `container/personas.demo.yaml`, and every installed copy in the wild are all
   this manifest — **When** it is loaded, **Then** every persona derives the
   route the table names and behaves byte-identically to today, because the
   derivation is total.
5. **Given** the persona snapshot a running epic froze at dispatch
   (workflow.py:1261 region) and a worker restarted mid-epic, **When** the
   restarted worker re-reads the unedited registry, **Then** the derivation
   yields the identical pair, because it is pure: same input, same output, no
   clock, no environment, no probe of anything outside the registry text.

### User Story 2 - A registry naming an agent the factory cannot run is refused at load (Priority: P1)

As the operator, a typo or a too-new value in my registry fails loudly at the
load that reads it, not silently in an attempt that runs the wrong CLI.

**Why this priority**: P1, shared with US1 because it closes the defect the
spec exists to close and is worthless if deferred. US1 makes `route` real; this
story makes `agent` honest. They are separated because the refusal is
independently testable and independently shippable — but a pull request landing
US1 without US2 leaves the defect open.

**Independent Test**: Load one registry naming a registered agent and one
naming an unregistered agent, and read what each does.

**Acceptance Scenarios**:

1. **Given** a persona declaring `agent: codex` while no adapter of that name
   is registered, **When** the registry is loaded, **Then** the load raises
   `ConfigError` naming `codex` and listing the agents the factory can run —
   rather than minting a key and dispatching Claude Code, which is today's
   behavior and the defect under repair.
2. **Given** a persona declaring `agent: claude-code`, **When** the registry is
   loaded with the adapter registry holding its one entry, **Then** the load
   succeeds — the refusal is of the unknown, not of the field.
3. **Given** a persona declaring some unknown agent, **When** it is loaded,
   **Then** the error text is the known-agent list, so an operator reading it
   learns the full set of valid values in one message rather than one typo at a
   time.
4. **Given** the legacy sentinel `agent: none`, **When** it is loaded, **Then**
   it is NOT refused as an unknown agent — a deterministic persona runs no CLI
   and must stay loadable with no adapter registered for it.

### User Story 3 - The dispatch path selects the adapter the persona names (Priority: P2)

As the factory, when I build an attempt for a persona, the adapter I invoke is
the one that persona names, not a constant.

**Why this priority**: P2 because it depends on US1 (the field must exist and
be derived) and US2 (only a registered agent is selectable). This is the story
that reconnects the seam the constant severed. It is also the one whose test
must be control-and-mutation, because a green suite that never varies the
persona proves the constant still works, not that selection does.

**Independent Test**: Register a stub second adapter, dispatch a persona naming
it, and read which adapter's invocation the stub recorded.

**Acceptance Scenarios**:

1. **Given** a persona naming a registered second adapter and an attempt built
   for it, **When** the dispatch path runs, **Then** the adapter invoked is the
   second one — proven by the invocation the stub records, not by a passing
   suite. `adapter_for` is called with the persona's value
   (agent_activities.py:521), not with `DEFAULT_AGENT`.
2. **Given** a persona naming the existing `claude-code`, **When** the same
   path runs, **Then** the adapter invoked is `ClaudeCodeAdapter` — the control
   half, proving the change selects rather than merely renaming the constant.
3. **Given** the control and the mutation run in the same test, **When** the
   diff is read, **Then** the two recorded invocations differ only in the
   adapter the persona named — so a diff that hardcodes either would fail one
   half.
4. **Given** `DEFAULT_AGENT` removed from the dispatch call site, **When** the
   stale comment above it (agent_activities.py:175-177) is read, **Then** it no
   longer claims `AttemptContext` carries no `agent` field, because that claim
   is false and is why the sever stayed invisible.

### User Story 4 - The agent-agnostic policy in run_attempt is shared, not copied (Priority: P2)

As the factory, the second adapter implements only the per-CLI surface and
inherits the policy every adapter shares, so the next CLI does not fork 170
lines of orchestration.

**Why this priority**: P2 and dependent on US3 — there is no second caller of
the seam until dispatch can reach it. This story is why the seam is worth
making: `ClaudeCodeAdapter.run_attempt` (adapter.py:1022-1191) is mostly not
about Claude. Pid file, orphan reap, archive directory, monitor loop,
wall-clock deadline, operator-question ferry, backend resolution, standards
path — none of that names a CLI, and a second adapter must not copy it.

**Independent Test**: Define a second adapter class implementing only the
per-CLI surface, and read which parts of attempt policy it did not write.

**Acceptance Scenarios**:

1. **Given** a second adapter class providing only the per-CLI concerns (argv,
   prompt delivery, provider env, home seeding, credential discovery,
   turn-happened probe, refusal markers), **When** an attempt runs through it,
   **Then** the shared policy — pid file, orphan reap, archive, deadline,
   operator-question ferry — comes from one implementation both adapters call,
   proven by the second class containing none of it.
2. **Given** the outer `AgentAdapter` protocol (`run_attempt`, adapter.py:735),
   **When** the hoist lands, **Then** orchestration still sees exactly one
   method — the hoist introduces a narrow inner seam the shared policy calls,
   and does NOT resurrect the five-method protocol that
   specs/005-workgraph-interpreter/contracts/adapter.md:7-14 sketched and the
   implementation deliberately collapsed. That rejection stands for the outer
   protocol; the spec must say so, so a reviewer does not read the inner seam
   as reversing a decision.
3. **Given** the conformance suite
   (tests/test_adapter.py and its siblings), **When** the hoist lands, **Then**
   the adapter tests sweep the `_ADAPTERS` registry rather than naming
   `claude-code` — the lesson carried in from
   `ci/the-adapter-conformance-suite-is-a-hardcoded-list-of-one`, so the suite
   that holds every adapter to the seam would notice a second adapter breaking
   it.

## Functional Requirements *(mandatory)*

- **FR-001**: The persona registry MUST accept an optional `route:` field. When
  present, it MUST be one of the routes `factory/verify/models.py:832-836`
  declares: `gateway`, `subscription`, `deterministic` (and `none`, the no-LLM
  case, per the brief's §4.1 table). When absent, it MUST be derived from
  `agent:` per the derivation table.
- **FR-002**: The legacy-to-derived mapping MUST be exactly: `claude-code` →
  (`claude-code`, `gateway`); `subscription` → (`claude-code`, `subscription`);
  `none` → (`none`, `none`). An explicit `route:` MUST win over derivation in
  every case.
- **FR-003**: The derivation MUST be pure and total: a function of the registry
  text alone, defined for every value the field accepts, with no dependence on
  clock, environment, or any state outside the loaded registry. A worker
  restarted mid-epic MUST read an unedited registry into an identical persona.
- **FR-004**: `load_personas` MUST refuse an `agent:` value with no registered
  adapter, raising `ConfigError` at load naming the value and listing the
  agents the factory can run. The deterministic persona (`agent: none`) MUST
  NOT be refused for lacking an adapter.
- **FR-005**: The dispatch call site (agent_activities.py:521) MUST pass the
  persona's `agent` value to `adapter_for`, not `DEFAULT_AGENT`. The stale
  comment at agent_activities.py:175-177 MUST be corrected in the same change.
- **FR-006**: The predicates MUST read the new fields on a single axis each:
  `is_llm` tests `agent != none`; `routes_through_gateway` and
  `needs_virtual_key` test `route == gateway`. `route_of`
  (`factory/verify/models.py:837`) MUST read the `route` field rather than
  derive it from the agent name.
- **FR-007**: The agent-agnostic attempt policy — pid file, orphan reap,
  archive, monitor loop, deadline, operator-question ferry, backend resolution,
  standards path — MUST be shared by every adapter through one implementation.
  The per-CLI surface an adapter supplies MUST be only: argv, prompt delivery,
  provider env, home seeding, credential discovery, the turn-happened probe,
  and refusal markers.
- **FR-008**: The adapter conformance tests MUST be parametrised over the
  `_ADAPTERS` registry (adapter.py:1512 region), not over the literal
  `claude-code`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-005]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-007, FR-008]
```

Three `depends_on_merged` edges, declared rather than left to inference. US2's
refusal only has a field to validate once US1 has created it and the derivation
to feed it — a US2 built first would refuse or accept a grammar that does not
exist yet. US3 wires the dispatch path to the persona's `agent` value, which is
only selectable once US2 has made that value honest; both must land first. US4
hoists the shared policy a second adapter calls, and there is no second caller
of the seam until US3 can route to it. The edges buy ordering, not freedom from
contention: US1 and US2 both touch `factory/config.py`, US3 and US4 both touch
`factory/workgraph/adapter.py`, so no story may be made `concurrent_with`
another that edits the same file. US1 and US2 share one file and are sequenced
by the edge; US3 and US4 share one file and are sequenced by the edge. No
`concurrent_with` override is added.

## Constitution References *(mandatory)*

- **Principle VII — Personas Over Model Tiers**: a persona resolves to "agent,
  model + fallback, skills, write scope, budget default, and breach policy."
  Adding `route` widens that list. This spec is an amendment and requires the
  decision-log entry the constitution's Governance section mandates —
  **D-053**, recording why the field was split rather than extended with more
  sentinels, and superseding D-018 without editing it.
- **Environment Constraints** (constitution.md:127-128): "Claude Code first;
  pi.dev/OpenCode later." The operator's settled priority is Codex, then
  pi.dev, then OpenCode, Copilot last. Codex belongs in that sentence in the
  governance motion this spec requires, in that order.
- **D-048**: `[[llm.persona]]` per-persona LLM config blocks were deleted and
  an AST-walking test fails if they return. Route selection is a registry
  field, not a return of that apparatus.

## Success Criteria *(mandatory)*

- A registry with an explicit `route:` loads; a legacy registry without one
  loads and derives per FR-002; an explicit `route:` wins over derivation.
- A registry naming `agent: codex` with no adapter registered raises
  `ConfigError` naming the known agents, rather than dispatching Claude Code.
- A persona naming a second registered adapter runs that adapter, proven by the
  invocation a stub records, with the `claude-code` persona as the control in
  the same test.
- A second adapter class implements only the per-CLI surface and inherits the
  shared attempt policy.
- `uv run pytest -q` green. That is the whole of this repo's gate
  (`ergane.yaml`).
