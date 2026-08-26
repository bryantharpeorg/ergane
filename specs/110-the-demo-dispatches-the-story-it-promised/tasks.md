# Tasks: the demo dispatches the story it promised

**Input**: `spec.md` and `plan.md` in this directory, both drafted 2026-08-26
against ergane-buildout at 4aae6b7.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch different files or independent test functions.

## Phase 1: User Story 1 — First boot leaves the demo project dispatchable

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001) Supervisor spawn test, in a new
  `tests/test_110_us1_demo_first_boot.py`: with `ERGANE_DEMO=1` and no
  sentinel, the supervisor spawns the demo driver after worker and bridge
  start — driven through the injectable `start_child`/`probe_address` seams
  (`container_supervisor.py:260-272`), asserting the driver is spawned as a
  plain subprocess, appears in neither the `controllers` nor the `tasks` maps
  (`:338-347`), and that a driver exiting nonzero leaves all three children
  running and the supervisor's return value unchanged. A second case with
  `ERGANE_DEMO` unset asserts nothing is spawned and the supervised set is
  exactly today's three.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, FR-003) Prepare-phase offline test:
  drive the driver's prepare phase against a scratch state home, scratch repo
  path and the real bundled answers file, with the `ergane install` step
  running through the CLI seam. Assert afterwards: the config file exists at
  the given path; the repo is a git repository on branch `main`; the manifest
  text equals `_demo_manifest_text()` (`factory/cli/install.py:1049-1056`);
  `specs/001-demo/{spec.md,plan.md,tasks.md}` exist; and exactly one commit
  exists whose author is the driver's explicit demo identity — proven in an
  environment with **no** global git identity (HOME pointed at a scratch dir).
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) Validate-and-derive test: on the
  prepared repo, run `spec validate` and `spec derive` through `_run_cli`
  (`factory/cli/install.py:1071-1075`) with `--target-repo`, assert both
  return 0 and `specs/001-demo/workgraph.json` exists and parses.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005) Sandbox-probe refusal test: with an
  injected probe callable that fails with a scripted stderr, assert the driver
  prints that stderr verbatim plus one remedy line, performs **no** dispatch
  step, and returns nonzero — **and, driven through the supervisor's
  injectable seams, that all three supervised children are still running
  after the driver's nonzero exit**. Proving only that no sentinel was
  written does not satisfy US1-S4 (the first run's judge failed exactly
  that). A companion assertion pins the probe's assembled argv to include
  `--unshare-pid` and `--proc` — the measured failure (`bwrap: Can't mount
  proc`, 2026-08-26) fires there and a probe without them passes on a host
  where the real sandbox cannot start (plan T5).
- [ ] T005 [P] [US1] (spec US1-S5, FR-006) Sentinel semantics tests, two
  states: (a) after a completed prepare with a passing probe, a second driver
  run performs no step, prints one line saying first boot already happened,
  and returns 0; (b) after a **probe refusal**, no `prepared` sentinel exists
  and a second run **retries the probe** (assert the probe callable is
  invoked again). The two sentinels and their write points are plan T4.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, FR-003, FR-005, FR-006) Add
  `factory/supervision/demo_driver.py` — prepare phase as functions over
  explicit paths, sandbox probe mirroring the adapter's bwrap shape
  (`factory/workgraph/adapter.py:427-580`), sentinel under
  `$ERGANE_STATE_HOME/demo/`, `main()` runnable as `python3 -m` with no
  `python -` substring in any assembled argv — and the supervisor spawn hook
  after `container_supervisor.py:334-336`, gated on `ERGANE_DEMO=1`, reaped by
  a task whose failure is logged and never fatal (plan T1, T2).
- [ ] T007 [US1] (FR-002) Append the `docs/decisions.md` entry recording the
  decision-7 boundary: `ergane install`'s closing demonstration stays free and
  stops at derive; the compose demo's exported `UPSTREAM_MODEL_API_KEY` is the
  operator's spend opt-in, bounded to one story by halt-after-pass. Taken
  2026-08-26. Append-only; supersede nothing.

### Verification for this story

- [ ] T008 [US1] (spec US1-S2, spec US1-S5, SC-001) Paste into the PR: the
  prepare-phase test transcript (T002) and the sentinel no-op line (T005), and
  the full-suite before-and-after counts.

