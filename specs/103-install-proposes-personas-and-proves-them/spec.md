---
state: ready
# DRAFTED 2026-08-23 ~10:00 PM CT by the operator session that produced
# docs/container-onramp-research-findings.md (§5 is this spec's evidence) and
# docs/container-onramp-program.md (this is the program's "fully configured"
# pillar). Tree at 838b9c3; every file:line below was read individually off
# that revision on 2026-08-23.
#
# WHAT THE DRAFTING PASS SETTLED, so nobody re-derives it:
#   - **Install proposes ALIASES, not personas.** The shipped example registry
#     (personas.example.yaml) is the authority on persona names, agents, write
#     scopes, skills, timeouts and context windows. This spec fills exactly
#     two fields per LLM persona — `model` and `fallback` — and changes
#     nothing else about the registry's shape. A spec that let install invent
#     write scopes would be a security surface, not a convenience.
#   - **The unauthenticated scan stays unauthenticated.** The discovery scan
#     (factory/discovery/llm_scanner.py:1-8) deliberately presents no
#     credential to unconfirmed endpoints. Enrichment is authenticated and
#     therefore happens AFTER the operator confirms the gateway and its
#     master-key env in the interview — a separate step, not a scan change.
#   - **The probe machinery already exists.** `verify_controlplane` mints a
#     short-TTL model-constrained key, revokes it in a `finally`, and probes
#     every registry alias with a 1-token completion (spec 054/US3,
#     factory/controlplane/verify.py:340-480). This spec REUSES that seam at
#     pick time and adds exactly one new probe shape: the judge canary.
#   - **Non-interactive paths keep today's contract.** --non-interactive and
#     --from-file seed the example and report unconfigured, exactly as now
#     (factory/cli/install.py:347-349, :441-443). The seamless path is the
#     interactive one; extending the answer-file schema to a second file's
#     content is a different spec if it is ever wanted.
#
# FLIPPED READY 2026-08-23 ~10:05 PM CT on the operator's instruction, after
# validate passed every layer at both states. Anchors verified against
# 838b9c3; the commits above it touch only docs/ and specs/.
---

# Feature Specification: install proposes personas and proves them

**Created**: 2026-08-23
**Evidence base**: `docs/container-onramp-research-findings.md` §5

## The gap, stated precisely

A persona is the only binding between a role and a model: code never names a
model (`factory/config.py:3-5`), and the registry ships as an example whose
aliases are prefixed `example/` (`factory/config.py:57`), which
`ergane install --verify` correctly reports as *unconfigured, not passing*
(`factory/controlplane/verify.py:373-381`; `factory/cli/nouns/install.py:95-99`).
So a developer finishes install with a factory that cannot dispatch until they
hand-edit `~/.config/ergane/personas.yaml`, mapping eight personas to whatever
aliases their gateway actually serves — the single worst step on the onramp,
and the one the operator's directive names: install must end *fully
configured*.

Everything needed to close the gap exists in pieces. The interview already
scans for endpoints and pre-fills the LLM answer
(`factory/cli/install.py:693`, `:1144`), the scan already returns the
gateway's alias list (`factory/discovery/llm_scanner.py:33`), install already
seeds the registry file (`factory/cli/install.py:261-263`,
`_seed_personas_registry` at `:300`), `--requirements` already derives which
aliases the registry demands (`factory/cli/nouns/install.py:59`,
`gather_gateway_aliases` at `factory/controlplane/verify.py:318`), and
`--verify` already probes aliases with real completions under a minted,
model-constrained, revoked-in-finally key
(`factory/controlplane/verify.py:340-480`). What is missing is the step in
the middle: turning an alias list into a *proposed, confirmed, proven*
mapping — without ever guessing silently, because a wrong judge model
produces plausible verdicts, which is the expensive kind of wrong.

## The rule this spec is asking for

**Interactive install ends with a persona registry whose every gateway alias
was proposed with a stated reason, confirmed by the operator, and proven by a
live probe — and a registry that cannot reach that bar fails install loudly,
never quietly.**

### The ruling, made here rather than left to the implementer

