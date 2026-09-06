---
state: draft
fixes:
  - install/subscription-only-operator-cannot-verify-green
  - verify/direct-mode-config-raises-instead-of-reporting
# DRAFTED 2026-08-27 by the operator session, against ergane-buildout at 3e5c940.
# Every file:line below was read from that commit and verified before drafting.
#
# WHY THIS EXISTS. The question that produced this spec was asked plainly: "what
# if all they have to start is a Claude Code subscription?" The answer, measured
# the same afternoon, is that Ergane can dispatch on one but cannot be installed
# for one — and that `docs/onramp.html` and `README.md` both tell such a reader,
# in their first substantive paragraph, that a database-backed LiteLLM gateway is
# the prerequisite. They close the tab, and they are not wrong to.
#
# THE ROUTE ALREADY EXISTS AND THIS FLOOR RUNS ON IT. `agent: subscription` is a
# real sentinel (`factory/config.py:145-149`), and two personas in this
# repository's own `personas.yaml` declare it. For those personas
# `routes_through_gateway` is False (`config.py:203-208`), no virtual key is
# minted (`needs_virtual_key`, `:210-216`), the adapter hands the child neither
# ANTHROPIC_BASE_URL nor ANTHROPIC_AUTH_TOKEN, and `discover_subscription_credential`
# (`factory/workgraph/adapter.py:797-830`) finds the operator's own login. The
# 2026-08-22 floor — four epics, 15 stories, 88% first-try — was built this way
# at zero per-token cost.
#
# WHAT IS MEASURED, AND WHAT BLOCKS A SUBSCRIPTION-ONLY OPERATOR (2026-08-27):
#   1. `discover_subscription_credential` searches exactly three FILE paths —
#      $XDG_CONFIG_HOME/claude/.credentials.json, ~/.config/claude/…, and
#      ~/.claude/… — and no environment variable. Its `environ` parameter
#      resolves XDG_CONFIG_HOME only. `grep -rn CLAUDE_CODE_OAUTH_TOKEN factory/`
#      returns nothing. Claude Code 2.1.223 ships `claude setup-token` ("Set up a
#      long-lived authentication token (requires Claude subscription)"), which is
#      the headless credential every comparable tool consumes. Ergane cannot.
#   2. `_seed_node_home` (`adapter.py:833-867`) COPIES the operator's credential
#      file into every per-node HOME. Its own docstring (`:846-850`) records the
#      hazard as unmeasured: "if rotation-on-use is the provider's behaviour… the
#      operator's own host login may be invalidated when the first node
#      refreshes."
#   3. The `llm` block is mandatory (`_expect_block(document, "llm", …)`,
#      `factory/controlplane/config.py:364`) and `KNOWN_LL_MODES` is
#      `("gateway", "direct")` (`:35`). There is no way to declare "no gateway".
#   4. `LLMProbe.evaluate` (`factory/controlplane/verify.py:648-656`) computes
#      `passed = bool(snapshot.results) and all(...)`. A registry whose personas
#      are all subscription yields zero aliases, so `gather` returns "no
#      dispatchable model aliases in the persona registry" (`:433-439`) and the
#      probe FAILS. The comment above it is explicit that this is deliberate:
#      "That is a failure, not a vacuous pass." Correct for an unconfigured
#      registry; wrong for a declared position.
#   5. `_GATEWAY_PERSONA_ORDER` (`factory/cli/install.py:471-478`) hard-codes all
#      six personas as gateway personas for discovery and probing. The interview's
#      subscription branch (`:668-679`) only asks the model name for personas that
#      ALREADY declare `agent: subscription`. Nothing offers to make one.
#   6. A latent crash: `LLMProbe.gather` asserts `config.llm.gateway is not None`
#      under the comment "`gateway` is the only mode a parsed config can carry
#      (048-US2)" (`verify.py:415-417`) — but `_read_llm` returns a populated
#      direct-mode config at `config.py:374-384`. `ergane install --verify` on a
#      direct config raises AssertionError instead of producing a finding.
#
# THE POSITION THIS SPEC TAKES, AND WHY IT IS NOT A HOLE. Recalled and
# load-bearing: the gateway does three jobs, not one. It delivers the agent's
# credential so a sandboxed agent never holds the operator's real key; it makes
# persona->model routing enforceable, because the minted key's model list derives
# from the registry; and it attributes spend. Only the third is bookkeeping.
# Dropping the gateway surrenders two SECURITY properties and one accounting one.
# Spec 055 already made that a declared choice rather than a silent default, and
# `DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT` (`config.py:350-360`) is the shape
# that choice takes today. This spec adds a third declared position in exactly
# that shape — never a mode that quietly works, always one that says what it
# costs before it is chosen.
#
# THE PRECEDENT THE DESIGN COPIES. Three control-plane subsystems already have a
# declared-absent form, and their verify output says so in the operator's own
# words. From the 2026-08-27 demo transcript, verbatim:
#     [PASS] memory: skipped by declaration: memory.backend is `none`
#     [PASS] telemetry: skipped by declaration: telemetry has no otlp_endpoint
#     [PASS] escalation: escalations will be dropped: escalation.adapter is
#            `none`; a node that would have asked a question fails instead of
#            waiting
# The third is the model: it passes, and it names the consequence in the same
# breath. `llm.mode = "none"` joins that family.
#
# NOT IN SCOPE. This spec does not make a subscription the default, does not
# change what a gateway persona does, and does not touch spend attribution for
# gateway-routed attempts. It does not add a second credential discovery order
# for gateway mode. And it does not make `ergane usage` invent figures it cannot
# read: a subscription-routed attempt has no per-key spend, which is already true
# today (`usage_activities.py:517-535`) and stays true.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c.
#
# SPEC 125 LANDED ON US1'S CODE AND TOOK MOST OF IT, WHICH WAS THE EXPENSIVE
# FIND. `125-a-credential-outlives-the-night` landed three stories on 2026-09-01
# (ed9aa51, 8d71de4, 01bb717) and did what measurement 1 above asked for:
# `CLAUDE_CODE_OAUTH_TOKEN` is now a named constant, it is carried into the
# subscription branch of the agent environment, it survives bwrap's `--clearenv`,
# and a whole new module — `factory/workgraph/credential_status.py` — reports
# which credential source is in use. Measurement 1's claim that the grep "returns
# nothing" is dead. So is FR-005's old premise: `claude login` was corrected to
# `claude auth login` by operator commit c5890b2 on 2026-08-28.
#
# WHAT 125 DID NOT REACH, AND IT IS THE WHOLE SUBSCRIPTION-ONLY CASE. The
# dispatch-time refusal still demands a credentials FILE before any token is
# consulted: `factory/workgraph/adapter.py:1073` raises when
# `discover_subscription_credential()` returns None, unconditionally, and the
# environment that would have carried the token is not assembled until
# `factory/workgraph/adapter.py:1113`. 125 added the token guard to the
# EXPIRED-file branch (`factory/workgraph/adapter.py:1085-1088`)
# and not to the ABSENT-file branch. An operator holding a long-lived token and
# no file — exactly the person this spec is for, and exactly a container — cannot
# dispatch a subscription-routed attempt at all. US1 is rewritten to that one gap
# and is now much smaller than it was.
#
# TWO LEDGER KEYS DECLARED, BOTH WHOLE, BOTH NAMING THIS SPEC ALREADY.
# `install/subscription-only-operator-cannot-verify-green` names four halves in
# its notes — the probe's permanent FAIL, the unstateable mode, the hard-coded
# persona list, and the unconsumed token — and US2, US3, US4 and US1 own them one
# each. `verify/direct-mode-config-raises-instead-of-reporting` is one mechanism
# and US2's FR-010 is it; the crash was re-confirmed live at 602a92c by
# constructing a direct config and calling the probe (AssertionError raised).
# Neither key is a name to build from: both were read for their notes.
#
# US3 SPLIT, AND US4 IS THE NEW NUMBER. The old US3 asked one node to add an
# interview answer, restructure a gateway-coupled 130-line function AND change
# where the persona list comes from, all inside `factory/cli/install.py`. The
# membership change is the half with the widest blast radius on the existing
# install suite, so it is now US4. No existing story number moved.
#
# THE PLAN WAS WRONG ABOUT WHERE FR-007 LIVES. It said the registry cross-check
# "belongs with the other control-plane refusals … at parse or verify time".
# `factory/controlplane/config.py:363` — `_read_llm` takes `(document, source)`
# and can no more see `personas.yaml` than it can see the network; only the probe
# holds a registry seam. An implementer obeying the old sentence would have
# reached for a registry from inside a pure document parser. FR-007 now names the
# probe's seam.
#
# US3's OLD S1 ASKED FOR AN ORDERING THE TREE DOES NOT HAVE. It required the
# surrender text "printed before the answer is accepted — the same ordering
# `direct` already uses". `direct` does not do that: the mode answer is accepted
# by `_ask` first and the text prints after, before the mode's follow-up
# questions. `none` has no follow-up questions at all, so the old wording was
# unsatisfiable. US3-S1 is now three assertions over the returned document, the
# captured output and the prompter's own record.
#
# ANCHORS. Every citation in all three files was bare-filename (`adapter.py:833`)
# and validate refused forty of them. All are now repository-relative, and every
# one that means a Python definition is written in the symbol-tier form so the
# next drift is machine-caught rather than re-discovered by hand. Six anchors had
# also MOVED: `discover_subscription_credential` 797→840, `_seed_node_home`
# 833→896, the dispatch refusal 1002→1073, `gather_gateway_aliases` 386→400,
# `LLMProbe.gather`'s assertion 415→431, `LLMProbe.evaluate` 648→662.
#
# THE COMPILED ARTIFACT BESIDE THIS FILE IS STALE AND MUST BE CLEARED BEFORE
# DISPATCH. `workgraph.json` in this directory was derived when every story's
# `implements` was `[]`, so each node's `requirement_keys` is the bare story key
# and there is no `us4` node at all. `ergane build start` reads a compiled graph
# off disk, and those requirement keys are what select the criteria the judge
# scores against — dispatching from that file would hand three nodes a criteria
# set that names no FR and drop US4 entirely. This refinement is not permitted to
# write or delete that artifact: the operator re-derives it and confirms four
# nodes carrying FR-001…FR-016.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), same tree, same sha 602a92c.
# US3 changed a prompt string two landed tests pin literally and declared neither:
# `tests/test_install_mode_routing.py:292` and
# `tests/test_ergane_install_walkthrough.py:635` both assert the exact text
# `llm mode (gateway)`, which FR-011 turns into `llm mode (gateway|none)`; both are
# now named in US3's sizing and amended by a task in T005's shape.
# FR-013 and US3-S4 pinned that same string as unchangeable while FR-011 required it
# to change — an unsatisfiable pair, because both recording prompters in this tree
# record the prompt STRING (`tests/test_ergane_install_walkthrough.py:290` —
# `Asked`, `tests/test_ergane_install_personas.py:372` — `_RecordingFilePrompter`).
# FR-013 now exempts the mode question's own offered-choices string and pins the
# follow-ups, their order, their defaults and the two written files.
# FR-005 and T006 never said which module holds the shared remedy constant, and the
# only reading their words supported — where the strings sit today — is a circular
# import: `factory/workgraph/credential_status.py:25` imports six names FROM the
# adapter and the adapter imports nothing back. The constant is now named as living
# in `factory/workgraph/adapter.py`, and FR-005 is widened to the third surface, the
# expired-copy refusal, whose rendered text must stay byte-identical.
# `_GATEWAY_PERSONA_ORDER` has FIVE readers, not the four trap 11 enumerated:
# `factory/cli/install.py:596` builds `tried_aliases` from it and
# `factory/cli/install.py:616` and `factory/cli/install.py:653` index it, so leaving
# it behind reproduces the exact `KeyError` the trap exists to prevent.
# FR-008's antecedent keyed on an empty alias map, which OVERLAPS FR-007 — a gateway
# persona carrying no model and no fallback contributes no alias, so the same input
# was required to fail and to pass. It is now the exact complement of FR-007.
# Three smaller instruction errors corrected: T022 sent the `none` path "straight to
# the subscription loop and the write", but the write-up loop at
# `factory/cli/install.py:683` indexes `chosen_primary` over the six-name constant
# and raises the very `KeyError` US3 removes; T015 and US2's sizing declared no
# snapshot discriminator and no `LLMProbe.evaluate` branch, without which FR-008's
# PASS is unreachable; and trap 6 claimed the existing suite pins the direct text to
# exactly one definition, which
# `tests/test_controlplane_direct_mode.py:448` —
# `test_surrendered_properties_source_is_single_module_constant` does not do.
# The stale `workgraph.json` is now a numbered operator step in plan.md, not only a
# note here. DECLINED: rewriting the module-level constant citations
# (`PASSTHROUGH_ENV`, `KNOWN_LL_MODES`, `_GATEWAY_PERSONA_ORDER`,
# `DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT`, `_DIRECT_SEED`) into symbol-tier form.
# `factory/cli/nouns/spec.py:825` — `_symbol_spans` builds its span map from
# `FunctionDef`, `AsyncFunctionDef` and `ClassDef` nodes only, so a constant written
# that way is reported absent and REFUSES a draft spec. Every citation naming a
# function or class already carries the symbol form; one that did not,
# `factory/controlplane/config.py:363` — `_read_llm`, now does.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): second pass, answering an
# adversarial review of the entry above. Same tree, same sha 602a92c; every
# claim below was re-derived by reading the code rather than by trusting the
# report.
# WHERE THIS CAME FROM. Two blocking defects and six smaller ones. Both
# blocking ones were the same shape: a landed fact the trio did not name.
# WHAT IT COST, MEASURED. (1) FR-006 widens `KNOWN_LL_MODES`, and
# `tests/test_controlplane_direct_mode.py:121` —
# `test_known_llm_modes_unchanged` asserts that tuple by exact equality under
# the docstring "The token list does not widen; 'direct' stays recognized". No
# trap, task or sizing paragraph named it, while the identical hazard WAS named
# and handled for US3 — so US2's first production edit met a red landed test
# whose own name reads as a prohibition, and the cheap wrong move is to delete
# the pin nobody replaced. Trap 18 names it, FR-006 requires it restated to
# `("gateway", "direct", "none")`, US2's sizing carries the file and T014
# amends it. The rest of the sweep clears: `tests/test_controlplane_config.py:395`
# iterates the tuple and `tests/test_direct_mode_refused.py:148` asserts
# membership, so both survive the widening and 121 is the only breakage.
# (2) The declared row's own clause — "the interview's subscription branch only
# asks the model name for personas that ALREADY declare agent: subscription" —
# was owned by no FR, and the tree makes it load-bearing.
# `factory/cli/install.py:1118` — `_seed_personas_registry` copies
# `factory/config.py:60` — `shipped_registry_text`, i.e. `personas.example.yaml`,
# whose architect, implementer, judge, closer, debugger and researcher all
# declare `agent: claude-code`. A fresh install answering `none` would therefore
# have FAILED its own FR-007 on six personas, and this spec's headline promise —
# declare, install into, verify green, dispatch — would have been unreachable
# without a hand-edit no file named. FR-017 and US3-S5 now own that clause: in
# `none` mode the interview offers to record each gateway-routed persona as
# `agent: subscription`, which means widening
# `factory/cli/install.py:409` — `_update_persona_lines` past `model` and
# `fallback`. Trap 19 is the reproduction.
# NOT FIXED HERE, NAMED SO THE KEY IS NOT READ AS WHOLE. The same row's fourth
# half — "credentials are file-copied per node with a rotation hazard the code
# records as unmeasured" — survives on the no-token path: FR-002 removes the
# copy only where the token is the credential source, and FR-004 deliberately
# keeps today's 0o600 copy otherwise. That residue is now stated in
# "### What this spec is not" as well as here.
# SIX SMALLER CORRECTIONS. Trap 12 and T008 listed four subscription suites and
# omitted spec 125's own two on the very code US1 edits —
# `tests/test_us1_long_lived_token.py`, which holds
# `test_token_wins_and_record_states_source`, the landed pin that must stay
# green after FR-002 stops the copy, and `tests/test_125_us3_credential_runway.py`;
# both were read (neither breaks) and both are now named. The plan's US4 sizing
# said four call sites where trap 11, T031 and the entry above all say five.
# `factory/cli/install.py:2197` — `_offered_llm_mode` is a third reader of
# `KNOWN_LL_MODES` that inherits `none` for free once the tuple widens, now
# named so it is not mistaken for a second place to edit. Trap 15 now says the
# new offer is confined to the no-usable-scan branch BECAUSE
# `tests/test_install_mode_routing.py:186`,
# `tests/test_install_mode_routing.py:218` and
# `tests/test_install_mode_routing.py:321` pin the other two branches' strings.
# T016 now requires the new snapshot field to carry a default, because
# `factory/controlplane/verify.py:70` — `LLMSnapshot` is constructed at five
# sites in that module and two outside it. And every statement anchor sitting
# inside a function now carries the symbol-tier form, so the next drift is
# machine-caught; the module-constant citations stay bare for the reason the
# DECLINED paragraph above records.
# ONE NEIGHBOUR THE ENTRY ABOVE DID NOT ACCOUNT FOR. `5f2208d`
# (095-the-ladder-charges-only-the-story/US1, 2026-08-30) landed inside
# `ClaudeCodeAdapter.run_attempt` — `PRE_AGENT_WINDOW_S`, `session_transcript`,
# `_failure_class` and an `agent_took_a_turn=` argument to the monitor call,
# about ten lines below the credential branch US1 guards. Read in full: it moves
# lines and changes no mechanism this spec depends on. Recorded so the next
# reader does not re-derive it.
# TASK IDS SHIFTED BY THE THREE TASKS THIS PASS INSERTED. The entry above's T022
# is now T024 and its T015 is now T016; T005, T006 and T008 did not move. Read a
# task id in an earlier entry against the numbering of the day it was written.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): third pass, answering a second
# adversarial review of the two entries above. Same tree, same sha 602a92c;
# every claim below was re-derived by reading the code rather than by trusting
# the report.
# WHERE THIS CAME FROM. One blocking defect and six smaller ones. The blocking
# one is arithmetic both earlier passes got wrong and the second reinforced, so
# it was never going to self-correct.
# WHAT IT COST, MEASURED. `_GATEWAY_PERSONA_ORDER` has FOUR live readers, not
# five. `grep -rn _ask_persona_alias factory/ tests/ scripts/` returns exactly
# one line — the function's own definition at
# `factory/cli/install.py:498` — `_ask_persona_alias` — so the read at
# `factory/cli/install.py:516` — `_ask_persona_alias` sits in unreferenced code
# that is handed no registry and cannot raise the `KeyError` trap 11 exists to
# prevent. The entry above ("`_GATEWAY_PERSONA_ORDER` has FIVE readers, not the
# four trap 11 enumerated") and the one after it ("the plan's US4 sizing said
# four call sites where trap 11, T031 and the entry above all say five") are both
# wrong on that count; provenance is append-only, so they stand and this line is
# the correction. The live readers are
# `factory/cli/install.py:596` — `_interview_personas` (the `tried_aliases`
# comprehension, whose keys are indexed unguarded at 616 and 653),
# `factory/cli/install.py:599` — `_interview_personas`,
# `factory/cli/install.py:640` — `_interview_personas` and
# `factory/cli/install.py:683` — `_interview_personas`; the arithmetic an
# implementer needs is "three of four leaves the KeyError", and 516 is now one
# sentence in trap 11, in US4's sizing and in T031 saying US4 may leave it alone.
# Told five, an implementer either hunts a `KeyError` that their own fix already
# removed or changes a dead function's signature to make a count come out right.
# SIX SMALLER CORRECTIONS, ONE OF THEM A RESIDUE NAMED RATHER THAN FIXED.
# (1) `tests/test_subscription_credential.py` never mentions
# `CLAUDE_CODE_OAUTH_TOKEN`, and three of its landed tests assert the seeded copy
# EXISTS —
# `tests/test_subscription_credential.py:173` — `test_subscription_home_carries_credential`,
# `tests/test_subscription_credential.py:291` — `test_moved_credential_is_still_seeded`
# and
# `tests/test_subscription_credential.py:358` — `test_credential_placement_is_a_distinct_copy`
# — so after FR-002 all three are green only on a host with no token exported and
# red on the host plan.md's operator step 1 describes. Trap 12 names all three
# and T005 requires the `monkeypatch.delenv` that states the precondition
# instead of inheriting it from whatever the host exports.
# (2) The declared row `install/subscription-only-operator-cannot-verify-green`
# carries a fourth clause in its notes — "credentials are file-copied per node
# with a rotation hazard the code records as unmeasured" — which FR-004
# deliberately preserves on the no-token path. The key stays declared, because
# the row's summary and its other three halves are owned outright; new operator
# step 8 files the successor finding before the next
# `ergane findings triage --apply`, so the surviving half keeps being counted
# rather than closed by this spec's own `fixes:` line.
# (3) Two neighbours the entries above did not account for. `5345044` and
# `eda14ed` (111-the-demo-sandbox-starts-or-says-why US1/US2, 2026-08-29) landed
# on `factory/controlplane/verify.py` and `factory/workgraph/adapter.py`, this
# spec's two central files. Read in full: 5345044 wires
# `_build_bwrap_remedy`/`sandbox_remedy` into `_inspect_host`; eda14ed rewrites
# two bwrap path-pin comments. Neither touches `LLMProbe`, `_read_llm`, the
# credential branch or `_seed_node_home` — line movers only, recorded so the
# sweep is not re-derived a third time.
# (4) The dispatch truth table's third row said `unchanged` for a token-set,
# expired-file input whose copy FR-002 in fact stops:
# `factory/workgraph/adapter.py:1101` — `ClaudeCodeAdapter.run_attempt` seeds the
# home unconditionally on the path, and `credential_source` at
# `factory/workgraph/adapter.py:1122` — `ClaudeCodeAdapter.run_attempt` resolves
# to the token on that input. The row now reads "proceeds on the token; nothing
# copied", which is what FR-002 and FR-004 already said between them. The FRs
# were consistent; only the table disagreed with them.
# (5) The `workgraph.json` paragraph in the REFINED entry above says the
# re-derivation check is FR-001…FR-016. FR-017 was added by the entry after it,
# so the check is FR-001…FR-017, exactly as plan.md's operator step 0 and T034
# state. Read an FR range in an earlier entry against the numbering of the day it
# was written.
# (6) Trap 13 was written after trap 19, at the end of plan.md's Traps section,
# which reads as a deleted trap. It is back in numeric order between traps 12 and
# 14. Nothing was renumbered, so every trap number tasks.md cites still means
# what it meant.
---

