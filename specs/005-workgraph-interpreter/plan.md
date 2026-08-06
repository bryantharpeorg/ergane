# Implementation Plan: Minimal WorkGraph Interpreter

**Branch**: `005-workgraph-interpreter` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-workgraph-interpreter/spec.md`

## Summary

The component that composes everything already built into a factory: one generic
Temporal workflow (namespace `factory`, task queue `workgraph`, D-002) that reads a
compiled WorkGraph JSON DAG per epic and drives every node through dispatch → agent
attempt → 002's verification ladder to a terminal state, unlocking downstream edges
only on PASS. The WorkGraph is never hand-authored: a pure deriver compiles the epic
spec's additive `## Work Graph` section (fenced YAML, one node per user story,
FR-011) into `workgraph.json`. Each producing node runs a headless coding agent
(Claude Code first) through the narrow D-018 adapter activity in its one worktree on
`factory/<epic>/<node>` (FR-013), bracketed by component 1's key lifecycle and
verified by component 2's activities exactly per
`specs/002-verification-gating/contracts/verification-flow.md`. Prompts are
assembled purely on the two-nested-loop model (inner ralph-derived contract,
advisory; outer 002 ladder, authoritative, FR-012). Node scheduling is sequential —
parallel execution, verifier nodes, and multi-epic scheduling are explicitly
deferred. A small `factory-epic` CLI (derive | start | status) and
pause/resume/kill signals are the operator's steering wheel; every attempt's
transcript is archived under the factory state directory (FR-007).

## Technical Context

**Language/Version**: Python 3.11+ (D-003)

**Primary Dependencies**: `temporalio` (workflow definition, activities, signals/
queries, time-skipping test environment), `pyyaml` (`## Work Graph` block, persona
registry) — both on the approved roster (constitution III). Stdlib: `asyncio` +
`subprocess` semantics via `asyncio.create_subprocess_exec` (adapter), `os`/`signal`
(process-group termination, orphan reaping), `shutil`/`pathlib` (transcript
archiving), `json` (workgraph.json), `argparse` (CLI), `uuid` (session ids).
Components 1 and 2 are consumed as-is through their activity surfaces. **No new
dependencies.**

**Storage**: No new store. Reuses `.factory/ledger.db` (001) and
`.factory/verification.db` (002) through their owning activities. Adds worker-host
filesystem state only: `.factory/worktrees/<epic>/<node>/` (the node's one
worktree), `.factory/transcripts/<epic>/<node>/attempt-<n>/` (FR-007 archives,
never committed to any repo), `.factory/run/` (adapter pid/pgid files for orphan
reaping). `workgraph.json` is a compiled, inspectable artifact written next to the
epic's spec by the deriver.

