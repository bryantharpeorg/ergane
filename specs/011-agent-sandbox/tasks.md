# Tasks: The worktree is where the agent starts, not where it is kept

Three stories, chained on merge edges: US1 → US2 → US3. Work test-first and
commit once per task.

## Tests for User Story 1 (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the detection case FIRST: an attempt whose scripted
      agent modifies a tracked file in the target repository outside its worktree
      files a critical finding naming that path, the epic, the node and the
      attempt (spec US1-S1) — must fail.
- [ ] T002 [P] [US1] Write the silence case FIRST: an attempt that writes only
      inside its own worktree files nothing (spec US1-S2) — must fail.
- [ ] T003 [P] [US1] Write the operator-work case FIRST — one fixture, two
      assertions. Against a target repo carrying unrelated uncommitted operator
      work: (a) the finding still reports the change, because the detector
      reports what happened and does not try to attribute intent (spec US1-S3);
      and (b) that work is still present and unmodified afterwards, because a
      detector that tidies destroys real work — plan.md trap 7 (spec US1-S4,
      FR-002) — must fail.
- [ ] T004 [P] [US1] Write the every-path case FIRST: the detector runs on all
      four terminations — completed, agent error, timeout, killed — because the
      breach is likeliest on the paths that end badly (spec US1-S1) — must fail.

## Implementation for User Story 1

- [ ] T005 [US1] Capture the target repository's tracked-file state at attempt
      start and at teardown, and file a critical finding on difference. Read
      `graph.target_repo`, never a hardcoded path (plan.md § US1). Hang it where
      it runs on every termination path; read 010's `try/finally` teardown
      bracket first as the precedent for that.
- [ ] T006 [US1] Give the finding a key that makes recurrence countable per
      epic/node, and put the changed paths in its evidence.

## Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [US2] Write the **git plumbing** case FIRST, before any other US2
      test: an agent inside the boundary runs `git add`, `git commit` and `git
      diff` in its worktree and all succeed. This is plan.md trap 1 — a
      worktree's `.git` is a file pointing into the target repo's `.git`, so the
      naive mount set breaks every operation the attempt performs at its end.
      Failing here first is what stops that being discovered at commit time
      (spec US2-S2, FR-005) — must fail.
- [ ] T008 [P] [US2] Write the containment case FIRST: an agent writing an
      absolute path into the target repository's working tree fails, and the
      operator's tree is unchanged (spec US2-S1, FR-004) — must fail.
- [ ] T009 [P] [US2] Write the timeout case FIRST with a deliberately hanging
      agent: the attempt is classified `timeout` and **no process from it
      survives**. plan.md trap 2 — a container changes what the recorded pid
      means, and a half-killed attempt holds a live virtual key (spec US2-S3,
      FR-006) — must fail.
- [ ] T010 [P] [US2] Write the transcript case FIRST, asserting on the archive's
      **contents** rather than on the environment: an attempt inside the boundary
      archives its stdout log and session transcript to the same paths with the
      same contents as today. plan.md trap 3 — the archive step returns early on
      a missing `HOME` and loses the transcript silently (spec US2-S4, FR-007) —
      must fail.
- [ ] T011 [P] [US2] Write the reach case FIRST: a read of the operator's home,
      or of any path outside the mount set, fails (spec US2-S5) — must fail.
- [ ] T012 [P] [US2] Write the refusal case FIRST: a runtime that cannot be
      provided is a refusal naming the image, never a silent fallback to the host
      (spec US2-S6, FR-008) — must fail.
- [ ] T013 [P] [US2] Write the no-runtime-installed case FIRST: the suite passes
      with the boundary driven by a substituted seam and no container runtime on
      the host. A skip is not a pass here (plan.md trap 5, FR-010) — must fail.

## Implementation for User Story 2

- [ ] T014 [US2] Put the agent launch behind a substitutable seam, following the
      `GateExecutor` Protocol precedent at `factory/verify/gates.py:153`. The
      seam lands before the runtime does, so T013 has something to drive.
- [ ] T015 [US2] Resolve the image from the manifest's `runtime:` — already
      parsed at `factory/verify/factory_yaml.py:99` — and run the agent inside it,
      rootless (plan.md trap 6). Mount the worktree writable, the git plumbing per
      T007, a writable temp dir, and a home for the agent CLI; do not mount the
      target repo's working tree or the operator's home.
- [ ] T016 [US2] Re-establish termination so the deadline still kills the agent
      and everything it spawned (FR-006). Do not assume the existing pgid path
      still reaches the agent — trap 2.
- [ ] T017 [US2] Leave `argv()`, the prompt, the standards path, the persona
      routing and the judge untouched (FR-011). This story changes where the
      agent runs and nothing about what it is asked to do.

## Tests for User Story 3 (write FIRST, must fail)

- [ ] T018 [P] [US3] Write the escape case FIRST: a gate command reading or
      writing outside the worktree fails inside the boundary where it would have
      succeeded on the host (spec US3-S1, FR-009) — must fail.
- [ ] T019 [P] [US3] Write the parity case FIRST: PASS, FAIL, TIMEOUT and the
      captured output tail are unchanged from host execution for gates that stay
      inside the worktree (spec US3-S2) — must fail.
- [ ] T020 [P] [US3] Write the hanging-gate case FIRST: a gate that hangs is
      killed with every process it spawned, as it is today (spec US3-S3) — must
      fail.

## Implementation for User Story 3

- [ ] T021 [US3] Add a second `GateExecutor` implementation beside the host one
      at `factory/verify/gates.py:296`. **Do not edit the host implementation and
      do not change the Protocol** — `run_gates` at `:388` selects between them.

## Verification

- [ ] T022 Run the full suite on a host with no container runtime installed and
      confirm it is green with no skips standing in for coverage (SC-005).
- [ ] T023 Drive one real attempt end to end inside the boundary: it commits, is
      judged, and lands through the merge queue with its evidence trail
      unchanged (SC-003). A PASS verdict is not this evidence — run the thing.
- [ ] T024 Confirm `git status` in the target repository is byte-identical before
      and after that attempt (SC-002).
- [ ] Final gate command passes green.
