# Tasks: a story can choose who builds it

**Spec**: `specs/070-a-story-can-choose-who-builds-it/spec.md`
**Plan**: `specs/070-a-story-can-choose-who-builds-it/plan.md`

Read the plan's traps before the first task. Trap 1 (do not touch the
`implementer` persona — the operator declined API billing and kimi stays the
builder), trap 9 (a ladder test written at default config is structurally unable
to fail) and trap 12 (one test file per story) are the three that decide whether
an attempt lands.

## Phase 1: User Story 1 — A story can name the persona that builds it

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In `tests/test_story_persona_pinning.py`, derive
      a graph whose one story declares a persona and assert **both** that the
      node carries it **and** that its siblings carry the default. A change that
      sets every node's persona passes an assertion about only the declared one.
- [ ] T002 [P] [US1] (spec US1-S2) Assert a story declaring no persona carries the
      default exactly as today.
- [ ] T003 [P] [US1] (spec US1-S3) Assert a story declaring an unknown persona is
      rejected at epic start naming the story and the persona, reaching
      `validate_workgraph`'s existing refusal rather than a second one.
- [ ] T004 [P] [US1] (spec US1-S4) Assert a declared persona resolving no timeout
      is rejected at start (`factory/workgraph/models.py:355-363`).
- [ ] T005 [P] [US1] (spec US1-S5) Assert the key is optional in the same way
      `timeout` is: blocks with neither key, one key, and both all derive.
- [ ] T006 [P] [US1] (spec US1-S6) Assert the pinned persona is snapshotted at epic
      start — a registry edit mid-epic does not change the running node
      (`factory/workgraph/models.py:199`).

### Implementation for this story

- [ ] T007 [US1] (FR-001) Add the persona key to
      `factory/workgraph/derive.py:79`'s `_OPTIONAL_KEYS`.
- [ ] T008 [US1] (FR-002) Carry it to the node, replacing the hardcoded
      `persona=IMPLEMENTER` at `factory/workgraph/derive.py:186`. Copy the shape
      of `timeout_override_s=declaration.timeout` at `:193`.
- [ ] T009 [US1] (FR-003) Ensure an unknown or timeout-less persona reaches the
      existing `validate_workgraph` refusal.
- [ ] T010 [US1] (FR-004) Confirm the snapshot discipline is unchanged.

## Phase 2: User Story 2 — A persona can be run against an operator subscription

### Establish feasibility BEFORE writing production code

- [ ] T011 [US2] (plan Sizing) By hand, outside the factory, confirm the Claude
      Code CLI authenticates from a **seeded credential in a synthetic HOME
      inside a bwrap sandbox with `--clearenv`** and `PASSTHROUGH_ENV` limited to
      PATH, LANG, TERM. Paste the result into the diff either way. If it does not
      work, this story is a different shape and saying so early is the correct
      outcome — do not spend the attempt discovering it last.

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1) In `tests/test_subscription_runner.py`, assert a
      subscription-routed node's environment contains neither
      `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN`
      (`factory/workgraph/adapter.py:774-775`).
- [ ] T013 [P] [US2] (spec US2-S2) Assert no virtual key is minted for it (trap 6).
- [ ] T014 [P] [US2] (spec US2-S3) Assert its per-node HOME carries the credential
      alongside the `.gitconfig` seeded at `factory/workgraph/adapter.py:740`.
- [ ] T015 [P] [US2] (spec US2-S4) **The control.** Assert a gateway persona still
      gets its key and both variables, and that **no** credential is seeded into
      its home. This is what keeps trap 4's exposure narrow.
- [ ] T016 [P] [US2] (spec US2-S5) Assert a missing credential is a named refusal
      **before the sandbox forks**, following `factory/verify/toolchain.py`'s
      `ToolchainError` precedent (trap 5).
- [ ] T017 [P] [US2] (spec US2-S6) Assert the ledger records the attempt as
      carrying no gateway spend data, distinguishably from a zero (trap 7).
