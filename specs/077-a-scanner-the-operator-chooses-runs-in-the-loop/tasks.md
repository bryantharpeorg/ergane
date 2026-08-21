# Tasks: a scanner the operator chooses runs in the loop

**Spec**: `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/spec.md`
**Plan**: `specs/077-a-scanner-the-operator-chooses-runs-in-the-loop/plan.md`

Read the plan's traps before the first task. Four decide whether an attempt
lands: **trap 1** (the bwrap sandbox is where this breaks — a bare
`subprocess.run` proves nothing), **trap 4** (record-only is structural — do not
pass the report into `compose_result`), **trap 8** (no coverage scanner, no
threshold, they are declared scope not omissions) and **trap 2** (do not write a
second unified-diff parser).

**This spec is record-only by construction.** No story in it may cause a scan to
change a verdict. If a task looks like it needs to, the task has been
misread — re-read the spec's "What this spec does not change".

## Phase 1: User Story 1 — The operator learns which scanners survive this sandbox

No production code lands in this story. Its deliverable is committed evidence,
because the judge sees only the diff (Constitution VIII) — a spike whose proof
lives in a terminal is a spike that must fail.

### Work

- [ ] T001 [P] [US1] (spec US1-S1) (FR-001) Run each candidate through `uvx` so nothing enters
      `pyproject.toml`. Candidates: `ruff`, `semgrep`, `bandit`, `radon`/`xenon`,
      and the CodeQL CLI. Confirm `git diff pyproject.toml uv.lock` is empty at
      the end and paste that confirmation into the note.
- [ ] T002 [US1] (spec US1-S3) (FR-003) For each candidate record the **exact** command, exit
      code, wall-clock and whether SARIF came back well-formed. Record the flag
      that actually worked, not the one the docs claim — a documented flag that
      does not exist is this repository's most expensive recurring defect class
      (`gh pr checks --json`, which never existed, cost epic 061 three stories).
- [ ] T003 [US1] (spec US1-S2) (FR-002) Run each surviving candidate **inside the real bwrap
      sandbox the gates use**, with `--clearenv` and only
      `SCRUBBED_ENV_ALLOWLIST` (`factory/verify/gates.py:97`) — no network, no
      writable `HOME` beyond what that list grants. Record what failed and how.
      A candidate that only works outside the sandbox is disqualified, and the
      note must say so in those words.
- [ ] T004 [P] [US1] (FR-004) Commit one real SARIF artifact per surviving
      candidate under `specs/077-.../research/`.
- [ ] T005 [US1] Measure each candidate against a **real node diff** from this
      repository, not against the whole tree, and state the wall-clock beside
      the gates' own runtime. A scanner slower than the suite it follows changes
      the loop's economics and the recommendation must reckon with it.
- [ ] T006 [US1] (spec US1-S4) Recommend one default scanner, citing the measurements. This
      recommendation is what US2's closed set admits — **US2 must not hardcode a
      name this plan guessed at**.

## Phase 2: User Story 2 — A loop can name a quality step, and one that does not costs nothing

### Tests for this story (write FIRST, must fail)

- [ ] T007 [P] [US2] (spec US2-S1) In `tests/test_quality_step_config.py`, assert
      a v2 manifest with `quality` in `verify:` resolves and the step appears in
      the resolved order.
- [ ] T008 [P] [US2] (spec US2-S2) Assert `quality` before `gates`, and `quality`
      before `diff_check`, are each refused **by name** — two separate
      assertions, because one refusal passing does not prove the other exists.
- [ ] T009 [P] [US2] (spec US2-S3) Assert `judge` before `quality` is refused.
- [ ] T010 [P] [US2] (spec US2-S4) Assert a scanner name outside the closed set is
      refused with the admissible names listed in the message.
- [ ] T011 [P] [US2] (spec US2-S5) Assert a manifest omitting `quality` resolves
      to a `FactoryConfig` equal to today's, **and** that no scanner module
      appears in `sys.modules` afterwards. The second half is the portability
      property and an assertion about the config alone cannot see it.
- [ ] T012 [P] [US2] (spec US2-S6) Assert two manifests differing only in scanner
      name produce different `loop_digest` values.
- [ ] T013 [P] [US2] (spec US2-S7) Assert a v1 manifest declaring `quality:` is
      refused, matching how v1 already refuses `ladder:` and `verify:`.
- [ ] T014 [P] [US2] (trap 9) Assert a repo declaring a **gate** named `quality`
      is refused, as `_RESERVED_GATE_NAMES` already refuses `gates`, `diff_check`,
      `judge` and `config`.

