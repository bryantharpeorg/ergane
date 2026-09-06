---
state: draft
fixes:
  - verify/dispatch-preflight-reads-the-proxys-advertised-alias-list-never-the-upstream-that-serves
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. P-1 and P-3 of the `ergane-web` consolidated hand-over —
# two of the eight items found AFTER that hand-over closed, and among the few in
# the whole corpus with no prior ledger row anywhere. Both keys were minted into
# this repository's findings store on 2026-09-03 during the triage that produced
# this spec.
#
# OBSERVED FIRING ON THIS HOST DURING THAT TRIAGE, and then observed recovered:
# every alias on the local gateway returned a connection error while `/v1/models`
# still advertised nineteen of them. The upstream outage was transient. The blind
# spot is permanent, and that asymmetry is the finding — a preflight that reads a
# declaration cannot tell a healthy floor from a dead one.
#
# THIS SUPERSEDES A DELIBERATE SCOPING RATHER THAN REPAIRING A DEFECT.
# `specs/006-interpreter-hardening/spec.md:113` states the preflight is "a read of
# `/v1/models` and a key listing" — chosen, not overlooked, as the cheapest fix
# for the most operator time lost. It was the right call for the failure mode 006
# had seen. A ladder whose first rung is a locally-hosted model behind a tunnel is
# a failure mode 006 had not seen. The contract widens knowingly.
#
# WHAT IT COSTS WHEN IT FIRES. Both attempts on the local rung are spent on a
# connection error, the ladder escalates to the cloud rung, and the epic completes
# on a model the operator did not choose to pay for — silently, because nothing on
# the floor says which rung ran. That last clause is spec 127's territory; this
# spec stops the dispatch instead.
#
# NOT IN SCOPE. This spec does not send a credential to a discovered address —
# that is the scan's rule and spec 055 settles it. It does not change the ladder's
# escalation order. It does not attempt to capture a response body for implementer
# attempts, because the CLI adapter never sees one. And it is NOT
# `080-a-probe-tests-the-endpoint-the-attempt-will-use`, which is still `draft`
# and is about `install --verify` minting against one base URL while completing
# against another — adjacent, different, and not to be folded in.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c.
#
# NO ANCHOR HAD MOVED, AND THAT WAS NOT THE POINT. 057 landed four stories
# between 238b494 and 602a92c across 34 files; none of them is a file this trio
# cites, and the last landing on any cited file was 126 on 2026-09-02, before this
# spec was drafted. All fifteen drafted anchors still resolve. Every one is now
# written in the `` `path.py:NN` — `symbol` `` form so the next drift is
# machine-caught rather than prose-checked (symbol-anchor lesson, 2026-09-03).
#
# THE REUSE REQUIREMENT NAMED A CAPABILITY THAT CANNOT RUN. `chat_completion` is
# called by three production paths — `factory/cli/install.py:375`,
# `factory/controlplane/canary/probe.py:261`, `factory/controlplane/verify.py:557`
# — and implemented by no client in this tree; only by test fakes. The first two
# raise `AttributeError` against a real `LiteLLMClient`; the third is guarded by
# `hasattr` and silently falls back to raw `httpx`. The old FR-003 sent the
# implementer to "reach the function at verify.py:548", which is a nested closure
# over four locals. FR-003 now names the seam the tree already assumes. This is an
# unfiled defect found during refinement; filing it is an operator act.
#
# THE COMPARISON REQUIREMENT CONTRADICTED ITS OWN TRAP. The old FR-009 required
# comparing the answered model against the requested alias — precisely the
# comparison plan trap 1 says agrees with itself always. An implementer building
# to that FR would have shipped a check that can never fire, passed the judge, and
# closed a warning-severity key on a defect still running. FR-014 now requires a
# source independent of the request, and US3's scenarios changed with it.
#
# THE PARITY REQUIREMENT WAS FALSE OF THE TREE. The three preflight surfaces do
# not return equal lists: two drop informational findings (126-US1) and the third
# does not, and only two are in the existing parity test. FR-005 and US1-S4 now
# assert what is true — one entry point, no second copy — instead of an equality
# no diff could produce.
#
# THE SLICE-CONTENTION ADVISORY IS RESOLVED BY OWNERSHIP, NOT BY WAIVER. US1 is
# the only story that touches `factory/controlplane/verify.py`, and the tautology
# at `factory/controlplane/verify.py:585` moved into it with the file (FR-009).
# US2 keeps the attempt record and names that file nowhere.
#
# BOTH KEYS KEPT, WHOLE. `...never-the-upstream-that-serves` is FR-001 to FR-009;
# `...the-model-that-answered-against-the-alias-that-was-requested` is FR-010 to
# FR-016. Nothing was removed, and the FR count grew because two of the old nine
# were unbuildable as written.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): trap 3's "benign credential and
# timeout swap" replaced with the closed-client mechanism it actually is, plus a
# new FR-010 that keeps the doctor's probe alive across the `hasattr` flip; the
# answered model re-paired onto the judge's own alias, because the attempt row's
# `model_alias` is the implementer rung's and pairing them files a false finding
# on every attempt; US3's comparison rewritten so an alias echo is silence rather
# than a warning per attempt, and a control added for the two-alias case;
# FR-013/FR-014 given two named values instead of two adjectives; the store's read
# side and `_call`'s missing timeout parameter named in the tasks.
#
# THE REQUIREMENT NUMBERS SHIFTED BY ONE, AND THE MAPPING ABOVE IS SUPERSEDED.
# FR-010 is new and belongs to US1. Key `...never-the-upstream-that-serves` is now
# FR-001 to FR-010; key `...the-model-that-answered-against-the-alias-that-was-requested`
# is now FR-011 to FR-017. No requirement was dropped and no key was removed.
#
# WHICH HALF OF KEY 2 THIS CLOSES, SAID PLAINLY, SO A TRIAGE NEED NOT READ US2-S3.
# The judge's completion is the only response body this factory holds, so FR-011
# to FR-017 close that key for judge routes and for the doctor's own probe. The
# implementer rung — the cost story in the key's own notes — has no observable
# response body in this tree and stays unobservable after this spec lands; FR-014
# records that absence as unobserved rather than as agreement. Closing the key
# on the frontmatter alone would over-read it.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, second pass): the adversarial review
# refuted this trio on four blocking counts and every one is answered below —
# US3 had no credential path, the plan denied that the suite can see FR-010's
# regression, two of the four verdict-building sites went unnamed, and US1-S6
# asserted one transport finding where `check_aliases` returns two. Two ledger
# corrections and a handful of wording fixes ride with them. No FR was added or
# removed; FR-007, FR-009, FR-010, FR-014, FR-015 and FR-017 changed text, US2
# gained a fifth scenario, and every anchor was re-read at 602a92c.
#
# THE "UNFILED DEFECT" SENTENCE ABOVE IS WRONG. IT IS FILED, AND IT IS CRITICAL.
# `chat_completion`'s absence is
# `install/litellmclient-has-no-chat-completion-and-three-call-sites-await-it-so-the-persona-interview-can-never-complete`
# — open, severity critical, and its refs name the same three call sites this
# spec enumerates. Do not file it again: a second row would mint the parallel
# identity the ledger's own notes warn against. FR-003 closes its first half, the
# `AttributeError`. Its second half — the primary pass's `while True` re-prompt
# with no give-up answer in `factory/cli/install.py` — is NOT fixed here, and
# that is why the key stays out of `fixes:`. Declaring it would be the 100/092
# half-fix shape.
#
# AND DEFINING THE METHOD UNMASKS A SECOND CRITICAL RATHER THAN REPAIRING IT.
# `install/the-judge-canary-closes-its-http-client-then-uses-it` is open and says
# so in its own notes: the missing method "raised AttributeError before httpx
# ever checked whether the client was open — two independent bugs in the same
# function, one hiding the other". `factory/controlplane/canary/probe.py:208` —
# `probe_judge_canary` closes the client in a `finally`, and
# `factory/controlplane/canary/probe.py:220` — `probe_judge_canary` then calls
# `judge_canary` on it. FR-010 buys back the doctor's probe and nothing else; the
# canary's client lifetime is out of scope and stays broken, in a different way,
# after this lands. Plan trap 3 claimed the method "repairs judge_canary" — it
# does not, and that sentence is corrected rather than softened.
#
# TWO MORE KEYS ARE TOUCHED AND NEITHER IS DECLARED.
# `verify/the-gateway-probe-discards-the-upstream-error-body-so-a-failed-alias-names-no-cause`
# is closed by consequence once the doctor's alias failure arrives as a
# `LiteLLMError` carrying `factory/usage/litellm_client.py:445` — `_proxy_message`
# instead of a bare `raise_for_status()`; and
# `verify/probe-mints-against-the-resolved-env-gateway-not-the-declared-one` has
# its *internal* disagreement removed, because mint and completion end up on one
# address — without settling which address is the right one. No FR carries either
# whole, so neither is in `fixes:`; both are named in plan trap 3 so the next
# triage reads them rather than re-mints them.
#
# US3 HAD NO CREDENTIAL AND NO ADDRESS. The old FR-015 sent
# `factory/activities/verify_activities.py:493` — `record_verification` to read an
# authenticated `/model/info` from a module whose own docstring
# (`factory/activities/verify_activities.py:54-57`) says `LITELLM_MASTER_KEY`
# "has no path into these calls", whose input carries only a result and a path,
# and which `tests/test_verification_sweep.py:790` —
# `test_this_component_never_names_the_master_key` forbids from even spelling the
# variable. FR-015 now takes the declaration where the credential and the address
# already arrive as data — the judge activity's own `virtual_key` and
# `proxy_url` — and hands the recording path two strings to compare. No network
# call rides the recording path at all, which is also FR-017's bound.
#
# THE SUITE DOES SEE FR-010's REGRESSION, AND THE PLAN SAID IT COULD NOT.
# `tests/test_controlplane_verify.py:1147` —
# `test_verify_llm_gather_against_live_double` drives the real client from
# `from_env` against a loopback listener and asserts `finding.passed is True`;
# its docstring says the client "has no chat_completion path, so the gather falls
# back to httpx". FR-003 makes that false and that test red. It is now named as a
# file US1 must edit and as FR-010's second, independent regression, and the
# operator's `ergane doctor` run is a proof beside it rather than the only one.
#
# A FOURTH VERDICT SITE, AND TWO SCENARIOS THAT COULD PASS ON NOTHING.
# `factory/workgraph/workflow.py:2942` — `_score` and
# `factory/verify/store.py:1261` — `_judge_from_dict` also build a `JudgeVerdict`.
# The first is the judge-unavailable case FR-014's sentinel exists for and no
# scenario covered it; US2-S5 is new. US1-S9's double now has to model httpx's
# closed-client contract, because a fake whose `aclose()` is a no-op —
# `tests/test_controlplane_llm_probe.py:81` — `_AliasRecordingLLMClient` — passes
# the old wording today, before any diff. And US1-S6 now asserts the two
# transport findings `factory/workgraph/preflight.py:857` — `check_aliases`
# actually returns for a dead proxy, instead of one.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, third pass): key 2 dropped from
# `fixes:`, because the frontmatter declared it and then said in the same block
# that declaring it would over-read it; US3's credential premise made falsifiable
# before dispatch instead of swallowed by FR-017's silence rule; FR-016 given a
# stable finding key, a category and a severity; US1's test placement and both
# stories' pasted evidence bounded; trap 6 given the activity ceiling it was
# describing without a number. No FR was added or removed. FR-015 and FR-016
# changed text, US3-S1 names the key, and every anchor added here was read at
# 602a92c.
#
# KEY 2 IS NO LONGER DECLARED, AND THE PARAGRAPH ABOVE IS THE REASON.
# `verify/nothing-compares-the-model-that-answered-against-the-alias-that-was-requested`
# is removed from `fixes:`. That list is the mechanism `ergane findings triage
# --apply` closes a key on, so "closing the key on the frontmatter alone would
# over-read it" and declaring it could not both stand — one of the two sentences
# had to go, and the honest one is the declaration. The key's own notes name the
# implementer attempt as the cost — "every artefact of that attempt records the
# alias, not the model" — and FR-011 to FR-017 reach the judge's completion only.
# The judge half lands here: the answered model recorded on the row, and a
# mis-mapped judge alias reported under one key. The implementer half stays open,
# and it is not unfixable in this tree, which is why leaving the key open is a
# statement rather than a shrug: `factory/usage/litellm_client.py:284` —
# `fetch_spend_log_rows` already drains `/spend/logs/v2` for every attempt lease
# at `factory/activities/usage_activities.py:511` — `_read_final_usage`, and
# LiteLLM records a model on each of those rows. Establishing that shape and then
# comparing it is a successor spec's work; nothing in this trio touches that path.
# The key stays open so the ledger keeps counting a defect that is still running
# on every implementer attempt — the 100/092/118 half-fix shape, and the reason
# this spec declares one key where the draft declared two. Every earlier line in
# this block that maps two keys onto the requirements — "BOTH KEYS KEPT, WHOLE"
# and the renumbering that superseded it — is superseded by this one: one key is
# declared, and the FR range FR-011 to FR-017 now belongs to no declared key.
#
# US3's CREDENTIAL WAS NAMED AND NEVER ESTABLISHED. FR-015 reads `/model/info`
# on the judge's per-attempt virtual key — `factory/workgraph/workflow.py:2926` —
# `_score` sets `virtual_key` from `lease.key` — and nothing in the trio or in
# the tree showed that such a key can read `litellm_params` at all. The one
# `/model/info` reader in this repository authenticates with the gateway master
# key and makes that a first-class precondition:
# `factory/discovery/llm_enrichment.py:75` — `enrich_aliases` reads
# `os.environ.get(master_key_env)` and returns every alias unclassified without
# it — `factory/discovery/llm_enrichment.py:83` — `enrich_aliases`: "no credential
# to reach gateway metadata". A `litellm_params` that is absent or redacted for a
# non-admin key is "a shape the reader does not recognise", which FR-017 turns
# into silence, so US3 could have landed green on a check that can never fire and
# closed a key on it. FR-015 now demands the payload read under that credential as
# committed evidence, plan trap 18 names the redaction hazard and the declared
# second source, and operator step 6 takes the read with a key of that kind
# before US3 is dispatched rather than with the master key from the operator's
# own shell, which would confirm the wrong premise.
---

