---
state: draft
fixes:
  - hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04-tail) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-worker-restart-does-not-leave-a-node-reading-running"
# (lines 312-328), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n 'Np'` and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. Ledger row
# `hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout`
# — open, critical, three sightings, first seen 2026-08-20, last 2026-09-03. It
# was measured twice on this floor and once by a consumer: the 2026-08-19/20
# orphan on epic-070, where a worker stopped at 03:24:55Z to land 071 and the
# node's agent died with it; and the `ergane-web` round-2 hand-over's N23, where
# a restart killed an in-flight activity and ninety minutes later the status
# line still read RUNNING attempt 6. The 2026-09-03 correction on that row is
# what this spec is cut against: it names the two mechanisms that survive.
#
# WHAT IT COST, MEASURED. Two hours of stalled epic on 2026-08-19/20 — us4 dead,
# us3 PENDING with satisfied edges and two free slots, nothing able to dispatch
# — cleared only by a hand-typed `temporal activity fail`. Ninety minutes of a
# consumer's floor reading RUNNING with a frozen spend figure while nothing ran,
# with the reporter noting the persona's full four-hour timeout as the real
# horizon. Neither cost is the heartbeat window: both are an activity that
# nothing was going to pick up, and a reading that could not say so.
#
# 099 RELEASED THIS KEY AND NAMED THIS ENTRY AS ITS OWNER, SO IT IS DECLARED
# HERE. `specs/099-a-worker-restart-does-not-orphan-the-work-in-flight` was
# refined earlier in this run; its provenance says the key "named the 7,200 s
# heartbeat window", that 082-US5 closed that window, that "nothing in this spec
# fixes either" surviving half, and that "the owner of record is the backlog item
# `a-worker-restart-does-not-leave-a-node-reading-running` ... whose 'Findings it
# would declare' block names this key", unowned by any spec at 602a92c. This spec
# is that owner. It declares the key once — 099 declares it nowhere — and its
# requirements cover both surviving mechanisms the row's 2026-09-03 correction
# names: FR-001..FR-006 and FR-013..FR-015 are "(1) the agent activity carries no
# `schedule_to_start_timeout`" and FR-007..FR-012 are "(2) the status line cannot
# distinguish PENDING_ACTIVITY_STATE_SCHEDULED from PENDING_ACTIVITY_STATE_STARTED".
# No third key is declared: the row's own summary was amended to those two, and
# the 100/092/118 half-fix shape is a `fixes:` list longer than the requirements
# justify, not a list of one that covers both halves of one row.
#
# THE 7,200 s HALF IS CLOSED, AND SAYING SO IS THIS SPEC'S FIRST JOB. The row's
# original summary — "Nothing fails until heartbeatTimeout (7200s here)" — names
# a mechanism that no longer exists: `factory/workgraph/workflow.py:487` sets a
# 120-second ceiling and `factory/workgraph/workflow.py:490` derives every
# attempt's heartbeat timeout inside it, landed as 082-US5 and shipped in v0.3.0,
# v0.4.0 and v0.5.0, and the scheduler park at `factory/workgraph/workflow.py:1138`
# is correct given that bound. An implementer who reads the row instead of this
# spec will re-derive a clamp that already exists. Plan trap 1 is that sentence
# handed to the node.
#
# TWO LANDED TESTS PIN SHAPES US2 CHANGES, FOUND BY GREP AFTER THE FIRST DRAFT
# AND FOLDED INTO plan.md AND tasks.md WITHOUT MOVING A REQUIREMENT.
# `tests/test_ergane_build.py:841` asserts a whole `live_spend` entry **equals** a
# two-key dict, so the correct FR-007 diff turns a landed test red — trap 14 says
# the red is confirmation and forbids the sibling-map workaround that would clear
# it. And `tests/test_ergane_status.py:1528` pins `_live_spend`'s exception
# clauses to exactly three, swept by name at
# `tests/test_ergane_status.py:1822`, which closes trap 7's tempting repair — a
# `try/except ValueError` around the scalar read — as trap 15. The same pass found
# a second production caller of `render_status`, the floor board at
# `factory/cli/status.py:805`, which passes no live map, and counted the landed
# `render_status` callers in `tests/` at nine, none of them passing one: all of
# them are FR-012's control, which is why that control exists.
#
# NOT IN SCOPE. `_agent_heartbeat_timeout` and its ceiling and floor, which are
# 082-US5's and stay exactly as they are; `_AGENT_RETRIES`, which this spec reads
# and does not change; any workflow-level run timeout (no `start_workflow` call
# site names one, and this spec adds none); a new `NodeState`, because the
# workflow cannot observe an activity's start at all — only a `describe` read
# can, which is why the reading half lives in the CLI; a manifest dial for the
# new bound; the unreferenced twin renderer in `factory/workgraph/cli.py`; and
# the `StaleWorkerProbe`, which already reports a missing worker and is not tied
# to a node.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail) after an adversarial review
# refuted the draft; anchors re-read again at 602a92c. Four classes of change,
# and no declared key moved. (1) The blocking one: `_attempt` has a **second**
# caller, `factory/workgraph/workflow.py:3954` — `EpicWorkflow._recovery_attempt`,
# whose try has only a `finally` — so FR-004's raise would have escaped through
# `_run_recovery` to the reaper at `factory/workgraph/workflow.py:1656` and ended
# the node KILLED, unrecorded, on an ordinary restart during a recovery cycle;
# worse, that finally reads a `termination` that is unbound before the attempt
# returns, so the raise becomes an `UnboundLocalError` and the recovery key is
# never closed. FR-013, US1-S6, a truth-table row and plan traps 16 and 17
# now own that path. (2) One worker serves both the workflow and the agent
# activity on one task queue, so the bound converts an unbounded pending attempt
# into a definite one classified when a worker next polls — it does not clear a
# stall while nobody polls. The gap section, the first table row and the
# operator's step 2 now say so instead of implying otherwise. (3) FR-014 bounds
# the new constant from below: nothing in the draft stopped a value short enough
# to kill a node across an ordinary `systemctl --user restart`. (4) FR-007 now
# requires JSON-serialisable fields (trap 18 — `last_heartbeat_time` is a
# protobuf `Timestamp` and `json.dumps` cannot carry it), the SCHEDULED token's
# occasion is stated in "What this spec is not", and four locator cites moved to
# the line they describe (:483, :283, :1178, :2407).
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail): a second adversarial review
# refuted the truth table rather than the mechanism, and three minor claims went
# with it. (1) THE ACTIVITY RETRIES. `factory/workgraph/workflow.py:367` is
# `_AGENT_RETRIES` with `maximum_attempts=2` at
# `factory/workgraph/workflow.py:369`, and a heartbeat timeout is retryable, so
# the sequence both measured sightings record — a worker dies mid-attempt and
# stays away — reaches `SCHEDULE_TO_START` on a **re-scheduled** attempt whose
# predecessor ran, heartbeated and spent money; the pinned SDK's own comment on
# the option this spec adds says the "schedule" time is when the most recent
# retry is scheduled. A sixth gap step, a sixth truth-table row, FR-015, US1-S7
# and plan trap 19 now carry that composite, and FR-004 classifies an ending as
# one in which no agent started only when **no heartbeat measurement is
# reachable** — otherwise hours of paid work would have been recorded as never
# having happened, against constitution V and against this spec's own trap 8.
# (2) The operator's step 2 asked for launch evidence that no operator surface
# carries after a single expiry: launch evidence goes on a local list that
# reaches only the next prompt, `record.launch_failures` is not a field of the
# query document (`factory/workgraph/workflow.py:895` — `EpicWorkflow.epic_status`),
# and `attempt_note` is written only for `PRE_AGENT_FAILURE`. Step 2 now reads
# the server's own timed-out event and takes the sequence to the second strike;
# plan trap 20 names `factory/workgraph/workflow.py:3152` —
# `EpicWorkflow._close_out` as a landed overwrite of `terminal_reason`, so the
# reason function is not the last writer in production. (3) US2-S1 now asserts
# all three fields FR-007 requires rather than the state alone; the plan's claim
# that no test drives `_live_spend`'s loop with a populated list is corrected to
# fakes only (`tests/test_ergane_build.py:815` drives it with real protos); the
# ten-module control list is nine, because
# `tests/test_both_verbs_agree_about_the_schedule.py` calls the roadmap's own
# `_render_status`; and the `factory/worker.py` cite splits into :284 and :285.
# No key was added or removed, no story was split, and no anchor moved.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail, cross-batch): a completeness
# pass found one blocking defect, in tasks.md only, and nothing in this file
# moved. tasks.md told the implementer twice that T005 is a non-regression
# control, green from the first commit — once in the preamble and once in T005's
# own closing sentence. Half of T005 is red today. US1-S7 and FR-015 require
# **both** shapes of a `SCHEDULE_TO_START` timeout that carries a measurement,
# including the payload reached through the cause chain, and at 602a92c
# `factory/workgraph/workflow.py:2512` — `EpicWorkflow._attempt_timeout` binds
# `timeout = exc.cause`, type-tests that one object and reads its
# `last_heartbeat_details` only; it walks no `__cause__`, so the cause-chain
# shape returns `last_snapshot=None` until T009's widening lands. An implementer
# told emphatically not to expect a failure, meeting that red, has one repair the
# file itself blessed: delete the cause-chain shape — which would remove the only
# committed guard on the half of FR-015 plan trap 19 turns on and ship T009
# unproven behind a green gate. The preamble and T005 now say which shape is
# green today, which is red today and why, and that the red stands until T009
# widens the search. No requirement, scenario, story or anchor changed, and the
# declared key is unchanged: 099 released
# `hardening/a-worker-restart-orphans-the-in-flight-agent-activity-for-the-full-heartbeat-timeout`
# and named this spec as its owner, this spec declares it once, and the 7,200 s
# half of that row stays closed by 082-US5 (plan trap 1).
---

