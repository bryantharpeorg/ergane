# Implementation Plan: a worker restart does not leave a node reading RUNNING

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The call site is eleven lines and names four options.**
`factory/workgraph/workflow.py:2392` — `EpicWorkflow._attempt` holds the whole of
US1's production change:

```python
        record.state = NodeState.RUNNING
        agent = workflow.start_activity(
            run_agent_attempt,
            context,
            activity_id=context.node_id,
            start_to_close_timeout=timedelta(
                seconds=context.timeout_s + _ADAPTER_GRACE_S
            ),
            heartbeat_timeout=_agent_heartbeat_timeout(context.timeout_s),
            retry_policy=_AGENT_RETRIES,
        )
```

The state assignment is `factory/workgraph/workflow.py:2428` —
`EpicWorkflow._attempt` and the four options are at
`factory/workgraph/workflow.py:2439`, `factory/workgraph/workflow.py:2440`,
`factory/workgraph/workflow.py:2443` and `factory/workgraph/workflow.py:2444`,
all inside `EpicWorkflow._attempt`. `schedule_to_start_timeout` is a real keyword
on `workflow.start_activity` in the pinned SDK — it sits between
`schedule_to_close_timeout` and `start_to_close_timeout` in every overload — and
this repository has never passed it: `grep -rn "schedule_to_start\|schedule_to_close"
factory/` returns nothing and `git log --all -S"schedule_to_start_timeout"`
returns no commit. FR-001.

**The bound that already exists, and must not move.**
`factory/workgraph/workflow.py:487` sets `_AGENT_HEARTBEAT_TIMEOUT_CEILING` to
120 seconds and `factory/workgraph/workflow.py:490` — `_agent_heartbeat_timeout`
derives each attempt's heartbeat bound as half its deadline inside that ceiling
and the floor above it. Its docstring says in the tree's own words that
`start_to_close_timeout` and `_AGENT_RETRIES` "are deliberately untouched: only
the liveness bound moves". The new constant belongs beside it and is derived from
nothing. FR-002, FR-003.

**The classification seam, which today has one branch too few.**
`factory/workgraph/workflow.py:2462` — `EpicWorkflow._attempt` is the try, and
five lines is the whole of it:

```python
        try:
            result = await agent
        except ActivityError as exc:
            cause = exc.cause
            if (
                isinstance(cause, ApplicationError)
                and cause.type == AGENT_LAUNCH_FAILED
            ):
                raise _LaunchFailed(cause.message) from exc
            return self._attempt_timeout(record, exc)
```

`factory/workgraph/workflow.py:2475` — `EpicWorkflow._attempt_timeout` is the
only consumer of that fall-through (`factory/workgraph/workflow.py:2471` —
`EpicWorkflow._attempt` is its one call site), it reads the cause at
`factory/workgraph/workflow.py:2491` — `EpicWorkflow._attempt_timeout`, and it
returns `AdapterResult(termination=Termination.TIMEOUT, ...)` at
`factory/workgraph/workflow.py:2506` — `EpicWorkflow._attempt_timeout` whatever
the timeout was. The discriminator it needs already exists on the exception the
SDK raises: `TimeoutError` carries a `type` property whose `TimeoutType` values
are `START_TO_CLOSE`, `SCHEDULE_TO_START`, `SCHEDULE_TO_CLOSE` and `HEARTBEAT`,
and the class is imported into this module under an alias at
`factory/workgraph/workflow.py:116`. FR-004, FR-005.

**THE ACTIVITY RETRIES ONCE, SO THE NEW BOUND NORMALLY ARMS ON A RETRY WHOSE
PREDECESSOR RAN.** `factory/workgraph/workflow.py:367` is `_AGENT_RETRIES` and
`factory/workgraph/workflow.py:369` is its `maximum_attempts=2`. A heartbeat
timeout is retryable, so the sequence this spec exists for — a worker dies
mid-attempt and stays away — does not leave attempt 1 pending: the 120-second
ceiling fires, the server re-schedules, and attempt 2 is what nobody accepts.
The pinned SDK's comment on `schedule_to_start_timeout` says which attempt the
bound measures — the "schedule" time is when the most recent retry is scheduled
— and the failure that expiry produces carries the heartbeat payload Temporal
retained from the attempt that did run, reachable either on the
`SCHEDULE_TO_START` `TimeoutError`'s own `last_heartbeat_details` or on a
`TimeoutError` in its cause chain (`TemporalError.cause` is Python's
`__cause__`, and the SDK's failure converter rebuilds nested causes on the way
in). `factory/workgraph/workflow.py:2492` — `EpicWorkflow._attempt_timeout`
already reads exactly that list for the heartbeat case, and
`factory/workgraph/workflow.py:2498` — `EpicWorkflow._attempt_timeout` already
turns it into the `UsageSnapshot` FR-015 keeps. FR-015, US1-S7, trap 19.

**The machinery a no-agent-started ending should reuse, all of it landed.**
`factory/workgraph/workflow.py:737` — `_LaunchFailed` is the workflow-internal
signal, and its docstring already states the contract this story needs: "a
pre-first-token launch fault: the agent never started". Its handler is
`factory/workgraph/workflow.py:2222` — `EpicWorkflow._run_node`, which increments
`record.launch_failures`, appends an `AttemptEvidence` rather than an
`AttemptRecord` at `factory/workgraph/workflow.py:2228` —
`EpicWorkflow._run_node`, and ends the node once the count reaches
`factory/workgraph/workflow.py:2233` — `EpicWorkflow._run_node`, reading
`max_launch_retries` from `factory/verify/models.py:1205` —
`VerificationConfig`, whose default is 2. The two strings that need to stop being
hardcoded are the terminal reason at `factory/workgraph/workflow.py:2235` —
`EpicWorkflow._run_node` and the escalation summary at
`factory/workgraph/workflow.py:2243` — `EpicWorkflow._run_node`. FR-006.

