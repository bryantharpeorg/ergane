# Tasks: a worker restart does not orphan the work in flight

**Spec**: `specs/099-a-worker-restart-does-not-orphan-the-work-in-flight/spec.md`
**Plan**: `specs/099-a-worker-restart-does-not-orphan-the-work-in-flight/plan.md`

Read the plan's traps before the first task. Five decide whether an attempt lands.

**Trap 1 first, because it is the one that produces a *passing* wrong answer.**
The sweep fails the activity the way the operator did: terminal, no retry
consumption. `temporal activity reset` is not a workaround — it only takes
effect on the next heartbeat, fail, or timeout, and a dead worker never
heartbeats again. A sweep that *resets* instead of *fails* passes a naive
"activity is no longer PENDING" test and fails US1-S1.

**Trap 5: the sweep and the skew check are one sequence.** Both reach for the
worker's boot path (`factory/worker.py:325`), so US2 lands on US1's base
(`depends_on_merged`). The sequence is sweep first, then skew check, then
`run()`. An attempt that reorders them, or that lets the skew check's restart
skip the sweep, lands a worker that orphans its own in-flight work on the very
restart that was supposed to fix it.

**Trap 3: the skew check must be silent when boot commit equals HEAD.** A
warning that fires permanently is the defect class
`operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install`
names. US2-S2 is the control. **Trap 4: do not restart on every landing** —
the check is "did the landing touch a module the sandbox imports," not "did a
landing happen." **Trap 9: do not touch the heartbeat timeout values** —
`_AGENT_HEARTBEAT_TIMEOUT_FLOOR` and `_AGENT_HEARTBEAT_TIMEOUT_CEILING` at
`factory/workgraph/workflow.py:447-448` are 082's.

## Phase 1: User Story 1 — A restart does not orphan the in-flight activity

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) In
      `tests/test_worker_boot_sweep_fails_orphaned_activities.py`, drive the
      boot path against a fake client that reports one started
      `run_agent_attempt` activity with no live process behind it, and assert
      the activity is failed (not left `PENDING_ACTIVITY_STATE_STARTED`) within
      a bounded interval that does not depend on the heartbeat timeout. The
      failure path fires on worker boot, not on heartbeat expiry (trap 1).
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert the scheduler unblocks after
      the boot-time failure: an epic with one dead activity and one ready
      independent node whose edges are satisfied dispatches the ready node
      without an operator running `temporal activity fail`. The park at
      `factory/workgraph/workflow.py:1014` re-evaluates on every activation;
      the test asserts the re-evaluation sees the failed task.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) **The no-op control.** Drive the
      boot path against a fake client that reports no in-flight activities and
      assert the sweep changes nothing and is observable as a no-op. The empty
      case is a first-class case, not an afterthought (trap 2).

### Implementation for this story

- [ ] T004 [US1] (FR-001, FR-002, FR-003) Implement the boot sweep in
      `factory/worker.py`'s boot path, between the `Client.connect` at
      `:333` and the `build_worker(client).run()` at `:341`. The sweep
      enumerates the activities the worker owns on the task queue, fails any
      that are in a started state with no live process behind them, and is a
      no-op when none exist. The terminal path is the existing ladder:
      `_attempt_timeout` at `factory/workgraph/workflow.py:2216` turns the
      failure into a `TIMEOUT` result, `_reap_finished` at `:1467` reaps the
      task, and the park at `:1014` unblocks. Do not touch the heartbeat
      timeout values (trap 9).
- [ ] T004a [US1] (FR-001) **The mechanism probe.** Before T004, run the
      probe named in the spec's Assumptions block: does the installed
      `temporalio` client expose the task queue's pending activities, and can
      a worker-side fail reach them? Commit the probe's output as pasted text.
      If the client cannot enumerate, the mechanism is a post-landing check on
      the epic's pending activities rather than a worker-side sweep, and T004
      moves to the epic's landing path. The terminal path is the same either
      way.

### Verification for this story

- [ ] T005 [US1] (SC-001) Commit the boot-sweep output for a worker that boots
      with one dead started activity: the activity's terminal state and the
      interval from boot to failure, alongside the heartbeat timeout it no
      longer depends on.
- [ ] T006 [US1] (SC-002) Commit the scheduler state after the sweep: the
      ready node dispatched, no operator command in between.
