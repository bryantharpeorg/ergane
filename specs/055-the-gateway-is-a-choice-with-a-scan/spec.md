---
state: landed
# Attested landed 2026-08-18. US1 336697688230 (#195), US2 30b33aba92db (#196),
# US3 e0cf102891c9 (#197) -- all three observed on ergane-buildout.
#
# Six attempts for three stories, improving as the chain descended: US1 took
# three (attempt 1 lost the boundary gate to the known real-clock concurrency
# flake under cap-2 load -- occurrence 3 of
# ci/flaky-concurrency-test-is-a-random-epic-killer -- and attempt 2 failed the
# judge on US1-S5, a test that asserted the scan result structure but never
# called render_scan_results). US2 took two (long first attempt, retry landed).
# US3 landed on its first attempt, integrating both siblings' surfaces --
# its tests reuse 033's scripted-prompter walkthrough harness, import
# EndpointClassification/ScanResult from US1's scanner, and quote
# DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT from US2's config work.
#
# Committed to git before dispatch (PR #194), applying 054's lesson the same
# night it was learned.
#
# Flipped draft -> ready 2026-08-17 ~10:13 PM CT at the operator's instruction.
# Ready is eligibility, not dispatch: the ordering note below still binds, and
# this epic is not to be started until 054 has landed.
#
# Drafted 2026-08-17 ~10:10 PM CT by an operator session, from two questions the
# operator asked in sequence: whether the LiteLLM gateway is only needed for
# "tokenomics style data" and could be optional, and then whether install could
# "ask for / scan for an existing LLM gateway" and whether anything is actually
# LiteLLM-specific "or just any openai endpoint".
#
# Both were answered against the tree before this was written, and the answers
# are what shape the three stories:
#
#   1. The gateway is doing three jobs, not one. It delivers the agent's
#      credential (`factory/workgraph/adapter.py:774` sets ANTHROPIC_BASE_URL and
#      :775 the minted virtual key), it makes persona->model routing enforceable
#      rather than advisory (`personas.yaml` says so in its own header, because
#      the key's `models` list is derived from the registry), and it attributes
#      spend. Only the third is tokenomics.
#   2. The three are not equally load-bearing. `factory/activities/usage_activities.py`
#      is explicit that "a poll is a read with no consequence ... nothing branches
#      on the number, at any magnitude, because enforcement is deferred (D-021)",
#      while `issue_attempt_key` "opens every attempt"
#      (`factory/workgraph/workflow.py:35`) and "issuance failure is not an
#      attempt". Attribution already degrades safely. Minting does not.
#   3. Yes, it is LiteLLM-specific. `factory/usage/litellm_client.py` calls six
#      endpoints -- `/key/generate`, `/key/info`, `/key/delete`, `/key/list`,
#      `/spend/logs/v2`, `/v1/models` -- and only the last is OpenAI-standard.
#      Independently, the agent CLI is handed `ANTHROPIC_BASE_URL`, so it speaks
#      the Anthropic Messages shape rather than OpenAI chat-completions. LiteLLM
#      serves both; a bare OpenAI-compatible server serves one.
#   4. Nothing in this repository installs LiteLLM. `ergane install` interviews
#      and writes `~/.config/ergane/config.toml`; its only subprocess is
#      `systemctl --user daemon-reload` as a capability probe. So the gap is not
#      that install provisions a gateway instead of finding one -- it is that it
#      asks blind.
#
# Why one spec and not two: a scan is only worth running if a non-LiteLLM answer
# is actionable. Today, discovering an Ollama endpoint lets install say exactly
# one thing, which is no. The discovery and the mode are the same feature seen
# from two ends, and US3 is where they meet.
#
# ORDERING, NOT A PREFERENCE: hold this until 054 has landed. 054's US2 and US3
# are rewriting `factory/controlplane/verify.py` right now, and US1 and US3 here
# land on the same surface.
#
# Numbered 055: 054 a stranger can install Ergane.
---

# Feature Specification: the gateway is a choice, and install can find one

**Created**: 2026-08-17

## What the gateway is actually for

Three jobs, and conflating them is why "is it optional?" has no one-word answer.

| Job | Where it lives | What is lost without it |
| --- | --- | --- |
| Deliver the agent's credential | `adapter.py:774-775` — `ANTHROPIC_BASE_URL` plus a per-attempt, TTL'd virtual key | The agent, which runs `--dangerously-skip-permissions` in a sandbox, holds the operator's real provider key, with no expiry |
| Make persona routing enforceable | the minted key's `models` list is derived from `personas.yaml` | The registry's own header stops being true: the binding becomes advisory |
| Attribute spend | `/key/info`, `/spend/logs/v2` | `ergane usage` has nothing to roll up |

The third is the one the operator asked about, and it is the one that already
degrades safely — `usage_activities.py` says a poll is "a read with no
consequence" and that nothing branches on the number at any magnitude, because
enforcement is deferred. The first two do not degrade. They simply stop.

