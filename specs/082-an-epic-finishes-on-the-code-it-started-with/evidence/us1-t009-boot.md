# US1 T009 — the same worker booted both ways against a real dev server

Run 2026-08-22 at revision `8ac9a35` against a dev server started for the run
(Temporal CLI 1.8.2, Server 1.31.2 — the banner is in the transcript). A fresh
server rather than the operator's `factory` namespace on purpose: registering
`ergane-worker` there would put a version on the live floor that this story has
no business creating, and US2 is the verb that does that deliberately.

The `temporal` CLI is not on this host's PATH, so the two commands below were
issued as the RPCs the CLI wraps — `ListWorkerDeployments` and
`DescribeWorkerDeployment` — and printed in the CLI's shape. The `$` lines name
the command the output corresponds to; they were not typed at a shell.

Both boots run the *production* registration (`factory.worker.build_worker`),
in a subprocess that had the environment before it imported anything — which is
how the unit US2 generates will start it.

```
Temporal CLI 1.8.2 (Server 1.31.2, UI 2.50.1)
Temporal Server:      localhost:33059

$ temporal worker deployment list   # fresh dev server
  deployments: (empty table)

=== control: no ERGANE_WORKER_BUILD_ID in the environment ===
$ ERGANE_WORKER_BUILD_ID=None uv run python -m factory.worker
  worker revision (053 capture): 8ac9a35
  deployment_config: None
  worker stopped

$ temporal worker deployment list   # after the control boot
  deployments: (empty table)

=== engaged: ERGANE_WORKER_BUILD_ID set to the frozen revision ===
$ ERGANE_WORKER_BUILD_ID='8ac9a35' uv run python -m factory.worker
  worker revision (053 capture): 8ac9a35
  deployment_config:
    deployment name       ergane-worker
    build id              8ac9a35
    use worker versioning True
  worker stopped

$ temporal worker deployment list   # after the versioned boot
  deployments: ['ergane-worker']

$ temporal worker deployment describe --deployment-name ergane-worker
  Name             ergane-worker
  CurrentVersion   __unversioned__
  Version          ergane-worker.8ac9a35
```

Three things this shows, in the order they matter.

**US1-S2, the control.** The worker booted without the variable resolved no
`deployment_config` and left the deployment table empty. It polled the same
queue with the same activities and the same 006/053 configuration it has been
polling with; nothing about it is new, which is the point of landing this dark.

**US1-S1.** The worker booted with the variable registered deployment
`ergane-worker` with build id `8ac9a35` — the value `_worker_revision()` already
captured for 053's revision query, not a second identity invented for
versioning. `describe` shows the version.

**`CurrentVersion __unversioned__`, and why that is correct here.** Registering
a version does not make it current, and this story deliberately does not make it
current. That separation is trap 1: a versioned worker serves only its own
version's tasks, so a floor whose only worker went versioned while no current
version existed would stall every new epic. `set-current-version` is US2's verb,
after `deploy` has polled `describe-version` and seen the worker register
(trap 7). Until then the deployment exists, `__unversioned__` is current, and
today's worker keeps serving everything — exactly the state this transcript
captures.
