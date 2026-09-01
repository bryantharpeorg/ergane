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

**Nothing is restarted, so every attempt in flight finishes on the version it
started with.** That is the whole reason this verb exists. An in-place restart
of a worker mid-attempt loses the attempt; deploy sidesteps the question by
never touching the running one.

**Refused while the tree is dirty.** A deploy ships commits, so there has to be
a commit to ship.

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

They are `systemctl --user` units. Start, stop and inspect them that way:

```bash
systemctl --user status ergane-worker --no-pager
systemctl --user restart ergane-worker.service
```

**Never start a worker with `nohup` or a bare background process.** The slice is
what bounds it, and a hand-started worker is outside it — which is how an
orphaned process tree survives the thing that was supposed to own it.

**Restart between attempts, never during one.** A restart mid-attempt leaves the
activity pending behind its heartbeat, and the epic wedges.

## See also

- [`ergane install`](install.md) — the control plane the worker dials
- [`ergane engine`](engine.md) — the container tier, an alternative to these units
- [`ergane uninstall`](uninstall.md) — remove everything, in the order that is safe