# Feature Specification: a worker restart does not leave a node reading RUNNING

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

A node is marked RUNNING when its agent activity is **scheduled**, and every
bound on that activity measures an activity a worker has already **started**. So
an activity nobody picks up is never bounded, never ends, and reads as work in
progress for as long as the epic lives.

The chain is six steps, each anchored to the line that makes it true:

1. `factory/workgraph/workflow.py:2429` — `EpicWorkflow._attempt` assigns
   `record.state = NodeState.RUNNING`. That is the only place in the module the
   value is written, and it happens on the line **above**
   `factory/workgraph/workflow.py:2429` — `EpicWorkflow._attempt`, where the
   activity is scheduled. Nothing between the two consults a worker.
2. That call names exactly four options — the activity id
   (`factory/workgraph/workflow.py:2439` — `EpicWorkflow._attempt`), the
   start-to-close bound (`factory/workgraph/workflow.py:2440` —
   `EpicWorkflow._attempt`), the heartbeat bound
   (`factory/workgraph/workflow.py:2480` — `EpicWorkflow._attempt`) and the retry
   policy (`factory/workgraph/workflow.py:2481` — `EpicWorkflow._attempt`). All
   three timers start when a worker accepts the task; none of them arms before
   that. `grep -rn "schedule_to_start\|schedule_to_close" factory/` returns
   nothing, and `git log --all -S"schedule_to_start_timeout"` returns no commit:
   the option exists on the SDK call and has never been passed.
