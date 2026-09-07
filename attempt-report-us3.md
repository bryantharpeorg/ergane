# Attempt 1 — US3: One verb assembles the causal chain

## What changed

Three commits, tests first:

- `tests/test_127_us3_build_why.py` (new, T018–T020) — ten tests committed
  observed-red on the unimplemented verb: the failed-node chain (S1: verdict,
  gate tail, judge feedback, queue outcomes, transcript directory, terminal
  reason), the whole-epic report (S2), the passed-node control (S3), the
  clipped tail against `EVIDENCE_TAIL_LINES`, the transcript path composed from
  the declared root and never the cwd (trap 11), the degraded reading when the
  query is refused, the unknown-node refusal, and the `NOT_FOUND` refusal in
  `_query_status`'s shape (trap 16 — no `epic_history` discriminator; that is
  US5's).
- `factory/cli/nouns/build.py` (T021) — the `why` subcommand, registered beside
  `attempts`: the store half read through `node_history`/`epic_history` the way
  `attempts_command` reads the store (module-level `_verification_store_path`
  called, not a third copy), the query half read through the `epic_status`
  query the way `_query_status` does, under the same guard pair. The transcript
  directory is composed with `transcript_dir` against
  `resolve_env_path(ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, DEFAULT_FACTORY_ROOT_PATH)`
  and never opened. What counts as a failure to explain is the node's own state
  read off the query answer, not the presence of a node argument — S3 names a
  passed node and must still be told there is nothing to explain.
- `factory/notify/messages.py` (T021) — the clipper promoted from `_tail` to a
  public `tail`, behaviour and bound unchanged, four internal call sites moved
  to the public name, `_tail` kept as an alias. `build.py` imports the public
  name; no second clipper was written (FR-009).
- `docs/127-us3-why-verb-evidence.md` (T022) — one pasted run of the verb
  against a real killed node, beside the worker-logged `LANDING_REF_CONFLICT`
  exception that was previously the only place the answer existed. The run is
  real end to end: real clone, real bare origin, real non-fast-forward refusal,
  the factory's own `ensure`/`push_branch`/`_failure_detail` paths, a live
  Temporal server, and the verb executed as a CLI subprocess against the still-
  queryable execution. Trimmed to the lines that carry the answer; the stored
  `output_tail` it quotes was 42 lines and the verb printed 20 of them, the
  clip naming the 22 dropped.

Two existing test files were extended for the verb's presence, not weakened:
`test_build_verbs_take_an_epic_id.py` classifies `why` in `LIVE_EPIC_VERBS`
(it acts on a started epic, and the epic id is the handle the operator holds),
and `test_ergane_status.py`'s guard sweep declares `_query_why` under the same
`TRANSPORT_FAILED`/`QUERY_REFUSED` pair `_query_status` carries.

## Scope discipline

No store, no query column, no directory walk. The `epic_history` discriminator
on `NOT_FOUND` is not built here — `why` refuses on `NOT_FOUND` exactly as
`_query_status` refuses, and US5 replaces that branch (trap 16). The duplicate
`_verification_store_path` definition was called, not tidied (trap 12).

## Diff budget

49,146 bytes against `DIFF_REFUSAL_THRESHOLD` = 65,536 (`factory/verify/
diffbounds.py`), code, tests and the pasted run together. The gate output in
the paste is the clipped 20-line tail, not the field whole (trap 15).

## Gates

`uv run pytest -q` (the one declared gate): 5719 passed, 49 skipped, green on
the final state. The red state for T018–T020 is committed at `4cba481`.