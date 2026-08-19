---
state: landed
# Attested landed 2026-08-18. US1 bb1ece6cd751 (#200), US2 6a8cb67645a9 (#201),
# US3 be894e7ab30a (#202) -- all three observed on ergane-buildout.
#
# PUBLISHED: ergane-cli 0.1.0 is live on PyPI, tagged v0.1.0 at f678730fd34f,
# uploaded by .github/workflows/release.yml over OIDC trusted publishing (no
# token exists on the worker host). Proven from the real index, not from a local
# build: `uv tool install ergane-cli` into a temp dir with no personas.yaml on
# any ancestor path gives `ergane 0.1.0` and resolves 7 personas from inside the
# installed package. The portability principle's first verb no longer rests on
# `git clone`.
#
# THE ESCAPE HATCH WAS AUTHORISED AND NOT NEEDED. The operator opened the night
# by asking for 035's hand-back path for speed; `ergane build external-completion-
# count` still reads 0. The factory built all three stories -- US1 and US2 first
# attempt, US3 on the debugger rung after the judge correctly caught a broken
# helper. Two operator commits DID land outside the hatch (#203, #204) and are
# recorded as such in their own messages: the hatch refuses any node outside a
# running epic, and both defects were found after epic-056 had COMPLETED. That
# is a real gap in 035 -- the hatch cannot repair what is discovered late.
#
# TWO VERIFICATION GAPS FOUND, both filed critical, both the same disease -- a
# check that can only say yes:
#   install/published-metadata-points-at-a-repository-that-does-not-exist
#     US3 declared every project URL under github.com/ergane/ergane, which is a
#     404; this repo is bryantharpeorg/ergane. The judge confirmed four URLs were
#     PRESENT, verify_wheel.py passed the same wheel 22/22, and
#     tests/test_release_path.py:103 asserts `"Project-URL" in metadata`. Nothing
#     checked that a declared URL RESOLVES. Fixed by #203 before the publish,
#     which was the only moment it was cheap.
#   verify/publish-guard-test-cannot-fail
#     PyYAML renders a GitHub Actions `on:` key as the BOOLEAN True, so
#     _workflow_is_operator_tag_trigger_only's `workflow.get("on")` is None and
#     its `"true" in workflow` fallback never fires (the key is True, not "true").
#     The function returns "permitted" for EVERY workflow. Proved by control: a
#     workflow with `on: push: branches: [main]` -- exactly what the test forbids
#     -- is reported operator-tag-only. FR-011/SC-005 are unproven. release.yml
#     itself is correct, verified by reading it; the guard holds by authorship,
#     not by verification.
#
# FLIPPED READY 2026-08-18 ~7:15 PM CT: publishing to PyPI and installing on
# an Azure VM is the operator's stated goal for tonight, and US1 is its whole
# critical path. Dispatched by hand at a one-attempt ladder; the roadmap stays
# paused, so nothing else reads this flag.
# CONFIRMED AS WRITTEN 2026-08-18 5:50 PM CT. The operator was asked directly
# whether to publish to PyPI at all, having been shown that the rename is forced
# only by that choice: `uv tool install git+https://...` puts the bits on a fresh
# box with no index name involved, which already answers the Azure question this
# spec came from. He chose to publish as `ergane-cli` and keep the import package
# `factory`, knowing what that means -- a very generic top-level name landing in
# the site-packages of everyone who installs. Recorded here so the acceptance is
# a decision on the record rather than an omission.
#
# The third option was also declined: renaming `factory/` -> `ergane/` by hand
# through the 035 operator-completion path before first publish. It is one
# mechanical commit for a human and unbuildable for an agent (1,309 import lines,
# ~141,000 diff bytes against a 65,536-byte ceiling), and it only ever has to
# happen before the name is public. It does not have to happen at all.
#
# SEQUENCING, and it is not in this spec's dependencies because it is not a
# dependency -- it is a file collision: **057 also edits `pyproject.toml`**, to
# force-include its floor text and stack packs the same way `personas.yaml` is
# force-included. US1 of this spec owns that file. Two in-flight worktrees
# editing it is a merge-queue conflict where the second lander rebases blind.
# Land one story before dispatching the other. Related and separate: 057 should
# land before this spec's US3 ever publishes, because a stranger's first
# `ergane init` should not be able to end with no standards document.
#
# --- original drafting note ---
# Drafted 2026-08-18 ~10:25 AM CT, rescoped ~10:55 AM CT at the operator's
# instruction: "im good leaving factory as the folder name but ergane-cli as
# the package name for the smaller change."
#
# Provenance. The operator was provisioning a fresh Azure dev box and asked
# "how do i get the bits there to do ergane install in the first place". The
# honest answer was `git clone`, which contradicts the portability principle he
# set on 2026-08-12: install into brownfield, bootstrap greenfield, unplug
# cleanly. A brownfield install that requires cloning the factory is not one.
# His answer was "python package. uv install ergane-cli".
#
# The first draft of this spec also renamed the import package `factory` ->
# `ergane`. That is now an explicit NON-GOAL -- the operator considered it and
# declined. The reason it was proposed, and the reason it was right to drop:
#
#   - Proposed because publishing a distribution whose import package is
#     `factory` drops a very generic top-level name into the site-packages of
#     everyone who installs it. That risk is real but small, and it is the
#     operator's to accept.
#   - Dropped because it was measured at 1,309 import lines / ~141,000 diff
#     bytes against a 65,536-byte judge ceiling -- unbuildable as a dispatched
#     story, and landable only through the 035 hand-back hatch. All of that
#     cost bought a name change nobody had asked for.
#
# Removing it removes the entire hard part. What remains is small, judgeable,
# and delivers the operator's actual ask.
#
# One fact established against reality before this was written, because it is
# what makes the spec necessary rather than cosmetic: `ergane` is TAKEN on PyPI
# -- owner `pjams`, version 0.7.3, an async web scraper. `pyproject.toml:2`
# declares `name = "ergane"`, so this project cannot be published under its own
# name at all. `ergane-cli` returns 404 and is unclaimed. The rename of the
# distribution is forced by an external fact, not chosen.
#
# Deliberately NOT in scope, and raised in the same conversation: `ergane init`
# treats `standards` as an optional manifest key, so a stranger can produce a
# valid `ergane.yaml` naming no constitution and dispatch agents with nothing to
# obey. That is a decision about defaults, not about packaging. § Open decision.
depends_on_landed: [054-a-stranger-can-install-ergane, 042-supervised-services]
---