3. The workflow then parks on that activity with no bound of its own —
   `factory/workgraph/workflow.py:2447` — `EpicWorkflow._attempt`, whose
   `timeout=None` is spelled at `factory/workgraph/workflow.py:2449`. The
   method's own docstring says so at `factory/workgraph/workflow.py:2429` —
   `EpicWorkflow._attempt`: the wait "creates **no Temporal timer**", which is
   true and is the point — nothing is counting.
4. When the wait does end in an error, the classification cannot tell the two
   apart. `factory/workgraph/workflow.py:2464` — `EpicWorkflow._attempt` catches
   every `ActivityError`, re-raises only the adapter's own
   `AGENT_LAUNCH_FAILED` (`factory/workgraph/workflow.py:2470` —
   `EpicWorkflow._attempt`), and hands everything else to
   `factory/workgraph/workflow.py:2512` — `EpicWorkflow._attempt_timeout`, which
   returns `AdapterResult(termination=Termination.TIMEOUT, ...)` at
   `factory/workgraph/workflow.py:2512` — `EpicWorkflow._attempt_timeout`. A
   timeout that means "a worker accepted this and then died" and one that would
   mean "no worker ever accepted this" become the same recorded attempt, charged
   to the ladder and sent to verification with nothing behind it.
5. And the sequence that produced both measured sightings arrives at that
   classification through a **retry**, not through a first attempt nobody ever
   accepted. `factory/workgraph/workflow.py:367` is `_AGENT_RETRIES`, whose
   `maximum_attempts=2` sits at `factory/workgraph/workflow.py:369`, and a
   heartbeat timeout is retryable. So a worker that dies mid-attempt does not
   leave attempt 1 pending for long: the 120-second ceiling fires, the server
   re-schedules, and **attempt 2** is what sits unaccepted for as long as the
   worker is away. The pinned SDK's own comment on the option this spec adds
   says which attempt it measures — the "schedule" time is when the most recent
   retry is scheduled — so the new bound normally arms on a retry, and the
   failure it produces carries the heartbeat measurement Temporal retained from
   the attempt that did run. Both measured sightings were taken before the
   120-second ceiling landed, which is why both record a **STARTED** attempt 1
   sitting for hours; on today's tree the same event reaches a re-scheduled
   attempt within two minutes, and it is that attempt which has no bound. An
   ending classified on the timeout type alone would therefore record hours of
   paid agent work as an attempt that never started.
