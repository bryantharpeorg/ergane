# Plan: 038-replay-eviction-leak

Supersedes 032's US1. Evidence chain:
`specs/032-replay-determinism/RESCOPE-2026-08-12.md` (both addenda), finding
`interpreter/replay-test-nondeterminism-under-load` (recurrence 7).

## Where the work is

1. `factory/workgraph/workflow.py` ~1655 — `_cancel()` catches
   `asyncio.CancelledError` and does not re-raise. This is the "coroutine
   ignored GeneratorExit" in every failing CI log. Re-raise after
   bookkeeping (FR-001).
2. `factory/workgraph/workflow.py` `_run_node` ~1236/1514 and `_teardown`
   ~1676 — teardown activity emission reachable from `finally` during
   unwind. Gate it so eviction-path unwind emits nothing: detect
   cancellation (e.g. re-raised `CancelledError` in flight) and skip
   emission, or move emission out of `finally` onto explicit failure paths
   (FR-002). The SDK already blocks the leaked command at the server for
   live runs — the damage is to REPLAY, where the leaked command corrupts
   the comparison stream.
3. `tests/test_interpreter.py::test_replay_dispatches_nothing_twice` —
   pin `fetch_history` to `result_run_id`; replay under the same runner
   class that recorded (`UnsandboxedWorkflowRunner` if that is what the
   test's worker uses — read the test, do not assume); keep the
   discriminator assertion and dump-on-failure block that are already on
   the capture branches (cherry-pick from `repro/032-history-capture-pr45`,
   commits e9af024/ec2ab64) (FR-004).
4. `tests/fixtures/replay-032/` — the ten dumped histories, ALREADY LANDED
   on the base branch as operator data (a10bea8). Your diff adds only the
   parametrised test that reads them. Do not copy or re-commit the JSON
   files: a 2.3MB diff overflows the judge's window and truncation reads as
   missing work — the first run of this story produced correct code and
   died on exactly that (finding: verify/judge-cannot-see-a-large-diff).

## Traps

1. **032's four-attempt grave is under this ground.** The old US1 died
   because it demanded a fail-first reproduction and the fix in one diff —
   the gate ran the repro test red. This story does NOT ask for a committed
   failing reproduction: the fixtures replay GREEN with the fix (that is the
   assertion), and scenario 2's eviction test asserts silence, not failure.
   Do not add a test that must fail post-fix.
2. **The deadlock detector cannot be reliably triggered in-suite** — months
   of local forcing failed (delays, no-sticky, CPU starvation, injected
   stalls; see RESCOPE). Scenario 2 must simulate eviction by cancelling the
   coroutine/task directly, not by trying to make the detector fire.
3. **Do not "fix" this by disabling the sandbox, raising the deadlock
   timeout, or skipping the test.** The test's contract (replay dispatches
   nothing twice) is the factory's replay-safety guarantee; keep it.
4. **`PytestUnraisableExceptionWarning` for `coroutine ignored GeneratorExit`
   appears in today's PASSING runs too** (e.g. 026/us1's gate log). After
   FR-001 it should be impossible; scenario 2 asserts its absence — use
   pytest's unraisable hooks, not log-grepping.
5. **Normal teardown is load-bearing** (kill paths, salvage, key revocation
   ride on it). FR-005's fence: every pre-existing interpreter test
   unmodified. If one needs an edit, the restructure is wrong.
6. **The sweep test forbids new `__main__` blocks / console scripts** in
   verification+notify; add none (irrelevant to this story unless a helper
   script is contemplated — don't).
7. **Fixture size**: ten histories ≈ 2.3MB raw JSON. Commit them as-is
   (text), no compression cleverness — the suite reads them with
   `WorkflowHistory.from_json`.

## Post-landing operator steps (not the implementer's)

- Rerun PR #46's capture matrix against a rebased capture branch to confirm
  zero divergences on the bench; then close PR #46 and #41 and delete the
  repro branches.
- Rerun PR #45's check; when green, its armed auto-merge lands 026/us1's
  judged diff; then relaunch 026 for us2.
- Resume the ready line (027/030/028, then 025).
