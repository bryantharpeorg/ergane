---
state: draft
fixes:
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
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. The anchor status paragraph above is now discharged: 63 citations
# were re-read line by line, 42 of them were bare `:NNN` refs sitting under
# bolded filename headings — which are not cites, so each silently inherited
# whatever path was named last: the three that meant factory/versioning.py read
# `factory/workgraph/adapter.py` while claiming `factory/versioning.py`. Every
# surviving anchor is now a full repository-relative path in the symbol-tier
# form.
#
# WHERE THIS CAME FROM. Three critical ledger rows, all measured on this host:
# the 2026-08-19/20 orphan on epic-070, the 2026-08-13 landing that wedged the
# 01:15Z roadmap activation, and the 2026-08-19 `uv sync` that deleted
# `.venv/bin/ergane`. The gap section below re-derives each mechanism from the
# tree at 602a92c rather than from those rows.
#
# WHAT IT COST, MEASURED. Two hours of stalled epic on 2026-08-19/20 (now
# bounded at 120 s, see below); five hours of wedged roadmap on 2026-08-13,
# 20:34Z landing to 01:15Z activation, cleared only by a hand-typed
# `systemctl --user restart`; and an operator host with a running factory and
# no CLI able to ask it anything, worked around by hand-writing a six-line shim
# that the next sync is free to delete again.
#
# NOT IN SCOPE. The heartbeat bound, which is 082-US5's and stays as it is; the
# missing schedule-to-start bound and the `build status` line that cannot tell
# SCHEDULED from STARTED, which are the surviving half of the removed lead key
# and are owned by no spec at 602a92c; `EpicWorkflow`, which goes on recording
# what it records today; the two `interpreter/` rows named below, which this
# spec touches and does not fix; and every mutation of the supervised host,
# which belongs to the operator's sequence in `plan.md` and to no node.
#
# THE LEAD KEY IS REMOVED, AND THE STORY THAT DECLARED IT IS RE-AIMED.
# `hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout`
# named the 7,200 s heartbeat window. 082-US5 closed it: the ceiling is
# `timedelta(seconds=120)` at `factory/workgraph/workflow.py:487`, shipped in
# v0.3.0, v0.4.0 and v0.5.0, and the scheduler park at
# `factory/workgraph/workflow.py:1137` is correct given that bound. The
# ledger's own 2026-09-03 correction says the surviving half is a missing
# schedule-to-start bound plus a status line that cannot tell SCHEDULED from
# STARTED. Nothing in this spec fixes either, so 099 does not declare it. The
# owner of record is the backlog item `a-worker-restart-does-not-leave-a-node-reading-running`
# in the operator's round-3 web triage document — named rather than anchored,
# because that document is untracked at 602a92c and so reaches no node
# worktree — whose "Findings it would declare" block names this key. That is a
# backlog entry and not a spec: no directory under `specs/` declares the key at
# 602a92c, so until one is drafted the row is open and unowned, and
# `ergane findings triage` should keep saying so.
# US1 keeps its number and its title and is re-aimed at the mechanism that is
# still live and still worker-side: nothing handles SIGTERM, so the drain the
# unit text already pays 120 s for never runs.
#
# US2 AND US3 KEEP THEIR KEYS, AND THE INSTRUCTIONS UNDER THEM WERE WRONG.
# The old plan told US2 to compare the boot revision against HEAD *at boot* —
# where they are equal by construction, so the check could never fire. It now
# runs while the worker runs. The old plan told US3 to edit the supervised
# host's own run script, which lives in the operator's separate homelab
# checkout — outside every node's worktree and outside this repository; the
# check moves into the worker's own boot, the only code this repository owns
# that runs on that host after that sync. The old FR-007 also required a
# non-zero exit on a non-writable venv, which under `Restart=on-failure` and
# `StartLimitBurst=5` stops the whole unit — trading a missing CLI for a dead
# factory. It now reports and keeps starting.
#
# TOUCHED, NOT FIXED: TWO CRITICAL INTERPRETER ROWS, DELIBERATELY UNDECLARED.
# `interpreter/a-landed-activity-type-blocks-every-new-epic-until-the-worker-restarts`
# (open, critical, 2 occurrences, last 2026-08-30) and
# `interpreter/a-fresh-epic-on-a-stale-worker-wedges-in-workflow-task-retry`
# (open, critical, 3 occurrences, last 2026-08-30) name the same stale-worker
# mechanism US2 acts on, and neither is fixed WHOLE here, so neither is
# declared. The first row's own primary ask is a different remedy — that
# `ergane build start` REFUSE at dispatch when the worker's loaded revision
# differs from the tree's — and US2 adds no refusal anywhere. The second row
# records a fact this spec never states and that bounds its own claim:
# "RESTARTING THE WORKER IS NOT SUFFICIENT ON ITS OWN" once a wedged run's
# history already holds a pre-landing payload; that run must also be
# terminated, and no requirement here terminates anything. US2 prevents the
# next wedge; it clears no wedge that already exists. Declaring either key
# would let a later `ergane findings triage --apply` close a critical row
# against a spec that never reached it — the 100/092/118 half-fix shape.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) at 602a92c, after an adversarial
# review refuted the refined trio. US1-S1 asked for a test that raises the stop
# signal in the test runner, which trap 14 and T001 forbid and which, in the
# mandated red phase, ends the pytest process instead of failing it — the
# criterion now asserts the registered handler callback, invoked directly.
# US1-S2 asked a fake adapter to prove a process-group kill and a transcript
# archive that the activity's own docstring assigns to the adapter, leaving a
# remainder a test-only diff satisfied — it now pins the drain's ordering,
# which no test-only diff can. US1-S3 and US3-S3 asserted a wall clock and a
# polling call no test may reach; both now assert the mechanism (the drain's
# own return reason, the connect at `factory/worker.py:342`). Five
# committed-evidence tasks told a node to restart the live worker, land factory
# code under it, delete `.venv/bin/ergane` or make its bin read-only — a node
# is an attempt inside the unit that restart kills, so all five are struck and
# the six host steps stay where they already were, in the operator's sequence.
# Four anchors are re-aimed at what the prose names
# (`factory/activities/agent_activities.py:522`,
# `factory/doctor/probes.py:362-365`, `factory/workgraph/workflow.py:1137`,
# `factory/supervision/units.py:599-601`), one trap is added for the git
# pathspec's cwd, and the lead key stays removed. State stays draft and the
# pre-dispatch hold above stands.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, after a second
# adversarial review: the removed lead key's owner was fiction and is corrected
# above — the entry directly above claimed a spec 147 drafted "in this run",
# and no such directory exists at 602a92c, so the owner of record is now cited
# as the backlog item `a-worker-restart-does-not-leave-a-node-reading-running`
# in the operator's round-3 web triage document and the key is stated to be
# unowned by any spec; FR-008's deferred exit had no
# acceptance scenario at all, so a latch-that-never-exits passed the whole
# story — US2-S6 now proves the exit fires once the last attempt ends, truth
# table row 3 says "defers" instead of "keeps working", and US2-S4 drives two
# concurrent attempts so "in flight" means more than zero; the in-flight
# counter instruction had two literal readings and both were green-and-dead (a
# cleared-to-zero count fires FR-007 into a live attempt; an increment placed
# after `adapter_for` runs the `finally` on the launch-failure path and reaches
# -1 forever), so trap 8 and T016 now pin the increment as the first statement
# inside the `try:` and the `finally` as a decrement; the two critical
# `interpreter/` rows are named above as touched-not-fixed; the drain's blast
# radius across non-agent activities is stated in "What this spec is not" and
# in a new trap; `factory/supervision/engine_identity.py:57` — `engine_skew` is
# named as the third skew surface an implementer will find first; four def/class anchors are
# rewritten in symbol-tier form; and operator step 1 now expects "terminal or
# relaunched" rather than "terminal". State stays draft and the pre-dispatch
# hold above stands.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, after a third
# adversarial review, whose two lenses contradicted each other on the SDK and
# were settled against the pinned source. sdk-core reports a graceful-shutdown
# cancellation to the server as a *retryable* `WorkerShutdown` application
# failure and discards the adapter's own `CancelledError` payload, so US1 keeps
# the one relaunch the retry policy gives rather than removing it, and the
# archived transcript reaches the epic never: FR-002 no longer says the
# activity is "terminal on the server", "What this spec is not" states what the
# epic still records, and plan trap 18 carries the mechanism. US2 had two ways
# to land green and dead — nothing pinned the checkout root production supplies
# and nothing pinned that the boot path starts the watch at all — so FR-005 now
# requires the boot path to start and stop it, FR-006 names the second wrong
# root, US2-S7 proves both, and plan trap 16 names `factory_root()`. Also: the
# untracked round-3 triage document is cited by name rather than by anchor,
# plan trap 4 names the legacy unit this host actually runs and operator step 2
# reads its real stop timeout, plan trap 12 makes the bin directory and the
# entry-point source parameters, and a `# NOT IN SCOPE.` paragraph joins the two
# house subheads above. The four module-constant anchors the review asked to be
# rewritten in symbol-tier form are deliberately left coarse: that tier resolves
# `def`/`class` only (`factory/cli/nouns/spec.py:825` — `_symbol_spans`), so the
# rewrite it asked for would make the gate refuse them. State stays draft and
# the pre-dispatch hold above stands.
---

