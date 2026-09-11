# US1 retention: red to green

All image references and subprocess calls below are synthetic captures; no daemon was contacted.

## Red — T001 before the repair (`5469b5c`)

```text
FAILED tests/test_engine_upgrade.py::test_retention_removes_only_exact_repository_older_releases
    assert (
        'ghcr.io/bryantharpeorg/ergane:0.1.0',
        'ghcr.io/bryantharpeorg/ergane:0.2.0',
        'example.com/operator/another-service:0.1.0',
        'ghcr.io/bryantharpeorg/ergane-operator/another-service:0.1.0',
    ) == (
        'ghcr.io/bryantharpeorg/ergane:0.1.0',
        'ghcr.io/bryantharpeorg/ergane:0.2.0',
    )
E  Left contains 2 more items
1 failed in 0.21s
```

## Green and captured calls — after `5c50f1e`

```text
uv run pytest -q tests/test_engine_upgrade.py -k "..."
9 passed, 8 deselected in 0.09s

default runner call order:
  docker compose -f <project>/compose.yaml down
  docker compose -f <project>/compose.yaml up -d --no-build
  docker images --format {{.Repository}}:{{.Tag}}
  docker rmi ghcr.io/bryantharpeorg/ergane:0.1.0
  docker rmi ghcr.io/bryantharpeorg/ergane:0.2.0
```

The inventory also contained the target, previous, unrelated, and prefix-lookalike references; the captured removal set is only the two exact-repository older releases. A failed `docker images` command raises before retention, so no `rmi` call occurs.
