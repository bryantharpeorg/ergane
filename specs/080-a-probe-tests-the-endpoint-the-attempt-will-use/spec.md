---
state: draft
fixes:
  - verify/probe-mints-against-the-resolved-env-gateway-not-the-declared-one
# Drafted 2026-08-21 ~8:20 AM CT by an operator session.
#
# THIS SPEC IS A SUBSTITUTION AND THE OPERATOR SHOULD KNOW WHY. It was asked for
# as "install --verify probes a different Temporal than the worker connects to"
# (finding `install/verify-probes-a-different-temporal-than-the-worker-connects-to`,
# critical, filed 2026-08-16). **That finding is already fixed and the fix is in
# the tree.** Verified 2026-08-21 by reading it rather than trusting the ledger:
#
#   - `factory/controlplane/resolve.py:232` `resolve_temporal_target` and `:252`
#     `temporal_target_for` share one precedence (environment, then declaration,
#     then built-in default), and `resolve_temporal_target` is *written in terms
#     of* `temporal_target_for`, so the two cannot diverge.
#   - `factory/controlplane/verify.py:170` `_temporal_client_factory` routes
#     through `temporal_target_for` with the config it was handed, and its
#     docstring at `:173-179` records exactly why: re-reading the config path
#     there would verify a different file than the one on the command line.
#   - Every other reader — `factory/worker.py:281`, `factory/doctor/probes.py:487`
#     and `:599`, `factory/notify/service.py:833`, `factory/cli/main.py:155` —
#     calls the same resolver.
#   The finding wants verifying and resolving in the ledger, not building again.
#
# WHAT IS STILL OPEN IS THE SAME DEFECT ON THE OTHER SUBSYSTEM, and it was
# demonstrated live on 2026-08-20:
#   `verify/probe-mints-against-the-resolved-env-gateway-not-the-declared-one`
#   (warning, open). A probe handed a config pointing at a local mint-incapable
#   fake, while `LITELLM_PROXY_URL` pointed at the real gateway, reported
#   "minted, constrained and revoked". It described a gateway the config never
#   named.
#
# It is filed as a warning rather than a critical, and it is in this release's
# scope anyway for two reasons the operator should weigh rather than take on
# faith: it sits on the install path a first-run user walks, and it is the last
# surviving instance of the class 061-US1 and 048-US4 were built to close --
# `verify/readiness-proves-a-thing-is-declared-not-that-it-works`, which IS
# critical and is 061-US4's subject.
#
# THE SPLIT, verified line by line on 2026-08-21:
#   - `factory/controlplane/verify.py:167` -- `return LiteLLMClient.from_env()`.
#     The admin client that mints, inspects and revokes the probe key is built
#     ENVIRONMENT-FIRST, from `factory/usage/litellm_client.py:136`'s `from_env`.
#   - `factory/controlplane/verify.py:315` -- `base_url = gateway.base_url`. The
#     completion fallback at `:452-453` posts to the DECLARED url, and every
#     message the probe emits names that same declared url.
#   So when the two disagree, the probe mints against one server, completes
#   against another, and reports both under one address -- including the failure
#   text at `:436`, which names a gateway it never called.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. The 2026-08-21 block above is kept verbatim as the record it is; its
# line numbers are as of that date and most of them have since moved — the
# exceptions are `factory/controlplane/resolve.py:232` and `:252` and
# `factory/doctor/probes.py:487` and `:599`, which still resolve as written.
#
# WHERE THIS CAME FROM. The 2026-08-21 block above is the origin and is kept for
# it: this spec is a SUBSTITUTION for a Temporal finding already fixed in tree,
# and what it builds instead is the same defect on the LLM side —
# `verify/probe-mints-against-the-resolved-env-gateway-not-the-declared-one`
# (warning, open, one occurrence), filed from the operator session of 2026-08-20
# that watched a probe report "minted, constrained and revoked" about a server the
# config never named. That ledger row is the only key this spec declares, and its
# summary is what the nine FRs are written against.
#
# WHAT IT COST, MEASURED. The defect was demonstrated live on 2026-08-20 at the
# cost of one operator session: a config naming a local mint-incapable fake, an
# environment naming the real gateway, and a verdict that read "minted,
# constrained and revoked" about a server the config never named. Nothing in the
# suite caught it, because every existing LLM-probe test patches
# `_llm_client_factory` — the exact function the defect lives in — and takes a
# completion branch production never takes. This refinement re-read 67 anchors:
# 21 had moved, 5 instructions were wrong, and 2 defects had changed shape.
#
# EVERY ANCHOR INTO `verify.py` HAD MOVED, BY TWO DIFFERENT DELTAS. Six stories
# landed on `factory/controlplane/verify.py` between 2026-08-21 and 2026-08-31
# (063-US3 `7551764`, 078-US2, the bwrap preflight, 105-US3, 111-US1/US2,
# 119-US3) adding 285 lines above the LLM probe. `7551764` also rewrote the alias
# derivation now at `factory/controlplane/verify.py:445`, inside `LLMProbe.gather`
# and above the key sequence this spec edits; it changes no instruction here. The
# module-level factories moved +8 (`_llm_client_factory` 160→168,
# `_temporal_client_factory` 170→178) and everything inside `LLMProbe.gather`
# moved +108 to +117 (`base_url = gateway.base_url` 315→432, the key sequence
# 361-423→467-537, the failure text 436→544, the completion request
# 452-453→560-566). Twelve anchors landed on blank lines and validate refused
# them; the rest are re-anchored in the `` `path.py:NN` — `symbol` `` form so the
# next drift is machine-caught. `resolve.py` has not been touched since 048-US4 on
# 2026-08-16 and all nine of its anchors still resolve.
#
# THE DEFECT CHANGED SHAPE, AND THE OLD PLAN WOULD HAVE SENT AN IMPLEMENTER
# LOOKING FOR THE WRONG THING. The 2026-08-21 block calls the admin half
# "ENVIRONMENT-FIRST" and the completion half "the DECLARED url". Half of that is
# now wrong: `from_env` has read `resolve_llm_gateway()` since 048-US1, so the
# admin half applies the *published* precedence. The completion half applies
# none — it binds `gateway.base_url` and `gateway.master_key_env` raw. So the
# asymmetry is not "two precedences" but "one precedence and no precedence", and
# there is a SECOND divergence nobody had written down: `resolve_llm_gateway()`
# called with no `config_path` falls back to `resolve_config_path()`, so on a run
# given a non-default config file the admin half reads a different FILE — the
# exact hazard `_temporal_client_factory`'s docstring records and avoids. FR-007
# is new and closes it.
#
# US1-S1 CONTRADICTED FR-003 AND WOULD HAVE INVERTED THE PRECEDENCE. It read
# "declared gateway cannot mint, environment can, THEN the probe fails". Under
# environment-first — which FR-003 requires and trap 1 defends — the environment
# gateway wins for *both* halves and the probe correctly passes, reporting on the
# machine the attempt will actually use. An implementer building to that Then
# would have made disagreement itself a refusal: declaration-first with extra
# steps, passing the judge, and reversing 048-US4's structural answer one
# subsystem over. Rewritten, and the failure case is now carried by US2-S2 where
# it belongs.
#
# THE COMPLETION PATH IS NOT A FALLBACK. Both the old spec and the old plan call
# `factory/controlplane/verify.py:560-566` "the completion fallback". The real
# `LiteLLMClient` defines no `chat_completion` (spec 132's refinement filed this
# as an unfiled defect on 2026-09-04), so the `hasattr` guard is always false in
# production and that block is the only path a real install takes. Only the test
# fakes take the other one. Trap 2 now says so; an implementer who reads
# "fallback" deprioritises the one branch that matters.
#
# SEVEN MESSAGE SITES, NOT SIX. The old plan enumerated `:436`, `:469`, `:474`,
# `:529`, `:533` and the completion request. Two more interpolated the same
# `base_url` on the day it was written and still do — now `:493` and `:519` — so
# a diff built to the old list would have left two messages naming a server the
# call never reached. FR-005 names all seven.
#
# ONE KEY DECLARED, TWO DELIBERATELY NOT. `fixes:` carries
# `verify/probe-mints-against-the-resolved-env-gateway-not-the-declared-one` and
# nothing else, and the nine FRs cover its ledger summary clause by clause.
# `install/verify-probes-a-different-temporal-than-the-worker-connects-to` is
# still `open` in the ledger and is not declared here, because this spec does not
# fix it — it was fixed by 048-US4 and 061 and wants an operator to verify and
# resolve it. `verify/readiness-proves-a-thing-is-declared-not-that-it-works` is
# not declared either: its ledger row lists five instances and this spec reaches
# one. The second instance — `gate_check` asserting a check exists rather than
# that it can fail — is spec 128's whole subject and 128 is still draft, so the
# 2026-08-21 claim that this is "the last surviving instance of the class" is not
# true and the class stays open.
#
# NOT IN SCOPE. The probe's five-step key sequence
# (`factory/controlplane/verify.py:467-537`, 061-US1, verified live by control and
# mutation on 2026-08-20) is untouched: this spec changes which client performs
# it, not what it performs. `from_env` and its call sites outside
# `factory/controlplane/verify.py` are untouched — FR-008 makes that a
# requirement rather than a hope. Nothing here touches Temporal, memory,
# telemetry or escalation resolution, and nothing here changes what
# `resolve_llm_gateway` decides; it changes only where its answer is read from.
# This spec is also NOT spec 132: 132 is about the alias preflight measuring the
# route it dispatched on, its own provenance says the two are "adjacent,
# different, and not to be folded in", and the sequencing hazard the two share is
# trap 9.
#
# STALE COMPILED ARTIFACT. `workgraph.json` beside this file was derived before
# this refinement and its `requirement_keys` stop short in both nodes, not one:
# `us1`'s end at FR-003 and `us2`'s at FR-006. `ergane build start`
# reads a compiled graph off disk, and those keys select the criteria the judge
# scores against, so dispatching from that file would hand both nodes a criteria
# set that never names FR-007, FR-008 or FR-009. This refinement is not permitted
# to write or delete it: the operator deletes it or re-derives it and confirms
# `us1.requirement_keys` ends in FR-008 and `us2.requirement_keys` in FR-009.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a review refuted the flip and four
# blocking defects are closed. (1) FR-004/FR-009 and US2-S1/US2-S3 demanded "the
# config file's path", which no probe can reach — `Probe.gather` is handed a
# parsed `ControlPlaneConfig` carrying no path and the only other route is the
# `resolve_config_path()` call FR-007 forbids — so all four now name the source
# the resolution already carries (a variable's name, or the declaration label),
# and plan trap 12 forbids plumbing a path. (2) US1-S3 pinned the detail string
# "character-for-character" and forbade changing it, while US2's rendering must;
# the pin is now scoped, US2 is named as the one story permitted to move it, and
# a US2 task does so. (3) FR-005 was already satisfied by US1's rebinding of
# `base_url`, so a test-only US2 diff passed it; it now requires the source
# clause at each of the seven sites, which US1 does not supply. (4) The operator's
# step 3 named an `ergane install --config` flag that does not exist; it is a
# runnable one-liner now, and the FR-007 divergence is stated as latent because no
# CLI route hands a non-default path. Minor: FR-008's "five production callers"
# was a stale count copied from `from_env`'s own docstring — six call sites in five
# modules, enumerated in plan.md § Sizing; trap 7's `527-537` and trap 9's `585`
# were off by one and two; the neighbour survey missed `7551764`; T005 no longer
# drives the whole eight-probe registry. The 2026-08-21 record, the substitution
# notice, the two withheld keys and the stale-artifact warning are unchanged.
#
# REPAIRED 2026-09-04, SECOND PASS (refinement-2026-09-04): an adversarial review
# refuted the flip on three blocking defects and all three are closed.
# (1) AN INSTRUCTION THAT COULD NOT BE EXECUTED. Trap 5 said "every new test MUST
# pass an explicit mapping", and no path here allows one:
# `factory/controlplane/verify.py:62` — `gather` takes only a config (trap 12
# forbids widening it) and `factory/usage/litellm_client.py:136` — `from_env` only
# a transport and a timeout (FR-008 forbids widening that). The trap now says what
# the tree does — the sibling takes `environ=` so the resolver is unit-testable,
# while the probe's own call sites pass none and fall to `os.environ`, exactly as
# `factory/controlplane/verify.py:192` already does — and T002 and T006 inject
# with `monkeypatch.delenv`/`setenv`.
# (2) A FALSE COMPLETENESS CLAIM IN "WHAT ALREADY EXISTS". The plan named two test
# files and omitted `tests/test_controlplane_verify.py:1147` —
# `test_verify_llm_gather_against_live_double`, the only existing test that runs
# both halves of this probe for real, and the five-endpoint loopback double at
# `tests/test_controlplane_verify.py:320` that three of US1's tests need. Both are
# now named, the double is declared the harness to extend rather than rebuild, and
# § Sizing is re-priced on reusing it.
# (3) BOTH OFFERED DOUBLES DELETED THE CODE UNDER TEST. A from-scratch fake
# client's `from_env` consults nothing, so US1-S5's "fails if `resolve_config_path`
# is consulted" passed on today's tree and US1-S1's before-transcript was
# fabricable. Any admin-client double MUST now subclass
# `factory/usage/litellm_client.py:108` — `LiteLLMClient`, and US1-S5's test is
# pasted failing against today's tree.
# MINOR, ALL CLOSED: US1-S4 claimed a discrimination it does not make and left
# FR-002's structural clause uncovered — it now also asserts `resolve_llm_gateway`'s
# own answer moves; US2-S2 drives all seven message sites rather than three;
# US1-S6 and US2-S4 are labelled controls; FR-009 and US2-S3 now say "the
# declaration label the probe passed in", as FR-004 already did; trap 9 mis-stated
# 132's FR-003 (it defines `chat_completion` on `LiteLLMClient`, it does not edit
# `factory/controlplane/verify.py:556`) and missed 132's FR-010, which restructures
# the client lifetime around the `finally` at
# `factory/controlplane/verify.py:528-537` that trap 7 forbids touching; trap 5
# gained the endpoint half of the ambient-override hazard
# (`scripts/ergane-env.sh:72-73` exports both variables, `tests/conftest.py:525`
# scrubs neither) with the traced conclusion that no existing assertion depends on
# either value; the neighbour survey gained `e4b111b`, which added `gateway_mode`
# at `factory/controlplane/config.py:130` and reaches neither resolver nor probe;
# § Sizing no longer says "three production files" when the third must not move;
# and four anchors that mean a Python symbol are rewritten in the
# `path.py:NN` — `symbol` form. `fixes:` is unchanged, the 2026-08-21 record is
# unchanged, and the two withheld keys and the stale-artifact warning stand.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a third adversarial review refuted
# the flip on three blocking defects; all three are closed and no anchor moved.
# (1) FR-001 HAS TWO CLAUSES AND ONLY ONE WAS PROVABLE. Every US1 Then was about
# addresses, so a diff that unified the URL and left `api_key_env` bound at
# `factory/controlplane/verify.py:433` passed the whole story while still
# authenticating to one server with another server's key — the exact wrong move
# plan.md § "The ordinary half" names. US1-S1 and T001 now record the credential
# each half authenticated with as well as the address, require the declaration to
# name a `master_key_env` the environment does not, and extend
# `tests/test_controlplane_verify.py:320` — `_loopback_llm_listener` to keep the
# `Authorization` header it discards today at
# `tests/test_controlplane_verify.py:343-354`.
# (2) THE SEVENTH MESSAGE SITE CANNOT BE DRIVEN BY ANY INPUT.
# `factory/controlplane/verify.py:544` is `key_probe_detail or f"…{base_url}"`, and
# every path that reaches `factory/controlplane/verify.py:539` has already assigned
# a non-empty detail, so that f-string renders on no input. US2-S2 and T016 asked a
# test to drive it, and T016's named driver — "an unconstrained key with no detail"
# — sets the message at `factory/controlplane/verify.py:500-504`, which names no
# address and is outside FR-005 entirely. US2-S2 now drives the six reachable
# branches and proves the seventh from the diff, FR-005 says which is which, and new
# plan trap 15 carries the trace plus the one optional forcing mechanism.
# (3) "PATCHES EXACTLY ONE SYMBOL" WAS UNSATISFIABLE UNDER THE SHAPE THE PLAN
# MANDATES. `factory/controlplane/verify.py:32` from-imports `temporal_target_for`
# while `factory/controlplane/resolve.py:249` calls it as a module global, so a
# sibling copied that way answers to two bindings and one `monkeypatch.setattr`
# moves only half of what US1-S4 asserts. US1-S4 and T004 now say "by name in every
# module that binds it"; new plan trap 16 names both acceptable shapes.
# MINOR, ALL CLOSED: the enumeration behind "no route hands a non-default path"
# named two no-argument callers and there are three — `factory/cli/init.py:174` and
# `factory/supervision/engine_upgrade.py:106` were missing — so § The gap step 6 and
# plan § Verification step 3 now name all six call sites; the plan's `e4b111b`
# paragraph implied `gateway_mode` had one reader in `factory/cli/install.py` and it
# has twelve, so it now says "the interview and apply paths, first at :162" while
# keeping the load-bearing half, that it reaches neither resolver nor probe; three
# `tests/conftest.py` commits (`b5bffad`, `625de8c`, `0371f1b`) missing from the
# neighbour survey are added, all pure additions that leave trap 5's two anchors
# true at 602a92c; and the stale-artifact paragraph above no longer attributes
# `us2`'s FR-006 to both nodes. `fixes:` is unchanged, the 2026-08-21 record is
# unchanged, and the two withheld keys stand.
---

