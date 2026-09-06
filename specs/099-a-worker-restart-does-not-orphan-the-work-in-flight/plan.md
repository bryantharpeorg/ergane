# Implementation Plan: a worker restart does not orphan the work in flight

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The boot path is eighteen lines and has no signal handling in it.**
`factory/worker.py:333` — `main` is the whole of the process's control flow, and
`factory/worker.py:360` is the entry point that runs it:

```python
async def main() -> None:
    """Connect, register, and poll `workgraph` until interrupted."""
    # ... four-line 048-US4 comment on the environment winning, elided
    target = resolve_temporal_target()
    address, namespace = target.address, target.namespace

    client = await Client.connect(address, namespace=namespace)
    logger.info(
        "worker polling '%s' at %s (namespace '%s') with %d activities",
        # ... four arguments, elided
    )
    await build_worker(client).run()


if __name__ == "__main__":  # pragma: no cover - process entry point
    # ... five-line 064-US1 comment on why not `logging.basicConfig`, elided
    configure_logging(level=logging.INFO)
    asyncio.run(main())
```

`Client.connect` is `factory/worker.py:342`, the `run()` is
`factory/worker.py:350`, and `configure_logging` is `factory/worker.py:359`.
There is no `try`, no `finally`, no `loop.add_signal_handler` anywhere in this
module or in anything it imports on the worker path. The only
`add_signal_handler` in `factory/` is
`factory/supervision/container_supervisor.py:491`, in the container supervisor,
which is a different process. Grep for it with the dot escaped: an unescaped
`signal.signal` also matches `send_signal(signal.` at
`factory/supervision/container_supervisor.py:326` and `handle.signal(signal_` at
`factory/cli/nouns/build.py:1498` and `factory/cli/nouns/build.py:1518`, none of
which is a handler.

**The worker already declares the contract this spec is asking for.**
`factory/worker.py:37-43` is the docstring paragraph that says a restart "loses
the epic's *progress*, never its work", because `run_agent_attempt`'s
cancellation path "terminates the agent's process group, archives the transcript
and classifies the attempt KILLED before it re-raises (constitution VI)". That
is true of Ctrl-C, which arrives as `KeyboardInterrupt` and cancels the task
`asyncio.run` is running. It is false of SIGTERM, which is what stops this
process in production.

**The cancellation path it names is real, and it is the thing to reach.**
`factory/activities/agent_activities.py:482` — `run_agent_attempt` ends with:

```python
    except asyncio.CancelledError:
        raise CancelledError(
            f"attempt {context.attempt} of {context.epic_id}/{context.node_id} "
            "was cancelled; the agent's process group is dead and its evidence "
            "is archived",
            AdapterResult(
                termination=Termination.KILLED,
                transcript_path=str(...),
            ),
        ) from None
```

That block is `factory/activities/agent_activities.py:562`. It runs only if the
SDK delivers a cancellation, which happens on `Worker.shutdown()` and on nothing
else this process ever performs.

**The SDK's own contract for the drain** (temporalio 1.31.0, the pinned
dependency): `Worker.run()` "will not return until shutdown is complete. This
means that activities have all completed after being told to cancel after the
graceful timeout period", and `Worker.shutdown()` "will not return until the
worker has completed shutting down"; its docstring adds that cancelling `run()`
instead "could also cancel the shutdown process. Therefore users are encouraged
to use explicit shutdown". `graceful_shutdown_timeout` defaults to
`timedelta(0)` — activities are told to cancel immediately, and the wait is for
them to finish, which is exactly what this spec wants.
`factory/worker.py:268` — `build_worker` is where the construction lives and
where 082's refusals are already raised, "in the unit's journal at boot, rather
than by polling a version no epic routes to".

**The unit text this repository generates, and the drain it already pays for.**
`factory/supervision/units.py:559` — `_service_text` renders every service body;
`factory/supervision/units.py:599-601` is the kill block:

```
KillMode=control-group
KillSignal=SIGTERM
TimeoutStopSec={stop_timeout_s}
```

