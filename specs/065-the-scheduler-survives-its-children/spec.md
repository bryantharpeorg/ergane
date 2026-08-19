---
state: ready
# FLIPPED READY 2026-08-19 2:55 PM CT at the operator's instruction, and
# dispatched BY HAND rather than through the roadmap, at all three nodes in
# parallel. The operator asked for the 035 escape hatch "to get it done
# quickly"; what he gets is the hatch ARMED rather than the hatch USED, and the
# distinction is worth recording because it is a property of 035's design that
# is easy to misremember:
#
#   The hand-back is only offered when the ladder returns ESCALATE
#   (factory/workgraph/workflow.py:1439). A node that has not exhausted its
#   attempts refuses any buffered signal outright -- "node ladder not
#   exhausted", :1466-1470. And the accepted branch still runs the full
#   gates + judge + PR + queue path (:1935), by design.
#
# So the hatch cannot be a shortcut PAST dispatch; used as one it would be
# SLOWER, requiring three failed attempts at roughly $15 each before the signal
# is even legal. It is an exit from a stuck node, not an alternative to
# starting one.
#
# The fast path with the same effect is: dispatch all three stories at once
# (they are declared independent and their file assignments were checked
# against the tree, not assumed), and hand back the moment any node exhausts
# instead of letting it re-ladder or page. That is what is happening.
#
# Drafted 2026-08-19 1:35 PM CT by an operator session, from two live incidents
# on the same day rather than from a review.
#
# EVIDENCE, both observed, both on this host:
#
#   epic-059-a-wired-repo-can-land   COMPLETED 2026-08-19T13:49:32Z
#       Result: {"metadata":{"encoding":"YmluYXJ5L251bGw="}}   (binary/null)
#       roadmap workflow task began failing 13:49:33Z, one second later,
#       and did not stop until an operator terminated the run at 14:07Z.
#
#   epic-060-install-can-be-driven-without-a-human  COMPLETED 16:22:37Z
#       Result: binary/null again.
#       Roadmap wedged again. Floor idle 1h49m before an operator noticed.
#
# In between, at 14:08:43Z, the worker was restarted on the hypothesis that the
# null was environmental. It was not: 060 ran entirely on the fresh worker and
# still returned null. That experiment is what makes this a spec rather than a
# restart.
#
# Two epics before the 2026-08-18T13:57:45Z worker restart -- epic-054 (04:20Z)
# and epic-055 (13:48Z) -- both recorded full EpicStatus JSON. So the null is
# not eternal, and something changed. US3 is where that gets settled.
#
# Filed as a finding before drafting:
#   roadmap/a-child-epic-returning-null-wedges-the-scheduler-permanently
#
# NOT IN SCOPE, and it has its own finding: the roadmap's failure notifier sends
# one page per spec per pass, so one persistent cause produced 63 Telegram
# messages in six minutes on 2026-08-19. `_should_notify_failure`
# (factory/roadmap/workflow.py:139) throttles *identical* texts geometrically,
# and the flood defeated it because each message named a different spec dir --
# 63 distinct texts, 63 counts of one. Real, separate, deliberately not here.
#   roadmap/failure-notices-have-no-dedupe-and-flood-the-operator
---

# Feature Specification: the scheduler survives its children

**Created**: 2026-08-19

## The gap, stated precisely

The roadmap reads a completed child epic's return value and dereferences it
without checking what it got:

```python
status: EpicStatus = handle.result()        # factory/roadmap/workflow.py:832
self._landed[spec_dir] = self._landed_status_for(status)   # :833
```

and `_landed_status_for` opens with `status.epic_state` (`:1319`). The
annotation on line 832 is an assertion about the child, not a check of it. When
the child returns `None`, the roadmap raises `AttributeError` inside **workflow
code**.

That is the whole defect, and its consequence is out of all proportion to it.

## Why a crash here is worse than a crash anywhere else

A failing **workflow task** is not a failing workflow. Temporal retries it
forever and the execution stays `RUNNING`. So:

