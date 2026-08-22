# Implementation Plan: a completed workflow keeps its result

**Spec**: `specs/086-a-completed-workflow-keeps-its-result/spec.md`

## What already exists, and where

**Every line number below was verified twice on 2026-08-21 by printing that
exact line individually** — at drafting against ergane-buildout 4805fe7, and
again on the pre-flip review against c84869b, after 078 had fully landed.

The `factory/worker.py` and `tests/test_worker.py` anchors are the ones you
edit, and they are the ones that hold: `git log 4805fe7..c84869b -- factory/worker.py
tests/test_worker.py` is **empty**, and no spec in the queue ahead of you
(079, 081) names either file in its edit surface. Every anchor into
`factory/workgraph/workflow.py` is read-only context and is cited by quoted
code instead, for the reason given in that section. Check each one anyway.

**The defect — `factory/worker.py`:**

- `:233` — `def build_worker(client: Client) -> Worker:` — the production
  construction, the only place the interceptor is wired.
- `:251` — `interceptors=[_WorkerRevisionInterceptor(_WORKER_REVISION)],`
- `:255` — `class _WorkerRevisionInterceptor(Interceptor):`
- `:265` — `async def execute_workflow(self, input: ExecuteWorkflowInput) -> None:`
  — the annotation that let this land.
- `:266-269` — the injection branch: `if input.type == "EpicWorkflow" and
  input.args:` … `input.args = (replace(original, worker_revision=revision),)`.
  053-US3's landed behavior. Not yours to touch.
- `:270` — `await self.next.execute_workflow(input)` — **the line. Awaited,
  never returned.**
- `:53-68` — the import block. No `typing` name is imported anywhere in this
  file (grep-verified), so `Any` needs `from typing import Any` added among
  the stdlib imports (`:55-61`).

**The harness you extend — `tests/test_worker.py`:**

- `:348-354` — the `env` fixture: `@pytest.fixture` (`:348`), `async def env()`
  (`:349`), `WorkflowEnvironment.start_time_skipping()` (`:350`), and
  `await environment.shutdown()` in the `finally` (`:354`). Five lines; copy
  them.
- `:357-371` — `test_the_worker_caps_heartbeat_throttle_to_hold_kill_latency`
  (def at `:357`): `built = worker_module.build_worker(env.client)` (`:368`),
  `cfg = built.config()` (`:369`), then asserts against `cfg[...]` (`:370-371`).
  **This three-line shape is how you lift the interceptor list** without
  importing the private class.
- `:374` — `async def test_temporal_accepts_the_registration(env:
  WorkflowEnvironment) -> None:`, which builds the production worker again at
  `:382` and proves it polls. **It never executes a workflow** — the gap this
  story closes sits immediately after this test.

**The base class you are restoring — the installed
`temporalio.worker._interceptor`:**

```python
class WorkflowInboundInterceptor:
    async def execute_workflow(self, input: ExecuteWorkflowInput) -> Any:
        """Called to run the workflow."""
        return await self.next.execute_workflow(input)
```

Read live off the installed SDK on 2026-08-21 (`inspect.getsource`). The
override in `factory/worker.py` drops the `return` and narrows `Any` to
`None`. **You are restoring two properties the base class already declares**,
which is why `-> Any` is ruled and not open. Confirm it yourself the same way
before you edit; if a later SDK changes the declaration, follow the SDK.

**The proof the value exists to lose, and the consumers that establish
severity — all in `factory/workgraph/workflow.py` (read, do not edit):**

**These are cited by quoted code, not line number, deliberately.** That file is
being rewritten by the queue this spec sits behind: 078/us3 alone added 97
lines and moved every one of these by 28 between this spec's drafting and its
first review, and 079 and 081 land in it before you start. Line numbers here
would be dead on arrival — grep the quoted line instead.

- `async def run(self, request: EpicInput) -> EpicStatus:` — the epic entry
  point, and `return self.epic_status()`, the single return at the end of it.
  That value is what the interceptor currently discards.
- `return await child` inside the escalation helper — the pressed-button path.
- `answered = await question`, followed by `answered.answered` — the question
  path; that attribute access on None is the epic-wedging AttributeError.
