# `ergane engine`

> manage the engine container

Commands for the container-tier engine — the alternative to the systemd units
[`ergane worker`](worker.md) installs. Which tier a host runs is chosen at
[`ergane install`](install.md) time via `--engine`.

```
ergane engine upgrade [--force]
```

---

## `ergane engine upgrade`

The intended sequence is to retarget the generated project's owned image and
version declarations to the CLI-matched published image, stop the engine, start
that image with the version in the Compose child's environment, verify it and
retain a rollback image. **The image lifecycle is still not qualified for
operational use:** the retargeting, the version forwarding at the Compose
subprocess boundary, the pre-stop identity ordering and the cleanup policy are
covered by committed captured-runner regressions, and those captures are
synthetic — no Docker daemon ran. A real drained-image upgrade and rollback is
still required before release; see [the container
warning](../container.md#upgrading-the-engine).

| flag | meaning |
| --- | --- |
| `--force` | proceed even when an epic is in flight |

Five things in the intended design, not a claim of completed qualification:

1. **Validate and retarget** the generated project before anything stops: the
   owned service image and `ERGANE_VERSION` declaration move to the
   CLI-matched published image and are persisted with the ownership manifest in
   one transaction. Changed, unclaimed, missing or unsupported artifacts are
   refused by path, and every other byte — the operator's mounts, user, ports
   and confinement — is preserved. `--force` does not adopt operator edits.
2. **Stop** the running engine container.
3. **Start** the image pinned to this CLI's version — the CLI and the engine
   image are versioned together, so an upgrade is a single decision rather than
   two that can disagree — and the Compose child receives that version in its
   actual subprocess environment.
4. **Verify through it** — the `install --verify` battery runs against the new
   engine, so a broken image is discovered by the upgrade rather than by the next
   epic.
5. **Reap** local images older than the previous version. The previous one is
   kept, deliberately, so a rollback has something to roll back to.

## `--force`

**Refused while any epic is in flight** without it, because stopping the engine
mid-epic strands the attempts running inside it.

`--force` accepts interruption of in-flight work; it does not repair the image
lifecycle issues, and it does not bypass project ownership: changed, unclaimed,
missing or unsupported artifacts refuse with or without it. Pausing dispatch
also does not mean that accepted work has finished. Inspect the actual
open/pinned work and preserve its evidence before any authorized stop; never
use this flag as a routine upgrade step.

## See also

- [`ergane install`](install.md) — chooses the tier, and `--verify` is what upgrade runs
- [`ergane worker`](worker.md) — the systemd tier
- [`ergane uninstall`](uninstall.md) — stops the engine container as one of its ordered steps
- [Container guide](../container.md) — mounts, credentials and qualification limits