# Feature Specification: a subscription is a starting position

**Created**: 2026-08-27
**Depends on**: nothing landed-but-unmerged. Spec 125 landed 2026-09-01 and is
assumed throughout: it is what put `CLAUDE_CODE_OAUTH_TOKEN` into the agent's
environment. US1 is independent; US2 → US3 → US4 are sequential.

## The gap, stated precisely

A person whose only credential is a Claude subscription can neither install this
factory nor dispatch on a headless token, and both refusals are unconditional.

The dispatch half is four steps:

1. A subscription-routed attempt reaches
   `factory/workgraph/adapter.py:1072` — `ClaudeCodeAdapter.run_attempt`, which
   calls
   `factory/workgraph/adapter.py:840` — `discover_subscription_credential`.
   That function searches three FILE paths and reads no environment variable.
2. When it returns `None` the attempt is refused outright at
   `factory/workgraph/adapter.py:1073` — `ClaudeCodeAdapter.run_attempt`.
   Nothing in that branch consults `CLAUDE_CODE_OAUTH_TOKEN`
   (`factory/workgraph/adapter.py:114`).
3. The environment that *would* have carried the token is not assembled until
   `factory/workgraph/adapter.py:947` — `attempt_env`, called at
   `factory/workgraph/adapter.py:1113` — `ClaudeCodeAdapter.run_attempt`, which
   the refusal in step 2 never reaches. Spec 125 added exactly this token guard
   to the neighbouring **expired-file** branch at
   `factory/workgraph/adapter.py:1088` — `ClaudeCodeAdapter.run_attempt` and
   not to the absent-file branch.
