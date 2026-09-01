---
state: landed
fixes:
  - agent/the-subscription-refresh-token-is-never-used-so-an-eight-hour-access-token-is-the-factorys-real-uptime
# ATTESTED 2026-09-01 7:10 AM CT by the operator session. All three stories are on
# ergane-buildout, each on its FIRST attempt on the ordinary implementer rung with
# no promotion: US1 ed9aa51 (#417), US2 8d71de4 (#418), US3 01bb717 (#419).
# Confirmed by `ergane spec landed <this dir> --default-branch ergane-buildout`,
# which observes all three.
#
# THE FIRST EPIC BUILT BY KIMI K2.7 CODE, and the throughput question is answered:
# 46, 58 and 54 minutes per story, dispatch 04:14:58Z to final landing 06:53:29Z,
# 2h39m end to end. Yesterday's four Opus-built specs ran 42-67 minutes with a
# median of 54. Indistinguishable on this codebase, unlike the deepseek trial that
# measured 3-8x slower. The judge was `ollama-cloud/glm-5.3` throughout, so the
# lineage doctrine held.
#
# THE EPIC OUTLIVED THE CREDENTIAL IT WAS WRITTEN TO FIX. The operator's OAuth
# access token expired at 04:12:34Z, two minutes before dispatch. Every story then
# built and landed anyway, because the builder rung had moved to a gateway-routed
# model that authenticates with a virtual key. That is not proof of this spec's fix
# -- the fix was not running yet -- but it is a clean demonstration of the
# diagnosis: the same epic dispatched twelve hours earlier would have produced
# 73-byte authentication failures on every rung.
#
# VERIFIED AGAINST ITS OWN TRAPS, by reading the landed diff rather than trusting
# the verdict. Trap 1 held: the token is constructed inside the subscription branch
# of `attempt_env` with a comment naming the trap, and `PASSTHROUGH_ENV` is still
# `("PATH", "LANG", "TERM")`. Trap 2 held: the name appears in BOTH mechanisms --
# the bwrap `--setenv` list and the environment dict. Trap 3 held: no
# `ANTHROPIC_API_KEY` was introduced. US3 shipped a new module,
# `factory/workgraph/credential_status.py`.
#
# PROVEN BY RUNNING IT, not only by its tests. With the token wired into the worker
# environment and the worker rotated onto this code at 2026-09-01T12:07:14Z,
# `credential_status()` returns
# `CredentialStatus(source='oauth_token', expires_at=None, remedies=())` -- naming
# the long-lived token as the source and correctly declining to report the eight-
# hour expiry sitting in the now-unused credential file. That is US3-S1 observed
# live.
#
# WHAT IS STILL UNPROVEN. No subscription-routed attempt has yet authenticated with
# the long-lived token, because the builder rung is currently kimi and reaches the
# gateway instead. The falsifiable test named in `plan.md` -- a subscription attempt
# running past a credential expiry -- still has not been run. Do not record this
# spec's finding as resolved on the strength of this attestation.
#
# FLIPPED TO READY 2026-08-31 9:58 PM CT at the operator's instruction, in the same
# breath as the builder rung moved to `ollama-cloud/kimi-k2.7-code` and the judge to
# `ollama-cloud/glm-5.3`. Both aliases were probe-verified through the gateway
# minutes before the flip, not merely read from `/v1/models`.
#
# DISPATCHED WITHOUT AN INDEPENDENT PRE-DISPATCH REVIEW. The operator's standing
# practice is that a spec is reviewed by someone other than its author before it
# reaches an agent; this one was drafted and flipped inside one session. The
# operator was told and chose to proceed. Recorded here because the next reader
# should weigh this spec's plan accordingly, and because the one design decision
# taken rather than deferred is US1's: the long-lived token is read from the
# WORKER'S OWN ENVIRONMENT, the way `LITELLM_MASTER_KEY` already is, rather than
# from a path declared in `ergane.yaml`. If that is wrong, it is wrong in US1 and
# every later story inherits it.
#
# THE BUILDER RUNG IS NOW IMMUNE TO THE DEFECT THIS SPEC FIXES, and the promotion
# rung is not. `implementer` routes through the gateway and authenticates with a
# virtual key, so the OAuth access token expiring at 2026-09-01T04:12:34Z cannot
# kill it. `opus-closer` and `debugger` remain subscription-routed. A story that
# burns both ordinary attempts after that timestamp escalates into a rung that
# cannot authenticate — which is the failure this spec exists to close, reached by
# a different road.
# DRAFTED 2026-08-31 9:15 PM CT by the operator session, against ergane-buildout at
# 30246c7. Every file:line below was read from that commit after the worker rotation
# and verified, not recalled. A new number: 124 is the highest slot in the corpus.
#
# THE FACTORY'S UNATTENDED UPTIME IS EIGHT HOURS, AND NOBODY CHOSE THAT NUMBER.
# Measured on the worker host 2026-08-31, reading the operator credential (values
# redacted, only timestamps read):
#
#     file mtime             2026-08-31T20:12:34Z
#     expiresAt              2026-09-01T04:12:34Z   <- exactly 8h after mtime
#     refreshTokenExpiresAt  2026-09-29T06:11:05Z   <- 28 days out, ALIVE
#     subscriptionType       max
#
# The access token lives eight hours. The token that could renew it is good for
# another four weeks. The renewal never happens, because the factory has no refresh
# path: grepping `factory/` for refreshToken / refresh_token / expiresAt returns only
# escalation timers, notify deadlines and build-question windows. Nothing reads the
# refresh token. Nothing checks the expiry before dispatching.
#
# THE SEED IS A SNAPSHOT. `_seed_node_home` (`factory/workgraph/adapter.py:859`,
# copy at `:892`) does `shutil.copy2` of the operator credential into each node's
# HOME. Its own docstring records the concern and leaves it unmeasured: "The
# refresh-token rotation behaviour of the provider has not been measured; if
# rotation-on-use is the provider's behaviour, a copy still" -- the sentence trails
# off mid-thought in the source. Either way, a refresh performed inside a node HOME
# dies with that HOME and never reaches the operator's file.
#
# WHY IT PRESENTS AS RANDOM. The operator credential IS refreshed -- silently, by the
# operator using Claude Code interactively. So the factory's real uptime is "eight
# hours after the operator last used Claude Code", which from inside the factory looks
# like an unpredictable expiry, and is why it survives a working day and dies
# overnight.
#
# MEASURED COST. Seven stories killed on 2026-08-31 across specs 095, 101, 119 and
# 120, each attempt producing a 73-byte stdout reading "Failed to authenticate: OAuth
# session expired and could not be refreshed" with no agent process ever started, and
# a 375-minute hole in an otherwise 42-67 minute story cadence. The archived session
# transcript beside one such attempt (119/us1/attempt-3, 06:52:17Z) is EIGHT LINES:
# the CLI started, queued the prompt, hit auth, exited. No model was contacted.
#
# THE REMEDY EXISTS AND WAS PROVEN ON THIS HOST. `claude setup-token` mints a
# long-lived token -- run 2026-08-31 9:00 PM CT on the worker host, output verbatim:
# "Long-lived authentication token created successfully! Your OAuth token (valid for
# 1 year) ... Use this token by setting: export CLAUDE_CODE_OAUTH_TOKEN=<token>".
# Scope `user:inference`. Minting it did NOT disturb the interactive session: the
# operator credential was byte-identical before and after (same md5, same mtime) and
# `claude auth status` still reported `loggedIn: true`. That was a live hypothesis and
# it was falsified by measurement rather than assumed.
#
# AND THE FACTORY CANNOT RECEIVE IT. The token arrives as an environment variable.
# `PASSTHROUGH_ENV` is `("PATH", "LANG", "TERM")` (`:102`), and after bwrap's
# `--clearenv` the only other names set are `ANTHROPIC_BASE_URL`,
# `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `ATTEMPT_ARCHIVE` and the
# git identity variables (`:584-600`). `CLAUDE_CODE_OAUTH_TOKEN` is on neither list,
# so it cannot reach the agent process. `_seed_node_home` writes only `.gitconfig`
# and `.credentials.json`, so there is no settings-file route either. The whole
# defect reduces to a three-name allowlist.
#
# THIS IS NOT THE HALF 095 FIXED, AND THE TWO ARE EASY TO CONFLATE. Spec 095 made a
# pre-agent failure legible and stopped it consuming the ordinary attempt budget
# (`Termination.PRE_AGENT_FAILURE`, `PRE_AGENT_WINDOW_S` at `:122`,
# `max_pre_agent_failures` and `pre_agent_failures_spent` at
# `factory/verify/ladder.py:393`). That work landed and went live in the worker at
# 2026-09-01T00:05:30Z. It makes the death cheap. It does not stop the death. This
# spec is the other half.
#
# NOT IN SCOPE. This spec does not implement OAuth refresh, does not obtain or rotate
# a credential, does not introduce an Anthropic API key or any gateway route for a
# subscription persona, does not change the tmpfs-HOME decision or the gate boundary's
# environment, and does not change `PASSTHROUGH_ENV`'s membership -- widening a
# global allowlist to solve a subscription-only problem is the wrong shape and is
# named as a trap in the plan.
---

