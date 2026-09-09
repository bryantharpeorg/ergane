# Tasks: operator skills report and act by declared intent

Spec 087 must land first so all edits target the canonical packaged skill tree.
Write tests first and use only temporary stores and repositories.

## Phase 1: User Story 1 — Floor and escalation reports are pure observations

- [ ] [US1-S1] Add routing/dispatch/provenance fixtures and failing renderer tests for `.agents/skills/floor-status/`.
- [ ] [US1-S2] Add denied mutation fakes plus a static command sweep that fails on implicit fetch, merge, push, dispatch, attestation, answer, findings write, or service action.
- [ ] [US1-S3] Add failing actual-choice and no-answer tests for `.agents/skills/escalation-triage/`.
- [ ] [US1] Refactor both skill documents and any deterministic helpers to consume the read-only build/attempt/escalation surfaces.
- [ ] [US1] Record one concise fixture transcript showing unavailable services remain unavailable and no action seam was called.

## Phase 2: User Story 2 — Build metrics preserve identity and unknown quantities

- [ ] [US2-S1] Add a failing two-dispatch fixture to `.agents/skills/build-metrics/scripts/rework.py` tests and assert both executions survive grouping.
- [ ] [US2-S2] Add failing empty-ledger, legacy-dimension, and unknown-usage cases.
- [ ] [US2-S3] Add a network-denied failing test for `.agents/skills/build-metrics/scripts/loc.py`, including unique scratch paths and unavailable local tools.
- [ ] [US2] Implement runtime-root discovery, dispatch-aware grouping, unknown rendering, empty input handling, and the stable local LOC boundary.
- [ ] [US2] Remove mutable remote execution and dated undifferentiated figures from the default report.

## Phase 3: User Story 3 — A rendered spec carries the validator's actual verdict

- [ ] [US3-S1] Add a failing `SpecValidation` fixture test covering refusal, advisory, and skipped layers in `.agents/skills/spec-html/`.
- [ ] [US3-S2] Add failing empty, unavailable, and error landing-result tests.
- [ ] [US3-S3] Add a filesystem-difference test proving local-only output absent explicit publication intent.
- [ ] [US3] Replace duplicate validation in the renderer with `factory.spec.validate_spec` and a tagged landing-read result.
- [ ] [US3] Update the skill contract to return a local path and describe publication as a separate authorized action.

## Phase 4: User Story 4 — Historical findings remain historical

- [ ] [US4-S1] Add failing parser/model/store round-trip tests for observation identity, observed time, and ingestion time in `factory/doctor/models.py` and `factory/doctor/store.py`.
- [ ] [US4-S2] Add a failing duplicate-ingestion test proving recurrence and `last_seen` do not advance.
- [ ] [US4-S3] Add failing transition tests proving historical fix prose cannot resolve a current row.
- [ ] [US4-S4] Add a before/after hash test for analysis-only `.agents/skills/findings-ingest/` rehearsal.
- [ ] [US4] Implement the schema migration and explicit historical-event apply path in `factory/doctor/cli.py`; keep current live `report` semantics unchanged.
- [ ] [US4] Rewrite the findings-ingest skill so analyze and apply are distinct declared intents and every rehearsal is sanitized.

## Verification

- [ ] Run focused skill/helper/doctor tests and the declared repository gate.
- [ ] Prove no network fetch occurred, no publication occurred, and the operational runtime stores are byte-identical to their pre-test hashes.