6. Meanwhile the only live reading discards exactly the case in question.
   `factory/cli/nouns/build.py:456` — `_live_spend` skips any pending activity
   with no `heartbeat_details`, so a scheduled-and-unaccepted activity puts
   nothing in the map at all; and Temporal retains `heartbeat_details` across
   retry attempts, so a **re-scheduled** attempt that still carries the previous
   attempt's payload puts in an entry indistinguishable from live work. The
   renderer then prints a bare figure — `factory/cli/nouns/build.py:494` —
   `render_status` — and drops even the capture time the map already carries at
   `factory/cli/nouns/build.py:459` — `_live_spend`.

So the floor prints `RUNNING ... spend $X` for a node whose activity no worker
has accepted, the figure it prints was measured before the worker died, and
nothing ends the wait.

**One worker serves both halves, which is what the bound buys and what it does
not.** `factory/worker.py:283` — `build_worker` registers the workflows and the
activities on one task queue — `factory/workgraph/workflow.py:279` is its only
definition — so the worker that is not there to accept the agent activity is the
same worker that is not there to serve the workflow task. The server records the
expiry the moment the bound fires; the workflow classifies it when a worker next
polls. That ordering is the honest claim of this spec: it converts an unbounded
pending attempt into a **definite, discarded** one, so the epic resumes on a
recorded ending instead of on a hand-typed `temporal activity fail`. It does not
make a stalled epic clear itself while nobody is polling, and no requirement
here says it does. The same fact bounds what US2 can show: while the worker is
gone, `ergane build status` renders nothing at all, because
`factory/cli/nouns/build.py:1298` — `_query_status` reads the node document from
a workflow query that no worker is there to answer.

**The half that is already closed, stated so nobody rebuilds it.** The ledger
row's original summary — "Nothing fails until heartbeatTimeout (7200s here)" —
is fixed. `factory/workgraph/workflow.py:487` sets a 120-second ceiling and
`factory/workgraph/workflow.py:495` — `_agent_heartbeat_timeout` derives each
attempt's bound inside it, landed as 082-US5. Given that bound, the scheduler
park at `factory/workgraph/workflow.py:1138` — `EpicWorkflow.run` is correct: a
node whose worker died stalls for two minutes, not two hours. That mechanism is
not this spec's — and closing it is what moved the defect one step along, from
an attempt that sat STARTED for hours to a retry that sits SCHEDULED forever.

**Why this is not an exotic case.** The factory runs one dedicated task queue
served by one worker (`factory/worker.py:283` — `build_worker`), which sets no
activity concurrency limit at all — so an agent activity sitting SCHEDULED means
nobody is polling, never that the pool is busy. And 082's worker versioning makes
a second route concrete: a PINNED epic whose deployment version is retired routes
to a version nobody serves, and `factory/versioning.py:163` — `strandable_epics`
guards only the retirement of the **unversioned** worker.

## The rule this spec is asking for

**An agent attempt no worker accepts ends at a stated bound instead of waiting
forever, on both of the paths that run one, and is recorded for what it was — an
attempt that never started when no measurement survives it, the attempt that did
run when one does; and until it ends, the status line says nobody has picked it
up rather than reporting the last figure a dead worker measured.**

The six endings, complete:

| the agent activity | a worker accepted it | today | with this spec |
|---|---|---|---|
| scheduled on a first attempt, nobody polling | **no** | waited on with no bound; the node reads RUNNING and no figure was ever measured | ends at the schedule-to-start bound, classified as an attempt that never started the next time a worker serves the epic |
| scheduled inside a recovery cycle, nobody polling | **no** | the same unbounded wait, on the second `_attempt` call site nothing catches | ends at the same bound; that recovery cycle ends as one that produced no result and escalates, never as an unhandled raise at the reaper (FR-013) |
| accepted, heartbeating, the worker died, and a worker returns inside the bound | yes | the heartbeat timeout fires and `_AGENT_RETRIES` re-schedules; the retry is picked up and runs | **unchanged** |
| accepted, heartbeating, the worker died and stayed away past the bound | yes | the heartbeat timeout re-schedules an attempt nobody accepts, and **that** wait has no bound — this is the measured stall | ends at the bound and is recorded as the `TIMEOUT` attempt it was, carrying the figure the failure retains (FR-015), never as an attempt that never started |
| accepted, adapter could not start the agent | yes | `AGENT_LAUNCH_FAILED` → launch failure, no attempt spent | **unchanged** on the node path, and no longer an `UnboundLocalError` on the recovery path (FR-013) |
| accepted and heartbeating | yes | `RUNNING` and a bare figure | `RUNNING`, the figure, and when it was measured |

### What this spec is not

It is not a change to the heartbeat bound. `_agent_heartbeat_timeout`, its
ceiling and its floor are 082-US5's and are untouched; so is `_AGENT_RETRIES`,
which this spec reads and reasons about but does not modify, and so is every
`start_workflow` call site, none of which gains a run timeout.

It is not a new `NodeState`. An activity's start is not an event the workflow
receives, so no workflow-side state can carry the distinction; the only surface
that can see it is the `describe` read the status command already makes. That is
why the second story is entirely a reading and touches no workflow file.

It is not a promise that the floor will often print SCHEDULED. The retry
composite does make the stalled pending activity genuinely SCHEDULED rather than
STARTED — attempt 2, re-scheduled after the ceiling fired, is the thing sitting
in the queue — but "while the worker is away" is exactly the window in which no
worker answers the status query, and once a worker returns the SCHEDULED window
is sub-second. The state token FR-009 asks for is a completeness property of the
reading — the map and the line stop lying by omission — while the requirement
that closes the consumer's measured sighting is FR-010: a retained figure
printed beside the moment it was measured cannot read as a live one. FR-009 is
worth its two lines, and it is not the load-bearing half.

It is not a claim to add signals that already ship. `build status --json`
already carries the whole live map including `captured_at`
(`factory/cli/nouns/build.py:1298` — `_query_status`), and
`factory/doctor/probes.py:345` — `StaleWorkerProbe.evaluate` already emits
`ops/no-worker-running`. Neither is tied to a node, which is the gap; neither is
removed or restated.

It is not a repair of the twin renderer. `factory/workgraph/cli.py:855` —
`_live_spend` and `factory/workgraph/cli.py:929` — `render_status` are a copy
that no module under `factory/` and no test imports; editing them satisfies no
scenario here.

## User Scenarios & Testing

### User Story 1 - An attempt no worker accepts ends, and names the reason (Priority: P1)

As the operator who restarts the worker to land factory code, a node whose agent
activity nobody picked up stops waiting and tells me nobody picked it up, instead
of holding the epic open until I go and read Temporal by hand.

**Why this priority**: P1 and it depends on nothing. It is the mechanism that
cost two hours in one measured sighting and ninety minutes in another, and it is
the half no landed bound reaches: every existing timer on the call measures an
activity that has already started.

**Independent Test**: Read the `ACTIVITY_TASK_SCHEDULED` event one epic writes
for `run_agent_attempt`, call the workflow's own timeout classification with each
timeout type and with each shape of retained measurement, and drive the resulting
signal through both callers of `_attempt`.

**Acceptance Scenarios**:

1. **Given** an epic dispatched through the real `EpicWorkflow`, **When** its
   recorded history is read, **Then** the `ACTIVITY_TASK_SCHEDULED` event for
   `run_agent_attempt` carries a non-zero `schedule_to_start_timeout` equal to
   the module constant this story adds, **and** that constant is at least the
   floor FR-014 states — asserted by one committed test that reads the event the
   way `tests/test_interpreter.py:2986` —
   `test_a_dead_agent_is_still_detected_under_a_derived_heartbeat_timeout`
   already reads `heartbeat_timeout` off the same event. The field is unset on
   today's tree, so a diff that leaves the call site alone cannot pass this, and
   a value short enough to fire across an ordinary worker restart fails the
   second half.
