---
state: draft
fixes:
  - hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout
  - hardening/self-landing-stales-the-running-worker
  - install/restarting-the-worker-deletes-the-operator-cli
# DRAFTED 2026-08-23 by the spec-routing session (branch spec-routing-plan), as
# the worked example for the authoring brief. Three findings, all critical, all
# measured on this host. 082 already landed the deploy-restart half; this spec
# is only what 082 left.
#
# ANCHOR STATUS: the file:line refs below were read from the ledger on
# 2026-08-23 and have NOT been re-verified against the current tree. The
# authoring brief's anchor-verification procedure applies to this spec before
# it flips to ready.
#
# DO NOT FLIP READY without a pre-dispatch review.
---

# Feature Specification: a worker restart does not orphan the work in flight

**Created**: 2026-08-23

## The gap, stated precisely

Three separate mechanisms each turn a routine worker restart or landing into a
floor that stops moving, and none of them is visible from the operator's
surface:

1. **The orphaned activity.** Restarting the worker kills the agent process
   group (`--die-with-parent`) but leaves its `run_agent_attempt` activity in
   `PENDING_ACTIVITY_STATE_STARTED`. Nothing fails until the heartbeat timeout
   (7,200 s measured on epic-070), and because the scheduler parks on
   `any(task.done())`, the whole epic stalls behind the dead activity —
   including ready, independent nodes with free slots. The only clear is a
   manual `temporal activity fail`.
2. **The stale worker.** A factory-code landing invalidates the live worker:
   sandboxed workflow code re-imports from disk while activity modules stay
   passthrough from the stale process, so the next workflow task fails on an
   `ImportError` and retries forever until a manual restart.
3. **The deleted CLI.** The supervised worker runs `uv sync --locked` at boot,
   which removed the `ergane` console script from the venv; the venv's own
   metadata still claims the script exists, so no later sync restores it.

## The rule this spec is asking for

A restart or a landing is a routine event, not an incident. After one, the
floor either keeps moving or says plainly what it is waiting on — and the
operator's own tools survive it.

## What this spec does not change

- 082's deploy-restart mechanics (the half that landed).
- The heartbeat timeout value itself; this spec makes the orphan not depend on
  it, not shorten it.
- The merge queue, the ladder, or judge behaviour.

## User Scenarios & Testing

### User Story 1 - A restart does not orphan the in-flight activity (Priority: P1)

As the worker that owns the agent activity, when I am restarted while an
attempt is running, the attempt is failed promptly and the epic's scheduler
moves on, instead of parking behind a dead activity for the full heartbeat
timeout.

**Why this priority**: P1. This is the measured 2-hour stall; the other two
stories are the same class of "restart is an incident" at different points in
the lifecycle.

**Independent Test**: restart the worker with an attempt in flight and assert
the activity reaches a terminal state within a bounded interval, with the
epic's remaining nodes dispatching.

**Acceptance Scenarios**:

1. **Given** a worker running an agent activity whose process group dies with
   the worker, **When** the worker restarts, **Then** the activity is failed
   (not left `PENDING_ACTIVITY_STATE_STARTED`) within a bounded interval that
   does not depend on the heartbeat timeout — proven by a committed test that
   asserts the failure path fires on worker boot, not on heartbeat expiry.
2. **Given** an epic with one dead activity and one ready independent node
   whose edges are satisfied, **When** the dead activity is failed on boot,
   **Then** the ready node dispatches without an operator running
   `temporal activity fail` — proven by a committed test asserting the
   scheduler unblocks after the boot-time failure.
3. **Given** a worker that boots with no in-flight activities, **When** it
   completes its boot sweep, **Then** it changes nothing and the sweep is
   observable as a no-op — proven by a committed test. The sweep must be safe
   to run on every boot, so the empty case is a first-class case, not an
   afterthought.

---

### User Story 2 - A self-landing does not stale the running worker (Priority: P1)

As the supervision that watches landings, when a factory-code story lands, the
worker is restarted (or the skew is detected and reported) so the next
workflow task does not die on an `ImportError` from a module the sandbox
re-imported but the process never did.

**Why this priority**: P1. Measured on 2026-08-13: a landing at 20:34Z wedged
the next activation at 01:15Z, five hours later, until a manual restart.

**Independent Test**: land a factory-code change, observe the next workflow
activation, and assert it either runs on the new code or reports the skew
plainly.

**Acceptance Scenarios**:

1. **Given** a running worker whose checkout is one commit behind a landing
   that adds a name to a module the workflow sandbox imports, **When** the
   next workflow task runs, **Then** it does not fail with an
   `ImportError`-class retry loop — proven by a committed test that drives
   the boot-time or post-landing check against a stale module set and asserts
   the worker restarts or reports the skew before the task runs.
2. **Given** the check, **When** the worker's boot commit equals the checkout
   HEAD, **Then** it reports no skew and changes nothing — proven by a
   committed test. The check must be silent on a healthy worker; a warning
   that fires permanently is the defect class
   `operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install`
   names, and this spec must not manufacture it.
