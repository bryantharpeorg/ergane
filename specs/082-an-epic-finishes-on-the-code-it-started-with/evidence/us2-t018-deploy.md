# US2 T018 — a deploy puts B on the floor without touching A

2026-08-22, session dev server 1.31.2, namespace `ergane-082-us2-evidence` (never
`factory`), source a `/tmp` clone so `git worktree add` wrote nowhere near the
operator's repository. A=`e423f13`, B=`23851fa`. **One substitution**: this
sandbox has no systemd user bus, so `systemctl --user enable --now` was replaced
by spawning exactly what the generated template's `ExecStart` says with exactly
its `Environment=`; the rest is `deploy()` itself. Minimal lines (D-050).

Deploy A, start an epic, then deploy B **with that epic in flight**:

```
[ran] git worktree add --detach …/deployments/e423f13/tree e423f133c98a…
[ran] uv sync --frozen  (in …/deployments/e423f13/tree)
[systemd] started ergane-worker@e423f13.service pid=26061
[systemd]   Environment=ERGANE_WORKER_BUILD_ID=e423f13
deployed e423f13: now current
[epic on A] behavior=PINNED pinned_version=ergane-worker.e423f13
--- deploy B ---
[systemd] started ergane-worker@23851fa.service pid=26140
deployed 23851fa: now current
[worker A]  pid=26061 alive=True unchanged=True
[epic on A] behavior=PINNED pinned_version=ergane-worker.e423f13
```

**US2-S1**: A's process is the same pid and still alive after B became current,
and the epic started on A is still pinned to A. No stop, restart, kill or
`temporal activity fail` — the transcript above is every command the deploy
issued (SC-005). US1's T001 measured the routing half on this same server.

**US2-S2**, **US2-S3** and **FR-010**:

```
[053 query] worker_revision='23851fa'   ← the next epic reports the deployed id
deployed 23851fa: already current       ← second deploy; nothing duplicated
[systemd] ergane-worker@23851fa.service already running pid=26140 — none started
versions of this deployment:  23851fa current   e423f13 draining
```

That `worker_revision` is why this story also fixes 053's interceptor (see
`factory/worker.py`): it had never fired, so the same line read `None` before.

**Not executed here**: a real `systemctl` deploy, and an epic *completing*
across one — no user bus, and an epic with a synthetic target closes at the
onboarding gate in a second. Both belong to the operator's first live deploy.
