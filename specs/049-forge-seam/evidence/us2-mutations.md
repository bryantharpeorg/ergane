# 049-US2 evidence

Measured on this story rebased onto US3, not beside it.

    $ uv run pytest -q
    2946 passed, 44 skipped, 5 warnings in 307.43s (0:05:07)

US2-S5 — the sole-author guard in `tests/test_ergane_init_check.py`, untouched
by this diff, still passes: `gate_check:`, `unknown_check:` and 034's local
facts are built only by `factory/mergequeue/onboard.py` (FR-008).

    $ uv run pytest -q tests/test_ergane_init_check.py -k "sole_author or judgment"
    1 passed, 13 deselected in 0.23s

One production edit at a time on a green *committed* HEAD (tree clean before and
after), reverted with `git checkout HEAD --`, over the six suites this story
touches — 85 passed unmutated. Each edit is the one its test's docstring names.

| edit | tests red |
|---|---|
| M1 the visibility check returns to the judgment | 16 · no-visibility, scan, +14 |
| M2 Q2 decided by a constant, not the forge | 5 · SC-003 control, +4 |
| M3 the GitHub forge stops contributing it | 4 · D-007, three profiles |
| M4 D-007's remedy reworded by one word | 1 · D-007 |
| M5 Q3 folded back into Q2 | 1 · gates-but-waits |
| M6 `gated_landing` renamed back to `merge_queue` | 8 · source scan, +7 |
| M7 `evaluate_repo` drops `reading.findings` | 5 · D-007, US1's findings, +3 |
| M8 the title remedy stops reaching it | 2 · landing_title, squash-title |
| M9 **control** — the source scan reads a missing file | 1 · source scan |

No mutation came back green, before the rebase or after it — the counts above
are the post-rebase run. M9 is the anti-vacuity control: a scan proving the
judgment names no forge's configuration must fail when it reads nothing.