- **Enumerate, enrich, rank — never name-guess.** Gateway aliases are
  operator vocabulary by design; `my-gpu-box-large` is the expected case, not
  the pathological one (findings §5). The ranking's inputs are the gateway's
  own metadata where it has any — a LiteLLM-shaped gateway's `/model/info`
  and wildcard-expanded model list, an Ollama's `/api/show` capabilities —
  and an alias with no metadata is presented as **unclassified**, never
  ranked on its name alone. Name heuristics may break ties; they may not
  create rankings.
- **The ranking is a small, legible requirements table, keyed by persona,
  shipped as data.** implementer: tool-calling required, largest context;
  judge: structured output required, reasoning preferred, and *prefer* an
  alias distinct from the implementer's primary; debugger: tool-calling
  required; closer: cheapest that supports tools; architect/researcher:
  reasoning preferred. `verifier` (`agent: none`,
  `factory/config.py:143`) needs nothing. Subscription personas
  (`factory/config.py:149`) resolve CLI-side model names, not gateway
  aliases (`gather_gateway_aliases` already excludes both,
  `factory/controlplane/verify.py:326-331`) — they are confirmed by the
  operator, never probed against the gateway.
- **Present, don't apply: a picker with the proposal and its reason
  pre-filled.** One line per persona — proposed alias, the *why*
  ("tools ✓, 262k ctx, cheapest of 3 candidates"), Enter accepts, or pick
  from the enumerated list. The complaint class in every comparable tool's
  tracker is silent or unstable assignment, never "it asked me once at
  setup" (findings §5).
- **Probe before writing; write only what passed.** The chosen alias for
  every gateway persona gets the existing 1-token completion probe under a
  minted model-constrained key; the judge's chosen alias additionally gets
  the **canary**: a toy diff with acceptance criteria and a required JSON
  verdict schema, checked for parseability *and* for the correct verdict on
  a known-bad diff. A probe failure removes the alias from that persona's
  candidates and re-ranks; it never becomes write-with-warning.
- **The never-silently-guessed line.** The judge, and every persona's
  `fallback` (a fallback engages unwatched, mid-failure), require explicit
  operator confirmation — pre-filled is fine, defaulted-through is not. If
  no enumerated alias passes the judge canary, install fails with the alias
  list and the unmet requirement printed — the same contract as today's
  `example/` rejection, with better words.
- **Scope is per-install.** The registry binds one gateway's private aliases
  plus write scopes and timeouts — partly security configuration — and the
  factory rewrites the repos it builds in. No repo-committed aliases.

## What this spec does not change

- **The registry's schema and the example file's authority.** `load_personas`
  (`factory/config.py:219`), the `Persona` fields (`:170`), and every
  non-alias field of every persona come from the shipped example unchanged.
- **The unauthenticated scan's security stance.**
  `factory/discovery/llm_scanner.py:64` keeps presenting no credential;
  enrichment is a new, post-confirmation step.
- **`--verify`'s probe suite and its refusal semantics.** The
  key-mint/constrain/revoke discipline (`factory/controlplane/verify.py:
  420-460`) is reused, not reimplemented; verify still fails a registry that
  is all `example/`.
- **Non-interactive install.** `--non-interactive` and `--from-file` keep
  seeding the example and reporting unconfigured
  (`factory/cli/install.py:347-349`, `:441-443`).

## User Scenarios & Testing

### User Story 1 - The gateway's models are enriched after confirmation (Priority: P1)

As the installer, once the operator has confirmed the gateway address and
master-key env, I fetch what the gateway knows about its own models — so the
proposal step ranks on declared capability, not on alias spelling.

**Independent Test**: against an injected transport simulating a LiteLLM
`/model/info` (and an Ollama `/api/show`), enrichment returns per-alias
capability records; against a gateway with no metadata endpoint, every alias
comes back unclassified with the reason recorded.

**Acceptance Scenarios**:

1. **Given** a confirmed LiteLLM-shaped gateway whose `/model/info` answers,
   **When** enrichment runs, **Then** each alias carries the fields the
   ranking needs (tool-calling, structured output, reasoning, context
   window, cost where present), the wildcard-expanded model list is used,
   and no credential was sent before the operator confirmed the endpoint —
   proven by committed tests over the injected transport.