**`_attempt` HAS TWO CALLERS, and only one of them catches anything.**
`grep -n "self\._attempt(" factory/workgraph/workflow.py` returns exactly two
lines: `factory/workgraph/workflow.py:1884` — `EpicWorkflow._run_node`, whose
`except _LaunchFailed` is `factory/workgraph/workflow.py:2222` —
`EpicWorkflow._run_node`; and `factory/workgraph/workflow.py:3976` —
`EpicWorkflow._recovery_attempt`, whose `try` at
`factory/workgraph/workflow.py:3975` — `EpicWorkflow._recovery_attempt` has no
`except` clause at all — only the `finally` at
`factory/workgraph/workflow.py:4031` — `EpicWorkflow._recovery_attempt`. Its
caller has none either: `factory/workgraph/workflow.py:3617` —
`EpicWorkflow._run_recovery` contains zero `except` clauses over its whole body,
and `factory/workgraph/workflow.py:1110` — `EpicWorkflow.run` dispatches it as
its own task, sibling to the `_run_node` task at
`factory/workgraph/workflow.py:1114` — `EpicWorkflow.run`. So a raise out of the
recovery attempt lands in `factory/workgraph/workflow.py:1654` —
`EpicWorkflow._reap_finished`, which sets `record.state = NodeState.KILLED` at
`factory/workgraph/workflow.py:1656` — `EpicWorkflow._reap_finished` and records
`_failure_detail(exc)` as the reason. FR-013, traps 16 and 17.

**The recovery path's `termination` is unbound until the attempt returns.**
`factory/workgraph/workflow.py:4034` — `EpicWorkflow._recovery_attempt` passes
`termination` to `_teardown` from inside the `finally`, and the only two
assignments to it are `factory/workgraph/workflow.py:3997` and
`factory/workgraph/workflow.py:4004` — both `EpicWorkflow._recovery_attempt`,
both **after** the awaited `_attempt` returns. `_run_node` binds its own at
`factory/workgraph/workflow.py:1780` — `EpicWorkflow._run_node` before its try;
the recovery path does not. So a raise from `_attempt` on that path does not even
reach the reaper as itself: the `finally` raises `UnboundLocalError`, that
replaces the original exception, and the recovery key is never closed. This is
already true at 602a92c for the adapter's own `_LaunchFailed` at
`factory/workgraph/workflow.py:2470` — `EpicWorkflow._attempt`; FR-013 closes it
for both, because FR-004 would otherwise route a routine worker restart into it.

**The precedent for both halves of the recovery scenario, landed and adjacent.**
`tests/test_interpreter.py:2598` —
`test_an_attempt_raise_still_teardowns_and_propagates` replaces
`EpicWorkflow._attempt` with a raising stub and asserts the node's ending and a
single teardown; `tests/test_interpreter.py:2530` —
`test_a_verify_raise_in_recovery_still_teardowns_and_propagates` does the same
one layer in, and counts the recovery teardowns at
`tests/test_interpreter.py:2588` by `lease.attempt == 2`; and
`tests/test_interpreter.py:4671` —
`test_recovery_escalation_kill_preserves_the_branch` is the scripted rejection
that drives a node into a recovery cycle at all — `script_landing` with
`checks_failed_snapshot()`, `script_sync`, and `press=EscalationChoice.KILL.value`
so the landing escalation has an answer. US1-S6 is those three composed, and
nothing new has to be built to reach the path.

**One worker serves the workflow and the activity, on one task queue.**
`factory/worker.py:281` — `build_worker` constructs the only `Worker` in
`factory/`, passing `task_queue=TASK_QUEUE` at `factory/worker.py:283` —
`build_worker`, `workflows=WORKFLOWS` at `factory/worker.py:284` —
`build_worker` and `activities=ACTIVITIES` at `factory/worker.py:285` —
`build_worker`; `TASK_QUEUE` is defined once, at
`factory/workgraph/workflow.py:279`. Two consequences the spec now states rather
than implies. The server records a schedule-to-start expiry when the bound fires,
but `_attempt_timeout` runs **inside the workflow**, so the classification lands
when a worker next polls — the bound turns an unbounded pending attempt into a
definite discarded one, it does not make a stalled epic clear itself while
nobody polls. And `ergane build status` cannot be read in that window at all:
`factory/cli/nouns/build.py:1125` — `_query_status` gets the node document from
`handle.query("epic_status")`, which no worker is there to serve, so the command
either raises `OperatorError` at `factory/cli/nouns/build.py:1141` —
`_query_status` with `EXIT_TRANSPORT` and prints no node line, or degrades
through `factory/cli/nouns/build.py:1126` — `_query_status` to
`{"nodes": {}}` and prints none either. Operator step 2 below is written around
that fact.

**The reading, and the filter that discards the case in question.**
`factory/cli/nouns/build.py:407` — `_live_spend` is fifty lines and the whole of
US2's first half:

```python
    for activity_info in pending:
        if not activity_info.HasField("activity_type"):
            continue
        if activity_info.activity_type.name != "run_agent_attempt":
            continue
        if converter is None or not activity_info.HasField("heartbeat_details"):
            continue
        node_id = activity_info.activity_id
        if node_id not in nodes:
            continue
```

`factory/cli/nouns/build.py:442` — `_live_spend` is the line that makes a
scheduled-and-unaccepted activity invisible, and
`factory/cli/nouns/build.py:457` — `_live_spend` is the two-key entry it builds
when the payload does decode. The pending activity message the loop is walking
carries far more than that: `state`, `heartbeat_details`, `last_heartbeat_time`,
`last_started_time`, `attempt`, `maximum_attempts`, `scheduled_time` and
`last_worker_identity` are all fields of Temporal's `PendingActivityInfo`, and
`state` is exactly the SCHEDULED/STARTED/CANCEL_REQUESTED discriminator this
story needs. FR-007.

**The renderer, and the token it drops.** `factory/cli/nouns/build.py:464` —
`render_status` reads the map at `factory/cli/nouns/build.py:493` —
`render_status` and builds the figure at `factory/cli/nouns/build.py:494` —
`render_status`:

```python
        figure = live.get(node_id)
        spend_token = (
            f"  spend ${figure['spend_usd']:.2f}" if figure is not None else ""
        )
```

