# US2 T018 — a deploy puts B on the floor, and A's epic finishes on A

2026-08-22, dev server 1.31.2, namespace `ergane-082-us2-t018b`, source a
`/tmp` clone — nothing touched `factory` or the operator's checkout.
A=`e423f13`, B=`b683288`. **Two substitutions**: no systemd user bus here, so
`systemctl --user enable --now` spawned exactly what the template's `ExecStart`
says with exactly its `Environment=`; and each instance served `ScriptedWorld`'s
activities, so an epic reaches COMPLETED without a proxy or an agent. All else
is the deployment's own code — `deploy()`, the workflows, the versioning
registration, the 053 interceptor. D-050: minimal lines; the
`status behavior version` triples drop the describe enums' prefixes.

## US2-S1 — the epic in flight finishes on A, with B current

```
deployed e423f13: now current
[epic on A] RUNNING    PINNED  ergane-worker.e423f13
--- deploy B, with that epic in flight ---
[systemd] started ergane-worker@b683288.service pid=885
[systemd]   Environment=ERGANE_WORKER_BUILD_ID=b683288
deployed b683288: now current
[worker A] pid=814 alive=True unchanged=True
[epic on A] result epic_state=COMPLETED nodes={'us1': 'MERGED', 'us2': 'MERGED',
  'us3': 'MERGED'} (waited 36s past the deploy)
[epic on A] COMPLETED  PINNED  ergane-worker.e423f13
[epic on A] history events matching CANCEL/FAILED/TERMINATED/TIMED_OUT: none
```

The activity running when B landed is the proof, from the server's own records:

```
run_agent_attempt STARTED   21:31:46.656  identity=814@spark-9cb5  ← worker A
b683288 current_since       21:32:00.279
run_agent_attempt COMPLETED 21:32:31.718  ← 31s after B became current, on A
activity identities across the whole epic: {'814@spark-9cb5': 49}
event types: ACTIVITY_TASK_SCHEDULED/STARTED/COMPLETED x49 each
```

pid 814 is A. Every activity of the epic ran in A's process and every one
completed — no cancellation, no KILLED, no `temporal activity fail` (SC-001,
SC-005).

## US2-S2, US2-S3 and FR-010

```
[053 query] worker_revision='b683288'   ← the next epic reports the deployed id
[epic on B] COMPLETED  PINNED  ergane-worker.b683288
deployed b683288: already current       ← second deploy; nothing duplicated
[systemd] ergane-worker@b683288.service already running pid=885 — none started
versions of this deployment:  b683288 current   e423f13 draining
```
