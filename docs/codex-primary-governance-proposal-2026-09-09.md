# Proposed governance amendment for account-backed Codex operation

**Status:** proposal for the agreed final subscription-rung phase; not a prerequisite for the operator or gateway migration
**Would append:** the next available decision (`D-056` at this source fingerprint) after the then-current last entry
**Would amend:** Constitution Principles V and VII, Environment Constraints, and version metadata

## Why a governance change is required

The operator clarified on 2026-09-09 that the immediate path is `agent: codex`,
`route: gateway`, and the existing `ollama-cloud/...` model aliases, plus Codex
CLI for the operator. The operator subsequently included an automatic
subscription upper rung as the final part of this work, scoped to the current
deployment. This proposal must be reconciled for that phase; agreeing to its
implementation sequence does not settle every proposed target-policy clause.
Its application was removed from draft spec 157 so it cannot block
the operator migration. The earlier factory-login design approval is retained
for that later phase.

That later use is an automatic ladder-selected subscription upper rung. The
operator's declared persona and ladder configuration supply execution authority
within configured bounds; this proposal adds no per-use approval gate. Setup,
governance, and qualification decisions are distinct from routine selection of
an already configured and qualified rung.

The constitution currently describes every coding attempt as receiving a scoped
LiteLLM virtual key, binds a persona's fields without naming the landed
runner/route split, and restricts targets/landing to public repositories. Ergane
now has a landed runner/credential-route split (D-053 and specs 154–156). A Codex
CLI may be the runner while its route is either gateway or subscription.
Governance must describe those axes honestly before subscription operation
becomes a default.

