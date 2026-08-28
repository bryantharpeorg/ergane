# Tasks: a subscription is a starting position

**Input**: `spec.md` and `plan.md` in this directory, both drafted 2026-08-27
against ergane-buildout at 3e5c940.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch different files or independent test functions.

## Phase 1: User Story 1 — A token is a credential the factory can take

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-002) Token-discovery test, in a new
  `tests/test_112_us1_subscription_token.py`: with `CLAUDE_CODE_OAUTH_TOKEN` set
  and an `operator_home` containing none of the three searched files, assert
  discovery resolves the token, and that seeding a scratch per-node HOME writes
  **no** `.claude/.credentials.json` into it. Assert the absence by listing the
  seeded home, not by checking one expected path — the point is that no copy of
  the operator's login exists anywhere under it.
- [ ] T002 [P] [US1] (spec US1-S2, FR-003) Environment-invariant test: with a
  token resolved, assert the agent environment the adapter assembles carries the
  token and contains neither `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN`.
  The subscription route is defined by that absence (070-US2 FR-006) and a token
  must not smuggle either back (plan T4).
- [ ] T003 [P] [US1] (spec US1-S3, FR-004) Precedence test: with **both** a token
  in the environment and a real credentials file at the third search path,
  assert the token is chosen and nothing is copied. Assert the order explicitly;
  a test that happens to pass because of statement order in the implementation
  does not pin a contract (plan T5).
- [ ] T004 [P] [US1] (spec US1-S4, FR-005) Refusal-text test: with no token and
  no file, assert the `AdapterError` names both `claude auth login` and
  `claude setup-token`, and that it does **not** contain the bare string
  `claude login` as a standalone remedy — that spelling is not a command in
  Claude Code 2.1.223 (plan T6).
- [ ] T005 [P] [US1] (FR-001) Regression guard: with no token set, assert the
  three-path file search resolves in today's order — `$XDG_CONFIG_HOME`, then
  `~/.config/claude`, then `~/.claude` — and that the file branch still copies at
  mode 0600. This floor runs on that branch; widening discovery must not disturb
  it.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, FR-003, FR-004, FR-005) Widen
  `discover_subscription_credential` (`factory/workgraph/adapter.py:797-830`) to
  return a result carrying either a token or a path; branch `_seed_node_home`
  (`:833-867`) on it — token writes nothing, path keeps today's 0600 copy; carry
  the token into the agent environment; correct the refusal at `:1002-1008`.

### Verification for this story

- [ ] T007 [US1] (spec US1-S1, SC-001) Paste into the PR: a listing of a seeded
  per-node HOME under a token showing no credentials file, the four subscription
  suites passing (29 tests today), and the full-suite before-and-after counts.

## Phase 2: User Story 2 — No gateway is a declaration, not a failure

### Tests for this story (write FIRST, must fail)

- [ ] T008 [US2] (spec US2-S1, FR-006) Parse test, in a new
  `tests/test_112_us2_no_gateway_mode.py`: a config declaring
  `llm.mode = "none"` parses with no `base_url` and no `master_key_env`, and
  carries a surrendered-properties text naming all three surrenders. Assert the
  text states that the credential reaches every attempt unexpiring and that
  persona-to-model binding is unenforced — the two security halves — not merely
  that spend attribution is unavailable (plan T1).
- [ ] T009 [P] [US2] (spec US2-S2, FR-007) Refusal test: `llm.mode = "none"` with
  a registry containing at least one persona whose `routes_through_gateway` is
  True is refused by name, and the refusal lists the offending personas. This is
  the combination that must be unreachable (plan T2).
- [ ] T010 [P] [US2] (spec US2-S3, FR-008) Declared-absent PASS test: with
  `llm.mode = "none"` and an all-subscription registry, the `llm` finding's
  `passed` is True and its detail names the surrender. Assert on the detail's
  content, in the manner the escalation probe's detail is pinned — a PASS whose
  detail says only "skipped" fails this scenario.
- [ ] T011 [P] [US2] (spec US2-S4, FR-010) Direct-mode finding test: verifying a
  `direct` config produces a finding and raises nothing. Today
  `LLMProbe.gather` asserts `config.llm.gateway is not None`
  (`factory/controlplane/verify.py:415-417`) while `_read_llm` returns a
  populated direct config (`factory/controlplane/config.py:374-384`); the test
  asserts no exception escapes.
