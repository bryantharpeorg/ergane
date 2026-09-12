# Tasks: each Codex attempt owns its evidence

Use the landed neutral result and preserve all fields generically; spec 159 is
not a dependency. Write tests first; no real model turn is part of this epic.

## Phase 1: User Story 1 — A decoder identifies one current Codex execution

- [ ] [US1-S1] Add official-shape failing JSONL fixtures and typed assertions for thread, turn, items, agent messages, fatal events, and usage in `tests/test_codex_events.py`; use the plan's measured0.154.0 error shapes, distinguish diagnostic error items, and accept normal items without repeated thread identifiers.
- [ ] [US1-S2] Add failing malformed, unknown, missing-thread, duplicate-terminal, and cross-thread cases requiring incomplete diagnostics and no fabricated evidence. Include an otherwise valid stream with `{"type":"item.completed","item":"bad"}` and require a stable malformed-known-event reason rather than silent success.
- [ ] [US1-S3] Add token-pattern fixtures and failing redaction/bounding tests for orchestration serialization while retaining a caller-owned raw spool.
- [ ] [US1-S4] Add failing usage-shape fixtures for JSON boolean, negative, fractional, string, object, and list values. Prove `{"input_tokens":true,"output_tokens":2}` cannot publish `True`/`1`, marks evidence incomplete/invalid with a stable malformed-usage reason, and preserves valid sibling counts only when the evidence model can represent their partial provenance honestly.
- [ ] [US1] Implement the pure streaming decoder and frozen evidence models in `factory/workgraph/codex_events.py`.

## Phase 2: User Story 2 — The adapter archives only this attempt's execution as current evidence

- [ ] [US2-S1] Add a failing persistent-home test with a prior rollout and a new pre-thread configuration failure around `CodexAdapter._turn_happened`.
- [ ] [US2-S2] Add fake processes emitting thread/turn starts, diagnostic error items, and fatal401 or missing-key events without model activity; retain protocol identity/raw archival while requiring false `agent_took_a_turn` and no final message.
- [ ] [US2-S3] Add normal, timeout, cancellation, and redelivered-finalization archive tests for one attempt identity.
- [ ] [US2-S4] Extend adapter conformance tests so Claude and all neutral consumers receive the same plain `AdapterResult` shape.
- [ ] [US2-S5] Add failing HostAgentBackend and BwrapBackend tests with valid stdout JSONL interleaved in time with ordinary stderr; assert separate exact archive files and unchanged Claude combined logging.
- [ ] [US2-S6] Add failing mode-0600, declared size/retention, truncation-completeness, and no-git/workflow/public-artifact tests for both raw files.
- [ ] [US2] Run Codex with `--json`, create separate current event/diagnostic spools before launch, decode stdout only, and replace rollout-existence turn detection in `factory/workgraph/adapter.py`.
- [ ] [US2] Extend `AgentInvocation`, `HostAgentBackend`, and `BwrapBackend` with adapter-selected combined versus separate output policies.

## Phase 3: User Story 3 — Refusals and questions come from typed current events

- [ ] [US3-S1] Add failing non-auth exits quoting401 in reasoning, tool output, fixtures, and the measured400 fatal error body.
- [ ] [US3-S2] Add the measured typed fatal-auth error/turn.failed pair with surrounding diagnostics and assert exactly one pre-agent refusal without rung charge; do not fabricate numeric status fields absent from the measured events.
- [ ] [US3-S3] Add failing question-marker controls for every non-agent item and non-final agent-message position.
- [ ] [US3-S4] Add a field-enumerating preservation test over every current `AdapterResult` field so new fields enter the assertion automatically; do not require future spec 159 fields.
- [ ] [US3] Refactor `_classify_auth_failure`, pre-agent detail, and question detection in `factory/activities/agent_activities.py` to consume typed evidence and preserve fields.

## Phase 4: User Story 4 — Codex usage evidence is recorded without inventing subscription cost

- [ ] [US4-S1] Add failing documented-usage mapping and no-double-count tests in `tests/test_codex_usage_evidence.py`.
- [ ] [US4-S2] Add missing, partial, failed, and multiple-terminal fixtures requiring unknowns, incomplete provenance, and unavailable subscription dollars.
- [ ] [US4-S3] Add a two-source gateway test proving LiteLLM remains authoritative and CLI usage stays separate corroboration.
- [ ] [US4] Implement usage normalization and the minimum storage/model extension in `factory/usage/` and `factory/activities/usage_activities.py`.

## Verification

- [ ] Run focused decoder, adapter, question, credential-provenance, usage, 154, and 155 tests, then the declared repository gate.
- [ ] Inspect archive idempotency and run credential sweeps over committed fixtures, result JSON, and rendered errors.
