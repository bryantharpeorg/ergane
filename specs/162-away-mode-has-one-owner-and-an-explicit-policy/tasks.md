# Tasks: away mode has one owner and an explicit policy

Do not enable a live monitor or scheduler while implementing this epic. All
tests use temporary state and injected fakes.

## Phase 1: User Story 1 — Enabling away mode creates one durable, bounded authority

- [ ] [US1-S1] Add failing start/parser/store tests for explicit target, deadline, notification intent, allowlist, owner/run id, and deny-by-default behavior in `tests/test_away_policy.py`.
- [ ] [US1-S2] Add a table-driven failing refusal test for every prohibited authority.
- [ ] [US1-S3] Add a concurrent-start test proving one owner and a redacted refusal/remedy for the second client.
- [ ] [US1-S4] Add fixed-clock absent, expired, and excessive-deadline tests requiring refusal or durable stop with no binding call.
- [ ] [US1] Implement models/store/start/status in `factory/operator/away.py` and the `ergane away` noun without a scheduler implementation.

## Phase 2: User Story 2 — Each tick observes before one generic journaled action

- [ ] [US2-S1] Add ordered-call tests requiring read-only observation and cursor persistence before any action executor can run.
- [ ] [US2-S2] Add one generic fake-action failing intent/result/idempotency/replay test for the journal mechanism.
- [ ] [US2-S3] Add policy-matrix no-call tests for omitted, held, unprovable, and prohibited actions.
- [ ] [US2] Implement `tick` over typed observers and one injected executor, short transactions, and the generic action journal in `factory/operator/away.py`.

## Phase 3: User Story 5 — Typed actions and notifications obey closed evidence policies

- [ ] [US5-S1] Add a failing closed table for all five allowed actions naming typed command, current evidence, idempotency identity, and forbidden state; deny workflow-internal calls.
- [ ] [US5-S2] Add failing builder-question fixtures for exact current authoritative facts and abstention on ambiguous, stale, free-form, tradeoff, and escalation-choice inputs.
- [ ] [US5-S3] Add quiet unchanged-tick tests with a notifier that fails if called.
- [ ] [US5-S4] Add meaningful-change/completion/failure/abstention/user-action notification and deduplication tests.
- [ ] [US5] Implement the five typed adapters and notification intents on top of US2's generic journal.

## Phase 4: User Story 3 — Each client binding declares what it can actually schedule

- [ ] [US3-S1] Add a failing Codex desktop task-definition fixture test under `.agents/skills/away-mode/`, including project, owner, target, deadline, allowed actions, quiet policy, stop conditions, and `definition rendered` state only.
- [ ] [US3-S2] Add Codex CLI/IDE capability fixtures requiring unavailable plus the explicit `ergane away tick` fallback.
- [ ] [US3-S3] Add Claude binding fixtures and normalized-policy equivalence tests.
- [ ] [US3-S4] Add missing/failing scheduler and notification binding tests requiring no authority widening and a visible fallback.
- [ ] [US3-S5] Add a failing live-qualification evidence parser/state test requiring separately observed `binding created` then `verified fired/notified`; fixtures cannot activate the run.
- [ ] [US3] Rewrite the canonical away skill and client references; keep all scheduler tool syntax outside production Python.

## Phase 5: User Story 4 — Stop and recovery outlive client restarts

- [ ] [US4-S1] Add crash-point tests requiring durable stop before cancel on explicit stop, expiry, and completion; later ticks must be no-ops.
- [ ] [US4-S2] Add before/after action and notification crash tests requiring journal reconciliation without duplication or loss.
- [ ] [US4-S3] Add a failed-cancel test that preserves stopped state and reports binding cleanup separately.
- [ ] [US4-S4] Add a simultaneous dual-client tick test requiring one claim, one quiet exit, and persistent ownership.
- [ ] [US4] Implement stop, recovery, in-doubt reconciliation, and short tick claims in `factory/operator/away.py` and the CLI noun.

## Verification

- [ ] Run focused away policy/store/CLI/skill tests, then the declared repository gate.
- [ ] Prove tests contacted no operational store or external service and that no automation was created or enabled.
