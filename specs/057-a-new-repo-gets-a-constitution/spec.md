---
state: ready
# FLIPPED READY 2026-09-02 9:20 PM CT, after a pre-dispatch refinement pass
# against ergane-buildout at `5fa87c2`. The operator approved the flip.
#
# THE PASS FOUND MORE THAN ANCHOR ROT, and this is why it ran. Sixteen anchors
# were re-read; FIFTEEN had moved in the fifteen days since drafting, and
# `ergane spec validate` refused on exactly ONE of them, because the other
# fourteen still resolved to real, non-blank, plausible lines. Line 251 of the
# init module, cited as the standards prompt text, now resolves to a subprocess
# keyword argument. `_default_gate_command` — the function US2's whole premise
# generalises — does not exist any more; it is `_default_gates`, and it returns
# a mapping instead of a rendered YAML line.
#
# THE FIND THAT WOULD HAVE COST AN ATTEMPT: spec 120 landed 2026-09-01 on this
# spec's exact code, and fixed the OTHER half of the same area.
# `120-an-init-that-finds-a-manifest-keeps-it` stopped `init` discarding a
# *committed* `standards` value on re-run. This spec gives a repository that
# never had one a document to point at. 120's own comment states the boundary in
# its own words — the remaining `None` is "reached only when the repository
# declared nothing for this key ... (FR-008: a fresh repository still gets
# nothing)". 120 also records that empty-answer-means-omit is "unchanged by
# 120 US2 and deliberately so". An implementer reading only the code would have
# re-implemented 120 or argued with it. It is now plan trap 1, the first thing
# in the traps list, and the tasks that touch that region point at it.
#
# ALSO RESOLVED SINCE DRAFTING: the 056 file-collision warning is stale. Both
# `056-the-factory-ships-as-a-package` and `104` have landed and both edited the
# force-include block, which now carries three entries at `pyproject.toml:73-76`.
# No in-flight competitor for that file. The pattern this spec copies is now
# proven three times over rather than once.
#
# Validate is green with zero refusals and zero advisories, including the
# anchor-resolution and symbol-anchor layers that 072 landed the day before.
#
# RESCOPED 2026-08-18 5:50 PM CT on the operator's ruling: "these should be
# default but overridable so they're more example templates."
#
# Two changes follow, and the first is a change of stance rather than of code.
#
#   1. THE SEEDED DOCUMENT IS A STARTING POINT, NOT A FLOOR. Mechanically it was
#      always overridable -- FR-002 says init never touches an existing document,
#      so from the moment it is written the file is the user's to edit or delete.
#      What was wrong was the framing: "invariant floor" and a wall of MUSTs read
#      as binding, and a user who feels dictated to deletes the whole file
#      including the two principles that would actually have helped them. So the
#      seeded text now carries a WHY per principle (FR-016), and the two that
#      follow from the factory's mechanics are stated as CONSEQUENCES -- here is
#      what happens if you remove this -- rather than as obligations (FR-017).
#      Persuasion survives deletion; assertion does not.
#   2. BRING YOUR OWN TEMPLATE. `init` accepts an operator-supplied template
#      source and seeds from it in preference to the shipped default (FR-018,
#      new US4). This is the no-lock-in principle applied to standards: a team
#      with its own constitution should not have to accept ours first and edit
#      it down. The shipped default becomes what you get when you have nothing,
#      which is the honest description of a default.
#
# The term "invariant floor" is retired throughout in favour of "default floor".
# Nothing about which principles ship changed -- only whether they are presented
# as law or as a recommendation the user is trusted to weigh.
#
# --- original drafting note ---
# Drafted 2026-08-18 ~11:10 AM CT from the operator's instruction: "ergane init
# should establish a constitution if it doesn't exist. the constitution should
# be scalable by teck stack or repo type. ideally give some seed data."
#
# This closes the open decision recorded in 056 and in 054's wake: `ergane init`
# treats `standards` as an optional manifest key (`factory/cli/init.py:251,262`,
# where empty answers for optional keys mean "omit"), so a stranger can today
# produce a valid `ergane.yaml` that names no standards document and dispatch
# agents with nothing to obey. The interview already asks for the path. It
# cannot create what the path names.
#
# Two operator decisions were taken before this was written, and they are the
# spine of the spec rather than details inside it:
#
#   1. A seeded constitution is an INVARIANT FLOOR + a STACK LAYER + the user's
#      own section. Ergane always seeds the principles that follow from Ergane
#      being the builder, because a factory whose judge reads only the diff
#      requires "provable from the diff" no matter what language the repo is in.
#      The stack layer is chosen for the repo. Everything above is the user's.
#   2. It is written wherever the manifest's `standards` key points, defaulting
#      to `.specify/memory/constitution.md` — one convention across Ergane and
#      every target repo — and the manifest's key is set to that path.
#
# A third fact was established by reading Ergane's own constitution, and it
# changes the implementation more than either decision: the floor CANNOT be
# produced by copying `.specify/memory/constitution.md` and deleting the
# Ergane-specific principles. Ergane's principles I and III each mix an
# invariant rule with Ergane-specific content inside a single principle -- I's
# rule is "each component ships as a small vertical slice with tests before the
# next begins", but its body names specs 003/004/005 and D-024; III's rule is
# "no dependency without approval", but its body is Ergane's own approved
# roster. The floor is AUTHORED generic. It is not a filtered snapshot.
depends_on_landed: [034-ergane-init, 050-init-preconditions]
---

