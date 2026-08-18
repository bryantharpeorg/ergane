# Tasks: the gateway is a choice, and install can find one

**Spec**: `specs/055-the-gateway-is-a-choice-with-a-scan/spec.md`
**Plan**: `specs/055-the-gateway-is-a-choice-with-a-scan/plan.md`

Read the plan's **Traps** first. Traps 1 and 2 decide whether US1 takes one
attempt or four; trap 3 is the one that makes US2 correct rather than merely
working.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass.

## Phase 1: User Story 1 — Install can find the gateway that is already there

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) `tests/test_llm_discovery.py`: an endpoint
      answering `/v1/models` through the injected seam is reported with its
      address and its advertised aliases.
- [ ] T002 [P] [US1] (spec US1-S2) Same file: an endpoint answering both
      `/v1/models` and the key-management API classifies as dispatchable; one
      answering only `/v1/models` classifies as inference-only and names the
      missing capability. Both cases in one test module, neither simulated away.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) Same file: assert **no probe request
      carries an authorization header** — the security property, checked at the
      request the seam actually receives, not at the caller (trap 1).
- [ ] T004 [P] [US1] (spec US1-S4, FR-004) Same file: with no address declared,
      only loopback candidates are probed; a non-loopback candidate is probed
      only when explicitly named.
- [ ] T005 [P] [US1] (spec US1-S5) Same file: a scan that finds nothing says so
      and names what it looked for, rather than reporting an empty success.
- [ ] T006 [P] [US1] (spec US1-S6, FR-005) Same file: assert the network is
      reached only through the injected seam and that no test in this module
      opens a real socket (trap 2).

### Implementation for this story

- [ ] T007 [US1] (spec US1-S1, FR-001) Add the discovery module: a candidate
      list, one injected transport seam, and a per-candidate result carrying
      address, reachability, advertised aliases and classification.
- [ ] T008 [US1] (spec US1-S2, FR-002) Classify from the unauthenticated
      responses: `/v1/models` alone is inference-only; the key-management API
      answering as well is dispatchable. Name the missing capability in the
      inference-only result.
- [ ] T009 [US1] (spec US1-S4, FR-004) Default the candidate list to loopback
      addresses only. A non-loopback candidate enters only by being named.
- [ ] T010 [US1] (spec US1-S1, FR-001) Add `ergane install --scan`: read-only,
      writes no config, renders the results as a table. It must not touch the
      interview (trap 8).
- [ ] T011 [US1] (spec SC-001) Commit the scan transcript against two real
      endpoints — one inference-only, one dispatchable — to
      `specs/055-the-gateway-is-a-choice-with-a-scan/evidence/us1-scan.md`
      (trap 10).

## Phase 2: User Story 2 — `direct` dispatches, and says what it gave up

Independent of US1. Touches config, the dispatch path and the registry — never
the interview (trap 8).

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-006) `tests/test_controlplane_direct_mode.py`:
      a config declaring `llm.mode = "direct"` with a base URL and an API key
      env var parses and carries a `direct` block. `KNOWN_LL_MODES` is unchanged
      — assert the tuple still reads `("gateway", "direct")` (plan, trap on the
      existing token).
- [ ] T013 [P] [US2] (spec US2-S2, FR-007) Same file: dispatching in `direct`
      mode still calls `issue_attempt_key` and still writes the attempt's ledger
      row; the activity returns the declared credential instead of a minted one
      (trap 3).
- [ ] T014 [P] [US2] (spec US2-S3, FR-008) Same file: the three surrendered
      properties are named at declaration time — non-expiring credential,
      advisory persona binding, no attribution.
- [ ] T015 [P] [US2] (spec US2-S4, FR-009) Same file: `ergane usage` in `direct`
      mode reports attribution unavailable and does **not** return an empty
      rollup (trap 4).
- [ ] T016 [P] [US2] (spec US2-S5, FR-011) Same file: the invariant
      `personas.yaml` states matches the modes the config admits.
