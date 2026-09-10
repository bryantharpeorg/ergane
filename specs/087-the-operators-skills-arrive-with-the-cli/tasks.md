# Tasks: the operator's skills arrive with the CLI

Preserve the four story numbers. Write tests first. Do not install into the real
operator home or change installed user skills while implementing this epic.

## Phase 1: User Story 1 — Canonical skill directories travel intact in the wheel

- [ ] [US1-S1] Add failing recursive source/archive inventory tests for regular files and safe internal symlinks under `.agents/skills/`; rebuild a wheel from an unpacked sdist with source-checkout access unavailable and compare resolved content/path parity.
- [ ] [US1-S2] Add a generated extra-file case and missing/extra archive-path diagnostics without fixed counts.
- [ ] [US1-S3] Add escaping-symlink, credential-shaped content, and divergent `.claude/skills/` compatibility mutation tests.
- [ ] [US1-S4] Add an allowlist test proving retired collections and unresolved `skills-lock.json` names do not enter the payload.
- [ ] [US1] Move the maintained six project skills to `.agents/skills/`, create repository-local Claude compatibility aliases, and implement resource inventory in `factory/cli/skills.py`.
- [ ] [US1] Update `pyproject.toml` and `.github/workflows/release.yml`; build wheel/sdist and compare their path/digest inventories.
- [ ] [US1-S3] Prove dangling/cyclic/escaping links and forbidden content refuse at the actual build-validation boundary, including the sdist route; keep the existing isolated Hatchling build working without new runtime dependencies.

## Phase 2: User Story 2 — One explicit verb installs skills for both clients without overwriting collisions

- [ ] [US2-S1] Add a failing clean-home install test for canonical skills, compatibility aliases, and a schema-versioned digest manifest.
- [ ] [US2-S2] Add a byte/timestamp snapshot test requiring an identical second install to make no change.
- [ ] [US2-S3] Add the absent/identical/owned-stale/unowned-file/unowned-directory/broken-alias collision truth table.
- [ ] [US2-S3] Include identical-unowned entries, modified-owned bytes, redirected parent symlinks, invalid manifest paths, interrupted file writes and failed manifest replacement; assert no ownership adoption, out-of-root write or false current result.
- [ ] [US2-S4] Add varied-home/XDG-state and one-client-only tests proving discovery roots remain `$HOME/.agents/skills` and `$HOME/.claude/skills` while only the ownership manifest follows declared operator state.
- [ ] [US2] Implement plan/apply installation in `factory/cli/skills.py` and expose `ergane skills install` through `factory/cli/nouns/skills.py`.

## Phase 3: User Story 3 — Filesystem status distinguishes absent, current, stale, and collided installs

- [ ] [US3-S1] Add table-driven failing state/remedy tests for absent, current-filesystem, stale, modified, collided, broken alias, unavailable version, and unsupported manifest.
- [ ] [US3-S2] Add checkout/no-metadata and future-manifest fixtures requiring explicit unavailable/unsupported results.
- [ ] [US3-S3] Add denied-write/network/client fakes and before/after hashes for status-only execution.
- [ ] [US3-S4] Add a failing presentation test proving `current-filesystem` says client loading remains unqualified and names the migration runbook's shared-discovery gate.
- [ ] [US3] Implement pure status models/rendering and `ergane skills status` without repair or timestamp inference.

## Phase 4: User Story 4 — Uninstall removes only digest-owned entries

- [ ] [US4-S1] Add install-then-uninstall tests for unchanged canonical files, aliases, and installation-created empty directories.
- [ ] [US4-S2] Add modified-byte and retargeted-alias preservation tests retaining manifest evidence.
- [ ] [US4-S3] Add repeated/partial teardown filesystem-difference tests.
- [ ] [US4-S4] Add survey/perform integration tests in `factory/cli/uninstall.py` forbidding unreviewed recursive removal.
- [ ] [US4-S4] Exercise the real ordered teardown table with relocated roots and captured external calls: skills are surveyed/removed before CLEAR_STATE, `--check` reaches no perform, and `--purge` preserves only the ownership record still needed for kept modified skill entries. Repeat teardown and verify the record still explains those entries.
- [ ] [US4] Implement skill survey and teardown using manifest digests and existing kept/removed reporting.
- [ ] [US4] Document the narrow retained-manifest purge exception and commit compact actual preservation/ordering evidence. Begin only after US3's merge because its library/noun changes are part of this story's base.

## Verification

- [ ] Run focused resource, package, install, status, and uninstall tests; build and inspect both archives; then run the declared repository gate.
- [ ] Confirm no real operator-home path, client configuration, installed skill, credential, runtime store, or service changed.
