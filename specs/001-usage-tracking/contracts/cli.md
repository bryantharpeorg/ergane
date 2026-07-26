# Contract: `factory-usage` CLI (read-only)

Console script (pyproject entry point). Structurally read-only: opens the ledger with
a `file:...?mode=ro` SQLite URI — any write attempt is an SQLite error (FR-012, US2
scenario 4).

## Invocation

```
factory-usage [--db PATH] --by {persona|epic|spec-ref|attempt|node}
              [--epic EPIC_ID] [--since YYYY-MM-DD] [--json]
```

| Flag | Default | Meaning |
|---|---|---|
| `--db` | `$FACTORY_LEDGER_PATH` or `.factory/ledger.db` | ledger file |
| `--by` | required | rollup dimension (FR-006) |
| `--epic` | all epics | filter |
| `--since` | all time | filter on `torn_down_at` |
| `--json` | off | machine-readable output |

## Output shape

Human mode: aligned table, one row per group, columns as below, footer line with
grand totals and unconfirmed-row count.

`--json` mode (stable contract):

```json
{
  "by": "persona",
  "filters": {"epic": "e1", "since": null},
  "groups": [
    {
      "key": "implementer",
      "prompt_tokens": 123456,
      "completion_tokens": 23456,
      "cache_read_tokens": 98765,
      "cache_write_tokens": 4567,
      "requests": 87,
      "spend_usd": 12.34,
      "rows": 9,
      "unconfirmed_rows": 1
    }
  ],
  "totals": { "...same metric fields...": 0 }
}
```

Rules:
- Token metrics that are NULL for every row in a group serialize as `null`, not 0
  (FR-004/FR-005 pass through to output).
- `unconfirmed_rows` > 0 flags estimates (US2 scenario 3).
- `--by attempt` groups by attempt ordinal across the filter scope (retry-cost view).
- `--by node` groups by `(epic_id, node_id)` with attempts aggregated.
- Exit codes: 0 success (including empty result), 2 bad arguments, 3 ledger
  missing/unreadable.
