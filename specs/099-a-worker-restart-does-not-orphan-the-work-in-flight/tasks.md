# Tasks: a worker restart does not orphan the work in flight

Read `plan.md` before the first task. Seven of its eighteen traps decide whether
an attempt lands. **Trap 1 is the one that produces a plausible wrong answer**: the
ledger row this spec grew from still names a 7,200 s heartbeat window that
082-US5 closed — `_AGENT_HEARTBEAT_TIMEOUT_CEILING` is `timedelta(seconds=120)`
at `factory/workgraph/workflow.py:487` — so an implementer who shortens that
ceiling, or adds a `schedule_to_start_timeout` at
`factory/workgraph/workflow.py:2429-2445`, has built something this spec
forbids and left the actual defect in place. **Trap 5** is why US2 does not
compare revisions at boot: `_WORKER_REVISION` (`factory/worker.py:240`) is
captured microseconds earlier, so a boot-time comparison can never fire.
**Trap 16** is the same shape one level down: `git log <rev>..HEAD -- factory/`
resolves its pathspec against the process's cwd, so the watch takes the checkout
root as a parameter instead of copying `_worker_revision`'s package directory —
and instead of the `.ergane` state directory
`factory/activities/agent_activities.py:188` — `factory_root` returns, which is
already imported in the file T018 edits and reads like the answer.
**Trap 8** is the one that fails silently in production: never cancel a live
attempt to take a restart, and write the in-flight counter exactly as that trap
says — increment as the **first** statement inside the `try:` at
`factory/activities/agent_activities.py:499`, **decrement** in the `finally`.
Both near-misses (an increment placed after `adapter_for`, a `finally` that
assigns zero) pass a one-attempt suite and are dead or harmful in production.
**Trap 11**: the console-script check may not exit non-zero, or five boots
inside five minutes leave the unit stopped. **Trap 17**: the drain cancels every
activity the worker holds, and FR-008 guards only the agent attempt — do not
widen it to all of them. **Trap 18**: sdk-core reports a graceful-shutdown
cancellation to the server as its own retryable `WorkerShutdown` failure and
discards the adapter's payload, so the archived transcript reaches the workflow
never and the one relaunch survives — do not chase either into
`factory/workgraph/workflow.py`, which no requirement here permits editing.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the
judge sees; runtime evidence is committed as pasted output.

Every paste below is one you can produce inside your own worktree. Nothing here
asks you to restart the worker, land code under a running one, delete
`.venv/bin/ergane` or change a venv's permissions: those four host mutations are
the operator's sequence in `plan.md` § "Verification the operator will run", and
the unit you would be restarting is the one this attempt is running inside
(`KillMode=control-group`, `factory/supervision/units.py:599`). If a task seems
to need the live host, it is the wrong task — say so in the attempt rather than
reaching for `systemctl`.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A restart does not orphan the in-flight activity

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 14) In
      `tests/test_worker_drains_on_stop_signal.py`, assert the boot path
      installs handlers for SIGTERM and SIGINT and that invoking each registered
      callback calls the constructed worker's `shutdown()`. Drive it against a
      fake worker with `run()` and `shutdown()`, never a connected client
      (`factory/roadmap/schedule.py:247` — `_refuse_live_client` is why), and
      never by raising a real signal at the pytest process: in this red phase no
      handler exists yet, so a raised SIGTERM ends the whole gate run at signal
      143 instead of failing this test.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, traps 2 and 3) Two assertions, one
      per half of the criterion. First: against a fake worker whose `shutdown()`
      completes only after a recorded in-flight attempt task finishes, the boot
      path returns only after that task completed — the ordering is the half a
      test-only diff cannot fake. Second: drive
      `factory/activities/agent_activities.py:482` — `run_agent_attempt` against
      a fake adapter that records the cancellation, and assert the raised
      `CancelledError` carries `Termination.KILLED` and a transcript path. Do
      not assert the process group died or a transcript was archived: the
      docstring at `factory/activities/agent_activities.py:493-494` says both
      are the adapter's, and a fake adapter does neither.
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) **The empty control.** Assert a
      worker with nothing in flight completes its shutdown and that the drain
      records that the wait ended because the shutdown finished, not because its
      bound elapsed — a returned reason or a recorded sentinel, not a wall
      clock. Assert too that the construction is unchanged: the same `Worker`
      arguments `factory/worker.py:268` — `build_worker` passes today.
