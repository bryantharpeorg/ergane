---
state: draft
depends_on_landed:
  - 159-a-subscription-credential-has-one-durable-owner
  - 160-each-codex-attempt-owns-its-evidence
---

# Feature Specification: a Codex worker proves its deployment

## Provenance and qualification hold

This spec qualifies the current-deployment portion of audit finding F5 and work
package E. It does not claim the broader, unused deployment matrix is qualified.
Landed spec 155 proves executable resolution in synthetic host/package tests.
It does not prove that the current worker delivers the declared credential and
tool payload, or that a real account-backed Codex turn can search, edit, test,
commit, cancel, and archive inside Ergane's actual confinement boundary.

Implementation tests use synthetic credentials and fake/local payloads. The final
account-backed qualification is a distinct, held story: it may run only after the
operator approves the credential-owner arrangement and names an eligible private
pilot target. Nothing here changes a live unit or worker in place.

### Approved final-phase scope

The 2026-09-09 migration runbook narrows this phase to the deployment actually
in use: a systemd-user worker launching the installed standalone Codex through
the existing host `BwrapBackend`. Container-engine deployment, new npm/standalone
parity, additional host layouts, and subscription-only onboarding in spec 112
are outside this epic. Existing container/npm and gateway/Claude behavior remain
regression controls, not new support claims or prerequisites for the pilot.

At the 2026-09-10 preparation snapshot the host resolves standalone Codex
0.154.0; `CODEX_RUNNER_VERSION` separately names the engine image's npm 0.153.4
pin. Neither a path nor a version command qualifies the payload. The pilot
must record and verify its own exact executable, version, installation payload,
worker revision and confinement declaration before dispatch, without silently
upgrading the image pin or following a changed host symlink.

This remains a draft. Before dispatch, spec 159 and spec 160 must be landed and
the subscription governance/private-target holds must be resolved. Narrowing
the implementation matrix does not approve that policy, supply an account,
name a pilot target, start a login, or authorize a future-default switch.

### User Story 1 - Deployment carries the declared owner, not an operator home (Priority: P1)

As an installer, I generate a worker deployment whose host-side policy can reach
the declared credential owner while its Codex child receives only one staged
attempt copy.

**Acceptance Scenarios**:

1. **Given** the current systemd-user worker declaration for Codex subscription, **When** its unit and host launch artifacts are rendered, **Then** the declared read-only bootstrap source and host-global owner state are accessible only to host-side factory policy, while the bwrap-confined Codex child receives one staged attempt copy and never the owner store or operator's whole home — proven by generated-artifact and mount-boundary tests.
2. **Given** gateway-only or Claude-only deployment, **When** artifacts are rendered, **Then** no Codex subscription credential mount or secret-bearing environment value appears and existing output remains unchanged — proven by golden semantic comparisons.
3. **Given** a declared source is absent, inaccessible, wrong-mode, or mounted at a different path, **When** install verification and worker preflight run, **Then** both refuse before dispatch with the same redacted status code and remedy from spec 159 — proven by temporary-layout tests.
4. **Given** a deployment is regenerated or uninstalled, **When** ownership is reconciled, **Then** operator-created credentials and valid durable generations are preserved unless the operator explicitly targets them; generated declarations are removed only under digest ownership — proven by filesystem-difference tests.

**Why this priority**: A confined child cannot use a credential that the host policy never staged for its attempt.

**Independent Test**: Render the current systemd-user/host-bwrap deployment into a temporary install root and validate permissions, staging, status, and teardown without starting services.

### User Story 2 - The deployed Codex layout exposes one qualified toolchain (Priority: P1)

As the worker, I either resolve a fully supported Codex executable and its runtime
payload or refuse the layout before a node is charged.

**Acceptance Scenarios**:

1. **Given** the explicitly selected current standalone installation, missing payload, mismatched declared version, and executable-only leaf bind, **When** toolchain resolution runs, **Then** the qualified layout returns executable, install-root, version, and required-tool facts while every incomplete layout refuses by a stable code; existing npm resolution remains unchanged — proven by planted-layout and regression tests.
2. **Given** the current systemd-user unit and host bwrap artifacts, **When** their PATH/bind/install-root configuration is inspected, **Then** each matches the selected layout contract rather than assuming a successful `--version` proves required tools are reachable — proven by artifact-to-resolver tests.
3. **Given** a newer Codex version appears on the host, **When** the worker is configured for the pinned baseline, **Then** it does not silently select the newer binary; qualification and version change require a separate declared update — proven by multi-version search tests.

**Why this priority**: A planted shell stub and an executable version check do not exercise the installation shape Codex uses.

**Independent Test**: Resolve the selected standalone, partial, and competing-version trees through the production resolver, retaining the existing npm regression control without claiming a new container qualification.

### User Story 3 - Startup proves confinement before dispatch (Priority: P1)

As an operator, I know the worker's actual process path is confined even though
Codex receives a permission-bypass flag inside that outer boundary.

**Acceptance Scenarios**:

1. **Given** the selected systemd-user worker and host bwrap deployment, **When** a local qualification probe runs through the production launch builder, **Then** the child can read its worktree, write only the allowed worktree/node-home paths, use its declared tool payload, and cannot read the host owner store or an outside canary — proven by committed synthetic-boundary evidence and tests.
2. **Given** the confinement profile, mount set, executable path, or worker revision differs from the declared deployment, **When** preflight runs, **Then** it refuses dispatch and names the mismatched fact rather than weakening the boundary or adding a bypass — proven by mutation tests.
3. **Given** cancellation and a spawned descendant, **When** the launch path terminates, **Then** the whole process group is reaped, the attempt archive finalizes, and the credential owner can prove no child remains before releasing state — proven by a real local process test.

**Why this priority**: An inner CLI bypass is acceptable only when the outer worker boundary is measured and intact.

**Independent Test**: Run the synthetic probe through the actual backend/process-group path, not a mocked `--version` call.

### User Story 5 - A private target proves queue eligibility before dispatch (Priority: P1)

As an operator, I can select the narrow private target allowed by provider
guidance without pretending the current public-only merge predicate supports it.

**Acceptance Scenarios**:

1. **Given** an operator-approved organization-owned private repository with an explicit account-backed-pilot declaration and verified GitHub Enterprise Cloud merge-queue capability, **When** readiness evaluates it, **Then** the private positive cell is eligible and names the governance decision/evidence that supersedes D-007/D-049 for this case — proven by forge-response and manifest fixtures.
2. **Given** a private organization without verified Enterprise Cloud capability, a user-owned repository of either visibility, or a public account-backed target, **When** readiness runs, **Then** each refuses before ruleset or dispatch mutation with a stable remedy, while existing public gateway-routed target behavior is unchanged — proven by a full ownership/visibility/route table.
3. **Given** the target declaration and observed forge facts disagree or cannot be read, **When** eligibility is evaluated, **Then** it refuses rather than inferring plan, ownership, or visibility from an ambient remote or checkout — proven by mismatched and unavailable fixtures.
4. **Given** the governance amendment is not approved, **When** the private positive cell is requested, **Then** readiness reports held and performs no ruleset, PR, queue, or dispatch action — proven by denied-mutation seams.

**Why this priority**: D-007/D-049 currently make a private landed pilot unreachable even if Codex itself is ready.

**Independent Test**: Evaluate the complete declared/observed target matrix through pure readiness and fake forge seams.

### User Story 4 - A private pilot proves a complete Codex attempt (Priority: P1)

As the operator qualifying the configured Codex subscription upper rung, I receive one
account-backed end-to-end record from the actual supported deployment.

**Acceptance Scenarios**:

1. **Given** the approved private pilot, quiescent or isolated worker, settled credential owner, and pinned model, **When** one small story runs, **Then** Codex searches, edits, runs the declared gate, commits, archives current-attempt evidence, persists any refreshed generation, passes the independent judge, and lands through the queue — proven by a committed redacted qualification record naming immutable revisions and landing identity.
2. **Given** controlled startup refusal, ordinary retry, auth refusal, question, timeout/cancellation, and route transition exercises, **When** the pilot suite completes, **Then** each outcome belongs to the correct attempt and no credential, stale rollout, unexplained rung charge, or route residue appears — proven by the redacted matrix and underlying store/Temporal references.
3. **Given** any required account, target, model, confinement, refresh, or landing evidence is unavailable, **When** qualification is evaluated, **Then** the result is held/failed with missing evidence named and Codex is not made the default — proven by qualification-report tests.
4. **Given** the supported real Codex version's redacted event stream, **When** pilot evidence is accepted, **Then** spec 160 decodes its stdout/stderr separation, current thread/turn, final message, failure/question classes, and usage completeness without relying only on synthetic shapes — proven by a committed redacted conformance artifact.
5. **Given** the qualified deployment and an explicitly configured Codex subscription upper rung, **When** controlled ordinary gateway failures cause the existing ladder to select it, **Then** the declared persona/model/route runs automatically within configured bounds, retains the independent judge and normal landing path, persists refreshed state, and requires no per-use approval — proven by a redacted ladder-transition record and absent/disabled/exhausted-rung controls.

**Why this priority**: Production readiness is an observed run, not a property inferred from implementation tests.

**Independent Test**: A reviewer can re-derive every redacted record field from the named private pilot execution and git landing without seeing credential material.

## Functional Requirements

- **FR-001**: The selected systemd-user/host-bwrap deployment MUST expose bootstrap and owner state only to host-side factory policy; the Codex child MUST receive one staged attempt copy and MUST NOT see the durable owner store or operator's whole home.
- **FR-002**: Gateway-only and Claude-only deployments MUST NOT acquire Codex credential mounts or secret-bearing environment values.
- **FR-003**: Install verification and worker preflight MUST consume spec 159's shared readiness contract and refuse path/mode/access mismatches before dispatch.
- **FR-004**: Regeneration and uninstall MUST preserve operator credentials and valid generations unless separately and explicitly targeted.
- **FR-005**: Toolchain resolution MUST validate executable, declared version, install root, and required runtime payload for the selected current standalone layout, while preserving existing npm/container behavior without claiming new qualification of those layouts.
- **FR-006**: An executable leaf or `--version` success alone MUST NOT establish toolchain readiness.
- **FR-007**: Worker resolution MUST NOT silently select an unqualified version.
- **FR-008**: A synthetic qualification MUST exercise the production launch builder and prove worktree access, allowed writes, outside denial, and owner-store denial.
- **FR-009**: Deployment/preflight mismatch MUST refuse; it MUST NOT weaken confinement or add a bypass flag.
- **FR-010**: Cancellation MUST reap the process group, finalize the archive, and satisfy the credential owner's fencing contract.
- **FR-011**: Account-backed qualification MUST run only on an operator-approved eligible private target using isolated or quiescent infrastructure.
- **FR-012**: The qualification record MUST name immutable worker, CLI, model, route, target, spec, attempt, judge, and landing identities while redacting credentials.
- **FR-013**: Missing required evidence MUST hold the rollout and MUST NOT be converted into a default switch.
- **FR-014**: This epic MUST NOT modify a live imported worker or unit in place.
- **FR-015**: Account-backed private landing eligibility MUST require an explicit target declaration plus observed organization ownership, private visibility, and GitHub Enterprise Cloud merge-queue capability.
- **FR-016**: The private positive cell MUST supersede D-007/D-049 only after approved governance; user-owned, public account-backed, unverified, unavailable, and mismatched cases MUST refuse before mutation.
- **FR-017**: Existing public gateway-routed target eligibility MUST remain unchanged.
- **FR-018**: The real pilot MUST include a redacted supported-version event artifact decoded by spec 160's current-attempt contract.
- **FR-019**: Qualification MUST prove automatic gateway-to-Codex-subscription selection by the configured ladder, with existing attempt bounds and absent/disabled/exhausted controls; it MUST NOT introduce per-use approval.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-008, FR-009, FR-010, FR-014]
US5:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-015, FR-016, FR-017]
US4:
  depends_on: []
  depends_on_merged: [US3, US5]
  implements: [FR-011, FR-012, FR-013, FR-018, FR-019]
```
