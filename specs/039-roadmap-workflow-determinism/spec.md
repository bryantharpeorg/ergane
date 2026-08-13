---
state: landed
# Attested landed 2026-08-13 23:33Z. US1 46f7e8ba89a6 (PR #63), US2
# 35d7c66c09fb (PR #64) — both observed on ergane-buildout, both attempt 1,
# both with their red-then-green transcripts committed without being chased.
# US1 took FR-002's route 2 (resolve inside the activity) and said why in its
# commit, as the plan asked.
# Operator verification, independent of the gate:
#   US1 — the new sandbox test passes on the fixed tree. (An operator mutation
#         attempt was malformed and broke collection; it proved nothing and is
#         recorded here rather than dressed up. The agent's own committed
#         transcript does show the RestrictedWorkflowAccessError on reverted
#         code, and that evidence stands.)
#   US2 — MUTATION CONFIRMED: injecting `os.environ.get("SNEAKY")` as the first
#         statement of the workflow's run() made the guard fail with
#         "factory/roadmap/workflow.py:640: run() reads process environment:
#         os.environ" — module and function named, per FR-007. The guard also
#         passes on the real tree, so it correctly ignores the two prose
#         comments in workgraph/workflow.py that a grep guard would flag.
# Flipped ready 2026-08-13 22:52Z on the operator's word ("I want to fix the
# roadmap workflow so work loads automatically"). Dispatched by hand the same
# minute — the roadmap cannot dispatch it, since the roadmap is what it fixes.
# Pre-dispatch verification done at 023d42b before the flip: `ergane spec
# validate` clean, graph derives to us1 -> us2 on a merge edge, preflight
# reports no findings, and all twelve of plan.md's line anchors were checked
# against the tree by hand. Two claims were chased: workgraph/workflow.py's two
# `environ` grep hits are prose comments (the module is clean, and this became
# trap 6's exhibit for requiring `ast` over grep), and notify_activities'
# legitimate activity-context read sits at :649.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `roadmap/success-path-reads-environ-inside-the-workflow` (critical,
# recurrence 3), then refined against the tree at 54e1153 on 2026-08-13 —
# after 030 landed, deliberately, because 030 moved `tests/conftest.py` and the
# roadmap test harnesses this spec's regression test has to live beside.
# Authorized by the operator on 2026-08-13 ("once 30 finishes, begin working on
# the roadmap fix"). The schedule has been PAUSED since 17:53Z and stays paused
# until US1 lands.
---

# Feature Specification: A scheduler that cannot report its own success

## The defect in one sentence

`_verification_db_path()` reads `os.environ` from inside workflow code, the
Temporal sandbox refuses it, the workflow task fails and retries forever, and
because the schedule skips new fires while a run is in flight, **one wedged run
silently disables the roadmap indefinitely**.

## The mechanism, verified against the tree

`factory/roadmap/workflow.py:136-140`:

```python
def _verification_db_path() -> str:
    """The store path the worker environment names, defaulting to the standard one."""
    from os import environ

    return environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH
```

It is called from *workflow* context at two sites — `:922` in
`_report_roadmap_failure` and `:956` in `_report_run_success` — and the sandbox
answers:

```
Cannot access os.environ.get from inside a workflow. If this is code from a
module not used in a workflow or known to only be used deterministically from
a workflow, mark the import as pass through.
```

Four properties make this worse than an ordinary crash, and each one is a
design lesson the fix has to answer:

1. **It is only reachable on success.** Both call sites belong to the
   failure-and-recovery *notifier*, and `_report_run_success` runs when a
   roadmap pass completes cleanly. Every earlier run died at preflight, so the
   defect sat unreached from the day 031 landed until the day the scheduler
   first worked end to end.
2. **The failure is a workflow task failure, not an activity failure.** Nothing
   in the notify path fires, so 031 — the component whose entire job is to tell
   the operator the scheduler broke — is silent about the thing breaking it.
3. **One wedge disables everything after it.** The schedule's overlap policy
   skips a fire while a run is in flight, and a workflow stuck in a
   `WORKFLOW_TASK_FAILED` retry loop is in flight forever.
4. **Nothing surfaced it.** It was found only because an unrelated host probe
   alerted on a different problem and sent the operator looking.

Observed live: run `roadmap-specs-2026-08-13T12:45:00Z` crashed at 16:21:24Z the
instant epic 027 completed, then looped for 95+ minutes until the operator
terminated it. Every fire from 12:45Z onward did nothing; epics 028/us3, 025 and
030 all reached the queue only because a human typed `ergane build start`.

Origin: the helper arrived with 021-roadmap-operability/us4 (`e4e90c3`), where it
was called from *activity* context and was correct. 031-scheduler-failure-notify/us1
(`867d337`) added the two workflow-context callers that make it fatal.

## Scope, already scanned

`grep -rln '@workflow.defn' factory/` returns exactly two modules.
`factory/workgraph/workflow.py` is clean — no `environ` or `getenv` read
anywhere in it. `factory/roadmap/workflow.py` has exactly one, the helper above.
**The defect is one function and two callers, and the guard surface is two
files.** The implementer does not need to repeat this scan, but US2's guard must
find the same answer by construction rather than by hardcoding the two names.

## User Scenarios & Testing

