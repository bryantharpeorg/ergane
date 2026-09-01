---
state: landed
fixes:
# ATTESTED 2026-08-31 4:16 PM CT by the operator session, in away mode.
# All three stories are on ergane-buildout, each on its first attempt and each on
# the ordinary implementer rung with no promotion: US1 fdddcf6 (#414), US2
# 0976127 (#415), US3 30246c7 (#416). Confirmed by `ergane spec landed <this dir>
# --default-branch ergane-buildout`, which observes all three.
#
# RECOVERED WORK, AND THE LAST OF IT. All three stories were KILLED on 2026-08-31
# by the credential outage — us1 burned four rungs 08:10-08:31Z on 73-byte OAuth
# failures, and us2 and us3 cascaded to KILLED at attempt 0 without ever reaching
# a model. `build reset` cleared the armed node ref at 12:25Z; the roadmap
# re-dispatched the spec at 18:13Z once an operator attestation and a `rescan`
# unparked the line. Every story then passed first attempt.
#
# ATTESTED IMMEDIATELY ON PURPOSE. 120 was the last dispatchable spec in the
# corpus, so leaving it at `ready` with 3/3 landed would have parked the roadmap
# with nothing behind it to reveal the stall — see
# roadmap/a-landed-but-unattested-spec-parks-the-line-and-the-floor-idles-until-an-operator-attests,
# filed today after that exact pattern cost twenty idle minutes on spec 119.
  - init/wiring-non-interactively-rewrites-the-committed-manifest-and-drops-standards-and-ladder
  - init/the-init-verb-cannot-see-the-ladder-block-it-deletes-and-its-own-remedy-recommends-the-deletion
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# A new number: none of the 089-102 slots reserved on 2026-08-23 names this.
#
# DATA LOSS ON A COMMITTED FILE, AND THE DROPPED KEY IS THE ONE THAT INJECTS THE
# CONSTITUTION INTO EVERY NODE. A repository already held a valid committed
# manifest. After `ergane init --wire --non-interactive`, `standards`, the whole
# `ladder` block and about forty lines of comments were gone, and the gates had
# been re-sorted. `init --check` then reported the manifest valid — because
# `standards` is optional — `_read_standards`
# (`factory/verify/factory_yaml.py:459-461`) records that "Absent is not a
# defect: most repos declare no standards document", which is correct schema
# behaviour and is not what this spec changes. Had the
# operator not diffed before committing, every subsequent node would have run
# with no standards document and the default ladder.
#
# THE MECHANISM IS FIVE LINES, AND THE COMMENT ON THEM IS THE DEFECT.
# `_init_default` (`factory/cli/init.py`) reads:
#
#     defaults = _build_defaults(repo_root)
#     # Optional keys have a safe default of "absent".
#     if key in _OPTIONAL_KEYS:
#         return None
#     if key in defaults:
#         return defaults[key]
#
# `_build_defaults` (`:611`) begins `existing = _load_existing_defaults(repo_root)`
# and seeds every key with `existing.get(...)` — so the committed value **is
# computed** and then thrown away, for exactly the optional keys, one line before
# it would have been used. "Absent" is a safe default for a manifest that does
# not exist yet and a destructive one for a manifest that does, and nothing in
# this function knows which case it is in.
#
# TWO KEYS ARE NOT EVEN IN THE VOCABULARY. `_OPTIONAL_KEYS` is
# `("timeouts", "standards", "roadmap", "forge", "writes")` (`:437`). `ladder`
# and `verify` are not in init's key vocabulary at all, so they drop on the
# interactive path too — an operator who answers every question still loses them.
# Measured on this tree 2026-08-29: `factory/cli/init.py` contains the string
# `ladder` **zero** times, while `factory/verify/factory_yaml.py` — which parses
# it as a v2 top-level key (`:116`) and enumerates its dials (`:126`) — contains
# it twenty-nine. The writer cannot see the key the reader requires.
#
# AND THE VERB'S OWN GUIDANCE RECOMMENDS THE DESTRUCTIVE ACT. `init.py:921`
# prints "github wiring: not attempted — re-run with `ergane init --wire` to
# queue the landing branch and require one check per declared gate". `--wire` is
# the command that strips the block. An operator following the tool's advice
# destroys the configuration the tool is advising them to complete, and US1
# closes this without editing that text: once a valid manifest is left
# byte-identical, the recommendation stops being dangerous.
#
# THE LOSS ERASES ITS OWN EVIDENCE, which is why this is critical rather than
# merely bad. The block is deleted; the Temporal schedule is then reconciled
# against the stripped manifest, so the two agree; and `--check` reports the
# repository healthy because both sides moved together. Measured by the reporter
# at 161 lines reduced to 9. Nothing in the loop can tell a repo that was never
# configured from one that was configured and then flattened.
#
# AND THE WRITE CANNOT PRESERVE COMMENTS. The manifest is emitted through
# `yaml.safe_dump` (`:605`), which discards every comment and re-sorts keys. Even
# a rewrite that carried every value forward would destroy the forty lines of
# operator prose that explain why those values are what they are.
#
# THE ADDENDUM IS ITS OWN DEFECT. The non-interactive path cannot reconcile a
# roadmap dial at all: it rewrites the manifest without the roadmap block, then
# compares the schedule against the rewritten manifest and prints "already
# satisfied". It is comparing the world to its own edit. Only the interactive
# path reconciled it, and it too stripped every comment.
#
# NOT IN SCOPE. This spec does not change the manifest schema, does not make
# `standards` mandatory, does not add a key to `_OPTIONAL_KEYS`, and does not
# replace the YAML emitter with a round-tripping one — preserving comments
# through a rewrite is a larger change than not rewriting, and US1 makes it
# unnecessary in the overwhelmingly common case.
---