and `factory/supervision/units.py:603-604` is `Restart={restart}` /
`RestartSec=10`. `factory/supervision/units.py:611` — `_worker_template_text`
fills those in for the worker with `restart="on-failure"`
(`factory/supervision/units.py:639`) and `stop_timeout_s=120`
(`factory/supervision/units.py:642`), whose comment reads: "The drain the whole
spec is about: stopping an instance must give the attempts pinned to it the same
120s the legacy unit gives its own." The start limit that governs a boot loop is
`factory/supervision/units.py:587-588` — 300 s and five starts, from
`factory/supervision/units.py:222-223`.

The wrapper every unit execs, `factory/supervision/units.py:746` —
`_wrapper_text`, runs no `uv sync`: it composes `PATH`, evaluates the operator's
environment command, and `exec`s the interpreter on the module. The
`uv sync --locked` that deleted the console script belongs to the supervised
host's own run script, which lives in the operator's separate homelab checkout
and is not in this repository or in any node's worktree.

**The revision the worker knows about itself.** `factory/worker.py:220` —
`_worker_revision` shells `git rev-parse --short HEAD` against the package
directory and returns `None` when the tree is not a checkout;
`factory/worker.py:240` captures it once, at import, into `_WORKER_REVISION`;
`factory/worker.py:299` — `_WorkerRevisionInterceptor` carries that value into
every `EpicWorkflow` input, and `factory/worker.py:243` —
`_deployment_registration` feeds it to 082's versioning. Nothing re-reads it,
ever.

**The skew surfaces that already exist, and must not be rebuilt — two that are this, and one that is not.**
`factory/doctor/probes.py:322` — `StaleWorkerProbe` compares the worker
process's start time against the newest commit touching `factory/`;
`factory/doctor/probes.py:345` — `evaluate` returns `ops/no-worker-running` at
INFO when no worker is running and builds the CRITICAL `ops/stale-worker` report
at `factory/doctor/probes.py:362-365`. Its helper
`factory/doctor/probes.py:161` — `_newest_factory_commit` is the git shape US2
copies, and trap 16 is the cwd that shape depends on.
`factory/cli/nouns/build.py:986` — `_skew_notice` is the CLI-side comparison,
and the source of the permanent-warning defect class. A third surface answers to
the same word and is not this: `factory/supervision/engine_identity.py:57` —
`engine_skew` compares a running container engine's *image version* against the
CLI's version and returns a refusal sentence, enforced as a dispatch-time
preflight by 105-US3. It measures versions, not git revisions, and it acts
before an epic starts rather than while a worker runs, so it fixes nothing US2
is about. An implementer searching this tree for "skew" will find it first;
copying its vocabulary or its refusal sentence into the worker's watch would
produce a check that fires on a packaged install and never on the self-landing
this story is measured by.

**The heartbeat bound that closed the original mechanism.**
`factory/workgraph/workflow.py:486-487` are the floor and the ceiling, the
latter `timedelta(seconds=120)`; `factory/workgraph/workflow.py:490` —
`_agent_heartbeat_timeout` is `max(min(timeout_s / 2, ceiling), floor)` and is
wired at `factory/workgraph/workflow.py:2443`, inside the
`workflow.start_activity` call at `factory/workgraph/workflow.py:2429-2445` in
`factory/workgraph/workflow.py:2392` — `_attempt`. `_AGENT_RETRIES` at
`factory/workgraph/workflow.py:367` is one relaunch and no more. When the
heartbeat expires, `factory/workgraph/workflow.py:2475` — `_attempt_timeout`
records `Termination.TIMEOUT` and, in its own words, no transcript, "because the
worker died before the adapter could archive one". The scheduler park that the
original ledger row blamed is the `wait_condition` at
`factory/workgraph/workflow.py:1137` — the row's own ref,
`factory/workgraph/workflow.py:1138`, is the predicate one line below it. With a
120 s ceiling that park is correct as written and this spec does not touch it.

