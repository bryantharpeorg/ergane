# Implementation Plan: a Codex worker proves its deployment

## Current seams

- `factory/supervision/container_project.py:536` — `resolve_project` renders the generated engine deployment; its current mounts do not declare a Codex credential source.
- `factory/supervision/units.py` owns generated systemd-user unit artifacts and must consume the same declaration without embedding secret bytes.
- `CODEX_RUNNER`, `CODEX_RUNNER_PACKAGE`, and `CODEX_RUNNER_VERSION` in `factory/verify/toolchain.py` name the pinned 0.153.4 baseline; `factory/verify/toolchain.py:434` — `install_root` and `factory/verify/toolchain.py:450` — `npm_install_root` expose the layout seam.
- The `The agent runners` instruction in `Dockerfile` installs the npm Codex payload in the engine image.
- `factory/workgraph/adapter.py:388` — `BwrapBackend` is the outer host boundary; `factory/workgraph/adapter.py:1873` — `CodexAdapter` receives its bypass flag inside that boundary.
- `factory/workgraph/adapter.py:838` — `transcript_dir` and the shared policy archive every attempt.
- `factory/mergequeue/wiring.py:356` — `repository_can_host_merge_queue` and `factory/mergequeue/github_forge.py:302` — `_readiness_visibility_finding` currently refuse every private repository under D-007/D-049.
- Specs 112, 159, and 160 provide readiness, credential ownership, and current-attempt evidence. Subscription governance is separately deferred in `docs/codex-primary-governance-proposal-2026-09-09.md`; 157 now covers only the operator contract.

## Story slices

### US1 — Declared credential delivery

Extend deployment models with paths and mount modes, never credential contents.
Container and systemd renderers consume the same host-global declaration.
Host-side factory policy may reach owner state; the Codex child receives only its
staged copy and has an explicit negative mount for the owner. Verification runs
against generated artifacts and shared readiness before any service starts.
Teardown preserves owned state under the existing digest discipline.

### US2 — Toolchain layout

Define the minimum payload for npm and standalone layouts. Resolve the pinned
binary and install root together. The standalone layout is supported only if its
bundled tool behavior is actually reproducible; otherwise refuse it and retain npm
as the supported shape rather than pretending parity.

### US3 — Synthetic production-path qualification

Drive a harmless local task through the real invocation builder, bwrap/container
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

1. **A config mount is not an auth mount.** The current generated project does not make host `auth.json` appear inside the engine.
2. **Do not mount the operator's whole home.** Deliver only declared bootstrap and owner paths.
3. **Paths are the contract.** Renderer, readiness, and adapter must agree exactly.
4. **Uninstall ownership is digest-based.** Never delete operator or refreshed state because a directory name matches.
5. **Executable-only is incomplete.** Bundled tools may live beside the binary's install root.
6. **Host newest is not worker selected.** Keep the pinned baseline until separately qualified.
7. **A shell stub proves argument plumbing only.** It is not a Codex turn.
8. **The bypass flag is inside the boundary.** Do not add unconfined fallback or hook-trust bypass.
9. **Confinement must deny the owner store.** The attempt receives a staged copy only.
10. **Cancellation includes descendants.** Fencing cannot succeed while a child process survives.
11. **Implementation evidence and account evidence differ.** Preserve both labels.
12. **Official account automation excludes public/open-source targets.** The private pilot is a real hold.
13. **No live imported edits.** Use an isolated deployment or wait for quiescence.
14. **A green PR check is not landing evidence.** Record the merge-group landing and observed attribution.
15. **Private is not sufficient.** Organization ownership and verified GitHub Enterprise Cloud queue capability are separate declared/observed facts.
16. **The engine is not the child.** Host-side policy may read owner state; the launched Codex sandbox must not.

## Verification

Stories 1–3 and 5 use temporary install roots, planted toolchains, canary files,
fake forge responses, and local fake children. Story 4 follows a separately approved runbook and generates
redacted evidence. Run container-project, unit, toolchain, adapter, confinement,
credential, evidence, and uninstall regressions, then the declared full gate.