- [ ] T017 [P] [US2] (spec US2-S6, FR-010) Same file: the declared credential is
      redacted from errors, logs and rendered output, held to the same bar
      `litellm_client.py` holds the master key to (trap 6).
- [ ] T018 [P] [US2] (spec SC-003) Same file: the surrendered-properties text has
      exactly one definition, and the interview copy, the config error and the
      docs all render from it (trap 5).

### Implementation for this story

- [ ] T019 [US2] (spec US2-S1, FR-006) Add `LLMDirect(base_url, api_key_env)` to
      the existing discriminated `LLM` union in
      `factory/controlplane/config.py`, and replace the
      `RULE_LLM_DIRECT_NOT_SUPPORTED` raise with the parse. Keep the refusal's
      own wording as the source of the surrendered-properties text — it is
      already an accurate list.
- [ ] T020 [US2] (spec US2-S2, FR-007) Give `issue_attempt_key` a direct-mode
      path returning the declared credential, leaving the ledger write and the
      call sites at `workflow.py:1197`, `:1809` and `:2437` untouched.
- [ ] T021 [US2] (spec US2-S4, FR-009) Make `ergane usage` report attribution as
      unavailable in `direct` mode.
- [ ] T022 [US2] (spec US2-S5, FR-011) Amend `personas.yaml`'s header so its
      claim is true in both modes.
- [ ] T023 [US2] (spec US2-S6, FR-010) Extend redaction to the direct credential
      everywhere the master key is already scrubbed.

## Phase 3: User Story 3 — Install offers the mode the host can actually run

Merge-depends on US1 and US2. Owns `factory/cli/install.py` outright.

### Tests for this story (write FIRST, must fail)

- [ ] T024 [P] [US3] (spec US3-S1, FR-012) `tests/test_install_mode_routing.py`:
      a dispatchable scan result offers `gateway` with that address defaulted.
- [ ] T025 [P] [US3] (spec US3-S2, FR-012) Same file: an inference-only result
      offers `direct`, defaults the address, and names the missing capability as
      the reason `gateway` is unavailable.
- [ ] T026 [P] [US3] (spec US3-S3, FR-008) Same file: choosing `direct` states
      the three surrendered properties **before** the config is written.
- [ ] T027 [P] [US3] (spec US3-S4, FR-012) Same file: a scan finding nothing
      falls back to today's question, unchanged.
- [ ] T028 [P] [US3] (spec US3-S5, FR-013) Same file: an operator-declared
      address overrides any scan result.

### Implementation for this story

- [ ] T029 [US3] (spec US3-S1, US3-S2, FR-012) Run the scan before the LLM
      question and use its classification to choose the offered mode and default
      the address.
- [ ] T030 [US3] (spec US3-S2, FR-012) When a mode is unavailable, say which
      capability is missing rather than that the mode is unsupported.
- [ ] T031 [US3] (spec US3-S3, FR-008) Render the surrendered-properties text
      from US2's single definition, before the write.
- [ ] T032 [US3] (spec US3-S4, US3-S5, FR-013) Keep the scan advisory: no
      failure, absence or classification may prevent the operator answering by
      hand.

## Verification

- [ ] T033 Run the scan against a real loopback inference endpoint and against
      the LiteLLM proxy; confirm the two classifications differ and that the
      inference-only result names the missing capability.
- [ ] T034 Observe the probe traffic during a scan and confirm no authorization
      header leaves the host — the one requirement where a passing test and a
      leaking implementation can coexist (plan, trap 1).
- [ ] T035 Prove SC-001 end to end: on a host with a provider key and no proxy,
      declare `direct` and dispatch one attempt to completion.
- [ ] T036 Prove FR-009 by control: run `ergane usage` in each mode and confirm
      gateway returns rows while direct reports attribution unavailable. Two
      empty tables means the story failed on a green suite.