# Feature Specification: a worker restart does not orphan the work in flight

**Created**: 2026-08-23
**Depends on**: nothing.

## The gap, stated precisely

The worker's own module docstring states the contract this spec is asking for,
and three mechanisms each break it in a different place.

1. **The graceful path exists and nothing reaches it.**
   `factory/worker.py:37-43` says interrupting the process cancels in-flight
   activities and that `run_agent_attempt`'s cancellation path terminates the
   agent's process group, archives the transcript and classifies the attempt
   KILLED before it re-raises. That path is real:
   `factory/activities/agent_activities.py:562` is the `except
   asyncio.CancelledError` that raises the SDK `CancelledError` carrying
   `Termination.KILLED` and the archived transcript directory.
2. **`main` installs no signal handler, so the supervisor's stop signal never
   reaches it.** `factory/worker.py:333` — `main` connects at
   `factory/worker.py:342` and awaits `build_worker(client).run()` at
   `factory/worker.py:350`; the entry point at `factory/worker.py:360` is a
   bare `asyncio.run(main())`. Python's default disposition for SIGTERM ends
   the process immediately, so `Worker.shutdown()` is never called and step 1's
   cancellation path never runs.
3. **SIGTERM is exactly how this factory is stopped, and the platform already
   pays for a drain that does not happen.** The unit text this repository
   generates sets `KillMode=control-group` and `KillSignal=SIGTERM`
   (`factory/supervision/units.py:599-600`) and renders `TimeoutStopSec`
   (`factory/supervision/units.py:601`) from `stop_timeout_s`, which the worker
   unit sets to 120 s at `factory/supervision/units.py:642` with the comment
   "The drain the whole spec is about". The supervisor waits two minutes for a
   drain the process never performs.
