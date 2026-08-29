# Attempt 1 — US2: The record says what the verdict was measured against

## What changed

Two commits, tests first. Six committed files, one new test module:

- `tests/test_118_record_names_its_base.py` (new) — the story's eight tests,
  written first and committed failing (T011–T013). 7 failed red against the
  unmodified tree (plus a fixture-corrected pass), each for the reason the
  plan predicted: `compose_result() got an unexpected keyword argument
  'base_ref'`, and a status document with no base or head in it.
- `factory/verify/models.py` (T014, T015) — `VerificationResult.base_ref`
  (the row) and the matching parameter on `compose_result`, both defaulted
  to `None`. That `None` **is** the unknown representation, decided once:
  a missing base reads as absent everywhere — never `""`, never a branch
  name, never a placeholder sha — and the composer cannot invent one, since
  it has no git to read and no default would be honest.
- `factory/verify/store.py` + `specs/002-verification-gating/contracts/
  verification-store.sql` (T014/T013) — schema 8: the additive `base_ref`
  TEXT column on `verification_results`, nullable, in DDL, contract file,
  `_RESULT_COLUMNS`, both codecs, and the `ALTER TABLE` migration keyed off
  `PRAGMA table_info`. NULL for pre-118 rows, never backfilled.
- `factory/workgraph/workflow.py` (T014/T016) — `_verify` passes
  `prepared.base_ref` to the composer (trap 5: the pin the attempt actually
  ran against; no second git read at record-writing time), `NodeStatus`
  carries `base_ref` and `landing_head`, and the landing poller records
  what the forge last reported.
- `factory/mergequeue/models.py` — `Landing.last_observed_base`.
- `factory/cli/nouns/build.py` (T016) — `_base_token`, appended to every
  node line.

## How the scenarios are covered

- **US2-S1 (row carries the prepared base)** — three tests. The composer
  unit pins the surface; the interpreter run pins the provenance (trap 5):
  the scripted world's target repo `/srv/factory/targets/library` does not
  exist on this host, so a recorded `base_ref` of `"9" * 40` could only have
  come from `PreparedWorktree.base_ref`. A third test proves the column
  round-trips through the real store.
- **US2-S2 (status shows base beside landing head)** — the real
  `epic_status` query, put through the real payload converter
  (`as_json_document`), then the real `render_status`. The landing head is
  the forge's last reported base (`PrSnapshot.base_sha`, the only
  landing-branch observation a workflow can hold without running git,
  constitution IV), recorded on every poll whatever it decided, ahead of the
  classify branch — a pending poll also says where the branch stands — and
  never overwritten by a poll that named no base ("did not say" is not a
  fact about the branch; same posture 069 set for the classifier). Controls:
  a node with no landing shows the base alone and renders no head; a node
  that never dispatched, and a pre-118 worker's document, render neither
  token, byte-identical to the old line.
- **US2-S3 (old rows read as unknown)** — a row inserted with only the
  columns a pre-118 writer knew, into a store the current writer migrated.
  The migration makes the column NULL, `node_history` reads `None`, and the
  test asserts `is None` — not a default that looks like a sha.

## The one line this story was for

Rendered by the committed code from a committed test's document shape:

```
us2  ENQUEUED  attempt 1  factory/118-a-verified-tree-is-the-tree-that-will-merge/us2  base 111111111111  landing head 999999999999 at factory/118-a-verified-tree-is-the-tree-that-will-merge/us2
```

Both SHAs on one line, twelve hex characters each: the stale-base PASS
would have been visible in exactly the seconds the finding said it should
have been.

## Traps, accounted

- **Trap 5** — the base travels `prepared.base_ref → compose_result →
  row`; no code path reads git at record time. The provenance is asserted
  by the non-existent target repo, not by trusting the caller.
- **T015 (decide the unknown once)** — `None` throughout: column NULL,
  dataclass field `str | None`, render sentinel `UNKNOWN_BASE` only for the
  *head* (a landing a forge never reported), with `"base <unknown>"` the
  output when a head exists but recorded nothing. The sentinel is braced so
  it cannot collide with a sha and read as a commit.
- **FR-010 (untouched things)** — the criteria snapshot, the reuse rule and
  the between-attempts continuity are untouched by this story: `ensure` and
  `_is_ancestor` were not edited (only `_verify`, the query, the poller and
  the render read what US1 already produced), and US1's six tests pass
  unmodified in the full run.

## Gate result

`uv run pytest -q` — **5188 passed, 58 skipped, 0 failed** (7m04s).

The scoped run is `tests/test_118_record_names_its_base.py`: 8 passed.

The red-first evidence, on the pre-implementation tree at `95ac948`:

```
FAILED .../test_118_record_names_its_base.py::test_the_composer_put_the_prepared_base_on_the_row - TypeError: compose_result() got an unexpected keyword argument 'base_ref'
FAILED tests/test_118_record_names_its_base.py::test_a_row_without_a_base_reads_as_unknown_not_as_a_guess - TypeError: ...
FAILED tests/test_118_record_names_its_base.py::test_a_verified_attempt_s_row_carries_the_prepared_base - TypeError: ...
FAILED tests/test_118_record_names_its_base.py::test_the_status_line_shows_the_base_beside_the_landing_head - KeyError: 'landing_head'
FAILED tests/test_118_record_names_its_base.py::test_a_node_with_no_landing_shows_the_base_alone - KeyError: 'base_ref'
FAILED tests/test_118_record_names_its_base.py::test_a_row_from_before_this_change_reads_as_unknown - OperationalError: no such column: base_ref
FAILED tests/test_118_record_names_its_base.py::test_the_base_survives_the_store_round_trip - OperationalError: no such column: base_ref
7 failed, 1 passed in 1.72s
```

## Migration-shaped decisions

- **Schema 8**, additive column, `ALTER TABLE ADD COLUMN`, no rebuild.
  `tests/test_verify_store.py` pins schema 8 and the column list; the DDL
  contract file and the store are compared structure-for-structure by the
  existing contract test, which forced both to move together.
- **No backfill.** A row measured before 118 cannot recover its base
  without re-deriving it, and re-derivation is precisely the trap. NULL is
  the record's answer, and it is stated in the contract DDL's own comment.

## Not done, and not in scope

US1 and US3 own the currency test and the standards resolution; neither
file they own beyond `worktree.py`/`prompt.py` was touched here. The live
floor demonstration named in the plan's verification section is T025's, in
US3's slice — this story's line is demonstrated above from the committed
renderer itself.