# Feature Specification: the factory measures the route it dispatched on

**Created**: 2026-09-03
**Depends on**: nothing.

## The gap, stated precisely

Two halves of one shape. **Before** the dispatch, the factory asks the router what
it advertises. **After** it, nothing compares what answered against what was
asked. Both live at the same seam, and both are fixed by making a measurement
where a declaration is read today.

**Before — the preflight reads a declaration.** Four steps:

1. `factory/workgraph/preflight.py:857` — `check_aliases` makes exactly two
   awaited reads: `list_model_ids()` at `factory/workgraph/preflight.py:876` —
   `check_aliases`, and `list_key_aliases()` at
   `factory/workgraph/preflight.py:914` — `check_aliases`.
2. The first is a `GET /v1/models` — **the router's own declaration of what it has
   been configured to route**. A LiteLLM proxy lists every declared alias whatever
   the upstream behind it is doing, so an alias whose upstream is unreachable
   passes that comparison cleanly.
3. Its docstring promises that a read failure is recorded with `transport=True`
   and never a silent pass. That promise is kept — for the *proxy* read. There is
   no read of the thing that will actually serve the tokens. The two reads are
   independent by design, and each has its own transport arm, so a proxy that is
   wholly down returns **two** transport findings rather than one.
4. All three dispatch surfaces inherit the blind spot together, because all three
   call that one function: `factory/activities/roadmap_activities.py:662` —
   `preflight_spec`, `factory/cli/nouns/build.py:359` — `_run_preflight`, and
   `factory/workgraph/cli.py:141` — `_run_preflight`.