2. **Given** two nodes in one epic whose `timeout_override_s` differ by two
   orders of magnitude, **When** both of their scheduled events are read,
   **Then** the two `schedule_to_start_timeout` values are equal while the two
   `heartbeat_timeout` values differ, and the `start_to_close_timeout` and retry
   policy of each are what today's code produces for that node — one committed
   test asserts all four, so a bound derived from `timeout_s` fails it and a diff
   that moved a bound this story is not about fails it too.
3. **Given** an `ActivityError` whose cause is a `TimeoutError` of type
   `SCHEDULE_TO_START` from which **no** heartbeat measurement is reachable —
   none on its own `last_heartbeat_details` and none on any error in its cause
   chain — **When** `EpicWorkflow._attempt_timeout` is called with it, **Then**
   it raises the workflow's no-agent-started signal instead of returning an
   `AdapterResult`, so no `AttemptRecord` is appended and `_attempts_spent` stays
   where it was. A committed test asserts the raise.
4. **Given** an `ActivityError` whose cause is a `TimeoutError` of type
   `HEARTBEAT` carrying a heartbeat payload, **When** the same method is called
   with it, **Then** it still returns `AdapterResult(termination=Termination.TIMEOUT)`
   carrying that payload's figure — the control, byte-identical to today, and the
   assertion that stops this story from swallowing a worker death.
5. **Given** a node killed by the adapter's own launch fault, driven end to end
   the way `tests/test_launch_is_not_an_attempt.py:145` —
   `test_launch_failure_is_reported_distinctly_naming_the_fault` drives it,
   **When** its `terminal_reason` is read, **Then** it is exactly what this
   story's reason function returns for that signal and count and it still
   contains `AGENT_LAUNCH_FAILED`; **and** when the same function is called with
   the no-worker signal it returns a reason naming the schedule-to-start cause
   and not `AGENT_LAUNCH_FAILED`. One committed test asserts both halves, so a
   single hardcoded string cannot serve both endings.
6. **Given** a node whose landing was rejected into a recovery cycle, with
   `EpicWorkflow._attempt` replaced so that the recovery's own attempt raises the
   no-agent-started signal — the substitution
   `tests/test_interpreter.py:2714` —
   `test_an_attempt_raise_still_teardowns_and_propagates` already makes, over the
   scripted rejection `tests/test_interpreter.py:4787` —
   `test_recovery_escalation_kill_preserves_the_branch` already builds — **When**
   the epic is run to completion, **Then** the node ends through the landing
   escalation rather than through the reaper: exactly one escalation was sent for
   it, its landing state is the one the scripted press produces, its
   `terminal_reason` is not the signal's text recorded as a crashed coroutine,
   and the recovery key was torn down exactly once, asserted the way
   `tests/test_interpreter.py:2646` —
   `test_a_verify_raise_in_recovery_still_teardowns_and_propagates` counts
   teardowns. One committed test asserts all four, and on today's tree the same
   raise reaches `factory/workgraph/workflow.py:1656` —
   `EpicWorkflow._reap_finished` as an `UnboundLocalError` with the key still
   open, so no diff that leaves the recovery call site alone can pass it.
7. **Given** an `ActivityError` whose cause is a `TimeoutError` of type
   `SCHEDULE_TO_START` that **does** carry a heartbeat measurement — the payload
   Temporal retained from the attempt that ran before the retry, presented twice:
   once on the timeout's own `last_heartbeat_details` and once on a `TimeoutError`
   reached through its cause chain — **When** `EpicWorkflow._attempt_timeout` is
   called with each, **Then** each returns
   `AdapterResult(termination=Termination.TIMEOUT)` carrying that payload's
   figure and neither raises, so a worker that died mid-attempt and stayed away
   is still recorded as the attempt it was and its measurement survives. One
   committed test asserts both shapes; a branch written on the timeout type
   alone raises on both and fails it.

### User Story 2 - The status line says which nodes have an agent actually working (Priority: P2)

As an operator reading the floor, a node whose activity is sitting in the queue
looks different from a node whose agent is producing tokens, and a spend figure
comes with the time it was measured.

**Why this priority**: P2 and it depends on nothing in US1 — it is a reading, in
a different file, of a fact the server already publishes. It is also the half
that was measured on a consumer's floor: ninety minutes of `RUNNING attempt 6`
over an activity that had already died.