4. When a file *is* present,
   `factory/workgraph/adapter.py:896` — `_seed_node_home` copies it into every
   per-node HOME at `factory/workgraph/adapter.py:929` — `_seed_node_home`,
   whether or not a token will be the credential actually used. The copy is
   what carries the rotation hazard the function's own docstring records as
   unmeasured.

The install half is four more:

5. The `llm` block is mandatory —
   `factory/controlplane/config.py:364` — `_read_llm` — and `KNOWN_LL_MODES` at
   `factory/controlplane/config.py:35` is `("gateway", "direct")`. There is no
   answer that means "no gateway".
6. `factory/controlplane/verify.py:431` — `LLMProbe.gather` asserts
   `config.llm.gateway is not None` under a comment claiming gateway is the
   only parseable mode. `factory/controlplane/config.py:374` — `_read_llm`
   returns a populated direct block, so verifying a `direct` config raises
   AssertionError instead of reporting. Re-confirmed by running it at 602a92c.
7. For a registry whose personas are all subscription,
   `factory/controlplane/verify.py:400` — `gather_gateway_aliases` returns
   `{}`, `factory/controlplane/verify.py:447` — `LLMProbe.gather` returns the
   "no dispatchable model aliases" snapshot, and
   `factory/controlplane/verify.py:665` — `LLMProbe.evaluate` computes
   `passed = bool(snapshot.results) and …`, which is False. The `llm` check
   fails permanently, by construction.