**After — the attempt record cannot disagree with itself.** Three steps:

5. A llama.cpp server answers **any** `model` string with `200` and runs whichever
   model it loaded, so a typo in the gateway's alias mapping resolves silently to
   whatever is on the box.
6. The judge's completion is the one route on which this factory ever holds a
   response body, and it throws the answer away: `factory/verify/judge.py:982` —
   `_assistant_content` reads `choices` out of the payload and returns the
   assistant's text, so the payload's own `model` field never leaves the function.
   What survives is two alias fields, both from the request side, and they are
   **not the same request**: `factory/verify/models.py:608` — `JudgeVerdict`
   carries the judge persona's alias, set at `factory/workgraph/workflow.py:2928`
   — `_score`; the attempt row carries the *implementer rung's* alias, set at
   `factory/workgraph/workflow.py:2688` — `_verify` from `routing.model_alias`
   and landing in `model_alias TEXT` at `factory/verify/store.py:258`. On this
   repository's own registry those two disagree on every attempt — `personas.yaml`
   routes the implementer at `ollama-cloud/kimi-k2.7-code` and the judge at
   `ollama-cloud/glm-5.3` — so which alias the answered model is filed beside
   decides whether the record is evidence or noise.
7. The nearest thing to a measurement is a tautology:
   `factory/controlplane/verify.py:585` — `_probe_one_alias` constructs
   `LLMAliasResult(alias=alias, model=alias)`, the answered model set from the
   request. It cannot disagree with itself.