**Independent Test**: Build the live map from a `describe` answer holding one
pending `run_agent_attempt` in each state, and produce the node lines from it.

**Acceptance Scenarios**:

1. **Given** a `describe` answer holding a pending `run_agent_attempt` whose
   activity id names a node in the status document and which carries **no**
   decodable heartbeat payload, **When** the live map is built, **Then** the map
   holds an entry for that node carrying all three fields FR-007 requires — the
   pending activity's state under its own key, that activity's own retry attempt
   as an integer, and its last heartbeat time — with no protobuf message among
   them. Today `factory/cli/nouns/build.py:456` — `_live_spend` discards it and
   the map is empty, so a diff that leaves that filter alone cannot pass, and a
   diff that carries the state alone fails the other two assertions; a committed
   test asserts the entry field by field.
2. **Given** two otherwise identical documents whose pending activity differs
   only in its state — one SCHEDULED, one STARTED — **When** the node lines are
   produced from each, **Then** the two lines are not equal and the line built
   from the SCHEDULED one names that state. A committed test asserts the pair,
   and no diff that only reads the state without putting it on the line can
   satisfy it.
3. **Given** a pending activity carrying a decodable heartbeat payload, **When**
   its node line is produced, **Then** the line carries both the spend figure and
   the capture time that figure was measured at, which
   `factory/cli/nouns/build.py:494` — `render_status` drops today. A committed
   test asserts both tokens on one line.
4. **Given** the same live map serialised by `build status --json`, **When** the
   `live_spend` object is read, **Then** every entry that carries a figure still
   carries `spend_usd` and `captured_at` under those exact keys with those exact
   types, **and** the whole document is JSON the reader can load — the control
   for the machine reader at `factory/cli/nouns/build.py:1298` —
   `_query_status`, asserted by a committed test that loads that document, so
   this story is additive for anything already parsing it and cannot ship a field
   `json.dumps` refuses.
5. **Given** a status document whose nodes have no pending agent activity at all,
   **When** its node lines are produced, **Then** they are byte-identical to
   today's — the control that keeps `tests/test_status_shows_the_dials_in_force.py:167`
   — `epic_and_node_lines` green, and the reason the new token may only appear
   when there is a pending activity to name.

## Functional Requirements

- **FR-001**: The agent activity scheduled at `factory/workgraph/workflow.py:2429`
  — `EpicWorkflow._attempt` MUST carry a `schedule_to_start_timeout`, so an
  attempt no worker accepts is bounded.
- **FR-002**: That bound MUST be a module-level constant independent of the
  node's `timeout_s`: it measures how long a worker may be absent, not how long
  the work may take, and a node with a twelve-second deadline and one with a
  four-hour deadline MUST receive the same value.
- **FR-003**: Adding the bound MUST NOT change the activity id, the
  `start_to_close_timeout`, the `heartbeat_timeout` or the `retry_policy` on the
  same call, and MUST NOT change `_agent_heartbeat_timeout`, its ceiling, its
  floor or `_AGENT_RETRIES`.
- **FR-004**: An `ActivityError` whose cause is a `TimeoutError` of type
  `SCHEDULE_TO_START` **from which no heartbeat measurement is reachable** MUST
  be classified as an ending in which no agent started — raised as the same
  workflow-internal signal `factory/workgraph/workflow.py:748` — `_LaunchFailed`
  carries — so on the node path at `factory/workgraph/workflow.py:1884` —
  `EpicWorkflow._run_node` it appends no `AttemptRecord`, spends nothing from the
  ladder, and is bounded by `factory/verify/models.py:1213` —
  `VerificationConfig` rather than looping.
- **FR-005**: Every other `ActivityError` MUST keep today's classification: a
  `HEARTBEAT` or `START_TO_CLOSE` timeout still returns
  `AdapterResult(termination=Termination.TIMEOUT)` carrying the last heartbeat
  figure, and the adapter's `AGENT_LAUNCH_FAILED` still raises the launch signal
  with its own message.
- **FR-006**: The node's terminal reason and its escalation summary MUST be
  produced by one function of the signal, so the no-worker ending names the
  schedule-to-start cause and the adapter's launch fault goes on naming
  `AGENT_LAUNCH_FAILED`; neither string may be hardcoded at
  `factory/workgraph/workflow.py:2235` — `EpicWorkflow._run_node` in a way that
  serves both.