# Feature Specification: the factory ships as a package

**Feature Branch**: `056-the-factory-ships-as-a-package`

**Created**: 2026-08-18

## What changes, and what deliberately does not

Python distinguishes the name you install from the name you import. This
feature changes the first and leaves the second alone.

| Kind | Today | After |
| --- | --- | --- |
| **Distribution** — the PyPI name, what `uv` installs | `ergane` | **`ergane-cli`** |
| **Import package** — the directory, what `import` resolves | `factory/` | `factory/` (**unchanged, deliberately**) |
| **Console script** — what the operator types | `ergane` | `ergane` (unchanged) |

`uv tool install ergane-cli` puts an `ergane` command on `PATH`, and that command
imports `factory.cli.main`. Two of the three names do not move.

**The import package staying `factory` is a decision, not an oversight.** An
implementer who "helpfully" renames it has done the one thing this spec exists
to avoid, and has produced a diff nothing can judge. Any change under this spec
that renames a directory, an import, a Temporal namespace, or the
`factory/<epic>/<node>` branch namespace is out of scope and wrong.

## The one line that makes this more than a metadata edit

`factory/cli/main.py:131-137` resolves the version by asking the installed
metadata for the *distribution* name:

```python
try:
    from importlib.metadata import version
    pkg_version = version("ergane")
except Exception:
    pkg_version = "0.1.0"
```

Rename the distribution to `ergane-cli` and `version("ergane")` raises
`PackageNotFoundError`. The bare `except Exception` swallows it, and
`ergane --version` reports the hardcoded string `0.1.0` — **forever, and
regardless of what is actually installed**. No error, no crash, a plausible
number. It fails toward green, which is why it gets its own requirements rather
than a line in a checklist.

