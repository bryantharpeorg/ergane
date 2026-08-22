---
state: landed
fixes:
  - worker/revision-interceptor-swallows-every-workflow-return-value
# Attested landed 2026-08-22. US1 602a62d8f8c6 (#281), observed on
# ergane-buildout, first attempt. This was the release blocker: the landed fix
# (factory/worker.py, the interceptor returning its awaited result) supersedes
# the operator hot-fix that ran uncommitted on the worker overnight, and the
# worker was restarted onto the landed revision on 2026-08-22 before the v0.2.0
# cut.
#
# READY. Drafted 2026-08-21 ~8:10 PM CT at the operator's instruction (tree at
# 4805fe7), reviewed and flipped by him ~10:20 PM CT after a pre-dispatch pass
# against c84869b. It dispatches behind 081 in numeric order.
#
# WHAT THE PRE-FLIP REVIEW CHANGED, so nobody re-derives it:
#   - **Three anchors were already dead.** 078/us3 added 97 lines to
#     `factory/workgraph/workflow.py` between drafting and review, moving every
#     citation into it by +28. Those are read-only context, and 079 and 081
#     land in that same file before this dispatches, so they are now cited by
#     quoted code rather than line number. The anchors you *edit* —
#     `factory/worker.py`, `tests/test_worker.py` — are untouched by anything
#     in the queue (`git log 4805fe7..c84869b --` on both is empty) and were
#     re-verified line by line: all 19 citations in this trio resolve.
#   - **The SDK settles the annotation.** `WorkflowInboundInterceptor.
#     execute_workflow` in the installed `temporalio.worker._interceptor` is
#     declared `-> Any` and its body is `return await
#     self.next.execute_workflow(input)` — read live. The fix restores the base
#     class verbatim; `-> Any` is the SDK's contract, not a preference.
#   - **`config()["interceptors"]` was an assumption and is now a fact.**
#     `interceptors` is a declared `WorkerConfig` key and `Worker.config()`
#     shallow-copies the config the worker was built with.
#
# WHY THIS EXISTS TONIGHT. This is the release blocker. The next PyPI cut was
# planned on 063 + 078, and every commit since v0.1.0 ships — including the
# defect below, which post-dates the tag. A fresh install gets a worker that
# swallows every workflow's return value. The cut waits for this story.
#
# WHAT THIS IS. 053-US3 (0ae48d6, 2026-08-18) added `_WorkerRevisionInterceptor`
# so every epic knows the worker revision that ran it. Its inner
# `execute_workflow` awaits the interceptor chain and drops the result:
#
#     async def execute_workflow(self, input: ExecuteWorkflowInput) -> None:
#         ...
#         await self.next.execute_workflow(input)      # awaited, never returned
#
# Python returns None from that path, so every workflow completing on a worker
# built by `build_worker` records a null result payload. The annotation says
# `-> None`, so no type checker objected; the tests proved the revision got
# *injected* and that the registration *polls*, and none of them ever executed
# a workflow and read its result back.
#
# THE MEASUREMENT, read out of Temporal history rather than remembered. On
# 2026-08-21 at 23:21:09Z, epic-063-the-readme-is-the-whole-truth completed;
# its WorkflowExecutionCompleted event carries one payload with encoding
# `binary/null` — while `EpicWorkflow.run`'s only return statement
# (`return self.epic_status()`, the last line of `run` in
# `factory/workgraph/workflow.py`) hands back a real `EpicStatus`. The
# interceptor sits between them. Detection came from 065-US1's child-result
# guard (`factory/roadmap/workflow.py:139`, landed 7c3adf3 on 2026-08-19):
# "discarded child result for 063-...: could not read returned value as
# EpicStatus (received NoneType)".
#
# THE BLAST RADIUS, each path live- or code-verified the same evening:
#   1. The roadmap discards every epic result and self-heals from git facts —
#      contained, but every epic completion pages the operator.
#   2. An escalation child's answer — the `return await child` inside
#      `_raise_escalation` in `factory/workgraph/workflow.py` — arrives as
#      None, so a pressed button is silently indistinguishable from expiry.
#   3. An answered agent question — `answered = await question` followed by
#      `answered.answered`, in the same file's question-park branch — raises
#      AttributeError inside workflow code: the epic wedges in a workflow-task
#      retry loop, and if the child completed under the broken worker the null
#      is in history forever and no later fix can read the answer back.
#
#   Those two sites are cited by the code they contain rather than by line
#   number ON PURPOSE. They are read-only context, and `workflow.py` is being
#   actively rewritten by the queue this spec sits behind — 078/us3 alone added
#   97 lines to it and moved every one of them by 28. Grep the quoted line.
#   Path 3 nearly fired live: 078/us1 parked on an operator question at
#   6:43 PM CT. The floor was verified quiescent and the operator blessed an
#   uncommitted one-line hot-fix plus a worker restart at 6:48 PM; the question
#   then resolved with a `json/plain` payload and the epic proceeded. That
#   hot-fix is deliberate dirt in the operator checkout and is discarded the
#   day this story lands.
#
# Filed as:
#   worker/revision-interceptor-swallows-every-workflow-return-value  CRITICAL, open
#   (the finding's first note attributed the defect to eb23d98/064-US1; that
#   commit merely touched the same file later. 0ae48d6/053-US3 introduced it,
#   corrected in the ledger when this spec was drafted.)
---

