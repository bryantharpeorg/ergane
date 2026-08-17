---
state: ready
# specs_root: specs
# target_repo: /home/admin/code/ergane-024-target
# Scaffolded by `ergane findings promote` from
# `interpreter/ledger-records-dollars-without-tokens` (critical, occ 2, source
# operator-2026-08-09), then refined against the tree at b4c5af9 on 2026-08-10.
---

# Feature Specification: A zero the factory did not measure

## The defect in one sentence

`aggregate_rows` treats "the proxy returned no rows" as "the attempt did no
work", so every ledger row written since 2026-08-08 06:51Z asserts
`prompt_tokens = 0`, `completion_tokens = 0` and `request_count = 0` next to a
real `spend_usd` — a measurement nobody took, printed as if somebody had.

## Why this is critical rather than cosmetic

Two reasons, and the second is the one that raises it.

The schema already decided this question. `factory/usage/ledger.py:69` carries
the comment `NULL = unknown (never fabricated 0)`, and `factory/usage/cli.py:60`
defines `UNMEASURED = "-"` so a metric nobody reported prints as absence.
(Re-checked 2026-08-16: this spec used to cite `contracts/ledger-schema.sql`
alongside it. **That file no longer exists**; the schema lives in `ledger.py`
alone.) Both mechanisms exist, work, and are bypassed: the
writer never sends a `NULL` for these three columns because the aggregate cannot
produce one.

And the number matters more than money here. The factory's models run on a
flat-rate subscription, so `spend_usd` measures nothing anyone pays; tokens are
the operator's only signal of how much effort an attempt actually cost. A ledger
that reads zero for every attempt has silently removed the one column that was
load-bearing, while continuing to look populated.

The row is also self-contradictory on its face, which is what makes it provable
rather than arguable: `019-operator-cli/us5` carries `spend_usd = 46.4664` beside
`request_count = 0`. Forty-six dollars of requests that never happened.

## The evidence

- Affected rows verified: all of `015`, `016` us3/us4, `006` us3, `019` us2/us4/us5
  — every row from 2026-08-08T06:51Z onward.
- Re-confirmed live 2026-08-10 against `.factory/ledger.db`: the three most recent
  attempts each carry non-zero `spend_usd` with `prompt_tokens = completion_tokens
  = request_count = 0`.
- **Re-measured 2026-08-16, and it has got worse.** `ergane usage --by epic`
  now reports **0 prompt, 0 completion, 0 requests** against real spend for
  every epic since the defect began: 036 ($11.30), 037 ($5.56), 038 ($52.68),
  039 ($12.99), and 043 ($48.01 across twenty rows). 033 is stranger still —
  19 prompt tokens and 2 completion tokens across **79 requests**, which is not
  a plausible measurement either. Six days of the factory's hardest running are
  recorded as having cost nothing.
- **The data is not lost.** Agent transcripts under
  `FACTORY_ROOT/transcripts/<epic>/<node>/attempt-N/*.jsonl` carry intact usage
  blocks. 006's five landed nodes sum to 387,490,083 input and 6,185,313 output
  tokens over 3,928 calls, against a ledger reading zero for all five.

## Scope

This spec makes the record honest. It does **not** make it complete, and the
difference is deliberate — see Out of scope.

### User Story 1 - An unmeasured metric is recorded as unknown, not as zero (Priority: P1)

When the usage snapshot for an attempt yields no rows to aggregate, the ledger
records `NULL` for `prompt_tokens`, `completion_tokens` and `request_count`, and
`ergane usage` renders them as `UNMEASURED`. A genuine zero — an attempt that
really did make no requests — is still recorded as `0` and still prints as `0`.

**Why this priority**: It is the whole defect. There is no second story.

**Independent Test**: Aggregate an empty row set alongside a non-zero spend and
assert the three metrics are `None`; aggregate rows that genuinely report zero
and assert they are `0`. Then walk one attempt end to end and read the row back
out of the ledger.

**Acceptance Scenarios**:

1. **Given** a usage snapshot whose row set is empty and whose spend is non-zero,
   **When** the attempt tears down, **Then** the ledger row carries `NULL` for
   `prompt_tokens`, `completion_tokens` and `request_count`, and the recorded
   `spend_usd` is unchanged.
2. **Given** a usage snapshot whose rows report token counts, **When** the attempt
   tears down, **Then** the ledger row carries those sums, exactly as it does today.
3. **Given** a usage snapshot whose rows are present and genuinely report zero
   tokens and zero requests, **When** the attempt tears down, **Then** the ledger
   row carries `0` — absence and zero are different answers and the row states
   which one it is.
4. **Given** a ledger row whose token columns are `NULL`, **When** the operator runs
   `ergane usage`, **Then** those cells render as `UNMEASURED` and never as `0`.
5. **Given** a ledger row whose token columns are `NULL`, **When** any total is
   computed across rows, **Then** the total does not treat the unknown as zero and
   does not silently drop the row from the count it reports.

## Functional Requirements

- **FR-001**: `AggregatedUsage.prompt_tokens`, `.completion_tokens` and
  `.request_count` MUST be able to express "not measured", using the same
  `int | None` shape the cache fields on the same dataclass already use.
- **FR-002**: `aggregate_rows` MUST return `None` for those three metrics when it
  received no rows to aggregate, and a sum when it received any.
- **FR-003**: The ledger writer MUST pass the unknown through as SQL `NULL`,
  honouring the schema comment already at `factory/usage/ledger.py:69`.
- **FR-004**: `spend_usd` MUST be unaffected. It is read on a different path and
  is not in question here.
- **FR-005**: A metric recorded as `NULL` MUST render as `UNMEASURED` wherever the
  usage surface prints it, and MUST NOT be summed as zero in any aggregate the CLI
  reports.
- **FR-006**: This feature MUST NOT rewrite, migrate or backfill any row written
  before it lands.

## Out of scope — named so an implementer does not build them

- **Backfilling the affected rows from transcripts.** The data exists and the
  recovery is worth doing, but it is a one-off operator migration over historical
  evidence, not interpreter behaviour, and mixing it in would put a data migration
  inside a story about a type. FR-006 forbids it here.
- **In-flight token observability.** A running node has only `stdout.log` until
  teardown, so effort is unobservable while it is being spent. That is a real gap
  and a separate feature; this spec changes only what teardown records.
- **Why the proxy stopped reporting rows.** Upstream, and outside this repository.
  This spec makes the factory honest about not knowing — it does not restore the
  knowing.

## Success Criteria

- **SC-001**: With a proxy that returns no spend rows, an attempt's ledger row has
  `NULL` in the three columns and a non-zero `spend_usd`, and `ergane usage`
  prints `-` for them.
- **SC-002**: With a proxy that returns rows, the ledger row is byte-identical to
  what the same attempt produces today.
- **SC-003**: The full suite stays green and no dependency is added.
- **SC-004**: No row written before this feature is modified.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
```
