# Tasks: a subscription is a starting position

Write the tests in each story before its production edit. Do not configure a
real client, read a live credential, or contact a provider in these tasks.

## Phase 1: User Story 1 — The absent gateway is a declared control-plane position

- [ ] [US1-S1] Add failing parse/render tests for an exact `llm.mode = "none"` block and its declared surrendered-properties text.
- [ ] [US1-S2] Add failing invalid-mode tests that pin the supported token list and stable rule.
- [ ] [US1-S3] Add a failing async regression test proving direct-mode gather returns a typed finding rather than raising.
- [ ] [US1] Extend the closed LLM mode/config model and branch `factory/controlplane/config.py:363` — `_read_llm` without weakening gateway or direct validation.
- [ ] [US1] Extend `factory/controlplane/verify.py:422` — `LLMProbe` with explicit `none` and direct snapshots and stable evaluation detail.

## Phase 2: User Story 2 — Readiness reports the capabilities each route actually has

- [ ] [US2-S1] Add a failing mixed-registry test proving only gateway routes reach the gateway alias probe and each subscription effective rung is checked once.
- [ ] [US2-S2] Add failing onboarding-versus-build assertions for `none`, locally ready Claude, structurally eligible/account-unqualified Codex, and a required gateway judge.
- [ ] [US2-S3] Add a focused failing regression fixture in this story's diff that pins Claude token-only absence handling and exact landed remedy bytes, then run `tests/test_us1_long_lived_token.py` and `tests/test_125_us3_credential_runway.py` as controls.
- [ ] [US2-S4] Add a failing Codex-status test whose discovery double raises if readiness reads credentials instead of consuming spec 159's result.
- [ ] [US2] Extend the LLM snapshot and report model so gateway, runner credential, and judge capability are distinct and deterministic.
- [ ] [US2] Preserve unknown subscription usage in the shared report; do not synthesize a currency or token figure.

## Phase 3: User Story 3 — Installation writes the runner and route separately

- [ ] [US3-S1] Add a failing exact-YAML/status test for independent Codex/Claude runner and gateway/subscription route choices, declared-but-unqualified subscription models, and rejection of new `agent: subscription` writes.
- [ ] [US3-S2] Add a failing mixed Codex-builder/gateway-judge transcript test that retains gateway questions and the judge canary.
- [ ] [US3-S3] Add a failing `none` contradiction test proving no partial write occurs while a persona remains gateway-routed.
- [ ] [US3-S4] Add a legacy fixture proving unrelated operations preserve the derived Claude/subscription meaning.
- [ ] [US3] Refactor `factory/cli/install.py:567` — `_interview_personas` to gather runner, route, and model choices separately and atomically validate the result.
- [ ] [US3] Keep gateway probing confined to gateway routes and keep subscription model validation at the selected CLI boundary.

## Phase 4: User Story 4 — Persona membership comes from the registry

- [ ] [US4-S1] Add a failing seven-persona test proving the added persona enters the appropriate proposal and report paths.
- [ ] [US4-S2] Add a failing five-persona test proving every loop and mapping tolerates a missing shipped persona.
- [ ] [US4-S3] Add a failing repeat-run assertion for deterministic prompt order and YAML bytes.
- [ ] [US4] Derive the shared ordered persona view from the loaded registry and replace every reader of `_GATEWAY_PERSONA_ORDER` in `factory/cli/install.py`.
- [ ] [US4] Remove the hard-coded tuple only after `rg` proves proposal, retry, fallback, update, and reporting paths share the derived view.

## Verification

- [ ] Run the focused control-plane, subscription credential, runner/route, and install walkthrough suites, then the declared repository gate.
- [ ] Re-derive `workgraph.json`, verify four story nodes and FR-001…FR-016 coverage, and run `git diff --check`.
