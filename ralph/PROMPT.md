# Ralph iteration — implement one task of specs/{{SPEC}}/

You are ONE iteration of an autonomous loop. The only durable state is
`specs/{{SPEC}}/tasks.md` and git history — your context is disposable.
Complete exactly ONE task, then stop.

1. **Select**: Read `specs/{{SPEC}}/tasks.md`. Pick the FIRST task whose
   checkbox is `[ ]` and whose dependencies (per the Dependencies section and phase
   ordering) are all `[X]`. Selection is mechanical — no judgment, no skipping ahead.
   If every task is `[X]`, print `RALPH_DONE` and stop immediately.
2. **Load context for that task only**: `specs/{{SPEC}}/plan.md` always;
   `data-model.md`, `research.md`, or files under `contracts/` only if the task
   touches what they describe. Read `.specify/memory/constitution.md` once and obey
   it (test-first is non-negotiable; no dependencies beyond the approved roster;
   never put credentials in code, logs, or committed files).
3. **Implement the task exactly as written.** A test task writes the test and runs
   it to confirm it FAILS for the right reason. An implementation task makes the
   previously-written failing tests pass. Do not implement ahead of the task.
4. **Gate**: run `uv run pytest -q`. A just-written test may be red only if its
   implementation task is still unchecked; anything previously green must stay
   green. Never weaken a test to pass the gate.
5. **Land it atomically**: mark the task `[X]` in tasks.md, then
   `git add -A && git commit -m "T0NN: <task description>"` (tasks.md and the work
   in the same commit).
6. **Stop.** Do not begin the next task.

If the selected task cannot be completed: revert your changes
(`git checkout -- . && git clean -fd` on anything you created), append one line to
`specs/{{SPEC}}/BLOCKED.md` (`T0NN — reason — recommended fix`), leave the
checkbox unchecked, print `RALPH_BLOCKED T0NN`, and stop.
