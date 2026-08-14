---
state: ready
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Drafted 2026-08-13 by the operator session, at 46f7e8b, on Bryan's word
# ("begin working on specs for the rest of the install and init epics").
#
# THIS SPEC EXISTS BECAUSE 033 AND 034 ASSUME IT. Both were written on
# 2026-08-11 against `ergane.yaml` and `.ergane/` — 34 references between them —
# and 034's own frontmatter records the decision: the rename is "its own small
# spec, ordered before 023 lands". It was decided and never written. Dispatched
# without it, an init story would write `ergane.yaml` files that no parser reads
# (`MANIFEST_NAME = "factory.yaml"`) and create `.ergane/` roots nothing uses.
#
# Deliberately NOT in scope, and the plan says so twice: the Python package
# `factory/` keeps its name. Renaming it touches every import in the tree for
# no operator-visible gain, and this spec is about what an operator types and
# commits, not about what the engine calls its own modules.
depends_on_landed: []
---

# Feature Specification: The names an operator types

## Why this is a spec and not a `sed`

Three things carry the old brand into repositories the factory does not own:
the manifest filename an operator commits, the runtime root that appears in
their `.gitignore`, and the environment variables their shell exports. All
three say `factory`; the product is called Ergane. Every provisioning story in
033 and 034 writes one of them, so this lands first or those land wrong.

It is not a `sed` because of three specific hazards, each measured against the
tree at `46f7e8b`:

1. **Three call sites bypass the constant.** `MANIFEST_NAME` exists
   (`factory/verify/factory_yaml.py:58`) but `merge_activities.py:612` and
   `onboard.py:161`/`:165` hardcode the literal `"factory.yaml"`. A rename that
   edits the constant alone leaves the merge-queue preflight and the readiness
   judgment looking for a file that no longer exists — and both fail *quietly*,
   as a missing-manifest finding rather than a crash.
2. **`.factory/` holds 281 MB of live state** on this host: the verification
   store this session has been writing to all day, the ledger, worktrees and
   transcripts. A rename that does not move it silently orphans the factory's
   entire memory of itself.
3. **`factory_yaml` is a finding key, not a filename.** `evaluate_repo` emits
   it (`onboard.py:161`) and the findings ledger compares findings by key across
   time. Renaming the key would break the recurrence counting that decides what
   gets promoted to the constitution. The file gets a new name; the key does not.

## Scope

**In**: the manifest filename, the runtime root directory, the `FACTORY_*`
environment variables, and the migration of existing state.

**Out**: the Python package `factory/`, every module path, every import, and the
`factory_yaml` finding key. Also out: `factory/` as a branch-name prefix
(`factory/<epic>/<story>`) — landed branch names are immutable history and the
merge queue's rulesets match on that prefix.

## User Scenarios & Testing

### User Story 1 - The manifest is `ergane.yaml` (Priority: P1)

**Goal**: a repo declares itself with `ergane.yaml`, and a repo that still has
`factory.yaml` keeps working.

**Why this priority**: 034/US1 writes this file. Nothing in the provisioning
pair is buildable until the parser reads the name those specs write.

**Independent Test**: a fixture repo with only `ergane.yaml` loads; a fixture
repo with only `factory.yaml` loads and reports a deprecation; a repo with both
loads `ergane.yaml` and says which it ignored.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree (constitution VIII).
Runtime claims are met by tool output pasted verbatim into a comment block in
the test file.

**Acceptance Scenarios**:

1. **Given** a repo containing only `ergane.yaml`, **When** the manifest is
   loaded, **Then** it parses exactly as `factory.yaml` does today, with every
   existing key and every existing rejection unchanged.
2. **Given** a repo containing only `factory.yaml`, **When** the manifest is
   loaded, **Then** it still loads, and the operator is told once, by name, that
   the file should be renamed — an existing managed repo does not break on an
   engine upgrade.
3. **Given** a repo containing both files, **When** the manifest is loaded,
   **Then** `ergane.yaml` wins and the diff shows the ignored file being named
   in the output — silent precedence is how two sources of truth start
   disagreeing.
4. **Given** the landed story, **When** the diff is inspected, **Then** no call
   site reads the literal string `"factory.yaml"` — every reader goes through
   the resolution helper, and a test asserts that by scanning the source.
5. **Given** the landed story, **When** the diff is inspected, **Then** the
   `factory_yaml` finding key is unchanged, and the diff contains no rename of
   the `factory/` Python package.

### User Story 2 - The runtime root is `.ergane/`, and existing state moves (Priority: P1)

**Goal**: runtime state lives under `.ergane/`, and the 281 MB already under
`.factory/` arrives there intact rather than being abandoned.