4. **So the attempt's ending is invented rather than observed.** The activity
   stays started until its heartbeat timeout —
   `factory/workgraph/workflow.py:490` — `_agent_heartbeat_timeout`, bounded by
   `_AGENT_HEARTBEAT_TIMEOUT_CEILING` at `factory/workgraph/workflow.py:487`.
   That bound is 082-US5's and it closed the 7,200 s window the original
   incident measured; what it did not close is that
   `factory/workgraph/workflow.py:2475` — `_attempt_timeout` then records
   `Termination.TIMEOUT` with an empty transcript path, saying so in its own
   comment: "the worker died before the adapter could archive one". The
   evidence the adapter would have archived is lost because it was never asked
   for.
5. **A factory-code landing under a running worker wedges the next workflow
   task, and nothing in the process notices.** `_WORKER_REVISION` is captured
   once when the module is imported (`factory/worker.py:240`, from
   `factory/worker.py:220` — `_worker_revision`) and nothing re-reads it. The
   workflow sandbox re-imports workflow modules from disk while activity
   modules stay passthrough from the stale process, so the next activation
   fails on an `ImportError` and retries forever — measured 2026-08-13, a
   20:34Z landing wedging the 01:15Z activation until a hand-typed restart. The
   one automatic notice is out of band and acts on nothing:
   `factory/doctor/probes.py:322` — `StaleWorkerProbe` reports
   `ops/stale-worker` at CRITICAL (`factory/doctor/probes.py:362-365`), from
   the doctor's timer, to a report an operator has to read.