- [ ] T018 [P] [US2] (spec US2-S7) Assert concurrent subscription-routed nodes are
      bounded by the declared limit.

### Implementation for this story

- [ ] T019 [US2] (FR-005) Add a second sentinel on the existing `agent` field,
      mirroring `DETERMINISTIC_AGENT` at `factory/config.py:143`, parsed at
      `:245` and required at `:145`.
- [ ] T020 [US2] (FR-006) Split `is_llm` (`factory/config.py:191`) into the two
      questions it now conflates — spends tokens, needs a key. **Read both
      callers first**: `factory/workgraph/preflight.py:552` and
      `factory/controlplane/verify.py:331` (trap 3).
- [ ] T021 [US2] (FR-006) Omit both gateway variables for a subscription node and
      mint no key.
- [ ] T022 [US2] (FR-007) Seed the credential into the per-node HOME
      (`factory/workgraph/adapter.py:719`, `:740`) for subscription personas only.
      Do not widen `PASSTHROUGH_ENV` at `:90` (trap 4).
- [ ] T023 [US2] (FR-008) Discover the credential's location rather than declaring
      it, and refuse by name before the fork if absent (trap 5).
- [ ] T024 [US2] (FR-009) Record the no-spend-data marker.
- [ ] T025 [US2] (FR-010) Bound concurrent subscription-routed nodes.

## Phase 3: User Story 3 — The ladder can promote a struggling node

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US3] (spec US3-S1) In `tests/test_promotion_rung.py`, assert a node
      whose ordinary attempts are spent is promoted rather than escalated.
      **Raise `max_attempts` above the cap under test** — at defaults the
      assertion cannot fail (trap 9,
      `factory/verify/ladder.py:17-19`).
- [ ] T027 [P] [US3] (spec US3-S2) Assert a node that has used its promotion
      escalates, bounded like the debugger rung.
- [ ] T028 [P] [US3] (spec US3-S3) **The regression control.** Assert the ladder
      behaves exactly as today when no promotion persona is configured.
- [ ] T029 [P] [US3] (spec US3-S4) Assert the new budget is honoured from
      `_LADDER_KEYS` (`factory/verify/factory_yaml.py:121`), alongside the
      existing three.
- [ ] T030 [P] [US3] (spec US3-S5) Assert a promoted attempt is distinguishable in
      history from an ordinary attempt and a debugger cycle, and assert **both**
      `_attempts_spent` (`ladder.py:111-119`) and `_debugger_cycles_spent`
      (`:122-124`) still count what they claim to (trap 8).
- [ ] T031 [P] [US3] (spec Edge Cases) Assert a node already built by the promotion
      persona skips the rung rather than promoting to itself.

### Implementation for this story

- [ ] T032 [US3] (FR-011) Add the rung to `NextAction`
      (`factory/verify/models.py:114`) and to `next_action`, above the escalation
      fallthrough. Keep `next_action` pure (trap 11). Never hardcode a persona
      name in code beyond a role constant, in the manner of `DEBUGGER_PERSONA`
      (`factory/verify/ladder.py:60`) — trap 2.
- [ ] T033 [US3] (FR-011) Make the promotion persona and its budget configuration,
      settable through `_LADDER_KEYS`.
- [ ] T034 [US3] (FR-012) Teach the history partition about the third rung.

## Verification

- [ ] T035 (SC-001) Derive a real spec with one story pinned and paste every
      node's persona.
- [ ] T036 (SC-002) Dispatch a subscription-routed node and paste the constructed
      environment with the credential **redacted**, showing neither gateway
      variable present. Say in the diff that you redacted it.
- [ ] T037 (SC-003) Paste the control from the same epic: a gateway node with both
      variables and no seeded credential.
- [ ] T038 (SC-004) Paste the ledger row for a subscription attempt, showing the
      no-spend-data marker rather than a zero.
- [ ] T039 (SC-005) Paste the promotion decision, then the escalation after the
      promotion is exhausted.
- [ ] T040 (SC-006) Run the existing ladder suite unchanged with no promotion
      persona configured and paste the result.
