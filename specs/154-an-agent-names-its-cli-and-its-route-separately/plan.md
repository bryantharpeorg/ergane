# Implementation Plan: an agent names its CLI and its route separately

Every `file:line` below was read from the working tree at `8e8b3a1` on
2026-09-06 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing. The tier that checks
`path.py:NN — symbol` anchors is a prose convention, not a validator — a green
`ergane spec validate` is not proof these are still good.

## What already exists, and where

**The seam is a Protocol a registry serves.** `AgentAdapter` is a Protocol with
one method, `run_attempt` (`factory/workgraph/adapter.py:720`, signature at
:735). `adapter_for(agent, **options)` (`adapter.py:750`) looks the name up in
`_ADAPTERS` and **already raises `AdapterError`** for an unknown name, with the
known-agent list in its message (`adapter.py:757-764`). The registry itself is a
single-entry dict: `_ADAPTERS = {ClaudeCodeAdapter.name: ClaudeCodeAdapter}`
(`adapter.py:1512`).

**The sever is one call site.** The only production caller passes a constant:
`DEFAULT_AGENT = ClaudeCodeAdapter.name` (`factory/activities/agent_activities.py:178`),
called as `adapter_for(DEFAULT_AGENT)` (`agent_activities.py:521`). The comment
above the constant (`agent_activities.py:175-177`) claims `AttemptContext`
carries no `agent` field. That is false: `agent: str = ""` sits at
`factory/workgraph/models.py:320` (documented :308-314), the workflow populates
it, and `ClaudeCodeAdapter` reads it. The field reaches every adapter and stops
one inch short of the lookup. The defect is not a missing guard — it is that
the guard at `adapter.py:750` is unreachable from production.

**The `agent` field means two things at once.** Live values are `claude-code`,
`subscription`, `none`. Everything reads it:

| Predicate | Location | Current test |
| --- | --- | --- |
| `is_llm` | `factory/config.py:197-200` | `agent != DETERMINISTIC_AGENT` |
| `routes_through_gateway` | `factory/config.py:203-208` | `agent not in (DETERMINISTIC_AGENT, SUBSCRIPTION_AGENT)` |
| `needs_virtual_key` | `factory/config.py:211-216` | `agent == "claude-code"` — bare literal |
| gateway env | `factory/workgraph/adapter.py:1112` | `context.agent != "subscription"` |
| credential seeding | `factory/workgraph/adapter.py:1071` | `context.agent == SUBSCRIPTION_AGENT` |
| usage expected | `factory/activities/usage_activities.py:182`,`:192` | `== SUBSCRIPTION_AGENT` |
| evidence route column | `factory/verify/models.py:837` (`route_of`) | derives gateway/subscription/deterministic from the agent name |

The sentinels live at `factory/config.py:143` (`DETERMINISTIC_AGENT = "none"`)
and `:149` (`SUBSCRIPTION_AGENT = "subscription"`).

**The registry schema rejects unknown fields.** `load_personas` raises
`ConfigError` on any field not in the two sets (`factory/config.py:264`), where
`_REQUIRED_FIELDS = ("agent","model","write_scope","needs_worktree")` and
`_OPTIONAL_FIELDS = ("fallback","skills","timeout","context_window")`
(`config.py:151-152`). So `route:` is refused outright today and must be added
to `_OPTIONAL_FIELDS` — FR-001 is not optional.

**The frozen snapshot makes purity real.** A running epic reads the registry
once and freezes it: "One registry read answers for the whole epic"
(`factory/workgraph/workflow.py:~1260`, `_read_registry()` at :1261). A
per-attempt re-read is named trap 1 there. The derivation must be pure so a
mid-epic worker restart re-reads an unedited registry identically.

**The hoist surface is genuinely there.** `ClaudeCodeAdapter`
(`adapter.py:993`) `run_attempt` begins at :1022; its per-CLI `argv()` method
follows at the launch section (`adapter.py:1195` region). The shared policy —
pid file, orphan reap, archive, monitor loop, deadline, operator-question
ferry, backend resolution, standards path — fills the body between, and none of
it names a CLI.

## What to build, in order

Four stories. US1 (the field) and US2 (the refusal) are independent and both
P1; land them together. US3 (dispatch selects) and US4 (the hoist) are P2 and
depend on US1+US2.

### US1 — split the field

Add `route` to the persona schema and derive it when absent.

1. Add `route` to `_OPTIONAL_FIELDS` (`config.py:152`).
2. Add a `route` attribute to the `Persona` dataclass, defaulting `None` until
   derivation fills it.
3. Write the derivation as a pure, total function of the entry text:
   `claude-code`→(`claude-code`,`gateway`); `subscription`→(`claude-code`,`subscription`);
   `none`→(`none`,`none`). Explicit `route:` wins.
