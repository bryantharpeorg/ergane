---
state: ready
depends_on_landed:
  - 104-install-brings-the-container-up-configured
  - 105-the-cli-and-the-image-share-one-version
fixes:
  - container/engine-upgrade-can-delete-unrelated-images
  - container/engine-upgrade-drops-the-requested-version-before-compose
  - container/engine-upgrade-reads-the-rollback-identity-after-replacement
---

# Feature Specification: the engine upgrade continuation keeps its predecessor

**Created**: 2026-09-11

## Why this continuation exists

Spec 166 US1 landed as `2649bf6a96506fb41588aca84f60713d0e089dba`
through PR 511 and now limits cleanup to older numeric releases from the exact
published repository.  A 38-second GitHub API outage then exhausted the landing
poll's three attempts and completed that workflow with US2 and US3 still
pending.  Replaying the graph would rerun a landed story number, so this spec
gives the never-started lifecycle and project-selection work new identities.

The continuation changes no model route, credential, release workflow, native
worker deployment or live container.  Factory gates capture child processes and
use disposable files.  A real drained image upgrade and rollback remains a
separate operator qualification before registry publication.

## User Scenarios & Testing

### User Story 1 - The pre-stop identity remains the rollback candidate (Priority: P1)

As an operator, cleanup decisions use the engine identity captured before the
old engine stops, even if shutdown removes that identity and the replacement
writes a new one.

**Independent Test**: Use the real identity writer and reader below a temporary
state root with a synthetic Docker seam whose stop removes the file and whose
start writes the target identity.

**Acceptance Scenarios**:

1. **Given** a known old file-backed identity, **When** stop removes it and start
   writes the target identity, **Then** production upgrade reads before stop,
   retains the old and target images, removes only eligible older exact-repository
   releases, and exposes the complete ordered call capture.
2. **Given** absent, malformed and image-less identities before stop, **When** a
   readable target identity appears after start, **Then** the rollback candidate
   remains unknown and cleanup removes no image in every case.
3. **Given** stop failure, start failure or a failing engine verification
   finding, **When** upgrade terminates or reports degradation, **Then** no image
   inventory or removal occurs; unrelated failed findings remain visible without
   changing the existing engine-specific degraded verdict.
4. **Given** landed spec-166 cleanup policy, **When** lifecycle regressions run,
   **Then** exact repository, unknown identity, ambiguous tag and numeric-ordering
   controls remain green without force, prune or automatic rollback.

### User Story 2 - The owned project persists and launches the requested image (Priority: P1)

As an operator, an upgrade retargets the existing generated project to the
CLI-matched published image without overwriting configuration I own.

**Independent Test**: Generate and persist an old operational project under a
temporary layout, drive the real default upgrade runner with captured subprocess
calls, and parse the saved Compose project without contacting a daemon.

**Acceptance Scenarios**:

1. **Given** an owned generated project at an old version, **When** upgrade
   requests the CLI-matched published image, **Then** the persisted service image
   and version assignment match the request, the actual Compose child receives
   the requested environment, and a later invocation selects the same image.
2. **Given** nondefault repository/config/state mounts, user, ports, confinement
   settings and an unrelated environment value, **When** the owned project is
   retargeted, **Then** every unrelated field remains byte-equivalent, no secret
   is written, and the ownership manifest recognizes the updated generated files.
3. **Given** changed, unclaimed, missing or unsupported project artifacts,
   **When** upgrade is requested with or without force, **Then** it refuses with
   the affected path before stop or write, preserves every byte, and force does
   not adopt operator edits.
4. **Given** a persistence failure after validation, **When** retargeting cannot
   commit the project atomically, **Then** start, verification and cleanup never
   run, and a subsequent invocation cannot observe a half-retargeted project.
5. **Given** the complete repair, **When** focused regressions and docs run,
   **Then** compact committed evidence labels all child calls synthetic,
   preserves the README/onboarding behavior, and states that real-image rollback
   qualification is still required before release.

## Functional Requirements

- **FR-001**: The landed spec-166 cleanup behavior MUST remain covered and MUST
  never broaden beyond older numeric tags from the exact published repository.
- **FR-002**: Upgrade MUST capture the real identity before the first disruptive
  call and MUST carry that immutable snapshot into retention.
- **FR-003**: Absent, malformed, image-less or unrecognized pre-stop identity
  MUST remain unknown even if the replacement later writes a readable identity.
- **FR-004**: Failed stop, failed start or a failing engine verification finding
  MUST prevent image inventory and cleanup; unrelated findings MUST remain visible.
- **FR-005**: The requested image MUST derive from the CLI version through the
  existing image vocabulary, and the actual Compose subprocess environment and
  persisted service image/version MUST agree with it.
- **FR-006**: Retargeting MUST use the existing generated-project and ownership
  boundaries, preserve unrelated fields and secret isolation, and update all
  affected ownership digests atomically.
- **FR-007**: Changed, unclaimed, missing or unsupported artifacts MUST cause a
  named refusal before stop or write; force MUST NOT bypass ownership.
- **FR-008**: A persistence failure MUST leave the prior project usable and MUST
  prevent start, verification and cleanup.
- **FR-009**: Tests MUST capture subprocess calls and use disposable real files;
  factory gates MUST NOT contact Docker, a worker, provider, credential store or
  live Temporal service.
- **FR-010**: Upgrade documentation MUST distinguish captured-runner evidence
  from the real drained-image/rollback qualification still required for release,
  while preserving README and onboarding behavior.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-009]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
```

The merge edge protects the shared upgrade module.  Readying this continuation
does not authorize a live container upgrade, worker restart or registry release.
