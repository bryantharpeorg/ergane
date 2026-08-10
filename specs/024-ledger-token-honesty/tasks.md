# Tasks: A zero the factory did not measure

One story, one node. Work test-first and commit once per task.

## Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the aggregate cases FIRST, in
      `tests/test_usage_aggregate.py`: an **empty** row set returns `None` for
      `prompt_tokens`, `completion_tokens` and `request_count`; a row set whose
      rows report counts returns the sums it returns today; and — the case that
      catches the shortcut in plan.md trap 3 — a row set whose rows are *present*
      and report zero returns `0`, not `None`. Absence and zero are different
      answers and this task is where that becomes enforceable (spec US1-S1,
      US1-S2, US1-S3) — must fail.
- [ ] T002 [P] [US1] Write the ledger round-trip case FIRST: a record built from
      an unmeasured aggregate writes SQL `NULL` in the three columns and reads
      back as `None`, with `spend_usd` unchanged and non-zero on the same row
      (spec US1-S1, FR-003, FR-004). Build the store under `tmp_path` — plan.md
      trap 5, this test must never touch `.factory/ledger.db` — must fail.
- [ ] T003 [P] [US1] Write the rendering case FIRST: a row whose token columns are
      `None` prints `UNMEASURED` for them, and a row whose columns are `0` prints
      `0`. Assert against the existing `UNMEASURED` constant rather than the
      literal `"-"` (spec US1-S4) — must fail.
- [ ] T004 [P] [US1] Write the totals case FIRST: a total computed over a mix of
      known and unknown rows does not treat the unknown as zero and does not
      silently drop it from the row count it reports (spec US1-S5, plan.md trap 4)
      — must fail.

## Implementation

- [ ] T005 [US1] Widen `AggregatedUsage.prompt_tokens`, `.completion_tokens` and
      `.request_count` to `int | None` in `factory/usage/models.py`, and extend the
      class docstring to state for them the rule it already states for the cache
      fields (plan.md, "The shape of this change").
- [ ] T006 [US1] In `factory/usage/aggregate.py`, seed those three accumulators as
      `None` and fold them with the existing `_accumulate` helper. **Do not modify
      `_as_int`** (plan.md trap 2). Correct the `aggregate_rows` docstring, which
      currently asserts the belief that caused the defect.
- [ ] T007 [US1] Follow the widened type outward until the tree type-checks: the
      writer at `factory/activities/usage_activities.py:149`, and any total in
      `factory/usage/cli.py`. `spend_usd` is untouched (FR-004, plan.md trap 1).
      No schema migration — the columns are already nullable.

## Verification

- [ ] T008 [US1] Run the full suite. Then read one row back with `sqlite3` against
      a scratch store and confirm the columns are `NULL` rather than `0` — the CLI
      printing `-` is not proof on its own (plan.md, "What done looks like").
- [ ] T009 [US1] Confirm no historical row changed (FR-006): the feature adds no
      migration, no `UPDATE`, and no backfill.
- [ ] Final gate command passes green.
