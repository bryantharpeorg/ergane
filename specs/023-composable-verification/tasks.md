# Tasks: Composable Verification

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip. T011 is this
file's one declared exception, for a reason it states inline.

The stakes here are the parser that decides every future node's fate and the
truth table that decides every verdict. A defect in either is not a bug in one
epic — it is a bug in every epic after it. Refusal tests outnumber acceptance
tests in this spec on purpose.

Tasks marked `[P]` touch disjoint files within their story and may be written in
any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [x] T001 Operator preflight. Re-verify every `file:line` anchor in plan.md
      against the tree that will host this work, and record findings here as
      021's T001 did — findings supersede plan.md where they differ. Beyond
      line drift, confirm four facts specifically:

      (a) The worker's installed parser still rejects `version: 2` (nothing
      landed partially) — `python -c` a two-line parse of a v2 snippet and
      show the `FactoryConfigError`.

      (b) `compose_result`'s current behaviour when handed an empty
      `gate_results` list plus a failing output check — T011's design turns
      on whether the FAIL guard already exists or must be added. Read the
      truth table, do not guess.

      (c) The exact judge-absent states `compose_result` and the store
      already model (`judge_unavailable` at minimum), so trap 8's third
      state (excluded-by-loop) is added beside them, not on top of them.

      (d) The parked-findings path the roadmap will reuse for a malformed
      manifest (plan § US2) — name the function and confirm a park carries
      an error detail a human can read later.

      **T001 findings, done 2026-08-17 against `deff9d0` (supersede plan.md
      where they differ):**

      General anchor state: the merges of 2026-08-17 (#157–#164) touched no
      cited file in `factory/verify/`, `factory/workgraph/`,
      `factory/cli/nouns/build.py`, `factory/activities/` or
      `factory/mergequeue/` except `factory/roadmap/workflow.py` (#162).
      Line drift from the 2026-08-10 numbers is uniform and small; every
      named construct exists — resolve by name.

      - **The live manifest is `ergane.yaml`** (040-manifest-rename).
        `MANIFEST_NAME = "ergane.yaml"` (`factory_yaml.py:59`);
        `factory.yaml` is `LEGACY_MANIFEST_NAME`, kept byte-identical at the
        repo root, and 040 forbids the legacy name as a quoted literal in
        that module — spell it via `LEGACY_MANIFEST_NAME` if a test needs
        it. Wherever plan.md or a task says "repo root `factory.yaml`", read
        "both root manifests, `ergane.yaml` the live one". US2's dispatch
        read joins via `resolve_manifest_path()` + `load_factory_config()`
        the way `factory/mergequeue/merge_activities.py:548-552` already
        does — not `Path(target_repo) / MANIFEST_NAME`.
      - (a) CONFIRMED on this tree: `parse_factory_config` on a
        `version: 2` snippet raises `FactoryConfigError: ergane.yaml:
        [version] declares `version: 2`; this factory supports only the
        integer literal 1` (rule `version`).
      - (b) The empty-gate-list FAIL guard ALREADY EXISTS: `gates_passed`
        (`factory/verify/models.py:443-457`) is `bool(gate_results) and
        all(...)`, with a docstring naming exactly this hazard. T011
        therefore takes its declared-exception branch — it passes
        immediately and stands as the regression pin; `compose_result`
        needs no change before T14.
      - (c) The judge-absent states today are two: `judge is None`
        (skipped-by-guard; composes PASS through `models.py:529` when gates
        and output pass) and `judge_unavailable`
        (`JudgeOutcome.UNAVAILABLE`, flag computed at `models.py:527`,
        store column `store.py:135`). Excluded-by-loop is a third state
        added beside these two.
      - (d) The roadmap park is `_park` (`factory/roadmap/workflow.py:1196`),
        writing `ParkedFinding(check, detail)` — `detail` is free text a
        human reads later. That file was touched tonight by #162; re-grep
        before citing lines in it.
      - The plan's four `escalation_timeout_s` call sites are now TWO:
        `factory/workgraph/workflow.py:1857` (node path) and `:2504`
        (landing path). `:1869`/`:2423`/`:2432` no longer resolve.
      - The plan's "roadmap-failure path at `notify_activities.py:549` uses
        the module constant" points at nothing: the roadmap parks rather
        than escalates, and `ESCALATION_TIMEOUT_S` appears only as dataclass
        defaults (`notify_activities.py:163`,
        `factory/escalation/workflow.py:146`). Trap 7's "do not fix it"
        instruction is moot; the 7200-parity requirement stands.
      - The "roadmap bound check `roadmap/workflow.py:546-553`" example of
        the type-identity idiom is gone from that file; surviving instances
        are `factory_yaml.py:463` and `factory/controlplane/config.py:799`.
        Trap 1 stands unchanged.
      - T010's "extend `tests/test_worker.py`'s AST check" is unnecessary:
        `_invoked_activity_names` (`test_worker.py:142`) discovers invoked
        activities generically from the workflow sources, so a new
        `read_loop_config` is caught automatically once its caller lands.
        Only `factory/worker.py`'s `ACTIVITIES` (`:98`) needs the edit;
        extending the hand-listed `_SURFACE_ANCHORS` is optional.
      - `_TOP_LEVEL_KEYS` is now EIGHT keys including `roadmap` and `forge`
        (049) — any test pinning the v1 vocabulary must include them.
      - US4's store column is not just a `_RESULT_COLUMNS` entry: the store
        carries `SCHEMA_VERSION = 3` with an explicit `_migrate`
        (`store.py:278-300`). The additive column needs the version bump
        plus a migration branch, and a pre-023 row still reads as absent.
      - Baseline suite on this host at `deff9d0`: 3312 passed, 47 skipped.
        The plan's "44 skips" is stale — measure your own baseline at your
        base commit before writing anything, and declare any skip beyond it.

---

## Phase 2: User Story 1 — The manifest can declare the loop (Priority: P1) 🎯 MVP

**Goal**: `parse_factory_config` accepts schema v2 — `ladder:`, `verify:`,
arbitrary gate names — refuses every violation by name, and parses v1
identically to today.

**Independent Test**: a full v2 manifest parses to a typed config; every
floor violation raises `FactoryConfigError` with its own stable rule slug;
the untouched v1 suite is green.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      runs; `tests/test_factory_yaml.py` exists and passes. Note any
      pre-existing live-tier failures and confirm they are unrelated before
      starting. STOP and report blocked if anything else is red.
- [ ] T003 [US1] (spec US1-S1) Write v2 acceptance cases FIRST in
      `tests/test_factory_yaml.py`: a `version: 2` manifest with gates
      `unit`/`contract` (order preserved), `verify: [diff_check, gates,
      judge]`, and a partial `ladder:` parses to a config carrying exactly
      those values with every undeclared ladder field at today's
      `VerificationConfig` default; a v2 manifest with *no* `ladder:` or
      `verify:` parses to today's defaults and today's order including
      `judge` — must fail.
- [ ] T004 [P] [US1] (spec US1-S3, US1-S4, US1-S5) Write refusal cases FIRST, one per named rule, asserting
      both the raise and the `.rule` slug: unknown ladder key; boolean where
      an integer belongs (`max_attempts: true` — trap 1); each ceiling
      violated (`max_attempts: 11`, `escalation_timeout_s: 90000`,
      `debugger_cycles: 4`); `verify:` empty, duplicated, unknown step,
      missing `gates`, missing `diff_check`, `judge` before either; a gate
      named `judge`, `diff_check`, `gates`, or `config` (reserved — the
      last is the synthetic name `config_error_result` emits); `ladder:` or
      `verify:` under `version: 1` refused as unknown keys exactly as today
      — must fail.
- [ ] T005 [P] [US1] (spec US1-S2, US1-S6) Write the v1-identity case FIRST: parse this repository's
      own committed manifest — `ergane.yaml`, the live name since 040; T001
      explains the rename — and assert the result equals today's
      field-for-field — the file that must stay byte-identical (FR-011) is
      also the regression fixture that proves v1 semantics never moved —
      must fail only if v1 handling changes.

### Implementation for User Story 1

- [ ] T006 [US1] Extend `factory/verify/factory_yaml.py` and
      `factory/verify/models.py` until T003–T005 pass: `_SUPPORTED_VERSION`
      becomes a pair with version-conditional vocabulary; new readers follow
      `_read_landing_branch`'s shape (optional, absent-means-today,
      type-identity ints, named rules); `FactoryConfig` grows
      `ladder: VerificationConfig` and `verify_order: tuple[str, ...]` with
      defaults equal to today. **No file outside these two and their tests.**
      Do not touch either repo-root manifest — `ergane.yaml` or its
      byte-identical legacy copy `factory.yaml` (trap 0, T001).

---

## Phase 3: User Story 2 — The declared ladder reaches the running epic (Priority: P1)

**Goal**: both dispatch paths read the committed manifest and pin the loop
into `EpicInput`; nothing a worktree writes can move it; the escalation row
advertises the configured deadline.

**Independent Test**: `ergane build start` against a v2 fixture carries the
declared caps; a scheduled child carries a config read at *its* dispatch; a
worktree `ladder:` rewrite changes nothing; timer and row agree at 7200s.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T007 [US2] (spec US2-S1, US2-S2, US2-S5) Write CLI dispatch cases FIRST: `_start_epic` against a
      fixture repo with a v2 manifest starts the workflow with the declared
      caps and order in `EpicInput` (assert the input directly — "the
      default happens to match" proves nothing, 021's T006 precedent);
      against a v1 fixture, today's defaults exactly; against a malformed
      manifest, dispatch refused at preflight with the parse rule named and
      a non-zero exit — must fail.
- [ ] T008 [P] [US2] (spec US2-S3, US2-S6) Write roadmap dispatch cases FIRST under time skipping:
      `_dispatch` sources the child's config from the new activity (script
      it — the seam pattern the roadmap suite already uses), so a manifest
      change between two dispatches reaches the second child; a parse
      failure parks that spec with the error recorded and the run continues
      to other specs (trap 6) — must fail.
- [ ] T009 [P] [US2] (spec US2-S4) Write tamper and parity cases FIRST: a node worktree
      that rewrites its own manifest's `ladder:` to `max_attempts: 99` still
      escalates on the pinned budget (SC-003 — the test must show the
      rewrite *would* have granted attempts if read); with
      `escalation_timeout_s: 7200` the workflow's wait and the stored row's
      `expires_at` both reflect 7200 — **the non-default value is the test**
      (trap 7; at 3600 the two sources are indistinguishable) — must fail.
      **Split this into two tests with two subjects (trap 7a — this is the
      scenario that failed 023's first run twice):** the timer half against
      the workflow with a scripted activity, and the row half calling the
      **real** `send_escalation` through `ActivityEnvironment` with
      `timeout_s=7200`, asserting `expires_at == sent_at + 7200s` computed
      from the record. A scripted activity returns a hardcoded `expires_at`,
      so a parity assertion made against it proves nothing and the judge
      will refuse it.
- [ ] T010 [US2] Implement until T007–T009 pass: manifest read in
      `_run_preflight`'s path (`FactoryConfigError` → `OperatorError`, rule
      named); new `read_loop_config` activity; its registration in
      `factory/worker.py` **and** `tests/test_worker.py`'s AST check in this
      same diff (trap 5 — unregistered is a silent stall, not an error);
      `_dispatch`'s config source replaced; `EpicInput` grows the order
      field additively with today's default (trap 3 — payload boundary;
      never rename, never retype).

