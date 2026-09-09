# Implementation Plan: the operator's skills arrive with the CLI

## Current seams

- `.claude/skills/` contains the six current project-owned skill directories. This story moves the maintained source to `.agents/skills/` and leaves verified Claude aliases, not duplicate copies.
- The `[tool.hatch.build.targets.wheel.force-include]` table in `pyproject.toml` currently does not package a canonical operator skill resource tree.
- `.github/workflows/release.yml` validates release payloads and is the correct place for source/archive parity.
- `factory/cli/main.py:54` — `_discover_nouns_with_failures` allows a focused `skills` noun without adding a legacy console script.
- `factory/cli/uninstall.py:609` — `_kept`, `factory/cli/uninstall.py:613` — `_removed`, and `factory/cli/uninstall.py:720` — `_survey_state` establish the existing preview/ownership vocabulary.
- `factory/cli/main.py:132` — `_version_text` is presentation only; use package metadata or explicit unavailable state for manifest comparison.

## Proposed interfaces

Add `factory/cli/skills.py` as the pure/resource/filesystem library and
`factory/cli/nouns/skills.py` as the thin `install|status` front door. Resource
inventory returns relative path, kind, and digest records. Installation manifest
records schema, package/source version, canonical destination, compatibility
entries, and per-path digests. No credential or absolute source-checkout path is
stored.

The Codex user destination is exactly `$HOME/.agents/skills`, as documented by
https://learn.chatgpt.com/docs/build-skills . Claude compatibility aliases live
under `$HOME/.claude/skills`. XDG/operator-state configuration may place the
ownership manifest; it does not silently relocate either client's discovery
root. A missing client binding is an availability result, not permission to
create unrelated client configuration.

## Story slices

### US1 — Resource payload

Move the tracked source once, create repository-local compatibility aliases, and
package the recursive canonical directories. Archive tests compare derived
inventories and reject symlink escape or secret-shaped content. Keep the six-job
declaration explicit while allowing each directory's contents to grow.

### US2 — Install

Implement plan/then-apply over individual entries. Classify absent, identical,
owned-stale, and unowned-collision before writing. Apply safe entries independently
and write the manifest atomically after results are known.

### US3 — Status

Read resources, manifest, destinations, and package metadata without mutation.
Render stable filesystem states and specific remedies. Broken/missing
compatibility aliases are separate from canonical content freshness. Even a
current filesystem state says client loading is unqualified; the migration
runbook's shared-discovery gate owns fresh client evidence.

### US4 — Teardown

Reuse the manifest inventory and current digests. Survey first, remove only exact
owned matches, retain mismatches, and integrate with wider uninstall's existing
two-phase behavior.

## Traps

1. **A skill is a directory.** Packaging only `*/SKILL.md` breaks scripts and references.
2. **Counts rot.** Derive recursive file inventory; keep only the six job names as the reviewed package boundary.
3. **One source, two clients.** Compatibility copies recreate drift; use verified aliases or the smallest tested loader.
4. **Operator home only.** Target context belongs to 139; dispatched nodes must not receive these skills automatically.
5. **Collision is per path.** One preserved file must not roll back unrelated safe entries.
6. **Owned once is not owned forever.** A modified file is operator data at teardown.
7. **Symlinks can escape.** Repository and package inventory must refuse out-of-root targets.
8. **Package version can be unavailable.** Never use timestamps as a substitute.
9. **Status is observation.** It performs no repair or client launch.
10. **Uninstall already has survey/perform semantics.** Do not add a recursive shortcut.
11. **Retired collections were deliberate.** Lockfile drift triggers review, not bulk restoration.
12. **No new dependency is approved.** Use importlib resources, hashlib, pathlib, and existing packaging support.
13. **Spec 158 changes behavior after this lands.** This spec packages faithfully; it does not absorb reporting/metrics/rendering repairs.

## Verification

Use temporary build outputs and homes. Compare archive/resource/destination
inventories, capture filesystem state before each run, and assert the exact
difference. Run focused packaging/install/status/uninstall tests, build wheel and
sdist, inspect their contents, then run the declared full gate.
