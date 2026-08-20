# Tasks: a story can choose who builds it

**Spec**: `specs/070-a-story-can-choose-who-builds-it/spec.md`
**Plan**: `specs/070-a-story-can-choose-who-builds-it/plan.md`

Read the plan's traps before the first task. Trap 1 (do not touch the
`implementer` persona — the operator declined API billing and kimi stays the
builder), trap 9 (a ladder test written at default config is structurally unable
to fail), trap 12 (one test file per story) and trap 15 (**the feasibility spike
is already done — do not re-run it**) are the four that decide whether an attempt
lands. Trap 16 (persona may reopen a LANDED story through the fingerprint) is new as of the 2026-08-19 field report and decides whether US1 is safe to use on existing specs at all.

**Restructured 2026-08-19.** What was one oversized US2 covering declaration,
credential, accounting and concurrency is now US2, US3 and US4; the promotion
rung moved from US3 to US5. The feasibility question that made the old US2
open-ended has been answered by an operator session and its result, with its
control, is in the plan's Sizing section.

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

- [ ] T048 [P] [US1] (spec US1-S7, trap 16) **The landed-story guard.** Assert that
      adding a `persona:` key to a story that has already landed does **not**
      reopen it — or, if the chosen design keeps the key fingerprint-bearing,
      assert `validate` warns by name that the edit changed a landed story's
      fingerprint. One of these two tests must exist; which one depends on the
      decision trap 16 forces. Read `fingerprint()`
      (`factory/workgraph/landed.py:319`) and `_story_parts` (`:349`) first: the
      declaration's raw YAML text is a fingerprint component today, so the
      reopen is the DEFAULT and costs no code to get wrong.

## Phase 2: User Story 2 — A persona can declare that it bills to a subscription

No credential is involved in this story. It is the routing decision only, which
is why it is separable and why it can be tested end to end on any host.

### Tests for this story (write FIRST, must fail)

- [ ] T011 [P] [US2] (spec US2-S1) In `tests/test_subscription_routing.py`, assert a
      subscription-routed node's environment contains neither
      `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN`
      (`factory/workgraph/adapter.py:774-775`).
- [ ] T012 [P] [US2] (spec US2-S2) Assert no virtual key is minted for it (trap 6).
      **Read where minting actually happens before asserting on it** — it is not
      gated by `is_llm` today.
- [ ] T013 [P] [US2] (spec US2-S3) **The control.** Assert a gateway persona still
      gets its virtual key and both variables, exactly as today. Without it the
      story is satisfiable by removing the variables for everyone.
- [ ] T014 [P] [US2] (spec US2-S4) **The regression control for the property split.**
      Assert both existing `is_llm` callers — `factory/workgraph/preflight.py:552`
      and `factory/controlplane/verify.py:331` — behave exactly as today for
      deterministic and gateway personas (trap 3).

### Implementation for this story

- [ ] T015 [US2] (FR-005) Add a second sentinel on the existing `agent` field,
      mirroring `DETERMINISTIC_AGENT` at `factory/config.py:143`, parsed at
      `:245` and required at `:145`.
- [ ] T016 [US2] (FR-006) Split `is_llm` (`factory/config.py:191`) into the two
      questions it now conflates — spends tokens, needs a key. **Read both
      callers first** (trap 3).
- [ ] T017 [US2] (FR-006) Omit both gateway variables for a subscription node and
      mint no key.
- [ ] T049 [P] [US2] (spec US2-S5) **The model-name test — write it with T011.**
      Assert the constructed argv for a subscription-routed node carries a
      `--model` value the CLI accepts, and that a gateway node's argv still
      carries its proxy alias unchanged. Needs no credential, so it runs on any
      host. Measured answers to check against: `anthropic/claude-opus-5` → exit 1
      "may not exist or you may not have access to it"; `opus` → exit 0.
- [ ] T053 [P] [US2] (spec US2-S6) **The dispatch-blocker test, and the one this
      story is most likely to be shipped without.** Assert that the alias set
      `aliases_to_check` collects for a graph containing a subscription-routed
      node does **not** contain that persona's model. Note T014 is not this test:
      it covers the two *old* persona kinds, so it passes whether or not the new
      one is handled.