---

## Phase 4: User Story 3 — The verify list drives the loop (Priority: P1)

**Goal**: `_verify` walks the declared order, fail-fast, judge guard intact,
judge-less loops mint nothing, defaults replay today's exact sequence.

**Independent Test**: declared `[diff_check, gates, judge]` runs no gate
command after a failed diff check; a judge-less loop never reaches the judge
key mint; v1 and default-v2 execute today's sequence against the unmodified
interpreter suite.

### Tests for User Story 3 (write FIRST)

- [ ] T011 [US3] (spec US3-S4) Write the trap-4 pin FIRST, as a unit test of
      `compose_result`: zero gate results plus a failing output check
      composes to FAIL, and zero gate results plus *nothing failing* is
      impossible-by-construction or composes to FAIL — never
      pass-by-default. **Declared exception to must-fail**: if T001(b)
      found the guard already present, this test passes immediately and
      stands as the regression pin; if it found the truth table assumes
      gates always ran, this test fails and the guard is added to
      `compose_result` *before* T014 touches `_verify`. Either way the pin
      exists before the first code path that can produce the input.
- [ ] T012 [US3] (spec US3-S1, US3-S2, US3-S3) Write order cases FIRST under time skipping, asserting
      activity invocation sequences directly: under `[diff_check, gates,
      judge]` an empty-diff attempt fails with **zero** gate commands run
      (SC-002); under a judge-less list a passing attempt composes PASS
      with `run_judge` never invoked and no judge key minted (SC-005 —
      assert `issue_attempt_key` saw no judge-persona call); under a v1
      manifest and under a v2 manifest with no `verify:`, the executed
      sequence is byte-for-byte today's; where `judge` is declared,
      `judge_required`'s short-circuit still skips it when scoring cannot
      matter — must fail.
