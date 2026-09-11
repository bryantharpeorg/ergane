---
name: "build-metrics"
description: "Measure what the factory has actually produced: lines of code by language and module, commit-size distribution with outliers trimmed, and the story rework rate with its trend over time. Use when asked how big the codebase is, how large a typical change is, how often stories need a second attempt, or whether the factory is getting better."
compatibility: "Requires a checkout of this repository, python3, git, and a stable local cloc executable. Reads .ergane/*.db read-only; honors ERGANE_ROOT (with FACTORY_ROOT as the legacy alias); does not need the worker or Temporal running."
metadata:
  author: "operator session"
user-invocable: true
disable-model-invocation: false
---

# Build metrics

Three families of measurement, each with a script under `scripts/`. Run only
what was asked for — the rework analysis is the expensive-to-interpret one and
nobody wants a LOC table when they asked about attempt counts.

| Question | Script |
| --- | --- |
| How big is this, by language and by module? | `scripts/loc.py` |
| How large is a typical commit? Does anything ever get deleted? | `scripts/commit_sizes.py` |
| How often does a story need reworking, and is that improving? | `scripts/rework.py` |

All three take an optional repo path and default to the current directory:

```bash
python3 .agents/skills/build-metrics/scripts/rework.py
```

`ergane` is **not on PATH** — anything shelling out to the CLI needs
`uv run ergane`, after `eval "$(scripts/ergane-env.sh)"`. The scripts here
deliberately avoid the CLI and read git and the SQLite stores directly, so they
work with the worker down.

## The traps, which are most of the value

Every one of these produced a wrong number first.

### Outliers can carry the churn

Raw commit-size means are summaries of the tail as well as the typical change.
**Report both and say which you mean.** The script's Tukey fences and trimmed
rows are the comparison; do not quote an unqualified mean as "typical."

### Machine-generated recordings can dominate LOC

Machine-generated fixtures are measured by `scripts/loc.py` as their own rows.
Keep that row visible in the answer; do not fold it into an authored-code total.

### The insertion:deletion ratio measures youth, not discipline

Repo-wide insertion:deletion measures youth, not discipline. The
growth-adjusted buckets by commits touching a file are the comparison. **Quote
the most-revisited bucket.** `scripts/commit_sizes.py` prints it.

### Rework has two honest definitions

- **Verification rework** — the story's first attempt was verified `FAIL`.
- **Dispatch rework** — the story was dispatched more than once, for any reason.

The second definition includes stories whose first attempt died before
verification could judge it: `agent_error`, `timeout`, `killed`, `question`.
Those absolutely are rework — the story was built twice — and the verification
store cannot see them because nothing was ever verified. **Lead with the
dispatch number.** Give the verification number as the narrower "the gates
rejected it" figure.

### Two dispatches can share every old key field

Group verification attempts by the recorded dispatch before collapsing to a
story. Dispatch identity comes only from recorded evidence that carries it; an
old `(epic, node, attempt, persona)` key and a timestamp window do not make a
second dispatch.

### Unknown is not zero

Missing tokens, dollars, runner, route, model, or landing data stay unknown.
Keep measured subtotals beside the rows that make them partial, legacy, or
unknown, and preserve accounting provenance even when one field happens to be
complete. Optional cache and request counters can remain unknown even when token
totals are complete.

### Empty input is valid

An empty ledger produces an empty report, not an exception. Percentages and
coverage have explicit no-denominator paths.

### `usage_records` has ~2 rows per attempt, not 1

One row per persona: `implementer`, `judge`, and `debugger` when the ladder
climbs. Always count `distinct attempt` per `(epic_id, node_id)`. Dividing row
counts by story counts overstates rework by roughly 2×.

### The stores do not cover everything that landed

`scripts/rework.py` re-runs this cross-check every time and prints the coverage
percentage or names the absence as unknown. **Say the coverage out loud in the
report.** Report the estimate and refuse to call it a census.

### Daily buckets are noise at this volume

Small periods have small denominators — one story can make a day look like
100% rework. Use **weekly** buckets and a **rolling 20-story window** ordered
chronologically, which is what the script emits. A rolling window over stories
rather than days is the one that shows a learning curve if there is one,
because it holds the denominator fixed.

### Read the stores read-only, always

The helpers resolve `.ergane/` first and honor the legacy `.factory/` name. Use
`--runtime-root` for a temporary store. This is the live store in normal use. A
skill that reports on the factory must not be a skill that writes to it.

### LOC has no network bootstrap

`scripts/loc.py` uses a stable local `cloc` executable or reports the
capability unavailable. It does not fetch executable code from a remote branch.
Its scratch output lives in a run-unique temporary directory.

## What to conclude, not just what to print

**Pair the rework trend with the findings ledger.** Rework rate is the outcome
metric for the whole detect-and-promote loop; `ergane findings list` is the
input side. Report the current rework trend beside the current findings trend.
That pairing is the report's actual finding; the tables are supporting evidence.

**Separate growth-phase artifacts from structural ones.** Additive commit
ratio and a findings backlog that outruns resolution can be artifacts of a
young repository. What does not correct itself is anything that compounds with
dispatch volume: test-code authorship, gate count as Goodhart surface, and
unknown quantities silently collapsed to zero. If asked to editorialise, sort
the criticisms by that axis rather than by severity.

**A flat trend is a finding, not a null result.** Name the period and the
denominator, then say plainly when there is no improvement.

## Baseline

`reference/baseline-2026-08-19.md` holds the full numbers as measured on
2026-08-19. It is a historical snapshot, not the default report. Re-measure
rather than quoting it — but do report which way a number moved, and by how
much.
