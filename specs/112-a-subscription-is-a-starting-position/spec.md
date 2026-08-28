---
state: draft
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
---

# Feature Specification: a subscription is a starting position

**Created**: 2026-08-27
**Depends on**: nothing landed-but-unmerged. US1 is independent; US2 → US3 are
sequential.

## The gap, stated precisely

There are two ways to hold a Claude subscription credential, and Ergane consumes
the fragile one and refuses the durable one.

`claude auth login` writes `~/.claude/.credentials.json`. That file is what
`discover_subscription_credential` finds, and what `_seed_node_home` copies into
each per-node HOME — a copy whose rotation behaviour the code itself records as
unmeasured, and whose worst case is the operator's own host login being
invalidated by the first node that refreshes.

`claude setup-token` mints a long-lived token for exactly this situation. Ergane
has no path for it. There is no `CLAUDE_CODE_OAUTH_TOKEN` anywhere in `factory/`.

And an operator whose *only* credential is that subscription cannot complete an
install at all. They must declare an `llm` block they will not use, and then
watch `ergane install --verify` report `[FAIL] llm: no dispatchable model aliases
in the persona registry` — forever, by construction, because an empty alias set
is coded as a failure and the interview never offers to produce a registry that
would have one.

## The rule this spec is asking for

**A registry that routes nothing through a gateway is a position an operator can
declare, install into, and verify green — and the declaration states, at the
moment it is made, that it surrenders per-attempt credential isolation and
enforceable persona-to-model routing, not merely spend attribution.**

### What this spec is not

It is not a recommendation. The gateway stays the default and stays the
documented path, for the reason spec 055 already settled: two of the three things
it does are security properties. It is not a way to run gateway personas without
a gateway — declaring `none` while any persona still routes through one is a
refusal, not a warning. And it is not a new credential store: Ergane continues to
read a credential the Claude CLI produced, and continues to never write one.

## User Scenarios & Testing

### User Story 1 - A token is a credential the factory can take (Priority: P1)

As an operator running the factory on a subscription, I hand it a long-lived
token from the environment instead of a credentials file, and the agent in its
sandbox authenticates without any copy of my login being made anywhere.

**Why this priority**: P1 and independent. It removes a documented, unmeasured
hazard from the path this floor already runs on, and it is the credential form a
container or a CI runner can actually carry.

**Independent Test**: drive credential discovery and node-home seeding against a
scratch home with the environment variable set and unset, and read back what was
resolved and what was written.

**Acceptance Scenarios**:

1. **Given** `CLAUDE_CODE_OAUTH_TOKEN` set in the environment and no credentials
   file anywhere in the three searched paths, **When** a subscription-routed
   attempt is prepared, **Then** discovery resolves the token, the attempt is
   not refused, and **no** `.credentials.json` is written into the per-node HOME
   — proven by a committed test that asserts the seeded home contains no
   credentials file.
2. **Given** the same token, **When** the adapter builds the agent's
   environment, **Then** the token reaches the child process and neither
   `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN` is set — the subscription
   route's existing invariant (US2 FR-006 of 070) is unchanged, proven by a test
   over the assembled environment.
3. **Given** both a token in the environment and a credentials file on disk,
   **When** discovery runs, **Then** the token wins and nothing is copied — one
   order, stated once, so two operators do not get two behaviours. The test
   asserts the precedence explicitly rather than inferring it.
4. **Given** neither a token nor any credentials file, **When** a
   subscription-routed attempt is prepared, **Then** the refusal names both ways
   to supply one — `claude auth login` and `claude setup-token` with its
   environment variable — proven by a test asserting both appear. The refusal
   today names `claude login`, which is not a command in Claude Code 2.1.223;
   the correct spelling is `claude auth login`.

### User Story 2 - No gateway is a declaration, not a failure (Priority: P1)

As an operator whose registry routes nothing through a gateway, I declare that,
and verification passes while telling me exactly what I gave up.

**Why this priority**: P1. Until an install can go green, a subscription-only
operator has no way to know their machine is ready, and every later refusal is
indistinguishable from a misconfiguration.

**Independent Test**: parse a config declaring the new mode, run the LLM probe
against a registry with no gateway personas, and read the finding.

**Acceptance Scenarios**:

1. **Given** a control-plane config declaring `llm.mode = "none"`, **When** it is
   parsed, **Then** it parses, requires no `base_url` and no `master_key_env`,
   and carries a surrendered-properties text naming per-attempt credential
   isolation, enforceable persona-to-model routing, and spend attribution — in
   the shape `DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT` already uses
   (`factory/controlplane/config.py:350-360`), proven by a committed test over
   the parsed object.