- [ ] T054 [US2] (FR-016) Exclude subscription personas from the served-alias
      check in `aliases_to_check` (`preflight.py:544-556`) and from `LLMProbe`
      (`factory/controlplane/verify.py:331`). Both ask `is_llm` today; after the
      T016 split they must ask "routes through the gateway", not "spends tokens".
- [ ] T050 [US2] (FR-014) Stop passing the registry alias verbatim to `--model`
      for subscription-routed nodes. `argv()` is `adapter.py:931`; the offending
      line is `:938`, `context.model_alias`. A second registry field or a
      translation at the seam — **say which in the diff, and why** (trap 17).

## Phase 3: User Story 3 — The credential reaches the sandbox, and only where it should

**Depends on US2** (`depends_on: [US2]`), logically and because both edit
`factory/workgraph/adapter.py` (trap 14).

**The sandbox is already known to work.** Plan § Sizing records the run and its
control: the CLI authenticates from a synthetic HOME containing only
`.gitconfig` and `.claude/.credentials.json`, under `--clearenv` with PATH, LANG,
TERM and HOME only. Do not re-establish it (trap 15).

### Tests for this story (write FIRST, must fail)

- [ ] T018 [P] [US3] (spec US3-S1) In `tests/test_subscription_credential.py`, assert
      a subscription-routed node's per-node HOME carries the credential alongside
      the `.gitconfig` seeded at `factory/workgraph/adapter.py:740`.
- [ ] T019 [P] [US3] (spec US3-S2) **The control, and the one that keeps the
      exposure narrow.** Assert a gateway-routed node's home has **no** credential
      in it (trap 4).
- [ ] T020 [P] [US3] (spec US3-S3) Assert a missing credential is a named refusal
      **before the sandbox forks**, following `factory/verify/toolchain.py`'s
      `ToolchainError` precedent (trap 5).
- [ ] T021 [P] [US3] (spec US3-S4) Assert the credential's location is **discovered,
      not hardcoded**: move it and assert discovery still succeeds (trap 5).
- [ ] T022 [P] [US3] (spec US3-S5, FR-013) Assert a credential that is present but
      refused is recorded as a named authentication failure, not as an empty
      diff. **Measured 2026-08-19: the CLI exits 1 and prints `Not logged in ·
      Please run /login` on STDOUT, not stderr.** Handling that watches stderr
      reads this as a silent success — that is what this test exists to catch.

### Implementation for this story

- [ ] T023 [US3] (FR-007) Seed the credential into the per-node HOME
      (`factory/workgraph/adapter.py:719`, `:740`) for subscription personas only.
      Do not widen `PASSTHROUGH_ENV` at `:90` (trap 4).
- [ ] T024 [US3] (FR-008) Discover the credential's location rather than declaring
      it, and refuse by name before the fork if absent (trap 5).
- [ ] T051 [P] [US3] (spec US3-S6) **The placement test.** Assert the credential
      placement the diff commits to is the one actually made in the node HOME
      (a copy, a bind, or a broker handle — whichever T052 chose).
- [ ] T052 [US3] (FR-015) Choose the placement **with respect to token refresh**
      and state the consequence in the diff. Facts to reason from, measured
      2026-08-19: the credential carries `expiresAt` and `refreshTokenExpiresAt`;
      the access token had 5.8h of life; `implementer`'s timeout is 14400s
      (`personas.yaml:80`), so attempts routinely outlive their own token. A
      plain copy means the refresh is discarded at teardown and every attempt
      re-refreshes from the same stored token. If you cannot establish whether
      the provider rotates refresh tokens on use, **say so** — do not assume the
      benign case (trap 18).
- [ ] T025 [US3] (FR-013) Classify a present-but-refused credential as an
      authentication failure.

## Phase 4: User Story 4 — A subscription attempt is honest in the ledger and bounded in flight

**Depends on US2** (`depends_on: [US2]`): an attempt cannot be recorded as
subscription-routed until the system can tell that it is.

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US4] (spec US4-S1) In `tests/test_subscription_accounting.py`, assert
      the ledger records the attempt as carrying no gateway spend data,
      distinguishably from a zero (trap 7).
- [ ] T027 [P] [US4] (spec US4-S2) **The control.** Assert a gateway attempt is
      recorded exactly as today.
