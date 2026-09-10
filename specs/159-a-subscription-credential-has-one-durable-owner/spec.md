---
state: draft
---

# Feature Specification: a subscription credential has one durable owner

## Provenance and operator decision

This spec closes audit findings F1–F3 and the refresh-ownership scope explicitly
deferred by landed spec 155. It does not claim that 155 promised persistence.
Official managed-account automation guidance requires file-backed ChatGPT-managed
credentials, persistence of Codex's refreshed file, a trusted private runner, and
one machine or serialized job stream per credential. It recommends API keys for
ordinary automation; this spec does not reinterpret the operator's subscription
decision as permission to choose API billing.

On 2026-09-09 the operator approved an operator-created factory login session
and credential directory separate from interactive Codex, owned by one serialized
stream on one trusted host. The eligible private pilot is still unnamed, and no
login or account-backed qualification has been performed. This spec remains
draft pending a promotion decision; its synthetic implementation is separable
from the held real account qualification in 161.

The later subscription use is an automatic ladder-selected upper rung, matching
the operator's prior Claude subscription arrangement. The configured ladder
and persona snapshot select Codex, its subscription route, model, and attempt
limits. No additional per-use approval action is part of this feature.

### User Story 1 - Subscription means validated managed ChatGPT authentication (Priority: P1)

As an operator selecting the subscription route, I know before launch that the
declared source is structurally eligible managed ChatGPT state and not an API key
or implicit fallback; actual account usability remains a qualification result.

**Acceptance Scenarios**:

1. **Given** real-shape synthetic credentials for `auth_mode: chatgpt`, API-key mode, external-token mode, malformed JSON, missing refresh data, and inaccessible storage, **When** the subscription credential is resolved, **Then** only the supported ChatGPT-managed shape is admitted and every refusal names the mode/source problem without exposing token values — proven by committed fixture tests.
2. **Given** an explicit credential source is missing while an interactive login exists elsewhere, **When** discovery runs, **Then** it refuses the missing declaration and never falls back to interactive auth — proven by a two-source filesystem test.
3. **Given** expired access with structurally present refresh data, missing/malformed refresh data, and a generation carrying a recorded prior provider revocation from Codex, **When** offline readiness is evaluated, **Then** the first is eligible-to-attempt-refresh, the local defects are refused locally, and only the recorded provider result is called revoked — proven by fixed-clock/status fixtures without calling an OAuth endpoint.
4. **Given** a valid source, **When** provenance is recorded, **Then** it contains only owner id, source kind, credential mode, redacted path identity, and generation; no token, credential JSON, or operator home path crosses workflow state or logs — proven by serialization and credential-sweep tests.

**Why this priority**: The existing file-existence check can silently bill through an API-key-shaped login while recording subscription usage as unavailable.

**Independent Test**: Resolve all credential fixtures without launching Codex or contacting a provider.

### User Story 2 - One credential owner serializes the effective subscription rung (Priority: P1)

As the factory, I admit at most one active use of a credential generation across
all epics, targets, and deployment shapes on its trusted host while unrelated
gateway work continues.

**Acceptance Scenarios**:

1. **Given** two epics in different targets/deployment shapes resolve the same declared credential identity on one host, **When** both effective rungs choose Codex subscription, **Then** both resolve one host-global owner, exactly one receives a durable lease, and the other waits through replay-safe timers without occupying a blocking file-lock wait — proven by concurrent workflow/activity tests.
2. **Given** the waiting epic also has gateway-routed work ready, **When** subscription admission is busy, **Then** gateway work progresses independently and receives its ordinary virtual-key attribution — proven by a mixed-route workflow test.
3. **Given** a retry or recovery changes runner or route in either direction on one node, **When** admission is decided, **Then** ownership follows the current effective rung rather than the node's original persona, acquiring or releasing exactly once — proven by a bidirectional route-transition test.
4. **Given** cancellation while waiting for admission, **When** the workflow settles it, **Then** no lease, child process, credential candidate, or coding-attempt charge is created — proven by time-skipping cancellation tests.
5. **Given** the same credential is declared on another host or resolves to two operator-state roots on one host, **When** ownership is evaluated, **Then** readiness refuses the unsupported topology rather than treating target-local locks as serialization — proven by owner-manifest tests.
6. **Given** an owner root is group/world accessible, symlinked, wrong-owner, or replaced after declaration, **When** admission opens it, **Then** it refuses before staging and names the ownership/permission invariant without credential bytes — proven by filesystem mutation tests.
7. **Given** an eligible Codex subscription promotion persona and attempt bounds in the epic's configured ladder, **When** ordinary gateway attempts exhaust their bound, **Then** the existing ladder automatically selects that persona and acquires its credential owner without an added approval prompt, while absent, disabled, or exhausted promotion configurations grant no subscription attempt — proven by configuration-driven workflow tests preserving the existing ladder order and failure escalation.