# Feature Specification: a probe tests the endpoint the attempt will use

**Created**: 2026-08-21
**Depends on**: nothing. Both resolvers it reads — `resolve_llm_gateway` and
`temporal_target_for` — landed under 048 on 2026-08-16.

## The gap, stated precisely

`ergane install --verify` exists to answer one question: will this host actually
build. Its LLM probe answers that question about two machines at once, and prints
one address for both. The chain is six steps.

1. The probe binds its endpoint and its credential straight off the parsed
   declaration, applying no precedence at all:
   `factory/controlplane/verify.py:432` is `base_url = gateway.base_url`, and
   `factory/controlplane/verify.py:433-434` are `api_key_env =
   gateway.master_key_env` followed by `api_key = os.environ.get(api_key_env)`.
2. The privileged half is built somewhere else entirely.
   `factory/controlplane/verify.py:477` calls
   `factory/controlplane/verify.py:168` — `_llm_client_factory`, whose whole body
   is `return LiteLLMClient.from_env()` at `factory/controlplane/verify.py:175`.
3. `factory/usage/litellm_client.py:136` — `from_env` resolves through
   `resolve_llm_gateway()` at `factory/usage/litellm_client.py:170-174`, and
   `factory/controlplane/resolve.py:334` — `_resolve_endpoint` answers
   `EndpointRef(override, PROXY_URL_ENV)` the moment `LITELLM_PROXY_URL` is set.
   `factory/controlplane/resolve.py:347` — `_resolve_credential` does the same for
   `LITELLM_MASTER_KEY`. So the admin half applies the published precedence and
   the ordinary half applies none.
