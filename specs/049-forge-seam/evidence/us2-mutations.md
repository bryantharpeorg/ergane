# 049-US2 evidence

    $ uv run pytest -q
    2870 passed, 44 skipped, 5 warnings in 296.07s (0:04:56)

US2-S5: `tests/test_ergane_init_check.py`'s sole-author guard, untouched by this
diff, still passes — `gate_check:`/`unknown_check:` and 034's local facts are
still built only by `factory/mergequeue/onboard.py` (FR-008).

    $ uv run pytest -q tests/test_ergane_init_check.py -k "sole_author or judgment"
    1 passed, 13 deselected in 0.23s

One production edit at a time, applied to a green *committed* HEAD (tree clean
before and after), run over six suites and reverted with `git checkout HEAD --`.
Each edit is the one its test's docstring names.

    $ uv run pytest -q tests/test_forge_readiness.py tests/test_onboard.py \
        tests/test_forge_seam.py tests/test_merge_activities.py \
        tests/test_ergane_init_check.py tests/test_ergane_init_wiring.py
    86 passed in 1.88s

| edit | tests red |
|---|---|
| M1 the visibility check goes back into the shared judgment | 17 · no-visibility, source scan, +15 |
| M2 Q2 decided by a constant, not by the forge | 5 · SC-003 control, gates-on-nothing, +3 |
| M3 the GitHub forge stops contributing its finding | 4 · D-007, three profiles |
| M4 D-007's remedy reworded by one word | 1 · D-007 |
| M5 Q3 folded back into Q2 | 1 · gates-but-waits |
| M6 `gated_landing` renamed back to `merge_queue` | 8 · source scan, +7 |
| M7 `evaluate_repo` drops `reading.findings` | 5 · D-007, US1's forge findings, +3 |
| M8 the forge's title remedy stops reaching the finding | 2 · landing_title, squash-title |
| M9 **control** — the source scan points at a file that does not exist | 1 · source scan |

No mutation came back green. M9 is the anti-vacuity control the brief asks for:
the scan that proves `onboard.py` names no forge's configuration must fail when
it reads nothing, and it does. Its second guard needs no mutation — the same
scanner over `github_forge.py` must find *every* banned word, so an emptied ban
list or a broken matcher fails there before it can pass over the judgment.

M4 is the one worth reading twice: a single word changed in a remedy string
fails, which is what "the same remedy an operator reads today" (US2-S2) means.
