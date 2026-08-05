# Tasks: Minimal WorkGraph Interpreter

**Input**: Design documents from `/specs/005-workgraph-interpreter/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R12), data-model.md, contracts/ (workgraph-schema, adapter, workflow, prompt-assembly, cli), quickstart.md

**Tests**: Mandatory (constitution II, test-first). Every implementation task is preceded by its failing test task.

**Organization**: Phases 3–5 are the user stories. Both P1 stories tie by the spec's own note; US2 (adapter) precedes US1 (interpreter) because the interpreter's tests import the activity types and names US2 defines — priority order is preserved (P1, P1, P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies). The ralph loop executes strictly in file order; [P] documents independence, not scheduling.
- **[Story]**: US1 (interpret end to end), US2 (adapter seam), US3 (operate an epic)

## Phase 1: Setup

- [X] T001 Verify components 1 and 2 are implemented and green: `uv run pytest -q` passes and `factory/usage/`, `factory/verify/`, `factory/notify/`, `factory/activities/usage_activities.py`, `factory/activities/verify_activities.py`, `factory/activities/notify_activities.py`, `personas.yaml` exist — constitution I gate; STOP if not satisfied
- [X] T002 Create skeletons and markers: `factory/workgraph/__init__.py`, `tests/fixtures/workgraph/.gitkeep`, `.factory/` present in `.gitignore` (add if missing), and a `live_epic` pytest marker in `pyproject.toml` alongside `live_proxy`/`live_telegram` ("runs a live one-node epic; auto-skips unless Tier 1 env is set")

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The two config-surface amendments every story reads, and the shared types. No user story work before this phase completes.

- [X] T003 [P] Amend `tests/test_config.py` FIRST: persona `timeout` field — a positive integer of seconds loads onto `Persona.timeout_s`; absent → `None`; zero/negative/non-int rejected naming the persona; forbidden on `agent: none` personas (error naming the persona, mirroring the model rule); unknown-field rejection still catches typos like `timeout_s` in YAML — must fail (field not implemented)
- [X] T004 Amend `factory/config.py` (`Persona.timeout_s`, `_OPTIONAL_FIELDS` + validation per research R8) and `personas.yaml` (set `timeout` on every agent-backed persona: architect/implementer/judge/debugger/researcher; operator-editable values, e.g. 3600–14400s) until T003 passes
- [X] T005 [P] Amend `tests/test_factory_yaml.py` FIRST: optional top-level `standards` key — non-empty string accepted onto `FactoryConfig.standards`; absent → `None`; empty/non-string rejected with rule slug `standards`; schema stays `version: 1`; existing rejection table unaffected — must fail
- [X] T006 Amend `factory/verify/models.py` (`FactoryConfig.standards: str | None = None`) and `factory/verify/factory_yaml.py` (accept + validate `standards` per research R11) until T005 passes
- [X] T007 Write `tests/test_workgraph_models.py` FIRST per contracts/workgraph-schema.md start-time validation: duplicate node ids, dangling `depends_on`, cycle (error names the cycle's members), blank `epic_id`/`feature`/`target_repo`, unresolvable persona and missing-timeout persona (against an injected registry mapping), valid graph passes and preserves declaration order; `NodeState`/`EpicState` are `StrEnum`s; `WorkGraph`/`WorkNode`/`AttemptContext`/`AdapterResult` round-trip through `dataclasses.asdict` + reconstruction (Temporal JSON converter shape) — must fail (no models.py yet)
- [X] T008 Implement `factory/workgraph/models.py` (all entities per data-model.md field tables + pure `validate_workgraph(graph, personas)` raising errors that name the offending node) until T007 passes

**Checkpoint**: Types and config surfaces ready — story phases can begin

---

## Phase 3: User Story 2 — Agent attempts through the adapter seam (Priority: P1)

**Goal**: The one place the factory touches an agent: launch/monitor/terminate/classify through the D-018 adapter in an isolated worktree, transcript archived on every path.

**Independent Test**: Run the adapter activity against a stub executable standing in for the agent CLI; assert env construction (proxy URL + virtual key + model alias), worktree isolation, termination classification, and transcript archiving (spec US2).

### Tests for User Story 2 (write FIRST, must fail)

- [X] T009 [P] [US2] Create `tests/stub_agent.py` — an executable standing in for the agent CLI per contracts/adapter.md test surface: records argv, env, cwd, and stdin to files in its cwd; behavior driven by a control file (exit code, sleep duration, whether to write a fake session transcript under the claimed `$HOME/.claude/projects/<munged-cwd>/<session-id>.jsonl`)
- [X] T010 [P] [US2] Write `tests/test_worktree.py` FIRST against `tmp_path` git repos: **ensure** creates `.factory/worktrees/<epic>/<node>` on branch `factory/<epic>/<node>` from the captured base ref and a second call reuses it unchanged (FR-013); **salvage** commits a dirty tree with message `salvage(<epic>/<node>): <termination> attempt <n>`, uses `--allow-empty` on a clean tree so every terminal attempt is ref-observable (SC-004), and is idempotent per attempt; **remove** deletes the worktree, the branch survives, already-removed is success — must fail (no worktree.py yet)
- [X] T011 [US2] Implement `factory/workgraph/worktree.py` (ensure/salvage/remove/base-ref capture per research R5) until T010 passes
- [X] T012 [US2] Write `tests/test_adapter.py` FIRST against the stub (contracts/adapter.md): child env is EXACTLY the allowlist (`ANTHROPIC_BASE_URL`=proxy url, `ANTHROPIC_AUTH_TOKEN`=virtual key, `PATH`/`HOME`/`LANG`/`TERM` passthrough) — plant `LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN` in the worker env and assert absent (US2-S1); prompt arrives on stdin; cwd = worktree; `--model <alias>` and `--session-id <uuid>` in argv; deadline → TERM then KILL to the process group, classified TIMEOUT (US2-S3); exit 0 → COMPLETED, non-zero → AGENT_ERROR; archive to `.factory/transcripts/<epic>/<node>/attempt-<n>/` contains `stdout.log` + the session transcript on every path (US2-S4, FR-007); a planted live process group named in `.factory/run/<epic>/<node>.pid` is reaped before relaunch (research R4) — must fail
- [X] T013 [US2] Implement `factory/workgraph/adapter.py` (`AgentAdapter` seam + `ClaudeCodeAdapter` per research R2/R6) until T012 passes
- [X] T014 [US2] Write `tests/test_agent_activities.py` FIRST (`ActivityEnvironment`): `resolve_graph` snapshots the registry per node (model alias, `models` list, write scope, timeout; per-story override wins) and raises non-retryable `GRAPH_INVALID` naming the node for unknown persona or unresolvable timeout; `prepare_worktree` is idempotent and raises non-retryable `STANDARDS_MISSING` when `factory.yaml` declares `standards` and the file is absent from the worktree (research R11); `run_agent_attempt` heartbeats, honors cancellation (terminates the stub, archives, classifies KILLED, re-raises); `salvage_worktree`/`remove_worktree` idempotency across re-runs — must fail
- [X] T015 [US2] Implement `factory/activities/agent_activities.py` (`resolve_graph` / `prepare_worktree` / `run_agent_attempt` / `salvage_worktree` / `remove_worktree` per contracts/adapter.md, plus the read-only `load_prompt_sources` per contracts/prompt-assembly.md) until T014 passes

**Checkpoint**: The factory can run and classify a real (stub) agent attempt with full evidence

---

## Phase 4: User Story 1 — Interpret a WorkGraph end to end (Priority: P1) 🎯 MVP

**Goal**: The component: one generic workflow driving every node through dispatch → attempt → 002 ladder to terminal state, edges unlocking only on PASS.

**Independent Test**: Run the interpreter in Temporal's time-skipping test environment against a small scripted graph (fake agent activity, scripted verification results); assert node state transitions, edge unlocking, and terminal epic state (spec US1).

### Tests for User Story 1 (write FIRST, must fail)

- [X] T016 [P] [US1] Write `tests/test_prompt.py` FIRST per contracts/prompt-assembly.md: golden assembly against fixture spec/plan/tasks texts with sections in contract order (role/scope; inner-loop ralph contract stated advisory; outer-loop stated authoritative with FR-012 language; standards directive present iff declared; story sections, full plan, tasks slice all verbatim); tasks-slice extraction by fence-masked header scan (story with a slice; story without → error naming the story, FR-006); retry prompts carry planted gate `output_tail`s and judge feedback byte-for-byte, newest last; same inputs → identical prompt — must fail (no prompt.py yet)
- [X] T017 [US1] Implement `factory/workgraph/prompt.py` (pure `build_attempt_prompt` per research R9) until T016 passes
- [X] T018 [US1] Write `tests/test_interpreter.py` FIRST (`WorkflowEnvironment.start_time_skipping()`, scripted fakes registered under the real activity names for the agent/usage/verify/notify surfaces): US1-S1 — 3-node graph (A→B chain + independent leaf) runs to epic completion with node transitions, edge-unlock order, and attempt counts exactly as scripted (SC-001), B dispatching only after A's PASS (FR-003); US1-S2 — scripted FAIL→RETRY re-dispatches with failure evidence in the prompt and attempt incremented; US1-S3 — ladder exhaustion → ESCALATE, scripted KILL resolution → node KILLED, salvage before remove, dependents never dispatch (SC-002 including failure/kill paths); an invalid graph is rejected before any dispatch (FR-002); every attempt is bracketed by `issue_attempt_key`/`teardown_attempt` and recorded via `record_verification` before any ladder action (FR-004, SC-003); the poll loop retains the last `UsageSnapshot` into `TeardownInput` (research R3); US1-S4 — replay from captured history double-dispatches nothing and double-issues no key — must fail (no workflow.py yet)
- [X] T019 [US1] Implement `factory/workgraph/workflow.py` (`EpicWorkflow` per contracts/workflow.md: sequential ready-node loop in declaration order, node lifecycle composing 002's verification-flow contract, escalation signal routing via `factory.notify.service.SIGNAL_NAME`, `epic_status` query, `workflow.uuid4()` session ids) until T018 passes

**Checkpoint**: MVP — a WorkGraph runs end to end under time skipping with every invariant asserted

---

## Phase 5: User Story 3 — Operate a running epic (Priority: P2)

**Goal**: The human-holdable steering wheel: derive, start, status; pause/resume/kill.

**Independent Test**: Start a scripted epic via the CLI against the dev-server test environment; signal pause and kill; assert the workflow honors both and the CLI's status output matches workflow state (spec US3).

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T020 [P] [US3] Build `tests/fixtures/workgraph/` fixture specs per contracts/workgraph-schema.md: `valid_epic/spec.md` (≥3 stories, `## Work Graph` fenced YAML with edges and one `timeout` override), plus one fixture per rejection rule — `missing_story` (declared story with no declaration), `unknown_story` (declaration for a story the spec lacks), `unknown_fr`, `unknown_dep`, `cycle`, `self_dep`, `no_section`, `two_blocks`, `non_mapping`, `unknown_key`, `bad_timeout`
- [ ] T021 [US3] Write `tests/test_derive.py` FIRST: the valid fixture derives exact nodes/edges/`requirement_keys`/`spec_ref`s (SC-006 — one node per story, spec order, ids lowercased, persona `implementer`, `requirement_keys = [story_key, *implements]`); each rejection fixture fails naming the offending story and rule with nothing emitted; derivation is pure (text in → WorkGraph out, no filesystem) — must fail (no derive.py yet)
- [ ] T022 [US3] Implement `factory/workgraph/derive.py` (fence-masked `## Work Graph` scan, YAML shape rules, cross-validation against `factory.verify.criteria.load_criteria`, per research R7) until T021 passes
- [ ] T023 [US3] Write `tests/test_epic_cli.py` FIRST per contracts/cli.md: `derive` writes `workgraph.json` next to the spec (or `-o`), prints every collected error and writes nothing on failure (exit 1); `start` against the time-skipping env prints workflow id `epic-<epic_id>` (US3-S1), duplicate start → operator message + exit 1; `status` human shape (epic line + per-node lines in declaration order) and `--json` (query result verbatim); exit codes 0/1/2; `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE` honored — must fail (no cli.py yet)
- [ ] T024 [US3] Implement `factory/workgraph/cli.py` and register the `factory-epic` console script in `pyproject.toml` until T023 passes
- [ ] T025 [US3] Write pause/resume/kill tests FIRST in `tests/test_interpreter.py`: US3-S2 — `pause_epic` blocks new node dispatch while the in-flight node completes its full ladder, `resume_epic` continues, a `PAUSE_EPIC` escalation resolution parks the node FAILED and pauses the epic (contracts/workflow.md), pause survives replay (research R1); US3-S3 — `kill_epic` cancels the in-flight attempt (adapter KILLED path), salvages worktrees, tears down keys, marks every non-terminal node KILLED, epic terminal KILLED with every node recorded — must fail
- [ ] T026 [US3] Implement the `pause_epic`/`resume_epic`/`kill_epic` signal handlers and the kill sequence in `factory/workgraph/workflow.py` until T025 passes
- [ ] T027 [US3] Write worker-registration test FIRST (in `tests/test_epic_cli.py` or a new `tests/test_worker.py`): importing `factory.worker` yields a registration set containing `EpicWorkflow` and every activity the workflow invokes by name (agent, usage, verify, notify surfaces) — name alignment asserted mechanically — must fail (no worker.py yet)
- [ ] T028 [US3] Implement `factory/worker.py` (runnable `python -m factory.worker`: Temporal client from `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`, worker on task queue `workgraph` registering the workflow + all three components' activities) until T027 passes

**Checkpoint**: All user stories independently functional; an operator can derive, start, watch, pause, and kill an epic

---

## Phase 6: Polish & Crossover Prerequisites

**Purpose**: Live smoke, documentation truth, and the D-024 crossover prerequisites the spec's Assumptions place on this feature.

- [ ] T029 [P] Commit Ergane's own `factory.yaml` at the repo root (`version: 1`, `runtime`, `gates: {test: "uv run pytest -q"}`, `standards: .specify/memory/constitution.md`) and add a `tests/test_factory_yaml.py` case loading the real file successfully (crossover prerequisite)
- [ ] T030 [P] Add the `## Work Graph` section to `specs/003-merge-queue/spec.md` declaring its stories' `depends_on`/`implements`, and add a `tests/test_derive.py` case deriving `specs/003-merge-queue/spec.md` successfully — the real-world fixture and the crossover's input (crossover prerequisite)
- [ ] T031 [P] Record decision-log entry D-025 in `docs/decisions.md` (the `## Work Graph` additive grammar extension — spec-compiled WorkGraph, no template fork — plus the persona `timeout` and factory.yaml `standards` config additions) and update `docs/architecture.md` §3 (interpreter implemented: layout, sequential scheduling, signals/query, transcript archiving) and §4 (timeout field)
- [ ] T032 [P] Add `tests/test_live_epic.py` with `@pytest.mark.live_epic`: one-node epic against a scratch target repo through the real dev server, proxy, and `claude` CLI per quickstart §4 (SC-005 rehearsal); asserts PASSED node, salvage commit on `factory/<epic>/us1`, ledger row, verification row, archived transcript; auto-skips unless Tier 1 env is set
- [ ] T033 Run full quickstart.md validation (§1 suite green, §2 derive demos behave as documented, §3 interpreter suite, §5 queries run as-is) and fix any drift
- [ ] T034 Final sweep: extend 002's credential sweep to `factory/workgraph/` (no `LITELLM_MASTER_KEY`/`TELEGRAM_BOT_TOKEN` value in any payload, artifact, or error path — the virtual key only ever inside `AttemptContext`); assert FR-012 component-wide (no code path reads agent stdout/exit into node state except the `Termination` classification); assert SC-002 (no dispatch path with unmet dependencies) and FR-007 (no transcript path under any repo worktree) via targeted tests

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none — start immediately; T001 is a hard gate (constitution I)
- **Phase 2 (Foundational)**: after Phase 1 — blocks all stories (types + config surfaces)
- **Phase 3 (US2)**: after Phase 2
- **Phase 4 (US1)**: after Phase 3 (imports the activity types/names US2 defines; fakes register under real names)
- **Phase 5 (US3)**: after Phase 4 (CLI starts the workflow; signals extend it)
- **Phase 6 (Polish)**: after Phase 5

### Within stories

- Every test task precedes its implementation task and must FAIL first for the right reason
- worktree → adapter → activities (US2); prompt → workflow (US1); fixtures → derive → CLI → signals → worker (US3)

### Parallel Opportunities

- T003/T005/T007 touch different test files; T009/T010 are independent; T016 is independent of Phase 3's tail; T020 is fixture-only; all of T029–T032 are mutually independent. The ralph loop ignores parallelism and runs strictly in order — [P] documents safety, not scheduling.

---

## Implementation Strategy

**MVP = Phases 1–4**: after T019 the component exists — a WorkGraph runs end to end under time skipping with every constitution invariant asserted. Phase 5 adds the operator surface (derive/CLI/signals/worker) required for any *live* run; Phase 6 adds the live smoke and the three crossover prerequisites. For the ralph run there is no reason to stop at the MVP checkpoint: the crossover (SC-005) needs everything through T034.

**Execution**: `./ralph/ralph.sh 005-workgraph-interpreter` — one task per fresh headless session, tasks.md checkboxes + git as the only durable state, `uv run pytest -q` as the gate after every task, one commit per task (`T0NN: <description>`).