2. **Given** a gateway whose metadata endpoint answers 404 or garbage,
   **When** enrichment runs, **Then** every alias is marked unclassified
   with a detail naming what was tried — never an exception, never a guess.
3. **Given** an Ollama-shaped endpoint, **When** enrichment runs, **Then**
   `/api/show` capabilities populate the same record shape — one record
   type, two sources.

### User Story 2 - A proposal with reasons, or an honest refusal (Priority: P1)

As the installer, I turn enriched aliases into one proposed mapping — every
LLM persona to a primary and a fallback, each with a stated reason — or I
state exactly which persona has no qualifying candidate.

**Independent Test**: pure-function tests over enrichment fixtures: rich
metadata yields full proposals with reasons; thin metadata yields
unclassified-heavy proposals that say so; an empty alias list yields a
refusal naming every unmet requirement.

**Acceptance Scenarios**:

1. **Given** enriched aliases where several qualify, **When** the proposal is
   built, **Then** every gateway persona gets a primary and a fallback with
   a human-readable reason string, the judge's proposal prefers an alias
   distinct from the implementer's primary when one qualifies, and the
   requirements table driving it is data a test can read — proven by
   committed tests.
2. **Given** aliases that are all unclassified, **When** the proposal is
   built, **Then** no persona is silently assigned: the proposal marks every
   slot "needs the operator's choice" with the candidate list attached.
3. **Given** no alias satisfying the judge's requirements, **When** the
   proposal is built, **Then** the result names the judge, the requirement,
   and the aliases considered — the shape the interview turns into a loud
   failure.

### User Story 3 - The judge canary exists and bites (Priority: P2)

As the probe library, I can ask "can this alias judge?" with a toy diff, a
criteria list and a required JSON verdict schema — and a model that answers
prose, or passes a known-bad diff, fails the canary.

**Independent Test**: with an injected client, a canned well-formed FAIL
verdict on the known-bad diff passes the canary; a prose answer, a schema
violation, and a PASS verdict on the known-bad diff each fail it with a
distinct reason.

**Acceptance Scenarios**:

1. **Given** an alias whose canned response is a schema-valid verdict
   correctly failing the known-bad diff, **When** the canary runs, **Then**
   it passes — proven by a committed test.
2. **Given** canned responses that are prose, schema-invalid, or a PASS on
   the known-bad diff, **When** the canary runs, **Then** each fails with a
   reason naming which check broke — three distinct reasons, proven by
   committed tests.
3. **Given** the canary's requests, **When** inspected, **Then** they run
   under the same minted, model-constrained, revoked-in-finally key
   discipline as the existing alias probes — proven by a committed test
   over the injected client's observed calls.

### User Story 4 - The interview picks, probes and writes (Priority: P1)

As an operator running interactive `ergane install`, after the LLM block I
see one pre-filled line per persona, press Enter down the list (or pick
otherwise), watch the probes run, and end with a written registry whose
verify passes — or a loud failure that names what could not be satisfied.

**Independent Test**: drive the interview with the file prompter and injected
enrichment/probe seams end to end: all-accept writes a registry whose every
gateway alias is probe-passed; a probe failure re-ranks and re-asks; an
unsatisfiable judge fails install with the candidate list in the message.

**Acceptance Scenarios**:

1. **Given** proposals and passing probes, **When** the operator accepts each
   pre-filled line, **Then** install writes `personas.yaml` with only `model`
   and `fallback` changed from the shipped example, prints what it wrote and
   why, and the subsequent `--verify` in the same run reports the registry
   configured — proven by a committed end-to-end interview test.
2. **Given** a chosen alias that fails its probe, **When** the interview
   continues, **Then** the failed alias is dropped from that persona's
   candidates, a new proposal is offered, and nothing failed is ever
   written — proven by a committed test.
3. **Given** no alias that passes the judge canary, **When** the interview
   reaches the judge, **Then** install exits nonzero naming the judge, the
   requirement and every alias tried — and the registry on disk is the
   seeded example, not a half-written mapping.
