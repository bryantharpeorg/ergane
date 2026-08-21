# Tasks: a probe tests the endpoint the attempt will use

**Spec**: `specs/080-a-probe-tests-the-endpoint-the-attempt-will-use/spec.md`
**Plan**: `specs/080-a-probe-tests-the-endpoint-the-attempt-will-use/plan.md`

Read the plan's traps before the first task. Trap 1 (**the precedence stays
environment-first**), trap 2 (**do not change `from_env`**) and trap 3 (two
variables from one source is not FR-002) are the three that decide whether an
attempt lands.

## Phase 1: User Story 1 — The probe mints where the attempt will run

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) In
      `tests/test_probe_mints_where_the_attempt_runs.py`, assert the probe FAILS
      when the declared gateway cannot mint and the environment names one that
      can. This is the configuration demonstrated live on 2026-08-20, on which
      today's tree reports "minted, constrained and revoked".
- [ ] T002 [P] [US1] (spec US1-S2, FR-003) **The control.** Assert a declared
      gateway that can mint, with no environment variable set, passes. A fix
      that reads the declaration and ignores the environment inverts the defect
      (trap 1).
- [ ] T003 [P] [US1] (spec US1-S3) **The second control, and the one that covers
      every real install.** Assert that when environment and declaration agree,
      the probe behaves exactly as it does today. If this test needs changing to
      pass, the change is wrong (trap 7).
- [ ] T004 [P] [US1] (spec US1-S4, FR-002) Change the resolved endpoint **once**
      and assert both the mint target and the completion target moved. This is
      the test that distinguishes FR-002 from setting two variables from one
      source (trap 3).

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002) Make `_llm_client_factory`
      (`factory/controlplane/verify.py:160`) and the completion path
      (`:315`, `:452-453`) read one resolution.
      `factory/controlplane/verify.py:170`'s `_temporal_client_factory` is the
      precedent in the same file, and `factory/controlplane/resolve.py:252`'s
      docstring says why it has the shape it has.
- [ ] T006 [US1] (FR-003) Preserve environment-first precedence.
      `factory/controlplane/resolve.py:158-159` is where the gateway applies it.
- [ ] T007 [US1] Leave `LiteLLMClient.from_env` alone (trap 2). If the probe
      needs a constructor that takes a resolution, add one beside it and say so.
- [ ] T008 [US1] Leave the five-step key sequence at
      `factory/controlplane/verify.py:361-423` untouched (trap 6).

### Verification for this story

- [ ] T009 [US1] (SC-001) Paste the mutation both ways: the run against today's
      tree reporting success, and the run after the fix reporting failure.
- [ ] T010 [US1] (SC-002) Paste the agreeing-configuration control.
- [ ] T011 [US1] (SC-003) Paste the declaration-only control.

## Phase 2: User Story 2 — A verdict names the endpoint and the source that chose it

**Depends on US1 having merged** (`depends_on_merged`). Both stories edit
`factory/controlplane/verify.py`.

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-004) In
      `tests/test_probe_names_the_endpoint_it_used.py`, assert a passing report
      names the gateway address that answered and the source that supplied it.
      `GatewayResolution` already carries both (`factory/controlplane/resolve.py:160-165`);
      this is rendering, not plumbing (trap 4).
- [ ] T013 [P] [US2] (spec US2-S2, FR-005) Assert a failing report names the
      address that was actually contacted. Today
      `factory/controlplane/verify.py:436` names the declared url regardless.
- [ ] T014 [P] [US2] (spec US2-S3, FR-004) Assert a report says so when an
      environment variable overrode a declaration.
- [ ] T015 [P] [US2] (spec US2-S4, FR-006) Assert no credential appears in a
      rendered report. This story adds print statements next to a master key
      (trap 5).

### Implementation for this story

- [ ] T016 [US2] (FR-004) Render the address and its source.
- [ ] T017 [US2] (FR-005) Correct the six message sites that interpolate
      `base_url`: `factory/controlplane/verify.py:436`, `:469`, `:474`, `:529`,
      `:533`, and the completion path at `:452-453`.

### Verification for this story

- [ ] T018 [US2] (SC-004) Paste a passing report showing the address and source.
- [ ] T019 [US2] (SC-005) Paste a failing report showing the address named is the
      address called.
- [ ] T020 [US2] (SC-006) Paste a report rendered with a master key set, showing
      the key absent.
</content>