# Feature Specification: a new repo gets a constitution

**Feature Branch**: `057-a-new-repo-gets-a-constitution`

**Created**: 2026-08-18

## Why a factory has to seed this

Ergane dispatches agents against a target repository and holds them to the
document the manifest's `standards` key names. Today that key is optional, so
the reachable end state is a repository Ergane will happily build in, with no
standards at all. The agents still run; nothing binds them.

That is not a gap in documentation. Two of Ergane's own principles are not
arbitrary taste — they are consequences of how the factory works, and a repo
that lacks them will produce work the factory cannot score. They are still the
user's to delete; deleting them just has a knowable price, and the seeded
document says what it is:

- **Acceptance criteria must be provable from the diff.** The judge is handed
  the story's diff and the criteria snapshot, and nothing else — no base tree,
  no commit message, no terminal, no running system. A repo whose criteria name
  a CI observation has written criteria that correct, complete work will fail,
  and no number of attempts can change that.
- **Work arrives as vertical slices with tests first.** The work graph
  dispatches one story at a time and the gates run tests against what comes
  back. A story that is not a testable slice is not a thing this factory can
  land.

Those hold in Python, in Go, in a repo Ergane has never seen. Ergane seeds them
because it is the party that knows them — and states why, because a rule a user
understands survives the first time it is inconvenient and a rule they resent
does not.

## The three layers

Everything seeded is a **default**: shipped because a repository that has nothing
is worse off than one that has this, and editable from the moment it is written.
The document belongs to the repository, not to Ergane.

| Layer | Who authors it | Seeded? |
| --- | --- | --- |
| **Default floor** — principles that follow from Ergane being the builder | Ergane, authored generic | Yes, unless a template source is supplied |
| **Stack layer** — toolchain, test command, lint and type gates, dependency policy | Ergane, chosen per stack | Yes, from the detected or declared stack |
| **Project principles** — what this project believes | The user | Never — seeded as an empty, named section |
| **Governance** — how the document is amended | Ergane, authored generic | Yes |

Supply your own template and Ergane seeds that instead (US4). The shipped
default is what you get when you have nothing, which is the only thing a
default should ever be.

**The Ergane-product principles are never seeded into another repository.**
Determinism at the Core, Spend Is Attributed, and Personas Over Model Tiers
describe how Ergane itself is built. They bind the factory, not its targets, and
copying them into a stranger's repo would be Ergane mistaking its own source for
everyone's.

## What the floor is not

**Not a snapshot of Ergane's constitution with principles removed.** As recorded
in the frontmatter, Ergane's principles I and III each carry a generic rule and
Ergane-specific content in the same body. A filtered copy would seed spec
numbers and a dependency roster into repositories they mean nothing in. The
floor is authored as generic text, once, and lives as data the package ships.

**Not binding.** Ergane holds agents to whatever the `standards` key names, and
after `init` that document is the repository's own. A user who deletes half the
seeded principles gets a factory that obeys the remaining half. The two that
follow from the factory's mechanics say what deleting them costs; they do not
prevent it, and nothing in this feature re-imposes them on a later run.