So: the gateway can be optional, and it cannot be *quietly* optional. A mode that
gives up two security properties has to say which two, in the place the operator
chooses it, and stay observable afterwards.

## Why "any OpenAI endpoint" is not the same question

Two independent reasons, both checked:

1. `factory/usage/litellm_client.py` calls `/key/generate`, `/key/info`,
   `/key/delete`, `/key/list`, `/spend/logs/v2` and `/v1/models`. Five of those
   are LiteLLM's proxy-management API and appear in no OpenAI specification. An
   Ollama or vLLM endpoint will not answer them.
2. The agent CLI is handed `ANTHROPIC_BASE_URL`, so it speaks Anthropic Messages,
   not OpenAI chat-completions.

`/v1/models` is the one call that is standard everywhere — which is exactly why
it makes a good probe, and why a *second* probe is needed to tell a full gateway
apart from an inference endpoint.

## User Scenarios & Testing

### User Story 1 - Install can find the gateway that is already there (Priority: P1)

As an operator installing on a machine that already runs something, I can ask
Ergane what LLM endpoints it can see and what each one can do, instead of typing
a URL from memory.

**Why this priority**: it is the cheapest of the three and it stands alone —
discovery is useful even to an operator who will end up declaring a gateway by
hand, because it confirms the address and the alias list before the interview
commits them.

**Independent Test**: point the scan at a simulated set of endpoints — one
answering `/v1/models` and `/key/generate`, one answering only `/v1/models`, one
answering nothing — and confirm three distinct classifications.

**Acceptance Scenarios**:

1. **Given** a host with an endpoint answering `/v1/models`, **When**
   `ergane install --scan` runs, **Then** it reports the address and the aliases
   that endpoint advertises — proven by a committed test against a simulated
   endpoint.
2. **Given** an endpoint that answers `/v1/models` **and** the key-management
   API, **When** the scan classifies it, **Then** it is reported as dispatchable;
   **Given** one that answers only `/v1/models`, **Then** it is reported as
   inference-only, naming the capability it lacks — proven by a committed test
   covering both.
3. **Given** the scan runs, **When** any endpoint is probed, **Then** no
   credential is sent to it. Discovery is unauthenticated; a key is presented
   only to an address the operator has confirmed — proven by a committed test
   asserting no probe request carries an authorization header. A scan that posts
   the master key to whatever answers a local port hands that key to any process
   that can bind one.
4. **Given** no address is declared, **When** the scan runs, **Then** it probes
   loopback candidates only, and reaching beyond loopback requires the operator
   to name the address — proven by a committed test. Sweeping a network is a
   different act from looking at your own machine and must be asked for.
5. **Given** the scan finds nothing, **When** it reports, **Then** it says so
   plainly and names what it looked for, rather than reporting an empty success.
6. **Given** the diff, **When** the probe is read, **Then** it reaches the
   network only through an injected seam, and no committed test for it opens a
   real socket — proven by a committed test.

---

### User Story 2 - `direct` dispatches, and says what it gave up (Priority: P1)

As an operator with a provider key and no proxy, I can declare
`llm.mode = "direct"` and dispatch, having been told exactly which properties I
am trading away.

**Why this priority**: it is what makes US1's answer actionable. A scan that can
only ever conclude "install LiteLLM first" is a nicer error message, not a
feature.

**Independent Test**: parse a `direct` config, dispatch one attempt against a
simulated provider endpoint, and confirm the attempt runs and the ledger records
it.

**Acceptance Scenarios**:

1. **Given** a config declaring `llm.mode = "direct"` with a base URL and an API
   key environment variable, **When** it is parsed, **Then** it succeeds and
   carries a `direct` block — proven by a committed test. `"direct"` is already a
   recognized token in `KNOWN_LL_MODES`; this story changes what happens after it
   is recognized, not the token list.
2. **Given** a `direct` config, **When** an attempt is dispatched, **Then**
   `issue_attempt_key` still runs and still writes the attempt's ledger row,
   returning the declared static credential instead of a minted one — proven by
   a committed test. The activity must not be skipped: skipping it also skips
   the record that the attempt happened.
3. **Given** a `direct` config, **When** the operator asks what they gave up,
   **Then** the answer is stated at declaration time and remains available
   afterwards — the credential is not per-attempt and does not expire, the
   persona-to-model binding is advisory rather than enforced, and spend
   attribution is unavailable — proven by a committed test asserting all three
   are named.
4. **Given** a `direct` config, **When** `ergane usage` runs, **Then** it reports
   that attribution is unavailable in this mode, rather than returning an empty
   rollup — proven by a committed test. An empty table and an inapplicable
   question look identical and mean opposite things.
5. **Given** the diff, **When** `personas.yaml` is read, **Then** its header no
   longer claims the binding is enforceable without qualification, because in
   `direct` mode it is not — proven by a committed test asserting the registry's
   stated invariant matches the modes the config admits. A file that describes a
   guarantee the code stopped making is worse than one that describes none.