- [ ] T007 [US1] (SC-003) Commit the no-op control: a boot with no in-flight
      activities changing nothing.

## Phase 2: User Story 2 — A self-landing does not stale the running worker

### Tests for this story (write FIRST, must fail)

- [ ] T008 [P] [US2] (spec US2-S1, FR-004) In
      `tests/test_worker_boot_skew_check.py`, drive the skew check against a
      fake checkout whose HEAD is one commit ahead of the worker's boot commit
      and whose landing adds a name to a module the workflow sandbox imports,
      and assert the worker restarts or reports the skew before the next
      workflow task runs. The check must not enter an `ImportError` retry
      loop.
- [ ] T009 [P] [US2] (spec US2-S2, FR-005) **The silent control.** Drive the
      skew check with the worker's boot commit equal to the checkout HEAD and
      assert it reports no skew and changes nothing. The check must be silent
      on a healthy worker; a warning that fires permanently is the defect
      class `operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install`
      names (trap 3).
- [ ] T010 [P] [US2] (spec US2-S3, FR-005) **The spec-only control.** Drive
      the skew check against a landing that touches no factory code (spec
      markdown only) and assert it takes no action. Restarting on every
      landing is not the rule (trap 4).

### Implementation for this story

- [ ] T011 [US2] (FR-004, FR-005) Implement the skew check in
      `factory/worker.py`'s boot path, after the sweep (trap 5: the sequence
      is sweep first, then skew check, then `run()`). The check compares
      `_WORKER_REVISION` (`factory/worker.py:229-231`, captured at import)
      against the checkout's current HEAD (the same command
      `_worker_revision()` already runs, `:212`). When the landing touches a
      module the sandbox imports, the worker restarts via 082's deploy path
      (`factory/supervision/deploy.py:500`) or reports the skew; when it does
      not, the check is silent. The check must not disturb
      `_deployment_registration()` (`:235`).

### Verification for this story

- [ ] T012 [US2] (SC-004) Commit the skew check's output for a stale worker
      (boot commit behind a factory-code landing) and for a healthy one, side
      by side.

## Phase 3: User Story 3 — Restarting the worker does not delete the operator CLI

### Tests for this story (write FIRST, must fail)

- [ ] T013 [P] [US3] (spec US3-S1, FR-006) In
      `tests/test_worker_boot_repairs_console_script.py`, simulate a venv in
      which the `ergane` console script is missing but the package metadata
      still lists it, drive the boot sync, and assert the script is restored.
      `uv sync --locked` alone reports "would make no changes" and cannot
      (trap 6).
- [ ] T014 [P] [US3] (spec US3-S2, FR-006) **The no-op control.** Drive the
      boot sync against a healthy venv and assert the console script is
      present before and after and the sync is a no-op for it. A repair that
      re-writes the script on every boot is a new defect class (trap 6).
- [ ] T015 [P] [US3] (spec US3-S3, FR-007) **The loud-failure case.** Drive
      the boot path against a non-writable venv and assert it fails loudly,
      naming the path, rather than silently leaving the CLI deleted. A silent
      no-op is exactly how this defect shipped (trap 7).

### Implementation for this story

- [ ] T016 [US3] (FR-006, FR-007) Implement the repair in the worker's boot
      sync path, after the `uv sync --locked` at
      `/home/admin/code/homelab/infra/ergane-supervision/ergane-worker-run.sh:32`.
      When the package metadata lists the `ergane` entry point
      (`pyproject.toml:36` — `ergane = "factory.cli.main:main"`) but the bin
      directory does not contain the script, re-write it from the entry point.
      When the script is present, the repair is a no-op. When the venv is not
      writable, the boot path fails loudly, naming the path, and exits
      non-zero (trap 7).
- [ ] T016a [US3] (FR-006) **The entry-point probe.** Before T016, verify the
      entry point is readable from `ergane_cli`'s metadata on this host.
      Commit the probe's output as pasted text. If the metadata does not list
      the entry point, the repair mechanism is different and the spec's
      Assumptions block must be re-read.

### Verification for this story

- [ ] T017 [US3] (SC-005) Commit the console script's presence before and
      after a worker restart, including the repair case where the script was
      missing but the metadata listed it.
- [ ] T018 [US3] (SC-006) Commit the loud-failure case: a non-writable venv,
      the named path, and the non-zero exit.
