# Implementation Plan: a subscription credential has one durable owner

## Current seams and official contract

- `factory/workgraph/adapter.py:943` — `discover_codex_credential` checks existence and may fall back from `CODEX_HOME` to the operator's default home.
- `factory/workgraph/adapter.py:1131` — `CredentialStage` has no lifecycle or finalization contract.
- `factory/workgraph/adapter.py:1165` — `SharedAttemptPolicy` seeds before its attempt boundary has reaped every earlier candidate owner.
- `factory/workgraph/adapter.py:1983` — `CodexAdapter._credential` accepts the discovered file without validating managed ChatGPT mode.
- `factory/workgraph/adapter.py:2122` — `_seed_codex_config` writes gateway configuration only, so later route changes can inherit incompatible bytes.
- `factory/workgraph/workflow.py:1502` — `_subscription_nodes_in_flight` is per epic and original persona, not credential-wide or effective-rung admission.
- `factory/locking.py:53` — `exclusive_lock` is a useful short local transaction primitive; its polling wait must not become a long async activity wait.
- `factory/workgraph/credential_status.py:44` — `_credential_runway` is Claude-only.
- The synthetic auth document near the top of `tests/test_155_us3_codex_subscription.py` is API-key-shaped and therefore proves copying, not subscription authenticity.
- Official source: https://learn.chatgpt.com/docs/auth/ci-cd-auth . It requires `auth_mode: chatgpt`, a refresh token, file-backed storage, persistence of Codex's refreshed file, trusted private automation, and one machine or serialized stream per credential.

## Proposed interfaces

Add a host-side `CodexCredentialOwner` contract in a focused module such as
`factory/workgraph/codex_credential.py`. Inputs and outputs are frozen redacted
records: `CredentialDeclaration`, `CredentialReadiness`, `CredentialLease`,
`CredentialCandidate`, and `CredentialFinalization`. Token-bearing JSON never
enters these records.

The durable owner directory belongs under one declared host-global operator
state root, outside every target's runtime root and never mounted into an agent
sandbox. An operator-declared redacted credential identity keys one directory
shared by every target and deployment shape on that host. It contains a current
generation, candidate area, quarantine, owner declaration, and append-only
recovery journal. The root is private, operator-owned, non-symlinked, and checked
again on admission. A short transaction lock protects state transitions.
Admission returns BUSY as data; the workflow sleeps and retries. Duplicate roots
or hosts for one identity refuse rather than pretending to serialize.

The attempt receives a disposable copy in its factory-owned node home. The
adapter validates the post-run copy and asks the owner to commit it before
releasing the lease. Every exception/cancellation branch funnels through that
finalizer. Route materialization first clears the route-specific files Ergane
owns, then writes exactly one route's inputs.

## Story slices

### US1 — Declaration, validation, and provenance

Build the pure parser/validator and synthetic fixtures first. Preserve raw token
bytes only inside a narrow file-copy boundary. Explicit declaration disables all
fallback discovery. Expired access is not by itself a refusal when refresh data
is structurally present. Offline inspection reports eligible-to-attempt, not
usable or account-qualified; only a recorded provider result establishes
revocation.

### US2 — Admission

Add host-global owner activities and effective-rung workflow integration. Resolve
all target/deployment callers with one declared credential identity to the same
operator-state root. Acquire at the actual attempt/recovery boundary, before the
rung is charged or a child starts. Return BUSY and wait in workflow time.
Cancellation while BUSY has nothing to clean up.

Integrate with the existing `promotion_persona`/`promotion_cycles` and frozen
persona routing contract. The configured ladder grants the upper rung
automatically; owner admission does not add a human confirmation step. Test
eligible, absent, disabled, exhausted, and BUSY cases with synthetic credentials.
Preserve existing ladder order, bounds, and terminal failure escalation; do not
create a new rescue choice or hard-code a persona/model/one-attempt policy.

### US3 — Staging, exact route, and fencing

Reap/fence an earlier child before candidate reads. Stage exact route state and
run Codex. On termination, end the current process group and prove it dead before
opening the candidate; retain recovery ownership when that proof fails. Gateway
and subscription transitions reuse one home but never one route configuration.

### US5 — Journal, finalization, and recovery

After US3 supplies a proven fence, journal intent, validate the candidate,
commit or quarantine atomically, and release. Parameterize termination, replay,
and crash points. A prior provider rejection is durable status evidence; offline
structure alone never invents revocation.

### US4 — Shared status

Generalize `CredentialStatus` by runner and route, then make install, preflight,
and build status consume it. Stable status codes, not prose parsing, allow 112
and 161 to reuse the result.

## Traps

1. **Existence is not authenticity.** An API-key-shaped `auth.json` currently passes.
2. **Expired access can be recoverable.** Do not reject a valid managed refresh token just because access is stale.
3. **Never inspect or print tokens.** Tests use synthetic values and credential sweeps.
4. **Explicit missing means missing.** Interactive fallback would couple factory and operator sessions again.
5. **A local lock is not distributed ownership.** Refuse multi-host claims.
6. **Do not block the async activity worker.** Long waits live in workflow timers.
7. **Count the effective rung.** Retry and recovery can switch runner or route.
8. **Gateway work is independent.** Credential contention must not stall unrelated virtual-key attempts.
9. **Reap before candidate inspection.** Prior and currently terminating process groups can still rewrite staged auth.
10. **Seed-on-every-run loses refresh.** Bootstrap only when no committed generation exists.
11. **Every termination can refresh.** Cancellation and timeout are persistence paths, not exceptions to it.
12. **Malformed or provider-rejected newest is not newest locally eligible.** Quarantine it and retain the prior committed generation.
13. **Route state is disposable.** Clear only Ergane-owned route files, not the whole node home.
14. **Readiness and usage are different claims.** Auth green does not measure tokens or dollars.
15. **Design approval is not account qualification.** The operator approved the separate factory session and host-global serialized owner on 2026-09-09; the private pilot and real account evidence remain outstanding.
16. **No account-backed run in this story.** Real qualification belongs to 161 after the private pilot is named.
17. **Owner state is host-global, not target runtime.** Two targets must not manufacture independent owners for the same declared identity.
18. **Filesystem identity can change.** Recheck ownership, mode, and symlinks at every admission.

## Verification

Use only synthetic credential shapes and fake children in implementation tests.
Capture state before every crash-point run and assert on the difference. Run the
focused adapter/workflow/status suites and the full gate. A final source sweep
must find no OAuth refresh request implementation and no token-shaped content in
logs, workflow payload fixtures, or committed evidence.
