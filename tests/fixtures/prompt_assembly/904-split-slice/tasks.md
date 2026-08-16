# Tasks: The agent sandbox (reconstructed)

**This is the defect, and it refuses nothing.** The Tests and Implementation
groups of each story are both written at phase level (`##`), so the slice cut
for a story runs from its Tests heading to the *next* heading of the same
depth — its own Implementation heading. Every node assembles a prompt; every
node's prompt contains that story's tests and none of its implementation.

The tasks below say which story they belong to, so what the slices drop is
computable offline: `T002`, `T003` and `T005` name a story whose slice does not
contain them.

## Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the detection case FIRST: an attempt that edits a
      file outside its own worktree is detected at teardown
      (spec US1-S1) — must fail.

## Implementation for User Story 1

- [ ] T002 [US1] Capture the target repository's tracked-file state at attempt
      start and compare it at teardown.
- [ ] T003 [US1] Record the escape under a stable key so recurrence is countable.

## Tests for User Story 2 (write FIRST, must fail)

- [ ] T004 [P] [US2] Write the containment case FIRST: an agent writing an
      absolute path outside its worktree is refused (spec US2-S1) — must fail.

## Implementation for User Story 2

- [ ] T005 [US2] Put the agent launch behind a substitutable seam and give the
      boundary the worktree as its only writable path.

## Verification

- [ ] T006 Run the full suite on a host with no container runtime installed and
      paste the summary line.
