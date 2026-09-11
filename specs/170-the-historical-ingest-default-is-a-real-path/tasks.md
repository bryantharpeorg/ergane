# Tasks: the historical ingest default is a real path

## Phase 1: User Story 1 — Historical ingestion is safe on every public analysis path

- [ ] T001 [US1] Integrate the four authored 158/US4 candidate commits through
      `3015d69` on the current buildout base, excluding the salvage-only commit.
      Resolve conflicts without weakening the original historical-event tests.
- [ ] T002 [US1] Add a failing production-boundary regression that invokes
      `findings ingest --batch <temporary batch>` without `--rehearsal-db` and
      proves success, one printed existing database path, a readable event and
      an unchanged operational-store byte snapshot. Covers US1-S2 and FR-002.
- [ ] T003 [US1] Instrument the temporary-file seam in that focused test to
      prove the returned descriptor is closed on success and refusal/error paths;
      repair the fd/path handling without leaving a placeholder collision.
- [ ] T004 [US1] Add a failing rehearsal test with synthetic credential-shaped
      content in `observation_id` and each already-sanitized finding field. Scan
      database bytes, returned rows, stdout, stderr and exceptions. Covers
      US1-S3 and FR-003.
- [ ] T005 [US1] Repair the historical sanitization boundary and add duplicate
      and distinct-identity controls proving deterministic idempotency without
      cross-observation collapse. Covers FR-004.
- [ ] T006 [US1] Preserve explicit existing-path refusal, explicit apply-only
      operational writes, historical/current-row independence, migration parity
      and current live-report semantics. Covers US1-S1, US1-S4 and US1-S5.
- [ ] T007 [US1] Run the two exact red/green loops, all focused historical
      ingestion tests, doctor CLI/store/schema controls and the full declared
      gate. Keep evidence bounded, synthetic and free of credential values.
- [ ] T008 [US1] Confirm the final diff does not mutate PR504, a live database,
      worker/roadmap state, model routing, dependencies or release artifacts.
