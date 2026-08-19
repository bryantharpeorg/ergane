# Implementation Plan: the scheduler survives its children

**Spec**: `specs/065-the-scheduler-survives-its-children/spec.md`

## What already exists, and where

Every line below was read on 2026-08-19. Check each against the tree before you
rely on it — 060 proved that a plan citing a moved anchor costs the attempt, not
the plan.

**US1 — the reap path:**

- `factory/roadmap/workflow.py:820-835` — the reap loop. Line 828-831 carries a
  comment explaining why `handle.result()` is a non-async accessor; leave that
  reasoning intact, it is correct and non-obvious.
- `factory/roadmap/workflow.py:832` — `status: EpicStatus = handle.result()`.
  **This line is the defect.**
- `factory/roadmap/workflow.py:833` — `self._landed[spec_dir] =
  self._landed_status_for(status)`.
- `factory/roadmap/workflow.py:1308-1325` — `_landed_status_for`, a
  `@staticmethod`. Line 1319 is `status.epic_state`, where the `AttributeError`
  is raised.
- `factory/roadmap/models.py:444` — `LandedStatus(landed: bool, kind: LandedKind)`.
- `factory/roadmap/models.py:94-104` — `LandedKind`, with `OBSERVED`. Its
  docstring already distinguishes `ATTESTED` (the operator's word) from
  `OBSERVED` (the system's), which is why `OBSERVED` is the right kind here.
- `factory/roadmap/workflow.py:955` — `_report_roadmap_failure(request,
  failure_text)`. This is the seam FR-004 needs. It is `async` and executes
  activities, so it can be awaited from the reap loop.

**US2 — the surfaces:**

- `factory/cli/roadmap.py:382` — where the query error becomes
  `cannot query roadmap '<name>': <error>`. The Temporal text to recognise is
  `Unable to query workflow due to Workflow Task in failed state`.
- `factory/doctor/probes.py` — `REGISTRY`, plus `Probe`, `FindingReport` and
  `ServiceNotAnswering`, all imported by `factory/doctor/cli.py:22`.
- `factory/doctor/cli.py:215-226` — `for probe in REGISTRY`, and the rule that a
  skipped probe (its service did not answer) forces exit 2. `ServiceNotAnswering`
  is how US2-S5's "Temporal is unreachable" case is expressed — it already
  exists, do not invent a second vocabulary for it.
- `factory/roadmap/discovery.py` — how the other verbs find a live roadmap
  without hardcoding a schedule id. The probe needs the same resolution.

**US3 — the return:**

- `factory/workgraph/workflow.py:616` — `async def run(self, request: EpicInput)
  -> EpicStatus`.
- `factory/workgraph/workflow.py:795-811` — the tail of `run`: the
  `_kill_requested` branch sets `KILLED`, the `else` sets `COMPLETED`, and both
  fall to `return self.epic_status()` at `:811`. Confirmed by AST walk that this
  is the **only** `Return` node in the function.
- `factory/workgraph/workflow.py:583` — `epic_status` is decorated
  `@workflow.query`. Verified empirically on temporalio 1.31.0 that a direct
  call to a `@workflow.query`-decorated method returns the underlying value, so
  the decorator is not an obvious explanation.

**Test seams that already exist — use them, do not build new ones:**

- `tests/roadmap_script.py` — a scripted `EpicWorkflow` registered under the real
  dispatch name, steered by a module-level `_SCRIPT` whose `statuses` maps a spec
  dir to the `EpicStatus` its child returns. **US1's entire reproduction is
  making one entry in that map return `None`.** Read its docstring first: the
  class lives outside the test module deliberately, because the workflow sandbox
  traces the defining module.
- `tests/test_roadmap_scheduler.py` — drives the roadmap under time skipping with
  those scripted children, and already contains a `start_child_workflow`
  interceptor.
- `tests/test_roadmap_failure_notifications.py` — where FR-004's assertion
  belongs.

## Traps

**1. The annotation is the bug. Do not fix it with a better annotation.**
`status: EpicStatus = handle.result()` already declares the type, and declaring
it is what let a null through. US1-S5 requires a test that fails when the guard
is removed. If your diff changes the annotation, adds a `cast`, or adds a
`# type: ignore`, you have not written a runtime check.

**2. Handle "cannot be interpreted", not "is None".** US1-S4 and the version-skew
edge case. `None` is one member of the class. A dict, an object from an older
worker's dataclass, or anything without `epic_state` must take the same path. A
guard written as `if status is None` passes US1-S1 and fails the story.

**3. Surviving is not swallowing.** FR-004. A child result the roadmap threw away
is a fact the operator must be told, and `_report_roadmap_failure` is right there
at `:955`. A silent recovery converts a loud permanent stall into a quiet
wrong answer, which is worse — the epic would be recorded not-landed forever and
nobody would know why.

**4. Do not touch the healthy path.** US1-S6. The existing scheduler tests pass
today and must pass unchanged. If you find yourself editing `_landed_status_for`'s
derivation of `completed and all_merged`, stop: the guard belongs before that
function is called, or at its entry, not inside its logic.

**5. `_report_roadmap_failure` is async and the reap loop is workflow code.**
Awaiting it inside the reap loop is fine — the loop already awaits
`workflow.wait_condition` — but be aware you are adding an activity call to a
path that previously made none, and the loop iterates over `list(self._children.items())`
while deleting from `self._children`. Do not restructure that iteration.

**6. Determinism.** This is workflow code. No `datetime.now()`, no `random`, no
filesystem, no environment reads. 039 landed because a workflow read
`os.environ` and silently disabled the whole schedule; that is the same file you
are editing. Anything non-deterministic goes in an activity.

**7. The probe must not fire on idle.** US2-S4. A roadmap at its epic cap has
dispatched nothing and is perfectly healthy — that is most of a normal day. A
probe that cannot tell idle from wedged will be switched off, and then the next
wedge is invisible again. The distinguishing fact is the *failing workflow task*,
not the absence of dispatch.

**8. A completed run is not a dead run.** The schedule's runs drain and exit by
design, every five minutes. The probe reads a run that has completed as normal.

**9. `ServiceNotAnswering` already exists for US2-S5.** `factory/doctor/probes.py`
defines it and `factory/doctor/cli.py` already forces exit 2 on it. Unreachable
Temporal is a skipped probe, not a wedged-roadmap finding.

**10. US3 is a contract story, not a debugging expedition.** The buildable
version is: write the test that asserts the *returned value*, watch it fail, then
find why. If you start by reading the SDK looking for the cause, you will spend
the attempt and produce nothing committable. Get the red test first — it is the
reproduction, and a reproduction in hand is what has landed the hard stories here.
If the cause does not fall out within the attempt, US3-S3 explicitly permits
saying so; it does not permit implying a fix you did not find.

**11. Assert the return, not the query.** US3-S1. `epic_status()` as a query has
worked throughout both incidents — the operator CLI read node states correctly
the entire time the roadmap was wedged. A test that calls the query proves
nothing about the defect.

**12. One test file per story, named here, because 060 got this wrong.**
060's Work Graph asserted its stories shared no files; two of them extended
`tests/test_ergane_install_walkthrough.py` and only luck in landing order avoided
a second conflict. So:
- US1 → `tests/test_roadmap_child_result.py` (plus assertions in
  `tests/test_roadmap_failure_notifications.py` for FR-004)
- US2 → `tests/test_roadmap_wedge_visibility.py`
- US3 → `tests/test_epic_returns_status.py`
If you need to touch a file assigned to another story, that is a signal the edge
declaration is wrong — say so rather than editing across the line.

**13. The judge sees the diff and the criteria, nothing else.** SC-001 through
SC-005 all require committed output. Paste the failing runs and the command
output into the diff; a description of what you observed is not evidence of it.

## Sizing

Three small stories, and US1 is the only one that matters for the outage.

US1 is a guard, a branch, and a test that scripts one existing fixture to return
`None`. The reproduction already exists in `tests/roadmap_script.py`; this is
perhaps twenty lines of production code.

US2 is a probe and an error-message improvement. The probe is the larger half,
and its risk is entirely in trap 7 — getting idle-versus-wedged right.

US3 is a test plus an unknown. Its floor is the test; its ceiling is unbounded,
which is why trap 10 constrains the method and US3-S3 permits an honest
non-answer.

## Verification the operator will run, independent of the gate

- **Prove US1 by scripting the null.** Point a scripted child at `None`, run the
  scheduler test, and confirm the roadmap dispatches the *next* spec. Then remove
  the guard and confirm the test fails. A guard nobody has watched fail is a
  guard nobody has tested.
- **Prove US1 live, which is the only proof that counts.** Let two epics complete
  back to back under one roadmap run chain with no operator intervention. That is
  SC-002 and it is the thing that has never happened on this host.
- **Prove US2 by wedging a fixture.** Put a roadmap into a failing-workflow-task
  state, run `ergane roadmap status` and `ergane doctor`, and read both outputs
  as a stranger would: does either tell an operator what to do next?
- **Prove US3 by control.** Confirm the new test fails against `HEAD` before the
  fix. If it passes before the fix, it is testing something else.