### Implementation for this story

- [ ] T015 [US2] (FR-005) Add `quality` to `_VERIFY_STEPS`
      (`factory/verify/factory_yaml.py:150`).
- [ ] T016 [US2] (trap 9) Add `quality` to `_RESERVED_GATE_NAMES`
      (`factory/verify/factory_yaml.py:147`).
- [ ] T017 [US2] (FR-006) Extend the ordering rules in `_read_verify`
      (`factory/verify/factory_yaml.py:650`). **Copy the existing `judge`
      ordering check; do not rewrite the function.**
- [ ] T018 [US2] (FR-007) Parse a `quality:` block with a closed-set `scanner:`
      name. Model it on `ladder:` at `factory/verify/models.py:260` — a nested
      dataclass with a default factory, not loose keys.
- [ ] T019 [US2] (FR-008) Confirm the default `verify_order`
      (`factory/verify/models.py:264`) is unchanged and that resolution imports
      no scanner module.
- [ ] T020 [US2] (FR-009) Fold the resolved scanner into `loop_digest` and
      `loop_summary`.
- [ ] T021 [US2] (FR-010) Pin the `quality:` block at dispatch from the operator
      clone, alongside the rest of the loop. **It must never be read from the
      node worktree** — that asymmetry is the whole reason a gate was rejected
      as the destination.
- [ ] T022 [US2] (FR-011) Refuse `quality:` in a v1 manifest.

## Phase 3: User Story 3 — A scanner is an adapter resolved by name

This is the hook system. Follow `factory/mergequeue/forge.py:286-320` and
`factory/notify/adapter.py:70` closely — two working precedents, both lazy-import
registries held to a config's closed set. Invent nothing.

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1) In `tests/test_scanner_registry.py`, assert
      importing the registry module imports no candidate scanner's package.
- [ ] T024 [P] [US3] (spec US3-S2) Assert the `sarif` adapter runs a declared
      command in a worktree, reads the SARIF it left, and returns parsed
      findings — driven by a fixture SARIF file, with no real scanner installed.
- [ ] T025 [P] [US3] (spec US3-S3) Assert the `none` scanner returns an empty
      report and executes nothing.
- [ ] T026 [P] [US3] (spec US3-S4) Assert **three** separate failure modes each
      produce `scanner_unavailable` with a reason and **raise nothing**:
      non-zero exit, timeout, malformed SARIF. One assertion covering one mode
      does not prove the other two.
- [ ] T027 [P] [US3] (spec US3-S5) Assert the registry's keys and the config's
      closed set match **in both directions**. Copy the messenger conformance
      suite's structure.
- [ ] T028 [P] [US3] (spec US3-S6) Assert a scanner command that cannot run under
      the sandbox records `scanner_unavailable` rather than an empty report — the
      two must be distinguishable, or trap 1's failures will look like clean scans.
- [ ] T029 [P] [US3] Assert resolving an unregistered name raises with the
      registered names listed.

### Implementation for this story

- [ ] T030 [US3] (FR-012) Add `factory/verify/scanner.py`: a `Scanner` Protocol,
      module-level `_REGISTRY`, a `register_scanner`, and `resolve_scanner(name)`
      with the lazy-import-then-retry shape from
      `factory/mergequeue/forge.py:304-320`.
- [ ] T031 [US3] (FR-014) Ship the built-in `sarif` adapter: run a declared
      command in the worktree, read the SARIF file, parse it. **It must not know
      which tool produced the file** — that ignorance is what makes scanners
      swappable.
- [ ] T032 [US3] (FR-015) Ship the built-in `none` scanner.
- [ ] T033 [US3] (FR-016) Make every failure path return a report, never raise.
      Precedents: `judge_unavailable`, `DeliveryReceipt`, and `CONFIG_ERROR`
      being one result rather than zero.
- [ ] T034 [US3] (FR-013) Add the closed set to
      `factory/controlplane/config.py` beside `KNOWN_ESC_ADAPTERS`
      (`factory/controlplane/config.py:51`).
- [ ] T035 [US3] (trap 3) Confirm the new module does not import
      `factory/verify/judge.py`. `tests/test_verification_sweep.py` enforces the
      single-importer rule on the import graph.

## Phase 4: User Story 4 — Findings are scoped to the diff, recorded, and change nothing

### Tests for this story (write FIRST, must fail)

