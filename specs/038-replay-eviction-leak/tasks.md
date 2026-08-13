# Tasks: An evicted workflow must exit silently, not command from its grave

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II) except where its own text declares
it a guard over green behaviour (T002's fixtures replay green by design — the
docstring states why, so the judge reads intent, not a fail-first violation).

## Format: `[ID] [Story] Description`

---

## Phase 1: User Story 1 — Cancellation propagates and teardown cannot outlive eviction (Priority: P1)

- [ ] T001 [US1] Read `_cancel()` (workflow.py ~1655), `_run_node`'s unwind
      path (~1236/1514), `_teardown` (~1676), and the current
      `test_replay_dispatches_nothing_twice`. Confirm the ten fixtures are
      present at `specs/038-replay-eviction-leak/fixtures/` (ask via the
      operator channel if absent — do not skip US1-S1). No code yet; the
      commit is allowed to be empty.
- [ ] T002 [US1] US1-S1: fixture-replay test copying the ten histories into
      `tests/fixtures/replay-032/` and replaying each against `EpicWorkflow`.
      These replay green with today's code — the test is a standing guard
      whose docstring says so; it fails only if a future change breaks
      replay compatibility.
- [ ] T003 [US1] US1-S2, failing first: eviction simulation (cancel the node
      task mid-activity), assert no unraisable `GeneratorExit` warning (use
      pytest's unraisable hooks, not log-grepping) and no teardown command
      emitted; then FR-001 (`_cancel()` re-raises after bookkeeping) and
      FR-002 (no command emission on the eviction path) to green it.
- [ ] T004 [US1] US1-S4: pin the replay test's `fetch_history` to
      `result_run_id`, replay under the same runner class that recorded
      (read the test's worker setup — do not assume), and keep the
      one-`validate_target_repo` discriminator assertion plus the
      dump-on-failure capture (cherry-pick from
      `repro/032-history-capture-pr45`, commits e9af024/ec2ab64).
- [ ] T005 [US1] US1-S3 + US1-S5: prove normal-path teardown unchanged —
      every pre-existing interpreter and sweep test passes unmodified — then
      the full gate (`uv run pytest -q`) green.

---

## Verification

- [ ] Final gate green; no pre-existing test edited; all ten fixtures
      replayed green.
