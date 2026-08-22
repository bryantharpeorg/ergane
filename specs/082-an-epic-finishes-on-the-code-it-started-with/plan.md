# Implementation Plan: an epic finishes on the code it started with

**Spec**: `specs/082-an-epic-finishes-on-the-code-it-started-with/spec.md`

## What already exists, and where

**Every line number below was re-verified on 2026-08-22 against the tree at
e5f9ce6** (the v0.2.0 release point) by printing the line or running the probe
named. The original 2026-08-21 pass at 158aa63 had drifted badly — sixteen
commits landed between the two, `EpicWorkflow`'s defn moved 72 lines and the
heartbeat derivation 25 — so check each one anyway before trusting it; this
batch of specs has already produced 36 bad citations once (see 078's
frontmatter).

**Live probes re-run 2026-08-22, all unchanged from draft time**: CLI 1.8.2 /
Server 1.31.2 / UI 2.50.1; `temporal worker deployment list --namespace
factory` answers with an empty table (API live, no flag); temporalio 1.31.0
carries `deployment_config` on `Worker.__init__`, `versioning_behavior` on
`workflow.defn`, and `WorkerDeploymentConfig(version, use_worker_versioning,
default_versioning_behavior)`.

**The worker, and the one queue:**

- `factory/worker.py:1-6` — the module docstring: one process, one queue, the
  only deployment.
- `factory/workgraph/workflow.py:259` — `TASK_QUEUE = "workgraph"`.
- `factory/worker.py:102` — `WORKFLOWS = [EpicWorkflow, RoadmapWorkflow,
  EscalationWorkflow, QuestionWorkflow]`.
- `factory/worker.py:234-254` — `build_worker`: the `Worker(...)`
  construction. `deployment_config=` goes here.
- `factory/worker.py:211-225` — `_worker_revision()`: short sha via
  `git rev-parse --short HEAD`, `None` outside a checkout. **This is the build
  id** — 053 already captures exactly the value versioning needs.
- `factory/worker.py:231` — `_WORKER_REVISION`, captured once at import.
- `factory/worker.py:256-280` — the 053 revision interceptor, **rewritten by
  086 since this plan was drafted**: `execute_workflow` now ends in
  `return await self.next.execute_workflow(input)` with a comment explaining
  that an inbound interceptor sits on the result path and one that awaits
  without returning completes every workflow with None. That `return` is
  load-bearing; any edit near it that drops it re-opens 086. Under versioning
  the interceptor's answer becomes *more* truthful (a pinned epic reporting
  its old sha is correct, not stale).
- `factory/worker.py:13-16` — `tests/test_worker.py` reads the activity
  invocations out of the workflow module's syntax tree. Touching the
  registration list ripples there.

**The workflow definitions that take `versioning_behavior`:**

- `factory/workgraph/workflow.py:634` — `@workflow.defn` on `EpicWorkflow`.
- `factory/roadmap/workflow.py:511` — `@workflow.defn` on `RoadmapWorkflow`.
- `factory/escalation/workflow.py:217` — `@workflow.defn` on
  `EscalationWorkflow`.
- `factory/escalation/question.py:86` — `@workflow.defn` on
  `QuestionWorkflow`.

**The roadmap's run boundaries (FR-002's lever):**

- `factory/roadmap/workflow.py:909`, `:937`, `:959` — the three
  continue-as-new call sites; `:990` — the `workflow.continue_as_new` itself.
  The roadmap's history is short-lived by construction.
- `factory/roadmap/workflow.py:1276` — child epics started with
  `parent_close_policy=ParentClosePolicy.ABANDON`. Children pin
  independently of the parent; the roadmap's own version never holds an
  epic's.

**The SDK and server surface (probed live at draft, re-probe first):**

- temporalio 1.31.0: `Worker.__init__` accepts `deployment_config`;
  `WorkerDeploymentConfig(version: WorkerDeploymentVersion,
  use_worker_versioning: bool, default_versioning_behavior:
  VersioningBehavior)`; `workflow.defn(versioning_behavior=...)`;
  `temporalio.common.{VersioningBehavior, WorkerDeploymentVersion,
  PinnedVersioningOverride, AutoUpgradeVersioningOverride}`.
