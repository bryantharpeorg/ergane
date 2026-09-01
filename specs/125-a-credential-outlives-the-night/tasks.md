# Tasks: a credential outlives the night

Read `plan.md` before starting. Its ten traps are the difference between a fix that
works and a fix that passes — trap 1 in particular describes the obvious edit and why
it is wrong.

Tests are written first and must fail before the implementation that satisfies them.
Every acceptance scenario is provable from the diff, which is all the judge sees
(trap 9).

`[P]` marks tasks that may be written in parallel within their phase. Tasks without it
touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A long-lived token reaches the agent

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, trap 1) Assert that with a long-lived token in the
      source environment, `attempt_env` for a **subscription**-routed context returns
      an environment carrying it. Use a synthetic token value (trap 4).
- [ ] T002 [P] [US1] (spec US1-S2, trap 2) Assert the token survives into the sandbox
      argument vector — that it appears as a `--setenv` after `--clearenv`, not only
      in the environment dict. This is the test that catches half a fix.
- [ ] T003 [P] [US1] (spec US1-S3, trap 1) **The control.** Assert that with the same
      token in the source environment, a **gateway**-routed context's environment does
      NOT carry it, and still carries `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`
      exactly as today.
- [ ] T004 [P] [US1] (spec US1-S4) **The control.** Assert that with no token in the
      source environment, a subscription-routed attempt's environment is byte-identical
      to today's, and the credential is still seeded into the per-node home.
- [ ] T005 [P] [US1] (spec US1-S5, trap 10) Assert that with both a token and a
      discoverable credential file present, the token is the credential used, and the
      attempt record states which source was chosen.
- [ ] T006 [P] [US1] (spec US1-S6, trap 5) **The boundary control.** Assert the gate
      boundary's environment does not carry the token, with the token present in the
      worker environment.
- [ ] T007 [P] [US1] (FR-012, traps 1 and 3) Assert `PASSTHROUGH_ENV` still equals
      `("PATH", "LANG", "TERM")`, and that no story introduced `ANTHROPIC_API_KEY`
      anywhere in `factory/`. A regression pin, not a behaviour test.

### Implementation for this story

- [ ] T008 [US1] (FR-001, FR-003, FR-004, trap 1) In `attempt_env`
      (`factory/workgraph/adapter.py:908`), construct the token into the environment
      in the subscription branch — beside the existing `if routes_through_gateway:`
      block, not by adding a member to `PASSTHROUGH_ENV`.
- [ ] T009 [US1] (FR-002, trap 2) Add the token to the sandbox's explicit `--setenv`
      tuple (`:584-600`), the second of the two mechanisms.
- [ ] T010 [US1] (FR-005, trap 10) Record which credential source the attempt used, so
      the precedence is legible in the record rather than inferred from behaviour.
- [ ] T011 [US1] (FR-006, trap 5) Confirm by reading `factory/verify/gates.py` that
      the gate boundary constructs its own environment and cannot inherit the token;
      if it can, close that path. Do not otherwise modify the gate boundary.

## Phase 2: User Story 2 — A credential that cannot work is refused before an attempt is spent

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1) Assert that with a copied credential whose recorded
      expiry has passed and no long-lived token, attempt preparation raises a refusal
      before the sandbox forks, and that the message names the expiry.
- [ ] T013 [P] [US2] (spec US2-S2) **The control.** Assert a credential whose expiry is
      in the future proceeds unchanged.
- [ ] T014 [P] [US2] (spec US2-S3, trap 6) **The control.** Assert that with a
      long-lived token present, an expired copied credential does NOT cause a refusal.
      The expired file is irrelevant when it is not the credential in use.
- [ ] T015 [P] [US2] (spec US2-S4, traps 6 and 7) **The control that matters most.**
      Assert a credential whose expiry is absent, unreadable or unparseable proceeds
      rather than refusing. Cover all three shapes; a check that refuses on absence
      stops a working factory.
- [ ] T016 [P] [US2] (spec US2-S5) Assert the refusal names both remedies — the
      interactive login and the long-lived token — not only the login the current
      message at `:1031-1033` names.
- [ ] T017 [P] [US2] (spec US2-S6) Assert the refusal is distinguishable from an
      attempt that ran and does not consume the ordinary attempt budget, using the
      shape 095 established (`pre_agent` on the record,
      `factory/verify/ladder.py:393`).
- [ ] T018 [P] [US2] (spec US2-S7, trap 8) Assert the credential check makes no network
      call, by a test that would fail if one were attempted.

### Implementation for this story

- [ ] T019 [US2] (FR-007, FR-009) Extend the existing subscription refusal at
      `factory/workgraph/adapter.py:1026-1034` to read the copied credential's recorded
      expiry and refuse before `_seed_node_home`. Read the local file only.
- [ ] T020 [US2] (FR-008, trap 7) Refuse only on positive evidence of expiry. Absent,
      unreadable and unparseable all proceed.
- [ ] T021 [US2] (FR-007) Rewrite the refusal message to name both remedies.
- [ ] T022 [US2] (FR-010) Give the refusal the record shape that keeps it off the
      ordinary attempt budget.

## Phase 3: User Story 3 — The operator can see the remaining runway

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1, trap 6) Assert that with a long-lived token
      configured, the status answer names the token as the source and does NOT report
      an expiry read from the unused credential file.
- [ ] T024 [P] [US3] (spec US3-S2) Assert that with only a copied credential, the
      answer names that source and its remaining validity.
- [ ] T025 [P] [US3] (spec US3-S3) Assert that with neither, the answer says so and
      names both remedies.
- [ ] T026 [P] [US3] (spec US3-S4, trap 4) **The safety test.** Assert no credential
      value appears in the rendered output, for every one of the three states above.

### Implementation for this story

- [ ] T027 [US3] (FR-011) Render the credential source and remaining validity on the
      operator surface, reading the precedence US2 established rather than re-deriving
      it (trap 10).
- [ ] T028 [US3] (FR-011, trap 4) Ensure the renderer cannot emit a credential value,
      in any of the three states.

## Phase 4: Verification, all stories

- [ ] T029 (FR-012, traps 1 and 3) Re-assert after all three phases: `PASSTHROUGH_ENV`
      unchanged at three members, no `ANTHROPIC_API_KEY` introduced, no subscription
      persona routed through the gateway.
- [ ] T030 (trap 4) Grep the diff for anything resembling a live credential —
      `sk-ant-`, a 108-character opaque string, or the operator-local token path — and
      confirm none is present in source, tests, fixtures or the attempt report.
- [ ] T031 (trap 9) Paste into the attempt report any runtime evidence the story
      produced. A described observation reaches no verdict; committed output does.
