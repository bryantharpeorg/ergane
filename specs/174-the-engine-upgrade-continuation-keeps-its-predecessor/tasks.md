# Tasks: the engine upgrade continuation keeps its predecessor

Read the full trio and every trap.  Spec 166 US1 is already landed and is never
replayed.  These are new story identities for its two pending slices.  Use real
files and generated projects below temporary roots; capture all child operations.
No Docker daemon, worker, provider, credential store or live Temporal service.

## User Story 1 — Preserve pre-stop rollback identity

- [ ] T001 [US1] (US1-S1, FR-002, FR-009) Add a file-backed regression using
      real identity writer/reader/remover.  Synthetic stop removes the old file
      and start writes the target; assert the old read precedes stop and capture
      the complete ordered lifecycle and retention result.  Record the old red.
- [ ] T002 [US1] (US1-S2, FR-003) Cover absent, malformed and image-less initial
      identities separately.  A later readable target identity authorizes no
      removal.  Do not patch the reader to return a constant object.
- [ ] T003 [US1] (US1-S1, US1-S2, FR-002, FR-003) Capture pre-stop identity once
      and carry that immutable value to retention.  Keep uncertainty sticky.
- [ ] T004 [US1] (US1-S3, FR-004) Prove failed stop, failed start and failing
      engine verification cause no inventory or removal.  Preserve unrelated
      finding visibility and the engine-specific degraded verdict.
- [ ] T005 [US1] (US1-S4, FR-001, FR-009) Re-run landed exact-repository,
      ambiguous-tag, unknown-identity and numeric-order controls; commit compact
      synthetic red/green evidence, then run the full declared gate.

## User Story 2 — Persist and launch the selected image

- [ ] T006 [US2] (US2-S1, FR-005, FR-006, FR-009) Generate and persist an old
      operational project through the real generator/writer.  Drive default
      upgrade with captured subprocesses; prove persisted image/version and the
      actual Compose environment select the CLI-matched published image.  Record
      both the dropped-environment and literal-old-image reds.
- [ ] T007 [US2] (US2-S2, FR-006) Compare nondefault mounts, user, ports,
      confinement and unrelated environment values before/after.  Assert updated
      ownership digests, unchanged unrelated fields and no written secret.
- [ ] T008 [US2] (US2-S3, FR-007) Cover changed, unclaimed, missing and
      unsupported artifacts with byte snapshots and no-call logs.  Refuse before
      stop/write; force must not adopt operator edits.
- [ ] T009 [US2] (US2-S4, FR-008) Inject persistence failure after validation;
      prove old bytes remain usable and start/verify/inventory/cleanup never run.
- [ ] T010 [US2] (US2-S1, US2-S2, US2-S3, US2-S4, FR-005, FR-006, FR-007,
      FR-008) Implement narrow pre-disruption validation and atomic persistent
      retargeting through existing project/manifest boundaries.  Forward the
      selected version at the actual Compose subprocess boundary; do not rerun
      install, infer defaults or bypass ownership.
- [ ] T011 [US2] (US2-S1, FR-005, FR-006) Assert a subsequent invocation reads
      the saved image/version and re-run both actual-boundary regressions.
- [ ] T012 [US2] (US2-S5, FR-009, FR-010) Reconcile the two upgrade docs while
      preserving README/on-ramp behavior and distinguishing synthetic captures
      from required real-image/rollback qualification.
- [ ] T013 [US2] (US2-S5, FR-009, FR-010) Commit compact labelled evidence, run
      upgrade/identity/project/manifest/onboarding controls, check the hashes and
      64 KiB bound, then run the full declared gate before normal judge and native
      merge-queue handling.