**Not the only source.** A team that already has a constitution can point `init`
at it and never see Ergane's (US4).

---

## User Scenarios & Testing

### User Story 1 - A repo with no standards document gets one (Priority: P1)

An operator runs `ergane init` in a repository that has no standards document,
and finishes with one: the default floor and governance, at the path the
manifest names, with the manifest's `standards` key pointing at it — and it
reads as a starting point they are expected to edit, not as terms imposed.

**Why this priority**: it is the whole defect. Everything else in this spec
makes the seeded document better; this one makes it exist.

**Independent Test**: run `init` against a repository fixture with no standards
document; a constitution appears at the manifest's `standards` path carrying the
floor principles, and the written `ergane.yaml` names that path. Run it again
against a repository that already has one and assert the existing file is
returned unchanged, byte for byte.

**Acceptance Scenarios**:

1. **Given** a repository with no standards document, **When** `ergane init`
   runs, **Then** a constitution is written at the manifest's `standards` path
   and the manifest's `standards` key names it.
2. **Given** no `standards` path declared in the interview, **When** the
   constitution is written, **Then** it goes to
   `.specify/memory/constitution.md` and the manifest records that path — the
   key is no longer omittable into nothing.
3. **Given** a repository that already has a standards document, **When**
   `ergane init` runs, **Then** the existing file is left byte-identical and the
   command says it found one rather than replacing it.
4. **Given** the seeded constitution, **When** it is read, **Then** it contains
   the default floor and a governance section, and contains none of
   Ergane's product-specific principles and no Ergane spec number, decision id,
   or dependency roster.
5. **Given** `ergane init --check` on a repository with no standards document,
   **When** it runs, **Then** it reports the absence as a readiness finding and
   writes nothing.
6. **Given** the seeded constitution, **When** any principle in it is read,
   **Then** that principle carries a one-line statement of why it is there, so
   a reader can decide whether to keep it without reading Ergane's source.
7. **Given** the two principles that follow from the factory's own mechanics,
   **When** they are read, **Then** each states what happens if it is removed
   rather than asserting that it must not be — and the document says plainly
   that it is the repository's file to edit.

---

### User Story 2 - The constitution fits the repo it is written into (Priority: P1)

The seeded document carries a stack layer — toolchain, test command, lint and
type gates, dependency policy — chosen for the repository rather than copied
from Ergane's.

**Why this priority**: a floor with no stack layer names no command an agent can
run. This is what "seed data" means, and it is what makes the document useful
rather than merely present.

**Independent Test**: seed against fixtures for each shipped stack and assert
each produces its own toolchain and commands; seed against a repository matching
no shipped stack and assert a language-agnostic layer is produced rather than a
wrong one.

**Acceptance Scenarios**:

1. **Given** a repository whose marker files identify a shipped stack, **When**
   `init` runs, **Then** the stack layer written is that stack's, and the
   detected stack is stated to the operator before it is used.
2. **Given** a detected stack the operator disagrees with, **When** they say so
   in the interview, **Then** their choice is used and detection is overridden.
3. **Given** a repository matching no shipped stack, **When** `init` runs,
   **Then** a language-agnostic stack layer is written, and the document says
   plainly which parts the user must complete.
4. **Given** any shipped stack pack, **When** it is seeded, **Then** every
   command it names is a real command for that toolchain, and no pack names a
   tool from another stack.
5. **Given** the shipped stack packs, **When** a new one is added, **Then** it
   is added as data without changing the code that selects or writes it.

---

### User Story 3 - A seeded floor's age is visible (Priority: P2)

The seeded document records which version of the floor produced it, so a
repository whose floor has fallen behind can be told so.

**Why this priority**: P2 because US1 and US2 deliver the feature. This is what
stops it rotting: Ergane's standards are promoted into as defect classes recur,
so a floor seeded today is a snapshot, and a snapshot nobody can date is a
snapshot nobody can fix.

**The report is advisory and must read that way.** Being behind is not a defect,
because the seeded document is a default the repository has since made its own —
a user who edited every principle deliberately is "behind" and correct. The
check says *newer starter material exists*, names both versions, changes
nothing, and never affects whether the repository is ready to build.

