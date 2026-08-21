---
state: landed
# ATTESTED landed 2026-08-20 7:07 AM CT. All five stories are observed on
# ergane-buildout: US1 e5f1ccd (#240), US2 3d7273b (#238), US3 357d227 (#239),
# US4 da44b6e (#241), US5 58f5f77 (#237) -- confirmed with
# `ergane spec landed --default-branch ergane-buildout`.
#
# Attested with some urgency: the roadmap's own view reported this spec as
# `ready (landed=False)` after the 12:05Z tick, and a resumed schedule would have
# re-dispatched five completed stories. Bookkeeping only -- a landed spec is
# skipped by the dispatch predicate, so this narrows the surface and arms nothing.
#
# --- the flip this supersedes, kept for the chain ---
# FLIPPED TO READY 2026-08-19 9:33 PM CT at the operator's explicit instruction,
# after a second review that found one dispatch-blocker (US2-S6/FR-016) and two
# gaps found by running the CLI rather than reading the tree (US2-S5/FR-014,
# US3-S6/FR-015). All 50 cited anchors were re-verified line by line; the full
# suite is green at 3705 passed / 47 skipped.
#
# Drafted 2026-08-19 6:00 PM CT by an operator session, at the operator's
# direction, after a night in which the factory lost three stories to a missing
# `git config user.email` in a fixture.
#
# HELD AT DRAFT DELIBERATELY. 067/068/069 were flipped straight to `ready` and a
# twelve-agent pre-dispatch review then found 68 attempt-costing defects in them.
# This spec goes to `ready` only after the same review comes back clean. That is
# now the rule, not a reaction.
#
# THE OPERATOR'S CONSTRAINT, stated so no implementer widens it: NO ANTHROPIC
# API BILLING. Kimi stays the builder. `implementer` in `personas.yaml` is not
# changed by this spec, by any story in it, at any point. What this spec adds is
# the ABILITY to route specific nodes elsewhere, and one place to route them to
# that costs no per-token API spend.
#
# WHAT IS ALREADY TRUE, verified line by line on 2026-08-19 by reading each cited
# line individually rather than from `grep -A` context -- the miscount that
# produced 067-069's defect list:
#
#   - `factory/workgraph/adapter.py:94`  DEFAULT_EXECUTABLE = "claude"
#     `factory/verify/toolchain.py:112`  DEFAULT_AGENT_RUNNER = "claude"
#     CLAUDE CODE IS ALREADY THE AGENT RUNNER. Every implementer node is already
#     the `claude` CLI in a bwrap sandbox. This spec changes its credentials, not
#     its identity.
#
#   - `factory/workgraph/adapter.py:774`  "ANTHROPIC_BASE_URL": context.proxy_url,
#     `factory/workgraph/adapter.py:775`  "ANTHROPIC_AUTH_TOKEN": context.virtual_key,
#     Those two lines are the whole of what makes a node gateway-billed.
#
#   - `factory/config.py:143`  DETERMINISTIC_AGENT = "none"
#     `factory/config.py:177`  agent: str
#     `factory/config.py:191`  def is_llm(self) -> bool:
#     The `agent` field is LIVE, required (`:145`), parsed (`:245`), and its only
#     semantic today is the binary `is_llm` = `agent != "none"`, which decides
#     whether a persona needs a virtual key. Two consumers only:
#     `factory/workgraph/preflight.py:552` and `factory/controlplane/verify.py:331`.
#
#   - `factory/workgraph/derive.py:79`  _OPTIONAL_KEYS = ("timeout", "depends_on_merged")
#     `factory/workgraph/derive.py:193` timeout_override_s=declaration.timeout,
#     `factory/workgraph/models.py:355`  def resolve_timeout_s(node, persona)
#     A PER-STORY OVERRIDE ALREADY EXISTS, for timeouts, declared in the Work
#     Graph block and resolved persona-first (R8). US1 is that pattern with
#     `persona` in place of `timeout`.
#
#   - `factory/workgraph/derive.py:186`  persona=IMPLEMENTER,
#     Hardcoded. This is the line that makes pinning impossible today.
#
#   - `factory/workgraph/adapter.py:719`  return Path(factory_root) / "homes" / epic_id / node_id
#     `factory/workgraph/adapter.py:740`  (home / ".gitconfig").write_text(config, encoding="utf-8")
#     The per-node HOME and the ONE thing seeded into it.
#
#   - `factory/verify/models.py:114`  class NextAction(StrEnum)
#     Members are PASSED, RETRY, DEBUGGER, ESCALATE, KILLED. There is no rung
#     that promotes a struggling node to a stronger persona.
#
#   - `personas.yaml:143` the `closer` persona already exists -- Opus 5, 1M
#     context window, `skills: [implement, tdd]`, four-hour timeout -- and the
#     string "closer" APPEARS NOWHERE IN `factory/*.py`. It is dead config. Its
#     own comment says why: "Promoting automatically on the third attempt is a
#     separate change: it needs `VerificationConfig.max_attempts` and a ladder
#     rung, both factory code, and therefore a spec." This is that spec.
#     Its alias also 401s today -- probed 2026-08-19, `x-api-key header is
#     required` -- which is the open finding
#     `personas/closer-alias-has-no-credential-behind-it` and is exactly why US2
#     exists: the subscription path reaches a frontier model without the API key
#     the operator does not want to buy.
#
# Filed as findings before drafting: none new. This spec is a capability, not a
# defect fix. The defects it touches are already filed:
#   personas/closer-alias-has-no-credential-behind-it
#   interpreter/persona-skills-are-parsed-validated-and-never-read
---

