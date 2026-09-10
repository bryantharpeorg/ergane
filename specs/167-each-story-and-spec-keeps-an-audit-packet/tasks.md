# Tasks: each story and spec keeps an audit packet

Read the entire trio and constitution before implementation. Test-first in each
phase: reproduce the missing behavior, implement, run focused regressions, then
commit compact real evidence. Existing behavior controls may already pass.
All scope is factory-built; no live operator-store edits or real-account setup.

## Phase 1: User Story 1 — Every execution keeps its identity and measured usage

- [ ] T001 [US1] Add failing tests in `tests/test_attestation_identity.py` for US1-S1, US1-S2: two real issuance/teardown execution identities, question-resume reuse, idempotent redelivery, frozen ladder and a configured rung transition.
- [ ] T002 [US1] Add US1-S3 pre-issuance failure, pre-agent refusal, timeout/cancel/question controls through production entry points; assert no lost launch and unchanged ladder/key cleanup behavior.
- [ ] T003 [US1] Add US1-S4, US1-S5 usage-source tests in `tests/test_attestation_usage.py`: partial dimensions despite confirmed flag, complete token totals with unknown optional cache/request metrics, repeated model amounts with distinct request IDs, gateway/CLI overlap, subscription dollars, ambiguous legacy joins and unknown serving identity. Include populated schema-v2 and mixed schema-v3 source fixtures; assert unchanged old database bytes on reads and no guessed invocation attribution.
- [ ] T004 [US1] Implement typed identity and journal contracts in `factory/attestation/`, and additive invocation provenance in `factory/usage/models.py`, `factory/usage/ledger.py` and `factory/activities/usage_activities.py`; reuse landed `usage_source`, `usage_status`, `cost_basis` and coverage semantics, preserving old schema/payload reading and authoritative ledger ownership. Consume160's typed Codex source once and preserve Claude acquisition; timestamp filtering of archived rollouts is not invocation identity.
- [ ] T005 [US1] Thread frozen identity/ladder and launch lifecycle through `factory/workgraph/workflow.py` and `factory/activities/agent_activities.py`; record intent/outcome including paths with no verification. Do not change routing or consume a rung for packet work.
- [ ] T006 [US1] Run focused usage/identity controls; commit bounded actual rows and test output as US1 evidence, with credentials and host paths removed. Confirm code+tests+evidence fit the diff ceiling.

## Phase 2: User Story 2 — Judge feedback and what resolved it survive every re-ask

- [ ] T007 [US2] Add failing `tests/test_attestation_judge_history.py` cases for US2-S1, US2-S2 using the real scoring loop with malformed/contradictory/valid replies and transport redelivery; one job total, separate actual evaluations, missing call metrics explicit.
- [ ] T008 [US2] Add pure report tests in `tests/test_attestation_report.py` for US2-S3, US2-S4: same-criterion later fix, changed criterion, unavailable/skipped judge, narrative feedback, disposition and gate contradiction; no blanket fully-fixed result.
- [ ] T009 [US2] Add US2-S5 real temporary Git history and gate evidence: NUL-safe names, binary/renamed/deleted paths, exact refs, log truncation and no inferred coverage percentage.
- [ ] T010 [US2] Persist every scoring result/failure through `factory/activities/verify_activities.py`, `factory/verify/judge.py` and the re-ask path in `factory/workgraph/workflow.py`, using US1 identity/journal. Keep judge decisions, prompt inputs and call count policy unchanged.
- [ ] T011 [US2] Implement pure report and resolution assembly in `factory/attestation/`; use existing verification/gate/usage authorities and capture exact Git evidence through activities before it disappears.
- [ ] T012 [US2] Run judge/retry/verdict/report regressions and commit compact actual before/after report evidence without raw prompts or secret-bearing transcripts.

## Phase 3: User Story 3 — A story packet exports and verifies without a running factory

- [ ] T013 [US3] Add failing `tests/test_attestation_archive.py` cases for US3-S1, US3-S2, US3-S3 using actual temporary stores, selected134 artifacts, reproducible exports, successor revisions and incomplete/missing evidence.
- [ ] T014 [US3] Add US3-S4, US3-S5 safety cases: source path/symlink swap, hardlink alias, FIFO, duplicate/unlisted ZIP entries, expansion bounds, corrupt bytes, partial writes, output collision, raw transcript exclusion, HTML text and opaque sensitivity.
- [ ] T015 [US3] Add real CLI tests in `tests/test_attestation_cli.py` for explicit subject selection, export, relocated offline verify, strict completeness and read-only behavior.
- [ ] T016 [US3] Implement immutable archive/storage/verification in `factory/attestation/` and `factory/cli/nouns/attestation.py`; reuse134 stored bytes, no worktree rescan, arbitrary URL fetch or upload.
- [ ] T017 [US3] Commit bounded real CLI output and a small synthetic manifest/report example proving reproducibility and corruption refusal; exclude opaque real reports from Git.

