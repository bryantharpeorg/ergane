# Tasks: install proposes personas and proves them

**Spec**: `specs/103-install-proposes-personas-and-proves-them/spec.md`
**Plan**: `specs/103-install-proposes-personas-and-proves-them/plan.md`

Read the plan's traps first. Three decide whether an attempt lands. Trap 1:
enrichment reads the *confirmed* document's endpoint and key env, never the
scan result's. Trap 2: probe first, write once, load the written file back
through `load_personas` before declaring success. Trap 6: the judge and every
fallback re-prompt even under an all-Enter transcript — structural, not a
printed warning.

## Phase 1: User Story 1 — Enrichment (parallel with Phase 3)

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001) Against an injected transport
      simulating LiteLLM `/model/info` + wildcard-expanded `/v1/models`,
      enrichment returns one record per alias with tool-calling, structured
      output, reasoning, context window and cost fields; assert no request
      carried a credential before the confirmed-document step provided one.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Metadata endpoint answers 404 /
      garbage: every alias unclassified with a detail naming what was tried;
      no exception escapes.
- [ ] T003 [P] [US1] (spec US1-S3, FR-001) Ollama-shaped endpoint:
      `/api/show` capabilities populate the same record type.

### Implementation for this story

- [ ] T004 [US1] (FR-001, FR-002) The enrichment module beside the scanner
      (`factory/discovery/`), copying `scan_endpoints`'s injected-transport
      shape (`factory/discovery/llm_scanner.py:64-87`) and endpoint-constant
      style (`:46-47`). Input: the confirmed llm block (base_url, key env
      name) + the alias tuple. Output: the one record type all three sources
      share.

### Verification for this story

- [ ] T020 [US1] (spec US1-S1, SC-001) Paste enrichment output for the three
      source shapes.

## Phase 2: User Story 2 — The proposal (after Phase 1 merges)

### Tests for this story (write FIRST, must fail)

- [ ] T005 [US2] (spec US2-S1, FR-003) Rich fixtures: every gateway persona
      in the shipped example gets (primary, fallback, reason); the judge's
      primary differs from the implementer's when a qualifying alternative
      exists; the requirements table is readable as data by the test.
- [ ] T006 [P] [US2] (spec US2-S2, FR-003) All-unclassified fixtures: every
      slot is "needs the operator's choice" with candidates attached; nothing
      auto-assigned.
- [ ] T007 [P] [US2] (spec US2-S3, FR-004) No qualifying judge candidate: the
      result names the judge, the requirement, and the aliases considered.

### Implementation for this story

- [ ] T008 [US2] (FR-003, FR-004) The requirements table (data, one row per
      LLM persona of `personas.example.yaml`, content per the spec's ruling)
      and the pure proposal builder over US1's record type. Exclusions via
      `routes_through_gateway` (`factory/config.py:202-208`), never agent
      strings (trap 9).

### Verification for this story

- [ ] T021 [US2] (spec US2-S1, SC-002) Paste one full proposal with reasons
      and one refusal.

## Phase 3: User Story 3 — The judge canary (parallel with Phase 1)

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US3] (spec US3-S1, FR-005) Canned schema-valid FAIL verdict on
      the committed known-bad diff fixture: canary passes.
- [ ] T010 [P] [US3] (spec US3-S2, FR-005) Prose answer, schema violation,
      PASS-on-known-bad: three failures, three distinct reasons (trap 4).
- [ ] T011 [P] [US3] (spec US3-S3, FR-005) The injected client's observed
      calls show the minted/constrained/revoked-in-finally key discipline
      (`factory/controlplane/verify.py:420-460`) and a generous explicit
      max_tokens (trap 5).

### Implementation for this story

- [ ] T012 [US3] (FR-005) The canary: committed toy-diff + criteria + verdict
      schema fixtures (trap 3), one entry point taking (alias, client),
      reusing the existing `LLMProbe` client seam
      (`factory/controlplane/verify.py:340`).

### Verification for this story

- [ ] T022 [US3] (spec US3-S1, SC-003) Paste the canary's pass and its three
      distinct failures.

## Phase 4: User Story 4 — The interview picks, probes and writes

### Tests for this story (write FIRST, must fail)

- [ ] T013 [US4] (spec US4-S1, FR-006, FR-007, FR-009) End-to-end interview
      through `_FilePrompter` (`factory/cli/install.py:384-412`) with
      injected enrichment + probe seams: all-accept writes a registry
      differing from the shipped example only in `model`/`fallback`; the
      write happens after probes; `load_personas` accepts the written file;
      the same run's `verify_controlplane` is invoked on it.
- [ ] T014 [P] [US4] (spec US4-S2, FR-007) A failing probe drops the alias,
      re-proposes, and the failed alias appears nowhere in the written file.
- [ ] T015 [P] [US4] (spec US4-S3, FR-008) Unsatisfiable judge: nonzero exit
      naming judge, requirement, candidates; the on-disk registry is the
      seeded example, byte-for-byte.
- [ ] T016 [P] [US4] (spec US4-S4, FR-006) All-Enter transcript still yields
      explicit prompts for the judge and every fallback (trap 6) — asserted
      on the prompter transcript.
- [ ] T017 [P] [US4] (spec US4-S5, FR-009) Subscription persona: confirmed
      with its CLI-side model name shown, no gateway probe issued.
- [ ] T018 [P] [US4] (FR-010) `--non-interactive` and `--from-file` behave
      exactly as today: seed at `factory/cli/install.py:347-349`/`:441-443`,
      verify reports unconfigured — their existing tests pass unmodified.

### Implementation for this story

- [ ] T019 [US4] (FR-006..FR-009) The persona step in `install_command`
      between `_interview` and `verify_controlplane`
      (`factory/cli/install.py:275-284` region): consume the confirmed llm
      block (trap 1), enrich (US1), propose (US2), present via `_ask`
      (`:950`) one line per persona with reason pre-filled, probe chosen
      aliases (1-token per alias, canary for the judge), then write once —
      temp-file-and-rename — and load back (trap 2). Failure paths per
      FR-008.

### Verification for this story

- [ ] T023 [US4] (spec US4-S1, SC-004) Paste the interview transcript, the
      registry diff against the example (alias fields only), and the passing
      verify from the same run.