- The roadmap **reports healthy** to anything that asks whether it is running.
- Nothing is dispatched again, for the life of the run.
- **~~No page fires.~~ WRONG — corrected 2026-08-19 4:35 PM CT, after this spec
  had landed 3/3.** The operator's Telegram channel shows the wedge paging
  correctly at 8:49 AM (`1 consecutive run`) and again at 4:05 PM
  (`3 consecutive runs`), both reading
  `'NoneType' object has no attribute 'epic_state'`. The reasoning below was
  built from reading `_report_roadmap_failure` (`:955`) and concluding that a
  workflow-code exception never reaches the notifier. It does.
  **The real defect is worse than the one this bullet claimed.** The operator was
  told, twice, hours apart, and acted on neither — because a Python exception
  repr does not tell a person that their factory has stopped building, or what to
  do about it. Not being told would at least have been an honest silence; being
  told uselessly cost 1h49m in the morning and ~1h38m in the afternoon. That is
  spec 066's subject, and it exists because of this error.
- `ergane roadmap status` stops working entirely, returning Temporal's own
  words: `Unable to query workflow due to Workflow Task in failed state`.
- The run cannot be recovered by restarting the worker, because the null is
  already written into that run's history. It must be terminated and replaced.

This is the silent-stall shape: **the failure that does not page you.** On
2026-08-19 it cost 23 minutes the first time and 1 hour 49 minutes the second,
and both times the only thing that ended it was an operator happening to look.

Measured consequence: the roadmap dispatches **exactly one epic per operator
intervention**. An unattended overnight run completes one epic and idles.

## Two defects, and the order matters

**The roadmap trusting the child's shape** is the one that must be fixed. Even a
perfectly-behaved child can return something unexpected after a version skew, a
data-converter change, or a workflow that terminates by a path nobody predicted.
A scheduler that dies on an unrecognised child result is a scheduler that dies.

**The child returning null** is the trigger, and it is genuinely unexplained.
`EpicWorkflow.run` has exactly one return statement — `return self.epic_status()`
at `factory/workgraph/workflow.py:811` — present since the first commit, and
`@workflow.query` verifiably preserves a direct call's return value on
temporalio 1.31.0. Yet the results split cleanly at a worker restart.

Fixing only the trigger leaves the wedge armed for the next unexpected value, so
US1 leads and US3 follows. This ordering is the point of the spec, not an
accident of numbering.

## User Scenarios & Testing

### User Story 1 - The scheduler survives a child result it cannot read (Priority: P1)

As an operator, a child epic that returns something the roadmap did not expect
costs me that epic's landed status, not the whole scheduler.

**Why this priority**: P1. It is the only story that makes unattended running
possible, and it is the durable fix — it holds for the next unexpected value as
well as this one.

**Independent Test**: script a child that returns `None`, drive the roadmap
through its reap path, and assert the run continues and dispatches the next
spec.

**Acceptance Scenarios**:

1. **Given** a scripted child epic whose result is `None`, **When** the roadmap
   reaps it, **Then** the run does not raise and goes on to dispatch the next
   dispatchable spec — proven by a committed test asserting the *subsequent*
   dispatch happened. Asserting only that no exception was raised would pass on
   a roadmap that silently stopped.
2. **Given** the same, **When** that spec's landed status is read, **Then** it is
   `landed=False` with kind `OBSERVED` — finished but not landed — proven by a
   committed test. The vocabulary already exists for this: a child that completed
   with a FAILED node is recorded exactly this way, so an unreadable result needs
   no new state, only the existing one.
3. **Given** the same, **When** the operator asks what happened, **Then** a
   roadmap failure was recorded and the notifier was reached — proven by a
   committed test asserting the failure record. Surviving must not mean
   swallowing: a child whose result could not be read is a fact the operator has
   to be told, and a silent recovery is how this defect returns as "the roadmap
   quietly stopped landing things".
4. **Given** a child that returns a value of the wrong shape — an object with no
   `epic_state`, or a dict — **When** the roadmap reaps it, **Then** the same
   three things hold — proven by a committed test over at least one non-null
   malformed value. `None` is one member of the class, not the class.
5. **Given** the diff, **When** the reap path is inspected, **Then** the check
   is a check and not a type annotation — proven by a committed test that fails
   if the guard is removed. `status: EpicStatus = handle.result()` is what
   created this defect: an annotation asserts, it does not verify.