OpenAI documents ChatGPT-managed non-interactive authentication as an advanced
pattern for trusted private automation. It uses file-backed `auth.json`, requires
`auth_mode: chatgpt`, refreshes the file, and requires the automation to persist
the refreshed result; API keys remain the general default
(https://learn.chatgpt.com/docs/auth/ci-cd-auth). This proposal therefore does
not claim account-backed interactive or unattended use is suitable for public or
untrusted target code.

D-007 and D-049 admit only organization-owned public repositories to Ergane's
native queue today. A private landed pilot is impossible until a narrowly
verified organization/GitHub Enterprise Cloud positive cell supersedes that
public-only rule. Private visibility by itself is not eligibility.

## Operator decisions needed

1. **Credential owner — approved 2026-09-09:** a separately created factory
   Codex login session and credential directory whose staged state is owned
   by one host-global durable serialized stream across epics, targets, deployment
   shapes, and recovery. It must not overwrite or concurrently refresh the
   operator's interactive login. This is design approval, not a completed login
   or approval of the remaining governance amendment.
2. **Pilot target:** name one operator-controlled, organization-owned private
   repository whose GitHub Enterprise Cloud merge-queue eligibility can be
   verified. No public, user-owned, fork-from-unknown, or untrusted PR target is
   eligible for the landed account-backed pilot under this proposal.
3. **Spec endpoint:** keep all nine trios as reviewed drafts, or authorize only
   mechanically valid and unheld trios to be promoted to `ready` after review.

## Proposed next-decision text (`D-056` at this source fingerprint)

> **D-0NN — Runner identity and credential route are governed separately.**
> Ergane preserves `agent` as the executable runner and `route` as the credential
> delivery path. Gateway-routed attempts receive the existing per-attempt,
> model-constrained virtual key and retain gateway attribution. An explicitly
> declared subscription-routed Codex attempt may instead receive narrowly staged
> managed-account state from one host-global durable serialized credential owner,
> only for an operator-approved eligible private target. A landed pilot
> additionally requires an organization-owned private target whose GitHub
> Enterprise Cloud merge-queue eligibility has been verified. This limited
> positive cell supersedes D-007's public-only target statement and D-049's
> public-only merge-queue predicate; public account-backed automation and
> user-owned repositories remain ineligible. A subscription attempt does not
> receive or claim a LiteLLM virtual key. Refreshed state is validated and
> persisted by the owner and never overwrites the operator's interactive login.
> Token or currency usage not present in supported current-attempt evidence is
> unknown, not zero. The independent gateway judge and Claude rollback remain.
> Rollout requires real deployment/confinement/landing evidence and can stop
> without altering running epic snapshots or deleting attempt evidence.

At this source fingerprint the entry would be D-056 after D-055. At application
time it takes the next available number and appends after the then-current last
entry. It preserves every earlier decision byte-for-byte, including D-007,
D-049, and D-053; the audit's earlier missing-D-053 observation was stale.

## Proposed Constitution changes

### Principle V — Spend Is Attributed, Never Anonymous

Replace only the gateway-universal clauses with:

> Every agentic attempt has an immutable attempt identity and records its runner,
> effective credential route, model, and evidence provenance. A gateway-routed
> attempt receives a scoped, expiring, model-constrained virtual key and retains
> the existing per-key attribution. An explicitly declared subscription-routed
> attempt may use narrowly staged account-backed state under the approved
> credential-owner policy and must never be represented as holding a gateway
> key. Usage values are recorded only when supported evidence from that attempt
> supplies them; unavailable token or currency values remain unknown. The
> factory never derives currency equivalents for subscription usage from model
> guesses or treats a flat-rate route as free.

### Principle VII — Personas Over Model Tiers

Replace the field-list sentence with:

> Nodes are routed by persona. A persona independently declares the executable
> runner (`agent`), credential-delivery `route`, model and fallback, skills,
> write scope, and the existing retry-policy fields. Code never derives one axis
> from another except when reading a documented legacy record, and never
> hardcodes a model name. A route change does not silently change the runner,
> model, fallback, skills, or write authority.

### Environment Constraints

Replace the conflicting model-access, agents, merge, and target clauses with:

> **Credential isolation:** A worker receives only the declared route's narrow
> credential material, never an operator's whole client home. Account-backed
> state has one durable serialized host-global owner across epics, targets,
> deployment shapes, and recovery. Workers cannot overwrite the operator's
> interactive login, select another route implicitly, or publish credential
> bytes as evidence. A supported deployment must prove credential access,
> toolchain layout, filesystem confinement, current-attempt capture, and cleanup
> before production use. Client-internal bypass flags do not replace Ergane's
> external confinement.
>
> Claude and Codex are supported runner families only when the selected binary,
> model/account access, credential route, and deployment shape have each passed
> their contract. Gateway routes retain their existing target policy. The judge
> remains independently selected gateway inference unless a later decision
> changes its execution contract.
>
> Account-backed Codex automation is initially restricted to an
> operator-controlled private target approved for the pilot; a pilot that lands
> through the native queue must additionally be organization-owned and have
> verified GitHub Enterprise Cloud merge-queue eligibility. Public, user-owned,
> unknown, or untrusted target code is ineligible until separately governed and
> supported by provider guidance. This private positive cell supersedes D-007
> and D-049 only as stated; all other ownership/visibility refusals remain.
> Model names in configuration are not entitlement evidence.

## Deferred implementation contract

The former draft 157-US3 scope is retained here and requires a separately scoped
implementation story before subscription rollout; it is not silently discarded:

- Amend Principle V to distinguish gateway attribution from declared
  subscription attempts, preserve attempt identity, and record unsupported
  usage as unknown without claiming a virtual key exists.
- Test the approved private-target restriction and the verified
  organization/GitHub Enterprise Cloud queue cell against the official source.
- Append the next available decision, preserving every earlier entry including
  D-007, D-049, and D-053 byte-for-byte, and update constitution version metadata.

## Version and test procedure if approved

- Allocate and append the next available decision (`D-056` only if D-055 is
  still last); do not edit any prior decision text.
- Apply only the approved constitutional passages and update the constitution
  version/date according to its versioning rule.
- Prove every earlier decision, including D-007, D-049, and D-053, is
  byte-identical and the new entry follows the then-current last decision.
- Pin independent persona axes, unknown subscription usage, the private-target
  and organization/GitHub Enterprise Cloud requirements, and Claude/gateway
  rollback in tests.
- Record exact operator decisions without account identifiers, tokens, or paths
  containing secrets.
- Until the remaining subscription decisions are settled, leave this deferred
  governance application, private-queue enablement, 159's account-backed rollout,
  and 161's private pilot held. These holds do not apply to 157, 087, 158, or
  gateway-only evidence work in 160.

## Non-goals

This proposal does not move the judge to subscription inference, authorize
public account-backed automation, make a model available to an account, assume
GitHub Enterprise Cloud eligibility without verification, install or trust
client hooks, start services, authorize unattended actions, grant memory writes
to nodes, or change existing live epic snapshots.
