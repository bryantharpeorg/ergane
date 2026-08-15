# Tasks: The worktree is where the agent starts, not where it is kept

Five stories, chained on merge edges: US1 → US2 → US3 → US4 → US5. Work
test-first and commit once per task. The backend is decided — bwrap; read
plan.md's "Decided at refinement" before the first commit.

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
- [ ] T005 [P] [US1] Write the runtime-root case FIRST: an attempt whose agent
      removes or truncates an evidence store, a ledger, or a sibling node's
      worktree files a critical finding naming those paths (spec US1-S5, FR-012)
      — must fail. A tracked-file diff of the target repo **cannot** see this;
      the runtime root is gitignored, which is why the 2026-08-14 destruction
      would have produced silence from T001's detector.
- [ ] T006 [P] [US1] Write the detector-survives-the-destruction case FIRST:
      the agent deletes the runtime root outright and the detector still reports,
      rather than failing because what it meant to compare against is what was
      destroyed (spec US1-S6, FR-013) — must fail. Hold the start-state snapshot
      somewhere the agent cannot reach (plan.md trap 10).

## Implementation for User Story 1

- [ ] T007 [US1] Capture the target repository's tracked-file state at attempt
      start and at teardown, and file a critical finding on difference. Read
      `graph.target_repo`, never a hardcoded path (plan.md § US1). Hang it where
      it runs on every termination path; read 010's `try/finally` teardown
      bracket first as the precedent for that.
- [ ] T008 [US1] Give the finding a key that makes recurrence countable per
      epic/node, and put the changed paths in its evidence.
- [ ] T009 [US1] Extend the capture to the runtime root: the evidence store,
      both ledgers and every sibling worktree (FR-012). Keep the start snapshot
      outside the runtime root so FR-013 holds — a snapshot stored in the
      directory under threat is not a snapshot.

## Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Write the parity case FIRST: an attempt dispatched through the
      seam with a fake backend substituted hands the fake an argv, prompt path,
      standards path and persona routing identical to what today's direct launch
      at `factory/workgraph/adapter.py:528-534` builds (spec US2-S1, FR-011) —
      must fail.
- [ ] T011 [P] [US2] Write the refusal case FIRST: a backend that cannot be
      provided is a refusal naming the backend and the platform, fired before
      any agent process starts, never a silent fallback to the host (spec
      US2-S2, FR-008) — must fail.
- [ ] T012 [P] [US2] Write the manifest case FIRST: a `runtime:` value holding
      the old container-image form is a validation refusal naming `bwrap` as
      the supported backend (spec US2-S3) — must fail.

## Implementation for User Story 2

