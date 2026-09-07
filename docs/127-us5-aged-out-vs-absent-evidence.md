# 127-US5 — the verb's two answers for the two absences

Committed evidence for epic 127's T031: `ergane build why`'s answer for an
epic id nothing is running under, and its answer for an epic whose
verification rows outlived its execution — the two absences that both reached
this verb as `RPCStatusCode.NOT_FOUND` on `epic_status` and were collapsed
into one refusal before this story (FR-010). Both runs are printed output,
executed as real CLI subprocesses; nothing is described that was not read.

## How this was produced

The live Temporal server on `localhost:7233` this worktree's environment
already answers (`epic-why-evidence-final3`, US3's evidence execution, is
still listed on it). No execution was started for either scenario: the
`NOT_FOUND` on `epic_status` is the server's own answer for both workflow ids
dialled.

The verification store is a real store at `/tmp/127-us5-evidence/
verification.db` (scratch, outside the worktree), written with the factory's
own `connect` and `upsert_result` — a FAIL phase attempt for node `us2` of
epic `127-us5-aged-out-demo`, the shape of a node whose suite died on its way
to a landing. `ERGANE_VERIFICATION_DB_PATH` and
`FACTORY_VERIFICATION_DB_PATH` both point the verb at it; `ERGANE_ROOT`
points the transcript composition at `/tmp/127-us5-evidence/factory-root`,
which holds no transcripts — composed, never opened (trap 11).

The discriminator is exercised for real and in the order the verb reads it:
the store rows are read *before* the dial, and `NOT_FOUND` with rows for a
*different* epic (`127-us5-never-started` against a store holding only
`127-us5-aged-out-demo`'s) still refuses — the rows that matter are this
epic's, not the store's mere existence.

## Run 1 (US5-S1, FR-010) — NOT_FOUND, and the store holds no rows: refuse

```text
$ ergane build why 127-us5-never-started
ergane: no epic '127-us5-never-started' is running here and the verification
store at /tmp/127-us5-evidence/verification.db holds no rows for it (looked
for workflow id epic-127-us5-never-started)
exit: 1
```

One line, no traceback — the shape `_query_status` refuses in. It names the
epic id, the workflow id it looked for, and the store path it read; the
store, not the status code, is what told this case from run 2, because both
begin as the same `NOT_FOUND`.

## Run 2 (US5-S2, FR-010) — the same NOT_FOUND, with rows: degrade

```text
$ ergane build why 127-us5-aged-out-demo
epic 127-us5-aged-out-demo — why
us2:
  attempt 2: FAIL (PHASE, verified at 2026-09-06T09:04:00Z)
      gate test: FAIL — exit 1
        gate output (last 20 lines):
          E   AssertionError: the suite died on its way to a landing
          1 failed, 411 passed in 190.02s
  transcript: /tmp/127-us5-evidence/factory-root/transcripts/127-us5-aged-out-demo/us2/attempt-2
  ending: unavailable — the execution has aged out of the server; the ending
(terminal reason, queue outcomes) died with it
exit: 0
```

## What the two runs show, against the requirement

- **The refusal, in `_query_status`'s shape** — one `ergane:` line, exit 1,
  no traceback, naming the epic id, the workflow id looked for and the store
  path read (US5-S1). Before this story the same command said only `no epic
  '…' is running here (looked for workflow id …)` — the store path and the
  no-rows finding are what US5 added to it.
- **The degradation, not a refusal** — the same status with rows prints the
  store half of the chain (verdict, failing gate, bounded tail, transcript
  directory) and exits 0 (US5-S2).
- **The ending named absent, with the reason** — `ending: unavailable — the
  execution has aged out of the server`, in the line the renderer already
  had for an unavailable ending, now carrying *which* absence. No store
  holds `terminal_reason`; the verb says so rather than implying the chain
  is complete.
- **The budget** — both answers trimmed to the lines that carry them; the
  whole story diff is 7,175 bytes against `DIFF_INPUT_LIMIT` = 65,536
  (`factory/verify/diffbounds.py`), evidence included.