6. **Given** a child that returns a well-formed `EpicStatus`, **When** the
   roadmap reaps it, **Then** landed derivation is byte-for-byte what it is
   today — proven by the existing scheduler tests continuing to pass unchanged.
   A guard that changes the healthy path has changed more than it was asked to.

---

### User Story 2 - A wedged scheduler is visible without an operator guessing (Priority: P1)

As an operator, I find out that the roadmap has stopped from the system, not
from noticing that nothing has landed for two hours.

**Why this priority**: P1. US1 removes this particular wedge. It cannot remove
the class: any unhandled exception in roadmap workflow code produces the same
invisible, permanent, healthy-looking stall, and nothing in the system is
watching for it. Both incidents on 2026-08-19 ended because a human looked.

**Independent Test**: put a roadmap into a failing-workflow-task state and
assert both surfaces report it as such.

**Acceptance Scenarios**:

1. **Given** a roadmap whose workflow task is failing, **When**
   `ergane roadmap status` runs, **Then** it states that the roadmap is wedged,
   names the failing run, and says the run must be terminated — proven by a
   committed test over the query error. Today it forwards Temporal's own
   sentence (`factory/cli/roadmap.py:382`), which names no remedy and reads like
   a transport problem.
2. **Given** the same, **When** `ergane doctor` runs, **Then** a probe reports a
   finding naming the wedged run — proven by a committed test. The doctor's
   `REGISTRY` (`factory/doctor/probes.py`, consumed at
   `factory/doctor/cli.py:224`) is the only place in the system that can see
   this, because the workflow cannot report its own crash.
3. **Given** a roadmap that is running normally, **When** the same probe runs,
   **Then** it reports nothing — proven by a committed test. A probe that fires
   on a healthy scheduler will be switched off within a week.
4. **Given** a roadmap that is running but has dispatched nothing because it is
   at its epic cap, **When** the probe runs, **Then** it reports nothing —
   proven by a committed test. Idle is not wedged, and conflating them is how a
   real alert gets ignored.
5. **Given** the diff, **When** the probe's detection is inspected, **Then** it
   distinguishes a failing workflow task from an unreachable Temporal — proven
   by a committed test. "I cannot reach the server" and "the scheduler is dead"
   demand different actions from the operator, and reporting the second when the
   first is true sends them to the wrong place.

---

### User Story 3 - The epic returns the status it declares (Priority: P2)

As a maintainer, `EpicWorkflow.run` returning `EpicStatus` is a fact a test
holds, not a type hint nobody checks.

**Why this priority**: P2, and only because US1 makes it non-urgent. It is the
trigger for both incidents and it is still unexplained, but with US1 landed a
recurrence costs one epic's landed status instead of the scheduler.

**Independent Test**: run an epic to completion in the workflow test environment
and assert the returned value is an `EpicStatus` with the expected `epic_state`.

**Acceptance Scenarios**:

1. **Given** an epic driven to completion in the test environment, **When** its
   workflow result is read, **Then** it is an `EpicStatus` whose `epic_state` is
   `COMPLETED` — proven by a committed test asserting the *returned value*,
   not the `epic_status` query. The query has always worked; it is the return
   that came back null, and a test that asserts the query would have passed
   throughout both incidents.
2. **Given** an epic driven to a killed conclusion, **When** its result is read,
   **Then** it is an `EpicStatus` whose `epic_state` is `KILLED` — proven by a
   committed test. Both branches of `run`'s final `if` reach the same return, so
   both are worth pinning.
3. **Given** the diff, **When** the cause of the null is stated, **Then** it is
   stated in the commit message or in a comment at the point it was fixed —
   whether that is the return path, the data converter, or the sandbox. If the
   investigation ends without a cause, say so explicitly rather than declaring
   it fixed because a test now passes.
4. **Given** the diff, **When** the test is inspected, **Then** it fails against
   the unfixed behaviour — proven by committed output of the failing run. This
   story exists because a null slipped past every green suite twice; a test that
   has never been watched to fail proves nothing here.

