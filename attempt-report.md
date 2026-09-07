# 130-US1 attempt report: a read-only-looking verb does not write

## What changed

Two commits, tests first:

- `tests/test_130_us1_derive_json_does_not_write.py` (new, T001–T005) — the
  five boundary tests over `ergane spec derive`. T001 seeds a differing
  artifact (`target_repo` naming another repo, the harm the ledger row
  records) and asserts bytes **and mtime** survive a `--json` run with no
  output path; observed red. T002 and T003 are the write controls (explicit
  `-o`, and no `--json`). T004 asserts the printed document carries no
  artifact path; observed red. T005 asserts `build ship --json` still reaches
  its summary, written so it fails against a guard keyed on `--json` alone.
- `factory/workgraph/cli.py` (T006) — the write at `derive_command` is now
  gated on `args.output is not None or not as_json`: an explicit output path
  is a request to persist, a call without `--json` writes exactly as today,
  and a `--json` call with no path prints and persists nothing. The document
  names the artifact only when one was written.
- `factory/cli/nouns/build.py` (T006) — `ship_command` passes a copy of its
  namespace to derive with `output` filled in, because ship requires the
  artifact on disk at stage 3 and its own `--json` is a presentation flag.
- `tests/test_ergane_spec.py` — 019-US2's committed control asserted the
  `artifact` key; under FR-003 the key is absent with no output path, so the
  assertion is inverted in place, with a comment naming 130-US1.

## The red runs

T001 and T004 against the tree as received:

```
$ uv run python -m pytest tests/test_130_us1_derive_json_does_not_write.py -q
FAILED tests/test_130_us1_derive_json_does_not_write.py::test_derive_json_without_output_path_leaves_seeded_bytes_on_disk
FAILED tests/test_130_us1_derive_json_does_not_write.py::test_derive_json_document_carries_no_artifact_path
2 failed, 3 passed, 1 warning in 1.03s
```

T005 discriminates a naive guard. With the write keyed on `--json` alone
(the shape trap 3 warns about), ship's stage-3 check raises and the suite
catches it:

```
$ uv run python -m pytest tests/test_130_us1_derive_json_does_not_write.py -q
FAILED tests/test_130_us1_derive_json_does_not_write.py::test_derive_json_with_output_path_writes_there
FAILED tests/test_130_us1_derive_json_does_not_write.py::test_ship_with_json_still_resolves_the_artifact_and_reaches_its_summary
2 failed, 3 passed, 1 warning in 0.27s
```

## The sha256sum pairs (T007)

The fixture is `tests/fixtures/workgraph/valid_epic` copied to a temp path
with a sentinel-free plan.md and tasks.md added, its `workgraph.json` seeded
with `target_repo: /srv/factory/targets/some-other-repo` — bytes no invocation
from that directory would derive. Run with the real console script
(`uv run --project <worktree> ergane spec derive spec --target-repo "$PWD"
--json`) from the temp directory, so the derivation's own `target_repo` is the
temp path and cannot equal the seed.

**Before T006 — the sums differ, which is the defect** (the seeded bytes were
rewritten from `edc445…` to `94d39e…`):

```
$ cd /tmp/e130-before
$ printf '{"epic_id": "valid_epic", ... "target_repo": "/srv/factory/targets/some-other-repo", ...}\n' > spec/workgraph.json
$ sha256sum spec/workgraph.json
edc4453493627a7188c2350eece4ca7211a57593533ebb57f8a11f6524b4e4d2  spec/workgraph.json
$ uv run --project <worktree> ergane spec derive spec --target-repo "$PWD" --json
$ sha256sum spec/workgraph.json
94d39e2f4639bc9f869010ec087f787936191b0df8599413f5a8649e0dccde4e  spec/workgraph.json
```

**After T006 — the sums match** (the seeded bytes survived the same command):

```
$ cd /tmp/e130-after
$ sha256sum spec/workgraph.json
edc4453493627a7188c2350eece4ca7211a57593533ebb57f8a11f6524b4e4d2  spec/workgraph.json
$ uv run --project <worktree> ergane spec derive spec --target-repo "$PWD" --json
$ sha256sum spec/workgraph.json
edc4453493627a7188c2350eece4ca7211a57593533ebb57f8a11f6524b4e4d2  spec/workgraph.json
$ python -c "import json; d=json.load(open('stdout.json')); print(sorted(d))"
['graph']
```

The printed document's only key is `graph` — no `artifact` (FR-003).

## Green gates on the declared command

```
$ uv run pytest -q
5732 passed, 58 skipped, 11 warnings in 500.77s (0:08:20)
```

Baseline before the change measured 5727 passed on the same command (the five
new tests are the difference). One further consumer surfaced in the full run:
`tests/test_colliding_slices_are_ordered.py:276` ran `spec derive --json` and
read the artifact back off disk; it now passes `-o` and its docstring names
why, per FR-002.