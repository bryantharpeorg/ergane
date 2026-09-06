# Tasks: a subscription is a starting position

Read `plan.md` before starting. Trap 1 is the one that would waste a whole
story: spec 125 landed on 2026-09-01 and already put `CLAUDE_CODE_OAUTH_TOKEN`
into the agent environment, into the bwrap allowlist and into an expired-copy
refusal, and operator commit `c5890b2` already corrected `claude login` to
`claude auth login`. US1 is what 125 did not reach — one `if` on the
absent-file branch — and nothing more; trap 14 says where its shared constant
goes, because the module the strings sit in today already imports the adapter
and the reverse edge does not import, it crashes. Trap 4 is the opposite hazard
for US2: the registry cross-check cannot live in the document parser, because
`factory/controlplane/config.py:363` — `_read_llm` has no registry and no way
to get one; trap 17 is what US2's PASS hangs on. Traps 15 and 16 are US3's: the
mode question's text is pinned literally by two landed tests, and the `none`
path must skip the write-up loop as well as the two gateway passes. Trap 11 is
US4's: **four** live readers of the persona constant must move together or the
`KeyError` stays exactly where it is — and the fifth read, in an unreferenced
function, is not one of them. Traps 18 and 19 are the two landed facts
an earlier draft of this trio did not name: a test that pins `KNOWN_LL_MODES`
by exact equality, and a shipped registry of six gateway personas that makes a
fresh `none` install fail its own cross-check until US3 offers the conversion.
Trap 13 binds every phase: a subscription attempt already records no gateway
spend, and a diff here that edits the ledger's gateway path is out of scope for
all four stories.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the
judge sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A long-lived token is credential enough

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-002, trap 1) In a new
      `tests/test_112_us1_token_is_enough.py`: with `CLAUDE_CODE_OAUTH_TOKEN`
      set to a non-empty value and a scratch operator home containing none of
      the three searched files, assert a subscription-routed attempt raises no
      refusal and that walking the seeded per-node HOME yields no
      `.credentials.json` anywhere beneath it. Assert on the walked file list,
      not on one expected path — the claim is that no copy of the operator's
      login exists under that home at all.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, FR-004, trap 2) Paired-seeding test:
      one fixture with a real credentials file at the third search path, run
      twice — token set and token unset. Assert the token run writes no
      credentials file and the unset run writes today's copy at mode `0o600`.
      Both halves in one test: the unset half passes today, so only the pair can
      fail a diff that stopped copying in every case.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 3) Environment-invariant test:
      with the token set, assert the assembled agent environment carries
      `CLAUDE_CODE_OAUTH_TOKEN` and carries neither `ANTHROPIC_BASE_URL` nor
      `ANTHROPIC_AUTH_TOKEN`, and assert `PASSTHROUGH_ENV`
      (`factory/workgraph/adapter.py:104`) is still exactly
      `("PATH", "LANG", "TERM")`. 125's FR-012 requires that constant to survive
      every story; this is a regression pin, not new behaviour.
- [ ] T004 [P] [US1] (spec US1-S4, FR-005, trap 14) Refusal-text test: with
      neither a token nor any credentials file, import the shared remedy constant
      **from `factory/workgraph/adapter.py`** and assert every element of it is a
      substring of the raised `AdapterError`; in the same test assert the
      expired-copy refusal's rendered sentence is byte-identical to the string
      125 landed. Import the constant — do not retype the strings — so the test
      fails if the three operator surfaces ever diverge.
- [ ] T005 [US1] (FR-004, FR-005, trap 12) Amend
      `tests/test_subscription_credential.py:236` — `test_missing_subscription_credential_refused_before_fork`
      to state its new precondition (no token in the environment) rather than
      deleting it, and give the same treatment to the three tests in that module
      that assert the seeded copy exists —
      `tests/test_subscription_credential.py:173` — `test_subscription_home_carries_credential`,
      `tests/test_subscription_credential.py:291` — `test_moved_credential_is_still_seeded`
      and
      `tests/test_subscription_credential.py:358` — `test_credential_placement_is_a_distinct_copy`
      — each of which passes today only because no token happens to be exported
      (`grep -n CLAUDE_CODE_OAUTH_TOKEN tests/test_subscription_credential.py`
      returns nothing) and each of which FR-002 turns red on a host where one
      is. Add `monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)` to
      each, or one autouse fixture in that module, so the suite states its
      precondition rather than inheriting it from the host. Then confirm by
      running that `tests/test_us2_credential_expiry.py` still passes
      **unmodified** — that suite is what proves the expired refusal's
      re-render changed no bytes.

### Implementation for this story

