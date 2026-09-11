# US1 pre-stop identity

All Docker calls are synthetic captures; only temporary files and real identity functions are used.

## T001 red

```text
FAILED tests/test_engine_upgrade.py::test_upgrade_reads_old_identity_before_stop
    At index 0 diff: 'stop' != 'read_identity'
```

The pre-repair order observed `stop`, `start`, then the identity read, so the replacement identity became the rollback candidate and the older exact-repository release was removed.

## T001 green

```text
uv run pytest -q tests/test_engine_upgrade.py
18 passed in 0.10s
```

Captured lifecycle:

```text
read_identity
docker compose down
docker compose up -d --no-build
verify
docker images --format {{.Repository}}:{{.Tag}}
docker rmi ghcr.io/bryantharpeorg/ergane:0.2.0
```

Retention kept the target and the pre-stop `0.3.0` image and removed only the older exact-repository `0.2.0` release.
