---
state: draft
depends_on_landed:
  - 159-a-subscription-credential-has-one-durable-owner
fixes:
  - install/subscription-only-operator-cannot-verify-green
  - verify/direct-mode-config-raises-instead-of-reporting
---

# Feature Specification: a subscription is a starting position

## Provenance and corrected boundary

The original trio was drafted on 2026-08-27 against `3e5c940` and repeatedly
refined on 2026-09-04 against `602a92c`. Spec 125 subsequently landed Claude's
long-lived-token discovery and reporting. Specs 154–156 then split the runner
(`agent`) from the credential route (`route`), so the legacy
`agent: subscription` sentinel is no longer the form new code should write.

This refinement retains the distinct `llm.mode = "none"` goal without making
removal of the gateway a prerequisite for Codex-primary builders. The `llm`
block describes the control-plane inference service; persona `agent` and
`route` fields describe worker execution. A mixed factory may therefore keep a
gateway-routed judge while running builders through a Codex or Claude
subscription. Declaring `none` is valid for installation and honest capability
reporting, but it cannot make a gateway-dependent judge look available.

The stale `workgraph.json` beside this trio predates this refinement. It must be
replaced by a fresh derivation before any dispatch; it is not implementation
evidence.

### User Story 1 - The absent gateway is a declared control-plane position (Priority: P1)

As a subscription-only operator, I can persist and reload an installation that
does not claim a LiteLLM gateway exists.

**Acceptance Scenarios**:

1. **Given** `llm.mode = "none"`, **When** control-plane configuration is parsed and rendered, **Then** it round-trips to semantic configuration equality without gateway or direct fields and carries explicit text saying gateway inference, virtual-key isolation, enforced aliases, per-key usage, and the gateway-routed judge are unavailable — proven by parser and document round-trip tests.
2. **Given** a mode outside `gateway`, `direct`, and `none`, **When** it is parsed, **Then** the stable unknown-mode rule refuses it and names all supported values — proven by a table-driven negative test.
3. **Given** the existing `direct` declaration, **When** readiness gathers it, **Then** it returns a typed finding instead of raising an assertion — proven by an async probe regression test.

**Why this priority**: A subscription starting point cannot be expressed while the control plane requires a gateway-shaped block.

**Independent Test**: Parse, render, and probe synthetic `none`, `direct`, and invalid configurations without contacting a provider.

### User Story 2 - Readiness reports the capabilities each route actually has (Priority: P1)

As an operator, I receive one honest readiness report for a registry that mixes
gateway, Claude subscription, Codex subscription, and deterministic personas.

**Acceptance Scenarios**:

1. **Given** gateway mode and a mixed registry, **When** LLM readiness runs, **Then** only gateway-routed aliases are probed while subscription readiness is read from the shared credential-status boundary introduced by spec 159 — proven by a mixed-registry test.
2. **Given** `none` mode with a locally ready Claude token and structurally eligible but account-unqualified Codex state, **When** readiness runs, **Then** it preserves those distinct statuses, reports gateway facilities and any required gateway judge unavailable, and never returns vacuous green for an unqualified runner or verification loop — proven by separate onboarding and build-readiness assertions.
3. **Given** a Claude token with no credential file, **When** Claude subscription readiness and dispatch preflight run, **Then** the landed spec-125 token path remains usable; given an expired or absent source, the existing stable remedy remains byte-identical — proven by the spec-125 regression suites.
4. **Given** a Codex subscription route, **When** readiness runs, **Then** it consumes spec 159's shared non-secret status rather than inspecting `auth.json` again — proven by a test-double that makes a second discovery attempt fail.

**Why this priority**: Green must mean the declared runners can start, not merely that an alias set happened to be empty.

**Independent Test**: Evaluate a matrix of control-plane modes, runner/route pairs, credential states, and judge requirements through pure seams.

### User Story 3 - Installation writes the runner and route separately (Priority: P2)

As an operator, I can choose subscription builders without changing the judge's
gateway route or emitting a deprecated sentinel.

**Acceptance Scenarios**:

1. **Given** the install interview, **When** I select a worker CLI and credential route per persona, **Then** the written registry carries `agent: codex` or `agent: claude-code` independently from `route: subscription` or `route: gateway`, records a declared subscription model without gateway probing, labels its account availability unqualified, and never writes `agent: subscription` — proven by exact YAML/status assertions.
2. **Given** a Codex-primary builder selection, **When** the judge remains gateway-routed, **Then** the gateway questions and judge canary still run and the resulting mixed registry reloads — proven by an interview transcript test.
3. **Given** `llm.mode = "none"`, **When** a persona is left gateway-routed, **Then** the interview names the contradiction before writing and requires an explicit correction or abort — proven by a no-partial-write test.
4. **Given** an old registry carrying `agent: subscription`, **When** it is read and later written by an unrelated operation, **Then** the landed derivation preserves its Claude/subscription meaning, while newly selected or rewritten entries use the split form — proven by compatibility fixtures.

**Why this priority**: Subscription is a route, not an executable, and the installer must not recreate the ambiguity specs 154–156 removed.

**Independent Test**: Drive the interview with a recording prompter and reload its output through `load_personas`.

### User Story 4 - Persona membership comes from the registry (Priority: P2)

As an operator, I am asked about the personas the registry actually contains,
not a six-name tuple embedded in the installer.

**Acceptance Scenarios**:

1. **Given** a registry with an added persona, **When** install proposes gateway and subscription choices, **Then** the added persona participates according to its runner and route — proven by a seven-persona fixture.
2. **Given** a registry omitting one shipped persona, **When** install runs, **Then** no proposal, retry map, fallback loop, update, or report indexes the missing name — proven by a five-persona fixture that raises no `KeyError`.
3. **Given** the same registry bytes, scan results, and answers, **When** the interview runs twice, **Then** prompt order and written output are identical — proven by a deterministic transcript assertion.

**Why this priority**: A hard-coded persona list makes the runner/route model nominal rather than extensible.

**Independent Test**: Run the interview against registries with added, absent, deterministic, gateway, and subscription entries.

## Functional Requirements

- **FR-001**: `llm.mode` MUST accept exactly `gateway`, recognized-but-refused `direct`, and `none`.
- **FR-002**: A `none` control-plane configuration MUST carry no gateway or direct credential fields and MUST round-trip to semantic configuration equality.
- **FR-003**: The `none` report MUST enumerate the unavailable gateway properties and MUST distinguish install validity from verification-loop readiness.
- **FR-004**: Direct-mode verification MUST produce a stable typed finding and MUST NOT assert.
- **FR-005**: Gateway probes MUST derive aliases only from personas whose effective route is `gateway`.
- **FR-006**: Subscription readiness MUST consume the shared credential-status boundary from spec 159 once per effective rung.
- **FR-007**: Claude token-only behavior and the stable Claude remediation text landed by spec 125 MUST remain intact.
- **FR-008**: A required gateway-routed judge under `llm.mode = "none"` MUST be reported unavailable and MUST prevent a build-readiness green.
- **FR-009**: New registry writes MUST encode the runner in `agent` and credential delivery in `route`; they MUST NOT write `agent: subscription`.
- **FR-010**: Legacy `agent: subscription` MUST continue to derive as Claude Code over the subscription route.
- **FR-011**: Selecting subscription builders MUST NOT implicitly change a gateway-routed judge or remove the gateway configuration.
- **FR-012**: A `none` interview MUST refuse to write while any active LLM persona remains gateway-routed.
- **FR-013**: Persona interview membership and order MUST derive deterministically from the loaded registry, not `_GATEWAY_PERSONA_ORDER`.
- **FR-014**: Retry, proposal, fallback, update, and report collections MUST share that derived membership.
- **FR-015**: Subscription model names MUST be stored as operator declarations without gateway probing, and account/model availability MUST remain unqualified until spec 161's real pilot proves it.
- **FR-016**: Usage for subscription attempts MUST remain unknown unless the attempt evidence supplies a supported value.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-016]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-009, FR-010, FR-011, FR-012, FR-015]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-013, FR-014]
```