4. Re-point the three predicates (`config.py:197-216`) to single-axis reads:
   `is_llm` on `agent != none`; `routes_through_gateway` and
   `needs_virtual_key` on `route == gateway`.
5. Re-point `route_of` (`verify/models.py:837`) to read the field.

**Test-first (constitution: tests precede implementation). US1-S2's derivation
table and US1-S4's byte-identical legacy load are the pair to write first** —
they pin the behavior a wrong derivation would break.

### US2 — refuse the unknown agent at load

The check exists at `adapter.py:750`; this story makes the load path reach it.

1. In `load_personas`, after the non-empty-string guard (`config.py:268-270`),
   validate the (derived) `agent` against the registered adapter names, raising
   `ConfigError` naming the value and the known agents.
2. Exempt the deterministic persona (`agent: none`) — no CLI, no adapter, must
   stay loadable.
3. The registry of known agents is `_ADAPTERS` (`adapter.py:1512`). Read it,
   do not hardcode a second list (constitution IX — a second copy of the
   meaning is a fork waiting to disagree).

### US3 — dispatch selects the named adapter

1. Change `agent_activities.py:521` from `adapter_for(DEFAULT_AGENT)` to
   `adapter_for(<the persona's agent>)`, sourced from the attempt context that
   already carries it (`models.py:320`).
2. Correct the stale comment at `agent_activities.py:175-177` in the same
   change.
3. The test is control-and-mutation in one: register a stub second adapter,
   dispatch a persona naming it, assert the stub recorded the invocation —
   with a `claude-code` persona as the control half in the same test.

### US4 — hoist the agent-agnostic policy

1. Extract the shared policy out of `ClaudeCodeAdapter.run_attempt`
   (`adapter.py:1022-1191`) into one implementation both adapters call.
2. Define the narrow inner seam as the per-CLI surface only: `argv`, prompt
   delivery, provider env, home seeding, credential discovery, turn-happened
   probe, refusal markers. The outer `AgentAdapter` protocol keeps its one
   `run_attempt` method — do NOT resurrect the five-method protocol that
   `specs/005-workgraph-interpreter/contracts/adapter.md:7-14` sketched and the
   implementation deliberately collapsed. Record that distinction in the spec
   text so a reviewer does not read the inner seam as a reversal.
3. Parametrize the adapter conformance tests over `_ADAPTERS`
   (`adapter.py:1512`), not over the literal `claude-code`.

## Traps

- **Trap 1 — the derivation must be a default, never an override.** An explicit
  `route:` always wins. A regression where derivation stomps an explicit route
  fails US1-S3 and silently re-routes a persona.
- **Trap 2 — the purity requirement is load-bearing, not stylistic.** The
  frozen snapshot (workflow.py:~1260) means one registry read answers for a
  whole epic. A derivation that reads the clock, the environment, or probes
  anything outside the registry text makes a mid-epic worker restart diverge
  from the snapshot the epic froze.
- **Trap 3 — `route_of` derives today; it must read.** `verify/models.py:837`
  currently derives a route from the agent name. After the split that
  derivation is a second source of truth that will disagree with the field.
  FR-006 requires it to read, not derive.
- **Trap 4 — do not re-add per-persona LLM config.** `[[llm.persona]]` blocks
  were deleted; an AST-walking test fails if they return (D-048). Route
  selection is a registry field, not provider config. Codex's wire/provider
  choice belongs in the next spec's generated `config.toml`, not here.
- **Trap 5 — do not touch the bwrap `--setenv` allowlist beyond what the hoist
  requires (none).** The operator is weighing moving away from bwrap (recorded
  2026-09-06); this spec deliberately adds no new investment in that boundary.
- **Trap 6 — the unknown-agent refusal must come from the registry, not a new
  literal.** `_ADAPTERS` at `adapter.py:1512` is the source of truth for "no
  adapter of that name." A parallel list in `config.py` is the IX fork.
- **Trap 7 — `DEFAULT_AGENT` may survive as a name, but not as the dispatch
  input.** Some paths (toolchain `factory/verify/toolchain.py`, the install
  wizard's synthetic persona at `factory/cli/install.py:519`,`:673`) reference a
  default agent legitimately. The fix is scoped to the dispatch call site
  (FR-005); do not delete the concept, only its use as the dispatch argument.

## Verification

- Re-read every anchor above against the tree at drafting time.
- `uv run pytest -q` green — the whole of this repo's gate (`ergane.yaml`).
- Control-and-mutation on the dispatch seam (US3-S3): the two recorded
  invocations differ only in the adapter the persona named.
- US2 proven by a load that raises, read from the raising test, not inferred
  from a passing suite.
