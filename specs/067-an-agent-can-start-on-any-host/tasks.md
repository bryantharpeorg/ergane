# Tasks: an agent can start on any host

**Spec**: `specs/067-an-agent-can-start-on-any-host/spec.md`
**Plan**: `specs/067-an-agent-can-start-on-any-host/plan.md`

Read the plan's traps before the first task. Trap 1 (never assert a `/lib64`
literal — this host is aarch64), trap 2 (read the host, do not widen the
constant) and trap 9 (one test file per story) are the three that decide whether
an attempt lands.

## Phase 1: User Story 1 — The sandbox mount set is read from the host

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_sandbox_mount_set.py`, supply a
      host layout in which `/lib64` is a symlink and assert the agent sandbox
      argv carries a `--symlink` entry for it with that symlink's own target.
      Supply the layout; never read the real root (trap 1).
- [ ] T002 [P] [US1] (spec US1-S2) Assert a layout without `/lib64` yields no
      `/lib64` entry. This is the over-correction guard (trap 2).
- [ ] T003 [P] [US1] (spec US1-S3) Assert each of `/bin`, `/lib`, `/lib64`,
      `/sbin` is emitted if and only if it is a symlink on the supplied layout,
      over a layout where the four differ, so the test cannot pass by treating
      them as a fixed set.
- [ ] T004 [P] [US1] (spec US1-S4) Assert the agent boundary and the gate boundary
      produce the same system-tree entries for one supplied layout — the
      assertion that FR-003's shared implementation actually is shared.
- [ ] T005 [P] [US1] (spec US1-S6) Assert a required system path that is neither
      symlink nor directory produces a named refusal **before the fork**,
      following `ToolchainError`'s precedent in `factory/verify/toolchain.py`.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002) Write one shared derivation that walks `/bin`,
      `/lib`, `/lib64`, `/sbin` and emits `--symlink <readlink(p)> <p>` for each
      that is a symlink on the host. Put it where both boundaries can reach it —
      `factory/verify/toolchain.py` is the natural home, since it already owns
      discover-don't-declare for this pair.
- [ ] T007 [US1] (FR-003) Call it from `factory/workgraph/adapter.py:427-431` and
      from `factory/verify/gates.py:586-590`, replacing both literal blocks.
      Leave the `--proc` / `--dev` / `--tmpfs` entries after them untouched —
      those are genuinely host-independent.
- [ ] T008 [US1] (FR-004) Refuse by name, before forking, when a required path can
      be neither bound nor linked.
- [ ] T009 [US1] (spec US1-S5, trap 4) Delete the stale comments at `adapter.py:427-428` and
      `gates.py:586-587`, and the stale sentence in the docstring at
      `adapter.py:318`. Replace them with a comment that states the rule rather
      than a fact about any host.

## Phase 2: User Story 2 — A launch that never reached the agent is not an attempt

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1) In `tests/test_launch_is_not_an_attempt.py`,
      drive a node whose sandbox launch fails before any agent output and assert
      the ladder's spent-attempt count is **unchanged**. Assert the count
      directly (`factory/verify/ladder.py:111-119`), not that the node retried.
- [ ] T011 [P] [US2] (spec US2-S2) Assert the failure is reported as a launch
      failure distinct from an attempt failure, naming the fault.
- [ ] T012 [P] [US2] (spec US2-S3) Assert the notifier is reached at the launch
      failure rather than after the ladder exhausts.
- [ ] T013 [P] [US2] (spec US2-S4) **The control.** Assert an agent that started,
      produced output and then failed IS still charged. Trap 5: the distinction
      is "did the agent start", not "did it fail quickly".
- [ ] T014 [P] [US2] (spec US2-S5) Assert repeated launch failures stop after a
      bounded number rather than looping forever (trap 6).

### Implementation for this story

- [ ] T015 [US2] (FR-005) Classify a pre-first-token launch fault separately from
      an attempt, and keep it out of `_attempts_spent`'s count
      (`factory/verify/ladder.py:111-119`). **The classification seam is
      `factory/workgraph/workflow.py:1603-1606`, not the adapter (trap 12).**
      `factory/activities/agent_activities.py:492-497` already raises the right
      error; the workflow discards it at `_attempt`'s blanket `except
      ActivityError`. Follow the `JUDGE_UNAVAILABLE` branch at
      `workflow.py:1990`.
- [ ] T016 [US2] (FR-006) Surface it as its own operator-facing condition at the
      time it happens.
- [ ] T017 [US2] (FR-007) Bound the launch-retry path so it cannot loop
      indefinitely.

## Phase 3: User Story 3 — A compiled graph means the same thing in both processes

### Tests for this story (write FIRST, must fail)

- [ ] T018 [P] [US3] (spec US3-S1) In `tests/test_graph_paths_are_absolute.py`,
      derive with a relative specs root and assert the artifact carries an
      absolute path.
- [ ] T019 [P] [US3] (spec US3-S2) Assert the same for the target repository.
- [ ] T020 [P] [US3] (spec US3-S3) Assert an artifact carrying a relative path is
      refused at read time, naming the field and the value, before any key is
      minted (trap 8).
- [ ] T021 [P] [US3] (spec US3-S4) Assert a non-existent specs root is reported as
      the **resolved absolute path**, not as the string supplied.

### Implementation for this story

- [ ] T023a [US3] (FR-008) Resolve `specs_root` and `target_repo` to absolute paths
      in **`derive_command` (`factory/workgraph/cli.py:219`, artifact written at
      `:273-279`)** — the single derive handler. `factory/cli/nouns/spec.py:203-207`
      only delegates and needs no change. **Resolve in the command, not in the
      deriver**: `derive_workgraph` / `derive_delta` are also called from
      `factory/activities/roadmap_activities.py:202`, and
      `factory/workgraph/derive.py:148-152` states the deriver "is handed text,
      not a path". Resolving there reds `tests/test_derive.py` and
      `tests/test_delta.py`.
- [ ] T023b [US3] (FR-009, FR-010) Refuse a relative path **at
      `factory/cli/nouns/build.py:196-223`** — `load_workgraph`, the
      read-for-dispatch site reached by `ergane build start`. The near-identical
      copy at `factory/workgraph/cli.py:526-560` is dead code reachable only from
      an unwired handler; a guard added there passes its own test and leaves the
      real path open. Report resolution failures as the resolved absolute path.

## Verification

- [ ] T024 (SC-001) Build both argvs against a layout with `/lib64` and one
      without, and paste both into the diff. They must differ by exactly that
      entry.
- [ ] T025 (SC-002) Remove the host-derivation, confirm the US1 tests fail, paste
      the failing output, restore it.
- [ ] T026 (SC-003) Drive a launch failure and paste the before-and-after attempt
      counts.
- [ ] T027 (SC-004) Paste the control: an agent that started and failed, still
      charged.
- [ ] T028 (SC-005) Derive from outside the repository root with a relative specs
      root, paste the artifact's resolved fields, and dispatch from a third
      directory.