**The capability the fix needs is assumed by three call sites and implemented by
none.** `factory/controlplane/verify.py:557` — `_probe_one_alias`,
`factory/cli/install.py:375` — `_async_probe_one_token` and
`factory/controlplane/canary/probe.py:261` — `judge_canary` all call
`client.chat_completion(request)`. No client in this tree defines that method;
`factory/usage/litellm_client.py:108` — `LiteLLMClient` has `issue_key`,
`get_key_info`, `revoke_key`, `get_spend`, `fetch_spend_log_rows`,
`list_model_ids` and `list_key_aliases`, and every generic request already goes
through `factory/usage/litellm_client.py:409` — `_call`. Only test fakes define
`chat_completion`, which is why three dead call sites have never been noticed —
and why defining it is not free. It is paid for twice:

- the doctor's guarded call site runs *after* its own client has been closed at
  `factory/controlplane/verify.py:535` — `gather`, so the flip must be bought
  back rather than inherited (FR-010); and
- the canary's call site runs after its client has been closed too —
  `factory/controlplane/canary/probe.py:208` — `probe_judge_canary` closes it in
  a `finally` and `factory/controlplane/canary/probe.py:220` —
  `probe_judge_canary` then calls `judge_canary` on it. That is a second filed
  defect, `install/the-judge-canary-closes-its-http-client-then-uses-it`, which
  the missing method has been masking. This spec does not repair it: the
  `AttributeError` becomes a use-after-close and `ergane install`'s persona step
  stays broken, in a way that is now visible rather than confused.

## The rule this spec is asking for

**A preflight exercises what will serve the request rather than what the router
advertises, and an attempt records what actually answered beside the alias that
asked for it.**

The preflight's four cases, complete:

| proxy answers `/v1/models` | alias advertised | completion answers | result |
|---|---|---|---|
| no | — | — | **today's model-list transport refusal, unchanged** — and no probe is attempted |
| yes | no | — | **today's declaration refusal, unchanged** — and no probe is attempted |
| yes | yes | no | **new refusal**, naming the alias, the address and the proxy's own words |
| yes | yes | yes | pass — the dispatch proceeds |

The first row says *model-list* refusal deliberately: the key-list read beside it
has its own transport arm, so a proxy that is wholly down already returns two
findings today and still returns exactly those two afterwards (FR-007).

### What this spec is not

It is not a credential sent to a discovered address. Spec 055 settles that rule
and it is unchanged: probes go to configured endpoints, never to scanned ones.