- [ ] T013 [US2] Put the agent launch behind a substitutable seam, following
      the `GateExecutor` Protocol precedent at `factory/verify/gates.py:208`.
      Today's host launch becomes one implementation — kept, but selectable
      only explicitly (US4's control needs it; nothing else may reach it).
- [ ] T014 [US2] Change `_read_runtime`'s value domain and error text
      (`factory/verify/factory_yaml.py:193`, `:197` — the message still says
      "container image reference") and update `factory.yaml:15` to
      `runtime: bwrap` in the same diff, so no window exists where the manifest
      declares an image nothing can run (spec US2-S3).
- [ ] T015 [US2] Leave `argv()`, the prompt, the standards path, the persona
      routing and the judge untouched (FR-011). This story changes where the
      launch is decided and nothing about what the agent is asked to do.
- [ ] T016 [US2] Prove the suite is green with no backend on the host: seam
      tests drive the fake, and the detection guard the live tests will use in
      US3/US4 exists and is exercised (FR-010, spec US2-S4, plan.md trap 5).
      A skip is not a pass here.

## Tests for User Story 3 (write FIRST, must fail)

- [ ] T017 [US3] Write the **git plumbing** case FIRST, before any other US3
      test: an agent inside the boundary runs `git add`, `git commit` and `git
      diff` in its worktree and all succeed. This is plan.md trap 1 — a
      worktree's `.git` is a file pointing into the target repo's `.git`, so the
      naive mount set breaks every operation the attempt performs at its end.
      Failing here first is what stops that being discovered at commit time
      (spec US3-S2, FR-005) — must fail.
- [ ] T018 [P] [US3] Write the containment case FIRST: an agent writing an
      absolute path into the target repository's working tree fails, and the
      operator's tree is unchanged (spec US3-S1, FR-004) — must fail.
- [ ] T019 [P] [US3] Write the reach case FIRST: a read of the operator's home,
      or of any path outside the mount set, fails (spec US3-S3) — must fail.
- [ ] T020 [P] [US3] Write the **destruction** case FIRST, using the literal
      2026-08-14 command: a scripted agent runs
      `cd <target-repo> && rm -rf .factory` inside the boundary; it fails, and
      the evidence store, both ledgers, every sibling worktree and its own
      worktree are all intact afterwards (spec US3-S4, FR-014, SC-007) — must
      fail. Paste the before/after sizes and row counts into the test.

## Implementation for User Story 3

- [ ] T021 [US3] The bwrap executor, per plan.md § US3: invoke `/usr/bin/bwrap`
      by absolute path (trap 6), `--ro-bind /usr` with `/bin` and `/lib`
      symlinks (no `/lib64` on this aarch64 host), the node worktree bound
      writable at its own absolute path — **the leaf, never the runtime root
      that contains it** (FR-014, trap 9) — the git plumbing per T017 (state
      which route: minimal set or whole-`.git`, and why), a tmpfs `/tmp`, a
      factory-owned home bound from a host path (traps 3 and 4), the toolchain
      leaves read-only (trap 13 — bind the symlink targets, set `PATH`),
      `--unshare-pid --die-with-parent`, and **no** `--unshare-net`.

## Tests for User Story 4 (write FIRST, must fail)

- [ ] T022 [P] [US4] Write the timeout case FIRST with a deliberately hanging
      agent: the attempt is classified `timeout` and **no process from it
      survives** — plan.md trap 2: the group kill reaches bwrap, and only
      `--die-with-parent` takes the namespace down with it (spec US4-S1,
      FR-006) — must fail.
- [ ] T023 [P] [US4] Write the transcript case FIRST, asserting on the
      archive's **contents** rather than on the environment: an attempt inside
      the boundary archives its stdout log and session transcript to the same
      paths with the same contents as today. plan.md trap 3 — the archive step
      at `adapter.py:738` returns early on a missing session file and loses the
      transcript silently (spec US4-S2, FR-007) — must fail.
- [ ] T024 [P] [US4] Write the **signal** case FIRST: a scripted agent runs
      `pkill -f "python -"` inside the boundary and the worker process is still
      alive afterwards (spec US4-S3, FR-015, SC-008) — must fail. Assert on the
      worker's liveness, never on `pkill`'s exit code, which is 1 whenever it
      matched nothing and is therefore indistinguishable from success (plan.md
      trap 11).
- [ ] T025 [US4] Write the **control** FIRST: with the boundary disabled via
      the seam's explicit host implementation, T020's and T024's commands both
      reproduce the damage (spec US4-S4, SC-009, plan.md trap 12) — this is the
      test that proves the boundary is what is doing the work. A containment
      claim proven only in the passing direction has not been proven.

## Implementation for User Story 4

- [ ] T026 [US4] Re-establish termination so the deadline still kills the agent
      and everything it spawned (FR-006). The pid file at
      `_write_pid_file` (`adapter.py:804`) now records bwrap's pgid, and the
      `killpg` path (`:835`, `:851`) reaches bwrap — do not assume that is
      sufficient; prove the namespace dies with it (plan.md trap 2).
- [ ] T027 [US4] Route the agent home so `_archive_session` (`adapter.py:738`)
      finds the session file on the host side of the bind (FR-007, plan.md
      trap 3).
- [ ] T028 [US4] Deny the agent the ability to signal processes outside its
      boundary (FR-015). `--unshare-pid` provides it; state it and test it
      rather than inheriting it by luck, so a later refactor cannot drop the
      flag with nothing failing.

## Tests for User Story 5 (write FIRST, must fail)

- [ ] T029 [P] [US5] Write the escape case FIRST: a gate command reading or
      writing outside the worktree fails inside the boundary where it would have
      succeeded on the host (spec US5-S1, FR-009) — must fail.
- [ ] T030 [P] [US5] Write the parity case FIRST: PASS, FAIL, TIMEOUT and the
      captured output tail are unchanged from host execution for gates that stay
      inside the worktree (spec US5-S2) — must fail.
- [ ] T031 [P] [US5] Write the hanging-gate case FIRST: a gate that hangs is
      killed with every process it spawned, as it is today (spec US5-S3) — must
      fail.

## Implementation for User Story 5

- [ ] T032 [US5] Add a second `GateExecutor` implementation beside the host one
      at `factory/verify/gates.py:351`. **Do not edit the host implementation
      and do not change the Protocol at `:208`** — `run_gates` at `:612`
      selects between them.

## Verification

- [ ] T033 Run the full suite on a host where bwrap is not reachable (mask the
      absolute path in the environment the suite controls) and confirm it is
      green with no skips standing in for seam coverage (SC-005).
- [ ] T034 Drive one real attempt end to end inside the boundary: it commits,
      is judged, and lands through the merge queue with its evidence trail
      unchanged (SC-003). A PASS verdict is not this evidence — run the thing.
- [ ] T035 Confirm `git status` in the target repository is byte-identical
      before and after that attempt (SC-002).
- [ ] T036 Run the two historical commands by hand against a live boundary and
      paste the results: `rm -rf .factory` (SC-007) and `pkill -f "python -"`
      (SC-008). Then run both again with the boundary disabled and confirm they
      still do damage (SC-009). Verify by control, not by a green suite — the
      thing being replaced was also believed to work.
- [ ] Final gate command passes green.