**The console script's declaration.** `pyproject.toml:36` is
`ergane = "factory.cli.main:main"`. The installed distribution carries the same
declaration in its metadata — that is what made the 2026-08-19 defect
unrecoverable, since `.venv/lib/.../ergane_cli-0.1.0.dist-info/RECORD` still
listed `../../../bin/ergane` after the file was gone, so `uv sync --locked`
reported that it would make no changes. Read the row's REMEDY as three parts and
notice which are already discharged: the 056 rename residue it names as the
likely cause has since been cleaned from this venv — `site-packages` now holds
only `ergane_cli-0.5.0.dist-info` and `_editable_impl_ergane_cli.pth`, and
`.venv/bin/ergane` is present — and the lock names one distribution. So the
2026-08-19 trigger does not reproduce on this host today, and an implementer
cannot find the failing state; it is manufactured, by deleting the script
(operator step 5) or by building the state in a temporary directory (T021).
FR-010 to FR-013 are the third part, the standing boot-time assertion the row
asks for, which is why declaring the key is honest and why no test may wait for
the trigger to recur. `factory/supervision/deploy.py:486` —
`_sync` runs `uv sync --frozen` on the *deploy* path and
`factory/supervision/deploy.py:500` — `_start` enables the unit; neither runs on
the supervised host's ordinary boot, which is why US3 does not live there.

## Traps

**Trap 1 — the 7,200 s window in the ledger row is closed; re-deriving a clamp
is the predictable wrong answer.** The row
`hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout`
still leads with "heartbeatTimeout 7200s", and its 2026-09-03 correction says
so: 082-US5 landed `_AGENT_HEARTBEAT_TIMEOUT_CEILING = timedelta(seconds=120)`
at `factory/workgraph/workflow.py:487`, and every release since carries it. An
implementer who reads the row and not this plan will shorten the ceiling, or add
a `schedule_to_start_timeout` at
`factory/workgraph/workflow.py:2429-2445`. Both are out of scope: the first
breaks 082's measured bound, the second belongs to the backlog item
`a-worker-restart-does-not-leave-a-node-reading-running`, which declares that
key. FR-002 is about reaching the cancellation path, not about shortening a
timeout.

**Trap 2 — cancel the shutdown, not the `run()`.** The obvious implementation is
to let SIGTERM cancel the task `asyncio.run` is awaiting and catch
`CancelledError` around `factory/worker.py:350`. The SDK's own `run` docstring
warns against it: "a cancel could also cancel the shutdown process. Therefore
users are encouraged to use explicit shutdown instead." FR-001 and FR-002
require the handler to call `Worker.shutdown()` on the constructed worker and
let `run()` return by itself. A test that only asserts "the process exited"
passes for the wrong implementation, which is why US1-S2 asserts the
cancellation path completed.

**Trap 3 — the agent is dying at the same instant, and the drain does not save
it.** `KillMode=control-group` (`factory/supervision/units.py:599`) means
systemd signals every process in the unit's cgroup — the worker, the agent, its
`bwrap`, its gate subprocesses. The drain's value is not that the attempt
survives; it is that the attempt *ends properly*: process group reaped,
transcript archived on disk, the activity reported the moment the worker stops
rather than left started until a heartbeat expires. "Properly" is not
"terminally" — what the server records is trap 18's retryable `WorkerShutdown`
failure, and the epic still spends the one relaunch it spends today. An
implementer who tries to keep the agent alive across a restart — moving it out
of the cgroup, double forking, `setsid` — is reintroducing the orphans the
comment at `factory/supervision/units.py:596-598` says that setting exists to
prevent.

**Trap 4 — an unbounded drain is the same defect wearing a fix's hat.**
`TimeoutStopSec` is rendered at `factory/supervision/units.py:601` from
`stop_timeout_s=120` (`factory/supervision/units.py:642`). A drain with no bound
that is still archiving at 120 s is SIGKILLed by systemd mid-write, which
orphans the activity exactly as today and corrupts the archive as a bonus.
FR-003 requires the drain bound to be the smaller of the two and requires a
committed test to assert the relation, because two numbers in two files agreeing
today is not the same as them being unable to disagree.