# Feature Specification: a story can choose who builds it

**Created**: 2026-08-19

## The gap, stated precisely

Every implementer node in this factory is built by the same persona, because
`factory/workgraph/derive.py:186` says `persona=IMPLEMENTER` and nothing can say
otherwise. There is one dial, it is global, and turning it changes every node in
every epic.

That is fine while every node is the same kind of work. It stops being fine the
moment one story is harder than its siblings, or one story needs a model with a
larger window, or the operator wants a stronger builder on the two stories that
keep failing and the house model everywhere else.

Three things are missing, and they compose.

## A story cannot name its builder

The Work Graph block already carries a per-story override — `timeout` becomes
`timeout_override_s` (`derive.py:193`) and resolves persona-first with a story
override (`models.py:355`, R8). The mechanism exists, is tested, and is
documented. It just does not cover the one field that decides who does the work.

## There is nowhere better to route to that does not cost API billing

The `closer` persona exists in the registry with everything a stronger builder
needs, and its model alias returns `401 x-api-key header is required`. Reaching a
frontier model today requires an Anthropic API key and per-token billing, which
the operator has declined.

But **Claude Code is already the runner** (`adapter.py:94`). What makes a node
gateway-billed is two environment variables (`adapter.py:774-775`). A node that
omits them and authenticates with the operator's existing Claude subscription
reaches the same frontier model at no per-token cost.

## The ladder cannot promote a node that is struggling

`NextAction` (`factory/verify/models.py:114`) offers PASSED, RETRY, DEBUGGER,
ESCALATE, KILLED. A node that has failed twice gets the same persona a third
time. The registry has been documenting the missing rung in a comment since it
was written.

## What this spec does not change

**The `implementer` persona is not touched by any story here.** Kimi stays the
builder, on the flat-rate subscription it already uses, for every node that does
not explicitly ask for something else. This spec adds the ability to choose; it
changes no default. A diff that edits `implementer` in `personas.yaml` has
exceeded its scope.

## User Scenarios & Testing

### User Story 1 - A story can name the persona that builds it (Priority: P1)

As an operator, I can write `persona: closer` in one story's Work Graph block and
have that story alone dispatched to that persona.

**Why this priority**: P1, and it is independently useful with nothing else in
this spec — it makes every persona already in the registry reachable per story.

**Independent Test**: derive a graph whose one story declares a persona and
assert that node carries it while its siblings carry the default.