- [ ] T006 [US1] (FR-005, trap 14) Define the two remedy strings once, as a
      module-level constant in `factory/workgraph/adapter.py`, beside the token
      constant at `factory/workgraph/adapter.py:114`. Render all three surfaces
      from it: the absent-credential refusal, the expired-copy refusal at
      `factory/workgraph/adapter.py:1096` — `ClaudeCodeAdapter.run_attempt`,
      and `factory/workgraph/credential_status.py:44` — `_credential_runway`,
      which imports it exactly as `factory/workgraph/credential_status.py:25`
      already imports the other six names. Do **not** put the constant in
      `credential_status.py` and import it back into the adapter: that edge is
      circular and fails at module load, on the import path every dispatched
      attempt takes.
- [ ] T007 [US1] (FR-001, FR-002, FR-003, FR-004, traps 1, 2, 3) In
      `factory/workgraph/adapter.py:1022` — `ClaudeCodeAdapter.run_attempt`:
      read the token once, before the credential branch; guard the absent-file
      refusal at
      `factory/workgraph/adapter.py:1073` — `ClaudeCodeAdapter.run_attempt` on
      it so the refusal fires only when neither form is available; and pass the
      decision, not just the path, into
      `factory/workgraph/adapter.py:896` — `_seed_node_home` at its one call
      site
      `factory/workgraph/adapter.py:1101` — `ClaudeCodeAdapter.run_attempt` so
      no credentials file is written when the token is the source. Reuse that
      same answer for the `credential_source` derivation at
      `factory/workgraph/adapter.py:1122` — `ClaudeCodeAdapter.run_attempt`
      rather than deriving it a second time. The expired-copy branch's
      *condition and outcome* are untouched; only its remedy sentence is
      re-rendered from T006's constant, byte-for-byte. Do not change
      `discover_subscription_credential`'s signature, `attempt_env` or the
      bwrap allowlist.

### Verification for this story

- [ ] T008 [US1] (spec US1-S1, spec US1-S2) Paste, as committed evidence: a
      recursive listing of a seeded per-node HOME under a token showing
      `.gitconfig` and no `.credentials.json`; the same listing without the token
      showing the 0600 copy; and the six suites named in trap 12 passing, with
      their totals — including spec 125's own
      `tests/test_us1_long_lived_token.py` and
      `tests/test_125_us3_credential_runway.py`, which are the two an
      implementer will not think to run.

## Phase 2: User Story 2 — No gateway is a declaration, not a failure

### Tests for this story (write FIRST, must fail)

- [ ] T009 [US2] (spec US2-S1, FR-006, trap 6) In a new
      `tests/test_112_us2_no_gateway_mode.py`: a config declaring
      `llm.mode = "none"` parses with no `base_url` and no `master_key_env` and
      carries a surrendered-properties text. Assert the text states that the
      credential is neither per-attempt nor isolated **and** that the
      persona-to-model binding is unenforceable — the two security halves — not
      merely that spend attribution is unavailable. Then add the source
      assertion US2-S1 actually asks for: read `factory/controlplane/config.py`
      as text and assert the `none` text's opening line occurs exactly once in
      it. Do not mirror
      `tests/test_controlplane_direct_mode.py:448` — `test_surrendered_properties_source_is_single_module_constant`;
      it asserts phrase presence and a three-bullet count and never counts
      definitions, which is weaker than this criterion.
- [ ] T010 [P] [US2] (spec US2-S2, FR-007, traps 4, 7) Cross-check refusal
      test: `llm.mode = "none"` with a registry containing at least one persona
      whose `factory/config.py:203` — `Persona.routes_through_gateway` is True
      yields a failing `llm` finding whose detail names that persona. Include
      one case where that persona carries neither a model nor a fallback, so
      the test pins that the FAIL is keyed on the persona property and not on
      an empty alias map. Drive the registry through
      `factory/controlplane/verify.py:149` — `_load_personas_for_probe`, the
      seam the existing probe tests already use.
- [ ] T011 [P] [US2] (spec US2-S3, FR-008, traps 5, 17) Declared-absent PASS
      test: `llm.mode = "none"` with an all-subscription registry yields a
      finding whose `passed` is True and whose detail states the surrender.
      Assert on the detail's content the way
      `factory/controlplane/verify.py:940` — `EscalationProbe.gather` is
      pinned; a PASS whose detail says only "skipped" must fail this test.
- [ ] T012 [P] [US2] (spec US2-S4, FR-010) Direct-mode finding test: verifying
      a `direct` config returns a finding and raises nothing. Today
      `factory/controlplane/verify.py:431` — `LLMProbe.gather` raises
      `AssertionError` before any snapshot is built.