4. When the variable disagrees with the file, the five-step key sequence at
   `factory/controlplane/verify.py:467-537` runs against the variable's server
   while the completion request goes to the declared one, at
   `factory/controlplane/verify.py:560-566`. That block is not a fallback: the
   real client defines no `chat_completion`, so the guard at
   `factory/controlplane/verify.py:556` is false on every real install and that is
   the only path production takes.
5. Every sentence the probe emits interpolates the declared address:
   `factory/controlplane/verify.py:493`, `factory/controlplane/verify.py:519`,
   `factory/controlplane/verify.py:544`, `factory/controlplane/verify.py:577`,
   `factory/controlplane/verify.py:582`, and — through the `base_url` parameter of
   `factory/controlplane/verify.py:625` — `_classify_key_failure` —
   `factory/controlplane/verify.py:637` and
   `factory/controlplane/verify.py:641`. Seven sites, one address, two servers.
   The green line at `factory/controlplane/verify.py:523-526` names no address at
   all, so an operator cannot even tell which of the two answered.
6. There is a second divergence on the same seam and it needs no environment
   variable. `resolve_llm_gateway()` called with no `config_path` falls through to
   `resolve_config_path()` at `factory/controlplane/resolve.py:412`, so the admin
   half reads the **default** config file whatever file
   `factory/controlplane/verify.py:1198` — `verify_controlplane_async` was handed.
   That is the exact hazard
   `factory/controlplane/verify.py:178` — `_temporal_client_factory` records in
   its own docstring at `factory/controlplane/verify.py:181-188` and avoids by
   never re-reading a path. **This second divergence is latent.** No caller in the
   tree hands a non-default path today, and there are six of them: three pass no
   argument at all — `factory/cli/nouns/install.py:40`, `factory/cli/init.py:174`
   and `factory/supervision/engine_upgrade.py:106` — and the three inside
   `factory/cli/install.py` (`factory/cli/install.py:954`,
   `factory/cli/install.py:1185`, `factory/cli/install.py:1279`) all pass the
   `path = resolve_config_path()` bound once at `factory/cli/install.py:901`.
   Nobody should credit this spec with
   curing a live install-path symptom for step 6; FR-007 closes the hole before a
   caller arrives, which is the cheap moment to close it.