## Phase 4: User Story 4 — Lifecycle completion produces recoverable packets

- [ ] T018 [US4] Add failing `tests/test_attestation_lifecycle.py` scenarios for US4-S1, US4-S4 using real temporary activities/journal and a time-skipping test workflow: all node/epic outcomes, collection before cleanup, teardown before final packet, unlaunched nodes explicit.
- [ ] T019 [US4] Add US4-S2, US4-S3 crash-window/replay/redelivery/failure-exhaustion tests; assert unchanged salvage/key revocation/build outcomes and successful explicit retry without a new model call.
- [ ] T020 [US4] Add US4-S5 configuration tests through manifest parser, manual build and roadmap dispatch, plus old-payload/replay controls; invalid finite bounds refuse before launch, disabled is explicit.
- [ ] T021 [US4] Implement the declared frozen policy in `factory/verify/models.py`, `factory/verify/factory_yaml.py`, CLI/roadmap dispatch adapters and `factory/workgraph/workflow.py`, using replay-compatible command changes.
- [ ] T022 [US4] Add bounded finalization activities in `factory/activities/attestation_activities.py`, register with `factory/worker.py`, and integrate every cleanup/completion path. Add read-only status and explicit finalize retry to `factory/cli/nouns/attestation.py`.
- [ ] T023 [US4] Run real workflow/restart controls and commit a short actual lifecycle trace showing capture, teardown, cleanup, finalization/recovery; no mock-only proof of deployment wiring.

## Phase 5: User Story 5 — A spec packet includes reruns without counting work twice

- [ ] T024 [US5] Add failing `tests/test_attestation_rollup.py` cases for US5-S1, US5-S2: two-story partial epic plus remainder, amended content, failed spend retained, distinct attested/observed evidence and source-ID deduplication.
- [ ] T025 [US5] Add US5-S3, US5-S4 controls for two targets with same spec name, ambiguous revision, missing child packet and portable nested verification.
- [ ] T026 [US5] Implement pure rollup selection and portable nested export in `factory/attestation/`, exposing explicit spec/revision selection in `factory/cli/nouns/attestation.py`; no current-HEAD or latest-timestamp guessing.
- [ ] T027 [US5] Commit actual small rollup output and independent total calculations from the controlled source rows, including partial totals and preserved predecessor references.

## Phase 6: User Story 6 — Teams attach their CI and audit reports to immutable revisions

- [ ] T028 [US6] Add failing `tests/test_attestation_attachments.py` cases for US6-S1, US6-S2, US6-S3: all requested report categories, branch/merge-group revision relationships, mismatch/refusal, repeat ID, conflicting bytes and concurrent submissions.
- [ ] T029 [US6] Add US6-S4, US6-S5 executable CLI/CI example tests in `tests/test_attestation_ci_examples.py`: strict completeness, selected downloadable artifact, late UAT successor rollup and unchanged earlier packet.
- [ ] T030 [US6] Implement transactional attachment and policy support in `factory/attestation/`, configuration models/parser and `factory/cli/nouns/attestation.py`; use local files only, preserve submitter versus claimed producer and immutable revisions.
- [ ] T031 [US6] Write `docs/attestation-packets.md` with tested setup, configuration, hook lifecycle, story/spec export, CI attachment, unknown/partial metrics, retention/recovery, privacy and offline verification examples. Use the team's existing artifact store, not a new Ergane endpoint.
- [ ] T032 [US6] Run focused integration and full declared gates; commit bounded actual test/CLI evidence and inspect total story diff size.

## Operator release qualification after all stories land

- [ ] T033 Independently compare a real approved-gateway build's packet to launch, usage, every judge evaluation, gates, file refs and native queue records; include failed first attempt and actual configured rung change.
- [ ] T034 Exercise supported deployed cleanup/restart, later CI/UAT attachment and two-execution spec export; verify downloaded bytes offline. Missing expected new-run measurements remain a release gap, not a silent completeness waiver.
- [ ] T035 Refresh getting-started/release docs with verified installed CLI examples; retain normal main promotion and registry publication gates. These tasks authorize no account/trust change or public evidence upload.