**Independent Test**: seed a repository, bump the floor version, and assert
`ergane init --check` reports the repository's floor as behind, naming both
versions and changing nothing.

**Acceptance Scenarios**:

1. **Given** a seeded constitution, **When** it is read, **Then** it records the
   floor version it was produced from, in a form a machine can read and a human
   can see.
2. **Given** a repository whose recorded floor version is older than the
   installed one, **When** `ergane init --check` runs, **Then** it reports the
   repository as behind, names both versions, and writes nothing.
3. **Given** a repository whose standards document was written by hand and
   records no floor version, **When** `--check` runs, **Then** it says the floor
   version is unknown and does not claim the repository is behind.
4. **Given** a repository already at the installed floor version, **When**
   `--check` runs, **Then** it reports the floor as current.
5. **Given** a repository reported as behind, **When** its readiness is
   evaluated, **Then** it is still ready — an out-of-date floor is information,
   never a blocker, and no dispatch is refused because of one.

---

### User Story 4 - A team brings its own template (Priority: P2)

An operator who already has a constitution — their own, their company's, one
from another project — points `ergane init` at it and gets that seeded, without
ever seeing Ergane's default.

This is the no-lock-in principle applied to standards. A team with existing
practice should not have to accept ours and edit it down; the shipped floor is
what you get when you have nothing, and "when you have nothing" is the whole of
its claim. The same seam serves stack packs: a template source may carry its own
packs, and where it does not, the shipped ones still apply.

**Why this priority**: P2 because US1 must first learn to write a document at
all, and because most repositories genuinely have nothing — the default is the
common case and this is the escape from it. It is not P3 because a factory that
can only seed its author's opinions is exactly the lock-in this project says it
does not do.

**Independent Test**: point `init` at a template source and assert the seeded
document is that template's content and contains none of the shipped default's;
point it at a source that does not exist and assert a refusal at interview time
naming the path; supply no source and assert the shipped default is used.

**Acceptance Scenarios**:

1. **Given** an operator-supplied template source, **When** `init` seeds a
   repository, **Then** the written document comes from that source and
   contains none of the shipped default's text.
2. **Given** no template source, **When** `init` seeds a repository, **Then**
   the shipped default is used — resolution order is supplied, then shipped.
3. **Given** any seeding run, **When** it completes, **Then** the source that
   produced the document is stated to the operator and recorded in the document
   itself, so a reader can tell whose standards these are.
4. **Given** a template source that does not exist, is unreadable, or is empty,
   **When** the interview evaluates it, **Then** it is refused there, naming the
   path — not at write time, and never by silently falling back to the default.
5. **Given** a supplied template that carries its own stack packs, **When**
   a stack is selected, **Then** its packs are preferred and the shipped packs
   fill only what it does not provide.

---

### Edge Cases

- **A seeded constitution is the user's file from the moment it is written.**
  It is content the operator consented to, not Ergane bookkeeping, so `forget`
  must leave it in place. This narrows the previously stated guarantee that
  `forget` leaves a tree byte-identical: it leaves *Ergane's own* artifacts
  removed and the user's content untouched, and the difference must be stated
  where an operator will read it.
- A `standards` path pointing outside the repository, or at a directory:
  refused at interview time, not at write time.
- A `standards` path inside a directory that does not exist yet: created, since
  `.specify/memory/` will not exist in a brownfield repo.
- A repository with an *empty* standards file: it exists, so it is not
  overwritten — an empty file is a choice, and silently filling it is the
  overwrite this spec forbids.
- Two markers for different stacks in one repository (a `pyproject.toml` beside
  a `package.json`): detection reports ambiguity and asks rather than picking.
