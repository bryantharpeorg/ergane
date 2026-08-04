# Tasks: Verification Gating

**Input**: Design documents from `/specs/002-verification-gating/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md — plus **component 1 (`001-usage-tracking`) implemented with green tests** (constitution I; this component consumes its `issue_attempt_key`/`teardown_attempt` activities and `.factory/` conventions).

**Tests**: INCLUDED — constitution II (test-first) is non-negotiable; each story's
tests are written first and must fail before implementation.

**Organization**: Grouped by user story; each story is independently implementable
and testable (US2 uses prepared CriteriaSets, US3 uses scripted verdicts, so
neither needs the other's implementation to test).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1 (criteria parsing), US2 (two-tier verification), US3 (retry ladder + escalation)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: gate on component 1, add the approved notifier dependency, extend the package skeleton

- [X] T001 Verify component 1 is implemented and green: `uv run pytest -q` passes and `factory/usage/`, `factory/activities/usage_activities.py`, `personas.yaml` exist per `specs/001-usage-tracking/plan.md` — constitution I gate; STOP if not satisfied
- [X] T002 Add `python-telegram-bot` to `pyproject.toml` (approved D-022), add `live_telegram` pytest marker alongside `live_proxy`, run `uv sync`
- [X] T003 [P] Create skeletons: `factory/verify/__init__.py`, `factory/notify/__init__.py`, `tests/fixtures/speckit/.gitkeep`, `tests/fixtures/target_repo/.gitkeep`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared types and the evidence store — every story records through them

**⚠️ CRITICAL**: No user story work until this phase completes

- [X] T004 [P] Implement `factory/verify/models.py`: enums (`RequirementKind`, `GateStatus`, `JudgeOutcome`, `OverallVerdict`, `VerificationForm`, `NextAction`, `EscalationChoice`) and frozen dataclasses (`Scenario`, `Requirement`, `CriteriaSet`, `FactoryConfig`, `GateResult`, `OutputCheck`, `JudgeScenarioFinding`, `JudgeVerdict`, `VerificationResult`, `VerificationConfig`, `AttemptRecord`, `EscalationRecord`) exactly per data-model.md field tables
- [X] T005 [P] Write `tests/test_verify_store.py` FIRST: creating a store applies `contracts/verification-store.sql` DDL (WAL on, `schema_version` = 1, both tables + indexes + CHECK constraints); upsert by `(epic_id, node_id, attempt, form)` records once on re-run; escalation state machine allows exactly one terminal transition (`resolved` xor `expired`, later attempts no-op); pending-escalations query returns only unresolved rows — must fail (no store.py yet)
- [X] T006 Implement `factory/verify/store.py` (connection factory with WAL + busy_timeout per 001's R6 pattern, schema bootstrap from embedded DDL matching `contracts/verification-store.sql`, `upsert_result`, `insert_escalation`, `resolve_escalation`, `expire_escalation`, `pending_escalations`, per-node history query) until T005 passes

**Checkpoint**: foundation ready — user stories can proceed (in parallel if desired)

---

## Phase 3: User Story 1 — Mechanical criteria parsing (Priority: P1) 🎯 MVP

**Goal**: extract acceptance criteria from Spec Kit feature specs (D-023) with zero LLM
involvement — deterministic, testable, validation errors naming the offender.

**Independent Test** (spec US1): feed fixture spec files exercising the full
grammar; assert extracted requirement/scenario structures and validation errors.

### Tests for User Story 1 (write FIRST, must fail)

- [X] T007 [P] [US1] Build fixture corpus under `tests/fixtures/speckit/`: every grammar production per architecture §2 — multi-story files with `### User Story <n> - <title> (Priority: P<m>)` headers, numbered acceptance scenarios with bold **Given/When/Then/And** steps (incl. multi-And items), `### Functional Requirements` sections with `- **FR-###**:` bullets, headers and FR-like bullets inside fenced code blocks, a story with zero acceptance scenarios, an FR missing SHALL/MUST, a scenario item with no bold keyword steps, duplicate requirement keys, plus a verbatim copy of `specs/001-usage-tracking/spec.md` as the real-world fixture (SC-001 coverage)
- [X] T008 [US1] Write `tests/test_criteria.py` FIRST against the corpus: story requirements keyed `US<n>` with title/priority and FUNCTIONAL requirements keyed `FR-###` per data-model.md, scenario ids `US<n>-S<k>` with steps captured verbatim in order, fence masking, requirement filtering by requested keys; validation errors name the exact requirement (SHALL/MUST missing, story with zero scenarios, keyword-less scenario item, duplicate keys, unknown requested key); the real-world fixture (001's spec.md) parses with 3 stories and 12 FRs; `CriteriaSet` carries `feature`, `source_sha256` of raw bytes and `snapshotted_at` — must fail (no criteria.py yet)

### Implementation for User Story 1

- [X] T009 [US1] Implement `factory/verify/criteria.py` (pure parser: fence-masked header scan `/^(#{1,6})\s+(.+)$/`, Spec Kit template grammar per architecture §2, validation rules per data-model.md, requirement filtering by key) until T008 passes
- [X] T010 [US1] Write `snapshot_criteria` activity tests FIRST in `tests/test_verify_activities.py` (ActivityEnvironment): returns `CriteriaSet` for the node's requirement keys with hash + timestamp; `CRITERIA_PARSE_FAILED` application error carries the validation message; `CRITERIA_FILE_MISSING` on absent spec.md — must fail
- [X] T011 [US1] Create `factory/activities/verify_activities.py` with `snapshot_criteria` per `contracts/activities.md` until T010 passes

**Checkpoint**: criteria parsing shippable and grammar-complete on its own

---

## Phase 4: User Story 2 — Two-tier verification of a node's diff (Priority: P1)

**Goal**: gates from committed `factory.yaml` (exit-code semantics, timeout,
CONFIG_ERROR never-pass-by-default) → anti-rubber-stamp output check → bounded
strict-per-scenario judge → composed verdict recorded to the evidence store.

**Independent Test** (spec US2): run verification against a prepared worktree with
known-passing/failing gates and a scripted judge (fake proxy); assert verdict
composition and evidence recording — uses hand-built `CriteriaSet`s, independent of
US1's parser.

### Tests for User Story 2 (write FIRST, must fail)

- [X] T012 [P] [US2] Write `tests/test_factory_yaml.py` FIRST: acceptance of the schema-v1 example; rejection table per `contracts/factory-yaml.md` (missing file, non-mapping YAML, wrong version, unknown gate name, empty command, unknown top-level key, bad timeout) each yielding `CONFIG_ERROR` with an actionable message naming the violated rule
- [X] T013 [P] [US2] Build `tests/fixtures/target_repo/` variants: valid `factory.yaml` with passing gate commands, a failing gate (non-zero exit), a hanging gate (sleep > timeout), a missing manifest, plus a minimal git repo skeleton for worktree tests
- [X] T014 [P] [US2] Write `tests/test_gates.py` FIRST: exit 0 → PASS, non-zero → FAIL with `exit_code`, deadline → TIMEOUT (SIGTERM then SIGKILL), `output_tail` capped at 32 KiB, gates run in declaration order with declared/default (600s) timeouts, subprocess env is scrubbed (`LITELLM_MASTER_KEY`/`TELEGRAM_BOT_TOKEN` set in test env never visible to the gate command), missing/malformed manifest → single `CONFIG_ERROR` gate result
- [X] T015 [P] [US2] Write `tests/test_diffcheck.py` FIRST: write-scope with clean worktree → `passed=False` (FR-004); modified tracked file → True; untracked-only file → True; read-scope ignores diff but requires every `expected_artifacts` path to exist non-empty; empty artifact file → False; vanished worktree → `WORKTREE_MISSING` error, not a verdict
- [X] T016 [P] [US2] Write `tests/test_judge.py` FIRST (fake proxy via `httpx.MockTransport` `/chat/completions`): prompt contains requirement body + every scenario verbatim + `prior_feedback` verbatim when given; >60 KiB diff proportionally truncated with `[... N lines truncated ...]` markers and `truncated_input=True`, criteria never truncated; strict parse accepts raw or single-fenced JSON; missing/extra scenario → malformed; `verdict: pass` with a `pass: false` finding → outcome forced to RETRY (stricter wins); malformed response consumes a judge attempt and after the cap yields FAIL with parse failure as feedback; request carries Bearer virtual key, `temperature 0`, `max_tokens` 2000, persona alias model — and never the master key

### Implementation for User Story 2

- [X] T017 [P] [US2] Implement `factory/verify/factory_yaml.py` until T012 passes
- [X] T018 [P] [US2] Implement `factory/verify/gates.py` (bash -c runner behind the `GateExecutor` seam per research R3) until T014 passes
- [X] T019 [P] [US2] Implement `factory/verify/diffcheck.py` (`git status --porcelain` + `git diff HEAD`, artifact checks) until T015 passes
- [X] T020 [US2] Implement `factory/verify/judge.py` (pure prompt assembly + truncation, strict verdict parsing with cross-check, httpx call per `contracts/judge.md`) until T016 passes
- [ ] T021 [US2] Write verification-activity tests FIRST in `tests/test_verify_activities.py`: `run_gates`/`check_output`/`run_judge` activity wrappers (incl. `JUDGE_UNAVAILABLE` after HTTP retries); `record_verification` upserts, rejects empty epic/node/attempt with `ATTRIBUTION_INCOMPLETE`, recomputes drift (changed spec file → `criteria_drift=1`); verdict truth table (SC-002): any gate FAIL/TIMEOUT/CONFIG_ERROR → FAIL, output-check fail → FAIL, judge RETRY/FAIL → FAIL, judge UNAVAILABLE with green gates → PASS + `judge_unavailable=1`; judge skipped entirely when a gate fails (cheapest-first, request log proves no proxy call) — must fail
- [ ] T022 [US2] Implement remaining activities in `factory/activities/verify_activities.py` (`run_gates`, `check_output`, `run_judge`, `record_verification`) and `compose_result` in `factory/verify/models.py` until T021 passes

**Checkpoint**: a prepared worktree gets a correct, recorded verdict end-to-end

---

## Phase 5: User Story 3 — Retry with feedback, then escalate (Priority: P2)

**Goal**: pure retry ladder (3 attempts default, judge-retry cap inside, debugger
once, then Telegram escalation with 1h default-kill) + the notifier pair
(send-only activity, callback bridge → Temporal signal) + the reference flow
proving it all under time-skipping.

**Independent Test** (spec US3): script a verifier that fails N times; assert the
ladder decisions, verbatim feedback injection, and escalation firing/resolution —
scripted verdicts, independent of US2's implementation.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T023 [P] [US3] Write `tests/test_ladder.py` FIRST (pure, no Temporal): PASS → PASSED; failures below `max_attempts` (3) → RETRY regardless of gate/judge mix; judge-RETRY outcomes bounded by `max_judge_retries` (2) within the total; attempts exhausted → DEBUGGER exactly once; debugger failure → ESCALATE; escalation RETRY grants exactly one more attempt; KILL/timeout → KILLED; custom `VerificationConfig` caps honored
- [ ] T024 [P] [US3] Write `tests/test_notify.py` FIRST: `messages.py` renders full failure history (SC-005) and buttons whose `callback_data` = `esc:<12-hex>:<choice>` ≤ 64 bytes for every choice; bridge handler (fake `telegram` update + fake Temporal client + tmp store): valid press → signal `escalation_resolved(escalation_id, choice)` on the stored `workflow_id`, row resolved, callback answered, message edited; invalid choice / unknown id / expired / already-resolved → answered notice, NO signal, row unchanged
- [ ] T025 [P] [US3] Write `tests/test_notify_activities.py` FIRST (ActivityEnvironment, fake Bot): `send_escalation` inserts the escalation row BEFORE sending (crash between insert and send leaves an expirable row — assert via fake-Bot failure injection); missing `TELEGRAM_BOT_TOKEN`/send failure → `delivered=false`, row retained; success → `delivered=true`, `expires_at = sent_at + 1h`; bot token never in inputs/results/errors; `expire_escalation` marks EXPIRED only from pending

### Implementation for User Story 3

- [ ] T026 [P] [US3] Implement `factory/verify/ladder.py` (pure `next_action(history, config)`) until T023 passes
- [ ] T027 [US3] Implement `factory/notify/messages.py` (pure rendering) and `factory/notify/service.py` (runnable long-polling bridge: parse → store lookup → validate → signal → resolve → answer → edit; stateless across restarts) until T024 passes
- [ ] T028 [US3] Implement `factory/activities/notify_activities.py` (`send_escalation`, `expire_escalation` per `contracts/activities.md`, env-only credentials) until T025 passes
- [ ] T029 [US3] Write `tests/test_verification_flow.py` FIRST (`WorkflowEnvironment.start_time_skipping`, reference workflow per `contracts/verification-flow.md` with scripted gate/judge activities): fail → retry prompt contains gate `output_tail` and judge feedback VERBATIM (SC-004); ladder walks retry → debugger → escalate; escalation signal RETRY/KILL/PAUSE_EPIC each honored; 1h silence → `expire_escalation` called then default KILL; `delivered=false` → immediate KILL with no wait; downstream unlock happens on PASS and only on PASS (FR-005); every attempt recorded via `record_verification` before any action (invariant 3) — must fail
- [ ] T030 [US3] Implement the test-support reference workflow (in `tests/reference_flow.py`, imported by the test — explicitly NOT production code; the interpreter component owns the production loop) until T029 passes

**Checkpoint**: all three stories independently functional

---

## Phase 6: Polish & Cross-Cutting

- [ ] T031 [P] Add `tests/test_live_judge.py` with `@pytest.mark.live_proxy`: real-proxy judge smoke per quickstart §3 — mint judge key via component 1, score a fixture diff on the judge persona alias, teardown, assert parsed verdict AND a usage-ledger row with persona=`judge` (constitution V); auto-skip when proxy env unset
- [ ] T032 [P] Add `tests/test_live_notify.py` with `@pytest.mark.live_telegram`: real escalation message per quickstart §4 with inline buttons and pending store row; auto-skip when Telegram env unset
- [ ] T033 [P] Update `docs/architecture.md` §6 and §9 to implemented state: evidence store (`.factory/verification.db`) added to the diagram/description, notifier described as send-activity + bridge pair, module names match shipped layout
- [ ] T034 Run full quickstart.md validation (§1 suite green, §2 gate-runner demo behaviors, §5 store schema/rollup queries run as-is) and fix any drift
- [ ] T035 Final sweep: grep-based tests assert no `TELEGRAM_BOT_TOKEN` or `LITELLM_MASTER_KEY` value in any persisted artifact or error path; confirm no judge invocation is reachable outside `run_judge` (FR-009 — nothing exports it toward CI/merge tooling); confirm verdict composition has no path to PASS with a failing gate or empty write-scope diff (SC-002)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2 → (Phases 3, 4, 5) → Phase 6**
- T001 gates everything (constitution I: component 1 green first)
- Phase 2 blocks all stories (models + evidence store)
- US1 (Phase 3), US2 (Phase 4), US3 (Phase 5) are mutually independent after
  Phase 2: US2 tests use hand-built `CriteriaSet`s; US3 tests use scripted
  verdicts. Only `tests/test_verify_activities.py` is shared (T010 creates it,
  T021 extends it) — sequence T021 after T010 or merge in one sitting.
- Full integration (parser → verify → ladder → escalation in one flow) lands in
  T029/T030 and is exercised again in T034

### Within stories

- Test tasks strictly before their implementation tasks (constitution II)
- US1: T007 ∥ T008 → T009 → T010 → T011
- US2: T012–T016 in parallel → T017/T018/T019 in parallel, T020 after T016 →
  T021 → T022
- US3: T023–T025 in parallel → T026 ∥ T027/T028 → T029 → T030

### Parallel Opportunities

- Phase 1: T003 after T001; T002 ∥ T003
- Phase 2: T004 ∥ T005
- After Phase 2: Tracks A (US1), B (US2), C (US3) can run in parallel
- Within US2: five test files (T012–T016) authored in parallel; three
  implementations (T017–T019) in parallel

## Parallel Example: after Phase 2 checkpoint

```bash
# Three independent story tracks:
Track A (US1): T007, T008 → T009 → T010 → T011
Track B (US2): T012, T013, T014, T015, T016 → T017, T018, T019, T020 → T021 → T022
Track C (US3): T023, T024, T025 → T026, T027, T028 → T029 → T030
```

## Implementation Strategy

**MVP first**: Phases 1–3 (criteria parsing is the ground truth everything else
consumes) → then US2 (the gate that makes the factory trustworthy — this is the
component's reason to exist) → then US3 (turns the gate into a self-healing loop)
→ Polish. Commit after each task or logical group; every checkpoint is a valid
stopping point. If sequencing solo, US2 before US3 matches the spec's priority
ordering (both P1s first, then P2).