**Acceptance Scenarios**:

1. **Given** a Work Graph block in which one story declares `persona: <name>`,
   **When** the graph is derived, **Then** that node's persona is `<name>` and
   every other node's is the default implementer — proven by a committed test
   asserting both, since a change that sets every node's persona would pass an
   assertion about only the declared one.
2. **Given** a story that declares no persona, **When** the graph is derived,
   **Then** it carries the default exactly as today — proven by a committed test.
3. **Given** a story declaring a persona that the registry does not define,
   **When** the graph is validated, **Then** it is rejected at start naming the
   story and the unknown persona — proven by a committed test. `validate_workgraph`
   already refuses a node whose persona does not resolve; this must reach that
   same refusal rather than failing later at dispatch.
4. **Given** a story declaring a persona whose registry entry resolves no
   timeout, **When** the graph is validated, **Then** it is rejected at start —
   proven by a committed test. This is `resolve_timeout_s`'s existing contract
   (`models.py:355`) and pinning must not create a way around it.
5. **Given** the diff, **When** the new key is inspected, **Then** it is optional
   in the same way `timeout` is — proven by a committed test asserting a block
   with neither key, one key, and both, all derive.
6. **Given** a pinned story, **When** the epic starts, **Then** the persona is
   snapshotted at epic start like every other persona resolution — proven by a
   committed test asserting a registry edit mid-epic does not change the running
   node. `models.py:199` makes this the existing discipline.

7. **Given** a story that has already **landed**, **When** a `persona:` key is
   added to its declaration, **Then** the story is not silently re-opened —
   proven by a committed test. `fingerprint()` (`landed.py:319`) hashes the
   story's raw declaration text, so re-opening is what happens by default and
   costs no code to get wrong; a re-opened landed node branches from a base that
   already contains its work and burns its ladder on an unjudgeable diff. Either
   exclude the key from the fingerprint, or make `validate` warn by name that the
   edit changed a landed story's fingerprint — the diff must say which was chosen
   and why. This is the mechanism behind
   `interpreter/editing-implements-on-a-landed-story-reopens-it-into-an-unwinnable-loop`,
   field-confirmed 2026-08-19, and it decides whether this key can be applied to
   the specs that already exist.

---

### User Story 2 - A persona can declare that it bills to a subscription (Priority: P1)

As an operator, I can declare a persona that runs the Claude Code CLI against my
existing subscription rather than the gateway, so a stronger builder costs no
per-token API billing.

**Why this priority**: P1. Without it, US1 can only route between models the
gateway already serves, and the one frontier alias in the registry returns 401.

**Split note**: this was one story until 2026-08-19, covering the declaration,
the credential, the accounting and the concurrency bound. A pre-dispatch review
called it oversized and it is now US2, US3 and US4. US2 is the routing decision
and touches no credential at all — it is testable end to end without one, which
is exactly why it is separable.

**Independent Test**: dispatch a node whose persona declares the subscription
runner and assert no virtual key is minted and no gateway variables are set.

**Acceptance Scenarios**:

1. **Given** a persona declaring the subscription runner, **When** a node routed
   to it is launched, **Then** neither `ANTHROPIC_BASE_URL` nor
   `ANTHROPIC_AUTH_TOKEN` is present in the agent's environment — proven by a
   committed test asserting over the constructed environment.
2. **Given** the same, **When** the attempt is prepared, **Then** no virtual key
   is minted for it — proven by a committed test. A key minted and unused is a
   live credential with no purpose and an attribution row that will read zero.
3. **Given** a gateway persona, **When** a node routed to it is launched,
   **Then** it gets its virtual key and both gateway variables exactly as today
   — proven by a committed test. This is the control: without it the story is
   satisfiable by removing the variables for everyone.
4. **Given** the split of `is_llm` into the two questions it conflates, **When**
   each of its existing callers runs, **Then** each behaves exactly as today for
   deterministic and gateway personas — proven by a committed test covering both
   call sites. "Spends tokens" and "needs a virtual key" stop being the same
   question the moment a subscription persona exists, and both callers mean only
   one of them.
