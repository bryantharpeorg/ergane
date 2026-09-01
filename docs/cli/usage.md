# `ergane usage`

> read-only usage rollups over the ledger

Render one rollup from the usage ledger without writing to it.

```
ergane usage --by DIMENSION [--db PATH] [--epic EPIC] [--since DAY] [--json]
```

| flag | default | meaning |
| --- | --- | --- |
| `--by` | **required** | rollup dimension: `persona`, `epic`, `spec-ref`, `attempt`, `node` |
| `--db` | `$ERGANE_LEDGER_PATH`, else `.factory/ledger.db` | ledger file |
| `--epic` | all | restrict to one epic |
| `--since` | all | only attempts torn down on or after this day (UTC) |
| `--json` | | emit the machine-readable document instead of the table |

## The table

```
by epic | epic: all | since: all
EPIC                            PROMPT  COMPLETION  CACHE_READ  CACHE_WRITE  REQUESTS  SPEND_USD  ROWS  UNCONFIRMED
003-merge-queue             21,912,008     136,551           -            -       230    33.1258    12            0
006-interpreter-hardening    8,108,516     139,343           -            -        85   163.5734    15            0
```

The header line restates the filters, so a pasted table always carries what it
was filtered to.

| column | meaning |
| --- | --- |
| `PROMPT`, `COMPLETION` | tokens in and out |
| `CACHE_READ`, `CACHE_WRITE` | prompt-cache tokens; `-` where the route did not report them |
| `REQUESTS` | model calls |
| `SPEND_USD` | cost as the gateway reported it |
| `ROWS` | ledger rows behind the line |
| `UNCONFIRMED` | rows whose usage was never confirmed by the gateway |

**`UNCONFIRMED` is the honesty column.** A non-zero value means the line under-
reports by an unknown amount, because those attempts' usage never came back.

## The dimensions

| `--by` | one row per |
| --- | --- |
| `persona` | persona — which model configuration is spending |
| `epic` | epic — what a spec cost end to end |
| `spec-ref` | spec reference |
| `attempt` | individual attempt — the finest grain, for finding the one that ran away |
| `node` | node (user story) |

`--by attempt --epic <id>` is the shape for "one epic cost far more than the
others, which attempt was it".

## Reading the numbers honestly

**Tokens are the effort signal; dollars are downstream of a price sheet.** A
route change moves `SPEND_USD` without any work changing, so a spend comparison
across a period that spans a model or route change compares two different
things. Token columns compare cleanly.

**Subscription-routed personas bill nothing per token.** An epic run on a
subscription route and one run through the gateway are not comparable on
`SPEND_USD` at all — the first is structurally zero regardless of how much work
it did. `--by persona` is the rollup that makes that visible.

**The ledger only knows what the gateway told it.** When a column reads `-` or
`UNCONFIRMED` is non-zero, the data is missing rather than zero, and the
difference matters.

## See also

- [`ergane build attempts`](build.md) — per-attempt verdicts and what the judge was shown
- [`ergane status`](status.md) — the `pace` section, for wall-time rather than cost
