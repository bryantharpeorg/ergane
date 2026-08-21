# Tasks: a stronger rung runs a stronger model

**Spec**: `specs/075-a-stronger-rung-runs-a-stronger-model/spec.md`
**Plan**: `specs/075-a-stronger-rung-runs-a-stronger-model/plan.md`

Read the plan's traps before the first task. Trap 1 (the registry read is already
in workflow code — resolve more at epic start, never again per attempt), trap 3
(the controls are the story) and trap 4 (`agent` and `model_alias` from one
lookup) are the three that decide whether an attempt lands.

## Phase 1: User Story 1 — The rung that changes the persona changes the model

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_rung_resolves_its_own_model.py`,
      build a debugger attempt for a node routed to persona A where the debugger
      persona B declares a different model, and assert the attempt context
      carries B's model alias.
- [ ] T002 [P] [US1] (spec US1-S2) **The control.** Assert an ordinary attempt on
      the same node carries A's model alias. Prove it can fail by making the
      selection unconditional and watching this go red (trap 3).
- [ ] T003 [P] [US1] (spec US1-S3) Assert a recovery after a `CONFLICT` rejection
      carries the conflict rung's persona **and** that persona's model alias.
- [ ] T004 [P] [US1] (spec US1-S4) **The second control.** Assert a recovery after
      a clean re-sync carries the node's own persona and model. The two paths
      fork at `factory/workgraph/workflow.py:2650` and `:2653` and must keep
      forking.
- [ ] T005 [P] [US1] (spec US1-S5) Assert a rung naming a persona absent from the
      snapshot fails the node, naming the persona and the rung — not a silent
      fallback to the node's model (trap 5 is about hardcoding; this is about
      failing loudly).
- [ ] T006 [P] [US1] (spec US1-S6) Assert `agent` and `model_alias` on one attempt
      come from the same resolved entry, over a fixture where a persona's agent
      and model would disagree if resolved separately (FR-002).

### Implementation for this story

- [ ] T007 [US1] (FR-003) Widen the snapshot at
      `factory/workgraph/workflow.py:947` so it holds every persona a rung may
      select — the node personas, `DEBUGGER_PERSONA`, and the configured
      promotion persona — resolved **once**, at epic start. Never
      `PROMOTION_PERSONA`, which is the `"__promotion__"` sentinel (trap 6).
- [ ] T008 [US1] (FR-004) Keep the resolution at epic start. Do **not** call
      `_resolve_persona` (`factory/workgraph/workflow.py:927-942`) from a per-attempt path: it
      reads the registry from workflow code and doing it per attempt turns a
      latent determinism defect into a live one (trap 1). File that existing read
      as its own finding; do not fix it here.
- [ ] T009 [US1] (FR-001, FR-002) Take `model_alias` **and** `agent` from the one
      resolved entry for the attempt's persona, at both attempt sites —
      `factory/workgraph/workflow.py:1380` (ordinary) and `:2785` (recovery).
      The `agent` half already flows at `:2753-2622`; extend it rather than
      adding a second resolution (trap 4).
- [ ] T010 [US1] (FR-006) Leave the clean-versus-conflicted fork at
      `factory/workgraph/workflow.py:2650`/`:2653` intact, and correct the stale
      comment at `:2751-2620` — it claims recovery "re-uses the same persona as
      the original node", which is false for a conflicted sync.
- [ ] T011 [US1] (FR-005) Fail the node by name when a rung's persona is absent
      from the snapshot.

## Phase 2: User Story 2 — The promotion rung can be switched on

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1) In
      `tests/test_promotion_persona_is_operator_settable.py`, assert
      `ergane build start` with a promotion persona puts it into the workflow's
      `VerificationConfig`, read from the start payload.
- [ ] T013 [P] [US2] (spec US2-S2) Assert `ergane roadmap start` passes it to
      every child epic.
- [ ] T014 [P] [US2] (spec US2-S3) **The control.** Assert that with no flag,
      `promotion_persona` is `None` and the rung stays off — today's behaviour is
      the default.
- [ ] T015 [P] [US2] (spec US2-S4) Assert a promotion persona absent from the
      registry is refused **before** the epic starts, naming the persona.

### Implementation for this story

- [ ] T016 [US2] (FR-007) Add the flag to `ergane build start` and pass it into
      the `VerificationConfig` built at `factory/cli/nouns/build.py:511`, which is
      bare today.
- [ ] T017 [US2] (FR-008) Same for `ergane roadmap start` at
      `factory/cli/roadmap.py:236`, so every child epic receives it.
- [ ] T018 [US2] (FR-009) Refuse an unknown persona before dispatch. Note
      `interpreter/cli-cannot-reject-an-unknown-persona`: the CLI does not
      currently reject an unknown *node* persona either, and this task is not
      that — scope it to the promotion flag.
- [ ] T019 [US2] (FR-010) Default to `None`.

## Phase 3: User Story 3 — An attempt says which persona and model it ran

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S1) In
      `tests/test_attempt_reports_persona_and_model.py`, assert each attempt in a
      node's history carries the persona and model alias it ran under, over a
      history spanning two personas.
- [ ] T021 [P] [US3] (spec US3-S2) Assert the human-readable
      `ergane build status` prints the current attempt's persona and model.
- [ ] T022 [P] [US3] (spec US3-S3) Assert an unresolvable persona is reported as
      such rather than as the node's model.

### Implementation for this story

- [ ] T023 [US3] (FR-011) Carry the persona and model alias on `AttemptRecord`.
- [ ] T024 [US3] (FR-012) Render both in `ergane build status`, JSON and human.

## Verification

- [ ] T025 (SC-001) Drive a debugger rung against a persona with a different
      model and paste the attempt's resolved model alias.
- [ ] T026 (SC-002) Drive an ordinary attempt on the same node and paste its
      model alias. Paste both together — the pair is the evidence, not either
      one.
- [ ] T027 (SC-003) Drive a conflicted recovery, then a clean re-sync, and paste
      the persona and model for each.
- [ ] T028 (SC-004) Start an epic with a promotion persona and paste the start
      payload's `VerificationConfig`; repeat without the flag.
- [ ] T029 (SC-005) Paste `ergane build status --json` for a node whose attempts
      ran on two personas.