- Server 1.31.2 dev server, namespace `factory`:
  `temporal worker deployment list` returns an empty table (API enabled, no
  flag needed). Verbs confirmed: `describe`, `describe-version`,
  `set-current-version`, `delete-version`.

**The unit generation (US2/US4's home):**

- `factory/supervision/units.py:57` — `WORKER_UNIT = "ergane-worker.service"`
  (the name being retired); `:81` — `ENABLE_TARGETS`; `:83` — `_MODULES`.
- `:111-152` — `InstallLayout`: `install_root`, `interpreter`, `unit_dir`,
  `generated_dir`, `env_command`, and the `roots` allow-list the path scan
  enforces (SC-006 of 042). **The deployments directory must join `roots` or
  every generated instance fails the scan.**
- `:155-160` — `supervision_home()` → `<state>/ergane/supervision`. Frozen
  checkouts go under here (`deployments/<build-id>/`), outside the operator
  checkout.
- `:165-196` — `resolve_layout`: `install_root` defaults to the directory
  holding `factory/` — the live checkout. A versioned instance's working
  directory must be the *deployment's* checkout instead.
- `:245-270` — `generated_files()`, the list `install()` writes; the template
  unit is one more `GeneratedFile` here, the legacy `WORKER_UNIT` one fewer.
- `:305-310` — the shared unit body: `Slice=`, `WorkingDirectory=
  {layout.install_root}` (`:308-309`), `ExecStart={layout.wrapper} {module}`.
- `:327` — `_worker_text` (becomes `_worker_template_text`).
- `:425-448` — `_wrapper_text`: the wrapper `cd`s to `install_root` and
  execs `{layout.interpreter} -m "$1"`. Both are frozen at install time —
  see trap 4.
- `:483` — `install()`; `:528` — `uninstall()`; the provenance rule
  (remove only what matches what install wrote) lives in these two.
- `factory/cli/nouns/worker.py:23-32` — the noun's two verbs; `deploy` joins
  them; `:35-61` — the parser shape to extend.

**The heartbeat derivation (US5):**

- `factory/workgraph/workflow.py:429-434` — `_agent_heartbeat_timeout`:
  `max(timeout_s / 2, _AGENT_HEARTBEAT_TIMEOUT_FLOOR)`.
- `:426` — the floor: five beats of `HEARTBEAT_INTERVAL_S`.
- `:411-425` — the comment defending the half-deadline derivation. It says,
  verbatim, "detecting a dead worker a minute later costs nothing (the epic
  is stalled either way)". 2026-08-19 priced that at ~2 hours of park. The
  comment must be rewritten with the cap's rationale, not contradicted by
  code beneath it.
- `:2152` — the sole consumer: `heartbeat_timeout=_agent_heartbeat_timeout(
  context.timeout_s)` on `run_agent_attempt`; `:2153` —
  `retry_policy=_AGENT_RETRIES`; `:345-348` — `_AGENT_RETRIES`,
  `maximum_attempts=2`. **Neither changes.**
- `:2302` — the gate heartbeat: `gate_timeout_s +
  _GATE_HEARTBEAT_GRACE_S` (`:403`) — bounded by a *per-gate* deadline,
  already the right shape. Leave it.
- `factory/workgraph/adapter.py:116` — `DEFAULT_HEARTBEAT_INTERVAL_S = 1.0`;
  `factory/activities/agent_activities.py:472-473` — the pump beats on wall
  clock while the agent works, handed `activity.heartbeat` and the interval.
  A tight timeout is safe from quiet-agent false positives because the pump
  is not output-gated.
- `factory/worker.py:197-208` — the worker-side cadence caps (5s), assembled
  through `_T_PART` (`:197`) with `_heartbeat_cadence_limits()` at `:203`,
  because the parameter's plain spelling is forbidden by 006's SC-005. Any
  new code naming that parameter must reuse the indirection.

**FR-009 is already landed machinery — discovered at the 2026-08-22
refinement pass, this is a REUSE, not a build:**

- `factory/workgraph/adapter.py:732-738` — `pid_file()`:
  `.factory/run/<epic>/<node>.pid`, keyed by node because the worktree is the
  protected resource. The runtime sidecar root — never the diffed tree.