# Feature Specification: a credential outlives the night

**Created**: 2026-08-31
**Depends on**: nothing outside this spec.

## The gap, stated precisely

A subscription-routed attempt authenticates with an eight-hour access token that the
factory snapshot-copies from the operator's interactive login and never renews. A
one-year token exists, is available on the same subscription, and cannot reach the
agent because the sandbox's environment allowlist has three names in it.

Three failures follow, in the order they cost a story:

1. **The long-lived credential cannot be delivered.** It arrives as an environment
   variable that `--clearenv` discards.
2. **A dead credential is discovered inside the agent**, as a 73-byte authentication
   error, rather than refused before the sandbox forks.
3. **Remaining runway is invisible.** Nothing on any operator surface says how long
   the factory can still authenticate, so an overnight run is started blind.

## The rule this spec is asking for

**A subscription attempt authenticates with the longest-lived credential the operator
has given the factory, a credential that cannot work is refused before an attempt is
spent, and the operator can see the remaining runway before starting a run.**

### What this spec is not

It is not an OAuth implementation. The factory does not refresh, rotate, or obtain a
credential; it uses what the operator supplies.

It is not an API key. `sk-ant-oat01-` is a subscription OAuth token with scope
`user:inference`. No story may introduce `ANTHROPIC_API_KEY`, and no story may route
a subscription persona through the gateway.

