# 049-US1 evidence

    $ uv run pytest -q
    2809 passed, 44 skipped, 5 warnings in 291.78s (0:04:51)

One production edit at a time, applied to a green *committed* HEAD, run over
`tests/test_forge_seam.py tests/test_merge_activities.py` (37 tests), reverted
with `git checkout HEAD --`. Each edit is the one its test's docstring names.

| edit | tests red |
|---|---|
| M1 `LandingPolicy` gains `merge_queue_enabled` | 1 · forge-native spelling |
| M2 `resolve_forge` defaults, never raises | 1 · unregistered name |
| M3 `evaluate_repo` drops `forge_findings` | 1 · forge's own findings |
| M4 `queue_enabled=True`, forge ignored | 2 · judged model, queue-missing |
| M5 forge stops reporting the title setting | 3 · squash-title findings |
| M6 `workgraph/cli.py` builds a `GhClient` | 1 · only-the-forge-constructs |
| M7 `cli/init.py` builds a `GhClient` | 1 · only-the-forge-constructs |
| M8 `merge_activities.py` builds a `GhClient` | 1 · only-the-forge-constructs |
| M9 forge grows `classify_landing` | 2 · decides, operation set |
| M10 `_load_builtins` returns early | 3 · registry imports the forge |
| M11 `GhError` escapes the seam | 1 · read failure is a failed profile |
| M12 `pyproject.toml` gains a dependency | 1 · no new dependency |

M10 first ran **all 37 green**. `tests/test_forge_seam.py` imported `GithubForge`
by name, so `github` stayed registered whatever the import loop did, and nothing
else in the suite resolved a forge for real — production would have resolved
none. `test_the_registry_imports_the_shipped_forge_itself` was written after that
mutation found the hole, the module's direct import was removed, and the whole
battery re-run: the numbers above are that second run.