- `:956`, `:980`, `:1010`, `:1032-1040` — the lifecycle: resolve the pid
  file, `await self._reap(pids)` **before** the agent starts, record the new
  process group after spawn, clear on exit.
- `:1320-1336` — `_reap()`: TERM the recorded group, bounded wait, KILL what
  survives. "A precaution, not a gate" — an unreadable/empty/garbage pid file
  costs the node nothing, and pgid `0` is refused by name. This IS the
  US5-S4 control, already written and already tested (`tests/test_adapter.py`).

## The shape of the change, story by story

**US1** — `build_worker` grows a `deployment_config` built from an explicit
environment gate (e.g. `ERGANE_WORKER_BUILD_ID`, validated against
`_WORKER_REVISION` when both exist) — absent, the Worker is constructed
exactly as at `factory/worker.py:242-254` today. The four `@workflow.defn`
decorators take `versioning_behavior`: pinned for epic, escalation, question.
The roadmap's behavior is decided by the trap-7 probe, not by this paragraph.

**US2** — a new module (suggested: `factory/supervision/deploy.py`) owning:
revision resolution and refusals; `git worktree add --detach
<supervision_home>/deployments/<build-id> <sha>` plus `uv sync --frozen`
inside it; instance start `ergane-worker@<build-id>`; bounded poll of
`describe-version` until the worker registers; `set-current-version`; the
report (FR-010). The CLI verb in `factory/cli/nouns/worker.py` stays thin,
like `install`/`uninstall` before it.

**US3** — the reap *decision* is a pure function (suggested: in
`factory/supervision/deploy.py`) over (versions+drainage, open pinned work,
unit states); the *sweep* that acts on it runs from the probe's cycle
(`factory/supervision/probe.py` — find its loop and report path; this plan
verified the module exists, not its internals) and from the tail of `worker
deploy`.

**US4** — `units.py`: `WORKER_UNIT` becomes the template
`ergane-worker@.service` whose body takes `%i` as the build id;
`_worker_text` → `_worker_template_text`; `install()`'s list swaps the file;
`uninstall()` learns the legacy name as a removable-if-matching extra. The
migration refusal (FR-007) queries open workflows for any started without a
versioning behavior before allowing legacy removal.

**US5** — `_agent_heartbeat_timeout` gains a cap:
`max(floor, min(timeout_s / 2, _AGENT_HEARTBEAT_TIMEOUT_CAP))` with the cap
at `timedelta(seconds=120)` — 24 beats of the worker's 5s cadence ceiling,
satisfying FR-008's twenty-beat minimum. **That is the whole story.** The
predecessor sweep (FR-009) already exists end to end — record, reap-before-
launch, garbage-tolerant control, sidecar placement — in the adapter's R4
machinery (see the FR-009 block above). The story verifies the existing
coverage still proves US5-S4 and touches it only if a genuine gap is found;
it does not rebuild it.

## Traps, numbered — read before the first task

1. **A versioned worker serves only its version.** If the production worker
   registers a version while no current version is set, every *new* epic
   stalls silently. This is why FR-001 gates on environment and US1-S2 is a
   control. Do not "simplify" the gate away.
2. **The frozen checkout must live outside the operator checkout** — under
   `supervision_home()/deployments/`. A worktree nested in the repo is
   executable surface in the place this spec exists to stop executing from,
   and the path scan (`InstallLayout.roots`) must learn the deployments root
   or refuse every instance unit.
3. **`git worktree add` writes state into the main repo's `.git`.** Reap
   with `git worktree remove` (and `prune` on failure), never bare `rm -rf` —
   this repository has already paid for sidecars that outlive their kill.
4. **The wrapper and the interpreter are frozen at install time**
   (`units.py:425-448`: `cd {install_root}`, `exec {interpreter}`). A
   template instance must run from the *deployment's* directory with the
   *deployment's* venv interpreter, or you have versioned the unit name and
   not the code. The env-command indirection (sops secrets) must be kept —
   resolving it into `Environment=` lines writes credentials to disk, the
   exact thing the wrapper's docstring exists to prevent.
5. **Do not guess the roadmap's migration mechanics — probe them.** On the
   dev server, with a toy long-lived workflow: does a PINNED workflow's
   continue-as-new inherit its version or re-route to current? If it
   inherits, the roadmap keeps every old version alive forever and FR-002
   fails structurally; the fix is auto-upgrade behavior for the roadmap or a
   `*VersioningOverride` applied by deploy (both SDK classes probed present).
   Write the probe's transcript into the story's evidence.
