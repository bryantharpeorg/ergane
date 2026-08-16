# Tasks: 048-declared-control-plane

Four stories in a diamond: US1 first, then US2 and US3 concurrently off it, then
US4 behind both. The edges are merge-edges, not pass-edges, and each has a
reason: US2 and US3 need US1's resolver *present*, US2 and US1 both append to
`docs/decisions.md`, US4 edits `factory/controlplane/verify.py` after US2 has
finished removing from it and needs US3's `--sources` mode to report into.

Work test-first and commit once per task.

Read plan.md before the first commit. Trap 1 (this host must keep building with
no config file at all), trap 3 (degrade for a missing config, refuse for a
broken one), trap 4 (a test that reads the operator's real
`~/.config/ergane/config.toml` cannot fail here) and trap 11 (`factory/controlplane/__init__.py`
must stay 0 bytes) are the four that cost a rejected attempt each if met late.

## Phase 1: User Story 1 — The build resolves its endpoint and credential from what was declared

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] Write the override-wins case FIRST, before any other:
      a fixture config declaring an endpoint and `master_key_env`, plus a
      fixture environment setting `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY`
      to *different* values; resolution returns the environment's values and
      names each variable as its source (spec US1-S2, plan trap 1) — the two
      sources must disagree on every value or the test proves nothing
      (plan trap 5) — must fail.
- [ ] T002 [P] [US1] Write the declared-only case: no `LITELLM_*` variable set,
      a fixture config declaring `llm.base_url` and
      `master_key_env = "DECLARED_KEY_VAR"`, and `DECLARED_KEY_VAR` set;
      resolution returns the declared endpoint and the declared variable name,
      each sourced to the config path (spec US1-S1, SC-002) — must fail.
- [ ] T003 [P] [US1] Write the file-not-read case: both overrides set and the
      config path bound to **unparseable TOML**; resolution succeeds and raises
      nothing, which a resolver that opened the file could not do
      (spec US1-S3, FR-002) — must fail.
- [ ] T004 [P] [US1] Write the nothing-declared refusal: no overrides, config
      path bound to a nonexistent file; epic start refuses naming both the
      environment variable and the config path (spec US1-S4, FR-004) — must
      fail.
- [ ] T005 [P] [US1] Write the broken-config refusal: no overrides, config path
      bound to a file the parser refuses; the refusal carries the parser's own
      reason and names the file rather than reporting an unset variable
      (spec US1-S5, FR-005, plan trap 3) — must fail.
- [ ] T006 [P] [US1] Write the missing-variable case: config declares
      `master_key_env = "DECLARED_KEY_VAR"`, nothing sets it, no override; the
      error names that variable and the config path and nothing else
      (spec US1-S6, FR-003) — must fail.
- [ ] T007 [P] [US1] Write the sentinel case: plant a distinctive credential
      value in the declared variable, resolve successfully, assert the sentinel
      is absent from the resolution's `repr` (spec US1-S7, SC-005, plan trap 6)
      — a blank or absent fixture credential makes this test worthless — must
      fail.
- [ ] T008 [P] [US1] Write the parity case: with both overrides exported and no
      config, the `EpicInput` built by epic start is byte-identical to today's,
      asserted against the current construction (spec US1-S8, SC-001) — must
      pass before and after; it is what pins trap 1.
- [ ] T009 [US1] Write the control FIRST, against the disable-seam: with the
      config branch of the resolver disabled, T002's declared-only fixture
      refuses exactly as the tree refuses today (SC-004) — the seam is an
      explicit argument or injected loader, never an environment read (plan
      route choices) — this is the test that proves the new branch changed an
      outcome.

### Implementation for this story

- [ ] T010 [US1] Add the resolver in a new `factory/controlplane/` module
      returning one frozen object carrying `base_url`, its source, the
      credential's **variable name** and its source — and no credential value,
      so FR-003 and SC-005 hold by construction (plan route choices). Leave
      `factory/controlplane/__init__.py` at 0 bytes; an import there closes a
      cycle through `factory/controlplane/verify.py:29` that surfaces as an
      unrelated `ImportError` at worker start (plan trap 11).
- [ ] T011 [US1] Delegate the credential half from
      `LiteLLMClient.from_env` (`factory/usage/litellm_client.py:134-157`) to
      the resolver, preserving the raise-names-the-variable-only discipline at
      `:148-150` and the explicit `__repr__` at `:175-178` (FR-001, FR-003,
      plan trap 10). Do **not** rename `from_env`; state why in the commit
      message (plan route choices).
- [ ] T012 [US1] Route `_master_key_from_env`
      (`factory/activities/roadmap_activities.py:348-357`) through the same
      resolver, so the roadmap and an epic cannot disagree about which host
      they are on (FR-006).
