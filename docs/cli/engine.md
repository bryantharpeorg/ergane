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

The intended sequence is to stop the engine, select the CLI-matched image,
verify it and retain a rollback image. **The current image lifecycle is not
qualified for operational use:** isolated checks reproduced cleanup selecting
unrelated images, the requested version not reaching Compose, and the previous
identity being read only after replacement. Do not run this command on the
strength of the sequence below; see [the container warning](../container.md#upgrading-the-engine).

| flag | meaning |
| --- | --- |
| `--force` | proceed even when an epic is in flight |

Four things in the intended design, not a claim of completed qualification:

1. **Stop** the running engine container.
2. **Start** the image pinned to this CLI's version — the CLI and the engine
   image are versioned together, so an upgrade is a single decision rather than
   two that can disagree.
3. **Verify through it** — the `install --verify` battery runs against the new
   engine, so a broken image is discovered by the upgrade rather than by the next
   epic.
4. **Reap** local images older than the previous version. The previous one is
   kept, deliberately, so a rollback has something to roll back to.

## `--force`

**Refused while any epic is in flight** without it, because stopping the engine
mid-epic strands the attempts running inside it.

`--force` accepts interruption of in-flight work; it does not repair the image
lifecycle issues. Pausing dispatch also does not mean that accepted work has
finished. Inspect the actual open/pinned work and preserve its evidence before
any authorized stop; never use this flag as a routine upgrade step.

## See also

- [`ergane install`](install.md) — chooses the tier, and `--verify` is what upgrade runs
- [`ergane worker`](worker.md) — the systemd tier
- [`ergane uninstall`](uninstall.md) — stops the engine container as one of its ordered steps
- [Container guide](../container.md) — mounts, credentials and qualification limits