6. **The boot sync deletes the operator's CLI and no later sync restores it.**
   The wrapper this repository generates
   (`factory/supervision/units.py:746` — `_wrapper_text`) runs no sync at all,
   but the supervised host's own run script runs `uv sync --locked` and then
   execs `python3 -m factory.worker` from the same venv. On 2026-08-19 that
   removed `.venv/bin/ergane` while the installed distribution's metadata kept
   listing it, so every later sync reports that it would make no changes. The
   entry point that names the missing script is declared at `pyproject.toml:36`
   and nothing in this repository ever looks at whether it is on disk.

## The rule this spec is asking for

**A restart is a routine event: the worker ends its in-flight attempt itself
before it exits, notices when the code underneath it has moved, and never
leaves the host without the CLI it just synced.**

The middle clause is the one whose inputs combine, so it is stated completely:

| revision on disk moved | a moved commit touched `factory/` | an attempt is in flight | what the worker does |
| --- | --- | --- | --- |
| no | — | — | nothing, and says nothing |
| yes | no | — | nothing, and says nothing |
| yes | yes | yes | reports the skew once, naming both revisions, keeps working, and defers the exit until no attempt is in flight — at which point it takes it |
| yes | yes | no | reports it once and exits non-zero through the drain, so supervision restarts it on the new code |
| revision unreadable | — | — | nothing, and says nothing — a packaged install is not a skew |

### What this spec is not

It is not a change to the heartbeat bound. `_AGENT_HEARTBEAT_TIMEOUT_FLOOR` and
`_AGENT_HEARTBEAT_TIMEOUT_CEILING` at
`factory/workgraph/workflow.py:486-487` are 082-US5's and stay exactly as they
are, as does `_AGENT_RETRIES` at `factory/workgraph/workflow.py:367`.

It is not the schedule-to-start bound and it is not the status line. An
activity no worker ever accepts, and a `build status` that cannot tell
SCHEDULED from STARTED, are the surviving half of
`hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout`.
The backlog item `a-worker-restart-does-not-leave-a-node-reading-running`, in
the operator's round-3 web triage document, declares that key, but it is a
backlog entry and not a spec — and that document is untracked at 602a92c, which
is why it is named here rather than anchored: no directory under `specs/` owns
the key.
This spec declares it nowhere, which leaves it open and unowned on purpose
rather than quietly closed under a spec that never touched it.

It is not a guard over every activity the drain cancels. `Worker.shutdown()`
cancels everything the worker holds, not only `run_agent_attempt`: a gate suite
(`run_gates`), the merge-queue landing activities and the roadmap's are
cancelled with it, and FR-008 deliberately guards only the agent attempt. Those
others are re-scheduled by `_RETRIES` (`factory/workgraph/workflow.py:356`,
three attempts) on the worker that comes back, at a cost of seconds; an agent
attempt cancelled mid-story costs hours of model time and cannot be resumed.
Widening FR-008's guard to every activity would mean a floor that lands work
continuously never restarts at all — see plan trap 17.