4. **Given** the judge and the fallbacks, **When** the interview presents
   them, **Then** each requires an explicit confirmation — the judge's line
   and every fallback line are never defaulted through by a blanket
   accept — proven by a committed test over the prompter transcript.
5. **Given** a subscription persona in the example registry, **When** the
   interview reaches it, **Then** it is confirmed by the operator (CLI-side
   model name shown) and no gateway probe runs for it — proven by a
   committed test.

## Requirements

### Functional Requirements

- **FR-001**: A post-confirmation enrichment step MUST fetch per-alias
  capability metadata from a confirmed gateway — LiteLLM-shaped
  (`/model/info`, wildcard-expanded models) and Ollama-shaped (`/api/show`)
  — through an injectable transport, and MUST NOT send any credential before
  the operator has confirmed the endpoint and named its key env.
- **FR-002**: Aliases without usable metadata MUST be represented as
  unclassified with a detail naming what was tried; enrichment failure MUST
  never abort install by exception.
- **FR-003**: A requirements table keyed by persona name MUST exist as data,
  covering every LLM persona in the shipped example, and the proposal builder
  MUST derive (primary, fallback, reason) per persona from it — with the
  judge preferring independence from the implementer's primary, and
  unclassified aliases never auto-assigned.
- **FR-004**: When no candidate satisfies a persona's requirements, the
  proposal MUST say so naming the persona, the requirement and the aliases
  considered.
- **FR-005**: A judge canary probe MUST exist: toy diff + criteria + required
  JSON verdict schema, failing on prose, on schema violation, and on a PASS
  verdict for the known-bad diff, each with a distinct reason — running
  under the existing minted-key discipline
  (`factory/controlplane/verify.py:420-460`).
- **FR-006**: The interactive interview MUST present one pre-filled line per
  persona with the proposal and its reason; Enter accepts; the judge and
  every fallback require explicit confirmation and are exempt from any
  blanket-accept mechanism.
- **FR-007**: Every chosen gateway alias MUST pass its probe (1-token
  completion for all; canary additionally for the judge) before being
  written; a failed probe re-ranks and re-asks; nothing failed is written.
- **FR-008**: On an unsatisfiable persona the interview MUST exit nonzero
  with the persona, requirement and candidates in the message, leaving the
  seeded example registry on disk unchanged.
- **FR-009**: The written registry MUST differ from the shipped example only
  in `model` and `fallback` values; subscription personas are confirmed, not
  probed; deterministic personas are untouched.
- **FR-010**: `--non-interactive` and `--from-file` MUST keep today's
  behaviour unchanged (seed example, report unconfigured).

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-003, FR-004]
US3:
  depends_on: []
  implements: [FR-005]
US4:
  depends_on: []
  depends_on_merged: [US2, US3]
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
```

US1 (enrichment) and US3 (canary) touch disjoint modules and start in
parallel. US2 is pure functions over US1's record type. US4 wires the
interview and needs US2 and US3 merged.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste enrichment output for a rich gateway, a bare gateway and
  an Ollama endpoint — three shapes, one record type, unclassified stated.
- **SC-002**: Paste one full proposal with reasons, and one refusal naming
  persona, requirement and candidates.
- **SC-003**: Paste the canary passing a correct verdict and failing all
  three bad shapes with three distinct reasons.
- **SC-004**: Paste the end-to-end interview transcript: pre-filled lines,
  probes running, the written registry diffed against the example showing
  only alias fields changed, and `--verify` passing in the same run.

## Assumptions

- **LiteLLM's `/model/info` is reachable with the master key the operator
  just named.** Where a deployment restricts it, enrichment degrades to
  unclassified (FR-002) and the picker still works — worse proposals, same
  contract.
- **The probe cost is accepted**: one 1-token completion per chosen alias
  plus one canary call for the judge, the same order of cost `--verify`
  already spends per alias (`factory/controlplane/verify.py:466-480`).
- **A reasoning model may return an empty content field under a tight
  max_tokens** (operator memory, kimi incident). The canary sets an
  explicit, sufficient max_tokens; the 1-token completion probe keeps the
  existing `bool(choices)` check, which that incident does not break.