- [ ] T004 [P] [US1] (spec US1-S4, FR-003, trap 4) Assert the drain bound is
      smaller than the worker unit's stop timeout by reading both from source:
      the bound this story introduces and `stop_timeout_s=120` at
      `factory/supervision/units.py:642`. Two numbers agreeing today is not the
      same as two numbers that cannot disagree.

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002, trap 2) In `factory/worker.py:333` — `main`,
      hold the constructed worker in a local, install SIGTERM and SIGINT
      handlers on the running loop that call its `shutdown()`, and await the
      `run()` at `factory/worker.py:350` as today. Do not catch
      `CancelledError` around the `run()` and do not cancel the task: the SDK's
      own `run` docstring says a cancel can cancel the shutdown.
- [ ] T006 [US1] (FR-003, FR-004, trap 4) Bound the drain and name the bound
      once, next to a comment citing `factory/supervision/units.py:642` and the
      120 s stop timeout it renders through `factory/supervision/units.py:601`.
      The bound is the smaller value; the drain is over before systemd's stop
      timeout could end the process group mid-archive. Record which of the two
      ended the wait — the shutdown completing or the bound elapsing — so T003
      can assert the empty case took the first.
- [ ] T007 [US1] (FR-004) Leave `factory/worker.py:268` — `build_worker`
      constructing exactly the arguments it constructs today, including
      `_heartbeat_cadence_limits()` and `_deployment_registration()`
      (`factory/worker.py:243` — `_deployment_registration`). The drain is a
      property of `main`, not of the
      registration, so a worker nobody signals behaves as it does today.

### Verification for this story

- [ ] T008 [US1] Paste, as committed evidence, the run of
      `tests/test_worker_drains_on_stop_signal.py` — the red run against the
      unchanged boot path and the green run after T005 to T007 — so the diff
      carries the proof that the drain test fails without the production
      change. The judge sees the diff only.
- [ ] T009 [US1] Paste, as committed evidence, the two numbers side by side: the
      drain bound this story introduces, and the `TimeoutStopSec=` line as
      `factory/supervision/units.py:611` — `_worker_template_text` renders it.
      Produce it from a short script in the worktree that calls that function;
      no host, no unit file, no `systemctl`.

## Phase 2: User Story 2 — A self-landing does not stale the running worker

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1, FR-005, FR-007, trap 9) In
      `tests/test_worker_skew_watch.py`, drive the watch against a throwaway
      checkout — a real `git init` in `tmp_path`, not a stubbed git — whose HEAD
      has moved past the imported revision with a commit touching `factory/`,
      with no attempt in flight, and assert one report naming both revisions and
      a request to exit with a **non-zero** status. A zero exit under
      `Restart={restart}` (`factory/supervision/units.py:603`) with
      `restart="on-failure"` (`factory/supervision/units.py:639`) leaves the
      floor down.
- [ ] T011 [P] [US2] (spec US2-S2, FR-005, FR-009, trap 10) **The silent
      control.** Equal revisions, ticked repeatedly: no log line, no exit
      request, nothing written. A notice that fires forever is the defect class
      `factory/cli/nouns/build.py:986` — `_skew_notice` already ships.
- [ ] T012 [P] [US2] (spec US2-S3, FR-006, trap 16) **The spec-only control.**
      In the same throwaway checkout, HEAD has moved but no commit between the
      two revisions touches a file under `factory/`: no report, no exit request.
      Pass the checkout root the way production will and let the real pathspec
      decide — a stubbed git answers this test and cannot catch trap 16's dead
      watch.
- [ ] T013 [P] [US2] (spec US2-S4, FR-008, trap 8) **The live-attempt control,
      driven with two.** Actionable skew with **two** agent attempts in flight at
      once — `factory/worker.py:268` — `build_worker` registers no limit on
      concurrent activities, so two are possible — ticked, then one attempt
      completes, then ticked again: neither attempt is cancelled, no exit is
      requested on either tick, and the report is emitted exactly once across
      both. One attempt cannot tell a `finally` that decrements from one that
      assigns zero; two can, and the zero variant fires the exit into a live
      attempt.
- [ ] T014 [P] [US2] (spec US2-S6, FR-007, FR-008, FR-009, trap 8) **The
      deferred exit.** The half a latch-and-forget implementation would leave
      untested: after the report has been emitted on an earlier tick with an
      attempt in flight, drive the in-flight count to zero and tick again —
      assert the non-zero exit request is made on that tick and the report is
      **not** repeated. Without this case a worker that reports once and never
      exits satisfies T010 to T013 and T015 in full while leaving FR-007's wedge
      in place for the whole of a multi-hour attempt.