Demonstrated live on 2026-08-20: a config naming a local mint-incapable fake, an
environment naming the real gateway, and a verdict reading "minted, constrained
and revoked" under the fake's address. That demonstration is steps 1 through 5.

## The rule this spec is asking for

**One resolution decides both halves of the LLM probe, and the verdict names the
address that answered together with the source that chose it.**

The cases, complete. "A" is the gateway declared in the config file the command
was given; "B" is a different address in `LITELLM_PROXY_URL`; "default" means the
file at `resolve_config_path()`.

| `LITELLM_PROXY_URL` | declared in the file given | the file given | mints against, today | completes against, today | after this spec |
|---|---|---|---|---|---|
| unset | A | the default | A | A | A and A; the verdict names A and the source that chose it |
| **B** | A | the default | **B** | **A** | B and B; the verdict names B and says the variable overrode the declaration |
| unset | A | **not** the default | whatever the **default file** declares | A | A and A; no second file is opened |
| B | B | either | B | B | unchanged; the verdict now names B and the variable |

Row three is **latent**: reaching it requires a caller that hands
`factory/controlplane/verify.py:1198` — `verify_controlplane_async` a non-default
path, and no CLI route does. It is the row FR-007 owns, and the operator's
independent check of it is a direct call rather than a command-line flag.