- `factory/roadmap/workflow.py` — `def _is_epic_status(` at `:139` (065-US1's
  guard) and the block that detected this live: `status = handle.result()`
  (`:882`), `if not _is_epic_status(status):` (`:883`), the
  `_report_roadmap_failure` call (`:885`) carrying `f"discarded child result
  for {spec_dir}: "` (`:887`), and the `landed=False, kind=LandedKind.OBSERVED`
  fallback (`:892`). That file is untouched since this spec was drafted, so
  these hold. Left exactly as 065-US1 built it.

**053-US3's injection tests (the control, run unmodified):**

- `tests/test_ergane_build.py` and `tests/test_ergane_build_status_refusal.py`
  — added by 0ae48d6. They prove the revision reaches the query document. They
  are FR-004's whole content: run them, do not edit them.

## Traps

**1. Deployment is not this story.** Landing the commit does not fix the
running worker — the restart that loads it is the operator's act, and worker
deploy semantics are spec 082's subject. Touch nothing under
`factory/supervision/` and nothing about systemd or restarts. Your diff is one
production file and one test file.

**2. The operator checkout carries this fix as deliberate uncommitted dirt.**
`-> object` where the spec rules `-> Any`, same `return await`. Your worktree
is cut from the landing branch and will never contain it. If you inspect the
live floor and see it, it is not a competing change and not yours to reconcile
— the operator discards it when you land.

**3. Test through `build_worker`, not a hand-rolled interceptor.** The defect
survived three days because every test either hand-rolled the pieces or
stopped at construction. Read the interceptor list off
`build_worker(env.client).config()` — the `:368-370` pattern — and hand it to a
minimal Worker registering one test-local echo workflow on a scratch task
queue. Do not import `_WorkerRevisionInterceptor` by name into the test: the
private name is not the contract, the wired list is.

**4. Do not execute a production workflow in the test.** `EpicWorkflow`,
`QuestionWorkflow` and their siblings schedule real activities (Telegram
sends, agent spawns) the moment they run. The interceptor is type-agnostic
past its injection branch, so a test-local echo workflow exercises the exact
seam. Executing a production workflow here is how a unit test grows a network
dependency — and this host has already been OOM-killed by test-spawned
orphans once (`hardening/orphaned-test-servers-exhaust-host-memory`).

**5. Red before green, and the red is pasted.** SC-001 wants the round-trip
test failing against the unfixed tree in the committed evidence. Write the
test first, run it, capture the failure, then fix. A test born green proves
nothing about this defect.

**6. One test file for the story:**
`tests/test_a_completed_workflow_keeps_its_result.py`. The `env` fixture is
local to `tests/test_worker.py`, not a conftest export — copy its five lines
(`:348-353`) rather than importing across test modules.

**7. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). All three SCs are pasted-output criteria; the pastes are
committed in the diff or the criterion is unprovable.

## Sizing

The smallest story this factory has dispatched: a one-line semantic change, an
annotation, an import, one new test file with two tests, and three pasted
runs. The most likely cause of a second attempt is trap 3 — hand-rolling the
interceptor because lifting it off `config()` feels indirect — or trap 5,
skipping the committed red run.

## What else is in flight, and why it does not collide

Tonight's queue is 078 → 079 → 081. None of their specs edits
`factory/worker.py` or `tests/test_worker.py` (verified by reading their
plans' edit surfaces at draft time). Specs 083/084/085 are held at draft; 083
and 085 name `factory/cli/roadmap.py` and 084 names the verify surface —
none touches this story's two files.

## Verification the operator will run, independent of the gate

- **Restart the worker after this lands and watch the next epic complete**:
  the roadmap must record its landed status with no "discarded child result"
  page. That page not appearing is the live proof.
- **Ask a live epic's node a question and answer it** (or wait for the next
  organic one): the answer must reach the next attempt verbatim, as it did on
  2026-08-21 only after the hot-fix.
- **Diff the landed interceptor against the operator checkout's dirt, then
  discard the dirt** — `git checkout -- factory/worker.py` in the operator
  tree once the landed line is present there.