- [ ] T013 [P] [US2] (spec US2-S5, FR-009, trap 5) Preserved-failure tests,
      three cases, each still failing: an empty alias set under a `gateway`
      declaration (`factory/controlplane/verify.py:447` — `LLMProbe.gather`),
      the `example/` placeholder registry
      (`factory/controlplane/verify.py:455` — `LLMProbe.gather`), and an unset
      master key (`factory/controlplane/verify.py:437` — `LLMProbe.gather`).
      This is the story's guard against widening FR-008 into "an empty alias
      set always passes".
- [ ] T014 [US2] (FR-006, trap 18) Amend, do not delete, the one landed
      assertion that pins the mode list by exact equality:
      `tests/test_controlplane_direct_mode.py:121` — `test_known_llm_modes_unchanged`
      asserts `KNOWN_LL_MODES == ("gateway", "direct")` under the docstring "The
      token list does not widen; 'direct' stays recognized". Restate the
      assertion to `("gateway", "direct", "none")` and restate the docstring with
      it; the pin is what stops the mode list widening again by accident, and
      deleting it removes a guard nobody replaced. Confirm by running that
      `tests/test_controlplane_config.py` and `tests/test_direct_mode_refused.py`
      still pass **unmodified** — the first iterates the tuple and the second
      asserts membership, so neither pins its length.

### Implementation for this story

- [ ] T015 [US2] (FR-006, trap 6) Add `"none"` to `KNOWN_LL_MODES`
      (`factory/controlplane/config.py:35`) and correct the stale comment above
      it that still calls `direct` refused; add an `LLMNone` frozen dataclass
      mirroring
      `factory/controlplane/config.py:134` — `ControlPlaneConfig.LLMDirect`, a
      field for it on
      `factory/controlplane/config.py:147` — `ControlPlaneConfig.LLM`, a
      surrender text beside `factory/controlplane/config.py:350`, and the
      `none` branch in `factory/controlplane/config.py:363` — `_read_llm`.
- [ ] T016 [US2] (FR-007, FR-008, FR-009, FR-010, traps 4, 5, 7, 17) In
      `factory/controlplane/verify.py:428` — `LLMProbe.gather`: delete the
      assertion at `factory/controlplane/verify.py:431` — `LLMProbe.gather` and
      the comment above it; add the `none` branch that reads the registry
      through the existing seam, returns a failing snapshot naming every
      persona whose `routes_through_gateway` is True, and otherwise returns a
      passing declared-absent snapshot; add the `direct` branch that returns a
      snapshot describing what direct mode cannot verify. Add the declaration
      field to
      `factory/controlplane/verify.py:70` — `LLMSnapshot` **with a default**, so
      the five constructors in that module and the two outside it
      (`tests/test_ergane_install_personas.py:103` and
      `tests/_us4_outputs/generate_interview_evidence.py:236`) need no edit for a
      requirement this story does not have; and one branch on it at the head of
      `factory/controlplane/verify.py:665` — `LLMProbe.evaluate`, shaped like
      `factory/controlplane/verify.py:915` — `TelemetryProbe.evaluate` and
      `factory/controlplane/verify.py:984` — `EscalationProbe.evaluate`:
      without it a `none` snapshot has no results and fails whatever `gather`
      wrote. Leave `evaluate`'s existing verdict untouched for every case it
      already decides.

### Verification for this story

- [ ] T017 [US2] (spec US2-S3, spec US2-S5) Paste, as committed evidence: the
      `[PASS] llm:` line from a no-gateway verify with its surrender detail; the
      failing line from the same config with one gateway persona restored; the
      `direct`-mode finding line; and the three preserved-failure results, all
      four as rendered findings rather than described.

## Phase 3: User Story 3 — The interview can produce that position

### Tests for this story (write FIRST, must fail)

- [ ] T018 [US3] (spec US3-S1, FR-011, traps 8, 9) In a new
      `tests/test_112_us3_install_no_gateway.py`: drive
      `factory/cli/install.py:1545` — `_ask_llm` with a scripted prompter
      answering `none` and capture stdout. Assert the returned document
      declares `llm.mode = "none"` with no `base_url` and no `master_key_env`,
      that the captured output contains the FR-006 surrender text, and that the
      prompter's recorded question list carries no further `llm` question. All
      three in one test.
- [ ] T019 [P] [US3] (spec US3-S2, FR-011, trap 15) Offered-choices test: with
      a scan result that is absent or unreachable, assert the choices string
      composed by `factory/cli/install.py:2149` — `_offered_llm_mode` names
      `none` alongside today's default. That is the branch at
      `factory/cli/install.py:2168` — `_offered_llm_mode`, and it is the branch
      the two landed assertions T023 amends run through.
