---
state: ready
depends_on_landed:
  - 157-one-operator-contract-serves-both-clients
---

# Feature Specification: the operator's skills arrive with the CLI

## Preserved provenance and revised ruling

The draft began on 2026-08-22 after commit `838b9c3` deliberately removed two
vendored third-party skill collections. The operator ruled that Ergane's own
skills are for the operator, not dispatched nodes. The 2026-09-04 refinement at
`602a92c` completed the missing trio, corrected dead anchors, changed the payload
from a fixed count to recursive directories, and kept the spec draft.

This 2026-09-09 refinement preserves that ownership and the four existing story
numbers. It supersedes only the former Claude-only source/destination assumption:
the canonical project skill source is `.agents/skills/`, Codex consumes that
source, and Claude receives compatibility aliases. Installation still writes
only to the operator's home. Spec 139 owns target-repository agent context; no
operator skill from this spec is installed into a target or dispatched node home.

The package inventory is the six Ergane-owned jobs present at this checkpoint:
`floor-status`, `escalation-triage`, `findings-ingest`, `away-mode`,
`build-metrics`, and `spec-html`. Earlier vendored collections remain retired;
lockfile names are not permission to reinstall them.

The 2026-09-10 pre-dispatch pass preserves all four story numbers and their
scope. It clarifies source-distribution rebuilds, manifest ownership after
partial uninstall, and merge ordering for the shared skills library. The
predecessor remains 157; this refinement does not dispatch either epic or change
an installed skill.

### User Story 1 - Canonical skill directories travel intact in the wheel (Priority: P1)

As an operator installing `ergane-cli`, I receive every file Ergane owns for each
canonical operator skill, not only its `SKILL.md`.

**Acceptance Scenarios**:

1. **Given** the tracked `.agents/skills/` source, **When** a wheel and sdist are built and another wheel is built from the unpacked sdist, **Then** every regular file and safe in-repository symlink beneath each declared skill directory is present at the same relative resource path with the same resolved content, including scripts and references — proven by archive-content and isolated sdist-rebuild tests derived from the source tree.
2. **Given** a new file is added below an existing declared skill, **When** release validation runs, **Then** packaging includes it without editing a hard-coded file count; a missing or extra packaged path fails with its relative name — proven by generated fixture tests.
3. **Given** a symlink escapes the canonical skill root, a credential-shaped file appears, or a stale `.claude/skills/` copy differs from canonical content, **When** packaging validates, **Then** the build refuses by name rather than following, shipping, or choosing one copy — proven by mutation tests.
4. **Given** the earlier third-party collections and unresolved `skills-lock.json` entries, **When** package inventory is built, **Then** none is restored merely because a name appears in history or the lockfile — proven by an allowlist/source-root test.

**Why this priority**: `build-metrics` and `spec-html` are broken if only `SKILL.md` ships.

**Independent Test**: Build archives in a temporary output directory and compare recursive path/digest inventories to the canonical source.

### User Story 2 - One explicit verb installs skills for both clients without overwriting collisions (Priority: P1)

As an operator, I explicitly install one canonical skill tree and safe client
entry points, preserving anything I already own.

**Acceptance Scenarios**:

1. **Given** clean operator destinations, **When** `ergane skills install` runs, **Then** it writes package-versioned canonical skills under `$HOME/.agents/skills` and creates supported aliases under `$HOME/.claude/skills` to those same bytes, with an ownership manifest containing source version and per-path digests — proven in a temporary home.
2. **Given** an identical prior install, **When** the verb runs again, **Then** it reports every path current and changes no bytes, timestamps, or aliases — proven by before/after filesystem snapshots.
3. **Given** a destination file, directory, or alias differs and is not owned by this installation, including a symlinked parent that redirects a write outside the declared destination, **When** install runs, **Then** the collision is preserved, reported with its exact path, and no sibling skill is rolled back or overwritten; an identical pre-existing unowned entry is not silently adopted for later deletion — proven by a truth-table test.
4. **Given** varied `HOME` and XDG state locations plus an environment with only one supported client installed, **When** destinations resolve, **Then** client discovery roots remain the exact home-relative paths while the ownership manifest may use the declared operator-state location, and an unavailable client binding is reported without failing the canonical install — proven by environment-matrix tests.

**Why this priority**: Packaging creates no operator capability until an explicit, collision-safe install exposes it.

**Independent Test**: Run install twice across clean, identical, and conflicting temporary homes and compare manifests and bytes.

### User Story 3 - Filesystem status distinguishes absent, current, stale, and collided installs (Priority: P2)

As an operator, I can tell whether the files and aliases for both clients match
the packaged skill version I am running, without mistaking that for proof a
fresh client loaded them.

