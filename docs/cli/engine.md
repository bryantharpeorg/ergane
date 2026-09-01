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

Drain the running engine, start the image that matches this CLI version, run the
`install --verify` battery **through it**, and remove local images older than the
previous version.

| flag | meaning |
| --- | --- |
| `--force` | proceed even when an epic is in flight |

Four things in order, and the order is the design:

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

`--force` is for when you have decided that stranding them is the lesser cost —
after a `build pause` and a look at [`ergane status`](status.md), not as the
first thing to try when the refusal appears.

## See also

- [`ergane install`](install.md) — chooses the tier, and `--verify` is what upgrade runs
- [`ergane worker`](worker.md) — the systemd tier
- [`ergane uninstall`](uninstall.md) — stops the engine container as one of its ordered steps
- `docs/container.md` — what the container tier is and why it exists
