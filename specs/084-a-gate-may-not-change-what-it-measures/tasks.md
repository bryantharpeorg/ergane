# Tasks: a gate may not change what it measures

**Spec**: `specs/084-a-gate-may-not-change-what-it-measures/spec.md`
**Plan**: `specs/084-a-gate-may-not-change-what-it-measures/plan.md`

Read the plan's traps before the first task. Three decide whether an attempt
lands. Trap 3: the snapshot goes around `backend.run(invocation)`, not inside an
executor, or you cover one of the two and pass your own test. Trap 6: ignored
paths do not count, because this repository's own gate is `uv run pytest -q` and
a check that counted them turns your own verification red. Trap 7: a dirtied
gate is reported with a status that is not PASS, because
`factory/workgraph/prompt.py:694-695` `continue`s past every PASS and a quiet
boolean would be invisible to the next attempt.

**The names are ruled in the spec and are not yours to choose**, because the
three stories cannot see each other: `GateResult.worktree_writes` for the paths,
`GateResult.writes_declared` for "the manifest said so", and `writes:` for the
manifest key — a top-level mapping from gate name to boolean.

## Phase 1: User Story 1 — A gate that writes into the worktree does not pass

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-004) In
      `tests/test_a_gate_that_writes_does_not_pass.py`, assert a gate whose
      command exits 0 and writes an unignored file is not reported PASS and
      carries the path it wrote.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) **The control.** Assert a gate that
      writes only `.gitignore`-matched paths passes and records nothing. Use
      `__pycache__/` and `.pytest_cache/` as the fixture's ignored names — the
      ones this repo's own gate produces (trap 6).
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) Assert a gate that rewrites a tracked
      file the agent had already modified is refused and the file named. Capture
      `git status --porcelain` before and after in the same test, so the
      byte-identical output is committed evidence that porcelain cannot see this
      (trap 5).
- [ ] T004 [P] [US1] (spec US1-S4, FR-001) Assert both gate-list runners refuse
      it: `_run_gate_list` (`factory/verify/gates.py:1244`) and
      `_run_gate_list_from_config` (`:1282`) (trap 2).
- [ ] T005 [P] [US1] (spec US1-S5, FR-001) Assert the refusal under three
      executors, naming the executor each case ran under (trap 3): a real
      `SubprocessGateExecutor` (`factory/verify/gates.py:397`); a **stub
      `GateExecutor`** that is neither shipped class, which is what proves the
      check sits at the seam and is the only case that runs on every host; and
      `BwrapGateExecutor` (`factory/verify/gates.py:490`) **behind a skip guard**
      copied from this repository's own — `_bwrap_available()`
      (`tests/test_us4_boundary.py:165`), early-return shape at
      `tests/test_us4_boundary.py:208`, `:264` and `:321` — because a sandboxed
      node agent may have no nested bwrap (trap 18).
- [ ] T006 [P] [US1] (spec US1-S6, FR-005) Assert a gate that exits non-zero
      *and* dirties keeps status FAIL with its exit code, still records the
      paths, and does not stop the gates declared after it (trap 9).
- [ ] T007 [P] [US1] (spec US1-S7, FR-006) Assert a snapshot git refuses yields a
      non-PASS result carrying git's error in `output_tail`, and that
      `run_gates` returns a list rather than raising (trap 9).
- [ ] T008 [P] [US1] (spec US1-S8, FR-003) Assert the new field round-trips
      through `_gate_to_dict` / `_gate_from_dict`
      (`factory/verify/store.py:668-692`) and that a stored row lacking it reads
      back as "nothing recorded" (trap 8).

### Implementation for this story

- [ ] T009 [US1] (FR-002) Add a worktree-content snapshot helper: `git add -A`
      into a throwaway `GIT_INDEX_FILE`, `git write-tree`, compare ids, name the
      paths with `git diff-tree -r --name-only`. Copy the mechanism from
      `factory/workgraph/worktree.py:1021-1026` — **you may not import that
      module from `factory/verify/gates.py`** (trap 4).
- [ ] T010 [US1] (FR-001) Call it around `backend.run(invocation)` in both loops,
      `factory/verify/gates.py:1275` and `:1311`. N gates, N+1 snapshots; keep it
      out of `duration_s` and out of the limiter's slot (trap 10).
- [ ] T011 [US1] (FR-003) Add `worktree_writes: tuple[str, ...] = ()` to
      `GateResult` (`factory/verify/models.py:277`; `concurrent_gates` at
      `factory/verify/models.py:301` is the shape to copy), populate it in
      `_to_result` (`factory/verify/gates.py:1332-1363`), and carry it through
      both codec halves in `factory/verify/store.py` (trap 8). Leave
      `writes_declared` alone — it is US3's, and it defaults false.