**Acceptance Scenarios**:

1. **Given** no manifest, a current filesystem install, an older package version, locally modified owned bytes, a preserved collision, and a broken compatibility alias, **When** `ergane skills status` runs, **Then** each skill/client entry reports the correct filesystem state, package version, installed version if known, and exact non-secret remedy — proven by table-driven tests.
2. **Given** code runs from a checkout without installed package metadata or a manifest from a newer incompatible schema, **When** status runs, **Then** it reports version/schema unavailable or unsupported and never guesses freshness from modification time — proven by fixtures.
3. **Given** status-only intent, **When** the command runs, **Then** it opens no destination for writing and makes no repair, alias change, package install, network call, or client invocation — proven by denied mutation fakes and filesystem hashes.
4. **Given** matching files and aliases, **When** status reports `current-filesystem`, **Then** it explicitly says client loading is unqualified and points to the migration runbook's separately authorized shared-discovery gate — proven by a presentation-contract test.

**Why this priority**: Silent stale skill behavior is more dangerous than an explicit unavailable state.

**Independent Test**: Render every state from temporary manifests and destinations with all writes denied.

### User Story 4 - Uninstall removes only digest-owned entries (Priority: P2)

As an operator removing Ergane, I can remove its skill installation without
deleting my changes or unrelated client skills.

**Acceptance Scenarios**:

1. **Given** an owned unchanged canonical file and compatibility alias, **When** the skill teardown step runs, **Then** it removes those entries and prunes only empty directories created by the installation — proven by a temporary-home test.
2. **Given** an owned path whose bytes or alias target changed after install, **When** teardown runs, **Then** it preserves the path, reports the digest/target mismatch, and retains enough manifest evidence for a later decision — proven by mutation tests.
3. **Given** a partial or repeated teardown, **When** it runs again, **Then** it is idempotent, removes no unrelated path, and reports already absent separately from preserved collision — proven by filesystem-difference tests.
4. **Given** the wider `ergane uninstall` flow, **When** its survey and perform phases run, including `--check` and `--purge` with modified skill entries, **Then** skill actions participate in the existing preview/ownership contract, their ownership evidence is read before state cleanup and needed retained records survive later cleanup, and no unreviewed recursive delete occurs — proven by survey/perform integration tests and compact committed evidence.

**Why this priority**: The operator's modifications are not package-owned merely because the original path was.

**Independent Test**: Install, modify a subset, uninstall twice, and assert exactly the unmodified owned set was removed.

## Functional Requirements

- **FR-001**: `.agents/skills/` MUST be the one canonical tracked source for Ergane-owned operator skills.
- **FR-002**: Packaging MUST include every safe recursive file required by each declared skill and MUST preserve relative paths.
- **FR-003**: Packaging validation MUST refuse escaping symlinks, credential-shaped content, divergent compatibility copies, and undeclared restored collections.
- **FR-004**: Release validation MUST compare source and archive path/digest inventories without a fixed skill or file count, including a wheel rebuilt from the sdist without a source checkout.
- **FR-005**: `ergane skills install` MUST be explicit and MUST write only to operator-home destinations.
- **FR-006**: Installation MUST use `$HOME/.agents/skills` as the Codex canonical destination and `$HOME/.claude/skills` for supported Claude compatibility aliases to those bytes.
- **FR-007**: Installation MUST record package/source version and per-path ownership digests in a schema-versioned manifest.
- **FR-008**: Identical reinstall MUST be byte- and timestamp-idempotent.
- **FR-009**: Unowned or modified collisions MUST be preserved and reported; they MUST NOT block unrelated safe entries. Identical unowned entries MUST NOT be silently adopted, and installation MUST NOT follow an unexpected destination-parent symlink to write outside its declared root.
- **FR-010**: This spec MUST NOT install operator skills into a target repository or dispatched node home; spec 139 alone owns target agent context.
- **FR-011**: Status MUST distinguish absent, current-filesystem, stale, modified, collided, broken-alias, unavailable-version, and unsupported-manifest states and MUST NOT claim a client loaded the files.
- **FR-012**: Status MUST be read-only and MUST NOT infer freshness from modification time.
- **FR-013**: Teardown MUST remove only unchanged digest-owned files/aliases and installation-created empty directories.
- **FR-014**: Modified owned paths and unrelated entries MUST be preserved with reviewable evidence; a later teardown step, including state purge, MUST NOT erase ownership records still needed to explain retained skill entries.
- **FR-015**: Skill teardown MUST participate in `ergane uninstall` survey/perform semantics and remain idempotent.
- **FR-016**: No missing lockfile entry or retired collection MUST be installed without a separately reviewed source and explicit operator decision.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-016]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-013, FR-014, FR-015]
```
