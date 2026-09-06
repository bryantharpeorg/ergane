# Tasks: an agent names its CLI and its route separately

Derived from `plan.md`. Tests precede implementation (constitution). Each story
phase runs its tests first, then implementation, then verification.

## Phase 1 — Setup

- [ ] T001 Re-read every `file:line` anchor in `plan.md` against the current
  tree with `sed -n` and confirm each resolves to the symbol named; record any
  that moved as a plan amendment before writing code. (Fulfils the plan's
  verification contract.)

## Phase 2: User Story 1 — A persona names its CLI and its route separately

### Tests for this story (write FIRST, must fail)

- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 1) Write the failing tests for
  the derivation: legacy `agent: subscription` → (`claude-code`,
  `subscription`), and the full table entry for entry.
- [ ] T003 [P] [US1] (spec US1-S4, FR-003) Write the failing test for the
  byte-identical load of a `route`-less manifest (`personas.example.yaml`,
  `container/personas.demo.yaml` shape): every persona derives the table's
  route and behaves as today.
- [ ] T004 [P] [US1] (spec US1-S1, US1-S3, US1-S5, FR-001, FR-002, trap 1)
  Write the failing tests for explicit `route:` parsing (US1-S1),
  explicit-wins (US1-S3), and derivation purity — same text, same pair, twice
  (US1-S5, FR-003).

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002) Add `route` to `_OPTIONAL_FIELDS`
  (`factory/config.py:152`) and add the `route` attribute to `Persona`;
  implement the pure, total derivation (FR-002, FR-003).
- [ ] T006 [US1] (FR-006, trap 3) Re-point `is_llm` / `routes_through_gateway`
  / `needs_virtual_key` (`factory/config.py:197-216`) to single-axis reads, and
  re-point `route_of` (`factory/verify/models.py:837`) to read the field rather
  than derive it.

### Verification for this story

- [ ] T007 [US1] (US1-S2/S3/S5, trap 2) Run the story's tests, confirm
  T002/T003/T004 now pass and no prior registry test regressed (scoped
  `uv run pytest -q`, then full).

## Phase 3: User Story 2 — A registry naming an agent the factory cannot run is refused at load

### Tests for this story (write FIRST, must fail)

- [ ] T008 [P] [US2] (spec US2-S1, US2-S3, US2-S4, FR-004, trap 6) Write the
  failing tests: unknown `agent: codex` raises `ConfigError` naming the value
  and the known agents (US2-S1); the error text is the known-agent list in one
  message (US2-S3); `agent: none` is NOT refused (US2-S4).
- [ ] T009 [P] [US2] (spec US2-S2, FR-004) Write the failing control: a persona
  declaring `agent: claude-code` loads with the one-adapter registry.

### Implementation for this story

- [ ] T010 [US2] (FR-004, trap 6) In `load_personas` (`factory/config.py`,
  after the non-empty-string guard at :268-270), validate the derived `agent`
  against the names in `_ADAPTERS` (`factory/workgraph/adapter.py:1512`), read
  from the registry — no second list.

### Verification for this story

- [ ] T011 [US2] (US2-S1) Verify: the raising test passes; full
  `uv run pytest -q` green.

## Phase 4: User Story 3 — The dispatch path selects the adapter the persona names

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US3] (spec US3-S1, US3-S2, US3-S3, FR-005) Write the failing
  control-and-mutation test: register a stub second adapter, dispatch a persona
  naming it, assert the stub recorded the invocation (US3-S1); the same test
  runs a `claude-code` persona as the control (US3-S2) and asserts the two
  recorded invocations differ only in the adapter named (US3-S3).

### Implementation for this story

- [ ] T013 [US3] (FR-005) Change the dispatch call site
  (`factory/activities/agent_activities.py:521`) from
  `adapter_for(DEFAULT_AGENT)` to `adapter_for` of the persona's agent, sourced
  from the attempt context (`factory/workgraph/models.py:320`).
- [ ] T014 [US3] (US3-S4, FR-005) Correct the stale comment at
  `factory/activities/agent_activities.py:175-177` in the same change.

### Verification for this story

- [ ] T015 [US3] (US3-S1/S3) Verify: the recorded invocations differ only in
  the adapter the persona named; full `uv run pytest -q` green.

## Phase 5: User Story 4 — The agent-agnostic policy in run_attempt is shared, not copied

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US4] (spec US4-S1, US4-S2, FR-007) Write the failing test: a
  second adapter class providing only the per-CLI surface runs an attempt and
  the shared policy (pid file, orphan reap, archive, deadline,
  operator-question ferry) comes from the single implementation (US4-S1); the
  outer protocol keeps one method (US4-S2).
- [ ] T017 [P] [US4] (spec US4-S3, FR-008) Write the failing conformance-sweep
  test: the adapter tests parametrize over `_ADAPTERS`
  (`factory/workgraph/adapter.py:1512`), not the literal `claude-code`.

### Implementation for this story

- [ ] T018 [US4] (FR-007) Extract the shared policy out of
  `ClaudeCodeAdapter.run_attempt` (`factory/workgraph/adapter.py:1022-1191`)
  into one implementation both adapters call; define the inner per-CLI seam
  (argv, prompt delivery, provider env, home seeding, credential discovery,
  turn-happened probe, refusal markers), keeping the five-method outer protocol
  collapsed.

### Verification for this story

- [ ] T019 [US4] (US4-S3) Verify: the second-class test and the registry-swept
  conformance suite pass; full `uv run pytest -q` green.

## Verification

- [ ] T020 Run `uv run pytest -q` over the whole repo; green is the only gate
  (`ergane.yaml`).
- [ ] T021 Confirm the governance motion is prepared for the operator: the
  D-053 decision-log entry (split, not sentinels; supersede D-018) and the
  Environment Constraints / Principle VII amendments the constitution's
  Governance section requires. The decision log is operator-promoted — hand it
  to the operator; do not append it autonomously.