### What this spec is not

It is not a change of precedence. Environment first, then declaration, then a
refusal naming both routes is what `factory/controlplane/resolve.py:334` —
`_resolve_endpoint` and `factory/controlplane/resolve.py:347` —
`_resolve_credential` already decide, and this spec moves no branch inside them.

It is not a refusal on disagreement. An operator exporting `LITELLM_PROXY_URL` is
overriding on purpose; the answer is to obey them in both halves and say so, not
to stop.

It is not a change to what the probe does. Minting a short-TTL key, asserting it
is model-constrained, reading the spend log and revoking it is 061-US1's work at
`factory/controlplane/verify.py:467-537`; it landed, it was verified live by
control and mutation on 2026-08-20, and it is correct.

It is not a change to `factory/usage/litellm_client.py:136` — `from_env` or to
its call sites outside `factory/controlplane/verify.py`. There are six of those,
in five modules, and FR-008 makes leaving them alone a requirement.

It is not a rendering of the config file's path. The probe is handed a parsed
`factory/controlplane/config.py:114` — `ControlPlaneConfig`, which carries no
path — `factory/controlplane/config.py:230` — `load_controlplane_config` computes
the label at `factory/controlplane/config.py:238` and keeps it only for its own
error messages — and the only other way to a path is the `resolve_config_path()`
call FR-007 forbids. What the verdict names is the source the resolution carries.

