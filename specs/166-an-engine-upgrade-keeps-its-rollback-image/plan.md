# Implementation Plan: an engine upgrade keeps its rollback image

## Evidence and scope

Revalidated against buildout `d7118c57e57c010db2b2ca1cbaf5b787ff159efd`.
The four cited production modules and two cited test modules are byte-identical
to the original qualification base `a654fca272c34d017888f6dc9281b4654be8f469`.
Original
container contracts are the landed 104/105 trios; their historical line numbers
and statements about missing modules are not the current tree.

Isolated production-boundary captures, repeated on 2026-09-10:

```text
cleanup_excludes_unrelated_images: false
would_remove: Ergane 0.4.0; example.com/operator/another-service:stable
requested_version_reaches_compose_process: false; subprocess_has_env=false
pre_upgrade_identity_is_retained: false
order: stop, start, verify, read_identity, list_images, remove_image, remove_image
would_remove: Ergane 0.5.0 (previous); Ergane 0.4.0
known_current_and_previous_are_kept (pure policy control): true
unknown_previous_removes_nothing (pure policy control): true
```

The actual generator/writer plus installed Compose configuration parser also
produced the following with only the requested process environment corrected:

```json
{"source": "real generated project and Docker Compose config parser", "compose_image": "ghcr.io/bryantharpeorg/ergane:0.5.0", "compose_environment_version": "0.6.0", "requested_image": "ghcr.io/bryantharpeorg/ergane:0.6.0", "daemon_access": false}
```

That check failed twice (0.12s and 0.13s). These version strings are synthetic
inputs, not a claim that a 0.6.0 image exists. No container was started/stopped,
no image deleted/pulled, and no production file changed for diagnosis.

## Existing seams to reuse

- `factory/supervision/engine_upgrade.py:185` — `_retention_decision`: pure policy;
  currently protects only two strings and selects every other supplied image.
- `factory/supervision/engine_upgrade.py:66` — `_ComposeDockerSeam`: its image
  listing is unfiltered; start computes an environment dictionary but `_compose`
  never forwards it. Capture the real subprocess arguments in regression tests.
- `factory/supervision/engine_upgrade.py:236` — `upgrade`: currently stops,
  starts and verifies before reading rollback identity. Keep the injected Docker
  seam and existing thin CLI; extend only the needed preparation boundary.
- `factory/supervision/engine_identity.py:29` — `EngineIdentity`, with actual
  `write_identity`, `read_identity` and `remove_identity` in the same file.
  Reuse the existing `IMAGE_REPOSITORY`, `cli_version` and `image_reference`.
- `factory/supervision/container_project.py:536` — `resolve_project`: generates
  a literal versioned image and a separate version assignment; reference-project
  interpolation is not the operational project's behavior.
- `factory/supervision/container_project.py:677` — `render_compose`, and
  `factory/supervision/container_project.py:728` — `render_env`: existing artifact
  renderers, not evidence that an installed old project is updated by upgrade.
- `factory/supervision/container_manifest.py:203` — `write_project`, and
  `factory/supervision/container_manifest.py:301` — `installed_project`: preserve
  digest-based ownership. Existence or a familiar filename is not ownership.
- `tests/test_engine_upgrade.py:183` —
  `test_upgrade_drained_path_calls_stop_start_verify_retention_in_order`: its
  high-level fake records inputs but neither forwards a process environment nor
  replaces the identity file. Retain useful controls; strengthen the boundary.
- `tests/test_container_project.py:89` — `host`, and
  `tests/test_container_project.py:142` — `_project`: use their relocated roots,
  real configuration and generator rather than a fabricated empty service map.

Resolve these symbols at dispatch. The line numbers are current hints only.

## Story boundaries and design decisions

**US1:** Correct the existing retention policy and its default inventory/removal
boundary. Derive the exact allowed repository from the declared image vocabulary.
Compare simple numeric release tuples, not lexicographic tag strings. Keep all
unrecognized/local/prerelease/digest/dangling entries; do not invent a registry
inventory, release lookup or new dependency. A previous image outside the known
published release shape disables cleanup. Never force image deletion.