2. **Given** `llm.mode = "none"` and a registry in which **any** persona routes
   through the gateway (`routes_through_gateway` is True — `config.py:203-208`),
   **When** the config is verified, **Then** it is refused by name, listing the
   offending personas. Declaring no gateway while dispatching through one is the
   one combination that must never be reachable, and the test names it.
3. **Given** `llm.mode = "none"` and a registry whose personas are all
   `subscription` or `none`, **When** `ergane install --verify` runs, **Then**
   the `llm` finding is **PASS**, and its detail names the surrender in the
   manner the escalation probe already names its own — proven by a test
   asserting the finding's `passed` is True and that its detail states what is
   given up rather than merely that the check was skipped.
4. **Given** a config declaring `llm.mode = "direct"`, **When**
   `ergane install --verify` runs, **Then** it produces a finding rather than
   raising — today `LLMProbe.gather` asserts `config.llm.gateway is not None`
   (`verify.py:415-417`) under a comment claiming gateway is the only parseable
   mode, while `_read_llm` returns a populated direct config
   (`config.py:374-384`). Proven by a test that verifies a direct config and
   asserts no exception escapes.
5. **Given** an **unconfigured** registry — the `example/` placeholder aliases,
   or a gateway mode with no reachable endpoint — **When** the probe runs,
   **Then** it still FAILS exactly as it does today. The distinction this story
   introduces is between *declared absent* and *not yet configured*, and
   collapsing them would surrender the check that `verify.py:648-651` exists to
   make.

### User Story 3 - The interview can produce that position (Priority: P2)

As an operator running `ergane install` with only a subscription, I am offered
that as an answer, and the registry the interview writes reflects it.

**Why this priority**: P2. US2 makes the position reachable by hand-editing two
files; this story makes it reachable the way every other control-plane choice is.

**Independent Test**: drive the interview through a scripted prompter answering
"subscription" and read back the written config and registry.

**Acceptance Scenarios**:

1. **Given** the interview at its LLM question, **When** the operator chooses
   the no-gateway answer, **Then** the surrendered-properties text is printed
   **before** the answer is accepted — the same ordering `direct` already uses
   (`factory/cli/install.py:1600-1602`) — proven by a test asserting the text
   reaches the transcript ahead of the confirmation.
2. **Given** that choice, **When** the interview writes its files, **Then** the
   config declares `llm.mode = "none"` and every persona in the written registry
   declares `agent: subscription` or `agent: none`, with a model name the Claude
   CLI accepts and no gateway alias — proven by a test that parses both written
   files and asserts `gather_gateway_aliases` (`verify.py:386-402`) returns
   empty for the result.
3. **Given** the same choice, **When** the interview reaches the per-persona
   questions, **Then** the six personas are no longer taken from a hard-coded
   gateway list (`_GATEWAY_PERSONA_ORDER`, `install.py:471-478`) but from the
   registry's own membership, so a registry that names five personas or seven is
   interviewed correctly — proven by a test driving a registry that is not the
   shipped six.
4. **Given** an operator who chooses the gateway, **When** the interview runs,
   **Then** its behaviour is byte-for-byte today's, proven by the existing
   install suite passing unmodified.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

Chain depth 2. US1 is independent of both — it edits the adapter and its tests
and touches neither the control-plane config nor the installer. US3 depends on
US2 because the answer it writes must be a mode the parser already accepts.

## Requirements (summary — numbered at refinement)

Token discovery and its precedence over the file; a seeded node HOME with no
credential copy when a token is present; the corrected refusal naming both
supply routes with the right spelling; `llm.mode = "none"` and its surrendered-
properties text; the refusal when a gateway persona survives the declaration;
the LLM probe's declared-absent PASS and its preserved unconfigured FAIL; the
direct-mode assertion replaced by a finding; the interview's new answer, its
pre-acceptance disclosure, and a persona list read from the registry rather than
a constant.

## Success Criteria (summary)

Pasted: a seeded node HOME listing with no credentials file under a token; the
`[PASS] llm:` line from a no-gateway verify, with its surrender text; the
refusal transcript for a gateway persona under a `none` declaration; and the
existing install suite's before-and-after counts.

**Operator verification, which is the point of the spec**: on a machine with a
Claude subscription and no LiteLLM anywhere, run `claude setup-token`, export the
token, run `ergane install` choosing the no-gateway answer, run
`ergane install --verify` and read a green `llm` line, then dispatch one real
story and watch it pass. Until that has been done once, this spec has made a
position declarable and proved nothing about whether it builds software.