It is not a widening of the environment allowlist. `PASSTHROUGH_ENV` keeps its three
members; what changes is what the subscription branch constructs.

It is not a change to the gate boundary. The gate's tmpfs `HOME` and its environment
are untouched, and a gate has no business holding an inference credential.

## User Scenarios & Testing

### User Story 1 - A long-lived token reaches the agent (Priority: P1)

As an operator, when I give the worker a long-lived token, the agent authenticates
with it instead of with a copied eight-hour credential.

**Why this priority**: P1 and it depends on nothing. It is the delivery mechanism;
without it the other two stories improve the diagnosis of a failure that still
happens.

**Acceptance Scenarios**:

1. **Given** a worker environment carrying a long-lived subscription token, **When**
   a subscription-routed attempt's environment is built, **Then** that environment
   carries the token — proven by a committed test.
2. **Given** that attempt, **When** the sandbox argument vector is constructed,
   **Then** the token survives `--clearenv` and is set inside the boundary — proven
   by a committed test. The environment dict and the bwrap `--setenv` list are two
   separate mechanisms and a name present in only one of them never reaches the
   process.
3. **Given** a worker environment carrying that token, **When** a **gateway**-routed
   attempt's environment is built, **Then** the token is absent — proven by a
   committed test. A gateway persona authenticates with its virtual key and must not
   receive an inference credential it has no use for.
4. **Given** a worker environment carrying no such token, **When** a
   subscription-routed attempt runs, **Then** it behaves exactly as it does today,
   seeding and using the copied credential — proven by a committed test. The token is
   an addition, not a replacement.
5. **Given** a worker environment carrying both a long-lived token and a copied
   credential, **When** the attempt authenticates, **Then** the long-lived token is
   the one used, and the record states which credential source was chosen — proven by
   a committed test. Two credentials with no stated precedence is a coin toss the
   operator cannot debug.
6. **Given** any attempt, **When** the **gate** boundary's environment is inspected,
   **Then** the token is absent — proven by a committed test. The blast radius of a
   credential is bounded to the process that needs it.

### User Story 2 - A credential that cannot work is refused before an attempt is spent (Priority: P1)

As an operator, a dead or expiring credential stops the dispatch with a named remedy
rather than being discovered by an agent that never starts.

**Why this priority**: P1. It is the measured cost — seven stories on 2026-08-31 —
and it is what turns the remaining failure mode from an attempt into a refusal.

**Acceptance Scenarios**:

1. **Given** a copied credential whose recorded expiry has passed and no long-lived
   token, **When** an attempt is prepared, **Then** it is refused before the sandbox
   forks, naming the expiry and both remedies — proven by a committed test. Today the
   failure surfaces as a 73-byte authentication error from inside the agent.