**Testing**: `pytest` + `pytest-asyncio`. Deriver: fixture specs under
`tests/fixtures/workgraph/` covering acceptance and every rejection (SC-006).
Adapter: `temporalio.testing.ActivityEnvironment` against a stub executable standing
in for the agent CLI (env construction, timeout TERM→KILL, classification,
transcript archiving — US2's independent test). Worktrees: `tmp_path` git repos.
Interpreter: `WorkflowEnvironment.start_time_skipping()` (binary proven on this
aarch64 host) with scripted fake activities — node transitions, edge unlocking,
retry/escalation routing, pause/kill signals, replay determinism (SC-001, SC-002,
US1/US3 independent tests). Live Tier 1 smoke behind an env-gated marker, following
the `live_proxy`/`live_telegram` pattern.

**Target Platform**: Single Linux worker host owning `.factory/` (001 topology),
alongside the Temporal dev server (namespace `factory`, D-006). Agent CLI (`claude`)
present on the worker host for live runs; tests use the stub.

**Project Type**: Library subpackage (`factory/workgraph/`) + one Temporal workflow
+ an activity surface (`factory/activities/agent_activities.py`) + a runnable worker
(`python -m factory.worker`) + a small operator CLI (`factory-epic`).

**Performance Goals**: Bootstrap scale — one epic at a time, nodes sequential
(parallelism deferred), single-digit node counts. Attempt wall-clock bounded by the
persona registry's `timeout` (FR-010); usage polling and activity heartbeats ~30s;
workflow history stays far below Temporal event limits at this scale.

**Constraints**: Workflow logic pure and replay-deterministic — all side effects in
activities (constitution IV, FR-001); agent self-reported success never influences
node state (FR-012); `LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN` stay in worker
env, read inside activities only (001/002 discipline) — the per-attempt virtual key
is the only credential allowed in payloads; transcripts stay on the worker host
(FR-007); vendored `.specify/templates/` are never modified (FR-011); no timeout,
model, or gate command hardcoded (constitution VII, FR-010); worktree salvage on
every termination path before cleanup (constitution VI).

**Scale/Scope**: Single operator, one epic in flight (the `.factory/` SQLite
constraint), ≤ ~10 nodes per bootstrap epic, attempt counts bounded by 002's ladder
caps.

## Constitution Check

*GATE: evaluated against constitution v2.2.0 before Phase 0; re-checked after Phase 1.*

| Principle | Status | Evidence |
|---|---|---|
| I. Build order, vertical slices | PASS | 001 and 002 are implemented and green (962 passed); 005 is next in the amended order (D-024) and consumes both strictly through their shipped activity surfaces. 003 starts only as this component's first dispatched epic. |
| II. Test-first | PASS | Every deliverable has a test strategy above; tasks will order tests first (the ralph loop enforces the discipline mechanically). |
| III. Ask before dependencies | PASS | Zero new dependencies; `temporalio` and `pyyaml` are roster items. The agent CLI is a worker-host binary, not a Python dependency. |
| IV. Determinism core, LLMs edges | PASS | Deriver, graph validation, prompt assembly, scheduling, and state transitions are pure functions; the ladder decision stays `factory.verify.ladder.next_action`. LLM judgment is confined to the agent attempt and 002's judge — both behind activities. The interpreter never parses output semantically: verdicts come from 002, termination from the adapter's exit classification. |
| V. Spend attributed, never anonymous | PASS | Every attempt is bracketed by `issue_attempt_key`/`teardown_attempt` (FR-004); the agent authenticates with the per-attempt virtual key via the proxy; SC-003 asserts ledger-row/verification-record coverage for 100% of attempts. Master key never enters payloads. |
| VI. No work lost | PASS | This component *is* the node-lifecycle owner both 001 and 002 deferred to: `salvage_worktree` commits the worktree to `factory/<epic>/<node>` on every termination path — kill, timeout, failure, escalation-expiry — before any cleanup (FR-013, SC-004). |
| VII. Personas over model tiers | PASS | Nodes name personas; the registry resolves agent, model, models list, write scope, and (new field, this feature) `timeout`. Code names no model and hardcodes no timeout (FR-010). |

**Post-Phase-1 re-check**: PASS — no design element introduced a violation;
Complexity Tracking is empty. The two config-surface amendments (persona `timeout`,
factory.yaml `standards`) are additive fields on existing operator-editable files,
owned by their existing loaders.

## Project Structure

### Documentation (this feature)

```text
specs/005-workgraph-interpreter/
├── plan.md                    # This file
├── research.md                # Phase 0 output (R1–R12)
├── data-model.md              # Phase 1 output
├── quickstart.md              # Phase 1 output
├── contracts/
│   ├── workgraph-schema.md    # `## Work Graph` grammar + workgraph.json schema + validation (FR-002, FR-011)
│   ├── adapter.md             # D-018 activity contract: env, timeout, classification, transcripts, reaping
│   ├── workflow.md            # interpreter loop, signals/queries, state machines, replay invariants
│   ├── prompt-assembly.md     # two-loop prompt: inputs, inner-loop contract, retry evidence (FR-006)
│   └── cli.md                 # factory-epic derive | start | status (FR-009)
└── tasks.md                   # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
factory/
├── workgraph/
│   ├── __init__.py
│   ├── models.py              # WorkGraph, WorkNode, NodeState, EpicState, AttemptContext, AdapterResult
│   ├── derive.py              # pure: spec text → WorkGraph (## Work Graph YAML, validated vs criteria) (R7)
│   ├── prompt.py              # pure: two-loop attempt prompt assembly (FR-006, R9)
│   ├── worktree.py            # git worktree create/reuse/salvage/remove runners (R5)
│   ├── adapter.py             # AgentAdapter seam + ClaudeCodeAdapter: launch/monitor/terminate/classify (R2, R6)
│   ├── workflow.py            # EpicWorkflow: the one generic interpreter (pure logic) (R3, R10)
│   └── cli.py                 # factory-epic derive | start | status (R12)
├── activities/
│   └── agent_activities.py    # resolve_graph / prepare_worktree / run_agent_attempt / salvage_worktree / remove_worktree
├── worker.py                  # runnable: python -m factory.worker — registers workflow + all activities
├── config.py                  # AMENDED: persona `timeout` field (R8)
└── verify/factory_yaml.py     # AMENDED: optional `standards` key (R11)

personas.yaml                  # AMENDED: timeout per agent-backed persona
factory.yaml                   # NEW at repo root: Ergane's own gates + standards (crossover prerequisite)
pyproject.toml                 # AMENDED: factory-epic console script

tests/
├── fixtures/workgraph/        # deriver fixture specs: valid + every rejection class (SC-006)
├── stub_agent.py              # stub executable standing in for the agent CLI (US2)
├── test_derive.py             # SC-006: nodes/edges/keys exact; missing/unknown declarations rejected
├── test_workgraph_models.py   # FR-002 graph validation: cycles, dangling refs, unknown personas
├── test_prompt.py             # FR-006: pure assembly, story slice, retry evidence verbatim, standards directive
├── test_worktree.py           # FR-013: create/reuse/salvage/remove against tmp git repos
├── test_adapter.py            # US2: env exactness, TERM→KILL timeout, classification, transcript archive, reaping
├── test_agent_activities.py   # ActivityEnvironment: activity surfaces, cancellation, idempotency
├── test_interpreter.py        # time-skipping: SC-001/SC-002, ladder routing, signals, replay (US1, US3)
├── test_epic_cli.py           # derive offline; start/status against the test env
├── test_config.py             # AMENDED: timeout field validation
├── test_factory_yaml.py       # AMENDED: standards key acceptance/rejection
└── test_live_epic.py          # Tier 1 smoke behind env-gated marker (SC-005 rehearsal)
```

**Structure Decision**: single `factory` package per D-004 — `workgraph/` is the
subpackage D-004 reserved for the interpreter. The adapter lives inside
`workgraph/` rather than a top-level `agents/` because D-018 makes it one narrow
seam of the dispatch path, not a subsystem; a second adapter is a second class in
the same module namespace. `factory/worker.py` is new but tiny: the worker that
registers the workflow plus all three components' activities is the first artifact
that needs every piece at once, and it belongs to no earlier component. Crossover
prerequisites the spec's Assumptions place on this feature (Ergane's own
`factory.yaml`, the `## Work Graph` section in 003's spec, the grammar-extension
decision-log entry) are in scope as tasks — they are cheap, testable, and 005 is
not "done" for D-024's purposes without them.

## Complexity Tracking

No constitution violations; table intentionally empty.