Know which unit that relation is about, because on this host it is not the unit
the operator restarts. `factory/supervision/units.py:611` —
`_worker_template_text` renders that 120 s into the template unit
`ergane-worker@.service` (`factory/supervision/units.py:83`). What
`systemctl --user restart ergane-worker` stops is the legacy unit named at
`factory/supervision/units.py:76`, which `factory/supervision/units.py:137`
lists in `RETIRED_UNITS`: the hand-written homelab unit the ledger rows were
measured on, whose `TimeoutStopSec` this repository never writes and this plan
never read. So FR-003's relation is machine-checked against the template unit,
and the live host's own stop timeout is read once by operator step 2 before that
relation is trusted there. Do not "fix" this by making the check read a unit
file off the host: no node can see one.

**Trap 5 — a boot-time skew check compares a value with itself, and this plan
used to ask for one.** `_WORKER_REVISION` (`factory/worker.py:240`) is captured
when the module is imported, which on the boot path is microseconds before
`main` runs. Comparing it against `git rev-parse HEAD` at
`factory/worker.py:342` yields equality on every boot forever; the check passes
every test written against it and can never fire in production. FR-005 requires
the comparison to run *while the worker runs*, at a bounded cadence — a
background task started beside the `run()` await, cancelled when it returns.

**Trap 6 — do not import the doctor package into the worker process.**
`factory/doctor/probes.py:161` — `_newest_factory_commit` is the right git shape
to copy and the wrong thing to import: `factory/doctor/probes.py:25-26` pulls
`LiteLLMClient` and `factory.workgraph.cli` at module scope, so importing it
from `factory/worker.py` drags the proxy client and a CLI module into the
worker's import graph — and into the workflow sandbox's re-import path, which is
the very mechanism US2 exists to fix. Copy the four-line `git log` invocation;
do not import it.

**Trap 7 — `StaleWorkerProbe` is not to be rebuilt or edited.**
`factory/doctor/probes.py:322` — `StaleWorkerProbe` already detects this skew
from outside, with its
own finding key, its own severity and its own test coverage. US2 is the worker
acting on its own skew from inside its own process. An implementer who "unifies"
the two will change a finding key an operator's ledger already counts, for no
requirement in this spec.

**Trap 8 — never cancel a live attempt to take the restart, and the counter
that decides it has two wrong shapes that both pass the suite.** FR-008. The
tempting implementation calls the drain the moment skew is seen, which kills an
attempt that may be hours into a story. It buys nothing: the epic whose workflow
task is failing on the `ImportError` is already making no progress, and the
attempt that is running will complete and be reaped by the restarted worker. The
exit waits until the count of in-flight agent attempts is zero, and then it
happens (US2-S6) — a watch that reports once and never exits is FR-007 dead.

The count is not observable from the `Worker` object, so it comes from the
activity itself: a module-level integer in
`factory/activities/agent_activities.py`. Write it exactly this way, because
both plausible variants are green and dead.

*The increment is the FIRST statement inside the `try:` at
`factory/activities/agent_activities.py:499`* — above the `activity.info()` /
`derive_session_id` lines and above `adapter = adapter_for(DEFAULT_AGENT)` at
`factory/activities/agent_activities.py:521`. Placing it "just before the
adapter call" at `factory/activities/agent_activities.py:522` puts it *after*
`adapter_for`, whose `AdapterError` is caught by the `except AdapterError` at
`factory/activities/agent_activities.py:576`: that path runs the `finally`
having never incremented, the count reaches -1, it never reads zero again, and
FR-007's exit is permanently dead on any host that has ever failed a launch.

*The `finally` DECREMENTS; it never assigns zero.* `factory/worker.py:268` —
`build_worker` passes no limit on concurrent activities and
`max_concurrent_nodes` (`factory/workgraph/workflow.py:569`) is an operator dial
whose floor is 1, so two `run_agent_attempt` activities can be in one worker at
once. A `finally` that sets the count to zero lets the first attempt to finish
declare the floor idle, and FR-007's exit then fires into the second, live
attempt — the exact harm this trap exists to prevent. US2-S4 drives two
concurrent attempts for this reason; a test with one attempt cannot tell the two
implementations apart.