There are two defects there, and the second outlives the rename: the version is
declared in `pyproject.toml` and again as a literal in `main.py`, so the two can
disagree and only one of them is true.

---

## User Scenarios & Testing

### User Story 1 - The distribution is named what it can be published as (Priority: P1)

An operator builds a wheel whose distribution name is `ergane-cli`, and the CLI
that wheel installs reports the version it was actually built with.

**Why this priority**: it is the whole rename, and every other story needs it to
exist. The name is forced by PyPI occupancy rather than chosen.

**Independent Test**: build the wheel, and assert its distribution metadata says
`ergane-cli` while its import package is still `factory` and its console script
is still `ergane` — then assert the version the CLI reports comes from installed
metadata rather than from a literal, by making them differ.

**Acceptance Scenarios**:

1. **Given** the changed `pyproject.toml`, **When** a wheel is built, **Then**
   its distribution name is `ergane-cli` and its version matches the declared
   version.
2. **Given** that wheel, **When** its contents are inspected, **Then** the
   import package is still `factory`, and `personas.yaml` and
   `merge_queue_ruleset.json` are still inside it.
3. **Given** the installed distribution, **When** `ergane --version` runs,
   **Then** the version it prints is the one `importlib.metadata` reports for
   `ergane-cli`, and a test proves this by making the metadata version differ
   from any literal in the source and observing the metadata value win.
4. **Given** a build in which the metadata lookup would fail, **When**
   `--version` runs, **Then** it does not silently report a plausible number —
   it reports that the version is unknown, so a broken install is visible.
5. **Given** the changed tree, **When** the suite runs, **Then** no directory,
   import statement, Temporal namespace, or branch namespace has changed.

---

### User Story 2 - A stranger installs it and it works (Priority: P1)

Someone whose machine has never held this repository installs the built
distribution and gets a working `ergane` command.

**Why this priority**: it is the operator's original question — how do the bits
get to a new box — and it is the only story that tests the artifact rather than
the source.

**Independent Test**: install the built wheel into a clean virtual environment
that has no checkout of this repository on any parent path, then run
`ergane --version` and a command that must read `personas.yaml`. Because the
judge sees only the diff, the run's output is committed as pasted evidence.

**Acceptance Scenarios**:

1. **Given** a clean virtual environment with the wheel installed and no
   repository checkout above it, **When** `ergane --version` runs, **Then** it
   prints the built version and exits zero.
2. **Given** that same environment, **When** a command that resolves the persona
   registry runs, **Then** it reads `personas.yaml` from inside the installed
   package rather than walking to a repository root that does not exist.
3. **Given** that same environment, **When** the evidence is committed, **Then**
   the pasted output shows the interpreter path inside the temporary
   environment, so a reader can tell it was not the development checkout.
4. **Given** a machine with the unrelated `ergane` distribution already
   installed, **When** `ergane-cli` is installed alongside it, **Then** the
   install succeeds — the two distributions are distinct names.

---

### User Story 3 - Publishing is a repeatable act the operator triggers (Priority: P2)

The distribution carries metadata fit for a public index, and there is a
declared, tested path from a version tag to a published artifact — which no
agent ever runs.

**Why this priority**: P2 because US1 and US2 make the artifact correct and
provable; this makes it reachable by `uv install`. It is last because it is the
only irreversible one.

**Independent Test**: run the release path in a mode that produces and validates
the artifact without contacting the real index, and assert the metadata a public
index would display is present and correct.

**Acceptance Scenarios**:

1. **Given** the distribution metadata, **When** it is inspected, **Then** it
   carries a description, a readme, a license, and project URLs that identify
   this project, and does not describe itself in terms confusable with the
   unrelated `ergane` distribution.
2. **Given** the release path, **When** it runs without an index credential,
   **Then** it builds and validates the artifact and stops before publishing,
   rather than failing in a way that leaves a partial release.
3. **Given** the release path, **When** it is inspected, **Then** publishing is
   triggered by an explicit operator action on a version tag, and no dispatched
   agent and no ordinary CI run on a branch can cause a publish.
4. **Given** a version tag, **When** the release path validates it, **Then** a
   tag that disagrees with the declared version is refused before any artifact
   is uploaded.