2. **Given** a copied credential whose recorded expiry is in the future, **When** an
   attempt is prepared, **Then** it proceeds unchanged — proven by a committed test.
3. **Given** a long-lived token and a copied credential whose expiry has passed,
   **When** an attempt is prepared, **Then** it proceeds — proven by a committed test.
   The expired file is irrelevant when it is not the credential in use.
4. **Given** a credential whose expiry cannot be determined, **When** an attempt is
   prepared, **Then** it proceeds rather than refusing — proven by a committed test.
   An unreadable expiry is not evidence of a dead credential, and a check that
   refuses on absence converts a working factory into a stopped one.
5. **Given** the refusal, **When** the operator reads it, **Then** it names both
   remedies — the interactive login and the long-lived token — rather than only the
   one that exists today — proven by a committed test.
6. **Given** the refusal, **When** it is recorded, **Then** it is distinguishable
   from an attempt that ran, and does not consume the ordinary attempt budget —
   proven by a committed test. 095 established this shape for pre-agent failures; a
   refusal before the fork is not a weaker case.
7. **Given** an attempt being prepared, **When** the credential check runs, **Then**
   it makes no network call — proven by a committed test. A probe that dials on every
   attempt adds latency to every dispatch and introduces a second thing that can fail.

### User Story 3 - The operator can see the remaining runway (Priority: P2)

As an operator, before I start an unattended run I can see which credential the
factory will use and how long it is good for.

**Why this priority**: P2 — it changes no outcome — but it is the difference between
starting an overnight run and starting a three-hour one. Seven stories died inside a
window that was visible on disk the whole time.

**Acceptance Scenarios**:

1. **Given** a worker configured with a long-lived token, **When** the operator asks
   for credential status, **Then** the answer names the token as the source and does
   not report a misleading eight-hour expiry read from an unused file — proven by a
   committed test.
2. **Given** a worker with only a copied credential, **When** the operator asks,
   **Then** the answer names that source and the remaining validity — proven by a
   committed test.
3. **Given** a worker with neither, **When** the operator asks, **Then** the answer
   says so and names both remedies — proven by a committed test.
4. **Given** any of the above, **When** the answer is rendered, **Then** no
   credential value appears in it — proven by a committed test. A status surface that
   prints a token is a worse defect than the one this spec closes.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

US1 and US2 both change `factory/workgraph/adapter.py` — US1 the environment
construction and the sandbox argument vector, US2 the pre-fork credential check — and
are serialised on file ownership rather than on logic. US3 renders what US2 already
determines and is chained behind it for the same reason: it must not re-derive the
precedence rule US2 establishes.

## Requirements

- **FR-001**: A subscription-routed attempt's environment MUST carry the long-lived
  token when the worker environment supplies one.
- **FR-002**: That token MUST survive `--clearenv` and be set inside the sandbox.
- **FR-003**: A gateway-routed attempt MUST NOT receive the token.
- **FR-004**: An attempt with no long-lived token available MUST behave exactly as it
  does today.
- **FR-005**: When both credential sources are present, the long-lived token MUST be
  used, and the attempt record MUST state which source was chosen.
- **FR-006**: The gate boundary's environment MUST NOT carry the token.
- **FR-007**: An attempt whose only credential is a recorded-expired copy MUST be
  refused before the sandbox forks, naming the expiry and both remedies.
- **FR-008**: A credential whose expiry cannot be determined MUST NOT cause a refusal.
- **FR-009**: The credential check MUST NOT make a network call.
- **FR-010**: A refusal raised by the credential check MUST NOT consume the ordinary
  attempt budget and MUST be distinguishable from an attempt that ran.
- **FR-011**: The operator MUST be able to read which credential source is in use and
  the remaining validity, without any credential value appearing in the output.
- **FR-012**: Every story MUST leave `PASSTHROUGH_ENV`
  (`factory/workgraph/adapter.py:102`) at its three current members, MUST NOT
  introduce `ANTHROPIC_API_KEY`, and MUST NOT route a subscription persona through the
  gateway.

## Success Criteria (summary)

- An unattended overnight run does not die at a credential, because the credential the
  factory holds outlives the night.
- A credential that cannot work costs one refusal naming its remedy, not an attempt.
- An operator can answer "how long can this run unattended?" before starting it,
  rather than after seven stories have died inside the answer.
