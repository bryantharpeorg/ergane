# 051-US1 evidence — full suite and mutation battery

## Full suite

Run on a **cold** cache: every `__pycache__` under `factory/` and `tests/`
removed and `.pytest_cache` deleted immediately before, with the tree clean —
tracked and untracked — at the start.

    $ git status --porcelain
    (no output)
    $ find factory tests -name '__pycache__' -type d -prune -exec rm -rf {} +
    $ rm -rf .pytest_cache
    $ uv run pytest -q
    3150 passed, 44 skipped, 6 warnings in 300.33s (0:05:00)

Skips are **44**, the baseline. No test in this story is skipped, and none was
added that could be. The warning count is not quoted as evidence: a
`SyntaxWarning` fires at compile time, so a warm cache reports fewer than a cold
one on an identical tree.

## Mutation battery

One production edit at a time in `factory/cli/init.py`, applied to a green
committed HEAD and reverted with `git checkout HEAD --`. `__pycache__` is purged
before every single run and `PYTHONDONTWRITEBYTECODE=1` is exported: CPython
validates a cached `.pyc` on `(mtime-in-whole-seconds, size)` alone, and two
same-size mutants written inside one wall-clock second otherwise execute the
first's bytecode — a failure that reproduces stably and always toward green.

The tree is asserted clean **tracked and untracked**, before the battery and
after every revert. `git checkout -- .` removes neither an untracked file nor a
stale `.pyc`, so "the diff looks right" is not the same claim.

Measured over the three suites this story can reach:

    tests/test_ergane_init_landing_branch.py
    tests/test_ergane_init.py
    tests/test_ergane_init_check.py

**The fixtures create `master` explicitly** (`git init -b master`). On a host
whose `init.defaultBranch` is `main` — this project's boxes — the derived branch
and the replaced literal coincide, and M1 below would show *zero* red tests
while the product stayed broken for everyone else.

| row | edit | result |
|---|---|---|
| **M0** | **control**: point at `::test_no_such_test_exists` | `(no match in any of [<Module test_ergane_init_landing_branch.py>])` rc 4 |
| — | collection, unmutated | `36 tests collected` |
| — | unmutated | `36 passed` rc 0 |
| M1 | the derivation removed; the literal is the answer again (the base tree) | 4 failed, 32 passed |
| M2 | `symbolic-ref --short HEAD` instead of `rev-parse --abbrev-ref HEAD` | 2 failed, 34 passed |
| M3 | the detached-HEAD sentinel guard dropped | 1 failed, 35 passed |
| M4 | the derivation put in front of the existing-manifest preference | 1 failed, 35 passed |
| M5 | the fallback literal changed from `main` to `trunk` | 1 failed, 35 passed |
| M6 | one extra interview question (FR-010 / SC-004) | 14 failed, 22 passed |

M0 is first, not last. A sweep pointed at a path that does not exist passes
forever, and if the control had reported "passed" every row under it would be
noise. `pytest` answers `no match in any of [...]` and exits 4, and the
collection count is pinned at 36 so a silently shrinking suite is a failure too.

### Which tests went red, and why that is the right set

**M1** — the base tree's behaviour, restored. Four red:

- `test_the_question_offers_the_branch_the_repository_is_on` (US1-S1, FR-001)
- `test_pressing_enter_writes_master_and_the_real_check_passes` (US1-S2)
- `test_a_typed_branch_wins_unchanged_over_the_derived_default` (US1-S4)
- `test_the_derived_branch_rides_the_default_slot_every_question_uses` (FR-005)

**M2** — the route choice the plan left open. Two red:

- `test_the_branch_reading_answers_none_when_head_does_not_resolve` (FR-002)
- `test_an_empty_repository_offers_the_literal_and_init_completes` (US1-S3)

This is the row the empty-repository test exists for. `symbolic-ref` names the
*unborn* branch of a repository with no commits, so it would offer `master`
where US1-S3 requires the literal. Both readings are green on a repository that
has a commit; only this case tells them apart.

**M3** — the detached-HEAD sentinel. One red:

- `test_the_branch_reading_answers_none_when_head_does_not_resolve`

`git rev-parse --abbrev-ref HEAD` answers the literal string `HEAD` on a
detached HEAD, and git refuses to create a branch by that name, so an unguarded
reading would offer a branch that cannot exist.

**M4** — FR-004, the preference this story must go *underneath*. One red:

- `test_an_existing_manifest_is_offered_ahead_of_the_repository_reading`

That test's repository is on `master` while its manifest declares `main`, which
is the only arrangement in which this mutation is visible: on a repository whose
branch already matches its manifest, the two answers coincide.

**M5** — the fallback literal itself. One red:

- `test_an_empty_repository_offers_the_literal_and_init_completes`

This row is why that test asserts the offer twice — once against
`_PLACEHOLDERS["landing_branch"]`, which says *which* value is the fallback, and
once against `"main"`, which says what it is. With only the first assertion the
test followed the mutation and stayed green; the second was added before the
battery ran, from planning it.

**M6** — FR-010 and SC-004, the story's blast radius. Fourteen red, across all
three suites, including nine tests in files this story never opened. Adding one
question is what "prompter ran out of answers" looks like, and it is the failure
mode the spec forbids by forbidding a new manifest key.

### Not mutated, and why

`factory/mergequeue/onboard.py` is not in this battery because it is not in this
diff. `_landing_branch_finding` produces the message quoted in the spec's
Context and is correct: the check was right, the offer was wrong. A mutation
there would measure 034's tests, not this story's.
