---
state: draft
# DRAFTED 2026-08-23 ~10:20 PM CT by the operator session behind
# docs/container-onramp-program.md. Spec-only draft: plan.md and tasks.md at
# refinement. US1 (workflow) can land before 088; US2-US4 need 088's
# supervisor merged. Evidence: findings §4 (version contract), decision 4 of
# the program document.
#
# Settled at drafting:
#   - Derive-and-refuse, the DDEV/Dagger model: the image tag is a pure
#     function of the CLI version. No compatibility matrix, ever — the
#     Supabase maintainers' refusal to own one (findings §4) is the lesson.
#   - The reference floor is arm64. Multi-arch (amd64+arm64) in ONE buildx
#     push from the first release; per-arch pushes to a shared tag silently
#     replace the manifest list (findings §4).
#   - GHCR (ghcr.io/bryantharpeorg/ergane), GITHUB_TOKEN auth, cosign
#     keyless over the pushed digest — the image-side analog of the PyPI
#     trusted publishing already in the release workflow.
#   - Image job runs needs:[pypi] so the only possible partial release is
#     the detectable one (CLI on PyPI, image 404 — findings failure mode 13).
#   - Never auto-upgrade a stateful engine (Watchtower corpus; and this
#     floor's own memory: a worker restart mid-attempt wedges the epic).
#     Upgrade is an explicit drain-first verb.
#   - The skew precedent to extend, not duplicate: the worker/CLI revision
#     notice from spec 053 (factory/cli/nouns/build.py:741 _cli_revision,
#     :761 _skew_notice) — today a warning; for a container engine the same
#     comparison becomes a refusal with the remedy printed.
---

# Feature Specification: the CLI and the image share one version

**Created**: 2026-08-23
**Depends on**: US1 independent; US2–US4 need spec 088 merged.

## The gap, stated precisely

The container introduces a failure mode the native install does not have:
two copies of the same code that can drift — and this project has been
bitten twice by a stale worker running code that no longer matched the tree.
Today no image is published at all, the release workflow publishes only to
PyPI, and the only skew detection is a *warning* comparing git revisions
(`factory/cli/nouns/build.py:741`, `:761`) that a container deployment,
installed from a wheel with no git checkout, cannot even produce.

## The rule this spec is asking for

**`ergane-cli X.Y.Z` runs exactly `ghcr.io/bryantharpeorg/ergane:X.Y.Z`;
every release publishes both or fails detectably toward the image; a
mismatch between a running engine and the CLI refuses with the remedy
printed; and upgrading is a deliberate, drained verb — never a side effect.**

### The ruling, made here rather than left to the implementer

- **Tags are immutable and versioned; `latest` is for humans only** and is
  never referenced by any generated or committed file. Compose's
  `pull_policy: missing` default thereby becomes a feature.
- **One buildx invocation, both platforms, asserted in CI** — the workflow
  fails the release when the pushed manifest list lacks either platform.
- **The engine reports its own identity.** The supervisor writes an identity
  file (version, image digest when knowable, start time) into the
  supervision home at startup — host-readable over the same bind mount the
  state root uses, no new API.
- **Refusal at the moments that matter**: `ergane build start` and
  `ergane install --verify` compare CLI version to engine identity and
  refuse on mismatch naming both versions and the upgrade verb; `ergane
  status` surfaces the same fact as a notice. The native path keeps its
  existing warning semantics untouched.
- **The upgrade verb drains first**: refuse (or wait) while attempts are in
  flight, stop the engine cleanly, bring up the new pinned version, verify
  through it, and keep the previous image one release back for rollback.

## User Scenarios & Testing

### User Story 1 - The release workflow gains the image job (Priority: P1)

As the release pipeline, one tag publishes the wheel and then the image, in
that order, multi-arch, signed — and the workflow's shape is pinned by test.

**Acceptance Scenarios**:

1. **Given** the committed workflow, **When** the drift test reads it,
   **Then** the image job exists with `needs: [pypi]`, one buildx invocation
   declaring `linux/amd64,linux/arm64`, GHCR login via `GITHUB_TOKEN`, a
   cosign keyless step over the pushed digest, and a platform assertion —
   red first with any element removed, green against the committed file.
2. **Given** both jobs, **When** the test reads their version sources,
   **Then** the image tag derives from the same git tag as the PyPI
   version — one source, two consumers.

### User Story 2 - The engine writes its identity (Priority: P1)

As the supervisor, I state what I am before I accept work.

**Acceptance Scenarios**:

1. **Given** the supervisor starting with stub children, **When** the worker
   is about to start, **Then** an identity file (version, start time, image
   digest when knowable) already exists in the supervision home — proven by
   a committed test.
2. **Given** a restart, **When** the supervisor comes back, **Then** the
   file is rewritten whole, never appended.

### User Story 3 - The handshake refuses (Priority: P1)

As an operator with a stale engine, I am refused with the remedy — not
allowed to dispatch into skew.

**Acceptance Scenarios**:

1. **Given** an identity file whose version differs from the CLI's, **When**
   `ergane build start` runs, **Then** it refuses naming both versions and
   the upgrade verb — proven by a committed test.
2. **Given** the same mismatch, **When** `install --verify` and `status`
   run, **Then** verify reports a finding and status a notice — and the
   native path's existing warning semantics are unchanged, its tests
   passing unmodified.
3. **Given** no identity file — a native engine or a pre-105 container —
   **When** the verbs run, **Then** behaviour is today's: the check
   activates only on evidence.

### User Story 4 - The upgrade verb drains first (Priority: P2)

As an operator upgrading, the engine is never swapped under running work.

**Acceptance Scenarios**:

1. **Given** attempts in flight, **When** `ergane engine upgrade` runs,
   **Then** it refuses naming them, and proceeds only under `--force` —
   proven by a committed test.
2. **Given** a drained engine, **When** upgrade runs, **Then** it stops the
   engine cleanly, starts the new pinned version, verifies through it, and
   retains the previous image — proven through seams.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
US4:
  implements: []
  depends_on: []
  depends_on_merged: [US3]
```

## Requirements (summary — numbered at refinement)

Immutable tag scheme; single-invocation multi-arch with CI assertion;
image-after-PyPI ordering; identity file schema and location; refuse
semantics per verb with remedy text; drain rules and retention count;
workflow drift test derives the version from the same tag the PyPI job uses.

## Success Criteria (summary)

Pasted: workflow drift test red-then-green; identity file from a supervisor
test run; both refusals with both versions and the remedy visible; the
upgrade verb refusing mid-flight and draining clean. Operator verification:
the 0.4.0 release cut publishes wheel and image in order, `docker buildx
imagetools inspect` shows both platforms, and a deliberate version mismatch
on the floor refuses as specified.
