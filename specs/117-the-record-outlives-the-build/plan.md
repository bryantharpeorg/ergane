# Implementation Plan: the record outlives the build

**Spec**: `specs/117-the-record-outlives-the-build/spec.md`

One column joins the upsert key, three columns join the row, and the reader
learns to group. The migration is the risk, not the schema.

## What already exists, and where

- **The key**: `UNIQUE (epic_id, node_id, attempt, form)` at
  `factory/verify/store.py:176`, annotated `-- upsert key (record_verification)`.
  It is mirrored in Python as `_RESULT_KEY = ("epic_id", "node_id", "attempt",
  "form")` (`:486`), and the upsert SQL is **generated** from that tuple
  (`_UPSERT_RESULT_SQL`, `:512-521`): the conflict target and the updated-column
  list both derive from it. Adding a name to `_RESULT_KEY` changes both without
  editing SQL text — read `:512-521` before assuming anything must be hand-written.
- **The reason the upsert exists**: the comment at `:510-511` — "A re-run
  overwrites every column except the four it matched on: the second recording of
  an attempt is the current one" — and `upsert_result`'s docstring (`:526-531`),
  which promises a row id "stable across reruns". Both are correct about a
  Temporal retry and neither distinguishes a re-dispatch. FR-002 preserves the
  first meaning; the spec's frontmatter explains why keying on the dispatch keeps
  it exactly.
- **The migration machinery, and its precedents**: `_migrate(conn)` called from
  the schema application at `:323-329`. Two precedents worth reading before
  writing: the additive one at `:105` ("written at 2, so `_migrate` below adds
  the column in place rather than…") and the destructive-but-safe one at
  `:362-383` ("`ALTER TABLE` cannot widen a CHECK, so: new table, rows copied,
  old dropped", ending in `ALTER TABLE escalations_v7 RENAME TO escalations`).
  A UNIQUE constraint cannot be altered in place either, so US1 needs the second
  shape.
- **The column-order trap, already written down**: `:200-201` — "Last in the
  table because ALTER TABLE ADD COLUMN appends, and a migrated store must have
  the same column order as a fresh one." This is FR-003 and it is the single
  easiest thing in this epic to get wrong.
- **The columns to add for US2**: `VerificationResult` and `_RESULT_COLUMNS`
  (`:488`), described as "Everything `upsert_result` writes, in DDL order".
- **Where persona and model are known**: the attempt's dispatch carries both;
  `loop_summary` already names the exact ladder that ran, which is the precedent
  for carrying rung-level facts onto the row.

## Traps

**Trap 1 — a UNIQUE constraint cannot be altered in place.** SQLite has no
`ALTER TABLE … DROP CONSTRAINT`. US1 must use the rebuild shape already in this
file at `:362-383`: create the new table, copy rows across supplying the dispatch
value for the old ones, drop the old table, rename. Anything else silently leaves
the old constraint and the defect intact while the tests pass against a fresh
store.

**Trap 2 — column order must match a fresh store, and the file says so.** After
a rebuild-style migration the column order is whatever the copy produced; after
`ADD COLUMN` it is appended. FR-003 requires a migrated store and a fresh store
to agree, because `_RESULT_COLUMNS` is documented as being "in DDL order" and a
positional read against a divergent order returns the wrong field for every row.
Assert the orders match, in a test, over a store built by migration and one built
fresh.

**Trap 3 — old rows need a dispatch value that cannot collide.** FR-004. Rows
written before this change belong to one unnamed dispatch. Give them a single
reserved value that no real dispatch can produce, so a later dispatch of the same
node does not merge into them. A NULL will not do it: SQLite treats NULLs as
distinct in a UNIQUE index, which would make every historical row unique on its
own and quietly disable the idempotence FR-002 requires for them.

**Trap 4 — the discriminator must be stable across a Temporal retry.** If the
value changes when an activity is retried, every retry writes a new row and the
upsert stops protecting anything. Use the identity that a retry preserves — the
dispatch's workflow run — not a timestamp, not a fresh uuid minted per activity
attempt. `criteria_sha256` explicitly cannot serve: it was identical across all
nine rows of the measured case.

**Trap 5 — US2's route and alias must be recorded at the point that resolved
them.** The debugger rung relabels the persona without re-resolving
`model_alias`, so a row that copies the persona's registry alias at write time
records the wrong model for exactly the rung this defect was noticed on. Record
what the attempt actually ran with, at the point it was resolved, and US2-S3 is
the proof.

**Trap 6 — FR-007's "unknown" is a value, not a silence.** An old row whose
persona column is NULL must read as unknown to a consumer, not as an empty
string that renders like a real persona named "". Decide the representation once
and assert it.

**Trap 7 — US3 must order by write time, not by id.** Surviving rows keep their
original ids, which is precisely why id order is not chronological order in a
re-dispatched node. FR-008 and US3-S4.

**Trap 8 — read-only consumers exist.** `node_history` and `attempt_timings` are
exported and already used by retry prompts and by at least one consumer outside
this repository. US3 may reshape what they return only in the ways FR-008 and
FR-009 permit: a single-dispatch node must read exactly as today.

## Sizing

US1 is the epic: a key change plus a rebuild migration, and four of the eight
traps are in it. US2 is three columns and a resolution point. US3 is a grouping
and a rendering.

If an attempt is editing the usage ledger or Temporal's retention, it has gone
outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the migration and the key. Only a real re-dispatch proves the
evidence survives:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. dispatch a one-story spec and let it record a few attempts
uv run ergane build start <spec-dir> --target-repo .
# 2. reset and re-dispatch the same spec
uv run ergane build reset <epic-id>
uv run ergane build start <spec-dir> --target-repo .
# 3. read the node's history and count the dispatches
uv run python -c "
from factory.verify.store import connect_readonly, node_history
conn = connect_readonly('.factory/verification.db')
for r in node_history(conn, '<epic-id>', 'us1'):
    print(r.attempt, r.verdict, r.persona, r.model_alias)"
```

The demonstration succeeds when both dispatches' attempt-one rows are present,
distinguishable and ordered, and each names its persona and model. Before this
spec the second dispatch's attempt one has silently replaced the first's, and the
persona and model columns do not exist. Paste the output into the attestation.