5. **Given** a subscription-routed node, **When** its argv is constructed,
   **Then** `--model` carries a name the CLI itself accepts rather than the
   registry's gateway alias — proven by a committed test asserting over the
   constructed argv. `argv()` (`adapter.py:931`) passes `context.model_alias`
   verbatim at `:938`, and the registry's `model` field (`config.py:178`) holds
   *proxy* aliases. Measured 2026-08-19 against the signed-in CLI, cleared
   environment, no `ANTHROPIC_*` set:

       --model anthropic/claude-opus-5   exit 1   "There's an issue with the
                                                   selected model ... It may not
                                                   exist or you may not have
                                                   access to it"
       --model opus                      exit 0   "OK"

   So a node built to US2 and US3 as they otherwise stand would authenticate
   correctly and then die on its model name, with a message naming neither auth
   nor the gateway. This spec does not prescribe the fix — a second registry
   field, or a translation at the seam — but the diff must say which was chosen
   and why. This scenario needs no credential, which keeps US2 testable on any
   host.
6. **Given** a graph containing a subscription-routed node, **When** dispatch
   preflight collects the aliases it will check against the gateway, **Then** the
   subscription persona's model is **not** among them — proven by a committed
   test asserting over the collected set. This is the scenario that decides
   whether the epic can dispatch at all, and it follows directly from US2-S5:
   once `--model` carries a name the *CLI* accepts, that name is by construction
   not a name the *proxy* serves. `aliases_to_check` (`preflight.py:544-556`)
   collects `persona.model` for every persona where `is_llm` is true, and
   `check_aliases` refuses any alias absent from `list_model_ids()`
   (`preflight.py:594-614`). Measured 2026-08-19 — the proxy serves 16 aliases,
   every one namespaced (`ollama-cloud/…`, `anthropic/…`, `local/…`); `opus`,
   `claude-opus-5` and `sonnet` are **all absent**, and always will be, because
   they are CLI-side names. A subscription persona declaring one would therefore
   park the whole epic at preflight with a message about an unserved alias,
   pointing the operator at the registry rather than at this split. The same
   applies to the second `is_llm` caller: `ergane install verify`'s `LLMProbe`
   (`factory/controlplane/verify.py:331`) completes a real token per alias and
   would report the subscription persona as broken.

---

### User Story 3 - The subscription credential reaches the sandbox, and only where it should (Priority: P1)

As an operator, a subscription-routed node finds my credential inside its
sandbox, and every other node still cannot see it.

**Why this priority**: P1 and it depends on US2. Routing without a credential
produces a node that starts and immediately refuses; a credential without
routing has nowhere to go.

**Independent Test**: seed a node's home for a subscription persona and assert
the credential is present; do the same for a gateway persona and assert it is
absent.

**Acceptance Scenarios**:

1. **Given** a subscription-routed node, **When** its HOME is seeded, **Then** it
   carries the subscription credential in addition to the `.gitconfig` it already
   gets (`adapter.py:740`) — proven by a committed test asserting what the seeded
   home contains.
2. **Given** a gateway persona, **When** its node's HOME is seeded, **Then**
   **no** subscription credential is present — proven by a committed test. This
   is the control, and it is the one that keeps the exposure narrow: a change
   that seeds the credential for every node has widened exactly what
   `factory/workgraph/adapter.py`'s own trap 13 exists to prevent.
3. **Given** a subscription persona and no credential available on the host,
   **When** the node is dispatched, **Then** it is refused by name before the
   sandbox forks — proven by a committed test. `ToolchainError`'s precedent: a
   named refusal before the fork, not a diffless `agent_error` afterwards.
4. **Given** the credential's location, **When** it is resolved, **Then** it is
   discovered rather than hardcoded — proven by a committed test that moves it
   and asserts discovery still succeeds. Where the CLI keeps its credential is a
   host fact, and a literal path encodes one machine on one afternoon.