**US2:** Capture the actual pre-stop identity once. Exercise its removal and
replacement through the real file helpers, not by patching the reader to return
a stable object forever. Keep uncertainty sticky: a newly written identity cannot
retroactively establish an unknown predecessor. Skip cleanup on failed engine
verification; retain the existing distinction from unrelated failed probes.
There is no automatic rollback or service restart policy added by this story.

**US3:** Prepare a narrowly scoped retargeting of the already installed generated
project. Validate required artifacts, supported shape and recorded digests before
stopping anything. Persist the requested image/version through the existing
project/manifest ownership boundary, then launch with the effective version
environment forwarded. Extend the existing project/manifest modules if needed;
do not run the installation interview or reconstruct mounts/configuration from
ambient defaults. Preserve unrelated field values and confinement artifacts.
The saved project must remain reusable by the normal later Compose invocation.
Capture and inspect the default runner, not just `DockerSeam.start`'s inputs.

Retargeting must not treat a failed or partial write as success: do not start or
prune after a persistence failure; report the affected path and preserve recovery
artifacts. Ownership refusal must happen before stop and must not rewrite a
digest to adopt operator edits. No force option may bypass project ownership.
Keep the change bounded to image selection/owned artifacts; do not redesign
container installation, the identity schema, systemd deployment or configuration.

## Traps that must reach the implementer

1. The original fake's green result proves only that a function received a
   string. Real process env and real saved service image are separate assertions.
2. A process environment of 0.6.0 can coexist with a literal 0.5.0 image. An
   env-only fix or a test using only the symbolic reference project misses this.
3. The supervisor removes identity on shutdown. Moving the read merely before
   start, but after stop, is still wrong. Use ordered file-backed lifecycle tests.
4. Prefix filtering can delete another repository's images. Use exact repository
   equality and conservative version parsing, including numeric 0.10 vs 0.9.
5. A one-off overlay that leaves the saved project unchanged is not an upgrade
   contract for future starts. Preserve the existing digest ownership mechanism.
6. Preserve the generated same-path mounts, environment names/assignments, user,
   ports and confinement variant; no host-wide permission, toolchain, login or
   credential change. No credential values enter artifacts or evidence output.
7. No factory test invokes Docker or a live service. Capture child calls and
   parse generated data in unit/integration tests. The operator's separate
   `compose config` probe is configuration evidence, not a running-image proof.
8. Write focused regressions first, obtain the specific red, fix and run nearby
   controls before the full declared gate. Do not burn a full suite to establish
   a small local regression. Gates, judge and native merge queue remain required.
9. Keep evidence compact and story-local. Each diff, including evidence, remains
   below 64 KiB. Do not duplicate old evidence or rewrite landed 104/105 trios.
10. The onboarding refresh has landed in `docs/container.md` and
    `docs/cli/engine.md`. Reconcile its current qualification warnings at landing;
    do not overwrite unrelated onboarding edits or call a mocked gate a live
    image qualification. US3 alone owns upgrade documentation for this epic.

## Readiness and dispatch boundary

The explicit release repair approval covers these three merge-ordered stories.
At the pinned buildout revision, all seven104 stories and all four105 stories
have observed landing facts; no attestation fallback is needed. The complete
trio passes all12 validation layers, including its three local finding keys,
without skipped layers, refusals or evidence warnings. Ready is eligibility,
not an automatic dispatch or a claim that the defects are repaired.

Keep the current epic and worker unchanged. Select this repair's slot in the
approved release sequence only after normal spec landing and final-base
revalidation. Do not resume the global roadmap to dispatch it implicitly.

## Independent operator release qualification

Re-run the original production-boundary matrix against the exact merged source.
Generate an old project in a disposable directory, run the repaired selection
path with captured daemon calls, and use the real Compose configuration parser
to verify the selected image and version agree without damaging unrelated fields.
Then qualify an actual drained container upgrade/rollback and retained state on
isolated infrastructure, with explicit image inventory and narrowly scoped
cleanup. Do not execute the unrepaired upgrade on the live host. No model/account
or native-worker switch is implied by this repair. Publication still waits for
the full release qualification, documentation refresh and normal promotion path.
