# Tasks: the unpark test observes its held child before it wakes the roadmap

## Phase 1: User Story 1 — the unpark scenario has one deterministic order

- [ ] T001 [US1] Move the existing `_await_running(handle, "002-bravo")`
  barrier in `tests/test_roadmap_prompt_assembly.py` before the `tasks.md` edit
  and `unpark_spec` signal. Covers US1-S1 and US1-S4.
- [ ] T002 [US1] Keep the direct child release after the unpark signal and make
  the surrounding comments state the tested sequence precisely.
- [ ] T003 [US1] Restore exact ordered list equality for `dispatched`, including
  multiplicity; remove the set conversion. Covers US1-S2.
- [ ] T004 [US1] Run the focused test repeatedly and the complete
  `tests/test_roadmap_prompt_assembly.py` module. If evidence is committed,
  keep it bounded and generated from the final committed ordering.
- [ ] T005 [US1] Confirm the diff contains no production code, timeout increase,
  sleep-based synchronization, fixture-protocol change, or weakened assertion.
  Covers US1-S3.