6. **Given** a `direct` config, **When** the declared credential appears in any
   error, log or rendered output, **Then** it is redacted — proven by a committed
   test, holding `direct` to the boundary `litellm_client.py` already holds the
   master key to.

---

### User Story 3 - Install offers the mode the host can actually run (Priority: P2)

As an operator being interviewed, the LLM question is answered with what was
found, and if only one mode is available I am told which and why.

**Why this priority**: P2 because US1 and US2 each stand alone. This is where
they stop being two features.

**Independent Test**: run the interview against each of the three scan
classifications and confirm the offered default and the stated reason differ.

**Acceptance Scenarios**:

1. **Given** a scan that found a dispatchable gateway, **When** the interview
   reaches the LLM question, **Then** that address is offered as the default and
   `gateway` is the offered mode — proven by a committed test.
2. **Given** a scan that found only an inference-only endpoint, **When** the
   interview reaches the LLM question, **Then** `direct` is offered, the address
   is the default, and the reason `gateway` is unavailable names the missing
   key-management capability — proven by a committed test.
3. **Given** the operator chooses `direct`, **When** the interview writes the
   config, **Then** the three surrendered properties from US2-S3 are stated
   before the write, not after — proven by a committed test. A trade disclosed
   after the fact was not offered.
4. **Given** a scan that found nothing, **When** the interview runs, **Then** it
   falls back to asking, exactly as it does today — proven by a committed test.
   Discovery may improve the question; it may never be required to answer it.
5. **Given** any scan result, **When** the operator declares an address by hand,
   **Then** the declaration wins — proven by a committed test.

## Functional Requirements

- **FR-001**: `ergane install` MUST provide a scan that reports LLM endpoints it
  can reach and the aliases each advertises.
- **FR-002**: The scan MUST classify each endpoint as dispatchable or
  inference-only, and MUST name the capability an inference-only endpoint lacks.
- **FR-003**: The scan MUST NOT send a credential to any endpoint it discovers.
- **FR-004**: The scan MUST probe loopback candidates by default, and MUST
  require an explicitly named address to probe anything else.
- **FR-005**: The scan MUST reach the network only through an injected seam.
- **FR-006**: `llm.mode = "direct"` MUST parse and MUST be dispatchable, carrying
  a base URL and an API key environment variable.
- **FR-007**: In `direct` mode `issue_attempt_key` MUST still run and MUST still
  write the attempt's ledger row.
- **FR-008**: `direct` mode MUST state, at declaration time, that the credential
  is neither per-attempt nor expiring, that the persona-to-model binding is
  advisory, and that spend attribution is unavailable.
- **FR-009**: `ergane usage` in `direct` mode MUST report attribution as
  unavailable rather than returning an empty rollup.
- **FR-010**: A credential declared for `direct` mode MUST be redacted from every
  error, log and rendered output.
- **FR-011**: `personas.yaml`'s stated invariant MUST match the modes the config
  admits.
- **FR-012**: The interview MUST offer the mode the scan found the host can run,
  MUST name why an unavailable mode is unavailable, and MUST fall back to asking
  when the scan finds nothing.
- **FR-013**: An operator-declared address MUST override any scan result.

## Success Criteria

- **SC-001**: On a host running an inference-only endpoint and no proxy, an
  operator reaches a dispatched attempt. Evidence is a committed transcript,
  because this is a claim about a running deployment.
- **SC-002**: The count of probe requests carrying an authorization header during
  a scan is zero, asserted by a test rather than by reading.
- **SC-003**: The properties `direct` surrenders are enumerated in exactly one
  place in the code, and the interview, the config error and the documentation
  all render from it — asserted by a test, so the three cannot drift.
- **SC-004**: No test added by this spec opens a real socket.

## Out of Scope

- **Installing or running a gateway.** Unchanged from 054. Ergane declares and
  discovers; it does not provision.
- **Budget enforcement.** Deferred to spec 004 (D-021). This spec makes the
  absence of attribution *visible* in `direct` mode; it does not add enforcement
  to either mode.
- **Serving OpenAI chat-completions to the agent.** The adapter hands the CLI
  `ANTHROPIC_BASE_URL`; whether a second wire format is worth supporting is a
  separate question with its own spec.
- **Network discovery.** FR-004 is deliberate. Loopback by default; anything
  wider is named by the operator, and sweeping a subnet is not a thing an
  installer should do unasked.
- **Making `direct` the default.** It is a documented choice with named costs,
  never the path of least resistance.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-012, FR-013]
```

US1 adds a discovery module and a read-only `--scan` flag. US2 works in
`factory/controlplane/config.py`, the dispatch path and `personas.yaml`. Neither
touches the interview. US3 owns `factory/cli/install.py`'s interview outright and
merge-depends on both, which is the only ordering that keeps three stories off
one file — a dependency edge models what a story needs to *exist*, and the
contention here is a separate reason to declare the same edge.