- [ ] T012 [P] [US2] (spec US2-S5, FR-009) Preserved-failure tests, three cases,
  all still FAIL: an empty alias set under a `gateway` declaration; the
  `example/` placeholder registry (`verify.py:441-451`); a missing master key
  (`:423-429`). This is the story's guard against widening FR-008 into "empty
  aliases always pass" (plan T3).

### Implementation for this story

- [ ] T013 [US2] (FR-006, FR-007) Add `"none"` to `KNOWN_LL_MODES`
  (`config.py:35`) with an `LLMNone` block mirroring `LLMDirect`
  (`:374-384`) and its surrender text beside
  `DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT` (`:350-360`); add the registry
  cross-check that refuses a `none` declaration while any persona routes through
  the gateway.
- [ ] T014 [US2] (FR-008, FR-009, FR-010) Remove the assertion at
  `verify.py:415-417` and its stale comment; add the declared-absent branch to
  `LLMProbe`; leave every other verdict in `evaluate` (`:648-656`) as it is.

### Verification for this story

- [ ] T015 [US2] (spec US2-S3, spec US2-S5, SC-002) Paste into the PR: the
  `[PASS] llm:` line from a no-gateway verify with its surrender text; the
  refusal transcript from T009; the three preserved-failure results from T012;
  and the existing control-plane suite passing unmodified.

## Phase 3: User Story 3 — The interview can produce that position

### Tests for this story (write FIRST, must fail)

- [ ] T016 [US3] (spec US3-S1, FR-011) Disclosure-ordering test, in a new
  `tests/test_112_us3_install_no_gateway.py`: driving the interview through a
  scripted prompter, the surrender text appears in the transcript **before** the
  answer is accepted — the ordering `direct` already uses
  (`factory/cli/install.py:1596-1602`).
- [ ] T017 [P] [US3] (spec US3-S2, FR-012) Written-files test: after choosing the
  no-gateway answer, the written config declares `llm.mode = "none"` and
  `gather_gateway_aliases` (`verify.py:386-402`) over the written registry
  returns empty.
- [ ] T018 [P] [US3] (spec US3-S3, FR-012) Registry-membership test: drive the
  interview against a registry that is **not** the shipped six — one with five
  personas and one with seven — and assert every persona in each is interviewed,
  and that the transcript's question order is stable across runs (plan T8 keeps
  `_GATEWAY_PERSONA_ORDER` as a sort key, so the order must not become dict
  iteration order).
- [ ] T019 [P] [US3] (spec US3-S4, FR-013) Unchanged-gateway-path test: the
  existing install suite passes unmodified, and a scripted gateway interview
  produces byte-for-byte today's config and registry.

### Implementation for this story

- [ ] T020 [US3] (FR-011, FR-012, FR-013) Add the no-gateway answer to the LLM
  question with its pre-acceptance disclosure; derive the per-persona question
  set from the resolved registry filtered to gateway personas, using
  `_GATEWAY_PERSONA_ORDER` (`install.py:471-478`) as a sort key rather than as
  membership.

### Verification for this story

- [ ] T021 [US3] (spec US3-S1, SC-003) Paste into the PR: the scripted interview
  transcript showing the surrender text ahead of the confirmation, the written
  config and registry, and the full-suite before-and-after counts.

## What no task here can prove

Every task above runs against scratch homes, scripted prompters and parsed
configs. **None of them proves the thing the spec is for**, which is that a
person holding nothing but a Claude subscription can install this factory and
watch it build something. That requires a machine with a subscription and no
gateway, and this one has both a gateway and a credentials file that has been in
place for weeks.

That proof is the operator verification in `plan.md`: `claude setup-token`,
export, install choosing the no-gateway answer, a green `llm` line, and one real
story reaching PASSED. A green verify line on its own proves a declaration
parses, which is the smaller half.

One risk this file will not hide: **US1 changes the credential path this floor
currently runs on.** Two personas in `personas.yaml` declare `agent:
subscription`, and every Opus-routed story since 2026-08-20 has gone through
`_seed_node_home`'s file copy. The four existing subscription suites are the
regression gate, and T005 exists so the file branch is pinned by a test that was
written to defend it rather than merely inherited.