# Feature Specification: an init that finds a manifest keeps it

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

`ergane init --wire` treats an existing manifest as a thing to regenerate rather
than a thing to read. Three failures follow, in descending order of how much they
destroy:

1. **Optional keys are dropped rather than carried.** The existing value is
   computed and discarded one line before use, and `standards` — the key that
   puts the constitution in front of every agent — is among them.
2. **Two keys are invisible to init entirely.** `ladder` and `verify` are not in
   its vocabulary, so they are lost on every path, interactive included.
3. **Comments cannot survive a rewrite.** The emitter discards them by
   construction.

And `init --check` cannot catch any of it, because a manifest missing an optional
key is valid.

## The rule this spec is asking for

**A verb asked to wire a repository does not rewrite a manifest that is already
valid, and a rewrite it does perform loses nothing it did not ask about.**

### What this spec is not

It is not a schema change. No key becomes mandatory, and `_OPTIONAL_KEYS` keeps
its members — what changes is what "optional" means when a value already exists.

It is not a round-tripping YAML emitter. Preserving comments through a rewrite is
a larger change than not rewriting, and US1 removes the need in the common case.
US2 covers the case where a rewrite is genuinely required.

It is not a reconciliation feature. US3 fixes a comparison that reads its own
edit; it does not add new reconciliation behaviour.

## User Scenarios & Testing

### User Story 1 - A valid manifest is not rewritten (Priority: P1)

As an operator, wiring a repository that already has a working manifest leaves
that manifest alone.

**Why this priority**: P1 and it depends on nothing. It is the fix with the
largest blast radius and the smallest surface — and it makes the comment problem
disappear rather than solving it.

**Acceptance Scenarios**:

1. **Given** a repository holding a valid manifest, **When** `ergane init --wire`
   runs, **Then** the manifest file is byte-identical afterwards, comments
   included — proven by a committed test.
2. **Given** that repository, **When** the same command runs, **Then** the wiring
   work it was asked to do still happens — proven by a committed test. Not
   rewriting the manifest is not declining the job.
3. **Given** a repository holding no manifest, **When** the command runs,
   **Then** one is written exactly as it is today — proven by a committed test.
4. **Given** a repository holding a manifest the schema refuses, **When** the
   command runs, **Then** the operator is told what is wrong and the file is not
   silently replaced — proven by a committed test. An invalid manifest is a
   conversation, not a licence to overwrite.