Put the `finally` on the `try:` that already opens at
`factory/activities/agent_activities.py:499`, so a cancelled attempt still
decrements. Do not add a second `except asyncio.CancelledError`: the one at
`factory/activities/agent_activities.py:562` stays the only handler in that
function. `factory/activities/agent_activities.py:526`, where an earlier draft
of this plan pointed, is a keyword argument four lines inside the call and
wrapping it wraps nothing.

**Trap 9 — a worker that exits zero does not come back.**
`factory/supervision/units.py:603` renders `Restart={restart}` and the worker
passes `restart="on-failure"` (`factory/supervision/units.py:639`). A clean
`sys.exit(0)` after a successful drain leaves the floor down until a human
notices. FR-007 requires a non-zero status. The counterpart hazard is trap 11:
non-zero is right for a *deliberate* skew exit and wrong for a boot-time
complaint.

**Trap 10 — a notice that fires forever is the defect class this must not
manufacture.** `factory/cli/nouns/build.py:986` — `_skew_notice` prints "worker
revision is unknown … the worker predates this check or is not a git checkout"
on every single call for a packaged install, which is the recommended install;
that is the open finding
`operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install`.
FR-005 and FR-009 make silence the healthy output: unreadable revision, equal
revisions, or a landing that touched nothing under `factory/` all produce no log
line at all. US2-S2, US2-S3 and US2-S5 are the three controls, and they are the
half of the story most likely to be skipped.

**Trap 11 — the console-script check must not be able to stop the factory.**
The previous draft required a non-zero exit on a non-writable venv. Under
`Restart=on-failure` with `StartLimitIntervalSec=300` / `StartLimitBurst=5`
(`factory/supervision/units.py:587-588`), five such exits inside five minutes —
`RestartSec=10` makes that fifty seconds — leave the unit stopped, and systemd
will not start it again without an operator. That trades a missing operator CLI
for a stopped factory, on a host where the CLI is exactly what an operator would
use to find out. FR-012: report at ERROR, naming the path and the entry point,
and continue starting.

**Trap 12 — read the entry point from the installed distribution, not from
`pyproject.toml`.** `pyproject.toml:36` declares it, but a wheel or
`uv tool install` has no `pyproject.toml` beside it, and the whole point of the
2026-08-19 defect is that the *installed metadata* still declared a script that
was not on disk. The check reads the console-script entry points of this
installation's own distribution and compares against the bin directory of the
interpreter that is running — `Path(sys.executable).parent` — so it repairs the
venv the worker actually booted from and never guesses at another. FR-010 and
FR-013 make "no console scripts declared" a silent, first-class case, because a
container image that ships none is not broken.

Both of those are *parameters*, and that is the seam US3's tests need. T021 and
T023 drive the check against a temporary bin directory and a read-only one,
which is only possible if the bin directory and the entry-point source are
arguments the caller supplies: production passes `Path(sys.executable).parent`
and the distribution resolved from the running package (the mapping
`importlib.metadata.packages_distributions()` returns for `factory`, or the
equivalent read of the distribution that provides this module); the tests pass a
`tmp_path` and a metadata double. Never a literal distribution name: the
distribution is `ergane-cli` (`pyproject.toml:2`) while the console script it
declares is `ergane` (`pyproject.toml:36`), and that split is the 056 rename the
ledger row names as its likely cause. A hardcoded name is that row's defect
class planted a second time.

**Trap 13 — the file that deletes the script is not in this repository, and
neither is `_sync`.** The supervised host's run script (`uv sync --locked`, then
`exec .venv/bin/python3 -m factory.worker`) lives in the operator's homelab
checkout: outside this repository, outside every node's worktree, and unreachable
by any diff this factory produces. `factory/supervision/deploy.py:486` — `_sync`
is a different sync on a different path (`uv sync --frozen`, deploy only) and the
legacy host never calls it. The worker's own boot is the only code this
repository owns that runs on that host immediately after the destructive sync,
which is why FR-010 puts the check there and why an implementer must not go
looking for the run script to edit.

