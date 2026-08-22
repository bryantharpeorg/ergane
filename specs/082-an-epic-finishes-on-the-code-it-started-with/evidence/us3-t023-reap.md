# US3 T023 — a drained version leaves the host

2026-08-22, dev server 1.31.2, namespace `ergane-082-us3`, source a `/tmp` clone
— nothing touched the `factory` namespace or the operator's checkout.
A=`a34ce04`, B=`ae69847`. **One substitution**: no systemd user bus here, so
`systemctl --user enable --now` spawned exactly what the template's `ExecStart`
says with exactly its `Environment=`, and `disable --now` TERMed that process
group. Everything else is the deployment's own code — `deploy()`, `reapable()`,
`sweep()`, the git removal, the Temporal calls. Sweeps fire on the probe's own
2-minute interval. D-050: minimal lines.

## US3-S1 / SC-003 — drained, then gone: unit, checkout, record

```
22:42:14 [deploy B] deployed ae69847: now current
22:42:15 [floor] a34ce04=draining ae69847=current   [open pinned work on A] 0
22:44:15 [sweep t+120s] reaped nothing: no version has finished draining
22:46:15 [systemd] stopped and disabled ergane-worker@a34ce04.service (pid=22820 exit=-15)
22:46:15 [sweep t+240s] reaped:
  a34ce04  unit and checkout are gone; the server kept the record (version
           'ergane-worker:a34ce04' cannot be deleted since it has active pollers)
22:46:15 [sweep t+240s] A: unit=inactive checkout=gone | floor: a34ce04=drained ae69847=current
22:52:17 [sweep t+601s] reaped:
  a34ce04  unit stopped and disabled, checkout removed, record deleted
22:52:17 [sweep t+601s] A: unit=inactive checkout=gone | floor: ae69847=current
```

The first sweep *after* the server called A drained took the unit and the
checkout. The record waited on a clock this factory does not own: Temporal
refuses to delete a version whose pollers it can still see, and they age out
~5 minutes after the worker stops. Hence no retry loop — each sweep is
idempotent and the one after the pollers converges, which is what t+601s is.
The two server clocks between "last pinned epic closes" and "version gone" are
the drainage refresh (~3 min, `a34ce04=draining` → `drained` between t+120s and
t+240s) and that poller TTL.

## Plan trap 3 — the checkout went through git, and git knows it

```
22:54:17 [final] worktrees registered in the clone:
/tmp/us3live/src                                        ae69847 [factory/082-...-with/us3]
/tmp/us3live/state/supervision/deployments/ae69847/tree ae69847 (detached HEAD)
```

A's registration is gone from the clone's `.git`, not just its directory. A bare
`rm -rf` would have left that line behind for nobody to clean.

## US3-S2 — the current version, never touched (the live half of the control)

Asserted on every one of the six cycles above, and last at the end:

```
22:54:17 [final] A unit alive=False checkout=False
22:54:17 [final] B (current) unit alive=True checkout=True
22:54:17 [final] describe: ae69847=current
```

## US3-S3 — and the server's own second lock, with real pinned work on it

From the pre-implementation probe (`probe-082-us3`, one open PINNED workflow on
`v1`, `v2` current), which also decided how the query is written:

```
[list] TemporalWorkerDeploymentVersion = "probe-082-us3.v1" ... -> []
[list] TemporalWorkerDeploymentVersion = "probe-082-us3:v1" ... -> ['probe-082-us3-open']
[delete] v1 skip_drainage=False -> ERROR RPCError: version 'probe-082-us3:v1'
         cannot be deleted since it is draining
```

The dotted form is the SDK's own `to_canonical_string()`, and it does not error
— it answers zero for every version, forever, which is the answer that would
have told the sweep to delete a version an epic was running on. And a version
with open pinned work is refused by the server too, even when asked: the reap's
decision and `skip_drainage=False` are two locks on the same door.