8. And the interview cannot produce such a registry anyway.
   `factory/cli/install.py:578` — `_interview_personas` reads
   `document["llm"]["base_url"]` and `master_key_env` before anything else, so
   a gateway-less document raises `KeyError` there; and its three persona loops
   (`factory/cli/install.py:599` — `_interview_personas`,
   `factory/cli/install.py:640` — `_interview_personas` and
   `factory/cli/install.py:683` — `_interview_personas`) take their membership
   from the constant at `factory/cli/install.py:471`, so a registry that is not
   exactly the shipped six raises `KeyError` too.
9. And the registry a fresh host starts from is six gateway personas.
   `factory/cli/install.py:1118` — `_seed_personas_registry` copies
   `factory/config.py:60` — `shipped_registry_text` verbatim, and in it
   architect, implementer, judge, closer, debugger and researcher each declare
   `agent: claude-code` (`personas.example.yaml:26`), which makes
   `factory/config.py:203` — `Persona.routes_through_gateway` True for all six.
   `factory/cli/install.py:954` — `install_command` verifies what the interview
   wrote, so an operator who declared "no gateway" and changed nothing else
   would be told, correctly, that six of their personas still route through
   one.

## The rule this spec is asking for

**A registry that routes nothing through a gateway is a position an operator can
declare, install into, verify green and dispatch on — and the declaration states,
at the moment it is made, that it surrenders per-attempt credential isolation and
enforceable persona-to-model routing, not merely spend attribution.**