- [ ] T013 [P] [US3] (spec US3-S5) Write the recorded-steps case FIRST: the verification
      result records which steps executed, and a judge excluded by the loop
      is recorded as exclusion — a third state beside ran and
      `judge_unavailable`, never conflated with an outage (trap 8; T001(c)
      names the existing states) — must fail.
- [ ] T014 [US3] Rewrite `_verify` as a walk over the declared order until
      T011–T013 pass. Fail-fast between steps; the judge's guard and
      `compose_result`'s truth table unchanged for every legal order; the
      two manifest-read sites keep their asymmetry and each gets a comment
      naming it (trap 2 — gate commands are worktree-read with a CI
      backstop; loop config is dispatch-pinned because it has none).

---

## Phase 5: User Story 4 — The verdict names its definition of verified (Priority: P2)

**Goal**: every verification row and PR body names the loop that produced it;
the default loop is a described state with a stable digest.

**Independent Test**: rows carry digest + summary; equal loops digest
equally; a v1 repo's rows name the explicit default; the PR body renders the
loop line.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T015 [US4] (spec US4-S1, US4-S3, US4-S4) Write digest and store cases FIRST: the digest is stable
      across attempts under the same loop and differs across different
      loops; the unconfigured default digests to a named constant the test
      asserts; the store column is additive and a pre-023 row reads as
      absent, never backfilled — must fail.
