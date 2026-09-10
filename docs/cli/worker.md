# `ergane worker`

> supervise the worker and the operator bridge with systemd

Generate systemd **user** units for the worker and the notify bridge, inside a
memory- and task-bounded slice that takes their whole process tree down with
them, plus a probe timer that reports degradation out of band and reaps orphaned
test servers.

```
ergane worker install   [--env-command COMMAND]
ergane worker uninstall
ergane worker deploy    [<revision>]
ergane worker migrate
```

---

## `ergane worker install`

| flag | meaning |
| --- | --- |
| `--env-command` | a command emitting `export NAME=value` lines, evaluated at unit start |

**Use `--env-command` to keep credentials out of the unit files.** The command
runs at unit start and its output becomes the unit's environment, so nothing
secret is written into a file systemd will happily print.

Uninstall removes exactly what install wrote.

The slice matters more than it looks: bounding memory and tasks, and taking the
whole process tree down together, is what stops a runaway agent or an orphaned
test server from taking the host with it.

---

## `ergane worker uninstall`

Remove exactly what `install` wrote. Nothing else.

---

## `ergane worker deploy [<revision>]`

Freeze a commit into a checkout of its own outside this one, give it its own
environment, start it as a **versioned** worker unit beside whatever is running,
and make it current.

| argument | default | meaning |
| --- | --- | --- |
| `<revision>` | `HEAD` | the commit to deploy — sha, tag or branch |

**Nothing is restarted, so in-flight work stays pinned to its original version.**
An in-place restart interrupts accepted activities and invokes their recovery
behavior. Versioned deployment avoids that interruption by starting the new
version separately.

**Without an explicit revision, a dirty source tree is refused.** Naming a
revision deploys that committed snapshot, not local uncommitted changes. Preserve
unrelated work; do not clean a checkout merely to make deployment succeed.
This native deployment path requires a Git checkout; an installed wheel alone
has no commit to freeze. Use an operator checkout or the container engine.

### Why the worker version matters

The worker imports factory code **live** from its checkout. A fix that has
landed on the branch is not a running fix until the worker is on a revision that
contains it. That has cost a full day on this repository — a landed fix sat
unproven because the worker was twenty commits stale — so after landing anything
that changes worker behaviour, deploy before concluding it works.

---

## `ergane worker migrate`

Remove `ergane-worker.service`, the in-place-restart worker unit that `install`
wrote before versioned deploys existed.

**Refused while any epic that predates versioning is still open.** Stopping that
unit takes the agents it is running with it, and whatever survives is adopted
onto whichever version is current at its next work item.

---

## Operating the units

They are `systemctl --user` units. Use the versioned unit name printed by the
deployment report, replacing `BUILD_ID` below with that exact identifier:

```bash
systemctl --user status ergane-worker@BUILD_ID.service --no-pager
journalctl --user -u ergane-worker@BUILD_ID.service -n 50 --no-pager
```

**Never start a worker with `nohup` or a bare background process.** The slice is
what bounds it, and a hand-started worker is outside it — which is how an
orphaned process tree survives the thing that was supposed to own it.

Do not use the retired `ergane-worker.service` as the name of a versioned
worker. Deploy through the supported command; do not restart a pinned worker
to import a new checkout. A stopped worker can leave its activities waiting
for that version until the applicable recovery bounds expire.

Before retiring an old version, check all workflows pinned to it, not only the
one epic you were watching. Preserve its verification records, usage ledger and
attempt evidence before cleanup. A deployment is successful only when its
report and serving revision agree; a merged commit alone does not prove this.

## See also

- [`ergane install`](install.md) — the control plane the worker dials
- [`ergane engine`](engine.md) — the container tier, an alternative to these units
- [`ergane uninstall`](uninstall.md) — remove everything, in the order that is safe