Two truth tables, because both inputs combine.

Dispatching a subscription-routed attempt:

| `CLAUDE_CODE_OAUTH_TOKEN` | credentials file | today | required |
|---|---|---|---|
| set | absent | **refused** | proceeds on the token; nothing copied into the node HOME |
| set | present | proceeds; file copied anyway | proceeds on the token; nothing copied |
| set | present but expired | proceeds (125); file copied anyway | proceeds on the token; nothing copied |
| unset | present | proceeds; file copied at 0600 | unchanged |
| unset | present but expired | refused, naming both remedies (125) | unchanged |
| unset | absent | refused, naming `claude auth login` only | refused, naming both supply routes |

Verifying a control plane:

| `llm.mode` | registry | today | required |
|---|---|---|---|
| `none` | — | unparseable | see below |
| `none` | any persona routes through the gateway | — | **FAIL**, naming those personas |
| `none` | all subscription or deterministic | — | **PASS**, detail naming the surrender |
| `gateway` | no dispatchable aliases | FAIL | **unchanged** |
| `gateway` | `example/` placeholders | FAIL | **unchanged** |
| `gateway` | master key unset | FAIL | **unchanged** |
| `direct` | — | **AssertionError** | a finding naming what direct cannot verify |

### What this spec is not

It is not a recommendation. The gateway stays the default and stays the
documented path, for the reason spec 055 already settled: two of the three
things it does are security properties. It is not a way to run gateway personas
without a gateway — declaring `none` while any persona still routes through one
fails verification, it does not warn. It is not a new credential store: Ergane
continues to read a credential the Claude CLI produced and continues never to
write one. And it does not re-do spec 125: the token's journey into the child
environment, its survival of `--clearenv`, its absence from gateway attempts
and the expired-copy refusal are all landed and stay exactly as they are. And
it is not the end of the credential-copy rotation hazard: FR-004 keeps today's
0o600 copy for an operator who holds a credentials file and no token, so the
hazard `factory/workgraph/adapter.py:896` — `_seed_node_home` records in its
own docstring survives on that path by design, and the ledger row that names it
is not closed by that half. The key stays declared because the row's summary and
its other three halves are owned outright by these FRs; operator step 8 in
`plan.md` files the successor finding for the surviving half, so that
`ergane findings triage --apply` cannot close the whole row on this spec's own
declaration.

## User Scenarios & Testing

### User Story 1 - A long-lived token is credential enough (Priority: P1)

