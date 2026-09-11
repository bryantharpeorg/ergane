# Tasks: a subscription credential has one durable owner

The operator approved the separate factory session and host-global serialized
owner design on 2026-09-09; the private pilot remains unnamed and unqualified.
Do not perform login, read a real credential, contact OAuth, or run account-backed
qualification in this epic.

## Phase 1: User Story 1 — Subscription means validated managed ChatGPT authentication

- [ ] [US1-S1] Replace the API-key-shaped control with real-shape synthetic managed, API-key, external-token, malformed, missing-refresh, and inaccessible fixtures; write failing parser/refusal tests for `factory/workgraph/codex_credential.py`.
- [ ] [US1-S2] Add a failing explicit-missing-versus-interactive-fallback filesystem test around `factory/workgraph/adapter.py:943` — `discover_codex_credential`.
- [ ] [US1-S3] Add fixed-clock/status tests distinguishing expired access with structurally present refresh data, locally missing/malformed refresh data, and a prior Codex provider-rejection record; offline results say eligible-to-attempt rather than usable.
- [ ] [US1-S4] Add failing redacted provenance serialization and credential-sweep tests.
- [ ] [US1] Implement pure declaration, managed-auth validation, readiness, and redacted provenance; integrate `CodexAdapter._credential` without reading token values into workflow records.

## Phase 2: User Story 2 — One credential owner serializes the effective subscription rung

- [ ] [US2-S1] Add a failing two-epic/two-target/two-deployment test proving one declared credential identity resolves to one host-global operator-state owner.
- [ ] [US2-S2] Add a failing mixed gateway/subscription scheduling test proving gateway progress while ownership is busy.
- [ ] [US2-S3] Add failing bidirectional effective-rung transition tests for ordinary retry and landing recovery.
- [ ] [US2-S4] Add a time-skipping cancellation-before-admission test with zero attempt/lease/child/candidate changes.
- [ ] [US2-S5] Add failing owner-host and duplicate-root tests; do not simulate serialization with target-local locks.
- [ ] [US2-S6] Add failing group/world-mode, symlink, wrong-owner, and post-declaration owner-root replacement tests.
- [ ] [US2-S7] Add configuration-driven tests for automatic gateway-to-Codex-subscription promotion using the frozen persona snapshot, with absent/disabled/exhausted negative controls; deny any newly introduced per-use confirmation and preserve existing ladder order, caps, and failure escalation.
- [ ] [US2] Implement short owner transactions and replay-safe BUSY waiting at the actual rung boundary; remove credential safety reliance from `_subscription_nodes_in_flight`.

## Phase 3: User Story 3 — An attempt is fenced before route state can change

- [ ] [US3-S1] Add ordered-call tests that fail unless old-process reap or fencing precedes candidate inspection, including a surviving orphan refusal.
- [ ] [US3-S2] Add same-home gateway-to-subscription-to-gateway tests around `_seed_codex_config` and staged auth cleanup.
- [ ] [US3-S3] Add parameterized normal, nonzero, timeout, and cancellation ordering tests requiring current process-group termination, proven reap/fence, then candidate read; retain recovery ownership on failed fencing.
- [ ] [US3] Implement prior/current child fencing and exact route materialization in `factory/workgraph/codex_credential.py` and `factory/workgraph/adapter.py`.

## Phase 4: User Story 5 — Refresh results become the next durable generation

- [ ] [US5-S1] Add parameterized termination tests requiring a fenced, structurally eligible candidate to promote atomically before owner release.
- [ ] [US5-S2] Add crash-point tests for journal intent, validation, atomic promote, and release, including malformed/wrong-mode/stale/prior-provider-rejected quarantine and no silent bootstrap restore.
- [ ] [US5-S3] Add a denied OAuth/network seam and source guard proving only the Codex child can refresh.
- [ ] [US5-S4] Add replay/idempotency tests proving each candidate commits or quarantines once and owner release follows its durable outcome.
- [ ] [US5] Implement owner journaling, finalization, quarantine, and recovery after US3's fence contract.

## Phase 5: User Story 4 — Readiness explains the same credential contract everywhere

- [ ] [US4-S1] Add table-driven failing status tests for Claude subscription, Codex subscription, gateway, and no-runner in `factory/workgraph/credential_status.py`.
- [ ] [US4-S2] Add contract tests feeding structurally eligible/unqualified, busy, invalid, recoverable, provider-rejected, host/root-mismatch, and missing-source states through install, preflight, and `factory/cli/nouns/build.py:1208` — `credential_status_command`.
- [ ] [US4-S3] Add renderer tests for complete, partial and absent subscription runner measurements without a gateway row. Preserve landed source/status/cost provenance and measured subtotals, unknown optional metrics and unavailable subscription dollars; independently vary auth readiness so it never supplies usage evidence.
- [ ] [US4] Implement the shared runner-aware status model and migrate all three consumers without duplicating auth parsers.

## Verification

- [ ] Run focused credential, adapter, workflow, control-plane, build-status, and spec-125/154/155 regression tests, then the declared gate.
- [ ] Run `git diff --check`, a token-pattern sweep, and crash-point cleanup checks; confirm no real credential or operational runtime store was opened.