`captured_at` is in the mapping and never reaches the line. The node line itself
is assembled at `factory/cli/nouns/build.py:501` — `render_status` out of five
tokens, three of which are already helper functions —
`factory/cli/nouns/build.py:757` — `_routing_token`,
`factory/cli/nouns/build.py:524` — `_base_token` and
`factory/cli/nouns/build.py:718` — `_reason_token`. A new token follows those,
not a new format string. FR-008, FR-009, FR-010, FR-012.

**The machine reading, which already carries what the human one drops.**
`factory/cli/nouns/build.py:1169` — `_query_status` calls `_live_spend` and
`factory/cli/nouns/build.py:1178` — `_query_status` puts the whole map under
`live_spend` in the `--json` document, `captured_at` included; the whole
document then goes through `json.dumps` at
`factory/cli/nouns/build.py:1188` — `_query_status`. That is the
control FR-011 protects: whatever fields the entry gains, those two keys stay.

**The renderer has a second production caller, and it passes no live map.**
`factory/cli/status.py:796` — `_epic_lines` imports `render_status` from
`factory/cli/nouns/build.py` and calls it at `factory/cli/status.py:805` —
`_epic_lines` for every epic on the floor board, with the comment "the per-epic
table is `build status`'s renderer, reused rather than re-formatted, so the two
verbs cannot drift into two shapes". It builds its document from two keys and
supplies no `live_spend` at all, so FR-012's control is what keeps `ergane
status` unchanged — one more reason the new token must be absent rather than
empty for a node with no pending activity.

**The precedent for asserting a timeout off recorded history — it is the same
assertion, for the sibling bound.** `tests/test_interpreter.py:2870` —
`test_a_dead_agent_is_still_detected_under_a_derived_heartbeat_timeout` builds a
graph with `timeout_override_s=12`, runs the epic, then reads the scheduled
event:

```python
    history = await script.handle.fetch_history()
    heartbeat_timeout = next(
        event.activity_task_scheduled_event_attributes.heartbeat_timeout.ToTimedelta()
        for event in history.events
        if event.event_type == _EVENT_ACTIVITY_SCHEDULED
        and event.activity_task_scheduled_event_attributes.activity_type.name
        == "run_agent_attempt"
    )
    assert heartbeat_timeout == timedelta(seconds=12 // 2)
```

`tests/test_interpreter.py:2901`, `tests/test_interpreter.py:2905` and
`tests/test_interpreter.py:2909` are the three lines that matter, and
`_EVENT_ACTIVITY_SCHEDULED` is defined at `tests/test_interpreter.py:3973`. Copy
this shape for `schedule_to_start_timeout` and for the second node of a two-node
graph built with `tests/test_interpreter.py:402` — `make_node`. US1-S1, US1-S2.

**The precedent for calling a workflow method directly, with the docstring that
justifies it.** `tests/test_escalation_offers_only_what_it_can_do.py:444` builds
an `EpicWorkflow()` outside any Temporal context and calls a method on it, and
says why in its own docstring: "Called directly rather than through Temporal
because the refusal path emits no command — it returns before any activity, which
is precisely the claim." `tests/test_interpreter.py:4795` does the same for the
scheduler's picker. `EpicWorkflow.__init__` (`factory/workgraph/workflow.py:755`
— `EpicWorkflow.__init__`) assigns plain fields and calls nothing from
`workflow`, and `_attempt_timeout` reads only `exc.cause` and writes only
`record.last_snapshot`, so the same route is open here. US1-S3, US1-S4.

**The precedent for a new module that borrows the interpreter harness.**
`tests/test_launch_is_not_an_attempt.py` is the story that landed the launch
classification US1 extends. It imports `env`, `run_epic`, `make_graph`,
`make_node`, `passing`, `states` and `ScriptedWorld` from `tests/test_interpreter.py`
rather than re-inventing the environment, subclasses the world at
`tests/test_launch_is_not_an_attempt.py:62` — `LaunchFailingWorld` to replace one
activity, and drives the end-to-end assertions at
`tests/test_launch_is_not_an_attempt.py:111` —
`test_launch_failure_does_not_consume_attempt_budget`,
`tests/test_launch_is_not_an_attempt.py:145` —
`test_launch_failure_is_reported_distinctly_naming_the_fault` and
`tests/test_launch_is_not_an_attempt.py:239` —
`test_repeated_launch_failures_are_bounded`. US1's tests go in a new module built
the same way, and the second of those three is the landed assertion US1-S5 has to
keep green: `tests/test_launch_is_not_an_attempt.py:159` requires
`AGENT_LAUNCH_FAILED` in the terminal reason.

**The status renderer's own test module, and what it does not pass.**
`tests/test_status_shows_the_dials_in_force.py:184` —
`test_a_running_epic_shows_the_landing_dials_it_is_using` renders a live query
answer through the real `render_status` at
`tests/test_status_shows_the_dials_in_force.py:207`, and every call in that file
omits `live_spend`. `tests/test_status_shows_the_dials_in_force.py:167` —
`epic_and_node_lines` is the helper that pins the node line against change. That
is the module US2's control scenario protects, and the reason FR-012 exists.
`tests/test_ergane_build_status_refusal.py:54` — `_FakeWorkflowHandle` is the
only fake `describe()` in the suite and it returns `pending_activities=[]` at
`tests/test_ergane_build_status_refusal.py:68`, so **no fake in this repository
drives `_live_spend`'s loop with a populated list**: US2 writes that fake, and
trap 7 is what it must get right. One landed test does drive the loop with real
protos — `tests/test_ergane_build.py:815` —
`test_status_reads_live_spend_off_the_running_attempt` runs the real CLI against
a paused epic with a live heartbeat snapshot and asserts the entry at
`tests/test_ergane_build.py:841` and the human line at
`tests/test_ergane_build.py:845` — so it is the landed backstop for trap 7's
`ValueError` and trap 18's `TypeError` as well as the assertion trap 14 says to
amend. It is not a substitute for the new fake: it exercises one STARTED
activity carrying a payload, which is the case that already works. Nine test
modules call this renderer — `tests/test_095_pre_agent_failure.py`,
`tests/test_095_the_ladder_names_its_bound.py`,
`tests/test_100_push_reports_refusal.py`, `tests/test_110_us2_demo_dispatch.py`,
`tests/test_118_record_names_its_base.py`,
`tests/test_attempt_reports_persona_and_model.py`,
`tests/test_external_completion_surfaces.py`,
`tests/test_landing_poller_failure_is_visible.py` and
`tests/test_status_shows_the_dials_in_force.py` — and **not one of them passes
`live_spend`**. (`tests/test_both_verbs_agree_about_the_schedule.py` matches a
grep for the name and is not one of them: it calls the roadmap's own
`_render_status` at `tests/test_both_verbs_agree_about_the_schedule.py:511`,
which this story does not touch.) Those nine plus the floor board at
`factory/cli/status.py:805` are FR-012's control, and they go red together on a
renderer that always appends a column.

**Two landed tests pin the shapes US2 has to change, and one of them is an exact
equality.** `tests/test_ergane_build.py:815` —
`test_status_reads_live_spend_off_the_running_attempt` drives the real CLI
against a live epic and asserts at `tests/test_ergane_build.py:841` that
`mid_json.json["live_spend"]["us2"]` **equals** `{"spend_usd": 6.25,
"captured_at": "2026-08-05T09:31:00Z"}` — a whole-dict comparison, so any field
FR-007 adds turns it red, and its human-side assertion at
`tests/test_ergane_build.py:845` (`"6.25" in mid_human.stdout`) is the one that
must stay true. And `tests/test_ergane_status.py:1516` is `EXPECTED_GUARDS`,
whose entry at `tests/test_ergane_status.py:1528` pins `_live_spend`'s exception
clauses to exactly `{("TRANSPORT_FAILED",), ("QUERY_REFUSED",), ("Exception",)}`,
swept by `tests/test_ergane_status.py:1808` —
`test_no_temporal_call_site_catches_the_transport_failure_alone`, which lists the
function by name at `tests/test_ergane_status.py:1844`. Traps 14 and 15.

**Why the reading half cannot live in the workflow.** An activity's start is not
delivered to a workflow — the workflow sees a scheduled command and then a
result, and nothing in between — so `record.state` cannot learn the difference
and no query answer can carry it. `factory/cli/nouns/build.py:429` —
`_live_spend` is where the distinction is already on the wire, because
`describe()` returns the server's pending-activity list. This is the whole
argument for US2 living entirely in the CLI, and for the "not a new `NodeState`"
paragraph in spec.md.

**Two facts about the deployment that make the unbounded wait reachable rather
than theoretical.** `factory/worker.py:268` — `build_worker` registers every
activity on one task queue at `factory/worker.py:285` — `build_worker` and sets
no `max_concurrent_activities`, so the SDK default applies and an agent activity
is never queued behind other work — a SCHEDULED agent activity means nobody is
polling. And `factory/versioning.py:57` names `ERGANE_WORKER_BUILD_ID`, while
`factory/versioning.py:163` — `strandable_epics` guards only the retirement of
the **unversioned** worker: a PINNED epic whose deployment version is retired
routes to a version nobody serves, with no refusal in the way.

## Traps

**Trap 1 — THE LEDGER ROW NAMES THE HALF THAT IS ALREADY FIXED, and the wrong
move is to rebuild it.** The row this spec declares still reads, in its original
summary, "Nothing fails until heartbeatTimeout (7200s here)". That window is
gone: `factory/workgraph/workflow.py:487` sets a 120-second ceiling,
`factory/workgraph/workflow.py:490` — `_agent_heartbeat_timeout` derives every
attempt's bound inside it, 082-US5 landed it, and v0.3.0, v0.4.0 and v0.5.0 all
ship it. Given that bound the scheduler park at
`factory/workgraph/workflow.py:1138` — `EpicWorkflow.run` is correct rather than
pathological. An implementer who reads the row and re-derives a heartbeat clamp
writes a second ceiling beside the first, fails FR-003, and fixes nothing. The
mechanism this spec is about is an activity that **never started**, which no
heartbeat bound can reach because the heartbeat timer does not arm until a worker
accepts the task.

**Trap 2 — TEMPORAL'S OWN GUIDANCE SAYS NOT TO SET THIS OPTION, and this
repository is the exception it names.** The pinned SDK's command proto says of
`schedule_to_start_timeout`: "This timeout should usually not be set: it's useful
in specific scenarios like worker-specific task queues." An implementer who finds
that sentence will be tempted to close the story as won't-fix. Read the next
clause of the same comment and the two facts above: the factory runs one
worker-specific task queue (`factory/worker.py:283` — `build_worker`), sets no
activity concurrency limit, and can route a PINNED epic to a retired deployment
version that nobody serves (`factory/versioning.py:163` — `strandable_epics`
guards only the unversioned worker). This is the specific scenario. Put that
reasoning in the constant's docstring, not in a commit message.

**Trap 3 — THE EXPIRY ITSELF IS NON-RETRYABLE AT THE SERVER, so once it fires
`_AGENT_RETRIES` buys nothing and the workflow's own launch bound is the only
recovery.** The same proto comment says the timeout "is always non retryable, as
all a retry would achieve is to put it back into the same queue". So the
schedule-to-start expiry ends the activity outright and the failure reaches
`factory/workgraph/workflow.py:2464` — `EpicWorkflow._attempt` **when a worker
next polls**, because the workflow and the activity share one task queue. The
bound is therefore a converter, not a self-clearing stall: it turns "waiting on
something nothing will pick up" into "a discarded attempt, classified on the next
poll". An implementer who assumes the retry policy will absorb a worker restart
will pick a bound far too short and kill nodes across every ordinary
`systemctl --user restart` — which is why FR-014 states a floor of thirty
minutes rather than leaving the magnitude to taste: the unit restarts after ten
seconds (`factory/supervision/units.py:604` — `_service_text`), but the operator
sequence in both measured sightings is stop, land, restart. The recovery this
story does get on the node path is the launch-retry path at
`factory/workgraph/workflow.py:2233` — `EpicWorkflow._run_node`, bounded by
`factory/verify/models.py:1205` — `VerificationConfig` at 2 by default, which is
why FR-004 routes the ending there rather than inventing a new one; the recovery
path has no such ladder, which is what trap 16 is about.

**Trap 4 — LEFT UNCLASSIFIED, THE NEW BOUND MAKES THINGS WORSE, NOT BETTER.**
`factory/workgraph/workflow.py:2471` — `EpicWorkflow._attempt` hands every
non-launch `ActivityError` to `factory/workgraph/workflow.py:2475` —
`EpicWorkflow._attempt_timeout`, which returns a `TIMEOUT` `AdapterResult`
whatever the cause. Add FR-001's bound and stop: a node nobody picked up now
produces a recorded attempt with no work behind it, charged against the ladder,
sent through verification with an empty worktree and a diff of nothing, and
judged. That is a worse outcome than the stall it replaces, and every gate would
be green. FR-004 and FR-001 land in one story for this reason, and the branch
starts from `TimeoutError.type == TimeoutType.SCHEDULE_TO_START` —
`factory/workgraph/workflow.py:2491` — `EpicWorkflow._attempt_timeout` already
narrows the cause to that class under the alias imported at
`factory/workgraph/workflow.py:116`. It does not **end** there: trap 19 is the
second half of the same branch, and a condition on the timeout type alone fails
US1-S7 and erases a measured attempt.

**Trap 5 — THE EXPIRY IS NOT REACHABLE END TO END IN THIS HARNESS, and both
routes that look like it are something else.** Do not spend attempts trying to
make a real schedule-to-start timeout fire inside
`tests/test_interpreter.py:1834` — `env`. (a) Omitting `run_agent_attempt` from
the worker's activity list does **not** leave the task unaccepted: a polling
worker that receives a task for an activity type it does not know fails that task
immediately with "is not registered on this worker", which arrives as an
`ApplicationError`, not a `TimeoutError`. (b) Blocking inside the fake activity —
the shape `tests/test_interpreter.py:1870` — `start_epic` supports and
`heartbeat_then_block` uses — produces a **STARTED** activity, which is the
heartbeat case this spec is not about. A worker constructed with no activities
registers no activity poller at all, which is the one true route, but reaching it
requires shutting the activity worker down in the window between
`issue_attempt_key` returning and `run_agent_attempt` being scheduled, and that
window is not something the harness exposes. US1-S1 and US1-S2 prove the wiring
off recorded history and US1-S3 and US1-S4 prove the classification by calling
the real method; the live expiry is the operator's step 2 below, not a node's.

**Trap 6 — A WORD IN AN OPERATOR STRING FAILS THE WHOLE SUITE.**
`tests/test_final_sweep.py` parses **every** module under `factory/` and refuses
any that spells an enforcement word outside a docstring — the set includes
`budget`, `cap`, `caps`, `capped`, `quota`, `throttle`, `breach`, `enforce`,
`exceed` and `exceeded`. Identifiers, attribute names, keyword-argument names and
non-docstring string constants all count; comments and docstrings do not, because
comments never reach the AST and docstrings are excluded by name. So a terminal
reason reading "the schedule-to-start limit was exceeded" turns the declared
`test` gate red for a reason that has nothing to do with this story, and so does
naming the constant anything with `cap` in it. `factory/workgraph/workflow.py:483-485`
is the tree explaining this to itself, two lines above the ceiling it names
"ceiling" for exactly this reason: "006's SC-005 forbids this component from
spelling enforcement vocabulary in code, and `tests/test_final_sweep.py` fails
the module that does". Write **bound** or **limit**, and put the
argument in the docstring.

**Trap 7 — `HasField` RAISES ON A SCALAR FIELD, and two of the three fields this
story wants are scalars.** `factory/cli/nouns/build.py:438` — `_live_spend` and
`factory/cli/nouns/build.py:442` — `_live_spend` call `HasField` on
`activity_type` and `heartbeat_details`, both of which are message fields where
it is legal. `state` and `attempt` are proto3 scalars with no presence, and
`HasField` on those raises `ValueError` rather than returning `False` — inside
`_live_spend`, which the surrounding `try` blocks do **not** guard, so the
failure surfaces as a broken `ergane build status` rather than as a degraded one.
Read `state` and `attempt` directly; `last_heartbeat_time` is a `Timestamp`
message, so `HasField` is legal for it and is how a never-heartbeated activity is
told from one whose timestamp is the epoch.

**Trap 8 — TEMPORAL RETAINS `heartbeat_details` ACROSS RETRY ATTEMPTS, which is
why a stale figure is the defect rather than a cosmetic flaw.** The consumer's
measured sighting is exactly this: `RUNNING attempt 6`, a spend figure, and
nothing running. A re-scheduled attempt carries the previous attempt's payload,
so `factory/cli/nouns/build.py:442` — `_live_spend` admits it,
`factory/cli/nouns/build.py:457` — `_live_spend` builds an entry from it, and
`factory/cli/nouns/build.py:494` — `render_status` prints it with no capture time
beside it. FR-010 is what closes that: a figure that arrives with the moment it
was measured cannot be mistaken for a fresh one. The wrong move is to drop the
figure for a non-STARTED activity — it is the last true measurement and
constitution V says record it, never fabricate a zero.

**Trap 9 — THE ACTIVITY'S `attempt` IS NOT THE NODE'S ATTEMPT, and printing them
under the same word is worse than printing neither.** The node line already
carries `attempt {node['attempt']}` from the workflow's own query document
(`factory/cli/nouns/build.py:501` — `render_status`), which is the ladder's
attempt number. `PendingActivityInfo.attempt` is Temporal's retry count for the
current activity, bounded by `_AGENT_RETRIES`, and the two are different numbers
that disagree routinely. FR-007 requires the activity's count to be carried;
label it so it cannot be read as the ladder's, and do not overwrite the node's.

**Trap 10 — THERE IS A SECOND `_live_spend` AND A SECOND `render_status`, AND
NOTHING CALLS EITHER.** `factory/workgraph/cli.py:842` — `_live_spend` and
`factory/workgraph/cli.py:916` — `render_status` are a pre-`ergane` copy with the
same filter (`factory/workgraph/cli.py:951` — `render_status` is the same bare
spend token). No module under `factory/` imports either, no test imports either,
and `ergane build status` dispatches
`factory/cli/nouns/build.py:464` — `render_status` through the parser at
`factory/cli/nouns/build.py:2166`. Editing the twin satisfies no scenario, and
editing **only** the twin produces a green gate and an unchanged floor. Leave it
alone; spec.md says so out loud.

**Trap 11 — DO NOT ADD A `NodeState`, however obviously it seems to be missing.**
`NodeState` is declared at `factory/workgraph/models.py:101` — `NodeState` and
`RUNNING` is written in exactly one place,
`factory/workgraph/workflow.py:2428` — `EpicWorkflow._attempt`. A new value
between `KEY_ISSUED` and `RUNNING` would have to be written by the workflow, and
the workflow never learns that a worker accepted the activity — the SDK delivers
a scheduled command and then a result, with no start event in between. The
distinction exists only in the server's pending-activity list, which only the
`describe` call at `factory/cli/nouns/build.py:429` — `_live_spend` reads. A
story that changes `NodeState` changes the query document, the store and every
consumer of both, and still cannot answer the question.

**Trap 12 — THE LANDED STATUS TESTS PASS NO `live_spend`, so the new token must
be absent, not empty.** Every `render_status` call in
`tests/test_status_shows_the_dials_in_force.py` omits the argument, and
`tests/test_status_shows_the_dials_in_force.py:167` — `epic_and_node_lines`
compares whole node lines across five degraded documents. A renderer that appends
` state -` or a blank-padded column for a node with no pending activity turns
that landed module red for a reason this story is not about — trap 6's shape from
a second direction. FR-012 is the requirement, and US2-S5 is the assertion; write
the control test first so the red you see is the one you meant.

**Trap 13 — TWO PARTIAL SIGNALS ALREADY SHIP AND MUST NOT BE RE-CLAIMED.**
`build status --json` already carries the whole live map, `captured_at` included,
at `factory/cli/nouns/build.py:1178` — `_query_status`; and
`factory/doctor/probes.py:345` — `StaleWorkerProbe.evaluate` already emits
`ops/no-worker-running` at `factory/doctor/probes.py:349` — as INFO, with the note
"A laptop run is not an incident". Neither is tied to a node, which is the whole
gap; but an implementer who "adds" `captured_at` to the JSON, or who raises the
probe's severity, has written a diff whose claim the judge cannot check against
the base tree it never sees. FR-011 protects the first as a control and this spec
touches the second not at all.

**Trap 14 — THE CORRECT US2 DIFF TURNS A LANDED TEST RED, and that red is the
proof the fields landed on the entry rather than beside it.** FR-007, T018.
`tests/test_ergane_build.py:841` compares the whole `live_spend` entry for one
node against a two-key dict, so the moment `state`, the activity's retry attempt
or `last_heartbeat_time` joins it, that assertion fails. Update it in the same
commit to name the fields the entry now carries; the same test's human-side
assertion at `tests/test_ergane_build.py:845` must go on passing untouched,
because FR-010 keeps printing the figure. The wrong move is to read the red as
"the entry may not change" and hang the new fields off a second sibling map: the
renderer would then have to join two maps by node id, FR-008's "one entry, figure
optional" would be unwritable, and the `--json` document would grow a key nobody
asked for. This is the same shape as `factory/cli/nouns/build.py:1178` —
`_query_status` staying additive: the keys survive, the dict grows.

**Trap 15 — YOU MAY NOT WRAP THE SCALAR READ IN A `try`, BECAUSE A SWEEP PINS
THIS FUNCTION'S EXCEPTION CLAUSES BY NAME.** Trap 7's tempting repair is
`try: ... except ValueError:` around `HasField("state")`.
`tests/test_ergane_status.py:1516` is `EXPECTED_GUARDS` and
`tests/test_ergane_status.py:1528` fixes `_live_spend`'s clause set to exactly
`{("TRANSPORT_FAILED",), ("QUERY_REFUSED",), ("Exception",)}`; the sweep at
`tests/test_ergane_status.py:1808` —
`test_no_temporal_call_site_catches_the_transport_failure_alone` names the
function at `tests/test_ergane_status.py:1844` and 052 built the whole file so
that a new clause "cannot be guarded wrongly in silence". A fourth clause fails
it. Read `state` and `attempt` as the plain scalars they are — proto3 gives them
no presence and therefore no way to be missing — and leave the two `Exception`
guards that already exist exactly where they are.

**Trap 16 — THE BRANCH YOU ADD IN `_attempt_timeout` FIRES ON A PATH NOBODY
CATCHES, and there it is an immediate node kill.** FR-004 turns a
schedule-to-start expiry into a raise. On `factory/workgraph/workflow.py:1884` —
`EpicWorkflow._run_node` that is exactly right: `factory/workgraph/workflow.py:2222`
— `EpicWorkflow._run_node` catches it and spends a launch strike. On
`factory/workgraph/workflow.py:3976` — `EpicWorkflow._recovery_attempt` it is
not caught by anything: not there (the `try` at
`factory/workgraph/workflow.py:3975` has only a `finally`), not in
`factory/workgraph/workflow.py:3617` — `EpicWorkflow._run_recovery` (no `except`
anywhere in its body), and not between them, because
`factory/workgraph/workflow.py:1110` — `EpicWorkflow.run` runs the recovery as
its own task. It lands in `factory/workgraph/workflow.py:1654` —
`EpicWorkflow._reap_finished`, which KILLs the node. So the headline scenario of
this spec — an operator restarts the worker — would, on any node whose landing
had been rejected, become an instant kill where today the same event yields a
`TIMEOUT` `AdapterResult` that the cycle verifies and escalates. Reproduce it
before you believe it: replace `_attempt` with a raising stub the way
`tests/test_interpreter.py:2598` —
`test_an_attempt_raise_still_teardowns_and_propagates` does, over the scripted
rejection `tests/test_interpreter.py:4671` —
`test_recovery_escalation_kill_preserves_the_branch` builds. The wrong move is
to add the branch in `_attempt_timeout` and stop — a green gate, because no
landed test drives a raise through `_recovery_attempt`, and a node killed by an
ordinary restart. FR-013 is the requirement; US1-S6 is the assertion.

**Trap 17 — ON THAT PATH THE RAISE IS NOT EVEN ITSELF: `termination` IS UNBOUND
IN THE `finally`, SO THE KEY LEAKS.**
`factory/workgraph/workflow.py:4034` — `EpicWorkflow._recovery_attempt` reads
`termination` inside the `finally` at `factory/workgraph/workflow.py:4031` —
`EpicWorkflow._recovery_attempt`, and it is assigned only at
`factory/workgraph/workflow.py:3997` and `factory/workgraph/workflow.py:4004` —
both after `_attempt` returns. `_run_node` binds its own before the try at
`factory/workgraph/workflow.py:1780` — `EpicWorkflow._run_node`; this one does
not. So any raise out of the awaited `_attempt` becomes an `UnboundLocalError`
raised from the `finally`, the original exception is lost, **and `_teardown`
never runs** — the recovery key stays open, which is precisely the leak
`tests/test_interpreter.py:2530` —
`test_a_verify_raise_in_recovery_still_teardowns_and_propagates` was written to
prevent one layer further in. Whatever shape FR-013's handler takes, the
teardown must still happen exactly once; assert it by counting
`script.teardowns` for `lease.attempt == 2`, the way
`tests/test_interpreter.py:2588` does.

**Trap 18 — EVERY FIELD ON THE ENTRY GOES THROUGH `json.dumps`, AND ONE OF THE
THREE IS A PROTOBUF MESSAGE.** `factory/cli/nouns/build.py:1178` —
`_query_status` puts the live map into the document and
`factory/cli/nouns/build.py:1188` — `_query_status` serialises the whole thing.
`PendingActivityInfo.last_heartbeat_time` is a `Timestamp` message and
`PendingActivityInfo.state` is an enum; carrying either through as it arrives
raises `TypeError: Object of type Timestamp is not JSON serializable` and breaks
`ergane build status --json` outright — not for the new case, for every epic.
Convert on the way in: the state as its enum **name**, the heartbeat time as an
ISO-8601 **string**, matching the plain `str` that `captured_at` already is at
`factory/cli/nouns/build.py:459` — `_live_spend` (`UsageSnapshot.captured_at` is
typed `str`). US2-S4 asserts the document loads, so this red is cheap — but it
is a red the plan can spend one sentence preventing.

**Trap 19 — THE HEADLINE SEQUENCE REACHES `SCHEDULE_TO_START` ON A RETRY OF AN
ATTEMPT THAT DID RUN, so a branch written on the timeout type alone records
hours of paid work as an attempt that never started.** Reproduce the reasoning
before you write the branch. `factory/workgraph/workflow.py:367` is
`_AGENT_RETRIES`; `factory/workgraph/workflow.py:369` is `maximum_attempts=2`; a
heartbeat timeout is retryable. So "the operator stops the worker with an
attempt in flight and leaves it down" runs: attempt 1 STARTED and heartbeating →
worker dies → the 120-second ceiling at
`factory/workgraph/workflow.py:487` fires → the server re-schedules → **attempt
2** sits unaccepted → FR-001's bound fires on attempt 2. The pinned SDK's
comment on the option says exactly which attempt it measures ("the 'schedule'
time is when the most recent retry is scheduled"), and the failure carries the
heartbeat payload Temporal retained from attempt 1. An implementer who writes
`if cause.type is TimeoutType.SCHEDULE_TO_START: raise` then classifies that
ending as one in which no agent started: no `AttemptRecord`, nothing spent from
the ladder, and the last true measurement dropped — the exact fabrication trap 8
forbids and constitution V refuses, on the most common path this spec has. Every
gate would be green, because nothing in the suite drives that composite. FR-015
is the requirement and US1-S7 is the assertion: compute the snapshot **first**,
the way `factory/workgraph/workflow.py:2492` — `EpicWorkflow._attempt_timeout`
already does, and raise only when nothing was measured — on the timeout's own
`last_heartbeat_details` and on the `TimeoutError`s reachable through its cause
chain, because which of the two the server populates is not something this
repository pins and reading only one of them is the same bug with a smaller
blast radius. The one case that stays ambiguous is an attempt that died before
its first heartbeat; FR-015 states out loud that it is classified as never
started, which spends nothing and re-dispatches.

**Trap 20 — YOUR REASON FUNCTION IS NOT THE LAST WRITER OF `terminal_reason` IN
PRODUCTION.** FR-006 makes one function own the node's terminal reason, and
`factory/workgraph/workflow.py:3152` — `EpicWorkflow._close_out` overwrites it:
on every non-parked terminal state the archive step assigns
`record.terminal_reason = "; ".join(report)` whenever that report is non-empty
(126-US2, landed 2026-09-02). It is invisible in the suite — the scripted world
returns an empty report, so US1-S5's exact-equality assertion is honest and
stays honest — and it is not this spec's to repair. Two consequences to hold.
Do not "fix" it here: widening scope to the archive report is a second story's
work and would put US1 over its sizing. And do not send the operator looking for
the reason on the terminal record alone: operator step 2 reads the server's own
timed-out event first, and the escalation summary — which `_close_out` does not
touch — second.

## Sizing

US1 touches one production file, `factory/workgraph/workflow.py`: one module
constant beside `factory/workgraph/workflow.py:487`, one keyword on the call at
`factory/workgraph/workflow.py:2429` — `EpicWorkflow._attempt`, one branch inside
`factory/workgraph/workflow.py:2475` — `EpicWorkflow._attempt_timeout` (the type
test plus the walk over the cause chain FR-015 needs, a handful of lines beside
the snapshot that method already builds), one field
on `factory/workgraph/workflow.py:737` — `_LaunchFailed`, one reason function the
two strings at `factory/workgraph/workflow.py:2235` and
`factory/workgraph/workflow.py:2243` — both `EpicWorkflow._run_node` — are built
from, and the second call site: a handler around
`factory/workgraph/workflow.py:3976` — `EpicWorkflow._recovery_attempt` plus the
`termination` binding its `finally` needs (traps 16 and 17). Under seventy
production lines. Its tests are one new module built the way
`tests/test_launch_is_not_an_attempt.py` is built, importing the harness from
`tests/test_interpreter.py` rather than restating it; no landed test file is
edited, and `tests/test_launch_is_not_an_attempt.py:159` must stay green
untouched, which is US1-S5's point.

US2 touches one production file, `factory/cli/nouns/build.py`: the loop and the
entry inside `factory/cli/nouns/build.py:407` — `_live_spend`, and one token
inside `factory/cli/nouns/build.py:464` — `render_status` beside the three that
already exist. Under fifty production lines. Its tests are one new module holding
a fake `describe()` answer with a populated pending-activity list — the fake this
repository does not yet have, since `tests/test_ergane_build_status_refusal.py:68`
returns an empty one — plus direct `render_status` calls in the style of
`tests/test_status_shows_the_dials_in_force.py:207`. It also amends **one**
landed assertion, and planning for it is part of the sizing:
`tests/test_ergane_build.py:841` compares a whole `live_spend` entry against a
two-key dict and grows by the fields FR-007 adds (trap 14). Nothing else in
`tests/` is edited: the nine modules that call `render_status` pass no live map
and stay green as FR-012's control, and `tests/test_ergane_status.py`'s guard
sweep stays green because no exception clause is added (trap 15).

The two stories name **no production file in common**, and no test file in
common. Both are far inside the 64 KiB deterministic diff bound (D-050): the
pasted evidence each verification task asks for is two short readings, not a
transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that, on the operator's
own host:

1. Start an epic, and while a node's agent is working run `ergane build status
   <epic-id>`. The node line must carry its state, its spend figure and the time
   that figure was measured, and `--json` must still carry `spend_usd` and
   `captured_at` under `live_spend`.
2. `systemctl --user stop` the worker with a node's attempt in flight and leave
   it stopped past the heartbeat ceiling and the new bound together. **Do not
   expect to read the floor in that window**: one worker serves both the
   workflow and the activity on one task queue, so while it is down
   `handle.query("epic_status")` has nobody to answer it and
   `factory/cli/nouns/build.py:1125` — `_query_status` either exits
   `EXIT_TRANSPORT` or degrades to `{"nodes": {}}` — either way, no node line.
   Then restart the worker and **read the server, not the CLI, for the ending
   itself**: in the epic's history (`temporal workflow show --workflow-id
   <epic-id>`, or Temporal's Web UI on port 8233) there must be an
   `ACTIVITY_TASK_TIMED_OUT` event for `run_agent_attempt` whose `timeout_type`
   is `SCHEDULE_TO_START`. That event is the bound firing, it cannot exist on
   today's tree because the option is never passed, and it is the falsifiable
   observation of this step. `ergane build status <epic-id>` corroborates and
   cannot replace it, because after **one** expiry the node carries no new
   operator-visible fact: the launch evidence goes on a local list that reaches
   only the next prompt (`factory/workgraph/workflow.py:2228` —
   `EpicWorkflow._run_node`), `record.launch_failures`
   (`factory/workgraph/models.py:382`) is not a field of the query document
   (`factory/workgraph/workflow.py:895` — `EpicWorkflow.epic_status`), and
   `attempt_note` — the one free-text line the renderer prints, at
   `factory/cli/nouns/build.py:507` — `render_status` through
   `factory/cli/nouns/build.py:738` — `_attempt_note_lines` — is written only for
   `Termination.PRE_AGENT_FAILURE`, at `factory/workgraph/workflow.py:1918` —
   `EpicWorkflow._run_node`, which the raise skips entirely. So from `build
   status` read the two facts that are there: the node re-dispatched with **no**
   new `AttemptRecord` in its history, and the ladder's attempt count where it
   was. Neither of those alone discriminates — they are also what you see if the
   bound never fired and the restarted worker simply picked the old activity back
   up — which is why the history event leads and step 3 follows.
3. Do it again, and this time take the node to its **second** launch strike:
   stop the worker before the re-dispatched attempt is accepted and leave it down
   past the bound a second time. `record.launch_failures >=
   max_launch_retries` then fires at `factory/workgraph/workflow.py:2233` —
   `EpicWorkflow._run_node` and the ending becomes operator-visible: the node
   ends, and the escalation sent at `factory/workgraph/workflow.py:2243` —
   `EpicWorkflow._run_node` must name the schedule-to-start cause and must not
   name `AGENT_LAUNCH_FAILED`. Read it with `ergane escalations list`, which is
   the surface the archive overwrite of trap 20 does not touch; the node's
   `terminal_reason` should say the same and may have been replaced by an archive
   report (`factory/workgraph/workflow.py:3152` — `EpicWorkflow._close_out`),
   which is trap 20 and not a regression in this spec.
4. Restart the worker and confirm an ordinary restart, well inside the bound,
   costs nothing: the attempt is re-scheduled, picked up, and the node continues.
   This is the false-positive check, and it is the one that decides whether the
   constant's value is right.
5. Confirm the heartbeat path is unchanged — which takes **two** worker deaths,
   not one. `factory/workgraph/workflow.py:367` gives the activity a second
   attempt, so: kill the worker with an attempt in flight; bring it back inside
   the new bound, so the retry is accepted and an agent runs again; then kill it
   a second time and leave it down past the heartbeat ceiling. With
   `maximum_attempts=2` there is no third attempt, so that ending arrives as
   `HEARTBEAT` and the attempt is recorded `TIMEOUT`, carries the last measured
   figure, and is verified like any other. That is 082-US5's behaviour and this
   step is what proves this spec did not eat it. Run with one death only, this
   step produces step 2's or step 4's outcome instead and a correct
   implementation reads as a regression; and if the timing slips so the ending
   arrives as `SCHEDULE_TO_START` with the figure still on it, FR-015 requires
   the same recorded ending, which is exactly what that requirement is for.
6. Reject a node's landing so it enters a recovery cycle, stop the worker again
   while the recovery's own attempt is pending, and restart past the bound. The
   node must end through the landing escalation — an escalation sent, a landing
   resolution applied — and **not** as a KILLED coroutine whose reason is an
   `UnboundLocalError`. This is FR-013's step, and it is the one the first draft
   of this plan did not have.

Steps 2 and 3 together are the falsifiable test of the whole spec: they are the
2026-08-19/20 two-hour stall and the consumer's ninety minutes of `RUNNING
attempt 6`, run forwards — step 2 for the event the server records, step 3 for
the ending an operator can read. Step 6 is the same event on the path that had
no handler.