- [ ] T012 [US1] (FR-004) Add the non-PASS status to `GateStatus`
      (`factory/verify/models.py:70-81`) and assign it in `_to_result` when the
      command exited 0 but the worktree moved. **Do not edit `gates_passed`**
      (`:490-492`) — it already refuses anything that is not PASS (trap 12).
- [ ] T013 [US1] (FR-005, FR-006) Keep FAIL and TIMEOUT as the headline when they
      apply, record paths regardless, and make an unreadable snapshot evidence
      rather than an exception.

### Verification for this story

- [ ] T014 [US1] (SC-001) Paste the refusal, showing the gate name and the path.
- [ ] T015 [US1] (SC-002) Paste the control: a **fixture gate** that writes
      `__pycache__/` and `.pytest_cache/` into a fixture repo whose `.gitignore`
      names them, run through the new check, still PASS, with those paths shown
      as not counted (trap 14 — both halves in the diff). **Do not invoke
      `uv run pytest -q` as the gate**: a full suite inside a gate run inside the
      node's own gate run is the recursion behind
      `hardening/orphaned-test-servers-exhaust-host-memory` (trap 17). The real
      suite control is the operator's, out of band.
- [ ] T016 [US1] (SC-003) Paste the tracked-rewrite refusal alongside the
      byte-identical `git status --porcelain` output from either side of it.
- [ ] T017 [US1] (SC-004) Paste the same refusal through each of the two
      gate-list runners, under `SubprocessGateExecutor` and under the stub
      executor. For `BwrapGateExecutor`, paste its passing case if this host has
      bwrap and otherwise the skip line **with `_bwrap_available()`
      (`tests/test_us4_boundary.py:165`) quoted beside it** — a bare `SKIPPED` is
      not evidence (trap 18).
- [ ] T018 [US1] (SC-005) Paste the failing-and-dirtied gate with the gate
      declared after it still present in the returned list.
- [ ] T019 [US1] (SC-006) Paste the unreadable-snapshot result and the returned
      list.

## Phase 2: User Story 2 — The next attempt is told which gate wrote what

**Depends on US1 having merged** (`depends_on_merged`). It renders a field that
does not exist until US1 lands. Shares no file with US3.

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US2] (spec US2-S1, FR-007) In
      `tests/test_the_next_attempt_is_told_what_the_gate_wrote.py`, assert the
      retry prompt names the gate, its command and every path it wrote, quoted.
- [ ] T021 [P] [US2] (spec US2-S2, FR-007) **The control.** Assert an attempt
      whose gates all passed cleanly renders nothing about worktree writes — a
      green gate's output stays noise (`factory/workgraph/prompt.py:681-683`).
- [ ] T022 [P] [US2] (spec US2-S3, FR-008) Assert the operator-facing gate line
      carries the marker, following `concurrent_gates`'s rendering at
      `factory/notify/messages.py:417-418`.

### Implementation for this story

- [ ] T023 [US2] (FR-007) Render the paths in `_attempt_block`
      (`factory/workgraph/prompt.py:678`). The gate is already reachable there
      because its status is not PASS (trap 7) — confirm that before adding a
      branch.
- [ ] T024 [US2] (FR-008) Extend `_gate_line` (`factory/notify/messages.py:410`).

### Verification for this story

- [ ] T025 [US2] (SC-007) Paste the retry prompt for an attempt whose gate
      dirtied the worktree.
- [ ] T026 [US2] (SC-008) Paste the operator gate line for a dirtied gate and the
      control line for a clean one.

## Phase 3: User Story 3 — A gate that is supposed to write says so

**Depends on US1 having merged** (`depends_on_merged`). Contention, not logic:
it edits `factory/verify/gates.py`, `factory/verify/models.py` and
`factory/verify/store.py`, all three of which US1 rewrites.

**T029 is the task this story fails without.** Every other US3 scenario can go
green against `_run_gate_list_from_config` alone while `writes:` is silently
dropped on the runner Ergane's own nodes take — which is
`verify/readiness-proves-a-thing-is-declared-not-that-it-works`, filed five times
here, inside a spec written to close a defect. Write T029 first.

### Tests for this story (write FIRST, must fail)

- [ ] T027 [P] [US3] (spec US3-S1, FR-009) In
      `tests/test_a_gate_may_declare_that_it_writes.py`, assert a fixture
      manifest whose `writes:` block declares gate `X` lets `X` write and still
      pass.