It is not a change to the ladder. Escalation order, rung composition and every
dial stay exactly as they are. This spec refuses a dispatch earlier; it does not
alter what happens once one starts.

It is not a repair of the judge canary's client lifetime.
`factory/controlplane/canary/probe.py:220` — `probe_judge_canary` uses a client
its own `finally` has already closed, filed as
`install/the-judge-canary-closes-its-http-client-then-uses-it`. FR-010 buys back
the doctor's probe, which is the one this spec breaks by defining the method.
The canary is broken today for a different reason and remains broken; a story
that quietly widened to cover it would be changing two subsystems for two
reasons.

It is not a claim about subscription rungs. `factory/workgraph/preflight.py:835` —
`aliases_to_check` skips any persona that does not route through the gateway
(`factory/config.py:203` — `routes_through_gateway`, which excludes deterministic
personas as well as subscription ones), so a subscription rung contributes no
alias and a completion probe cannot cover it. The ask is scoped to gateway-routed
aliases and says so.

It is not a re-labelling of the attempt row's `model_alias`. That column is the
implementer rung's dispatch attribution, landed by 117-US2, and
`factory/verify/models.py:998` — `compose_result` says in its own docstring that
the alias is only ever the routing's. The answered model is a fact about a
*different* completion and is recorded as such; nothing in this spec may set the
row's `model_alias` from a judge.

It is not a per-attempt key. The probe rides the client the preflight already
holds, on the master key, and mints nothing: a probe key would carry an alias that
the very next check — the first-attempt collision read at
`factory/workgraph/preflight.py:914` — `check_aliases` — tests for collisions, so
a probe whose revocation failed would leave the floor refusing itself. The cost of
that choice is stated rather than hidden: one token per gateway-routed alias per
dispatch, attributed to no node.

## User Scenarios & Testing

### User Story 1 - Preflight exercises what will serve (Priority: P1)

As an operator, a dispatch against a dead upstream is refused before an agent is
paid.

**Why this priority**: P1 and it depends on nothing. It is the half that costs
tokens, and it is the half that was observed firing on this host.

**Independent Test**: Point a gateway alias at an unreachable upstream, run the
preflight, and read the finding.

**Acceptance Scenarios**:

1. **Given** a fake gateway that advertises alias `a` in `/v1/models` and answers
   `POST /chat/completions` for it with a 500, **When** the preflight runs,
   **Then** a committed test asserts it returns a failing finding whose text names
   `a`, the gateway address the completion was posted to, the proxy's own refusal
   words, and the fact that nothing was dispatched.
2. **Given** a fake gateway that advertises and serves every gateway-routed alias
   the graph names, **When** the preflight runs, **Then** a committed test asserts
   the fake recorded one `POST /chat/completions` per alias and the preflight
   returned no finding for any of them.
3. **Given** a graph naming a persona that does not route through the gateway,
   **When** the preflight runs, **Then** a committed test asserts the fake
   recorded no completion for that persona's alias, because a subscription rung
   has no alias for a probe to exercise.
4. **Given** one fixture graph and one fake gateway, **When** each of the three
   preflight surfaces runs, **Then** a committed test asserts each surface's alias
   findings are the ones `check_aliases` returned — equal across the two dispatch
   surfaces the existing parity test already compares, and present unchanged in
   the third — so a second copy of this check cannot be added without a red test.
5. **Given** an alias the proxy does not advertise at all, **When** the preflight
   runs, **Then** a committed test asserts today's declaration-based refusal still
   fires and the fake recorded no completion for that alias — one outage, one
   finding.
6. **Given** a fake gateway that refuses every request, **When** the preflight
   runs, **Then** a committed test asserts the findings returned are exactly the
   two transport findings the two independent reads produce today — the
   model-list read's and the key-list read's, each worded as it is today — and
   that the probe added no third finding on top of them.
7. **Given** a graph naming four served gateway-routed aliases, **When** the
   preflight runs, **Then** a committed test asserts four completions were
   recorded and that the fake held the first one open until the last one arrived,
   so the four overlapped, and the diff issues them through one `asyncio.gather`
   over the served aliases.
8. **Given** the doctor's per-alias probe answering with a payload whose `model`
   differs from the requested alias, **When** the probe result is built, **Then** a
   committed test asserts the result carries the payload's `model`, and carries the
   empty string — not `None` — when the payload reports none, so the tautology at
   `factory/controlplane/verify.py:585` is gone and the field stays
   distinguishable from one nobody set.
9. **Given** a double whose `aclose()` marks it closed and whose subsequent
   `chat_completion` raises `RuntimeError("Cannot send a request, as the client
   has been closed.")` — httpx's own contract, and not an `httpx.HTTPError`, so
   `factory/usage/litellm_client.py:409` — `_call`'s handler cannot see it — and a
   gateway that serves the alias, **When** `factory/controlplane/verify.py:428` —
   `gather` runs its per-alias probe, **Then** a committed test asserts the probe
   reports the alias completed, and the committed diff shows
   `tests/test_controlplane_verify.py:1147` —
   `test_verify_llm_gather_against_live_double` still asserting `finding.passed is
   True` with its docstring's "the client has no chat_completion path" sentence
   rewritten to the path it now takes.