- [ ] T015 [P] [US2] (spec US2-S5, FR-009, trap 10) **The packaged control.**
      `factory/worker.py:220` — `_worker_revision` returns `None`: no report,
      no exit request, nothing written.
- [ ] T016 [P] [US2] (spec US2-S7, FR-005, FR-006, traps 5 and 16) **The
      wiring, and the root production supplies.** Drive
      `factory/worker.py:333` — `main` against a fake worker with `run()` and
      `shutdown()`, with the process's working directory set to the throwaway
      checkout of T010 and the watch's construction recorded: assert the watch
      was started before the `run()` await at `factory/worker.py:350` and
      cancelled after that await returned, and that the checkout root it was
      constructed with is that working directory — neither
      `Path(__file__).parent` nor the `.ergane` state directory
      `factory/activities/agent_activities.py:188` — `factory_root` returns.
      Without this case a watch nothing ever starts, or one handed a root whose
      pathspec matches nothing, passes T010 to T015 in full.

### Implementation for this story

- [ ] T017 [US2] (FR-005, FR-006, traps 6 and 16) Add the skew watch to
      `factory/worker.py`: a background task started beside the `run()` await
      at `factory/worker.py:350` and cancelled when it returns, comparing
      `_WORKER_REVISION` (`factory/worker.py:240`) against a fresh
      `factory/worker.py:220` — `_worker_revision` at a bounded cadence, and
      asking git whether any commit between the two touched `factory/`. Copy
      the invocation shape from `factory/doctor/probes.py:161` —
      `_newest_factory_commit`; do **not** import it —
      `factory/doctor/probes.py:25-26` pulls `LiteLLMClient` and
      `factory.workgraph.cli` into the worker's import graph. Take the checkout
      root as a parameter and run the range query there — never at the package
      directory `factory/worker.py:220` — `_worker_revision` uses, and never at
      the `.ergane` state directory
      `factory/activities/agent_activities.py:188` — `factory_root` returns: the
      pathspec is relative to cwd, so from the package directory it resolves to
      `factory/factory/` and from the state directory to `.ergane/factory/`, and
      both match nothing for every landing forever. What `main` passes is the
      process's own working directory, which the wrapper's `cd "$root"`
      (`factory/supervision/units.py:802`) and the unit's `WorkingDirectory`
      (`factory/supervision/units.py:593`) both establish. Start the watch
      beside that `run()` await and cancel it when the await returns (FR-005,
      US2-S7): a watch `main` never starts is the other way this story lands
      green and dead.
- [ ] T018 [US2] (FR-008, trap 8) Add the in-flight count the watch reads: a
      module-level integer in `factory/activities/agent_activities.py`,
      **incremented as the first statement inside** the `try:` that already opens
      at `factory/activities/agent_activities.py:499` — above the
      `activity.info()` and `derive_session_id` lines and above
      `adapter = adapter_for(DEFAULT_AGENT)` at
      `factory/activities/agent_activities.py:521` — and **decremented** in a
      `finally` on that same `try:`, so a cancelled attempt still decrements. Two
      near-misses, both of which pass a one-attempt test: an increment placed
      "before the adapter call" at
      `factory/activities/agent_activities.py:522` sits after `adapter_for`,
      whose `AdapterError` is caught at
      `factory/activities/agent_activities.py:576`, and that path runs the
      `finally` without having incremented — the count reaches -1 and FR-007's
      exit is dead forever; and a `finally` that **assigns zero** rather than
      decrementing lets the first of two concurrent attempts declare the floor
      idle, firing the exit into the second. Do not add a second
      `except asyncio.CancelledError` — the one at
      `factory/activities/agent_activities.py:562` stays the only handler. The
      `Worker` object exposes no such count.
- [ ] T019 [US2] (FR-007, FR-008, FR-009, traps 7 and 17) On actionable skew,
      report once and request the exit through US1's drain with a non-zero
      status on the first tick at which the count from T018 reads zero — the
      request is deferred by a live attempt, never abandoned by one, and the
      count is of `run_agent_attempt` only, never of every activity the worker
      holds (trap 17). Do not touch `factory/doctor/probes.py:322` —
      `StaleWorkerProbe`, and do not mint or reuse its `ops/stale-worker`
      finding key: this is the worker acting on its own skew, not a second
      detector.

