# Plan: A zero the factory did not measure

Refined against `b4c5af9` on 2026-08-10, **re-verified against `851e0bf` on
2026-08-16**. Every anchor below was read by hand at the later tree. The three
that had drifted are corrected in place; the rest held. If one still does not
resolve when you read it, trust the code and say so in your handoff rather than
hunting.

## The shape of this change

The codebase already contains the correct answer, applied to two of its six
metrics. `AggregatedUsage` carries six fields; `cache_read_tokens` and
`cache_write_tokens` are `int | None` and are documented with precisely the rule
this spec wants:

> The cache fields are `None` when the metric was absent from *every* row, and a
> sum when it was present on any: an attempt that genuinely read no cache reports
> 0, an attempt whose backend does not report cache reports nothing (FR-004).

— `factory/usage/models.py:102-105`

That is the whole design. This story extends it to `prompt_tokens`,
`completion_tokens` and `request_count`. You are not inventing a convention; you
are finishing one, and the docstring you should match is already written.

## What to read first

| Thing | Where | Why |
| --- | --- | --- |
| The correct precedent | `factory/usage/models.py:102-112` | The cache fields and their rationale — copy this rule |
| The dataclass to change | `factory/usage/models.py:107-112` | `prompt_tokens: int`, `completion_tokens: int`, `request_count: int` become `int \| None` |
| The function to change | `factory/usage/aggregate.py:39-72` | `aggregate_rows` — the accumulator seeds and the return |
| The existing accumulator | `factory/usage/aggregate.py:61-62` | `_accumulate(...)` is how the cache fields already do "None until reported" — reuse it |
| The row-level helper | `factory/usage/aggregate.py:100-102` | `_as_int` — **do not change this**, see trap 2 |
| The schema's own rule | `factory/usage/ledger.py:69-71` | `NULL = unknown (never fabricated 0)` |
| The renderer | `factory/usage/cli.py:60` and `:209` | `UNMEASURED = "-"`; `None` already prints as `-` |
| The writer path | `factory/activities/usage_activities.py:155` | Where `AggregatedUsage` becomes a `UsageRecord` |
| The record type | `factory/usage/models.py:138-142` | Already `int \| None` — the ledger row can hold this today |

Note the asymmetry that makes this small: the *destination* already accepts
`NULL` (`models.py:138-142`, and the SQL column is nullable), and the *display*
already renders `None` as `-`. Only the middle of the pipe cannot express it.

## The change

1. `AggregatedUsage.prompt_tokens`, `.completion_tokens`, `.request_count` become
   `int | None`. Extend the class docstring to say the same thing about them that
   it already says about the cache fields.
2. In `aggregate_rows`, seed those three as `None` rather than `0` and fold with
   `_accumulate` — the same helper the cache fields use. An empty row set then
   returns `None` for all three because nothing ever accumulated; any row at all
   makes them a sum, including a sum of zeroes.
3. Correct the `aggregate_rows` docstring. It currently asserts the belief that
   caused this defect: *"An empty row set is a genuine zero-request aggregate: the
   proxy answered, and it answered 'no rows'."* It is not, and the ledger has
   forty-six dollars of evidence that it is not. Say instead that an empty row set
   is an unmeasured aggregate, and that a zero is only a zero when a row said so.
4. Follow the `int | None` outward to whatever no longer type-checks — the writer
   at `factory/activities/usage_activities.py:149` and any totals in
   `factory/usage/cli.py`. The columns are already nullable, so there is no
   migration.

## Traps

**Trap 1 — `spend_usd` is not part of this.** It arrives on a different read from
the token metrics, which is exactly why the contradictory row is possible. Leave
its accumulation alone. FR-004 exists to stop a tidying instinct from making all
six fields optional "for consistency" and turning a real spend into an unknown.

**Trap 2 — do not fix this in `_as_int`.** The obvious-looking change is to make
`_as_int` return `None` for a missing column. That is the wrong level and it
breaks a case that currently works: `_as_int` is row-level, and a *row* that omits
a token column while other rows report one should contribute nothing to the sum,
not poison it to unknown. Its docstring at `aggregate.py:100-102` already states
this and is correct. The distinction this spec turns on is at the *aggregate*
level — no rows at all — and `_accumulate` is where it belongs.

**Trap 3 — absence and zero must stay distinguishable, and a test must prove
both.** It is possible to satisfy every scenario about `None` by returning `None`
whenever the sum is zero. That passes scenarios 1 and 4 and is wrong: an attempt
that genuinely made zero requests would then report "unmeasured", which is the
same lie in the other direction. Scenario 3 is the one that catches it, and it
needs rows that are present and report zero — not an empty list.

**Trap 4 — `None` is not zero in a total.** Wherever the CLI sums a column across
rows, `None` must not be coerced. Summing unknowns as zero reproduces the original
defect one layer up, and it is harder to see there because the total looks
plausible. If a total spans a mix of known and unknown rows, the honest rendering
says so; do not silently report the partial sum as if it were complete.

**Trap 5 — the suite must not touch the live evidence store.** There is an open
finding, `hardening/test-suite-writes-to-the-live-evidence-store`, that running
pytest with the operator's environment exported writes real rows to the real
ledger and can page the operator. This story is *about* the ledger, so it is the
one most likely to trip it. Every test here builds its own store under `tmp_path`.
No test may read `.factory/ledger.db`.

**Trap 6 — do not rewrite history to make the demo look better.** FR-006. The
affected rows stay exactly as they are; they are the evidence that this happened.
Backfilling them from transcripts is real work the operator has scoped out of this
spec, not a helpful extra.

**Trap 7 — purge `__pycache__` between mutants.** CPython validates a cached
`.pyc` on `(mtime-in-whole-seconds, size)` only, so two same-size mutants written
inside one wall-clock second make the second run execute the *first* mutant's
bytecode. Your mutations here are type-annotation and seed-value swaps, which
preserve size trivially — this trap is aimed straight at this story. Run under
`PYTHONDONTWRITEBYTECODE=1` or purge between runs. Filed as
`verify/mutation-batteries-can-test-stale-bytecode-when-a-mutation-preserves-file-size`.

**Trap 8 — quote `passed` and `skipped`, never the warning count.** A
`SyntaxWarning` fires at compile time, so a warm cache reports fewer warnings
than a cold one on an identical tree. The skip count is the load-bearing one;
baseline is 44 and a new skip is a hidden test you must declare.

**Trap 9 — measure exit codes without a pipe.** `cmd | head; echo $?` reports the
pipe's status, not the command's. That error produced a false reading of
`ergane install --verify` on 2026-08-16 and nearly became a filed finding.
Capture `rc=$?` before any pipe. Relevant here because "done" below asks you to
read a row back with `sqlite3`.

## What "done" looks like

An attempt runs against a proxy that reports no spend rows, and its ledger row
reads `-` under PROMPT, COMPLETION and REQUESTS in `ergane usage` while still
showing its spend. Read the row back with `sqlite3` and see `NULL`, not `0` —
the CLI rendering `-` is not by itself proof, because `-` is also what a `0`
would print if someone mapped it that way.