- [ ] T028 [P] [US3] (spec US3-S2, FR-010) Assert the paths are still on
      `worktree_writes` and `writes_declared` is true. **An opt-out nobody can
      see is how this defect returns.**
- [ ] T029 [P] [US3] (spec US3-S3, FR-012) Assert **both** gate-list runners
      honour the declaration: `_run_gate_list` (`factory/verify/gates.py:1244`)
      and `_run_gate_list_from_config` (`factory/verify/gates.py:1282`), each
      passing the declared gate and each recording its paths as declared. This
      mirrors T004, which proves both *refuse*. The candidate runner is the one
      that gets nothing for free (trap 16), and it is the one this story's own
      verification runs on — the fork is `if candidate_path.exists():` at
      `factory/verify/gates.py:1135`.
- [ ] T030 [P] [US3] (spec US3-S4, FR-011) Assert a `writes:` entry naming a gate
      the manifest does not declare is refused, naming the unknown gate.
      `_read_timeouts` (`factory/verify/factory_yaml.py:370`) already refuses
      that shape at `factory/verify/factory_yaml.py:386-393`; follow it,
      message included.
- [ ] T031 [P] [US3] (spec US3-S5, FR-009) **The control.** Assert a manifest
      without the key parses exactly as it does today.

### Implementation for this story

- [ ] T032 [US3] (FR-009) Add `"writes"` to `_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:103-112`) — `_V2_TOP_LEVEL_KEYS`
      (`factory/verify/factory_yaml.py:115`) is derived from that tuple, so both
      schemas learn it in one edit — read it beside `timeouts` at
      `factory/verify/factory_yaml.py:195`, and land it on `FactoryConfig`
      (`factory/verify/models.py:230`) beside the `timeouts` field at
      `factory/verify/models.py:250`. Mapping of gate name to boolean; absent and
      `false` both mean nothing declared. Reject a non-boolean the way
      `_read_timeouts` rejects a non-int, with `type(value) is not bool`. **Do
      not add the key to this repository's own `factory.yaml`** — the config gate
      parses a node's manifest with the worker's installed parser, and 020/US1
      died four times on exactly that (trap 11, `factory.yaml:38-42`).
- [ ] T033 [US3] (FR-012) Carry the declaration through the candidate protocol,
      or the key never reaches the runner Ergane's own nodes use (trap 16): add
      the field to `_AcceptedConfig` (`factory/verify/gates.py:181-186`), read it
      in `_interpret_candidate` (`factory/verify/gates.py:947-948`, returned at
      `factory/verify/gates.py:966-969`), pass it at the `_run_gate_list(...)`
      call (`factory/verify/gates.py:1146-1154`) and take it in `_run_gate_list`'s
      signature (`factory/verify/gates.py:1244`). The emitting half is already
      done — `factory/verify/factory_yaml.py:879` serializes the whole
      `FactoryConfig`. Four sites, and T029 is what catches a missed one.
- [ ] T034 [US3] (FR-010) Add `writes_declared: bool = False` to `GateResult`
      (`factory/verify/models.py:277`), carry it through both codec halves in
      `factory/verify/store.py` with the absent read defaulted (trap 8), and set
      it in `_to_result` (`factory/verify/gates.py:1332`): a declared gate keeps
      PASS and still carries its `worktree_writes`, flagged declared. **Not a new
      `GateStatus` member** — a declared writer passes, and a new status would
      force an edit to `gates_passed` (trap 12).
- [ ] T035 [US3] (FR-011) Refuse an unknown gate name at parse time, following
      `_read_timeouts`'s own refusal at `factory/verify/factory_yaml.py:386-393`
      (`if name not in gates:` → `FactoryConfigError` naming the declared gates).
      `_reject_unknown_keys` (`factory/verify/factory_yaml.py:242-244`) is the
      *top-level key* refusal and is not this.

### Verification for this story

- [ ] T036 [US3] (SC-009) Paste the fixture manifest, the gate writing, the run
      passing, and the evidence showing the paths on `worktree_writes` with
      `writes_declared` true.
- [ ] T037 [US3] (SC-010) Paste the unknown-gate refusal with the parser's own
      message.
- [ ] T038 [US3] (SC-011) Paste the declared gate passing through **each** of the
      two gate-list runners, naming the candidate-parser runner explicitly. This
      is the criterion that distinguishes a declaration that works from one that
      is merely parsed, stored and emitted.
