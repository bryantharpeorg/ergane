# Implementation Plan: the engine upgrade continuation keeps its predecessor

## Landed baseline and reuse

- `factory/supervision/engine_upgrade.py:71` — `_ComposeDockerSeam` is the real
  captured subprocess boundary.  Preserve explicit `docker rmi` and no force/prune.
- `factory/supervision/engine_upgrade.py:208` — `_retention_decision` is the
  landed exact-repository numeric policy from spec 166 US1.
- `factory/supervision/engine_upgrade.py:275` — `upgrade` currently stops,
  starts and verifies before reading identity.  US1 moves one real read before
  stop and keeps that snapshot sticky.
- `factory/supervision/engine_identity.py:99` — `write_identity` is the real
  file writer for lifecycle tests.
- `factory/supervision/engine_identity.py:126` — `read_identity` is the real
  file reader for lifecycle tests.
- `factory/supervision/container_project.py:536` — `resolve_project` owns the
  requested image, version assignment and deployment fields.
- `factory/supervision/container_manifest.py:203` — `write_project` owns
  generated-file writes and digests.
- `factory/supervision/container_manifest.py:301` — `installed_project` owns
  normal ownership queries.

The prior workflow is not resumed or reset.  PR 511's exact tree is already on
buildout as `2649bf6`; its cleanup tests and evidence are the baseline.  US1 and
US2 here are new story identities for the original spec-166 US2/US3 work that
never started.

## Implementation

**US1:** Write the known old identity through `write_identity` below a temporary
state root.  Make the injected seam's stop remove it and start write the target.
Capture the ordered calls and prove `read_identity` happens before stop.  Read
the pre-stop identity exactly once and pass its image reference to retention.
Unknown/malformed/image-less inputs remain `None`.  Gate inventory and removal
behind successful stop, successful start and a passing engine finding; preserve
unrelated finding visibility and the existing degraded rule.  Add no rollback.

**US2:** Generate an old operational project with `resolve_project`, persist it
through the existing writer, and query normal ownership.  Before disruption,
validate the required artifacts, supported shape and recorded digests.  Compute
the CLI-matched published image through the existing identity vocabulary,
narrowly update only the owned image/version declarations, persist the project
and manifest atomically, then invoke Compose with the selected version in its
actual subprocess environment.  On any refusal or persistence failure, stop has
not run and existing bytes remain.  A later invocation reads the saved selection.

## Traps

1. **Identity dies on shutdown.** Reading after stop or before cleanup is too
   late.  A replacement identity must never become the predecessor.
2. **Unknown stays unknown.** Ambient CLI version and the new identity cannot
   backfill an absent or malformed pre-stop record.
3. **Verification gates cleanup.** A failing engine finding prevents inventory
   and deletion.  An unrelated failed probe remains visible but does not make the
   engine degraded by itself.
4. **Environment is not persistence.** Passing `ERGANE_VERSION` while leaving a
   literal old Compose image writes no durable upgrade.
5. **Ownership precedes disruption.** Validate claimed digests and supported
   shape before stop.  Force bypasses only the open-epic refusal, never ownership.
6. **Do not rerun install.** Re-rendering defaults would erase operator-selected
   mounts, user, ports and confinement.  Retarget only the owned declarations.
7. **Persistence failure is pre-start.** Atomic write failure leaves the old
   project usable and authorizes no lifecycle or cleanup call.
8. **No live Docker in gates.** Child operations are captured.  Real drained
   upgrade/rollback qualification belongs to the operator before publication.
9. **Preserve onboarding.** Reconcile existing warnings; do not claim synthetic
   subprocess capture is real-image qualification and do not rewrite README flow.

## Documentation baseline

At the spec-166 dispatch baseline, the operator recorded:

- `README.md` — `36bebd8446dc7c93578a28cb696fc8d62c9816162942d0e271d1d65782eb5b8e`
- `docs/container.md` — `64281b14b0c81d6edabbe7c335773e0efb1de6ba5c5bb648f16d5940f0d4bda2`
- `docs/cli/engine.md` — `30df3a90c73119a709e4c5987a29fb1cf46eb0b0cd0809e74afb9cb83b50af9a`
- `docs/onramp-exercise.md` — `bcc8df1afd2bcc3f7be4fcd6a5fd48bebc08764bf752ffb9f5d8dc87f205d5f1`

US2 alone owns any required `docs/container.md` and `docs/cli/engine.md` edits.
README and the on-ramp remain byte-identical unless a proven contradiction makes
an edit necessary; any such edit requires an explicit regression and explanation.

## Scope and qualification

Production scope is the narrow upgrade/project/manifest seam named above; tests,
two upgrade docs and compact evidence may change with it.  No dependency, model,
route, credential, native-worker, release-workflow or live deployment change.

Each story must remain below 64 KiB and pass the declared full gate.  Independent
qualification uses a detached exact-head snapshot, executes file-backed identity
transitions and generated-project ownership failures, compares subprocess order
and saved artifacts, runs the related upgrade/identity/project/manifest suites,
checks onboarding hashes, and then observes judge and native merge-group evidence.