### User Story 2 - A rewrite carries everything forward (Priority: P1)

As an operator, when init does write a manifest over an existing one, nothing I
had is silently absent afterwards.

**Why this priority**: P1. US1 covers the common case; this covers the case where
a rewrite is genuinely required, and it is the mechanism the data loss came
through.

**Acceptance Scenarios**:

1. **Given** an existing manifest declaring `standards`, **When** a rewrite
   occurs on the non-interactive path, **Then** the rewritten manifest still
   declares it with the same value — proven by a committed test.
2. **Given** an existing manifest declaring `ladder` and `verify`, **When** a
   rewrite occurs on either path, **Then** both survive — proven by a committed
   test. Neither is in init's vocabulary today and both are lost on every path.
3. **Given** an existing manifest carrying a key init does not recognise,
   **When** a rewrite occurs, **Then** the verb refuses naming the key rather
   than dropping it — proven by a committed test.
4. **Given** no existing manifest, **When** one is written, **Then** optional
   keys are absent exactly as they are today — proven by a committed test.
   "Absent" stays the right default for a manifest that does not exist.
5. **Given** a rewrite that will lose comments, **When** it is about to happen,
   **Then** the operator is told before the write — proven by a committed test.
6. **Given** a repository whose manifest declares a `ladder` block, **When** the
   operator follows the guidance at `factory/cli/init.py:921` and re-runs with
   `--wire`, **Then** the `ladder` block is still present afterwards — proven by
   a committed test. The verb's own remedy currently recommends the command that
   deletes it.
7. **Given** that same repository after the re-run, **When** `init --check`
   runs, **Then** it reports the state the manifest is actually in — proven by a
   committed test. Today the schedule is reconciled to the stripped file, so
   both sides agree and the check calls a flattened repository healthy.

### User Story 3 - The roadmap dial is reconciled against the file, not the rewrite (Priority: P2)

As an operator, the non-interactive path compares my schedule against my manifest
rather than against the manifest it just produced.

**Why this priority**: P2. It changes no file, but it makes a reconciliation
report that is currently meaningless mean something.

**Acceptance Scenarios**:

1. **Given** a manifest declaring a roadmap dial and a schedule disagreeing with
   it, **When** the non-interactive path reconciles, **Then** the disagreement is
   reported — proven by a committed test. It currently prints "already
   satisfied".
2. **Given** a manifest and schedule that agree, **When** reconciliation runs,
   **Then** it reports agreement — proven by a committed test.
3. **Given** a manifest declaring no roadmap dial, **When** reconciliation runs,
   **Then** it says so rather than comparing against a default — proven by a
   committed test.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

All three change `factory/cli/init.py` and are serialised on file ownership
rather than on logic.

## Requirements

- **FR-001**: `ergane init --wire` MUST leave an existing valid manifest
  byte-identical.
- **FR-002**: The wiring work MUST still be performed when the manifest is left
  alone.
- **FR-003**: A repository with no manifest MUST have one written exactly as
  today.
- **FR-004**: An existing manifest the schema refuses MUST produce a report and
  MUST NOT be silently replaced.
- **FR-005**: A rewrite MUST carry forward every value the existing manifest
  declared, including optional keys.
- **FR-006**: A rewrite MUST preserve `ladder` and `verify`, which init does not
  currently recognise.
- **FR-007**: A rewrite encountering an unrecognised key MUST refuse naming it.
- **FR-008**: Writing a manifest where none existed MUST leave optional keys
  absent, as today.
- **FR-009**: A rewrite that will discard comments MUST say so before writing.
- **FR-010**: Roadmap reconciliation MUST compare the schedule against the
  manifest on disk.

## Success Criteria (summary)

- An operator can run `init --wire` on a configured repository and commit the
  result without diffing it first.
- No node ever runs without a standards document because a wiring verb removed
  the key that names it.
- A reconciliation report that says "already satisfied" means the schedule and
  the operator's manifest agree.