**Trap 14 — tests never reach the live server, and never raise a real signal at
the test runner.** One Temporal serves this host and it holds the live floor;
the precedent is `factory/roadmap/schedule.py:247` — `_refuse_live_client`,
which exists because removing a sentinel check once created five schedules on
the operator's live namespace. US1's tests drive the signal wiring against a
constructed-but-not-connected worker or a fake with the same two methods, and
assert on what was called: they invoke the callback the boot path *registered*,
never `signal.raise_signal` and never `os.kill` aimed at the pytest process.
That is not a style preference. The red phase tasks.md mandates runs before any
handler exists, so a raised SIGTERM there meets Python's default disposition and
ends the suite at signal 143 instead of failing one test — and the whole gate
run with it. US1-S1 is written to match, so the diff that obeys this trap is the
diff that satisfies the criterion the judge scores.

That criterion is only satisfiable if the registration is a *seam*, and this is
the sentence an implementer needs: `loop.add_signal_handler` has no supported
read-back. `signal.getsignal(SIGTERM)` returns asyncio's own noop shim, not the
callback that was registered, and the real one lives in the private
`loop._signal_handlers[sig]._callback`, which is not an assertion surface and
will change under a Python upgrade. So make the registration a named function
taking the loop and the constructed worker — production passes the running loop,
the test passes a recording double and then invokes the callback it was handed.
The two wrong moves are reaching into `_signal_handlers` and switching to
`signal.signal`, which T005 rules out because it does not deliver into a running
event loop.

**Trap 15 — one test module per story, named for the property.** US1's is about
the drain, US2's about the skew watch, US3's about the console script. A single
`test_worker_boot.py` holding all three makes the three no-op controls (US1-S3,
US2-S2, US3-S2) look like one test instead of three, and it puts three stories'
diffs in one file the merge queue will serialise anyway.