## User Scenarios & Testing

### User Story 1 - The probe mints where the attempt will run (Priority: P1)

As an operator verifying an install, the key-management half of the LLM check
runs against the same gateway, with the same credential, as the completion half,
so the verdict is about one machine.

**Why this priority**: P1, and it is the whole defect. Everything US2 renders is
a lie until this is true.

**Independent Test**: gather the probe against a declaration naming one address
and one credential variable, and an environment naming another of each, then read
back the URL every request went to and the credential it went out with.

**Acceptance Scenarios**:

1. **Given** a declaration naming gateway A and the credential variable
   `ERGANE_LLM_MASTER_KEY`, and an environment in which `LITELLM_PROXY_URL` names
   gateway B and `LITELLM_MASTER_KEY` holds a different value, **When** the probe
   gathers, **Then** the key-management client and the completion request both
   address B and neither addresses A, **and both authenticate with the credential
   the resolution chose (`LITELLM_MASTER_KEY`) rather than the declared
   `ERGANE_LLM_MASTER_KEY`** — proven by a committed test that records the base
   URL *and the `Authorization` header* of every request each half issues. The
   declaration MUST name a `master_key_env` the environment does not, because a
   declaration that agrees on the credential leaves FR-001's second clause
   untested and a diff that unifies only the URL — leaving `api_key_env` bound at
   `factory/controlplane/verify.py:433` — then passes this whole story while
   authenticating to one server with another server's key. The recorder is
   `tests/test_controlplane_verify.py:320` — `_loopback_llm_listener` extended to
   keep the header it discards today at
   `tests/test_controlplane_verify.py:343-354`, which is the same double this
   scenario already extends for base URLs. The same recording against today's tree
   shows the mint at B under the resolved credential and the completion at A under
   the declared one, and that transcript is pasted into the diff beside the new
   one. The double that records it MUST subclass
   `factory/usage/litellm_client.py:108` — `LiteLLMClient`, so the *before*
   addresses are the ones production resolved rather than ones a from-scratch
   fake invented.
2. **Given** a declaration naming gateway A, with neither `LITELLM_PROXY_URL` nor
   `LITELLM_MASTER_KEY` set, **When** the probe gathers, **Then** both halves
   address A and read the credential variable the declaration names — proven by a
   committed test. **This is the control against the opposite error**: a fix that
   reads the declaration everywhere inverts the defect instead of removing it, and
   `factory/controlplane/resolve.py:334` — `_resolve_endpoint` is the one place
   the order is written down.
3. **Given** a declaration and an environment that agree on both the address and
   the credential variable, **When** the probe gathers, **Then** the snapshot's
   detail is character-for-character what today's tree produces for the same
   inputs, and both halves address the one agreed gateway — proven by a committed
   test that pins the string and records both base URLs. This is the second
   control and it covers every real install: US1 changes which client is built and
   which address it is built for, and no rendered text at all, so if this pin has
   to move for *US1* to pass, US1 is wrong. US2 is the one story permitted to move
   it, and does so in its own diff with the old and the new string both visible.
4. **Given** the one resolution function both halves read — the new sibling —
   replaced by a stub answering gateway C, **When** the probe gathers and
   `resolve_llm_gateway` is called, **Then** the key-management client and the
   completion request both address C **and**
   `factory/controlplane/resolve.py:137` — `resolve_llm_gateway` answers C too —
   proven by a committed test that replaces that one function **by name in every
   module that binds it** — in `factory.controlplane.resolve`, and in whatever
   binding `factory/controlplane/verify.py` holds — and changes nothing else. Two
   `monkeypatch.setattr` lines naming one function are still one symbol: the
   Temporal shape T007 and T008 copy is a from-import at
   `factory/controlplane/verify.py:32` against a module-global call at
   `factory/controlplane/resolve.py:249`, so under it a single patch moves only
   half of this Then; plan trap 16 traces both bindings and the one alternative
   shape that needs a single patch. The first half proves neither part of the
   probe re-derives the address from the parsed declaration; the second is
   FR-002's structural clause, and a diff that adds the sibling while leaving
   `resolve_llm_gateway` assembling its own `GatewayResolution` fails it. This
   scenario does **not** tell one shared read from two calls to the same
   function — replacing the one function moves both — and US1-S1 is what catches
   a half that reads the declaration instead.