### User Story 2 - The attempt records what answered (Priority: P2)

As an operator reading a build afterwards, I can tell which model actually ran.

**Why this priority**: P2 and it depends on nothing in this spec. It is the half
that costs *truth* rather than tokens, and it is what makes a silent mis-route
visible at all.

**Independent Test**: Complete against an alias whose upstream serves a different
model, and read the attempt record.

**Acceptance Scenarios**:

1. **Given** a judge completion issued under the judge's alias `judge-primary`
   whose response payload reports `model: "qwen3-coder-30b"`, on an attempt whose
   routing dispatched the implementer under a different alias
   `ollama-cloud/kimi-k2.7-code`, **When** the attempt record is written,
   **Then** a committed test asserts the row's answered column carries
   `qwen3-coder-30b`, the verdict on that row carries `judge-primary` as the alias
   that asked for it, and the row's own `model_alias` still carries
   `ollama-cloud/kimi-k2.7-code` — two completions, two aliases, neither
   overwriting the other.
2. **Given** a response payload that reports no `model` field, **When** the record
   is written, **Then** a committed test asserts the answered column holds the
   empty string and is not the requested alias, because a field that falls back to
   the request can never disagree with it.
3. **Given** an attempt with no judge verdict at all — the implementer route,
   whose CLI adapter surfaces no response body — **When** the record is written,
   **Then** a committed test asserts the answered column is stored as SQL NULL and
   reads back as the unobserved sentinel, which is a different value from the
   empty string US2-S2 asserts.
4. **Given** a verification store written before this feature, **When** it is
   opened by the new code, **Then** a committed test asserts the column is added
   in place, the pre-existing rows read back as the unobserved sentinel, and the
   column order of the migrated store equals the column order of a fresh one.
5. **Given** an attempt whose judge activity was unreachable — the
   `JudgeOutcome.UNAVAILABLE` verdict `factory/workgraph/workflow.py:2942` —
   `_score` builds when no response body was ever held — **When** the record is
   written, **Then** a committed test asserts the answered column is the
   unobserved sentinel and not the empty string, and separately that a verdict
   round-tripped through `factory/verify/store.py:1238` — `_judge_to_dict` and
   `factory/verify/store.py:1261` — `_judge_from_dict` keeps that value while a
   stored verdict written before this spec reads back as the sentinel rather than
   raising.

### User Story 3 - A disagreement is a finding, not a silence (Priority: P3)

As an operator, a mis-mapped alias surfaces as a defect rather than as a memory.

**Why this priority**: P3 and it follows US2 because it consumes the field US2
records. Last because it is worthless until the two values can differ.

**Independent Test**: Arrange an alias whose gateway mapping names one upstream
while the response reports a third name, and read the findings store.

**Acceptance Scenarios**:

1. **Given** an attempt whose answered model is `llama-3.1-8b`, whose judge
   completion was issued under alias `judge-primary`, and a gateway declaring that
   alias's upstream as `hosted_vllm/qwen3-coder-30b`, **When** the attempt is
   recorded, **Then** a committed test asserts a finding is reported under the key
   literal `verify/an-alias-answered-with-a-model-its-gateway-does-not-declare`,
   naming the alias, the answered model and the declared upstream — the answered
   name is neither of the two names that alias is allowed to answer with — and
   asserts a second, differently mis-mapped alias files under that same key
   literal, so a key built from the alias cannot pass.
2. **Given** an attempt whose answered model is `qwen3-coder-30b` while the
   gateway declares the issuing alias's upstream as `hosted_vllm/qwen3-coder-30b`,
   **When** it is recorded, **Then** a committed test asserts no finding is
   reported, because the two names differ only by the provider prefix the
   declaration carries and a check that filed this would file one on every healthy
   attempt.
3. **Given** an attempt whose answered model is the issuing alias string itself
   while the declared upstream differs, **When** it is recorded, **Then** a
   committed test asserts no finding is reported, because a proxy that echoes the
   requested alias back has told us nothing the request did not already say — the
   tautology FR-009 deletes, arriving one layer down.
4. **Given** an attempt whose answered model is unobserved, or whose declared
   upstream could not be read because the `/model/info` call failed or timed out,
   **When** it is recorded, **Then** a committed test asserts no finding is
   reported, the verdict is returned unchanged and the attempt row is still
   written, because absence of evidence must not be filed as evidence of
   mis-routing and a diagnostic may not break a recording.
5. **Given** an attempt whose judge alias and implementer alias name different
   models — this repository's own registry, judge `ollama-cloud/glm-5.3` against
   implementer `ollama-cloud/kimi-k2.7-code` — and an answered model agreeing with
   the judge alias's declared upstream, **When** it is recorded, **Then** a
   committed test asserts no finding is reported, because the comparison is made
   against the alias that issued the completion and never against the row's
   `model_alias`.

