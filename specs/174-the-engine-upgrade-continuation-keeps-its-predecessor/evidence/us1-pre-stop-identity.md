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

## T002 unknown states

```text
uv run pytest -q tests/test_engine_upgrade.py::test_upgrade_unknown_pre_stop_identity_removes_nothing
3 passed in 0.11s
```

`absent`, `malformed`, and `image-less` each read once before stop, retained uncertainty after start wrote `0.4.0`, and removed no image.

## T003 snapshot control

The production read is moved above `docker.stop`; `test_upgrade_reads_old_identity_before_stop` records exactly one `read_identity`, before stop/start, and retention keeps the read `0.3.0` image. The T002 matrix proves `None` uncertainty remains `None` when `0.4.0` is written later.

## T004 failure gates

```text
FAILED tests/test_engine_upgrade.py::test_upgrade_degraded_when_engine_finding_mismatches
    assert ('list_images', ()) not in seam.calls
```

Green:

```text
uv run pytest -q tests/test_engine_upgrade.py
23 passed in 0.13s
```

Failed stop and failed start stop at their seam call; a failed engine finding is visible and degraded, but inventory/removal do not run. With a passing engine finding, unrelated failed findings remain in the report and degraded stays false.

## T005 controls and full gate

```text
uv run pytest -q tests/test_engine_upgrade.py -k "exact_repository or unknown_previous or unrecognized_and_ambiguous or orders_numeric or reads_old_identity or unknown_pre_stop or lifecycle_failure or degraded_when or unrelated_probe"
12 passed, 11 deselected in 0.10s
```

```text
uv run pytest -q
6283 passed, 58 skipped in 658.71s
```

The story diff from its dispatch base is below 16 KiB, within the 64 KiB bound. The skipped tiers are environmental and did not contact Docker or a live worker.