- [ ] T013 [US1] Resolve the endpoint at all three CLI entry points before the
      workflow input is built — `factory/cli/nouns/build.py:371-378`,
      `factory/workgraph/cli.py:457-467` and `factory/cli/roadmap.py:203-206`
      (including the `--proxy-url` default at `:86`) — one resolver, no second
      copy of the precedence (FR-006). Nothing in `factory/workgraph/workflow.py`
      or `factory/roadmap/workflow.py` changes: the endpoint is already a
      declared input (`workflow.py:415`, `roadmap/workflow.py:211`), and no
      workflow-scoped function may read the environment or the disk (FR-007,
      plan trap 2, `tests/test_workflow_env_guard.py:227`).
- [ ] T014 [US1] Bind the config path explicitly in every test this story adds,
      via `ERGANE_CONFIG_PATH` on a `tmp_path` or an explicit argument; none may
      resolve the operator's real `~/.config/ergane/config.toml` (FR-012, plan
      trap 4).
- [ ] T015 [US1] Append the precedence entry to `docs/decisions.md`: the
      environment overrides the declaration, why (a change requiring this host
      to be re-provisioned to keep working is a failed change), and that
      inverting it once install is the normal path is a migration with its own
      story (spec US1-S9, FR-013). Take the next free number after the one your
      base contains; never renumber or edit an existing entry (plan trap 12).

## Phase 2: User Story 2 — A declaration the dispatch path cannot honour is refused where it is made

### Tests for this story (write FIRST, must fail)

- [ ] T016 [P] [US2] Write the parser refusal FIRST: a document declaring
      `llm.mode = "direct"` raises with a new stable rule slug whose message
      names dispatch's virtual-key requirement as the reason and `gateway` as
      the supported route (spec US2-S1, FR-008) — model it on
      `RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED`
      (`factory/controlplane/config.py:54`, raised at `:437-443`, plan trap 8)
      — must fail.
- [ ] T017 [P] [US2] Write the interview case: answering `direct` to the llm
      mode question re-asks carrying the parser's refusal, exactly as any other
      rejected value does through `_ask`
      (`factory/cli/install.py:381-422`, plan trap 9) (spec US2-S2, FR-009) —
      must fail.
- [ ] T018 [P] [US2] Write the pre-existing-config case: a config file on disk
      declaring `direct`, re-running `ergane install`, fails closed naming the
      file and the reason through `_starting_document`
      (`factory/cli/install.py:171-180`) rather than silently rewriting it
      (spec US2-S3) — must fail.
- [ ] T019 [P] [US2] Write the verification case: `ergane install --verify`
      against a `direct` config reports the parser's refusal and no check
      reports PASS (spec US2-S4, FR-010, SC-003) — this is the one that closes
      the inversion: today `direct` is the mode that verifies cleanest — must
      fail.
- [ ] T020 [US2] Write the structural case: an AST walk of
      `factory/controlplane/config.py`, `factory/cli/install.py` and
      `factory/controlplane/verify.py` finds no path that constructs, renders or
      probes a `direct` LLM block (spec US2-S5) — walk the AST, do not grep
      (043/US3 established the shape) — must fail.

### Implementation for this story

- [ ] T021 [US2] Refuse `direct` in `_read_llm`
      (`factory/controlplane/config.py:317-341`, direct branch at `:328-330`)
      with the new slug. Keep `"direct"` in `KNOWN_LL_MODES` (`:31`) so the
      refusal is specific rather than "unknown mode" (plan trap 8).
- [ ] T022 [US2] Remove the now-unreachable construction, seeding and rendering:
      `_read_direct_personas` (`config.py:344-395`), the persona rendering
      (`config.py:567`, `:583-597`, `:658-670`), `_PERSONA_SEED` and
      `_apply_llm_mode`'s direct arm (`factory/cli/install.py:83-88`, `:501-502`),
      the mode question's offer text (`:186`) and its branch (`:193-194`), and
      `_ask_personas` (`:214-249`) (FR-009).
- [ ] T023 [US2] Remove `LLMProbe`'s direct branch
      (`factory/controlplane/verify.py:182-197`, `:249-250`) and the already
      unreachable `raise` in `_llm_client_factory` (`:102-111`) (FR-010).
- [ ] T024 [US2] Flip, do not delete, the existing direct-mode cases in
      `tests/test_controlplane_config.py`, `tests/test_controlplane_verify.py`
      and `tests/test_ergane_install_walkthrough.py`: each becomes the refusal's
      test or is removed with the reason stated in the commit message (plan
      trap 7). Check the diff's running size against `DIFF_INPUT_LIMIT`
      (`factory/verify/diffbounds.py:38`) before committing; split the probe
      removal out rather than shipping a diff the judge refuses (plan trap 14).
- [ ] T025 [US2] Append the removal entry to `docs/decisions.md`: the
      alternative considered (make `direct` reach dispatch), why it was rejected
      (a second per-attempt attribution primitive, an epic that touches
      principle V), what a user who wanted `direct` is told, and the
      `temporal.mode = "managed"` precedent it follows (spec US2-S6, FR-014).
      Next free number after your base; never renumber (plan trap 12).

