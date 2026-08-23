---
state: draft
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
---

# Feature Specification: a probe tests the endpoint the attempt will use

## The gap, stated precisely

`ergane install --verify` exists to answer one question: will this host actually
build. Its LLM probe answers a narrower one, because the client that performs
the privileged half of the check is built from the environment while the client
that performs the ordinary half is built from the declaration the operator wrote.
On any host where those two disagree — and they disagree on exactly the hosts
where an operator is debugging their gateway — the verdict describes a machine
the factory will not use.

The verdict is also unauditable. It names one address for both halves, so an
operator reading a green line cannot tell which server answered, and an operator
reading a red one is sent to a URL that was never called.

## Why the Temporal half is not in scope

048-US4 and 061-US1 already closed this for Temporal, and closed it
*structurally*: `resolve_temporal_target` is written in terms of
`temporal_target_for`, so one function decides both readings and a future edit
cannot separate them. That is the shape this spec wants for the gateway, and it
is the reason the requirements below say "the same resolution" rather than
"resolve both from the config".

## What this spec does not change

- The probe's content. Minting a short-TTL key, asserting it is model-constrained,
  checking the spend log and revoking it is 061-US1's work, it landed, it was
  verified live by control and mutation on 2026-08-20, and it is correct.
- `LiteLLMClient.from_env`'s five other callers. This spec changes which
  constructor the *probe* uses, not what `from_env` does.
- Anything about Temporal, memory, telemetry or escalation resolution.

## User Scenarios & Testing

### User Story 1 - The probe mints where the attempt will run (Priority: P1)

As an operator verifying an install, the key-management half of the LLM check
runs against the same gateway the completion half runs against, so a verdict is
about one machine.

**Why this priority**: P1 and it is the whole defect.

**Independent Test**: hand the probe a config naming a gateway that cannot mint,
with the environment naming one that can, and assert the probe fails.

**Acceptance Scenarios**:

1. **Given** a declared gateway that cannot mint a key and an environment
   variable naming one that can, **When** the probe runs, **Then** it fails —
   proven by a committed test. This is the 2026-08-20 demonstration, which
   currently reports success.
2. **Given** a declared gateway that can mint and an environment that names
   nothing, **When** the probe runs, **Then** it passes — proven by a committed
   test. **This is the control**: a fix that reads the declaration and ignores
   the environment entirely inverts the defect rather than removing it. The
   established precedence is environment first, and
   `factory/controlplane/resolve.py:158-159` is where the gateway applies it.
3. **Given** the environment and the declaration agree, **When** the probe runs,
   **Then** its behaviour is exactly what it is today — proven by a committed
   test. This is the second control and it covers every real install.
4. **Given** the probe's two halves, **When** an implementer changes one,
   **Then** the other follows, because both read one resolution — proven by a
   committed test that changes the resolved endpoint once and asserts both the
   mint target and the completion target moved. A fix that sets two variables
   from one source is a fix that comes apart at the next edit; 048-US4's
   structural answer is the model.

---

### User Story 2 - A verdict names the endpoint and the source that chose it (Priority: P2)

As an operator reading install verification, the line about the gateway tells me
which address answered and which source supplied it, so a green line can be
audited and a red one sends me to a server that was actually called.

**Why this priority**: P2. US1 makes the verdict true; this makes it checkable.
It is the difference between the readiness class being fixed and being believed
to be fixed, which is the entire subject of
`verify/readiness-proves-a-thing-is-declared-not-that-it-works`.

**Independent Test**: run the probe and assert its report carries the resolved
address and the name of the source that supplied it.

**Acceptance Scenarios**:

1. **Given** a passing probe, **When** its report is rendered, **Then** it names
   the gateway address that answered and the source that supplied it — proven by
   a committed test.
2. **Given** a failing probe, **When** its report is rendered, **Then** the
   address in the message is the address that was called — proven by a committed
   test. Today the failure text at `factory/controlplane/verify.py:436` names the
   declared url whether or not the declared url was ever contacted.
3. **Given** an environment variable that overrode a declaration, **When** the
   report is rendered, **Then** it says so — proven by a committed test. An
   operator whose config is being silently overridden should learn it here, not
   from a failed epic.
4. **Given** a report, **When** it is rendered, **Then** it contains no
   credential — proven by a committed test asserting the master key does not
   appear. The gateway's URL is safe to print; what authenticates to it is not,
   and this spec is adding print statements next to a credential.

## Requirements

### Functional Requirements

- **FR-001**: The probe's key-management client and its completion client MUST
  address the same gateway.
- **FR-002**: That gateway MUST be chosen by the same resolution both halves
  read, so the two cannot diverge in a later edit.
- **FR-003**: The established precedence — environment, then declaration — MUST
  be preserved.
- **FR-004**: A probe report MUST name the gateway address that answered and the
  source that supplied it.
- **FR-005**: A probe failure message MUST name the address that was actually
  contacted.
- **FR-006**: A probe report MUST NOT contain a credential.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006]
```

Both stories edit `factory/controlplane/verify.py`. The edge is contention, not
logic.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the mutation — declared gateway cannot mint, environment can
  — showing the probe failing, alongside the same run against the tree as it
  stands today, showing it passing.
- **SC-002**: Paste the control: environment and declaration agreeing, probe
  behaving exactly as before.
- **SC-003**: Paste the control: declaration alone, no environment variable,
  probe passing.
- **SC-004**: Paste a passing report showing the address and the source.
- **SC-005**: Paste a failing report showing that the address named is the
  address called.
- **SC-006**: Paste a report rendered with a master key set, showing the key does
  not appear in it.

## Assumptions

- `factory/controlplane/resolve.py:137`'s `resolve_llm_gateway` is the resolution
  both halves should read. If an implementer finds a reason it is not — a caller
  that needs the raw declaration — say so in the diff and name it rather than
  introducing a second resolver.
- The probe's five-step key sequence is correct and stays. Verified live by
  control and mutation on 2026-08-20 under 061-US1.
</content>
