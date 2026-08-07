# Tasks: Roadmap Scheduler

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution I): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [ ] T001 Operator: confirm 003 and 006 have landed on the target's default
      branch (this spec's own frontmatter declares the 003 dependency), then
      re-verify plan.md's reuse inventory against that tree — the inventory was
      drafted 2026-08-07 against `ergane-buildout` + the `003-landed` branch
      and landings may have moved line numbers or shapes. Correct the plan
      before deriving, not the nodes after.

---

## Phase 2: User Story 1 — The roadmap is machine-readable (Priority: P1) 🎯 MVP

**Goal**: frontmatter intent states + `depends_on_landed` edges parse purely,
readiness computes, and one command renders the whole roadmap with blockers
named.

**Independent Test**: a fixture corpus of spec files yields states and edges;
unknown keys/states/cycles reject with named findings; the render names every
blocker.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; `factory/workgraph/derive.py`, `factory/workgraph/models.py`,
      `factory/verify/criteria.py` exist and plan.md's parser-safety claims
      hold (frontmatter is fence-inert to both scanners) — constitution I
      gate; STOP and report blocked if not satisfied.
- [ ] T003 [P] [US1] Write frontmatter-grammar cases FIRST against a fixture
      corpus (one directory per fixture, the `tests/fixtures/README.md`
      convention): valid states parse; absent frontmatter reads `draft`
      (FR-002); unknown key, unknown state value, non-mapping frontmatter, and
      a `depends_on_landed` entry naming no spec directory each reject with a
      finding naming offender and file; a spec-level dependency cycle reports
      only the specs on it; the parser opens no file beyond the corpus (the
      `test_derivation_opens_no_file` purity pattern) — must fail.
- [ ] T004 [P] [US1] Write readiness cases FIRST: `ready` + attested-landed
      dependency → dispatchable; `ready` + unsatisfied dependency → blocked
      with the edge named; `deferred`/`draft` never dispatchable; attested vs
      observed satisfaction are distinguishable in the computed graph (FR-003;
      observed arrives in US2, the seam must exist now) — must fail.
- [ ] T005 [US1] Write render cases FIRST for the CLI: every spec appears with
      its state; each blocked spec names its unsatisfied dependencies; output
      is deterministic; exit codes follow the existing contract (`1`
      operator-fixable, `2` service not answering — though US1's render needs
      no service, the contract is stated once) — must fail.

### Implementation for User Story 1

- [ ] T006 [US1] Implement `factory/roadmap/models.py` (entry, graph, states
      as `StrEnum` — the Temporal-converter spelling `workgraph/models.py`
      documents) and the pure frontmatter reader with staged `_Rejections`-
      style findings, until T003 passes. Generalize `_find_cycle` to take an
      adjacency mapping and reduce the two existing byte-identical copies
      (`workgraph/models.py`, `workgraph/derive.py`) to callers of it — three
      duplicates is the defect the second copy's docstring warned about.
- [ ] T007 [US1] Implement readiness computation until T004 passes.
- [ ] T008 [US1] Implement the roadmap render command (new `factory-roadmap`
      console script or subcommand — match `factory-epic`'s parser shape) until
      T005 passes.
- [ ] T009 [US1] Add frontmatter to the existing specs: `003-merge-queue`,
      `006-interpreter-hardening`, `007-parallel-dispatch`,
      `008-operator-channel` with their true states and dependency edges;
      `004-budget-enforcement` as `deferred`; `001/002/005` as attested
      `landed`. Do not touch any `**Status**:` prose line — dead text stays
      dead (plan.md § US1 trap).

---

## Phase 3: User Story 2 — A ready spec dispatches when its dependencies land (Priority: P1)

**Goal**: `RoadmapWorkflow` starts dispatchable specs as child `EpicWorkflow`s,
bounded (default 1), pre-dispatch refusals park with findings, landed edges
compute from child results.

**Independent Test**: scripted two-spec roadmap (`B` depends on `A`) runs A to
landed and dispatches B unprompted; a failed landing leaves B blocked.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Write scheduler cases FIRST under time skipping with scripted
      children (fakes-under-real-names, the `ScriptedWorld` pattern): a
      dispatchable spec's child starts with the correct `EpicInput` and id
      convention; completion with all landings MERGED marks the dependency
      observed-landed and dispatches the dependent in the same pass; completion
      with a FAILED node leaves dependents blocked and reported
      finished-but-not-landed; two dispatchable specs respect the bound and
      declaration order (FR-005); a pre-dispatch refusal parks the spec with
      the finding verbatim and the roadmap proceeds to other work (FR-006) —
      must fail.
- [ ] T011 [P] [US2] Write child-policy cases FIRST: `parent_close_policy` is
      ABANDON (terminating the roadmap leaves the child running — SC-004); a
      dispatch that collides with a RUNNING workflow under the child's id parks
      with the collision named, never adopts; a closed id is reused cleanly
      (tonight's five-closed-runs precedent); capacity accounting counts an
      operator-started `epic-*` workflow the roadmap did not start — must fail.
- [ ] T012 [P] [US2] Write the credential sweep case FIRST: no key value can
      reach frontmatter parsing output, parked findings, `roadmap_status`
      payloads, or the roadmap's workflow input (FR-009, the grep-backed 001
      pattern) — must fail.

### Implementation for User Story 2

- [ ] T013 [US2] Implement `RoadmapWorkflow` dispatch (child start, landed-edge
      evaluation from `EpicStatus`, bound, parking) and the pre-dispatch
      activities (clone at default branch; derivation behind a thin activity;
      reuse 006's preflight and 003's onboarding as they stand) until T010,
      T011, T012 pass. Register in `factory/worker.py` `WORKFLOWS` and widen
      `tests/test_worker.py`'s AST activity scan to every module invoking
      `workflow.execute_activity` — the scan currently reads only
      `workgraph/workflow.py` and would leave roadmap activities unchecked.
      Mind the D-021 naming trap (plan.md § US2): children are `dispatches`,
      never `requests`; the knob is `max_concurrent_epics`.

---

## Phase 4: User Story 3 — The roadmap runs indefinitely and answers the operator (Priority: P2)

**Goal**: continue-as-new at quiescence bounds history; pause/resume/promote
signals and `roadmap_status` give the operator the same grip on the roadmap
the epic surface gives on a node.

**Independent Test**: ten scripted epics leave every run's history under a
constant; pause parks between epics; a promotion dispatches next pass; state
survives continue-as-new.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T014 [US3] Write durability cases FIRST: after each child concludes and
      the roadmap is quiescent it continues-as-new with an explicit carry-over
      input (parked findings, promotions, pause flag, bound); no run's history
      event count grows with the number of epics (the 006-US1 history-bound
      proof, one level up); continue-as-new never fires with a child open;
      a restart re-reads the world and does not double-dispatch — must fail.
- [ ] T015 [P] [US3] Write operator-surface cases FIRST: `pause_roadmap` parks
      dispatch between epics while the in-flight child finishes;
      `resume_roadmap` releases; `promote_spec` makes a draft dispatchable on
      the next pass and `roadmap_status` reports the promotion as such;
      `roadmap_status` reports every spec's state, the running child, parked
      findings, attested-vs-observed landings, and the bound in force — must
      fail.

### Implementation for User Story 3

- [ ] T016 [US3] Implement continue-as-new with the carry-over dataclass until
      T014 passes. There is no continue-as-new precedent in this repo; verify
      the SDK mechanics empirically before the test is written in stone, the
      way 006-us1's attempt did for cancellation (its transcript is the
      precedent for *how*).
- [ ] T017 [US3] Implement signals, query, and CLI start/status until T015
      passes.
- [ ] T018 [US3] Final sweep + docs (FR-010): record the D-002 supersession in
      `docs/decisions.md` at the next free number and update the two places
      that assert one workflow type (`factory/worker.py` docstring,
      `tests/test_worker.py` docstring); extend `docs/architecture.md`'s module
      table with `factory/roadmap/`; grep-backed assertion that no credential
      reaches any roadmap surface.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — including re-verifying the
  reuse inventory this spec's plan leans on.
- Phase 2 (US1) has no dependency and is the MVP: the status board's READY
  column becomes a computation the day it lands.
- Phase 3 (US2) depends on US1's grammar and readiness seam.
- Phase 4 (US3) depends on US2's scheduler existing.

## Implementation Strategy

US1 alone is worth landing if anything must be cut — it converts roadmap
judgment into computation and costs no new workflow type. US2 is the feature
and carries the D-002 supersession. US3 is what makes it unattended; until it
lands, an operator restarting the roadmap between epics is a tolerable
substitute. Nothing here modifies the epic interpreter — the child-workflow
seam consumes `EpicWorkflow`'s public contract only, which is what keeps this
spec buildable by the factory it schedules.