**Why this priority**: 034/US1 writes the `.gitignore` entry for this directory
and creates the root. It must name the directory the engine actually uses.

**Independent Test**: with only `.ergane/` present the engine reads and writes
it; with only `.factory/` present the engine still finds it and says so; the
migration moves a populated root and leaves the databases openable.

**Evidence rule for every scenario below**: as US1 — runtime claims are met by
verbatim pasted output committed in the diff.

**Acceptance Scenarios**:

1. **Given** no runtime root, **When** the engine needs one, **Then** it creates
   and uses `.ergane/`.
2. **Given** an existing populated `.factory/` and no `.ergane/`, **When** the
   engine resolves the root, **Then** it uses `.factory/` and reports the
   migration command by name — an operator mid-epic is never silently pointed
   at an empty store.
3. **Given** a populated `.factory/` containing a verification store with rows,
   **When** the migration runs, **Then** `.ergane/` contains the same tree, every
   database opens and returns the same row counts, and the pasted transcript
   shows the before and after counts.
4. **Given** the migration, **When** it runs a second time, **Then** it reports
   already-migrated and moves nothing.
5. **Given** an epic currently running, **When** the migration runs, **Then** it
   refuses, naming the epic — moving the evidence store out from under a live
   workflow is the failure this refusal exists to prevent.

### User Story 3 - The environment variables are `ERGANE_*` (Priority: P2)

**Goal**: the variables an operator exports carry the product's name, and a
shell that still exports the old ones keeps working.

**Why this priority**: operator-facing and small, but it is the surface
`scripts/ergane-env.sh`, every runbook and every clean-env drill types. It
rides after the two that block 033 and 034.

**Independent Test**: each new name is honored; each old name is honored with a
deprecation; when both are set the new one wins and the conflict is reported.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** `ERGANE_ROOT`, `ERGANE_VERIFICATION_DB_PATH`, `ERGANE_LEDGER_PATH`
   and `ERGANE_EVIDENCE_STORE_ALLOW_REAL` are set, **When** each is resolved,
   **Then** each is honored exactly as its `FACTORY_*` predecessor is today.
2. **Given** only the `FACTORY_*` names are set, **When** each is resolved,
   **Then** each is still honored and a single deprecation is reported — not one
   per read, which would flood every command.
3. **Given** both names set to different values, **When** resolution runs,
   **Then** the `ERGANE_*` value wins and the disagreement is reported naming
   both.
4. **Given** the landed story, **When** the diff is inspected, **Then**
   `scripts/ergane-env.sh` exports the new names, and 030's session isolation
   fixture in `tests/conftest.py` sets whichever names the engine now reads — a
   rename that leaves that fixture pointing at dead variables re-opens the live
   store leak 030 just closed.

## Functional Requirements

- **FR-001**: The manifest MUST resolve as `ergane.yaml` first and `factory.yaml`
  second, through one helper that every reader calls.
- **FR-002**: A repo carrying only `factory.yaml` MUST continue to load, and the
  engine MUST report the deprecation once per command, naming the file.
- **FR-003**: When both manifests exist, `ergane.yaml` MUST win and the ignored
  file MUST be named in the output.
- **FR-004**: No code path MAY read the literal `"factory.yaml"`; a test MUST
  assert this against the module source, as `tests/test_gh_client.py` already
  does for its own forbidden strings.
- **FR-005**: The runtime root MUST resolve as `.ergane/` first and `.factory/`
  second, and MUST report which it chose when it chooses the legacy one.
- **FR-006**: A migration MUST move a populated legacy root to the new name,
  MUST be idempotent, and MUST refuse while any epic is running.
- **FR-007**: The migration MUST NOT lose rows: the verification and usage stores
  MUST open after the move and return the counts they held before it.
- **FR-008**: The `ERGANE_*` environment variables MUST be honored, the
  `FACTORY_*` names MUST remain honored with one deprecation per command, and
  `ERGANE_*` MUST win a conflict.
- **FR-009**: `scripts/ergane-env.sh` and `tests/conftest.py`'s session isolation
  fixture MUST be updated together with the resolution change.
- **FR-010**: The `factory_yaml` finding key, the `factory/` Python package, and
  the `factory/<epic>/<story>` branch prefix MUST NOT change.

## Success Criteria

- **SC-001**: A repo scaffolded by a future `ergane init` — `ergane.yaml` plus a
  `.gitignore` entry for `.ergane/` — is fully usable by the engine.
- **SC-002**: This repository keeps working across the change with no operator
  action beyond running the migration once.
- **SC-003**: The full suite is green, and the live evidence store still holds
  the rows it held before.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-010]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009]
```
