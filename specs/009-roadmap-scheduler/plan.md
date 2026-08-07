# Implementation Plan: Roadmap Scheduler

**Branch**: `009-roadmap-scheduler` | **Date**: 2026-08-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-roadmap-scheduler/spec.md`

## Summary

The factory gains its second workflow type: a long-lived `RoadmapWorkflow`
that reads spec frontmatter (intent), computes readiness against landed
dependencies (observation), and dispatches each dispatchable spec as a child
`EpicWorkflow` — woken by completion events, bounded to one concurrent epic by
default, continued-as-new at quiescence so no run's history grows with the
number of epics. The night this was drafted, the gap it closes was measured
directly: 003 landed at 22:36 UTC and dev-ready 007 sat idle behind it for
want of an operator glance.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined,
each verified against the tree the night of drafting — and T001 re-verifies
them against the tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: `temporalio`, `yaml` — both on the approved roster
(`tests/test_final_sweep.py:487`). Frontmatter parsing needs no new
dependency. **This feature adds none.**

**Verified reuse inventory** (file:line as of drafting; T001 re-checks):

- `EpicWorkflow.run` returns `EpicStatus` (`factory/workgraph/workflow.py`,
  `return self.epic_status()`) — the child-workflow result. **Landed** is
  derived: `epic_state == COMPLETED` and every node's landing `MERGED`
  (`_all_landings_terminal`; `_LANDING_TERMINAL = {MERGED, KILLED}`).
  `EpicState` deliberately has no LANDED member — keep it derived.
- `depends_on_merged` (node-level, `factory/workgraph/models.py`) is the
  vocabulary precedent for spec-level `depends_on_landed`.
- CLI: `_connect()` and the id convention `workflow_id(epic_id) ->
  f"epic-{epic_id}"` (`factory/workgraph/cli.py`) — the roadmap takes the
  sibling convention `roadmap-<specs-root-name>` so ids cannot collide.
  Env-before-client ordering in `start_command` is the pattern to keep.
- Worker: `WORKFLOWS = [EpicWorkflow]` (`factory/worker.py`) — registration is
  a one-line append. `tests/test_worker.py` asserts membership with `in`, so
  it survives; **but its AST activity scan reads only
  `factory/workgraph/workflow.py`** and must be widened to every module that
  calls `workflow.execute_activity`, or the roadmap's activity dispatch goes
  unchecked.
- Frontmatter is parser-safe, verified: the deriver and criteria snapshotter
  treat only backtick/tilde lines as fences and have no positional heading
  requirement; the prompt assembler slices spec.md to `US<n>` sections and
  `FR-<n>` bullets, so frontmatter never reaches an agent prompt. It DOES ride
  `PromptSources.spec_text` into payloads — hence FR-009's closed key set.
- `_find_cycle` exists byte-identical in `factory/workgraph/models.py` and
  `factory/workgraph/derive.py`; the roadmap graph is the third caller.
  Generalize to `_find_cycle(adjacency: Mapping[str, Sequence[str]])` and
  reduce both existing callers to it — two duplicates was tolerable, three is
  the defect the copy comments warn about.
- Rejection style: the deriver's staged `_Rejections` discipline and
  `unknown_key` rule; the fixture-corpus pattern in `tests/fixtures/README.md`
  and `tests/test_derive.py` (`REJECTIONS` table) is the template for roadmap
  grammar rejections; `test_derivation_opens_no_file` is the purity pattern.
- Pre-dispatch reuse: 006-US2's preflight (model aliases, key collisions) and
  003-US3's onboarding gate (`validate_target_repo` / `onboard_target_repo`).
  Onboarding re-validates per epic by design, uncached — the roadmap inherits
  N preflights for N epics; inherit, do not optimize.

**Storage**: none. The roadmap's only durable state is its workflow input
(carried through continue-as-new) plus what it re-reads from the repo and
Temporal. No `.factory/` store is added — a store would be a second source of
truth for facts the system of record already holds.

**Testing**: `pytest`, `WorkflowEnvironment.start_time_skipping()`. Scripted
child epics follow the fakes-under-real-names pattern
(`ScriptedWorld.activities()` in `tests/test_interpreter.py`); the roadmap's
children can be a scripted `EpicWorkflow` whose run returns a prescribed
`EpicStatus`. The duplicated `env` fixture appears in three test files
already; a fourth copy is acceptable, consolidation is not this epic's job.

**Project Type**: single Python package; new module directory
`factory/roadmap/` (models + parsing, workflow, CLI), mirroring `workgraph/`'s
layout so the architecture doc's module table extends rather than bends.

## Constitution Check

- **I (test-first)**: every task pairs a failing test with implementation.
- **III (dependencies)**: none added; `yaml` and `temporalio` are roster.
- **V (credentials)**: FR-009. The roadmap CLI holds what the epic CLI already
  holds (master key for preflight); the workflow input carries none of it.
  Frontmatter's key set is closed so payload-borne text stays provably inert.
- **VI (salvage)**: untouched — node terminal paths belong to the epic.
- **VII (persona routing)**: untouched — the roadmap never chooses a model.

## Approach by story

### US1 — the grammar and the render (FR-001, 002, 003)

`factory/roadmap/models.py` + a pure reader: split frontmatter (leading
`---` fence pair, `yaml.safe_load`, closed key set), fold absent frontmatter
to `draft`, build the roadmap graph over `specs/*/spec.md`, validate with the
generalized `_find_cycle` and the dangling-dep check, compute readiness
(observed-landed is US2's input; at US1 the satisfied test covers attested
`landed` and reports the distinction). Render command lists every spec, its
state, and each blocked spec's unsatisfied edges by name.

**The trap**: `**Status**:` prose lines look like state and are not — 006's is
a four-sentence paragraph. The reader must never consult them; the honest
grammar is the new field only.

### US2 — the scheduler (FR-004, 005, 006, 009)

`factory/roadmap/workflow.py`: `RoadmapWorkflow` computes the dispatchable
set, runs pre-dispatch as activities (clone at default branch, derive — the
existing pure `derive_workgraph` behind a thin activity — then preflight +
onboarding), starts children with `workflow.start_child_workflow(
EpicWorkflow.run, EpicInput(...), id=workflow_id(spec), task_queue=TASK_QUEUE)`
and awaits completion. Refusals park the spec with the finding verbatim.

Child policies — no precedent in the repo, decide here, verify in T002:
**`parent_close_policy=ABANDON`** (killing or continuing the roadmap must
never kill an epic; SC-004) and default id reuse (closed ids are reusable —
tonight's `epic-006-interpreter-hardening` had five closed runs before its
sixth started; a *running* collision parks with the collision named).

Capacity accounting must include epics the roadmap did not start (edge case:
operator-started epic mid-flight when the roadmap boots) — an activity lists
open `epic-*` workflows at pass start; the roadmap dispatches around them.

**Naming trap (D-021, will bite exactly here)**: the sweep bans branching on
values named `requests`/`cost`/`tokens` and bans 18 enforcement words in
identifiers and strings — snake_case is split, so `max_cap` fails. The
concurrency knob is `max_concurrent_epics`; in-flight children are
`dispatches` or `children`, never `requests`.

### US3 — durability and the operator surface (FR-007, 008, 010)

Continue-as-new **at quiescence only**: after a child concludes and before the
next dispatch, when zero children are open — the one moment the carry-over is
small and no completion event can be lost. Carry-over is an explicit input
dataclass (parked findings, promotions, pause flag, the bound); everything
else is re-read on the new run — re-reading is what makes SC-004's "restarting
re-reads the world" true for free. There is no continue-as-new precedent in
the repo; the task that lands it must also prove the history bound (SC-003)
under time skipping, the way 006-US1 proves the attempt-loop bound.

Signals/query mirror the epic's four-signal-one-query shape: `pause_roadmap`
parks dispatch between epics (the in-flight child finishes — the epic pause
contract, one level up), `promote_spec` covers the gap until the frontmatter's
next edit and is reported as a promotion in `roadmap_status`. Kill semantics:
none at roadmap level beyond Temporal's terminate; ABANDON makes that safe.

FR-010's decision-log entry (D-002 supersession) is written at landing, next
free number — the invariant being superseded is asserted in
`docs/decisions.md`, `factory/worker.py`'s docstring, and a test docstring;
the sweep task updates all three.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| Lost completion event across continue-as-new | CAN closes the run; a child finishing mid-CAN would notify a corpse | CAN at quiescence only — zero open children, asserted in tests |
| Roadmap kills a mid-flight epic | Default parent-close terminates children | `parent_close_policy=ABANDON`, asserted (SC-004) |
| Double-dispatch after restart | New run forgets what the old run started | Capacity pass lists open `epic-*` workflows before dispatching; asserted with a pre-started child |
| D-021 sweep failures | Scheduler vocabulary collides with banned words | Naming chosen in this plan; sweep runs in CI via existing test |
| Grammar drift from deriver discipline | Two rejection styles in one repo | Reuse `_Rejections` staging + fixture-corpus rejection tests |
| Frontmatter payload leakage | spec_text rides PromptSources whole | Closed key set (FR-001) + FR-009 sweep assertion |