**Why this priority**: The current per-epic count of original personas is neither credential-wide nor rung-aware.

**Independent Test**: Run two workflow instances over one fake owner store and a separate gateway rung; inspect leases and attempt history.

### User Story 3 - An attempt is fenced before route state can change (Priority: P1)

As the credential owner, I prove no old or terminating child can still modify
staged state before I inspect a candidate or release the credential.

**Acceptance Scenarios**:

1. **Given** a prior child or process handle survives, **When** a new owner lease begins, **Then** the owner reaps or fences that child before reading or staging its candidate and refuses when death cannot be proved — proven by ordered-call and surviving-orphan tests.
2. **Given** a leased generation, **When** an attempt starts on gateway, subscription, then gateway in the same node home, **Then** each attempt materializes exact route configuration: gateway provider without auth file, subscription auth without gateway provider, and gateway again without subscription residue — proven by same-home tests.
3. **Given** a current child exits normally, fails, times out, or is cancelled with descendants, **When** finalization begins, **Then** the ordered contract is terminate process group, prove reap/fence, then read the candidate; inability to prove death quarantines the untouched candidate and retains the lease for recovery — proven by ordered-call and real local process tests.

**Why this priority**: Reading a candidate while any child can still write it makes every later validation and journal guarantee illusory.

**Independent Test**: Exercise prior and current process fencing plus bidirectional route materialization with synthetic state and local child groups.

### User Story 5 - Refresh results become the next durable generation (Priority: P1)

As the credential owner, I let Codex own refresh and preserve the last valid
result across success, failure, cancellation, and crash after the child is dead.

**Acceptance Scenarios**:

1. **Given** a fenced attempt whose Codex child changed structurally eligible managed-auth state, **When** finalization runs after normal exit, failure, timeout, or cancellation, **Then** the candidate is atomically promoted under the owner transaction and becomes the next generation before release — proven by parameterized termination tests.
2. **Given** persistence is interrupted or the candidate is malformed, wrong-mode, stale, or carries a recorded prior provider rejection, **When** recovery runs, **Then** the journal chooses the newest fully committed locally valid generation, quarantines invalid candidates, and never silently restores the bootstrap seed — proven by crash-point tests.
3. **Given** refresh is needed, **When** the attempt executes, **Then** Codex's built-in refresh flow is the only component allowed to contact provider refresh behavior; Ergane neither invokes OAuth refresh endpoints nor rewrites the original operator login — proven by denied-network seams and source guards.
4. **Given** finalization or recovery is replayed, **When** the same generation/candidate intent is processed again, **Then** it commits or quarantines once and releases ownership only after the durable outcome — proven by idempotency-key tests.

**Why this priority**: Copying the seed before every attempt discards refreshed state, while promoting before fencing accepts a still-changing file.

**Independent Test**: Drive the owner journal through termination/replay/crash points after a fake child's fence is proven.

### User Story 4 - Readiness explains the same credential contract everywhere (Priority: P1)

As an operator, install, build preflight, and status agree on credential ownership,
mode, generation, runway, route configuration, and recovery.

**Acceptance Scenarios**:

1. **Given** Claude subscription, Codex subscription, gateway, and no-runner personas, **When** credential status is requested, **Then** a runner-aware shared model reports only the checks applicable to the effective route and preserves Claude's landed token-only behavior — proven by table-driven tests.
2. **Given** busy ownership, invalid current generation, recoverable staged generation, unsupported multi-host topology, or missing explicit source, **When** any readiness surface renders it, **Then** each uses the same stable code, redacted facts, and actionable remedy — proven by contract tests across install, preflight, and build status.
3. **Given** subscription attempts with complete, partial, or absent measurements from their supported runner evidence source and no LiteLLM usage record, **When** readiness and status render, **Then** measured token subtotals and their source/completeness are preserved, missing metrics and subscription dollars remain unavailable rather than free, and credential readiness is not presented as usage evidence — proven by renderer tests.

**Why this priority**: A lifecycle is unsafe if dispatch and onboarding disagree about whether it is usable.

**Independent Test**: Feed one status object to every renderer and compare stable fields and remedy codes.

## Functional Requirements

- **FR-001**: Codex subscription discovery MUST validate file-backed `auth_mode: chatgpt` structure and MUST refuse API-key, external-token, malformed, inaccessible, or locally refresh-incapable sources by name while labeling structural eligibility separately from account qualification.
- **FR-002**: An explicit missing source MUST NOT fall back to an interactive login.
- **FR-003**: Ergane MUST let Codex perform refresh and MUST NOT call OAuth refresh endpoints itself.
- **FR-004**: Credential provenance MUST be redacted and MUST include owner id, source kind, mode, and generation.
- **FR-005**: One host-global owner keyed by declared redacted credential identity MUST admit at most one Codex subscription use across all epics, targets, and deployment shapes on its declared host.
- **FR-006**: Admission MUST use the effective attempt rung and MUST allow unrelated gateway work to progress.
- **FR-007**: Waiting admission MUST use short owner transactions plus replay-safe workflow waiting; it MUST NOT hold a blocking file lock in the async activity loop.
- **FR-008**: Cancellation before admission MUST create no attempt charge, lease, child, or staged credential.
- **FR-009**: Ownership MUST refuse the same credential across hosts or multiple owner roots; a target-local lock MUST NOT count as serialization.
- **FR-010**: The owner MUST reap or fence an earlier child before touching its candidate.
- **FR-011**: Every attempt MUST materialize exact route configuration and remove incompatible residue during gateway/subscription transitions.
- **FR-012**: Finalization MUST terminate and prove the current process group reaped/fenced before reading a candidate and MUST retain recovery ownership if death cannot be proved.
- **FR-013**: Finalization MUST validate and atomically persist a resulting candidate on every termination path before releasing ownership.
- **FR-014**: Recovery MUST use a journaled committed generation and MUST never silently restore the original seed over a later valid generation.
- **FR-015**: A shared runner-aware status contract MUST drive install, preflight, and build status.
- **FR-016**: Claude's token-only subscription behavior from spec 125 MUST remain supported.
- **FR-017**: Subscription usage MUST remain unavailable unless measured; it MUST NOT render as zero or free.
- **FR-018**: Account-backed qualification MUST remain held until the operator approves a credential-owner arrangement and an eligible private pilot target.
- **FR-019**: Invalid or previously provider-rejected candidates MUST be quarantined with redacted evidence and MUST NOT replace the current generation.
- **FR-020**: The host-global owner root MUST be private, non-symlinked, owned by the declared operator identity, and revalidated before admission.
- **FR-021**: An eligible subscription rung MUST execute automatically when selected by the configured ladder and frozen persona snapshot, within existing attempt bounds; credential admission MUST NOT add per-use approval or invent a rung when promotion is absent, disabled, or exhausted.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-020, FR-021]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-010, FR-011, FR-012]
US5:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-003, FR-013, FR-014, FR-019]
US4:
  depends_on: []
  depends_on_merged: [US5]
  implements: [FR-015, FR-016, FR-017, FR-018]
```