It is not a change to `EpicWorkflow`, and this is the accepted cost worth
stating rather than discovering. The drain makes the adapter's KILLED
classification and its archived transcript exist *on disk*; neither reaches the
workflow, because the SDK discards the payload of a graceful-shutdown
cancellation and reports its own retryable `WorkerShutdown` failure in its place
(plan trap 18). So a restart still costs the epic one relaunch under
`_AGENT_RETRIES`, and if that relaunch is cancelled too the node still records
`Termination.TIMEOUT` with an empty transcript path — what changes is that the
attempt ends at once instead of at the heartbeat bound, and that the evidence
exists to be read. Teaching the epic to find it is a separate story, and no
requirement here permits editing `factory/workgraph/workflow.py`.

It is not a second detector. `StaleWorkerProbe` keeps its finding key, its
severity and its text; this spec makes the worker act on its own skew, out of
its own process. It is not `factory/supervision/engine_identity.py:57` —
`engine_skew` either: that one compares a container engine's image version
against the CLI's and refuses at dispatch, and this spec neither reads it nor
changes it.

It is not a change to the supervised host. Restarting the live worker, landing
factory code under it, deleting `.venv/bin/ergane` and making a venv bin
read-only are the four host mutations this spec's mechanisms are measured by,
and every one of them belongs to the operator's sequence in `plan.md`. No node
performs them: a node is an attempt running inside the very unit
`KillMode=control-group` (`factory/supervision/units.py:599`) would take down.

## User Scenarios & Testing

### User Story 1 - A restart does not orphan the in-flight activity (Priority: P1)

As the worker that owns the agent activity, when my supervisor stops me while
an attempt is running, I end that attempt myself — process group dead,
transcript archived, the activity reported at once — instead of dying and
leaving it started until a heartbeat expires.

**Why this priority**: P1, and the other two stories land on the seam it
creates. It is also the story that makes the platform honest: the unit text
already waits 120 s for a drain, and today nothing drains.

**Independent Test**: invoke the handler the boot path registers for SIGTERM,
against a worker built from the production registration with a fake attempt in
flight, and read whether the SDK's shutdown ran and that attempt's task
completed before the boot path returned. The signal itself is raised only at a
worker in a process of its own, never at the test runner.

**Acceptance Scenarios**:

1. **Given** the boot path at `factory/worker.py:333` — `main` driven against a
   fake worker exposing `run()` and `shutdown()`, **When** the handler it
   registers for the signal its unit declares in `KillSignal=SIGTERM`
   (`factory/supervision/units.py:600`), and the one it registers for SIGINT,
   are each invoked, **Then** each initiates that worker's own `shutdown()`
   rather than ending the process or cancelling the `run()` task — proven by a
   committed test that hands the handler-installing function the boot path calls
   a recording loop double, takes the callback it was handed for each signal,
   invokes it, and asserts `shutdown()` was awaited and `run()` returned of its
   own accord. The
   test raises no real signal at the pytest process and reads back no private
   loop attribute (plan trap 14): with no handler installed yet, the default
   disposition would end the suite instead of failing it, and
   `add_signal_handler` exposes no supported read-back.
2. **Given** a fake worker whose `shutdown()` completes only after a recorded
   in-flight attempt task has finished, and
   `factory/activities/agent_activities.py:482` — `run_agent_attempt` driven
   against a fake adapter that records the cancellation it is handed, **When**
   the drain the handler starts runs to its end, **Then** the boot path returns
   only after that attempt task completed, and the cancelled attempt raised the
   `CancelledError` built at `factory/activities/agent_activities.py:562`,
   carrying `Termination.KILLED` and a transcript path — proven by one
   committed test asserting the completion order and one asserting the carried
   result. Ending the process group and archiving the evidence are the
   adapter's own, as the docstring at
   `factory/activities/agent_activities.py:493-494` states; a fake adapter
   performs neither, so those two are the operator's step 1 rather than this
   criterion's.