5. **Given** an unauthenticated subscription node that nonetheless reaches the
   sandbox, **When** the CLI refuses, **Then** the attempt is recorded as a
   named authentication failure rather than as an empty diff — proven by a
   committed test. Measured 2026-08-19: the CLI exits **1** and prints
   `Not logged in · Please run /login` **on stdout, not stderr**. A caller
   watching stderr sees a silent, diffless success.
6. **Given** an attempt that can outlive its own access token, **When** the
   credential's placement is chosen, **Then** the diff names the placement and
   its consequence for refresh, and a committed test asserts the placement
   actually made. Measured 2026-08-19: the credential carries both `expiresAt`
   and `refreshTokenExpiresAt`, and the access token had **5.8 hours** of life
   against an `implementer` timeout of **14400s — four hours**
   (`personas.yaml:80`). An attempt outliving its own access token is therefore
   ordinary, not an edge case. A *copy* — the shape US3-S1 describes — puts the
   refreshed token in a directory discarded at teardown, so every attempt
   re-refreshes from the same stored token; and if the provider rotates refresh
   tokens on use, concurrent nodes invalidate each other **and the operator's own
   login on this host**. Copy, bind-mount or broker: the diff must name which and
   why. Nobody has measured the rotation behaviour, so an implementer who cannot
   establish it must say so rather than assume the benign case.

---

### User Story 4 - A subscription attempt is honest in the ledger and bounded in flight (Priority: P2)

As an operator, an attempt that spent no gateway tokens says so rather than
reporting zero, and my one subscription is not hammered by parallel nodes.

**Why this priority**: P2 and it depends on US2. The factory works without it;
the ledger lies without it. Splitting it out means US2 and US3 can land while
this is still being argued about.

**Independent Test**: record a subscription attempt and assert the ledger row is
distinguishable from a genuinely free one.

**Acceptance Scenarios**:

1. **Given** a subscription node's attempt, **When** it is recorded in the
   ledger, **Then** it is marked as carrying no gateway spend data rather than
   recorded as costing zero — proven by a committed test asserting the recorded
   marker. A row that says `$0` is indistinguishable from a free call and will be
   read as one.
2. **Given** a gateway node's attempt, **When** it is recorded, **Then** it is
   recorded exactly as today — proven by a committed test. The control.
3. **Given** more subscription-routed nodes than a declared concurrency limit,
   **When** they are dispatched, **Then** no more than the limit run at once —
   proven by a committed test. A virtual key isolates concurrent nodes; one
   subscription does not, and its rate limits are per-account.
4. **Given** no declared limit, **When** subscription nodes are dispatched,
   **Then** the behaviour is the documented default and is stated — proven by a
   committed test. An unbounded default here is a decision, not an oversight, and
   must be made on purpose.

---

### User Story 5 - The ladder can promote a struggling node to a stronger persona (Priority: P2)

As an operator, a node that has failed its ordinary attempts is retried by a
stronger persona before I am paged, instead of being handed to the same builder
again.

**Why this priority**: P2. US1 and US2 make the stronger builder reachable and
routable by hand; this makes it automatic. Valuable, and the least urgent of the
three.

**Independent Test**: drive a node's history to the point the new rung should
fire and assert the decided action names the stronger persona.

**Acceptance Scenarios**:

1. **Given** a node whose ordinary attempts are spent, **When** the next action
   is decided, **Then** it is a promotion to the configured stronger persona
   rather than an escalation — proven by a committed test asserting the returned
   action.
2. **Given** a node that has already used its promotion, **When** the next action
   is decided, **Then** it escalates as today — proven by a committed test. The
   rung is bounded like the debugger's (`ladder.py:60`, `_debugger_cycles_spent`).
3. **Given** a configuration that declares no promotion persona, **When** the
   next action is decided, **Then** the ladder behaves exactly as today — proven
   by a committed test. Every existing ladder test must pass unchanged.
