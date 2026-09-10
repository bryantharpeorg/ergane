# Implementation Plan: the operator's skills arrive with the CLI

## Current seams

Rechecked against `0d909c5fd96a5ee966243ecf4c896cce90d26174` on 2026-09-10,
after157-US1 landed. The production, packaging and teardown seams below are
unchanged from the earlier `a654fca` review. Predecessor157-US2 is still in
verification; revalidate against157's final merged base before dispatch. None
of the new skills library/noun/source tree exists at this pin.

- `.claude/skills/` contains the six current project-owned skill directories. This story moves the maintained source to `.agents/skills/` and leaves verified Claude aliases, not duplicate copies.
- The `[tool.hatch.build.targets.wheel.force-include]` table in `pyproject.toml` currently does not package a canonical operator skill resource tree.
- `.github/workflows/release.yml` validates release payloads and is the correct place for source/archive parity.
- `factory/cli/main.py:54` — `_discover_nouns_with_failures` allows a focused `skills` noun without adding a legacy console script.
- `factory/cli/uninstall.py:609` — `_kept`, `factory/cli/uninstall.py:613` — `_removed`, and `factory/cli/uninstall.py:720` — `_survey_state` establish the existing preview/ownership vocabulary.
- `factory/cli/main.py:132` — `_version_text` is presentation only; use package metadata or explicit unavailable state for manifest comparison.
- `factory/cli/uninstall.py:1040` — `run_teardown` reads the ordered `STEPS` tuple, currently placing unit teardown before state cleanup; add skill teardown before the state step can remove its ownership record. The same table drives survey and perform, so `--check` must never reach the new acting half.
- `factory/cli/uninstall.py:766` — `_perform_state` currently removes every surveyed state subject under purge; it must preserve the exact retained skill-ownership evidence required by this spec, not recursively erase the record a previous step just retained.
- `tests/test_release_path.py:29` — `_build_wheel` copies the Git index and then selected current files. This does not automatically carry an unstaged new canonical skill file into a generated mutation fixture.
- `tests/test_teardown_owns_the_ordering.py` and `tests/test_teardown_names_what_it_kept.py` hold preview and preservation semantics; `tests/test_teardown_container_step.py` shows how an added step participates without a parallel teardown command.

## Proposed interfaces

Add `factory/cli/skills.py` as the pure/resource/filesystem library and
`factory/cli/nouns/skills.py` as the thin `install|status` front door. Resource
inventory returns relative path, kind, and digest records. Installation manifest
records schema, package/source version, canonical destination, compatibility
entries, and per-path digests. No credential or absolute source-checkout path is
stored.

Store ownership under the existing declared operator-state location. A manifest
records only entries actually created or updated through a prior matching
ownership digest. Matching pre-existing bytes are reusable, not proof that
Ergane owns them: do not claim an unowned file or directory for later teardown.
Classify missing, identical-unowned, unchanged-owned, safely-upgradeable-owned,
modified-owned and unowned-conflicting states separately. Use lstat/containment
checks for parent directories as well as leaf paths; do not write through a
pre-existing symlink that redirects the declared destination. A legitimate
home/XDG declaration is not a reason to trust arbitrary nested symlinks.

Validate a manifest before using any of its paths for writes or deletion. An
unknown schema, malformed entry or out-of-root path must never become an
uninstall target. Manifest read/write failure is explicit, not an empty
successful inventory. Preserve the previous record across failed updates and
make interrupted apply/manifest replacement recoverable without adopting
unowned files. Current filesystem state and recorded ownership are distinct.

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

Wheel members may materialize a safe source symlink's resolved bytes; require
path/content parity and portability rather than a wheel-specific symlink mode.
Preserve the source layout needed to rebuild from an unpacked sdist with no
checkout access. Reject dangling links, cycles and escapes rather than silently
omitting them. Source/archive validation must actually execute during the
declared local build/release path, including a failing mutation, not merely be
mentioned in workflow YAML or implemented in an uncalled helper. Use the
existing Hatchling backend; do not add build/runtime dependencies. Any build
validation helper imported in an isolated backend must not require uninstalled
runtime services or dependencies. Ordinary CI tests do not run a publish job.

### US2 — Install

Implement plan/then-apply over individual entries. Classify absent, identical,
owned-stale, and unowned-collision before writing. Apply safe entries independently
and write the manifest atomically after results are known.

Filesystem aliases and an installed client executable are different facts.
Create the declared safe entry points without launching either client; report
an absent client as unqualified/unavailable rather than a missing canonical
payload. A partial collision must not be reported as a complete current skill.

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

US4 has a merge-edge from US3 because both extend the same skills library and
noun surfaces. Add its step before CLEAR_STATE, while the ownership record
still exists. When modified entries are kept, retain their minimal manifest
evidence and protect that exact record from the later purge step. Keep only
the necessary path and parent directories, not unrelated state; explain this
narrow preservation exception in the teardown report/documentation. Repeated
uninstall, including purge, must still identify why those entries were kept.
Never pass either client's whole skill root to recursive deletion, and never
let a path supplied by a malformed manifest reach the removal runner.

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
14. **The index is not the edited source.** Existing wheel-test helpers copy tracked index files. Ensure generated extra/missing-file tests really alter the source the build consumes; a clean checkout-only test misses the required recursive-inventory behavior.
15. **A wheel built in this checkout is insufficient.** Extract the sdist into a new temporary root and build there without access to the source checkout. Compare the resulting installed resources, not just the presence of an sdist filename.
16. **Atomic manifest replacement is not atomic installation.** Exercise an interrupted file write and a failed manifest replacement; do not lose existing ownership or claim a partially installed skill current.
17. **Purge comes later.** Preserving a modified skill in the skills step is meaningless if CLEAR_STATE then erases the record needed to explain it. Exercise the real ordered teardown table with relocated roots and all service/ref operations captured.
18. **Current discovery is separate evidence.** Never relabel an old client observation with a new file digest. Filesystem status may be current while fresh-client loading remains explicitly unqualified.

## Verification

Use temporary build outputs and homes. Compare archive/resource/destination
inventories, capture filesystem state before each run, and assert the exact
difference. Run focused packaging/install/status/uninstall tests, build wheel and
sdist, inspect their contents, then run the declared full gate.

Use named negative controls and compact pasted output so every acceptance
scenario is judgeable from the story diff. Keep each story, including evidence,
below 64 KiB. No real operator-home installation, service teardown, account use,
publish workflow, tag, model route or running epic changes occur in these tests.
