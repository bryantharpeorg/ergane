# Tasks: each Codex attempt owns its evidence

Use the landed neutral result and preserve all fields generically; spec 159 is
not a dependency. Write tests first; no real model turn is part of this epic.

## Phase 1: User Story 1 — A decoder identifies one current Codex execution

- [ ] [US1-S1] Add official-shape failing JSONL fixtures and typed assertions for thread, turn, items, agent messages, fatal events, and usage in `tests/test_codex_events.py`.
- [ ] [US1-S2] Add failing malformed, unknown, missing-thread, duplicate-terminal, and cross-thread cases requiring incomplete diagnostics and no fabricated evidence.
- [ ] [US1-S3] Add token-pattern fixtures and failing redaction/bounding tests for orchestration serialization while retaining a caller-owned raw spool.
- [ ] [US1] Implement the pure streaming decoder and frozen evidence models in `factory/workgraph/codex_events.py`.

## Phase 2: User Story 2 — The adapter archives only this attempt's execution as current evidence

- [ ] [US2-S1] Add a failing persistent-home test with a prior rollout and a new pre-thread startup failure around `CodexAdapter._turn_happened`.
- [ ] [US2-S2] Add a fake process emitting only an error event; require raw archival and absent turn/final message.
- [ ] [US2-S3] Add normal, timeout, cancellation, and redelivered-finalization archive tests for one attempt identity.
- [ ] [US2-S4] Extend adapter conformance tests so Claude and all neutral consumers receive the same plain `AdapterResult` shape.
- [ ] [US2-S5] Add failing HostAgentBackend and BwrapBackend tests with valid stdout JSONL interleaved in time with ordinary stderr; assert separate exact archive files and unchanged Claude combined logging.
- [ ] [US2-S6] Add failing mode-0600, declared size/retention, truncation-completeness, and no-git/workflow/public-artifact tests for both raw files.
- [ ] [US2] Run Codex with `--json`, create separate current event/diagnostic spools before launch, decode stdout only, and replace rollout-existence turn detection in `factory/workgraph/adapter.py`.
- [ ] [US2] Extend `AgentInvocation`, `HostAgentBackend`, and `BwrapBackend` with adapter-selected combined versus separate output policies.

## Phase 3: User Story 3 — Refusals and questions come from typed current events

- [ ] [US3-S1] Add failing non-auth exits quoting 401 in reasoning, tool output, and fixtures.
- [ ] [US3-S2] Add a failing typed fatal-auth event with surrounding output and assert pre-agent refusal without rung charge.
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
