---
state: draft
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
- **A subscription credential that expires mid-epic.** It presents as an auth
  failure at launch, which is 067/US2's launch-versus-attempt distinction. Until
  067 lands it will consume an attempt, and this spec should not duplicate that
  fix.
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

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006]
US3:
  depends_on: [US2]
  implements: [FR-007, FR-008, FR-013]
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
- `implementer` stays on `ollama-cloud/kimi-k2.7-code`. Nothing in this spec
  changes it, and the operator has explicitly declined Anthropic API billing.
- Seeding a credential into a node HOME is a deliberate, narrow exception to the
  rule that no operator credential reaches an agent
  (`factory/workgraph/adapter.py`, trap 13). It applies only to personas that
  declare the subscription runner, and **US3-S2** is the test that keeps it
  narrow.
- 067/US2's launch-versus-attempt distinction is not duplicated here.
