# Implementation Plan: a worker restart does not orphan the work in flight

**Spec**: `specs/099-a-worker-restart-does-not-orphan-the-work-in-flight/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-23 by printing that exact line
individually** (`sed -n '<n>p' <file>`). Check each one anyway.

**The boot path — `factory/worker.py`:**

- `:325` — `async def main() -> None:` — *"Connect, register, and poll
  `workgraph` until interrupted."* `resolve_temporal_target()` →
  `Client.connect(address, namespace=namespace)` → `await build_worker(client).run()`.
  **This is the sequence the sweep and the skew check insert into**, between the
  connect and the `run()`.
- `:260` — `def build_worker(client: Client) -> Worker:` — whose docstring
  records the precedent this spec copies: *"Which is also why 082's refusals are
  raised from here: a worker that has been told to register a build id it cannot
  establish must fail where an operator reads the failure, in the unit's journal
  at boot, rather than by polling a version no epic routes to."* A boot sweep
  that finds something wrong belongs in that same place: the journal, at boot,
  before the first task.
- `:229-231` — `_WORKER_REVISION = _worker_revision()`, captured once at import;
  `:212` — `def _worker_revision() -> str | None:` — `git rev-parse --short HEAD`
  via subprocess, `None` when the tree is not a git checkout. **US2's skew check
  compares this against the checkout's current HEAD** — the same command, run
  again, at boot.
- `:235` — `def _deployment_registration() -> dict[str, WorkerDeploymentConfig]:`
  — 082-US1's half; empty dict when versioning is disengaged. The skew check
  must not disturb it.
- `:291` — `class _WorkerRevisionInterceptor(Interceptor):` — carries
  `_WORKER_REVISION` into every `EpicWorkflow` input; the query answer that
  `ergane build status` reads.
- `:349-352` — the `__main__` block: `configure_logging(level=logging.INFO)`
  then `asyncio.run(main())`. The journal an operator pastes is this process's.

**The orphan mechanism — `factory/workgraph/workflow.py`:**

- `:2166-2185` — the `workflow.start_activity(run_agent_attempt, context, ...)`
  call inside `_attempt` (`:2133`): `activity_id=context.node_id`,
  `start_to_close_timeout=timedelta(seconds=context.timeout_s + _ADAPTER_GRACE_S)`,
  `heartbeat_timeout=_agent_heartbeat_timeout(context.timeout_s)`,
  `retry_policy=_AGENT_RETRIES`. **The activity the restart orphans is this one.**
- `:346-349` — `_AGENT_RETRIES = RetryPolicy(initial_interval=timedelta(seconds=5),
  maximum_attempts=2)`. An external fail of the activity is terminal, not a
  retry consumption — the measured clear proved it (spec Assumptions).
- `:447-448` — `_AGENT_HEARTBEAT_TIMEOUT_FLOOR = timedelta(seconds=5 *
  HEARTBEAT_INTERVAL_S)` and `_AGENT_HEARTBEAT_TIMEOUT_CEILING =
  timedelta(seconds=120)`; `:451` — `def _agent_heartbeat_timeout(timeout_s:
  float) -> timedelta:` — `max(min(timeout_s / 2, ceiling), floor)`. The ceiling
  is 082's; the measured 2-hour stall predates it. **This spec does not touch
  these values** — it makes the orphan not depend on them at all.
- `:1014` — `await workflow.wait_condition(lambda: any(task.done() for task in
  in_flight.values()) or self._kill_requested or self._paused)` — **the
  scheduler park.** It re-evaluates on every activation, so the moment a dead
  node's task completes, the ready nodes dispatch. The stall is not the park;
  the stall is that the dead node's task never completes until the heartbeat
  times out.
- `:1467` — `async def _reap_finished(` — `task.result()` per finished task;
  `except Exception` → KILLED; `CancelledError` passes through. **Where a
  failed-attempt task gets reaped and the node's lock-out applied.**
- `:2216` — `def _attempt_timeout(self, record, exc) -> AdapterResult:` — turns a
  heartbeat `TimeoutError` into `AdapterResult(termination=Termination.TIMEOUT,
  last_snapshot=snapshot)`; *"A heartbeat-timeout attempt is verified like any
  other (FR-012)."* **A boot-time fail flows through this same ladder** — the
  attempt is verified, the node re-enters the ladder, and nothing new is
  invented for the terminal path.
- `:1415` — `async def _drain_in_flight(`; `:2745` — `async def _close_out(`
  (salvage → sweep, in that order, on every path); `:2798` — `async def _land(`;
  `:2893-2894` — `record.state = NodeState.ENQUEUED` then
  `self._landing_tasks[node.id] = asyncio.ensure_future(self._ride_landing(graph,
  record, config))`; `:2895` — `async def _ride_landing(`; `:2956` — `async def
  _poll_landing(` — the queue's own beat; `:3046` — `async def
  _remove_worktree(`.
- `:1291` — `_ready_set`; `:1325` — `_edges_satisfied` (`depends_on` →
  `verified`; `depends_on_merged` → `state == NodeState.MERGED`).

**The activity itself — `factory/activities/agent_activities.py`:**

- `:157` — `HEARTBEAT_INTERVAL_S = DEFAULT_HEARTBEAT_INTERVAL_S` (= 1.0, from
  `factory/workgraph/adapter.py:116`).
- `:443` — `async def run_agent_attempt(context: AttemptContext) ->
  AdapterResult:` — beats roughly every `HEARTBEAT_INTERVAL_S`; on cancellation
  re-raises `CancelledError` carrying `AdapterResult(termination=Termination.KILLED,
  ...)`. **When the worker dies, this coroutine dies with it; the activity
  record on the server does not.**

**The stale-worker mechanism — `factory/versioning.py`:**

- `:53` — `DEPLOYMENT_NAME = "ergane-worker"`; `:58` —
  `WORKER_BUILD_ID_ENV = "ERGANE_WORKER_BUILD_ID"`; `:73` — `ENGAGED_BUILD_ID`
  frozen at import.
- `:94` — `def resolve_deployment_version(*, revision: str | None, requested:
  str | None) -> WorkerDeploymentVersion | None:` — raises `VersioningRefused`
  when `revision` is `None` or `revision != requested`. **The build id is the
  checkout's revision, never the environment's opinion.** US2's skew check is
  the same comparison without the environment gate: boot commit vs checkout
  HEAD, at boot, on every boot.

**The deleted-CLI mechanism — the supervised boot:**

- `~/.config/systemd/user/ergane-worker.service` — `KillMode=control-group`
  (the comment above it: *"KillMode=control-group is the point, not a default
  worth losing: agents, gate …"*), `Restart=on-failure`, `RestartSec=10`.
- `/home/admin/code/homelab/infra/ergane-supervision/ergane-worker-run.sh` —
  `:19` the comment *"Sync first, then exec the interpreter directly rather
  than staying under …"*; `:32` — `uv sync --locked --quiet`; `:33` —
  `exec "$ERGANE/.venv/bin/python3" -m factory.worker`. **The `python3 -m`
  spelling is deliberate** (032's agent `pkill` matched the substring
  `python -`); the `uv sync --locked` at `:32` is the line that deleted the
  `ergane` console script and reports "would make no changes" ever since.
- `pyproject.toml:36` — `ergane = "factory.cli.main:main"` — the console script
  entry point. **US3's repair re-writes the script from this entry point when
  the metadata lists it but the bin directory does not.**
- `factory/supervision/deploy.py:486` — `def _sync(tree: Path, run: Runner) ->
  None:` — `run(("uv", "sync", "--frozen"), cwd=tree)`; `:500` — `def _start(unit:
  str, run: Runner) -> None:` — `systemctl --user enable --now`. The deploy
  path's sync is the same class of operation as the run script's; US3's repair
  belongs on the boot path, not here.

## Traps

**1. `temporal activity reset` is not a workaround, and the sweep must not be
one either.** It only takes effect on the next heartbeat, fail, or timeout —
and a dead worker never heartbeats again. The measured clear was
`temporal activity fail`, and the external fail proved terminal rather than
consuming the retry attempt (`_AGENT_RETRIES` at
`factory/workgraph/workflow.py:346-349` has `maximum_attempts=2`; a fail that
consumed the attempt would leave the node with one attempt left and the ladder
half-eaten). The sweep fails the activity the way the operator did: terminal,
no retry consumption. US1-S1 asserts the failure path fires on worker boot,
not on heartbeat expiry — a sweep that *resets* instead of *fails* passes a
naive "activity is no longer PENDING" test and fails US1-S1.

**2. The sweep must be a no-op on a healthy worker, and the no-op must be
observable.** US1-S3 is the control: a boot with no in-flight activities
changes nothing. A sweep that touches the server on every boot — even to read
— is a new defect class wearing this spec's hat. The empty case is a
first-class case, not an afterthought, and the test for it is committed.

**3. The skew check must be silent when boot commit equals HEAD.** A warning
that fires permanently is the defect class
`operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install`
names, and this spec must not manufacture it. US2-S2 is the control: boot
commit == checkout HEAD → no skew reported, nothing changed. The check runs on
every boot; its healthy output is silence.

**4. Do not restart on every landing.** US2-S3: a landing that touches no
factory code (spec markdown only) takes no action. Restarting on every landing
is not the rule; restarting on a landing that can change the worker's imported
modules is. The check is "did the landing touch a module the sandbox imports,"
not "did a landing happen."

**5. The sweep and the skew check are one sequence, and US2 lands on US1's
base.** Both reach for the worker's boot path (`factory/worker.py:325`), so
the Work Graph declares `US2.depends_on_merged: [US1]`. US2's check must not
restart the worker into US1's half-finished sweep: the sequence is sweep
first, then skew check, then `run()`. An attempt that reorders them, or that
lets the skew check's restart skip the sweep, lands a worker that orphans its
own in-flight work on the very restart that was supposed to fix it.

**6. The repair must not fight `uv sync`.** `uv sync --locked` reconciles
against `uv.lock`, not the filesystem, so it reports "would make no changes"
while the script stays gone. US3's repair runs *after* the sync, re-writes the
script from the entry point in `pyproject.toml:36` when the metadata lists it
but the bin directory does not, and is itself a no-op when the script is
present. US3-S2 is the control: healthy venv, script present before and after,
sync a no-op for it. A repair that re-writes the script on every boot is a
new defect class (a bin directory that churns on every restart).

**7. A non-writable venv fails loudly, naming the path.** US3-S3: the boot
path cannot silently leave the CLI deleted — that is exactly how this defect
shipped (the sync succeeded, the script stayed gone, nothing said so). The
failure names the path and exits non-zero; the unit's journal is where an
operator reads it, the same place 082's refusals raise
(`factory/worker.py:260` docstring).

**8. Tests reach the server through the seam, never a real client.** One
Temporal serves this host and it holds the live floor. The sweep's test drives
the boot path against a fake client that reports one started activity with no
live process; the skew check's test drives it against a fake checkout whose
HEAD is one commit ahead. Never connect. The precedent is 085's trap 5
(`factory/roadmap/schedule.py:247` exists because removing its sentinel check
*created five schedules on the operator's live namespace*).

**9. Do not touch the heartbeat timeout values.** `_AGENT_HEARTBEAT_TIMEOUT_FLOOR`
and `_AGENT_HEARTBEAT_TIMEOUT_CEILING` at `factory/workgraph/workflow.py:447-448`
are 082's, and the spec's "What this spec does not change" says so plainly.
This spec makes the orphan not depend on the timeout; it does not shorten it.
An attempt that "fixes" the stall by lowering the ceiling is fixing a different
defect and breaking 082's measured bound.

**10. One test file per story, named for the story's property.** The suite's
convention is one file per story, named for what the story proves, not for the
module it tests. US1's file is about the sweep; US2's about the skew check;
US3's about the repair. A single `test_worker_boot.py` holding all three is
the predictable second attempt here, because it makes the no-op controls
(US1-S3, US2-S2, US3-S2) look like one test instead of three.

## Sizing

**US1 is the largest of the three, and it is the one the plan must settle
before dispatch.** The Assumptions block names the open question: can the
worker enumerate the activities it owns at boot, or is the mechanism a
post-landing check on the epic's pending activities? The probe is a single
`.venv/bin/python -c` against the installed `temporalio` — does the client
expose the task queue's pending activities, and can a worker-side fail reach
them? The answer decides whether the sweep lives in `factory/worker.py`'s boot
path or in the epic's landing path. Either way the terminal path is the
existing ladder (`_attempt_timeout` at `factory/workgraph/workflow.py:2216`,
`_reap_finished` at `:1467`), and the scheduler unblock is the existing park
(`:1014`) re-evaluating. The work is the sweep itself, the no-op control, and
the test that drives it through the seam.

**US2 is small but exacting.** One comparison (boot commit vs checkout HEAD,
the same command `_worker_revision()` already runs), one decision (restart or
report), and the three controls: stale → restart or report; healthy → silent;
spec-only landing → no action. The trap is trap 4 — a check that restarts on
every landing — and trap 3, the permanent warning. The restart mechanism is
082's deploy path (`factory/supervision/deploy.py:500`), not a new one.

**US3 is small.** One repair (re-write the console script from
`pyproject.toml:36` when the metadata lists it but the bin directory does
not), one no-op control, and the loud-failure case. The trap is trap 6 — a
repair that fights `uv sync` by re-writing on every boot — and trap 7, the
silent no-op on a non-writable venv. The entry point is readable from the
package metadata on this host; the plan's Assumptions block says the probe
must verify that before US3 dispatches.

## Verification the operator will run, independent of the gate

- **Restart the live worker with an attempt in flight and time the activity's
  terminal state.** That is the measured 2-hour scenario and the only thing
  that proves US1. The interval from boot to failure should be seconds, not
  the heartbeat timeout, and the epic's remaining nodes should dispatch
  without an operator running `temporal activity fail`.
- **Restart the live worker with no in-flight activities and diff the journal
  against a healthy boot.** The sweep's no-op control, on the real host. A
  journal that names the sweep on every boot is trap 2.
- **Land a factory-code change and watch the next workflow activation.** The
  skew check's real case: the worker either restarts or reports the skew
  before the task runs, and the task does not die on an `ImportError` retry
  loop. Then land a spec-markdown-only change and confirm the check takes no
  action (US2-S3).
- **Delete the `ergane` console script from the venv's bin directory, restart
  the worker, and run `command -v ergane`.** The repair's real case. Then
  restart a second time and confirm the script is still there and the sync is
  a no-op for it (US3-S2).
- **Point the boot path at a read-only venv and read the journal.** The
  loud-failure case: the named path, the non-zero exit, and the unit's journal
  saying so plainly (US3-S3, trap 7).
- **Grep the diff for the heartbeat timeout values and confirm they are
  untouched.** `_AGENT_HEARTBEAT_TIMEOUT_FLOOR` and
  `_AGENT_HEARTBEAT_TIMEOUT_CEILING` at `factory/workgraph/workflow.py:447-448`
  are 082's. A diff that moves them is fixing a different defect (trap 9).