The inputs, complete. "The alias" throughout is the one that issued the completion
the answer came from — the judge's — never the attempt row's:

| answered model | the issuing alias's declaration | result |
|---|---|---|
| equals the declared upstream, provider prefix aside | read | nothing reported |
| equals the alias string itself | read | nothing reported — the proxy echoed the request |
| a third name, matching neither | read | **finding**, naming alias, answered model and declared upstream |
| empty — the payload reported none | read | nothing reported |
| unobserved — no response body was held | — | nothing reported, recording unaffected |
| any | unreadable | nothing reported, recording unaffected |

## Functional Requirements

- **FR-001**: The dispatch preflight MUST post a bounded one-token completion for
  every gateway-routed alias the graph names that the `/v1/models` read confirmed
  served, and MUST return a failing finding for any alias whose completion does
  not answer.
- **FR-002**: That finding MUST name the alias, the gateway address the completion
  was posted to and the proxy's own refusal text, and MUST state that nothing was
  dispatched.
- **FR-003**: The completion MUST be issued through one method on
  `factory/usage/litellm_client.py:108` — `LiteLLMClient` — the client all three
  preflight surfaces already hold, and the call three production paths already
  make against a method no client defines — rather than a fourth spelling of "post
  one token and see".
- **FR-004**: Personas that do not route through the gateway MUST NOT be probed,
  preserving the filter `factory/workgraph/preflight.py:835` — `aliases_to_check`
  already applies.
- **FR-005**: All three preflight surfaces MUST obtain the new check from
  `factory/workgraph/preflight.py:857` — `check_aliases` and none MUST add its own
  copy; the existing two-surface parity test MUST be extended to cover it, and the
  third surface MUST be asserted to carry the same alias findings.
- **FR-006**: An alias the proxy does not advertise MUST still produce today's
  declaration-based refusal and MUST NOT also be probed.
- **FR-007**: When the `/v1/models` read itself fails, no completion MUST be
  attempted and the probe MUST add no finding of its own. An unreachable proxy is
  already refused by that read with `transport=True`, and by the independent
  key-list read beside it: `factory/workgraph/preflight.py:857` — `check_aliases`
  returns **two** transport findings for a wholly dead proxy today, and this spec
  MUST leave both of them worded exactly as they are and add no third.
- **FR-008**: The completions MUST be issued concurrently over the served aliases,
  so the preflight's added wall time is one completion rather than one per alias.
- **FR-009**: The per-alias probe result MUST carry the `model` string the response
  payload reported, and MUST carry the empty string — never `None`, which the
  field's `str | None` type would otherwise allow and which is indistinguishable
  from nobody having set it — when the payload reports none, replacing
  `LLMAliasResult(alias=alias, model=alias)` at
  `factory/controlplane/verify.py:585` — `_probe_one_alias`.
- **FR-010**: Defining that method MUST NOT break the probe that already calls it
  under `hasattr`: the doctor's per-alias completion probe MUST hold an open client
  when it runs, because `factory/controlplane/verify.py:535` — `gather` closes the
  one it built before `factory/controlplane/verify.py:557` — `_probe_one_alias` is
  ever called. The client MUST still be closed on the early return at
  `factory/controlplane/verify.py:539` — `gather`, which leaves the function
  before the probe loop at `factory/controlplane/verify.py:594` — `gather` is
  reached, so "move the close below the loop" MUST NOT become a leak on the
  key-probe failure path. Two committed tests MUST hold this: one asserting a
  served alias still completes against a double whose `aclose()` makes later
  requests raise the way httpx's does, and
  `tests/test_controlplane_verify.py:1147` —
  `test_verify_llm_gather_against_live_double`, which drives the real client
  against a loopback listener and MUST still assert `finding.passed is True`.
- **FR-011**: The judge's completion MUST carry the `model` string its response
  payload reported out of the response parse and onto the verdict it returns,
  beside `factory/verify/models.py:608` — `JudgeVerdict`'s existing `model_alias`,
  which is the alias that completion was issued under.
- **FR-012**: The attempt record MUST store that answered model as a column
  appended last in both the fresh schema and the migration, recorded as a fact
  about the judge's completion; `factory/verify/models.py:946` —
  `VerificationResult`'s `model_alias` MUST keep carrying the routing's alias as
  `factory/workgraph/workflow.py:2688` — `_verify` sets it, and MUST NOT be set
  from a judge.
- **FR-013**: The answered value MUST be the empty string when the payload reported
  no model string, and MUST NOT default to the requested alias.
- **FR-014**: An attempt the factory holds no response body for MUST record the
  answered value as a sentinel meaning unobserved, stored as SQL NULL the way
  `factory/verify/store.py:1024` — `_result_values` stores `UNKNOWN_BUILDER`, and
  that sentinel MUST be distinguishable from the empty string of FR-013; rows
  written before this column MUST read back as that sentinel. The verdict
  `factory/workgraph/workflow.py:2942` — `_score` builds when the judge activity
  was unreachable MUST carry that same sentinel, because no response body was ever
  held on that path. And the verdict's own codecs —
  `factory/verify/store.py:1238` — `_judge_to_dict` and
  `factory/verify/store.py:1261` — `_judge_from_dict` — MUST round-trip the field,
  the read side defaulting an absent key to the sentinel the way
  `factory/verify/store.py:1281` — `_judge_from_dict` already defaults
  `gates_shown`, so a verdict stored before this spec reads back rather than
  raising `KeyError`.
