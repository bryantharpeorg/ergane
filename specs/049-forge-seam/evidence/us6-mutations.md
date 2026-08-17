# US6 mutation battery

## The suite, both sides of the change

Cold cache both times — `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`,
`-p no:cacheprovider` — because CPython validates a cached `.pyc` on
`(mtime-in-whole-seconds, size)` alone, and a warm cache also suppresses
compile-time warnings. So `passed` and `skipped` are quoted and warnings are not.

```
before (0f8f6b3):  2985 passed, 44 skipped, 6 warnings in 315.54s (0:05:15)
after:             3094 passed, 44 skipped, 6 warnings in 316.90s (0:05:16)
```

3094 − 2985 = 109, which is exactly what `tests/test_forge_sweep.py` collects:
105 parametrized module cases and 4 tests beside them. **Skips are unchanged at
44** — this story adds no test that could hide in one.

US6's deliverable *is* a test, so the ways a test can be secretly unable to fail
are the central risk rather than a footnote. Each row below breaks one thing the
sweep claims to check, on a committed tree, and records the verbatim summary.
Instrument discipline, enforced by the runner rather than promised: `git status
--porcelain` asserted empty (tracked **and** untracked) before and after every
row; `__pycache__` purged and `PYTHONDONTWRITEBYTECODE=1` set before every run,
so two same-size mutants inside one wall-clock second cannot execute each
other's bytecode; and the **collected count recorded on every row**, so a run
that collected nothing cannot read as a survivor.

| # | mutation | collected | result |
|---|---|---|---|
| — | baseline, unmutated | `109 tests collected` | `109 passed in 0.46s` |
| **M1** | **CONTROL — point the sweep at a path that does not exist** | `5 tests collected` | `3 failed, 1 passed, 1 skipped in 0.19s` |
| M2 | put `via gh` back into `merge_activities`' read-failure finding | `109` | `1 failed, 108 passed in 0.48s` |
| M3 | plant `mergeStateStatus` in `classify.py` — inside the directory, off the allowlist | `109` | `1 failed, 108 passed in 0.47s` |
| M4 | allowlist a module that spells nothing (`classify.py`) | `109` | `1 failed, 108 passed in 0.50s` |
| M5 | empty `FORGE_NATIVE_SPELLINGS` | `109` | `1 failed, 108 passed in 0.46s` |
| M6 | break the extractor: `_spelled` returns nothing | `109` | `5 failed, 104 passed in 0.36s` |
| M7 | narrow the merge-surface sweep: drop the `factory/mergequeue` glob | `109` | `1 failed, 108 passed in 0.47s` |
| M8 | widen the swept set by name instead of by construction | `109` | `1 failed, 108 passed in 0.47s` |
| M9 | rename `apply_landing_policy` to a word the package reserves | `109` | `1 failed, 108 passed in 0.47s` |
| M10 | drop the `enforcement` field from the ruleset payload | `109` | `1 failed, 108 passed in 0.47s` |

## M1, the control, run first and not last

If the sweep reads nothing then every other mutation below it is meaningless, so
this is the row that had to come first. Pointing `COMPONENT_ROOT` at a directory
that does not exist:

```
SKIPPED [1] tests/test_forge_sweep.py:196: got empty parameter set for (path)
FAILED tests/test_forge_sweep.py::test_the_sweep_read_the_package_and_can_still_find_a_forge_native_term
FAILED tests/test_forge_sweep.py::test_every_forge_module_is_guarded_because_of_where_it_lives
FAILED tests/test_forge_sweep.py::test_the_word_the_package_may_not_spell_still_lives_only_in_the_data_file
3 failed, 1 passed, 1 skipped in 0.19s
```

That `SKIPPED` line is trap 4 with its face showing. A sweep whose glob stops
matching does not fail and does not disappear — pytest turns 104 assertions into
**one silent skip**, and a suite tail reading `passed` is unchanged except for a
number nobody reads. The anti-vacuity test is what converts that silence into
three red lines, which is why US6-S2 is not a formality.

## M6, the one worth reading twice

Breaking the extractor so it returns no tokens leaves every *non*-allowlisted
module green — 100 modules "prove" they name no forge, by a scanner that can no
longer see one. What catches it is the two things the sweep asserts besides
absence: the anti-vacuity control (the same scanner over `github_forge.py` must
still find terms) and the allowlist's second direction (an allowlisted module
must still spell something). Five red, and none of them from the modules the
sweep is nominally about.

## M2, which was not a planted mutation first

M2 restores a leak the sweep found in the real tree on its first run.
`merge_activities.py`'s read-failure finding read `could not read the repo via
gh`. `tests/test_forge_landing.py`'s own docstring calls that prose US2's; US2
left it too. Both stories' structural checks are scoped to one module or five
named activities, so neither was pointed at it. A package-wide sweep with a path
allowlist is the shape that finds a leak nobody assigned to themselves — which is
the whole argument of US6, arriving as evidence instead of as a claim.
