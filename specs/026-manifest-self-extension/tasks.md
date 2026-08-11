# Tasks: The gate that judges a story with the parser it is changing

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip — except where a
task's docstring says it is a regression guard, written to fail only if the
implementation over-reaches.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      hosts the work, and record the answers here. Five things, because each
      one is a premise some task turns on: that `run_gates` still parses the
      manifest in-process at `factory/verify/gates.py:420-423` and returns
      `[config_error_result(error)]` (the edit point — if a refactor moved it,
      trap 7 applies); that `SubprocessGateExecutor` still merges stderr into
      stdout (`stderr=subprocess.STDOUT`, `:317`) — trap 3's whole argument;
      that `factory/verify/factory_yaml.py` still has no `__main__` handling
      (if someone added one, US1 changes from "build" to "conform"); that
      `tests/fixtures/target_repo/` still carries no `factory/` directory, so
      the probe finds no candidate there and US2-S3 tests what it claims; and
      that `FactoryConfig` (`factory/verify/models.py:184`) is still a plain
      dataclass whose fields `asdict` cleanly — the JSON shape depends on it.

---

## Phase 2: User Story 1 — The parser learns to speak for itself (Priority: P1)

**Goal**: any tree's factory package can be asked, from a subprocess, whether
it accepts a manifest — config JSON on stdout + exit 0, or the parser's own
refusal on stderr + a distinguished exit code.

**Independent Test**: real subprocess invocations of the CLI against a manifest
the schema accepts, one it refuses, and a path that does not exist.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; `factory/verify/factory_yaml.py` and `tests/test_factory_yaml.py`
      exist and plan.md's inventory claims hold — constitution II gate; STOP
      and report blocked if not satisfied.
- [ ] T003 [US1] In `tests/test_factory_yaml.py`, write the accept case FIRST:
      run `python -m factory.verify.factory_yaml <path>` as a real subprocess
      (via `sys.executable -m`, cwd this repo) against a valid manifest written
      to `tmp_path`; assert exit 0 and that stdout parses as a single JSON
      document whose `gates` and `timeouts` equal what `parse_factory_config`
      returns in-process for the same text (spec US1-S1) — must fail: today the
      module has no `__main__` and exits 0 printing nothing.
- [ ] T004 [US1] Write the reject cases FIRST, beside T003: an unknown-top-
      level-key manifest exits with the distinguished rejection code
      (`PARSE_CLI_REJECTED`), stdout is empty of JSON, and stderr carries the
      `FactoryConfigError` message with its rule slug (`unknown_key`) and the
      source path (spec US1-S2); a manifest path that does not exist exits the
      same way carrying the `missing_manifest` message, and stderr contains no
      traceback (spec US1-S3) — must fail.
- [ ] T005 [US1] Write the additivity guard: assert the CLI constants exist and
      that no library entry point changed signature, then run the pre-existing
      `tests/test_factory_yaml.py` tests unmodified and record green in the
      commit message (spec US1-S4). Regression guard — say in its docstring
      that it fails only if the implementation over-reaches into parsing
      behaviour.

### Implementation for User Story 1

- [ ] T006 [US1] Implement the CLI in `factory/verify/factory_yaml.py` per
      plan.md § US1: `PARSE_CLI_OK = 0`, `PARSE_CLI_REJECTED = 65` (sysexits
      `EX_DATAERR` — not 1 or 2, plan trap 9), `_main(argv)`
      wrapping `load_factory_config` (a missing path is already a
      `FactoryConfigError`, which is why US1-S3 costs no extra branch), JSON
      via `dataclasses.asdict` to stdout, `str(error)` to stderr, and the
      `if __name__ == "__main__":` guard. Wrong argv count is a rejection with
      a usage line on stderr. No other change to the module — until T003–T005
      pass.

---

## Phase 3: User Story 2 — The gate judges a manifest with the candidate's parser (Priority: P1) 🎯 the deadlock killed

**Goal**: `run_gates` consults the worktree's candidate parser via subprocess
when one is present; a candidate acceptance runs the gates, a rejection is one
`CONFIG_ERROR` carrying the candidate's message, and a candidate that cannot
run falls back to today's behaviour — with the worker surviving all of it.

**Independent Test**: the candidate seam faked to each outcome against a
manifest the worker's parser refuses, plus one unfaked end-to-end run against
this repository's own tree.

**Chained on US1 merged**: US2-S6 executes the CLI US1 builds, so this story's
base must contain it (merge-edge, spec Work Graph).

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [US2] Verify prerequisites in this worktree: `uv run pytest -q`
      green and `factory/verify/factory_yaml.py` contains `_main` and
      `PARSE_CLI_REJECTED` — the merge-edge delivered US1; STOP and report
      blocked if not, because it means the worktree was created before US1
      merged and every test after this one would blame the wrong story.
- [ ] T008 [US2] In `tests/test_gates.py`, write the interpretation table
      FIRST, against the pure interpreter (no processes): exit 0 + valid
      protocol JSON → accepted with that gates/timeouts view; the rejection
      exit code + a stderr message → rejected carrying the message; exit 0 +
      empty stdout → cannot-run, the pre-CLI-worktree shape (spec US2-S5, plan
      trap 2); any other nonzero exit → cannot-run — including exit 2 with a
      TOML error on stderr, the measured shape of `uv run` over a worktree
      whose `pyproject.toml` an agent broke, which must never read as rejected
      (plan trap 9); timed out → cannot-run;
      exit 0 + JSON whose `gates` is not a non-empty str→str mapping or whose
      `timeouts` is not str→positive-int → cannot-run (spec US2-S4's
      "producing output that is not the protocol") — must fail: the
      interpreter does not exist.
