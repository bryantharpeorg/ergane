# Implementation Plan: a subscription is a starting position

## Landed seams to preserve

- `factory/config.py:180` — `derive_agent_and_route` is the compatibility table for old `agent: subscription` entries.
- `factory/config.py:196` — `effective_route` makes an explicit route authoritative and falls back only for old payloads.
- `factory/config.py:233` — `Persona` already keeps runner and route as separate axes.
- `KNOWN_LLM_MODES` in `factory/controlplane/config.py` owns the closed control-plane mode tuple; `factory/controlplane/config.py:363` — `_read_llm` is the pure parser seam.
- `factory/controlplane/verify.py:400` — `gather_gateway_aliases` already filters on effective gateway routing.
- `factory/controlplane/verify.py:422` — `LLMProbe` still assumes every parsed config has a gateway, and `factory/controlplane/verify.py:662` — `LLMProbe.evaluate` deliberately rejects an empty result set.
- `_GATEWAY_PERSONA_ORDER` in `factory/cli/install.py` is the hard-coded tuple read by proposal, retry, fallback, update, and reporting paths inside `factory/cli/install.py:567` — `_interview_personas`.
- `factory/cli/install.py:1556` — `_ask_llm` owns control-plane mode questions; do not turn that answer into a persona runner.
- `CLAUDE_CODE_OAUTH_TOKEN` in `factory/workgraph/adapter.py` preserves Claude's long-lived-token environment name, and `factory/workgraph/adapter.py:907` — `discover_subscription_credential` is the Claude file fallback that spec 125 landed.
- Spec 159 introduces the shared Codex credential-status boundary. This trio consumes it and must not add another `auth.json` reader.

## Story slices

### US1 — Parser and non-throwing probe

Add a `none` value to the closed mode model, a declaration object carrying the
human-readable surrendered properties, and exact render/parse behavior. Branch
the LLM probe before reading a gateway. Direct remains recognized and refused
for dispatch, but verification converts that state into a finding instead of an
assertion.

### US2 — Route-aware readiness

Separate configuration validity, runner credential readiness, and verification
loop readiness in the snapshot/evaluation data. Gateway aliases still use the
existing one-token probe. Claude and Codex subscription routes use the shared
status contracts; deterministic personas need neither. The build-readiness view
must name a gateway-routed judge as unavailable under `none` even when builders
are ready.

### US3 — Mixed-route interview

Offer runner and route independently for each LLM persona. Keep gateway
discovery, model probing, and the judge canary for gateway routes. Store
operator-declared CLI model names without gateway probing for subscription routes
and report account availability unqualified until 161's pilot. Validate the
whole proposed registry before the atomic write. Preserve unrelated legacy
sentinel bytes where no migration is requested.

### US4 — Registry-derived membership

Replace every consumer of `_GATEWAY_PERSONA_ORDER` in the persona interview with
one ordered view derived from the loaded registry. Preserve source order and
filter by effective runner/route only where the operation requires it. Delete
the tuple only after a search proves no consumer remains.

## Traps

1. **`none` does not mean no agents.** It means no control-plane gateway; subscription runners remain real.
2. **The judge remains gateway inference today.** A ready builder credential cannot make the full verification loop green without that judge.
3. **Do not roll back D-053/spec 154.** `agent: subscription` is read compatibility, never a new-write format.
4. **Do not re-implement spec 125.** Claude token precedence, bwrap delivery, and remedy wording are landed contracts.
5. **Do not inspect Codex auth twice.** Spec 159 owns discovery, staging, finalization, and status publication.
6. **Do not make the gateway disappear by default.** Codex-primary builders and a gateway judge are a supported mixed position.
7. **Empty alias sets have two meanings.** A deliberate no-gateway declaration is valid configuration; an unrunnable required judge is not ready.
8. **No partial registry writes.** Validate every proposed runner/route/model combination before replacing the file.
9. **Usage stays honest.** Subscription attempts do not inherit a fabricated per-key spend value.
10. **The existing compiled graph is stale.** Re-derive it from this trio before dispatch and verify four nodes carry FR-001 through FR-016.

## Verification

Run the new parser/probe tests, the full control-plane mode suite, the spec-125
credential suites, the spec-154 runner/route suites, and the install walkthrough
tests. Then run the declared repository gate, derive this trio anew, inspect its
four nodes and requirement keys, and run `git diff --check`.