### User Story 1 - The success path must not read the environment (Priority: P1)

Move the store path out of workflow scope, and prove the success path survives a
real sandbox.

**Goal**: a roadmap run that completes cleanly reports its success and finishes,
instead of wedging the schedule.

**Why this priority**: nothing dispatches unattended until this lands. It is the
only work in the corpus that buys back autonomy rather than adding capability.

**Independent Test**: run a roadmap pass end to end under the real Temporal
sandbox, with a prior failure recorded so the recovery branch is taken, and
watch it reach a completed state.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree, never a test run
(constitution VIII). Where a scenario asks for runtime behaviour, it is met by
an artifact the diff contains: tool output **pasted verbatim** into a comment
block in the test file, never described or summarized.

**Acceptance Scenarios**:

1. **Given** the roadmap workflow, **When** the diff is inspected, **Then**
   `_verification_db_path()` is no longer called from workflow scope — neither
   `_report_roadmap_failure` nor `_report_run_success` reaches `os.environ`,
   directly or through a helper — and the path they hand to their activity
   arrives from outside the workflow.
2. **Given** a roadmap pass that completes cleanly with a prior failure recorded,
   **When** it runs under the real Temporal test environment with the sandbox
   enabled, **Then** a test exercising that exact path exists in the diff and the
   pasted transcript shows it passing.
3. **Given** the same test, **When** the fix is reverted and the test re-run,
   **Then** the pasted transcript shows it failing with
   `RestrictedWorkflowAccessError`, and shows it passing again once the fix is
   restored. Both halves of that transcript are in the diff.
4. **Given** the landed story, **When** the diff is inspected, **Then** the
   sandbox is not disabled, no module is marked pass-through to silence the
   error, and no test asserts the wedge is acceptable — the sandbox is the thing
   that caught this, and weakening it is the forbidden fix.

### User Story 2 - No workflow module may read the environment again (Priority: P2)

A guard that finds the class, not the instance.

**Goal**: reintroducing an environment read at workflow scope fails a test
instead of disabling the scheduler.

**Why this priority**: US1 fixes one function. This is a defect the tree has
already produced once by accident, in a component whose failure is silent, and
the scan surface is two files — so the guard is cheap and the failure it
prevents is expensive.

**Independent Test**: add an `os.environ` read back into a workflow-scoped
function and watch the guard fail, naming the offending module and function.

**Evidence rule for every scenario below**: as US1 — runtime claims are met by
verbatim pasted output committed in the diff.

**Acceptance Scenarios**:

1. **Given** the guard, **When** the diff is inspected, **Then** it discovers
   workflow-defining modules **by construction** — scanning for the workflow
   decorator across `factory/` — rather than by naming the two known modules, so
   a third module added later is covered without editing the test.
2. **Given** the tree with US1 landed, **When** the guard runs, **Then** it
   passes, and the pasted transcript shows it.
3. **Given** an `os.environ` read reintroduced into a workflow-scoped function,
   **When** the guard runs, **Then** it fails and names the module and the
   function; the pasted transcript shows that failure, and shows the guard green
   again once the reintroduction is reverted.
4. **Given** the guard, **When** the diff is inspected, **Then** it does not
   forbid environment reads in *activity* functions or at module import time —
   `_verification_db_path` was correct for two months in activity context, and a
   guard that bans the read everywhere would be wrong about the code it is
   protecting.

## Functional Requirements

- **FR-001**: `_report_roadmap_failure` and `_report_run_success` MUST obtain the
  evidence-store path without reading the process environment from workflow
  scope.
- **FR-002**: The path MUST arrive by one of two routes — carried on the
  workflow's input from the caller that starts it, or read inside the activity
  that already receives `db_path`. Both call sites already pass `db_path` to
  their activity, so no new activity is required.
- **FR-003**: A test MUST exercise a roadmap pass that completes cleanly, under
  the real Temporal test environment with the workflow sandbox enabled, taking
  the recovery branch that `_report_run_success` guards.
- **FR-004**: That test MUST fail on the pre-fix code with
  `RestrictedWorkflowAccessError`, and the diff MUST carry the verbatim
  red-then-green transcript proving it.
- **FR-005**: The fix MUST NOT disable the workflow sandbox, mark any module
  pass-through, or otherwise suppress the sandbox's diagnosis.
- **FR-006**: A guard test MUST discover every module defining a Temporal
  workflow by scanning `factory/`, and fail if any function reachable at
  workflow scope in those modules reads the process environment.
- **FR-007**: The guard MUST name the offending module and function in its
  failure message.
- **FR-008**: The guard MUST NOT flag environment reads in activity functions or
  at module import time.
- **FR-009**: Neither story MUST change the roadmap's observable behaviour on the
  failure path — the `roadmap_failures` count, its reset semantics and the notice
  text MUST stay exactly as 031 landed them.

## Success Criteria

- **SC-001**: A roadmap pass that completes cleanly reaches a completed state
  rather than a `WORKFLOW_TASK_FAILED` retry loop.
- **SC-002**: Reintroducing the defect fails a test rather than disabling the
  scheduler.
- **SC-003**: The full suite is green, and the guard adds no live-service
  dependency — it reads source, it does not run a workflow.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-009]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008]
```