- **Ergane's own repository must be unaffected.** It already has a constitution
  and running `init` here must not touch it — the US1-S3 path is the one that
  protects it, and it is the case most likely to be tested carelessly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ergane init` MUST write a standards document when the repository
  has none.
- **FR-002**: `ergane init` MUST NOT modify an existing standards document.
- **FR-003**: The written document MUST be placed at the manifest's `standards`
  path, defaulting to `.specify/memory/constitution.md`, and the manifest's
  `standards` key MUST name that path.
- **FR-004**: The written document MUST contain the default floor and a
  governance section.
- **FR-005**: The default floor MUST be authored generic text carried as
  package data, and MUST NOT contain Ergane spec numbers, decision ids, or
  dependency rosters.
- **FR-006**: Ergane's product-specific principles MUST NOT appear in a seeded
  document.
- **FR-007**: The written document MUST contain a stack layer selected for the
  repository.
- **FR-008**: The stack MUST be detected from repository markers, stated to the
  operator, and overridable by them.
- **FR-009**: A repository matching no shipped stack MUST receive a
  language-agnostic stack layer that names what the user must complete.
- **FR-010**: Stack packs MUST be data, such that adding one requires no change
  to the code that selects or writes them.
- **FR-011**: The written document MUST record the floor version that produced
  it.
- **FR-012**: `ergane init --check` MUST report a repository whose recorded
  floor version is behind the installed one, and MUST write nothing.
- **FR-013**: `ergane init --check` MUST report a missing standards document as
  a readiness finding.
- **FR-014**: A standards document with no recorded floor version MUST be
  reported as unknown rather than as behind.
- **FR-015**: `forget` MUST leave a seeded standards document in place.
- **FR-016**: Every principle in the written document MUST carry a one-line
  statement of why it is there, so a reader can weigh it without reading
  Ergane's source.
- **FR-017**: The principles that follow from the factory's own mechanics MUST
  be written as consequences — what happens if this is removed — rather than as
  obligations, and the document MUST say that it is the repository's to edit.
  Nothing in this feature may re-impose a principle a user has removed.
- **FR-018**: `ergane init` MUST accept an operator-supplied template source and
  seed from it in preference to the shipped default. Resolution order MUST be
  supplied-then-shipped; the source used MUST be stated to the operator and
  recorded in the written document; and a supplied source that is missing,
  unreadable, or empty MUST be refused at interview time naming the path, never
  by falling back to the default.
- **FR-019**: The `--check` report of an out-of-date floor MUST be advisory: it
  MUST NOT affect whether a repository is ready, and MUST NOT be phrased as
  non-compliance.

## Success Criteria

- **SC-001**: The number of ways `ergane init` can complete against a repository
  that ends with no standards document is zero.
- **SC-002**: Running `ergane init` in this repository leaves
  `.specify/memory/constitution.md` byte-identical.
- **SC-003**: Every shipped stack pack names only commands valid for its own
  toolchain, checked mechanically rather than by reading.
- **SC-004**: Adding a stack pack changes no file outside the pack data.
- **SC-005**: A repository seeded at floor version N, checked against installed
  floor version N+1, is reported as behind, is not modified, and is still
  reported ready to build.
- **SC-006**: The number of principles in the seeded document that carry no
  statement of why they are there is zero.
- **SC-007**: A repository seeded from an operator-supplied template contains
  none of the shipped default's text, and names its source in the document.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-013, FR-015, FR-016, FR-017]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-011, FR-012, FR-014, FR-019]
US4:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-018]
```

US1 owns the write path and the floor data — where the document goes, what is
always in it, how it is worded, and the refusal to overwrite. US2 adds stack
selection and the packs; US3 adds the version marker and the check; US4 adds the
template source. All three merge-depend on US1 because all three extend the
document US1 first learns to write, and they touch disjoint surfaces from each
other: US2 works in detection and pack data, US3 in the marker and `--check`,
US4 in source resolution and the interview.

**FR-016 and FR-017 belong to US1, not to a later story, and this is deliberate.**
They govern how the seeded text is *worded* — a why per principle, consequences
rather than obligations — and the floor text is authored once, in US1. Bolting
the rationale on afterwards means authoring the floor twice and reviewing it
twice, and the second pass is the one that gets skipped.

## Key Entities

- **Default floor** — generic principles that follow from Ergane being the
  builder; package data, versioned, seeded unless a template source is supplied,
  and the repository's to edit from the moment it lands.
- **Stack pack** — toolchain, commands and dependency policy for one stack;
  package data, addable without code change.
- **Template source** — an operator-supplied constitution or pack directory that
  displaces the shipped default for this repository.
- **Floor version** — the marker a seeded document carries so its age is legible.