---

### Edge Cases

- **A publish cannot be undone.** PyPI permits yanking a release but never
  reuse of a name-and-version pair. A wrong version published is burned. This is
  why FR-011 puts publishing behind an operator action and forbids it from any
  automated path an agent can reach.
- The metadata lookup succeeding but returning the *wrong* distribution, because
  both `ergane` and `ergane-cli` are installed in the same environment: the
  lookup names one distribution and must keep naming the right one.
- A test that asserts `--version` "prints something": it passes against the
  hardcoded fallback and proves nothing. US1-S3 exists to force the two values
  apart.
- An editable install (`uv pip install -e .`) resolves metadata differently from
  a wheel install; both must report the same version.
- The `factory` import package colliding with another installed distribution
  that provides a top-level `factory`: accepted, deliberately, as the cost of
  not renaming.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The distribution name MUST be `ergane-cli`.
- **FR-002**: The import package MUST remain `factory`, and no directory,
  module, or import statement may be renamed by this feature.
- **FR-003**: The console script MUST remain `ergane` and MUST resolve to
  `factory.cli.main`.
- **FR-004**: `ergane --version` MUST report the version recorded in the
  installed distribution's metadata.
- **FR-005**: The version MUST have exactly one declared source; no literal
  version string may shadow it.
- **FR-006**: When the installed metadata cannot be read, `--version` MUST say
  the version is unknown and MUST NOT substitute a version-shaped literal.
- **FR-007**: The built distribution MUST contain the persona registry and the
  merge queue ruleset inside the import package.
- **FR-008**: Installing the built distribution into an environment with no
  repository checkout above it MUST yield a CLI that resolves its persona
  registry from inside the package.
- **FR-009**: Distribution metadata MUST carry a description, readme, license,
  and project URLs identifying this project.
- **FR-010**: Distribution metadata MUST NOT be confusable with the unrelated
  `ergane` distribution published on PyPI.
- **FR-011**: Publishing MUST be triggered only by an explicit operator action
  on a version tag. No dispatched agent, and no branch or pull-request CI run,
  may publish.
- **FR-012**: A version tag that disagrees with the declared version MUST be
  refused before any artifact is uploaded.
- **FR-013**: The Temporal namespace and the `factory/<epic>/<node>` branch
  namespace MUST be unchanged.

## Success Criteria

- **SC-001**: The suite's passed and skipped counts equal the pre-change
  baseline; a new skip is a hidden test and fails this criterion.
- **SC-002**: The number of version-shaped string literals in the source that
  can be reported as the CLI's version is zero.
- **SC-003**: `ergane spec landed` returns the same story-to-commit mapping
  before and after the change, proving the attribution grammar was untouched.
- **SC-004**: A wheel installed into a clean environment answers
  `ergane --version` with the built version and resolves `personas.yaml`, with
  the run's output committed as evidence.
- **SC-005**: The count of automated paths that can publish without an operator
  action on a tag is zero.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-013]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-009, FR-010, FR-011, FR-012]
```

US1 owns `pyproject.toml` and `factory/cli/main.py` and must land first — it is
the rename and the version seam together, because the second is broken by the
first. US2 adds an install-time test and touches no source that US1 touched.
US3 works in metadata and a release workflow. US2 and US3 share no file, so they
run beside each other once US1 has merged.

## Open decision — not scoped here

`ergane init` treats `standards` as an optional manifest key, so a stranger who
installs `ergane-cli` and runs `ergane init` can produce a valid `ergane.yaml`
that names no standards document, and dispatch agents with no constitution to
obey. Ergane's own `ergane.yaml:29` names `.specify/memory/constitution.md`; a
fresh repository has no such file.

Three answers are available and the operator has not chosen one: scaffold a
default constitution on `init`, ship a baseline inside the package that a repo
inherits until it writes its own, or accept a standards-less factory as a
legitimate configuration and say so where an operator will read it. This wants
its own spec, and it is the last real gap between "installs" and "works".

## Key Entities

- **Distribution** — `ergane-cli`, the published artifact and the name
  `importlib.metadata` is asked about.
- **Import package** — `factory`, deliberately unchanged.