## Phase 3: User Story 3 — The operator can see which source won for each value

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US3] Write the declared-source case: with only the declared
      credential variable set, `ergane env --sources` names the config path as
      the endpoint's source and the declared variable as the credential's
      (spec US3-S1) — must fail.
- [ ] T027 [P] [US3] Write the override-source case: with both overrides set
      and a config declaring different values, the output names the environment
      variable as the winning source for both (spec US3-S2) — must fail.
- [ ] T028 [P] [US3] Write the sentinel case: a planted credential value
      appears nowhere in the captured output (spec US3-S3, FR-012, SC-005,
      plan trap 6) — must fail.
- [ ] T029 [P] [US3] Write the nothing-resolved case: no overrides, no config;
      both values report unresolved, both ways to satisfy each are named, and
      the exit code is zero because a report is not a gate (spec US3-S4) — must
      fail.
- [ ] T030 [P] [US3] Write the default-output case: bare `ergane env` renders
      byte-identically to today for every entry except that the two override
      variables no longer read `required` (spec US3-S5, FR-017) — assert
      byte-equality for the unchanged entries, not a spot check — must fail
      only on those two lines.

### Implementation for this story

- [ ] T031 [US3] Add the `--sources` mode to `factory/cli/env.py`, reporting
      the winning source and the alternative route per value from US1's
      resolution object (FR-011). `_SECRET_VARS` (`:27`) keeps the credential
      redacted; a config-declared variable *name* is not a secret and is
      printed, its value never is (FR-012).
- [ ] T032 [US3] Correct `_ENTRIES`' `required` labels for the two override
      variables (`factory/cli/env.py:33-34`) and change nothing else about the
      default rendering (FR-017, plan route choices).

## Phase 4: User Story 4 — Temporal connects to what was declared

### Tests for this story (write FIRST, must fail)

- [ ] T033 [P] [US4] Write the declared-only case: a fixture config declaring
      `temporal.address` and `temporal.namespace`, neither `TEMPORAL_ADDRESS`
      nor `TEMPORAL_NAMESPACE` set; both resolve from the config, each sourced
      to the config path (spec US4-S1, FR-015) — must fail.
- [ ] T034 [P] [US4] Write the override-wins case: the same config plus both
      variables set to *different* values; the environment wins for both and
      each source names its variable (spec US4-S2, plan traps 1 and 5) — must
      fail.
- [ ] T035 [US4] Write the probe-agreement case: a config declaring one address
      and `TEMPORAL_ADDRESS` set to another; the verify probe resolves the same
      target the operational path resolves (spec US4-S3, FR-016, SC-006, plan
      trap 13) — this is the story's reason to exist — must fail, because
      `verify.py:118-119` and `:308-309` are config-first today.
- [ ] T036 [P] [US4] Write the fallback case: neither config nor variable; the
      target is `DEFAULT_TEMPORAL_ADDRESS` / `DEFAULT_TEMPORAL_NAMESPACE`
      (`factory/notify/service.py:108`, `:111`) exactly as today, plus a test
      reading the diff for hardcoded `"localhost:7233"` / `"factory"` /
      `"TEMPORAL_ADDRESS"` literals at any connect site (spec US4-S4) — must
      fail on the four sites that carry literals today.
- [ ] T037 [P] [US4] Write the reporting case: `ergane env --sources` reports
      the winning source for the Temporal address and namespace alongside the
      LLM values (spec US4-S5) — must fail.

### Implementation for this story

- [ ] T038 [US4] Extend the resolver with a Temporal sibling of the same shape
      and the same precedence as US1's, carrying address, namespace and the
      source of each (FR-015).
- [ ] T039 [US4] Route the eight operational connect sites through it:
      `factory/worker.py:221-222`, `factory/cli/nouns/__init__.py:51-52`,
      `factory/cli/main.py:152-153`, `factory/cli/roadmap.py:183-184`,
      `factory/cli/repo.py:62-63`, `factory/workgraph/cli.py:778-779`,
      `factory/notify/service.py:678-679` and `factory/doctor/probes.py:483-484`
      — the last of which carries hardcoded literals rather than the constants
      (FR-015). The worker is the one that must keep connecting untouched
      (plan trap 1).
- [ ] T040 [US4] Flip `factory/controlplane/verify.py:118-119` and `:308-309`
      from config-first to the one precedence (FR-016, plan trap 13). Existing
      verify tests that assumed config-first will fail; those failures are the
      story working — flip them, do not delete them.
- [ ] T041 [US4] Report the Temporal values through `--sources`
      (`factory/cli/env.py`, FR-011's surface). Check the running diff size
      against `DIFF_INPUT_LIMIT` before committing; ten sites is thin per site
      and not thin in total (plan trap 14).

## Verification

- [ ] Final gate command passes green.