# Feature Specification: a completed workflow keeps its result

## The gap, stated precisely

A Temporal workflow's return value is part of its contract: parents await
children and act on what comes back. `build_worker`
(`factory/worker.py:233`) wires `_WorkerRevisionInterceptor` into every
workflow execution (`factory/worker.py:251`), and the interceptor's
`execute_workflow` (`factory/worker.py:265-270`) awaits the chain without
returning it. Every workflow that completes on this worker — epic, escalation,
question, roadmap — completes with a null payload, whatever its code returned.

The test gap is exact and worth naming, because this story exists to close it:
`test_temporal_accepts_the_registration` (`tests/test_worker.py:373`) hands the
production construction to a real time-skipping server and proves it polls;
053-US3's own tests (`tests/test_ergane_build.py`,
`tests/test_ergane_build_status_refusal.py`) prove the revision reaches the
workflow's query document. Nothing between them ever executed a workflow
through the production interceptor and read the result off the client. The
defect lived precisely in the seam no test crossed.

## The rule this spec is asking for

**An interceptor hands back what the intercepted workflow returned, and a test
executes a workflow through the production worker construction and reads the
result — so this class of defect cannot land silently again.**

### The ruling, made here rather than left to the implementer

- **The fix is the return, not a redesign — and the SDK already wrote it.**
  `WorkflowInboundInterceptor.execute_workflow` in the installed
  `temporalio.worker._interceptor` is, in its entirety:

  ```python
  async def execute_workflow(self, input: ExecuteWorkflowInput) -> Any:
      """Called to run the workflow."""
      return await self.next.execute_workflow(input)
  ```

  Read live from the installed SDK on 2026-08-21. The override drops the
  `return` and narrows `Any` to `None`; the fix restores the base class's own
  two properties verbatim. **This is not a judgement call about annotations —
  it is the contract the SDK declares**, which is why the spec rules `-> Any`
  and not `-> object` or a bare removal. The injection branch above it is
  053-US3's landed behavior and is not touched.
- **The regression test goes through `build_worker`'s own construction, not a
  hand-rolled Worker.** The defect survived because tests hand-rolled or only
  constructed. The production interceptor list is read off the built worker the
  same way the heartbeat test already reads its config
  (`tests/test_worker.py:368-369`, `build_worker(env.client)` then
  `built.config()`), and handed to a minimal worker that registers one
  test-local echo workflow. Executing a production
  workflow instead would drag real activities (Telegram sends, agent spawns)
  into a unit test; the interceptor is type-agnostic past its injection branch,
  so the echo workflow exercises the exact seam.

## What this spec does not change

- **The injection behavior.** 053-US3's revision injection — the `if` at
  `factory/worker.py:266-269` — keeps working, proven by its existing tests
  passing unmodified.
- **The running floor.** Landing this commit does not fix a running worker;
  the restart that loads it is an operator act, and worker deploy semantics
  are spec 082's whole subject. Nothing here touches supervision, systemd or
  restart logic.