- [ ] T020 [P] [US3] (spec US3-S3, FR-012, traps 10, 16) No-gateway
      persona-interview test: drive
      `factory/cli/install.py:567` — `_interview_personas` with a `none`-mode
      document, a registry of subscription personas, and alias-fetch and probe
      seams that **raise if called**. Assert the interview completes, neither
      seam was called, each subscription persona's model was confirmed through
      the prompter, and
      `factory/controlplane/verify.py:400` — `gather_gateway_aliases` over the
      written registry returns empty. Today this raises `KeyError` at
      `factory/cli/install.py:578` — `_interview_personas`, and a fix that
      guards only that line raises it again at
      `factory/cli/install.py:683` — `_interview_personas`.
- [ ] T021 [P] [US3] (spec US3-S4, FR-013) Paired gateway/none test: one scripted
      interview body run twice. Assert that every recorded question of the
      gateway run *after* the mode question — text, position and default — and
      both files it wrote match a fixture committed with this story, and that the
      none run writes `mode = "none"` and asks no gateway question. Exclude the
      mode question's own offered-choices string from the comparison and only
      that, because FR-011 changes it; record the post-change string in the
      fixture. The gateway half alone passes today, so only the pair can fail a
      diff that disturbed the gateway path.
- [ ] T022 [P] [US3] (spec US3-S5, FR-017, trap 19) Conversion-offer test, in
      the module T018 creates: drive
      `factory/cli/install.py:567` — `_interview_personas` with a `none`-mode
      document over the registry
      `factory/config.py:60` — `shipped_registry_text` seeds, answering yes for
      five of its six `agent: claude-code` personas and no for the sixth. Assert
      the written file carries `agent: subscription`, the prompted model name and
      `fallback: null` for the five; is byte-identical to the seeded text for the
      sixth; and that
      `factory/controlplane/verify.py:400` — `gather_gateway_aliases` over it
      returns aliases for the declined persona and no others. Today
      `factory/cli/install.py:409` — `_update_persona_lines` cannot write an
      `agent:` line at all, so no diff that leaves it alone can pass this.
- [ ] T023 [US3] (spec US3-S2, FR-013, trap 15) Amend, do not delete, the two
      landed assertions that pin the old mode-question string to the new one:
      `tests/test_install_mode_routing.py:292` — `test_empty_scan_falls_back_to_todays_question`
      (`prompter.defaults_for("llm mode (gateway)")`, driven through the
      no-usable-scan branch by an empty scan result) and
      `tests/test_ergane_install_walkthrough.py:635` — `test_the_real_terminal_prompter_drives_the_interview`
      (`"llm mode (gateway) [gateway]" in result.stdout`, with
      `_scan_endpoints` stubbed at
      `tests/test_ergane_install_walkthrough.py:619` — `test_the_real_terminal_prompter_drives_the_interview`).
      State the new offered-choices string in each; the pin is what stops a
      later diff from changing the question by accident.

### Implementation for this story

- [ ] T024 [US3] (FR-011, traps 8, 9, 15) Add a `none` seed beside
      `factory/cli/install.py:266` carrying nothing but the mode, a `none`
      branch in `factory/cli/install.py:2035` — `_apply_llm_mode` that uses it,
      the `none` branch in `_ask_llm` that prints the FR-006 constant and asks
      no follow-up, and `none` in the choices returned by
      `factory/cli/install.py:2168` — `_offered_llm_mode` when the scan found
      nothing usable. Import the text from `factory/controlplane/config.py`
      exactly as `factory/cli/install.py:52` already imports the `direct` one.
- [ ] T025 [US3] (FR-012, FR-013, traps 10, 16) In
      `factory/cli/install.py:567` — `_interview_personas`, take the no-gateway
      path before `factory/cli/install.py:578` — `_interview_personas` reads
      `base_url`: no gateway fields read, no aliases fetched, no alias probed,
      and **both** the two gateway passes at
      `factory/cli/install.py:599` — `_interview_personas` and
      `factory/cli/install.py:640` — `_interview_personas` **and** the write-up
      loop at `factory/cli/install.py:683` — `_interview_personas` skipped —
      that loop indexes `chosen_primary`, which is empty here, and would raise
      the same `KeyError` this story removes. Run the subscription loop at
      `factory/cli/install.py:670` — `_interview_personas` and write
      `subscription_updates` alone. Leave the gateway path's questions and
      their order untouched.