## Phase 2: User Story 2 — The demo dispatches, narrates, and halts

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US2] (spec US2-S1, FR-007) Argv test, in a new
  `tests/test_110_us2_demo_dispatch.py`: the dispatch phase assembles exactly
  `ergane build ship specs/001-demo --target-repo <repo> --yes
  --halt-after-pass` and runs it through the injectable CLI seam — no
  separate validate/derive/start invocations anywhere in the phase.
- [ ] T010 [P] [US2] (spec US2-S2, FR-008) Scripted watch test: a seam that
  plays `build status` documents through PENDING → RUNNING → VERIFYING →
  PASSED; assert each transition is printed exactly once, and the final output
  contains the halting-mode statement from `_halt_after_pass_lines`
  (`factory/cli/nouns/build.py:557-572`) **verbatim** — the assertion quotes
  the statement, so a reworded driver fails rather than paraphrases.
- [ ] T011 [P] [US2] (spec US2-S3, FR-009) Refusal test: the seam's `build
  ship` returns nonzero with a scripted refusal message; assert the driver
  prints it as its last words, writes the dispatch sentinel (so a second run
  is a no-op), and returns nonzero — with no supervisor interaction at all.
- [ ] T012 [P] [US2] (spec US2-S4, FR-010) Failure-render test: the scripted
  sequence ends in a gate failure instead of PASSED; assert the driver prints
  the failure render as given and adds no text of its own beyond the
  transition lines.

### Implementation for this story

- [ ] T013 [US2] (FR-007, FR-008, FR-009, FR-010) Add the dispatch/watch phase
  to `factory/supervision/demo_driver.py`: sentinel-before-ship (plan T4), the
  one-verb dispatch, the status poll loop with transition diffing, terminal
  render pass-through.

### Verification for this story

- [ ] T014 [US2] (spec US2-S2, SC-002) Paste into the PR: the scripted
  narration from T010 ending in the verbatim halt statement, and the
  full-suite before-and-after counts.

## Phase 3: User Story 3 — The file carries the demo

### Tests for this story (write FIRST, must fail)

- [ ] T015 [US3] (spec US3-S1, FR-011) Extend
  `tests/test_109_us2_demo_compose.py`: `ERGANE_DEMO=1` and
  `LITELLM_PROXY_URL=http://gateway:4000` are present in the engine service's
  environment as **literal** values (no `${` in either), and
  `test_demo_compose_requires_exactly_one_mandatory_env_var` (`:275`) still
  passes with a count of exactly one.
- [ ] T016 [P] [US3] (spec US3-S2, FR-012) `systempaths=unconfined` is present
  in the engine service's `security_opt`, and the comment above it names the
  mechanism — assert the adjacent comment block mentions the masked-/proc
  refusal (the string `bubblewrap#284`), in the manner the existing tests pin
  the seccomp/apparmor comment.
- [ ] T017 [P] [US3] (spec US3-S3, FR-013) Unchanged-shape guard: services,
  named volumes, configs and the single mandatory variable are exactly as
  landed by 109 — the existing drift suite passes unmodified except the tests
  this story adds.

### Implementation for this story

- [ ] T018 [US3] (FR-011, FR-012, FR-013) The three lines in
  `container/compose.demo.yaml`: two literal environment entries in the list
  at `:33`, one `security_opt` entry in the list at `:20-32` with its
  mechanism comment in the voice of the existing block (`:22-30`).

### Verification for this story

- [ ] T019 [US3] (spec US3-S3, SC-003) Paste into the PR: the compose drift
  suite's before-and-after counts.

## What no task here can prove

Every task above is checkable from the diff, and the committed tests drive
every phase through seams. **None of them proves the thing the spec is for**,
which is a stranger's first five minutes: a real first boot, a real install, a
real agent spending a real key inside the shipped confinement, and the halt
statement arriving on a screen a human is actually watching. That proof is the
operator verification in `plan.md` — one watched run on the floor host from a
locally built image before the release is cut, and the released-asset rerun on
a machine that has never had Ergane after it ships. tasks.md forbids proving
this here on purpose: a test that dispatches a real epic spends money and
starts processes the suite must never own (plan T8).
