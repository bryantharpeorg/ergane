# 049-US4 evidence

    $ uv run pytest -q
    2968 passed, 44 skipped, 6 warnings in 316.53s (0:05:16)

Baseline measured on this worktree before the first commit: `2960 passed, 44
skipped, 6 warnings in 315.92s`. The eight added tests are this story's, and the
**skip count is unchanged at 44** — nothing here hid a test behind a skip.

## The battery

One production edit at a time on a clean **committed** tree, over the three
suites this story touches (34 items), each edit reverted with `git checkout --`
and the tree asserted clean by `git status --porcelain` — which lists untracked
files, the ones `checkout` does not remove — before and after every row. Every
run purged `__pycache__` and ran under `PYTHONDONTWRITEBYTECODE=1`: CPython
validates a cached `.pyc` on `(mtime-in-whole-seconds, size)` only, so two
same-size mutants written inside one wall-clock second otherwise make the second
run execute the first's bytecode, and it fails *toward green*. Every row is
asserted to have collected 34 items, because a run that collected nothing reads
exactly like a survivor. Only `passed`/`failed` are quoted; warning counts are
not evidence, since a `SyntaxWarning` fires at compile time and a warm cache
reports fewer of them on an identical tree.

| edit | result | tests killed |
|---|---|---|
| **M0 control — no edit at all** | **0 failed, 34 passed** | none, which is the point |
| M1 the wiring operation reports acts it never issues | 13 failed, 21 passed | the round trip, both idempotence cases, both refusals, and 8 of the existing `--wire` suite |
| M2 `--wire` reaches past the seam for the forge's client again | 1 failed, 33 passed | `test_init_wire_drives_the_forge_it_resolved_rather_than_a_forge_native_client` |
| M3 the squash title is written without reading it first | 2 failed, 32 passed | both idempotence cases |
| M4 the ruleset comparison stops deciding anything | 2 failed, 32 passed | both idempotence cases |
| M5 the prerequisite probe is dropped | 3 failed, 31 passed | no-usable-credentials, gh-absent, gh-unauthenticated |
| M6 a refusal carries no by-hand steps | 3 failed, 31 passed | cannot-change-settings, gh-absent, token-without-admin |
| M7 the seam stops declaring the wiring operation | 3 failed, 31 passed | the protocol shape, and conformance for *both* registered forges |
| M8 `wiring.py` defines a second class of the same name | 7 failed, 27 passed | the refusal-identity test, and every CLI refusal path |

No survivors. **M0 is the control the rest of the table depends on**: pointed at
an unmutated tree the battery detects nothing, so every red above is the edit
talking rather than the harness.

Two rows carry more than a count. **M2** is the story's criterion in one line —
it restores exactly the `.client` this story deleted, the existing `--wire`
suite stays green, and only the new CLI test notices. That is what "the seam was
decorative at this call" meant, and what US4-S4 asks to have proven. **M7** kills
conformance for `conformance-probe` as well as `github`, so the registry
parametrization really did enrol a second forge rather than run twice over one.

**M1's 13** is the other half worth reading: eight of them are 034/US3's own
`--wire` tests, unedited by this story. The wiring they assert now runs through
`apply_landing_policy`, so the seam is load-bearing rather than a name laid over
the old call.

## What no test here proves

No test in this repository wires a real repository on a real forge. The GitHub
implementation is exercised against a model of a GitHub repository driven
through the real `gh` argv surface, which is the strongest evidence available
offline and is not the same claim. `ergane init --wire` against a live target is
the operator's check, and the wiring path is unchanged by this story — 034/US3's
`wire_repo` is reached, not rewritten.