4. **Given** the promotion rung, **When** its budget is inspected, **Then** it is
   operator-settable in the same place as `max_attempts`, `max_judge_retries` and
   `debugger_cycles` — proven by a committed test asserting the key is honoured.
   `factory/verify/factory_yaml.py`'s `_LADDER_KEYS` is where those three live; a
   fourth dial that is not settable there repeats the
   `max_recovery_cycles` defect filed on 2026-08-19.
5. **Given** a promoted attempt, **When** it is recorded, **Then** it is
   distinguishable in the attempt history from an ordinary attempt and from a
   debugger cycle — proven by a committed test. `_attempts_spent` and
   `_debugger_cycles_spent` partition history on `persona`; a third rung that is
   invisible to that partition corrupts both counts.

---

### Edge Cases

- **A pinned persona that is also the promotion target.** A node already built by
  the stronger persona has nothing to promote to; the rung must skip rather than
  promote to itself.
- **A subscription credential that expires between attempts.** It presents as an
  auth failure at launch, which is 067/US2's launch-versus-attempt distinction.
  Until 067 lands it will consume an attempt, and this spec should not duplicate
  that fix.
- **A credential that expires *during* an attempt.** Not the case above, and not
  a launch failure at all: the CLI is already running and refreshes itself. With
  a four-hour timeout against a token measured at 5.8 hours of life, this is the
  common case rather than the rare one. US3-S6 is where it is decided.
- **A deterministic persona (`agent: none`) named in a `persona:` key.** It spends
  no tokens and needs no worktree; pinning a producing story to it must be
  refused at validation rather than dispatched to nothing.
- **Two subscription nodes and a limit of one.** The second waits rather than
  failing; a rate-limit rejection is not a code defect and must not be priced as
  one.

## Requirements

### Functional Requirements

- **FR-001**: A story's Work Graph block MUST accept an optional persona
  declaration, optional in the same way `timeout` is.
- **FR-002**: A node MUST carry the declared persona, and a node that declares
  none MUST carry the default implementer.
- **FR-003**: A declared persona that the registry does not define, or that
  resolves no timeout, MUST be rejected at epic start naming the story.
- **FR-004**: A pinned persona MUST be snapshotted at epic start, like every
  other persona resolution.
- **FR-005**: A persona MUST be declarable as running against an operator
  subscription rather than the gateway, expressed on the existing `agent` field
  in the manner of `DETERMINISTIC_AGENT` (`factory/config.py:143`).
- **FR-006**: A subscription-routed node MUST be launched with neither
  `ANTHROPIC_BASE_URL` nor `ANTHROPIC_AUTH_TOKEN`, and MUST have no virtual key
  minted.
- **FR-007**: A subscription-routed node MUST have its credential seeded into its
  own per-node HOME, and a gateway-routed node MUST NOT.
- **FR-008**: A missing subscription credential MUST be a named refusal before
  the sandbox forks.
- **FR-009**: A subscription attempt MUST be recorded as carrying no gateway
  spend data, distinguishably from an attempt that cost zero.
- **FR-010**: Concurrent subscription-routed nodes MUST be bounded by a declared
  limit.
- **FR-011**: The ladder MUST offer a bounded promotion rung to a configured
  stronger persona before escalating, MUST behave exactly as today when none is
  configured, and its budget MUST be operator-settable alongside the existing
  ladder dials.
- **FR-012**: A promoted attempt MUST be distinguishable in attempt history from
  an ordinary attempt and from a debugger cycle.
- **FR-013**: A subscription-routed attempt whose credential is present but not
  usable — expired, revoked, or logged out — MUST be recorded as a named
  authentication failure rather than as an attempt that produced no diff.
  FR-008 covers the credential being *absent* and is checkable before the fork;
  this covers it being *present and refused*, which is only observable after it.
- **FR-014**: A subscription-routed node MUST be launched with a `--model` value
  the CLI accepts, never a gateway alias passed through unchanged. The registry's
  `model` field holds proxy aliases, and `argv()` passes it verbatim today
  (`adapter.py:938`).
- **FR-015**: The seeded credential's placement MUST be chosen with respect to
  token refresh and stated in the diff, and a node's refresh MUST NOT be capable
  of invalidating the operator's own session on the worker host.