### Verification for this story

- [ ] T020 [US2] Paste, as committed evidence, the watch driven against the
      throwaway checkout of T010 and T012: the transcript of the two ticks — one
      after a commit touching `factory/` and one after a spec-markdown-only
      commit — showing the single skew line naming both revisions, the non-zero
      exit request, and then nothing at all for the markdown landing. Paste
      beside it the three-tick transcript of T014: the count at two, at one and
      at zero, with exactly one report and the exit request appearing only on
      the last. It is the
      pathspec that has to be exercised, and a real temporary repository
      exercises it without touching this host's worker.

## Phase 3: User Story 3 — Restarting the worker does not delete the operator CLI

### Tests for this story (write FIRST, must fail)

- [ ] T021 [P] [US3] (spec US3-S1, FR-010, FR-011, trap 12) In
      `tests/test_worker_restores_console_script.py`, build a temporary bin
      directory whose declared console script is missing while the
      distribution's metadata still declares it — the 2026-08-19 state,
      manufactured, because the residue that caused it is long gone from this
      venv — drive the boot check, and assert the file exists afterwards, is
      executable, and invokes the declared entry point. Read the declaration
      from the installed distribution's metadata, not from `pyproject.toml:36`.
- [ ] T022 [P] [US3] (spec US3-S2, FR-013) **The no-op control.** Every
      declared script present: assert the file's bytes and modification time
      are unchanged and nothing was logged. A repair that rewrites on every
      boot churns the bin directory on every restart.
- [ ] T023 [P] [US3] (spec US3-S3, FR-012, traps 11 and 14) **The loud,
      non-fatal case.** A bin directory that cannot be written: assert one ERROR
      naming the path and the entry point, **and** that the boot continued to
      its connect at `factory/worker.py:342`, with the client patched so the
      test reaches no server. An exit here burns `StartLimitBurst`
      (`factory/supervision/units.py:588`) and stops the unit.
- [ ] T024 [P] [US3] (spec US3-S4, FR-010) **The nothing-declared control.** An
      installation whose metadata declares no console script: nothing written,
      nothing logged, nothing raised.

### Implementation for this story

- [ ] T025 [US3] (FR-010, FR-013, trap 12) Add the check to
      `factory/worker.py:333` — `main`, before the connect at
      `factory/worker.py:342`: read this installation's own console-script
      entry points from its distribution metadata, compare against the bin
      directory of the interpreter running the process
      (`Path(sys.executable).parent`), and return silently when every declared
      script is present or when none is declared. Take the bin directory and the
      entry-point source as arguments, which is the only way T021 and T023 can
      drive a temporary and a read-only directory at all: `main` supplies
      `Path(sys.executable).parent` and the distribution resolved from the
      running package, never a literal distribution name — the 056 rename moved
      it to `ergane-cli` while the console script kept the old name, and that
      residue is what the ledger row blames (trap 12).
- [ ] T026 [US3] (FR-011, FR-012, traps 11 and 13) When a declared script is
      absent, write it back from the declared entry point, make it executable
      and log once; when the write fails, log at ERROR naming the path and the
      entry point and continue. Do not raise, do not exit, and do not go
      looking for the host's `uv sync` run script — it is outside this
      repository and outside the worktree — nor add this to
      `factory/supervision/deploy.py:486` — `_sync`, which the supervised
      host's boot never calls.

### Verification for this story

- [ ] T027 [US3] Paste, as committed evidence, the boot check driven against a
      temporary bin directory in all four of its states: the restored script's
      mode and first line, the untouched file's identical mtime on a second
      pass, the ERROR line naming the path and the entry point when the
      directory is read-only, and the silence when the metadata declares no
      script. A `tmp_path` and a `chmod` inside it produce every one; the
      operator's venv is not involved.

## Verification

- [ ] T028 The full gate command passes green.
- [ ] T029 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end, by the operator and not by any node. Its
      steps 1 to 6 mutate the live host — restarting the worker with an attempt
      in flight, landing factory code under it, deleting `.venv/bin/ergane`,
      making the venv bin read-only — and no attempt may perform any of them on
      itself. Step 4
      — a factory-code landing while an attempt is in flight — is the one step no
      committed test replaces, and step 7's grep is the check that this spec did
      not quietly become the heartbeat spec it is not.