5. **Given** a declaration parsed from a config file that is not the default path,
   and a different gateway declared in the file at the default path, **When** the
   LLM probe gathers that parsed declaration, **Then** both halves address the
   gateway the parsed declaration names — proven by a committed test that gathers
   `LLMProbe` directly and fails if `resolve_config_path` is consulted at all
   during the probe. Today the admin half reaches it through `from_env`, which is
   how a verdict could describe a config the operator did not name; no caller
   hands a non-default path yet, so this scenario pins a latent divergence shut.
   The test proves nothing unless its admin-client double subclasses
   `factory/usage/litellm_client.py:108` — `LiteLLMClient`: a from-scratch fake
   carrying its own `from_env`, or a patched `_llm_client_factory`, never reaches
   `resolve_config_path` on today's tree either, so the criterion would go green
   on a diff that changed no production line. The test is therefore pasted
   **failing** against today's tree with the consult recorded, so a vacuous
   version is visible in the diff.
6. **Given** a client built through `factory/usage/litellm_client.py:136` —
   `from_env` under an environment naming gateway B, **When** its `base_url` is
   read, **Then** it is B — proven by a committed test. **This is the third
   control**: it is already true of today's tree, because `from_env` has resolved
   through `resolve_llm_gateway` since 048-US1 landed on 2026-08-16, so its value
   is regression protection rather than proof of the change — the probe's new
   construction path is shown not to have been bought by changing the constructor
   five other modules depend on.

---

### User Story 2 - A verdict names the endpoint and the source that chose it (Priority: P2)

As an operator reading install verification, the line about the gateway tells me
which address answered and which source supplied it, so a green line can be
audited and a red one sends me to a server that was actually called.

**Why this priority**: P2. US1 makes the verdict true; this makes it checkable.
It is the difference between the readiness class being fixed and being believed
to be fixed.

**Independent Test**: gather the probe and read its detail string for the address,
the source and the absence of any credential value.

**Acceptance Scenarios**:

1. **Given** a probe whose key sequence passed, **When** its detail is built,
   **Then** the detail names the gateway address that answered and the source the
   resolution carries for it — the name of the environment variable that won, or
   the declaration label `_DECLARED_SOURCE` at
   `factory/controlplane/verify.py:46` — proven by a committed test asserting both
   substrings. Today the passing text at
   `factory/controlplane/verify.py:523-526` names neither. The detail must not
   name a configuration file path: there is none to name, for the reason
   § "What this spec is not" gives.
2. **Given** a key-management call that failed against the address the resolution
   chose, while a different address is declared, **When** the failure detail is
   built, **Then** it names the address that call was issued to **and** the source
   that chose that address, and the address it was not issued to appears nowhere
   in it — proven by a committed test asserting both presences and the absence.
   US1 already binds `base_url` to the resolved address, so the address half
   arrives inherited; the source clause is US2's work, and a US2 diff that leaves
   all seven message sites unchanged fails this scenario. The committed test
   drives **each of the six reachable branches** and asserts the source clause at
   every one — `issue_key` failing under both classifications
   (`factory/controlplane/verify.py:637` and
   `factory/controlplane/verify.py:641`), `/key/info` failing
   (`factory/controlplane/verify.py:493`), the spend log failing
   (`factory/controlplane/verify.py:519`), the completion timing out
   (`factory/controlplane/verify.py:577`) and the completion erroring
   (`factory/controlplane/verify.py:582`). The seventh site, the key-probe
   fallback at `factory/controlplane/verify.py:544`, is defensive code no input
   reaches — every path to `factory/controlplane/verify.py:539` has already
   assigned a non-empty detail, traced in plan trap 15 — so it is proven by the
   diff carrying its edited source clause rather than by a driving test, and an
   implementer who spends the attempt hunting for a driver has been sent after
   something that is not there. A test reaching three of the seven is how the
   previous five-site enumeration shipped two messages nobody had touched.
3. **Given** `LITELLM_PROXY_URL` naming an address the declaration does not
   carry, **When** the detail is built, **Then** it states that the variable
   overrode the declaration and names both the variable that won and the
   declaration label the probe passed in — proven by a committed test. When the
   environment wins, the resolution carries only the variable's name as its
   source (`factory/controlplane/resolve.py:334` — `_resolve_endpoint` answers
   `EndpointRef(override, PROXY_URL_ENV)`), so the declaration label in this
   sentence is the `source=` argument, exactly as FR-004 words it. An operator whose
   declaration is being silently overridden should learn it here rather than from
   a failed epic.