- [ ] T009 [P] [US2] Write the deadlock case FIRST — the scenario this spec
      exists for: a `tmp_path` worktree whose manifest declares a top-level key
      the worker's imported parser refuses; the candidate seam faked to accept
      with a valid gates view; `run_gates` with a `RecordingExecutor` returns
      one result per declared gate and **no** `CONFIG_ERROR`, and the executor
      saw every declared gate (spec US2-S1) — must fail.
- [ ] T010 [P] [US2] Write the candidate-rejection case FIRST: the seam faked
      to reject with a distinctive message; `run_gates` returns exactly one
      result, `status=CONFIG_ERROR`, `name="config"`, `output_tail` carrying
      that message verbatim, and the `RecordingExecutor` saw zero invocations —
      the one-result contract, plan trap 4 (spec US2-S2) — must fail.
- [ ] T011 [P] [US2] Write the no-candidate case FIRST: against
      `tests/fixtures/target_repo/` (no `factory/` directory), with a spy
      runner installed, `run_gates` never invokes the candidate seam and
      returns exactly what it returns today for both a good manifest and a
      refused one (spec US2-S3). Regression guard — docstring must say it
      fails only if the probe or fallback over-reaches. The broader half of
      this evidence is trap 6: the pre-existing `test_gates.py` tests stay
      byte-unmodified and green.
- [ ] T012 [US2] Write the fallback case FIRST: the seam faked to cannot-run
      (with a reason string); with a manifest the worker's parser accepts,
      gates run exactly as today; with one it refuses, the single
      `CONFIG_ERROR`'s `output_tail` carries **both** the worker parser's
      message and the candidate's cannot-run reason (spec US2-S4, FR-006) —
      must fail.
- [ ] T013 [US2] Write the end-to-end case FIRST: `run_gates` with the **real**
      subprocess runner, this repository's own root as the worktree and a
      `RecordingExecutor` so no actual gate runs; assert the gate names it
      resolved equal what `load_factory_config` returns in-process for the same
      manifest (spec US2-S6). The suite already runs under `uv run`, so the
      subprocess reuses the live venv — bound the test generously rather than
      tightly. Must fail: nothing invokes a subprocess yet.

### Implementation for User Story 2

- [ ] T014 [US2] Implement per plan.md § US2, in `factory/verify/gates.py`: the
      probe (`worktree / "factory/verify/factory_yaml.py"` exists), the
      dedicated parse runner (argv `uv run -q python -m
      factory.verify.factory_yaml <manifest>`, cwd worktree, `scrubbed_env()`,
      **separated** pipes — trap 3 — `start_new_session`, TERM-then-KILL group
      reclaim on timeout copied from `_reclaim`, `DEFAULT_GATE_TIMEOUT_S`
      deadline — trap 5 — limiter acquired around the run), the pure
      three-way interpreter, and the wiring ahead of the existing
      `load_factory_config` call at `:420-423`: accepted → iterate the JSON
      view's gates; rejected → one candidate `CONFIG_ERROR`; cannot-run → the
      existing in-process path, appending the cannot-run reason to a fallback
      rejection's `output_tail`. The seam is a keyword parameter defaulting to
      the real runner, mirroring `executor`. No `importlib`, no `sys.path`
      writes (SC-002, trap 1). Until T008–T013 pass.
- [ ] T015 [US2] Final sweep + docs: a `docs/decisions.md` numbered entry
      claimed at landing — the config gate judges a node's manifest by the
      worktree's candidate parser (subprocess, never import), superseding
      "judged by last-landed code"; the entry also records the residual,
      deliberately non-constitutional sequencing rule: the repository's own
      `factory.yaml` gains a new key only after its parser lands and the worker
      restarts (spec, Out of Scope — one occurrence does not promote).
      Confirm: no new dependency (SC-005), `RunGatesInput` and the activity
      surface unchanged, the pre-existing `test_gates.py`/`test_factory_yaml.py`
      tests byte-unmodified (SC-003, trap 6), and `grep -n "importlib\|sys.path"
      factory/verify/gates.py` comes back empty (SC-002).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything; its second check (the
  executor's merged stderr) in particular, because if that has changed, trap 3
  — and with it the case for a dedicated parse runner — must be re-argued
  rather than assumed.
- Phase 2 (US1) has no dependency and is landable alone: an entry point nobody
  calls yet, zero runtime behaviour change (SC-004).
- Phase 3 (US2) chains on US1 **merged**. The stories touch disjoint files, so
  this is not conflict avoidance — it is content: T013 executes the CLI that
  T006 builds, and a pass-edge would let US2's worktree be created from a base
  that does not contain it.

## Implementation Strategy

US1 is deliberately tiny — two constants, one function, one guard — because
everything risky lives in US2, and a fat protocol story would put the risk in
both. US2's risk is concentrated in two places the tests aim at directly: the
interpretation table (trap 2's exit-0-garbage row is the one a hurried
implementation gets wrong) and the byte-identical fallback (trap 6, proven by
leaving the old tests untouched). Neither story edits this repository's
`factory.yaml`, no manifest schema changes, and the worker that judges these
attempts runs the pre-fix code from its own checkout — which is why this spec
can fix the bootstrap deadlock without deadlocking on it (plan trap 8).
