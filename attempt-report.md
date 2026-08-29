# Attempt 3 — US3: A declaration that names nothing is refused

## What changed

Added one committed test to `tests/test_089_validate_checks_fixes.py`:

- `test_validate_fixes_less_specs_in_real_corpus_unchanged` (T018a / US3-S4):
  Iterates the repository's own `specs/` corpus, selects every spec whose
  frontmatter omits `fixes:`, and asserts that `ergane spec validate` treats each
  exactly as it did before this story: no `fixes` entry in `checked` or
  `skipped`, identical exit code, and identical findings when the new layer is
  monkeypatched to a no-op.

This closes the gap the judge identified in Attempt 2: a synthetic fixture
proves the code path, but only a corpus-wide test proves the acceptance scenario
over the real specs that omit the key.

## Implementation state

The `_check_fixes` layer in `factory/cli/nouns/spec.py` was already present and
unchanged in this attempt. The existing implementation already satisfies the
other acceptance scenarios:

- US3-S1: unknown `fixes:` key refused, naming key and store path (T015).
- US3-S2: known keys pass and report count (T016).
- US3-S3: absent ledger reports `fixes` layer as `not checked`, no refusal (T017).
- US3-S4: fixes-less specs unchanged (T018 + T018a).
- FR-006 / trap 6: validate does not create the store it reads (T019).

## Modules untouched by this story

Per T022 / FR-007, this story edits neither of the read-only modules named in
FR-007:

- `factory/doctor/triage.py` — unchanged.
- `factory/roadmap/models.py` — unchanged.

## Gate result

`uv run pytest -q` — 5155 passed, 58 skipped, 0 failed.

## Note on report location

The `$ATTEMPT_ARCHIVE` directory is mounted read-only, so this report is
committed into the worktree at `attempt-report.md`.