- [ ] T028 [P] [US4] (spec US4-S3) Assert concurrent subscription-routed nodes are
      bounded by the declared limit.
- [ ] T029 [P] [US4] (spec US4-S4) Assert the documented behaviour when no limit is
      declared. An unbounded default is a decision to make on purpose, not an
      omission to discover.

### Implementation for this story

- [ ] T030 [US4] (FR-009) Record the no-spend-data marker.
- [ ] T031 [US4] (FR-010) Bound concurrent subscription-routed nodes, and state the
      no-limit default.

## Phase 5: User Story 5 — The ladder can promote a struggling node

### Tests for this story (write FIRST, must fail)

- [ ] T032 [P] [US5] (spec US5-S1) In `tests/test_promotion_rung.py`, assert a node
      whose ordinary attempts are spent is promoted rather than escalated.
      **Raise `max_attempts` above the cap under test** — at defaults the
      assertion cannot fail (trap 9, `factory/verify/ladder.py:17-19`).
- [ ] T033 [P] [US5] (spec US5-S2) Assert a node that has used its promotion
      escalates, bounded like the debugger rung.
- [ ] T034 [P] [US5] (spec US5-S3) **The regression control.** Assert the ladder
      behaves exactly as today when no promotion persona is configured.
- [ ] T035 [P] [US5] (spec US5-S4) Assert the new budget is honoured from
      `_LADDER_KEYS` (`factory/verify/factory_yaml.py:121`), alongside the
      existing three. **`_LADDER_KEYS` is integer-only** and its bounds lookup
      raises on an unknown key — a persona *name* cannot be a ladder key, so the
      budget goes there and the persona goes elsewhere.
- [ ] T036 [P] [US5] (spec US5-S5) Assert a promoted attempt is distinguishable in
      history from an ordinary attempt and a debugger cycle, and assert **both**
      `_attempts_spent` (`ladder.py:111-119`) and `_debugger_cycles_spent`
      (`:122-124`) still count what they claim to (trap 8).
- [ ] T037 [P] [US5] (spec Edge Cases) Assert a node already built by the promotion
      persona skips the rung rather than promoting to itself.

### Implementation for this story

- [ ] T038 [US5] (FR-011) Add the rung to `NextAction`
      (`factory/verify/models.py:114`) and to `next_action`, above the escalation
      fallthrough. Keep `next_action` pure (trap 11). Never hardcode a persona
      name in code beyond a role constant, in the manner of `DEBUGGER_PERSONA`
      (`factory/verify/ladder.py:60`) — trap 2.
- [ ] T039 [US5] (FR-011) Make the promotion persona and its budget configuration.
      The **budget** belongs in `_LADDER_KEYS`; the **persona name** does not —
      see T035.
- [ ] T040 [US5] (FR-012) Teach the history partition about the third rung.

## Verification

- [ ] T041 (SC-001) Derive a real spec with one story pinned and paste every
      node's persona.
- [ ] T042 (SC-002) Dispatch a subscription-routed node and paste the constructed
      environment with the credential **redacted**, showing neither gateway
      variable present. Say in the diff that you redacted it.
- [ ] T043 (SC-003) Paste the control from the same epic: a gateway node with both
      variables and no seeded credential.
- [ ] T044 (SC-004) Paste the ledger row for a subscription attempt beside a
      gateway row from the same epic, showing the no-spend-data marker rather
      than a zero.
- [ ] T045 (SC-005) Paste the promotion decision, then the escalation after the
      promotion is exhausted.
- [ ] T046 (SC-006) Run the existing ladder suite unchanged with no promotion
      persona configured and paste the result.
- [ ] T047 (SC-007) Paste the unauthenticated case: a subscription-routed node
      whose credential is absent or stale, showing the named refusal rather than
      a diffless attempt.
- [ ] T055 (SC-008) Paste the constructed argv for a subscription node and for a
      gateway node from the same epic, showing the CLI-accepted model name on one
      and the proxy alias on the other.
- [ ] T056 (SC-009) Paste the chosen credential placement and one sentence on
      what becomes of a token refreshed at hour three of a four-hour attempt.
- [ ] T057 (SC-010) Paste the alias set dispatch preflight collects for a graph
      holding both node kinds, showing the gateway alias present and the
      subscription persona's model absent.
