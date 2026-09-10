---
state: ready
depends_on_landed:
  - 105-the-cli-and-the-image-share-one-version
  - 104-install-brings-the-container-up-configured
fixes:
  - container/engine-upgrade-can-delete-unrelated-images
  - container/engine-upgrade-drops-the-requested-version-before-compose
  - container/engine-upgrade-reads-the-rollback-identity-after-replacement
---

# Feature Specification: an engine upgrade keeps its rollback image

**Created**: 2026-09-10

## Why this repair exists

The operator approved repairing the container upgrade path before the next
release. Qualification of the actual Python boundaries found that cleanup can
select unrelated images, the requested version is dropped before Compose, and
the previous engine identity is read only after the old engine is replaced.
The committed tests inject a Docker seam that remembers the supplied version
and never replaces the identity file, so they do not expose these failures.

A second isolated check used the real operational-project generator and Docker
Compose's configuration parser, without contacting a daemon. Supplying a new
version in the process environment changed the container's version variable
but left its literal image reference on the old version. Passing an environment
variable alone therefore does not repair version selection.

This separately numbered repair preserves the existing explicit, drain-first
upgrade contract. It changes no live deployment, model route, credentials,
release workflow, native-worker lifecycle or already-landed story identity.

## User Scenarios & Testing

### User Story 1 - Cleanup leaves other software and unknown versions alone (Priority: P1)

As an operator, upgrading Ergane cannot remove another application's images or
interpret an unfamiliar tag as an old Ergane release.

**Independent Test**: Call the production retention decision and default Docker
runner through a captured subprocess boundary with synthetic image inventory.
No Docker daemon or container is needed.

**Acceptance Scenarios**:

1. **Given** published Ergane target, previous and older release tags mixed with
   unrelated repositories and a similarly prefixed repository, **When** cleanup
   is selected, **Then** only strictly older numeric release tags from the exact
   declared published Ergane repository are removable; target, previous and all
   unrelated images remain — proven by committed tests of production code.
2. **Given** unknown previous identity, an unrecognized previous tag, dangling
   image names, digest references, nonrelease tags or releases newer than the
   previous version, **When** retention is evaluated, **Then** uncertainty never
   authorizes removal: unknown previous means no removals, and ambiguous/newer
   inventory entries remain — proven by unconditional keep/remove assertions.
3. **Given** the real default image-listing and removal runner with subprocess
   calls captured, **When** inventory succeeds or fails, **Then** successful
   inventory passes through the same retention policy, failure causes no image
   deletion, and removals use explicit references without force or global prune;
   compact committed output shows the unrelated-image regression red then green.

### User Story 2 - The replaced engine remains the rollback candidate (Priority: P1)

As an operator, the image retained for rollback describes the engine that was
running before upgrade, not the replacement that just wrote a new identity.

**Independent Test**: Use real identity serialization under a temporary state
root, with a Docker seam whose stop removes that file and whose start writes a
different identity. Assert the production upgrade's ordered calls and removals.

**Acceptance Scenarios**:

1. **Given** a known old identity, a stop that removes it and a start that writes
   the target identity, **When** production upgrade completes, **Then** the
   previous identity was captured before stop, and cleanup retains both the old
   and target images while selecting only eligible older images — proven by
   committed file-backed tests and an ordered call capture.
2. **Given** absent, malformed or image-less identity before stop, **When** the
   replacement later writes a readable identity, **Then** the earlier unknown
   rollback candidate remains unknown and no image is removed — proven by
   committed tests using the actual identity reader, not a dictionary stand-in.
3. **Given** a stop/start failure or a failing engine verification finding,
   **When** upgrade terminates, **Then** no image cleanup occurs; a passing
   engine finding with only an unrelated probe failure still reports that
   finding without declaring the engine degraded — proven by committed controls
   and compact before/after evidence for the replaced-identity regression.

### User Story 3 - The generated project actually selects the requested image (Priority: P1)

As an operator, upgrading the CLI selects its matching published image in the
existing generated project, preserves my deployment configuration, and does not
quietly revert to the old image on a later start.

**Independent Test**: Generate and persist an operational project at a synthetic
old version, then drive the actual upgrade/default runner while capturing the
subprocess boundary. Parse the resulting project and inspect the exact command
and version environment supplied to Compose. No daemon or privileged operation
belongs in the factory gate.

**Acceptance Scenarios**:

1. **Given** an owned generated project with a literal old image and old version
   assignment, **When** upgrade requests the CLI-matched published image,
   **Then** the persisted effective service image and version assignment agree
   with that request, and the default Compose subprocess receives the requested
   version; a later invocation of the same project still selects that image —
   proven by committed tests of the real generator, writer and runner.
2. **Given** nondefault repository/config/state mounts, user, ports, confinement
   settings and an unrelated environment assignment, **When** that owned project
   is retargeted, **Then** all remain unchanged, no credential value is written,
   and the existing digest manifest recognizes the updated generated files —
   proven by before/after artifact comparisons and normal ownership queries.
3. **Given** changed or unclaimed project files, missing required files, or an
   unsupported project shape, **When** an upgrade is requested, **Then** it
   refuses naming the affected path before stopping the engine or overwriting
   any file; open-epic refusal and explicit force semantics remain intact —
   proven by committed no-call and byte-preservation controls.
4. **Given** the completed selection and lifecycle repair, **When** focused
   regressions run, **Then** compact committed evidence contains the original
   dropped-version and literal-old-image failures followed by passing actual
   boundary checks, plus the existing upgrade/project/manifest controls. The
   documentation states the implemented behavior and separately identifies
   real-image/operator qualification still required before release.

## Functional Requirements

- **FR-001**: Image cleanup MUST use the exact published Ergane repository
  declaration, never a broad prefix, global prune or unrelated repository.
- **FR-002**: Automatic removal MUST be limited to numeric major.minor.patch
  releases strictly older than the captured previous published release.
  Unrecognized inventory entries MUST remain; absent or unrecognized previous
  identity MUST disable cleanup rather than infer a version from ambient state.
- **FR-003**: Inventory failure MUST cause no deletion; explicit image removal
  MUST NOT force removal or broaden to daemon-wide cleanup.
- **FR-004**: Upgrade MUST capture rollback identity before stopping the old
  engine and MUST NOT replace that snapshot with the new engine's identity.
- **FR-005**: Failed stop/start or a failing engine verification finding MUST
  prevent cleanup. Unrelated verification findings MUST remain visible without
  changing the existing engine-specific degraded verdict.
- **FR-006**: The requested image MUST be derived from the CLI version using
  the existing image vocabulary, and both effective Compose image and version
  assignment MUST select it through the actual default runner.
- **FR-007**: Selection MUST persist in the existing generated project and its
  ownership record, preserving unrelated deployment fields and secret isolation.
  A temporary invocation-only override MUST NOT leave future starts on the old image.
- **FR-008**: Unowned, changed, missing or unsupported project artifacts MUST
  cause a named refusal before disruption or overwrite. The open-epic refusal
  and explicit force option MUST retain their existing authority boundary.
- **FR-009**: Tests MUST cover production boundaries with isolated generated
  files and captured child calls, not only a high-level fake that records its
  arguments. Factory tests MUST NOT contact a Docker daemon, real worker,
  provider, credential store or live Temporal service.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-006, FR-007, FR-008, FR-009]
```

The merge edges protect the shared upgrade module. Readying this spec does not
dispatch it or resume the global roadmap. Select a deliberate build slot within
the approved release work and qualify the final image before publication.