3. **Given** a fake worker with nothing in flight, **When** the handler runs the
   drain, **Then** the drain's wait returns because the shutdown completed and
   not because its bound elapsed — the recorded reason says which — and the
   registration the boot path performs is the one
   `factory/worker.py:268` — `build_worker` performs today, proven by committed
   tests asserting both. The empty case is the common case: most restarts
   happen on an idle floor and must stay as fast as they are today.
4. **Given** the drain bound this story introduces and the `stop_timeout_s`
   the worker unit sets (`factory/supervision/units.py:642`), **When** a
   committed test reads both, **Then** it asserts the drain bound is the
   smaller of the two, so a drain can never be still archiving when the
   supervisor's stop timeout ends the process group.

---

### User Story 2 - A self-landing does not stale the running worker (Priority: P1)

As the worker whose own code just changed underneath it, I notice, say so once,
and take myself down for a restart when I can do it without killing an
attempt — rather than failing every subsequent workflow task on an
`ImportError` until an operator types `systemctl --user restart`.

**Why this priority**: P1. Measured 2026-08-13: a landing at 20:34Z wedged the
next activation at 01:15Z, five hours later, and only a hand-typed restart
cleared it. Self-hosting makes it recur on every factory-code landing.

**Independent Test**: drive the skew watch against a throwaway checkout whose
HEAD has moved past the imported revision, once with `factory/` touched and once
without, and read what the worker reported and whether it asked for a restart;
then drive the boot path itself and read whether it started that watch at all,
and with which root.

**Acceptance Scenarios**:

1. **Given** a running worker whose imported revision is behind the checkout's
   HEAD and at least one commit between them touched `factory/`, and no agent
   attempt in flight, **When** the skew watch ticks, **Then** the worker
   reports the skew once, naming both revisions, and exits non-zero through
   US1's drain — proven by a committed test asserting both the report and the
   non-zero exit path, since a zero exit under `Restart=on-failure`
   (`factory/supervision/units.py:603`) would leave the floor down.
2. **Given** a worker whose imported revision equals the checkout's HEAD,
   **When** the watch ticks repeatedly, **Then** it reports nothing and
   requests no exit — proven by a committed test asserting an empty log and an
   untouched worker. A notice that fires permanently is the defect class
   `operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install`
   names, and this spec must not manufacture it.
3. **Given** a HEAD that has moved but whose commits touch no file under
   `factory/` — a spec-markdown-only landing — **When** the watch ticks,
   **Then** it reports nothing and requests no exit, proven by a committed
   test driven against a real throwaway checkout rather than a stubbed git, so
   the pathspec is exercised from the root the worker actually runs from. The
   question is "did the landing change a module this process imported", never
   "did a landing happen".
4. **Given** skew that does touch `factory/` **and** two agent attempts in
   flight at once — which `factory/worker.py:268` — `build_worker` permits,
   registering no limit on concurrent activities — **When** the watch ticks,
   one of the two attempts then completes, and the watch ticks again, **Then**
   neither attempt is cancelled, no exit is requested on either tick, and the
   report is emitted exactly once across both — proven by a committed test
   driving the in-flight count from two to one. "In flight" means more than
   zero, never exactly one: a count that the first attempt to finish resets to
   zero fires FR-007's exit into a live attempt, which is the harm this
   scenario exists to forbid.
5. **Given** a worker whose revision cannot be read at all — an unpacked or
   packaged install, where `factory/worker.py:220` — `_worker_revision`
   returns `None` — **When** the watch ticks, **Then** it reports nothing,
   requests no exit and writes nothing, proven by a committed test, so the
   packaged case stays silent instead of reproducing
   `factory/cli/nouns/build.py:986` — `_skew_notice`'s permanent warning.