- [ ] T036 [P] [US4] (spec US4-S3, **the central test**) Assert that for one
      fixed set of gate, diff-check and judge results, an attempt with a
      400-finding scan and an attempt with a clean scan compose the **same**
      `OverallVerdict`.
- [ ] T037 [P] [US4] (trap 4) Assert by signature inspection that
      `compose_result` (`factory/verify/models.py:517`) takes no quality
      parameter. This is the test that survives a refactor; T036 alone does not,
      because a future `mode` flag would keep T036 green.
- [ ] T038 [P] [US4] (spec US4-S1) Assert findings outside the attempt's changed
      lines are dropped from the scoped set.
- [ ] T039 [P] [US4] (spec US4-S2) Assert every finding in a file the attempt
      created is in scope.
- [ ] T040 [P] [US4] (spec US4-S4) Assert the row carries scoped findings, the
      scanner name and its version string.
- [ ] T041 [P] [US4] (spec US4-S5) Assert quality evidence is NULL when the scan
      never ran, and distinguishable from a recorded empty report. Mirror the
      `judge_verdict` test (`factory/verify/store.py:158`).
- [ ] T042 [P] [US4] (spec US4-S6) Assert a redelivered activity upserts onto the
      first run's row.
- [ ] T043 [P] [US4] (trap 6) Assert a finding whose path does not resolve inside
      the worktree is recorded and excluded, never mapped to a wrong file.
- [ ] T044 [P] [US4] (edge case) Assert a SARIF result with no `physicalLocation`
      is recorded and excluded, never mapped to line 1.
- [ ] T045 [P] [US4] Assert a pre-077 row reads its quality column as NULL after
      migration, and is never backfilled.

### Implementation for this story

- [ ] T046 [US4] (FR-017, trap 2) Scope findings to changed lines. **Reuse
      `split_sections` (`factory/verify/diffbounds.py:69`)** and extend within
      that module's discipline for hunk-header line numbers. Do not write a
      second unified-diff parser.
- [ ] T047 [US4] (FR-018, trap 6) Normalise SARIF URIs against the worktree root;
      refuse to scope anything that does not resolve inside it.
- [ ] T048 [US4] (FR-020, FR-022) Add the evidence column. Bump `SCHEMA_VERSION`
      6 → 7 and copy the additive `ALTER TABLE ... ADD COLUMN` migration at
      `factory/verify/store.py:368-371`. Add the column to the list at
      `factory/verify/store.py:439`.
- [ ] T049 [US4] (FR-021) Write NULL when the scan did not run.
- [ ] T050 [US4] (FR-019, trap 4) Wire the scan into the verifier activity so the
      report reaches the **store and nothing else**. `compose_result` gains no
      parameter.
- [ ] T051 [US4] (trap 7) Capture the scanner's version at scan time.

## Phase 5: User Story 5 — The recorded scans are queryable

### Tests for this story (write FIRST, must fail)

- [ ] T052 [P] [US5] (spec US5-S1) Against a store seeded with known rows, assert
      per-rule counts ordered by frequency over a selectable window.
- [ ] T053 [P] [US5] (spec US5-S2) Assert per-story output gives findings per
      attempt, so "did attempt 2 improve" is answerable.
- [ ] T054 [P] [US5] (spec US5-S3) Assert pre-077 rows report as **unmeasured**,
      not as zero findings. A zero here would silently halve any average the
      follow-on spec sets a threshold from.
- [ ] T055 [P] [US5] (spec US5-S4) Assert a scanner-name change inside the window
      is visible in the output.

### Implementation for this story

- [ ] T056 [US5] (FR-023) Add the read surface under `factory/cli/`.
- [ ] T057 [US5] (FR-024) Report unmeasured rows as unmeasured.
- [ ] T058 [US5] (FR-025) Surface scanner-name changes within a window.

## Verification

- [ ] T059 Full suite green: `uv run pytest -q`.
- [ ] T060 Confirm `git diff pyproject.toml uv.lock` is empty across the whole
      spec. **No story here adds a dependency** — the Constitution III approval
      is the operator's to spend after US1 reports, with a `docs/decisions.md`
      entry.
- [ ] T061 Run a real epic end to end with `quality` absent from `verify:` and
      confirm behaviour and `loop_digest` are unchanged (SC-001). A green suite
      is evidence, not proof; this repository has shipped a fully green run of a
      command that could not start.
- [ ] T062 Run a real epic with `quality` present and a scanner that reports
      findings, and confirm the verdict is what it would have been without one
      (SC-003, SC-004).