As an operator whose only Claude credential is a long-lived token, I dispatch a
subscription-routed attempt on a host with no credentials file, and no copy of
any login is written into the agent's home.

**Why this priority**: P1 and independent of everything else here. It is the
half of spec 125 that was left behind, it blocks the container tier as well as
the bare-metal one, and it removes the file copy whose rotation hazard the code
itself records as unmeasured.

**Independent Test**: drive `run_attempt`'s credential branch and the node-home
seeding against a scratch operator home, with the environment variable set and
unset, and read back what was resolved, what was refused and what was written.

**Acceptance Scenarios**:

1. **Given** `CLAUDE_CODE_OAUTH_TOKEN` set to a non-empty value and no
   credentials file at any of the three searched paths, **When** a
   subscription-routed attempt is prepared, **Then** no refusal is raised and the
   seeded per-node HOME holds no `.credentials.json` anywhere beneath it — proven
   by a committed test that walks the seeded home and asserts the file list
   contains no credentials file, rather than checking one expected path.
2. **Given** one fixture run twice — once with the token set and once with it
   unset — each with a real credentials file at the third search path, **When**
   the node home is seeded, **Then** the token run writes no credentials file and
   the unset run writes today's copy at mode 0o600, asserted as a pair in one
   committed test. Only the pair can fail a diff that stopped copying in every
   case, and the token half fails today.
3. **Given** the token set, **When** the agent's environment is assembled for a
   subscription-routed attempt, **Then** it carries the token and carries neither
   `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN`, and `PASSTHROUGH_ENV` is
   still `("PATH", "LANG", "TERM")` — proven by a committed test over the
   assembled environment and the constant, so the token cannot smuggle gateway
   semantics back in behind a gateway that does not exist. This is a regression
   pin on what spec 125 landed, not new behaviour: it must be unchanged by this
   story, and it is US1-S1, US1-S2 and US1-S4 that no test-only diff can satisfy.
4. **Given** neither a token nor a credentials file, **When** a
   subscription-routed attempt is prepared, **Then** the refusal names both
   supply routes, and each remedy string is an element of the FR-005 constant
   that `factory/workgraph/credential_status.py:73` — `_credential_runway` and
   the expired-copy refusal at
   `factory/workgraph/adapter.py:1096` — `ClaudeCodeAdapter.run_attempt` also
   render — proven by one committed test that imports the shared constant from
   `factory/workgraph/adapter.py`, asserts every element of it is a substring
   of this refusal, and asserts the expired refusal's rendered sentence is
   byte-identical to the string 125 landed. Three operator surfaces that answer
   the same question must not be able to answer it differently.

### User Story 2 - No gateway is a declaration, not a failure (Priority: P1)

As an operator whose registry routes nothing through a gateway, I declare that,
and verification passes while telling me exactly what I gave up.

**Why this priority**: P1. Until an install can go green, a subscription-only
operator has no way to know their machine is ready, and every later refusal is
indistinguishable from a misconfiguration.

**Independent Test**: parse a config declaring the new mode, run the LLM probe
against registries with and without gateway personas, and read the findings.

**Acceptance Scenarios**:

1. **Given** a control-plane config declaring `llm.mode = "none"`, **When** it is
   parsed, **Then** it parses with no `base_url` and no `master_key_env`, and the
   parsed block carries a surrendered-properties text naming per-attempt
   credential isolation and enforceable persona-to-model routing as security
   properties and spend attribution as the accounting one — proven by a committed
   test over the parsed object that asserts on the two security clauses, not only
   on the spend clause, plus a source assertion that the text is defined exactly
   once in `factory/controlplane/config.py`.
2. **Given** `llm.mode = "none"` and a registry in which any persona's
   `routes_through_gateway`
   (`factory/config.py:203` — `Persona.routes_through_gateway`) is True,
   **When** the control plane is verified, **Then** the `llm` finding fails and
   its detail names every offending persona. Declaring no gateway while
   dispatching through one is the one combination that must never verify green,
   and the committed test names it.
3. **Given** `llm.mode = "none"` and a registry whose personas are all
   subscription or deterministic, **When** the control plane is verified,
   **Then** the `llm` finding's `passed` is True and its detail states the
   surrender in the manner
   `factory/controlplane/verify.py:940` — `EscalationProbe.gather` already
   states its own — proven by a committed test asserting on the detail's
   content. A PASS whose detail says only "skipped" fails this scenario.
4. **Given** a config declaring `llm.mode = "direct"`, **When** the control
   plane is verified, **Then** a finding is produced and no exception escapes —
   proven by a committed test that verifies a direct config and asserts on the
   returned finding. Today this raises `AssertionError` from
   `factory/controlplane/verify.py:431` — `LLMProbe.gather`.
5. **Given** three unconfigured registries — an empty alias set under a
   `gateway` declaration, the `example/` placeholder aliases, and an unset
   master key — **When** each is verified, **Then** each still fails, proven by
   three committed assertions. The distinction this story introduces is between
   *declared absent* and *not yet configured*, and collapsing them would
   surrender the check
   `factory/controlplane/verify.py:665` — `LLMProbe.evaluate` exists to make.
   All three fail today: this is a regression pin, and it is US2-S1 to US2-S4
   that no test-only diff can satisfy.

### User Story 3 - The interview can produce that position (Priority: P2)

As an operator running `ergane install` with only a subscription, I am offered
the no-gateway answer, and the interview completes and writes files that reflect
it — including a persona registry that no longer routes anything through a
gateway that is not there.

**Why this priority**: P2. US2 makes the position reachable by hand-editing two
files; this story makes it reachable the way every other control-plane choice is,
and it is the story that stops `ergane install` raising `KeyError` one step after
the answer is accepted.

**Independent Test**: drive `_ask_llm` and the persona interview through a
scripted prompter answering the no-gateway choice, with an alias-fetch seam that
raises if it is called, and read back the returned document and the written
registry — over the shipped example registry as well as an all-subscription
one.

**Acceptance Scenarios**:

1. **Given** a scripted prompter answering `none` at the LLM mode question,
   **When** the LLM block is asked, **Then** the returned document declares
   `llm.mode = "none"` with no `base_url` and no `master_key_env`, the captured
   output contains the FR-006 surrender text, and the prompter's recorded
   question list carries no further `llm` question — one committed test asserting
   all three.
2. **Given** no reachable endpoint from the scan, **When** the LLM mode
   question is composed, **Then** the offered choices name `none` alongside
   today's default, proven by a committed test on the offered choices string,
   **and** the two landed assertions that pin the old string —
   `tests/test_install_mode_routing.py:292` — `test_empty_scan_falls_back_to_todays_question`
   and
   `tests/test_ergane_install_walkthrough.py:635` — `test_the_real_terminal_prompter_drives_the_interview`
   — state the new one rather than being deleted. An answer nothing offers is
   an answer nobody finds; an assertion deleted rather than restated is a pin
   nobody replaced.
3. **Given** a `none`-mode document and a registry of subscription personas,
   **When** the persona interview runs with an alias-fetch seam and a probe
   seam that each raise if called, **Then** it completes without calling
   either, each subscription persona's model name is confirmed through the
   prompter, and the written registry parses with
   `factory/controlplane/verify.py:400` — `gather_gateway_aliases` returning
   empty over it — proven by a committed test asserting the seams were not
   called and the written file parses that way. Today this raises `KeyError` at
   `factory/cli/install.py:578` — `_interview_personas`.
4. **Given** one scripted interview body run twice, once answering `gateway` and
   once answering `none`, **When** each run finishes, **Then** every recorded
   question of the gateway run *after* the mode question — its text, its position
   and its default — and both files that run wrote are identical to the fixture
   committed with this story, while the none run writes `mode = "none"` and asks
   no gateway question — asserted as a pair in one committed test, so the guard
   cannot pass on a diff that changed the gateway path. The mode question's own
   offered-choices string is excluded from the comparison and only from it,
   because FR-011 is what changes it; the fixture records the post-change string.
5. **Given** a `none`-mode document and the registry a fresh host is seeded
   with — `personas.example.yaml:26`, in which six of the eight personas
   declare `agent: claude-code` — **When** the persona interview runs, **Then**
   each of those six is offered as a conversion to `agent: subscription`, every
   one accepted is written back carrying `agent: subscription`, the model name
   confirmed through the prompter and `fallback: null`, every one declined is
   written back byte-identical to the way it was seeded, and
   `factory/controlplane/verify.py:400` — `gather_gateway_aliases` over the
   written file returns aliases for the declined personas and no others —
   proven by one committed test that runs the interview over the seeded
   registry with at least one persona declined, reads the file back and asserts
   on both halves. Today `factory/cli/install.py:409` — `_update_persona_lines`
   rewrites `model` and `fallback` lines only, so no `agent:` line can change
   at all, and the position US2 made verifiable would stay unreachable from a
   fresh install.

### User Story 4 - The persona questions come from the registry, not a constant (Priority: P3)

As an operator whose registry does not name exactly the six personas this
repository ships, I am asked about the personas I actually have.

**Why this priority**: P3 and last. It is the remaining half of the ledger row's
`_GATEWAY_PERSONA_ORDER` complaint, it is separable from the no-gateway answer,
and it is the change with the widest blast radius on the existing install suite —
which is why it is not carried on US3's back.

**Independent Test**: drive the persona interview against registries of five,
seven and exactly the shipped six gateway personas and read back the recorded
question sequence and the written registry.

**Acceptance Scenarios**:

1. **Given** a registry naming five gateway personas, **When** the persona
   interview runs, **Then** every one of the five is asked and no `KeyError` is
   raised — proven by a committed test asserting the recorded question sequence
   covers exactly those five names. Today the three loops index a six-name
   constant.
2. **Given** a registry naming seven gateway personas, two of them absent from
   `factory/cli/install.py:471`, **When** the persona interview runs, **Then**
   all seven are asked, the five known names come first in the constant's order
   and the two unknown names follow in registry order — proven by a committed
   test asserting the exact recorded sequence, so question order stays declared
   rather than becoming dict-iteration order.
3. **Given** a registry naming exactly the shipped six, **When** the persona
   interview runs, **Then** the recorded question sequence and the written
   registry are identical to the fixture committed with US3-S4 — asserted in the
   same test module as scenario 1, so a derivation that reordered the shipped six
   fails here rather than on an operator's machine.

## Functional Requirements

- **FR-001**: When `CLAUDE_CODE_OAUTH_TOKEN` is set and non-empty in the worker
  environment, a subscription-routed attempt MUST NOT be refused for the absence
  of a credentials file; the absent-credential refusal MUST fire only when
  neither credential form is available.
- **FR-002**: When the long-lived token is the credential source, the per-node
  HOME MUST receive no `.credentials.json`, and no copy of the operator's login
  may exist anywhere beneath it.
- **FR-003**: Under either credential form the child MUST receive neither
  `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN`, and `PASSTHROUGH_ENV`
  (`factory/workgraph/adapter.py:104`) MUST remain `("PATH", "LANG", "TERM")`.
- **FR-004**: With no token set, the three-path search order, the 0o600 copy and
  the recorded-expiry refusal MUST behave exactly as they do today.
- **FR-005**: The two remedies — `claude auth login` and
  `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` — MUST be defined once,
  as a module constant in `factory/workgraph/adapter.py` beside the token
  constant at `factory/workgraph/adapter.py:114`, and every surface that names
  both routes MUST render from it: the absent-credential refusal, the
  expired-copy refusal at
  `factory/workgraph/adapter.py:1096` — `ClaudeCodeAdapter.run_attempt`, and
  `factory/workgraph/credential_status.py:44` — `_credential_runway`. The
  constant MUST NOT live in `factory/workgraph/credential_status.py`, which
  already imports from the adapter at
  `factory/workgraph/credential_status.py:25`; the reverse edge is a circular
  import in the module every dispatched attempt loads. The expired refusal's
  rendered sentence MUST stay byte-identical to the one spec 125 landed, so
  this is a re-rendering and not a behaviour change.