### Edge Cases

- **A child that is terminated rather than completed.** `handle.result()` raises
  rather than returning; that path exists today and must keep working. The guard
  is for a *completed* child whose value is unreadable.
- **A child from an older worker, mid-deploy.** This is the version-skew case
  and it is the reason US1 must not be written as "handle None" but as "handle a
  result this code cannot interpret".
- **The probe running while Temporal itself is down.** US2-S5. It must say the
  server is unreachable, not that the scheduler is wedged.
- **A roadmap run that has legitimately completed and exited.** The schedule's
  runs drain and exit by design, so the probe must not read a completed run as a
  dead one.

## Requirements

### Functional Requirements

- **FR-001**: The roadmap MUST NOT raise when a completed child's result cannot
  be interpreted as an `EpicStatus`.
- **FR-002**: Such a spec MUST be recorded `landed=False`, kind `OBSERVED`.
- **FR-003**: The roadmap MUST continue dispatching after such a result.
- **FR-004**: The roadmap MUST record a failure and reach the notifier when it
  discards a child result it could not read.
- **FR-005**: The guard MUST be a runtime check, not a type annotation, and MUST
  cover malformed values as well as `None`.
- **FR-006**: A well-formed `EpicStatus` MUST derive landed status exactly as it
  does today.
- **FR-007**: `ergane roadmap status` MUST report a failing workflow task as a
  wedged roadmap and name the remedy.
- **FR-008**: A registered doctor probe MUST report a finding for a roadmap
  whose workflow task is failing, and MUST report nothing for a healthy or idle
  one.
- **FR-009**: That probe MUST distinguish a failing workflow task from an
  unreachable Temporal.
- **FR-010**: A committed test MUST assert `EpicWorkflow.run`'s **returned
  value** is an `EpicStatus`, for both the completed and killed conclusions.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  implements: [FR-007, FR-008, FR-009]
US3:
  depends_on: []
  implements: [FR-010]
```

No edges. The three stories touch disjoint production files — US1
`factory/roadmap/workflow.py`, US2 `factory/cli/roadmap.py` and
`factory/doctor/probes.py`, US3 `factory/workgraph/workflow.py` — and the plan
assigns each story its own test file by name, because 060 declared exactly this
kind of disjointness from the plan and was contradicted by the diffs: two of its
stories extended one test file that the Work Graph said they shared nothing in.
`depends_on` models what a story needs to exist, never what it will touch, so
the file assignment is written down rather than assumed.

US3 does not depend on US1 even though US1 makes it safe. If US3 lands first it
fixes the trigger, which is useful on its own; if US1 lands first the wedge is
closed regardless. Neither ordering is wrong, which is what "no edge" means.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A roadmap run whose child returns `None` dispatches the next spec
  in the same run — evidenced by committed test output, and by the run's own
  history if one is captured live.
- **SC-002**: After this lands, an epic completing does not require an operator
  to terminate the roadmap — evidenced by two consecutive epics dispatched by
  one roadmap run chain with no intervention between them.
- **SC-003**: `ergane roadmap status` against a wedged roadmap names the run and
  the remedy — evidenced by committed output of the command against a wedged
  fixture.
- **SC-004**: `ergane doctor` reports a finding for a wedged roadmap and none for
  a healthy one — evidenced by committed output of both runs.
- **SC-005**: `EpicWorkflow.run`'s returned value is asserted by a test that
  fails against the unfixed behaviour — evidenced by committed output of the
  failing run.

## Assumptions

- `LandedStatus(landed=False, kind=OBSERVED)` is the right record for an
  unreadable result, because it is already what a child that finished without
  landing everything gets, and its consequence — dependents stay blocked, the
  readiness report names it finished-but-not-landed — is exactly the consequence
  wanted here. No new state is needed and none should be added.
- The doctor is the right home for US2's detection because it is the only
  component that observes the system from outside a workflow. If a supervision
  probe already reaches Temporal, US2 extends it rather than adding a second.
- US3 may end without a root cause. That is an acceptable outcome provided it is
  stated plainly; what is not acceptable is a passing test presented as a fix
  when nobody knows why the value changed.