6. **Given** actionable skew already reported on an earlier tick while an
   attempt was in flight, **When** the last such attempt completes and the
   watch ticks again, **Then** the worker requests the non-zero exit through
   US1's drain on that tick and does not repeat the report — proven by a
   committed test driving the in-flight count from one to zero across
   consecutive ticks and asserting exactly one report and exactly one exit
   request. A worker that reports once and then never exits satisfies US2-S1
   through US2-S5 in full and leaves the wedge of FR-007 in place for the whole
   of a multi-hour attempt, which is the common self-hosting case.
7. **Given** the boot path at `factory/worker.py:333` — `main` driven against
   the same fake worker exposing `run()` and `shutdown()`, with the process's
   working directory set to a throwaway checkout and the watch's construction
   recorded, **When** `main` runs to its return, **Then** the watch was started
   before the `run()` await at `factory/worker.py:350` and cancelled after that
   await returned, **and** the checkout root it was constructed with is that
   working directory — neither the package directory
   `factory/worker.py:220` — `_worker_revision` runs git in, nor the runtime
   state directory `factory/activities/agent_activities.py:188` — `factory_root`
   returns — proven by one committed test asserting the start-and-cancel order
   and one asserting the recorded root. These are the two remaining ways US2
   lands green and dead: a watch nothing wires, and a watch handed a root whose
   `git log <rev>..HEAD -- factory/` matches nothing (plan trap 16). Either
   passes US2-S1 through US2-S6 in full, because each of those supplies its own
   root and calls the watch itself.

---

### User Story 3 - Restarting the worker does not delete the operator CLI (Priority: P2)

As the operator whose tools live in the venv the worker boots from, when the
worker starts I still have a CLI afterwards — or, if it cannot be put back, the
journal says which path is missing and why, and the factory keeps running.

**Why this priority**: P2. The worker is unaffected — it runs
`python3 -m factory.worker` — so nothing stops; what breaks is every operator
surface, and it does not self-heal, because `uv sync` reconciles against
`uv.lock` rather than against the filesystem.

**Independent Test**: point the boot check at a temporary bin directory with
the script deleted, and read whether it came back and what was logged; then at
a read-only one, and read whether the boot went on to its connect.

**Acceptance Scenarios**:

1. **Given** an installation whose distribution metadata declares the console
   script `ergane` (`pyproject.toml:36`) and a writable bin directory that does
   not contain it, **When** the worker boots, **Then** the script is written
   back from the declared entry point, is executable, and one line says so —
   proven by a committed test that builds that state in a temporary directory
   and asserts the file's presence, its mode and its content.
2. **Given** an installation whose declared console scripts are all present,
   **When** the worker boots, **Then** nothing is written and nothing is
   logged — proven by a committed test asserting the file's bytes and
   modification time are unchanged and the log is empty. A repair that rewrites
   on every boot is a bin directory that churns on every restart.
3. **Given** a bin directory that cannot be written, **When** the worker boots,
   **Then** it reports at ERROR naming the missing path and the entry point
   that declares it, and the boot still reaches its connect at
   `factory/worker.py:342` — proven by a committed test with a patched client
   asserting the connect was attempted after the ERROR line. A boot that exits
   non-zero here burns `StartLimitBurst`
   (`factory/supervision/units.py:588`) in under a minute and stops the unit,
   trading a missing CLI for a stopped factory.
4. **Given** an installation whose metadata declares no console script at all,
   **When** the worker boots, **Then** the check writes nothing, reports
   nothing and raises nothing — proven by a committed test. A container image
   that ships no console script is not a defect.

## Functional Requirements

- **FR-001**: The worker process MUST install handlers for SIGTERM and SIGINT
  that initiate the SDK's own worker shutdown, rather than leaving either
  signal to Python's default disposition.