**Trap 16 — the range query's pathspec is relative to cwd, and this tree's two
git helpers disagree about cwd.** `factory/worker.py:220` — `_worker_revision`
runs `git rev-parse --short HEAD` with `cwd=Path(__file__).resolve().parent`,
the *package* directory. `factory/doctor/probes.py:161` —
`_newest_factory_commit`, whose invocation shape US2 copies, passes no cwd at all
and relies on the process's own cwd being the checkout root — which it is,
because the supervised host's run script changes into the tree before exec'ing
the module and the generated unit sets `WorkingDirectory`
(`factory/supervision/units.py:593`). An implementer who mirrors
`_worker_revision`'s cwd for the range query runs `git log <rev>..HEAD --
factory/` with cwd `<root>/factory`, where the pathspec resolves to
`<root>/factory/factory/` and matches nothing: FR-006 then answers "no commit
touched `factory/`" for every landing forever, the watch never fires, and every
test written against an explicit fake checkout still passes. FR-006 therefore
requires the checkout root to be a parameter of the watch — supplied by `main`
in production and by the test's own temporary repository in the tests. A test
that passes a root while production passes the package directory is green and
dead, which is trap 5 wearing different clothes. US2-S7 is the criterion that
closes it: the recorded root `main` hands the watch must be the process's own
working directory.

There is a second wrong root, and it is the more seductive one because it is
already imported in the file T018 edits.
`factory/activities/agent_activities.py:188` — `factory_root` is called at
`factory/activities/agent_activities.py:498`, the line immediately above the
`try:` of trap 8, and it reads like the answer to "what is the root?". It is
not: it returns the *runtime state* directory — `.ergane/`, via
`factory/workgraph/worktree.py:191` — `resolve_factory_root` — so a range query
run there resolves the pathspec to `.ergane/factory/` and matches nothing, which
is trap 16 again with a different literal. What `main` must pass is the
process's own working directory, which the wrapper this repository generates
establishes with `cd "$root"` (`factory/supervision/units.py:802`) and which the
unit sets as `WorkingDirectory` (`factory/supervision/units.py:593`).

**Trap 17 — the drain cancels every activity the worker holds, and FR-008
guards only one of them.** `Worker.shutdown()` cancels the lot: `run_gates`, the
merge-queue landing activities (`enqueue_landing`, `poll_landing`), the
roadmap's — not only `run_agent_attempt`. Two consequences, and an implementer
must not act on the wrong one. First, that is why the exit is deliberately not
free: FR-007's exit fires on any operator pull that moves HEAD with a `factory/`
change, and it can land mid-gate or mid-landing. That is accepted, because those
activities carry `_RETRIES` (`factory/workgraph/workflow.py:356`, three
attempts) and are re-scheduled on the worker that comes back, costing seconds;
an agent attempt cancelled mid-story costs hours of model time and cannot be
resumed. Second — and this is the wrong move — do not "fix" the asymmetry by
widening FR-008's guard to count every in-flight activity. On a busy floor the
roadmap and the landing poller are almost never all idle, so a worker that waits
for that would never restart at all, which is the wedge FR-007 exists to end.
The counter of trap 8 counts `run_agent_attempt` and nothing else. Operator step
3 is where a mid-gate exit would first be seen; it is expected, not a failure.

**Trap 18 — the drain's evidence lands on disk and reaches the workflow never,
and the tempting "fix" is out of scope.** Read the pinned SDK before predicting
what the epic sees. `Worker.shutdown()` makes core issue a cancel with reason
`WorkerShutdown`; the Python worker turns that into a cancelled completion
(`cancelled_by_request` is `is_cancelled` **or** `is_worker_shutdown`); and
sdk-core then *rewrites* it — in the `Status::Cancelled` arm of its activity
completion handler it calls `fail_activity_task` with its own
`worker_shutdown_failure()`, a **retryable** `ApplicationFailure` of type
`WorkerShutdown`, with the comment "We report cancels for graceful shutdown as
failures, so we don't wait for the whole timeout to elapse". Three consequences.
First, the adapter's `CancelledError` payload — the `Termination.KILLED` and the
transcript path built at `factory/activities/agent_activities.py:562` — is
discarded on the way out and never reaches `EpicWorkflow`; the archive it names
is real, and only on disk. Second, the activity is *not* terminal, so
`_AGENT_RETRIES` (`factory/workgraph/workflow.py:367`, `maximum_attempts=2`)
still gives one relaunch: US1 does not remove today's automatic relaunch, it
makes it happen at once instead of after the heartbeat bound, and
`factory/workgraph/workflow.py:2464-2471` still routes an exhausted attempt to
`factory/workgraph/workflow.py:2475` — `_attempt_timeout` and its empty
transcript path. Third — the wrong move — do not "complete" US1 by teaching the
workflow to read the carried result, or by reaching for
`graceful_shutdown_timeout`, `non_retryable_error_types` or anything else in
`factory/workgraph/workflow.py`. No FR here permits editing that module, and
operator step 7's grep is the check. A test asserting the epic recorded KILLED
is asserting something the SDK forbids.

## Sizing

**US1** touches `factory/worker.py` and nothing else in production: a signal
handler installed inside `factory/worker.py:333` — `main`, the worker held in a
local so `shutdown()` can reach it, and a bounded wait around the `run()` at
`factory/worker.py:350`. Its tests are one new module. Under fifty production
lines; the pasted evidence is a run of that test module and a two-line rendering
of the drain bound beside `stop_timeout_s`, both short and both produced inside
the worktree.

**US2** touches `factory/worker.py` (the watch task, started and cancelled
around the same `run()`) and `factory/activities/agent_activities.py` (the
in-flight counter of trap 8: incremented as the first statement inside the
`try:` at `factory/activities/agent_activities.py:499` and decremented in a
`finally` on that same `try:`, never assigned zero). Its tests are one new module
with seven cases — the four rows of the spec's truth table, the
unreadable-revision row, the deferred exit of US2-S6, and the boot wiring of
US2-S7 — driven against a throwaway checkout built in `tmp_path` so trap 16's
pathspec is exercised for real, against a count driven from two to one to zero
so trap 8's two dead shapes are both caught, and once against `main` itself so
the root production supplies is the recorded one. Under eighty production
lines.

**US3** touches `factory/worker.py` only: one check called from `main` before
the connect at `factory/worker.py:342`, taking the bin directory and the
entry-point source as arguments — production supplies
`Path(sys.executable).parent` and this installation's own console-script
metadata, the tests supply a `tmp_path` and a double (trap 12) — so a temporary
and a read-only bin directory are drivable at all. Its tests are one new module
driving a temporary bin directory in four states. Under sixty production
lines.

All three name `factory/worker.py`; no two share any other production file, and
the Work Graph serialises them with declared `depends_on_merged` edges rather
than letting the contention detector infer them. Each story is far inside the
64 KiB deterministic diff bound (D-050), and each verification task asks for a
short pasted excerpt rather than a transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only,
so runtime evidence is committed as pasted output. Every step below is the
operator's own and no story task asks a node for any of it. Each one mutates the
live host — restarting the worker, landing factory code under it, deleting
`.venv/bin/ergane`, making a venv bin read-only — and a node is an attempt
running inside the very unit that `KillMode=control-group`
(`factory/supervision/units.py:599`) would take down with it, so a node obeying
step 1 would kill the agent writing the evidence. What the nodes paste is what
they can produce inside their own worktrees. On this host:

1. **Start an epic, let a node reach RUNNING, then
   `systemctl --user restart ergane-worker` and immediately
   `temporal workflow describe --workflow-id <epic>`.** Before US1 the pending
   activity stays `PENDING_ACTIVITY_STATE_STARTED` until its heartbeat timeout;
   after US1 it is reported at once and, by the time the new worker is polling,
   is either awaiting its relaunch or already running it — never
   STARTED-until-heartbeat. Expect the relaunch and read it as success: what the
   server receives is sdk-core's own retryable `WorkerShutdown` application
   failure, not the adapter's `CancelledError` (trap 18), so `_AGENT_RETRIES`
   (`factory/workgraph/workflow.py:367`, `maximum_attempts=2`) gives one
   relaunch exactly as it does today; what changes is that it comes at once
   instead of after the heartbeat bound. The reliable
   falsifier is the other half of the step: the node's transcript directory for
   that attempt is on disk and non-empty. That — the archive existing at all —
   is the falsifiable test of US1, because
   `factory/workgraph/workflow.py:2475` — `_attempt_timeout` cannot produce
   one.
2. **Read the live unit's stop timeout, then restart the worker with an idle
   floor and read `journalctl --user -u ergane-worker`.** Run
   `systemctl --user show -p TimeoutStopUSec ergane-worker` first: FR-003's
   machine-checked relation is against the 120 s this repository renders into
   its own template unit, and what this host runs is the hand-written legacy
   unit whose stop timeout this repository never sets (trap 4). The drain bound
   must be under whatever that command prints; if it is not, the number to move
   is the drain bound, not the requirement. Then the stop must be as fast as it
   is today. A stop that now takes seconds on an idle floor means the drain is
   waiting on something it should not.
3. **Land a factory-code change while the worker runs, with no attempt in
   flight, and watch the journal.** One skew line naming both revisions, then a
   non-zero exit, then systemd's restart ten seconds later, then the next
   workflow task succeeding on the new code. Then repeat with a
   spec-markdown-only landing and confirm the journal stays silent. If a gate
   run or a landing poll happened to be in flight, expect it to be cancelled and
   re-scheduled on the worker that comes back rather than lost — that is trap 17
   and it is the accepted cost of FR-008 guarding only the agent attempt.
4. **Land a factory-code change while an attempt is in flight.** The skew line
   appears once and the attempt keeps running to its own end; the exit happens
   after it, not during it. This is trap 8, run forwards, and it is the one
   step that cannot be replaced by a test.
5. **Delete `.venv/bin/ergane`, restart the worker, and run `command -v
   ergane`.** The script is back and the journal says it was restored. Restart a
   second time and confirm the journal is silent and the file's modification
   time did not move.
6. **Make the bin directory read-only, restart the worker, and read the
   journal.** One ERROR naming the path and the entry point — and the worker
   polling anyway. `systemctl --user status ergane-worker` must show it active,
   not a failed unit that has burned its start limit (trap 11).
7. **Grep the diff for `_AGENT_HEARTBEAT_TIMEOUT`, `_AGENT_RETRIES`,
   `schedule_to_start` and `factory/workgraph/workflow.py`.** All four must be
   absent. A diff that touches any of them is fixing a different defect, owned
   by a different spec (trap 1).
