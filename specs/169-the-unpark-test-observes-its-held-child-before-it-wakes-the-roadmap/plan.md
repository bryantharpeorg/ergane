# Implementation Plan: the unpark test observes its held child before it wakes the roadmap

Refined 2026-09-11 against `ergane-buildout` at `e28a7330abc2`. Resolve
citations by their named symbol if later landings move the line numbers.

## Current mechanism

- `tests/test_roadmap_prompt_assembly.py:415` — `_await_running` polls the
  roadmap's `roadmap_status` query until the named spec appears in `running`.
- `tests/test_roadmap_prompt_assembly.py:446` —
  `test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it`
  declares this sequence in its docstring: park 001, hold 002 in flight, edit
  001, unpark 001, release 002, then observe 001 dispatch.
- `tests/test_roadmap_prompt_assembly.py:475` — the test configures
  `_SCRIPT.hold = {"002-bravo"}`.
- `tests/test_roadmap_prompt_assembly.py:401` — `_await_park` returns before
  the same scheduling pass is required to start 002; its own helper docstring
  says a returned park proves nothing about whether the child has started.
- `tests/test_roadmap_prompt_assembly.py:446` —
  `test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it`
  calls `unpark_spec` before it calls `_await_running`.
- `tests/test_roadmap_prompt_assembly.py:494` — the landed retry converts the
  dispatch list to a set, hiding both order and duplicate dispatches.
- `tests/roadmap_script.py:111` — `ScriptedEpicWorkflow.run` honors
  `_SCRIPT.hold` through its existing `workflow.wait_condition`; this seam is
  already sufficient and remains unchanged.

## Proven failure mechanism

On PR500's exact failed merge head `13e58aee1af2`, the target test passed four
times and failed once in an instrumented loop. The failed history ran
`001-runtime-root` first after the early unpark, completed the original roadmap
run through continue-as-new, and only then started the held `002-bravo` child.
The test kept querying the original run handle, which could never report the
new run's child, and timed out after 30 seconds. This matches the earlier
finding evidence: moving the existing wait before the edit and signal passed
ten repetitions; restoring the old order reproduced the failure.

## Implementation

1. In
   `test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it`
   (`tests/test_roadmap_prompt_assembly.py:446`), move the existing
   `_await_running(handle, "002-bravo")` call to immediately after the three
   park assertions and before the `tasks.md` edit.
2. Keep the edit and `unpark_spec` signal together after that state barrier.
3. Keep the direct `epic-002-bravo` release after the signal. Update the nearby
   comments so they describe the actual ordering barrier.
4. Replace `assert set(dispatched) == {...}` with exact ordered list equality.
5. Run the focused test repeatedly, then run the whole
   `tests/test_roadmap_prompt_assembly.py` module. A committed evidence file is
   optional; if added, keep it concise and inside the story's diff budget.

## Traps

1. **The signal is the race trigger.** Waiting after `unpark_spec` preserves
   the defect even if it passes locally. The wait must precede both the edit
   and the signal so the test matches the four-step sequence in its docstring.
2. **Do not fix a test race in production.** `RoadmapWorkflow` correctly
   continues as new when its children are quiescent. Changing the scheduler to
   accommodate a client holding an old run handle would widen the story and
   change valid behavior.
3. **Do not use elapsed time as synchronization.** No sleep can establish that
   002 is recorded in the queried run. `_await_running` is the existing state
   barrier and is the only allowed seam.
4. **Order is evidence.** The finding exists because PR478 replaced ordered
   equality with set equality. Restoring the exact list is part of the repair,
   not an optional cleanup.
5. **Keep the negative control temporary.** If the old ordering is replayed to
   demonstrate red, restore the repaired ordering before commit; only committed
   evidence is judge-visible.

## Scope

One test file, with an optional small evidence artifact. No production module,
fixture protocol, workflow timeout, dependency, manifest, or generated graph
changes.