- **FR-006**: `KNOWN_LL_MODES` (`factory/controlplane/config.py:35`) MUST admit
  `"none"`. A `none` block MUST require no `base_url` and no `master_key_env`,
  and MUST carry a surrendered-properties text naming, in this order,
  per-attempt credential isolation, enforceable persona-to-model routing and
  spend attribution, with the first two named as security properties. That text
  MUST be defined exactly once, beside `factory/controlplane/config.py:350` —
  the `direct` mode's own text. The one landed assertion that pins that tuple
  by exact equality,
  `tests/test_controlplane_direct_mode.py:121` — `test_known_llm_modes_unchanged`,
  MUST be restated to `("gateway", "direct", "none")` — with the docstring that
  calls the widening forbidden restated with it — rather than deleted.
- **FR-007**: A `none` declaration MUST produce a failing `llm` finding naming
  every persona in the resolved registry whose `routes_through_gateway` is
  True. The registry MUST be reached through the probe's existing registry seam
  (`factory/controlplane/verify.py:149` — `_load_personas_for_probe`); the
  document parser MUST NOT be given a registry.
- **FR-008**: When the config declares `none` and no persona in the resolved
  registry has `routes_through_gateway` True — the exact complement of FR-007,
  so the two partition the input rather than overlapping — the `llm` finding
  MUST pass and its detail MUST state what was surrendered rather than only
  that the check was skipped. The antecedent MUST NOT be keyed on
  `factory/controlplane/verify.py:400` — `gather_gateway_aliases` returning
  empty, because a gateway-routed persona carrying neither a model nor a
  fallback contributes no alias and would satisfy FR-007 and FR-008 at once.
  The PASS MUST be carried on a discriminator the snapshot itself declares and
  `factory/controlplane/verify.py:665` — `LLMProbe.evaluate` branches on, in
  the manner `factory/controlplane/verify.py:915` — `TelemetryProbe.evaluate`
  and `factory/controlplane/verify.py:984` — `EscalationProbe.evaluate` already
  carry theirs; today `factory/controlplane/verify.py:70` — `LLMSnapshot` has
  no such field and an empty result set is the only signal.
- **FR-009**: Every other `llm` verdict MUST be unchanged: an empty alias set
  under a `gateway` declaration still fails, the `example/` placeholder registry
  still fails, and an unset master key still fails.
- **FR-010**: `factory/controlplane/verify.py:428` — `LLMProbe.gather` MUST NOT
  assert on `config.llm.gateway`. A `direct` config MUST produce a finding
  naming what direct mode cannot verify, and the comment claiming gateway is
  the only parseable mode MUST be removed with the assertion.
- **FR-011**: `factory/cli/install.py:1545` — `_ask_llm` MUST accept `none`,
  and that branch MUST print the FR-006 surrender text — read from the FR-006
  constant, never copied — before it returns, and MUST ask no gateway follow-up
  question.
- **FR-012**: In `none` mode
  `factory/cli/install.py:567` — `_interview_personas` MUST read no
  `llm.base_url` and no `llm.master_key_env`, fetch no alias list and probe no
  alias, and MUST still confirm each subscription persona's CLI-side model name
  and write the registry.
- **FR-013**: A gateway answer MUST leave every question after the mode
  question — its text, its position and its default — and both written files
  exactly as they are today. The mode question's own offered-choices string is
  excluded, because FR-011 changes it: the two landed assertions that pin it,
  `tests/test_install_mode_routing.py:292` — `test_empty_scan_falls_back_to_todays_question`
  and
  `tests/test_ergane_install_walkthrough.py:635` — `test_the_real_terminal_prompter_drives_the_interview`,
  MUST be restated to the new string rather than deleted.
- **FR-014**: The gateway persona question set MUST be derived from the resolved
  registry's own membership filtered by `routes_through_gateway`, so a registry
  naming five personas or seven is interviewed without raising `KeyError`.
- **FR-015**: `_GATEWAY_PERSONA_ORDER` (`factory/cli/install.py:471`) MUST remain
  the transcript's sort key — names it knows first in its own order, names it
  does not know after them in registry order — so question order stays declared
  rather than becoming dict-iteration order.
- **FR-016**: A registry naming exactly the shipped six MUST produce today's
  question sequence and today's written registry.
- **FR-017**: In `none` mode the persona interview MUST offer, for every
  persona in the resolved registry whose `routes_through_gateway`
  (`factory/config.py:203` — `Persona.routes_through_gateway`) is True, to
  record that persona as `agent: subscription` with a CLI-side model name
  confirmed through the prompter and its `fallback` written `null`, and MUST
  write every accepted change into the registry file.
  `factory/cli/install.py:409` — `_update_persona_lines` rewrites only `model`
  and `fallback` lines today and MUST be widened to `agent`, with `agent`
  optional in the updates mapping so that a gateway run writes byte-for-byte
  what it writes today (FR-013). A persona the operator declines MUST be
  written back unchanged, so that verification names it under FR-007 rather
  than the interview converting it behind the operator's back.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012, FR-013, FR-017]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-014, FR-015, FR-016]
```

Chain depth 3, and every edge is `depends_on_merged` because none of them is a
pass-edge: no story here needs another's verdict, only another's code on the
landing branch. US1 has no edge at all — it owns `factory/workgraph/adapter.py`
and touches neither the control-plane schema nor the installer, so it runs
alongside from round one. US3 depends on US2 because `_ask` validates every
candidate answer through `parse_controlplane_config`
(`factory/cli/install.py:1910` — `_ask`), so an interview that offers `none`
before the parser admits it would refuse its own answer in a loop. US4 depends
on US3 because both edit `factory/cli/install.py` and US3's no-gateway branch
is the context US4's membership derivation is written against — and because
FR-017 widens `factory/cli/install.py:409` — `_update_persona_lines`, which
US4's write-up loop feeds; serialising them buys freedom from contention as
well as correctness of sequencing.
