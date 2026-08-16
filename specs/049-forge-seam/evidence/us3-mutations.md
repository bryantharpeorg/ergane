# US3 mutation battery

Each behaviour US3 claims to test, broken one at a time on a committed tree, the
suite run, the edit restored. Verbatim final line of each run.

| # | mutation | result |
|---|---|---|
| M1 | `classify.py`: delete the `in_conflict` row | `2 failed, 5 passed in 0.07s` |
| M2 | `models.py`: default off `in_conflict` | `1 failed, 6 passed in 0.08s` |
| M3 | `models.py`: drop `__post_init__`'s legacy `DIRTY` reading | `3 failed, 17 passed in 0.42s` |
| M4 | `merge_activities.py`: build a `GhClient` in `poll_landing` again | `2 failed, 18 passed in 0.11s` |
| M5 | `test_merge_activities.py`: change one landing assertion | `1 failed, 6 passed in 0.07s` |
| M6 | `workflow.py`: import the forge into workflow code | `1 failed, 6 passed in 0.07s` |
| M7 | `github_forge.py`: name `--delete-branch` on withdraw | `2 failed, 41 passed in 0.12s` |
| M8 | `gh.py`: "restore" the merge-strategy flag behind the seam | `1 failed, 30 passed in 1.01s` |
| M9 | `fake_forge.py`: raise instead of degrading with no log | `1 failed, 6 passed in 0.07s` |
| M10 | `classify.py`: put the `DIRTY` row back in the docstring | `1 failed, 6 passed in 0.07s` |

## The one that came back green, and why

**M3's first run reported `no tests ran in 0.22s`** — not a surviving mutation
but a battery defect: it named a test node id that does not exist, so pytest
failed collection and ran nothing. A green-looking line from a run that
collected zero tests is the shape trap 4 warns about, and the battery itself can
wear it. Re-run against the real id
(`test_conflict_routes_one_bounded_cycle_to_the_debugger_persona`) it is red,
and it is the sharpest mutation here: dropping the legacy reading leaves a
pre-049 history classifying as "keep polling" instead of `CONFLICT` — a replay
divergence in production, not a test failure. Every mutation ran on a committed
tree, so nothing untracked could survive a restore into a later run.
