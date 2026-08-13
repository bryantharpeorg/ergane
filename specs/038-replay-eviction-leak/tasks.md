# Tasks: 038-replay-eviction-leak

The implementer works its slice test-first and commits once per task.

## Implementation

- [ ] T001 Read `_cancel()`, `_run_node`'s unwind path, `_teardown`, and the
      current `test_replay_dispatches_nothing_twice`. Confirm the fixtures
      are present under `tests/fixtures/replay-032/` (ask the operator via
      the channel if absent — do not skip US1-S1). No code yet; the commit
      is allowed to be empty.
- [ ] T002 US1-S1 harness: fixture-replay test over every file in
      `tests/fixtures/replay-032/` (with today's code these replay green
      locally — the fixtures guard the FUTURE against regression; state this
      in the test's docstring so the judge reads intent, not fail-first).
- [ ] T003 US1-S2 first, failing first: eviction simulation (cancel the node
      task mid-activity), assert no unraisable `GeneratorExit` warning and
      no teardown command emitted; then FR-001 (`_cancel()` re-raises) and
      FR-002 (no emission on the eviction path) to green it.
- [ ] T004 US1-S4: pin the replay test to `result_run_id`, replay under the
      recording runner class, keep the discriminator + dump-on-failure
      (cherry-pick from `repro/032-history-capture-pr45`).
- [ ] T005 US1-S3 + US1-S5: normal-teardown behaviour proven unchanged;
      full gate (`uv run pytest -q`) green with every pre-existing test
      unmodified.

## Verification

- [ ] Final gate green; no pre-existing test edited; fixtures replayed green.
