---
state: draft
---

# Feature Specification: each Codex attempt owns its evidence

## Provenance and boundary

This spec closes audit finding F4 and carries the attempt-evidence half of work
package D. Landed spec 155 proves Codex can launch; it does not prove that a
persistent node home's rollout files belong to the attempt currently being
classified. This spec replaces existence and substring heuristics with a small
Codex JSONL decoder while preserving the neutral `AdapterResult` boundary and
Claude behavior.

The 2026-09-09 scope clarification prioritizes Codex through the gateway to
Ollama Cloud. This evidence contract applies to either credential route and
consumes the existing landed neutral result. It does not wait for subscription
ownership in 159; future fields must survive the same generic preservation
contract when introduced.

Official non-interactive documentation defines `codex exec --json` as a JSONL
event stream with thread, turn, item, error, and usage events; agent messages are
distinct from reasoning, command execution, file changes, MCP calls, web search,
and plan updates. Those typed events are the evidence surface used here.

### User Story 1 - A decoder identifies one current Codex execution (Priority: P1)

As the adapter, I turn one Codex JSONL stream into typed, redacted evidence tied
to the thread and turn that this process started.

**Acceptance Scenarios**:

1. **Given** a valid stream containing `thread.started`, turn events, reasoning, command output, file changes, agent messages, usage, and errors, **When** it is decoded, **Then** the result carries the current thread id, turn outcome, ordered agent messages, typed fatal events, and usage separately from every diagnostic item — proven by official-shape fixture tests.
2. **Given** malformed JSON, unknown future event types, a missing thread start, duplicate terminal events, or events for a different thread, **When** decoding completes, **Then** raw lines remain archived, known evidence is retained, and the decoder reports a stable incomplete/invalid reason without fabricating a turn or message — proven by parameterized tests.
3. **Given** token-shaped text appears in any event, **When** the neutral evidence is serialized or logged, **Then** the raw archive remains host-local while every orchestration-facing field is redacted and bounded — proven by credential-sweep tests.

**Why this priority**: Every later classification is only as accurate as the event identity it consumes.

**Independent Test**: Decode fixed JSONL fixtures without running Codex or reading a rollout directory.

### User Story 2 - The adapter archives only this attempt's execution as current evidence (Priority: P1)

As an operator inspecting an attempt, I can distinguish its raw stream and final
message from older node-home rollouts and startup-only failures.

**Acceptance Scenarios**:

1. **Given** a prior rollout exists and a new Codex launch fails before `thread.started`, **When** the new attempt is classified and archived, **Then** it says no current turn occurred and does not copy or cite the prior rollout as this attempt's evidence — proven by a persistent-home regression test.
2. **Given** a fresh process emits startup bookkeeping, diagnostic items, and a fatal error but no model-authored activity, including a credential refusal after `thread.started` and `turn.started`, **When** it exits, **Then** the raw stream and protocol identity are archived but `agent_took_a_turn` and final-message evidence remain false/absent — proven by fixture process tests.
3. **Given** a normal, timed-out, or cancelled process has started a current thread, **When** archival runs, **Then** stdout/stderr, JSONL, final message if any, thread id, termination, and attempt identity land in exactly this attempt's archive even when finalization is retried — proven by parameterized archive tests.
4. **Given** existing neutral consumers and the Claude adapter, **When** Codex switches to JSONL, **Then** they continue receiving plain final-message evidence and the same `AdapterResult` contract rather than raw JSON events — proven by adapter conformance tests.
5. **Given** valid stdout JSONL and ordinary stderr diagnostics interleaved in time, **When** host and bwrap backends launch Codex, **Then** only stdout feeds `codex-events.jsonl` and the decoder, stderr feeds `codex-stderr.log`, and Claude retains its existing combined-log policy — proven by production-backend launch tests.
6. **Given** either raw Codex file, **When** it is archived, retained, or a size/retention limit is reached, **Then** it is mode `0600`, remains host-local under the current attempt, records truncation/completeness explicitly, and is excluded from git, workflow payloads, and public qualification artifacts — proven by filesystem and serialization tests.

**Why this priority**: A previous successful rollout currently makes a later startup failure look like work happened.

**Independent Test**: Reuse one node home across two attempts and inspect only the second attempt archive and result.

### User Story 3 - Refusals and questions come from typed current events (Priority: P1)

As the workflow, I respond only to actual fatal authentication events and actual
agent messages from the current attempt.

**Acceptance Scenarios**:

1. **Given** a non-authentication nonzero exit whose reasoning, tool output, or non-authentication fatal error body quotes a historical 401 refusal, **When** classification runs, **Then** it remains an ordinary agent failure and retains all credential provenance — proven by quoted-marker controls.
2. **Given** a current fatal authentication event with surrounding diagnostics, **When** classification runs, **Then** it becomes the stable pre-agent authentication refusal once, with the typed event retained and no coding rung charged — proven by an actual-event fixture.
3. **Given** an operator-question marker appears in reasoning, tool output, a test fixture, or an agent message that does not end with the marker contract, **When** question detection runs, **Then** the node does not park; only the current final agent message satisfying the landed marker grammar can ask — proven by controls for every item type.
4. **Given** classification reconstructs an `AdapterResult`, **When** any failure class changes, **Then** every unrelated field, including existing session identity, credential source, usage, archive path, final message, and raw-event provenance, remains byte-equivalent and newly added fields are covered automatically — proven by a field-enumerating preservation test.

**Why this priority**: A quoted error or marker must not change node state.

**Independent Test**: Feed typed evidence directly to classification with no filesystem scan.

### User Story 4 - Codex usage evidence is recorded without inventing subscription cost (Priority: P2)

As an operator comparing attempts, I see the token counts Codex emitted, their
provenance and completeness, while dollar cost remains unavailable on subscription.

**Acceptance Scenarios**:

1. **Given** a completed turn event with input, cached input, output, and reasoning output tokens, **When** evidence is normalized, **Then** each supported count and its current-attempt source are recorded with no double-counting against LiteLLM gateway rows — proven by fixture and aggregation tests.
2. **Given** missing usage, partial usage, a failed turn, or multiple turn terminals, **When** a subscription result is recorded, **Then** unobserved fields remain unknown, completeness is false where appropriate, and `spend_usd` remains unavailable rather than zero — proven by parameterized ledger tests.
3. **Given** a gateway Codex attempt, **When** both JSONL token evidence and LiteLLM attribution exist, **Then** the ledger keeps the gateway's authoritative spend path and stores CLI evidence as separate corroboration rather than adding the values — proven by a two-source test.

**Why this priority**: Honest subscription evidence improves comparison without pretending plan value is a per-attempt dollar amount.

**Independent Test**: Normalize usage fixtures into a temporary ledger and compare gateway versus subscription source selection.

## Functional Requirements

- **FR-001**: Codex automation MUST use its JSONL event stream as the current-execution evidence source.
- **FR-002**: The decoder MUST separate thread identity, turn outcome, agent messages, diagnostics/tools, fatal errors, and usage.
- **FR-003**: Unknown or malformed events MUST remain in the raw archive and MUST NOT fabricate a turn, message, refusal, question, or usage value.
- **FR-004**: Orchestration-facing event evidence MUST be redacted and bounded; raw events MUST remain host-local.
- **FR-005**: Rollout files predating the current process MUST NOT count as current-attempt evidence or be copied as such.
- **FR-006**: Error-only execution MUST NOT set `agent_took_a_turn` or fabricate a final message; thread/turn startup bookkeeping and diagnostic error items alone MUST NOT prove model-authored activity.
- **FR-007**: Normal, timeout, cancellation, and retry-finalization archives MUST retain exactly one current attempt identity.
- **FR-008**: The neutral `AdapterResult` and Claude conformance MUST remain compatible.
- **FR-009**: Authentication refusal classification MUST consume typed fatal current events, not substrings in combined output.
- **FR-010**: Operator-question detection MUST consume only the current final agent message under the landed marker grammar.
- **FR-011**: Reclassification MUST preserve every unrelated result and credential-provenance field.
- **FR-012**: Pre-agent authentication failure MUST spend no coding rung.
- **FR-013**: Supported Codex usage counts MUST carry source and completeness metadata.
- **FR-014**: Missing or partial usage MUST remain unknown and subscription dollars MUST remain unavailable.
- **FR-015**: Gateway ledger usage MUST remain authoritative; CLI usage MUST NOT be added to it.
- **FR-016**: `AgentInvocation`, `HostAgentBackend`, and `BwrapBackend` MUST support an adapter-selected output policy that separates Codex stdout JSONL from stderr diagnostics while preserving Claude's combined log.
- **FR-017**: Raw `codex-events.jsonl` and `codex-stderr.log` MUST be current-attempt, host-local, mode `0600`, governed by declared size/retention values with explicit incompleteness, and MUST NOT enter git, workflow payloads, or public qualification artifacts.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-016, FR-017]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010, FR-011, FR-012]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-013, FR-014, FR-015]
```