4. **Given** an environment in which the resolved credential variable holds the
   value `sk-must-not-be-printed`, **When** the detail is built for a passing
   probe and again for a failing one, **Then** neither contains that value and
   both name the variable instead — proven by a committed test asserting the
   absence of the value and the presence of the name. **This is a control**, in
   the sense US1-S2 and US1-S3 are: nothing in
   `factory/controlplane/verify.py:428` — `gather` interpolates the credential
   value today — it reaches only the `Authorization` header at
   `factory/controlplane/verify.py:562` — so a US2 diff that touched no production
   file would pass it. Its worth is regression protection while this story adds
   print statements next to a master key, not evidence that FR-006 was earned;
   US2-S1, US2-S2 and US2-S3 are what force the production change.
   `factory/controlplane/resolve.py:78` — `CredentialRef` exists so that a
   rendering carries the name and never the value.

## Functional Requirements

- **FR-001**: The probe's key-management client and its completion request MUST
  address the same gateway URL and read the same credential variable. Both
  clauses are load-bearing and US1-S1 is the scenario that proves both: a diff
  that unifies the URL and leaves `api_key_env` bound at
  `factory/controlplane/verify.py:433` still authenticates to one server with
  another server's key, and no scenario asserting addresses alone can tell the
  two apart.
- **FR-002**: Both MUST take that URL and that variable name from one function,
  and `factory/controlplane/resolve.py:137` — `resolve_llm_gateway` MUST be
  written in terms of it — the shape
  `factory/controlplane/resolve.py:232` — `resolve_temporal_target` already has
  with respect to `factory/controlplane/resolve.py:252` — `temporal_target_for` —
  so a later edit cannot separate the two readings.
- **FR-003**: The established precedence — environment, then declaration, then a
  refusal naming both routes — MUST be preserved, for the endpoint and for the
  credential variable alike.
- **FR-004**: A probe detail MUST name the gateway address that answered and the
  source the resolution carries for it: the name of the environment variable that
  won, or the declaration label the probe passed in. It MUST NOT name a
  configuration file path, which the probe has no way to know.
- **FR-005**: Every probe message that names a gateway address MUST name the
  address the call was issued to **and** the source that chose it. US1's
  rebinding of `base_url` at `factory/controlplane/verify.py:432` already makes
  the address right at all seven sites; the source clause is what changes at each
  of them. There are seven: `factory/controlplane/verify.py:493`,
  `factory/controlplane/verify.py:519`, `factory/controlplane/verify.py:544`,
  `factory/controlplane/verify.py:577`, `factory/controlplane/verify.py:582`, and
  the two reached through the `base_url` parameter of
  `factory/controlplane/verify.py:625` — `_classify_key_failure` at
  `factory/controlplane/verify.py:637` and `factory/controlplane/verify.py:641`.
  Six of the seven are reachable by an input. The seventh,
  `factory/controlplane/verify.py:544`, is defensive code that renders on no
  input (plan trap 15), so its source clause is required in the diff and is not
  required to be driven by a test.
- **FR-006**: No probe message MAY contain a credential value; a message that
  refers to the credential MUST name the variable instead.
- **FR-007**: The probe MUST resolve from the declaration
  `factory/controlplane/verify.py:1198` — `verify_controlplane_async` already
  parsed, and MUST NOT open a configuration file of its own;
  `factory/controlplane/resolve.py:412` is the fallback that makes a second read a
  different file. The divergence this closes is latent — every CLI route passes
  the default path or nothing — so the requirement is that the second read stop
  existing, not that a reported symptom stop appearing.
- **FR-008**: `factory/usage/litellm_client.py:136` — `from_env` MUST keep its
  present behaviour, and its call sites outside `factory/controlplane/verify.py`
  MUST be untouched. There are six, in five modules, enumerated in plan.md
  § Sizing; `from_env`'s own docstring at
  `factory/usage/litellm_client.py:144-147` says "five production callers", which
  is stale — count the tree, not the docstring.
- **FR-009**: When the environment overrode the declaration, the probe detail MUST
  say so, naming the variable that won and the declaration label the probe passed
  in — FR-004's wording, because a resolution the environment won carries only the
  variable's name as its source.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-007, FR-008]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-009]
```

One `depends_on_merged` edge and no pass-edge. US2 has nothing true to render
until US1 has made one resolution decide both halves — a detail naming "the
address that answered" is meaningless while two addresses answer — so the edge
buys correctness of sequencing. It is also the only thing keeping the two stories
off each other: both edit `factory/controlplane/verify.py`, US1 inside
`_llm_client_factory` and the head of `LLMProbe.gather`, US2 in the seven message
sites and the passing text further down the same method. The edge has a second
job the plan names in trap 11: US1's pinned detail test is US2's to update, and
`depends_on_merged` is what guarantees US2 sees it. Declared rather than left
inferred (069-US2 FR-007).