- **FR-015**: The disagreement check MUST compare the answered model against the
  upstream the gateway declares for **the alias that issued the completion the
  answer came from** — `factory/verify/models.py:608` — `JudgeVerdict`'s
  `model_alias` — read from `/model/info`'s `litellm_params`. That read MUST be
  made where the address and the credential already arrive as data:
  `factory/activities/verify_activities.py:430` — `run_judge` holds
  `factory/activities/verify_activities.py:420` — `RunJudgeInput`'s `virtual_key`
  and `proxy_url`, which is the same pair
  `factory/verify/judge.py:942` — `_complete` authenticates the completion with,
  and the declared upstream MUST ride out on the verdict beside the answered
  model. `factory/activities/verify_activities.py:493` — `record_verification`
  MUST make no network call and MUST name no credential: its input carries only a
  result and a spec path (`factory/activities/verify_activities.py:467` —
  `RecordVerificationInput`), its module docstring at
  `factory/activities/verify_activities.py:54-57` states that
  `LITELLM_MASTER_KEY` has no path into these calls, and
  `tests/test_verification_sweep.py:790` —
  `test_this_component_never_names_the_master_key` refuses a module that so much
  as spells it. That credential is the attempt's own virtual key —
  `factory/workgraph/workflow.py:2926` — `_score` sets `virtual_key` from
  `lease.key`, the short-TTL key `factory/usage/litellm_client.py:206` —
  `issue_key` mints scoped to the persona's models — and it is NOT the gateway
  master key the one existing `/model/info` reader in this tree requires
  (`factory/discovery/llm_enrichment.py:75` — `enrich_aliases`). Because a
  non-admin key may be served a payload whose `litellm_params` is absent or
  redacted, which FR-017 would turn into permanent silence rather than into a
  failure anyone notices, the diff MUST commit as pasted evidence one
  `/model/info` entry read under a key of that kind — the single entry for the
  alias under test, with `api_key` and `api_base` redacted — and the normalisation
  MUST be written against that pasted payload rather than against an invented
  shape. The comparison MUST NOT be made against the attempt row's
  `model_alias`, and MUST NOT be a comparison of the answered model against the
  requested alias string alone. Equality MUST hold when the two differ only by the
  provider prefix the declaration carries.
- **FR-016**: A finding MUST be reported only when the answered model matches
  neither the declared upstream nor the issuing alias itself, and MUST name the
  alias, the answered model and the declared upstream in the finding's `refs` and
  `notes`, written through the ledger's existing writer at
  `factory/doctor/store.py:137` — `report`. It MUST be filed under **one stable
  key for every alias and every attempt** —
  `verify/an-alias-answered-with-a-model-its-gateway-does-not-declare`, category
  `verify`, severity `warning` — the way `factory/workgraph/detector.py:419` —
  `_finding_key` files the class rather than the occurrence. The alias and the two
  model names MUST NOT appear in the key: `report` upserts `ON CONFLICT (key)` and
  increments `occurrences`, so a key built from the alias mints a parallel row per
  mis-mapped alias and the recurrence count that decides promotion into the
  constitution never rises above one.
- **FR-017**: Agreement, an answered model that is only the issuing alias echoed
  back, an empty answered model, an unobserved answered model and an unreadable
  upstream declaration MUST each report nothing, and the check MUST NOT fail or
  delay the recording it rides on. The declaration read MUST be bounded — one
  attempt, no retry, under a timeout no longer than the judge activity's own — and
  a read that fails, times out or returns a shape the reader does not recognise
  MUST leave the verdict returned and the attempt row written exactly as they are
  today.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
US2:
  depends_on: []
  implements: [FR-011, FR-012, FR-013, FR-014]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-015, FR-016, FR-017]
```

US1 and US2 are concurrent and share no production file. US1 owns the completion
seam and everything that probes with it — `factory/usage/litellm_client.py`,
`factory/workgraph/preflight.py` and `factory/controlplane/verify.py`, which is
why FR-009's one-line tautology and FR-010's client lifetime travel with US1
rather than with the story whose subject they look like. US2 owns the attempt
record — `factory/verify/judge.py`, `factory/verify/models.py` and
`factory/verify/store.py` — and names `factory/controlplane/verify.py` nowhere.

The one `depends_on_merged` edge is declared rather than left inferred (069-US2
FR-007). US3 compares two values that only US2 makes distinguishable; built
concurrently it would be comparing a field against itself, which is exactly the
no-op trap plan.md records. That declared edge also covers the files US3 reads
from US2's half — the verdict, its codecs and the judge activity — so their
slices cannot race.