- **FR-002**: The shutdown MUST let an in-flight `run_agent_attempt` reach the
  cancellation path at `factory/activities/agent_activities.py:562` before the
  process exits, so the adapter reaps the process group and archives the
  transcript rather than anybody reconstructing them, and so the activity is
  reported the moment the worker stops instead of idling until its heartbeat
  bound. It does not make the activity terminal: the SDK reports a
  graceful-shutdown cancellation as a *retryable* `WorkerShutdown` failure, so
  the one relaunch `_AGENT_RETRIES` (`factory/workgraph/workflow.py:367`)
  permits is the expected sequel, not a regression (plan trap 18).
- **FR-003**: The drain MUST be bounded, and that bound MUST be smaller than
  the `stop_timeout_s` the worker unit declares
  (`factory/supervision/units.py:642`); a committed test MUST assert the
  relation rather than leaving two numbers to agree by luck.
- **FR-004**: A worker with nothing in flight MUST complete its shutdown
  without waiting on the drain bound, and MUST record which of the two ended
  the wait; an unsignalled worker's construction and polling MUST be what
  `build_worker` performs today.
- **FR-005**: While the worker runs, it MUST compare the revision it imported
  against the checkout's current HEAD at a bounded cadence, and MUST do nothing
  and say nothing when the two are equal or when the revision cannot be read.
  The boot path MUST be what starts that comparison — beside the `run()` await
  at `factory/worker.py:350`, stopped when that await returns — so the watch is
  the running worker's, not a function only its own tests ever construct.
- **FR-006**: When the two differ, the worker MUST act only if at least one
  commit between them touched a file under `factory/`; a landing that touched
  no such file MUST produce no report and no exit. The comparison MUST be made
  against the checkout root the process runs from — neither the directory the
  worker's own module sits in nor the runtime state directory
  `factory/activities/agent_activities.py:188` — `factory_root` returns.
- **FR-007**: On actionable skew the worker MUST report it exactly once, naming
  both revisions, and MUST request an exit with a non-zero status through the
  drain of FR-002, so a supervisor configured `Restart=on-failure` brings it
  back on the new code with no operator action.
- **FR-008**: The worker MUST NOT cancel or interrupt an in-flight agent
  attempt to take that restart; the exit MUST wait until the number of agent
  attempts in flight is zero — more than one may be in flight, since the
  registration declares no limit on concurrent activities — and MUST then be
  taken on the first tick at which that number reaches zero, rather than being
  abandoned once the skew has been reported.
- **FR-009**: The skew report MUST NOT be emitted repeatedly for one skew, and
  MUST NOT be emitted at all when either revision is unavailable.
- **FR-010**: At boot the worker MUST check that every console script its own
  installation's distribution metadata declares is present in the bin directory
  of the interpreter running it, and MUST take no action when the metadata
  declares none.
- **FR-011**: When a declared console script is absent and the directory is
  writable, the worker MUST write it back from the declared entry point, make
  it executable, and record that it did so once.
- **FR-012**: When a declared console script is absent and cannot be written,
  the worker MUST report at ERROR naming the path and the entry point, and MUST
  continue starting; it MUST NOT exit non-zero and MUST NOT raise.
- **FR-013**: When every declared console script is present, the check MUST
  write nothing and log nothing.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-010, FR-011, FR-012, FR-013]
  persona: opus-closer
```

All three stories edit `main` in `factory/worker.py`, so the graph is a chain of
`depends_on_merged` edges declared by the author rather than inferred by the
contention detector (069-US2 FR-007). The first edge is a real dependency and
not only a file collision: FR-007's exit is FR-002's drain, and a US2 that
landed first would have to invent a second way out of the process. The second
edge is contention alone — US3's boot check shares nothing with the skew watch
but the function it is called from — and it is declared rather than raced
because whichever of the two landed second would otherwise be rejected for the
other's change. Nothing else is shared: US1 touches `factory/worker.py` only,
US2 adds `factory/activities/agent_activities.py`, US3 adds nothing.