- [ ] T016 [P] [US4] (spec US4-S2) Write the PR body case FIRST: `render_pr_body`'s
      evidence includes one line naming declared order, ladder caps and
      judge presence, and no credential, proxy URL, or transcript path
      appears in it (the PR body is public; the existing body tests are the
      pattern) — must fail.
- [ ] T017 [US4] Implement until T015–T016 pass: canonical rendering +
      SHA-256 digest, `VerificationResult` field, store column,
      `render_pr_body` line.
- [ ] T018 [US4] Final sweep and docs: record the decision-log entry at the
      next free number (loop composition as declared data; the
      environment-constraints wording amendment per spec § Assumptions, with
      the constitution version bump); extend `docs/architecture.md`'s
      manifest and verification sections (schema v2, the dispatch pin, the
      two-read asymmetry); `git diff` both repo-root manifests —
      `ergane.yaml` and the legacy `factory.yaml` — against the epic's base
      and paste the empty output (FR-011).

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — T011's shape and trap 8's
  third state both hang on what T001 finds.
- Phase 2 (US1) is the MVP: a pure parser change, zero behavioural effect,
  every later story imports its types.
- Phases 3, 4 and 5 chain on the previous **merged**: US2 and US3 both edit
  `factory/workgraph/workflow.py`, US2 additionally the CLI and roadmap
  dispatch paths, US4 the result types US3 populates. One module,
  no registry trick to split it — the chain is what the files dictate, the
  same reason as 021.
- Dispatch this epic **by hand**, not through the roadmap: US2 edits
  `_dispatch` itself, and a scheduling parent mid-flight across its own
  dispatch path is 021 trap 7 with a sharper edge.
- After landing: restart the worker **before** any repo (this one included)
  commits a `version: 2` manifest — the running worker's parser decides
  CONFIG_ERROR, and it learns v2 only by restart (trap 0).

## Implementation Strategy

US1 alone is a complete, landable slice — a parser that speaks v2 while
nothing yet emits it. US2 makes a declared ladder real and closes the tamper
question while the verify chain is still today's. US3 is the visible half —
order, fail-fast, judge-less loops — and carries the truth-table risk, which
is why its pin test precedes its rewrite. US4 is what makes composition
auditable rather than merely possible, and it is deliberately last: a digest
describes loops that exist, and until US3 lands there is exactly one.

Nothing here touches salvage, attribution, landing, personas, or a single
timeout class — the platform floor this spec exists to leave alone.
