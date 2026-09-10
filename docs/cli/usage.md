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
| `SPEND_USD` | estimated cost using the gateway’s configured prices |
| `ROWS` | ledger rows behind the line |
| `UNCONFIRMED` | rows whose usage is missing or partial |

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

**Subscription usage comes from structured runner telemetry.** Claude and Codex
attempts record measured tokens after their sessions are archived. `SPEND_USD`
is unknown (`-`), not zero: the factory does not allocate monthly subscription
charges to individual attempts. Claude input totals include reported cache-read
and cache-write tokens; Codex input totals already include cached input. Codex
cumulative usage does not establish request count, so `REQUESTS` stays unknown.

The table includes a **measured token subtotal** with missing, partial, and legacy
row counts. The original complete totals remain unknown when any included row
has unknown counters or explicitly partial usage. Group numbers are measured
subtotals. The additive JSON `coverage` object gives the same subtotals and
coverage per group and overall, plus `usage_sources` and `cost_bases`.

New ledger fields are `usage_source` (`gateway`, runner name, `mixed`, `unknown`),
`usage_status` (`complete`, `partial`, `unknown`), and `cost_basis`
(`proxy_estimate`, `unknown`). Existing rows retain `legacy` provenance/status;
migration does not retroactively certify them. Read-only usage commands can read
old ledgers without migrating them. The writer upgrades the schema additively.

A gateway teardown reads up to three snapshots, with 1 and 2 second pauses,
and requires stable, usable token detail and agreement between request-log and
key cost. Matching costs alone cannot establish completeness: free models still
need token-bearing request records. Persistent inconsistencies remain partial;
confirmed measurements survive a retry after key revocation. Live build status
continues to report proxy cost only, explicitly labelled as an estimate.

Historical recovery is separate: `python -m factory.usage.reconcile` creates a
read-only preview from a reviewed export of daily gateway totals. It never
updates the ledger. Do not estimate missing tokens by dividing dollars by rates.

## See also

- [`ergane build attempts`](build.md) — per-attempt verdicts and what the judge was shown
- [`ergane status`](status.md) — the `pace` section, for wall-time rather than cost