3. **Given** a landing that touches no factory code (spec markdown only),
   **When** the check runs, **Then** it takes no action — proven by a
   committed test. Restarting on every landing is not the rule; restarting on
   a landing that can change the worker's imported modules is.

---

### User Story 3 - Restarting the worker does not delete the operator CLI (Priority: P2)

As the operator whose tools live in the same venv the worker syncs, when the
worker restarts, the `ergane` console script is still there afterwards.

**Why this priority**: P2. The worker itself is unaffected (it runs
`python3 -m factory.worker`); what breaks is every operator surface, and it
does not self-heal because `uv sync` reconciles against `uv.lock`, not the
filesystem.

**Independent Test**: restart the worker and assert `command -v ergane` still
resolves, and that a second restart is a no-op for the script.

**Acceptance Scenarios**:

1. **Given** a venv in which the `ergane` console script is missing but the
   package metadata still lists it, **When** the worker's boot sync runs,
   **Then** the script is restored — proven by a committed test that simulates
   the missing-script state and asserts the boot path repairs it, since
   `uv sync --locked` alone reports "would make no changes" and cannot.
2. **Given** a healthy venv, **When** the worker's boot sync runs, **Then**
   the console script is present before and after and the sync is a no-op for
   it — proven by a committed test.
3. **Given** the boot path, **When** it runs on a host where the venv is not
   writable, **Then** it fails loudly naming the path, rather than silently
   leaving the CLI deleted — proven by a committed test. A silent no-op is
   exactly how this defect shipped: the sync succeeded, the script stayed
   gone, and nothing said so.

## Requirements

### Functional Requirements

- **FR-001**: On worker boot, the worker MUST fail any agent activity it owns
  that is still in a started state with no live process behind it, within a
  bounded interval that does not depend on the heartbeat timeout.
- **FR-002**: The boot-time failure MUST unblock the epic's scheduler: a ready
  node with satisfied edges MUST dispatch after the failure, with no operator
  action.
- **FR-003**: The boot sweep MUST be a no-op when no such activity exists, and
  MUST be safe to run on every boot.
- **FR-004**: After a landing that changes a module the workflow sandbox
  imports, the worker MUST either restart itself or report the skew before the
  next workflow task runs; it MUST NOT enter an `ImportError` retry loop.
- **FR-005**: The skew check MUST be silent when the worker's boot commit
  equals the checkout HEAD, and MUST take no action on landings that touch no
  factory code.
- **FR-006**: The worker's boot sync MUST restore the `ergane` console script
  when the package metadata lists it but it is absent from the venv's bin
  directory.
- **FR-007**: The boot path MUST fail loudly, naming the path, when it cannot
  write to the venv; it MUST NOT report success while leaving the CLI
  deleted.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005]
  persona: opus-closer
US3:
  depends_on: []
  implements: [FR-006, FR-007]
  persona: opus-closer
```

US1 and US2 both reach for the worker's boot path, so US2 lands on US1's base
(`depends_on_merged`): the boot sweep and the skew check are one sequence, and
US2's check must not restart the worker into US1's half-finished sweep. US3
is independent: it touches the boot sync, not the activity or module paths,
and can run in parallel with US1.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the boot-sweep output for a worker that boots with one
  dead started activity: the activity's terminal state and the interval from
  boot to failure, alongside the heartbeat timeout it no longer depends on.
- **SC-002**: Paste the scheduler state after the sweep: the ready node
  dispatched, no operator command in between.
- **SC-003**: Paste the no-op control: a boot with no in-flight activities
  changing nothing.
- **SC-004**: Paste the skew check's output for a stale worker (boot commit
  behind a factory-code landing) and for a healthy one, side by side.
- **SC-005**: Paste the console script's presence before and after a worker
  restart, including the repair case where the script was missing but the
  metadata listed it.
- **SC-006**: Paste the loud-failure case: a non-writable venv, the named
  path, and the non-zero exit.

## Assumptions

- The worker can enumerate the activities it owns at boot (the SDK exposes the
  worker's task-queue state); if it cannot, FR-001's mechanism is a
  post-landing check on the epic's pending activities rather than a
  worker-side sweep. The plan must settle which, with a probe, before US1
  dispatches.
- `temporal activity reset` is NOT a workaround for the orphan: it only takes
  effect on the next heartbeat, fail, or timeout, and a dead worker never
  heartbeats again. The measured clear was `temporal activity fail`, and the
  external fail proved terminal rather than consuming the retry attempt.
- The venv metadata defect (missing script, RECORD still listing it) is
  repairable by re-writing the script from the entry point declared in the
  package metadata; the plan must verify the entry point is readable from
  `ergane_cli`'s metadata on this host before US3 dispatches.
- 082's deploy-restart half is landed and out of scope; this spec does not
  re-derive how a restart is triggered, only what must be true afterwards.