- **FR-016**: A subscription-routed persona's model MUST NOT be checked against
  the gateway's served-alias list — neither by dispatch preflight nor by install
  verification. It names a model the CLI resolves, not one the proxy serves, so
  checking it there refuses an epic that would have run.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-014, FR-016]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-007, FR-008, FR-013, FR-015]
US4:
  depends_on: [US2]
  implements: [FR-009, FR-010]
US5:
  depends_on: []
  implements: [FR-011, FR-012]
```

The edges are logical, not merely contentious: US3 seeds a credential only for
nodes US2 taught the system to recognise, and US4 records and bounds attempts it
cannot identify until US2 lands. US2 and US3 also both edit
`factory/workgraph/adapter.py`, so the edge is doing two jobs at once — which is
fine, but means it must not be removed on the grounds that "the files could be
kept apart".

US1 and US5 are genuinely independent of all of this and of each other: US1 is
derivation, US5 is the ladder.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Derive a real spec with one story pinned and paste the resulting
  node personas for every node in the graph.
- **SC-002**: Dispatch a subscription-routed node and paste the constructed
  environment with the credential redacted, showing neither gateway variable is
  present.
- **SC-003**: Paste the control: a gateway-routed node in the same epic, showing
  both variables present and no subscription credential seeded.
- **SC-004**: Paste the ledger row for a subscription attempt, showing the
  no-spend-data marker rather than a zero, beside a gateway row from the same
  epic.
- **SC-005**: Drive a node to the promotion rung and paste the decided action,
  then exhaust the promotion and paste the escalation.
- **SC-006**: Run the existing ladder suite unchanged with no promotion persona
  configured and paste the result. Every test must pass.
- **SC-007**: Paste the unauthenticated case: a subscription-routed node whose
  credential is absent or expired, showing the named refusal rather than a
  diffless attempt. The CLI's own behaviour is measured in the plan — exit 1,
  message on stdout — so this criterion is checkable against a known answer.
- **SC-008**: Paste the constructed argv for a subscription-routed node showing
  the `--model` value the CLI accepts, beside a gateway node's argv from the same
  epic showing its proxy alias. Both are checkable against the answers measured
  in US2-S5.
- **SC-009**: Paste the chosen credential placement and state, in one sentence,
  what becomes of a token refreshed at hour three of a four-hour attempt.
- **SC-010**: Paste the alias set dispatch preflight collects for a graph holding
  both a gateway node and a subscription node, showing the gateway node's alias
  present and the subscription node's absent. This is the criterion that proves
  the epic can dispatch at all.

## Assumptions

- The operator has a working Claude Code subscription on the worker host. Where
  its credential lives is a host fact the implementer must discover rather than
  assume, in the manner of `factory/verify/toolchain.py`.
- **The CLI authenticates from a seeded credential inside the factory's own
  sandbox. This is no longer an assumption — it was run on 2026-08-19 and both
  the positive case and its control are pasted in the plan's Sizing section.**
  That was the single largest unknown in this spec and it resolved in the
  favourable direction: no `~/.claude.json`, no onboarding state and no extra
  environment variable is needed beyond the credential file itself.
  **What the spike did not cover, so that nobody reads it as wider than it is:**
  it ran one trivial prompt to completion. It did not pass `--model` (US2-S5), and
  it was far too short to reach a token refresh (US3-S6). Both were found
  afterwards, on 2026-08-19 evening, by running the CLI again rather than by
  reasoning about it.
- `implementer` stays on `ollama-cloud/kimi-k2.7-code`. Nothing in this spec
  changes it, and the operator has explicitly declined Anthropic API billing.
- Seeding a credential into a node HOME is a deliberate, narrow exception to the
  rule that no operator credential reaches an agent
  (`factory/workgraph/adapter.py`, trap 13). It applies only to personas that
  declare the subscription runner, and **US3-S2** is the test that keeps it
  narrow.
- 067/US2's launch-versus-attempt distinction is not duplicated here.
