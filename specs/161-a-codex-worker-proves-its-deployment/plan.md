# Implementation Plan: a Codex worker proves its deployment

## Current seams

- `factory/supervision/units.py` owns the current generated systemd-user worker artifacts; add the narrow host-side declaration without embedding secret bytes.
- `CODEX_RUNNER_PACKAGE` and `CODEX_RUNNER_VERSION` in `factory/verify/toolchain.py` name the image's npm 0.153.4 pin, not the actual host's standalone version. The preparation snapshot resolves standalone 0.154.0; remeasure the exact selected path/version/payload for qualification. `factory/verify/toolchain.py:434` — `install_root` and `factory/verify/toolchain.py:450` — `npm_install_root` expose the existing layout seams.
- `factory/supervision/container_project.py` and `Dockerfile` remain regression surfaces. New container credential wiring, npm parity and image-version changes are outside this narrowed phase.
- `factory/workgraph/adapter.py:388` — `BwrapBackend` is the outer host boundary; `factory/workgraph/adapter.py:1873` — `CodexAdapter` receives its bypass flag inside that boundary.
- `factory/workgraph/adapter.py:838` — `transcript_dir` and the shared policy archive every attempt.
- `factory/mergequeue/wiring.py:356` — `repository_can_host_merge_queue` and `factory/mergequeue/github_forge.py:302` — `_readiness_visibility_finding` currently refuse every private repository under D-007/D-049.
- Spec 159 supplies shared credential readiness and ownership; spec 160 supplies current-attempt evidence. This deployment already has a gateway and independent gateway judge, so spec 112's subscription-only onboarding is not a prerequisite. Subscription governance is separately held in `docs/codex-primary-governance-proposal-2026-09-09.md`; 157 covers only the operator contract.

## Story slices

### US1 — Declared credential delivery

Extend the current systemd-user/host-bwrap declaration with paths and access
modes, never credential contents. Do not add a second container deployment path.
Host-side factory policy may reach owner state; the Codex child receives only its
staged copy and has an explicit negative mount for the owner. Verification runs
against generated artifacts and shared readiness before any service starts.
Teardown preserves owned state under the existing digest discipline.

### US2 — Toolchain layout

Define and measure the minimum payload for the standalone layout actually used
by this host. Resolve its explicitly declared executable/version and install
root together; qualify required tool behavior through the production boundary.
If that selected layout cannot be qualified, refuse it and name the gap rather
than silently installing npm, upgrading a version, or broadening the bind set.
Existing npm/container controls stay green but do not imply a new support claim.

### US3 — Synthetic production-path qualification

Drive a harmless local task through the real invocation builder, host bwrap
profile, process group, current-attempt archive, and owner fencing. Canary reads
prove the negative boundary. Tests modify one declaration at a time and require
refusal.

### US5 — Private merge-queue eligibility

After the deferred governance proposal is separately approved and applied, expand eligibility by one declared and
observed positive cell: organization-owned, private, verified GitHub Enterprise
Cloud capability, and an explicit account-backed pilot declaration. Retain
existing public gateway behavior and every user-owned/unverified refusal.
Readiness validates manifest intent against forge facts before mutation.

### US4 — Account-backed private pilot

This is operational qualification after implementation, not a unit-test story.
Use the named private target and isolated/quiescent worker only after operator
approval and US5 eligibility. Record immutable identities and redacted evidence,
including a supported-version event sample decoded by 160; do not store account
tokens, raw private repository content, or secrets in the artifact. Failure keeps
future defaults unchanged.

Include the intended automatic upper-rung use: trigger controlled ordinary
gateway failures, let the configured ladder select the declared Codex
subscription persona, and record the route, owner, model, bounded attempt,
judge, and landing. Qualification approval concerns setting up this pilot;
there is no extra approval per selected rung. Absent/disabled/exhausted controls
must retain the existing ladder behavior without reaching account credentials.

## Traps

1. **A config path is not a staged credential.** A correct host declaration must deliver the selected attempt copy inside bwrap; do not infer this from an environment value or a version command.
2. **Do not mount the operator's whole home.** Deliver only declared bootstrap and owner paths.
3. **Paths are the contract.** Renderer, readiness, and adapter must agree exactly.
4. **Uninstall ownership is digest-based.** Never delete operator or refreshed state because a directory name matches.
5. **Executable-only is incomplete.** Measure which required tools live beside the selected binary and which are separately declared; prove they remain usable inside the production boundary.
6. **The image pin is not the host selection.** The image's npm 0.153.4 constant does not prove the observed standalone 0.154.0 is qualified. Bind qualification to the exact declared executable/version/payload; reject a changed host selection without silently changing the image pin.
7. **A shell stub proves argument plumbing only.** It is not a Codex turn.
8. **The bypass flag is inside the boundary.** Do not add unconfined fallback or hook-trust bypass.
9. **Confinement must deny the owner store.** The attempt receives a staged copy only.
10. **Cancellation includes descendants.** Fencing cannot succeed while a child process survives.
11. **Implementation evidence and account evidence differ.** Preserve both labels.
12. **Official account automation excludes public/open-source targets.** The private pilot is a real hold.
13. **No live imported edits.** Use an isolated deployment or wait for quiescence.
14. **A green PR check is not landing evidence.** Record the merge-group landing and observed attribution.
15. **Private is not sufficient.** Organization ownership and verified GitHub Enterprise Cloud queue capability are separate declared/observed facts.
16. **The worker is not the child.** Host-side policy may read owner state; the launched Codex sandbox must not.
17. **Scope is the deployment in use.** Do not reintroduce spec 112, general host/container parity, a new runner installation or a future-default switch. A failed selected-layout qualification is an explicit hold, not permission to pick another layout.

## Verification

Stories 1–3 and 5 use temporary install roots, planted toolchains, canary files,
fake forge responses, and local fake children. Story 4 follows a separately approved runbook and generates
redacted evidence. Run unit, toolchain, adapter, confinement,
credential, evidence, and uninstall regressions, then the declared full gate.
Keep existing container/npm tests as compatibility controls only. No production
dispatch of this trio occurs until its credential/evidence dependencies and
separately approved governance/private-target conditions are satisfied.