6. **Pre-versioning epics are the migration's live edge.** Verify on the dev
   server what happens to an open unversioned workflow when a versioned
   worker becomes current — served, stalled, or auto-upgraded — and let
   FR-007's refusal encode the observed answer, not the hoped one.
7. **`set-current-version` before the worker registers fails.** Deploy must
   poll `describe-version` bounded, then set current; on timeout report and
   leave the unit up (US2-S5) — a re-run converges. No rollback logic; the
   idempotent re-run *is* the recovery.
8. **Restart-in-place of a versioned instance must not mint a version.**
   Same checkout, same build id, re-registration — `Restart=on-failure`
   carries to the template unchanged. If you find yourself generating a
   fresh build id at boot, stop; the id comes from the checkout's revision.
9. **Do not touch `start_to_close_timeout` or `_AGENT_RETRIES`** while
   capping the heartbeat. The deadline is the work budget; the retry count
   is the recovery policy; only the liveness bound moves. And the derivation
   comment at `:386-400` must be rewritten to argue the cap, or the next
   reader will "fix" it back.
10. **The predecessor sweep already exists — reuse it, never rebuild it.**
    The adapter's R4 machinery (`pid_file` at `factory/workgraph/adapter.py:732`,
    `_reap` at `:1320`) already records the process group in the runtime
    sidecar (`.factory/run/<epic>/<node>.pid`) and reaps a live predecessor
    before every launch, with the garbage-tolerant control in place. A second
    record or a second sweep is how two mechanisms disagree about one
    resource. If you extend it, the record stays in the sidecar, not the
    worktree — anything inside the diffed tree reaches `read_worktree_diff`,
    the gates and the judge as apparent work product.
11. **A `None` revision must refuse versioned boot by name** (US1-S5).
    `_worker_revision()` returning `None` is a wheel or an unpacked tree —
    exactly the deployments that must not pretend to a build id.
12. **The worker-cadence parameter's plain spelling is forbidden** (006
    SC-005); reuse the `_T_PART` assembly at `factory/worker.py:197-200` if
    any new code needs to name it.
13. **`tests/test_worker.py` runs the production registration against the
    TIME-SKIPPING test server** (`WorkflowEnvironment.start_time_skipping()`,
    `tests/test_worker.py:350`) — not the dev server on 7233. Whether the
    time-skipping server supports the worker-deployment API is UNKNOWN; do
    not assume it. Probe it first; if it refuses, US1's registration test
    (T004) needs `start_local()` or the session dev server behind the
    established live-tier guard — a guard that catches temporalio's **bare
    `RuntimeError`** on a dead port (see `tests/test_doctor_probes.py:361`
    for the shape), never a marker. Either way, keep the versioned worker
    constructible without a deployment existing server-side (the SDK allows
    construction; registration happens at run), so the existing suite passes
    untouched.
14. **Pasted live evidence is now charged to the 64 KiB diff budget.**
    Constitution 2.5.0 (D-050, landed 701b149 — AFTER this spec was drafted)
    counts committed evidence against `DIFF_INPUT_LIMIT = 64 * 1024`
    (`factory/verify/diffbounds.py:42`). This spec's stories lean on pasted
    evidence unusually hard (SC-001..SC-005, T001/T002 transcripts, T009,
    T018, T023, T028, T033). Paste the minimal lines that prove the claim —
    the kill timestamp and the reschedule timestamp, not the whole journal;
    the `describe-version` stanza, not the full describe. A story that pastes
    a raw transcript will blow the boundary gate on evidence alone.

## What this plan deliberately does not include

- **An out-of-band crash reconciler** (systemd `OnFailure=` →
  `temporal activity fail` for the dead worker's pending activities). With
  the US5 cap, its marginal win is ~2 minutes against real machinery and a
  new failure mode (an identity mismatch failing a live activity). Priced
  out; revisit only if the 120s cap proves too slow in practice.
- **Ramping, percentage rollout, manager identities** — single-operator
  floor; current-or-draining is the lifecycle.
- **Versioning the bridge/probe/temporal units** — no epic state; restarts
  are free.