- **FR-007**: The live map built by `factory/cli/nouns/build.py:421` —
  `_live_spend` MUST hold an entry for every pending `run_agent_attempt` whose
  activity id names a node in the status document, whether or not a heartbeat
  payload decodes, and each entry MUST carry the pending activity's state, that
  activity's own retry attempt and its last heartbeat time. Every value on the
  entry MUST be a JSON scalar the `--json` document can carry, because
  `factory/cli/nouns/build.py:1298` — `_query_status` serialises the whole map:
  the state as its name and the heartbeat time as a string beside `captured_at`,
  never the protobuf messages they arrive as.
- **FR-008**: An entry's spend figure MUST stay optional — present only when a
  payload decodes — and `factory/cli/nouns/build.py:478` — `render_status` MUST
  produce a line for an entry that has none.
- **FR-009**: The node line MUST name the pending activity's state, so two
  documents differing only in that state do not produce the same line.
- **FR-010**: Whenever the node line carries a spend figure it MUST also carry
  the capture time that figure was measured at, so a figure retained from a dead
  worker's last heartbeat cannot read as a fresh measurement.
- **FR-011**: `live_spend` in `build status --json` MUST keep `spend_usd` and
  `captured_at` at their present keys and types; every field this story adds is
  additive.
- **FR-012**: A node with no pending agent activity MUST produce a line
  byte-identical to today's, and the state token MUST be absent rather than
  rendered as a sentinel.
- **FR-013**: The no-agent-started signal MUST be handled at **both** call sites
  of `EpicWorkflow._attempt`. At `factory/workgraph/workflow.py:3954` —
  `EpicWorkflow._recovery_attempt` it MUST end that recovery cycle as one that
  produced no result — the same `None` the cycle's other failures return, which
  reaches the landing escalation at `factory/workgraph/workflow.py:3817` —
  `EpicWorkflow._run_recovery` — with the recovery key torn down exactly once at
  `factory/workgraph/workflow.py:4114` — `EpicWorkflow._recovery_attempt`. It
  MUST NOT reach `factory/workgraph/workflow.py:1656` —
  `EpicWorkflow._reap_finished`, whose `except Exception` ends the node KILLED
  with no attempt and no landing resolution.
- **FR-014**: The constant FR-002 adds MUST be at least thirty minutes. It is a
  floor, not a value: the systemd unit restarts the worker after ten seconds
  (`factory/supervision/units.py:604` — `_service_text`), but the operator
  sequence that produced both measured sightings is stop-worker, land, restart,
  which is minutes; and a node gets only the two launch strikes
  `factory/verify/models.py:1213` — `VerificationConfig` allows, so a bound short
  enough to fire during an ordinary restart kills nodes that were never in
  trouble. The ending only has to beat the unbounded wait it replaces.
- **FR-015**: A `SCHEDULE_TO_START` timeout that **does** carry a heartbeat
  measurement MUST be recorded as today's
  `AdapterResult(termination=Termination.TIMEOUT)` carrying that figure, exactly
  as FR-005 requires of the heartbeat case, and MUST NOT be classified as an
  ending in which no agent started. This is the normal shape of the defect, not
  an edge: `factory/workgraph/workflow.py:367` gives every agent activity a
  second attempt, Temporal retains the last heartbeat payload across attempts,
  and the bound FR-001 adds therefore fires on a retry whose predecessor ran and
  spent money. The retained measurement is the discriminator, and its one
  boundary is stated rather than hidden — an attempt that started and died before
  its first heartbeat leaves nothing to find and is classified as never started,
  which spends nothing and re-dispatches, the safe direction — while an attempt
  that ran for hours is never recorded as one that never started (constitution V).

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-013, FR-014, FR-015]
US2:
  depends_on: []
  implements: [FR-007, FR-008, FR-009, FR-010, FR-011, FR-012]
  concurrent_with: [US1]
```

No edge, declared deliberately rather than left to be inferred. US1 is entirely
inside `factory/workgraph/workflow.py` and US2 is entirely inside
`factory/cli/nouns/build.py`; neither reads a value the other adds, and neither
story's tests import the other's module. A `depends_on` edge would serialise two
nodes that cannot collide, and a `depends_on_merged` edge would do the same for
no correctness gain, so `concurrent_with` records that the contention an inferred
edge would guard against does not exist here. The one fact both stories rest on —
that a scheduled activity is not a started one — is a property of Temporal, not
of code either story writes.