- [ ] T026 [US3] (FR-017, FR-013, trap 19) On the no-gateway path only, walk the
      resolved registry's own membership filtered by
      `factory/config.py:203` — `Persona.routes_through_gateway`, offer each such
      persona as a conversion, and fold every accepted one into the same updates
      mapping the subscription loop fills — `agent`, the confirmed model and
      `fallback: null` per accepted persona, nothing at all per declined one.
      Widen `factory/cli/install.py:409` — `_update_persona_lines` to rewrite an
      `agent:` line when one is supplied, leaving its `model`/`fallback`
      behaviour and its `_scalar` rendering exactly as they are so a gateway run
      writes byte-for-byte what it writes today (FR-013). Do not reach for
      `_GATEWAY_PERSONA_ORDER` for the membership here: US4 has not landed, and
      that constant is the bug this story must not inherit.

### Verification for this story

- [ ] T027 [US3] (spec US3-S1, spec US3-S3, spec US3-S5) Paste, as committed
      evidence: the
      scripted no-gateway interview transcript showing the surrender text and the
      absence of any gateway question; the `config.toml` and the `personas.yaml`
      it wrote, with the `agent:`, `model:` and `fallback:` lines of every
      converted persona and of the one declined; and the gateway run's transcript
      beside them for comparison.

## Phase 4: User Story 4 — The persona questions come from the registry, not a constant

### Tests for this story (write FIRST, must fail)

- [ ] T028 [US4] (spec US4-S1, FR-014, trap 11) In a new
      `tests/test_112_us4_persona_membership.py`: drive
      `factory/cli/install.py:567` — `_interview_personas` against a registry
      naming five gateway personas and assert all five are asked and no
      `KeyError` is raised. Assert on the recorded question sequence, so a fix
      that silently skipped a persona fails too.
- [ ] T029 [P] [US4] (spec US4-S2, FR-014, FR-015, trap 11) Seven-persona test:
      two of the names absent from `factory/cli/install.py:471`. Assert the
      exact recorded sequence — the five known names first in the constant's
      order, then the two unknown names in registry order — so question order
      stays declared rather than becoming dict-iteration order. Drive it far
      enough that both `tried_aliases[name]` lookups at
      `factory/cli/install.py:616` — `_interview_personas` and
      `factory/cli/install.py:653` — `_interview_personas` run for an unknown
      name, which is where a three-of-four fix raises `KeyError`.
- [ ] T030 [P] [US4] (spec US4-S3, FR-016) Shipped-six control: a registry naming
      exactly the six produces the same recorded question sequence and the same
      written registry as the fixture committed with US3-S4. In the same module
      as T028, so a derivation that reordered the shipped six fails here. This is
      a regression pin on today's behaviour.

### Implementation for this story

- [ ] T031 [US4] (FR-014, FR-015, FR-016, trap 11) Add one derivation that
      takes the resolved registry, filters on
      `factory/config.py:203` — `Persona.routes_through_gateway`, and orders
      the result by `_GATEWAY_PERSONA_ORDER` with unknown names appended in
      registry order. Move all **four** live readers onto it:
      `factory/cli/install.py:596` — `_interview_personas` (the dict
      comprehension that seeds `tried_aliases`, whose keys are indexed
      unguarded at `factory/cli/install.py:616` — `_interview_personas` and
      `factory/cli/install.py:653` — `_interview_personas`),
      `factory/cli/install.py:599` — `_interview_personas`,
      `factory/cli/install.py:640` — `_interview_personas` and
      `factory/cli/install.py:683` — `_interview_personas`. Keep the constant;
      it is the sort key, not the membership. Leave
      `factory/cli/install.py:516` — `_ask_persona_alias` alone: it reads the
      constant too, but `grep -rn _ask_persona_alias factory/ tests/ scripts/`
      returns only its own definition at
      `factory/cli/install.py:498` — `_ask_persona_alias`, so it receives no
      registry, has no caller and cannot raise the `KeyError`. Changing it
      proves nothing and changes no behaviour.

### Verification for this story

- [ ] T032 [US4] (spec US4-S1, spec US4-S2) Paste, as committed evidence: the
      recorded question sequences for the five-, seven- and six-persona
      registries side by side, and `tests/test_ergane_install_personas.py`
      passing with its totals.

## Verification

- [ ] T033 The full gate command passes green.
- [ ] T034 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end, beginning with step 0 — re-deriving the stale
      `workgraph.json` beside this spec and confirming four nodes carrying
      FR-001…FR-017 before any dispatch. Step 7 — dispatching one real story from
      a no-gateway install — is the falsifiable test of this whole spec, because
      everything before it proves only that a declaration parses.