- **The sibling findings.** The roadmap's defensive discard
  (`factory/roadmap/workflow.py:881-892`) stays exactly as 065-US1 built it —
  it is the guard that caught this and it guards against more than this. The
  open findings on the bare-workflow shadow and the unknown worker revision
  are different defects and out of scope.

## User Scenarios & Testing

### User Story 1 - The worker hands back what the workflow returned (Priority: P1)

As the parent of any child workflow — the roadmap awaiting an epic, an epic
awaiting an escalation or a question — I receive the value the child's code
returned, not None, so I can act on it instead of discarding it, mistaking it
for expiry, or crashing on it.

**Why this priority**: P1 and it is the whole spec, and the release blocker.
Every parent-child contract on this floor crosses this seam.

**Independent Test**: execute a workflow returning a known value through a
worker carrying the production interceptor list, and assert the client observes
that value.

**Acceptance Scenarios**:

1. **Given** a worker whose interceptor list is read off `build_worker`'s own
   construction, **When** a registered test workflow returning a known non-None
   value is executed to completion on the time-skipping server, **Then** the
   result the client observes equals that value — proven by a committed test
   that fails against the current tree and passes with the fix.
2. **Given** the same worker, **When** a test workflow that genuinely returns
   None completes, **Then** the client observes None — proven by a committed
   test. **The control**: after the fix, a null result means the workflow said
   None, never that the worker lost the answer.
3. **Given** the corrected interceptor, **When** 053-US3's existing tests run
   (`tests/test_ergane_build.py`, `tests/test_ergane_build_status_refusal.py`),
   **Then** they pass without modification — the revision injection this
   interceptor exists for is untouched.

## Requirements

### Functional Requirements

- **FR-001**: `_WorkerRevisionInterceptor`'s inner `execute_workflow` MUST
  return the value of `await self.next.execute_workflow(input)`, and its
  return annotation MUST be `Any` — matching
  `WorkflowInboundInterceptor.execute_workflow`'s own declaration in the
  installed SDK, quoted above.
- **FR-002**: A committed test MUST execute a workflow through the interceptor
  list read off `build_worker`'s construction and assert the client-observed
  result equals the workflow's return value, using the existing time-skipping
  environment shape (`tests/test_worker.py:348-353`).
- **FR-003**: A committed test MUST prove a None-returning workflow still
  completes with None observed.
- **FR-004**: 053-US3's revision-injection tests MUST pass unmodified.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
  persona: opus-closer
```

One story, one node. There is nothing to parallelize and nothing downstream.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the new round-trip test failing against the unfixed tree
  (the observed result is None where the workflow returned a value), then
  passing with the fix — both runs in the diff, red before green.
- **SC-002**: Paste the None-control test passing: the workflow returned None
  and None is what the client observed, now meaning what it says.
- **SC-003**: Paste the unmodified 053-US3 test files passing —
  `tests/test_ergane_build.py` and `tests/test_ergane_build_status_refusal.py`
  named in the run output — so injection is proven preserved by tests this
  story did not edit.

## Assumptions

- The time-skipping environment executes interceptors the same way a real
  server does. Grounded in use: `build_worker(env.client)` is already
  constructed against it twice in `tests/test_worker.py` (`:368` and `:382`),
  and the live incident plus the hot-fixed worker's behavior — a `json/plain`
  question payload and a full `EpicStatus` from 078's completion, both
  2026-08-21 — agree with what the test asserts.
- `built.config()["interceptors"]` exposes the production interceptor list.
  **No longer an assumption — verified against the installed SDK on
  2026-08-21**: `interceptors` is a declared key of `WorkerConfig`
  (`temporalio.worker._worker`), and `Worker.config()` returns a shallow copy
  of the config the worker was built with. Its `active_config` parameter
  defaults to False, which is the initial configuration — exactly the list
  `build_worker` passed. The heartbeat test already reads sibling keys off the
  same mapping (`tests/test_worker.py:369-371`).
- The operator checkout carries a semantically identical uncommitted hot-fix
  (`-> object` where this spec rules `-> Any`). An implementer never sees that
  tree; it is noted so nobody reads the dirt as a competing change. The dirt
  is discarded when this lands.
