# Tasks: a Codex worker proves its deployment

Do not touch a live worker, unit, credential, registry, or public account-backed
target. Stories 1–3 and 5 are implementation tests; story 4 begins only after explicit
operator approval of the owner and private pilot.

This is the approved current-deployment slice: systemd-user worker, host bwrap,
and the selected installed standalone Codex. Spec 112 onboarding, new container
credential delivery, cross-layout parity and image-pin changes are outside it.
The whole trio stays draft until its dependencies and governance/target holds
are resolved; this scope refinement is not operational approval.

## Phase 1: User Story 1 — Deployment carries the declared owner, not an operator home

- [ ] [US1-S1] Add failing systemd-user/host-bwrap artifact tests proving host-side policy can read narrow bootstrap/owner paths while the Codex child receives only a staged copy and cannot mount the owner.
- [ ] [US1-S2] Add gateway-only and Claude-only semantic controls requiring no Codex mounts or secret values.
- [ ] [US1-S3] Add absent, inaccessible, wrong-mode, and mismounted path tests shared across install verification and worker preflight.
- [ ] [US1-S4] Add regeneration/uninstall filesystem-difference tests preserving operator and durable-generation files.
- [ ] [US1] Extend `factory/supervision/units.py`, the current host install/launch layout, and uninstall ownership to carry declarations only; leave container credential wiring outside this slice.

## Phase 2: User Story 2 — The deployed Codex layout exposes one qualified toolchain

- [ ] [US2-S1] Add selected-standalone, missing-payload, mismatched-declared-version, and leaf-bind failing tests for `factory/verify/toolchain.py`; preserve existing npm behavior as a compatibility control.
- [ ] [US2-S2] Add artifact-to-resolver tests for generated systemd-user/host-bwrap PATH and bind layout, proving required tools work beyond `--version`; leave the image npm pin unchanged.
- [ ] [US2-S3] Add competing-version tests proving no silent host-newest selection.
- [ ] [US2] Implement the selected layout result containing executable, install root, declared/observed version, and payload facts; refuse an unqualified or changed selection rather than silently installing another layout or choosing the host's newest version.

## Phase 3: User Story 3 — Startup proves confinement before dispatch

- [ ] [US3-S1] Add a failing production host-bwrap synthetic task that reads/writes allowed paths, exercises its declared tools, and is denied host-owner and outside-canary reads.
- [ ] [US3-S2] Add one-at-a-time mutation tests for profile, mounts, executable, payload, and worker revision, all requiring preflight refusal.
- [ ] [US3-S3] Add a local descendant-process cancellation test requiring group reap, current archive finalization, and owner fencing.
- [ ] [US3] Implement the production-path qualification probe and stable refusal codes without adding bypasses or unconfined fallback.

## Phase 4: User Story 5 — A private target proves queue eligibility before dispatch

- [ ] [US5-S1] Add failing target/forge fixtures for explicit account-backed pilot intent plus observed organization ownership, private visibility, and GitHub Enterprise Cloud queue capability.
- [ ] [US5-S2] Add the full ownership/visibility/route matrix, preserving current public gateway behavior and refusing private-without-capability, user-owned, and public account-backed cells before mutation.
- [ ] [US5-S3] Add declaration/forge mismatch and unavailable-fact tests that deny ambient remote/checkout inference.
- [ ] [US5-S4] Add a governance-held test with ruleset, PR, queue, and dispatch mutation seams denied.
- [ ] [US5] Extend `repository_can_host_merge_queue`, GitHub readiness, and target declaration parsing only for the approved private organization/Enterprise Cloud cell.

## Phase 5: User Story 4 — A private pilot proves a complete Codex attempt

- [ ] [US4-S1] After approval, run one small story on the named private target through the actual deployment and record immutable search/edit/gate/commit/archive/refresh/judge/landing identities.
- [ ] [US4-S2] Run controlled refusal, retry, auth, question, timeout/cancel, and route-transition exercises and assemble the redacted outcome matrix.
- [ ] [US4-S3] Add qualification-report tests that render missing evidence as held/failed and cannot switch defaults.
- [ ] [US4-S4] Commit a redacted supported-version stdout/stderr event fixture and prove spec 160 decodes current identity, messages, classifications, and usage completeness.
- [ ] [US4-S5] Qualify an automatic ladder-selected Codex subscription upper rung after controlled gateway failures, retaining configured bounds, judge, landing, and refresh ownership; record absent/disabled/exhausted controls and prove no per-use confirmation is introduced.
- [ ] [US4] Commit only the redacted qualification artifact; retain raw private and credential evidence in its authorized host stores.

## Verification

- [ ] Run focused deployment, unit, toolchain, confinement, uninstall, credential, evidence, and 155 regressions, then the declared repository gate.
- [ ] Keep existing npm/container compatibility controls green without labelling them new deployment qualification; preserve the explicit gateway builders, independent gateway judge and Claude alternatives.
- [ ] Re-derive every account-backed artifact field from the approved private execution and observed landing before recommending any default change.
